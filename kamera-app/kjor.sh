#!/usr/bin/env bash
# kjor.sh — bygg, installer og styr fuglekamera-appen paa Pixel-en fra Macen.
#
#     kamera-app/kjor.sh              # bygg, installer og start
#     kamera-app/kjor.sh bygg         # bygg APK-en
#     kamera-app/kjor.sh installer    # legg den paa telefonen, med kameratillatelse
#     kamera-app/kjor.sh start        # (om)start appen
#     kamera-app/kjor.sh konfig       # send kamera-app/kamera.json til telefonen;
#                                     # appen leser den paa nytt uten omstart
#     kamera-app/kjor.sh titt [tele]  # helt bilde med feltene tegnet inn, til
#                                     # ut/siste.jpg (groent: felt, roedt: telesona)
#     kamera-app/kjor.sh test x y     # tenkt bevegelse i (x, y), uten fugl
#     kamera-app/kjor.sh bilder       # hent bildene appen har tatt til ut/bilder/
#     kamera-app/kjor.sh logg [n]     # de siste n linjene i appens logg
#
# Telefonen naas over USB eller traadloes feilsoeking. Er ingen koblet til,
# finner skriptet den over Wi-Fi selv.
#
# Verktoeyene er installert med Homebrew og ligger ikke i PATH, derfor settes
# stiene her. Paa en ny Mac:
#   brew install openjdk@17 gradle
#   brew install --cask android-commandlinetools
#   sdkmanager platform-tools "platforms;android-37.0" "build-tools;37.0.0"
set -euo pipefail
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
ADB="$ANDROID_HOME/platform-tools/adb"
HER="$(cd "$(dirname "$0")" && pwd)"
PAKKE=no.fugleramme.kamera
MAPPE="/sdcard/Android/data/$PAKKE/files"
APK="$HER/app/build/outputs/apk/debug/app-debug.apk"
UT="$HER/ut"

koble() {
  local s adr
  s=$("$ADB" devices | awk 'NR > 1 && $2 == "device" {print $1; exit}')
  if [ -z "$s" ]; then
    adr=$("$ADB" mdns services 2>/dev/null | awk '/_adb-tls-connect/ {print $3; exit}')
    if [ -n "$adr" ]; then "$ADB" connect "$adr" >/dev/null 2>&1 || true; fi
    s=$("$ADB" devices | awk 'NR > 1 && $2 == "device" {print $1; exit}')
  fi
  if [ -z "$s" ]; then
    echo "finner ikke telefonen: koble til USB eller slaa paa traadloes feilsoeking" >&2
    exit 1
  fi
  export ANDROID_SERIAL="$s"
}

case "${1:-alt}" in
  bygg)
    "$HER/gradlew" -p "$HER" --quiet assembleDebug
    echo "$APK" ;;
  installer)
    koble
    "$ADB" install -r "$APK"
    "$ADB" shell pm grant "$PAKKE" android.permission.CAMERA ;;
  start)
    koble
    "$ADB" shell am start -S -n "$PAKKE/.MainActivity" >/dev/null
    echo "startet" ;;
  konfig)
    koble
    [ -f "$HER/kamera.json" ] || { echo "mangler $HER/kamera.json (mal: kamera.example.json)" >&2; exit 1; }
    python3 -m json.tool "$HER/kamera.json" >/dev/null
    "$ADB" push "$HER/kamera.json" "$MAPPE/kamera.json" >/dev/null
    echo "sendt; appen leser den paa nytt" ;;
  titt)
    koble
    mkdir -p "$UT"
    "$ADB" shell "rm -f $MAPPE/siste.jpg"
    printf '%s' "${2:-}" > "$UT/TA_BILDE"
    "$ADB" push "$UT/TA_BILDE" "$MAPPE/TA_BILDE" >/dev/null
    for _ in $(seq 1 30); do
      if "$ADB" shell "test -f $MAPPE/siste.jpg"; then
        "$ADB" pull "$MAPPE/siste.jpg" "$UT/siste.jpg" >/dev/null
        echo "$UT/siste.jpg"
        exit 0
      fi
      sleep 1
    done
    echo "fikk ikke noe bilde paa 30 s; kjoerer appen? (kjor.sh logg)" >&2
    exit 1 ;;
  test)
    # Tenkt bevegelse i (x, y), andeler av bildet: hele veien med utsnitt,
    # telelinse og reserve, uten at noe beveger seg. kjor.sh test 0.5 0.5
    koble
    mkdir -p "$UT"
    printf 'test %s %s' "${2:?x mangler}" "${3:?y mangler}" > "$UT/TA_BILDE"
    "$ADB" push "$UT/TA_BILDE" "$MAPPE/TA_BILDE" >/dev/null
    sleep "${4:-8}"
    "$ADB" shell "tail -n 6 $MAPPE/logg.txt" ;;
  bilder)
    koble
    mkdir -p "$UT/bilder"
    "$ADB" pull "$MAPPE/bilder/." "$UT/bilder/" >/dev/null
    ls -t "$UT/bilder" | head ;;
  logg)
    koble
    "$ADB" shell "tail -n ${2:-40} $MAPPE/logg.txt" ;;
  alt)
    "$0" bygg
    "$0" installer
    "$0" start ;;
  *)
    sed -n '2,20p' "$0"
    exit 1 ;;
esac
