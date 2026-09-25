#!/usr/bin/env python3
"""
artsstatistikk.py -- hvor mange dager hver art er hoert, til nettsida.

    python3 tools/artsstatistikk.py data/observations.jsonl nettside/statistikk.json

Leser observasjonsloggen (én rad per opptak, se helse.py) og skriver én
JSON med, per art: antall dager arten er hoert, beste sikkerhet, foerste og
siste dag. En dag teller naar arten hadde kommet paa dagens liste: minst
SURE_CONF i ett opptak, eller hoert i to oekter, samme regel som
render_daily_panel bruker. Ingen posisjon, ingen filnavn, ingen opptak: bare
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
from render_daily_panel import SURE_CONF  # noqa: E402


def regn(logg: str) -> dict:
    per_dag: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    beste: dict[str, float] = {}
    dager_med_opptak: set[str] = set()
    with open(logg, encoding="utf-8") as f:
        for rad in f:
            rad = rad.strip()
            if not rad:
                continue
            try:
                o = json.loads(rad)
            except ValueError:
                continue
            dato = o.get("date", "")
            if not dato:
                continue
            dager_med_opptak.add(dato)
            for s in o.get("species", []):
                sci = (s.get("scientific_name") or "").strip()
                if not sci:
                    continue
                c = float(s.get("confidence", 0))
                per_dag[sci][dato].append(c)
                beste[sci] = max(beste.get(sci, 0.0), c)
    arter = {}
    for sci, dager in per_dag.items():
        talte = sorted(d for d, conf in dager.items() if max(conf) >= SURE_CONF or len(conf) >= 2)
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
