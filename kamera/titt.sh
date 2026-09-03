#!/usr/bin/env bash
# titt.sh — ta et bilde av hele rammen med fuglekameraet, hent det ned og
# aapne det paa Macen. Til finjustering av fokus og retning.
#
#     kamera/titt.sh              # ett bilde, aapnes i Forhaandsvisning
#     kamera/titt.sh /tmp/x.jpg   # lagre et bestemt sted
#
# Ber kamera-tjenesten paa Pi-en om bildet ved aa legge fila TA_BILDE ved
# siden av kamera.py; tjenesten tar bildet, skriver siste.jpg og sletter
# fila. Ingenting sendes til serveren.
set -euo pipefail
PI="${PI:-bruker@192.168.1.223}"
UT="${1:-$HOME/Desktop/fugleramme-kamera.jpg}"

ssh "$PI" 'cd ~/kamera && rm -f siste.jpg && touch TA_BILDE
  for i in $(seq 1 30); do [ -f siste.jpg ] && exit 0; sleep 0.5; done
  echo "Fikk ikke noe bilde paa 15 s — kjoerer tjenesten? (systemctl status fugleramme-kamera)" >&2; exit 1'
scp -q "$PI:~/kamera/siste.jpg" "$UT"
echo "$UT"
command -v open >/dev/null && open "$UT"
