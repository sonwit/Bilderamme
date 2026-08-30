#!/usr/bin/env python3
"""
helse.py — status og statistikk for hele Fugleramme, som én side.

Alt vi trenger har ligget der hele tiden, spredt: batterispenning og
WiFi-styrke i helse-sidecarene ved hvert opptak, artene i
observations.jsonl, hva som sist ble tegnet i plates/dagens-bakgrunn.json.
Denne fila samler det og tegner det opp.

Hvorfor det er verdt en side: i loepet av ett doegn gikk utedelen tom for
Gemini-kreditt, laa femten timer i bootloader uten at noen saa det, og fikk en
ny lytteplan som tredoblet strømforbruket. Ingen av delene var synlige noe
sted. Naa er de det.

    python3 helse.py > /tmp/helse.html     # frittstaaende, til testing
    curl localhost:8090/helse              # servert av frame_server.py

Kun stdlib -- samme regel som resten av serveren. Grafene er handtegnet SVG,
ingen biblioteker.
"""

from __future__ import annotations

import collections
import datetime
import glob
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("FUGLE_DIR", HERE)
AUDIO = os.path.join(BASE, "audio")
DATA = os.path.join(BASE, "data")
PLATES = os.path.join(BASE, "plates")
WWW = os.environ.get("FRAME_OUTPUT_DIR", os.path.join(BASE, "www"))

# Trappene i lytteplan.py. Gjentatt her fordi helse.py skal kunne kjoere uten
# at lytteplan er importerbar -- den har ingen tunge avhengigheter, men denne
# sida skal virke ogsaa hvis noe annet er i stykker.
TRAPPER = [(3.80, "full plan, 10/20 min"),
           (3.65, "nedtrappet, 15/30 min"),
           (0.00, "sparemodus, 30/60 min")]
STILLE_MIN = 45


# ----------------------------------------------------------------------
# Innsamling
# ----------------------------------------------------------------------

def _sidecars(dager: int = 21) -> list[dict]:
    """Helse-JSON fra hvert opptak, nyeste sist, med tidsstempel paa."""
    ut = []
    for sti in sorted(glob.glob(os.path.join(AUDIO, "fugl_*.json"))):
        navn = os.path.basename(sti)
        try:
            t = datetime.datetime.strptime(navn[5:20], "%Y%m%d_%H%M%S")
            with open(sti) as f:
                d = json.load(f)
        except (ValueError, OSError):
            continue
        d["t"] = t
        ut.append(d)
    grense = datetime.datetime.now() - datetime.timedelta(days=dager)
    return [d for d in ut if d["t"] >= grense]


def _observasjoner(dager: int = 21) -> list[dict]:
    grense = (datetime.date.today() - datetime.timedelta(days=dager)).isoformat()
    ut = []
    try:
        with open(os.path.join(DATA, "observations.jsonl")) as f:
            for rad in f:
                rad = rad.strip()
                if not rad:
                    continue
                try:
                    o = json.loads(rad)
                except ValueError:
                    continue
                if o.get("date", "") >= grense:
                    ut.append(o)
    except OSError:
        pass
    return ut


def _les(sti: str) -> dict | None:
    try:
        with open(sti) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _vakt(naa: datetime.datetime) -> tuple[list[str], list[str]]:
    """(aktive advarsler, siste linjer fra vaktloggen).

    Vakten kjoerer fra cron hvert kvarter og skriver bare til logg. Uten dette
    maatte man SSH-e inn for aa se hva den har sagt -- og da blir den ikke
    lest. Advarslene regnes ut paa nytt her, saa de er ferske, mens loggen
    viser historikken."""
    aktive, logg = [], []
    try:
        import sys
        sys.path.insert(0, HERE)
        import vakt
        aktive = [m for _, m in vakt.sjekk(naa)]
    except Exception as e:  # noqa: BLE001
        aktive = [f"vakt.py kunne ikke kjøres: {e}"]
    try:
        with open(os.path.join(BASE, "logs", "vakt.log")) as f:
            logg = [r.rstrip() for r in f.readlines()[-8:] if r.strip()]
    except OSError:
        pass
    return aktive, logg


