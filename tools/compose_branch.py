#!/usr/bin/env python3
"""
Fugleramme: sett dagens fugler paa den faste grenen — deterministisk.

Bakgrunn: vi proevde aa gi Gemini grenmalen som referanse og be den plassere
fuglene paa den. Modellen ignorerte malen, tegnet sin egen gren midt paa sida
og la 20,6 % blekk i tekstsonen. Komposisjon er ikke noe man overtaler en
modell til.

Her gjoer vi det motsatte: modellen tegner ÉN fugl om gangen, vi limer dem paa
grenen selv. Da er plasseringen et regnestykke, og teksten KAN ikke bli
overtegnet.

  1) plates/gren.png     — fast gren, laget én gang (compose_hero.py --lag-gren)
  2) plates/fugler/<art> — én fugl per art, 1:1 paa hvitt, laget én gang per art
  3) denne fila          — klipper bort det hvite og limer fuglene paa
                           festepunkter der grenen faktisk har en overflate

    venv/bin/python compose_branch.py --birds birds.json

Skriver plates/dagens-bakgrunn.png + .json, samme kontrakt som
compose_hero.py --full, saa render_daily_panel.py plukker den opp uendret.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bird_names import length_cm, norwegian_name  # noqa: E402
from generate_daily_image import generate_image  # noqa: E402
from prepare_plates import whiten              # noqa: E402
from compose_hero import (BG_JSON, BG_PNG, GREN_PNG, REF_MAX,  # noqa: E402
                          fit_to_panel, zone_report)
from render_daily_panel import (PLATES_DIR, load_birds, plate_path,  # noqa: E402
                                split_species)

FUGL_DIR = os.path.join(PLATES_DIR, "fugler")

# Settes fra --nye-fotpunkter i main().
NYE_FOTPUNKTER = False
PUSS_MODELL = None

# Festepunkter langs grenen: (x_senter, y_foetter, hoeyde, speilvendt).
# y-verdiene er lest ut av gren.png — der grenen faktisk har en overflate paa
# den x-en (se `--kart`). Rekkefoelgen er prioritert: dagens best belagte art
# faar foerste punkt.
#
# Alle punktene ligger UTENFOR tekstsonen (x < 576 og y < 1200): punkt A er
# under lista, resten til hoeyre for den. Det er den garantien hele denne
# fila finnes for.
# Rekkefoelgen er NEDENFRA OG OPP, ikke etter hvor godt belagt arten er:
# stoerste fugl faar den tykkeste greina nederst, minste faar tynnkvisten
# oeverst. En skjaere paa en topp-kvist ser feil ut uansett hvor sikker
# BirdNET var.
ANKRE = [
    (700, 1364, 205, False),   # nedre grein, midt paa — tykkest
    (350, 1400, 195, False),   # nedre grein til venstre, under artslista
    (900, 1034, 180, True),    # sidegrein opp mot stammen
    (1035, 830, 165, True),    # stammen mellom sidegreina og oevre gaffel
                               # (trukket inn fra 1090: spettmeisen laa
                               #  for taett i hoeyre kant)
    (1010, 596, 170, True),    # oevre gaffel
    (1000, 299, 155, False),   # toppen — tynnest
]

# Relativ stoerrelse. Rett proporsjon (lengde/lengde) gaar ikke: en graahegre
# paa 94 cm ved siden av en groennsisik paa 12 ville gjort sisiken til en
# flekk paa aatte piksler. Vi komprimerer med en eksponent -- forskjellene
# blir tydelige, men ingen art sprenger arket.
#
#   skala = (lengde / 21 cm) ** 0.6,  klemt til 0,55-1,60
#
# Med 21 cm (rødvingetrost) som midtpunkt gir det skjaere 1,56x og
# groennsisik 0,71x -- skjaera blir godt over dobbelt saa stor, som stemmer
# med hvordan de faktisk ser ut ved siden av hverandre.
REF_LENGDE_CM = float(os.environ.get("FUGL_REF_CM", "21"))
STOERRELSE_EKSP = float(os.environ.get("FUGL_EKSP", "0.6"))
STOERRELSE_MIN = float(os.environ.get("FUGL_MIN", "0.55"))
STOERRELSE_MAKS = float(os.environ.get("FUGL_MAKS", "1.60"))


def size_factor(scientific: str) -> float:
    rel = max(1.0, length_cm(scientific)) / REF_LENGDE_CM
    return min(STOERRELSE_MAKS, max(STOERRELSE_MIN, rel ** STOERRELSE_EKSP))

# Under dette snittnivaaet regnes pikselen som fugl, over som papir. Hard
# terskel med vilje: myke kanter blir lyse mellomtoner, og de finnes ikke i
# panelets palett — de ville blitt dither-stoey rundt hver fugl.
KUTT = float(os.environ.get("FUGL_KUTT", "242"))


def bird_prompt(common: str, sci: str) -> str:
    return (
        f"A single {common} ({sci}), hand-coloured 19th-century lithograph in "
        "the style of the reference plate: fine engraved linework, naturalistic "
        "plumage and markings. Side profile, perched upright, legs and feet "
        "clearly visible below the body. "
        "NO branch, no perch, no twig, no leaves, no ground, no shadow. "
        "The bird alone, isolated on a pure white background. "
        "No border, no frame, no text, no caption, no signature. "
        "The bird fills most of the frame."
    )


def ensure_bird(s: dict, force: bool = False) -> str | None:
    """Hent (eller lag) artens 1:1-fugl. Lages én gang og gjenbrukes hver dag
    arten dukker opp — det er derfor biblioteket vokser med arter, ikke dager."""
    sci = s["scientific_name"]
    dest = os.path.join(FUGL_DIR, sci.strip().lower().replace(" ", "-") + ".png")
    if os.path.exists(dest) and not force:
        return dest
    forelegg = plate_path(sci)
    if not forelegg:
        print(f"  {sci}: ingen plansje aa tegne etter — hopper over",
              file=sys.stderr)
        return None
    ref = Image.open(forelegg).convert("RGB")
    ref.thumbnail((REF_MAX, REF_MAX), Image.LANCZOS)
    img = whiten(generate_image(bird_prompt(s["common_name"], sci),
                                ref_images=[ref], aspect_ratio="1:1"))
    os.makedirs(FUGL_DIR, exist_ok=True)
    img.save(dest)
    print(f"  laget {os.path.basename(dest)} ({img.width}x{img.height})")
    return dest


# ----------------------------------------------------------------------
# Fotpunkt som metadata
# ----------------------------------------------------------------------
# Hver 1:1-fugl faar en sidecar <navn>.json med hvor foettene er i BILDET.
# Det er en engangsjobb per art -- fuglen tegnes én gang og gjenbrukes hver
# dag arten dukker opp, saa punktet skal bare bestemmes én gang.
#
# Hvorfor det trengs: sammensettingen sentrerte fuglen paa bildets bredde og
# la nederste piksel paa greina. Begge deler er feil for en fugl med hale --
# skjaera fikk foettene godt til side for festepunktet OG hengende i lufta.
# Med et fotpunkt legger vi den ene pikselen der den skal.

# gemini-2.5-flash er avviklet (404 fra APIet selv om den staar i
# modellista). gemini-3.5-flash er gjeldende raskmodell.
VISION_MODEL = os.environ.get("VISION_MODEL", "gemini-3.5-flash")

FOT_PROMPT = (
    "This image shows a single bird illustration on a plain white background. "
    "Find the point where the bird's feet meet the surface it stands on — the "
    "underside of the toes, midway between the two feet. If the feet are "
    "hidden, give the point directly below the body where they would be. "
    'Answer with ONLY a JSON object: {"x": <int>, "y": <int>} in coordinates '
    "normalized to 0-1000, where (0,0) is the top-left corner of the image and "
    "(1000,1000) the bottom-right. No explanation, no other text."
)


def _meta_path(bird_path: str) -> str:
    return os.path.splitext(bird_path)[0] + ".json"


def probe_feet(img: Image.Image) -> tuple[int, int] | None:
    """Spoer modellen hvor foettene er. Returnerer (x, y) i bildets piksler,
    eller None hvis svaret ikke lot seg lese."""
    try:
        from google import genai
        client = genai.Client()
        resp = client.models.generate_content(
            model=VISION_MODEL, contents=[FOT_PROMPT, img])
        tekst = (resp.text or "").strip()
        tekst = tekst.removeprefix("```json").removeprefix("```").removesuffix("```")
        d = json.loads(tekst.strip())
        x = int(round(float(d["x"]) / 1000 * img.width))
        y = int(round(float(d["y"]) / 1000 * img.height))
        if 0 <= x < img.width and 0 <= y < img.height:
            return x, y
    except Exception as e:  # noqa: BLE001
        print(f"    fotpunkt fra modellen feilet: {str(e)[:110]}", file=sys.stderr)
    return None


def foot_point(bird_path: str, fugl: Image.Image, force: bool = False) -> tuple[int, int]:
    """Fotpunktet i utsnittets piksler. Leses fra sidecar hvis den finnes,
    ellers bestemmes det én gang og lagres.

    Rekkefoelge: manuelt satt punkt > modellen > heuristikken. Et punkt som
    er skrevet inn for haand skal ALDRI overskrives av en ny kjoering."""
    meta_p = _meta_path(bird_path)
    if os.path.exists(meta_p) and not force:
        try:
            with open(meta_p) as f:
                m = json.load(f)
            fx, fy = m["fot"]
            return int(fx), int(fy)
        except Exception:  # noqa: BLE001
            pass
    if os.path.exists(meta_p) and force:
        try:
            with open(meta_p) as f:
                if json.load(f).get("kilde") == "manuell":
                    print("    (manuelt punkt — roeres ikke)")
                    with open(meta_p) as g:
                        fx, fy = json.load(g)["fot"]
                    return int(fx), int(fy)
        except Exception:  # noqa: BLE001
            pass

    punkt, kilde = probe_feet(fugl), "modell"
    if punkt is None:
        punkt, kilde = (fugl.width // 2, foot_row(fugl)), "heuristikk"
    with open(meta_p, "w") as f:
        json.dump({"fot": list(punkt), "kilde": kilde,
                   "bilde": [fugl.width, fugl.height]}, f, indent=2)
    print(f"    fotpunkt {punkt} ({kilde}) -> {os.path.basename(meta_p)}")
    return punkt


def foot_row(fugl: Image.Image) -> int:
    """Hvilken rad i utsnittet foettene staar paa.

    Ikke nederste rad i bildet -- det er halespissen. En skjaere har 25 cm
    hale som henger godt under greina, og aligner vi paa den, lander halen
    paa veden og fuglen svever over. Beina staar derimot omtrent under
    kroppens midte, saa vi ser bare i det midterste beltet av bredden og tar
    nederste blekk DER.

    Faller tilbake paa nederste rad hvis midtbeltet er tomt (en fugl i en
    stilling vi ikke har tenkt paa skal plasseres litt feil, ikke krasje)."""
    a = np.asarray(fugl)
    maske = a[:, :, 3] > 0 if a.shape[2] == 4 else a.mean(axis=2) < KUTT
    w = maske.shape[1]
    belte = maske[:, int(w * 0.32):int(w * 0.68)]
    rader = np.where(belte.any(axis=1))[0]
    if not len(rader):
        rader = np.where(maske.any(axis=1))[0]
    return int(rader[-1]) if len(rader) else maske.shape[0] - 1


def cutout(path: str) -> Image.Image:
    """Fjern det hvite papiret rundt fuglen og beskjaer til fuglen selv."""
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    maske = arr.mean(axis=2) < KUTT
    rows, cols = np.where(maske.any(axis=1))[0], np.where(maske.any(axis=0))[0]
    if not len(rows) or not len(cols):
        raise ValueError(f"{path} er helt hvit")
    rgba = np.dstack([arr.astype(np.uint8),
                      (maske * 255).astype(np.uint8)])
    ut = Image.fromarray(rgba, "RGBA")
    return ut.crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))


# Tekstfeltet som en hard sperre, med litt luft. Ingen fugl faar overlappe
# dette rektangelet -- det er poenget med hele den lokale sammensettingen, og
# det maa gjelde ogsaa naar en art er stor nok til aa vokse inn i det.
# Marginen er bevisst liten: sonemaalingen etterpaa er den egentlige vakten,
# og en for raus margin gir falske utslag. Rødvingetrosten paa den nedre
# venstregreina har toppen sin 5 px under sonen -- med 12 px margin ble den
# flyttet helt bort fra det hjoernet den var ment aa fylle.
SPERRE_X = int(0.48 * 1200) + 8       # 584
SPERRE_Y = int(0.75 * 1600)           # 1200


def perch_y(ark: Image.Image, x: int, y_hint: int, vindu: int = 150) -> int:
    """Finn grenens overflate ved x, naermest y_hint. Flytter vi en fugl
    sidelengs for aa komme klar av teksten, maa foettene finne ny bakke --
    ellers svever den."""
    a = np.asarray(ark.convert("RGB")).mean(axis=2)
    x = int(np.clip(x, 0, a.shape[1] - 1))
    y0, y1 = max(0, y_hint - vindu), min(a.shape[0], y_hint + vindu)
    ink = np.where(a[y0:y1, x] < 225)[0]
    if not len(ink):
        return y_hint
    # toppen av det segmentet som ligger naermest y_hint
    seg = np.split(ink, np.where(np.diff(ink) > 12)[0] + 1)
    topper = [y0 + int(g[0]) for g in seg if len(g) > 3]
    return min(topper, key=lambda t: abs(t - y_hint)) if topper else y_hint


# Hvor mye to fugler faar overlappe. Litt er helt greit -- pussetrinnet
# fletter dem pent sammen, og en flokk paa samme grein SKAL staa taett. Men
# to store fugler paa naesten samme punkt (kattugla landet oppaa skjaera da
# tekstsperren dyttet begge mot hoeyre) blir bare rot.
MAKS_OVERLAPP = float(os.environ.get("FUGL_OVERLAPP", "0.22"))


def _overlapp(a: tuple, b: tuple) -> float:
    """Andel av det MINSTE rektangelet som dekkes av det andre."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    bx = max(0, min(ax1, bx1) - max(ax0, bx0))
    by = max(0, min(ay1, by1) - max(ay0, by0))
    if not (bx and by):
        return 0.0
    minste = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
    return (bx * by) / minste if minste else 1.0


