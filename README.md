# Fugleramme

Et DIY-prosjekt som kombinerer fuglelyd-gjenkjenning, værdata og AI-bildegenerering
for å vise et daglig oppdatert kunstbilde på en 13.3" e-ink bilderamme.

Hver morgen: hjemmeserveren genererer et bilde med Gemini (`gemini-2.5-flash-image`),
basert på værdata fra yr (api.met.no), dithrer det til panelets 6-fargers palett, og
**pusher** det til e-ink-rammen inne, som viser det og sover til neste morgen.

## Status

- ✅ **Innedel (ePaper-ramme):** bekreftet i live-test 2026-07-21 — `fugleramme.local`
  svarer på ping, og `send_to_frame.py` fikk skjermen til å tegne et bilde.
  Se `firmware/indoor_frame/`.
- ✅ **Bildegenerering (hjemmeserver):** `generate_daily_image.py` på
  `192.168.1.38` genererer dagens bilde, henter vær, dithrer og skriver
  `frame.bin` i riktig panelformat. Serveres også på
  `http://192.168.1.38:8080/frame.bin` for inspeksjon/debugging.
- ✅ **Daglig push:** `tools/push_to_frame.py` sender `frame.bin` videre til
  rammen rett etter generering — se «Daglig flyt» under. Kjøres fra cron på
  hjemmeserveren (07:07, verifisert 2026-07-24).
- ✅ **Webapp + Siri:** `tools/frame_server.py` (systemd-tjeneste, port 8090) —
  galleri over alle genererte bilder, «lag nytt bilde»-skjema, og
  `POST /generate` for Siri-snarveien. Se `docs/Webapp — galleri og
  generering.md` og `docs/On-demand — Siri-kommando.md`.
- ✅ **Utedel v2 (XIAO ESP32-S3, fuglelyd):** montert ute og i drift
  2026-08-04. Våkner fra deep sleep etter plan (04:00–08:30 hvert 30. min,
  09–21 hver time), tar opp 60 s fra INMP441, POST-er til serveren og sover
  på ~14 µA. Soldrevet: panel → Waveshare Solar Power Manager (D) → 10 Ah
  LiPo → XIAO-ens BAT-pads. Se `firmware/outdoor_sensor/` og
  `docs/Utedel v2 — ESP32-S3 XIAO.md`.
  *(v1 med Raspberry Pi 3 B trakk for mye strøm og døde 2026-07-28 —
  historikk og lærdommer i `docs/Utedel — status og neste steg.md`.)*
- ✅ **BirdNET-pipeline (hjemmeserver):** `tools/audio_ingest.py` (systemd,
  port 8091) tar imot opptakene og trigger `tools/birdnet_analyze.py` →
  `data/observations.jsonl` (alt, for godt) + `birds.json` (dagens arter, som
  dagens bilde genereres fra). `tools/bird_stats.py` lager statistikk og
  daglig rapport: arter, lydnivå, dekning.

### Kjente snurrer (ikke bugs, men lurt å vite om)

- **"Connection reset" når du sender med `send_to_frame.py`/`push_to_frame.py`:**
  Firmwaren kaller `client.stop()` rett etter å ha skrevet HTTP-svaret, uten
  å flushe først — det gjør at klienten av og til får en "connection reset"
  mens den prøver å *lese* svaret, selv om bildet ble mottatt og tegnet helt
  fint. Begge scriptene håndterer nå dette (skiller "klarte ikke sende" fra
  "sendte ok, men fikk ikke lest svaret") og gir en tydelig melding i stedet
  for en traceback. Vil du fjerne snurren helt: legg til `client.flush();
  delay(5);` før begge `client.stop()`-kallene i `indoor_frame.ino` og reflash
  — ikke nødvendig for at noe skal virke, bare kosmetikk i loggen.
