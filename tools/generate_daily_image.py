#!/usr/bin/env python3
"""
Fugleramme: genererer dagens bilde med Gemini (nano banana),
konverterer til 6-fargers e-ink-format og legger det klart for skjermen.

Krav:
  pip install google-genai pillow numpy requests

Miljøvariabel:
  GEMINI_API_KEY  (fra https://aistudio.google.com)

Kjøres av cron sammen med push_to_frame.py, se README.md i workspace-repoet, f.eks.:
  7 7 * * * cd /opt/fugleramme && venv/bin/python3 generate_daily_image.py >> logs/daily.log 2>&1 \
            && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
(07:07, ikke hel time — vær-API-er er som regel mest overbelastet akkurat kl. XX:00.)
"""

import os
import re
import sys
import json
import time
import random
import datetime
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageEnhance

from google import genai
from google.genai import types

# ----------------------------------------------------------------------
# Konfigurasjon
# ----------------------------------------------------------------------

# Kartverket-koordinater for hagen (59.98° N,
# 10.93° E). Stod tidligere som 60.09, 10.93 -- 12 km
# for langt nord. Det paavirket baade vaervarselet og BirdNETs
# artsfilter, som bruker posisjon + dato til aa avgjoere hva som er
# plausibelt her akkurat naa.
LAT, LON = 59.98, 10.93
OUTPUT_DIR = os.environ.get("FRAME_OUTPUT_DIR", "/opt/fugleramme/www")
# Arkiv: hvert bilde (full-farge originalen) lagres her med tidsstempel, saa
# historikken beholdes selv om www/original.png overskrives ved neste bilde.
ARCHIVE_DIR = os.environ.get("FRAME_ARCHIVE_DIR", os.path.join(OUTPUT_DIR, "arkiv"))

# Panelet (Waveshare ESP32-S3-ePaper-13.3E6) er PORTRETT: 1200 bred x 1600 hoey.
# Se EPD_13IN3E_WIDTH/HEIGHT i firmware/indoor_frame/EPD_13in3e.h og
# tools/send_to_frame.py -- begge bruker 1200x1600. Dette var tidligere
# 1600,1200 (byttet om) her, som ga riktig byte-ANTALL (960000) men feil
# rad-lengde (800 byte/rad i stedet for 600) -- dvs. et forskjoevet/vridd
# bilde paa skjermen sjoel om filstoerrelsen saa riktig ut.
WIDTH, HEIGHT = 1200, 1600

# Fast bildestil -- valgt fra docs/Prompt-guide — bilder til ePaper-rammen.md.
# Testene der viste at flate, mettede farger gjengis rent paa dette panelet,
# mens bloett akvarell/pastell/graatoner blir stoeyete (de finnes ikke i
# 6-fargepaletten pg maa "gjettes" med dithering-prikker). Bytt gjerne til en
# av de andre stilene i guiden hvis du vil variere.
STYLE = (
    "modern cartoon illustration, clear bold outlines, cel shading, "
    "bright saturated colors, simple clean background"
)

# Stilene fra web-grensesnittet (label, prompt-bit). Brukes til "tilfeldig stil".
# Hold i synk med <select> i frame_server.py sin WEBUI_HTML.
STYLES = [
    ("Tegneserie", STYLE),
    ("Flat vektor / plakat",
     "bold flat vector illustration, poster style, clean thick outlines, "
     "large flat areas of saturated color, minimal shading, plain background"),
    ("Japansk tresnitt",
     "ukiyo-e woodblock print style, flat color areas, bold outlines, "
     "limited palette, clean composition"),
    ("Risograph",
     "risograph print style, 3-4 bold spot colors, flat layered shapes, "
     "slight grain, clean paper background"),
    ("Barnebok",
     "bold children's book illustration, simple flat shapes, warm saturated "
     "colors, clear outlines, uncluttered background"),
]

# Motiver for det DAGLIGE bildet — tilfeldig valgt for variasjon frem til
# BirdNET-lyttemekanismen ute er paa plass. Fugle-tunge (passer "fugleramme"),
# med noen andre koselige hage-dyr innimellom. Holdt aarstids-noeytrale saa de
# funker med hvilket som helst vaer.
DAILY_SUBJECTS = [
    "a European robin perched on a branch",
    "a great tit on a bird feeder",
    "a blackbird singing on a fence post",
    "a bullfinch on a rowan branch",
    "a blue tit hanging from a seed feeder",
    "a chaffinch on a mossy stone",
    "a Eurasian magpie on the lawn",
    "a great spotted woodpecker on a tree trunk",
    "a goldfinch among garden flowers",
    "a nuthatch climbing a tree trunk",
    "a yellowhammer on a wooden fence",
    "a white wagtail on a stone path",
    "a red squirrel on a pine branch",
    "a hedgehog in the grass",
    "a bumblebee on a garden flower",
    "a butterfly resting on a leaf",
]

