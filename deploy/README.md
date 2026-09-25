# deploy/ — serveren

Hjemmeserveren er en Linux-maskin på samme nett som rammen. Alt ligger flatt
i `/opt/fugleramme/`, eid av brukeren tjenestene kjører som. Ingenting i
`www/` serveres over HTTP; galleriet i webappen viser arkivet.

```
/opt/fugleramme/
├── *.py                       scriptene fra tools/, kopiert av deploy.sh
├── plates/                    plansjer, gren.png, fugler/ (1:1 + fotpunkt), maler/*.json
│   ├── vasket/                hvitpunkt-korrigerte plansjer (lages her)
│   └── dagens-bakgrunn.png    dagens illustrasjon + .json med sonemåling
├── frame_server.env           hemmeligheter og oppsett (se under)
├── esp_config.json            fjernkonfigen utedelen henter
├── birds.json                 DAGENS aggregerte artsliste
├── audio/                     innkomne opptak + helse-sidecars (ryddes etter 21 dager)
├── bilder/                    kamerabilder + meta
├── data/observations.jsonl    én linje per analysert opptak, for godt
├── data/kamera.jsonl          én linje per analysert kamerabilde
├── logs/                      daily.log, stats.log, vakt.log
├── venv/  venv-birdnet/       to venv-er: bilde/Gemini og BirdNET
└── www/
    ├── frame.bin              dagens bilde i panelformat (960 000 byte)
    ├── preview.png            slik frame.bin faktisk ser ut
    ├── original.png           bildet før dithering
    └── arkiv/                 alt som er generert, med tidsstempel
```

## To venv-er

```bash
python3 -m venv /opt/fugleramme/venv
/opt/fugleramme/venv/bin/pip install google-genai pillow numpy requests playwright
/opt/fugleramme/venv/bin/playwright install chromium-headless-shell

python3 -m venv /opt/fugleramme/venv-birdnet
/opt/fugleramme/venv-birdnet/bin/pip install birdnetlib numpy soundfile
```

BirdNET og bildebiblioteket lever i hver sin venv med vilje: de drar inn
forskjellige tunge avhengigheter, og sidene som serveres er ren `stdlib` så de
kjører i begge. `headless-shell`, ikke full chromium: den starter uten
`libatk`/`libcups`, som ville krevd root.

## frame_server.env

Kopier `frame_server.env.example` til `/opt/fugleramme/frame_server.env` og
fyll inn. Både systemd-tjenestene og cron-linjen leser den.

| Variabel | Hva |
|---|---|
| `GEMINI_API_KEY` | Kreves. Samme nøkkel for bildene, retusjen og kameraanalysen. |
| `FRAME_HOST` | Rammens adresse. Bruk navnet `fugleramme.local`, ikke IP: brettet får adresse fra DHCP. |
| `FRAME_SERVER_PORT`, `FRAME_TOKEN` | Webappens port (8090) og valgfri delt hemmelighet. |
| `INGEST_PORT`, `INGEST_TOKEN` | Mottaket fra utedelen (8091) og valgfri token, samme som i utedelens `config.h`. |
| `FUGLERAMME_LAT`, `FUGLERAMME_LON` | Hvor hagen er. To desimaler holder. Styrer været, BirdNETs artsfilter og soloppgangen. |
| `FUGLERAMME_STED` | Stedsnavnet på fuglesiden. |
| `FUGLERAMME_KONTAKT` | Kontakten i User-Agent mot api.met.no og Commons. E-post eller URL. |
| `VARSEL_URL` | Hvor vakten sender meldinger, for eksempel en ntfy.sh-kanal. Uten: bare loggen. |
| `PANEL_SURE_CONF`, `PANEL_BLOKKERT`, `PANEL_SORTERING` | Terskel, blokkliste og sortering på fuglesiden. |
| `TEGN_MIN_OEKTER` | Hvor mange økter en art må være hørt i for å bli tegnet. Standard 1. |
| `RETUSJ`, `RETUSJ_MODELL`, `FUGL_MODELL`, `VISION_MODEL`, `IMAGE_MODEL` | Modellvalg og antall retusjforsøk. |
| `KAMERA_MODELL`, `KAMERA_BILDE_PX`, `KAMERA_MAKS_PER_TIME`, `KAMERA_PAUSE_429_S` | Kostnadsbremsene på kameraanalysen. |
| `BIRDNET_MIN_CONF`, `BIRDNET_NORM_PEAK`, `AUDIO_KEEP_DAYS` | Analysens terskler og hvor lenge lyd beholdes. |

Alle scriptene leser variablene sine med `os.environ.get(..., standard)`, så
det som ikke står i filen får standardverdien i scriptet.

## deploy.sh

```bash
cp deploy/deploy.env.example deploy/deploy.env     # FUGLE_SERVER=bruker@server, ignorert av git
deploy/deploy.sh
```

Scriptet kopierer python-scriptene i listen si, plansjene og malenes JSON,
installerer tjenestefilene med `User=` satt til SSH-brukeren (overstyr med
`FUGLE_USER`), og restarter tjenestene. Det ber om sudo-passordet på
serveren. Det rører aldri `frame_server.env` eller `www/`.

