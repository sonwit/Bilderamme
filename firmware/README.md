# firmware/ — de to brettene

To Arduino-skisser. Begge flashes fra Macen med `tools/flash_firmware.sh`,
uten Arduino IDE; førstegangsoppsett av arduino-cli og feilsøking står i
`docs/Flashing med arduino-cli.md`. WiFi-innstillingene ligger i `config.h`,
som er ignorert av git: kopier `config.example.h` og fyll inn. WiFi må være
2,4 GHz.

## indoor_frame/ — rammen på veggen

Waveshare ESP32-S3-ePaper-13.3E6: 13,3" Spectra 6 med seks farger, WiFi og
16 MB PSRAM, i en IKEA RÖDALM-ramme på 30×40 cm.

Skissen er en liten HTTP-server. `GET /` gir en statusside, `POST /display`
tar imot nøyaktig 960 000 rå byte og tegner dem med Waveshares
`EPD_13IN3E_Display`. Sender-siden gjør all tung jobb: skalerer til
1200×1600, dithrer til seks farger og pakker to piksler per byte. Brettet
trenger bare å motta bytene og skyve dem til panelet. Den henter ingenting
selv.

Rammen passer på seg selv: en task-watchdog starter brettet på nytt hvis noe
blokkerer (typisk driverens `ReadBusyH`, som venter evig hvis BUSY-pinnen
aldri slipper), og WiFi gjenopprettes eller brettet startes på nytt hvis
nettet forsvinner. En normal tegning blokkerer i 25–35 s, så watchdogen står
på 120 s. Firmwaren blanker ikke skjermen ved oppstart: e-papir beholder
forrige bilde uten strøm, og init skjer rett før neste bilde tegnes. Et lite
«pling» spilles gjennom ES8311-kodeken når bildet lander.

```bash
cp firmware/indoor_frame/config.example.h firmware/indoor_frame/config.h
tools/flash_firmware.sh --monitor        # ESP32S3 Dev Module, Flash 32MB, OPI PSRAM
ping -c 3 fugleramme.local               # mDNS-navnet fra firmwaren
curl -s http://fugleramme.local/         # statusside med «Fugleramme» og IP
cd tools && python3 send_to_frame.py test.png     # et testbilde, ~30 s
```

Svarer ikke `fugleramme.local`, bruk IP-en fra Serial Monitor. Se «To
nettverk under samme navn» i `docs/Fase 1 — Kom i gang med ePaper-skjermen.md`
hvis Macen og brettet havner på hvert sitt subnett.

**Ting å dobbeltsjekke** når et bilde ser feil ut:

- **Orientering.** Panelet er 1200×1600, portrett, styrt som to halvdeler.
  600 byte per rad × 1600 rader. Bytter man bredde og høyde blir byte-tallet
  det samme, så det feiler ikke på størrelse, bare som et forskjøvet bilde.
- **Fargekoder.** BLACK 0x0, WHITE 0x1, YELLOW 0x2, RED 0x3, BLUE 0x5,
  GREEN 0x6. `send_to_frame.py`, `generate_daily_image.py` og firmwaren
  bruker samme tabell.
- **Nibble-rekkefølge.** Høy nibble er venstre piksel i paret. Ser fargene
  «byttet om» ut, er dette første mistenkte.
- **mDNS fra serveren.** Linux uten `avahi-daemon` slår ikke opp `.local`;
  installer `libnss-mdns` eller sett en fast IP i `FRAME_HOST`.

Driverfilene `DEV_Config.*`, `EPD_13in3e.*` og `Debug.h` er Waveshares (MIT).
`es8311*` er Espressifs ES8311-driver (Apache-2.0). `audio.*` er
kodekoppsettet fra Waveshares lydeksempel.

## outdoor_sensor/ — lytteren i hagen

Seeed XIAO ESP32-S3 med 8 MB PSRAM, INMP441 I2S-mikrofon med skumgummi som
vindbeskyttelse, Waveshare Solar Power Manager (D) med MPPT-lading, 3,7 V
LiPo på 10 Ah og et solcellepanel (6–24 V inn). XIAO-en går rett på
batteriet via BAT-padene; managerens 5 V-utgang brukes ikke, for
powerbank-brikken kutter ved µA-last.

Per oppvåkning: ta opp `REC_SECONDS` (60 s) mono 16-bit rett i PSRAM, med
radioen av så mikrofonen slipper WiFi-støy. Koble til WiFi, synk klokka med
NTP og regn tidsstempelet bakover fra synket klokke. `POST` WAV-en til
serverens `/upload` med helse-JSON (spenning, WiFi-styrke, temperatur,
boot-teller) i `X-Fugl-Health`. Hent `GET /config`, regn ut neste økt og sov.
Deep sleep er ~14 µA. Feiler opplastingen, prøver den noen ganger og gir så
opp: PSRAM overlever ikke deep sleep, så opptaket droppes og hullet vises i
dekningsstatistikken.

Fjernkonfigen (`gain_shift`, `highpass_hz`, `rec_seconds`, `dawn_*`,
`day_*`) hentes etter hver opplasting og lagres i RTC-minne. Nye verdier
gjelder fra neste økt; ved strømbrudd faller brettet tilbake til
`config.h`-standardene til første vellykkede henting. Lytteplanen som
serveren svarer med er beskrevet i `tools/README.md`.

```bash
cp firmware/outdoor_sensor/config.example.h firmware/outdoor_sensor/config.h
tools/flash_firmware.sh utedel           # XIAO_ESP32S3, PSRAM på
```

Alt om montering, strøm og feilsøking står i `docs/Utedel v2 — ESP32-S3 XIAO.md`.
Versjon 1 på Raspberry Pi 3 B, som trakk for mye strøm, ligger i `../pi/`.