def samle(dager: int = 21) -> dict:
    naa = datetime.datetime.now()
    helse = _sidecars(dager)
    obs = _observasjoner(dager)
    siste = helse[-1] if helse else None

    # --- utedelen ---
    stille_min = int((naa - siste["t"]).total_seconds() / 60) if siste else None
    volt = siste.get("volt") if siste else None
    trapp = next((tekst for grense, tekst in TRAPPER if volt and volt >= grense),
                 TRAPPER[-1][1])

    # Spenning per doegn: laveste og hoeyeste, saa ladingen gjennom dagen synes.
    per_dag = collections.defaultdict(list)
    for d in helse:
        if d.get("volt"):
            per_dag[d["t"].date()].append(d["volt"])
    batteri = [{"dato": k.isoformat(), "min": min(v), "maks": max(v),
                "snitt": sum(v) / len(v), "opptak": len(v)}
               for k, v in sorted(per_dag.items())]

    # --- fuglene ---
    arter_per_dag = collections.defaultdict(set)
    per_time = collections.Counter()
    teller = collections.Counter()
    beste = {}
    for o in obs:
        d = o.get("date", "")
        for s in o.get("species", []):
            if s.get("confidence", 0) < 0.5:
                continue
            sci = s.get("scientific_name", "")
            arter_per_dag[d].add(sci)
            per_time[o.get("hour", 0)] += 1
            teller[sci] += 1
            beste[sci] = max(beste.get(sci, 0), s["confidence"])

    # --- plansjedekning: hva har vi hoert som ikke kan tegnes? ---
    har_plansje = set()
    for f in glob.glob(os.path.join(PLATES, "fugler", "*.png")):
        n = os.path.basename(f)[:-4]
        if not n.endswith("-flyvende"):
            har_plansje.add(n.replace("-", " "))
    mangler = sorted(
        ((sci, teller[sci], beste[sci]) for sci in teller
         if sci.lower() not in har_plansje),
        key=lambda x: -x[2])

    # --- sida og ramma ---
    bg = _les(os.path.join(PLATES, "dagens-bakgrunn.json")) or {}
    frame = os.path.join(WWW, "frame.bin")
    vakt_aktive, vakt_logg = _vakt(naa)
    return {
        "naa": naa,
        "vakt": vakt_aktive,
        "vaktlogg": vakt_logg,
        "utedel": {
            "sist": siste["t"] if siste else None,
            "stille_min": stille_min,
            "stille": stille_min is not None and stille_min > STILLE_MIN,
            "volt": volt,
            "trapp": trapp,
            "temp": siste.get("temp_c") if siste else None,
            "wifi": siste.get("wifi_dbm") if siste else None,
            "boot": siste.get("boot_count") if siste else None,
            "ok": siste.get("uploads_ok") if siste else None,
            "feil": siste.get("uploads_failed") if siste else None,
            "fw": siste.get("fw") if siste else None,
            "cfg_rev": siste.get("cfg_rev") if siste else None,
            "rec_s": siste.get("duration_req_s") if siste else None,
            "opptak_i_dag": sum(1 for d in helse if d["t"].date() == naa.date()),
        },
        "batteri": batteri,
        "arter_per_dag": [{"dato": k, "antall": len(v)}
                          for k, v in sorted(arter_per_dag.items())],
        "per_time": [per_time.get(h, 0) for h in range(24)],
        "topp": sorted(teller.items(), key=lambda x: -x[1])[:12],
        "beste": beste,
        "mangler": mangler,
        "side": {
            "dato": bg.get("date"),
            "mal": bg.get("mal"),
            "fugler": len(bg.get("species", [])),
            "metode": bg.get("metode", ""),
            "frame_tid": (datetime.datetime.fromtimestamp(os.path.getmtime(frame))
                          if os.path.exists(frame) else None),
        },
    }


