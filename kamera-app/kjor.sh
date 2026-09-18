#!/usr/bin/env bash
# kjor.sh — bygg, installer og kjoer kameratesten paa Pixel-en over USB, og
# hent bildene og rapporten til kamera-app/ut/.
#
#     kamera-app/kjor.sh            # alt under, i rekkefoelge
#     kamera-app/kjor.sh bygg       # bygg APK-en
#     kamera-app/kjor.sh installer  # legg den paa telefonen, med kameratillatelse
#     kamera-app/kjor.sh start      # start appen; den tar bildene selv
#     kamera-app/kjor.sh hent       # hent bilder og kameratest.txt
#     kamera-app/kjor.sh logg       # foelg appens logg
#
# Telefonen maa ha USB-feilsoeking paa og vaere koblet til Macen.
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

case "${1:-alt}" in
  bygg)
    "$HER/gradlew" -p "$HER" --quiet assembleDebug
    echo "$APK" ;;
  installer)
    "$ADB" install -r "$APK"
    "$ADB" shell pm grant "$PAKKE" android.permission.CAMERA ;;
  start)
    "$ADB" shell "rm -f $MAPPE/*"
    "$ADB" shell am start -S -n "$PAKKE/.MainActivity" >/dev/null
    echo "appen tar bildene ..."
    for _ in $(seq 1 45); do
      "$ADB" shell "cat $MAPPE/kameratest.txt 2>/dev/null" | grep -q '^ferdig' && exit 0
      sleep 2
    done
    echo "ikke ferdig etter 90 s — se kjor.sh logg" >&2; exit 1 ;;
  hent)
    mkdir -p "$UT"
    "$ADB" pull "$MAPPE/." "$UT/" >/dev/null
    cat "$UT/kameratest.txt" ;;
  logg)
    "$ADB" logcat -s Fuglekamera ;;
  alt)
    "$0" bygg
    "$0" installer
    "$0" start
    "$0" hent ;;
  *)
    sed -n '2,11p' "$0"; exit 1 ;;
esac
