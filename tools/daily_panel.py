#!/usr/bin/env python3
"""
Fugleramme: dagens fugleside, hele veien fra birds.json til frame.bin.

Dette er inngangspunktet cron kaller. Det gjoer i tur og orden:

  1. compose_branch.py  — dagens fugler paa den faste grenen (og retusjerer dem)
  2. render_daily_panel — sida som HTML, med lista oppaa illustrasjonen
  3. render_panel_png   — rastrer + Atkinson-dithring -> www/frame.bin
  4. arkiverer sida saa galleriet paa :8090 faar den med

    venv/bin/python daily_panel.py

Returnerer 0 bare hvis frame.bin faktisk ble skrevet. Feiler noe -- ingen av
dagens arter har plansje ennaa, Gemini er nede, vaer-APIet svarer ikke -- gaar
den ut med feilkode, og cron faller tilbake paa generate_daily_image.py. Da
henger det gamle AI-bildet paa veggen i stedet for ingenting.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BIRDS = os.environ.get("BIRDS_JSON", os.path.join(HERE, "birds.json"))
WWW = os.environ.get("FRAME_OUTPUT_DIR", "/opt/fugleramme/www")
ARKIV = os.environ.get("FRAME_ARCHIVE_DIR", os.path.join(WWW, "arkiv"))
HTML = os.path.join(WWW, "panel.html")

# Retusjtrinnet koster ett Gemini-kall og kan feile. Sett RETUSJ=0 for aa hoppe
# over det -- sida blir fortsatt riktig, fuglene ser bare litt mindre ut som
# de griper.
RETUSJ = os.environ.get("RETUSJ", "2")

# Ferske arter gjoeres klare FOER sida tegnes: kildeplansje fra Commons,
# 1:1-fugler, fotpunkt og metadata. Uten dette sto en ny art i lista uten aa
# bli tegnet til noen oppdaget det for haand -- groennfinken laa slik i ukevis
# paa 96 %. Taket er lavt med vilje: hver art koster to bildekall, og en dag
# med mange gjester skal ikke kunne tygge seg gjennom kvota ubemerket.
# NYE_ARTER=0 slaar det av.
NYE_ARTER = int(os.environ.get("NYE_ARTER", "2"))

# Morgensida skal vise dagen som paagaar -- men lytteplanen foelger sola, og om
# vinteren har utedelen ikke vaaknet ennaa kl. 07. Maalt over aaret: 14-24
# opptak foer kl. 07 i mai-august, og NULL fra midten av oktober til ut
# februar, fordi sola staar opp 09:13 i desember og foerste opptak er 08:00.
# Da tegnes gaarsdagen ferdig i stedet. Det er bedre enn AI-bildet, som var
# det den ellers falt tilbake paa. RESERVE_I_GAAR=0 slaar det av.
RESERVE_I_GAAR = os.environ.get("RESERVE_I_GAAR", "1") != "0"


def kjoer(navn: str, *args: str) -> None:
    print(f"\n--- {navn} ---", flush=True)
    r = subprocess.run([PY, os.path.join(HERE, navn), *args])
    if r.returncode != 0:
        raise SystemExit(f"FEIL: {navn} gikk ut med kode {r.returncode}")


def kjoer_kode(navn: str, *args: str) -> int:
    """Som kjoer(), men gir tilbake exit-koden i stedet for aa stoppe."""
    print(f"\n--- {navn} ---", flush=True)
    return subprocess.run([PY, os.path.join(HERE, navn), *args]).returncode


def kjoer_mykt(navn: str, *args: str) -> None:
    """Som kjoer(), men en feil stopper ikke dagen."""
    print(f"\n--- {navn} ---", flush=True)
    r = subprocess.run([PY, os.path.join(HERE, navn), *args])
    if r.returncode != 0:
        print(f"ADVARSEL: {navn} gikk ut med kode {r.returncode} — fortsetter",
              file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tegn dagens fugleside.")
    # Begge kjoeringene tegner dagen som paagaar. Finnes det ingenting aa
    # tegne ennaa -- vintermorgener, foer utedelen har vaaknet -- faller
    # i-dag tilbake paa i-gaar (se RESERVE_I_GAAR).
    ap.add_argument("--dag", default=os.environ.get("DAG", "i-dag"),
                    help="i-dag (standard) | i-gaar | YYYY-MM-DD")
    args = ap.parse_args()

    os.makedirs(WWW, exist_ok=True)

    def forbered(dag: str) -> str:
        """birds.json for dagen. birds.json paa disk er alltid DAGENS --
        analysatoren skriver den om ved hver opplasting -- saa en annen dato
        maa aggregeres fram fra observasjonsloggen foerst."""
        if dag == "i-dag":
            return BIRDS
        sti = os.path.join(WWW, "birds-valgt.json")
        kjoer("birdnet_analyze.py", "--dag", dag, sti)
        return sti

    dager = [args.dag]
    if args.dag == "i-dag" and RESERVE_I_GAAR:
        dager.append("i-gaar")

    birds = BIRDS
    for i, dag in enumerate(dager):
        birds = forbered(dag)
        # Foer sammensettingen, ikke etter: compose_branch leser bird_names ved
        # import, og ny_art skriver metadataene til plates/arter.json. At det
        # er en egen prosess er nettopp det som gjoer at arten er med med én
        # gang.
        if NYE_ARTER > 0:
            kjoer_mykt("ny_art.py", "--mangler", "--birds", birds,
                       "--maks", str(NYE_ARTER))
        kode = kjoer_kode("compose_branch.py", "--birds", birds,
                          "--retusj", RETUSJ)
        if kode == 0:
            break
        if i + 1 < len(dager):
            print(f"Ingenting aa tegne for {dag} ennaa — tegner "
                  f"{dager[i + 1]} i stedet.", file=sys.stderr)
        else:
            raise SystemExit(f"FEIL: compose_branch.py gikk ut med kode {kode}")
    # Puta avgjoeres av om teksten FAKTISK kolliderer med illustrasjonen, ikke
    # av hvor mye blekk som ligger i et rektangel. Sida tegnes derfor én gang
    # uten bakgrunn foerst: alt som ikke er hvitt der er tekst, og da kan vi
    # maale bare under bokstavene. Koster to ekstra chromium-skudd, ingen
    # API-kall.
    maske_html = os.path.join(WWW, "panel-maske.html")
    maske_png = os.path.join(WWW, "panel-maske.png")
    bg_json = os.path.join(os.path.dirname(WWW), "plates", "dagens-bakgrunn.json")
    bg_png = os.path.join(os.path.dirname(WWW), "plates", "dagens-bakgrunn.png")
    if os.path.exists(bg_json) and os.path.exists(bg_png):
        kjoer("render_daily_panel.py", "--birds", birds, "--out", maske_html,
              "--uten-bakgrunn")
        kjoer("render_panel_png.py", "--html", maske_html, "--bare-png", maske_png)
        kjoer("tekstkollisjon.py", "--maske", maske_png,
              "--bakgrunn", bg_png, "--json", bg_json)

    kjoer("render_daily_panel.py", "--birds", birds, "--out", HTML)
    kjoer("render_panel_png.py", "--html", HTML, "--out-dir", WWW)

    frame = os.path.join(WWW, "frame.bin")
    if not os.path.exists(frame) or os.path.getsize(frame) != 960000:
        raise SystemExit("FEIL: frame.bin mangler eller har feil stoerrelse")

    # Arkiver sida slik den ble, saa galleriet viser historikken ogsaa for
    # panelet -- ikke bare for AI-bildene. Feiler stille: arkivering skal
    # aldri stoppe dagens bilde.
    try:
        os.makedirs(ARKIV, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        shutil.copy2(os.path.join(WWW, "panel.png"),
                     os.path.join(ARKIV, f"{stamp}_dagens-side.png"))
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: klarte ikke arkivere sida: {e}", file=sys.stderr)

    print(f"\nOK: dagens side klar i {frame}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
