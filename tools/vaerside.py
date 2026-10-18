#!/usr/bin/env python3
"""
vaerside.py -- reservesiden: vaeret fra api.met.no, time for time og de neste
dagene, naar det ikke er fugler aa vise.

Mikrofonen i hagen korroderte og hveste fra 9. okt 2026. Til den nye lytteren
er paa plass, tegner daily_panel.py denne siden i stedet for en tom fugleside
(se VAERSIDE der). Samme format og loype som fuglesiden: HTML paa noeyaktig
1200x1600, som render_panel_png.py rastrerer og dithrer.

    python3 vaerside.py --out panel.html
    python3 vaerside.py --fra-fil varsel.json --out /tmp/vaer.html   # uten nett
    python3 vaerside.py --merknad "Lytteren er ute av drift." --out panel.html

Kun stdlib. Grafene er SVG tegnet for haand, og bare i panelets seks farger:
svart, hvitt, roedt, gult, blaatt og groent. Roedt er varme, blaatt er kulde
og nedboer, slik yr.no gjoer det; gult er sol og lyn.

Tidene fra api.met.no er UTC. Alt som vises, regnes om til serverens lokale
tid (Europe/Oslo paa serveren).
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import math
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oppsett import LAT, LON, STEDSNAVN, user_agent  # noqa: E402

WIDTH, HEIGHT = 1200, 1600
MET_USER_AGENT = os.environ.get(
    "MET_USER_AGENT", user_agent("fugleramme-epaper/1.0"))
URL = ("https://api.met.no/weatherapi/locationforecast/2.0/compact"
       f"?lat={LAT:.2f}&lon={LON:.2f}")

TIMER = 24          # timer i grafen
DAGER = 5           # dager i tabellen, fra i morgen

SVART, HVIT, ROED, GUL, BLAA = "#000", "#fff", "#f00", "#ff0", "#00f"

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
MAANEDER = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
            "august", "september", "oktober", "november", "desember"]
RETNINGER = ["nord", "nordøst", "øst", "sørøst", "sør", "sørvest", "vest", "nordvest"]

VAER = {
    "clearsky": "Klarvær", "fair": "Lettskyet", "partlycloudy": "Delvis skyet",
    "cloudy": "Overskyet", "fog": "Tåke",
    "lightrain": "Lett regn", "rain": "Regn", "heavyrain": "Kraftig regn",
    "lightrainshowers": "Lette regnbyger", "rainshowers": "Regnbyger",
    "heavyrainshowers": "Kraftige regnbyger",
    "lightsleet": "Lett sludd", "sleet": "Sludd", "heavysleet": "Kraftig sludd",
    "lightsleetshowers": "Lette sluddbyger", "sleetshowers": "Sluddbyger",
    "heavysleetshowers": "Kraftige sluddbyger",
    "lightsnow": "Lett snø", "snow": "Snø", "heavysnow": "Kraftig snø",
    "lightsnowshowers": "Lette snøbyger", "snowshowers": "Snøbyger",
    "heavysnowshowers": "Kraftige snøbyger",
}


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------

def hent_varsel() -> dict:
    req = urllib.request.Request(URL, headers={"User-Agent": MET_USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def punkter(varsel: dict) -> list[dict]:
    """Tidsserien flatet ut, med lokal tid. n1/n6 er None der api-et ikke har
    dem: timesverdiene slutter etter rundt tre doegn, saa kommer bare
    seks-timersblokker."""
    ut = []
    for p in varsel["properties"]["timeseries"]:
        t = datetime.datetime.fromisoformat(p["time"].replace("Z", "+00:00")).astimezone()
        d = p["data"]
        det = d["instant"]["details"]

        def blokk(navn):
            b = d.get(navn)
            if not b:
                return None
            return {"symbol": b.get("summary", {}).get("symbol_code", ""),
                    "mm": b.get("details", {}).get("precipitation_amount")}

        ut.append({"t": t, "temp": det.get("air_temperature"),
                   "vind": det.get("wind_speed"), "fra": det.get("wind_from_direction"),
                   "n1": blokk("next_1_hours"), "n6": blokk("next_6_hours"),
                   "n12": blokk("next_12_hours")})
    return ut


def symbol_for(p: dict) -> str:
    for navn in ("n1", "n6", "n12"):
        if p.get(navn) and p[navn]["symbol"]:
            return p[navn]["symbol"]
    return ""


def dagsoversikt(ps: list[dict], dato: datetime.date) -> dict | None:
    dagens = [p for p in ps if p["t"].date() == dato]
    if not dagens:
        return None
    temp = [p["temp"] for p in dagens if p["temp"] is not None]
    # Nedboer: timesverdier der de finnes, ellers seks-timersblokkene. I
    # seks-timersdelen ligger punktene seks timer fra hverandre, saa summen
    # dekker doegnet uten aa telle noe to ganger.
    mm = sum((p["n1"]["mm"] or 0) if p["n1"] else ((p["n6"] or {}).get("mm") or 0)
             for p in dagens)
    # Symbolet for dagen: blokken naermest midt paa dagen.
    med6 = [p for p in dagens if p["n6"]] or dagens
    midt = min(med6, key=lambda p: abs(p["t"].hour - 12))
    return {"dato": dato, "maks": max(temp), "min": min(temp), "mm": mm,
            "vind": max(p["vind"] or 0 for p in dagens),
            "symbol": (midt["n6"] or {}).get("symbol") or symbol_for(midt)}


# ----------------------------------------------------------------------
# Tekst
# ----------------------------------------------------------------------

def grader(t: float) -> str:
    # -0 skal ikke staa paa veggen.
    n = round(t)
    return f"{n if n else 0}°"


def temp_farge(t: float) -> str:
    return BLAA if round(t) < 0 else ROED


def mm_tekst(mm: float) -> str:
    return f"{mm:.1f}".replace(".", ",") + " mm"


def retning(fra: float | None) -> str:
    if fra is None:
        return ""
    return RETNINGER[int((fra % 360) / 45 + 0.5) % 8]


def beskrivelse(symbol: str) -> str:
    base = symbol.split("_", 1)[0]
    torden = base.endswith("andthunder")
    base = base.removesuffix("andthunder")
    tekst = VAER.get(base, "Skiftende vær")
    return tekst + " og torden" if torden else tekst


# ----------------------------------------------------------------------
# Ikoner, tegnet i et 100x100-felt
# ----------------------------------------------------------------------

def _sol(cx, cy, r) -> str:
    straaler = "".join(
        f'<line x1="{cx + math.cos(v) * (r + 6):.1f}" y1="{cy + math.sin(v) * (r + 6):.1f}" '
        f'x2="{cx + math.cos(v) * (r + 15):.1f}" y2="{cy + math.sin(v) * (r + 15):.1f}" '
        f'stroke="{SVART}" stroke-width="4" stroke-linecap="round"/>'
        for v in (i * math.pi / 4 for i in range(8)))
    return straaler + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{GUL}" stroke="{SVART}" stroke-width="4"/>'


def _maane(cx, cy, r) -> str:
    # Sigd: en gul skive med en hvit skive over seg, begge med strek.
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{GUL}" stroke="{SVART}" stroke-width="4"/>'
            f'<circle cx="{cx + r * 0.55:.1f}" cy="{cy - r * 0.35:.1f}" r="{r * 0.85:.1f}" '
            f'fill="{HVIT}" stroke="{SVART}" stroke-width="4"/>')


def _sky(dx=0, dy=0) -> str:
    return (f'<path transform="translate({dx},{dy})" d="M22,74 A15,15 0 0 1 22,44 '
            'A22,22 0 0 1 64,36 A18,18 0 0 1 84,74 Z" '
            f'fill="{HVIT}" stroke="{SVART}" stroke-width="4" stroke-linejoin="round"/>')


def ikon(symbol: str, x: float, y: float, s: float) -> str:
    """Et vaersymbol fra symbol_code, skalert til s piksler."""
    base, _, tid = symbol.partition("_")
    natt = tid == "night"
    torden = base.endswith("andthunder")
    base = base.removesuffix("andthunder")
    byger = base.endswith("showers")
    kropp = base.removesuffix("showers")
    styrke = 2 if kropp.startswith("light") else 4 if kropp.startswith("heavy") else 3
    kropp = kropp.removeprefix("light").removeprefix("heavy")

    deler = []
    himmel = _maane if natt else _sol
    if base == "clearsky":
        deler.append(himmel(50, 50, 24))
    elif base == "fog":
        deler += [f'<line x1="14" x2="86" y1="{y0}" y2="{y0}" stroke="{SVART}" '
                  'stroke-width="5" stroke-linecap="round"/>' for y0 in (36, 52, 68)]
    else:
        if base in ("fair", "partlycloudy") or byger:
            deler.append(himmel(34, 32, 17))
        if base != "fair":
            deler.append(_sky(4, -6) if base == "cloudy" else "")
        deler.append(_sky(6, 4) if base == "fair" else _sky())
        # Nedboer under skyen: blaa streker er regn, blaa kryss er snoe.
        if kropp in ("rain", "sleet", "snow"):
            xs = [30, 46, 62, 78][:styrke]
            for i, x0 in enumerate(xs):
                snoe = kropp == "snow" or (kropp == "sleet" and i % 2)
                if snoe:
                    deler.append(f'<path d="M{x0 - 5},{86} l10,0 M{x0},{81} l0,10" '
                                 f'stroke="{BLAA}" stroke-width="4" stroke-linecap="round"/>')
                else:
                    deler.append(f'<line x1="{x0}" y1="80" x2="{x0 - 5}" y2="94" '
                                 f'stroke="{BLAA}" stroke-width="5" stroke-linecap="round"/>')
        if torden:
            deler.append(f'<path d="M58,62 L46,82 L56,82 L48,98 L70,74 L60,74 L66,62 Z" '
                         f'fill="{GUL}" stroke="{SVART}" stroke-width="3" stroke-linejoin="round"/>')
    k = s / 100
    return f'<g transform="translate({x:.1f},{y:.1f}) scale({k:.3f})">{"".join(deler)}</g>'


def ikon_svg(symbol: str, s: int) -> str:
    return (f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}">'
            f'{ikon(symbol, 0, 0, s)}</svg>')


def vindpil(fra: float | None, cx: float, cy: float, r: float = 13) -> str:
    """Pil i den retningen vinden blaaser. Pilen peker mot soer uten rotasjon,
    og vind FRA nord blaaser mot soer, saa rotasjonen er rett og slett fra."""
    if fra is None:
        return ""
    return (f'<g transform="translate({cx:.1f},{cy:.1f}) rotate({fra % 360:.0f})">'
            f'<line x1="0" y1="{-r}" x2="0" y2="{r}" stroke="{SVART}" stroke-width="3"/>'
            f'<path d="M-7,{r - 9} L0,{r + 1} L7,{r - 9}" fill="none" stroke="{SVART}" '
            'stroke-width="3" stroke-linejoin="round"/></g>')


# ----------------------------------------------------------------------
# Time for time
# ----------------------------------------------------------------------

def timegraf(timer: list[dict], b: int = 1104, h: int = 560) -> str:
    n = len(timer)
    kol = b / n
    x = [kol * (i + 0.5) for i in range(n)]

    # Rader, ovenfra: ikoner, temperaturkurve, nedboersoeyler, klokkeslett, vind.
    ik_y, ik_s = 0, 64
    kurve_topp, kurve_bunn = 120, 300
    regn_topp, regn_bunn = 330, 420
    klokke_y = 452
    vind_y = 500

    temps = [p["temp"] for p in timer]
    lav, hoey = min(temps), max(temps)
    spenn = max(hoey - lav, 4)
    midt = (hoey + lav) / 2
    lav, hoey = midt - spenn / 2, midt + spenn / 2

    def ty(t):
        return kurve_bunn - (t - lav) / (hoey - lav) * (kurve_bunn - kurve_topp)

    deler = []
    # Nullstreken, hvis kurven krysser den.
    if lav < 0 < hoey:
        deler.append(f'<line x1="0" x2="{b}" y1="{ty(0):.1f}" y2="{ty(0):.1f}" '
                     f'stroke="{BLAA}" stroke-width="2" stroke-dasharray="6 6"/>')

    # Kurven i biter, farget etter om biten ligger over eller under null.
    for i in range(n - 1):
        t0, t1 = temps[i], temps[i + 1]
        farge = temp_farge((t0 + t1) / 2)
        deler.append(f'<line x1="{x[i]:.1f}" y1="{ty(t0):.1f}" x2="{x[i + 1]:.1f}" '
                     f'y2="{ty(t1):.1f}" stroke="{farge}" stroke-width="6" stroke-linecap="round"/>')

    mm = [(p["n1"] or {}).get("mm") or 0 for p in timer]
    # Skalaen staar fast paa minst 2 mm/t, saa yr regn ikke ser ut som styrtregn.
    topp_mm = max(max(mm), 2.0)
    deler.append(f'<line x1="0" x2="{b}" y1="{regn_bunn}" y2="{regn_bunn}" '
                 f'stroke="{SVART}" stroke-width="2"/>')
    for i, v in enumerate(mm):
        if v <= 0:
            continue
        hh = max((regn_bunn - regn_topp) * v / topp_mm, 3)
        deler.append(f'<rect x="{round(x[i] - kol * 0.36)}" y="{round(regn_bunn - hh)}" '
                     f'width="{round(kol * 0.72)}" height="{round(hh)}" fill="{BLAA}" '
                     'shape-rendering="crispEdges"/>')
    if max(mm) > 0:
        deler.append(f'<text x="{b}" y="{regn_topp - 6}" text-anchor="end" font-size="20" '
                     f'fill="{BLAA}">mm per time, høyest {mm_tekst(max(mm))}</text>')

    for i, p in enumerate(timer):
        hver3 = i % 3 == 0
        if hver3:
            deler.append(ikon(symbol_for(p), x[i] - ik_s / 2, ik_y, ik_s))
            deler.append(f'<text x="{x[i]:.1f}" y="{ty(temps[i]) - 18:.1f}" text-anchor="middle" '
                         f'font-size="30" font-weight="600" fill="{temp_farge(temps[i])}">'
                         f'{grader(temps[i])}</text>')
            deler.append(f'<circle cx="{x[i]:.1f}" cy="{ty(temps[i]):.1f}" r="7" '
                         f'fill="{HVIT}" stroke="{temp_farge(temps[i])}" stroke-width="4"/>')
            deler.append(f'<text x="{x[i]:.1f}" y="{klokke_y}" text-anchor="middle" '
                         f'font-size="26">{p["t"]:%H}</text>')
            if (p["vind"] or 0) >= 0.5:
                deler.append(vindpil(p["fra"], x[i], vind_y))
            deler.append(f'<text x="{x[i]:.1f}" y="{vind_y + 46}" text-anchor="middle" '
                         f'font-size="22">{round(p["vind"] or 0)} m/s</text>')
        else:
            # Hele piksler og crispEdges: en strek paa et halvt piksel blir
            # to graa, og dithringen gjoer graatt om til prikker (18. okt 2026).
            deler.append(f'<line x1="{round(x[i])}" x2="{round(x[i])}" y1="{klokke_y - 26}" '
                         f'y2="{klokke_y - 16}" stroke="{SVART}" stroke-width="2" '
                         'shape-rendering="crispEdges"/>')
        # Midnatt: en loddrett strek og navnet paa den nye dagen.
        if p["t"].hour == 0 and i > 0:
            xm = round(x[i] - kol / 2)
            deler.append(f'<line x1="{xm}" x2="{xm}" y1="{kurve_topp - 30}" '
                         f'y2="{regn_bunn}" stroke="{SVART}" stroke-width="2" stroke-dasharray="3 5" '
                         'shape-rendering="crispEdges"/>')
            deler.append(f'<text x="{xm + 8:.1f}" y="{kurve_topp - 34}" font-size="20" '
                         f'letter-spacing="2">{UKEDAGER[p["t"].weekday()].upper()}</text>')
    return (f'<svg class="timer" width="{b}" height="{h}" viewBox="0 0 {b} {h}">'
            f'{"".join(deler)}</svg>')


# ----------------------------------------------------------------------
# Siden
# ----------------------------------------------------------------------

def bygg_html(varsel: dict, naa: datetime.datetime, merknad: str = "") -> str:
    ps = punkter(varsel)
    timeliste = [p for p in ps if p["n1"] and p["t"] >= naa.replace(minute=0, second=0, microsecond=0)]
    timeliste = timeliste[:TIMER]
    if len(timeliste) < 12:
        raise SystemExit("FEIL: varselet har for faa timesverdier")
    forst = timeliste[0]
    i_dag = naa.date()
    resten = dagsoversikt([p for p in ps if p["t"] >= forst["t"]], i_dag)
    dager = [d for d in (dagsoversikt(ps, i_dag + datetime.timedelta(days=n))
                         for n in range(1, DAGER + 1)) if d]

    dag = f"{UKEDAGER[i_dag.weekday()]}"
    dato = f"{i_dag.day}. {MAANEDER[i_dag.month - 1]} {i_dag.year}"
    oppdatert = varsel["properties"].get("meta", {}).get("updated_at", "")
    try:
        oppdatert = datetime.datetime.fromisoformat(oppdatert.replace("Z", "+00:00")).astimezone()
        oppdatert = f"Varsel fra kl. {oppdatert:%H:%M}"
    except ValueError:
        oppdatert = ""

    sym = symbol_for(forst)
    vind = f"Vind {round(forst['vind'] or 0)} m/s"
    if forst["fra"] is not None and (forst["vind"] or 0) >= 0.5:
        vind += f" fra {retning(forst['fra'])}"
    resten_tekst = ""
    if resten:
        resten_tekst = (f'Resten av dagen <b style="color:{temp_farge(resten["maks"])}">'
                        f'{grader(resten["maks"])}</b> til '
                        f'<b style="color:{temp_farge(resten["min"])}">{grader(resten["min"])}</b>'
                        f' · <span style="color:{BLAA}">{mm_tekst(resten["mm"])}</span>')

    rader = "".join(
        f'<tr><td class="dag">{UKEDAGER[d["dato"].weekday()]}'
        f'<span>{d["dato"].day}. {MAANEDER[d["dato"].month - 1]}</span></td>'
        f'<td class="ik">{ikon_svg(d["symbol"], 76)}</td>'
        f'<td class="besk">{html.escape(beskrivelse(d["symbol"]))}</td>'
        f'<td class="temp"><b style="color:{temp_farge(d["maks"])}">{grader(d["maks"])}</b>'
        f'<span style="color:{temp_farge(d["min"])}">{grader(d["min"])}</span></td>'
        f'<td class="mm" style="color:{BLAA}">{mm_tekst(d["mm"]) if d["mm"] >= 0.05 else ""}</td>'
        f'<td class="vind">{round(d["vind"])} m/s</td></tr>'
        for d in dager)

    bunn_venstre = (f'<span class="merknad">{html.escape(merknad)}</span>' if merknad
                    else f'<span>{html.escape(STEDSNAVN)}</span>')

    return f"""<meta charset="utf-8">
