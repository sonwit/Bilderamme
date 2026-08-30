#!/usr/bin/env python3
"""
frame_server.py — HTTP-server på hjemmeserveren (192.168.1.38) for Fugleramme.

To bruksmåter:
  1) WEBAPP  — åpne http://192.168.1.38:8090/ i nettleseren: galleri over alle
     genererte bilder, "send til rammen"-knapp per bilde, og et skjema for å lage
     nye bilder (emne + stil + valgfritt referanse/seed-bilde for bilde-til-bilde).
  2) API/Siri — POST /generate med et emne (se Siri-snarvei i docs/).

Endepunkter:
  GET  /                web-appen (galleri + generer-skjema)
  GET  /api/images      JSON: liste over arkiverte bilder (nyeste først)
  GET  /arkiv/<fil>     serverer et arkivert bilde
  POST /api/generate    JSON {emne, stil?, seeds?[]}  -> generer + send
  POST /api/send        JSON {name}                   -> send et arkivbilde på nytt
  GET/POST /generate    emne i body (Skjema/JSON/tekst) eller ?emne=  (Siri)
  GET/POST /daily       dagens standardbilde (som cron)
  GET  /status          hva serveren jobber med akkurat nå
  GET  /help            kort tekst-hjelp

Den tunge jobben (Gemini + dithering + push til rammen) kjøres i en bakgrunnstråd,
og bare én jobb kjøres om gangen. Rammen spiller et "pling" når bildet lander.

Miljøvariabler:
  GEMINI_API_KEY   kreves      FRAME_HOST  rammens adresse (default fugleramme.local)
  FRAME_SERVER_PORT (8090)     FRAME_TOKEN valgfri delt hemmelighet (?token=... )

Kjør som systemd-tjeneste, se deploy/fugleramme-frame-server.service.
"""
import os
import sys
import json
import time
import base64
import threading
import traceback
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PIL import Image

# Importer nabo-scriptene uansett hvor serveren kjøres fra.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_daily_image as gen
from push_to_frame import post_frame, SendFailed, DEFAULT_HOST

# Ett sted for defaulten: push_to_frame.DEFAULT_HOST. (Den stod hardkodet til
# en IP her, og da rammen fikk ny DHCP-leie 2026-08-26 gikk webappen/Siri rett
# i "No route to host" mens push_to_frame.py fra cron var uberoert.)
FRAME_HOST = os.environ.get("FRAME_HOST", DEFAULT_HOST)
FRAME_PATH = os.environ.get("FRAME_PATH", os.path.join(gen.OUTPUT_DIR, "frame.bin"))
PORT = int(os.environ.get("FRAME_SERVER_PORT", "8090"))
TOKEN = os.environ.get("FRAME_TOKEN")

MAX_SUBJECT_LEN = 300
MAX_SEEDS = 3
SEED_MAX_PX = 1024

_busy = threading.Lock()
_state = {"status": "idle", "last": ""}


# ----------------------------------------------------------------------
# Arkiv-hjelpere
# ----------------------------------------------------------------------

def _subject_from_name(fn):
    base = fn[:-4] if fn.lower().endswith(".png") else fn
    parts = base.split("_", 2)          # dato, tid, slug
    slug = parts[2] if len(parts) >= 3 else base
    if slug == "dagens":
        return "Dagens bilde"
    return (slug.replace("-", " ").strip().capitalize()) or slug


def _when_from_name(fn):
    parts = fn.split("_")
    if len(parts) >= 2 and len(parts[1]) >= 4:
        return f"{parts[0]} {parts[1][:2]}:{parts[1][2:4]}"
    return ""


def _archive_list():
    d = gen.ARCHIVE_DIR
    items = []
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if not fn.lower().endswith(".png"):
                continue
            p = os.path.join(d, fn)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                mt = 0
            items.append({
                "name": fn,
                "url": "/arkiv/" + fn,
                "subject": _subject_from_name(fn),
                "when": _when_from_name(fn),
                "mtime": mt,
            })
    # Filnavnet starter med "YYYY-MM-DD_HHMMSS" som sorterer kronologisk leksikalsk
    # -- mer stabilt enn mtime (som endres hvis filer kopieres). Nyeste foerst.
    items.sort(key=lambda x: x["name"], reverse=True)
    return items


