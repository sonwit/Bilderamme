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

from bird_names import habitat, length_cm, norwegian_name  # noqa: E402
from generate_daily_image import generate_image  # noqa: E402
from prepare_plates import whiten              # noqa: E402
from compose_hero import (BG_JSON, BG_PNG, REF_MAX,  # noqa: E402
                          fit_to_panel, zone_report)
from render_daily_panel import (OVERLAY_ROWS, PLATES_DIR,  # noqa: E402
                                get_weather, load_birds, plate_path,
                                split_species)

FUGL_DIR = os.path.join(PLATES_DIR, "fugler")

# Settes fra --nye-fotpunkter i main().
NYE_FOTPUNKTER = False
RETUSJ_MODELL = None
# Latinske navn som skal tegnes paa nytt selv om fila finnes
# (--ny-fugl). Bildene er tilfeldige, saa av og til vil man bare ha
# en ny variant uten aa slette filer for haand.
NY_FUGL: set = set()

# Festepunkter langs grenen: (x_senter, y_foetter, hoeyde, speilvendt).
# y-verdiene er lest ut av gren.png — der grenen faktisk har en overflate paa
# den x-en (se `--kart`). Rekkefoelgen er prioritert: dagens best belagte art
# faar foerste punkt.
#
# Alle punktene ligger UTENFOR tekstsonen (x < 576 og y < 1200): punkt A er
# under lista, resten til hoeyre for den. Det er den garantien hele denne
# fila finnes for.
# ----------------------------------------------------------------------
# Maler
# ----------------------------------------------------------------------
# En mal er ett habitat: et bakgrunnsbilde og en liste plasser aa sette fugler
# paa. Den ligger som JSON i plates/maler/, saa en ny mal er en fil og ikke en
# kodeendring.
#
# Plass-typene svarer til hva fuglen faktisk gjoer:
#   "gren"   sitter paa ved -- y snappes til greinas overflate, fotpunkt brukes
#   "bakke"  staar paa mark/siv -- y er bakkelinja, ingen snapping
#   "luft"   flyr -- ingen fotpunkt, fuglen sentreres paa punktet, og den
#            tegnes i FLYGENDE positur (egen 1:1-fil per art)
#
# Plassene staar NEDENFRA OG OPP for gren/bakke: stoerste fugl faar den
# tykkeste greina nederst. En skjaere paa en topp-kvist ser feil ut uansett
# hvor sikker BirdNET var.
MAL_DIR = os.path.join(PLATES_DIR, "maler")

# Hvilke arter en plass tar imot. En skjaere kan ikke staa i siv, og en
# myrrikse hoerer ikke hjemme paa en kvist -- men ALLE fugler kan fly, saa
# luftplassene tar imot hvem som helst. Det er ogsaa det som gjoer at
# myrmalen faar liv en dag bare et par vaatmarksarter er hoert: resten
# flyr over.
PLASS_TAR_IMOT = {
    "gren": {"tre"},
    "bakke": {"vaatmark", "bakke"},
    "luft": {"tre", "vaatmark", "bakke", "luft"},
}


def passer(plass: dict, sci: str) -> bool:
    return habitat(sci) in PLASS_TAR_IMOT.get(plass.get("type", "gren"), set())


def velg_arter(kandidater: list[dict], mal: dict) -> list[dict]:
    """Fyll plassene med de sikreste artene hver enkelt plass kan ta imot.

    Kandidatene ligger allerede med sikreste foerst. Vi gaar plass for plass
    og gir hver den beste arten som faktisk kan staa der.

    Det gamle grepet -- malens habitat foerst, resten etterpaa, kutt ved antall
    plasser -- saa paa malen under ett, og da ble myrriksa aldri tegnet. Den er
    nesten daglig blant de sikreste artene, men grenmalen har bare
    gren-plasser, og de tar bare trefugler: seks trefugler fylte lista foer
    myrriksa kom til orde. Ser vi paa hver plass for seg, tar luftplassen --
    som staar sist -- den beste som er igjen naar greinene er fulle."""
    igjen = list(kandidater)
    valgt = []
    for plass in mal["plasser"]:
        for s in igjen:
            if passer(plass, s.get("scientific_name", "")):
                valgt.append(s)
                igjen.remove(s)
                break
    return valgt


def last_maler() -> list[dict]:
    """Alle maler, med arv loest opp.

    En sesongvariant («samme gren, men med knopper») arver plassene fra
    grunnmalen sin. Det er hele poenget med arven: varianten tegnes OPPAA den
    samme greina, saa festepunktene stemmer fortsatt og trenger ikke maales
    paa nytt for hver aarstid."""
    if not os.path.isdir(MAL_DIR):
        return []
    raa = {}
    for f in sorted(os.listdir(MAL_DIR)):
        if f.endswith(".json"):
            with open(os.path.join(MAL_DIR, f)) as fh:
                m = json.load(fh)
                raa[m["navn"]] = m
    # Arven loeses REKURSIVT: snoemalen arver fra grankvisten, som selv arver
    # fra grunngreina. Én runde gjennom lista holdt bare saa lenge filnavnene
    # tilfeldigvis kom i riktig rekkefoelge alfabetisk.
    def loes(m, sett=None):
        sett = sett or set()
        navn = m["navn"]
        if navn in sett:
            raise SystemExit(f"Sirkulaer arv i malene rundt {navn}")
        base = raa.get(m.get("basert_paa"))
        if base:
            loes(base, sett | {navn})
            if not m.get("plasser"):
                m["plasser"] = base["plasser"]
            m.setdefault("habitat", base.get("habitat", []))
        return m

    for m in list(raa.values()):
        loes(m)
    # Etter at arven er loest: en plass kan begrense seg til bestemte maler.
    # Den lille plassen paa nedre grein er ren luft paa bjoerka og den bare
    # greina -- 2 % blekk -- men ligger midt inne i barmassen paa grankvisten,
    # der samme rute er 58 % dekket. Ett skjelett, men ikke hver plass er
    # brukbar i hver aarstid.
    for m in raa.values():
        m["plasser"] = [p for p in m.get("plasser", [])
                        if not p.get("bare_i") or m["navn"] in p["bare_i"]]
    return list(raa.values())


