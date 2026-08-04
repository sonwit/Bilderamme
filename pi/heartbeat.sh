#!/usr/bin/env bash
#
# heartbeat.sh — skriver ÉN linje om at Pi-en lever, hvert 15. minutt.
#
# Hensikt: riggen har ingen batterimaaler (I2C-bussene er tomme), saa vi kan
# ikke lese ladningsnivaa. Det vi KAN gjoere er aa vite noeyaktig NAAR den
# doer. Uten dette ser vi bare «opptakene kl. 03-05 mangler»; med dette ser vi
# «siste livstegn 01:12, tilbake 05:34» — og da vet vi hvor stort
# stroemunderskuddet er, ikke bare at det finnes.
#
# Koster ingenting: ingen radio (skrives lokalt), ~100 byte per linje,
# ~10 kB per natt. Lasted opp sammen med neste opptak.
#
# Cron:  */15 * * * * /home/bruker/heartbeat.sh

set -u
LOG="${FUGLE_HEARTBEAT:-/home/bruker/heartbeat.log}"

ts="$(date +%Y-%m-%dT%H:%M:%S)"
uptime_s="$(cut -d. -f1 /proc/uptime)"
throttled="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
uv="$(dmesg 2>/dev/null | grep -ci 'undervoltage detected')"
temp="$(vcgencmd measure_temp 2>/dev/null | sed "s/temp=//;s/'C//")"
wifi="$(awk 'NR==3{gsub(/\./,"",$4); print $4}' /proc/net/wireless 2>/dev/null)"

# CSV: tid,uptime,throttled,undervoltage,temp,wifi_dbm
echo "${ts},${uptime_s:-0},${throttled:-?},${uv:-0},${temp:-0},${wifi:-0}" >> "$LOG"

# Hold fila liten (~7 doegn). Gjoeres her, ikke i egen cron-jobb.
lines="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
if [ "$lines" -gt 1200 ]; then
  tail -800 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
