#!/usr/bin/env python3
"""
audio_ingest.py — HTTP-mottak av fugleopptak fra ESP32-utedelen.

Pi-en brukte scp+ssh; ESP32-en kan ikke det, saa den POST-er WAV-en hit i
stedet. Serveren lagrer fila i audio/ (samme mappe og navnekonvensjon som
foer) og trigger birdnet_analyze.py — resten av pipelinen (observations.jsonl,
birds.json, statistikk) er uendret.

Endepunkter:
  POST /upload?stamp=YYYYmmdd_HHMMSS[&token=...]   body = WAV
       Helse-JSON kan sendes i header X-Fugl-Health -> lagres som sidecar
       (samme rolle som Pi-ens <opptak>.json).
       Svarer 200 umiddelbart; analysen kjoeres i bakgrunnen (én om gangen,
       saa ESP-en slipper aa holde radioen paa mens BirdNET tenker).
  GET  /status                                      hva som skjer / sist skjedde
  GET  /config                                      fjernkonfig til utedelen
                                                    (planen regnes ut her, se under)
  POST /config   body = JSON                        oppdater fjernkonfigen

Fjernkonfig: ESP-en henter GET /config etter hver opplasting og tar verdiene
i bruk fra neste oekt — parametre kan altsaa justeres uten aa hente ned boksen.
Gyldige noekler (alle valgfrie): gain_shift, highpass_hz, rec_seconds,
test_interval_s, dawn_start, dawn_end, dawn_interval_min, day_start, day_end,
og "rev" (heltall — bump den, saa ser du i helse-JSON-ens cfg_rev naar brikken
har plukket opp endringen). Eksempel fra Macen:
  curl -X POST --data '{"rev": 2, "gain_shift": 12}' http://192.168.1.38:8091/config
Lagres i esp_config.json ved siden av scriptet. POST erstatter HELE konfigen
(det som utelates faller tilbake til firmware-standardene ved neste
stroembrudd, ellers beholdes gjeldende verdi paa brikken).

Manuell test:
  curl -X POST --data-binary @test.wav -H 'Content-Type: audio/wav' \\
       'http://192.168.1.38:8091/upload?stamp=20260803_120000'

Miljoevariabler:
  FUGLE_DIR     (/opt/fugleramme)   INGEST_PORT (8091)
  INGEST_TOKEN  valgfri delt hemmelighet — kreves i ?token= hvis satt
  ANALYZE_PY    python som kjoerer analysen (default: samme som denne prosessen,
                dvs. venv-birdnet naar tjenesten kjoerer der)

Kjoer som systemd-tjeneste, se deploy/fugleramme-audio-ingest.service.
"""
from __future__ import annotations