def velg_mal(species: list[dict], maaned: int, tvungen: str | None = None,
             vaersymbol: str = "") -> dict:
    """Malen som passer dagens fugler best.

    Poeng = hvor mange av artene som hoerer hjemme i malens habitat. Er ingen
    mal bedre enn grenmalen, vinner den -- den er standarden fordi de aller
    fleste hagefuglene sitter paa en grein. Maaneds-filteret hindrer at
    snoemalen dukker opp i juli."""
    maler = [m for m in last_maler()
             if maaned in m.get("maaneder", list(range(1, 13)))
             # En mal kan kreve bestemt vaer. Snoemalen skal ikke dukke opp
             # paa barmark i november bare fordi maaneden stemmer.
             and (not m.get("vaer") or vaersymbol in m["vaer"])]
    if not maler:
        raise SystemExit(f"Ingen maler i {MAL_DIR}")
    if tvungen:
        # Tvungen mal gaar utenom baade maaneds- og vaerfilteret. Uten det kan
        # man ikke se paa hoestmalen i august, som er nettopp naar man vil
        # sjekke at den ser riktig ut.
        for m in last_maler():
            if m["navn"] == tvungen:
                return m
        raise SystemExit(f"Fant ingen mal som heter {tvungen} i {MAL_DIR}")

    def poeng(m):
        h = set(m.get("habitat", []))
        treff = sum(1 for s in species if habitat(s.get("scientific_name", "")) in h)
        # En mal som ogsaa treffer vaeret gaar foran en som bare treffer
        # habitatet -- snoedekt gran naar det faktisk snoer.
        vaer = 1 if (m.get("vaer") and vaersymbol in m["vaer"]) else 0
        # Sesongvarianter foran den noeytrale grunnmalen: staar det en variant
        # for akkurat denne maaneden, er den mer presis enn aarsrund-greina.
        sesong = 1 if len(m.get("maaneder", [])) < 12 else 0
        return (treff, vaer, sesong, 1 if m["navn"] == "gren" else 0)

    beste = max(maler, key=poeng)
    for m in sorted(maler, key=poeng, reverse=True):
        h = set(m.get("habitat", []))
        n = sum(1 for s in species if habitat(s.get("scientific_name", "")) in h)
        print(f"  mal {m['navn']:8s} {n} av {len(species)} arter i habitat"
              + ("   <- valgt" if m is beste else ""))
    return beste


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


# Skalaen skal si hvor mye papir fuglen tar, ikke hvor hoey den blir.
# Plansjene har vidt forskjellige proporsjoner: skjaera er bredere enn hoey
# (halen er halve fuglen), kattugla er hoeyere enn bred. Skalerte vi paa
# hoeyde alene fikk skjaera dobbel bredde paa kjoepet og dekket 139 000
# piksler mot uglas 44 000 -- tre ganger saa mye papir til en fugl som veier
# under halvparten. Vi sikter derfor mot et kvadrat med side ah*skala og
# regner hoeyden ut fra plansjens eget sideforhold.
#
# Klemt fordi ytterpunktene er plansjer, ikke fugler: en flygende fugl med
# utslaatte vinger er tre ganger saa bred som hoey, og uten tak ville den
# krympet til en strek.
ASPEKT_MIN = float(os.environ.get("FUGL_ASPEKT_MIN", "0.72"))
ASPEKT_MAKS = float(os.environ.get("FUGL_ASPEKT_MAKS", "1.40"))


def scale_height(ah: int, scientific: str, raa: Image.Image) -> int:
    side = ah * size_factor(scientific)
    aspekt = min(ASPEKT_MAKS, max(ASPEKT_MIN, raa.width / raa.height))
    return max(1, round(side / (aspekt ** 0.5)))


# Under dette snittnivaaet regnes pikselen som fugl, over som papir. Hard
# terskel med vilje: myke kanter blir lyse mellomtoner, og de finnes ikke i
# panelets palett — de ville blitt dither-stoey rundt hver fugl.
KUTT = float(os.environ.get("FUGL_KUTT", "242"))


def bird_prompt(common: str, sci: str, positur: str = "sittende") -> str:
    felles = (
        "hand-coloured 19th-century lithograph in the style of the reference "
        "plate: fine engraved linework, naturalistic plumage and markings. "
        "NO branch, no perch, no twig, no leaves, no ground, no shadow. "
        "The bird alone, isolated on a pure white background. "
        "No border, no frame, no text, no caption, no signature. "
        "The bird fills most of the frame."
    )
    if positur == "flyvende":
        return (f"A single {common} ({sci}) in flight, {felles} "
                "Side view, wings fully spread, body level, as in a plate "
                "showing the bird on the wing. Feet tucked, not extended.")
    return (f"A single {common} ({sci}), {felles} "
            "Side profile, perched upright, legs and feet clearly visible "
            "below the body.")


