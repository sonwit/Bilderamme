#!/usr/bin/env python3
"""
Fugleramme: lag dagens hovedplansje av de ekte plansjene.

Idéen: i stedet for aa vise ÉN skannet plansje av ÉN art, gi Gemini de vaskede
plansjene til dagens arter som referansebilder og be den komponere ÉN plansje
med én fugl av hver, i samme stil som forelegget -- og i det formatet layouten
faktisk trenger.

Det loeser to ting paa én gang:
  * De gamle plansjene er staaende. Hero-ramma er liggende (1104x620 = 16:9).
    En skannet plansje fyller derfor bare en tredel av ramma. Her bestiller vi
    formatet vi vil ha.
  * Dagens fugler kommer sammen paa ett bilde i stedet for at bare den
    best belagte arten faar plass.

    venv/bin/python compose_hero.py --birds birds.json

Skriver plates/dagens-hero.png + dagens-hero.json (dato + hvilke arter som er
med). render_daily_panel.py bruker den som hero naar den er fra i dag.

MERK: dette er en TEGNING etter forelegg, ikke et oppslagsverk. Gemini kopierer
stilen godt, men ikke nødvendigvis artskjennetegnene -- en fugl her kan ha feil
vingebånd. Vil du ha noe som er sant ned til fjæra, bruk den skannede plansjen.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bird_names import norwegian_name          # noqa: E402
from generate_daily_image import generate_image  # noqa: E402  (retry-logikken)
from prepare_plates import whiten              # noqa: E402
from render_daily_panel import (PLATES_DIR, load_birds, plate_path,  # noqa: E402
                                split_species)

HERO_PNG = os.path.join(PLATES_DIR, "dagens-hero.png")
HERO_JSON = os.path.join(PLATES_DIR, "dagens-hero.json")
# --full skriver hit i stedet: bakgrunn som fyller hele 1200x1600.
BG_PNG = os.path.join(PLATES_DIR, "dagens-bakgrunn.png")
BG_JSON = os.path.join(PLATES_DIR, "dagens-bakgrunn.json")

# Hvor mange arter som faar plass i én komposisjon. Over 4 blir fuglene smaa og
# stilen mister presisjonen -- og hero-ramma er tross alt 1104x620.
MAX_BIRDS = int(os.environ.get("HERO_MAX_BIRDS", "3"))

# Referansebildene skaleres ned foer de sendes: modellen trenger stilen og
# fasongen, ikke 1900x2900 piksler, og store vedlegg gjoer kallet tregt.
REF_MAX = 900


# Sonene teksten skal ligge i naar bakgrunnen fyller hele skjermen. Brøkdeler
# av 1200x1600, og de MAA stemme med grid-omraadene i render_daily_panel.py sin
# overlegg-layout -- maaler vi paa feil sted, sier maalingen ingenting.
#   (navn, x0, y0, x1, y1)
SONER = [
    # Ett sammenhengende felt til venstre i stedet for topp+venstre hver for
    # seg: infoboksen og artslista ligger naa i samme spalte, og det er
    # enklere for modellen aa forholde seg til ÉN tom flate enn to.
    ("venstre",  0.00, 0.00, 0.48, 0.72),   # infoboks + artsliste
    # (Bunnsonen er borte: bunnlinja ble flyttet inn under lista, saa malen
    #  skal fylle nedre kant og maa ikke holdes ren der.)
]
# Hvor stor andel av en sone som kan ha blekk foer teksten trenger en hvit pute
# under seg. 3 % taaler en enslig kvist; over det begynner bokstavene aa drukne.
SONE_GRENSE = float(os.environ.get("HERO_ZONE_LIMIT", "0.03"))


# Sonen deles i vannrette baand foer den maales. Snittet over hele spalten
# lyver: en enslig fugl midt i artslista ga 1,9 % -- under grensen -- selv om
# den laa rett oppaa fire linjer med tekst. Det som teller er hvor mye blekk
# det er DER det er mest, ikke i snitt.
SONE_BAAND = int(os.environ.get("HERO_ZONE_BANDS", "10"))


def zone_report(img: Image.Image) -> dict:
    """Hvor mye blekk ligger i hver tekstsone? Modellen foelger ikke alltid
    komposisjonsinstruksen, saa vi maaler i stedet for aa haape. Sonene som
    ikke er rene nok, faar en hvit pute under teksten i panelet."""
    import numpy as np
    arr = np.asarray(img.convert("RGB"), dtype=np.float32).mean(axis=2)
    H, W = arr.shape
    out = {}
    for navn, x0, y0, x1, y1 in SONER:
        felt = arr[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        if not felt.size:
            out[navn] = {"blekk": 1.0, "verst": 1.0, "ren": False}
            continue
        blekk = float((felt < 235).mean())
        baand = np.array_split(felt, SONE_BAAND, axis=0)
        verst = max(float((b < 235).mean()) for b in baand if b.size)
        out[navn] = {"blekk": round(blekk, 4), "verst": round(verst, 4),
                     "ren": verst <= SONE_GRENSE}
    return out


def fit_to_panel(img: Image.Image, w: int = 1200, h: int = 1600) -> Image.Image:
    """Legg bildet paa et hvitt ark paa noeyaktig panelstoerrelse.

    Gemini treffer ikke formatet paa pikselen -- en 3:4-bestilling kom tilbake
    som 864x1184 (0,730 mot 0,750). Skalerer nettleseren det med `cover`,
    beskjaeres 22 px oppe og nede, og da mistet vi hodet paa fuglen oeverst.
    Vi skalerer derfor til aa FYLLE INNI, og fyller resten med hvitt -- hvitt
    er papir her, og en av panelets seks farger, saa det koster ingenting."""
    skala = min(w / img.width, h / img.height)
    ny = img.resize((round(img.width * skala), round(img.height * skala)),
                    Image.LANCZOS)
    ark = Image.new("RGB", (w, h), (255, 255, 255))
    ark.paste(ny, ((w - ny.width) // 2, (h - ny.height) // 2))
    return ark


# Grenmalen bor naa sammen med de andre malene i plates/maler/.
GREN_PNG = os.path.join(PLATES_DIR, "maler", "gren.png")

# Grunnen til at grenen finnes: prompt-tekst styrer komposisjon daarlig.
# Samme instruks ga 0,1 % blekk i tekstsonen ett forsoek og 14,8 % det neste.
# Et FAST forelegg -- en gren som allerede ligger der den skal -- gir modellen
# en fysisk plassering aa henge fuglene paa i stedet for en beskrivelse aa
# tolke. Grenen lages EN gang og gjenbrukes hver dag, saa sida faar samme
# skjelett uansett hvilke fugler som var i hagen.
GREN_PROMPT = (
    "A single bare tree branch, drawn as a 19th-century engraved book plate: "
    "fine linework, muted brown bark, no leaves. "
    "The branch enters at the bottom-right corner, runs along the BOTTOM edge "
    "and up the RIGHT edge, forming an L that frames the lower and right "
    "margins of the page, with a few small side twigs reaching inward. "
    "The upper-left region — the left 48% of the width, from the very top down "
    "to 75% of the height — must be completely empty white paper: nothing at "
    "all there. Keep the bottom 6% empty white paper across the full width. "
    "Pure white background, no paper texture, no border, no frame, no shading "
    "behind the branch. No birds, no text, no signature. "
    "Tall vertical composition."
)


def build_branch_prompt(names: list[str]) -> str:
    """Fuglene settes paa den ferdige grenen. Foerste referansebilde ER
    malen -- resten er stilforelegg for artene."""
    birds = ", ".join(names)
    return (
        "The FIRST reference image is the exact layout template: a bare branch "
        "on white paper. Reproduce that branch in the SAME position and shape, "
        f"and perch these birds on it, one of each: {birds}. "
        "The remaining reference images show how each species should look — "
        "match their style: hand-coloured 19th-century lithograph, fine "
        "engraved linework, naturalistic plumage. "
        "Place the birds along the branch so they sit in the lower and right "
        "part of the page. Do not move the branch, do not add a second branch. "
        "The upper-left region — the left 48% of the width, from the very top "
        "down to 75% of the height — must stay completely empty white paper. "
        "Keep the bottom 6% empty white paper across the full width. "
        "Pure white background, no paper texture, no border, no frame. "
        "Bold saturated colours in flat areas, minimal soft shading. "
        "Absolutely no text anywhere: no captions, no labels, no species "
        "names, no handwriting, no signature. "
        "Tall vertical composition."
    )


def build_full_prompt(names: list[str]) -> str:
    """Helsides bakgrunn: fuglene til hoeyre, tomt papir der teksten skal.

    Formuleringen er bevisst konkret ("the left 45%") og gjentar hva TOMT
    betyr. Ber man bare om «space for text», fyller modellen det med kvister."""
    birds = ", ".join(names)
    return (
        f"An antique ornithological book plate showing these birds, one of "
        f"each: {birds}. "
        "Hand-coloured 19th-century lithograph, fine engraved linework, "
        "naturalistic plumage, birds perched on bare branches. "
        "COMPOSITION IS CRITICAL: place all birds and all branches in the "
        "RIGHT HALF of the image and along the LOWER portion of the image, "
        "so that they form an L shape hugging the right edge and the bottom. "
        "The upper-left region — the left 48% of the width, from the very top "
        "down to 75% of the height — must be completely empty white paper: no "
        "birds, no branches, no twigs, no leaves, no shading, nothing at all. "
        "The bottom 6% must also be empty white paper across the full width. "
        "Pure white paper background everywhere — no paper texture, no "
        "ageing, no stains, no border, no frame, no vignette. "
        "Bold saturated colours in flat areas, minimal soft shading. "
        "Absolutely no text anywhere: no captions, no labels, no species "
        "names, no handwriting, no signature, no page numbers. "
        "Tall vertical composition."
    )


def build_prompt(names: list[str]) -> str:
    """Prompten. Tre ting maa staa der for at resultatet skal kle panelet:
    rent hvitt papir (alt annet blir gul dither-stoey), flate mettede farger,
    og ingen tekst (panelet setter navnene selv, i sin egen font)."""
    birds = ", ".join(names)
    return (
        f"Compose a single antique ornithological book plate showing these "
        f"birds together, one of each: {birds}. "
        "Match the reference plates: hand-coloured 19th-century lithograph, "
        "fine engraved linework, naturalistic plumage and posture, birds "
        "perched on bare branches at different heights. "
        "Pure white paper background — no paper texture, no ageing, no stains, "
        "no border, no frame, no vignette. "
        "Bold saturated colours in flat areas, minimal soft shading. "
        "No text, no captions, no labels, no signature. "
        "Wide horizontal composition, the birds spread across the full width."
    )


def pick_species(birds: dict) -> list[dict]:
    """Dagens best belagte arter som faktisk HAR en plansje aa vise fram."""
    sure, _ = split_species(birds.get("species", []))
    picked = [s for s in sure if plate_path(s.get("scientific_name", ""))]
    return picked[:MAX_BIRDS]


def load_refs(species: list[dict]) -> list[Image.Image]:
    refs = []
    for s in species:
        p = plate_path(s["scientific_name"])
        img = Image.open(p).convert("RGB")
        img.thumbnail((REF_MAX, REF_MAX), Image.LANCZOS)
        refs.append(img)
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description="Komponer dagens hovedplansje.")
    ap.add_argument("--birds", default=os.path.join(HERE, "birds.json"))
    ap.add_argument("--aspect", default="16:9",
                    help="Gemini-format. 16:9 matcher hero-ramma (1104x620).")
    ap.add_argument("--full", action="store_true",
                    help="helsides bakgrunn (3:4) med tomme soner til teksten, "
                         "i stedet for en hero som fyller 16:9-ramma")
    ap.add_argument("--lag-gren", action="store_true",
                    help="lag (eller lag paa nytt) grenmalen plates/gren.png "
                         "og avslutt — kjoeres én gang, ikke daglig")
    ap.add_argument("--tries", type=int, default=int(os.environ.get("HERO_TRIES", "3")),
                    help="maks antall forsoek i --full; beste sonemaaling vinner")
    ap.add_argument("--uten-gren", action="store_true",
                    help="ignorer grenmalen selv om den finnes")
    ap.add_argument("--dry-run", action="store_true",
                    help="skriv prompten og hvilke plansjer som ville blitt brukt")
    args = ap.parse_args()

    if args.lag_gren:
        img = fit_to_panel(whiten(generate_image(GREN_PROMPT, aspect_ratio="3:4")))
        soner = zone_report(img)
        for navn, v in soner.items():
            print(f"  sone {navn:9s} {v['blekk']*100:5.1f} % blekk, "
                  f"verste baand {v['verst']*100:5.1f} %  "
                  f"{'ren' if v['ren'] else 'OPPTATT'}")
        os.makedirs(PLATES_DIR, exist_ok=True)
        img.save(GREN_PNG)
        print(f"OK: {GREN_PNG} ({img.width}x{img.height})")
        return 0

    birds = load_birds(args.birds)
    species = pick_species(birds)
    if not species:
        print("Ingen av dagens arter har en plansje ennaa — hopper over.",
              file=sys.stderr)
        return 1

    names = [f"{s['common_name']} ({s['scientific_name']})" for s in species]
    if args.full and args.aspect == "16:9":
        args.aspect = "3:4"          # helsides = hele panelet, ikke hero-ramma
    # Har vi en grenmal, bruker vi den: den styrer komposisjonen mye hardere
    # enn ord gjoer.
    bruk_gren = args.full and os.path.exists(GREN_PNG) and not args.uten_gren
    if args.full:
        prompt = build_branch_prompt(names) if bruk_gren else build_full_prompt(names)
    else:
        prompt = build_prompt(names)
    if bruk_gren:
        print(f"Mal: {os.path.basename(GREN_PNG)} (gren som foerste referanse)")
    print("Arter: " + ", ".join(
        norwegian_name(s["scientific_name"], s["common_name"]) for s in species))
    print(f"Forelegg: " + ", ".join(os.path.basename(plate_path(s["scientific_name"]))
                                    for s in species))
    print(f"Prompt: {prompt}")
    if args.dry_run:
        return 0

    refs = load_refs(species)
    if bruk_gren:
        mal = Image.open(GREN_PNG).convert("RGB")
        mal.thumbnail((REF_MAX, REF_MAX), Image.LANCZOS)
        refs.insert(0, mal)      # foerste referanse = malen

    if not args.full:
        img = whiten(generate_image(prompt, ref_images=refs,
                                    aspect_ratio=args.aspect))
    else:
        # Modellen er ustabil paa komposisjon: samme prompt ga 0,1 % blekk i
        # venstresonen i ett forsoek og 11,5 % i det neste. Vi tar derfor flere
        # forsoek og beholder det reneste -- og stopper med én gang alle soner
        # er rene, saa det vanligvis koster ett kall.
        best, best_soner, best_sum = None, None, None
        for forsoek in range(1, args.tries + 1):
            kandidat = fit_to_panel(whiten(
                generate_image(prompt, ref_images=refs, aspect_ratio=args.aspect)))
            soner = zone_report(kandidat)
            # Rangér paa det verste baandet, ikke snittet -- det er der
            # teksten faktisk faar problemer.
            sum_blekk = sum(v["verst"] for v in soner.values())
            status = " ".join(f"{n}={v['blekk']*100:.1f}%/verst {v['verst']*100:.1f}%"
                              for n, v in soner.items())
            print(f"  forsoek {forsoek}/{args.tries}: {status}")
            if best_sum is None or sum_blekk < best_sum:
                best, best_soner, best_sum = kandidat, soner, sum_blekk
            if all(v["ren"] for v in soner.values()):
                print("  alle soner rene — beholder denne")
                break
        img, forhaands_soner = best, best_soner

    os.makedirs(PLATES_DIR, exist_ok=True)
    png, meta_path = (BG_PNG, BG_JSON) if args.full else (HERO_PNG, HERO_JSON)
    img.save(png)

    # Sonene ble maalt paa det ferdige arket i loekka over -- samme geometri
    # som teksten faktisk havner i.
    soner = forhaands_soner if args.full else {}
    for navn, v in soner.items():
        merk = "ren" if v["ren"] else f"OPPTATT — teksten faar hvit pute"
        print(f"  sone {navn:9s} {v['blekk']*100:5.1f} % blekk, "
              f"verste baand {v['verst']*100:5.1f} %  {merk}")

    with open(meta_path, "w") as f:
        json.dump({
            "soner": soner,
            "date": birds.get("date") or datetime.date.today().isoformat(),
            "aspect": args.aspect,
            "species": [{"common_name": s["common_name"],
                         "scientific_name": s["scientific_name"],
                         "norsk": norwegian_name(s["scientific_name"],
                                                 s["common_name"])}
                        for s in species],
            "forelegg": [os.path.basename(plate_path(s["scientific_name"]))
                         for s in species],
        }, f, indent=2, ensure_ascii=False)

    print(f"OK: {png} ({img.width}x{img.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