def _prepare_from_archive(name):
    """Last et arkivert bilde, gjør det klart i panel-format og skriv frame.bin."""
    safe = os.path.basename(name)
    if not safe.lower().endswith(".png"):
        raise ValueError("ugyldig filnavn")
    path = os.path.join(gen.ARCHIVE_DIR, safe)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"fant ikke {safe} i arkivet")
    img = Image.open(path).convert("RGB")
    img = gen.fit_to_screen(img)
    preview, framebuf = gen.to_epaper(img)
    os.makedirs(gen.OUTPUT_DIR, exist_ok=True)
    tmp = os.path.join(gen.OUTPUT_DIR, "frame.bin.tmp")
    with open(tmp, "wb") as f:
        f.write(framebuf)
    os.replace(tmp, os.path.join(gen.OUTPUT_DIR, "frame.bin"))
    preview.save(os.path.join(gen.OUTPUT_DIR, "preview.png"))
    img.save(os.path.join(gen.OUTPUT_DIR, "original.png"))


def _decode_seed(s):
    """base64 / data-URL -> PIL.Image (nedskalert). Returnerer None for tomt."""
    if not s:
        return None
    s = s.strip()
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    img = Image.open(BytesIO(base64.b64decode(s))).convert("RGB")
    img.thumbnail((SEED_MAX_PX, SEED_MAX_PX))
    return img


# ----------------------------------------------------------------------
# Jobbkjøring (én om gangen, i bakgrunnen)
# ----------------------------------------------------------------------

def _push_with_retries(retries=4, delay=15):
    last = None
    for attempt in range(1, retries + 1):
        try:
            outcome, code, info = post_frame(FRAME_PATH, FRAME_HOST)
        except (SendFailed, ValueError, OSError) as e:
            last = str(e)
            if attempt < retries:
                time.sleep(delay)
            continue
        if outcome == "unconfirmed":
            return True, "sendt (ubekreftet — kjent firmware-snurr, tegnes som regel fint)"
        if code == 200:
            return True, "sendt og bekreftet"
        last = f"HTTP {code}: {info}"
        if attempt < retries:
            time.sleep(delay)
    return False, last or "ukjent feil"


def _launch(prepare, busy_label, reply_msg):
    """Ta busy-låsen (om ledig), kjør prepare()+push i bakgrunnstråd. Returnerer
    (http_status, tekst). prepare() skal skrive frame.bin; push skjer etterpå."""
    if not _busy.acquire(blocking=False):
        return 409, f"Rammen holder på med noe allerede ({_state['status']}). Prøv igjen om et lite minutt."

    def worker():
        try:
            _state["status"] = busy_label
            prepare()
            _state["status"] = f"sender til rammen ({busy_label})"
            ok, info = _push_with_retries()
            _state["last"] = f"{'OK' if ok else 'FEIL'}: {busy_label} — {info}"
            print(_state["last"], flush=True)
        except Exception as e:  # noqa: BLE001 — slipp alltid låsen
            msg = str(e)
            if getattr(gen, "_is_transient", None) and gen._is_transient(e):
                friendly = "Gemini er overbelastet akkurat nå (prøvde flere ganger). Vent litt og prøv igjen."
            else:
                friendly = msg
            _state["last"] = f"FEIL: {busy_label} — {friendly}"
            print(f"FEIL: {busy_label} — {msg}", flush=True)
            traceback.print_exc()
        finally:
            _state["status"] = "idle"
            _busy.release()

    threading.Thread(target=worker, daemon=True).start()
    return 202, reply_msg


