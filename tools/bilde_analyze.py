#!/usr/bin/env python3
"""
bilde_analyze.py — hvilken fugl er paa bildet? Ett bilde fra kameraet i
vinduet inn, en linje i data/kamera.jsonl ut.

Motstykket til birdnet_analyze.py for lyd. Pi-en har alt gjort
bevegelsesdeteksjonen og beskjaeringen; her spoer vi modellen hva som staar
paa materen. Svaret er JSON med artene den ser, latinsk og norsk navn, hvor
sikker den er, og hvor mange. Ingen fugl er et helt vanlig svar -- greiner i
vind og skygger utloeser ogsaa kameraet -- og logges som tom liste, saa
statistikken ser hvor ofte kameraet gaar av for ingenting.

    venv/bin/python3 bilde_analyze.py bilder/kamera_20260903_113000.jpg

Trigges av audio_ingest.py etter hvert mottatt bilde. Kjoeres i den vanlige
venv-en (google-genai + Pillow), ikke i venv-birdnet.

Kostnadsbremsene (maalt 12. sep 2026): 3.-10. sep gikk 1559 bilder til
gemini-3.5-flash i 1280 px med tenking paa, anslaatt 0,05-0,15 kr per bilde
og 80-90 % av hele Gemini-regningen. Halvparten hadde ingen fugl, og 808 av
1558 kom under ett minutt etter forrige bilde. Derfor:

  * gemini-3.1-flash-lite uten tenking, 768 px (én flis = 258 tokens):
    under 0,01 kr per bilde.  KAMERA_MODELL, KAMERA_BILDE_PX
  * tak per time -- resten logges som hoppet over.  KAMERA_MAKS_PER_TIME
  * pause etter 429 (kvote/tak), saa vi ikke banker paa en stengt doer
    hundrevis av ganger om dagen.  KAMERA_PAUSE_429_S
  * tokenforbruket per kall skrives i loggen, saa prisen kan regnes, ikke
    anslaas.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time

BASE_DIR = os.environ.get("FUGLE_DIR", "/opt/fugleramme")
DATA_DIR = os.environ.get("FUGLE_DATA_DIR", os.path.join(BASE_DIR, "data"))
LOGG = os.path.join(DATA_DIR, "kamera.jsonl")

# Modellen. gemini-3.1-flash-lite koster 0,25/1,50 USD per million tokens
# mot 1,50/9,00 for gemini-3.5-flash, og kjenner igjen en skjaere like godt.
# 2.5-modellene svarer 404 «no longer available to new users» for denne
# noekkelen (sjekket 13. sep 2026), saa de er ikke et valg. Tenkingen settes
# til «minimal»: svaret er en kort JSON, og tenketokens betales som utdata --
# «low» brukte 121 tenketokens paa aa svare «OK».
KAMERA_MODELL = os.environ.get("KAMERA_MODELL", "gemini-3.1-flash-lite")
# Lengste side paa bildet som sendes. Opp til 768 px er én flis (258 tokens);
# 1280 px var fire. Utsnittet fra Pi-en er alt beskaaret rundt materen.
BILDE_PX = int(os.environ.get("KAMERA_BILDE_PX", "768"))
# Flere bilder enn dette i loepet av en time analyseres ikke -- de logges som
# hoppet over. En skjaere som sitter i ti minutter gir ikke ny informasjon
# for hvert bilde.
MAKS_PER_TIME = int(os.environ.get("KAMERA_MAKS_PER_TIME", "12"))
# Etter et 429 (kvote brukt opp, tak naadd) ventes det saa lenge foer neste
# kall. 10.-12. sep 2026 gjorde vi 686 avviste kall paa tre dager.
PAUSE_ETTER_429_S = int(os.environ.get("KAMERA_PAUSE_429_S", "3600"))
PAUSEFIL = os.path.join(DATA_DIR, "kamera.pause")

PROMPT = (
    "This photo was taken through a window by a fixed camera pointed at a bird "
    "feeder in a garden near Oslo, Norway, in {maaned}. "
    "Identify every bird or other animal visible -- a squirrel or a cat goes "
    "in the same list, with its scientific name. Common species here: great tit, blue tit, "
    "coal tit, magpie, hooded crow, jay, fieldfare, redwing, blackbird, "
    "chaffinch, greenfinch, siskin, bullfinch, tree sparrow, house sparrow, "
    "nuthatch, great spotted woodpecker, lesser spotted woodpecker, robin, "
    "dunnock, wood pigeon, red squirrel (Sciurus vulgaris).\n\n"
    "Answer with JSON only, nothing else:\n"
    '{{"fugler": [{{"scientific_name": "<Genus species>", '
    '"common_name": "<English name>", "norsk": "<Norwegian bokmal name>", '
    '"confidence": <0.0-1.0, how sure you are of the species>, '
    '"antall": <how many of this species>}}], '
    '"annet": "<anything else notable in one short sentence, or empty>"}}\n'
    "If there is no bird, answer {{\"fugler\": [], \"annet\": \"...\"}}. "
    "Do not guess a species from a blur: if you can see a bird but not which, "
    "use scientific_name \"Aves\" with low confidence."
)


def _config():
    """Tenking av. 2.5-modellene tar thinking_budget=0; 3.x-modellene har
    thinking_level, der «minimal» ga null tenketokens paa begge lite-modellene
    (maalt 13. sep 2026)."""
    from google.genai import types
    if KAMERA_MODELL.startswith("gemini-2.5"):
        tenk = types.ThinkingConfig(thinking_budget=0)
    else:
        tenk = types.ThinkingConfig(thinking_level="minimal")
    return types.GenerateContentConfig(thinking_config=tenk)


def _tokens(resp) -> dict:
    """Forbruket slik API-et rapporterer det. Tenkte tokens skilles ut: de
    betales som utdata og er det som gjoer et kall dyrt."""
    u = getattr(resp, "usage_metadata", None)
    if u is None:
        return {}
    return {
        "inn": int(getattr(u, "prompt_token_count", 0) or 0),
        "ut": int(getattr(u, "candidates_token_count", 0) or 0),
        "tenkt": int(getattr(u, "thoughts_token_count", 0) or 0),
        "totalt": int(getattr(u, "total_token_count", 0) or 0),
    }


def analyser(sti: str) -> dict:
    from google import genai
    from PIL import Image

    im = Image.open(sti).convert("RGB")
    # Modellen trenger ikke 12 MP for aa kjenne igjen en meis, og mindre
    # bilde er billigere og raskere.
    im.thumbnail((BILDE_PX, BILDE_PX))
    maaned = datetime.date.today().strftime("%B")
    client = genai.Client()
    resp = client.models.generate_content(
        model=KAMERA_MODELL, contents=[PROMPT.format(maaned=maaned), im],
        config=_config())
    tekst = (resp.text or "").strip()
    tekst = tekst.removeprefix("```json").removeprefix("```").removesuffix("```")
    d = json.loads(tekst.strip())
    fugler = []
    for f in d.get("fugler", []):
        try:
            fugler.append({
                "scientific_name": str(f.get("scientific_name", "")).strip(),
                "common_name": str(f.get("common_name", "")).strip(),
                "norsk": str(f.get("norsk", "")).strip(),
                "confidence": round(max(0.0, min(1.0, float(f.get("confidence", 0)))), 2),
                "antall": int(f.get("antall", 1) or 1),
            })
        except (TypeError, ValueError):
            continue
    return {"fugler": fugler, "annet": str(d.get("annet", "")).strip()[:200],
            "tokens": _tokens(resp)}


def les_meta(sti: str) -> dict:
    try:
        with open(os.path.splitext(sti)[0] + ".json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ----------------------------------------------------------------------
# Bremsene
# ----------------------------------------------------------------------

def analyser_siste_time() -> int:
    """Hvor mange modellkall loggen har den siste timen. Leser bakfra: radene
    staar i tidsrekkefoelge, saa vi stopper ved foerste rad som er eldre."""
    grense = datetime.datetime.now() - datetime.timedelta(hours=1)
    try:
        with open(LOGG, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 300_000))
            linjer = f.read().decode("utf-8", "replace").split("\n")
    except OSError:
        return 0
    n = 0
    for l in reversed(linjer):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
            t = datetime.datetime.fromisoformat(r.get("analyzed_at", ""))
        except ValueError:
            continue
        if t < grense:
            break
        if not r.get("hoppet_over"):
            n += 1
    return n


def pause_igjen_s() -> int:
    """Sekunder igjen av pausen etter et 429, eller 0."""
    try:
        igjen = PAUSE_ETTER_429_S - (time.time() - os.path.getmtime(PAUSEFIL))
    except OSError:
        return 0
    return int(igjen) if igjen > 0 else 0


def start_pause(grunn: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PAUSEFIL, "w") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {grunn}\n")


def er_kvotefeil(e: Exception) -> bool:
    t = str(e)
    return "429" in t or "RESOURCE_EXHAUSTED" in t


def hvorfor_hoppe_over() -> str | None:
    igjen = pause_igjen_s()
    if igjen:
        til = (datetime.datetime.now() + datetime.timedelta(seconds=igjen)).strftime("%H:%M")
        return f"pause etter 429 til {til}"
    n = analyser_siste_time()
    if n >= MAKS_PER_TIME:
        return f"tak {MAKS_PER_TIME} analyser per time naadd ({n})"
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("Bruk: bilde_analyze.py <bilde.jpg>", file=sys.stderr)
        return 2
    sti = sys.argv[1]
    if not os.path.isfile(sti):
        print(f"Finner ikke fila: {sti}", file=sys.stderr)
        return 1
    navn = os.path.basename(sti)
    try:
        stamp = datetime.datetime.strptime(navn[7:22], "%Y%m%d_%H%M%S")
    except ValueError:
        stamp = datetime.datetime.now()

    rad = {
        "captured_at": stamp.isoformat(timespec="seconds"),
        "analyzed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "date": stamp.date().isoformat(),
        "hour": stamp.hour,
        "file": navn,
        "species": [],
        "annet": "",
        "kamera": les_meta(sti),
    }

    grunn = hvorfor_hoppe_over()
    if grunn:
        # Logges, men uten modellkall: statistikken skal se at bildet kom, og
        # fugler.py skal ikke telle det som «ingen fugl».
        rad["hoppet_over"] = grunn
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOGG, "a") as f:
            f.write(json.dumps(rad, ensure_ascii=False) + "\n")
        print(f"=== {navn}: hoppet over — {grunn} ===")
        return 0

    try:
        svar = analyser(sti)
    except Exception as e:  # noqa: BLE001
        if er_kvotefeil(e):
            start_pause(str(e)[:120])
            print(f"FEIL: 429 fra Gemini for {navn} — kameraanalysen tar pause i "
                  f"{PAUSE_ETTER_429_S // 60} min: {str(e)[:160]}", file=sys.stderr)
        else:
            print(f"FEIL: analysen feilet for {navn}: {str(e)[:160]}", file=sys.stderr)
        return 1

    rad["species"] = svar["fugler"]
    rad["annet"] = svar["annet"]
    rad["modell"] = KAMERA_MODELL
    rad["tokens"] = svar["tokens"]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOGG, "a") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")
    tok = svar["tokens"]
    tokentekst = (f" · {tok.get('totalt', 0)} tokens"
                  + (f" ({tok['tenkt']} tenkt)" if tok.get("tenkt") else "")
                  if tok else "")
    if svar["fugler"]:
        print(f"=== {navn}: " + ", ".join(
            f"{s['norsk'] or s['common_name']} ({s['scientific_name']}) {s['confidence']:.2f}"
            + (f" x{s['antall']}" if s['antall'] > 1 else "")
            for s in svar["fugler"]) + tokentekst + " ===")
    else:
        print(f"=== {navn}: ingen fugl" + (f" — {svar['annet']}" if svar["annet"] else "")
              + tokentekst + " ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
