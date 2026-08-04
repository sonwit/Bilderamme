#!/usr/bin/env bash
#
# record_and_upload.sh — fugleramme-utedelens lytteoekt (kjoeres paa Pi-en).
#
# Tar opp fuglelyd med INMP441-mikrofonen, laster opp til hjemmeserveren og
# trigger BirdNET-analysen der (som skriver birds.json + observations.jsonl).
#
# Kjoeres flere ganger om dagen fra cron — se pi/crontab.txt.
# Manuell test:  FUGLE_DURATION=20 /home/bruker/record_and_upload.sh
#
# Designvalg (utedelen gaar paa solcelle + batteri og er tungvint aa naa):
#   * S16_LE i stedet for S32_LE  -> halv filstoerrelse, halv radiotid.
#     INMP441 tar opp lavt uansett, og serveren normaliserer foer analyse.
#   * Opptak til /tmp (tmpfs)     -> ingen SD-slitasje i normaltilfellet.
#   * Koe paa disk ved feil       -> et opptak gaar ikke tapt om wifi/server er
#     nede; det lastes opp ved neste oekt.
#   * Fartsgrense paa scp         -> lavere topplast paa 5V-skinna. Pi-en har
#     hatt undervoltage-dipp, og wifi-sending er akkurat naar de skjer.
#   * Lydkort velges paa NAVN     -> kortnummer kan bytte mellom oppstarter.

set -uo pipefail

SERVER="${FUGLE_SERVER:-bruker@192.168.1.38}"
REMOTE_AUDIO="/opt/fugleramme/audio"
REMOTE_PY="/opt/fugleramme/venv-birdnet/bin/python"
REMOTE_ANALYZE="/opt/fugleramme/birdnet_analyze.py"

DURATION="${FUGLE_DURATION:-60}"        # sekunder opptak
RATE_KBIT="${FUGLE_SCP_LIMIT:-4000}"    # scp-fartsgrense (kbit/s), 0 = av
QUEUE_DIR="${FUGLE_QUEUE:-/home/bruker/queue}"
QUEUE_MAX="${FUGLE_QUEUE_MAX:-60}"      # behold maks saa mange opptak i koen
WORK_DIR="/tmp/fugleopptak"
LOCK="/tmp/fugleopptak.lock"

log() { echo "[$(date '+%F %T')] $*"; }

# Én oekt av gangen. Blir en oekt hengende (wifi borte), skal ikke neste
# cron-kjoering stable seg oppaa og spise stroem.
exec 9>"$LOCK"
if ! flock -n 9; then
  log "En annen oekt kjoerer allerede — hopper over."
  exit 0
fi

mkdir -p "$WORK_DIR" "$QUEUE_DIR"

# --- finn mikrofonen paa navn (kortnummer er ikke garantert stabilt) --------
find_device() {
  if [ -n "${FUGLE_MIC:-}" ]; then echo "$FUGLE_MIC"; return; fi
  local name
  name="$(arecord -l 2>/dev/null | sed -n 's/^card [0-9]*: \([^ ]*\) .*voicehat.*/\1/ip' | head -1)"
  if [ -n "$name" ]; then echo "plughw:CARD=$name"; else echo "plughw:1"; fi
}

# --- helsedata: blir med opptaket til serveren og havner i statistikken -----
health_json() {
  local throttled volt temp up wifi_dbm uv model load
  throttled="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
  volt="$(vcgencmd measure_volts 2>/dev/null | sed 's/volt=//;s/V//')"
  temp="$(vcgencmd measure_temp 2>/dev/null | sed "s/temp=//;s/'C//")"
  up="$(cut -d. -f1 /proc/uptime)"
  wifi_dbm="$(awk 'NR==3{gsub(/\./,"",$4); print $4}' /proc/net/wireless 2>/dev/null)"
  uv="$(dmesg 2>/dev/null | grep -ci 'undervoltage detected')"
  model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
  load="$(cut -d' ' -f1 /proc/loadavg)"
  cat <<EOF
{"host": "$(hostname)", "model": "$model", "throttled": "${throttled:-?}",
 "volt": ${volt:-0}, "temp_c": ${temp:-0}, "uptime_s": ${up:-0},
 "wifi_dbm": ${wifi_dbm:-0}, "undervoltage_events": ${uv:-0},
 "loadavg": ${load:-0}, "duration_req_s": $DURATION}
EOF
}

