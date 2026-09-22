#!/usr/bin/env python3
"""
Fugleramme: vask skannede plansjer saa de taaler 6-fargepaletten.

Problemet: en gammel plansje er skannet med papiret sitt -- kremgult, litt
flekkete. Den fargen finnes ikke i panelets palett, saa Atkinson-dithringen
maa gjette den med gule prikker, og hele arket blir en gul stoeyflate rundt
fuglen. (Se «Grumsete bilde» i tools/README.md -- samme fenomen som med
akvarell.)

Loesningen er hvitpunkt-korreksjon: finn papirtonen, strekk den til rent
hvitt, og la fuglen beholde fargene sine. Da blir bakgrunnen én palettfarge
og dithres ikke i det hele tatt.

    venv/bin/python prepare_plates.py            # alle i plates/
    venv/bin/python prepare_plates.py --force    # ogsaa de som alt er vasket

Skriver plates/vasket/<samme-navn>.png. render_daily_panel.py ser der foerst.
Originalen roeres ikke -- vil du justere, kjoer paa nytt med --force.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
PLATES_DIR = os.environ.get(
    "PLATES_DIR",
    os.path.join(HERE, "plates") if os.path.isdir(os.path.join(HERE, "plates"))
    else os.path.join(HERE, "..", "plates"))
CLEAN_DIR = os.path.join(PLATES_DIR, "vasket")

# Papirtonen ligger i den lyse enden av histogrammet, men ikke helt paa toppen
# (en skanning har gjerne noen fA overeksponerte piksler). 85-persentilen
# treffer arket, ikke glimtene.
PAPER_PCT = float(os.environ.get("PLATE_PAPER_PCT", "85"))
# Hvor naer hvitt en piksel maa vaere for aa regnes som marg naar vi beskjaerer.
TRIM_LEVEL = int(os.environ.get("PLATE_TRIM_LEVEL", "244"))
# Over dette snittnivaaet er pikselen papir, ikke motiv.
SNAP_WHITE = float(os.environ.get("PLATE_SNAP_WHITE", "228"))


def whiten(img: Image.Image) -> Image.Image:
    """Strekk papirtonen til rent hvitt, per kanal. Per kanal er poenget: et
    kremgult ark har hoeyere R og G enn B, og skalerer vi alle likt beholder
    det gulstikket -- som er nettopp det dithringen lager prikker av."""
    arr = np.asarray(img, dtype=np.float32)
    lum = arr.mean(axis=2)
    paper_mask = lum >= np.percentile(lum, PAPER_PCT)
    if paper_mask.sum() < 100:
        return img
    paper = arr[paper_mask].mean(axis=0)          # papirets RGB
    paper = np.maximum(paper, 1.0)
    arr = np.clip(arr * (255.0 / paper), 0, 255)

    # Ett globalt hvitpunkt rekker ikke: skanninger er moerkere i kantene, saa
    # en gul rand blir igjen rundt plansjen etter strekket. Alt som allerede er
    # naer hvitt klemmes derfor helt til hvitt. Terskelen ligger trygt over ren
    # gul (snittkanal 170), saa fuglens farger roeres ikke.
    lum2 = arr.mean(axis=2)
    arr[lum2 > SNAP_WHITE] = 255.0
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def trim(img: Image.Image) -> Image.Image:
    """Beskjaer den hvite margen rundt selve plansjen, saa fuglen faar hele
    ramma i stedet for aa sitte som et frimerke midt i et ark."""
    arr = np.asarray(img.convert("RGB")).mean(axis=2)
    ink = arr < TRIM_LEVEL
    rows, cols = np.where(ink.any(axis=1))[0], np.where(ink.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return img
    pad = 8
    top, bot = max(0, rows[0] - pad), min(img.height, rows[-1] + pad)
    left, right = max(0, cols[0] - pad), min(img.width, cols[-1] + pad)
    return img.crop((left, top, right, bot))


def prepare(src: str, dest: str) -> tuple[int, int]:
    img = Image.open(src).convert("RGB")
    img = whiten(img)
    img = trim(img)
    # Litt metning og kontrast dytter mellomtonene mot palettens ytterpunkter,
    # samme grep som to_epaper() gjoer paa AI-bildet.
    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img.save(dest)
    return img.size


def main() -> int:
    ap = argparse.ArgumentParser(description="Vask plansjer for e-ink.")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(CLEAN_DIR, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(PLATES_DIR)):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        src = os.path.join(PLATES_DIR, name)
        dest = os.path.join(CLEAN_DIR, os.path.splitext(name)[0] + ".png")
        if os.path.exists(dest) and not args.force:
            continue
        w, h = prepare(src, dest)
        print(f"  {name} -> vasket/{os.path.basename(dest)} ({w}x{h})")
        n += 1
    print(f"OK: {n} plansjer vasket til {CLEAN_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