<title>Været — {dato}</title>
<style>
  /* Bare panelets seks farger. Flate palettfarger dithres ikke, saa tekst og
     streker blir knivskarpe. */
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background:#fff; }}
  body {{
    width:{WIDTH}px; height:{HEIGHT}px;
    font-family:"EB Garamond","Libre Baskerville","Iowan Old Style",
                "Palatino Linotype",Palatino,"DejaVu Serif",Georgia,serif;
    color:#000; -webkit-font-smoothing:none;
  }}
  .side {{ width:100%; height:100%; padding:44px 48px 36px;
           display:flex; flex-direction:column; }}
  header {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .kicker {{ font-size:20px; letter-spacing:.42em; text-transform:uppercase; }}
  h1 {{ font-size:64px; line-height:1.02; font-weight:600; margin-top:6px; }}
  .dato {{ font-size:30px; margin-top:2px; }}
  .sted {{ text-align:right; font-size:24px; line-height:1.35; padding-top:10px; }}
  .sted div:first-child {{ letter-spacing:.16em; text-transform:uppercase; font-size:18px; }}
  .regel {{ border-top:5px solid #000; border-bottom:2px solid #000; height:9px;
            margin-top:22px; }}

  .naa {{ display:flex; align-items:center; gap:36px; padding:30px 0 18px; }}
  .naa .tall {{ font-size:168px; line-height:.9; font-weight:600; }}
  .naa .tekst {{ font-size:30px; line-height:1.35; }}
  .naa .tekst .hoved {{ font-size:46px; font-weight:600; line-height:1.1; margin-bottom:6px; }}
  .naa b {{ font-weight:600; }}

  h3 {{ font-size:17px; letter-spacing:.3em; text-transform:uppercase; font-weight:600;
        border-bottom:2px solid #000; padding-bottom:8px; margin:18px 0 22px; }}
  svg text {{ font-family:inherit; fill:#000; }}

  table {{ width:100%; border-collapse:collapse; }}
  td {{ border-bottom:1px solid #000; padding:4px 0; vertical-align:middle; }}
  td.dag {{ font-size:32px; width:230px; }}
  td.dag span {{ display:block; font-size:19px; }}
  td.ik {{ width:96px; }}
  td.ik svg {{ display:block; }}
  td.besk {{ font-size:26px; }}
  td.temp {{ font-size:34px; text-align:right; width:150px; white-space:nowrap; }}
  td.temp b {{ font-weight:600; }}
  td.temp span {{ font-size:26px; margin-left:12px; }}
  td.mm {{ font-size:24px; text-align:right; width:130px; }}
  td.vind {{ font-size:24px; text-align:right; width:110px; }}

  .bunn {{ margin-top:auto; border-top:2px solid #000; padding-top:8px;
           display:flex; justify-content:space-between; gap:24px; font-size:19px; }}
  .merknad {{ color:#f00; }}
</style>
<div class="side">
  <header>
    <div>
      <div class="kicker">Været i dag</div>
      <h1>{dag}</h1>
      <div class="dato">{dato}</div>
    </div>
    <div class="sted">
      <div>{html.escape(STEDSNAVN)}</div>
      <div>{html.escape(oppdatert)}</div>
    </div>
  </header>
  <div class="regel"></div>

  <section class="naa">
    {ikon_svg(sym, 190)}
    <div class="tall" style="color:{temp_farge(forst['temp'])}">{grader(forst['temp'])}</div>
    <div class="tekst">
      <div class="hoved">{html.escape(beskrivelse(sym))}</div>
      <div>{html.escape(vind)}</div>
      <div>{resten_tekst}</div>
    </div>
  </section>

  <h3>Time for time</h3>
  {timegraf(timeliste)}

  <h3>De neste dagene</h3>
  <table>{rader}</table>

  <footer class="bunn">
    {bunn_venstre}
    <span>Data fra MET Norge · yr.no</span>
  </footer>
</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Tegn vaersiden for panelet.")
    ap.add_argument("--out", default="vaerside.html")
    ap.add_argument("--fra-fil", help="les varselet fra en lagret JSON i stedet for api.met.no")
    ap.add_argument("--merknad", default="", help="roed linje nederst, for eksempel om lytteren")
    ap.add_argument("--naa", help="late som klokka er ISO-tid (for test med lagret varsel)")
    args = ap.parse_args()

    if args.fra_fil:
        with open(args.fra_fil) as f:
            varsel = json.load(f)
    else:
        varsel = hent_varsel()
    naa = (datetime.datetime.fromisoformat(args.naa).astimezone() if args.naa
           else datetime.datetime.now().astimezone())
    with open(args.out, "w") as f:
        f.write(bygg_html(varsel, naa, args.merknad))
    print(f"OK: {args.out} — vaeret for {naa:%Y-%m-%d %H:%M}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
