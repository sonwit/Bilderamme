# Utedel v2 — Seeed XIAO ESP32-S3

Sist oppdatert: 2026-08-04 — **montert ute og i drift.** Full kjede verifisert:
deep sleep etter plan → opptak → opplasting → BirdNET → statistikk.

Erstatter Raspberry Pi 3 B som lydsensor. Hvorfor: Pi-en trakk ~450 mA i
tomgang, fikk undervoltage-dipp på solcelledrift og har ingen sovemodus.
XIAO ESP32-S3 bruker ~100 mA i de ~1,5 minuttene en økt varer og **~14 µA i
deep sleep** — ekte duty-cycling, det dokumentet om v1 konkluderte med at
krevde ekstra maskinvare (Witty Pi/PiJuice) på en Pi.

**Strømregnskap:** ~23 økter/døgn à ~90 s aktiv ≈ **60–70 mAh/døgn**, mot
Pi-ens ~10 000 mAh/døgn. Grovt 150× mindre.

## Arkitektur (det eneste som endres er venstre boks)

```
[XIAO ute]  deep sleep → våkner etter plan → 60 s I2S-opptak (INMP441, PSRAM)
            → wifi på → NTP → HTTP POST til serveren → deep sleep
[Server]    audio_ingest.py (:8091) lagrer audio/fugl_<stamp>.wav + helse-json
            → trigger birdnet_analyze.py (samme som før)
            → observations.jsonl / birds.json / statistikk — UENDRET
```

ESP32 kan ikke scp/ssh, derfor HTTP. Mottakeren `tools/audio_ingest.py`
kjører i BirdNET-venvet som egen systemd-tjeneste og bruker samme
filnavnkonvensjon (`fugl_YYYYmmdd_HHMMSS.wav`), så analysen og statistikken
merker ikke forskjell.

## Deler (fra ordren + det vi har)

- **Seeed XIAO ESP32-S3** (uten Sense — vi bruker INMP441-en vi har)
- **INMP441** I2S-mikrofon (flyttes fra Pi-en)
- ESP32-S3-DevKitC 8MB PSRAM — reserve/benkebrett, samme firmware kan testes der
- Breadboard 400 + koblingstråd — benketest før lodding
- JST-PH-kabler — til LiPo på BAT-padene (alternativ B under)
- USB-C-kabel med åpen ende — 5V fra dagens solcellebank (alternativ A)

## Kobling INMP441 ↔ XIAO

```
INMP441        XIAO ESP32-S3
-------        -------------
VDD     →      3V3
GND     →      GND
L/R     →      GND            (venstre kanal)
SCK     →      D1  (GPIO2)
WS      →      D2  (GPIO3)
SD      →      D3  (GPIO4)
```

Pinnene er valgt i `config.h` og kan flyttes fritt (ESP32-S3 har GPIO-matrise).
Hold ledningene korte (<10 cm) — I2S-klokka går på 3 MHz ved 48 kHz.

## Strøm — dagens rigg gjenbrukes som den er

Riggen består av (kartlagt 2026-08-03):
- **Waveshare Solar Power Manager (D)** — MPPT-lader for 6–24 V panel,
  lader en 3,7 V Li-celle, gir regulert 5 V/3 A ut (Type-C + skruterminal).
- **3,7 V 10 000 mAh LiPo** (1260100-celle) på batteriterminalene.
- Solcellepanelet inn på DC-kontakten/skruterminalen (6–24 V, MPPT ordner resten).

Kobling — **XIAO rett på batteriet** (testresultat 2026-08-03, se under):
JST-kabel loddet på XIAO-ens BAT-pads (undersiden: + til BAT+, − til BAT−,
**verifiser polaritet før tilkobling**) → manager-ens batteriterminaler
(skruterminalen). Manager-ens 5V-utgang står UBRUKT. USB-C på XIAO-en kan
fortsatt brukes samtidig til flashing/benketest.

**Hvorfor ikke 5V-utgangen? Testet og forkastet (2026-08-03).** Boosteren
(SW6201S, powerbank-brikke) kutter utgangen når lasten faller til µA — og
XIAO-en sover på 14 µA. Målt over 41 min / 9 økter: `boot_count` i
helse-JSON-en ble nullstilt gjentatte ganger (kutt i 5 av 8 søvnperioder,
vaklende mønster selv etter dobbelttrykk/«low-current mode», som uansett er
udokumentert og kan utløpe av seg selv). Systemet selvhelbredet riktignok —
brikkens testpulser gir XIAO-en strøm igjen etter ~3 min og kaldstart gir
umiddelbar økt — men i normal drift ville det ødelagt opptaksplanen totalt.
Rett-på-batteri fjerner hele feilklassen: 14 µA-søvn er nettopp det
BAT-padene er laget for, og manageren fortsetter som MPPT-lader og
underspenningsvern (3,0 V) for cellen.

