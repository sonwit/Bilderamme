#!/usr/bin/env python3
"""
Fugleramme: kjoer BirdNET paa en WAV-fil, logg observasjonen og oppdater
dagens artsliste (birds.json).

Kjoeres paa hjemmeserveren i BirdNET-venvet (IKKE bilde-venvet):
    /opt/fugleramme/venv-birdnet/bin/python /opt/fugleramme/birdnet_analyze.py <fil.wav>

Med lat/lon + dato filtrerer BirdNET paa arter som er plausible her (Hagen,
Norge) akkurat naa -- saa vi slipper tropiske feiltreff.

Skriver TO ting:

1. `data/observations.jsonl` -- én linje per analysert opptak, for godt.
   Inneholder arter MED antall deteksjoner, lydnivaa (peak/RMS/klipping) og
   Pi-helse (spenning, throttling, temperatur, wifi). Dette er datagrunnlaget
   for `bird_stats.py` -- baade for aa se hvilke fugler vi hoerer og for aa se
   om plassering, mikrofonnivaa og stroemforsyning holder maal.

2. `birds.json` -- DAGENS aggregerte artsliste (union av alle oekter i dag,
   ikke bare siste opptak). Det er denne generate_daily_image.py leser.
   Skrives alltid, ogsaa naar dagen enda ikke har noen arter.

Pi-en kan legge ved en helse-sidecar `<samme-navn>.json` sammen med WAV-en;
den flettes inn i observasjonen hvis den finnes.
"""

import datetime
import json
import os
import sys
import tempfile

import numpy as np
import soundfile as sf
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

# Samme koordinater som generate_daily_image.py (her).
# Kartverket-koordinater for hagen. Se generate_daily_image.py.
LAT, LON = 59.98, 10.93
MIN_CONF = float(os.environ.get("BIRDNET_MIN_CONF", "0.25"))

BASE_DIR = os.environ.get("FUGLE_DIR", "/opt/fugleramme")
BIRDS_JSON = os.environ.get("BIRDS_JSON", os.path.join(BASE_DIR, "birds.json"))
DATA_DIR = os.environ.get("FUGLE_DATA_DIR", os.path.join(BASE_DIR, "data"))
OBS_LOG = os.path.join(DATA_DIR, "observations.jsonl")

# Gamle opptak i audio/ slettes etter saa mange dager. Selve observasjonene
# (JSONL) beholdes for godt -- de er smaa. Serveren har rikelig plass, saa vi
# holder paa lyden en stund: da kan vi lytte gjennom et rart treff i ettertid.
AUDIO_KEEP_DAYS = int(os.environ.get("AUDIO_KEEP_DAYS", "21"))

# INMP441-mikrofonen tar opp LAVT nivaa (se «Fallgruver» i handoff-dokumentet).
# Er opptaket svakere enn dette, peak-normaliseres det foer analyse -- BirdNET
# treffer mye bedre paa normalisert signal (verifisert: 0 treff -> treff).
NORMALIZE_BELOW_PEAK = float(os.environ.get("BIRDNET_NORM_PEAK", "0.5"))


# ----------------------------------------------------------------------
# Lyd: maal nivaa og normaliser svake opptak
# ----------------------------------------------------------------------

def audio_metrics(wav_path: str) -> dict:
    """Nivaamaal for opptaket. Brukes til aa se om mikrofonplasseringen og
    forsterkningen er fornuftig: for lavt => fuglene drukner i stoeygulvet,
    klipping => for hoyt/vind paa membranen."""
    data, sr = sf.read(wav_path, dtype="float64")
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.abs(data).max()) if len(data) else 0.0
    # Robust peak: 99,9-persentilen. ESP32-firmwarens hoeypassfilter lager ett
    # enkelt fullskala-sample ved opptaksstart; absolutt peak paa 1.0 ville
    # ellers slaatt av normaliseringen for opptak som reelt er stille.
    peak999 = float(np.quantile(np.abs(data), 0.999)) if len(data) else 0.0
    rms = float(np.sqrt((data ** 2).mean())) if len(data) else 0.0
    clipped = float((np.abs(data) > 0.99).mean() * 100) if len(data) else 0.0
    return {
        "duration_s": round(len(data) / sr, 1) if sr else 0.0,
        "samplerate": int(sr),
        "peak": round(peak, 4),
        "peak999": round(peak999, 4),
        "rms": round(rms, 5),
        # dBFS er lettere aa resonnere om enn raa RMS: -60 er nesten stille,
        # -30 er bra nivaa for et feltopptak, 0 er full skala.
        "rms_dbfs": round(20 * np.log10(rms), 1) if rms > 0 else -99.0,
        "clipped_pct": round(clipped, 3),
    }


