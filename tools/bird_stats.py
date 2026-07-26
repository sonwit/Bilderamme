#!/usr/bin/env python3
"""
Fugleramme: statistikk over lytteoekten ute.

    /opt/fugleramme/venv-birdnet/bin/python /opt/fugleramme/bird_stats.py
    ... bird_stats.py --days 3
    ... bird_stats.py --day 2026-07-27
    ... bird_stats.py --json          (maskinlesbart, for webapp e.l.)

Leser data/observations.jsonl (skrevet av birdnet_analyze.py) og svarer paa de
tre spoersmaalene vi faktisk lurer paa i innkjoeringsfasen:

  1. Hoerer vi fugler?      -- arter, deteksjoner, doegnrytme
  2. Er plasseringen OK?    -- lydnivaa per oekt, stille/klippede opptak
  3. Holder stroemmen?      -- undervoltage, throttling, temperatur, omstarter

Kun stdlib -- kan kjoeres med hvilket som helst python3 paa serveren.
"""

import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

BASE_DIR = os.environ.get("FUGLE_DIR", "/opt/fugleramme")
OBS_LOG = os.path.join(os.environ.get("FUGLE_DATA_DIR",
                                      os.path.join(BASE_DIR, "data")),
                       "observations.jsonl")

# Grenser for «er dette et brukbart opptak?». RMS i dBFS: under -55 er i
# praksis stillhet (mikrofonen hoerer ikke hagen), over -12 er saa hoyt at vi
# risikerer klipping i vindkast.
QUIET_DBFS = float(os.environ.get("QUIET_DBFS", "-55"))
LOUD_DBFS = float(os.environ.get("LOUD_DBFS", "-12"))


def load(path: str) -> list[dict]:
    obs = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        print(f"Ingen observasjoner enda ({path} finnes ikke).", file=sys.stderr)
    return obs


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def _bar(n: int, scale: float, width: int = 34) -> str:
    return "█" * max(0, min(width, round(n * scale)))


def filter_obs(obs: list[dict], days: int | None, day: str | None) -> list[dict]:
    if day:
        return [o for o in obs if o.get("date") == day]
    if days:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
        return [o for o in obs if o.get("date", "") >= cutoff]
    return obs


def summarize(obs: list[dict]) -> dict:
    """Alt rapporten trenger, i én struktur (ogsaa brukt av --json)."""
    species_sessions: Counter = Counter()
    species_dets: Counter = Counter()
    species_best: dict[str, float] = {}
    species_sci: dict[str, str] = {}
    species_days: defaultdict = defaultdict(set)
    per_day: defaultdict = defaultdict(lambda: {"sessions": 0, "species": set(), "detections": 0})
    per_hour: defaultdict = defaultdict(lambda: {"sessions": 0, "detections": 0, "species": set()})

    levels, quiet, loud, clipped, silent_sessions = [], 0, 0, 0, 0
    undervolt, throttled_now, temps, volts = 0, 0, [], []
    hosts: Counter = Counter()

    for o in obs:
        d, h = o.get("date", "?"), o.get("hour", 0)
        per_day[d]["sessions"] += 1
        per_hour[h]["sessions"] += 1

        sp = o.get("species", [])
        if not sp:
            silent_sessions += 1
        for s in sp:
            name = s["common_name"]
            n = s.get("detections", 1)
            species_sessions[name] += 1
            species_dets[name] += n
            species_best[name] = max(species_best.get(name, 0), s.get("confidence", 0))
            species_sci[name] = s.get("scientific_name", "")
            species_days[name].add(d)
            per_day[d]["species"].add(name)
            per_day[d]["detections"] += n
            per_hour[h]["detections"] += n
            per_hour[h]["species"].add(name)

        a = o.get("audio") or {}
        db = a.get("rms_dbfs")
        if db is not None and db > -99:
            levels.append(db)
            if db < QUIET_DBFS:
                quiet += 1
            if db > LOUD_DBFS:
                loud += 1
        if (a.get("clipped_pct") or 0) > 0.1:
            clipped += 1

        p = o.get("pi") or {}
        if p:
            hosts[p.get("host", "?")] += 1
            if p.get("undervoltage_events"):
                undervolt = max(undervolt, int(p["undervoltage_events"]))
            th = str(p.get("throttled", "0x0"))
            try:
                if int(th, 16) & 0xF:  # lav nibble = skjer NAA
                    throttled_now += 1
            except ValueError:
                pass
            if p.get("temp_c"):
                temps.append(float(p["temp_c"]))
            if p.get("volt"):
                volts.append(float(p["volt"]))

    return {
        "sessions": len(obs),
        "silent_sessions": silent_sessions,
        "species_total": len(species_sessions),
        "species": [
            {
                "common_name": n,
                "scientific_name": species_sci.get(n, ""),
                "sessions": species_sessions[n],
                "detections": species_dets[n],
                "best_confidence": round(species_best.get(n, 0), 3),
                "days": len(species_days[n]),
            }
            for n in sorted(species_sessions,
                            key=lambda n: (-species_sessions[n], -species_dets[n]))
        ],
        "per_day": {d: {"sessions": v["sessions"], "species": len(v["species"]),
                        "detections": v["detections"]}
                    for d, v in sorted(per_day.items())},
        "per_hour": {h: {"sessions": v["sessions"], "detections": v["detections"],
                         "species": len(v["species"])}
                     for h, v in sorted(per_hour.items())},
        "audio": {
            "median_rms_dbfs": round(_median(levels), 1),
            "min_rms_dbfs": round(min(levels), 1) if levels else None,
            "max_rms_dbfs": round(max(levels), 1) if levels else None,
            "quiet_sessions": quiet,
            "loud_sessions": loud,
            "clipped_sessions": clipped,
        },
        "power": {
            "undervoltage_events_max": undervolt,
            "sessions_throttled_now": throttled_now,
            "median_temp_c": round(_median(temps), 1) if temps else None,
            "max_temp_c": round(max(temps), 1) if temps else None,
            "median_volt": round(_median(volts), 2) if volts else None,
            "hosts": dict(hosts),
        },
    }