Et nytt script som en tjeneste importerer må inn i listen i `deploy.sh`.
Ellers svarer `/helse`, `/fugler` eller `/dag` med 500 mens resten av
serveren ser frisk ut, eller `GET /config` faller tilbake til filen.

## systemd

To tjenester på serveren, filene ligger her:

| Tjeneste | Script | Port |
|---|---|---|
| `fugleramme-frame-server` | `frame_server.py` i `venv` | 8090 |
| `fugleramme-audio-ingest` | `audio_ingest.py` i `venv-birdnet` | 8091 |

`deploy.sh` installerer dem. For hånd:

```bash
sudo cp fugleramme-*.service /etc/systemd/system/     # bytt User= først
sudo systemctl daemon-reload
sudo systemctl enable --now fugleramme-frame-server fugleramme-audio-ingest
journalctl -u fugleramme-audio-ingest -f
```

`fugleramme-kamera.service` hører til Pi-kameraet i `kamera/` og installeres
på Pi-en, ikke på serveren.

## cron

Den daglige kjeden kjøres tre ganger om dagen, og bare morgenkjøringen har
reserven:

```cron
# Frokostsiden 07:07: hele gårsdagen. Feiler den, faller cron tilbake på AI-bildet.
7 7 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && { venv/bin/python3 daily_panel.py || venv/bin/python3 generate_daily_image.py; } >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
# 09:37: dagens første tegnbare fugler. 16:00: dagen så langt. Ingen reserve her:
# feiler de, blir forrige side hengende heller enn at et AI-bilde tar plassen.
37 9 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && venv/bin/python3 daily_panel.py >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
0 16 * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && venv/bin/python3 daily_panel.py >> logs/daily.log 2>&1 && venv/bin/python3 push_to_frame.py >> logs/daily.log 2>&1
# Statistikk for dagen, og vakten hvert kvarter. Begge er ren stdlib og går på systemets python3.
0 22 * * * cd /opt/fugleramme && python3 bird_stats.py --day $(date +\%F) >> logs/stats.log 2>&1
*/15 * * * * cd /opt/fugleramme && set -a && . /opt/fugleramme/frame_server.env && set +a && python3 vakt.py >> logs/vakt.log 2>&1
```

Tre ting som må være som over, ellers feiler cron stille:

1. **`venv/bin/python3`, ikke `/usr/bin/python3`.** Systemets python mangler
   numpy, pillow og google-genai.
2. **`. /opt/fugleramme/frame_server.env` med absolutt sti.** Cron kjører
   `/bin/sh` (dash), og dash sin `.` leter bare i `$PATH`. Med relativ sti
   blir det `not found`, kjeden stopper, og Python starter aldri. Den
   klassiske «virker i bash, feiler i cron»-fellen.
3. **`mkdir -p /opt/fugleramme/logs`** må være gjort.

Serveren har ingen e-postserver, så feil *før* log-omdirigeringen forsvinner.
Test derfor alltid via cron, ved å legge en midlertidig linje to minutter
fram, ikke bare manuelt i bash.

07:07 og ikke 07:00 med vilje: vær-API-er er mest overbelastet på hel time.

## Etter en reflash av rammen

Rammen kan få ny DHCP-adresse. Med `FRAME_HOST=fugleramme.local` og
`libnss-mdns` på serveren løser det seg selv. Ryker mDNS, sett en IP i
`frame_server.env` til det er oppe igjen, ellers feiler både cron og webappen
med `[Errno 113] No route to host`.

## Nettsiden: eksport fra serveren

Serveren pusher hver tegnet dag til repoet selv, og GitHub Pages bygger
siden. Det går utenom `deploy.sh`: scriptet kjører fra en klone av repoet.

- Klonen ligger i `/opt/fugleramme/repo`, med `user.email` satt til
  noreply-adressen. `git pull` skjer i starten av hver eksport, så scriptet
  oppdaterer seg selv.
- Nøkkelen er `~/.ssh/bilderamme-deploy`, en deploy key med skriverett på
  bare dette repoet, koblet til vertsnavnet `github.com-bilderamme` i
  `~/.ssh/config`. Den kan ikke brukes til noe annet på GitHub.
- Cron kjører eksporten etter hver tegning og logger til `logs/nettside.log`:

```
20 7  * * * cd /opt/fugleramme && venv/bin/python3 repo/tools/eksporter_dag.py >> logs/nettside.log 2>&1
50 9  * * * cd /opt/fugleramme && venv/bin/python3 repo/tools/eksporter_dag.py >> logs/nettside.log 2>&1
15 16 * * * cd /opt/fugleramme && venv/bin/python3 repo/tools/eksporter_dag.py >> logs/nettside.log 2>&1
```

Eksporten skriver ingen posisjon, og stopper heller enn å pushe hvis noe i
den ligner en koordinat. Se `nettside/dager/README.md` for hva filene inneholder.
