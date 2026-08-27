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

# Utedelens opptaksplan — MAA holdes i synk med firmware/outdoor_sensor/config.h
# (DAWN_*/DAY_*): dagsang hver halvtime 04:00-08:30, ellers hver hele time
# 09:00-21:00 = 23 oekter per doegn.
#
# Stod tidligere som en per-time-tabell tilpasset den gamle Pi-en (*/20 i
# dagsangen, 31 oekter per doegn). Utedel v2 leverte hver eneste planlagte oekt
# 27.08., men ble maalt mot 31 og fikk "⚠ hull, 76 %". Falskt alarm — planen
# var byttet, ikke dekningen.
DAWN_START_HOUR   = int(os.environ.get("DAWN_START_HOUR", "4"))
DAWN_END_HOUR     = int(os.environ.get("DAWN_END_HOUR", "8"))    # til og med
DAWN_INTERVAL_MIN = int(os.environ.get("DAWN_INTERVAL_MIN", "30"))
DAY_START_HOUR    = int(os.environ.get("DAY_START_HOUR", "9"))
DAY_END_HOUR      = int(os.environ.get("DAY_END_HOUR", "21"))

# Opptaket starter et minutt eller to FOER slottet (08:59 hoerer til 09:00-oekta),
# saa vi runder av i utedelens favoer naar vi teller.
SLOT_SLACK_MIN = 5

# Hvor langt fra et slott et opptak kan ligge og fortsatt regnes som DEN oekta.
# Halve dagsang-intervallet: da kan to opptak aldri havne paa samme slott.
SLOT_MATCH_MIN = 15


def scheduled_slots() -> list[int]:
    """Planlagte oekter i et doegn, som minutter etter midnatt."""
    slots = []
    m = DAWN_START_HOUR * 60
    while m <= DAWN_END_HOUR * 60 + 59:
        slots.append(m)
        m += DAWN_INTERVAL_MIN
    slots += [h * 60 for h in range(DAY_START_HOUR, DAY_END_HOUR + 1)]
    return sorted(set(slots))


def slot_for(minutes: int) -> int | None:
    """Hvilken planlagt oekt hoerer et opptak paa dette klokkeslettet til?

    Returnerer None for opptak som ikke hoerer til planen (kaldstart etter et
    stroembrudd, manuelle oekter fra benken). De teller ikke som dekning, men
    skal heller ikke faa dekningen til aa se ut som over 100 %."""
    best = min(scheduled_slots(), key=lambda m: abs(m - minutes))
    return best if abs(best - minutes) <= SLOT_MATCH_MIN else None


def expected_sessions(date_str: str, now: datetime.datetime,
                      first: datetime.datetime | None = None) -> int:
    """Forventet antall opptak for en dato.

    To justeringer, ellers loeper dekningen alltid under 100 %:
      * innevaerende dag: bare oekter som ER passert
      * foerste datoen med data: bare oekter etter at foerste opptak kom, siden
        planen ikke fantes foer den."""
    slots = scheduled_slots()
    if date_str == now.date().isoformat():
        slots = [m for m in slots if m <= now.hour * 60 + now.minute]
    if first and date_str == first.date().isoformat():
        start = first.hour * 60 + first.minute - SLOT_SLACK_MIN
        slots = [m for m in slots if m >= start]
    return len(slots)


DATA_DIR = os.environ.get("FUGLE_DATA_DIR", os.path.join(BASE_DIR, "data"))

# Hjerteslag skrives hvert 15. min. Er det mer enn dette mellom to linjer, var
# Pi-en borte (stroemmen tok slutt, eller den restartet).
HEARTBEAT_GAP_MIN = float(os.environ.get("HEARTBEAT_GAP_MIN", "25"))


