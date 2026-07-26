#!/usr/bin/env python3
"""
send_to_frame.py — gjoer et hvilket som helst bilde klart for Fugleramme
og sender det til e-Paper-rammen over WiFi.

Bruk:
    python3 send_to_frame.py bilde.jpg
    python3 send_to_frame.py bilde.jpg --host 192.168.1.50
    python3 send_to_frame.py bilde.jpg --out buffer.bin        # bare lag fila, ikke send

Standard host er http://fugleramme.local (mDNS fra firmwaren).

Krever:  pip install pillow numpy   (bruker http.client fra standardbiblioteket for sending)
"""

import argparse
import sys
import numpy as np
from PIL import Image, ImageOps

# Panelet er 1200x1600, staaende. 2 piksler per byte -> 600 byte/rad.
WIDTH, HEIGHT = 1200, 1600
FB_SIZE = (WIDTH // 2) * HEIGHT  # 960000

# Panelets 6 farger:  (panel-kode, RGB)
#   BLACK 0x0, WHITE 0x1, YELLOW 0x2, RED 0x3, BLUE 0x5, GREEN 0x6
PALETTE = [
    (0x0, (0,   0,   0)),
    (0x1, (255, 255, 255)),
    (0x2, (255, 255, 0)),
    (0x3, (255, 0,   0)),
    (0x5, (0,   0,   255)),
    (0x6, (0,   128, 0)),
]
CODES   = np.array([c for c, _ in PALETTE], dtype=np.uint8)
PAL_RGB = np.array([rgb for _, rgb in PALETTE], dtype=np.float32)


def load_and_fit(path):
    """Aapne bildet, roter etter EXIF, beskjaer/skaler til 1200x1600 (cover)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    # ImageOps.fit = skaler + senter-beskjaer til noeyaktig maal uten forvrengning
    img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.LANCZOS)
    return img


def _nearest_codes(pixels):
    """pixels: (H,W,3) float -> (H,W) panel-koder (naermeste palett-farge)."""
    flat = pixels.reshape(-1, 3)
    d = ((flat[:, None, :] - PAL_RGB[None, :, :]) ** 2).sum(axis=2)
    return CODES[d.argmin(axis=1)].reshape(pixels.shape[0], pixels.shape[1])


# --- Feildiffusjon: sprer avrundingsfeilen til nabopiksler ---
_KERNELS = {
    #            (dx, dy, vekt)
    "floyd":    [(1, 0, 7/16), (-1, 1, 3/16), (0, 1, 5/16), (1, 1, 1/16)],
    "atkinson": [(1, 0, 1/8), (2, 0, 1/8), (-1, 1, 1/8), (0, 1, 1/8), (1, 1, 1/8), (0, 2, 1/8)],
}


def _error_diffuse(img, kernel):
    arr = np.asarray(img, dtype=np.float32).copy()
    H, W, _ = arr.shape
    out = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            old = arr[y, x].copy()
            k = int(np.argmin(((PAL_RGB - old) ** 2).sum(axis=1)))
            out[y, x] = CODES[k]
            err = old - PAL_RGB[k]
            for dx, dy, w in kernel:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    arr[ny, nx] += err * w
    return out


# --- Ordnet dithering: fast terskel-maske, ingen diffusjon (rask, vektorisert) ---
def _bayer_mask(H, W):
    m = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                  [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)
    m = (m + 0.5) / 16.0 - 0.5                      # -> [-0.5, 0.5)
    ry, rx = (H + 3) // 4, (W + 3) // 4
    return np.tile(m, (ry, rx))[:H, :W]


def _bluenoise_mask(H, W):
    rng = np.random.default_rng(0)
    n = rng.random((H, W)).astype(np.float32)
    F = np.fft.fft2(n)
    fy = np.fft.fftfreq(H)[:, None]
    fx = np.fft.fftfreq(W)[None, :]
    F *= np.sqrt(fx**2 + fy**2)                     # hoeypass -> blue-noise-aktig
    bn = np.fft.ifft2(F).real
    bn = (bn - bn.min()) / (bn.max() - bn.min() + 1e-9)
    return (bn - 0.5).astype(np.float32)


def _ordered(img, mask, amplitude=110.0):
    arr = np.asarray(img, dtype=np.float32)
    biased = arr + mask[:, :, None] * amplitude
    return _nearest_codes(biased).astype(np.uint8)


def convert(img, mode):
    """Konverter til panel-koder. mode: none | floyd | atkinson | ordered | bluenoise."""
    H, W = img.size[1], img.size[0]
    if mode == "none":
        return _nearest_codes(np.asarray(img, dtype=np.float32)).astype(np.uint8)
    if mode in _KERNELS:
        return _error_diffuse(img, _KERNELS[mode])
    if mode == "ordered":
        return _ordered(img, _bayer_mask(H, W))
    if mode == "bluenoise":
        return _ordered(img, _bluenoise_mask(H, W))
    raise ValueError(f"Ukjent modus: {mode}")


def pack(indices):
    """Pakk 2 piksler per byte: hoey nibble = venstre piksel. 600 byte/rad."""
    hi = indices[:, 0::2]           # partallskolonner (venstre i paret)
    lo = indices[:, 1::2]           # oddetallskolonner
    packed = (hi << 4) | lo         # (H, W/2)
    return packed.astype(np.uint8).tobytes()


def save_preview(indices, path):
    """Lagre en PNG som viser noeyaktig hvordan bildet blir paa 6-farge-panelet.
    Bruk denne for aa fange stygge bakgrunner (stoey) FOER du sender til rammen."""
    out = np.zeros((indices.shape[0], indices.shape[1], 3), dtype=np.uint8)
    for code, rgb in PALETTE:
        out[indices == code] = rgb
    Image.fromarray(out, "RGB").save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="Bildefil (jpg/png/heic...)")
    ap.add_argument("--host", default="http://fugleramme.local",
                    help="Rammens adresse (default http://fugleramme.local)")
    ap.add_argument("--out", help="Lagre den raa bufferen til fil i stedet for aa sende")
    ap.add_argument("--preview", help="Lagre en PNG av hvordan bildet blir paa panelet (6 farger). Sender ikke.")
    ap.add_argument("--dither", default="atkinson",
                    choices=["none", "floyd", "atkinson", "ordered", "bluenoise"],
                    help="Konverteringsmetode. atkinson=best allrounder (standard, bra paa "
                         "akvarell/foto/tegneserie), none=flat/plakat (djervest for tegneserie), "
                         "bluenoise, ordered, floyd. Standard: atkinson.")
    ap.add_argument("--flat", action="store_true", help="Alias for --dither none (rene flater, plakat-stil).")
    args = ap.parse_args()

    print("Aapner og skalerer til 1200x1600 ...")
    img = load_and_fit(args.image)

    mode = "none" if args.flat else args.dither
    print(f"Konverterer til 6 farger (modus: {mode}) ...")
    idx = convert(img, mode)

    buf = pack(idx)
    assert len(buf) == FB_SIZE, f"Feil bufferstoerrelse: {len(buf)} != {FB_SIZE}"
    print(f"Buffer klar: {len(buf)} byte")

    # Forhaandsvisning: se hvordan det blir paa panelet, uten aa sende
    if args.preview:
        save_preview(idx, args.preview)
        print(f"Forhaandsvisning lagret til {args.preview} (sender ikke)")
        return

    if args.out:
        with open(args.out, "wb") as f:
            f.write(buf)
        print(f"Lagret til {args.out}")
        return

    hostname = args.host.split("://", 1)[-1].rstrip("/")
    print(f"Sender til http://{hostname}/display ...")
    import http.client
    conn = http.client.HTTPConnection(hostname, timeout=120)
    try:
        conn.request("POST", "/display", body=buf,
                     headers={"Content-Type": "application/octet-stream",
                              "Content-Length": str(len(buf))})
    except OSError as e:
        print(f"FEIL: klarte ikke sende til {hostname}: {e}")
        return

    # Bufferet er naa sendt. Firmwaren (indoor_frame.ino) har en kjent snurr:
    # den kaller client.stop() rett etter aa ha skrevet svaret, uten aa
    # flushe foerst -- det gir av og til "connection reset" naar VI proever
    # aa lese svaret, sjoel om bildet ble mottatt og tegnes helt fint. Skill
    # derfor mellom "klarte ikke sende" (over, reell feil) og "sendte, men
    # fikk ikke lest svaret" (under, normalt og ikke noe aa bekymre seg for).
    try:
        resp = conn.getresponse()
        body = resp.read().decode(errors="replace").strip()
        print(f"Svar: {resp.status} {body}")
        if resp.status == 200:
            print("Sendt! Skjermen oppdaterer seg naa (~20-35 sek).")
        conn.close()
    except (http.client.HTTPException, OSError) as e:
        conn.close()
        print(f"Sendt (fikk ikke lest svaret: {e}) — dette er en kjent snurr i "
              "firmwaren og betyr som regel ikke at noe gikk galt. Skjermen "
              "oppdaterer seg naa (~20-35 sek); sjekk den visuelt.")


if __name__ == "__main__":
    main()
