#!/usr/bin/env python3
"""
Fugleramme: rasteriser dagens fugleside (HTML) til panelformat.

    venv/bin/python render_panel_png.py --html panel.html --out-dir www

Steg:
  1. HTML -> PNG paa noeyaktig 1200x1600 med headless chromium (playwright)
  2. PNG  -> Atkinson-dithering + 2 piksler per byte via to_epaper() i
     generate_daily_image.py -- SAMME funksjon som AI-bildet bruker, saa
     panelet ser nyaktig ut som resten av loypa forventer.
  3. skriver frame.bin (det push_to_frame.py sender), preview.png (slik det
     faktisk blir seende ut) og panel.png (raa rastrering, for feilsoeking)

Krever paa serveren:
    venv/bin/pip install playwright
    venv/bin/playwright install chromium-headless-shell
(headless-shell, ikke full chromium: den starter uten libatk/libcups, som
ikke er installert her og ville krevd root.)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_daily_image import WIDTH, HEIGHT, to_epaper  # noqa: E402

from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def html_to_png(html_path: str, png_path: str) -> None:
    """Skyt et skjermbilde av sida paa noeyaktig panelstoerrelse.

    device_scale_factor=1: vi vil ha 1 CSS-piksel = 1 panelpiksel. Skalerer vi
    opp og ned igjen, faar vi graatoner i kantene paa bokstavene -- og graatoner
    er nettopp det dithringen maa gjette seg fram til med prikker."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
        )
        page.goto("file://" + os.path.abspath(html_path))
        page.wait_for_load_state("networkidle")
        page.screenshot(path=png_path, full_page=False)
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML-side -> frame.bin for panelet.")
    ap.add_argument("--html", required=True)
    ap.add_argument("--out-dir", default="/opt/fugleramme/www")
    ap.add_argument("--bare-png", metavar="UT.PNG",
                    help="bare rastrer til denne fila, ingen dithering")
    args = ap.parse_args()

    if args.bare_png:
        html_to_png(args.html, args.bare_png)
        print(f"OK: {args.bare_png}")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    raw = os.path.join(args.out_dir, "panel.png")
    html_to_png(args.html, raw)

    img = Image.open(raw).convert("RGB")
    if img.size != (WIDTH, HEIGHT):
        raise SystemExit(f"Feil stoerrelse fra rastreringen: {img.size}")

    preview, framebuf = to_epaper(img)
    assert len(framebuf) == (WIDTH // 2) * HEIGHT, f"Feil bufferstoerrelse: {len(framebuf)}"

    tmp = os.path.join(args.out_dir, "frame.bin.tmp")
    with open(tmp, "wb") as f:
        f.write(framebuf)
    os.replace(tmp, os.path.join(args.out_dir, "frame.bin"))
    preview.save(os.path.join(args.out_dir, "preview.png"))

    print(f"OK: {raw} -> {len(framebuf)} bytes i {args.out_dir}/frame.bin "
          f"(+ preview.png)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
