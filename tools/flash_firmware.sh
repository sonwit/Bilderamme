#!/usr/bin/env bash
#
# flash_firmware.sh — kompiler og flash firmwaren med arduino-cli.
# Kjøres fra Macen, med brettet i USB-C. Ingen Arduino IDE nødvendig.
#
#     tools/flash_firmware.sh                    # innedel (bilderammen)
#     tools/flash_firmware.sh utedel             # utedelen (XIAO ESP32-S3)
#     tools/flash_firmware.sh --sjekk            # bare kompiler, uten brett
#     tools/flash_firmware.sh --port /dev/cu.usbserial-1420
#     tools/flash_firmware.sh --monitor          # åpne Serial Monitor etterpå
#
# Board-innstillingene under er de samme som tabellen i
# «docs/Fase 1 — Kom i gang med ePaper-skjermen.md», bare uttrykt som FQBN.
# Overstyr hele strengen med FQBN=... hvis du må eksperimentere.
#
# Se docs/Flashing med arduino-cli.md for førstegangsoppsett og feilsøking.

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"

# ESP32S3 Dev Module + Flash 32MB + OPI PSRAM + USB CDC On Boot: Disabled.
# Partisjonen er 32M-varianten («32M Flash (4.8MB APP/22MB FATFS)»); skissen
# bruker ikke filsystemet, så den bryr seg bare om APP-plassen.
FQBN_INNE="esp32:esp32:esp32s3:FlashSize=32M,PSRAM=opi,CDCOnBoot=default,PartitionScheme=app5M_fat24M_32MB"
# XIAO ESP32-S3: bare PSRAM må skrus på (opptaket ligger i PSRAM).
FQBN_UTE="esp32:esp32:XIAO_ESP32S3:PSRAM=opi"

ESP32_URL="https://espressif.github.io/arduino-esp32/package_esp32_index.json"
ESP32_CORE="esp32:esp32"
BAUD=115200

TARGET="inne"
PORT=""
COMPILE_ONLY=0
MONITOR=0

while [ $# -gt 0 ]; do
  case "$1" in
    inne|innedel|frame|ramme)      TARGET="inne" ;;
    ute|utedel|sensor|outdoor)     TARGET="ute" ;;
    --sjekk|--compile-only)        COMPILE_ONLY=1 ;;
    --monitor|-m)                  MONITOR=1 ;;
    --port|-p)                     PORT="${2:?--port trenger en verdi}"; shift ;;
    -h|--help)                     sed -n '3,17p' "$0" | cut -c3-; exit 0 ;;
    *) echo "Ukjent argument: $1 (prøv --help)" >&2; exit 2 ;;
  esac
  shift
done

if [ "$TARGET" = "inne" ]; then
  SKETCH="$HERE/firmware/indoor_frame"
  FQBN="${FQBN:-$FQBN_INNE}"
  NAVN="innedelen (bilderammen)"
else
  SKETCH="$HERE/firmware/outdoor_sensor"
  FQBN="${FQBN:-$FQBN_UTE}"
  NAVN="utedelen (XIAO ESP32-S3)"
fi

# ---------------------------------------------------------------- arduino-cli
if ! command -v arduino-cli >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Fant ikke arduino-cli.

Installer den først:
    brew install arduino-cli

Har du ikke Homebrew:
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

(Alternativ uten Homebrew — legger binæren i ~/bin:)
    mkdir -p ~/bin && curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/bin sh
    export PATH="$HOME/bin:$PATH"
EOF
  exit 1
fi

# ---------------------------------------------------------------- Rosetta
# arduino-cli kjører Arduinos «ctags» som en del av kompileringen, og den
# finnes bare som Intel-binær. På Apple Silicon uten Rosetta stopper byggingen
# med et ganske ubrukelig «bad CPU type in executable», så vi tar det her i
# stedet. (universal-ctags fra Homebrew er ikke et alternativ — den mangler
# feltene Arduino bruker til å generere funksjonsprototyper, og lager i stedet
# ødelagt kode som ikke kompilerer.)
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] &&
   [ ! -d /Library/Apple/usr/share/rosetta ] &&
   [ ! -f /Library/Apple/usr/libexec/oah/libRosettaRuntime ]; then
  cat >&2 <<'EOF'
