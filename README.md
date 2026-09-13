# Fugleramme

Et DIY-prosjekt som kombinerer fuglelyd-gjenkjenning, værdata og AI-tegnede
fugleplansjer til en daglig oppdatert side på en 13.3" e-ink bilderamme.

Hver morgen: hjemmeserveren setter sammen **dagens fugleside** — artene BirdNET
faktisk hørte i hagen, med norsk og latinsk navn, klokkeslett og sikkerhet, over
en plansje der de samme fuglene sitter på en gren i stil med gamle fuglebøker.
Sida dithres til panelets 6-fargers palett og **pushes** til e-ink-rammen inne,
som viser den og sover til neste morgen.

Fram til august 2026 var det daglige motivet et fritt AI-bilde av dagens fugl.
Den veien finnes fortsatt — den er reserve hvis fuglesida feiler, og den er
fremdeles det Siri-kommandoen og «lag nytt bilde» i webappen bruker.

## Status

- ✅ **Innedel (ePaper-ramme):** bekreftet i live-test 2026-07-21 — `fugleramme.local`
  svarer på ping, og `send_to_frame.py` fikk skjermen til å tegne et bilde.
  Se `firmware/indoor_frame/`.
- ✅ **Bildegenerering (hjemmeserver):** `generate_daily_image.py` på
  `192.168.1.38` genererer et fritt AI-bilde, henter vær, dithrer og skriver
  `frame.bin` i riktig panelformat under `/opt/fugleramme/www/`. Hentes med
  `scp` for inspeksjon/debugging — se «Feilsøking» under. Var den daglige veien
  fram til 2026-08-28; nå reserve for fuglesida, og fortsatt det Siri og
  webappen bruker.
- ✅ **Daglig push:** `tools/push_to_frame.py` sender `frame.bin` videre til
  rammen rett etter generering — se «Daglig flyt» under. Kjøres fra cron på
  hjemmeserveren (07:07, verifisert 2026-07-24).
- ✅ **Webapp + Siri:** `tools/frame_server.py` (systemd-tjeneste, port 8090) —
  galleri over alle genererte bilder, «lag nytt bilde»-skjema, og
  `POST /generate` for Siri-snarveien. Se `docs/Webapp — galleri og
  generering.md` og `docs/On-demand — Siri-kommando.md`. Undersider:
  `/helse` (`tools/helse.py`, status for hele anlegget) og `/fugler`
  (`tools/fugler.py`, dashboard over artene: plansje, hvor ofte, hvor
  sikkert, når på døgnet, med avspilling av opptakene).
- ✅ **Utedel v2 (XIAO ESP32-S3, fuglelyd):** montert ute og i drift
  2026-08-04. Våkner fra deep sleep etter plan (04:00–08:30 hvert 30. min,
  09–21 hver time), tar opp 60 s fra INMP441, POST-er til serveren og sover
  på ~14 µA. Soldrevet: panel → Waveshare Solar Power Manager (D) → 10 Ah
  LiPo → XIAO-ens BAT-pads. Se `firmware/outdoor_sensor/` og
  `docs/Utedel v2 — ESP32-S3 XIAO.md`.
  *(v1 med Raspberry Pi 3 B trakk for mye strøm og døde 2026-07-28 —
  historikk og lærdommer i `docs/Utedel — status og neste steg.md`.)*
- ✅ **Dagens fugleside (hjemmeserver):** `tools/daily_panel.py` kjører hele
  kjeden 07:07, 09:37 og 16:00 (09:37 lagt til 3. sep 2026: kl. 07 hadde
  bare 5 av 14 dager noe å tegne, kl. 09 hadde 9) — `compose_branch.py` (fuglene på grenen) → `render_daily_panel.py`
  (sida som HTML) → `render_panel_png.py` (rastrer + dithrer) → `push_to_frame.py`.
  Feiler noe, faller cron tilbake på `generate_daily_image.py`. Se «Dagens
  fugleside» under.
- ✅ **Plansjebibliotek:** `plates/` — skannede plansjer fra Wikimedia Commons
  (public domain, valgt med `tools/fetch_plates.py`), den faste grenen
  `gren.png`, og én 1:1-fugl per art under `plates/fugler/` med fotpunktet sitt
  i en sidecar-JSON. Lages én gang per art og gjenbrukes hver dag arten dukker opp.