# --- last opp alt som ligger i koen (eldste foerst) og trigg analyse --------
flush_queue() {
  local sent=0 failed=0
  for wav in $(ls -1 "$QUEUE_DIR"/*.wav 2>/dev/null | sort); do
    local base scp_args
    base="$(basename "$wav")"
    scp_args=(-q -o ConnectTimeout=15 -o BatchMode=yes)
    [ "$RATE_KBIT" -gt 0 ] && scp_args+=(-l "$RATE_KBIT")

    if scp "${scp_args[@]}" "$wav" "${wav%.wav}.json" "$SERVER:$REMOTE_AUDIO/" 2>/dev/null; then
      if ssh -o ConnectTimeout=15 -o BatchMode=yes "$SERVER" \
           "$REMOTE_PY $REMOTE_ANALYZE $REMOTE_AUDIO/$base" 2>&1 \
           | grep -E '^(===|  [A-Z]|I dag|Svakt)'; then
        :
      fi
      rm -f "$wav" "${wav%.wav}.json"
      sent=$((sent + 1))
    else
      log "Opplasting av $base feilet — blir liggende i koen."
      failed=$((failed + 1))
      break   # er nettet nede, nytter det ikke aa proeve resten naa
    fi
  done
  log "Koe: $sent lastet opp, $(ls -1 "$QUEUE_DIR"/*.wav 2>/dev/null | wc -l) igjen."
}

# --- rydd koen hvis den vokser (nettet nede lenge) --------------------------
trim_queue() {
  local n
  n="$(ls -1 "$QUEUE_DIR"/*.wav 2>/dev/null | wc -l)"
  if [ "$n" -gt "$QUEUE_MAX" ]; then
    log "Koen har $n opptak (maks $QUEUE_MAX) — sletter de eldste."
    ls -1 "$QUEUE_DIR"/*.wav | sort | head -n $((n - QUEUE_MAX)) | while read -r old; do
      rm -f "$old" "${old%.wav}.json"
    done
  fi
}

# ---------------------------------------------------------------- hovedloep
STAMP="$(date +%Y%m%d_%H%M%S)"
WAV="$WORK_DIR/fugl_${STAMP}.wav"
DEVICE="$(find_device)"

log "Opptak: ${DURATION}s fra ${DEVICE}"
if ! arecord -D "$DEVICE" -c1 -r 48000 -f S16_LE -d "$DURATION" "$WAV" 2>/dev/null; then
  log "FEIL: arecord feilet (enhet $DEVICE). Avbryter oekten."
  rm -f "$WAV"
  exit 1
fi

health_json > "${WAV%.wav}.json"
mv "$WAV" "${WAV%.wav}.json" "$QUEUE_DIR/" 2>/dev/null

trim_queue
flush_queue

# Send med hjerteslagsloggen (bittelien) saa serveren kan se naar Pi-en levde
# og naar den var borte -- det er den eneste kilden vi har til «overlevde den
# natta?», siden riggen ikke har noen batterimaaler.
HEARTBEAT="${FUGLE_HEARTBEAT:-/home/bruker/heartbeat.log}"
if [ -s "$HEARTBEAT" ]; then
  scp -q -o ConnectTimeout=15 -o BatchMode=yes "$HEARTBEAT" \
      "$SERVER:/opt/fugleramme/data/heartbeat-$(hostname).log" 2>/dev/null \
    || log "(fikk ikke sendt hjerteslagsloggen — proever igjen neste oekt)"
fi

log "Ferdig."
