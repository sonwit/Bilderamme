#!/usr/bin/env python3
"""
Fugleramme: dagens fugleliste som et fast oppsett -- «dagens side i fugleboka».

Leser birds.json (dagens arter fra birdnet_analyze.py) og skriver en HTML-side
paa noeyaktig 1200x1600 -- samme format som panelet. Sida rasteriseres senere
til PNG og gaar gjennom den samme dither-/pakkeloypa som AI-bildet
(generate_daily_image.py sin to_epaper()), saa dette steget erstatter bare
*motivet*, ikke roerledningen.

    python3 render_daily_panel.py --birds birds.json --out panel.html
    python3 render_daily_panel.py --no-weather        # uten nettkall

Kun stdlib, saa den kjoerer baade paa Macen og i begge venv-ene paa serveren.

Farger: bare de seks panelfargene brukes (svart, hvitt, roedt, gult, blaatt,
groent). Flate palettfarger treffer paletten eksakt og trenger ingen dithering
-- derfor blir tekst og streker knivskarpe, i motsetning til et fotografi.

Plansjene: PLATES_DIR/<slekt-art>.png hvis den finnes, ellers en enkel
silhuett-plassholder. Panelet skal aldri stoppe fordi en plansje mangler.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bird_names import norwegian_name, is_translated  # noqa: E402

WIDTH, HEIGHT = 1200, 1600          # samme som panelet
# Paa serveren ligger alt flatt i /opt/fugleramme/, i repoet ligger scriptene i
# tools/ og plansjene i plates/. Se etter begge deler.
_HERE = os.path.dirname(os.path.abspath(__file__))
PLATES_DIR = os.environ.get(
    "PLATES_DIR",
    os.path.join(_HERE, "plates") if os.path.isdir(os.path.join(_HERE, "plates"))
    else os.path.join(_HERE, "..", "plates"))

LAT, LON = 60.09, 10.93
MET_USER_AGENT = os.environ.get(
    "MET_USER_AGENT", "fugleramme-epaper/1.0 https://github.com/sonwit/Bilderamme")

# Hovedlista vs. «ogsaa mulige». BirdNET-konfidens er en score per deteksjon,
# ikke sannsynligheten for at arten var der -- rørdrum paa 0,41 i en hage paa
# Hagen er nesten sikkert et feiltreff. Arter under terskelen som bare er hoert
# i én oekt havner i fotnoten i stedet for aa faa en linje paa veggen.
SURE_CONF = float(os.environ.get("PANEL_SURE_CONF", "0.5"))
MAX_ROWS = int(os.environ.get("PANEL_MAX_ROWS", "7"))

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
MAANEDER = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
            "august", "september", "oktober", "november", "desember"]

VAER = {
    "clearsky": "Klarvær", "fair": "Lettskyet", "partlycloudy": "Delvis skyet",
    "cloudy": "Overskyet", "fog": "Tåke", "lightrain": "Lett regn",
    "rain": "Regn", "heavyrain": "Kraftig regn",
    "lightrainshowers": "Lette regnbyger", "rainshowers": "Regnbyger",
    "heavyrainshowers": "Kraftige regnbyger", "lightsleet": "Lett sludd",
    "sleet": "Sludd", "heavysleet": "Kraftig sludd",
    "lightsleetshowers": "Sluddbyger", "sleetshowers": "Sluddbyger",
    "heavysleetshowers": "Kraftige sluddbyger", "lightsnow": "Lett snø",
    "snow": "Snø", "heavysnow": "Kraftig snø",
    "lightsnowshowers": "Lette snøbyger", "snowshowers": "Snøbyger",
    "heavysnowshowers": "Kraftige snøbyger",
}


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------

def load_birds(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_weather() -> dict | None:
    """Vaeret naa fra yr/api.met.no. None hvis noe feiler -- vaeret er pynt."""
    url = ("https://api.met.no/weatherapi/locationforecast/2.0/compact"
           f"?lat={LAT}&lon={LON}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": MET_USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            ts = json.load(r)["properties"]["timeseries"][0]["data"]
        details = ts["instant"]["details"]
        symbol = ""
        for horizon in ("next_1_hours", "next_6_hours", "next_12_hours"):
            if horizon in ts and "summary" in ts[horizon]:
                symbol = ts[horizon]["summary"].get("symbol_code", "")
                break
        base = symbol.split("_", 1)[0]
        return {
            "temp": round(details["air_temperature"]),
            "desc": VAER.get(base, "Skiftende vær"),
            "wind": round(details.get("wind_speed", 0.0)),
        }
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: vaer-API feilet ({str(e)[:100]}) — panel uten vaer.",
              file=sys.stderr)
        return None


def norsk_dato(d: datetime.date) -> tuple[str, str]:
    return UKEDAGER[d.weekday()], f"{d.day}. {MAANEDER[d.month - 1]} {d.year}"


def split_species(species: list[dict], max_rows: int | None = None) -> tuple[list[dict], list[dict]]:
    """Del i «hoert» (paa veggen) og «ogsaa mulige» (fotnote). Sortert paa
    hvor godt belagt arten er: flere oekter > flere deteksjoner > hoeyere
    konfidens. En art hoert i to oekter er mer troverdig enn én med hoey score
    i én enkelt tre-sekunders bit."""
    ordered = sorted(species, key=lambda s: (-s.get("sessions", 1),
                                             -s.get("detections", 0),
                                             -s.get("confidence", 0.0)))
    sure = [s for s in ordered
            if s.get("confidence", 0) >= SURE_CONF or s.get("sessions", 1) >= 2]
    unsure = [s for s in ordered if s not in sure]
    n = MAX_ROWS if max_rows is None else max_rows
    return sure[:n], unsure + sure[n:]


# ----------------------------------------------------------------------
# Plansjer
# ----------------------------------------------------------------------

# compose_hero.py kan legge en komponert hovedplansje her: én tegning med
# dagens fugler samlet, i 16:9 saa den fyller hero-ramma. Er den fra i dag,
# gaar den foran den skannede enkeltplansjen.
HERO_PNG = os.path.join(PLATES_DIR, "dagens-hero.png")
HERO_JSON = os.path.join(PLATES_DIR, "dagens-hero.json")
# Helsides bakgrunn fra compose_hero.py --full: illustrasjonen fyller hele
# 1200x1600 og teksten ligger oppaa, i sonene modellen ble bedt om aa la staa
# tomme. Sidecar-JSON-en sier om den faktisk gjorde det.
BG_PNG = os.path.join(PLATES_DIR, "dagens-bakgrunn.png")
BG_JSON = os.path.join(PLATES_DIR, "dagens-bakgrunn.json")
# Hvor mange arter overlegget viser. Den staaende venstrespalten er hoeyere enn
# lista i standard-layouten, saa der faar vi plass til nesten hele dagen.
OVERLAY_ROWS = int(os.environ.get("PANEL_OVERLAY_ROWS", "10"))


def todays_background(date: str) -> dict | None:
    """Dagens helsides bakgrunn, eller None. Samme datosjekk som hero."""
    if not (os.path.exists(BG_PNG) and os.path.exists(BG_JSON)):
        return None
    try:
        with open(BG_JSON) as f:
            meta = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if meta.get("date") != date:
        print(f"dagens-bakgrunn.png er fra {meta.get('date')} (ikke {date}) "
              "— hopper over overlegget.", file=sys.stderr)
        return None
    return meta


def todays_hero(date: str) -> dict | None:
    """Dagens komponerte plansje, eller None. Sjekker datoen: en gammel
    hero-fil skal ikke henge igjen paa veggen med feil fugler."""
    if not (os.path.exists(HERO_PNG) and os.path.exists(HERO_JSON)):
        return None
    try:
        with open(HERO_JSON) as f:
            meta = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if meta.get("date") != date:
        print(f"dagens-hero.png er fra {meta.get('date')} (ikke {date}) "
              "— bruker skannet plansje.", file=sys.stderr)
        return None
    return meta


def _slug(scientific: str) -> str:
    return scientific.strip().lower().replace(" ", "-")


def plate_path(scientific: str) -> str | None:
    """Vasket versjon foerst (prepare_plates.py), ellers raa skanning. En raa
    skanning har papirtone som ikke finnes i paletten og blir en gul
    stoeyflate paa panelet -- den vaskede er alltid den vi vil ha."""
    for d in (os.path.join(PLATES_DIR, "vasket"), PLATES_DIR):
        for ext in (".png", ".jpg", ".jpeg"):
            p = os.path.abspath(os.path.join(d, _slug(scientific) + ext))
            if os.path.exists(p):
                return p
    return None


# Plassholder-silhuetter. Tre grovformer valgt paa slekt -- nok til aa vurdere
# oppsettet foer de ekte plansjene er paa plass. Ikke ment aa vaere fugleart-
# noeyaktige; de skal byttes ut med skannede/genererte plansjer.
_LONGTAIL = {"pica", "corvus", "nucifraga", "garrulus"}
_WADER = {"charadrius", "gallinago", "numenius", "tringa", "actitis", "ardea",
          "botaurus", "grus", "porzana", "rallus", "crex", "fulica",
          "gallinula", "vanellus", "scolopax", "anas", "mareca", "cygnus",
          "anser", "branta", "aythya", "bucephala", "mergus"}


def _shape_for(scientific: str) -> str:
    genus = scientific.strip().lower().split(" ")[0]
    if genus in _LONGTAIL:
        return "longtail"
    if genus in _WADER:
        return "wader"
    return "songbird"


def placeholder_svg(scientific: str) -> str:
    shape = _shape_for(scientific)
    if shape == "longtail":
        body = """
          <ellipse cx="140" cy="112" rx="48" ry="34" transform="rotate(-16 140 112)"/>
          <circle cx="182" cy="74" r="24"/>
          <polygon points="204,68 236,76 204,84"/>
          <polygon points="96,130 4,182 20,194 110,146"/>
          <rect x="132" y="140" width="5" height="30"/>
          <rect x="152" y="140" width="5" height="30"/>"""
    elif shape == "wader":
        body = """
          <ellipse cx="128" cy="104" rx="52" ry="30" transform="rotate(-8 128 104)"/>
          <circle cx="182" cy="62" r="20"/>
          <rect x="176" y="72" width="9" height="34"/>
          <polygon points="200,56 250,62 200,68"/>
          <polygon points="76,112 22,124 30,134 84,128"/>
          <rect x="118" y="130" width="5" height="46"/>
          <rect x="140" y="130" width="5" height="46"/>"""
    else:
        body = """
          <ellipse cx="128" cy="112" rx="52" ry="38" transform="rotate(-15 128 112)"/>
          <circle cx="172" cy="72" r="26"/>
          <polygon points="196,66 226,74 196,82"/>
          <polygon points="80,130 20,160 32,170 92,148"/>
          <rect x="120" y="146" width="5" height="26"/>
          <rect x="140" y="146" width="5" height="26"/>"""
    return f"""<svg class="silhouette" viewBox="0 0 260 200" preserveAspectRatio="xMidYMid meet">
      <g fill="#000">{body}</g>
      <rect x="10" y="172" width="240" height="5" fill="#000"/>
    </svg>"""


def plate_html(s: dict, big: bool) -> str:
    """Én plansje: ekte bilde hvis vi har det, ellers silhuett + tydelig merke."""
    sci = s.get("scientific_name", "")
    p = plate_path(sci)
    if p:
        return f'<img class="plate-img" src="file://{html.escape(p)}" alt="">'
    return (placeholder_svg(sci) +
            '<div class="mangler">plansje mangler</div>')


# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------

def _heard(s: dict) -> str:
    a, b = s.get("first_heard"), s.get("last_heard")
    if a and b and a != b:
        return f"{a}–{b}"
    return a or b or "—"


def _name_html(s: dict) -> str:
    sci = s.get("scientific_name", "")
    name = norwegian_name(sci, s.get("common_name", ""))
    cls = "" if is_translated(sci) else ' class="utenlandsk"'
    return f'<span{cls}>{html.escape(name)}</span>'


def species_row(s: dict, bar: bool = True) -> str:
    conf = s.get("confidence", 0.0)
    det = s.get("detections", 0)
    sess = s.get("sessions", 1)
    okt = f"{sess} økter" if sess > 1 else f"{det} ggr"
    return f"""
      <tr>
        <td class="navn">{_name_html(s)}
            <span class="latin">{html.escape(s.get('scientific_name',''))}</span></td>
        <td class="tid">{_heard(s)}<span class="okt">{okt}</span></td>
        <td class="bar">
          {'<div class="bar-spor"><div class="bar-fyll" style="width:%.0f%%"></div></div>' % (conf*100) if bar else ''}
          <span class="pst">{conf*100:.0f}%</span>
        </td>
      </tr>"""


def species_card(s: dict, bar: bool = False, nr: int | None = None) -> str:
    """Art som stablet kort. Venstrespalten i overlegget er bare ~550 px bred,
    saa tabellen med tre kolonner faar ikke plass -- her ligger navn og prosent
    paa én linje, resten under.

    Baren er AV som standard: den viste konfidensen, altsaa noeyaktig samme tall
    som prosenten ved siden av. To fremstillinger av samme tall gjoer bare raden
    hoeyere. Slaa den paa med --bar paa hvis du vil ha den tilbake."""
    conf = s.get("confidence", 0.0)
    sess = s.get("sessions", 1)
    okt = f"{sess} økter" if sess > 1 else f"{s.get('detections', 0)} ggr"
    spor = (f'<div class="bar-spor"><div class="bar-fyll" '
            f'style="width:{conf*100:.0f}%"></div></div>') if bar else ""
    # Plassen holdes av ogsaa uten tall, ellers starter de unummererte
    # linjene lenger til venstre enn resten.
    tall = f'<span class="nr">{nr if nr else ""}</span>' 
    return f"""
      <div class="art">
        <div class="l1">{tall}<span class="navn">{_name_html(s)}</span><span class="p">{conf*100:.0f}%</span></div>
        <div class="l2"><span class="latin">{html.escape(s.get('scientific_name',''))}</span>
             · {_heard(s)} · {okt}</div>
        {spor}
      </div>"""


def build_html(birds: dict, weather: dict | None, pute: str = "maalt",
               bar: bool = False) -> str:
    """pute styrer den hvite flaten under teksten i overlegget:
    'maalt'  -- bare der compose_hero maalte at sonen ikke ble tom (standard)
    'alltid' -- alltid, uansett maaling (tryggest, mest synlig)
    'aldri'  -- aldri; teksten ligger rett paa illustrasjonen"""
    date = datetime.date.fromisoformat(birds.get("date")) \
        if birds.get("date") else datetime.date.today()
    ukedag, dato = norsk_dato(date)
    bg_meta = todays_background(birds.get("date", ""))
    sure, unsure = split_species(birds.get("species", []),
                                 OVERLAY_ROWS if bg_meta else None)
    sessions = birds.get("sessions_today", 0)

    hero_meta = None if bg_meta else todays_hero(birds.get("date", ""))
    hero = sure[0] if sure else None
    # Med komponert hero viser den lille plansjen en art som IKKE er med der,
    # saa sida ikke gjentar seg selv.
    if hero_meta:
        i_hero = {sp["scientific_name"] for sp in hero_meta.get("species", [])}
        side = next((s for s in sure if s["scientific_name"] not in i_hero),
                    sure[1] if len(sure) > 1 else None)
    else:
        side = sure[1] if len(sure) > 1 else None

    vaer = (f"{weather['desc']} · {weather['temp']}° · {weather['wind']} m/s"
            if weather else "")

    rows = "".join(species_row(s, bar=bar) for s in sure)

    # Puta: ren #fff under teksten. 'maalt' foelger sonerapporten fra
    # compose_hero.py -- den vet hvor mye blekk modellen faktisk la i hver sone.
    def _pute(sone: str) -> str:
        if not bg_meta or pute == "aldri":
            return ""
        # Bunnlinja faar bare den hvite flaten, ikke rammestreken: der er det
        # grenen selv som ligger under, og en boks rundt to linjer smaatekst
        # blir tyngre enn problemet den loeser.
        kant = "" if sone == "bunn" else " kant"
        if pute == "alltid":
            return " pute" + kant
        ren = (bg_meta.get("soner", {}).get(sone) or {}).get("ren", False)
        return "" if ren else " pute" + kant

    pute_venstre, pute_bunn = _pute("venstre"), _pute("bunn")
    # Tallene knytter fuglen paa plansjen til linja i lista. De settes i den
    # HVITE luften ved siden av fuglen, ikke oppaa den: et tall midt i
    # fjaerdrakten forsvinner i dithringen.
    # Nummereringen gjelder BARE artene som faktisk er tegnet opp, og loeper
    # 1..k i listas rekkefoelge. Numererte vi alle linjene, ville 1, 7 og 8
    # peke paa fugler som ikke finnes paa plansjen -- et tall uten svar er
    # verre enn ikke noe tall.
    tegnet = {}
    if bg_meta:
        tegnet = {sp["scientific_name"]: sp for sp in bg_meta.get("species", [])
                  if sp.get("merke")}
    nummer: dict[str, int] = {}
    for sp in sure:
        sci = sp.get("scientific_name", "")
        if sci in tegnet:
            nummer[sci] = len(nummer) + 1

    def _markoerer() -> str:
        """Tallene som knytter fuglen paa plansjen til linja i lista.
        Posisjonen er funnet av compose_branch.py i det ferdige arket -- den
        vet hvor det er ren hvit luft, det gjoer ikke denne fila."""
        ut = []
        for sci, n in nummer.items():
            mx, my = tegnet[sci]["merke"]
            ut.append(f'<span class="markoer" style="left:{mx}px;top:{my}px">{n}</span>')
        return "".join(ut)

    markoerer = _markoerer()
    overlegg_cls = " overlegg" if bg_meta else ""
    bakgrunn_img = (f'<img class="bakgrunn" src="file://'
                    f'{html.escape(os.path.abspath(BG_PNG))}" alt="">'
                    if bg_meta else "")

    if unsure:
        navn = ", ".join(norwegian_name(s.get("scientific_name", ""),
                                        s.get("common_name", "")) for s in unsure[:6])
        fotnote = f'<p class="usikre"><span>Også mulige:</span> {html.escape(navn)}</p>'
    else:
        fotnote = ""

    def hero_block(meta):
        navn = " · ".join(sp["norsk"] for sp in meta.get("species", []))
        latin = " · ".join(sp["scientific_name"] for sp in meta.get("species", []))
        return f"""
        <section class="hero komponert">
          <div class="ramme"><img class="plate-img" src="file://{html.escape(os.path.abspath(HERO_PNG))}" alt=""></div>
          <div class="plate-tekst">
            <h2>{html.escape(navn)}</h2>
            <p class="latin">{html.escape(latin)}</p>
          </div>
        </section>"""

    def plate_block(s, cls, big):
        if not s:
            return f'<section class="{cls}"></section>'
        sci = s.get("scientific_name", "")
        return f"""
        <section class="{cls}">
          <div class="ramme">{plate_html(s, big)}</div>
          <div class="plate-tekst">
            <h2>{html.escape(norwegian_name(sci, s.get('common_name','')))}</h2>
            <p class="latin">{html.escape(sci)}</p>
            {'<p class="detalj">Hørt ' + _heard(s) + ' · ' + str(s.get('detections',0)) + ' deteksjoner</p>' if big else ''}
          </div>
        </section>"""

    # Overlegget samler dato og vaer i ÉN boks oeverst til venstre. Standard-
    # layouten har fortsatt tittel til venstre og vaer til hoeyre -- der er det
    # ingen illustrasjon bak teksten, saa de trenger ikke holde sammen.
    if bg_meta:
        topptekst = f"""<section class="info{pute_venstre}">
    <div class="kicker">Hagen i dag</div>
    <h1>{ukedag}</h1>
    <div class="dato">{dato}</div>
    <div class="vaerlinje">
      <span class="sted">Hagen</span><br>
      {html.escape(vaer)}<br>
      {sessions} opptak i dag
    </div>
  </section>"""
    else:
        topptekst = f"""<header class="tittel">
    <div class="kicker">Hagen i dag</div>
    <h1>{ukedag}</h1>
    <div class="dato">{dato}</div>
  </header>

  <div class="vaer">
    <div class="sted">Hagen</div>
    <div>{html.escape(vaer)}</div>
    <div>{sessions} opptak</div>
  </div>"""

    if bg_meta:
        # Illustrasjonen ER midtdelen. Ingen regel, ingen hero-ramme, ingen
        # liten plansje -- alt det er bakgrunnen naa.
        midtdel = ""
        sideplansje = ""
        liste_innhold = "".join(
            species_card(s, bar=bar, nr=nummer.get(s.get("scientific_name", "")))
            for s in sure)
    else:
        midtdel = ('<div class="regel"></div>\n  '
                   + (hero_block(hero_meta) if hero_meta
                      else plate_block(hero, "hero", True)))
        sideplansje = plate_block(side, "side-plansje", False)
        liste_innhold = f"<table>{rows}</table>"

    return f"""<meta charset="utf-8">
