# Handoff: bygg BirdNET-automatikken (fugleramme utedel)

Denne fila er kontekst til en fersk Claude Code-økt. Målet nå: **automatisere
sløyfa** der fugler hørt i hagen bestemmer dagens AI-genererte bilde på e-ink-
rammen. Alle enkeltdeler er verifisert å virke (se «Bevist»). Det som gjenstår
er ren rørlegging (se «Oppgaven»).

---

## Hva prosjektet er

«Fugleramme»: hver morgen genereres et bilde med Gemini (basert på fugler + vær),
dithres til 6-fargers e-ink-palett, og pushes til en ESP32-S3 e-ink-ramme inne.
En utendørs mikrofon tar opp fuglelyd, BirdNET kjenner igjen artene, og de skal
mate inn i bilde-prompten. Repo: `~/workspace/fugleramme` (git).

## Arkitektur (nåværende design — viktig)

BirdNET kjører på **hjemmeserveren**, ikke på Pi-en. Pi-en er en tynn lydsensor.

```
[Pi ute]   morgen → arecord tar opp ~1 min lyd → scp/last opp til serveren
[Server]   BirdNET på lyden (norsk lat/lon) → birds.json
           → generate_daily_image.py leser birds.json → Gemini-bilde → push til rammen
```

## Maskiner og tilgang

- **Hjemmeserver** — `ssh bruker@192.168.1.38` (x86_64,
  Python 3.12.3). **Kun SSH-nøkkel (passord-innlogging AV).** Prosjekt i
  `/opt/fugleramme` (eid av `bruker`, chown -R gjort). To venv:
  - `/opt/fugleramme/venv` — bilde-pipeline (numpy, pillow, google-genai, requests)
  - `/opt/fugleramme/venv-birdnet` — BirdNET (birdnetlib, tensorflow-cpu, librosa, resampy)
  - `frame_server.py` kjører som systemd-tjeneste `fugleramme-frame-server` (User=bruker) på port 8090.
  - Cron kjører dagens bilde kl. 07 (se «Fallgruver» pkt. 1 for den eksakte linja).
  - Hemmeligheter i `/opt/fugleramme/frame_server.env` (`GEMINI_API_KEY`, `FRAME_HOST=fugleramme.local`).
- **Utendørs sensor** — `ssh bruker@192.168.1.225` (hostname `fugleramme-pi`,
  Raspberry Pi 3 model B, Raspberry Pi OS 64-bit, Debian trixie). **Dette er en
  testbenk**; endelig hjem blir en Pi Zero 2W (bestilt) — alt overføres 1:1.
  - `alsa-utils` installert. **Pi-en har SSH-nøkkel til serveren** (kan `scp` dit passordfritt).
  - INMP441 I2S-mikrofon loddet og virker. Kabling: VDD→pinne1(3.3V), GND→pinne6,
    SCK→pinne12(GPIO18), WS→pinne35(GPIO19), SD→pinne38(GPIO20), L/R→pinne9(GND).
  - `/boot/firmware/config.txt`: `dtparam=i2s=on` + `dtoverlay=googlevoicehat-soundcard`.
  - Mikrofon = **card 1**, enhet **`plughw:1`**. Opptak: `arecord -D plughw:1 -c1 -r 48000 -f S32_LE ...`
  - Kamera (RPi HQ Camera V1.0 + 6mm lens, og Camera Module 3) virker også (`rpicam-still`).
- **E-ink-ramme** — `fugleramme.local` (ESP32-S3, DHCP — var `.94`, er `.92` per
  2026-08-27, så ikke hardkod IP-en noe sted). HTTP-server; `POST /display`
  med **nøyaktig 960000 byte** tegner bildet. Push, ikke pull. Linux-serveren
  mangler `libnss-mdns`, men `push_to_frame.py` gjør mDNS-oppslaget selv.

## Bevist (verifisert virker)

- Dagens bilde-pipeline (Gemini → dither → push) kjører automatisk via cron (fikset).
- BirdNET på serveren kjenner igjen arter — **ende-til-ende testet**: fuglelyd
  spilt på Mac → tatt opp på Pi-mikrofonen → `scp` til server → BirdNET ga
  **European Robin 0.92**. Hele kjeden fungerer.

## Viktige filer (repo `~/workspace/fugleramme`, speilet til `/opt/fugleramme` på server via `deploy/deploy.sh`)

- `tools/generate_daily_image.py` — dagens bilde. `get_weather()` (Open-Meteo,
  lat 60.09 lon 10.93), `build_prompt(weather, subject, style, ref, daily_subject)`,
  `DAILY_SUBJECTS` (tilfeldige fugler) + `STYLES` (tilfeldig stil), `generate_image()`
  (Gemini `gemini-2.5-flash-image`, retry på 503), `fit_to_screen()` (1200x1600),
  `to_epaper()` (Atkinson-dither → 6 farger → 960000 byte), `archive_original()`
  (www/arkiv/), `run(subject, style, ref_images)`. `main()`=`run()`=dagens.
