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
    # Flere utsnitt: ett lite felt rundt hver mater. Bevegelse maales i hvert
    # for seg, og bildet som sendes dekker alle. Er lista tom, brukes roi.
    # Innfoert 3. sep 2026: ett stort utsnitt rundt to matere tok med saa mye
    # loev at vinden utloeste hvert kvarter.
    "roier": [],
    # Bevegelsen maa vare saa mange rammer paa rad. Et vindkast er borte paa
    # neste ramme; en fugl blir sittende.
    "varighet": 2,
    # Hvor mye en piksel (0-255) maa endre seg for aa telle som endret ...
    "diff_terskel": 28,
    # ... og hvor stor andel av utsnittet som maa ha endret seg. Med
    # utsnittet rundt materen (ca 230x180 px i 1152x648) er 0,3 % ~120
    # piksler -- en meis paa ni meter er ~10x10 der. Sensorstoey er mindre,
    # men greiner i vind er stoerre: se --vis foer terskelen settes.
    "bevegelse_andel": 0.003,
    # Blokkmaalet (se bevegelse()): blokkstoerrelse i px i den lille
    # stroemmen, hvor stor del av blokka som maa ha endret seg, og hvor mange
    # tette blokker som utloeser. En meis paa 7 m er ~12x12 px i 1152x648,
    # altsaa 2-4 blokker paa 6 px.
    "blokk": 5,
    "blokk_andel": 0.5,
    "blokker_min": 3,
    # Omrammingen rundt de tette blokkene maa vaere mindre enn denne andelen
    # av utsnittet -- ellers er det lys eller vind, ikke én fugl.
    "klynge_maks": 0.25,
    # Endrer mer enn dette av utsnittet seg paa én gang, er det lyset.
    "bevegelse_maks": 0.08,
    # Sekunder mellom to bilder, og mellom to rammer i overvaakingen.
    "pause_s": 15,
    "ramme_s": 0.5,
    # Gjennomsnittlig lysstyrke (0-255) i utsnittet under dette = natt.
    "lys_min": 25,
    # Fast fokusavstand i meter til materen. 0 = kontinuerlig autofokus, som
    # gjerne laaser seg paa vindusglasset.
    "fokus_m": 0,
    # Stort bilde og hvor mye ekstra rundt utsnittet som sendes med. Full
    # opploesning: materen er 8-10 m unna og 60 px bred i et 2304-bilde, saa
    # en meis blir 25 px. Med 4608 blir den 50, og det er utsnittet som
    # sendes, ikke hele bildet.
    # Camera Module 3 Wide: [4608, 2592]. HQ-kameraet: [4056, 3040].
    "bilde": [4608, 2592],
    # Den lille stroemmen bevegelsen maales i. 640x360 var for grovt paa
    # den avstanden: en meis ble 5 px og druknet i stoey.
    "lores": [1152, 648],
    "margin": 0.08,
    "jpeg_kvalitet": 88,
    # 0, 90, 180 eller 270 grader med klokka. Kameraet staar gjerne opp ned
    # eller paa siden naar kabelen skal ut av bildet -- 3. sep 2026 kom foerste
    # bilde med gresset oeverst, og HQ-kameraet med stammen vannrett. 180 tas
    # av sensoren; 90 og 270 snus i numpy, og utsnittet (roi) gjelder det
    # snudde bildet.
    "roter": 0,
}


def les_konfig() -> dict:
    cfg = dict(STANDARD)
    try:
        with open(KONFIG) as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    return cfg


def _mtime(sti: str) -> float:
    try:
        return os.path.getmtime(sti)
    except OSError:
        return 0.0


def logg(msg: str) -> None:
    print(f"{datetime.datetime.now():%H:%M:%S} {msg}", flush=True)


# ----------------------------------------------------------------------
# Kamera
# ----------------------------------------------------------------------

def start_kamera(cfg: dict):
    from picamera2 import Picamera2

    cam = Picamera2()
    w, h = cfg["bilde"]
    _LORES[:] = [int(cfg["lores"][0]), int(cfg["lores"][1])]
    from libcamera import Transform
    snu = int(cfg["roter"]) == 180
    _ROT[0] = int(cfg["roter"]) % 360
    konf = cam.create_still_configuration(
        main={"size": (w, h)},
        lores={"size": tuple(cfg["lores"]), "format": "YUV420"},
        transform=Transform(hflip=snu, vflip=snu),
        buffer_count=2)
    cam.configure(konf)
    cam.start()
    # Bare Camera Module 3 har autofokus. HQ-kameraet har fokusring paa
    # linsa (se fokus.py), og aa sette AfMode paa det gir feil.
    if "AfMode" in cam.camera_controls:
        from libcamera import controls
        if cfg["fokus_m"]:
            # LensPosition er i dioptrier (1/m). Fast fokus slaar autofokusen,
            # som ellers gjerne finner vindusglasset mer interessant enn materen.
            cam.set_controls({"AfMode": controls.AfModeEnum.Manual,
                              "LensPosition": 1.0 / float(cfg["fokus_m"])})
        else:
            cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
    time.sleep(1.5)  # eksponering og hvitbalanse trenger noen rammer
    return cam


_LORES = [640, 360]
_ROT = [0]


def _snu(a: np.ndarray) -> np.ndarray:
    """90/270 grader med klokka i numpy. 180 tar sensoren selv."""
    if _ROT[0] == 90:
        return np.ascontiguousarray(np.rot90(a, -1))
    if _ROT[0] == 270:
        return np.ascontiguousarray(np.rot90(a, 1))
    return a