- ✅ **BirdNET-pipeline (hjemmeserver):** `tools/audio_ingest.py` (systemd,
  port 8091) tar imot opptakene og trigger `tools/birdnet_analyze.py` →
  `data/observations.jsonl` (alt, for godt) + `birds.json` (dagens arter, som
  dagens bilde genereres fra). `tools/bird_stats.py` lager statistikk og
  daglig rapport: arter, lydnivå, dekning.

### Kjente snurrer (ikke bugs, men lurt å vite om)

- **`fugleramme.local` er *rammen*, ikke hjemmeserveren.** Navnet peker på
  ESP32-en i bilderammen, som bare svarer med en liten
  statusside på `/` og tar imot `POST /display`.
  Bruk navnet og ikke IP-en. Rammen får adresse fra DHCP, og den byttet fra
  `.94` til `.92` en gang mellom 9. og 19. august. Resultatet står i
  `logs/daily.log`: **åtte døgn på rad (19.–26. aug) med
  `[Errno 113] No route to host`**, mens alt annet gikk som normalt — bildet ble
  generert og arkivert hver morgen, det kom bare aldri fram. Veggen viste
  9. august-bildet i atten dager. Fikset 26. aug ved å installere `libnss-mdns`
  på serveren og sette `FRAME_HOST=fugleramme.local`; første vellykkede push
  var 27. aug. Webappen/galleriet ligger på
  hjemmeserveren, som ikke kunngjør noe `.local`-navn i det
  hele tatt (avahi kjører ikke der) — den må nås på IP:
  `http://192.168.1.38:8090/`.