def report(s: dict) -> None:
    print(f"\n{'=' * 62}\n  FUGLERAMME — lyttestatistikk\n{'=' * 62}")
    print(f"\nOpptak analysert: {s['sessions']}"
          f"   Arter totalt: {s['species_total']}"
          f"   Opptak uten fugl: {s['silent_sessions']}")

    if not s["sessions"]:
        print("\nIngen data enda.\n")
        return

    print(f"\n--- Arter (flest oekter foerst) {'-' * 30}")
    print(f"  {'Art':32s} {'oekter':>6s} {'dets':>6s} {'beste':>6s} {'dager':>6s}")
    for sp in s["species"][:25]:
        print(f"  {sp['common_name']:32s} {sp['sessions']:6d} {sp['detections']:6d} "
              f"{sp['best_confidence']:6.2f} {sp['days']:6d}")
    if not s["species"]:
        print("  (ingen arter registrert — se lydnivaa nedenfor)")

    print(f"\n--- Doegnrytme (deteksjoner per time) {'-' * 24}")
    ph = s["per_hour"]
    mx = max((v["detections"] for v in ph.values()), default=0)
    scale = 34 / mx if mx else 0
    for h in range(24):
        v = ph.get(h) or ph.get(str(h))
        if not v:
            continue
        print(f"  {h:02d}  {v['detections']:5d} {_bar(v['detections'], scale)}"
              f"  ({v['sessions']} opptak, {v['species']} arter)")

    print(f"\n--- Per dag {'-' * 50}")
    for d, v in s["per_day"].items():
        print(f"  {d}   {v['sessions']:3d} opptak   {v['species']:3d} arter   "
              f"{v['detections']:4d} deteksjoner")

    a = s["audio"]
    print(f"\n--- Lydnivaa (plassering/mikrofon) {'-' * 27}")
    print(f"  Median RMS: {a['median_rms_dbfs']} dBFS   "
          f"(spenn {a['min_rms_dbfs']} .. {a['max_rms_dbfs']})")
    print(f"  For stille (< {QUIET_DBFS} dBFS): {a['quiet_sessions']} opptak")
    print(f"  For hoyt   (> {LOUD_DBFS} dBFS): {a['loud_sessions']} opptak")
    print(f"  Med klipping:               {a['clipped_sessions']} opptak")
    if a["median_rms_dbfs"] < QUIET_DBFS:
        print("  ⚠ Nivaaet er gjennomgaaende svaert lavt — vurder aa flytte "
              "mikrofonen naermere foringsplass/busker, eller oeke forsterkning.")

    p = s["power"]
    print(f"\n--- Stroem og helse {'-' * 42}")
    print(f"  Undervoltage-hendelser (maks sett siden boot): "
          f"{p['undervoltage_events_max']}")
    print(f"  Opptak tatt mens Pi-en var throttlet:          "
          f"{p['sessions_throttled_now']}")
    print(f"  Temperatur: median {p['median_temp_c']} °C, maks {p['max_temp_c']} °C")
    if p["hosts"]:
        print(f"  Enheter: {', '.join(f'{k} ({v})' for k, v in p['hosts'].items())}")
    if p["undervoltage_events_max"]:
        print("  ⚠ Undervoltage betyr at 5V-skinna dipper under ~4,63 V — "
              "risiko for SD-korrupsjon. Se docs/Utedel.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Statistikk over fugleopptakene")
    ap.add_argument("--days", type=int, default=7, help="antall dager bakover (standard 7)")
    ap.add_argument("--day", help="kun én dato, YYYY-MM-DD")
    ap.add_argument("--all", action="store_true", help="hele historikken")
    ap.add_argument("--json", action="store_true", help="skriv JSON i stedet for rapport")
    args = ap.parse_args()

    obs = load(OBS_LOG)
    sel = filter_obs(obs, None if args.all else args.days, args.day)
    s = summarize(sel)
    if args.json:
        print(json.dumps(s, indent=2, ensure_ascii=False))
    else:
        report(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