Regnestykke: XIAO-en bruker ~60–70 mAh/døgn; manageren har selv noen mA
hvilestrøm som nå blir største forbruker (~50–700 mAh/døgn avhengig av modus).
Med 10 Ah batteri er det likevel uker med buffer uten sol — mot Pi-ens
~10 000 mAh/døgn var dette aldri i nærheten av å gå rundt.

**Valgfritt, anbefalt:** mål batterispenningen. To like motstander (f.eks.
2×220 kΩ) som spenningsdeler fra manager-ens BAT+-skruterminal til GND,
midtpunktet til XIAO A0/GPIO1 (GND er felles via USB-kabelen). Sett
`BATT_ADC_PIN 1` i config, og statistikken får endelig ekte batterispenning
(`volt` i helse-JSON) — det v1-riggen aldri kunne måle.

## Steg 1 — Server: mottakeren

```bash
~/workspace/fugleramme/deploy/deploy.sh
```

Deployer nå også `audio_ingest.py` + `fugleramme-audio-ingest.service`.
Verifiser med et hvilket som helst WAV-opptak:

```bash
curl -X POST --data-binary @test.wav -H 'Content-Type: audio/wav' \
     'http://192.168.1.38:8091/upload?stamp=20260803_120000'
```

Svar `{"ok": true, ...}` og deretter analyse i loggen:
`ssh bruker@192.168.1.38 'journalctl -u fugleramme-audio-ingest -n 20'`

Valgfritt: sett `INGEST_TOKEN=...` i `/opt/fugleramme/frame_server.env` (og
samme verdi i firmware-`config.h`) hvis du vil ha et lite lås på endepunktet.

## Steg 2 — Firmware

1. Arduino IDE med **esp32-core ≥ 3.0** (Boards Manager: "esp32 by Espressif").
2. Board: **XIAO_ESP32S3**. Tools → **PSRAM: "OPI PSRAM"** (må på — opptaket
   ligger i PSRAM; uten får du feilmelding om ps_malloc i Serial Monitor).
3. `cp firmware/outdoor_sensor/config.example.h firmware/outdoor_sensor/config.h`
   og fyll inn wifi + server. Sett `TEST_INTERVAL_S 120` for benketesting
   (økt hvert 2. min i stedet for planen).
4. Åpne `outdoor_sensor.ino`, koble XIAO via USB-C, **Upload**.
5. Serial Monitor (115200): du skal se opptak → wifi → `Opplastet (5625 kB)` →
   `TESTMODUS: sover 120 s`. Sjekk at opptaket dukker opp i
   `ssh bruker@192.168.1.38 'ls -lt /opt/fugleramme/audio | head'`.
6. **Lytt på et testopptak** (verifiser at mikrofonen faktisk hører noe):
   `scp bruker@192.168.1.38:/opt/fugleramme/audio/fugl_*.wav /tmp/ && open /tmp/fugl_*.wav`
7. Sett `TEST_INTERVAL_S 0` og flash på nytt → normal plan (04:00–08:30 hvert
   30. min, 09–21 hver time, sover 21:00→04:00 — samme som Pi-ens crontab).

Merk om USB og deep sleep: XIAO-en re-enumererer USB ved hver oppvåkning, så
Serial Monitor mister forbindelsen mellom økter. Det er normalt. Ved kaldstart
venter firmwaren 2,5 s så du rekker å åpne monitoren.

## Steg 3 — Migrering ✅ (gjennomført 2026-08-03/04)

Slik gikk det (avvik fra planen i kursiv):

1. Benketest inne: full kjede + mikrofon (RMS −22 dBFS) verifisert på under
   en time. *Pi-en viste seg å ha vært død siden 28. juli (batteri/SD), så det
   var ingenting å bevare — mikrofonen ble flyttet med en gang.*
2. Strømtest mot manageren: 5V-utgangen FORKASTET (se «Strøm» over) → XIAO
   rett på batteriet. Verifisert med klatrende `boot_count` gjennom en hel
   natts deep sleep (04:00-øktene traff på sekundet).
3. Montert ute 2026-08-04. Signal fra plassen: **−84 til −87 dBm — på
   kanten, men alle opplastinger lykkes.** Følg dekningen; første grep ved
   frafall er antenna ut av kassa (vertikalt, fritt), så flytting/repeater.
4. *Vindfunn etter montering:* vind rett på membranen ga ~100 % av
   lydenergien under 100 Hz, klipping, og falske BirdNET-treff («myrrikse» =
   rytmiske vindstøt). Fikset med skumgummi over mikrofonåpningen (porten
   peker nedover) + høypassfilter i firmware (`HIGHPASS_HZ 150`). Resultat:
   RMS fra −23 til −44 dBFS, null klipping.