# ----------------------------------------------------------------------
# Grafer -- handtegnet SVG, ingen biblioteker
# ----------------------------------------------------------------------

def _svg_linje(punkter: list[tuple[float, float]], w: int, h: int,
               ymin: float, ymaks: float, linjer: list[tuple[float, str]] = (),
               fyll: bool = False) -> str:
    """En enkel kurve. punkter er (x-andel 0-1, verdi)."""
    if not punkter:
        return '<p class="tom">ingen data</p>'
    spenn = (ymaks - ymin) or 1

    def xy(px, v):
        return (12 + px * (w - 24), h - 18 - (v - ymin) / spenn * (h - 34))

    d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                 for i, (px, v) in enumerate(punkter)
                 for x, y in [xy(px, v)])
    ut = [f'<svg viewBox="0 0 {w} {h}" class="graf" role="img">']
    for v, merke in linjer:
        if ymin <= v <= ymaks:
            _, y = xy(0, v)
            ut.append(f'<line x1="12" y1="{y:.1f}" x2="{w - 12}" y2="{y:.1f}" '
                      f'class="terskel"/>')
            ut.append(f'<text x="{w - 10}" y="{y - 3:.1f}" class="terskeltekst" '
                      f'text-anchor="end">{html.escape(merke)}</text>')
    if fyll:
        x0, _ = xy(punkter[0][0], ymin)
        xn, _ = xy(punkter[-1][0], ymin)
        ut.append(f'<path d="{d} L{xn:.1f},{h - 18} L{x0:.1f},{h - 18} Z" '
                  f'class="fyll"/>')
    ut.append(f'<path d="{d}" class="kurve"/>')
    ut.append("</svg>")
    return "".join(ut)


def _svg_stolper(verdier: list[float], w: int, h: int,
                 merker: list[str] | None = None) -> str:
    if not verdier or max(verdier) == 0:
        return '<p class="tom">ingen data</p>'
    n = len(verdier)
    bw = (w - 24) / n
    top = max(verdier)
    ut = [f'<svg viewBox="0 0 {w} {h}" class="graf" role="img">']
    for i, v in enumerate(verdier):
        hh = (v / top) * (h - 34)
        x = 12 + i * bw
        ut.append(f'<rect x="{x + 1:.1f}" y="{h - 18 - hh:.1f}" '
                  f'width="{bw - 2:.1f}" height="{hh:.1f}" class="stolpe"/>')
        if merker and merker[i]:
            ut.append(f'<text x="{x + bw / 2:.1f}" y="{h - 5}" class="akse" '
                      f'text-anchor="middle">{html.escape(merker[i])}</text>')
    ut.append("</svg>")
    return "".join(ut)


# ----------------------------------------------------------------------
# Sida
# ----------------------------------------------------------------------

STIL = """
  .helse .rad{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 4px}
  .helse .tall{flex:1;min-width:118px;background:var(--bg);border:1px solid var(--line);
    border-radius:12px;padding:10px 12px}
  .helse .tall b{display:block;font-size:1.35rem;line-height:1.2;font-variant-numeric:tabular-nums}
  .helse .tall b.ordverdi{font-size:1rem;line-height:1.35;font-weight:600}
  .helse .tall span{font-size:.78rem;color:var(--muted)}
  .helse .graf{width:100%;height:auto;display:block;margin:6px 0 2px}
  .helse .kurve{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round}
  .helse .fyll{fill:var(--accent);opacity:.10}
  .helse .stolpe{fill:var(--accent);opacity:.75}
  .helse .terskel{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3;opacity:.55}
  .helse .terskeltekst,.helse .akse{fill:var(--muted);font-size:9px}
  .helse .tom{color:var(--muted);font-size:.9rem;margin:8px 0}
  .helse table{width:100%;border-collapse:collapse;font-size:.92rem}
  .helse td{padding:5px 0;border-bottom:1px solid var(--line)}
  .helse td:last-child{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
  .helse .lat{font-style:italic;color:var(--muted);font-size:.85rem}
  .merke{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.78rem}
  .merke.ok{background:rgba(46,125,82,.14);color:var(--ok)}
  .merke.feil{background:rgba(178,58,58,.14);color:var(--err)}
  .helse.varsel{border-color:var(--err)}
  .helse .advarsel{margin:0 0 6px;color:var(--err);font-weight:600}
  .helse .logg{margin:8px 0 0;padding:10px 12px;background:var(--bg);
    border:1px solid var(--line);border-radius:10px;font-size:.8rem;
    line-height:1.5;white-space:pre-wrap;color:var(--muted);overflow-x:auto}
"""