def ensure_bird(s: dict, positur: str = "sittende",
                force: bool = False) -> str | None:
    """Hent (eller lag) artens 1:1-fugl. Lages én gang og gjenbrukes hver dag
    arten dukker opp — det er derfor biblioteket vokser med arter, ikke dager."""
    sci = s["scientific_name"]
    navn = sci.strip().lower().replace(" ", "-")
    if positur == "flyvende":
        navn += "-flyvende"
    dest = os.path.join(FUGL_DIR, navn + ".png")
    if sci.strip().lower() in NY_FUGL:
        force = True
    if os.path.exists(dest) and not force:
        return dest
    forelegg = plate_path(sci)
    if not forelegg:
        print(f"  {sci}: ingen plansje aa tegne etter — hopper over",
              file=sys.stderr)
        return None
    ref = Image.open(forelegg).convert("RGB")
    ref.thumbnail((REF_MAX, REF_MAX), Image.LANCZOS)
    img = whiten(generate_image(bird_prompt(s["common_name"], sci, positur),
                                ref_images=[ref], aspect_ratio="1:1"))
    os.makedirs(FUGL_DIR, exist_ok=True)
    img.save(dest)
    stram_til_fuglen(dest)
    return dest


def stram_til_fuglen(sti: str) -> None:
    """Klipp den lagrede fila ned til fuglen selv, paa hvit bunn.

    Modellen tegner paa et 1024x1024-ark og legger av og til igjen en svak
    strek eller et par prikker ute i hjoernet. Skaleringen sikter paa BOKSEN,
    ikke paa fuglen, saa en slik flekk krymper fuglen paa arket: kjoettmeisas
    utsnitt var 907x854 der bare 9,3 % var fugl, og paa sida ble den halve
    stoerrelsen den skulle hatt ved siden av en spettmeis paa samme 14 cm.

    cutout() kaster loese flekker uansett naar bildet leses, men da ligger
    feilen fortsatt i fila og dukker opp igjen neste gang noen ser paa den.
    Her skrives fila slik den skal vaere med én gang. Hvit bunn, ikke
    gjennomsiktig: cutout leser med convert(\"RGB\"), og en alfakanal ville
    blitt svart."""
    tett = cutout(sti)
    paa_hvitt = Image.new("RGB", tett.size, (255, 255, 255))
    paa_hvitt.paste(tett, (0, 0), tett)
    paa_hvitt.save(sti)
    andel = (np.asarray(tett.convert("RGBA"))[:, :, 3] > 0).mean()
    merknad = "" if andel >= 0.15 else "   <- mistenkelig tynn, se paa den"
    print(f"  laget {os.path.basename(sti)} ({tett.width}x{tett.height}, "
          f"{andel*100:.0f} % fugl){merknad}")


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
    # En flygende fugl har ingen foetter aa sette ned -- luftplassene sentrerer
    # paa kroppen. Da er det bortkastet aa bruke et modellkall paa aa lete
    # etter taer, og et lagret punkt ville bare vaert forvirrende.
    if os.path.basename(bird_path).endswith("-flyvende.png"):
        return fugl.width // 2, fugl.height // 2

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


# En loes flekk mindre enn denne andelen av den stoerste sammenhengende
# klatten regnes som stoey og kastes. En virkelig loesrevet fugledel -- en fot,
# en vingespiss -- er aldri saa liten; stoeyen er noen faa piksler.
FLEKK = float(os.environ.get("FUGL_FLEKK", "0.01"))


def uten_flekker(maske: np.ndarray) -> np.ndarray:
    """Behold den stoerste klatten og alt som er en reell del av fuglen."""
    from scipy import ndimage

    merket, n = ndimage.label(maske)
    if n <= 1:
        return maske
    stoerrelser = ndimage.sum(maske, merket, range(1, n + 1))
    grense = stoerrelser.max() * FLEKK
    beholdes = np.zeros(n + 1, dtype=bool)
    beholdes[1:] = stoerrelser >= grense
    return beholdes[merket]


def cutout(path: str) -> Image.Image:
    """Fjern papiret rundt fuglen og beskjaer til fuglen selv.

    Terskel alene gaar ikke: den fjerner ALT som er lyst nok, ogsaa hvitt
    MIDT i fuglen. Skjaera mistet buken og skulderflekken sin og ble
    gjennomsiktig der. Bakgrunn er ikke «lyst», det er «lyst og ikke omsluttet
    av fugl».

    binary_fill_holes fyller nettopp de hullene i motivmasken som ikke henger
    sammen med kanten -- altsaa hvitt som er innelukket av fjaerdrakt. (PIL sin
    ImageDraw.floodfill ble proevd foerst og fylte ingenting i denne
    Pillow-versjonen: 0 % av bakgrunnen ble merket.)

    Loese flekker kastes foer beskjaeringen. Modellen legger av og til igjen
    en svak strek eller et par prikker ute i hjoernet av arket, og siden
    skaleringen sikter paa BOKSEN, ikke paa fuglen, blir fuglen tilsvarende
    mindre: kjoettmeisas utsnitt var 907x854 der bare 9,3 % var fugl, mot
    spettmeisas 452x445 med 40,4 %. Paa arket ble kjoettmeisa dermed halve
    stoerrelsen den skulle hatt, enda begge er 14 cm."""
    from scipy import ndimage

    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    motiv = arr.mean(axis=2) < KUTT
    synlig = ndimage.binary_fill_holes(motiv)
    synlig = uten_flekker(synlig)

    rows, cols = np.where(synlig.any(axis=1))[0], np.where(synlig.any(axis=0))[0]
    if not len(rows) or not len(cols):
        raise ValueError(f"{path} er helt hvit")
    rgba = np.dstack([arr.astype(np.uint8), (synlig * 255).astype(np.uint8)])
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