def _maybe_normalize(wav_path: str, peak: float) -> str:
    """Peak-normaliser svake opptak til en midlertidig fil. Returnerer stien
    som skal analyseres (originalen hvis nivaaet alt er greit, eller noe gaar
    galt -- et unormalisert forsoek er bedre enn ingen analyse)."""
    if peak <= 0 or peak >= NORMALIZE_BELOW_PEAK:
        return wav_path
    try:
        data, sr = sf.read(wav_path)
        data = data * (0.89 / peak)
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="norm_")
        os.close(fd)
        sf.write(tmp, data, sr)
        print(f"Svakt opptak (peak {peak:.3f}) — normalisert foer analyse.")
        return tmp
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: normalisering feilet ({e}) — analyserer originalen.",
              file=sys.stderr)
        return wav_path


# ----------------------------------------------------------------------
# BirdNET
# ----------------------------------------------------------------------

def analyze(wav_path: str, peak: float) -> list[dict]:
    """Kjoer BirdNET paa fila (peak-normalisert ved behov). Returnerer arter
    dedupet paa navn, med beste konfidens og antall 3-sekunders vinduer arten
    ble hoert i (`detections` -- en grov aktivitets-/naerhetsindikator)."""
    norm_path = _maybe_normalize(wav_path, peak)
    analyzer = Analyzer()
    rec = Recording(
        analyzer, norm_path,
        lat=LAT, lon=LON,
        date=datetime.date.today(),
        min_conf=MIN_CONF,
    )
    try:
        rec.analyze()
    finally:
        if norm_path != wav_path:
            os.remove(norm_path)

    best: dict[str, dict] = {}
    for d in rec.detections:
        name = d["common_name"]
        s = best.setdefault(name, {
            "common_name": name,
            "scientific_name": d["scientific_name"],
            "confidence": 0.0,
            "detections": 0,
        })
        s["detections"] += 1
        s["confidence"] = max(s["confidence"], round(float(d["confidence"]), 3))
    return sorted(best.values(), key=lambda s: (-s["confidence"], -s["detections"]))


# ----------------------------------------------------------------------
# Observasjonslogg + dagens aggregat
# ----------------------------------------------------------------------

def read_health_sidecar(wav_path: str) -> dict:
    """Pi-en legger ved <opptak>.json med spenning/throttling/temp/wifi."""
    side = os.path.splitext(wav_path)[0] + ".json"
    try:
        with open(side) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: kunne ikke lese helse-sidecar: {e}", file=sys.stderr)
        return {}


def append_observation(wav_path: str, species: list[dict], audio: dict,
                       health: dict) -> dict:
    """Legg oekten til i observations.jsonl (append-only, én linje per opptak)."""
    now = datetime.datetime.now()
    # Tidspunktet i filnavnet (fugl_YYYYmmdd_HHMMSS.wav) er naar opptaket ble
    # GJORT -- det er det vi vil ha i statistikken, ikke naar serveren rakk aa
    # analysere det (en koe kan gjoere de to veldig forskjellige).
    recorded = now
    base = os.path.basename(wav_path)
    try:
        stamp = base.replace("fugl_", "").rsplit(".", 1)[0]
        recorded = datetime.datetime.strptime(stamp, "%Y%m%d_%H%M%S")
    except ValueError:
        pass

    obs = {
        "recorded_at": recorded.strftime("%Y-%m-%dT%H:%M:%S"),
        "analyzed_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "date": recorded.strftime("%Y-%m-%d"),
        "hour": recorded.hour,
        "file": base,
        "audio": audio,
        "species": species,
        "pi": health,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OBS_LOG, "a") as f:
        f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    return obs


