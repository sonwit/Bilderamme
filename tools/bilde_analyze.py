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
"""

from __future__ import annotations

import datetime
import json
import os
import sys

BASE_DIR = os.environ.get("FUGLE_DIR", "/opt/fugleramme")
DATA_DIR = os.environ.get("FUGLE_DATA_DIR", os.path.join(BASE_DIR, "data"))
LOGG = os.path.join(DATA_DIR, "kamera.jsonl")
VISION_MODEL = os.environ.get("VISION_MODEL", "gemini-3.5-flash")

PROMPT = (
    "This photo was taken through a window by a fixed camera pointed at a bird "
    "feeder in a garden in Hagen, just north of Oslo, Norway, in {maaned}. "
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


def analyser(sti: str) -> dict:
    from google import genai
    from PIL import Image

    im = Image.open(sti).convert("RGB")
    # Modellen trenger ikke 12 MP for aa kjenne igjen en meis, og mindre
    # bilde er billigere og raskere.
    im.thumbnail((1280, 1280))
    maaned = datetime.date.today().strftime("%B")
    client = genai.Client()
    resp = client.models.generate_content(
        model=VISION_MODEL, contents=[PROMPT.format(maaned=maaned), im])
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
    return {"fugler": fugler, "annet": str(d.get("annet", "")).strip()[:200]}


def les_meta(sti: str) -> dict:
    try:
        with open(os.path.splitext(sti)[0] + ".json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


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

    try:
        svar = analyser(sti)
    except Exception as e:  # noqa: BLE001
        print(f"FEIL: analysen feilet for {navn}: {str(e)[:160]}", file=sys.stderr)
        return 1

    rad = {
        "captured_at": stamp.isoformat(timespec="seconds"),
        "analyzed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "date": stamp.date().isoformat(),
        "hour": stamp.hour,
        "file": navn,
        "species": svar["fugler"],
        "annet": svar["annet"],
        "kamera": les_meta(sti),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOGG, "a") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")

    if svar["fugler"]:
        print(f"=== {navn}: " + ", ".join(
            f"{s['norsk'] or s['common_name']} ({s['scientific_name']}) {s['confidence']:.2f}"
            + (f" x{s['antall']}" if s['antall'] > 1 else "")
            for s in svar["fugler"]) + " ===")
    else:
        print(f"=== {navn}: ingen fugl" + (f" — {svar['annet']}" if svar["annet"] else "") + " ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