- **Grumsete/støyete bilde på skjermen er ofte forventet, ikke en feil:**
  testet med `tools/test.png` (et mykt akvarell-aktig bilde) 2026-07-21, og
  det så støyete ut på skjermen. En lokalt generert forhåndsvisning
  (`--preview`, ingen nettverk involvert) av nøyaktig samme fil viser identisk
  støy — altså er det Atkinson-dithringen som gjør akkurat det den skal på et
  bilde med myke/pastellfargede flater, ikke en overførings- eller
  driver-feil. Se «Bildekonvertering» under: bruk `--preview` for å sjekke
  *før* du sender, og hold deg til flate, mettede farger (som prompt-guiden
  anbefaler) for pene resultater. De faktiske daglige Gemini-bildene bør
  allerede være stilt inn på dette via `docs/Prompt-guide — bilder til
  ePaper-rammen.md`.

## Struktur

```
fugleramme/
├── firmware/
│   ├── indoor_frame/       ESP32-S3 Arduino-sketch for 13.3" Spectra 6 e-Paper.
│   │                       Kjører en liten HTTP-server: POST /display med
│   │                       960000 raa byte -> tegnes på panelet. PUSH, ikke pull —
│   │                       brettet henter ingenting selv.
│   └── outdoor_sensor/     XIAO ESP32-S3 Arduino-sketch for utedelen: deep sleep
│                           etter opptaksplan, 60 s I2S-opptak (INMP441) i PSRAM,
│                           høypassfilter mot vind, NTP-synk, HTTP-opplasting med
│                           helse-JSON. Se docs/Utedel v2 — ESP32-S3 XIAO.md.
├── tools/
│   ├── send_to_frame.py    Gjør et vilkårlig bilde (jpg/png) om til panel-format
│   │                       og sender det til rammen. Til manuell testing fra Macen.
│   ├── push_to_frame.py    Sender en ferdig-pakket frame.bin til rammen. Cron.
│   ├── generate_daily_image.py  Dagens bilde: vær (yr) + dagens hørte fugler
│   │                       (birds.json) -> Gemini -> dither -> frame.bin.
│   ├── frame_server.py     Webapp/galleri + Siri-endepunkt (systemd, port 8090).
│   ├── audio_ingest.py     Mottak av opptak fra utedelen (systemd, port 8091);
│   │                       trigger analysen. ESP32 kan ikke scp — derfor HTTP.
│   ├── birdnet_analyze.py  BirdNET på én WAV -> observations.jsonl + birds.json.
│   └── bird_stats.py       Statistikk/rapport: arter, lydnivå, dekning, strøm.
├── pi/                     v1-utedelen (Raspberry Pi 3 B) — pensjonert 2026-08-04,
│                           beholdt som referanse/reserve.
├── deploy/                 deploy.sh + systemd-tjenestefiler for hjemmeserveren.
└── docs/                   Prosjektnotater og guider.
```

**Hjemmeserveren (`192.168.1.38`, utenfor dette repoet, i `/opt/fugleramme/`):**

```
/opt/fugleramme/
├── generate_daily_image.py   Dagens bilde (Gemini + vær + dagens fugler).
├── frame_server.py            Webapp/Siri (systemd: fugleramme-frame-server, :8090)
├── audio_ingest.py            Mottak fra utedelen (systemd: fugleramme-audio-ingest, :8091)
├── birdnet_analyze.py         BirdNET-analyse (kjøres av audio_ingest per opptak)
├── bird_stats.py              Statistikk (cron 22:00 -> logs/stats.log)
├── birds.json                 DAGENS aggregerte artsliste (leses av bildegen.)
├── audio/                     Innkomne opptak + helse-sidecars (ryddes etter 21 d)
├── data/observations.jsonl    Én linje per analysert opptak — for godt
├── venv/  venv-birdnet/       To venv-er: bilde/Gemini og BirdNET
└── www/
    ├── frame.bin              Dagens bilde, panel-format (960000 byte).
    ├── preview.png             Forhåndsvisning av frame.bin, RGB.
    └── original.png            Det AI-genererte bildet før dithering.
```
`www/` serveres på `http://192.168.1.38:8080/` — nyttig for å se hva som ble
generert og for feilsøking, men rammen henter **ikke** derfra selv (se under).