def _tall(verdi, etikett, tekst: bool = False) -> str:
    """tekst=True setter verdien mindre: «gren-sommer» brakk over to linjer
    i tallstoerrelsen, og en mal er ikke et tall."""
    kl = " ordverdi" if tekst else ""
    return (f'<div class="tall"><b class="{kl.strip()}">{html.escape(str(verdi))}</b>'
            f'<span>{html.escape(etikett)}</span></div>')


def _antall(n: int, ord_ent: str, ord_fl: str) -> str:
    return f"{n} {ord_ent if n == 1 else ord_fl}"


def side(d: dict) -> str:
    u = d["utedel"]
    s = d["side"]

    # --- utedelen ---
    if u["sist"] is None:
        stempel = '<span class="merke feil">ingen opptak</span>'
    elif u["stille"]:
        stempel = (f'<span class="merke feil">stille i '
                   f'{u["stille_min"]} min</span>')
    else:
        stempel = (f'<span class="merke ok">sist for {u["stille_min"]} min '
                   f'siden</span>')

    bat = d["batteri"]
    if bat:
        lav = min(b["min"] for b in bat)
        hoy = max(b["maks"] for b in bat)
        pkt = [(i / max(1, len(bat) - 1), b["snitt"]) for i, b in enumerate(bat)]
        graf_bat = _svg_linje(pkt, 520, 130, min(lav, 3.6) - .05, max(hoy, 4.1) + .05,
                              linjer=[(3.80, "3,80 V"), (3.65, "3,65 V")], fyll=True)
        bat_under = (f'{bat[0]["dato"][5:]} – {bat[-1]["dato"][5:]} · '
                     f'{lav:.2f}–{hoy:.2f} V')
    else:
        graf_bat, bat_under = '<p class="tom">ingen data</p>', ""

    apd = d["arter_per_dag"]
    graf_arter = _svg_stolper(
        [x["antall"] for x in apd], 520, 120,
        [x["dato"][8:] if i % 3 == 0 else "" for i, x in enumerate(apd)])

    graf_time = _svg_stolper(
        d["per_time"], 520, 120,
        [f"{h:02d}" if h % 3 == 0 else "" for h in range(24)])

    topp = "".join(
        f'<tr><td>{html.escape(navn)}<br><span class="lat">{html.escape(sci)}</span></td>'
        f"<td>{_antall(n, 'deteksjon', 'deteksjoner')}<br>"
        f"beste {d['beste'][sci]:.0%}</td></tr>"
        for sci, n in d["topp"]
        for navn in [_norsk(sci)]) or '<tr><td class="tom">ingen data</td></tr>'

    mangler = "".join(
        f'<tr><td>{html.escape(_norsk(sci))}<br>'
        f'<span class="lat">{html.escape(sci)}</span></td>'
        f"<td>{_antall(n, 'deteksjon', 'deteksjoner')}<br>"
        f"beste {b:.0%}</td></tr>"
        for sci, n, b in d["mangler"][:10]) or \
        '<tr><td class="tom">alle hørte arter kan tegnes</td></tr>'

    if d["vakt"]:
        vaktboks = ('<section class="card helse varsel"><h2>Vakten sier fra</h2>'
                    + "".join(f'<p class="advarsel">{html.escape(m)}</p>'
                              for m in d["vakt"]))
    else:
        vaktboks = ('<section class="card helse"><h2>Vakten '
                    '<span class="merke ok">alt i orden</span></h2>')
    if d["vaktlogg"]:
        vaktboks += ('<pre class="logg">'
                     + html.escape("\n".join(d["vaktlogg"])) + "</pre>")
    else:
        vaktboks += '<p class="tom">Ingenting i vaktloggen. Den skriver bare når noe er galt.</p>'
    vaktboks += "</section>"

    return f"""
{vaktboks}
<section class="card helse">
  <h2>Utedelen {stempel}</h2>
  <div class="rad">
    {_tall(f'{u["volt"]:.2f} V' if u["volt"] else "–", u["trapp"])}
    {_tall(f'{u["temp"]:.0f} °C' if u["temp"] is not None else "–", "temperatur")}
    {_tall(f'{u["wifi"]} dBm' if u["wifi"] is not None else "–", "wifi-styrke")}
    {_tall(u["opptak_i_dag"], "opptak i dag")}
    {_tall(f'{u["ok"]}/{(u["ok"] or 0) + (u["feil"] or 0)}'
           if u["ok"] is not None else "–", "opplastinger ok")}
    {_tall(f'{u["rec_s"]} s' if u["rec_s"] else "–", "per opptak")}
  </div>
  {graf_bat}
  <p class="tom">{html.escape(bat_under)} · firmware {html.escape(str(u["fw"]))}
     · cfg_rev {html.escape(str(u["cfg_rev"]))} · oppvåkning {u["boot"]}</p>
</section>

<section class="card helse">
  <h2>Sida på veggen</h2>
  <div class="rad">
    {_tall(_dato(s["dato"]), "viser", tekst=True)}
    {_tall(s["mal"] or "–", "mal", tekst=True)}
    {_tall(s["fugler"], "fugler tegnet")}
    {_tall(s["frame_tid"].strftime("%H:%M") if s["frame_tid"] else "–", "sist sendt")}
  </div>
  <p class="tom">{html.escape(s["metode"] or "")}</p>
</section>

<section class="card helse">
  <h2>Sikre arter per dag</h2>
  {graf_arter}
</section>

<section class="card helse">
  <h2>Når på døgnet</h2>
  {graf_time}
  <p class="tom">Deteksjoner over 50 % fordelt på klokketime.</p>
</section>

<section class="card helse">
  <h2>Oftest hørt</h2>
  <table>{topp}</table>
</section>

<section class="card helse">
  <h2>Mangler plansje</h2>
  <table>{mangler}</table>
  <p class="tom">Disse er hørt, men kan ikke tegnes ennå.
     ny_art.py tar to av dem ved hver kjøring.</p>
</section>
"""


MAANED = ("jan", "feb", "mars", "april", "mai", "juni",
          "juli", "aug", "sep", "okt", "nov", "des")


def _dato(iso: str | None) -> str:
    if not iso:
        return "–"
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    i_dag = datetime.date.today()
    if d == i_dag:
        return "i dag"
    if d == i_dag - datetime.timedelta(days=1):
        return "i går"
    return f"{d.day}. {MAANED[d.month - 1]}"


def _norsk(sci: str) -> str:
    """Norsk navn hvis bird_names er tilgjengelig, ellers det latinske."""
    try:
        import sys
        sys.path.insert(0, HERE)
        from bird_names import norwegian_name
        return norwegian_name(sci)
    except Exception:  # noqa: BLE001
        return sci


if __name__ == "__main__":
    d = samle()
    print(f"<!doctype html><meta charset=utf-8><title>Fugleramme — helse</title>"
          f"<style>{STIL}</style><body>{side(d)}</body>")
