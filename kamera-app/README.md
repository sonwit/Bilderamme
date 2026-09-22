# kamera-app/ — fuglekameraet som Android-app

Lytteposten hører fuglene. Denne ser dem. En Android-telefon med telelinse
står i vinduet, rettet mot materen. Appen overvåker hele hagen på 1x, og når
noe rører seg i et felt, tar den et bilde med 5x-telen, klipper ut utsnittet
rundt bevegelsen og sender det til serverens `POST /bilde`. Der svarer
`bilde_analyze.py` på hva som står på materen.

Hvorfor en telefon: fra 8–10 meter er en meis rundt 100 piksler bred i
telen og ubrukelig liten i et vidvinkelkamera. Forgjengeren på Raspberry Pi
med HQ-kamera (`../kamera/`) virket, men ble tatt ned da modellkallene viste
seg å være 80–90 % av regningen.

## Kjøre

`kjor.sh` bygger, installerer og styrer appen fra Macen, over USB eller
trådløs feilsøking:

```bash
kamera-app/kjor.sh               # bygg, installer og start
kamera-app/kjor.sh konfig        # send kamera.json til telefonen; leses uten omstart
kamera-app/kjor.sh titt [tele]   # helt bilde med feltene tegnet inn, til ut/siste.jpg
kamera-app/kjor.sh test x y      # tenkt bevegelse i (x, y), uten fugl
kamera-app/kjor.sh bilder        # hent bildene appen har tatt
kamera-app/kjor.sh logg [n]      # appens logg
```

Verktøyene installeres med Homebrew og ligger ikke i PATH; scriptet setter
`JAVA_HOME` og `ANDROID_HOME` selv. På en ny Mac: `brew install openjdk@17
gradle` og `brew install --cask android-commandlinetools`, så `sdkmanager`
for platform-tools, plattformen og build-tools (versjonene står øverst i
`kjor.sh`).

## Innstillinger

`kamera.json` i appens mappe på telefonen, fra `kamera.example.json`.
Navnene er de samme som i `../kamera/kamera.py` der de betyr det samme.

| Nøkkel | Hva |
|---|---|
| `server`, `token` | Serverens `audio_ingest` på port 8091, og `INGEST_TOKEN` hvis den er satt. |
| `send` | `false`: bildene lagres bare på telefonen. Slå på når feltene er stilt. |
| `roier` | Feltene bevegelse måles i, som andeler av 1x-bildet. Standard: hele bildet. |
| `tele`, `tele_sone` | Om telen brukes, og hvor i 1x-bildet telen dekker. |
| `pause_s` | Pause etter et bilde. En fugl på materen i tre minutter skal ikke bli 60 bilder. |
| `lukker_maks_s`, `iso_maks` | Eksponeringsgrenser, så en fugl i bevegelse ikke blir en strek. |

Bevegelsestersklene er små med vilje: feltet er hele hagen, og en spettmeis
ved materen er rundt 20×10 piksler på 1x. Kommentarene i `Konfig.kt` og
`kamera.py` forklarer tallene.
