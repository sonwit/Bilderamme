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
ANALYZE = os.path.join(BASE_DIR, "birdnet_analyze.py")
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
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/status"):
            return self._reply(200, {**_state, "queue": _jobs.qsize()})
        return self._reply(404, {"ok": False, "message": "Ukjent endepunkt."})

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path.rstrip("/") != "/upload":
            return self._reply(404, {"ok": False, "message": "Ukjent endepunkt."})
        if TOKEN and query.get("token", [None])[0] != TOKEN:
            return self._reply(401, {"ok": False, "message": "Mangler eller feil token."})

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