- **"Connection reset" når du sender med `send_to_frame.py`/`push_to_frame.py`:**
  Firmwaren kalte `client.stop()` rett etter å ha skrevet HTTP-svaret, uten
  å flushe først — det gjorde at klienten av og til fikk en "connection reset"
  mens den prøvde å *lese* svaret, selv om bildet ble mottatt og tegnet helt
  fint. `indoor_frame.ino` flusher nå før hver `client.stop()`, så snurren er
  borte etter reflash. Begge scriptene håndterer den uansett (skiller "klarte
  ikke sende" fra "sendte ok, men fikk ikke lest svaret") og gir en tydelig
  melding i stedet for en traceback — så et brett med gammel firmware virker
  fortsatt.
- **Prompt-styrt komposisjon er ikke til å stole på — mål, ikke håp.** Da
  fuglesida skulle ha et tomt felt til venstre for teksten, ba vi Gemini om det
  i klartekst («the left 48% must be completely empty white paper», gjentatt tre
  ganger). Samme prompt ga **0,1 % blekk i tekstsonen ett forsøk og 14,8 % det
  neste**. Vi ga den til og med en ferdig gren som referansebilde med «reproduser
  denne i samme posisjon» — den tegnet sin egen gren midt på sida og la 20,6 % i
  tekstsonen, altså verre enn uten mal. Løsningen ble å flytte komposisjonen ut
  av modellen: den tegner én fugl om gangen, og `compose_branch.py` limer dem på
  grenen selv. Da er plasseringen et regnestykke og tekstsonen måler 0,0 %.
  Modellen brukes fortsatt til å retusjere kontaktpunktene, men **hvert forsøk måles
  og forkastes hvis det skitner til tekstfeltet**.
- **Gråtoner og gjennomsiktighet finnes ikke på dette panelet.** Et halvgjennom-
  siktig hvitt felt bak tekst virker som en god idé og blir en grumsete flekk:
  fargen finnes ikke i paletten, så dithringen gjetter den med prikker. Ren
  `#fff` treffer paletten eksakt og dithres ikke i det hele tatt. Samme regel
  gjelder alt annet på sida — hele fuglesida er tegnet i de seks fargene, og
  det er derfor teksten blir knivskarp.
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
- **Gemini-regningen er kameraet, ikke fuglesida.** Målt 12. sep 2026: 1559
  kamerabilder på åtte dager til `gemini-3.5-flash` i 1280 px med tenking på,
  anslått 0,05–0,15 kr per bilde og 80–90 % av forbruket; retusjen
  (`gemini-3-pro-image`, 1,27 kr per forsøk, 4–5 om dagen) var resten. Bremsene
  ligger i `tools/bilde_analyze.py` (`KAMERA_MODELL`, `KAMERA_BILDE_PX`,
  `KAMERA_MAKS_PER_TIME`, `KAMERA_PAUSE_429_S`, tokenforbruk i `kamera.jsonl`),
  i `kamera/kamera.py` (`pause_s`, 60 s) og i retusjen (én gang per fuglesett,
  se «Kjøre for hånd»). Forbruket per modell står i AI Studio under Usage, ikke
  på Cloud-fakturaen — den viser bare påfyllingene.

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
│   ├── generate_daily_image.py  Fritt AI-bilde: vær (yr) + dagens hørte fugler
│   │                       (birds.json) -> Gemini -> dither -> frame.bin.
│   │                       Reserve for fuglesida + Siri/webb.
│   ├── frame_server.py     Webapp/galleri + Siri-endepunkt (systemd, port 8090).
│   ├── flash_firmware.sh   Kompiler + flash begge brettene med arduino-cli.
│   ├── audio_ingest.py     Mottak av opptak fra utedelen (systemd, port 8091);
│   │                       trigger analysen. ESP32 kan ikke scp — derfor HTTP.
│   ├── birdnet_analyze.py  BirdNET på én WAV -> observations.jsonl + birds.json.
│   ├── bird_stats.py       Statistikk/rapport: arter, lydnivå, dekning, strøm.
│   │
│   │                       — Dagens fugleside (kjøres i denne rekkefølgen) —
│   ├── daily_panel.py      Inngangspunktet cron kaller. Kjører de tre under.
│   ├── compose_branch.py   Dagens fugler limt på den faste grenen, lokalt.
│   ├── render_daily_panel.py  Sida som HTML på nøyaktig 1200x1600.
│   ├── render_panel_png.py    Rastrer HTML -> PNG -> dither -> frame.bin.
│   │
│   │                       — Plansjebiblioteket (engangsjobb per art) —
│   ├── fetch_plates.py     Kortliste + nedlasting fra Wikimedia Commons.
│   ├── prepare_plates.py   Vasker skanninger: papirtone -> rent hvitt.
│   ├── compose_hero.py     Lager grenmalen; alternativ AI-komponert plansje.
│   └── bird_names.py       Norske navn + kroppslengder, nøklet på latinsk navn.
├── plates/                 Plansjebiblioteket. Kildeskanninger (PD, fra Commons),
│                           gren.png, og fugler/<art>.png + .json med fotpunkt.
│                           vasket/ og dagens-* lages på serveren, ikke i repoet.
├── design/                 Artboards for designcanvaset (tre layoutretninger).
├── pi/                     v1-utedelen (Raspberry Pi 3 B) — pensjonert 2026-08-04,
│                           beholdt som referanse/reserve.
├── deploy/                 deploy.sh + systemd-tjenestefiler for hjemmeserveren.
└── docs/                   Prosjektnotater og guider.
```

**Hjemmeserveren (`192.168.1.38`, utenfor dette repoet, i `/opt/fugleramme/`):**

```
/opt/fugleramme/
├── daily_panel.py             DAGENS SIDE — det cron kjører (07:07)
├── compose_branch.py          fuglene på grenen
├── render_daily_panel.py      sida som HTML
├── render_panel_png.py        rastrering + dithring -> frame.bin
├── plates/                    plansjer, gren.png, fugler/ (1:1 + fotpunkt)
│   ├── vasket/                hvitpunkt-korrigerte plansjer (lages lokalt)
│   └── dagens-bakgrunn.png    dagens ferdige illustrasjon + .json med sonemåling
├── generate_daily_image.py   Reserve hvis fuglesida feiler + Siri/webb-bilder.
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
Filene i `www/` serveres **ikke** over HTTP. Vil du se hva som ble generert,
bruk galleriet i webappen på `http://192.168.1.38:8090/` (viser hele arkivet
under `/arkiv/`), eller hent filene direkte med `scp` — se «Feilsøking» under.
Rammen henter uansett ikke selv; den får bildet pushet (se under).

## Hvordan alt henger sammen (daglig flyt)

```
[Hjemmeserver 192.168.1.38]                      [ESP32-S3 e-Paper-ramme]
daily_panel.py                                     "fugleramme.local"
  → compose_branch.py                                    (HTTP-server, port 80)
      les birds.json (dagens arter)
      hver art: 1:1-fugl fra plates/fugler/
      lim dem på plates/gren.png i faste
        festepunkter, skalert etter cm
      Gemini retusjerer kontaktpunktene
      mål tekstsonene → forkast om urent
  → render_daily_panel.py
      yr / api.met.no (vær)
      HTML 1200x1600, tekst i palettfarger
  → render_panel_png.py
      headless chromium → PNG
      Atkinson-dither, pakk 2 px/byte
  → skriv www/frame.bin  ──┐
                            │
push_to_frame.py           │
  → les frame.bin  ────────┘
  → POST http://fugleramme.local/display  ────────►  mottar 960000 byte
                                                       → tegner på panelet
                                                       (~20-35 sek)
```

Hele kjeden trigges av **ett cron-kall** på hjemmeserveren (`crontab -e`,
byttet fra AI-bildet til fuglesida 2026-08-28):

```cron
7 7 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && { venv/bin/python3 daily_panel.py || venv/bin/python3 generate_daily_image.py; } >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
```

**AI-bildet er reserven.** `daily_panel.py` går bare ut med 0 hvis `frame.bin`
faktisk finnes og er 960000 byte. Har ingen av dagens arter fått plansje ennå,
eller er Gemini nede, kjører `generate_daily_image.py` i stedet — da henger det
et bilde på veggen i stedet for ingenting. Push-steget bryr seg ikke om hvem som
lagde fila.

Merk at 07:07 er tidlig for en side som sier «Hørt i dag»: klokka sju rommer
lista bare morgenøktene (04:00–07:00). Headeren teller opptakene, så det er ikke
usant — men vil du ha hele dagen, må jobben flyttes til kvelden.

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

## Dagens fugleside

Sida er ett fast oppsett: infoboks oppe til venstre, artslista under den,
bunnlinje, og en fugleplansje som fyller resten av arket. Alt er tegnet i
panelets seks farger, så teksten dithres ikke.

### Å legge til en ny art

Når BirdNET hører noe nytt, trengs to engangsjobber. Begge lagres og gjenbrukes
hver dag arten dukker opp igjen.

**1. Finn en plansje.** Commons har en `<Vitenskapelig navn> (illustrations)`-
kategori for 40 av de 41 artene vi har hørt så langt — Gould, Keulemans,
Naumann, Morris — alle falt i det fri. Kategoriene inneholder også frimerker,
lydfiler og 250 px-utsnitt, så maskinen lager kortliste og du velger:

```bash
python3 tools/fetch_plates.py --shortlist --birds birds.json --out plates/velg.html
python3 tools/fetch_plates.py --get "File:Keulemans Onze vogels 1 33.jpg" --for "Spinus spinus"
python3 tools/prepare_plates.py          # vasker papirtonen til rent hvitt
```

Velg plansjer med **lyst papir**. En mørk, gulnet skanning lar seg ikke redde av
hvitpunkt-korreksjonen, og blir grumsete på panelet.

**2. Fuglen tegnes.** Første gang arten er med på sida lager `compose_branch.py`
en 1:1-fugl av den med plansjen som forelegg, og bestemmer fotpunktet med
`gemini-3.5-flash`. Begge deler lagres i `plates/fugler/`. Sjekk resultatet:

```bash
python3 tools/compose_branch.py --sjekk-foetter fotpunkter.png
```

Kontaktarket viser hver fugl med et kryss der fotpunktet er satt. Ser et feil ut,
rett `fot` i artens `.json` og sett `"kilde": "manuell"` — da rører ingen senere
kjøring det igjen, heller ikke `--nye-fotpunkter`.

### Hvorfor fotpunkt og ikke bunnkant

Nederste piksel i bildet er **halespissen** på en skjære, ikke foten. Aligner man
på den, lander halen på veden og fuglen henger i lufta over. Samme gjelder
vannrett: sentrerer man på bildets bredde, havner føttene godt til side for
festepunktet fordi halen drar tyngdepunktet med seg. Fotpunktet løser begge.

### Størrelser

Fuglene skaleres etter faktisk kroppslengde (`LENGDE_CM` i `bird_names.py`,
totallengde med hale). Rett proporsjon går ikke — en gråhegre på 94 cm ville
gjort grønnsisiken på 12 til en flekk — så det komprimeres:

```
skala = (lengde / 21 cm) ** 0,6,   klemt til 0,55–1,60
```

Med rødvingetrosten som midtpunkt gir det skjære 1,56× og grønnsisik 0,71×.
Største art får den tykkeste greina nederst, minste den tynne kvisten øverst.

### Festepunktene

`ANKRE` i `compose_branch.py` er en liste `(x, y, høyde, speilvendt)` sortert
nedenfra og opp. `y` snappes til greinas faktiske overflate, så punktene kan
settes omtrentlig — `--kart` viser hvor grenen har ved ved hver x.

Hver fugl prøver ankrene i tur og orden og tar det første der den får stå i fred
(inntil 22 % overlapp; en flokk på samme grein skal stå tett). Vil du ha flere
fugler på sida, legg til ankre og hent plansjer for flere arter — resten ordner
seg selv.

### Tekstsonen er en hard sperre

Ingen fugl får overlappe feltet der teksten står (venstre 48 %, ned til 75 % av
høyden). Blir en fugl bred nok til å nå inn, flyttes den sidelengs — og
`perch_y` finner ny ved under føttene, så den ikke blir stående og sveve. Er den
for bred til å få plass til høyre, krymper den i stedet.

Etterpå måles sonene uansett, i vannrette bånd og ikke som snitt: en enslig fugl
midt i artslista ga 1,9 % totalt — under grensen — mens den lå rett oppå fire
linjer tekst. Sonen som ikke blir ren, får en **helt ugjennomsiktig** hvit pute
under teksten.

### Kjøre for hånd

```bash
# på serveren, i bilde-venv-et
venv/bin/python daily_panel.py                    # hele kjeden -> www/frame.bin
venv/bin/python compose_branch.py --birds birds.json --retusj 0   # uten AI-retusj
venv/bin/python render_daily_panel.py --bar paa   # med konfidens-bar
RETUSJ=0 venv/bin/python daily_panel.py             # spar et Gemini-kall
```

`--retusj` sender det ferdige arket tilbake til Gemini for å få tærne til å gripe
rundt veden. `gemini-3-pro-image` gjør det merkbart bedre enn
`gemini-2.5-flash-image` og er standard for akkurat det steget; det daglige
AI-bildet bruker fortsatt sin egen modell.

Retusjen koster 1,27 kr per forsøk, og fra 13. sep 2026 gjøres den **én gang
per fuglesett per dag**: sidecar-JSON-en husker hvilket sett som ble retusjert
(`retusj_signatur`), og står de samme fuglene på de samme plassene i neste
kjøring, gjenbrukes arket uten nytt kall. Et forkastet forsøk gjentas heller
ikke; bare et forsøk som feilet (429, nett) får prøve igjen. Standard er ett
forsøk (`RETUSJ=1`), tidligere to.

## Kom i gang / test alt

**1. Flash firmwaren (kun hvis brettet ikke allerede kjører den)**

```bash
cp firmware/indoor_frame/config.example.h firmware/indoor_frame/config.h
# fyll inn WiFi-navn/passord (2,4 GHz), så:
./tools/flash_firmware.sh --monitor
```
Scriptet kompilerer og laster opp med riktige board-innstillinger (ESP32S3 Dev
Module, Flash 32MB, PSRAM OPI) uten at Arduino IDE er involvert. Serial Monitor
(115200) viser IP-en og `http://fugleramme.local`. Førstegangsoppsett av
arduino-cli og feilsøking: `docs/Flashing med arduino-cli.md`.

> **Etter en reflash kan rammen få ny DHCP-IP.** Da må `FRAME_HOST` i
> `/opt/fugleramme/frame_server.env` oppdateres, ellers feiler både cron-jobben
> 07:07 og webappen/Siri med `[Errno 113] No route to host`. Se siste avsnitt i
> flashe-dokumentet for engangsfiksen og de to varige.

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
scp bruker@192.168.1.38:/opt/fugleramme/www/frame.bin /tmp/frame.bin
ls -la /tmp/frame.bin                       # skal være nøyaktig 960000 byte
curl -s -X POST --data-binary @/tmp/frame.bin \
     -H "Content-Type: application/octet-stream" \
     http://fugleramme.local/display
```
Se på skjermen: stemmer motivet og fargene med forhåndsvisningen? Hent den med
`scp bruker@192.168.1.38:/opt/fugleramme/www/preview.png /tmp/ && open /tmp/preview.png`.
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