def _start(subject, style=None, ref_images=None):
    """Generer et bilde (emne og/eller referansebilder) og send til rammen."""
    if subject:
        subject = subject.strip()[:MAX_SUBJECT_LEN].strip() or None
    if subject:
        label = subject
        reply = f"Tegner et bilde av {subject}. Det er klart på skjermen om omtrent ett minutt."
    elif ref_images:
        label = "bilde fra referanse"
        reply = "Tegner et bilde fra referansebildet. Klart på skjermen om omtrent ett minutt."
    else:
        label = "dagens bilde"
        reply = "Tegner dagens bilde. Det er klart på skjermen om omtrent ett minutt."
    return _launch(lambda: gen.run(subject=subject, style=style, ref_images=ref_images),
                   f"genererer: {label}", reply)


def _start_send(name):
    return _launch(lambda: _prepare_from_archive(name),
                   f"sender arkivbilde: {name}",
                   f"Sender bildet til rammen. Klart på skjermen om ~30 sekunder.")


# ----------------------------------------------------------------------
# HTTP-handler
# ----------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Fugleramme/2.0"

    # --- svar-hjelpere ---
    def _reply(self, code, text, ctype="text/plain; charset=utf-8"):
        body = text.encode("utf-8") if isinstance(text, str) else text
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _reply_json(self, code, obj):
        self._reply(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _authorized(self, query):
        if not TOKEN:
            return True
        return query.get("token", [None])[0] == TOKEN or self.headers.get("X-Token") == TOKEN

    def _serve_archive(self, name):
        safe = os.path.basename(name)
        if not safe.lower().endswith(".png"):
            return self._reply(404, "ikke funnet")
        path = os.path.join(gen.ARCHIVE_DIR, safe)
        if not os.path.isfile(path):
            return self._reply(404, "ikke funnet")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

    # --- GET ---
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        if path.startswith("/arkiv/"):
            if not self._authorized(query):
                return self._reply(401, "Mangler eller feil token.")
            return self._serve_archive(path[len("/arkiv/"):])
        path = path.rstrip("/") or "/"
        if not self._authorized(query):
            return self._reply(401, "Mangler eller feil token.")
        if path == "/":
            return self._reply(200, WEBUI_HTML, "text/html; charset=utf-8")
        if path == "/helse":
            # Helsesida bygges av helse.py, som ogsaa kan kjoeres frittstaaende.
            # Feiler den, skal resten av serveren staa: dette er en side som
            # skal FORTELLE om feil, ikke skape dem.
            try:
                import helse
                return self._reply(200, _helse_side(helse), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                return self._reply(500, f"Helsesida feilet: {e}")
        if path == "/api/helse":
            try:
                import helse
                d = helse.samle()
                d["naa"] = d["naa"].isoformat()
                for k in ("sist",):
                    if d["utedel"].get(k):
                        d["utedel"][k] = d["utedel"][k].isoformat()
                if d["side"].get("frame_tid"):
                    d["side"]["frame_tid"] = d["side"]["frame_tid"].isoformat()
                return self._reply_json(200, d)
            except Exception as e:  # noqa: BLE001
                return self._reply_json(500, {"ok": False, "message": str(e)})
        if path == "/api/images":
            return self._reply_json(200, {"images": _archive_list(), "status": _state["status"], "last": _state["last"]})
        if path == "/status":
            return self._reply(200, f"status: {_state['status']}\nsist: {_state['last']}")
        if path == "/generate":
            emne = query.get("emne", [None])[0] or query.get("subject", [None])[0]
            return self._reply(*_start(emne))
        if path == "/daily":
            return self._reply(*_start(None))
        if path == "/help":
            return self._reply(200,
                "Fugleramme frame-server.\n"
                "Web: GET /   |  POST /api/generate {emne,stil,seeds[]}  |  POST /api/send {name}\n"
                "Siri: POST /generate (emne i body)  |  GET /generate?emne=...\n"
                "GET /daily   GET /status   GET /api/images   GET /helse\n")
        return self._reply(404, "Ukjent endepunkt.")

    # --- POST ---
    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"
        if not self._authorized(query):
            return self._reply(401, "Mangler eller feil token.")
        raw = self._read_body()
        ctype = (self.headers.get("Content-Type") or "").lower()

        if path == "/api/generate":
            try:
                d = json.loads(raw) if raw else {}
            except Exception:
                return self._reply_json(400, {"ok": False, "message": "Ugyldig JSON."})
            emne = (d.get("emne") or "").strip()
            stil = (d.get("stil") or "").strip() or None
            seeds = d.get("seeds") or ([d["seed"]] if d.get("seed") else [])
            refs = []
            for s in seeds[:MAX_SEEDS]:
                try:
                    im = _decode_seed(s)
                    if im is not None:
                        refs.append(im)
                except Exception as e:
                    return self._reply_json(400, {"ok": False, "message": f"Kunne ikke lese referansebilde: {e}"})
            if not emne and not refs:
                return self._reply_json(400, {"ok": False, "message": "Skriv et emne eller last opp et bilde."})
            code, msg = _start(emne or None, style=stil, ref_images=refs or None)
            return self._reply_json(code, {"ok": code == 202, "message": msg})

        if path == "/api/send":
            try:
                d = json.loads(raw) if raw else {}
            except Exception:
                return self._reply_json(400, {"ok": False, "message": "Ugyldig JSON."})
            name = os.path.basename((d.get("name") or "").strip())
            if not name.lower().endswith(".png") or not os.path.isfile(os.path.join(gen.ARCHIVE_DIR, name)):
                return self._reply_json(404, {"ok": False, "message": "Fant ikke bildet i arkivet."})
            code, msg = _start_send(name)
            return self._reply_json(code, {"ok": code == 202, "message": msg})

        if path == "/generate":
            emne = _parse_subject(raw, ctype) or query.get("emne", [None])[0] or query.get("subject", [None])[0]
            return self._reply(*_start(emne))
        if path == "/daily":
            return self._reply(*_start(None))
        return self._reply(404, "Ukjent endepunkt.")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def _parse_subject(raw, ctype):
    """Hent emnet ut av en POST-body (Skjema / JSON / ren tekst) — for Siri."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "json" in ctype or raw[0] in "{[":
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                for k in ("emne", "subject", "text"):
                    if d.get(k):
                        return str(d[k]).strip() or None
        except Exception:
            pass
    if "form-urlencoded" in ctype or raw.startswith(("emne=", "subject=", "text=")):
        d = parse_qs(raw)
        for k in ("emne", "subject", "text"):
            if d.get(k):
                return d[k][0].strip() or None
    return raw


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("ADVARSEL: GEMINI_API_KEY er ikke satt — generering vil feile.", file=sys.stderr)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Fugleramme frame-server lytter på :{PORT} "
          f"(web: http://<server>:{PORT}/ , ramme: {FRAME_HOST}, token: {'ja' if TOKEN else 'nei'})",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ----------------------------------------------------------------------
# Web-appen (én selvstendig HTML-side)
# ----------------------------------------------------------------------

def _helse_side(helse) -> str:
    """Helsesida i web-appens drakt: samme palett, samme kort."""
    stil = WEBUI_HTML.split("<style>", 1)[1].split("</style>", 1)[0]
    return ("<!doctype html><html lang=no><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width, initial-scale=1'>"
            "<title>Fugleramme — helse</title><style>"
            + stil + helse.STIL +
            "</style></head><body>"
            "<header><h1>Helse</h1>"
            "<div class=status><a href='/'>← tilbake til bildene</a></div>"
            "</header><main>" + helse.side(helse.samle()) + "</main></body></html>")


WEBUI_HTML = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fugleramme</title>
<style>
  :root{
    --bg:#f4f1ea; --card:#fffdf8; --ink:#2b2a26; --muted:#8a857a;
    --line:#e4ded1; --accent:#3a6ea5; --accent-ink:#fff; --ok:#2e7d52; --err:#b23a3a;
    --shadow:0 1px 3px rgba(0,0,0,.08),0 6px 18px rgba(0,0,0,.05);
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#17161c; --card:#211f28; --ink:#eceae3; --muted:#9a94a6;
           --line:#332f3d; --accent:#6ea3d8; --accent-ink:#10131a; --shadow:0 1px 3px rgba(0,0,0,.4);}
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  header{padding:20px 16px 8px;max-width:1100px;margin:0 auto;}
  h1{font-size:1.5rem;margin:0;display:flex;align-items:center;gap:.5rem}
  h1 .dot{width:12px;height:12px;border-radius:50%;background:var(--muted);flex:none}
  h1 .dot.busy{background:#e0a92e;animation:pulse 1.1s infinite}
  h1 .dot.idle{background:var(--ok)}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  .status{color:var(--muted);font-size:.9rem;margin-top:4px;min-height:1.2em}
  main{max-width:1100px;margin:0 auto;padding:8px 16px 48px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;
    box-shadow:var(--shadow);padding:16px;margin:16px 0}
  .card h2{font-size:1.05rem;margin:0 0 12px}
  label{display:block;font-size:.85rem;color:var(--muted);margin:10px 0 4px}
  textarea,select,input[type=text]{width:100%;padding:11px 12px;border:1px solid var(--line);
    border-radius:11px;background:var(--bg);color:var(--ink);font:inherit}
  textarea{resize:vertical;min-height:64px}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  .row>div{flex:1;min-width:180px}
  .seedbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
  .seedbar img{width:64px;height:64px;object-fit:cover;border-radius:9px;border:1px solid var(--line)}
  .filebtn{display:inline-block;padding:9px 13px;border:1px dashed var(--line);border-radius:11px;
    color:var(--muted);cursor:pointer;font-size:.9rem}
  button{font:inherit;border:0;border-radius:11px;padding:11px 16px;cursor:pointer;
    background:var(--accent);color:var(--accent-ink);font-weight:600}
  button.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent);font-weight:500}
  button:disabled{opacity:.5;cursor:default}
  .generate-row{display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;
    box-shadow:var(--shadow);display:flex;flex-direction:column}
  .tile .imgwrap{aspect-ratio:3/4;background:var(--bg);overflow:hidden}
  .tile img{width:100%;height:100%;object-fit:cover;display:block}
  .tile .meta{padding:9px 11px;flex:1;display:flex;flex-direction:column;gap:6px}
  .tile .subj{font-size:.9rem;font-weight:600;line-height:1.25}
  .tile .when{font-size:.72rem;color:var(--muted)}
  .tile button{padding:8px;font-size:.82rem;border-radius:0;border-top:1px solid var(--line);
    background:transparent;color:var(--accent);font-weight:600}
  .empty{color:var(--muted);text-align:center;padding:40px 0}
  .toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--ink);
    color:var(--bg);padding:11px 18px;border-radius:12px;box-shadow:var(--shadow);opacity:0;
    transition:opacity .25s;pointer-events:none;max-width:90vw;text-align:center;z-index:9}
  .toast.show{opacity:1}
  .toast.err{background:var(--err);color:#fff}
</style>
</head>
<body>
<header>
  <h1><span class="dot idle" id="dot"></span> Fugleramme</h1>
  <div class="status" id="status">Klar.</div>
</header>
<main>
  <section class="card">
    <h2>Lag nytt bilde</h2>
    <label for="emne">Hva vil du tegne?</label>
    <textarea id="emne" placeholder="f.eks. en ridderborg med en drage, eller en katt på en traktor"></textarea>
    <div class="row">
      <div>
        <label for="stil">Stil</label>
        <select id="stil">
          <option value="">Tegneserie (standard)</option>
          <option value="random">🎲 Tilfeldig stil</option>
          <option value="bold flat vector illustration, poster style, clean thick outlines, large flat areas of saturated color, minimal shading, plain background">Flat vektor / plakat</option>
          <option value="ukiyo-e woodblock print style, flat color areas, bold outlines, limited palette, clean composition">Japansk tresnitt</option>
          <option value="risograph print style, 3-4 bold spot colors, flat layered shapes, slight grain, clean paper background">Risograph</option>
          <option value="bold children's book illustration, simple flat shapes, warm saturated colors, clear outlines, uncluttered background">Barnebok</option>
        </select>
      </div>
      <div>
        <label>Referansebilde(r) — valgfritt</label>
        <label class="filebtn" for="seed">📎 Velg bilde(r) …</label>
        <input id="seed" type="file" accept="image/*" multiple style="display:none">
        <div class="seedbar" id="seedbar"></div>
      </div>
    </div>
    <div class="generate-row">
      <button id="gen">Generer og send til rammen</button>
      <span class="status" id="genhint" style="margin:0"></span>
    </div>
  </section>

  <section class="card">
    <h2>Tidligere bilder</h2>
    <div id="gallery" class="grid"></div>
    <div class="empty" id="empty" style="display:none">Ingen bilder ennå.</div>
  </section>
</main>
<div class="toast" id="toast"></div>

<script>
const TOKEN = new URLSearchParams(location.search).get('token');
function api(u){ if(!TOKEN) return u; return u + (u.includes('?')?'&':'?') + 'token=' + encodeURIComponent(TOKEN); }
const $ = s => document.querySelector(s);
let seeds = [];   // data-URL-strenger

function toast(msg, isErr){
  const t=$('#toast'); t.textContent=msg; t.className='toast show'+(isErr?' err':'');
  setTimeout(()=>t.className='toast', 3200);
}

async function refreshStatus(){
  try{
    const r = await fetch(api('/api/images'));
    const d = await r.json();
    renderGallery(d.images||[]);
    const busy = d.status && d.status!=='idle';
    $('#dot').className = 'dot '+(busy?'busy':'idle');
    $('#status').textContent = busy ? d.status : (d.last || 'Klar.');
  }catch(e){ $('#status').textContent='Får ikke kontakt med serveren.'; }
}

function renderGallery(imgs){
  const g=$('#gallery'); const empty=$('#empty');
  empty.style.display = imgs.length? 'none':'block';
  g.innerHTML = imgs.map(im => `
    <div class="tile">
      <div class="imgwrap"><img loading="lazy" src="${api(im.url)}" alt=""></div>
      <div class="meta">
        <div class="subj">${escapeHtml(im.subject)}</div>
        <div class="when">${escapeHtml(im.when||'')}</div>
      </div>
      <button onclick="sendImage('${encodeURIComponent(im.name)}', this)">Send til rammen</button>
    </div>`).join('');
}
function escapeHtml(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

async function sendImage(nameEnc, btn){
  const name = decodeURIComponent(nameEnc);
  if(btn){btn.disabled=true; btn.textContent='Sender …';}
  try{
    const r = await fetch(api('/api/send'), {method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name})});
    const d = await r.json();
    toast(d.message||(d.ok?'Sendt.':'Feil.'), !d.ok);
  }catch(e){ toast('Nettverksfeil.', true); }
  finally{ if(btn){btn.disabled=false; btn.textContent='Send til rammen';} refreshStatus(); }
}

$('#seed').addEventListener('change', ev=>{
  const files=[...ev.target.files].slice(0,3);
  seeds=[];
  $('#seedbar').innerHTML='';
  files.forEach(f=>{
    const reader=new FileReader();
    reader.onload=()=>{ seeds.push(reader.result);
      const img=document.createElement('img'); img.src=reader.result; $('#seedbar').appendChild(img); };
    reader.readAsDataURL(f);
  });
});

$('#gen').addEventListener('click', async ()=>{
  const emne=$('#emne').value.trim();
  const stil=$('#stil').value;
  if(!emne && !seeds.length){ toast('Skriv et emne eller last opp et bilde.', true); return; }
  const btn=$('#gen'); btn.disabled=true; btn.textContent='Genererer …';
  try{
    const r=await fetch(api('/api/generate'),{method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({emne, stil, seeds})});
    const d=await r.json();
    toast(d.message||(d.ok?'Sendt.':'Feil.'), !d.ok);
    if(d.ok){ $('#emne').value=''; }
  }catch(e){ toast('Nettverksfeil.', true); }
  finally{ btn.disabled=false; btn.textContent='Generer og send til rammen'; setTimeout(refreshStatus, 1500); }
});

refreshStatus();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