def compose(species: list[dict]) -> tuple[Image.Image, list[dict]]:
    ark = Image.open(GREN_PNG).convert("RGB")
    plassert = []
    # Stoerste art nederst paa den tykkeste greina, minste oeverst.
    etter_stoerrelse = sorted(species,
                              key=lambda s: -length_cm(s.get("scientific_name", "")))
    ledige = list(ANKRE)
    opptatt: list[tuple] = []
    for s in etter_stoerrelse:
        if not ledige:
            break
        sti = ensure_bird(s)
        if not sti:
            continue
        sci = s["scientific_name"]
        print(f"  {norwegian_name(sci, s['common_name']):16s} "
              f"{length_cm(sci):3.0f} cm -> {size_factor(sci):.2f}x")
        raa = cutout(sti)
        # Fotpunktet maales paa UTSNITTET (samme utsnitt hver gang, saa
        # koordinatene holder). Modellen ser bildet paa hvit bunn.
        paa_hvitt = Image.new("RGB", raa.size, (255, 255, 255))
        paa_hvitt.paste(raa, (0, 0), raa)
        raa_fot = foot_point(sti, paa_hvitt, force=NYE_FOTPUNKTER)

        # Proev ankrene i tur og orden og ta det foerste der fuglen faar staa
        # i fred. Uten dette havnet kattugla oppaa skjaera: begge ble dyttet
        # mot hoeyre av tekstsperren og endte paa samme punkt.
        valgt = None
        for anker in ledige:
            ax, ay, ah, speil = anker
            h = round(ah * size_factor(sci))
            fugl = raa.resize((max(1, round(raa.width * h / raa.height)), h),
                              Image.LANCZOS)
            sk = h / raa.height
            fx, fy = round(raa_fot[0] * sk), round(raa_fot[1] * sk)
            if speil:
                fugl = fugl.transpose(Image.FLIP_LEFT_RIGHT)
                fx = fugl.width - fx       # fotpunktet speiles med bildet
            x, y = ax, perch_y(ark, ax, ay)   # snap til veden

            # Kom klar av tekstfeltet. Kantene regnes fra FOTPUNKTET, ikke fra
            # bildets midte: det er der fuglen faktisk kommer til aa staa.
            flyttet = False
            if (x - fx) < SPERRE_X and (y - fy) < SPERRE_Y:
                x = SPERRE_X + fx + 8
                y = perch_y(ark, x, y)
                flyttet = True
                if (x - fx + fugl.width) > 1180:
                    ny_h = max(90, round(h * (1180 - SPERRE_X) / fugl.width))
                    sk2 = ny_h / fugl.height
                    fugl = fugl.resize((round(fugl.width * sk2), ny_h), Image.LANCZOS)
                    fx, fy = round(fx * sk2), round(fy * sk2)
                    x = SPERRE_X + fx + 8
                    y = perch_y(ark, x, y)

            boks = (x - fx, y - fy + 4, x - fx + fugl.width, y - fy + 4 + fugl.height)
            if any(_overlapp(boks, b) > MAKS_OVERLAPP for b in opptatt):
                continue                  # opptatt plass — proev neste anker
            valgt = (anker, fugl, x, y, fx, fy, boks, flyttet)
            break

        if valgt is None:
            print("      (fant ingen ledig plass — hopper over)")
            continue
        anker, fugl, x, y, fx, fy, boks, flyttet = valgt
        ledige.remove(anker)
        opptatt.append(boks)
        print(f"      {fugl.height} px paa ({x}, {y})"
              + ("  — flyttet klar av teksten" if flyttet else ""))

        # Fotpunktet legges paa greinas overflate, med fire piksler overlapp
        # saa klørne ser ut til aa gripe. Hale og vingespisser faar henge
        # under greina, som de skal.
        ark.paste(fugl, (x - fx, y - fy + 4), fugl)
        plassert.append({**s, "_anker": [x, y, fugl.height]})
    return ark, plassert


