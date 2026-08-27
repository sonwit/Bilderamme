#!/usr/bin/env python3
"""
push_to_frame.py — send an already-rendered frame.bin to Fugleramme's
ESP32-S3 e-Paper display over HTTP.

Runs on the HOME SERVER (192.168.1.38), right after generate_daily_image.py
has written frame.bin. It does NOT do any image processing — frame.bin is
already in the exact format the firmware expects (960 000 bytes, 1200x1600
panel, 2 px/byte, palette BLACK 0x0 WHITE 0x1 YELLOW 0x2 RED 0x3 BLUE 0x5
GREEN 0x6) — this script just POSTs the bytes to the board.

The board's firmware (workspace/fugleramme/firmware/indoor_frame/indoor_frame.ino)
is a small HTTP server that listens for:
    POST /display   body = exactly 960000 raw bytes -> drawn on the panel

It does NOT poll or fetch frame.bin itself — the previous setup that got a
test image on screen worked by pushing to it (send_to_frame.py from the Mac).
This script is the same push, automated from cron on the server instead of
being run by hand from the Mac.

Usage:
    python3 push_to_frame.py
    python3 push_to_frame.py --frame /opt/fugleramme/www/frame.bin --host 192.168.1.50
    FRAME_HOST=192.168.1.50 python3 push_to_frame.py

Cron (after generate_daily_image.py, logging both to the same file):
    7 7 * * * cd /opt/fugleramme && \
        /usr/bin/python3 generate_daily_image.py >> logs/daily.log 2>&1 && \
        /usr/bin/python3 push_to_frame.py        >> logs/daily.log 2>&1

Notes:
- Default host is the mDNS name "fugleramme.local", NOT a fixed IP. The board
  gets its address from DHCP and it HAS changed under us: 19-26 Aug 2026 this
  push failed eight days running with [Errno 113] No route to host while the
  image was generated and archived every morning as usual — nothing looked
  broken except logs/daily.log. The name follows the board; an IP does not.
  Resolving .local needs avahi-daemon + libnss-mdns on Linux (macOS/iOS do it
  via Bonjour). The home server has both since 26 Aug. On a server without
  them, pass an IP with --host / FRAME_HOST instead.
- KNOWN FIRMWARE QUIRK (confirmed 2026-07-21, fixed 2026-08-27): indoor_frame.ino
  used to call client.print(...) followed immediately by client.stop() with no
  flush/delay in between. That made the ESP32 send a TCP reset instead of a
  clean close while we were still reading the HTTP response — even though the
  full 960000-byte body was already received and the panel was drawing fine.
  The firmware now does client.flush(); delay(5); before every stop(), so this
  should no longer happen — but a board running older firmware still will, and
  the handling below stays: a failure while SENDING (couldn't connect, upload
  itself errored) is a real failure and is retried; a reset/error while READING
  the response, *after* the body was fully handed off, is logged as "sent,
  unconfirmed" and treated as success — retrying that would just make the board
  redraw the same image for no reason.
- Retries (send-phase failures only) a few times with a delay, because the
  board can be briefly unreachable right after waking from deep sleep or
  while a previous refresh is still drawing (~20-35s).
- Exits non-zero only on a real failure, so cron's output (captured above
  into daily.log) reflects genuine problems — check that log if a day's
  image doesn't show up.
"""
import argparse
import http.client
import os
import sys
import time

FB_SIZE = 960_000
DEFAULT_FRAME = "/opt/fugleramme/www/frame.bin"
DEFAULT_HOST = os.environ.get("FRAME_HOST", "fugleramme.local")
RETRIES = 4
RETRY_DELAY = 20  # seconds


class SendFailed(Exception):
    """Raised when we couldn't even hand the body off to the board — real failure, worth retrying."""


def post_frame(frame_path, host, timeout=60):
    """Returns ('confirmed', status, body) or ('unconfirmed', None, reason).
    Raises SendFailed if the request itself (connect + upload) didn't go through."""
    with open(frame_path, "rb") as f:
        data = f.read()
    if len(data) != FB_SIZE:
        raise ValueError(
            f"{frame_path} er {len(data)} byte, forventet {FB_SIZE} — "
            "avbryter (ville tegnet feil/forskjoevet bilde)."
        )

    hostname = host.split("://", 1)[-1].rstrip("/")
    conn = http.client.HTTPConnection(hostname, timeout=timeout)
    try:
        conn.request(
            "POST",
            "/display",
            body=data,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
            },
        )
    except OSError as e:
        conn.close()
        raise SendFailed(str(e)) from e

    # Kroppen er naa fullt sendt til brettet. Alt herfra er bare forsoek paa
    # aa lese svaret -- se "KNOWN FIRMWARE QUIRK" i modul-docstringen.
    try:
        resp = conn.getresponse()
        body = resp.read().decode(errors="replace").strip()
        status = resp.status
        conn.close()
        return "confirmed", status, body
    except (http.client.HTTPException, OSError) as e:
        conn.close()
        return "unconfirmed", None, str(e)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frame", default=DEFAULT_FRAME, help=f"Sti til frame.bin (default {DEFAULT_FRAME})")
    ap.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Rammens adresse (default {DEFAULT_HOST}; sett FRAME_HOST env for aa overstyre uten flagg)",
    )
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--retry-delay", type=int, default=RETRY_DELAY)
    args = ap.parse_args()

    if not os.path.exists(args.frame):
        print(f"FEIL: fant ikke {args.frame}", file=sys.stderr)
        sys.exit(1)

    last_err = None
    for attempt in range(1, args.retries + 1):
        try:
            outcome, status, info = post_frame(args.frame, args.host)
        except (SendFailed, ValueError) as e:
            last_err = str(e)
            print(f"Forsoek {attempt}/{args.retries} feilet under sending: {last_err}", file=sys.stderr)
            if attempt < args.retries:
                time.sleep(args.retry_delay)
            continue

        if outcome == "confirmed" and status == 200:
            print(f"OK: sendt {args.frame} til {args.host} (forsoek {attempt}, bekreftet) — {info}")
            sys.exit(0)
        if outcome == "confirmed":
            last_err = f"HTTP {status}: {info}"
            print(f"Forsoek {attempt}/{args.retries} feilet: {last_err}", file=sys.stderr)
            if attempt < args.retries:
                time.sleep(args.retry_delay)
            continue

        # outcome == "unconfirmed": bildet ble sendt fullt ut, men vi fikk ikke
        # lest svaret (kjent snurr i firmwaren). Regn som suksess -- ikke
        # gjoer om hele opplastingen paa nytt for det.
        print(
            f"OK (ubekreftet): {args.frame} ble sendt fullt ut til {args.host}, men fikk ikke "
            f"lest svaret fra brettet ({info}). Dette er en kjent snurr i firmwaren "
            "(client.stop() uten flush) og skjer ofte selv om bildet tegnes helt fint. "
            "Sjekk skjermen visuelt om du er usikker."
        )
        sys.exit(0)

    print(f"FEIL: klarte ikke sende bildet etter {args.retries} forsoek. Siste feil: {last_err}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