# BirdNET-resultatet fra utedelen (Pi tar opp ~06:40, birdnet_analyze.py paa
# serveren skriver denne). Er den fersk (fra i dag), brukes den/de oeverste
# artene som dagens motiv i stedet for tilfeldig DAILY_SUBJECTS.
BIRDS_JSON = os.environ.get("BIRDS_JSON", "/opt/fugleramme/birds.json")

# Smaa scener aa sette den hoerte fuglen i -- DAILY_SUBJECTS har scener bakt
# inn i teksten, men BirdNET gir bare artsnavn, saa vi legger paa en her.
HEARD_SCENES = [
    "perched on a branch",
    "on a bird feeder",
    "singing on a fence post",
    "on a mossy stone",
    "among garden flowers",
    "on the lawn",
]


def _article(name: str) -> str:
    """'a'/'an' for artsnavn. NB: 'Eu...' uttales 'ju' -> 'a European Robin'."""
    if name[:2].lower() == "eu":
        return "a"
    return "an" if name[:1].lower() in "aeiou" else "a"


# Hvor mange av dagens arter som er med i trekningen til bildet. Aa alltid ta
# den aller vanligste ville gitt skjaere og kjoettmeis hver eneste dag; en
# vektet trekning blant toppen gir variasjon og er fortsatt helt sant -- alle
# kandidatene er faktisk hoert i hagen i dag.
HEARD_CANDIDATES = 5


def get_heard_bird() -> str | None:
    """Les birds.json (dagens aggregerte artsliste fra birdnet_analyze.py) og
    lag dagens motiv av fugler som faktisk ble hoert i hagen. Returnerer None
    hvis fila mangler, er fra en annen dag eller ikke har noen arter -- da
    faller run() tilbake til DAILY_SUBJECTS. Feiler stille: en oedelagt
    birds.json skal aldri stoppe dagens bilde."""
    try:
        with open(BIRDS_JSON) as f:
            data = json.load(f)
        if data.get("date") != datetime.date.today().isoformat():
            print(f"birds.json er fra {data.get('date')} (ikke i dag) — "
                  "bruker tilfeldig motiv.", file=sys.stderr)
            return None
        species = (data.get("species") or [])[:HEARD_CANDIDATES]
        if not species:
            return None

        # Vekt = hvor godt belagt arten er i dag (antall oekter den ble hoert
        # i, minst 1). Vanlige gjester dominerer, men en sjeldnere gjest kan
        # ogsaa faa dagen sin.
        weights = [max(1, s.get("sessions", 1)) for s in species]
        picked = random.choices(species, weights=weights,
                                k=min(2, len(species)))
        # random.choices trekker med tilbakelegging -- fjern duplikat.
        chosen = []
        for s in picked:
            if s["common_name"] not in [c["common_name"] for c in chosen]:
                chosen.append(s)

        scene = random.choice(HEARD_SCENES)
        if len(chosen) == 2:
            a, b = chosen[0]["common_name"], chosen[1]["common_name"]
            subject = f"{_article(a)} {a} and {_article(b)} {b} together {scene}"
        else:
            a = chosen[0]["common_name"]
            subject = f"{_article(a)} {a} {scene}"

        print(f"Dagens motiv fra BirdNET ({data.get('sessions_today', '?')} opptak i dag, "
              f"kandidater: "
              + ", ".join(f"{s['common_name']} x{s.get('sessions', 1)}" for s in species)
              + f") -> valgt: {', '.join(c['common_name'] for c in chosen)}")
        return subject
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: klarte ikke lese {BIRDS_JSON}: {e}", file=sys.stderr)
        return None


# Fast hale som holder ALLE bilder panel-vennlige (flate, mettede farger),
# uansett om det er dagens motiv eller et fritt emne fra Siri.
# "fills the whole frame ... no border" demper den svarte rammen som
# tegneserie-stilen ofte la rundt bildet (den passet ikke med paspartuen).
PANEL_SUFFIX = (
    "Bold saturated colors (red, yellow, blue, green), flat color areas, "
    "clear outlines, one clear focal subject, simple clean background, "
    "minimal fine detail, no text. The artwork fills the entire frame edge to "
    "edge — no border, no frame, no dark margins around the image. "
    "Vertical 3:4 composition."
)