# Den lokale sammensettingen gir riktig PLASSERING, men fuglene ser limt paa
# ut: foettene moeter grenen uten aa gripe den, og kroppsvinkelen foelger ikke
# kvisten. Her sendes hele arket tilbake til Gemini med én eneste oppgave --
# fikse kontaktpunktene. Alt annet skal staa.
#
# Risikoen er at modellen tegner om mer enn den blir bedt om. Derfor maales
# sonene paa nytt etterpaa, og et forsoek som skitner til tekstfeltet blir
# FORKASTET -- da beholder vi den lokale versjonen. Garantien ligger i
# maalingen, ikke i tilliten.
PUSS_PROMPT = (
    "This is an antique bird plate: birds standing on a bare branch, on white "
    "paper. Each bird is already in the right place, at the right size. "
    "Your job is to make every bird look like it is genuinely PERCHED on the "
    "wood it stands on, not pasted on top of it. "
    "You MAY: rotate or tilt a bird a little so its posture follows the angle "
    "of its branch; redraw its legs, toes and claws so they wrap around and "
    "grip the wood; adjust how the tail hangs and how the body balances over "
    "the feet; nudge a bird a few pixels so the feet meet the branch exactly; "
    "and redraw the small area of branch where the feet touch. "
    "You MUST NOT: change any bird's size, move a bird to a different branch "
    "or a different part of the page, change which species is where, add or "
    "remove birds, branches, twigs, leaves, text, captions or shadows. "
    "Leave the empty white area alone — the left 48% of the width from the top "
    "down to 75% of the height must stay completely empty white paper. "
    "Keep the fine engraved linework and the hand-coloured lithograph style, "
    "and keep the pure white background."
)