# Hvor mye to fugler faar overlappe. Litt er helt greit -- retusjtrinnet
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


def compose(species: list[dict], mal: dict) -> tuple[Image.Image, list[dict]]:
    ark = Image.open(os.path.join(MAL_DIR, mal["bilde"])).convert("RGB")
    plassert = []
    # Stoerste art nederst paa den tykkeste greina, minste oeverst.
    etter_stoerrelse = sorted(species,
                              key=lambda s: -length_cm(s.get("scientific_name", "")))
    ledige = list(mal["plasser"])
    opptatt: list[tuple] = []
    for s in etter_stoerrelse:
        if not ledige:
            break
        sci = s["scientific_name"]
        print(f"  {norwegian_name(sci, s['common_name']):16s} "
              f"{length_cm(sci):3.0f} cm -> {size_factor(sci):.2f}x  "
              f"[{habitat(sci)}]")

        # Proev plassene i tur og orden og ta den foerste der fuglen faar staa
        # i fred. Uten dette havnet kattugla oppaa skjaera: begge ble dyttet
        # mot hoeyre av tekstsperren og endte paa samme punkt.
        valgt = None
        for plass in ledige:
            typ = plass.get("type", "gren")
            if not passer(plass, sci):
                continue
            positur = "flyvende" if typ == "luft" else "sittende"
            sti = ensure_bird(s, positur, force=False)
            if not sti:
                break                      # ingen plansje aa tegne etter
            raa = cutout(sti)
            paa_hvitt = Image.new("RGB", raa.size, (255, 255, 255))
            paa_hvitt.paste(raa, (0, 0), raa)

            ax, ay, ah = plass["x"], plass["y"], plass["h"]
            h = scale_height(ah, sci, raa)
            fugl = raa.resize((max(1, round(raa.width * h / raa.height)), h),
                              Image.LANCZOS)
            sk = h / raa.height
            if typ == "luft":
                # En flygende fugl har ingen foetter aa sette ned. Punktet er
                # midt paa kroppen, og den skal ikke snappe til noe.
                fx, fy = fugl.width // 2, fugl.height // 2
            else:
                rf = foot_point(sti, paa_hvitt, force=NYE_FOTPUNKTER)
                fx, fy = round(rf[0] * sk), round(rf[1] * sk)
            if plass.get("speil"):
                fugl = fugl.transpose(Image.FLIP_LEFT_RIGHT)
                fx = fugl.width - fx       # fotpunktet speiles med bildet

            # Bare gren-plasser snapper til ved. Bakke- og luftplasser er
            # satt der de skal vaere.
            x, y = ax, perch_y(ark, ax, ay) if typ == "gren" else ay

            # Kom klar av tekstfeltet. Kantene regnes fra FESTEPUNKTET, ikke
            # fra bildets midte: det er der fuglen faktisk kommer til aa staa.
            flyttet = False
            if (x - fx) < SPERRE_X and (y - fy) < SPERRE_Y:
                x = SPERRE_X + fx + 8
                if typ == "gren":
                    y = perch_y(ark, x, y)
                flyttet = True
                if (x - fx + fugl.width) > 1180:
                    ny_h = max(90, round(h * (1180 - SPERRE_X) / fugl.width))
                    sk2 = ny_h / fugl.height
                    fugl = fugl.resize((round(fugl.width * sk2), ny_h), Image.LANCZOS)
                    fx, fy = round(fx * sk2), round(fy * sk2)
                    x = SPERRE_X + fx + 8
                    if typ == "gren":
                        y = perch_y(ark, x, y)

            boks = (x - fx, y - fy + 4, x - fx + fugl.width, y - fy + 4 + fugl.height)
            # Plassen kan tillate mer overlapp enn standarden. Paa myrkanten
            # er det bare ett baelte der en bakkefugl faar kroppen mot lyst
            # papir, saa de to vaderne maa staa taett -- slik de faktisk gjoer.
            tak = plass.get("maks_overlapp", MAKS_OVERLAPP)
            if any(_overlapp(boks, b) > tak for b in opptatt):
                continue                  # opptatt plass — proev neste
            valgt = (plass, fugl, x, y, fx, fy, boks, flyttet, typ)
            break

        if valgt is None:
            print("      (fant ingen ledig plass — hopper over)")
            continue
        plass, fugl, x, y, fx, fy, boks, flyttet, typ = valgt
        ledige.remove(plass)
        opptatt.append(boks)
        print(f"      {typ}: {fugl.height} px paa ({x}, {y})"
              + ("  — flyttet klar av teksten" if flyttet else ""))

        # Festepunktet legges der det skal, med fire piksler overlapp saa
        # klørne ser ut til aa gripe. Hale og vingespisser faar henge under.
        ark.paste(fugl, (x - fx, y - fy + 4), fugl)
        # Boksen tas vare paa saa sida kan sette et tall ved fuglen som
        # peker tilbake i artslista. Koordinatene er i arkets piksler
        # (1200x1600), som er noeyaktig panelets -- ingen omregning senere.
        plassert.append({**s, "boks": list(boks), "fot": [x, y], "type": typ})
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
def retusj_prompt(plassert: list[dict]) -> str:
    """Retusj-instruksen, bygget av det som faktisk staar i bildet.

    Den var foer en fast tekst om aa faa fuglene til aa «sitte paa veden de
    staar paa». Paa myrmalen ga det tull: en flygende skjaere har ingen ved aa
    sitte paa, saa modellen tegnet inn en stubbe og satte den paa den. Naa
    faar den vite hva hver enkelt fugl gjoer -- og at ingenting nytt skal
    legges til."""
    typer = {p.get("type", "gren") for p in plassert}
    oppgaver = []
    if "gren" in typer:
        oppgaver.append(
            "The birds standing on branches: make their toes wrap around and "
            "grip the wood, with correct contact and weight, and let each "
            "bird's body and tail angle follow the branch it stands on.")
    if "bakke" in typer:
        oppgaver.append(
            "The birds standing on the ground: plant their feet properly on "
            "the mud or among the stems, so they stand in the vegetation "
            "rather than on top of it.")
    if "luft" in typer:
        oppgaver.append(
            "The birds in flight: they must STAY in flight, wings spread, "
            "with open empty sky around and below them. Do not give them "
            "anything to land on and do not fold their wings.")

    return (
        "This is an antique bird plate. Every bird is already in the right "
        "place, at the right size, doing the right thing. "
        "Your job is ONLY to make each bird belong in the scene instead of "
        "looking pasted on top of it. "
        + " ".join(oppgaver) + " "
        "You MAY rotate or tilt a bird slightly, redraw its legs, toes and "
        "claws, adjust how the tail hangs, nudge a bird a few pixels, and "
        "redraw the small area where it meets what it stands on. "
        "You MUST NOT add ANYTHING that is not already in the picture — no "
        "new branch, perch, stump, twig, plant, ground or shadow. Do not add "
        "or remove birds. Do not change any bird's size, do not move a bird "
        "somewhere else, and do not change which species is where. "
        "Do not change any bird's plumage or markings — colours, patterns and "
        "field marks must stay exactly as drawn. "
        "Leave the empty white area alone — the left 48% of the width from "
        "the top down to 72% of the height must stay completely empty white "
        "paper. "
        "Keep the fine engraved linework, the hand-coloured lithograph style "
        "and the pure white background."
    )