import datetime
import json
import os
import queue
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.environ.get("FUGLE_DIR", "/opt/fugleramme")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
CONFIG_PATH = os.path.join(BASE_DIR, "esp_config.json")
ANALYZE = os.path.join(BASE_DIR, "birdnet_analyze.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lytteplan
except Exception as _e:  # noqa: BLE001
    lytteplan = None
    print(f"ADVARSEL: lytteplan utilgjengelig ({_e}) — /config svarer bare med fila",
          file=sys.stderr)
ANALYZE_PY = os.environ.get("ANALYZE_PY", sys.executable)
PORT = int(os.environ.get("INGEST_PORT", "8091"))
TOKEN = os.environ.get("INGEST_TOKEN")

MAX_BYTES = 64 * 1024 * 1024          # 60 s / 48 kHz / 16-bit er ~5,8 MB
STAMP_RE = re.compile(r"^\d{8}_\d{6}$")

_jobs: "queue.Queue[str]" = queue.Queue()
_state = {"last": "", "received": 0, "analyzed": 0, "failed": 0}


def _worker():
    """Én analyse om gangen — BirdNET-modellen er tung, og ESP-en har alt
    faatt sitt 200 og sover. Koeen toemmes i mottaksrekkefoelge."""
    while True:
        wav = _jobs.get()
        try:
            r = subprocess.run([ANALYZE_PY, ANALYZE, wav],
                               capture_output=True, text=True, timeout=600)
            for line in (r.stdout or "").splitlines():
                print(f"  {line}", flush=True)
            if r.returncode == 0:
                _state["analyzed"] += 1
                _state["last"] = f"analysert: {os.path.basename(wav)}"
            else:
                _state["failed"] += 1
                _state["last"] = f"FEIL i analyse av {os.path.basename(wav)} (kode {r.returncode})"
                print(f"{_state['last']}\n{r.stderr}", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001 — arbeideren skal aldri doe
            _state["failed"] += 1
            _state["last"] = f"FEIL: {e}"
            print(_state["last"], file=sys.stderr, flush=True)
        finally:
            _jobs.task_done()


def siste_volt() -> float | None:
    """Batterispenningen fra den ferskeste helse-sidecaren.

    Utedelen sender den i X-Fugl-Health ved hver opplasting, saa den nyeste
    fila er aldri mer enn én oekt gammel. Finner vi ingen, returnerer vi None
    -- og lytteplanen velger da den forsiktigste trappa. Ukjent batteri skal
    aldri gi den tetteste planen."""
    try:
        filer = [f for f in os.listdir(AUDIO_DIR) if f.endswith(".json")]
        if not filer:
            return None
        nyest = max(filer)          # fugl_YYYYmmdd_HHMMSS.json sorterer kronologisk
        with open(os.path.join(AUDIO_DIR, nyest)) as f:
            v = json.load(f).get("volt")
        return float(v) if v else None
    except Exception:  # noqa: BLE001
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "FugleIngest/1.0"

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/", "/status"):
            return self._reply(200, {**_state, "queue": _jobs.qsize()})
        if path == "/config":
            if TOKEN and parse_qs(parsed.query).get("token", [None])[0] != TOKEN:
                return self._reply(401, {"ok": False, "message": "Mangler eller feil token."})
            cfg = {}
            # Planen foerst, saa den manuelle fila oppaa. Feiler utregningen,
            # skal brikka fortsatt faa et svar -- den er ute i hagen og har
            # ingen annen kilde til en plan.
            if lytteplan is not None:
                try:
                    cfg = lytteplan.plan(datetime.datetime.now(), siste_volt())
                except Exception as e:  # noqa: BLE001
                    print(f"ADVARSEL: lytteplanen feilet ({e}) — bruker bare fila",
                          file=sys.stderr)
            try:
                with open(CONFIG_PATH) as f:
                    cfg.update(json.load(f))
            except FileNotFoundError:
                pass
            except ValueError:
                return self._reply(500, {"ok": False, "message": "esp_config.json er ugyldig JSON."})
            return self._reply(200, cfg)
        return self._reply(404, {"ok": False, "message": "Ukjent endepunkt."})

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if TOKEN and query.get("token", [None])[0] != TOKEN:
            return self._reply(401, {"ok": False, "message": "Mangler eller feil token."})

        if parsed.path.rstrip("/") == "/config":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if 0 < length <= 4096 else b""
            try:
                new_cfg = json.loads(raw)
                assert isinstance(new_cfg, dict)
            except Exception:
                return self._reply(400, {"ok": False, "message": "Body maa vaere et JSON-objekt."})
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(new_cfg, f, indent=2)
            os.replace(tmp, CONFIG_PATH)
            print(f"Fjernkonfig oppdatert: {json.dumps(new_cfg)}", flush=True)
            return self._reply(200, {"ok": True, "config": new_cfg,
                                     "message": "ESP-en plukker den opp etter neste oekt."})

        if parsed.path.rstrip("/") != "/upload":
            return self._reply(404, {"ok": False, "message": "Ukjent endepunkt."})

        stamp = query.get("stamp", [""])[0]
        if not STAMP_RE.match(stamp):
            return self._reply(400, {"ok": False, "message": "stamp maa vaere YYYYmmdd_HHMMSS."})

        length = int(self.headers.get("Content-Length", 0) or 0)
        if not 44 < length <= MAX_BYTES:
            return self._reply(400, {"ok": False, "message": f"Urimelig stoerrelse: {length} byte."})

        data = b""
        while len(data) < length:
            chunk = self.rfile.read(min(1 << 20, length - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) != length or data[:4] != b"RIFF":
            return self._reply(400, {"ok": False, "message": "Ufullstendig eller ikke en WAV."})

        # Samme navnekonvensjon som Pi-en — birdnet_analyze.py leser tidspunktet
        # ut av filnavnet, og statistikken er blind for hvem som tok opp.
        os.makedirs(AUDIO_DIR, exist_ok=True)
        wav_path = os.path.join(AUDIO_DIR, f"fugl_{stamp}.wav")
        tmp = wav_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, wav_path)

        # Helse-sidecar (frivillig): flettes inn i observasjonen av analysen.
        health = self.headers.get("X-Fugl-Health")
        if health:
            try:
                parsed_health = json.loads(health)
                with open(os.path.join(AUDIO_DIR, f"fugl_{stamp}.json"), "w") as f:
                    json.dump(parsed_health, f, ensure_ascii=False)
            except ValueError:
                print(f"ADVARSEL: ugyldig X-Fugl-Health ignorert ({stamp})",
                      file=sys.stderr, flush=True)

        _state["received"] += 1
        _jobs.put(wav_path)
        print(f"Mottatt fugl_{stamp}.wav ({length // 1024} kB) — koe: {_jobs.qsize()}",
              flush=True)
        return self._reply(200, {"ok": True, "file": os.path.basename(wav_path),
                                 "queue": _jobs.qsize()})

    def log_message(self, fmt, *args):
        pass  # vi logger selv — én linje per mottak, ikke per HTTP-detalj


def main():
    threading.Thread(target=_worker, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Fugleramme audio-ingest lytter paa :{PORT} "
          f"(audio: {AUDIO_DIR}, analyse: {ANALYZE_PY}, token: {'ja' if TOKEN else 'nei'})",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