Rosetta mangler — arduino-cli klarer ikke kompilere uten.

Installer den én gang (kommandoen spør om passordet ditt):
    softwareupdate --install-rosetta --agree-to-license

Kjør så dette scriptet på nytt.
EOF
  exit 1
fi

# ---------------------------------------------------------------- esp32-kjerne
if ! arduino-cli core list 2>/dev/null | grep -q "^$ESP32_CORE "; then
  echo "→ esp32-kjernen mangler. Installerer den (≈1 GB, tar noen minutter) ..."
  arduino-cli core update-index --additional-urls "$ESP32_URL"
  arduino-cli core install "$ESP32_CORE" --additional-urls "$ESP32_URL"
fi

# ---------------------------------------------------------------- config.h
CONFIG="$SKETCH/config.h"
if [ ! -f "$CONFIG" ]; then
  cp "$SKETCH/config.example.h" "$CONFIG"
  cat >&2 <<EOF

config.h fantes ikke, så jeg laget den fra malen:
    $CONFIG

Fyll inn WiFi-navn og passord (2,4 GHz-nettet) og kjør scriptet på nytt.
Fila er git-ignorert — passordet havner aldri i repoet.
EOF
  exit 1
fi
if grep -q "DITT_WIFI_PASSORD" "$CONFIG"; then
  echo "config.h har fortsatt malverdiene — fyll inn WiFi først: $CONFIG" >&2
  exit 1
fi

# ---------------------------------------------------------------- kompiler
echo "→ Kompilerer $NAVN"
echo "  sketch: ${SKETCH#$HERE/}"
echo "  fqbn:   $FQBN"
arduino-cli compile --fqbn "$FQBN" "$SKETCH"

if [ "$COMPILE_ONLY" = 1 ]; then
  echo "✅ Kompilerte fint. (--sjekk, så ingenting ble lastet opp.)"
  exit 0
fi

# ---------------------------------------------------------------- finn port
if [ -z "$PORT" ]; then
  PORTS="$(arduino-cli board list 2>/dev/null | awk '$2 == "serial" && /USB/ { print $1 }')"
  ANTALL="$(printf '%s\n' "$PORTS" | grep -c . || true)"
  if [ "$ANTALL" -eq 0 ]; then
    cat >&2 <<'EOF'
Fant ingen USB-seriellport.

- Sitter USB-C-kabelen i? Noen kabler er kun strøm — prøv en annen.
- Sjekk hva Macen ser:   arduino-cli board list
- Henger opplastingen på «Connecting…»: hold inne BOOT, trykk og slipp RESET,
  slipp BOOT — da står brettet i nedlastingsmodus. Kjør scriptet på nytt.
EOF
    exit 1
  fi
  if [ "$ANTALL" -gt 1 ]; then
    echo "Flere USB-porter funnet — velg én med --port:" >&2
    printf '  %s\n' $PORTS >&2
    exit 1
  fi
  PORT="$PORTS"
fi

# ---------------------------------------------------------------- last opp
echo "→ Laster opp til $PORT"
arduino-cli upload --fqbn "$FQBN" --port "$PORT" "$SKETCH"
echo "✅ Flashet $NAVN."

if [ "$MONITOR" = 1 ]; then
  echo "→ Serial Monitor ($BAUD) — Ctrl-C for å avslutte."
  arduino-cli monitor --port "$PORT" --config "baudrate=$BAUD"
else
  echo "   Se hva den sier:  arduino-cli monitor --port $PORT --config baudrate=$BAUD"
fi
