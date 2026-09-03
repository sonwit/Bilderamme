#!/usr/bin/env python3
"""
fugler.py — fugledataene som dashboard: hvem vi har hoert, hvor ofte, hvor
sikkert, og naar paa doegnet. Med plansjebildet til hver art.

Helsesida (helse.py) svarer paa «virker anlegget?». Denne svarer paa «hva
har det hoert?» -- og lar en grave: periode, terskel for sikkerhet, minste
antall opptak, sortering, og én art om gangen med doegnrytme, dagsforloep,
sikkerhetsfordeling og hvert enkelt opptak med avspilling saa lenge lydfila
finnes (21 dager).

    python3 fugler.py > /tmp/fugler.html   # sida, frittstaaende (henter data fra /api/fugler)
    python3 fugler.py --json               # datagrunnlaget som JSON
    curl localhost:8090/fugler             # servert av frame_server.py

Sida er ett HTML-dokument med all logikk i nettleseren: serveren sender hele
observasjonsloggen som kompakt JSON (744 opptak = ~100 kB), og filtreringen
skjer lokalt -- det er det som gjoer det mulig aa dra i terskelen og se
tallene flytte seg med en gang. Kun stdlib paa serversiden, samme regel som
resten. Grafene er SVG tegnet i JavaScript, ingen biblioteker.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("FUGLE_DIR", HERE)
AUDIO = os.path.join(BASE, "audio")
DATA = os.path.join(BASE, "data")
PLATES = os.path.join(BASE, "plates")
FUGLER = os.path.join(PLATES, "fugler")

LYDFIL = re.compile(r"^fugl_\d{8}_\d{6}\.wav$")
BILDEFIL = re.compile(r"^kamera_\d{8}_\d{6}\.jpg$")
BILDER = os.path.join(BASE, "bilder")


# ----------------------------------------------------------------------
# Datagrunnlag
# ----------------------------------------------------------------------

def _slug(sci: str) -> str:
    return sci.strip().lower().replace(" ", "-")


def plansje(sci: str) -> str | None:
    """Den sittende 1:1-fuglen fra plansjebiblioteket, eller None."""
    p = os.path.join(FUGLER, _slug(sci) + ".png")
    return p if os.path.isfile(p) else None


def lydfil(navn: str) -> str | None:
    """Sti til et opptak, bare hvis navnet ser ut som et opptak og fila finnes."""
    if not LYDFIL.match(navn):
        return None
    p = os.path.join(AUDIO, navn)
    return p if os.path.isfile(p) else None


def kamerabilde(navn: str) -> str | None:
    """Sti til et kamerabilde, bare hvis navnet ser ut som ett og fila finnes."""
    if not BILDEFIL.match(navn):
        return None
    p = os.path.join(BILDER, navn)
    return p if os.path.isfile(p) else None


def _navn():
    try:
        sys.path.insert(0, HERE)
        from bird_names import habitat, norwegian_name
        return norwegian_name, habitat
    except Exception:  # noqa: BLE001
        return (lambda sci, common="": common or sci), (lambda sci: "")


def samle() -> dict:
    """Hele observasjonsloggen, kompakt. Ett element per opptak:
    f = filstamme, d = dato, t = klokkeslett, rms = nivaa (dBFS),
    smell = klipping i foerste sekund (%), lyd = om WAV-en finnes ennaa,
    a = [[latinsk navn, sikkerhet, antall 3-sekundersvinduer], ...]."""
    norsk, habitat = _navn()
    finnes = {os.path.basename(p) for p in glob.glob(os.path.join(AUDIO, "fugl_*.wav"))}
    opptak, arter = [], {}
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
                fil = o.get("file", "")
                a = o.get("audio") or {}
                arter_i = []
                for s in o.get("species", []):
                    sci = s.get("scientific_name", "")
                    if not sci:
                        continue
                    arter_i.append([sci, round(float(s.get("confidence", 0)), 3),
                                    int(s.get("detections", 0))])
                    if sci not in arter:
                        arter[sci] = {
                            "norsk": norsk(sci, s.get("common_name", "")),
                            "engelsk": s.get("common_name", ""),
                            "habitat": habitat(sci),
                            "plansje": plansje(sci) is not None,
                        }
                opptak.append({
                    "f": os.path.splitext(fil)[0],
                    "d": o.get("date", ""),
                    "t": (o.get("recorded_at") or "")[11:16],
                    "rms": a.get("rms_dbfs"),
                    "smell": a.get("smell_pct"),
                    "lyd": fil in finnes,
                    "a": arter_i,
                })
    except FileNotFoundError:
        pass

    # Kameraet i vinduet (bilde_analyze.py -> data/kamera.jsonl). Bare bilder
    # med noe paa: f = filstamme, d/t = naar, bilde = om JPEG-en finnes ennaa,
    # a = [[latinsk navn, sikkerhet, antall], ...]. Arter kameraet ser men
    # mikrofonen aldri hoerer -- ekorn, for eksempel -- faar ogsaa en
    # oppfoering i arter, med det norske navnet modellen ga hvis vi ikke har
    # et selv.
    kamera, tomme = [], 0
    try:
        with open(os.path.join(DATA, "kamera.jsonl")) as f:
            for rad in f:
                rad = rad.strip()
                if not rad:
                    continue
                try:
                    k = json.loads(rad)
                except ValueError:
                    continue
                if not k.get("species"):
                    tomme += 1
                    continue
                fil = k.get("file", "")
                a_i = []
                for sp in k["species"]:
                    sci = sp.get("scientific_name", "").strip()
                    if not sci:
                        continue
                    a_i.append([sci, round(float(sp.get("confidence", 0)), 2),
                                int(sp.get("antall", 1) or 1)])
                    if sci not in arter:
                        eget = norsk(sci, "")
                        arter[sci] = {
                            "norsk": eget if eget and eget != sci else (sp.get("norsk") or sp.get("common_name") or sci),
                            "engelsk": sp.get("common_name", ""),
                            "habitat": habitat(sci),
                            "plansje": plansje(sci) is not None,
                        }
                kamera.append({
                    "f": os.path.splitext(fil)[0],
                    "d": k.get("date", ""),
                    "t": (k.get("captured_at") or "")[11:16],
                    "bilde": kamerabilde(fil) is not None,
                    "a": a_i,
                })
    except FileNotFoundError:
        pass
    return {
        "generert": datetime.datetime.now().isoformat(timespec="seconds"),
        "opptak": opptak,
        "arter": arter,
        "kamera": kamera,
        "kamera_tomme": tomme,
    }


# ----------------------------------------------------------------------
# Sida
# ----------------------------------------------------------------------

STIL = r"""
  .fugler{--serie1:#2a78d6;--serie2:#eb6834;--flate:var(--card)}
  @media (prefers-color-scheme: dark){.fugler{--serie1:#3987e5;--serie2:#d95926}}
  .fugler .filtre{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin:4px 0 12px}
  .fugler .filtre>div{display:flex;flex-direction:column;gap:4px}
  .fugler .filtre label{margin:0;font-size:.78rem}
  .fugler .knapper{display:flex;gap:4px;flex-wrap:wrap}
  .fugler .knapper button{padding:7px 11px;font-size:.85rem;font-weight:500;
    background:transparent;color:var(--ink);border:1px solid var(--line)}
  .fugler .knapper button.paa{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
  .fugler input[type=date],.fugler input[type=search],.fugler select{padding:7px 10px;border-radius:9px;
    border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit;font-size:.9rem}
  .fugler input[type=range]{width:150px;accent-color:var(--accent)}
  .fugler .verdi{font-variant-numeric:tabular-nums;font-size:.85rem;color:var(--muted)}
  .fugler .rad{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 4px}
  .fugler .tall{flex:1;min-width:118px;background:var(--bg);border:1px solid var(--line);
    border-radius:12px;padding:10px 12px}
  .fugler .tall b{display:block;font-size:1.35rem;line-height:1.2}
  .fugler .tall span{font-size:.78rem;color:var(--muted)}
  .fugler .grafer{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
  .fugler .grafer .card{margin:0}
  .fugler .graf{width:100%;height:auto;display:block;margin:6px 0 2px;overflow:visible}
  .fugler .stolpe{fill:var(--serie1)}
  .fugler .stolpe.dempet{fill:var(--serie2)}
  .fugler .treff{fill:transparent;cursor:crosshair}
  .fugler .treff:hover+.stolpe,.fugler g:hover .stolpe{opacity:.75}
  .fugler .akse{fill:var(--muted);font-size:10px}
  .fugler .rute{stroke:var(--line);stroke-width:1}
  .fugler .tom{color:var(--muted);font-size:.9rem;margin:8px 0}
  .fugler .rutenett{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
  .fugler .art{display:flex;gap:12px;align-items:center;padding:10px;border:1px solid var(--line);
    border-radius:14px;background:var(--bg);cursor:pointer;text-align:left;color:var(--ink);font:inherit}
  .fugler .art:hover{border-color:var(--accent)}
  .fugler .art.valgt{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent) inset}
  .fugler .art img,.fugler .art .ingen{width:72px;height:72px;object-fit:contain;flex:none;
    background:#fff;border-radius:10px;border:1px solid var(--line)}
  .fugler .art .ingen{display:flex;align-items:center;justify-content:center;color:var(--muted);
    font-size:1.6rem;background:var(--card)}
  .fugler .art .navn{font-weight:600;line-height:1.25}
  .fugler .art .lat{font-style:italic;color:var(--muted);font-size:.8rem}
  .fugler .art .nk{font-size:.82rem;color:var(--muted);margin-top:4px;font-variant-numeric:tabular-nums}
  .fugler .art .nk b{color:var(--ink);font-weight:600}
  .fugler .detalj .topp{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
  .fugler .detalj .topp img{width:140px;height:140px;object-fit:contain;background:#fff;
    border-radius:12px;border:1px solid var(--line)}
  .fugler .detalj h2{font-size:1.3rem;margin:0}
  .fugler .lukk{float:right;background:transparent;color:var(--muted);border:1px solid var(--line);
    padding:5px 10px;font-weight:500}
  .fugler table{width:100%;border-collapse:collapse;font-size:.9rem}
  .fugler th{text-align:left;font-weight:600;font-size:.78rem;color:var(--muted);padding:6px 6px 6px 0;
    border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap}
  .fugler th.sortert{color:var(--ink)}
  .fugler td{padding:6px 6px 6px 0;border-bottom:1px solid var(--line);vertical-align:middle}
  .fugler td.n,.fugler th.n{text-align:right;font-variant-numeric:tabular-nums}
  .fugler td img{width:34px;height:34px;object-fit:contain;background:#fff;border-radius:7px;
    border:1px solid var(--line);vertical-align:middle;margin-right:8px}
  .fugler .spill{padding:4px 10px;font-size:.8rem;font-weight:500;background:transparent;
    color:var(--accent);border:1px solid var(--accent)}
  .fugler .spill.aktiv{background:var(--accent);color:var(--accent-ink)}
  .fugler .prosent{display:inline-block;min-width:44px}
  .fugler .sikker{display:inline-block;height:6px;border-radius:3px;background:var(--serie1);vertical-align:middle}
  .fugler .tabellvalg{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
  .fugler .tabellvalg h2{margin:0}
  #tt{position:fixed;pointer-events:none;z-index:9;background:var(--card);color:var(--ink);
    border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:.82rem;line-height:1.35;
    box-shadow:var(--shadow);max-width:260px;display:none;white-space:nowrap}
  #tt b{font-variant-numeric:tabular-nums}
  #tt .mk{display:inline-block;width:10px;height:3px;border-radius:2px;background:var(--serie1);
    vertical-align:middle;margin-right:6px}
  .fugler .fotnote{color:var(--muted);font-size:.8rem;margin:10px 0 0}
  .fugler .kam{display:flex;gap:10px;flex-wrap:wrap}
  .fugler .kam a{display:block;width:150px;text-decoration:none;color:var(--ink)}
  .fugler .kam img{width:150px;height:110px;object-fit:cover;border-radius:10px;border:1px solid var(--line);
    background:var(--bg);display:block}
  .fugler .kam .tekst{font-size:.78rem;color:var(--muted);margin-top:3px;line-height:1.3}
  .fugler .kam .tekst b{color:var(--ink);font-weight:600}
  .fugler .sett{display:inline-block;padding:1px 7px;border-radius:999px;font-size:.74rem;
    background:rgba(42,120,214,.14);color:var(--serie1);margin-left:4px;vertical-align:middle}
"""

# JavaScript-en. Alt som kan endre seg (filtre, valgt art, kort/tabell) ligger
# i URL-hashen, saa en visning kan deles som lenke.
SKRIPT = r"""
(function(){
'use strict';
const q = new URLSearchParams(location.search);
const TOKEN = q.get('token') ? '?token=' + encodeURIComponent(q.get('token')) : '';
const $ = s => document.querySelector(s);
const tt = $('#tt');
const MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];
let DATA = null;              // {opptak, arter}
let S = {periode:'30', fra:'', til:'', minConf:0.5, minOpptak:1, sok:'', sort:'opptak', visning:'kort', art:''};

// ------------------------------------------------------------ hjelpere
function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function pct(v){ return Math.round(v*100) + ' %'; }
function dato(iso){ if(!iso) return '–'; const d = new Date(iso+'T00:00'); return d.getDate() + '. ' + MND[d.getMonth()]; }
function datoLang(iso){ if(!iso) return '–'; const d = new Date(iso+'T00:00'); return d.getDate() + '. ' + MND[d.getMonth()] + ' ' + d.getFullYear(); }
function isoDag(d){ return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }  // lokal dato, ikke UTC
function median(xs){ if(!xs.length) return 0; const s=[...xs].sort((a,b)=>a-b); const m=s.length>>1; return s.length%2 ? s[m] : (s[m-1]+s[m])/2; }
function dagerMellom(a,b){ const ut=[]; for(let d=new Date(a+'T00:00'); isoDag(d)<=b; d.setDate(d.getDate()+1)) ut.push(isoDag(d)); return ut; }
function navn(sci){ const a = DATA.arter[sci]; return a ? a.norsk : sci; }
function kamKort(k, sci){
  // Ett kamerabilde som miniatyr med tid og hva modellen saa. sci: hvilken
  // art som skal staa foerst i teksten (i artsvisningen), ellers alle.
  const arter = k.a.filter(([s,c]) => c >= S.minConf);
  const tekst = (sci ? arter.filter(([s]) => s === sci).concat(arter.filter(([s]) => s !== sci)) : arter)
    .map(([s,c,n]) => `<b>${esc(navn(s))}</b> ${Math.round(c*100)} %${n > 1 ? ' ×' + n : ''}`).join(', ');
  const src = k.bilde ? `/kamerabilde/${encodeURIComponent(k.f)}.jpg${TOKEN}` : '';
  const img = src ? `<img src="${src}" alt="" loading="lazy">` : `<div class="ingen" style="width:150px;height:110px">📷</div>`;
  return `<a href="${src || '#'}" ${src ? 'target="_blank"' : ''}>${img}<div class="tekst">${esc(dato(k.d))} kl. ${esc(k.t)}<br>${tekst}</div></a>`;
}

function bilde(sci, kl){ const a = DATA.arter[sci]; return a && a.plansje
  ? `<img class="${kl||''}" src="/plansje/${encodeURIComponent(sci.toLowerCase().replace(/ /g,'-'))}.png${TOKEN}" alt="" loading="lazy">`
  : `<div class="ingen ${kl||''}" aria-hidden="true">${esc(navn(sci)[0]||'?')}</div>`; }

function lesHash(){
  const h = new URLSearchParams(location.hash.slice(1));
  for (const k of Object.keys(S)) if (h.has(k)) S[k] = h.get(k);
  S.minConf = +S.minConf; S.minOpptak = +S.minOpptak;
}
function skrivHash(){
  const h = new URLSearchParams();
  for (const [k,v] of Object.entries(S)) if (v !== '' && v !== null) h.set(k, v);
  history.replaceState(null, '', '#' + h.toString());
}

// ------------------------------------------------------------ periode
function grenser(){
  const alle = DATA.opptak.map(o => o.d).filter(Boolean).sort();
  const siste = alle[alle.length-1] || isoDag(new Date());
  const forste = alle[0] || siste;
  if (S.periode === 'egen') return [S.fra || forste, S.til || siste];
  if (S.periode === 'alt') return [forste, siste];
  const n = +S.periode; const til = siste;
  const d = new Date(til+'T00:00'); d.setDate(d.getDate() - (n-1));
  return [isoDag(d) < forste ? forste : isoDag(d), til];
}

// ------------------------------------------------------------ utvalg
function utvalg(){
  const [fra, til] = grenser();
  const opptak = DATA.opptak.filter(o => o.d >= fra && o.d <= til);
  const arter = {};
  for (const o of opptak) for (const [sci, conf, det] of o.a) {
    if (conf < S.minConf) continue;
    const a = arter[sci] || (arter[sci] = {sci, opptak:[], dager:new Set(), conf:[], det:0, timer:new Array(24).fill(0), perDag:{}});
    a.opptak.push({o, conf, det}); a.dager.add(o.d); a.conf.push(conf); a.det += det;
    a.timer[+o.t.slice(0,2)]++; a.perDag[o.d] = (a.perDag[o.d]||0) + 1;
  }
  // Kameraet: samme terskel for sikkerhet. En art som bare er sett, ikke
  // hoert, faar en oppfoering med null opptak -- den skal ogsaa staa i lista.
  const kamera = (DATA.kamera || []).filter(k => k.d >= fra && k.d <= til);
  for (const k of kamera) for (const [sci, conf, antall] of k.a) {
    if (conf < S.minConf) continue;
    const a = arter[sci] || (arter[sci] = {sci, opptak:[], dager:new Set(), conf:[], det:0, timer:new Array(24).fill(0), perDag:{}});
    (a.sett || (a.sett = [])).push({k, conf, antall});
  }
  let liste = Object.values(arter).filter(a => a.opptak.length >= S.minOpptak || (a.sett || []).length);
  for (const a of liste) {
    a.sett = a.sett || [];
    a.n = a.opptak.length; a.best = a.conf.length ? Math.max(...a.conf) : 0; a.median = median(a.conf);
    const tider = a.opptak.map(x => x.o.d + ' ' + x.o.t).concat(a.sett.map(x => x.k.d + ' ' + x.k.t)).sort();
    a.sist = tider[tider.length - 1]; a.forst = tider[0];
    a.settBest = a.sett.length ? Math.max(...a.sett.map(x => x.conf)) : 0;
    a.settDager = new Set(a.sett.map(x => x.k.d)).size;
    a.navn = navn(a.sci);
  }
  const sok = S.sok.trim().toLowerCase();
  if (sok) liste = liste.filter(a => a.navn.toLowerCase().includes(sok) || a.sci.toLowerCase().includes(sok));
  const sorter = {
    opptak: (x,y) => y.n - x.n || y.sett.length - x.sett.length || y.best - x.best,
    sikkerhet: (x,y) => Math.max(y.best, y.settBest) - Math.max(x.best, x.settBest) || y.n - x.n,
    sett: (x,y) => y.sett.length - x.sett.length || y.n - x.n,
    sist: (x,y) => (y.sist > x.sist) - (y.sist < x.sist),
    navn: (x,y) => x.navn.localeCompare(y.navn, 'nb'),
    dager: (x,y) => y.dager.size - x.dager.size || y.n - x.n,
  }[S.sort] || ((x,y) => y.n - x.n);
  liste.sort(sorter);
  return {fra, til, opptak, arter, liste, kamera};
}

// ------------------------------------------------------------ grafer
// Stolpediagram i SVG. verdier: [{etikett, verdi, tips, klasse}]. Hele
// kolonnen er treffflate, ikke bare stolpen.
function stolper(verdier, opts){
  // Bred og lav: SVG-en skaleres til kortets bredde, saa forholdet her
  // bestemmer hoeyden paa skjermen. 640x150 gir ~150 px i et 660 px kort.
  const W = 640, H = opts.h || 150, ML = 28, MB = 22, MT = 8;
  const top = Math.max(1, ...verdier.map(v => v.verdi));
  const n = verdier.length, bw = (W - ML - 6) / n;
  const y = v => MT + (1 - v/top) * (H - MT - MB);
  let s = `<svg viewBox="0 0 ${W} ${H}" class="graf" role="img" aria-label="${esc(opts.tittel||'')}">`;
  const steg = top <= 5 ? 1 : top <= 12 ? 2 : top <= 30 ? 5 : top <= 60 ? 10 : Math.ceil(top/5/10)*10;
  for (let g = 0; g <= top; g += steg) {
    s += `<line x1="${ML}" x2="${W-6}" y1="${y(g).toFixed(1)}" y2="${y(g).toFixed(1)}" class="rute"/>`;
    s += `<text x="${ML-5}" y="${(y(g)+3.5).toFixed(1)}" class="akse" text-anchor="end">${g}</text>`;
  }
  verdier.forEach((v, i) => {
    const x = ML + i*bw, h = Math.max(0, y(0) - y(v.verdi));
    const hh = v.verdi > 0 ? Math.max(h, 2) : 0;
    s += `<g data-i="${i}"><rect class="treff" x="${x.toFixed(1)}" y="${MT}" width="${bw.toFixed(1)}" height="${H-MT-MB}"/>`;
    if (hh) s += `<rect class="stolpe ${v.klasse||''}" x="${(x+1).toFixed(1)}" y="${(y(0)-hh).toFixed(1)}" width="${Math.max(1,bw-2).toFixed(1)}" height="${hh.toFixed(1)}" rx="${Math.min(3,bw/3).toFixed(1)}"/>`;
    if (v.etikett && (n <= 16 || i % Math.ceil(n/12) === 0)) s += `<text x="${(x+bw/2).toFixed(1)}" y="${H-6}" class="akse" text-anchor="middle">${esc(v.etikett)}</text>`;
    s += '</g>';
  });
  s += '</svg>';
  const el = document.createElement('div'); el.innerHTML = s;
  const svg = el.firstChild;
  svg.addEventListener('mousemove', e => {
    const g = e.target.closest('g[data-i]'); if (!g) { tt.style.display='none'; return; }
    const v = verdier[+g.dataset.i];
    tt.innerHTML = v.tips; tt.style.display = 'block';
    const r = tt.getBoundingClientRect();
    tt.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 8) + 'px';
    tt.style.top = Math.max(8, e.clientY - r.height - 12) + 'px';
  });
  svg.addEventListener('mouseleave', () => tt.style.display = 'none');
  return svg;
}

function grafDager(u, arter, sci){
  const dager = dagerMellom(u.fra, u.til);
  const perDag = {};
  for (const o of u.opptak) perDag[o.d] = perDag[o.d] || {opptak:0, arter:new Set(), n:0};
  for (const o of u.opptak) { perDag[o.d].opptak++; for (const [s,c] of o.a) if (c >= S.minConf && (!sci || s === sci)) { perDag[o.d].arter.add(s); perDag[o.d].n++; } }
  const verdier = dager.map(d => {
    const p = perDag[d] || {opptak:0, arter:new Set(), n:0};
    const v = sci ? p.n : p.arter.size;
    const tips = sci
      ? `<b>${v}</b> opptak med ${esc(navn(sci))}<br>${esc(datoLang(d))} · ${p.opptak} opptak i alt`
      : `<b>${v}</b> arter · ${esc(datoLang(d))}<br>${p.opptak} opptak` + (p.arter.size ? '<br>' + [...p.arter].slice(0,6).map(navn).map(esc).join(', ') + (p.arter.size > 6 ? ' …' : '') : '');
    return {etikett: dager.length <= 16 ? String(+d.slice(8)) : (d.slice(8) === '01' || dager.indexOf(d) === 0 ? dato(d) : ''), verdi: v, tips, klasse: p.opptak === 0 ? 'dempet' : ''};
  });
  return stolper(verdier, {tittel: sci ? 'Opptak per dag' : 'Arter per dag'});
}

function grafTimer(u, sci){
  const timer = new Array(24).fill(0), alle = new Array(24).fill(0);
  for (const o of u.opptak) { const h = +o.t.slice(0,2); alle[h]++; let hit = false; for (const [s,c] of o.a) if (c >= S.minConf && (!sci || s === sci)) hit = true; if (hit) timer[h]++; }
  return stolper(timer.map((v,h) => ({etikett: h % 3 === 0 ? String(h).padStart(2,'0') : '', verdi: v,
    tips: `<b>${v}</b> av ${alle[h]} opptak kl. ${String(h).padStart(2,'0')}` + (sci ? ` med ${esc(navn(sci))}` : ' med fugl')})), {tittel:'Når på døgnet'});
}

function grafSikkerhet(u, sci){
  const bins = new Array(15).fill(0);  // 0,25–1,00 i steg paa 0,05
  for (const o of u.opptak) for (const [s,c] of o.a) if (!sci || s === sci) bins[Math.min(14, Math.max(0, Math.floor((c - 0.25) / 0.05)))]++;
  return stolper(bins.map((v,i) => { const lo = 0.25 + i*0.05; return {etikett: i % 3 === 0 ? Math.round(lo*100) + '' : '', verdi: v,
    tips: `<b>${v}</b> treff på ${Math.round(lo*100)}–${Math.round((lo+0.05)*100)} %` + (lo + 0.05 <= S.minConf ? '<br>under terskelen din' : ''), klasse: lo + 0.05 <= S.minConf ? 'dempet' : ''}; }), {tittel:'Sikkerhet'});
}

// ------------------------------------------------------------ tegning
function tall(v, etikett){ return `<div class="tall"><b>${esc(v)}</b><span>${esc(etikett)}</span></div>`; }

function tegn(){
  if (!DATA) return;
  const u = utvalg();
  skrivHash();
  $('#periode-tekst').textContent = datoLang(u.fra) + ' – ' + datoLang(u.til);
  const medFugl = u.opptak.filter(o => o.a.some(([s,c]) => c >= S.minConf)).length;
  const det = u.liste.reduce((a,x) => a + x.n, 0);
  const dagerMed = new Set(u.opptak.filter(o => o.a.some(([s,c]) => c >= S.minConf)).map(o => o.d)).size;
  const sett = u.kamera.filter(k => k.a.some(([s,c]) => c >= S.minConf)).length;
  $('#nokkel').innerHTML = tall(u.liste.length, 'arter') + tall(u.opptak.length, 'opptak') + tall(medFugl, 'opptak med fugl')
    + tall(det, 'artstreff') + tall(dagerMed + ' av ' + dagerMellom(u.fra, u.til).length, 'dager med fugl')
    + tall(sett, 'sett av kameraet');
  const kamSiste = [...u.kamera].filter(k => k.a.some(([s,c]) => c >= S.minConf)).sort((x,y) => (y.d + y.t).localeCompare(x.d + x.t)).slice(0, 8);
  $('#kamera').hidden = !DATA.kamera || !DATA.kamera.length;
  $('#kamera-liste').innerHTML = kamSiste.length ? '<div class="kam">' + kamSiste.map(k => kamKort(k)).join('') + '</div>'
    : '<p class="tom">Ingen kamerafunn i perioden.</p>';
  $('#g-dager').replaceChildren(grafDager(u)); $('#g-timer').replaceChildren(grafTimer(u)); $('#g-sikkerhet').replaceChildren(grafSikkerhet(u));

  const liste = $('#liste');
  if (!u.liste.length) { liste.innerHTML = '<p class="tom">Ingen arter i utvalget. Senk terskelen eller utvid perioden.</p>'; }
  else if (S.visning === 'tabell') {
    const kol = [['navn','Art',''],['opptak','Opptak','n'],['dager','Dager','n'],['sikkerhet','Best','n'],['median','Median','n'],['det','Vinduer','n'],['sett','Sett','n'],['sist','Sist','']];
    liste.innerHTML = '<table><thead><tr>' + kol.map(([k,t,c]) => `<th class="${c} ${S.sort===k?'sortert':''}" data-sort="${k}">${t}${S.sort===k?' ↓':''}</th>`).join('') + '</tr></thead><tbody>'
      + u.liste.map(a => `<tr><td><button class="art velg" data-sci="${esc(a.sci)}" style="padding:0;border:0;background:none;gap:0">${bilde(a.sci)}<span><span class="navn">${esc(a.navn)}</span> <span class="lat">${esc(a.sci)}</span></span></button></td>`
        + `<td class="n">${a.n}</td><td class="n">${a.dager.size}</td><td class="n">${a.n ? `<span class="sikker" style="width:${Math.round(a.best*40)}px"></span> ` + pct(a.best) : '–'}</td><td class="n">${a.n ? pct(a.median) : '–'}</td><td class="n">${a.det}</td><td class="n">${a.sett.length ? a.sett.length + ' 📷' : '–'}</td><td>${esc(dato(a.sist.slice(0,10)))} ${esc(a.sist.slice(11))}</td></tr>`).join('') + '</tbody></table>';
    liste.querySelectorAll('th[data-sort]').forEach(th => th.onclick = () => { S.sort = th.dataset.sort === 'median' ? 'sikkerhet' : th.dataset.sort; tegn(); });
  } else {
    liste.innerHTML = '<div class="rutenett">' + u.liste.map(a => `<button class="art velg ${S.art===a.sci?'valgt':''}" data-sci="${esc(a.sci)}">${bilde(a.sci)}<div><div class="navn">${esc(a.navn)}</div><div class="lat">${esc(a.sci)}</div>`
      + `<div class="nk">${a.n ? `<b>${a.n}</b> opptak · <b>${a.dager.size}</b> ${a.dager.size===1?'dag':'dager'}` : 'bare sett, ikke hørt'}${a.sett.length ? `<span class="sett">📷 ${a.sett.length}</span>` : ''}<br>${a.n ? `best <b>${pct(a.best)}</b> · ` : ''}sist ${esc(dato(a.sist.slice(0,10)))}</div></div></button>`).join('') + '</div>';
  }
  liste.querySelectorAll('.velg').forEach(b => b.onclick = () => { S.art = S.art === b.dataset.sci ? '' : b.dataset.sci; tegn(); if (S.art) $('#detalj').scrollIntoView({behavior:'smooth', block:'start'}); });
  tegnDetalj(u);
}

function tegnDetalj(u){
  const d = $('#detalj');
  const a = u.arter[S.art];
  if (!S.art || !a) { d.hidden = true; d.innerHTML = ''; return; }
  a.n = a.opptak.length; a.best = a.conf.length ? Math.max(...a.conf) : 0; a.median = median(a.conf);
  a.sett = a.sett || [];
  const info = DATA.arter[S.art] || {};
  const settHtml = a.sett.length
    ? `<h2 style="margin-top:16px">Sett av kameraet <span class="sett">📷 ${a.sett.length}</span></h2><div class="kam">`
      + [...a.sett].sort((x,y) => (y.k.d + y.k.t).localeCompare(x.k.d + x.k.t)).slice(0, 24).map(x => kamKort(x.k, S.art)).join('') + '</div>'
    : '';
  const rader = [...a.opptak].sort((x,y) => (y.o.d + y.o.t).localeCompare(x.o.d + x.o.t));
  d.hidden = false;
  d.innerHTML = `<button class="lukk" id="lukk">lukk ×</button><div class="topp">${bilde(S.art)}<div><h2>${esc(navn(S.art))}</h2>
    <div class="lat">${esc(S.art)}${info.engelsk ? ' · ' + esc(info.engelsk) : ''}${info.habitat ? ' · ' + esc(info.habitat) : ''}${info.plansje ? '' : ' · ingen plansje ennå'}</div>
    <div class="rad" style="margin-top:10px">${tall(a.n, 'opptak')}${tall(a.dager.size, 'dager hørt')}${tall(a.n ? pct(a.best) : '–', 'best')}${tall(a.n ? pct(a.median) : '–', 'median')}${tall(a.det, 'vinduer à 3 s')}${tall(a.sett.length, 'sett av kameraet')}</div>
    <div class="fotnote">Først ${esc(datoLang(a.forst.slice(0,10)))} kl. ${esc(a.forst.slice(11))} · sist ${esc(datoLang(a.sist.slice(0,10)))} kl. ${esc(a.sist.slice(11))}</div></div></div>
    ${settHtml}
    <div class="grafer" style="margin-top:14px"><div class="card"><h2>Opptak per dag</h2><div id="d-dager"></div></div>
    <div class="card"><h2>Når på døgnet</h2><div id="d-timer"></div></div><div class="card"><h2>Sikkerhet</h2><div id="d-sikkerhet"></div></div></div>
    <h2 style="margin-top:16px">Opptakene</h2><table><thead><tr><th>Når</th><th class="n">Sikkerhet</th><th class="n">Vinduer</th><th class="n">Nivå</th><th>Også i opptaket</th><th></th></tr></thead><tbody>`
    + rader.map(r => `<tr><td>${esc(datoLang(r.o.d))} ${esc(r.o.t)}</td><td class="n"><span class="sikker" style="width:${Math.round(r.conf*40)}px"></span> ${pct(r.conf)}</td><td class="n">${r.det}</td>`
      + `<td class="n">${r.o.rms == null ? '–' : Math.round(r.o.rms) + ' dBFS'}${r.o.smell > 0.05 ? ' · smell' : ''}</td>`
      + `<td>${r.o.a.filter(([s]) => s !== S.art).map(([s,c]) => `${esc(navn(s))} ${Math.round(c*100)}`).join(', ')}</td>`
      + `<td>${r.o.lyd ? `<button class="spill" data-f="${esc(r.o.f)}">▶ spill</button>` : '<span class="lat">lyd slettet</span>'}</td></tr>`).join('')
    + '</tbody></table><p class="fotnote">Lydfilene ligger 21 dager på serveren. «Smell» betyr at opptaket begynte med et klippet smell (mikrofonen ikke klar).</p>';
  if (a.n) { $('#d-dager').replaceChildren(grafDager(u, u.arter, S.art)); $('#d-timer').replaceChildren(grafTimer(u, S.art)); $('#d-sikkerhet').replaceChildren(grafSikkerhet(u, S.art)); }
  else d.querySelectorAll('.grafer, .grafer + h2, .grafer + h2 + table, .grafer + h2 + table + p').forEach(el => el.remove());
  $('#lukk').onclick = () => { S.art = ''; tegn(); };
  d.querySelectorAll('.spill').forEach(b => b.onclick = () => spill(b));
}

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

// ------------------------------------------------------------ filtre
function kobleFiltre(){
  document.querySelectorAll('[data-periode]').forEach(b => b.onclick = () => { S.periode = b.dataset.periode; visPeriode(); tegn(); });
  $('#fra').onchange = e => { S.fra = e.target.value; S.periode = 'egen'; visPeriode(); tegn(); };
  $('#til').onchange = e => { S.til = e.target.value; S.periode = 'egen'; visPeriode(); tegn(); };
  $('#minConf').oninput = e => { S.minConf = +e.target.value; $('#minConf-v').textContent = pct(S.minConf); tegn(); };
  $('#minOpptak').onchange = e => { S.minOpptak = +e.target.value; tegn(); };
  $('#sort').onchange = e => { S.sort = e.target.value; tegn(); };
  $('#sok').oninput = e => { S.sok = e.target.value; tegn(); };
  document.querySelectorAll('[data-visning]').forEach(b => b.onclick = () => { S.visning = b.dataset.visning; visPeriode(); tegn(); });
}
function visPeriode(){
  document.querySelectorAll('[data-periode]').forEach(b => b.classList.toggle('paa', b.dataset.periode === S.periode));
  document.querySelectorAll('[data-visning]').forEach(b => b.classList.toggle('paa', b.dataset.visning === S.visning));
  const [fra, til] = grenser(); $('#fra').value = fra; $('#til').value = til;
  $('#minConf').value = S.minConf; $('#minConf-v').textContent = pct(S.minConf);
  $('#minOpptak').value = S.minOpptak; $('#sort').value = S.sort; $('#sok').value = S.sok;
}

lesHash();
fetch('/api/fugler' + TOKEN).then(r => r.json()).then(d => {
  DATA = d; kobleFiltre(); visPeriode(); tegn();
  $('#generert').textContent = 'Data fra ' + d.opptak.length + ' opptak · ' + Object.keys(d.arter).length + ' arter i alt · oppdatert ' + d.generert.replace('T', ' ').slice(0, 16);
}).catch(e => { $('#liste').innerHTML = '<p class="tom">Klarte ikke hente data: ' + esc(e.message) + '</p>'; });
})();
"""


def side() -> str:
    """Selve sida. Tom for data -- JavaScript-en henter /api/fugler."""
    return """
  <section class="card fugler">
    <div class="filtre">
      <div><label>Periode</label><div class="knapper">
        <button data-periode="7">7 dager</button><button data-periode="21">21 dager</button>
        <button data-periode="30">30 dager</button><button data-periode="alt">alt</button></div></div>
      <div><label>Fra</label><input type="date" id="fra"></div>
      <div><label>Til</label><input type="date" id="til"></div>
      <div><label>Minste sikkerhet <span class="verdi" id="minConf-v"></span></label>
        <input type="range" id="minConf" min="0.25" max="0.95" step="0.05"></div>
      <div><label>Minst</label><select id="minOpptak"><option value="1">1 opptak</option>
        <option value="2">2 opptak</option><option value="3">3 opptak</option><option value="5">5 opptak</option></select></div>
      <div><label>Sortering</label><select id="sort"><option value="opptak">flest opptak</option>
        <option value="dager">flest dager</option><option value="sikkerhet">sikrest</option>
        <option value="sett">oftest sett</option>
        <option value="sist">sist hørt</option><option value="navn">navn</option></select></div>
      <div><label>Søk</label><input type="search" id="sok" placeholder="art"></div>
    </div>
    <div class="verdi" id="periode-tekst"></div>
    <div class="rad" id="nokkel" style="margin-top:8px"></div>
  </section>

  <div class="grafer fugler">
    <div class="card"><h2>Arter per dag</h2><div id="g-dager"></div></div>
    <div class="card"><h2>Når på døgnet</h2><div id="g-timer"></div></div>
    <div class="card"><h2>Sikkerhet på alle treff</h2><div id="g-sikkerhet"></div>
      <p class="fotnote">Treff under terskelen din er tegnet i oransje.</p></div>
  </div>

  <section class="card fugler" id="kamera" hidden>
    <h2>Sist sett av kameraet</h2>
    <div id="kamera-liste"></div>
    <p class="fotnote">Kameraet i kontorvinduet, rettet mot materne. Klikk på et bilde for full størrelse.
      Arten er modellens tolkning av bildet, med dens egen sikkerhet.</p>
  </section>

  <section class="card fugler">
    <div class="tabellvalg"><h2>Artene</h2><div class="knapper">
      <button data-visning="kort">kort</button><button data-visning="tabell">tabell</button></div></div>
    <div id="liste"><p class="tom">Henter data …</p></div>
  </section>

  <section class="card fugler detalj" id="detalj" hidden></section>
  <p class="fotnote fugler" id="generert"></p>
  <div id="tt" role="tooltip"></div>
  <script>""" + SKRIPT + "</script>\n"


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(samle(), ensure_ascii=False))
    else:
        print(f"<!doctype html><meta charset=utf-8><title>Fugleramme — fugler</title>"
              f"<style>{STIL}</style><body>{side()}</body>")