# Foreleggets oppløsning: hoeyere enn REF_MAX ellers i prosjektet, fordi
# modellen her skal GJENSKAPE arket, ikke bare hente stil fra det.
RETUSJ_REF = int(os.environ.get("RETUSJ_REF", "1200"))


SONE_SLAKK = float(os.environ.get("RETUSJ_SLAKK", "0.01"))


def _god_nok(soner: dict, basis: dict) -> bool:
    """Godtar et retusjforsoek som ikke gjoer tekstsonen VERRE enn den var.

    Absolutt terskel gaar ikke naar malen selv har blekk der: myrmalens
    sivkant ligger saavidt inne i sonen, og da ville ingen forsoek noen gang
    bli godtatt, uansett hvor pent modellen oppfoerte seg."""
    from compose_hero import SONE_GRENSE
    for navn, v in soner.items():
        if navn == "bunn":
            continue                       # bunnen har alltid mal-innhold
        tak = max(SONE_GRENSE, basis.get(navn, {}).get("verst", 0.0) + SONE_SLAKK)
        if v["verst"] > tak:
            return False
    return True


# Hvor mye av blekket i en fugls boks som maa vaere igjen etter retusjen.
# Under dette har modellen flyttet eller slettet fuglen i stedet for aa feste
# foettene dens.
BLIR_STAAENDE = float(os.environ.get("RETUSJ_BLIR_STAAENDE", "0.45"))


def _fuglene_staar(kandidat: Image.Image, foer: Image.Image,
                   plassert: list[dict]) -> str | None:
    """Navnet paa foerste fugl som er blitt borte, eller None hvis alle staar.

    Retusjen skal bare feste foetter. 29. august slettet den i stedet
    groennsisiken fra plassen sin og tegnet to fugler et annet sted paa arket
    -- boksen sto igjen med bar kvist, og merket pekte paa ingenting.
    Sonemaalingen fanget det ikke, for den ser bare paa tekstfeltet.

    Vi teller blekk i hver fugls boks foer og etter. En fugl som fester
    foettene flytter noen piksler; en fugl som er fjernet tar med seg det
    meste av blekket sitt."""
    a = np.asarray(foer.convert("L"), dtype=np.float32)
    b = np.asarray(kandidat.convert("L"), dtype=np.float32)
    if a.shape != b.shape:
        return None                        # ulik stoerrelse -- ikke sammenlignbart
    for s in plassert:
        x0, y0, x1, y1 = s["boks"]
        fer = float((a[y0:y1, x0:x1] < KUTT).sum())
        etter = float((b[y0:y1, x0:x1] < KUTT).sum())
        if fer > 0 and etter / fer < BLIR_STAAENDE:
            return (f"{norwegian_name(s['scientific_name'], s.get('common_name', ''))}"
                    f" ({etter / fer * 100:.0f} % av blekket igjen)")
    return None


