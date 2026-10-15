#!/usr/bin/env python3
"""
lydkvalitet.py — kjenner igjen opptak som bare er sus fra mikrofonen.

Fra 9. okt 2026 ~07:00 tok utedelen opp jevn bredbaandsstoey paa rundt
-35 dBFS doegnet rundt. Natten laa foer paa -55 til -65. BirdNET hoerte en
dvergspett i suset paa nesten hvert opptak (35-59 om dagen), og veggen viste
bare dvergspett i en uke uten at noe varslet. Kjeden virket; det var lyden
som var borte. Mistanken er fukt i mikrofonen.

Kjennetegnet er at suset er baade HOEYT og FLATT. Flatt maales som crest:
forholdet mellom 99,9-persentilen av utslaget (peak999) og RMS, i dB. Hvit
stoey ligger paa ~10 dB (3,3 sigma). Maalt per opptak:

                         RMS (median)   crest (median)
    1.-7. okt (frisk)    -60 til -53    13-18 dB
    9.-15. okt (hveser)  -36 til -28    11-12 dB
    8. okt (regn?)       -34            19 dB  -- hoeyt, men ikke flatt

Et stoeygulv er noe som varer, saa et opptak doemmes sammen med naboene sine
(NABO paa hver side, samme dag): det er sus naar det selv ligger over
HVES_RMS, og medianen i vinduet ligger over HVES_RMS med crest under
HVES_CREST. Ett opptak alene holder ikke. 7. okt kl. 09:39 laa et
dompapopptak (0,93) paa -41 dBFS med crest 12 -- en naer fugl kan ogsaa vaere
jevn -- men naboene laa paa -55, og dompapen skal staa.

Saa artene. 12. okt kl. 14:59 og 15:59 loeftet noe crest til 14-15 oppaa
suset, og dvergspetten slapp gjennom i de to opptakene, mot 56 i sus. En art
som er hoert i sus i minst SUS_ANDEL_ART av oektene sine, er hoert i suset,
og holdes utenfor selv om et par opptak slapp gjennom.

Maalt mot en kopi av observations.jsonl 15. okt 2026: 56-61 av 61 opptak
per dag er sus 9.-15. okt (30/30 den 13., 16/16 den 15.), og ingen 1.-8.
okt. Artslisten for 1.-7. okt blir noeyaktig som foer; 9.-15. okt er
dvergspetten (og én fuglekonge 12. okt) borte og listen tom. Bakover i
historikken treffer det 1-7 enkeltopptak paa fem dager i august, med crest
helt ned i 4-7 (ikke fuglelyd), og ingen dag er i naerheten av daarlig.

Standardbibliotek, saa vakt.py og --dag-modusen i birdnet_analyze.py kan
bruke den fra hvilket miljoe som helst.

    python3 lydkvalitet.py data/observations.jsonl            # dag for dag
    python3 lydkvalitet.py data/observations.jsonl 2026-10-01 # fra en dato
"""

from __future__ import annotations

import math
import os
import statistics

HVES_RMS = float(os.environ.get("HVES_RMS_DBFS", "-45"))
HVES_CREST = float(os.environ.get("HVES_CREST_DB", "14"))

NABO = int(os.environ.get("HVES_NABO", "2"))
SUS_ANDEL_ART = float(os.environ.get("HVES_SUS_ANDEL_ART", "0.8"))

# Hvor stor del av dagens opptak som maa vaere sus foer siden sier at lyden er
# daarlig. 9.-15. okt var andelen 92-100 %; ellers hoeyst 21 % (5. aug).
DAARLIG_ANDEL = float(os.environ.get("HVES_DAARLIG_ANDEL", "0.5"))

# Vakta ser paa de siste N opptakene (to-tre timer i vaaken tid). Medianen
# taaler at en skjaere eller et vindkast loefter noen av dem, og at
# nedre kvartil ligger tett under medianen er det som sier «stoeygulv».
# 9.-15. okt: median -36 til -26, avstand til nedre kvartil 0,1-0,5 dB.
VAKT_N = int(os.environ.get("HVES_VAKT_N", "12"))
VAKT_SPREDNING = float(os.environ.get("HVES_VAKT_SPREDNING_DB", "2"))


