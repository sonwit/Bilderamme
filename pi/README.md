# pi/ — utedel v1 på Raspberry Pi (pensjonert)

Den første lytteposten: en Raspberry Pi 3 B med INMP441-mikrofon, drevet av
solcelle og batteri. Den trakk rundt 450 mA i tomgang, fikk undervoltage på
solcelledrift og døde 28. juli 2026. Utedel v2 på XIAO ESP32-S3
([../firmware/README.md](../firmware/README.md)) tok over 4. august 2026.

| Fil | Hva |
|---|---|
| `record_and_upload.sh` | Lytteøkta: opptak til tmpfs, opplasting med scp, kø på disk ved feil, fartsgrense på sendingen. |
| `crontab.txt` | Planen: hver halvtime 04–08, hver time 09–21, heartbeat hvert kvarter. |
| `heartbeat.sh` | Et livstegn til serveren, så stillhet kunne skilles fra et dødt brett. |
| `power_tune.sh` | Strømsparing: HDMI, LED-er og det som ellers kunne skrus av. |

Historikken og lærdommene står i `docs/Utedel — status og neste steg.md`.
Mikrofonen og designvalgene (16-bit, normalisering på serveren, kø ved feil)
ble med videre til v2.