def retusjer(ark: Image.Image, tries: int,
           plassert: list[dict]) -> tuple[Image.Image, dict, bool]:
    """Send arket tilbake for aa faa foettene til aa gripe. Returnerer
    (bilde, soner, ble_retusjert). Faller tilbake paa originalen hvis ingen
    forsoek holder tekstsonen ren."""
    ref = ark.copy()
    ref.thumbnail((RETUSJ_REF, RETUSJ_REF), Image.LANCZOS)
    basis = zone_report(ark)
    for forsoek in range(1, tries + 1):
        try:
            kandidat = fit_to_panel(whiten(
                generate_image(retusj_prompt(plassert), ref_images=[ref],
                               aspect_ratio="3:4",
                               model=RETUSJ_MODELL)))
        except Exception as e:  # noqa: BLE001
            print(f"  retusj {forsoek}/{tries} feilet: {str(e)[:120]}", file=sys.stderr)
            continue
        soner = zone_report(kandidat)
        status = " ".join(f"{n}={v['blekk']*100:.1f}%/verst {v['verst']*100:.1f}%"
                          for n, v in soner.items())
        ren = _god_nok(soner, basis)
        borte = _fuglene_staar(kandidat, ark, plassert) if ren else None
        if not ren:
            dom = "FORKASTET — rotet i tekstsonen"
        elif borte:
            dom = f"FORKASTET — flyttet paa {borte}"
        else:
            dom = "godtatt"
        print(f"  retusj {forsoek}/{tries}: {status}  {dom}")
        if ren and not borte:
            return kandidat, soner, True
    print("  ingen retusjforsoek besto — beholder den lokale sammensettingen",
          file=sys.stderr)
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


# Merket settes ved FOTPUNKTET, ikke ved bildekanten. Fotpunktet er ett punkt
# vi selv har satt; bildekanten er hele silhuetten, og hos en skjaere er halve
# den hale. Et merke «26 px utenfor boksen» kunne derfor havne 200 px fra
# fuglen: spettmeisens tall endte 150 px til venstre for den, naermere
# myrriksa enn meisen, fordi det naermeste rene papiret laa hos naboen.
MERKE = 40                                   # merket krever saa mye albuerom
MERKE_UT = 36                                # avstand fra foten til merket