Daglig oppfølging:
```bash
ssh bruker@192.168.1.38 'cd /opt/fugleramme && python3 bird_stats.py'
curl -s http://192.168.1.38:8091/status
```
Dekningen er nøkkeltallet. Helse-JSON-en fra ESP-en har
`boot_count`/`uploads_failed`/`temp_c` (og `volt` når deleren kommer på) i
stedet for Pi-ens throttle/undervoltage-felter — `uptime_s` sendes bevisst
IKKE, siden hver deep sleep-oppvåkning er en omstart og ville forsøplet
omstart-statistikken. `boot_count` som nullstilles = strømbrudd;
`uploads_failed` som øker = wifi-trøbbel.

## Fjernkonfig — juster parametre uten aa hente ned boksen

ESP-en henter `GET /config` fra mottakeren etter hver opplasting og tar
verdiene i bruk fra **neste** oekt (lagres i RTC-minne; stroembrudd = tilbake
til config.h-standardene til neste henting). Endre fra Macen:

```bash
curl -X POST --data '{"rev": 2, "gain_shift": 12}' http://192.168.1.38:8091/config
```

Gyldige noekler: `gain_shift` (8–16), `highpass_hz` (0–2000), `rec_seconds`
(10–75, PSRAM-grense), `test_interval_s` (0=plan, ellers benketest),
`dawn_start/dawn_end/dawn_interval_min/day_start/day_end` (opptaksplanen —
juster naar vinteren flytter graalysningen). Bump `rev` ved hver endring:
brikken ekkoer den som `cfg_rev` i helse-JSON-en, saa du ser i observasjonene
noeyaktig naar den plukket opp endringen. Verdiene klemmes til trygge omraader
i firmwaren.

## Kjente quirks i drift (ufarlige)

- **NTP over svakt wifi feiler av og til** (UDP drukner først). Da stemples
  opptaket med den driftende RTC-klokka og kan bomme med ~2 min. Kosmetisk.
- **Tidlig-våkning kan gi dobbeltøkt:** våkner den for tidlig (drift), tar den
  økta, NTP-korrigeres, ser at det ekte slottet gjenstår — og tar det også.
  Koster ett minutt batteri.
- **Ett fullskala-sample ved opptaksstart** (høypassfilterets DC-sprang).
  Serveren normaliserer derfor på 99,9-persentil-peak (`peak999`), ikke
  absolutt peak. Firmware-fix (filter primes på første sample) er skrevet og
  flashes ved neste anledning.

## Videre planer

1. **Batterimåling** (deler kjøpt hos Kjell 2026-08-04): 2×100 kΩ fra
   manager-ens BAT+ til GND, midtpunkt til D0, `BATT_ADC_PIN 1` i config,
   reflash. Da får statistikken `volt` i hver økt.
2. **Permanent lodding:** flytt fra breadboard til 60×80 mm hullplate med
   stablebar sokkel for XIAO-en (breadboard-fjærkontakter ruster ute).
   Krympestrømpe på loddepunktene.
3. **Ideer, uprioritert:** INA219 på I²C (D4/D5) for ekte energiregnskap;
   BME280 for lufttemperatur/fuktighet i kassa (brikketemp `temp_c` logges
   allerede, men ligger noen grader varmt); LittleFS-kø for opptak ved
   wifi-frafall (krever egen partisjonstabell).

## Kjente valg og begrensninger (v1)

- **Ingen opptakskø.** Feiler opplastingen (3 forsøk) droppes opptaket — PSRAM
  overlever ikke deep sleep, og XIAO-en har ikke SD-kort. Hullet synes i
  dekningen. Blir wifi-tap et reelt problem: v2-idé er én kø-plass i flash
  (LittleFS, krever egen partisjonstabell) — eller flytt riggen/repeateren
  (v1-målingene viste −72 til −75 dBm, det koster også strøm).
- **Klokkedrift i deep sleep** (RC-oscillator, ±2–3 %): etter nattesøvnen kan
  første økt bomme med noen minutter. Tidsstempelet på opptaket er likevel
  riktig — det regnes bakover fra NTP-synket klokke ved opplasting.
- **Digital gain `GAIN_SHIFT 14`** (+12 dB vs Pi-ens S32→S16). INMP441 tar opp
  lavt; dette bevarer flere signalbiter før serverens peak-normalisering.
  Klipper opptak (`clipped_pct` i statistikken), sett 15 eller 16.
- Kamera: XIAO-en har ikke kamera (det har Sense-varianten). Uaktuelt nå.
