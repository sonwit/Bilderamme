#!/usr/bin/env python3
"""
dag.py — dagsoversikten: naar opptakene ble gjort, og hvilke fugler som ble
hoert i hvert av dem. Én dag om gangen, med en stripe til aa bla i de andre.

Helsesida (helse.py) svarer paa «virker anlegget?», fuglesida (fugler.py) paa
«hva har det hoert i det hele tatt?». Denne svarer paa «hva skjedde i dag?»:
doegnet som forloep, med hvert opptak paa klokkeslettet sitt, artene i det,
lydnivaa og avspilling saa lenge WAV-en ligger der, og kamerabildene flettet
inn paa tiden sin. Nederst i dagvelgeren ligger alle dagene som en stripe --
ett klikk (eller piltast) for aa bla bakover.

    python3 dag.py > /tmp/dag.html     # sida, frittstaaende (henter /api/dag)
    python3 dag.py --json [dato]       # datagrunnlaget for én dag
    curl localhost:8090/dag            # servert av frame_server.py

Serveren sender én dag om gangen (~10 kB) pluss en liten indeks over alle
dager med data -- nok til aa tegne bla-stripa uten aa laste hele loggen, som
er forskjellen paa denne og fuglesida. Kun stdlib, SVG tegnet for haand.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("FUGLE_DIR", HERE)
DATA = os.path.join(BASE, "data")

sys.path.insert(0, HERE)
import fugler  # noqa: E402 — plansje/lydfil/kamerabilde: samme filer, samme vask

# To terskler, ikke en glidebryter: BirdNET skriver alt fra 25 % og opp til
# loggen, men et doegn med alle de usikre treffene er stoey aa se paa. Sida
# staar paa «sikkert» og har en avkryssingsboks for de usikre.
SIKKER = 0.5
ALLE = 0.25

DATO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _navn():
    """Norske navn og habitat, samme oppslag som fuglesida bruker."""
    try:
        from bird_names import habitat, norwegian_name
        return norwegian_name, habitat
    except Exception:  # noqa: BLE001
        return (lambda sci, common="": common or sci), (lambda sci: "")


def _rader(sti: str):
    """Én JSON-linje om gangen. Halve linjer og manglende fil er ikke feil --
    loggen skrives av en tjeneste som kan bli drept midt i en skriving."""
    try:
        with open(sti) as f:
            for rad in f:
                rad = rad.strip()
                if not rad:
                    continue
                try:
                    yield json.loads(rad)
                except ValueError:
                    continue
    except FileNotFoundError:
        return


STEMPEL = re.compile(r"_(\d{2})(\d{2})\d{2}\.")


def _tid(iso: str, filnavn: str) -> str:
    """HH:MM fra tidsstemplet, ellers fra filnavnet (fugl_YYYYmmdd_HHMMSS.wav).
    Doegnstripa tegner paa klokkeslett, saa en tom tid ville blitt et merke
    uten plass."""
    if len(iso) >= 16 and iso[13] == ":":
        return iso[11:16]
    m = STEMPEL.search(filnavn or "")
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def _tom_dag() -> dict:
    return {"n": 0, "fugl": 0, "fuglAlle": 0, "arter": set(), "arterAlle": set(),
            "kam": 0, "kamAlle": 0}


def samle(dato: str | None = None) -> dict:
    """Indeksen over alle dager + alt vi vet om én av dem.

    dato: 'YYYY-MM-DD', eller None for siste dag med opptak (som regel i dag).
    Opptak: f = filstamme, t = klokkeslett, rms = nivaa (dBFS), smell =
    klipping i foerste sekund (%), lyd = om WAV-en finnes ennaa, a = [[latinsk
    navn, sikkerhet, antall 3-sekundersvinduer], ...]."""
    norsk, habitat = _navn()
    dager: dict[str, dict] = {}
    opptak: dict[str, list] = {}
    kamera: dict[str, list] = {}
    engelsk: dict[str, str] = {}
    modellnavn: dict[str, str] = {}

    for o in _rader(os.path.join(DATA, "observations.jsonl")):
        d = o.get("date") or (o.get("recorded_at") or "")[:10]
        if not DATO.match(d or ""):
            continue
        dag = dager.setdefault(d, _tom_dag())
        dag["n"] += 1
        a = o.get("audio") or {}
        arter_i = []
        for s in o.get("species", []):
            sci = (s.get("scientific_name") or "").strip()
            if not sci:
                continue
            conf = round(float(s.get("confidence", 0)), 3)
            arter_i.append([sci, conf, int(s.get("detections", 0))])
            engelsk.setdefault(sci, s.get("common_name", ""))
            if conf >= ALLE:
                dag["arterAlle"].add(sci)
            if conf >= SIKKER:
                dag["arter"].add(sci)
        if any(c >= SIKKER for _, c, _ in arter_i):
            dag["fugl"] += 1
        if any(c >= ALLE for _, c, _ in arter_i):
            dag["fuglAlle"] += 1
        fil = o.get("file", "")
        opptak.setdefault(d, []).append({
            "f": os.path.splitext(fil)[0],
            "t": _tid(o.get("recorded_at") or "", fil),
            "rms": a.get("rms_dbfs"),
            "smell": a.get("smell_pct"),
            "lyd": bool(fil) and fugler.lydfil(fil) is not None,
            "a": arter_i,
        })

    # Kameraet i kontorvinduet (bilde_analyze.py -> data/kamera.jsonl). Bare
    # bilder med noe paa -- «hoppet_over» er ikke analysert i det hele tatt,
    # og et tomt bilde sier ingenting om doegnet.
    for k in _rader(os.path.join(DATA, "kamera.jsonl")):
        d = k.get("date") or (k.get("captured_at") or "")[:10]
        if not DATO.match(d or "") or k.get("hoppet_over") or not k.get("species"):
            continue
        dag = dager.setdefault(d, _tom_dag())
        arter_i = []
        for sp in k["species"]:
            sci = (sp.get("scientific_name") or "").strip()
            if not sci:
                continue
            conf = round(float(sp.get("confidence", 0)), 2)
            arter_i.append([sci, conf, int(sp.get("antall", 1) or 1)])
            engelsk.setdefault(sci, sp.get("common_name", ""))
            if sp.get("norsk"):
                modellnavn.setdefault(sci, sp["norsk"])
        if not arter_i:
            continue
        if any(c >= SIKKER for _, c, _ in arter_i):
            dag["kam"] += 1
        if any(c >= ALLE for _, c, _ in arter_i):
            dag["kamAlle"] += 1
        fil = k.get("file", "")
        kamera.setdefault(d, []).append({
            "f": os.path.splitext(fil)[0],
            "t": _tid(k.get("captured_at") or "", fil),
            "bilde": bool(fil) and fugler.kamerabilde(fil) is not None,
            "a": arter_i,
        })

    i_dag = datetime.date.today().isoformat()
    kjente = sorted(dager)
    valgt = dato if (dato and DATO.match(dato)) else (kjente[-1] if kjente else i_dag)

    arter = {}
    for sci in {s for r in opptak.get(valgt, []) + kamera.get(valgt, []) for s, _, _ in r["a"]}:
        eget = norsk(sci, "")
        arter[sci] = {
            "norsk": eget if eget and eget != sci else (modellnavn.get(sci) or engelsk.get(sci) or sci),
            "engelsk": engelsk.get(sci, ""),
            "habitat": habitat(sci),
            "plansje": fugler.plansje(sci) is not None,
        }

    return {
        "generert": datetime.datetime.now().isoformat(timespec="seconds"),
        "idag": i_dag,
        "dato": valgt,
        "sikker": SIKKER,
        "alle": ALLE,
        "dager": [{"d": d, "n": v["n"], "fugl": v["fugl"], "fuglAlle": v["fuglAlle"],
                   "arter": len(v["arter"]), "arterAlle": len(v["arterAlle"]),
                   "kam": v["kam"], "kamAlle": v["kamAlle"]} for d, v in sorted(dager.items())],
        "opptak": sorted(opptak.get(valgt, []), key=lambda r: r["t"]),
        "kamera": sorted(kamera.get(valgt, []), key=lambda r: r["t"]),
        "arter": arter,
    }


# ----------------------------------------------------------------------
# Sida
# ----------------------------------------------------------------------

STIL = r"""
  .dag{--serie1:#2a78d6;--serie2:#eb6834}
  @media (prefers-color-scheme: dark){.dag{--serie1:#3987e5;--serie2:#d95926}}
  .dag .dagvelg{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:space-between}
  .dag .dagvelg .naa{flex:1 1 220px}
  .dag .styring{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .dag .dagvelg h2{margin:0;font-size:1.3rem;line-height:1.2}
  .dag .dagvelg h2::first-letter{text-transform:uppercase}
  .dag .pil{padding:8px 13px;font-size:1rem;font-weight:600;background:transparent;
    color:var(--ink);border:1px solid var(--line)}
  .dag .pil:disabled{opacity:.3}
  .dag .pil:not(:disabled):hover{border-color:var(--accent);color:var(--accent)}
  .dag .naaknapp{padding:8px 13px;font-size:.85rem;font-weight:500;background:transparent;
    color:var(--accent);border:1px solid var(--accent)}
  .dag input[type=date]{padding:7px 10px;border-radius:9px;border:1px solid var(--line);
    background:var(--bg);color:var(--ink);font:inherit;font-size:.9rem}
  .dag .merke{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.72rem;
    background:var(--accent);color:var(--accent-ink);vertical-align:middle;margin-left:6px}
  .dag .under{color:var(--muted);font-size:.9rem;margin-top:3px}

  /* Bla-stripa: alle dagene, ogsaa de tomme -- hullene er ogsaa informasjon. */
  .dag .stripe{display:flex;gap:2px;align-items:flex-end;overflow-x:auto;padding:14px 2px 4px;
    margin-top:12px;border-top:1px solid var(--line);scrollbar-width:thin}
  .dag .stripe .skille{align-self:stretch;display:flex;align-items:flex-end;padding:0 6px 16px 5px;
    margin-left:3px;border-left:1px solid var(--line);color:var(--muted);font-size:.7rem;flex:none}
  .dag .dagknapp{flex:none;width:17px;padding:0;background:transparent;border:0;border-radius:6px;
    display:flex;flex-direction:column;align-items:center;gap:3px;cursor:pointer}
  .dag .dagknapp:hover{background:var(--bg)}
  .dag .dagknapp>*{pointer-events:none}
  .dag .dagknapp .sot{width:9px;border-radius:3px;background:var(--serie1);opacity:.55}
  .dag .dagknapp .nr{font-size:.62rem;line-height:1;color:var(--muted);font-variant-numeric:tabular-nums}
  .dag .dagknapp.tom .sot{background:var(--line);opacity:1}
  .dag .dagknapp.valgt{background:var(--accent)}
  .dag .dagknapp.valgt .sot{background:var(--accent-ink);opacity:1}
  .dag .dagknapp.valgt .nr{color:var(--accent-ink);font-weight:600}

  .dag .rad{display:flex;gap:12px;flex-wrap:wrap;margin:0}
  .dag .tall{flex:1;min-width:118px;background:var(--bg);border:1px solid var(--line);
    border-radius:12px;padding:10px 12px}
  .dag .tall b{display:block;font-size:1.35rem;line-height:1.2}
  .dag .tall span{font-size:.78rem;color:var(--muted)}

  /* Doegnet: ett merke per opptak paa klokkeslettet sitt. */
  .dag .graf{width:100%;height:auto;display:block;overflow:visible}
  .dag .merket{fill:var(--serie1);cursor:pointer}
  .dag .merket.stille{fill:var(--line)}
  .dag .merket.kam{fill:var(--serie2)}
  .dag .akse{fill:var(--muted);font-size:10px}
  .dag .rute{stroke:var(--line);stroke-width:1}
  .dag .spor{fill:var(--bg);stroke:var(--line);stroke-width:1}
  .dag .laneetikett{fill:var(--muted);font-size:9px}

  .dag .arter{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
  .dag .artkort{display:flex;gap:10px;align-items:center;padding:9px;border:1px solid var(--line);
    border-radius:13px;background:var(--bg);cursor:pointer;text-align:left;color:var(--ink);font:inherit}
  .dag .artkort:hover{border-color:var(--accent)}
  .dag .artkort.valgt{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent) inset}
  .dag .artkort.usikker{opacity:.62}
  .dag .artkort img,.dag .artkort .ingen{width:56px;height:56px;object-fit:contain;flex:none;
    background:#fff;border-radius:9px;border:1px solid var(--line)}
  .dag .artkort .ingen{display:flex;align-items:center;justify-content:center;color:var(--muted);
    font-size:1.3rem;background:var(--card)}
  .dag .artkort .navn{font-weight:600;line-height:1.25}
  .dag .artkort .nk{font-size:.78rem;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}

  /* Forloepet: én linje per opptak, klokkeslettet i margen. */
  .dag .forlop{display:flex;flex-direction:column}
  .dag .hendelse{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)}
  .dag .hendelse:first-child{border-top:0}
  .dag .hendelse .kl{flex:none;width:52px;font-variant-numeric:tabular-nums;font-weight:600;
    padding-top:2px}
  .dag .hendelse.stille .kl{color:var(--muted);font-weight:500}
  .dag .hendelse .innhold{flex:1;min-width:0}
  .dag .hendelse .meta{font-size:.76rem;color:var(--muted);margin-top:4px;font-variant-numeric:tabular-nums}
  .dag .hendelse .hoeyre{flex:none;display:flex;align-items:flex-start}
  .dag .hendelse.blink{animation:dagblink 1.4s ease-out}
  @keyframes dagblink{0%{background:rgba(42,120,214,.22)}100%{background:transparent}}
  .dag .chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px 3px 3px;margin:2px 6px 2px 0;
    border:1px solid var(--line);border-radius:999px;background:var(--card);cursor:pointer;
    font:inherit;font-size:.88rem;color:var(--ink)}
  .dag .chip:hover{border-color:var(--accent)}
  .dag .chip.valgt{border-color:var(--accent);background:var(--accent);color:var(--accent-ink)}
  .dag .chip.usikker{opacity:.6;border-style:dashed}
  .dag .chip img,.dag .chip .ingen{width:26px;height:26px;object-fit:contain;border-radius:50%;
    background:#fff;flex:none}
  .dag .chip .ingen{display:flex;align-items:center;justify-content:center;font-size:.7rem;color:var(--muted)}
  .dag .chip .p{font-size:.76rem;color:var(--muted);font-variant-numeric:tabular-nums}
  .dag .chip.valgt .p{color:var(--accent-ink)}
  .dag .kambilde{width:132px;height:99px;object-fit:cover;border-radius:10px;border:1px solid var(--line);
    background:var(--bg);display:block;flex:none}
  .dag .hendelse.kam .innhold{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}
  .dag .spill{padding:5px 11px;font-size:.8rem;font-weight:500;background:transparent;
    color:var(--accent);border:1px solid var(--accent)}
  .dag .spill.aktiv{background:var(--accent);color:var(--accent-ink)}
  .dag .stille .ingenting{color:var(--muted);font-size:.9rem}
  .dag .valg{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  .dag .valg label{margin:0;font-size:.85rem;color:var(--ink);display:flex;align-items:center;gap:5px}
  .dag .knapper{display:flex;gap:4px;flex-wrap:wrap}
  .dag .knapper button{padding:7px 11px;font-size:.85rem;font-weight:500;
    background:transparent;color:var(--ink);border:1px solid var(--line)}
  .dag .knapper button.paa{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
  .dag .tabellvalg{display:flex;justify-content:space-between;align-items:center;gap:10px;
    flex-wrap:wrap;margin-bottom:10px}
  .dag .tabellvalg h2{margin:0}
  .dag .tom{color:var(--muted);font-size:.9rem;margin:8px 0}
  .dag .fotnote{color:var(--muted);font-size:.8rem;margin:10px 0 0}
  .dag .fotnote a{color:var(--accent)}
  #tt{position:fixed;pointer-events:none;z-index:9;background:var(--card);color:var(--ink);
    border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:.82rem;line-height:1.35;
    box-shadow:var(--shadow);max-width:260px;display:none}
  #tt b{font-variant-numeric:tabular-nums}
"""

# JavaScript-en. Alt som kan endre seg (dato, rekkefoelge, filtre, valgt art)
# ligger i URL-hashen, saa en dag kan deles som lenke.
SKRIPT = r"""
(function(){
'use strict';
const RAW = new URLSearchParams(location.search).get('token');
const TOKEN = RAW ? '?token=' + encodeURIComponent(RAW) : '';
function api(u){ return RAW ? u + (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(RAW) : u; }
const $ = s => document.querySelector(s);
const tt = $('#tt');
const MND = ['januar','februar','mars','april','mai','juni','juli','august','september','oktober','november','desember'];
const MNDK = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];
const UKE = ['søndag','mandag','tirsdag','onsdag','torsdag','fredag','lørdag'];

let INDEKS = [];              // [{d, n, fugl, arter, kam, ...}] -- alle dager med data
let DAG = null;               // dagen som vises naa
const BUFFER = new Map();     // dato -> svar, saa bla fram og tilbake er gratis
let seq = 0;                  // siste fetch vinner, uansett hvem som svarer foerst
let S = {dato:'', rekke:'ny', bare:0, usikre:0, art:''};

// ------------------------------------------------------------ hjelpere
function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function pct(v){ return Math.round(v*100) + ' %'; }
function isoDag(d){ return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }
function datoLang(iso){ if(!iso) return '–'; const d = new Date(iso+'T00:00'); return d.getDate() + '. ' + MND[d.getMonth()] + ' ' + d.getFullYear(); }
function ukedag(iso){ return UKE[new Date(iso+'T00:00').getDay()]; }
function flytt(iso, n){ const d = new Date(iso+'T00:00'); d.setDate(d.getDate()+n); return isoDag(d); }
function dagerMellom(a,b){ const ut=[]; for(let d=new Date(a+'T00:00'); isoDag(d)<=b; d.setDate(d.getDate()+1)) ut.push(isoDag(d)); return ut; }
function min(t){ return (+t.slice(0,2))*60 + (+t.slice(3,5)); }
function terskel(){ return S.usikre ? (DAG ? DAG.alle : 0.25) : (DAG ? DAG.sikker : 0.5); }
function navn(sci){ const a = DAG.arter[sci]; return a ? a.norsk : sci; }
function antall(n, ent, fl){ return n + ' ' + (n === 1 ? ent : fl); }

// Plansjefuglen, eller forbokstaven hvis arten ikke har faatt plansje ennaa.
function bilde(sci){
  const a = DAG.arter[sci] || {};
  return a.plansje
    ? `<img src="/plansje/${encodeURIComponent(sci.toLowerCase().replace(/ /g,'-'))}.png${TOKEN}" alt="" loading="lazy">`
    : `<div class="ingen" aria-hidden="true">${esc((navn(sci)[0]||'?').toUpperCase())}</div>`;
}

function lesHash(){
  const h = new URLSearchParams(location.hash.slice(1));
  for (const k of Object.keys(S)) if (h.has(k)) S[k] = h.get(k);
  S.bare = +S.bare ? 1 : 0; S.usikre = +S.usikre ? 1 : 0;
}
function skrivHash(){
  const h = new URLSearchParams();
  for (const [k,v] of Object.entries(S)) if (v !== '' && v !== null && v !== 0) h.set(k, v);
  history.replaceState(null, '', '#' + h.toString());
}

function tips(html, e){
  tt.innerHTML = html; tt.style.display = 'block';
  const r = tt.getBoundingClientRect();
  tt.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - r.width - 8)) + 'px';
  tt.style.top = Math.max(8, e.clientY - r.height - 12) + 'px';
}

// ------------------------------------------------------------ henting
function hent(dato){
  const merke = ++seq;
  if (BUFFER.has(dato)) { vis(BUFFER.get(dato), merke); return; }
  $('#forlop').innerHTML = '<p class="tom">Henter …</p>';
  fetch(api('/api/dag' + (dato ? '?dato=' + encodeURIComponent(dato) : '')))
    .then(r => r.json())
    .then(d => { BUFFER.set(d.dato, d); vis(d, merke); })
    .catch(e => { if (merke === seq) $('#forlop').innerHTML = '<p class="tom">Klarte ikke hente dagen: ' + esc(e.message) + '</p>'; });
}
function vis(d, merke){
  if (merke !== seq) return;     // en nyere dag er alt paa vei inn
  DAG = d; INDEKS = d.dager.length ? d.dager : INDEKS;
  S.dato = d.dato;
  tegn();
}
function gaaTil(dato){ if (!dato || dato === S.dato) return; S.art = ''; skrivHash(); hent(dato); }

// ------------------------------------------------------------ dagvelger
function velger(){
  const dager = INDEKS.map(x => x.d);
  const forrige = dager.filter(d => d < S.dato).pop();
  const neste = dager.find(d => d > S.dato);
  const f = $('#forrige'), n = $('#neste');
  f.disabled = !forrige; n.disabled = !neste;
  f.title = forrige ? datoLang(forrige) : 'ingen eldre dager'; n.title = neste ? datoLang(neste) : 'ingen nyere dager';
  f.onclick = () => gaaTil(forrige); n.onclick = () => gaaTil(neste);
  $('#idag').onclick = () => gaaTil(DAG.idag);
  $('#idag').disabled = S.dato === DAG.idag;
  const d = $('#dato'); d.value = S.dato; d.max = DAG.idag;
  if (dager.length) d.min = dager[0];
  d.onchange = e => gaaTil(e.target.value);

  const iGaar = flytt(DAG.idag, -1);
  const merke = S.dato === DAG.idag ? '<span class="merke">i dag</span>'
    : S.dato === iGaar ? '<span class="merke">i går</span>' : '';
  $('#tittel').innerHTML = esc(ukedag(S.dato) + ' ' + datoLang(S.dato)) + merke;

  const t = terskel();
  const tider = DAG.opptak.map(o => o.t).sort();
  const arter = new Set();
  for (const o of DAG.opptak) for (const [s,c] of o.a) if (c >= t) arter.add(s);
  for (const k of DAG.kamera) for (const [s,c] of k.a) if (c >= t) arter.add(s);
  const kam = DAG.kamera.filter(k => k.a.some(([s,c]) => c >= t)).length;
  $('#under').textContent = !tider.length
    ? (kam ? antall(kam, 'bilde', 'bilder') + ' fra kameraet, ingen opptak' : 'Ingen opptak denne dagen.')
    : antall(tider.length, 'opptak', 'opptak') + ' mellom ' + tider[0] + ' og ' + tider[tider.length-1]
      + ' · ' + antall(arter.size, 'art hørt', 'arter hørt') + (kam ? ' · ' + antall(kam, 'bilde', 'bilder') + ' fra kameraet' : '');

  const medFugl = DAG.opptak.filter(o => o.a.some(([s,c]) => c >= t)).length;
  const treff = DAG.opptak.reduce((a,o) => a + o.a.filter(([s,c]) => c >= t).length, 0);
  $('#nokkel').innerHTML = [[DAG.opptak.length,'opptak'], [medFugl,'opptak med fugl'], [arter.size,'arter'],
    [treff,'artstreff'], [tider.length ? tider[0] : '–','første opptak'], [tider.length ? tider[tider.length-1] : '–','siste opptak']]
    .map(([v,e]) => `<div class="tall"><b>${esc(v)}</b><span>${esc(e)}</span></div>`).join('');
  stripe();
}

// Bla-stripa: hver dag fra foerste til siste i loggen, ogsaa de uten opptak --
// et hull er ogsaa et svar (utedelen var tom for stroem, serveren var nede).
function stripe(){
  const el = $('#stripe');
  if (!INDEKS.length) { el.innerHTML = ''; return; }
  const per = Object.fromEntries(INDEKS.map(x => [x.d, x]));
  const fra = INDEKS[0].d < S.dato ? INDEKS[0].d : S.dato;
  const til = INDEKS[INDEKS.length-1].d > S.dato ? INDEKS[INDEKS.length-1].d : S.dato;
  const verdi = x => S.usikre ? x.arterAlle : x.arter;
  const topp = Math.max(1, ...INDEKS.map(verdi));
  el.innerHTML = dagerMellom(fra, til).map(d => {
    const i = per[d], v = i ? verdi(i) : 0;
    const h = i && i.n ? Math.round(5 + (v/topp)*27) : 4;
    const tekst = i ? antall(i.n, 'opptak', 'opptak') + ' · ' + antall(v, 'art', 'arter') : 'ingen opptak';
    const skille = d.slice(8) === '01' ? `<span class="skille">${MNDK[+d.slice(5,7)-1]}</span>` : '';
    return skille + `<button class="dagknapp ${d===S.dato?'valgt':''} ${i&&i.n?'':'tom'}" data-d="${d}"
      title="${esc(datoLang(d) + ' — ' + tekst)}"><span class="sot" style="height:${h}px"></span><span class="nr">${+d.slice(8)}</span></button>`;
  }).join('');
  el.querySelectorAll('.dagknapp').forEach(b => b.onclick = () => gaaTil(b.dataset.d));
  const valgt = el.querySelector('.valgt');
  // scrollLeft, ikke scrollIntoView: den sistnevnte drar hele sida med seg.
  // Maalt med rektangler, ikke offsetLeft -- den siste er relativ til
  // offsetParent (kortet), ikke stripa, og sentreringen bommet tilsvarende.
  if (valgt) el.scrollLeft += valgt.getBoundingClientRect().left - el.getBoundingClientRect().left
    - el.clientWidth/2 + valgt.offsetWidth/2;
}

// ------------------------------------------------------------ doegnet
// Ett merke per opptak paa klokkeslettet sitt: blaatt hvis noe ble hoert,
// graatt hvis opptaket var tomt. Kameraet faar sitt eget spor under.
function doegn(){
  const t = terskel();
  const harKam = DAG.kamera.length > 0;
  const W = 640, ML = 30, MR = 10, MT = 8, LANE = 22, GAP = 6;
  const H = MT + LANE + (harKam ? LANE + GAP : 0) + 16;
  const x = m => ML + (m/1440) * (W - ML - MR);
  const bunn = MT + LANE + (harKam ? LANE + GAP : 0);
  let s = `<svg viewBox="0 0 ${W} ${H}" class="graf" role="img" aria-label="Når opptakene er tatt">`;
  s += `<rect class="spor" x="${ML}" y="${MT}" width="${W-ML-MR}" height="${LANE}" rx="6"/>`;
  s += `<text class="laneetikett" x="${ML-6}" y="${MT+LANE/2+3}" text-anchor="end">lyd</text>`;
  if (harKam) {
    s += `<rect class="spor" x="${ML}" y="${MT+LANE+GAP}" width="${W-ML-MR}" height="${LANE}" rx="6"/>`;
    s += `<text class="laneetikett" x="${ML-6}" y="${MT+LANE+GAP+LANE/2+3}" text-anchor="end">foto</text>`;
  }
  for (let h = 0; h <= 24; h += 3) {
    const xx = x(h*60).toFixed(1);
    s += `<line class="rute" x1="${xx}" x2="${xx}" y1="${MT}" y2="${bunn}"/>`;
    s += `<text class="akse" x="${xx}" y="${H-3}" text-anchor="middle">${String(h).padStart(2,'0')}</text>`;
  }
  const merker = [];
  DAG.opptak.forEach(o => {
    if (!o.t) return;
    const arter = o.a.filter(([s2,c]) => c >= t);
    merker.push({m: min(o.t), lane: 0, klasse: arter.length ? '' : 'stille', id: 'h-'+o.f,
      tips: `<b>${esc(o.t)}</b> · ${o.rms == null ? 'opptak' : Math.round(o.rms) + ' dBFS'}<br>`
        + (arter.length ? arter.map(([s2,c]) => esc(navn(s2)) + ' ' + pct(c)).join('<br>') : 'ingen fugl hørt')});
  });
  DAG.kamera.forEach(k => {
    const arter = k.a.filter(([s2,c]) => c >= t);
    if (!arter.length || !k.t) return;
    merker.push({m: min(k.t), lane: 1, klasse: 'kam', id: 'h-'+k.f,
      tips: `<b>${esc(k.t)}</b> · kameraet<br>` + arter.map(([s2,c,n]) => esc(navn(s2)) + ' ' + pct(c) + (n > 1 ? ' ×' + n : '')).join('<br>')});
  });
  merker.forEach((v,i) => {
    const y = MT + v.lane*(LANE+GAP), xx = x(v.m);
    s += `<g data-i="${i}"><rect x="${(xx-6).toFixed(1)}" y="${y}" width="12" height="${LANE}" fill="transparent"/>`
      + `<rect class="merket ${v.klasse}" x="${(xx-2).toFixed(1)}" y="${y+4}" width="4" height="${LANE-8}" rx="2"/></g>`;
  });
  s += '</svg>';
  const boks = document.createElement('div');
  boks.innerHTML = s;
  const svg = boks.firstChild;
  svg.addEventListener('mousemove', e => {
    const g = e.target.closest('g[data-i]');
    if (!g) { tt.style.display = 'none'; return; }
    tips(merker[+g.dataset.i].tips, e);
  });
  svg.addEventListener('mouseleave', () => tt.style.display = 'none');
  svg.addEventListener('click', e => {
    const g = e.target.closest('g[data-i]');
    if (g) tilHendelse(merker[+g.dataset.i].id);
  });
  return svg;
}

function tilHendelse(id){
  let el = document.getElementById(id);
  if (!el) {                      // gjemt av et filter -- ta det bort foerst
    S.bare = 0; S.art = ''; tegn();
    el = document.getElementById(id);
  }
  if (!el) return;
  el.scrollIntoView({behavior:'smooth', block:'center'});
  el.classList.remove('blink'); void el.offsetWidth; el.classList.add('blink');
}

// ------------------------------------------------------------ artene i dag
function arterIDag(){
  const t = terskel(), m = {};
  const faa = sci => m[sci] || (m[sci] = {sci, n:0, det:0, best:0, sett:0, settBest:0, tider:[]});
  for (const o of DAG.opptak) for (const [sci,c,n] of o.a) {
    if (c < t) continue;
    const a = faa(sci); a.n++; a.det += n; a.best = Math.max(a.best, c); a.tider.push(o.t);
  }
  for (const k of DAG.kamera) for (const [sci,c] of k.a) {
    if (c < t) continue;
    const a = faa(sci); a.sett++; a.settBest = Math.max(a.settBest, c); a.tider.push(k.t);
  }
  const liste = Object.values(m);
  for (const a of liste) {
    a.tider.sort(); a.forst = a.tider[0]; a.sist = a.tider[a.tider.length-1]; a.navn = navn(a.sci);
  }
  liste.sort((x,y) => y.n - x.n || y.sett - x.sett || y.best - x.best);
  return liste;
}

function artKort(a){
  const usikker = Math.max(a.best, a.settBest) < DAG.sikker;
  const naar = a.forst === a.sist ? 'kl. ' + a.forst : a.forst + '–' + a.sist;
  const hva = a.n ? `<b>${a.n}</b> opptak` : 'bare sett';
  return `<button class="artkort ${S.art===a.sci?'valgt':''} ${usikker?'usikker':''}" data-sci="${esc(a.sci)}"
      title="${esc(a.sci)}${usikker ? ' — usikkert treff' : ''}">${bilde(a.sci)}
    <div><div class="navn">${esc(a.navn)}</div>
    <div class="nk">${hva}${a.sett ? ` · 📷 ${a.sett}` : ''} · ${esc(naar)}</div>
    <div class="nk">best ${pct(Math.max(a.best, a.settBest))}</div></div></button>`;
}

// ------------------------------------------------------------ forloepet
function chip(sci, conf, antallSett){
  const usikker = conf < DAG.sikker;
  return `<button class="chip ${S.art===sci?'valgt':''} ${usikker?'usikker':''}" data-sci="${esc(sci)}"
    title="${esc(sci)}${usikker?' — usikkert treff':''}">${bilde(sci)}<span>${esc(navn(sci))}</span>
    <span class="p">${pct(conf)}${antallSett > 1 ? ' ×' + antallSett : ''}</span></button>`;
}

function forlop(){
  const t = terskel();
  let rader = DAG.opptak.map(o => ({type:'lyd', t:o.t, o, arter:o.a.filter(([s,c]) => c >= t)}))
    .concat(DAG.kamera.map(k => ({type:'kam', t:k.t, k, arter:k.a.filter(([s,c]) => c >= t)})));
  const alt = rader.length;
  if (S.bare) rader = rader.filter(r => r.arter.length);
  if (S.art) rader = rader.filter(r => r.arter.some(([s]) => s === S.art));
  rader.sort((a,b) => S.rekke === 'kron' ? a.t.localeCompare(b.t) || a.type.localeCompare(b.type)
                                         : b.t.localeCompare(a.t) || a.type.localeCompare(b.type));
  const el = $('#forlop');
  if (!alt) {
    el.innerHTML = INDEKS.length
      ? '<p class="tom">Ingen opptak denne dagen. Bla deg til en annen dag i stripa over.</p>'
      : '<p class="tom">Ingen opptak i loggen ennå. Sida fylles etter hvert som utedelen sender inn.</p>';
    return;
  }
  if (!rader.length) {
    el.innerHTML = '<p class="tom">Ingen av opptakene passer filteret.</p>';
    return;
  }
  el.innerHTML = '<div class="forlop">' + rader.map(r => {
    if (r.type === 'kam') {
      const src = r.k.bilde ? `/kamerabilde/${encodeURIComponent(r.k.f)}.jpg${TOKEN}` : '';
      return `<div class="hendelse kam" id="h-${esc(r.k.f)}"><div class="kl">${esc(r.t)}</div>
        <div class="innhold">${src ? `<a href="${src}" target="_blank"><img class="kambilde" src="${src}" alt="" loading="lazy"></a>` : ''}
        <div style="flex:1;min-width:150px">${r.arter.map(([s,c,n]) => chip(s,c,n)).join('')}
        <div class="meta">sett av kameraet${r.k.bilde ? '' : ' · bildet er slettet'}</div></div></div>
        <div class="hoeyre"></div></div>`;
    }
    const vinduer = r.arter.reduce((a,[s,c,n]) => a + n, 0);
    const nivaa = [r.o.rms == null ? '' : Math.round(r.o.rms) + ' dBFS',
                   r.o.smell > 0.05 ? 'smell' : '',
                   vinduer ? antall(vinduer, 'vindu à 3 s', 'vinduer à 3 s') : ''].filter(Boolean).join(' · ');
    return `<div class="hendelse ${r.arter.length ? '' : 'stille'}" id="h-${esc(r.o.f)}"><div class="kl">${esc(r.t)}</div>
      <div class="innhold">${r.arter.length ? r.arter.map(([s,c]) => chip(s,c,1)).join('')
        : '<span class="ingenting">ingen fugl hørt</span>'}
      <div class="meta">${esc(nivaa)}</div></div>
      <div class="hoeyre">${r.o.lyd ? `<button class="spill" data-f="${esc(r.o.f)}">▶ spill</button>`
        : '<span class="meta">lyd slettet</span>'}</div></div>`;
  }).join('') + '</div>';
  el.querySelectorAll('.spill').forEach(b => b.onclick = () => spill(b));
  el.querySelectorAll('.chip').forEach(b => b.onclick = () => velgArt(b.dataset.sci));
}

function velgArt(sci){ S.art = S.art === sci ? '' : sci; tegn(); }

// ------------------------------------------------------------ avspilling
let lyd = null, lydKnapp = null;
function spill(b){
  if (lydKnapp === b && lyd && !lyd.paused) { lyd.pause(); b.classList.remove('aktiv'); b.textContent = '▶ spill'; return; }
  if (lyd) { lyd.pause(); if (lydKnapp) { lydKnapp.classList.remove('aktiv'); lydKnapp.textContent = '▶ spill'; } }
  lyd = new Audio(`/lyd/${encodeURIComponent(b.dataset.f)}.wav${TOKEN}`); lydKnapp = b;
  b.classList.add('aktiv'); b.textContent = '■ stopp';
  lyd.onended = () => { b.classList.remove('aktiv'); b.textContent = '▶ spill'; };
  lyd.onerror = () => { b.classList.remove('aktiv'); b.textContent = 'feil'; };
  lyd.play();
}

// ------------------------------------------------------------ tegning
function tegn(){
  if (!DAG) return;
  skrivHash();
  velger();
  // En dag uten opptak: doegnsporet og artslista har ingenting aa vise, og et
  // tomt kort er verre enn ikke noe kort.
  const tomDag = !DAG.opptak.length && !DAG.kamera.length;
  $('#s-doegn').hidden = tomDag;
  $('#s-arter').hidden = tomDag;
  if (!tomDag) $('#doegn').replaceChildren(doegn());
  const arter = tomDag ? [] : arterIDag();
  $('#arter').innerHTML = arter.length ? arter.map(artKort).join('')
    : '<p class="tom">Ingen arter over terskelen denne dagen. Hak av «vis usikre treff» for å se alt BirdNET meldte.</p>';
  $('#arter').querySelectorAll('.artkort').forEach(b => b.onclick = () => velgArt(b.dataset.sci));
  $('#historikk').hidden = !S.art;
  if (S.art) {
    $('#historikk').innerHTML = `<a href="/fugler#art=${encodeURIComponent(S.art)}&periode=alt">`
      + `Se hele historikken for ${esc(navn(S.art))} på fuglesida →</a>`;
  }
  document.querySelectorAll('[data-rekke]').forEach(b => b.classList.toggle('paa', b.dataset.rekke === S.rekke));
  $('#bare').checked = !!S.bare; $('#usikre').checked = !!S.usikre;
  forlop();
  $('#generert').textContent = INDEKS.length
    ? `${antall(INDEKS.length, 'dag', 'dager')} med opptak i loggen · oppdatert ${DAG.generert.replace('T',' ').slice(0,16)}`
    : 'Ingen opptak i loggen ennå.';
}

// ------------------------------------------------------------ oppstart
function kobleValg(){
  document.querySelectorAll('[data-rekke]').forEach(b => b.onclick = () => { S.rekke = b.dataset.rekke; tegn(); });
  $('#bare').onchange = e => { S.bare = e.target.checked ? 1 : 0; tegn(); };
  $('#usikre').onchange = e => { S.usikre = e.target.checked ? 1 : 0; tegn(); };
  // Hash-en er delelig -- da skal den ogsaa virke naar noen limer en inn i
  // adressefeltet paa en aapen side (replaceState under tegning gir ingen
  // hashchange, saa dette utloeses bare av brukeren selv).
  addEventListener('hashchange', () => {
    const foer = S.dato;
    lesHash();
    if (S.dato && S.dato !== foer) hent(S.dato); else tegn();
  });
  // Piltastene blar i dager -- men ikke mens en skriver i datofeltet.
  document.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target.tagName;
    if (t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
    if (e.key === 'ArrowLeft') { const b = $('#forrige'); if (!b.disabled) { b.click(); e.preventDefault(); } }
    if (e.key === 'ArrowRight') { const b = $('#neste'); if (!b.disabled) { b.click(); e.preventDefault(); } }
  });
}

lesHash();
kobleValg();
hent(S.dato);
})();
"""


def side() -> str:
    """Selve sida. Tom for data -- JavaScript-en henter /api/dag."""
    return """
  <section class="card dag">
    <div class="dagvelg">
      <div class="naa"><h2 id="tittel">…</h2><div class="under" id="under"></div></div>
      <div class="styring">
        <button class="pil" id="forrige" aria-label="forrige dag">←</button>
        <button class="pil" id="neste" aria-label="neste dag">→</button>
        <input type="date" id="dato" aria-label="velg dato">
        <button class="naaknapp" id="idag">i dag</button>
      </div>
    </div>
    <div class="stripe" id="stripe"></div>
    <p class="fotnote">Hver strek er en dag — høyden er antall arter. Klikk, eller bruk piltastene,
      for å bla. Dagene uten opptak står som tomme streker.</p>
  </section>

  <section class="card dag"><div class="rad" id="nokkel"></div></section>

  <section class="card dag" id="s-doegn">
    <h2>Når opptakene er tatt</h2>
    <div id="doegn"></div>
    <p class="fotnote">Ett merke per opptak gjennom døgnet: blått når noe ble hørt, grått når opptaket
      var tomt. Nederste spor er kameraet. Klikk på et merke for å hoppe til det i forløpet.</p>
  </section>

  <section class="card dag" id="s-arter">
    <h2>Hørt denne dagen</h2>
    <div class="arter" id="arter"></div>
    <p class="fotnote" id="historikk" hidden></p>
  </section>

  <section class="card dag">
    <div class="tabellvalg"><h2>Dagens forløp</h2>
      <div class="valg">
        <div class="knapper"><button data-rekke="ny">nyeste først</button><button data-rekke="kron">kronologisk</button></div>
        <label><input type="checkbox" id="bare"> bare med fugl</label>
        <label><input type="checkbox" id="usikre"> vis usikre treff</label>
      </div></div>
    <div id="forlop"><p class="tom">Henter …</p></div>
    <p class="fotnote">Opptakene er 60 sekunder. «Usikre treff» er dem BirdNET gir 25–50 % —
      de står stiplet, og de teller ikke med før du huker av. «Smell» betyr at opptaket begynte med
      et klippet smell (mikrofonen ikke klar). Lydfilene ligger 21 dager på serveren, kamerabildene like lenge.</p>
  </section>

  <p class="fotnote dag" id="generert"></p>
  <div id="tt" role="tooltip"></div>
  <script>""" + SKRIPT + "</script>\n"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--json" in sys.argv:
        print(json.dumps(samle(args[0] if args else None), ensure_ascii=False))
    else:
        print(f"<!doctype html><meta charset=utf-8><title>Fugleramme — dagen</title>"
              f"<style>{STIL}</style><body>{side()}</body>")
