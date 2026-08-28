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
# Andel av tekstpikslene i sonen som kan ligge moerkt foer den trenger pute.
GRENSE = float(os.environ.get("KOLLISJON_GRENSE", "0.01"))


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

    for navn, x0, y0, x1, y1 in SONER:
        t = tekst[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        d = moerk[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        antall = int(t.sum())
        kollisjon = float((t & d).sum() / antall) if antall else 0.0
        ren = kollisjon <= GRENSE
        soner.setdefault(navn, {})
        soner[navn]["kollisjon"] = round(kollisjon, 4)
        soner[navn]["ren"] = ren
        print(f"  sone {navn:9s} {antall:6d} tekstpiksler, "
              f"{kollisjon*100:5.2f} % paa moerk bunn  "
              f"{'ren' if ren else 'TRENGER PUTE'}")

    with open(args.json, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