## Hvordan alt henger sammen (daglig flyt)

```
[Hjemmeserver 192.168.1.38]                      [ESP32-S3 e-Paper-ramme]
generate_daily_image.py                            "fugleramme.local"
  → yr / api.met.no (vær)                                (HTTP-server, port 80)
  → Gemini (bilde)
  → dither til 6 farger, pakk 2 px/byte
  → skriv www/frame.bin  ──┐
                            │
push_to_frame.py           │
  → les frame.bin  ────────┘
  → POST http://fugleramme.local/display  ────────►  mottar 960000 byte
                                                       → tegner på panelet
                                                       (~20-35 sek)
```

Begge stegene trigges av **ett cron-kall** på hjemmeserveren (`crontab -e`,
verifisert fungerende 2026-07-24):

```cron
7 7 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && venv/bin/python3 generate_daily_image.py >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
```

Tidspunktet er med vilje 07:07, ikke hel time: vær-API-er er mest overbelastet
akkurat kl. XX:00 (alle verdens cron-jobber treffer samtidig — det ga to dagers
503-stopp i juli 2026 da jobben lå på 07:00). Skulle været likevel feile, prøver
`get_weather_safe()` 3 ganger og genererer deretter bildet uten værreferanse —
værfeil stopper aldri dagens bilde lenger.

Tre ting som MÅ være som over, ellers feiler cron stille:

1. **`venv/bin/python3`, ikke `/usr/bin/python3`.** Systemets python mangler
   numpy/pillow/google-genai; de ligger i venv-en. (Cron leser scriptet på nytt
   hver gang, så nye kodeendringer plukkes opp automatisk — ingen restart nødvendig.)
2. **`. /opt/fugleramme/frame_server.env` med ABSOLUTT sti** (ikke `. frame_server.env`).
   Cron kjører `/bin/sh` (dash), og dash sin `.`-kommando leter kun i `$PATH`,
   ikke i gjeldende mappe slik bash gjør. Med relativ sti blir det
   `.: frame_server.env: not found`, kjeden stopper, og Python starter aldri —
   den klassiske «virker manuelt (bash), feiler i cron (dash)»-fella. Dette
   sourcer `GEMINI_API_KEY` + `FRAME_HOST` (cron arver ikke shell-profilen din).
3. **`mkdir -p /opt/fugleramme/logs`** må finnes.

Sjekk `daily.log` hvis en dag ikke dukker opp på skjermen. Merk at serveren ikke
har e-postserver (MTA), så feil FØR log-omdirigeringen (som dash-`.`-feilen over)
havner ikke i loggen — de forsvinner. Test derfor alltid via cron (ikke bare
manuelt i bash) ved å legge en midlertidig linje 2 min frem. `push_to_frame.py`
prøver 4 ganger, og `generate_daily_image.py` prøver Gemini på nytt ved 503.

**Hvorfor push og ikke pull:** firmwaren (`indoor_frame.ino`) er en HTTP-server
som venter på `POST /display` — den henter ingenting selv, og har ingen
klokke/deep-sleep-vekk-og-hent-logikk innebygd. Det er også nøyaktig samme
mekanisme som ble brukt til å få det første testbildet på skjermen
(`send_to_frame.py` fra Macen), så dette gjenbruker en løsning som allerede
er verifisert å virke — ingen ny flashing nødvendig.

## Kom i gang / test alt

**1. Flash firmwaren (kun hvis brettet ikke allerede kjører den)**

```
cd firmware/indoor_frame
cp config.example.h config.h      # fyll inn WiFi-navn/passord (2,4 GHz)
```
Åpne `indoor_frame.ino` i Arduino IDE (ESP32S3 Dev Module, Flash 32MB, PSRAM OPI),
og last opp. Serial Monitor (115200) viser IP-en og `http://fugleramme.local`.

