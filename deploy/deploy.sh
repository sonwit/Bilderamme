#!/usr/bin/env bash
#
# deploy.sh — kopier de nyeste scriptene til hjemmeserveren og restart tjenesten.
# Kjør fra Macen (fra hvor som helst):
#     ~/workspace/fugleramme/deploy/deploy.sh
#
# Overstyr serveren ved behov:
#     FUGLE_SERVER=bruker@192.168.1.38 ~/workspace/fugleramme/deploy/deploy.sh
#
# NB: rører ALDRI /opt/fugleramme/frame_server.env (hemmelighetene dine) eller
# noe i www/ (bildene). Kun python-scriptene + systemd-tjenesten oppdateres.

set -euo pipefail

SERVER="${FUGLE_SERVER:-bruker@192.168.1.38}"
DEST="/opt/fugleramme"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ Kopierer python-scripts til $SERVER:$DEST ..."
scp "$HERE/tools/generate_daily_image.py" \
    "$HERE/tools/push_to_frame.py" \
    "$HERE/tools/frame_server.py" \
    "$HERE/tools/birdnet_analyze.py" \
    "$HERE/tools/bird_stats.py" \
    "$HERE/tools/audio_ingest.py" \
    "$SERVER:$DEST/"

echo "→ Kopierer systemd-tjenestefiler ..."
scp "$HERE/deploy/fugleramme-frame-server.service" "$SERVER:/tmp/fugleramme-frame-server.service"
scp "$HERE/deploy/fugleramme-audio-ingest.service" "$SERVER:/tmp/fugleramme-audio-ingest.service"

echo "→ Installerer tjeneste + restarter (ber om sudo-passord på serveren) ..."
ssh -t "$SERVER" '
  set -e
  sudo mv /tmp/fugleramme-frame-server.service /etc/systemd/system/fugleramme-frame-server.service
  sudo mv /tmp/fugleramme-audio-ingest.service /etc/systemd/system/fugleramme-audio-ingest.service
  sudo systemctl daemon-reload
  sudo systemctl enable fugleramme-frame-server 2>/dev/null || true
  sudo systemctl enable fugleramme-audio-ingest 2>/dev/null || true

  # Stopp tjenesten rent foerst (unngaar auto-restart-kapploep), ...
  sudo systemctl stop fugleramme-frame-server 2>/dev/null || true
  # ... og drep en evt. MANUELT startet server som ellers holder gammel kode + port 8090.
  # [f]-trikset gjoer at pkill ikke treffer sitt eget deploy-skall.
  if pkill -f "[f]rame_server\.py" 2>/dev/null; then
    echo "  (stoppet en manuelt startet frame_server.py)"; sleep 1
  fi

  # Drep en evt. manuelt startet audio_ingest som ellers holder port 8091.
  if pkill -f "[a]udio_ingest\.py" 2>/dev/null; then
    echo "  (stoppet en manuelt startet audio_ingest.py)"; sleep 1
  fi

  sudo systemctl start fugleramme-frame-server
  sudo systemctl restart fugleramme-audio-ingest
  sleep 1
  echo "Status:"
  systemctl is-active fugleramme-frame-server || true
  systemctl is-active fugleramme-audio-ingest || true
'
echo "✓ Deploy ferdig — tjenesten kjoerer nyeste kode."