def _resolve_style(style: str | None) -> str:
    """Tilfeldig stil hvis style == 'random', ellers valgt stil (eller standard)."""
    if style == "random":
        return random.choice([s for _, s in STYLES])
    return style or STYLE

# E Ink Spectra 6-paletten med 4-bits fargekoder (fra Waveshare-driveren).
# Samme rekkefoelge/koder som tools/send_to_frame.py -- IKKE endre uten aa
# endre der ogsaa, ellers blir fargene byttet om mellom manuell test og
# daglig bilde.
PALETTE = [
    (0x0, (0, 0, 0)),        # svart
    (0x1, (255, 255, 255)),  # hvit
    (0x2, (255, 255, 0)),    # gul
    (0x3, (255, 0, 0)),      # roed
    (0x5, (0, 0, 255)),      # blaa
    (0x6, (0, 255, 0)),      # groenn
]
CODES = np.array([c for c, _ in PALETTE], dtype=np.uint8)
PAL_RGB = np.array([rgb for _, rgb in PALETTE], dtype=np.float32)

# Atkinson-dithering -- valgt i tools/send_to_frame.py sine tester som beste
# allrounder for dette panelet. Floyd-Steinberg (PIL sin innebygde
# ImageOps/quantize-dithering) ble eksplisitt frarAådET i
# docs/Prompt-guide — bilder til ePaper-rammen.md: "overdiffunderer paa
# dette panelet -> stoey og groent hud-stikk". Denne fila brukte tidligere
# Image.FLOYDSTEINBERG via quantize() -- byttet ut med samme
# Atkinson-implementasjon som send_to_frame.py for konsistens.
ATKINSON_KERNEL = [(1, 0, 1 / 8), (2, 0, 1 / 8), (-1, 1, 1 / 8), (0, 1, 1 / 8), (1, 1, 1 / 8), (0, 2, 1 / 8)]

# yr/MET sine symbol_code-verdier (uten _day/_night/_polartwilight-suffiks)
# -> engelsk beskrivelse til prompten. Ukjente koder faar "unsettled weather".
WEATHER_SYMBOLS = {
    "clearsky": "clear sky", "fair": "mostly clear",
    "partlycloudy": "partly cloudy", "cloudy": "overcast", "fog": "foggy",
    "lightrain": "light rain", "rain": "rain", "heavyrain": "heavy rain",
    "lightrainshowers": "light rain showers", "rainshowers": "rain showers",
    "heavyrainshowers": "heavy rain showers",
    "lightsleet": "light sleet", "sleet": "sleet", "heavysleet": "heavy sleet",
    "lightsleetshowers": "sleet showers", "sleetshowers": "sleet showers",
    "heavysleetshowers": "heavy sleet showers",
    "lightsnow": "light snow", "snow": "snow", "heavysnow": "heavy snow",
    "lightsnowshowers": "light snow showers", "snowshowers": "snow showers",
    "heavysnowshowers": "heavy snow showers",
}


# ----------------------------------------------------------------------
# Steg 1: vaerdata (yr / api.met.no)
# ----------------------------------------------------------------------

# MET krever en identifiserende User-Agent (sidenavn + kontakt) -- anonyme
# klienter blir blokkert. Se https://api.met.no/doc/TermsOfService
MET_USER_AGENT = os.environ.get(
    "MET_USER_AGENT", "fugleramme-epaper/1.0 https://github.com/sonwit/Bilderamme")

WEATHER_RETRIES = int(os.environ.get("WEATHER_RETRIES", "3"))
WEATHER_BACKOFF = int(os.environ.get("WEATHER_BACKOFF", "10"))  # sekunder * forsoeksnr


def _symbol_to_desc(symbol_code: str) -> str:
    base = symbol_code.split("_", 1)[0]  # "partlycloudy_night" -> "partlycloudy"
    if base in WEATHER_SYMBOLS:
        return WEATHER_SYMBOLS[base]
    if "thunder" in base:
        return "thunderstorm"
    return "unsettled weather"