def label_spots(ark: Image.Image, plassert: list[dict]) -> None:
    """Sett merket ved hver fugls fotpunkt, og velg stil etter bunnen der.

    Posisjonen er fast: rett nedenfor foten, foerst mot venstre. Fotpunktet
    flytter seg ikke -- det er der VI satte fuglen -- saa tallet peker alltid
    paa riktig fugl, ogsaa naar silhuetten er skjev av en lang hale.

    Tallet tegnes som hvitt paa en svart skive, og da spiller bunnen ingen
    rolle: baade #000 og #fff er blant panelets seks farger, saa skiva blir
    like skarp som teksten uansett hva som ligger under. Derfor maaler vi
    ikke lenger bakgrunnen -- og slipper at samme art faar tall én dag og
    skive den neste, alt etter hva retusjen tegnet."""
    W, H = ark.size
    tatt: list[tuple] = []

    def brukbar(cx: int, cy: int) -> bool:
        if not (MERKE <= cx <= W - MERKE and MERKE <= cy <= H - MERKE):
            return False
        # Aldri inn i tekstspalten (venstre 48 %, ned til 75 % av hoeyden).
        if cx < SPERRE_X and cy < SPERRE_Y:
            return False
        return not any(abs(cx - tx) < MERKE and abs(cy - ty) < MERKE
                       for tx, ty in tatt)

    for sp in plassert:
        x0, y0, x1, y1 = sp["boks"]
        fx, fy = sp["fot"]
        if sp.get("type") == "luft":
            # En flygende fugl har ingen foetter aa staa paa: «fot» er midt
            # paa kroppen, saa merket maa utenfor silhuetten i stedet.
            kand = [(x0 - MERKE_UT, y1), (x1 + MERKE_UT, y1),
                    (x0 - MERKE_UT, y0), (x1 + MERKE_UT, y0)]
        else:
            # Rett nedenfor foten ligger ved eller bakke -- aldri fuglekropp.
            kand = [(fx - MERKE_UT, fy + MERKE_UT // 2),
                    (fx + MERKE_UT, fy + MERKE_UT // 2),
                    (fx - MERKE_UT, fy - MERKE_UT),
                    (fx + MERKE_UT, fy - MERKE_UT)]
        plass = next((k for k in kand if brukbar(int(k[0]), int(k[1]))), None)
        if plass is None:
            print(f"      (fant ingen plass til merket for "
                  f"{sp.get('common_name', '?')})")
            continue
        cx, cy = int(plass[0]), int(plass[1])
        sp["merke"] = [cx, cy]
        tatt.append((cx, cy))


def kart(mal: dict) -> None:
    """Skriv ut hvor malen har overflate, som hjelp til aa sette plassene."""
    a = np.asarray(Image.open(os.path.join(MAL_DIR, mal["bilde"]))
                   .convert("RGB")).mean(axis=2)
    for x in range(100, 1200, 100):
        ink = np.where(a[:, x] < 225)[0]
        if not len(ink):
            print(f"  x={x:4d}  tomt")
            continue
        seg = np.split(ink, np.where(np.diff(ink) > 12)[0] + 1)
        print(f"  x={x:4d}  overflater y={[int(s[0]) for s in seg if len(s) > 4]}")


def fjern_ramme(img: Image.Image, kant: int = 45) -> tuple[Image.Image, bool]:
    """Fjern en tegnet ramme rundt arket, hvis den finnes.

    Modellen tegner den av og til uansett hvor tydelig prompten forbyr det --
    myrmalen fikk en 1 px strek ~25 px inn, tre forsoek paa rad. Vi leter etter
    en rad/kolonne naer hver kant som er dekket over mer enn halve lengden, og
    hvitner den og alt UTENFOR den. Motivet ligger innenfor rammen, saa
    ingenting av det gaar tapt.

    Merk at det er ramma vi fjerner, ikke en marg: en mal der motivet faktisk
    gaar helt ut i kanten (grenmalen) har ingen slik gjennomgaaende strek, og
    blir staaende urort."""
    a = np.asarray(img.convert("RGB")).copy()
    H, W, _ = a.shape
    moerk = a.mean(axis=2) < 225
    funnet = False

    for side in ("topp", "bunn", "venstre", "hoeyre"):
        if side in ("topp", "bunn"):
            rader = range(kant) if side == "topp" else range(H - 1, H - kant - 1, -1)
            treff = [r for r in rader if moerk[r, :].mean() > 0.5]
            if treff:
                r = treff[0]
                if side == "topp":
                    a[:r + 3, :] = 255
                else:
                    a[r - 2:, :] = 255
                funnet = True
        else:
            kols = range(kant) if side == "venstre" else range(W - 1, W - kant - 1, -1)
            treff = [c for c in kols if moerk[:, c].mean() > 0.5]
            if treff:
                c = treff[0]
                if side == "venstre":
                    a[:, :c + 3] = 255
                else:
                    a[:, c - 2:] = 255
                funnet = True

    return Image.fromarray(a, "RGB"), funnet


def har_ramme(img: Image.Image, kant: int = 45) -> bool:
    """Har modellen tegnet en ramme rundt arket?

    Sonemaalingen fanger den ikke -- en strek paa én piksel er promiller av
    sonen -- men den er stygg og gjoer at malen ikke gaar helt ut i kanten.
    Her ser vi etter en sammenhengende moerk strek langs OEVRE kant: er mer
    enn halve bredden dekket der, er det en ramme og ikke motiv (myrmalen har
    tomt papir oeverst, grenmalen har bare tynne kvister)."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32).mean(axis=2)
    baand = a[:kant, :]
    dekket = (baand < 225).any(axis=0).mean()
    return bool(dekket > 0.5)


def lag_mal(mal: dict, tries: int = 3) -> None:
    """Generer malens bakgrunnsbilde fra prompten som staar i malfila.

    Kjoeres én gang per mal, ikke daglig -- bakgrunnen skal vaere den samme
    hver dag, saa sida faar et gjenkjennelig skjelett.

    Samme forsoeksloekke som resten: modellen er like ustadig her som ellers.
    Hoestmalen la 11,7 % blekk i tekstsonen foerste forsoek selv om
    grunnmalen den tegnet oppaa var helt ren der. Vi tar flere forsoek og
    beholder det reneste."""
    refs = None
    base = mal.get("basert_paa")
    if base:
        basefil = os.path.join(MAL_DIR, f"{base}.png")
        if not os.path.exists(basefil):
            raise SystemExit(f"Mangler {basefil} — lag {base} foerst.")
        r = Image.open(basefil).convert("RGB")
        r.thumbnail((RETUSJ_REF, RETUSJ_REF), Image.LANCZOS)
        refs = [r]
        print(f"  forelegg: {os.path.basename(basefil)}")

    best, best_soner, best_sum = None, None, None
    for forsoek in range(1, tries + 1):
        img = fit_to_panel(whiten(generate_image(
            mal["prompt"], ref_images=refs, aspect_ratio="3:4",
            model=RETUSJ_MODELL)))
        img, ramme_fjernet = fjern_ramme(img)
        if ramme_fjernet:
            print("      (fjernet en tegnet ramme rundt arket)")
        soner = zone_report(img)
        ramme = har_ramme(img)
        sum_verst = sum(v["verst"] for v in soner.values()) + (1.0 if ramme else 0.0)
        print(f"  forsoek {forsoek}/{tries}: "
              + " ".join(f"{n}={v['blekk']*100:.1f}%/verst {v['verst']*100:.1f}%"
                         for n, v in soner.items())
              + ("  RAMME rundt arket" if ramme else ""))
        if best_sum is None or sum_verst < best_sum:
            best, best_soner, best_sum = img, soner, sum_verst
        if all(v["ren"] for v in soner.values()) and not ramme:
            print("  alle soner rene og ingen ramme — beholder denne")
            break

    for navn, v in best_soner.items():
        print(f"  sone {navn:9s} {v['blekk']*100:5.1f} % blekk, "
              f"verste baand {v['verst']*100:5.1f} %  "
              f"{'ren' if v['ren'] else 'OPPTATT'}")
    os.makedirs(MAL_DIR, exist_ok=True)
    ut = os.path.join(MAL_DIR, mal["bilde"])
    best.save(ut)
    print(f"OK: {ut} ({best.width}x{best.height})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sett dagens fugler paa grenen.")
    ap.add_argument("--birds", default=os.path.join(HERE, "birds.json"))
    ap.add_argument("--ny-fugl", action="append", metavar="'Genus art'",
                    default=[],
                    help="tegn arten paa nytt selv om bildet finnes "
                         "(kan gjentas)")
    ap.add_argument("--nye-fotpunkter", action="store_true",
                    help="bestem fotpunktene paa nytt (manuelt satte roeres ikke)")
    # gemini-3-pro-image gjoer retusjtrinnet merkbart bedre enn
    # gemini-2.5-flash-image: taerne griper faktisk rundt veden, og
    # streken holder seg renere. Satt som standard KUN her -- det daglige
    # AI-bildet bruker fortsatt sin egen modell til noen bestemmer noe annet.
    ap.add_argument("--retusj-modell",
                    default=os.environ.get("RETUSJ_MODELL", "gemini-3-pro-image"),
                    help="bildemodell for retusjtrinnet")
    ap.add_argument("--sjekk-foetter", metavar="UT.PNG",
                    help="kontaktark med kryss der fotpunktene er satt")
    ap.add_argument("--kart", action="store_true",
                    help="vis hvor malen har overflate (til aa sette plassene)")
    ap.add_argument("--mal", help="tving en bestemt mal (ellers velges den "
                                  "som passer dagens fugler best)")
    ap.add_argument("--lag-mal", metavar="NAVN",
                    help="generer bakgrunnsbildet for en mal og avslutt")
    ap.add_argument("--retusj", type=int, default=int(os.environ.get("RETUSJ_TRIES", "2")),
                    help="antall forsoek paa aa la Gemini feste foettene til "
                         "grenen (0 = hopp over)")
    ap.add_argument("--bare-fugler", action="store_true",
                    help="lag manglende 1:1-fugler og stopp")
    args = ap.parse_args()

    global NYE_FOTPUNKTER, RETUSJ_MODELL, NY_FUGL
    NYE_FOTPUNKTER, RETUSJ_MODELL = args.nye_fotpunkter, args.retusj_modell
    NY_FUGL = {a.strip().lower() for a in args.ny_fugl}

    if args.sjekk_foetter:
        sjekk_foetter(args.sjekk_foetter)
        return 0

    maler = {m["navn"]: m for m in last_maler()}
    if args.lag_mal:
        if args.lag_mal not in maler:
            raise SystemExit(f"Ingen mal som heter {args.lag_mal} i {MAL_DIR}")
        lag_mal(maler[args.lag_mal], args.retusj or 3)
        return 0

    birds = load_birds(args.birds)
    dato = (datetime.date.fromisoformat(birds["date"]) if birds.get("date")
            else datetime.date.today())

    # Malen velges av dagens arter, saa artslista maa bestemmes foerst -- men
    # da vet vi ikke enda hvor mange plasser malen har. Vi tar rikelig og
    # kutter etterpaa.
    kandidater, _ = split_species(birds.get("species", []), 12)
    kandidater = [s for s in kandidater if plate_path(s.get("scientific_name", ""))]
    if not kandidater:
        print("Ingen av dagens arter har en plansje ennaa.", file=sys.stderr)
        return 1

    vaer = None if args.mal else get_weather()
    mal = velg_mal(kandidater, dato.month, args.mal,
                   (vaer or {}).get("symbol", ""))
    bilde = os.path.join(MAL_DIR, mal["bilde"])
    if not os.path.exists(bilde):
        raise SystemExit(f"Mangler {bilde} — kjoer --lag-mal {mal['navn']} foerst.")
    if args.kart:
        kart(mal)
        return 0

    # Plass for plass, sikreste art foerst. Uten dette faller enkeltbekkasinen
    # ut av myrmalen fordi den ligger paa aattendeplass i lista, mens en
    # groennsisik som ikke kan staa i siv tar plassen.
    # Ikke flere fugler enn lista har rader til: et tall paa arket skal alltid
    # kunne slaas opp i lista. Malen har flere plasser enn det -- de ekstra er
    # der for at de rette artene skal faa staa, ikke for aa fylle arket.
    species = velg_arter(kandidater, mal)[:OVERLAY_ROWS]
    print("Arter: " + ", ".join(
        norwegian_name(s["scientific_name"], s["common_name"]) for s in species))

    if args.bare_fugler:
        for s in species:
            ensure_bird(s)
        return 0

    ark, plassert = compose(species, mal)
    ark = fit_to_panel(ark)
    retusjert = False
    if args.retusj > 0:
        ark, soner, retusjert = retusjer(ark, args.retusj, plassert)
    else:
        soner = zone_report(ark)
    for navn, v in soner.items():
        print(f"  sone {navn:9s} {v['blekk']*100:5.1f} % blekk, "
              f"verste baand {v['verst']*100:5.1f} %  "
              f"{'ren' if v['ren'] else 'OPPTATT'}")

    # Merkeplassene finnes paa det ferdige arket -- retusjeringen flytter piksler,
    # og et merke plassert foer den kan havne oppaa en nytegnet kvist.
    label_spots(ark, plassert)

    ark.save(BG_PNG)
    with open(BG_JSON, "w") as f:
        json.dump({
            "soner": soner,
            "date": birds.get("date") or datetime.date.today().isoformat(),
            "mal": mal["navn"],
            "metode": (f"{mal['navn']} + 1:1-fugler, satt sammen lokalt"
                       + (" og retusjert av Gemini" if retusjert else "")),
            "species": [{"common_name": s["common_name"],
                         "scientific_name": s["scientific_name"],
                         "norsk": norwegian_name(s["scientific_name"],
                                                 s["common_name"]),
                         "boks": s["boks"], "fot": s["fot"], "type": s.get("type", "gren"),
                         "merke": s.get("merke")}
                        for s in plassert],
        }, f, indent=2, ensure_ascii=False)
    print(f"OK: {BG_PNG} — {len(plassert)} fugler paa malen " + mal["navn"]
          + (", retusjert" if retusjert else ", uretusjert"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
