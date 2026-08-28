#!/usr/bin/env python3
"""
Fugleramme: maal om teksten FAKTISK kolliderer med illustrasjonen.

Sonemaalingen i compose_hero.py teller blekk i et rektangel. Det er en grov
tilnaerming: rektangelet dekker hele venstre spalte, mens teksten bare er
bokstaver med luft imellom. Snoegrana la 4,8 % blekk i sonen og fikk pute --
men barnaalene laa i mellomrommene, ikke oppaa noen bokstav.

Her tegnes sida én gang UTEN illustrasjonen. Alt som ikke er hvitt i det
bildet er tekst. Saa ser vi paa bakgrunnen bare der de pikslene er, og teller
hvor mange av dem som havner paa noe moerkt nok til aa svelge svart tekst.

    python3 tekstkollisjon.py --maske maske.png --bakgrunn dagens-bakgrunn.png \\
                              --json dagens-bakgrunn.json

Resultatet skrives tilbake i sidecar-JSON-en som `soner[...]["ren"]`, saa
render_daily_panel.py sin pute-logikk virker uendret -- bare paa et maal som
betyr noe.

Maalingen dekker HELE arket, ikke sonerektangelet. Rektangelet var en rest
fra da vi telte blekk: da maatte man si hvor man skulle telle. Maska sier det
selv -- den er sida uten illustrasjon, saa alt som ikke er hvitt der ER tekst,
uansett hvor paa arket det staar. Det er ikke en detalj: listeboksen vokser
nedover med antall arter, og med ni fugler naadde kildelinjene ned til y=1300
mens rektangelet sluttet ved y=1152. Teksten laa synlig oppaa en rodvingetrost
og maalingen meldte «ren».
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compose_hero import SONER  # noqa: E402

# Hvor moerk bakgrunnen maa vaere for aa true svart tekst. Lys snoe og bleke
# straa gjoer ingenting; moerke barnaaler og fugler gjoer.
MOERK = float(os.environ.get("KOLLISJON_MOERK", "165"))
# Litt luft rundt bokstavene: et moerkt parti som taangerer teksten er ogsaa
# et problem, selv om det ikke ligger midt paa en strek.
LUFT = int(os.environ.get("KOLLISJON_LUFT", "3"))
# Andel av tekstpikslene i et baand som kan ligge moerkt foer sida trenger pute.
GRENSE = float(os.environ.get("KOLLISJON_GRENSE", "0.01"))
# Maalt i vannrette baand, ikke som ett snitt over arket. Noeyaktig samme
# laerdom som sonemaalingen i compose_hero: teksten ligger i linjer nedover
# sida, og to kildelinjer som er helt dekket forsvinner i snittet av ni linjer
# som ligger fritt. Med ni fugler ble 4,8 % kollisjon i det nederste baandet
# til 0,7 % over hele arket -- under grensa, saa puta uteble og linjene laa
# synlig oppaa en roedvingetrost.
BAAND = int(os.environ.get("KOLLISJON_BAAND", "10"))
# Et baand med en haandfull tekstpiksler skal ikke kunne avgjoere noe.
MIN_PIKSLER = int(os.environ.get("KOLLISJON_MIN", "500"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Maal tekst mot illustrasjon.")
    ap.add_argument("--maske", required=True, help="sida rendret uten bakgrunn")
    ap.add_argument("--bakgrunn", required=True)
    ap.add_argument("--json", required=True, help="sidecar som skal oppdateres")
    args = ap.parse_args()

    m = np.asarray(Image.open(args.maske).convert("RGB"), dtype=np.float32).mean(axis=2)
    b = np.asarray(Image.open(args.bakgrunn).convert("RGB"), dtype=np.float32).mean(axis=2)
    if m.shape != b.shape:
        raise SystemExit(f"Ulik stoerrelse: {m.shape} vs {b.shape}")

    tekst = ndimage.binary_dilation(m < 200, iterations=LUFT)
    moerk = b < MOERK
    H, W = m.shape

    with open(args.json) as f:
        meta = json.load(f)
    soner = meta.setdefault("soner", {})

    antall = int(tekst.sum())
    snitt = float((tekst & moerk).sum() / antall) if antall else 0.0
    verst = 0.0
    for i in range(BAAND):
        y0, y1 = i * H // BAAND, (i + 1) * H // BAAND
        t = tekst[y0:y1]
        n = int(t.sum())
        if n < MIN_PIKSLER:
            continue
        verst = max(verst, float((t & moerk[y0:y1]).sum() / n))

    # Ett maal for hele arket, skrevet under hvert sonenavn: puta er én
    # avgjoerelse -- enten ligger teksten fritt, eller saa gjoer den ikke det.
    ren = verst <= GRENSE
    for navn, *_ in SONER:
        soner.setdefault(navn, {})
        soner[navn]["kollisjon"] = round(snitt, 4)
        soner[navn]["verst"] = round(verst, 4)
        soner[navn]["ren"] = ren
        print(f"  sone {navn:9s} {antall:6d} tekstpiksler, "
              f"{snitt*100:5.2f} % paa moerk bunn, verste baand {verst*100:5.2f} %  "
              f"{'ren' if ren else 'TRENGER PUTE'}")

    with open(args.json, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