# Foreleggets oppløsning: hoeyere enn REF_MAX ellers i prosjektet, fordi
# modellen her skal GJENSKAPE arket, ikke bare hente stil fra det.
PUSS_REF = int(os.environ.get("PUSS_REF", "1200"))


def refine(ark: Image.Image, tries: int) -> tuple[Image.Image, dict, bool]:
    """Send arket tilbake for aa faa foettene til aa gripe. Returnerer
    (bilde, soner, ble_pusset). Faller tilbake paa originalen hvis ingen
    forsoek holder tekstsonen ren."""
    ref = ark.copy()
    ref.thumbnail((PUSS_REF, PUSS_REF), Image.LANCZOS)
    for forsoek in range(1, tries + 1):
        try:
            kandidat = fit_to_panel(whiten(
                generate_image(PUSS_PROMPT, ref_images=[ref], aspect_ratio="3:4",
                               model=PUSS_MODELL)))
        except Exception as e:  # noqa: BLE001
            print(f"  puss {forsoek}/{tries} feilet: {str(e)[:120]}", file=sys.stderr)
            continue
        soner = zone_report(kandidat)
        status = " ".join(f"{n}={v['blekk']*100:.1f}%/verst {v['verst']*100:.1f}%"
                          for n, v in soner.items())
        ren = soner.get("venstre", {}).get("ren", False)
        print(f"  puss {forsoek}/{tries}: {status}  "
              f"{'godtatt' if ren else 'FORKASTET — rotet i tekstsonen'}")
        if ren:
            return kandidat, soner, True
    print("  ingen pusseforsoek holdt tekstsonen ren — beholder den lokale "
          "sammensettingen", file=sys.stderr)
    return ark, zone_report(ark), False