def crest_db(audio: dict) -> float | None:
    """peak999 / RMS i dB, eller None naar maalingene mangler."""
    rms, peak = audio.get("rms"), audio.get("peak999")
    if not rms or not peak or rms <= 0 or peak <= 0:
        return None
    return 20 * math.log10(peak / rms)


def sus(lyd: list[dict | None]) -> list[bool]:
    """Ett flagg per opptak: er det bare sus? lyd er audio-feltene for ÉN
    dags opptak i tidsrekkefoelge. Mangler maalingene, er svaret nei: et
    gammelt opptak uten tall skal ikke forsvinne."""
    lyd = [a or {} for a in lyd]
    ut = []
    for i, a in enumerate(lyd):
        vindu = lyd[max(0, i - NABO):i + NABO + 1]
        rms = [b["rms_dbfs"] for b in vindu if b.get("rms_dbfs") is not None]
        crest = [c for c in (crest_db(b) for b in vindu) if c is not None]
        ut.append(bool(
            a.get("rms_dbfs") is not None and a["rms_dbfs"] > HVES_RMS
            and rms and crest
            and statistics.median(rms) > HVES_RMS
            and statistics.median(crest) < HVES_CREST))
    return ut


def hoert_i_suset(i_sus: int, rene: int) -> bool:
    """Er arten hoert i suset? i_sus og rene er antall oekter av hvert slag."""
    return i_sus > 0 and i_sus >= SUS_ANDEL_ART * (i_sus + rene)


def stoeygulv(observasjoner: list[dict]) -> dict | None:
    """Status for de siste VAKT_N opptakene, eller None hvis det er for faa.

    hveser er sann naar medianen av RMS ligger over HVES_RMS, nedre kvartil
    ligger tett under medianen (lite variasjon mellom opptakene) og crest-
    medianen er under HVES_CREST (lite variasjon inne i hvert opptak)."""
    siste = [o.get("audio") or {} for o in observasjoner][-VAKT_N:]
    rms = sorted(a["rms_dbfs"] for a in siste if a.get("rms_dbfs") is not None)
    crest = [c for c in (crest_db(a) for a in siste) if c is not None]
    if len(rms) < VAKT_N or len(crest) < VAKT_N:
        return None
    median = statistics.median(rms)
    spredning = median - rms[len(rms) // 4]
    crest_median = statistics.median(crest)
    return {
        "n": len(rms),
        "median": round(median, 1),
        "spredning": round(spredning, 1),
        "crest": round(crest_median, 1),
        "hveser": (median > HVES_RMS and spredning < VAKT_SPREDNING
                   and crest_median < HVES_CREST),
    }


def lyd_daarlig(birds: dict) -> bool:
    """Sier birds.json at de fleste av dagens opptak bare er sus?"""
    n = birds.get("sessions_today", 0)
    return bool(n) and birds.get("hvesende_opptak", 0) / n >= DAARLIG_ANDEL


def main() -> int:
    import json
    import sys
    from collections import defaultdict

    if len(sys.argv) < 2:
        print("Bruk: lydkvalitet.py observations.jsonl [FRA-DATO]",
              file=sys.stderr)
        return 2
    fra = sys.argv[2] if len(sys.argv) > 2 else ""
    per_dag: dict[str, list[dict]] = defaultdict(list)
    with open(sys.argv[1], encoding="utf-8") as f:
        for rad in f:
            try:
                o = json.loads(rad)
            except ValueError:
                continue
            if o.get("date", "") >= fra:
                per_dag[o["date"]].append(o)
    for dag in sorted(per_dag):
        obs = sorted(per_dag[dag], key=lambda o: o.get("recorded_at", ""))
        n_hves = sum(sus([o.get("audio") for o in obs]))
        rms = [o["audio"]["rms_dbfs"] for o in obs
               if (o.get("audio") or {}).get("rms_dbfs") is not None]
        print(f"{dag}  {n_hves:2d}/{len(obs):2d} sus  "
              f"RMS-median {statistics.median(rms) if rms else float('nan'):6.1f}"
              + ("  LYDEN ER DAARLIG" if lyd_daarlig(
                  {"sessions_today": len(obs), "hvesende_opptak": n_hves})
                 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