- `tools/push_to_frame.py` — `POST frame.bin` til rammen (`FRAME_HOST`), retries,
  håndterer firmwarens «connection reset»-snurr.
- `tools/frame_server.py` — HTTP-server :8090: webapp (galleri+generer),
  `/api/generate {emne,stil,seeds}`, `/api/send {name}`, `/generate` (Siri),
  `/daily`, serverer `/arkiv/`. Importerer `generate_daily_image` + `push_to_frame`
  (kjører i `venv`). systemd-tjeneste.
- `tools/test_birdnet.py` — kjører BirdNET på en WAV (uten lat/lon = alle treff).
  Kjøres med `venv-birdnet/bin/python`.
- `deploy/deploy.sh` — kopier scripts til serveren + restart tjenesten (fra Mac).

## Fallgruver vi har lært (ikke gjenta disse)

1. **Cron bruker `/bin/sh` (dash), ikke bash.** `. frame_server.env` MÅ ha
   ABSOLUTT sti. Dagens fungerende cron-linje på serveren:
   ```
   0 7 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && venv/bin/python3 generate_daily_image.py >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
   ```
2. **To venv** (`venv` for bilde, `venv-birdnet` for BirdNET) — hold adskilt.
3. Serveren har **ingen MTA** → cron-feil FØR log-omdirigeringen forsvinner.
   Test alltid via cron (ikke bare manuelt i bash) med en midlertidig linje 2 min frem.
4. Server: passord-SSH av (kun nøkkel). `/opt/fugleramme` eid av `bruker`. Tjenesten kjører som `bruker`.
5. Panel: 1200×1600 portrett, palett BLACK 0x0 WHITE 0x1 YELLOW 0x2 RED 0x3
   BLUE 0x5 GREEN 0x6, 2 piksler/byte (hoey nibble=venstre), 960000 byte.
6. INMP441 tar opp lavt nivaa — kan trenge forsterkning (`sox`/gain) for beste
   BirdNET-treff, men fungerte (Robin 0.92) uten. Format S32_LE 48kHz mono, `plughw:1`.

## Oppgaven: bygg automatikken

Bygg og test på Pi 3-en (192.168.1.225) + serveren (192.168.1.38). Foreslått:

1. **Server: `birdnet_analyze.py`** (kjøres i `venv-birdnet`). Input: WAV-sti.
   Kjør BirdNET med `lat=60.09, lon=10.93, date=today, min_conf≈0.25` (norsk
   steds-filter → bare plausible arter). Skriv **`birds.json`** (f.eks.
   `/opt/fugleramme/birds.json`): liste over arter `{common_name, scientific_name,
   confidence}`, dedupet, sortert synkende, + tidsstempel. Baser deg på
   `test_birdnet.py`.
2. **Server: motta lyd.** Enkleste: Pi-en `scp`-er WAV til `/opt/fugleramme/audio/`
   og trigger analyse via `ssh bruker@192.168.1.38 'venv-birdnet/bin/python
   /opt/fugleramme/birdnet_analyze.py /opt/fugleramme/audio/<fil>.wav'`. (Alternativ:
   `POST /api/audio` i `frame_server.py`. Velg det enkleste som er robust.)
3. **Pi: `record_and_upload.sh`** — `arecord -D plughw:1 -c1 -r 48000 -f S32_LE
   -d 60 /tmp/fugl.wav`, evt. forsterk, `scp` til serveren, og trigg analysen (pkt. 2).
   Legg i Pi-ens cron ~kl. 06:40 (FØR serverens 07:00-bilde).
4. **Kobling: `generate_daily_image.py`** — les `birds.json` i `run()`/`build_prompt()`.
   Er det ferske deteksjoner (fra i dag), bruk den/de øverste artene som
   `daily_subject` i stedet for tilfeldig `DAILY_SUBJECTS`. Fall tilbake til
   tilfeldig fugl hvis ingen fersk lyd/deteksjon. Behold vær + stil-logikken.
5. **Planlegging:** Pi-cron 06:40 (opptak+opplasting+analyse) → server-cron 07:00
   (bilde, leser `birds.json`). Sørg for at `birds.json` er fersk før 07:00.

**Akseptansekriterium:** Pi tar opp til planlagt tid, `birds.json` oppdateres med
faktiske arter, og 07:00-bildet får en **faktisk hørt fugl** i prompten (verifiser
i `logs/daily.log` sin `Prompt:`-linje).

## Arbeidsflyt-tips for Claude Code

- Rediger scripts i repoet (`~/workspace/fugleramme`), deploy til server med
  `deploy/deploy.sh` (den kjører scp + restart). `generate_daily_image.py`
  plukkes opp av cron automatisk (ingen restart nødvendig for den).
- Pi-scriptene: rediger lokalt/i repo, `scp` til Pi-en (`bruker@192.168.1.225`).
  Vurder en egen `pi/`-mappe i repoet for Pi-siden.
- Test alltid BirdNET-delen med en ekte fuglelyd (spill på Mac, ta opp på Pi),
  og cron-delen via en midlertidig 2-min-linje (se fallgruve 3).
```
