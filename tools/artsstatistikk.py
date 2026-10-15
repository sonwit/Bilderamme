#!/usr/bin/env python3
"""
artsstatistikk.py -- hvor mange dager hver art er hoert, til nettsida.

    python3 tools/artsstatistikk.py data/observations.jsonl nettside/statistikk.json

Leser observasjonsloggen (én rad per opptak, se helse.py) og skriver én
JSON med, per art: antall dager arten er hoert, beste sikkerhet, foerste og
siste dag. En dag teller naar arten hadde kommet paa dagens liste: minst
SURE_CONF i ett opptak, eller hoert i to oekter, samme regel som
render_daily_panel bruker. Opptak som bare er sus fra mikrofonen gir ingen
arter, og en art som nesten bare er hoert i sus teller ikke den dagen, som i
birdnet_analyze.aggregate_day (se lydkvalitet.py). Ingen posisjon, ingen filnavn, ingen opptak: bare
tall per art. Nettsida sorterer biblioteket etter dette.

Standardbibliotek, som resten av serversidene. Fase to: kjoeres paa serveren
etter hver tegning, sammen med eksporten av dagen.
"""

from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lydkvalitet import hoert_i_suset, sus  # noqa: E402
from render_daily_panel import BLOKKERT, SURE_CONF  # noqa: E402


def les_dager(logg: str) -> dict[str, list[dict]]:
    """Observasjonsloggen per dato, hver dag i tidsrekkefoelge."""
    dager: dict[str, list[dict]] = collections.defaultdict(list)
    with open(logg, encoding="utf-8") as f:
        for rad in f:
            rad = rad.strip()
            if not rad:
                continue
            try:
                o = json.loads(rad)
            except ValueError:
                continue
            if o.get("date"):
                dager[o["date"]].append(o)
    for obs in dager.values():
        obs.sort(key=lambda o: o.get("recorded_at", ""))
    return dager


def hoert_per_dag(dager: dict[str, list[dict]]) -> dict[str, dict[str, list[float]]]:
    """Per art og dato: sikkerheten i hvert rene opptak arten var i.

    Opptak som bare er sus, gir ingen arter. 9.-15. okt 2026 hoerte BirdNET
    en dvergspett i suset paa 35-59 opptak om dagen, og statistikken ga den
    en uke med dager. En art som er hoert i sus i de fleste oektene sine,
    er hoert i suset og teller ikke den dagen, ogsaa om et par opptak slapp
    gjennom (12. okt). Samme regel som birdnet_analyze.aggregate_day."""
    per_dag: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for dato, obs in dager.items():
        i_sus: collections.Counter[str] = collections.Counter()
        rene: collections.Counter[str] = collections.Counter()
        for o, er_sus in zip(obs, sus([o.get("audio") for o in obs])):
            for s in o.get("species", []):
                sci = (s.get("scientific_name") or "").strip()
                # Kjente feiltreff (myrrikse, storfugl ...) teller ikke som
                # «hoert»: myrriksa laa fjerde oeverst paa forsiden med 16 dager.
                if not sci or sci in BLOKKERT:
                    continue
                if er_sus:
                    i_sus[sci] += 1
                    continue
                rene[sci] += 1
                per_dag[sci][dato].append(float(s.get("confidence", 0)))
        for sci in rene:
            if hoert_i_suset(i_sus[sci], rene[sci]):
                del per_dag[sci][dato]
    return per_dag


def regn(logg: str) -> dict:
    dager = les_dager(logg)
    dager_med_opptak = set(dager)
    per_dag = hoert_per_dag(dager)
    beste = {sci: max(max(c) for c in d.values()) for sci, d in per_dag.items() if d}
    arter = {}
    for sci, hoert in per_dag.items():
        talte = sorted(d for d, conf in hoert.items() if max(conf) >= SURE_CONF or len(conf) >= 2)
        if not talte:
            continue
        arter[sci] = {"dager": len(talte), "beste": round(beste[sci], 2), "foerst": talte[0], "sist": talte[-1]}
    return {
        "fra": min(dager_med_opptak) if dager_med_opptak else None,
        "til": max(dager_med_opptak) if dager_med_opptak else None,
        "dager_med_opptak": len(dager_med_opptak),
        "terskel": SURE_CONF,
        "arter": dict(sorted(arter.items(), key=lambda x: (-x[1]["dager"], -x[1]["beste"], x[0]))),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    ut = regn(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(ut, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"OK: {len(ut['arter'])} arter, {ut['dager_med_opptak']} dager med opptak "
          f"({ut['fra']} .. {ut['til']}) -> {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
