#!/usr/bin/env python3
"""
Sjekk av opptaksplanleggeren i utedelens firmware (next_slot).

Planleggeren kan ikke testes der den kjoerer -- den ligger i en ESP32 i hagen,
og feilen den hadde viste seg bare som et moenster i tidsstemplene over timer.
Derfor er den portert hit, og kjoeres mot de driftene vi FAKTISK maalte 29.
august 2026 (audio/*.json, feltet awake_ms mot filnavnets tidsstempel).

Feilen: `if (t > now) return t` godtok et slott som laa sekunder unna.
Deep-sleep-timeren bommer 2-7 % og uforutsigbart, saa naar brikka vaaknet mer
enn en oektlengde for tidlig var den ferdig FOER slottet -- og siktet da paa
det slottet den nettopp hadde dekket.

    python3 test_neste_slott.py
"""

from __future__ import annotations

import datetime

OEKT_S = 65          # opptak + wifi + opplasting, maalt (awake_ms 62-66 s)
MARGIN_MAKS_S = 240  # SLOT_MARGIN_MAX_S i config.h

# Drift maalt 29. august: hvor stor andel av soevnen brikka kuttet.
# 2,5-3,4 % det meste av dagen, men to soevner paa rad bommet over 7 %.
DRIFT = [0.025, 0.033, 0.072, 0.071, 0.027, 0.028, 0.034, 0.030]


def neste_slott(naa: datetime.datetime, steg_min: int, margin: bool) -> datetime.datetime:
    """Porten av next_slot(). margin=False er den gamle oppfoerselen."""
    m = min(steg_min * 30, MARGIN_MAKS_S) if margin else 0
    grense = naa + datetime.timedelta(seconds=m)
    t = naa.replace(minute=0, second=0, microsecond=0)
    for _ in range(24 * 60 // steg_min + 2):
        if t > grense:
            return t
        t += datetime.timedelta(minutes=steg_min)
    raise AssertionError("fant ikke noe slott")


def spill_av(steg_min: int, margin: bool, timer: int = 12) -> tuple[int, int]:
    """Returnerer (antall oekter, antall dubletter) over `timer` timer."""
    naa = datetime.datetime(2026, 8, 29, 9, 0, 0)
    slutt = naa + datetime.timedelta(hours=timer)
    oekter = dubletter = 0
    forrige: datetime.datetime | None = None
    i = 0
    while naa < slutt:
        maal = neste_slott(naa, steg_min, margin)
        # Brikka sover mot `maal`, men timeren kutter soevnen med DRIFT.
        sov = (maal - naa).total_seconds()
        vaakner = naa + datetime.timedelta(seconds=sov * (1 - DRIFT[i % len(DRIFT)]))
        i += 1
        if vaakner >= slutt:
            break
        oekter += 1
        if forrige and (vaakner - forrige).total_seconds() < 5 * 60:
            dubletter += 1
        forrige = vaakner
        naa = vaakner + datetime.timedelta(seconds=OEKT_S)
    return oekter, dubletter


if __name__ == "__main__":
    print(f"  Tolv timer, oekt {OEKT_S} s, drift som maalt 29. august\n")
    print(f"  {'steg':>6s}  {'uten margin (i dag)':>26s}  {'med margin (fikset)':>26s}")
    for steg in (10, 20, 60):
        a_o, a_d = spill_av(steg, margin=False)
        b_o, b_d = spill_av(steg, margin=True)
        print(f"  {steg:4d}m  {a_o:8d} oekter, {a_d:3d} dubletter"
              f"  {b_o:12d} oekter, {b_d:3d} dubletter")

    print("\n  Og med 30 sekunders opptak, som var planen foer vi fant feilen:")
    OEKT_S = 35  # noqa: F811 — samme maaling, kortere opptak
    globals()["OEKT_S"] = 35
    for steg in (10, 20):
        a_o, a_d = spill_av(steg, margin=False)
        b_o, b_d = spill_av(steg, margin=True)
        print(f"  {steg:4d}m  {a_o:8d} oekter, {a_d:3d} dubletter"
              f"  {b_o:12d} oekter, {b_d:3d} dubletter")