def graa(cam) -> np.ndarray:
    """Y-planet fra den lille stroemmen, som float for differansen."""
    arr = cam.capture_array("lores")
    w, h = _LORES
    return _snu(arr[:h, :w]).astype(np.float32)


def utsnitt(a: np.ndarray, roi: list[float]) -> np.ndarray:
    h, w = a.shape[:2]
    x0, y0, x1, y1 = roi
    return a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def utsnittene(cfg: dict) -> list[list[float]]:
    return list(cfg["roier"]) or [cfg["roi"]]


def bevegelse(forrige: np.ndarray, naa: np.ndarray, cfg: dict) -> tuple[float, int]:
    """Stoerste (andel, tette blokker) over alle utsnittene."""
    beste = (0.0, 0)
    for roi in utsnittene(cfg):
        a, t = _bevegelse_i(forrige, naa, cfg, roi)
        if t > beste[1] or (t == beste[1] and a > beste[0]):
            beste = (a, t)
    return beste


def _bevegelse_i(forrige: np.ndarray, naa: np.ndarray, cfg: dict,
                 roi: list[float]) -> tuple[float, int]:
    """(andel endrede piksler i utsnittet, antall tette blokker).

    Andelen alene skiller ikke fugl fra vind: 3. sep 2026 laa den paa 1-8 %
    i granbaret uten en fugl i naerheten. Vind flytter tusen bladkanter litt
    hver; en fugl flytter ett sammenhengende omraade mye. Derfor deles
    utsnittet i blokker paa `blokk` px, og en blokk teller som tett naar mer
    enn halvparten av pikslene i den endret seg. Bladverk gir null tette
    blokker, en meis paa materen gir noen."""
    d = np.abs(utsnitt(naa, roi) - utsnitt(forrige, roi))
    endret = d > cfg["diff_terskel"]
    b = int(cfg["blokk"])
    h, w = endret.shape
    h2, w2 = h - h % b, w - w % b
    if h2 < b or w2 < b:
        return float(endret.mean()), 0
    blokker = endret[:h2, :w2].reshape(h2 // b, b, w2 // b, b).mean(axis=(1, 3))
    tette = blokker > cfg["blokk_andel"]
    n = int(tette.sum())
    if n == 0:
        return float(endret.mean()), 0
    # En fugl er én klynge. Ligger de tette blokkene spredt over hele
    # utsnittet, er det et vindkast eller en sky som gikk for sola (11:26
    # 3. sep: 50 tette blokker, ingen fugl). Maalet er hvor stor del av
    # utsnittet klyngens omramming dekker.
    ys, xs = np.nonzero(tette)
    boks = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    spredning = boks / tette.size
    if spredning > cfg["klynge_maks"]:
        return float(endret.mean()), 0
    return float(endret.mean()), n


def ta_bilde(cam, cfg: dict) -> bytes:
    """Stort bilde, beskaaret til utsnittet med margin, som JPEG-byte."""
    from PIL import Image

    arr = _snu(cam.capture_array("main"))
    im = Image.fromarray(arr)
    alle = utsnittene(cfg)
    x0 = min(r[0] for r in alle); y0 = min(r[1] for r in alle)
    x1 = max(r[2] for r in alle); y1 = max(r[3] for r in alle)
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
        "roi": utsnittene(cfg),
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
    logg(f"starter: server {cfg['server']}, utsnitt {utsnittene(cfg)}, "
         f"blokker >= {cfg['blokker_min']} i {cfg['varighet']} rammer, "
         f"rotasjon {cfg['roter']}")
    cam = start_kamera(cfg)
    konfig_mtime = _mtime(KONFIG)

    if args.en:
        g = graa(cam)
        lys = float(utsnitt(g, utsnittene(cfg)[0]).mean())
        jpeg = ta_bilde(cam, cfg)
        ok = last_opp(cfg, jpeg, meta_for(cam, 0.0, lys, cfg) | {"test": True})
        return 0 if ok else 1

    forrige = graa(cam)
    sist_bilde = 0.0
    paa_rad = 0
    while True:
        time.sleep(cfg["ramme_s"])
        # Konfigurasjonen leses paa nytt naar fila endres, saa felt og
        # terskler kan justeres uten aa restarte tjenesten (som krever sudo).
        # Bildestoerrelse og rotasjon gjelder foerst ved neste start.
        m = _mtime(KONFIG)
        if m != konfig_mtime:
            konfig_mtime = m
            ny = les_konfig()
            for k in ("bilde", "lores", "roter"):
                ny[k] = cfg[k]
            cfg = ny
            logg(f"konfig lest paa nytt: utsnitt {utsnittene(cfg)}, "
                 f"blokker >= {cfg['blokker_min']} i {cfg['varighet']} rammer")
        naa = graa(cam)
        lys = float(np.mean([utsnitt(naa, r).mean() for r in utsnittene(cfg)]))
        if lys < cfg["lys_min"]:
            if args.vis:
                logg(f"moerkt ({lys:.0f} < {cfg['lys_min']}), venter")
            time.sleep(60)
            forrige = graa(cam)
            continue
        andel, tette = bevegelse(forrige, naa, cfg)
        forrige = naa
        if args.vis:
            logg(f"bevegelse {andel:.3%}  tette blokker {tette:3d}  lys {lys:.0f}")
            continue
        treff = (cfg["bevegelse_andel"] <= andel <= cfg["bevegelse_maks"]
                 and tette >= cfg["blokker_min"])
        paa_rad = paa_rad + 1 if treff else 0
        if paa_rad < cfg["varighet"]:
            continue
        if time.time() - sist_bilde < cfg["pause_s"]:
            continue
        paa_rad = 0
        logg(f"bevegelse {andel:.2%}, {tette} tette blokker — tar bilde")
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