def sjekk_foetter(ut: str) -> None:
    """Kontaktark: hver fugl med et kryss der fotpunktet er satt.

    Poenget er at et menneske skal kunne se over alle artene paa én gang og
    si fra om noen er feil. Er den det, rett `fot` i artens .json og sett
    "kilde": "manuell" -- da roerer ingen senere kjoering den igjen."""
    from PIL import ImageDraw
    filer = sorted(f for f in os.listdir(FUGL_DIR)
                   if f.lower().endswith(".png")) if os.path.isdir(FUGL_DIR) else []
    if not filer:
        print("Ingen fugler aa sjekke.", file=sys.stderr)
        return
    RUTE, KOL = 300, 4
    rader = (len(filer) + KOL - 1) // KOL
    ark = Image.new("RGB", (KOL * RUTE, rader * (RUTE + 26)), (255, 255, 255))
    tegn = ImageDraw.Draw(ark)
    for i, navn in enumerate(filer):
        sti = os.path.join(FUGL_DIR, navn)
        fugl = cutout(sti)
        paa_hvitt = Image.new("RGB", fugl.size, (255, 255, 255))
        paa_hvitt.paste(fugl, (0, 0), fugl)
        fx, fy = foot_point(sti, paa_hvitt)
        sk = min(RUTE / fugl.width, RUTE / fugl.height)
        liten = paa_hvitt.resize((round(fugl.width * sk), round(fugl.height * sk)))
        ox, oy = (i % KOL) * RUTE, (i // KOL) * (RUTE + 26)
        ark.paste(liten, (ox, oy))
        cx, cy = ox + round(fx * sk), oy + round(fy * sk)
        tegn.line([(cx - 16, cy), (cx + 16, cy)], fill=(255, 0, 0), width=3)
        tegn.line([(cx, cy - 16), (cx, cy + 16)], fill=(255, 0, 0), width=3)
        kilde = ""
        mp = _meta_path(sti)
        if os.path.exists(mp):
            try:
                kilde = json.load(open(mp)).get("kilde", "")
            except Exception:  # noqa: BLE001
                pass
        tegn.text((ox + 4, oy + RUTE + 4),
                  f"{os.path.splitext(navn)[0]}  [{kilde}]", fill=(0, 0, 0))
        tegn.rectangle([ox, oy, ox + RUTE - 1, oy + RUTE - 1], outline=(200, 200, 200))
    ark.save(ut)
    print(f"OK: {ut} — {len(filer)} fugler med fotpunkt")


def kart() -> None:
    """Skriv ut hvor grenen har overflate, som hjelp til aa sette ANKRE."""
    a = np.asarray(Image.open(GREN_PNG).convert("RGB")).mean(axis=2)
    for x in range(100, 1200, 100):
        ink = np.where(a[:, x] < 225)[0]
        if not len(ink):
            print(f"  x={x:4d}  tomt")
            continue
        seg = np.split(ink, np.where(np.diff(ink) > 12)[0] + 1)
        print(f"  x={x:4d}  overflater y={[int(s[0]) for s in seg if len(s) > 4]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sett dagens fugler paa grenen.")
    ap.add_argument("--birds", default=os.path.join(HERE, "birds.json"))
    ap.add_argument("--nye-fotpunkter", action="store_true",
                    help="bestem fotpunktene paa nytt (manuelt satte roeres ikke)")
    # gemini-3-pro-image gjoer pussetrinnet merkbart bedre enn
    # gemini-2.5-flash-image: taerne griper faktisk rundt veden, og
    # streken holder seg renere. Satt som standard KUN her -- det daglige
    # AI-bildet bruker fortsatt sin egen modell til noen bestemmer noe annet.
    ap.add_argument("--puss-modell",
                    default=os.environ.get("PUSS_MODELL", "gemini-3-pro-image"),
                    help="bildemodell for pussetrinnet")
    ap.add_argument("--sjekk-foetter", metavar="UT.PNG",
                    help="kontaktark med kryss der fotpunktene er satt")
    ap.add_argument("--kart", action="store_true",
                    help="vis hvor grenen har overflate (til aa sette ANKRE)")
    ap.add_argument("--puss", type=int, default=int(os.environ.get("PUSS_TRIES", "2")),
                    help="antall forsoek paa aa la Gemini feste foettene til "
                         "grenen (0 = hopp over)")
    ap.add_argument("--bare-fugler", action="store_true",
                    help="lag manglende 1:1-fugler og stopp")
    args = ap.parse_args()

    global NYE_FOTPUNKTER, PUSS_MODELL
    NYE_FOTPUNKTER, PUSS_MODELL = args.nye_fotpunkter, args.puss_modell

    if args.sjekk_foetter:
        sjekk_foetter(args.sjekk_foetter)
        return 0
    if args.kart:
        kart()
        return 0
    if not os.path.exists(GREN_PNG):
        raise SystemExit(f"Mangler {GREN_PNG} — kjoer compose_hero.py --lag-gren foerst.")

    birds = load_birds(args.birds)
    sure, _ = split_species(birds.get("species", []), len(ANKRE))
    species = [s for s in sure if plate_path(s.get("scientific_name", ""))]
    if not species:
        print("Ingen av dagens arter har en plansje ennaa.", file=sys.stderr)
        return 1
    print("Arter: " + ", ".join(
        norwegian_name(s["scientific_name"], s["common_name"]) for s in species))

    if args.bare_fugler:
        for s in species:
            ensure_bird(s)
        return 0

    ark, plassert = compose(species)
    ark = fit_to_panel(ark)
    pusset = False
    if args.puss > 0:
        ark, soner, pusset = refine(ark, args.puss)
    else:
        soner = zone_report(ark)
    for navn, v in soner.items():
        print(f"  sone {navn:9s} {v['blekk']*100:5.1f} % blekk, "
              f"verste baand {v['verst']*100:5.1f} %  "
              f"{'ren' if v['ren'] else 'OPPTATT'}")

    ark.save(BG_PNG)
    with open(BG_JSON, "w") as f:
        json.dump({
            "soner": soner,
            "date": birds.get("date") or datetime.date.today().isoformat(),
            "metode": ("gren + 1:1-fugler, satt sammen lokalt"
                       + (" og pusset av Gemini" if pusset else "")),
            "species": [{"common_name": s["common_name"],
                         "scientific_name": s["scientific_name"],
                         "norsk": norwegian_name(s["scientific_name"],
                                                 s["common_name"])}
                        for s in plassert],
        }, f, indent=2, ensure_ascii=False)
    print(f"OK: {BG_PNG} — {len(plassert)} fugler paa grenen"
          + (", pusset" if pusset else ", upusset"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