<title>Fugleramme — {dato}</title>
<style>
  /* Bare panelets seks farger: svart, hvitt, roedt, gult, blaatt, groent.
     Flate palettfarger dithres ikke, saa tekst og streker blir knivskarpe. */
  :root {{ --blekk:#000; --papir:#fff; --aksent:#f00; }}

  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background:var(--papir); }}
  body {{
    width:{WIDTH}px; height:{HEIGHT}px;
    font-family:"EB Garamond","Libre Baskerville","Iowan Old Style",
                "Palatino Linotype",Palatino,"DejaVu Serif",Georgia,serif;
    color:var(--blekk);
    -webkit-font-smoothing:none;   /* ingen graatone-antialias -> mindre aa dithre */
  }}

  /* 12 x 16 rutenett paa 1200x1600 = 100px celler (minus marg). */
  .side {{
    width:100%; height:100%; padding:44px 48px 36px;
    display:grid;
    grid-template-columns:repeat(12,1fr);
    grid-template-rows:repeat(16,1fr);
    column-gap:24px; row-gap:0;
  }}

  /* --- tittel oppe til venstre --- */
  .tittel {{ grid-column:1/9; grid-row:1/3; align-self:start; }}
  .kicker {{ font-size:20px; letter-spacing:.42em; text-transform:uppercase; }}
  .tittel h1 {{ font-size:64px; line-height:1.02; font-weight:600; margin-top:6px; }}
  .tittel .dato {{ font-size:30px; margin-top:2px; }}

  .vaer {{ grid-column:9/13; grid-row:1/3; align-self:start; text-align:right;
           font-size:24px; line-height:1.35; padding-top:10px; }}
  .vaer .sted {{ letter-spacing:.16em; text-transform:uppercase; font-size:18px; }}

  .regel {{ grid-column:1/13; grid-row:3/4; align-self:start;
            border-top:5px solid var(--blekk); border-bottom:2px solid var(--blekk);
            height:9px; }}

  /* --- stor plansje i midten --- */
  .hero {{ grid-column:1/13; grid-row:3/10; padding-top:24px;
           display:flex; flex-direction:column; }}
  .hero .ramme {{ flex:1; min-height:0; }}
  .komponert .ramme {{ padding:0; }}
  .komponert .plate-img {{ width:100%; height:100%; object-fit:cover; }}
  .komponert h2 {{ font-size:40px; }}
  .komponert .latin {{ font-size:24px; }}
  .hero .plate-tekst {{ text-align:center; padding-top:8px; }}
  .hero h2 {{ font-size:46px; font-weight:600; letter-spacing:.02em; }}

  .ramme {{ border:3px double var(--blekk); padding:14px;
            display:flex; align-items:center; justify-content:center;
            overflow:hidden; background:var(--papir); position:relative; }}
  .plate-img {{ max-width:100%; max-height:100%; object-fit:contain; }}
  .silhouette {{ width:82%; height:82%; }}
  .mangler {{ position:absolute; right:10px; bottom:8px; font-size:15px;
              letter-spacing:.14em; text-transform:uppercase;
              border:2px solid var(--aksent); color:var(--aksent);
              padding:2px 8px; }}

  .latin {{ font-style:italic; }}
  .hero .latin {{ font-size:28px; }}
  .utenlandsk {{ font-style:italic; }}   /* mangler norsk navn -> synlig */

  /* --- artsliste nede til venstre --- */
  .liste {{ grid-column:1/9; grid-row:10/16; padding-top:20px; overflow:hidden; }}
  .liste h3, .side-plansje h3 {{
    font-size:17px; letter-spacing:.3em; text-transform:uppercase;
    border-bottom:2px solid var(--blekk); padding-bottom:8px; margin-bottom:14px;
    font-weight:600;
  }}
  table {{ width:100%; border-collapse:collapse; }}
  td {{ padding:5px 0; vertical-align:baseline;
        border-bottom:1px solid var(--blekk); }}
  .navn {{ font-size:29px; line-height:1.1; }}
  .navn .latin {{ font-size:19px; display:block; }}
  .tid {{ font-size:22px; text-align:right; white-space:nowrap; padding-right:16px;
          width:190px; }}
  .tid .okt {{ display:block; font-size:17px; }}
  .bar {{ width:150px; white-space:nowrap; }}
  .bar-spor {{ display:inline-block; width:96px; height:15px;
               border:2px solid var(--blekk); vertical-align:middle; }}
  .bar-fyll {{ height:100%; background:var(--aksent); }}
  .pst {{ display:inline-block; width:46px; text-align:right; font-size:19px;
          vertical-align:middle; }}

  /* --- liten plansje nede til hoeyre --- */
  .side-plansje {{ grid-column:9/13; grid-row:10/16; padding-top:20px;
                   display:flex; flex-direction:column; }}
  .side-plansje .ramme {{ flex:1; min-height:0; }}
  .side-plansje .plate-tekst {{ padding-top:8px; text-align:center; }}
  .side-plansje h2 {{ font-size:30px; font-weight:600; }}
  .side-plansje .latin {{ font-size:19px; }}

  /* --- bunnlinje --- */
  .bunn {{ grid-column:1/13; grid-row:16/17; align-self:end;
           border-top:2px solid var(--blekk); padding-top:8px;
           display:flex; justify-content:space-between; font-size:19px; }}
  .usikre {{ font-size:17px; padding-top:16px; }}
  .usikre span {{ letter-spacing:.16em; text-transform:uppercase; font-size:14px; }}

  /* --- overlegg: illustrasjonen fyller hele arket, teksten ligger oppaa --- */
  body {{ position:relative; }}
  .bakgrunn {{ position:absolute; left:0; top:0; width:{WIDTH}px; height:{HEIGHT}px;
               object-fit:fill; z-index:0; }}
  .side.overlegg {{ position:relative; z-index:1; }}
  /* Tittel og vaer er slaatt sammen til én boks oeverst til venstre. To
     bokser lot vaerboksen ligge midt oppe paa illustrasjonen; nå holder all
     teksten seg i den samme tomme spalten modellen ble bedt om aa la staa. */
  .overlegg .info  {{ grid-column:1/6; grid-row:1/4; align-self:start; }}
  .overlegg .liste {{ grid-column:1/6; grid-row:4/14; padding-top:26px;
                      overflow:hidden; }}
  .overlegg .bunn  {{ grid-column:1/13; grid-row:16/17; }}

  .info .kicker {{ font-size:19px; }}
  .info h1 {{ font-size:60px; line-height:1.04; font-weight:600; margin-top:8px; }}
  .info .dato {{ font-size:29px; margin-top:2px; }}
  .info .vaerlinje {{ font-size:23px; margin-top:16px; padding-top:14px;
                      border-top:2px solid var(--blekk); line-height:1.45; }}
  .info .vaerlinje .sted {{ letter-spacing:.16em; text-transform:uppercase;
                            font-size:17px; }}

  /* Puta under teksten er HELT ugjennomsiktig hvit -- ren #fff er en av
     panelets seks farger og dithres ikke i det hele tatt. En halvgjennomsiktig
     hvit ville blitt en lys mellomtone som IKKE finnes i paletten, og da maa
     dithringen gjette den med prikker: nettopp grumset vi vil unngaa.
     box-shadow uten slør utvider det hvite feltet uten aa flytte paa noe. */
  .pute {{ background:var(--papir); box-shadow:0 0 0 14px var(--papir); }}
  .pute.kant {{ outline:2px solid var(--blekk); outline-offset:12px; }}

  /* Kompakt: raden er navn + prosent paa én linje og detaljene under.
     Uten baren gaar radhoeyden fra ~83 til ~54 px. */
  /* Tallet foran arten peker paa den samme fuglen i plansjen. Alle linjer
     nummereres, ogsaa de som ikke er tegnet opp -- en liste med hull i
     nummereringen leses som en feil. */
  .art .nr {{ flex:0 0 30px; font-size:19px; }}
  .art .navn {{ flex:1 1 auto; }}
  .markoer {{ position:absolute; z-index:1; width:34px; height:34px;
              margin:-17px 0 0 -17px;          /* sentrer paa punktet */
              display:flex; align-items:center; justify-content:center;
              font-size:25px; line-height:1; color:var(--blekk); }}
  .art {{ padding:11px 0; border-bottom:1px solid var(--blekk); }}
  .art .l1 {{ display:flex; justify-content:space-between; align-items:baseline;
              font-size:26px; line-height:1.15; }}
  .art .l1 .p {{ font-size:18px; }}
  .art .l2 {{ font-size:17px; margin-top:4px; padding-left:30px; }}
  .art .bar-spor {{ display:block; width:100%; height:10px; margin-top:5px;
                    border:2px solid var(--blekk); }}