def get_weather() -> dict:
    url = ("https://api.met.no/weatherapi/locationforecast/2.0/compact"
           f"?lat={LAT}&lon={LON}")
    r = requests.get(url, timeout=20, headers={"User-Agent": MET_USER_AGENT})
    r.raise_for_status()
    ts = r.json()["properties"]["timeseries"][0]["data"]
    details = ts["instant"]["details"]
    symbol = ""
    for horizon in ("next_1_hours", "next_6_hours", "next_12_hours"):
        if horizon in ts and "summary" in ts[horizon]:
            symbol = ts[horizon]["summary"].get("symbol_code", "")
            break
    return {
        "temp": round(details["air_temperature"]),
        "desc": _symbol_to_desc(symbol),
        "wind": details.get("wind_speed", 0.0),
    }


def get_weather_safe() -> dict | None:
    """get_weather() med retry -- og None hvis alt feiler. Vaeret er kos, ikke
    kritisk: et dagsbilde uten vaerreferanse er mye bedre enn ingen bilde
    (26.07.2026: to dagers stopp fordi vaer-API-et svarte 503 kl. 07:00)."""
    for attempt in range(1, WEATHER_RETRIES + 1):
        try:
            return get_weather()
        except Exception as e:  # noqa: BLE001
            if attempt < WEATHER_RETRIES:
                wait = WEATHER_BACKOFF * attempt
                print(f"Vaer-API feilet (forsoek {attempt}/{WEATHER_RETRIES}): "
                      f"{str(e)[:140]} — venter {wait}s og proever igjen", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"ADVARSEL: vaer-API feilet {WEATHER_RETRIES} ganger ({str(e)[:140]}) "
                      "— genererer dagens bilde uten vaer.", file=sys.stderr)
    return None


def get_season(month: int) -> str:
    return {
        12: "deep winter", 1: "deep winter", 2: "late winter",
        3: "early spring", 4: "spring", 5: "late spring",
        6: "early summer", 7: "midsummer", 8: "late summer",
        9: "early autumn", 10: "autumn", 11: "late autumn",
    }[month]


def get_time_of_day(hour: int) -> str:
    if hour < 7:
        return "dawn"
    if hour < 11:
        return "bright morning"
    if hour < 15:
        return "midday"
    if hour < 19:
        return "afternoon"
    return "dusk"


# ----------------------------------------------------------------------
# Steg 2: bygg prompt
# ----------------------------------------------------------------------

def build_prompt(weather: dict | None = None, subject: str | None = None,
                 style: str | None = None, ref: bool = False,
                 daily_subject: str | None = None) -> str:
    """Bygger prompten.
    - ref=True       -> bilde-til-bilde: tegn OM referansebildet i valgt stil,
                        med emnet som ekstra instruksjon.
    - subject satt   -> fritt emne (fra Siri/HTTP): "A <stil> of <emne>. <panel-hale>"
    - subject None   -> dagens motiv (daily_subject, tilfeldig fugl/dyr) med
                        vaer/aarstid/doegntid. style='random' gir tilfeldig stil."""
    style = _resolve_style(style)
    if ref:
        base = f"Redraw the reference image as a {style}."
        if subject:
            base += f" {subject}."
        return f"{base} Keep the main subject clearly recognizable. {PANEL_SUFFIX}"
    if subject:
        return f"A {style} of {subject}. {PANEL_SUFFIX}"
    ds = daily_subject or random.choice(DAILY_SUBJECTS)
    now = datetime.datetime.now()
    season = get_season(now.month)
    time_of_day = get_time_of_day(now.hour)
    w = weather if weather is not None else get_weather_safe()
    if w:
        conditions = f"{w['desc'].capitalize()}, about {w['temp']} degrees Celsius, {season}."
    else:
        # Vaer-API-et nede: dropp vaeret, behold aarstid. Bildet skal alltid komme.
        conditions = f"{season.capitalize()}."
    return (
        f"A {style} of {ds} in a Norwegian garden at {time_of_day}. "
        f"{conditions} "
        f"{PANEL_SUFFIX}"
    )


# ----------------------------------------------------------------------
# Steg 3: Gemini-generering
# ----------------------------------------------------------------------

# Forbigaaende feil fra Gemini (modellen overbelastet e.l.) -- disse proever vi
# paa nytt automatisk i stedet for aa gi opp.
_TRANSIENT_MARKERS = ("503", "unavailable", "overloaded", "high demand",
                      "500", "internal", "429", "resource_exhausted", "deadline")

GEMINI_RETRIES = int(os.environ.get("GEMINI_RETRIES", "5"))
GEMINI_BACKOFF = int(os.environ.get("GEMINI_BACKOFF", "10"))  # sekunder * forsoeksnr


