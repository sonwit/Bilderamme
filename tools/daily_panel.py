#!/usr/bin/env python3
"""
Fugleramme: dagens fugleside, hele veien fra birds.json til frame.bin.

Dette er inngangspunktet cron kaller. Det gjoer i tur og orden:

  1. compose_branch.py  — dagens fugler paa den faste grenen (og pusser dem)
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

# Pussetrinnet koster ett Gemini-kall og kan feile. Sett PUSS=0 for aa hoppe
# over det -- sida blir fortsatt riktig, fuglene ser bare litt mindre ut som
# de griper.
PUSS = os.environ.get("PUSS", "2")


def kjoer(navn: str, *args: str) -> None:
    print(f"\n--- {navn} ---", flush=True)
    r = subprocess.run([PY, os.path.join(HERE, navn), *args])
    if r.returncode != 0:
        raise SystemExit(f"FEIL: {navn} gikk ut med kode {r.returncode}")


def main() -> int:
    os.makedirs(WWW, exist_ok=True)
    kjoer("compose_branch.py", "--birds", BIRDS, "--puss", PUSS)
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
        kjoer("render_daily_panel.py", "--birds", BIRDS, "--out", maske_html,
              "--uten-bakgrunn")
        kjoer("render_panel_png.py", "--html", maske_html, "--bare-png", maske_png)
        kjoer("tekstkollisjon.py", "--maske", maske_png,
              "--bakgrunn", bg_png, "--json", bg_json)

    kjoer("render_daily_panel.py", "--birds", BIRDS, "--out", HTML)
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