</style>

{bakgrunn_img}
{markoerer}
<div class="side{overlegg_cls}">
  {topptekst}

  {midtdel}

  <section class="liste{pute_venstre}">
    <h3>Hørt i dag</h3>
    {liste_innhold}
    {fotnote}
  </section>

  {sideplansje}

  <footer class="bunn{pute_bunn}">
    <span>BirdNET · utedelen i hagen · 60.09°N 10.93°Ø</span>
    <span>{len(sure) + len(unsure)} arter på {sessions} opptak</span>
  </footer>
</div>
"""


def main():
    ap = argparse.ArgumentParser(description="Bygg dagens fugleside som HTML.")
    ap.add_argument("--birds", default="test/data/birds-2026-08-28.json")
    ap.add_argument("--out", default="test/panel.html")
    ap.add_argument("--no-weather", action="store_true")
    ap.add_argument("--bar", choices=("av", "paa"),
                    default=os.environ.get("PANEL_BAR", "av"),
                    help="vis konfidens-baren i tillegg til prosenten "
                         "(samme tall to ganger; av som standard)")
    ap.add_argument("--pute", choices=("maalt", "alltid", "aldri"),
                    default=os.environ.get("PANEL_PUTE", "maalt"),
                    help="hvit flate under teksten i overlegget")
    args = ap.parse_args()

    birds = load_birds(args.birds)
    weather = None if args.no_weather else get_weather()
    out = build_html(birds, weather, pute=args.pute,
                     bar=(args.bar == "paa"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(out)
    sure, unsure = split_species(birds.get("species", []))
    print(f"OK: {args.out} — {len(sure)} arter i lista, "
          f"{len(unsure)} i fotnoten, plansjer fra {os.path.abspath(PLATES_DIR)}")


if __name__ == "__main__":
    sys.exit(main())