def _iter_observations():
    try:
        with open(OBS_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return


def write_todays_birds() -> dict:
    """Aggreger ALLE dagens oekter til birds.json (det generate_daily_image.py
    leser). En fugl hoert kl. 05 skal fortsatt telle for bildet kl. 07."""
    today = datetime.date.today().isoformat()
    agg: dict[str, dict] = {}
    sessions = 0
    for obs in _iter_observations():
        if obs.get("date") != today:
            continue
        sessions += 1
        t = obs.get("recorded_at", "")[11:16]
        for s in obs.get("species", []):
            name = s["common_name"]
            a = agg.setdefault(name, {
                "common_name": name,
                "scientific_name": s.get("scientific_name", ""),
                "confidence": 0.0,
                "detections": 0,
                "sessions": 0,
                "first_heard": t,
                "last_heard": t,
            })
            a["confidence"] = max(a["confidence"], s.get("confidence", 0.0))
            a["detections"] += s.get("detections", 1)
            a["sessions"] += 1
            a["first_heard"] = min(a["first_heard"], t) if a["first_heard"] else t
            a["last_heard"] = max(a["last_heard"], t)

    # Sorter paa hvor godt belagt arten er i dag: flest oekter foerst, saa
    # antall deteksjoner, saa konfidens. Bildet velger blant toppen av denne.
    species = sorted(agg.values(),
                     key=lambda s: (-s["sessions"], -s["detections"], -s["confidence"]))

    payload = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "date": today,
        "sessions_today": sessions,
        "species": species,
    }
    # Atomisk skriving saa generate_daily_image.py aldri leser en halvskrevet fil.
    tmp = BIRDS_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, BIRDS_JSON)
    return payload


def prune_old_audio(wav_path: str) -> None:
    """Slett WAV-er (og sidecars) eldre enn AUDIO_KEEP_DAYS i opptaksmappa.
    Feiler stille -- opprydding skal aldri velte selve analysen."""
    try:
        audio_dir = os.path.dirname(os.path.abspath(wav_path))
        cutoff = datetime.datetime.now().timestamp() - AUDIO_KEEP_DAYS * 86400
        removed = 0
        for name in os.listdir(audio_dir):
            if not name.lower().endswith((".wav", ".json")):
                continue
            p = os.path.join(audio_dir, name)
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
                removed += 1
        if removed:
            print(f"Ryddet bort {removed} gamle filer i audio/")
    except Exception as e:  # noqa: BLE001
        print(f"ADVARSEL: opprydding i audio/ feilet: {e}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) != 2:
        print("Bruk: birdnet_analyze.py <fil.wav>", file=sys.stderr)
        return 2
    wav_path = sys.argv[1]
    if not os.path.isfile(wav_path):
        print(f"Finner ikke fila: {wav_path}", file=sys.stderr)
        return 1

    audio = audio_metrics(wav_path)
    species = analyze(wav_path, audio["peak999"])
    health = read_health_sidecar(wav_path)
    append_observation(wav_path, species, audio, health)
    today = write_todays_birds()

    print(f"=== {len(species)} arter i {os.path.basename(wav_path)} "
          f"({audio['duration_s']}s, RMS {audio['rms_dbfs']} dBFS, "
          f"peak {audio['peak']:.3f}) ===")
    for s in species:
        print(f"  {s['common_name']:30s} ({s['scientific_name']})  "
              f"{s['confidence']:.2f}  x{s['detections']}")
    print(f"I dag totalt: {len(today['species'])} arter "
          f"paa {today['sessions_today']} opptak -> {BIRDS_JSON}")

    prune_old_audio(wav_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
