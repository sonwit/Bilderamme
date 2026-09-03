#!/usr/bin/env python3
"""
kamera.py — fuglekameraet i vinduet. Kjoerer paa en Raspberry Pi 3 B med
Camera Module 3 Wide, rettet mot fuglemateren gjennom glasset.

Lytteposten hoerer fuglene; denne ser dem. 3. sep 2026 sto to troster paa
plenen som mikrofonen aldri hoerte, og det var det som satte i gang dette.

Slik virker den:

  1. Kameraet leverer to stroemmer samtidig: en liten graatonestroem
     (640x360) som leses hele tiden, og en stor (2304x1296) som bare brukes
     naar noe skjer.
  2. Bevegelse = andelen piksler i utsnittet (ROI) som endret seg mer enn
     `diff_terskel` siden forrige ramme. Over `bevegelse_andel` -> ta bilde.
  3. Bildet beskjaeres til utsnittet med margin og POST-es til serveren paa
     samme maate som utedelen sender lyd: POST /bilde?stamp=... paa :8091.
     Serveren lagrer det og spoer modellen hva som staar der.
  4. Deretter venter den `pause_s` sekunder foer neste bilde -- en fugl paa
     materen i tre minutter skal ikke bli 60 bilder.

Ingenting analyseres her: Pi 3-en er for svak til aa kjenne igjen fugler
selv, og serveren har alt den trenger. Natt hoppes over: er utsnittet
moerkere enn `lys_min`, sover den et minutt og ser igjen.

    python3 kamera.py                 # tjenesten (se deploy/fugleramme-kamera.service)
    python3 kamera.py --en            # ett bilde naa, last opp, avslutt (test)
    python3 kamera.py --vis           # skriv bevegelsesmaal hvert sekund, uten aa sende

Konfig i kamera.json ved siden av scriptet (se kamera.example.json). Manglende
noekler faar standardverdiene under. Avhengigheter: python3-picamera2 og
python3-numpy fra apt, resten er stdlib.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KONFIG = os.path.join(HERE, "kamera.json")

STANDARD = {
    "server": "http://192.168.1.38:8091",
    "token": "",
    # Utsnittet som overvaakes, som andeler av bildet: [x0, y0, x1, y1].
    # Hele bildet til aa begynne med; snevres inn til materen naar kameraet
    # staar der det skal, saa greiner i vind utenfor ikke utloeser.
    "roi": [0.0, 0.0, 1.0, 1.0],
    # Hvor mye en piksel (0-255) maa endre seg for aa telle som endret ...
    "diff_terskel": 28,
    # ... og hvor stor andel av utsnittet som maa ha endret seg. 0,4 % av
    # 640x360 er ~900 piksler -- en meis paa tre meter er stoerre enn det,
    # sensorstoey er mindre.
    "bevegelse_andel": 0.004,
    # Sekunder mellom to bilder, og mellom to rammer i overvaakingen.
    "pause_s": 12,
    "ramme_s": 0.5,
    # Gjennomsnittlig lysstyrke (0-255) i utsnittet under dette = natt.
    "lys_min": 25,
    # Fast fokusavstand i meter til materen. 0 = kontinuerlig autofokus, som
    # gjerne laaser seg paa vindusglasset.
    "fokus_m": 0,
    # Stort bilde og hvor mye ekstra rundt utsnittet som sendes med.
    "bilde": [2304, 1296],
    "margin": 0.08,
    "jpeg_kvalitet": 88,
}


def les_konfig() -> dict:
    cfg = dict(STANDARD)
    try:
        with open(KONFIG) as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    return cfg


def logg(msg: str) -> None:
    print(f"{datetime.datetime.now():%H:%M:%S} {msg}", flush=True)


# ----------------------------------------------------------------------
# Kamera
# ----------------------------------------------------------------------

def start_kamera(cfg: dict):
    from picamera2 import Picamera2

    cam = Picamera2()
    w, h = cfg["bilde"]
    konf = cam.create_still_configuration(
        main={"size": (w, h)},
        lores={"size": (640, 360), "format": "YUV420"},
        buffer_count=2)
    cam.configure(konf)
    cam.start()
    if cfg["fokus_m"]:
        from libcamera import controls
        # LensPosition er i dioptrier (1/m). Fast fokus slaar autofokusen,
        # som ellers gjerne finner vindusglasset mer interessant enn materen.
        cam.set_controls({"AfMode": controls.AfModeEnum.Manual,
                          "LensPosition": 1.0 / float(cfg["fokus_m"])})
    else:
        from libcamera import controls
        cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
    time.sleep(1.5)  # eksponering og hvitbalanse trenger noen rammer
    return cam


def graa(cam) -> np.ndarray:
    """Y-planet fra den lille stroemmen, som float for differansen."""
    arr = cam.capture_array("lores")
    return arr[:360, :640].astype(np.float32)


def utsnitt(a: np.ndarray, roi: list[float]) -> np.ndarray:
    h, w = a.shape[:2]
    x0, y0, x1, y1 = roi
    return a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def bevegelse(forrige: np.ndarray, naa: np.ndarray, cfg: dict) -> float:
    """Andel piksler i utsnittet som endret seg mer enn terskelen."""
    d = np.abs(utsnitt(naa, cfg["roi"]) - utsnitt(forrige, cfg["roi"]))
    return float((d > cfg["diff_terskel"]).mean())


def ta_bilde(cam, cfg: dict) -> bytes:
    """Stort bilde, beskaaret til utsnittet med margin, som JPEG-byte."""
    from PIL import Image

    arr = cam.capture_array("main")
    im = Image.fromarray(arr)
    x0, y0, x1, y1 = cfg["roi"]
    m = cfg["margin"]
    boks = (int(max(0, x0 - m) * im.width), int(max(0, y0 - m) * im.height),
            int(min(1, x1 + m) * im.width), int(min(1, y1 + m) * im.height))
    if boks != (0, 0, im.width, im.height):
        im = im.crop(boks)
    ut = io.BytesIO()
    im.save(ut, "JPEG", quality=int(cfg["jpeg_kvalitet"]))
    return ut.getvalue()


# ----------------------------------------------------------------------
# Opplasting
# ----------------------------------------------------------------------

def last_opp(cfg: dict, jpeg: bytes, meta: dict) -> bool:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    url = f"{cfg['server']}/bilde?stamp={stamp}"
    if cfg["token"]:
        url += f"&token={cfg['token']}"
    req = urllib.request.Request(url, data=jpeg, method="POST", headers={
        "Content-Type": "image/jpeg",
        "X-Fugl-Meta": json.dumps(meta, ensure_ascii=False),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            svar = json.loads(r.read().decode("utf-8", "replace"))
        logg(f"lastet opp kamera_{stamp}.jpg ({len(jpeg) // 1024} kB) -> {svar.get('message', 'ok')}")
        return True
    except (urllib.error.URLError, OSError, ValueError) as e:
        logg(f"opplasting feilet: {e}")
        return False


def meta_for(cam, andel: float, lys: float, cfg: dict) -> dict:
    md = {}
    try:
        md = cam.capture_metadata()
    except Exception:  # noqa: BLE001
        pass
    temp = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = round(int(f.read()) / 1000, 1)
    except OSError:
        pass
    return {
        "host": os.uname().nodename,
        "bevegelse": round(andel, 4),
        "lys": round(lys, 1),
        "lux": round(float(md.get("Lux", 0)), 1) if md.get("Lux") is not None else None,
        "eksponering_us": md.get("ExposureTime"),
        "fokus": md.get("LensPosition"),
        "roi": cfg["roi"],
        "temp_c": temp,
    }


# ----------------------------------------------------------------------
# Hovedsloeyfe
# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Fuglekameraet i vinduet.")
    ap.add_argument("--en", action="store_true", help="ett bilde naa, last opp, avslutt")
    ap.add_argument("--vis", action="store_true", help="skriv bevegelsesmaal, ikke send")
    args = ap.parse_args()

    cfg = les_konfig()
    logg(f"starter: server {cfg['server']}, roi {cfg['roi']}, "
         f"terskel {cfg['bevegelse_andel']:.3%}, fokus "
         f"{cfg['fokus_m'] or 'auto'}")
    cam = start_kamera(cfg)

    if args.en:
        g = graa(cam)
        lys = float(utsnitt(g, cfg["roi"]).mean())
        jpeg = ta_bilde(cam, cfg)
        ok = last_opp(cfg, jpeg, meta_for(cam, 0.0, lys, cfg) | {"test": True})
        return 0 if ok else 1

    forrige = graa(cam)
    sist_bilde = 0.0
    while True:
        time.sleep(cfg["ramme_s"])
        naa = graa(cam)
        lys = float(utsnitt(naa, cfg["roi"]).mean())
        if lys < cfg["lys_min"]:
            if args.vis:
                logg(f"moerkt ({lys:.0f} < {cfg['lys_min']}), venter")
            time.sleep(60)
            forrige = graa(cam)
            continue
        andel = bevegelse(forrige, naa, cfg)
        forrige = naa
        if args.vis:
            logg(f"bevegelse {andel:.3%}  lys {lys:.0f}")
            continue
        if andel < cfg["bevegelse_andel"]:
            continue
        if time.time() - sist_bilde < cfg["pause_s"]:
            continue
        logg(f"bevegelse {andel:.2%} — tar bilde")
        jpeg = ta_bilde(cam, cfg)
        last_opp(cfg, jpeg, meta_for(cam, andel, lys, cfg))
        sist_bilde = time.time()
        # Etter et bilde er referansen gammel; ta en ny saa selve
        # bildetakingen ikke utloeser neste.
        forrige = graa(cam)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
