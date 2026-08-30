#!/usr/bin/env python3
"""
vakt.py — sier fra naar noe er galt med Fugleramme. Ellers helt stille.

Kjoeres av cron hvert kvarter. Skriver bare naar det er noe aa si, saa en tom
logg betyr at alt er i orden.

STILLHET er det viktigste den ser etter, og den vanskeligste aa oppdage. Da
utedelen laa femten timer i bootloader 29.-30. august merket ingen det: det
kom jo ingen nye filer aa reagere paa, og en vakt som bare ser paa nye data er
blind for at dataene har sluttet aa komme.

Varsling: uten VARSEL_URL skriver den bare til stdout, som cron legger i
loggen og helsesida viser. Med VARSEL_URL sendes meldinga dit -- ntfy.sh er
det enkleste (POST med teksten i kroppen, appen paa telefonen, ingen konto):

    VARSEL_URL=https://ntfy.sh/et-langt-navn-ingen-gjetter

Alt som sendes dit forlater huset, saa velg et navn ingen kommer til aa gjette.
Vil du heller ha e-post, maa serveren ha en SMTP-klient (msmtp) foerst -- den
har ingen i dag.

    python3 vakt.py            # sjekk én gang
    python3 vakt.py --status   # skriv ut alt, ogsaa naar det er bra
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import urllib.request

BASE = os.environ.get("FUGLE_DIR", os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(BASE, "audio")
WWW = os.environ.get("FRAME_OUTPUT_DIR", os.path.join(BASE, "www"))
VARSEL_URL = os.environ.get("VARSEL_URL", "")
# Hvor lenge det kan gaa mellom opptak i vaaken tid foer noe er galt. Planen
# gir 10-20 minutter, saa 45 er romslig nok til aa taale et par bomskudd.
STILLE_MIN = int(os.environ.get("VAKT_STILLE_MIN", "45"))
# Vaaken tid. Utenfor dette sover utedelen, og stillhet er meningen.
FRA_TIME, TIL_TIME = 5, 22
# Under dette trapper lytteplanen seg ned av seg selv -- verdt aa vite om.
LAV_VOLT = float(os.environ.get("VAKT_LAV_VOLT", "3.80"))
# Sida paa veggen skal fornyes to ganger i doegnet. Er den eldre enn dette,
# har begge kjoeringene feilet.
GAMMEL_SIDE_T = int(os.environ.get("VAKT_GAMMEL_SIDE_T", "26"))
# Ikke mas: samme varsel gjentas hoeyst én gang i timen.
GJENTA_MIN = int(os.environ.get("VAKT_GJENTA_MIN", "60"))
TILSTAND = os.path.join(BASE, ".vakt-tilstand.json")


def _siste_opptak() -> tuple[datetime.datetime | None, dict]:
    filer = sorted(glob.glob(os.path.join(AUDIO, "fugl_*.json")))
    if not filer:
        return None, {}
    navn = os.path.basename(filer[-1])
    try:
        t = datetime.datetime.strptime(navn[5:20], "%Y%m%d_%H%M%S")
    except ValueError:
        return None, {}
    try:
        with open(filer[-1]) as f:
            return t, json.load(f)
    except (OSError, ValueError):
        return t, {}


def sjekk(naa: datetime.datetime) -> list[tuple[str, str]]:
    """Liste med (noekkel, melding). Noekkelen brukes til aa unngaa gjentakelse."""
    ut: list[tuple[str, str]] = []
    t, helse = _siste_opptak()

    if t is None:
        ut.append(("ingen-opptak", "Utedelen: ingen opptak i det hele tatt."))
    elif FRA_TIME <= naa.hour < TIL_TIME:
        min_siden = int((naa - t).total_seconds() / 60)
        if min_siden > STILLE_MIN:
            ut.append(("stille",
                       f"Utedelen er stille: {min_siden} min siden siste "
                       f"opptak ({t:%d.%m %H:%M})."))

    volt = helse.get("volt")
    if volt and volt < LAV_VOLT:
        ut.append(("batteri",
                   f"Batteriet er nede i {volt} V — under {LAV_VOLT}, "
                   f"saa lytteplanen trapper seg ned."))

    frame = os.path.join(WWW, "frame.bin")
    if os.path.exists(frame):
        alder = (naa - datetime.datetime.fromtimestamp(
            os.path.getmtime(frame))).total_seconds() / 3600
        if alder > GAMMEL_SIDE_T:
            ut.append(("gammel-side",
                       f"Sida paa veggen er {alder:.0f} timer gammel — "
                       f"begge dagens kjoeringer har feilet."))
    else:
        ut.append(("ingen-side", "www/frame.bin finnes ikke."))
    return ut


def _tilstand() -> dict:
    try:
        with open(TILSTAND) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _varsle(tekst: str) -> None:
    if not VARSEL_URL:
        return
    try:
        req = urllib.request.Request(
            VARSEL_URL, data=tekst.encode("utf-8"),
            headers={"Title": "Fugleramme", "Tags": "warning"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001
        print(f"  (klarte ikke varsle: {str(e)[:90]})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Vakt over Fugleramme.")
    ap.add_argument("--status", action="store_true",
                    help="skriv ut ogsaa naar alt er bra")
    args = ap.parse_args()

    naa = datetime.datetime.now()
    feil = sjekk(naa)
    gammel = _tilstand()
    ny = {}
    nye_meldinger = []

    for noekkel, melding in feil:
        sist = gammel.get(noekkel, 0)
        ny[noekkel] = sist
        if (naa.timestamp() - sist) / 60 > GJENTA_MIN:
            ny[noekkel] = naa.timestamp()
            nye_meldinger.append(melding)

    if nye_meldinger:
        for m in nye_meldinger:
            print(f"{naa:%Y-%m-%d %H:%M}  {m}")
        _varsle("\n".join(nye_meldinger))

    if args.status and not feil:
        t, helse = _siste_opptak()
        print(f"{naa:%Y-%m-%d %H:%M}  alt i orden — siste opptak "
              f"{t:%H:%M} ({helse.get('volt')} V)" if t else "  ingen opptak")

    try:
        with open(TILSTAND, "w") as f:
            json.dump(ny, f)
    except OSError:
        pass
    return 1 if feil else 0


if __name__ == "__main__":
    raise SystemExit(main())