def load_heartbeats() -> list[dict]:
    """Les alle heartbeat-*.log i data/. CSV: tid,uptime,throttled,uv,temp,wifi."""
    beats = []
    try:
        names = [n for n in os.listdir(DATA_DIR) if n.startswith("heartbeat-")]
    except FileNotFoundError:
        return beats
    for name in names:
        try:
            with open(os.path.join(DATA_DIR, name)) as f:
                for line in f:
                    p = line.strip().split(",")
                    if len(p) < 6:
                        continue
                    try:
                        beats.append({
                            "t": datetime.datetime.fromisoformat(p[0]),
                            "uptime_s": int(p[1]),
                            "throttled": p[2],
                            "uv": int(p[3]),
                            "host": name[len("heartbeat-"):-len(".log")],
                        })
                    except (ValueError, IndexError):
                        continue
        except OSError:
            continue
    return sorted(beats, key=lambda b: b["t"])


def find_outages(beats: list[dict]) -> list[dict]:
    """Finn periodene der Pi-en var borte. Et hull mellom to hjerteslag betyr
    at den ikke kjoerte. Er uptime LAVERE etter hullet, har den startet paa
    nytt (stroembrudd) -- ellers stoppet bare cron/klokka et blaff."""
    outages = []
    for a, b in zip(beats, beats[1:]):
        gap_min = (b["t"] - a["t"]).total_seconds() / 60
        if gap_min > HEARTBEAT_GAP_MIN:
            outages.append({
                "from": a["t"].strftime("%Y-%m-%d %H:%M"),
                "to": b["t"].strftime("%Y-%m-%d %H:%M"),
                "minutes": round(gap_min),
                "rebooted": b["uptime_s"] < a["uptime_s"],
                # Natt = 21-06. Det er da batteriet er alene om jobben.
                "at_night": a["t"].hour >= 21 or a["t"].hour < 6,
            })
    return outages


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
    per_day: defaultdict = defaultdict(lambda: {"sessions": 0, "species": set(), "detections": 0,
                                               "slots": set()})
    per_hour: defaultdict = defaultdict(lambda: {"sessions": 0, "detections": 0, "species": set()})

    levels, quiet, loud, clipped, silent_sessions = [], 0, 0, 0, 0
    undervolt, throttled_now, temps, volts = 0, 0, [], []
    hosts: Counter = Counter()

    for o in obs:
        d, h = o.get("date", "?"), o.get("hour", 0)
        per_day[d]["sessions"] += 1
        try:
            t = datetime.datetime.fromisoformat(o["recorded_at"])
            slot = slot_for(t.hour * 60 + t.minute)
            if slot is not None:
                per_day[d]["slots"].add(slot)
        except (ValueError, KeyError, TypeError):
            pass
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

    # --- omstarter og undervoltage paa tvers av oppstarter -----------------
    # `undervoltage_events` teller siden BOOT. Restarter Pi-en (typisk fordi
    # batteriet gikk tomt) nullstilles telleren -- saa vi kan ikke bare ta
    # maks. Vi deler i boot-oekter (uptime som gaar NED = omstart) og summerer
    # maks fra hver oekt.
    reboots = 0
    seq = sorted((o for o in obs if o.get("pi", {}).get("uptime_s") is not None),
                 key=lambda o: o.get("recorded_at", ""))
    prev_up, boot_max = None, 0
    for o in seq:
        up = int(o["pi"]["uptime_s"])
        uv = int(o["pi"].get("undervoltage_events") or 0)
        if prev_up is not None and up < prev_up:
            reboots += 1
            undervolt += boot_max     # avslutt forrige boot-oekt
            boot_max = 0
        boot_max = max(boot_max, uv)
        prev_up = up
    undervolt += boot_max

    # Undervoltage per time gir et tall vi kan sammenlikne over tid, uavhengig
    # av hvor mange doegn rapporten dekker.
    span_h = 0.0
    if len(seq) >= 2:
        try:
            t0 = datetime.datetime.fromisoformat(seq[0]["recorded_at"])
            t1 = datetime.datetime.fromisoformat(seq[-1]["recorded_at"])
            span_h = max((t1 - t0).total_seconds() / 3600, 0.0)
        except (ValueError, KeyError):
            pass

    # --- dekning: kom opptakene cron lovte oss? ---------------------------
    now = datetime.datetime.now()
    first_obs = None
    if seq:
        try:
            first_obs = datetime.datetime.fromisoformat(seq[0]["recorded_at"])
        except (ValueError, KeyError):
            pass
    coverage = {}
    for d, v in per_day.items():
        exp = expected_sessions(d, now, first_obs)
        # Dekning = hvor mange av de planlagte oektene som faktisk kom, ikke
        # hvor mange opptak som finnes. Ekstra opptak utenfor planen skal ikke
        # kunne skjule en oekt som mangler.
        got = len(v["slots"])
        coverage[d] = {"expected": exp, "actual": got, "sessions": v["sessions"],
                       "pct": round(100 * got / exp) if exp else None}

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
        "coverage": coverage,
        "power": {
            "undervoltage_events": undervolt,
            "undervoltage_per_hour": round(undervolt / span_h, 2) if span_h else None,
            "reboots": reboots,
            "observed_hours": round(span_h, 1),
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

    print(f"\n--- Per dag (dekning = kom opptakene cron lovte?) {'-' * 12}")
    for d, v in s["per_day"].items():
        c = s["coverage"].get(d, {})
        pct = c.get("pct")
        dek = f"{c.get('actual', 0)}/{c.get('expected', 0)} ({pct}%)" if pct is not None else "-"
        flagg = "  ⚠ hull" if pct is not None and pct < 90 else ""
        print(f"  {d}   {v['species']:3d} arter   {v['detections']:4d} deteksjoner   "
              f"dekning {dek}{flagg}")

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
    print(f"  Undervoltage-hendelser: {p['undervoltage_events']}"
          f"   ({p['undervoltage_per_hour']} per time over {p['observed_hours']} t)")
    print(f"  Omstarter i perioden:   {p['reboots']}")
    print(f"  Opptak tatt mens Pi-en var throttlet: {p['sessions_throttled_now']}")
    print(f"  Temperatur: median {p['median_temp_c']} °C, maks {p['max_temp_c']} °C")
    if p["hosts"]:
        print(f"  Enheter: {', '.join(f'{k} ({v})' for k, v in p['hosts'].items())}")

    # --- overlevde den natta? ---------------------------------------------
    beats = load_heartbeats()
    outages = find_outages(beats)
    night_out = [o for o in outages if o["at_night"]]
    print(f"\n--- Nattoverlevelse (hjerteslag hvert 15. min) {'-' * 16}")
    if not beats:
        print("  Ingen hjerteslag enda — kommer fra og med i natt.")
    else:
        print(f"  Hjerteslag: {len(beats)} stk, "
              f"{beats[0]['t']:%Y-%m-%d %H:%M} → {beats[-1]['t']:%Y-%m-%d %H:%M}")
        if not outages:
            print("  ✓ Ingen avbrudd — Pi-en har vaert oppe hele perioden.")
        else:
            for o in outages[-8:]:
                natt = " NATT" if o["at_night"] else ""
                boot = "omstart" if o["rebooted"] else "kun opphold"
                print(f"  ✗ Borte {o['minutes']:4d} min: "
                      f"{o['from']} → {o['to']}  ({boot}){natt}")
            if night_out:
                verst = max(night_out, key=lambda o: o["minutes"])
                print(f"  → {len(night_out)} nattavbrudd, lengste "
                      f"{verst['minutes']} min fra {verst['from']}")

    # --- konklusjon: skal vi bytte maskinvare? ----------------------------
    print(f"\n--- Vurdering {'-' * 48}")
    tot_exp = sum(c["expected"] for c in s["coverage"].values())
    tot_act = sum(c["actual"] for c in s["coverage"].values())
    # Klampes til 100: manuelle testopptak teller ogsaa med i `actual`, og
    # «267 % dekning» sier ingenting fornuftig om stroemsituasjonen.
    dek = min(100, round(100 * tot_act / tot_exp)) if tot_exp else None

    if dek is None:
        print("  For lite data enda.")
    elif dek >= 95 and not p["reboots"]:
        print(f"  ✓ Stroem: dekning {dek} % og ingen omstarter — riggen holder.")
    elif dek >= 80:
        print(f"  ~ Stroem: dekning {dek} %, {p['reboots']} omstarter — "
              "grensetilfelle. Se hvilke timer som mangler nedenfor.")
    else:
        print(f"  ✗ Stroem: bare {dek} % av opptakene kom inn "
              f"({p['reboots']} omstarter) — riggen holder IKKE. "
              "Bytt til Pi Zero 2W, eller styrk panel/batteri/kabel.")

    # NB: bare uttal deg om natta naar vi FAKTISK har hjerteslag fra natta.
    # Ellers ville rapporten gitt gronn lampe etter to slag paa ettermiddagen.
    night_beats = [b for b in beats if b["t"].hour >= 21 or b["t"].hour < 6]
    newest = max((b["t"] for b in beats), default=None)
    stale = (datetime.datetime.now() - newest).days if newest else None
    if stale is not None and stale > 3:
        # Utedel v2 (ESP32) skriver ingen hjerteslag — de siste er fra Pi-en.
        # Uten denne sjekken doemmer vi natta paa maanedsgamle tall.
        print(f"  … Natt: ingen ferske hjerteslag (siste {newest:%Y-%m-%d}, "
              f"{stale} doegn siden). Utedel v2 sender ikke hjerteslag — bruk "
              "\"volt\" i helse-JSON-ene i stedet.")
    elif night_out:
        lengste = max(o["minutes"] for o in night_out)
        print(f"  ✗ Natt: {len(night_out)} avbrudd i moerket, lengste {lengste} min "
              "— batteriet holder ikke gjennom natta.")
    elif len(night_beats) >= 20:   # ~5 timer moerke daekket
        print("  ✓ Natt: ingen avbrudd — batteriet holder saa langt "
              "(sjekk igjen etter en graavaersdag).")
    else:
        print("  … Natt: ikke nok hjerteslag fra moerket enda — svar i morgen tidlig.")

    if p["undervoltage_events"]:
        print(f"  ⚠ Undervoltage: 5V-skinna dipper under ~4,63 V "
              f"({p['undervoltage_per_hour']}/time) — risiko for SD-korrupsjon. "
              "Mistenk foerst USB-kabelen (tynn/lang), saa panel/batteri.")

    # Bare doem plasseringen paa opptak fra dagsangen (03-08). Midt paa dagen i
    # slutten av juli er hagen stille uansett -- null arter da sier ingenting
    # om hvor mikrofonen staar.
    ph = s["per_hour"]
    dawn = sum((ph.get(h) or ph.get(str(h)) or {}).get("sessions", 0)
               for h in range(3, 9))
    if s["species_total"] == 0 and dawn >= 10:
        a = s["audio"]
        if a["median_rms_dbfs"] > QUIET_DBFS:
            print(f"  ✗ Fugler: null arter paa {dawn} opptak i dagsangen, tross "
                  "brukbart lydnivaa — mikrofonen staar sannsynligvis for "
                  "langt fra der fuglene er.")
        else:
            print("  ✗ Fugler: null arter OG svaert lavt lydnivaa — "
                  "sjekk mikrofon/kabling foerst.")
    elif s["species_total"] == 0:
        print(f"  … Fugler: ingen arter enda, men bare {dawn} opptak i "
              "dagsangen (03-08) — for tidlig aa si noe. Svar i morgen.")
    elif s["species_total"]:
        print(f"  ✓ Fugler: {s['species_total']} arter hoert — "
              "lyttedelen fungerer.")
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