# 429 er normalt forbigaaende (rate limit) -- men IKKE naar den kommer av at
# prosjektet har naadd beloepsgrensen sin. Da hjelper ingen venting, og med
# 5 forsoek x voksende backoff brenner hvert kall halvannet minutt paa
# ingenting. Disse gaar rett i feil.
_ENDELIGE_MARKERS = ("spending cap", "exceeded its monthly", "billing",
                     "quota exceeded for quota metric", "permission_denied",
                     "api key not valid", "invalid_argument")


def _is_transient(err: Exception) -> bool:
    m = str(err).lower()
    if any(t in m for t in _ENDELIGE_MARKERS):
        return False
    return any(t in m for t in _TRANSIENT_MARKERS)


# Bildemodellen. gemini-2.5-flash-image har vaert standarden her siden
# starten; nyere generasjoner finnes (se `client.models.list()`) og er
# betydelig flinkere til aa foelge komposisjonsinstrukser. Overstyres per
# kall eller med IMAGE_MODEL i miljoet, saa det daglige bildet ikke endrer
# oppfoersel uten at noen har bestemt det.
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gemini-2.5-flash-image")


def generate_image(prompt: str, ref_images: list | None = None,
                   aspect_ratio: str = "3:4",
                   model: str | None = None) -> Image.Image:
    """Generer et bilde. ref_images (liste med PIL.Image) sendes med som
    referanse/seed for bilde-til-bilde — modellen (Nano Banana) tar imot bilder
    i tillegg til teksten. Proever paa nytt ved forbigaaende feil (503/overbelastet).

    aspect_ratio er 3:4 (portrett, hele panelet) for alt som fyller skjermen.
    compose_hero.py ber om 16:9, som er formatet paa hero-ramma inne i
    fuglesida — se den for hvorfor."""
    client = genai.Client()  # leser GEMINI_API_KEY fra miljoet
    contents = [prompt]
    if ref_images:
        contents.extend(ref_images)  # google-genai godtar PIL.Image direkte i contents
    cfg = types.GenerateContentConfig(
        image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
    )

    last_err = None
    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=model or IMAGE_MODEL, contents=contents, config=cfg)
            for part in resp.candidates[0].content.parts:
                if part.inline_data is not None:
                    return Image.open(BytesIO(part.inline_data.data)).convert("RGB")
            raise RuntimeError("Gemini returnerte ikke noe bilde")
        except Exception as e:  # noqa: BLE001
            last_err = e
            if _is_transient(e) and attempt < GEMINI_RETRIES:
                wait = GEMINI_BACKOFF * attempt
                print(f"Gemini opptatt (forsoek {attempt}/{GEMINI_RETRIES}): "
                      f"{str(e)[:140]} — venter {wait}s og proever igjen", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise last_err


# ----------------------------------------------------------------------
# Steg 4: tilpass og konverter til e-ink
# ----------------------------------------------------------------------

def fit_to_screen(img: Image.Image) -> Image.Image:
    """Skalerer og beskjaerer til WIDTHxHEIGHT (senter-crop, cover)."""
    src_ratio = img.width / img.height
    dst_ratio = WIDTH / HEIGHT
    if src_ratio > dst_ratio:
        new_h = HEIGHT
        new_w = int(new_h * src_ratio)
    else:
        new_w = WIDTH
        new_h = int(new_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - WIDTH) // 2
    top = (new_h - HEIGHT) // 2
    return img.crop((left, top, left + WIDTH, top + HEIGHT))


def _atkinson_dither(arr: np.ndarray) -> np.ndarray:
    """arr: (H,W,3) float32 RGB -> (H,W) panel-koder. Samme algoritme som
    tools/send_to_frame.py sin _error_diffuse(), holdt identisk med vilje."""
    H, W, _ = arr.shape
    arr = arr.copy()
    out = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            old = arr[y, x].copy()
            k = int(np.argmin(((PAL_RGB - old) ** 2).sum(axis=1)))
            out[y, x] = CODES[k]
            err = old - PAL_RGB[k]
            for dx, dy, w in ATKINSON_KERNEL:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    arr[ny, nx] += err * w
    return out


def _pack(indices: np.ndarray) -> bytes:
    """2 piksler per byte, hoey nibble = venstre piksel. Identisk med
    tools/send_to_frame.py sin pack()."""
    hi = indices[:, 0::2]
    lo = indices[:, 1::2]
    return ((hi << 4) | lo).astype(np.uint8).tobytes()


def to_epaper(img: Image.Image) -> tuple[Image.Image, bytes]:
    """Dithrer til Spectra 6-paletten (Atkinson) og pakker 2 piksler per byte."""
    # Litt ekstra metning og kontrast gjoer seg foer dithering til en saa
    # begrenset palett -- dytter mellomtoner mot palettens ytterpunkter.
    img = ImageEnhance.Color(img).enhance(1.3)
    img = ImageEnhance.Contrast(img).enhance(1.1)

    arr = np.asarray(img, dtype=np.float32)
    idx = _atkinson_dither(arr)
    framebuf = _pack(idx)

    code_to_rgb = {code: rgb for code, rgb in PALETTE}
    preview = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for code, rgb in code_to_rgb.items():
        preview[idx == code] = rgb

    return Image.fromarray(preview, "RGB"), framebuf


# ----------------------------------------------------------------------
# Hovedloep
# ----------------------------------------------------------------------

def _slug(text: str, maxlen: int = 40) -> str:
    """Lag et filnavn-vennlig kortnavn av emnet: æøå -> ae/oe/aa, resten a-z0-9."""
    t = text.lower()
    for k, v in {"æ": "ae", "ø": "oe", "å": "aa"}.items():
        t = t.replace(k, v)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:maxlen].strip("-") or "bilde"


