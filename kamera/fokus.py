#!/usr/bin/env python3
"""
fokus.py — fokushjelper for HQ-kameraet, som har manuell fokusring.

Skriver et skarphetstall hvert sekund, maalt i feltene rundt materne fra
kamera.json (roier, med rotasjon) -- ikke midt i bildet, for der er det
gjerne loev eller gjerde. Vri fokusringen paa linsa sakte til tallet er
hoeyest, og laas den. Tallet er variansen av Laplace-operatoren: skarpe
kanter gir hoeyt tall. Stolpen er logaritmisk paa fast skala: tom er helt
uskarpt, full er skarpt.

    ssh bruker@fugleramme-kamera python3 kamera/fokus.py

Stopper kamera-loekka selv foerst (kameraet kan bare brukes av én) -- start
den igjen etterpaa, eller la systemd gjoere det.
"""
import json
import os
import subprocess
import sys
import time

import numpy as np
from picamera2 import Picamera2

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(HERE, "kamera.json")) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {}
roier = cfg.get("roier") or [cfg.get("roi", [0.25, 0.25, 0.75, 0.75])]
rot = int(cfg.get("roter", 0)) % 360

subprocess.run(["pkill", "-f", "^python3 kamera.py"], check=False)
time.sleep(1)

cam = Picamera2()
cam.configure(cam.create_still_configuration(
    main={"size": (2028, 1520)}, lores={"size": (1014, 760), "format": "YUV420"}))
cam.start()
time.sleep(1)
beste = 0.0
print(f"skarphet i {len(roier)} felt (rotasjon {rot}). Vri fokusringen til tallet er "
      "hoeyest, Ctrl-C for aa avslutte.")


def snu(a):
    if rot == 90:
        return np.rot90(a, -1)
    if rot == 270:
        return np.rot90(a, 1)
    if rot == 180:
        return a[::-1, ::-1]
    return a


try:
    while True:
        y = snu(cam.capture_array("lores")[:760, :1014]).astype(np.float32)
        h, w = y.shape
        verdier = []
        for x0, y0, x1, y1 in roier:
            m = y[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
            if m.shape[0] < 3 or m.shape[1] < 3:
                continue
            lap = (-4 * m[1:-1, 1:-1] + m[:-2, 1:-1] + m[2:, 1:-1]
                   + m[1:-1, :-2] + m[1:-1, 2:])
            verdier.append(float(lap.var()))
        s = float(np.mean(verdier)) if verdier else 0.0
        beste = max(beste, s)
        stolpe = "#" * min(60, int(max(0.0, np.log10(max(s, 1.0))) * 20))
        print(f"{s:9.1f}  {stolpe}", flush=True)
        time.sleep(0.7)
except KeyboardInterrupt:
    print(f"\nbeste: {beste:.0f}. Start kameraet igjen: cd ~/kamera && nohup python3 kamera.py > kamera.log 2>&1 &")
    sys.exit(0)
