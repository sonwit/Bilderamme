#!/usr/bin/env python3
"""
fokus.py — fokushjelper for HQ-kameraet, som har manuell fokusring.

Skriver et skarphetstall hvert sekund, maalt i midten av bildet. Vri
fokusringen paa linsa sakte til tallet er hoeyest, og laas den. Tallet er
variansen av Laplace-operatoren: skarpe kanter gir hoeyt tall, uskarpt
gir lavt. Absoluttverdien betyr ingenting, det er toppen som teller.

    ssh bruker@fugleramme-kamera python3 kamera/fokus.py

Stopp kamera-tjenesten foerst, kameraet kan bare brukes av én.
"""
import sys
import time

import numpy as np
from picamera2 import Picamera2

cam = Picamera2()
cam.configure(cam.create_still_configuration(
    main={"size": (2028, 1520)}, lores={"size": (1014, 760), "format": "YUV420"}))
cam.start()
time.sleep(1)
beste = 0.0
print("skarphet (vri fokusringen til tallet er hoeyest, Ctrl-C for aa avslutte)")
try:
    while True:
        y = cam.capture_array("lores")[:760, :1014].astype(np.float32)
        h, w = y.shape
        m = y[h // 4:3 * h // 4, w // 4:3 * w // 4]   # midten
        lap = (-4 * m[1:-1, 1:-1] + m[:-2, 1:-1] + m[2:, 1:-1]
               + m[1:-1, :-2] + m[1:-1, 2:])
        s = float(lap.var())
        beste = max(beste, s)
        stolpe = "#" * min(60, int(s / max(beste, 1) * 60))
        print(f"{s:8.0f}  {stolpe}", flush=True)
        time.sleep(0.7)
except KeyboardInterrupt:
    print(f"\nbeste: {beste:.0f}")
    sys.exit(0)
