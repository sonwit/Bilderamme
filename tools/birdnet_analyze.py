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

# numpy, soundfile og birdnetlib lastes foerst naar de trengs. --dag bygger
# bare en birds.json ut av observasjonsloggen -- ren tekst, ingen lyd -- og
# skal kunne kjoeres fra bildemiljoeet, som ikke har lydavhengighetene.

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

# Smellet i starten. 233 av 293 opptak siden 19.08.2026 begynner med et
# klippet smell paa opptil ett sekund (maalt 02.09), og alle opptak under
# 22 °C i boksen har det. Mest sannsynlig mikrofonen som ikke er vaaken --
# eller fuktig -- naar I2S starter. Smellet gir ingen BirdNET-treff i seg
# selv, men det oedelegger nivaamaalingene: peak, klipping og RMS beskriver
# smellet, ikke opptaket. Klipper foerste sekund mer enn terskelen, kuttes
# de foerste SMELL_KUTT_S sekundene foer maaling og analyse. Rene opptak
# roeres ikke, saa dette virker likt foer og etter at firmwaren kaster mer
# ved start.
SMELL_TERSKEL_PCT = float(os.environ.get("BIRDNET_SMELL_PCT", "0.05"))
SMELL_KUTT_S = float(os.environ.get("BIRDNET_SMELL_KUTT_S", "1.0"))


# ----------------------------------------------------------------------
# Lyd: maal nivaa og normaliser svake opptak
# ----------------------------------------------------------------------

def kutt_smell(wav_path: str) -> tuple[str, float]:
    """Kutt smellet i starten om det er der. Returnerer (sti som skal
    maales og analyseres, klipping i foerste sekund i prosent). Stien er en
    midlertidig fil naar noe ble kuttet -- den som kaller, rydder."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(wav_path, dtype="float64")
    if data.ndim > 1:
        data = data.mean(axis=1)
    forste = np.abs(data[:sr]) if len(data) else np.zeros(0)
    smell = float((forste > 0.99).mean() * 100) if len(forste) else 0.0
    kutt = int(SMELL_KUTT_S * sr)
    if smell <= SMELL_TERSKEL_PCT or len(data) <= kutt:
        return wav_path, round(smell, 3)
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="kutt_")
    os.close(fd)
    sf.write(tmp, data[kutt:], sr)
    return tmp, round(smell, 3)


def audio_metrics(wav_path: str) -> dict:
    """Nivaamaal for opptaket. Brukes til aa se om mikrofonplasseringen og
    forsterkningen er fornuftig: for lavt => fuglene drukner i stoeygulvet,
    klipping => for hoyt/vind paa membranen."""
    import numpy as np
    import soundfile as sf

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
        import soundfile as sf

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
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

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


def aggregate_day(dag: str) -> dict:
    """Aggreger ALLE oektene paa én dato til formatet birds.json har.

    En fugl hoert kl. 05 skal fortsatt telle for bildet kl. 07. Datoen er et
    argument fordi frokostsida tegner GAARSDAGEN: kl. 07 er bare aatte av
    doegnets 20-30 opptak gjort, og de fanget 22 % av dagens sikre arter --
    paa halvparten av dagene ingen i det hele tatt."""
    agg: dict[str, dict] = {}
    sessions = 0
    tider: list[str] = []
    for obs in _iter_observations():
        if obs.get("date") != dag:
            continue
        sessions += 1
        t = obs.get("recorded_at", "")[11:16]
        if t:
            tider.append(t)
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

    # Opptaksvinduet, ikke deteksjonsvinduet: sida skal kunne si hvilken
    # periode lista faktisk dekker. Tegnes dagen mens den paagaar, slutter
    # vinduet ved siste opptak -- og da er «03:45-15:58» det aerlige svaret.
    periode = f"{min(tider)}–{max(tider)}" if tider else ""

    return {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "date": dag,
        "sessions_today": sessions,
        "periode": periode,
        "species": species,
    }


def skriv_birds(payload: dict, sti: str) -> dict:
    """Atomisk skriving saa ingen leser en halvskrevet fil."""
    tmp = sti + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, sti)
    return payload


def write_todays_birds() -> dict:
    return skriv_birds(aggregate_day(datetime.date.today().isoformat()),
                       BIRDS_JSON)


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


def loes_dag(dag: str) -> str:
    if dag == "i-gaar":
        return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if dag == "i-dag":
        return datetime.date.today().isoformat()
    return dag


def main() -> int:
    # Egen modus: bygg en birds.json for en valgt dato uten aa analysere lyd.
    # daily_panel.py bruker den til frokostsida.
    if len(sys.argv) >= 2 and sys.argv[1] == "--dag":
        if len(sys.argv) != 4:
            print("Bruk: birdnet_analyze.py --dag i-gaar|i-dag|YYYY-MM-DD UT.json",
                  file=sys.stderr)
            return 2
        dag = loes_dag(sys.argv[2])
        p = skriv_birds(aggregate_day(dag), sys.argv[3])
        print(f"{dag}: {len(p['species'])} arter paa {p['sessions_today']} "
              f"opptak ({p['periode'] or 'ingen'}) -> {sys.argv[3]}")
        # Ingen opptak den dagen: si fra, saa cron kan falle tilbake.
        return 0 if p["sessions_today"] else 1

    if len(sys.argv) != 2:
        print("Bruk: birdnet_analyze.py <fil.wav>", file=sys.stderr)
        return 2
    wav_path = sys.argv[1]
    if not os.path.isfile(wav_path):
        print(f"Finner ikke fila: {wav_path}", file=sys.stderr)
        return 1

    kilde, smell = kutt_smell(wav_path)
    try:
        audio = audio_metrics(kilde)
        # Smellet loggfoeres selv om det er kuttet: det er selve sporet etter
        # en mikrofon som ikke var klar, og det vi vil se mot temperatur og
        # doegn i statistikken.
        audio["smell_pct"] = smell
        audio["kuttet_s"] = SMELL_KUTT_S if kilde != wav_path else 0.0
        species = analyze(kilde, audio["peak999"])
    finally:
        if kilde != wav_path:
            os.remove(kilde)
    health = read_health_sidecar(wav_path)
    append_observation(wav_path, species, audio, health)
    today = write_todays_birds()

    print(f"=== {len(species)} arter i {os.path.basename(wav_path)} "
          f"({audio['duration_s']}s, RMS {audio['rms_dbfs']} dBFS, "
          f"peak {audio['peak']:.3f}"
          + (f", smell {smell:.2f} % -> kuttet {audio['kuttet_s']:.0f} s"
             if audio["kuttet_s"] else "") + ") ===")
    for s in species:
        print(f"  {s['common_name']:30s} ({s['scientific_name']})  "
              f"{s['confidence']:.2f}  x{s['detections']}")
    print(f"I dag totalt: {len(today['species'])} arter "
          f"paa {today['sessions_today']} opptak -> {BIRDS_JSON}")

    prune_old_audio(wav_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