**2. Sjekk at rammen er på og svarer** (kjør fra en maskin på samme nett som
rammen, f.eks. Macen — se «⚠️ To nettverk under samme navn» i
`docs/Fase 1 — Kom i gang med ePaper-skjermen.md` hvis dette ikke svarer):

```bash
ping -c 3 fugleramme.local
curl -s http://fugleramme.local/          # skal gi en statusside med "Fugleramme" + IP
```
Svarer ikke `fugleramme.local`: bruk IP-en fra Serial Monitor i stedet
(`ping -c 3 192.168.1.x`, `curl http://192.168.1.x/`).

**3. Send et testbilde manuelt**

```
cd tools
pip install pillow numpy
python3 send_to_frame.py test.png          # eller test_2.jpg / test_3.png som allerede ligger her
```
Skjermen skal oppdatere seg på ~20-35 sekunder.

**4. Test selve dagsflyten end-to-end** (henter det faktiske frame.bin fra
hjemmeserveren og sender det rått, uten `send_to_frame.py`s bildebehandling —
akkurat det `push_to_frame.py` gjør):

```bash
curl -s http://192.168.1.38:8080/frame.bin -o /tmp/frame.bin
ls -la /tmp/frame.bin                       # skal være nøyaktig 960000 byte
curl -s -X POST --data-binary @/tmp/frame.bin \
     -H "Content-Type: application/octet-stream" \
     http://fugleramme.local/display
```
Se på skjermen: stemmer motivet og fargene med `http://192.168.1.38:8080/preview.png`?
Er bildet **rotert eller forskjøvet**, se «Ting å dobbeltsjekke» under.

**5. Sett opp cron på hjemmeserveren**

```bash
scp tools/push_to_frame.py bruker@192.168.1.38:/opt/fugleramme/
ssh bruker@192.168.1.38
mkdir -p /opt/fugleramme/logs
crontab -e
# legg til linjen fra «Hvordan alt henger sammen» over
```

## Ting å dobbeltsjekke

- **Orientering:** panelet er `1200×1600` (portrett, bekreftet i
  `EPD_13in3e.h` og brukt av `send_to_frame.py`). Sørg for at
  `generate_daily_image.py` også skriver `frame.bin` som `1200×1600` (600
  byte/rad × 1600 rader) — ikke `1600×1200`. Byte-tallet blir 960000 uansett
  rekkefølge, så en evt. forbytting av bredde/høyde vil **ikke** feile på
  størrelse, bare gi et forskjøvet/rotert bilde på skjermen. Test steg 4 over
  avslører dette raskt.
- **Fargekoder:** `generate_daily_image.py` sine koder (`0x0` svart, `0x1`
  hvit, `0x2` gul, `0x3` rød, `0x5` blå, `0x6` grønn) matcher
  `send_to_frame.py`/firmwarens palett nøyaktig — ingen endring nødvendig der.
- **Nibble-rekkefølge:** høy nibble = venstre piksel i paret (samme som
  `send_to_frame.py`s `pack()`). Hvis fargene ser "byttet om" ut på skjermen,
  er dette først mistenkte.
- **mDNS fra hjemmeserveren:** `fugleramme.local` er testet fra macOS/iOS
  (Bonjour er innebygd). Er hjemmeserveren Linux uten `avahi-daemon`, vil
  ikke navnet slå opp — sett `FRAME_HOST=192.168.1.x` (fast IP, gjerne
  DHCP-reservert på ruteren) i cron-jobben eller bruk `push_to_frame.py --host`.
- **To nettverk under samme WiFi-navn:** dette var et reelt problem under
  første oppsett (Mac og brett havnet på forskjellige subnett). Se
  `docs/Fase 1 — Kom i gang med ePaper-skjermen.md` for detaljer/løsning —
  relevant igjen hvis hjemmeserveren plutselig ikke når rammen.