def archive_original(img: "Image.Image", subject: str | None) -> str:
    """Lagre full-farge originalen med tidsstempel (+ emne hvis satt) i arkivet.
    Returnerer stien. Feiler stille (kun advarsel) saa arkivering aldri stopper
    selve bildevisningen."""
    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        name = f"{stamp}_{_slug(subject)}.png" if subject else f"{stamp}_dagens.png"
        path = os.path.join(ARCHIVE_DIR, name)
        img.save(path)
        return path
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: klarte ikke arkivere bildet: {e}", file=sys.stderr)
        return ""


def run(subject: str | None = None, style: str | None = None,
        ref_images: list | None = None) -> str:
    """Hele roerledningen: bygg prompt -> generer -> tilpass -> dither -> skriv
    frame.bin (+ preview.png/original.png). Returnerer prompten som ble brukt.

    subject=None gir dagens standardbilde (det cron kjoerer). subject satt gir
    et fritt emne (det frame_server.py bruker for Siri-kommandoen). ref_images
    (PIL.Image-liste) gir bilde-til-bilde (seed-bilder). Selve sendingen til
    skjermen gjoeres av push_to_frame.py / frame_server.py etterpaa."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Daglig bilde (ingen emne, ingen referanse): bruk fugl(er) BirdNET hoerte
    # i hagen i morges hvis birds.json er fersk, ellers tilfeldig motiv.
    # Tilfeldig stil uansett. Emne/Siri beholder valgt stil (forutsigbart).
    daily_subject = None
    if not subject and not ref_images:
        daily_subject = get_heard_bird() or random.choice(DAILY_SUBJECTS)
        if style is None:
            style = "random"

    # build_prompt henter selv vaer (med retry + uten-vaer-fallback) naar det
    # trengs -- kun for dagens bilde; emne/referanse bruker ikke vaer.
    prompt = build_prompt(subject=subject, style=style,
                          ref=bool(ref_images), daily_subject=daily_subject)
    print(f"Prompt: {prompt}")

    img = generate_image(prompt, ref_images=ref_images)
    img = fit_to_screen(img)
    preview, framebuf = to_epaper(img)

    assert len(framebuf) == (WIDTH // 2) * HEIGHT, f"Feil bufferstoerrelse: {len(framebuf)}"

    # frame.bin er det push_to_frame.py sender til rammen. Skrives atomisk via tmp-fil.
    tmp = os.path.join(OUTPUT_DIR, "frame.bin.tmp")
    with open(tmp, "wb") as f:
        f.write(framebuf)
    os.replace(tmp, os.path.join(OUTPUT_DIR, "frame.bin"))

    preview.save(os.path.join(OUTPUT_DIR, "preview.png"))
    img.save(os.path.join(OUTPUT_DIR, "original.png"))

    # Arkiver under emnet (Siri/web) eller dagens tilfeldige motiv, saa
    # galleriet viser hva bildet var — ogsaa for det daglige.
    archived = archive_original(img, subject or daily_subject)

    print(f"OK: {len(framebuf)} bytes skrevet til {OUTPUT_DIR}/frame.bin")
    if archived:
        print(f"Arkivert: {archived}")
    return prompt


def main():
    run()


if __name__ == "__main__":
    sys.exit(main())
