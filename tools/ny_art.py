#!/usr/bin/env python3
"""
Fugleramme: gjoer en ukjent art klar til aa tegnes.

Foer denne fila var en ny art en manuell oeving i fem trinn: finne en plansje
paa Commons, se gjennom kontaktarket og velge, vaske skanningen, be Gemini
tegne fuglen 1:1, og maale fotpunktet. Metadataene -- norsk navn, lengde,
habitat -- maatte skrives inn i bird_names.py for haand. Sto arten uten, ble
den tegnet 18 cm stor (standardverdien), plassert som trefugl og navngitt paa
engelsk.

Her gjoeres alt i én kjoering:

  1. Kildeplansje   Commons-kategorien «<Genus art> (illustrations)».
                    fetch_plates rangerer kandidatene, modellen ser paa
                    miniatyrene og velger den ene som faktisk er brukbar --
                    kategoriene inneholder ogsaa frimerker, foto og
                    fargeleggingsark.
  2. Vasking        prepare_plates: hvitpunkt per kanal + trimming. En raa
                    skanning har papirtone som ikke finnes i panelets palett.
  3. Metadata       norsk navn, lengde i cm, habitat, overvintring. Skrives
                    til plates/arter.json, som bird_names.py leser.
  4. 1:1-fugler     sittende og flygende, med kildeplansja som forelegg.
  5. Fotpunkt       hvor foettene er i bildet, saa fuglen kan settes paa en
                    grein i stedet for aa sveve over den.

    venv/bin/python ny_art.py --art "Chloris chloris"
    venv/bin/python ny_art.py --mangler --birds birds.json

Koster 2 bildekall + 2 modellkall per art, én gang. Alt gjenbrukes hver dag
arten dukker opp -- det er derfor biblioteket vokser med arter, ikke dager.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bird_names import ARTER_JSON, norwegian_name  # noqa: E402
from fetch_plates import UA, candidates, fetch  # noqa: E402
from prepare_plates import prepare  # noqa: E402
from render_daily_panel import PLATES_DIR, plate_path, split_species  # noqa: E402
import compose_branch as cb  # noqa: E402

VASKET_DIR = os.path.join(PLATES_DIR, "vasket")

# Hvor mange kandidater modellen faar se. Flere gir bedre valg, men hver
# miniatyr er et bilde i konteksten -- seks holder i praksis, kategoriene er
# rangert paa forhaand.
VIS_KANDIDATER = int(os.environ.get("ART_KANDIDATER", "6"))

# Tak paa hvor mange arter én kjoering klargjoer. Uten det kunne en dag med
# mange ferske arter tygge seg gjennom kvoten uten at noen saa det.
STANDARD_MAKS = int(os.environ.get("ART_MAKS", "3"))


VELG_PROMPT = (
    "These are candidate illustrations of {sci} ({navn}) from Wikimedia "
    "Commons, numbered 1 to {n} in the order shown.\n\n"
    "Pick the ONE that works best as a source plate for redrawing this bird: "
    "a single bird, whole body visible including legs and feet, seen from the "
    "side, drawn or painted rather than photographed, plumage and markings "
    "clearly readable, no caption or text across the bird, no heavy frame. "
    "A 19th-century hand-coloured engraving is ideal. Reject photographs, "
    "stamps, colouring-book outlines, museum specimens, eggs, nests, maps, "
    "and images where the bird is small or partly hidden.\n\n"
    "Answer with JSON only, nothing else: "
    '{{"nr": <the number>, "hvorfor": "<six words or fewer>"}}. '
    'If none are usable, answer {{"nr": 0, "hvorfor": "..."}}.'
)

FAKTA_PROMPT = (
    "Facts about the bird {sci}. Answer with JSON only, nothing else:\n"
    "{{\n"
    '  "norsk": "<the Norwegian (bokmal) name, one word if that is the name, '
    'first letter capitalised>",\n'
    '  "engelsk": "<the common English name>",\n'
    '  "lengde_cm": <typical total length from bill tip to tail tip in '
    "centimetres, a plain number>,\n"
    '  "habitat": "<exactly one of: tre, vaatmark, bakke, luft — tre = '
    "normally perches in trees or bushes, vaatmark = wetland, reeds, marsh or "
    "water, bakke = normally on open ground, luft = spends most of its time "
    'on the wing>",\n'
    '  "overvintrer": <true if the species normally stays in Norway through '
    "the winter, false if it migrates away>\n"
    "}}"
)


def _modellsvar(deler: list) -> dict | None:
    """Ett modellkall som skal svare JSON. None hvis svaret ikke lot seg lese."""
    try:
        from google import genai
        client = genai.Client()
        resp = client.models.generate_content(
            model=cb.VISION_MODEL, contents=deler)
        tekst = (resp.text or "").strip()
        tekst = tekst.removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(tekst.strip())
    except Exception as e:  # noqa: BLE001
        print(f"    modellkallet feilet: {str(e)[:120]}", file=sys.stderr)
        return None


def _hent_miniatyr(url: str) -> Image.Image | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception as e:  # noqa: BLE001
        print(f"    miniatyr feilet: {str(e)[:90]}", file=sys.stderr)
        return None


def kildeplansje(sci: str, navn: str) -> str | None:
    """Finn, velg, hent og vask en kildeplansje. Returnerer stien, eller None.

    Kategoriene paa Commons er rotete -- ved siden av Naumann og Gould ligger
    frimerker, moderne foto og fargeleggingsark. fetch_plates filtrerer paa
    lisens, format og stoerrelse og rangerer kjente plansjeverk foerst, men
    toppkandidaten er ikke alltid brukbar. Derfor faar modellen se miniatyrene
    og peke ut én: ett kall, ingen bortkastede nedlastinger."""
    finnes = plate_path(sci)
    if finnes:
        print(f"  kildeplansje finnes alt: {os.path.basename(finnes)}")
        return finnes

    kand = candidates(sci)[:VIS_KANDIDATER]
    if not kand:
        print(f"  {sci}: ingen brukbare kandidater paa Commons", file=sys.stderr)
        return None
    print(f"  {len(kand)} kandidater fra Commons")

    bilder, vist = [], []
    for k in kand:
        im = _hent_miniatyr(k.get("thumb") or "")
        if im:
            bilder.append(im)
            vist.append(k)
    if not bilder:
        return None

    deler: list = [VELG_PROMPT.format(sci=sci, navn=navn, n=len(vist))]
    for i, im in enumerate(bilder, 1):
        deler += [f"Candidate {i}:", im]
    svar = _modellsvar(deler) or {}
    nr = int(svar.get("nr") or 0)
    if not 1 <= nr <= len(vist):
        print(f"  {sci}: modellen fant ingen brukbar plansje "
              f"({svar.get('hvorfor', 'uten begrunnelse')})", file=sys.stderr)
        return None
    valgt = vist[nr - 1]
    print(f"  valgte {nr}/{len(vist)}: {valgt['title']}"
          f"  ({svar.get('hvorfor', '')})")

    raa = fetch(valgt["title"], sci)
    os.makedirs(VASKET_DIR, exist_ok=True)
    ut = os.path.join(VASKET_DIR,
                      os.path.splitext(os.path.basename(raa))[0] + ".png")
    w, h = prepare(raa, ut)
    print(f"  vasket -> {os.path.basename(ut)} ({w}x{h})")
    return ut


def fakta(sci: str) -> dict | None:
    """Norsk navn, lengde, habitat og overvintring for arten.

    Lengden er den viktigste: uten den tegnes fuglen 18 cm stor, og da blir en
    stokkand like stor som en kjoettmeis. Habitatet avgjoer hvilke plasser paa
    malen arten kan staa paa."""
    d = _modellsvar([FAKTA_PROMPT.format(sci=sci)])
    if not d:
        return None
    try:
        lengde = float(d["lengde_cm"])
        habitat = str(d["habitat"]).strip().lower()
        if habitat not in ("tre", "vaatmark", "bakke", "luft"):
            print(f"    ukjent habitat «{habitat}» — bruker tre", file=sys.stderr)
            habitat = "tre"
        if not 5 <= lengde <= 300:
            print(f"    urimelig lengde {lengde} cm — hopper over arten",
                  file=sys.stderr)
            return None
        return {
            "norsk": str(d["norsk"]).strip(),
            "engelsk": str(d.get("engelsk", "")).strip(),
            "lengde_cm": round(lengde, 1),
            "habitat": habitat,
            "overvintrer": bool(d.get("overvintrer", False)),
            "kilde": "modell",
            "lagt_til": datetime.date.today().isoformat(),
        }
    except (KeyError, TypeError, ValueError) as e:
        print(f"    ufullstendig svar: {e}", file=sys.stderr)
        return None


def lagre_fakta(sci: str, d: dict) -> None:
    alle = {}
    if os.path.exists(ARTER_JSON):
        with open(ARTER_JSON) as f:
            alle = json.load(f)
    alle[sci.strip().lower()] = d
    tmp = ARTER_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(sorted(alle.items())), f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARTER_JSON)


def klargjoer(sci: str, vanlig: str = "", flyvende: bool = True) -> bool:
    """Hele veien for én art. True hvis den kan tegnes etterpaa."""
    print(f"\n=== {sci} ===")
    navn = vanlig or norwegian_name(sci) or sci

    # Fakta foerst: er arten ukjent for modellen ogsaa, er det ingen vits i aa
    # bruke to bildekall paa den.
    d = fakta(sci)
    if not d:
        return False
    lagre_fakta(sci, d)
    print(f"  {d['norsk']} ({d['engelsk']}) · {d['lengde_cm']} cm · "
          f"{d['habitat']} · {'overvintrer' if d['overvintrer'] else 'trekkfugl'}")
    vanlig = vanlig or d["engelsk"] or navn

    if not kildeplansje(sci, d["norsk"]):
        return False

    s = {"scientific_name": sci, "common_name": vanlig}
    sti = cb.ensure_bird(s, "sittende")
    if not sti:
        return False

    # Fotpunktet maales paa den utklipte fuglen paa hvit bunn -- samme bilde
    # sammensettingen selv jobber med.
    raa = cb.cutout(sti)
    paa_hvitt = Image.new("RGB", raa.size, (255, 255, 255))
    paa_hvitt.paste(raa, (0, 0), raa)
    fx, fy = cb.foot_point(sti, paa_hvitt, force=True)
    print(f"  fotpunkt ({fx}, {fy}) i {raa.width}x{raa.height}")

    if flyvende:
        # Flygende fugler trenger ikke fotpunkt -- de sentreres paa kroppen.
        cb.ensure_bird(s, "flyvende")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gjoer en ukjent art klar til aa tegnes.")
    ap.add_argument("--art", action="append", default=[], metavar="'Genus art'",
                    help="latinsk navn (kan gjentas)")
    ap.add_argument("--vanlig", default="", metavar="'English name'",
                    help="engelsk navn til bildeprompten (bare med én --art)")
    ap.add_argument("--mangler", action="store_true",
                    help="klargjoer alle sikre arter i --birds som mangler plansje")
    ap.add_argument("--birds", default=os.path.join(HERE, "birds.json"))
    ap.add_argument("--ingen-flyvende", action="store_true",
                    help="hopp over den flygende varianten (sparer ett bilde)")
    ap.add_argument("--maks", type=int, default=STANDARD_MAKS,
                    help=f"tak paa antall arter i én kjoering (standard "
                         f"{STANDARD_MAKS}); 0 lister bare hva som mangler")
    args = ap.parse_args()

    arter = [a.strip() for a in args.art]
    if args.mangler:
        with open(args.birds) as f:
            birds = json.load(f)
        sure, _ = split_species(birds.get("species", []), None)
        for s in sure:
            sci = s.get("scientific_name", "")
            if sci and not plate_path(sci) and sci not in arter:
                arter.append(sci)
    if not arter:
        print("Ingen arter aa klargjoere.")
        return 0

    # --maks 0 er en ren rapport: si hva som mangler og la det staa.
    if args.maks <= 0:
        print(f"{len(arter)} arter mangler plansje: {', '.join(arter)}")
        return 0
    if len(arter) > args.maks:
        print(f"{len(arter)} arter mangler, tar de {args.maks} foerste "
              f"(--maks for flere): {', '.join(arter[args.maks:])} venter",
              file=sys.stderr)
        arter = arter[:args.maks]

    ok = 0
    for sci in arter:
        vanlig = args.vanlig if len(arter) == 1 else ""
        try:
            ok += bool(klargjoer(sci, vanlig, not args.ingen_flyvende))
        except Exception as e:  # noqa: BLE001
            print(f"  {sci} feilet: {str(e)[:140]}", file=sys.stderr)

    print(f"\n{ok} av {len(arter)} arter klare.")
    # Klarte vi ingen, skal den som kalte oss faa vite det.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