## Bildekonvertering — velg riktig modus (for manuell `send_to_frame.py`-bruk)

Panelet har bare 6 rene farger, så bildet må «oversettes» til dem. Metoden
(`--dither`) avgjør hvor pent det blir. **Atkinson er standard og beste
allrounder.**

| Modus | Best for | Uttrykk |
|---|---|---|
| `atkinson` *(standard)* | akvarell, foto, **og** tegneserie | rene flater, naturlige farger, lett trykk-tekstur |
| `none` (`--flat`) | flat tegneserie/vektor/plakat | djervest, mest plakataktig; farger «snappes» (kan bli posterisert) |
| `bluenoise` | foto | naturlig korn, men litt uro på store flate flater |
| `ordered` | — | retro/mønstret rutenett-look |
| `floyd` | (unngå) | Floyd-Steinberg: overdiffunderer på dette panelet → støy og grønt hud-stikk |

```
python3 send_to_frame.py bilde.png                      # atkinson (standard)
python3 send_to_frame.py bilde.png --dither none         # flat/plakat
python3 send_to_frame.py bilde.png --dither bluenoise --preview ut.png
```

Se `docs/Prompt-guide — bilder til ePaper-rammen.md` for prompt-maler som gir
gode resultater på 6-fargepanelet (flate, mettede farger — ikke bløt akvarell).

### Farger som gjengis best / bør unngås

De 6 fargene er **svart, hvit, rød, gul, blå, grønn**. Bygg bildene rundt disse:

- **Bra:** klar blå himmel, grønt løv/gress, rød (hytte, detaljer), gult, rein
  hvit bakgrunn, svarte konturer.
- **Unngå store flater av:** lilla, turkis, rosa, oransje, og rene gråtoner —
  de finnes ikke i paletten og må tilnærmes med tekstur (blir lett urolige).
- Beige/pastell går greit med `atkinson` (blir subtil tekstur på hvitt), men
  ble stygt med `floyd`. Er du i tvil: kjør `--preview` først.

## Maskinvare

**Innedel:**
- Waveshare ESP32-S3-ePaper-13.3E6 (13.3", 7-farge Spectra 6, WiFi, 16 MB PSRAM)
- IKEA RÖDALM 30×40 cm ramme

**Utedel (v2, i drift fra 2026-08-04):**
- Seeed XIAO ESP32-S3 (8 MB PSRAM — 60 s opptak bor i minnet, deep sleep ~14 µA)
- INMP441 I2S-mikrofon (gjenbrukt fra v1), skumgummi som vindbeskyttelse
- Waveshare Solar Power Manager (D) — MPPT-lading fra solcellepanel + vern.
  NB: modulens 5V-utgang brukes IKKE (powerbank-brikken kutter ved µA-last);
  XIAO-en går rett på batteriet via BAT-padene.
- 3,7 V 10 000 mAh LiPo + solcellepanel (6–24 V inn på manageren)

Full komponentliste og prosjektbeskrivelse i `docs/`.

## Tekniske notater

- Panelet er 1200×1600, styrt som to halvdeler (master/slave). Bildet må pakkes
  2 piksler/byte (600 byte/rad). `send_to_frame.py` og `generate_daily_image.py`
  (på hjemmeserveren) gjør dette; firmwaren viser med Waveshares
  `EPD_13IN3E_Display`.
- 6 farger: BLACK 0x0, WHITE 0x1, YELLOW 0x2, RED 0x3, BLUE 0x5, GREEN 0x6.
- WiFi må være 2,4 GHz.
- Firmwaren blanker **ikke** skjermen ved oppstart/strømbrudd — e-ink beholder
  forrige bilde uten strøm. Init skjer rett før neste bilde tegnes.

## Lisens

Privat hobbyprosjekt. Driverfilene i `firmware/indoor_frame/` (`DEV_Config.*`,
`EPD_13in3e.*`, `Debug.h`) er fra Waveshare og beholder deres opphavsrett.
