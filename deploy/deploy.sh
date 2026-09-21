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

# Undersidene til webappen (helse.py, fugler.py, dag.py) importeres av
# frame_server.py ved foerste kall. Blir de liggende igjen paa Macen, svarer
# /helse, /fugler og /dag med 500 mens resten av serveren ser frisk ut.
echo "→ Kopierer python-scripts til $SERVER:$DEST ..."
scp "$HERE/tools/generate_daily_image.py" \
    "$HERE/tools/push_to_frame.py" \
    "$HERE/tools/frame_server.py" \
    "$HERE/tools/birdnet_analyze.py" \
    "$HERE/tools/bird_stats.py" \
    "$HERE/tools/audio_ingest.py" \
    "$HERE/tools/daily_panel.py" \
    "$HERE/tools/compose_branch.py" \
    "$HERE/tools/compose_hero.py" \
    "$HERE/tools/render_daily_panel.py" \
    "$HERE/tools/render_panel_png.py" \
    "$HERE/tools/prepare_plates.py" \
    "$HERE/tools/fetch_plates.py" \
    "$HERE/tools/bird_names.py" \
    "$HERE/tools/helse.py" \
    "$HERE/tools/fugler.py" \
    "$HERE/tools/dag.py" \
    "$SERVER:$DEST/"

# Plansjebiblioteket: kildeskanningene, den faste grenen og 1:1-fuglene med
# fotpunktene sine. Ikke plates/vasket/ (lages av prepare_plates.py) og ikke
# plates/dagens-* (byttes hver morgen) — de skal ikke overskrives herfra.
if [ -d "$HERE/plates" ]; then
  echo "→ Kopierer plansjer og fugler ..."
  ssh "$SERVER" "mkdir -p $DEST/plates/fugler"
  scp "$HERE"/plates/*.jpg "$HERE"/plates/gren.png "$HERE"/plates/plates.json \
      "$SERVER:$DEST/plates/" 2>/dev/null || true
  scp "$HERE"/plates/fugler/* "$SERVER:$DEST/plates/fugler/" 2>/dev/null || true
  # Malenes JSON, men ikke bildene deres. Plassene i JSON-en er haandsatt og
  # hoerer sammen med koden -- en ny plass-type i compose_branch.py er
  # verdiloes hvis malen som bruker den blir liggende igjen paa Macen.
  # Bakgrunnsbildene lages derimot én gang med --lag-mal og skal ikke sendes
  # fram og tilbake for hver deploy.
  ssh "$SERVER" "mkdir -p $DEST/plates/maler"
  scp "$HERE"/plates/maler/*.json "$SERVER:$DEST/plates/maler/" 2>/dev/null || true
fi

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
  # NB: pkill -f matcher mot hele kommandolinja, og HELE dette skriptet er
  # kommandolinja til skallet som kjoerer det. [f]-trikset skjuler moensteret,
  # men meldingen under inneholdt det samme navnet uforkledd -- saa pkill drepte
  # sitt eget deploy-skall, rett etter «systemctl stop» og foer «start».
  # Deployen doede der hver gang, og lot frame-serveren ligge nede (sist
  # 1. september 21:46). Derfor: finn PID-ene, hopp over vaart eget skall, drep
  # resten. Da kan meldingene si hva de vil.
  drept=""
  for pid in $(pgrep -f "[f]rame_server\.py" 2>/dev/null); do
    if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then kill "$pid" 2>/dev/null && drept=ja || true; fi
  done
  if [ -n "$drept" ]; then
    echo "  (stoppet en manuelt startet frame_server.py)"; sleep 1
  fi

  # Drep en evt. manuelt startet audio_ingest som ellers holder port 8091.
  drept=""
  for pid in $(pgrep -f "[a]udio_ingest\.py" 2>/dev/null); do
    if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then kill "$pid" 2>/dev/null && drept=ja || true; fi
  done
  if [ -n "$drept" ]; then
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
