# tools/ — serveren og verktøyene

Alt som kjører på hjemmeserveren ligger her, sammen med verktøyene som kjøres
fra Macen. På serveren ligger filene flatt i `/opt/fugleramme/`; her ligger
de i `tools/` og plansjene i `plates/`. Scriptene ser etter begge deler.
Oppsett av serveren, env-fila, systemd og cron står i
[../deploy/README.md](../deploy/README.md).

## Hva som ligger her

```
— Dagens fugleside, i den rekkefølgen den kjøres —
daily_panel.py          Inngangspunktet cron kaller. Kjører de tre under.
compose_branch.py       Dagens fugler limt på den faste grenen, lokalt og deterministisk.
render_daily_panel.py   Sida som HTML på nøyaktig 1200x1600, i palettfarger.
render_panel_png.py     Rastrer HTML -> PNG -> Atkinson-dither -> frame.bin.
push_to_frame.py        Sender en ferdig frame.bin til rammen. Cron.
tekstkollisjon.py       Måler om teksten faktisk kolliderer med illustrasjonen.

— Lyd og arter —
audio_ingest.py         Mottak av opptak og kamerabilder fra utedelen (systemd, port 8091).
                        Svarer også GET /config: lytteplanen til utedelen.
lytteplan.py            Når utedelen skal våkne, regnet ut fra soloppgang og batteri.
birdnet_analyze.py      BirdNET på én WAV -> observations.jsonl + birds.json.
bird_stats.py           Statistikk og daglig rapport: arter, lydnivå, dekning, strøm.
bilde_analyze.py        Hvilken fugl er på kamerabildet? Én linje i kamera.jsonl.

— Websidene (serveres av frame_server.py) —
frame_server.py         Webapp, galleri, Siri-endepunkt (systemd, port 8090).
dag.py                  /dag: døgnet som forløp, opptak for opptak, én dag om gangen.
fugler.py               /fugler: artene over tid, hvor ofte, hvor sikkert, når på døgnet.
helse.py                /helse: virker anlegget? Batteri, dekning, siste push.
vakt.py                 Sier fra når noe er galt. Cron hvert kvarter, ellers stille.

— Plansjebiblioteket (engangsjobb per art) —
ny_art.py               Hele jobben for én ny art: plansje, vask, metadata, fugl, fotpunkt.
fetch_plates.py         Kortliste og nedlasting fra Wikimedia Commons.
prepare_plates.py       Vasker skanninger: papirtone -> rent hvitt.
compose_hero.py         Lager grenmalen. Alternativ AI-komponert plansje, ikke i daglig bruk.
bird_names.py           Norske navn, kroppslengder og habitat, nøklet på latinsk navn.

— Reserven og det manuelle —
generate_daily_image.py Fritt AI-bilde: vær + dagens fugler -> Gemini -> dither -> frame.bin.
send_to_frame.py        Gjør et vilkårlig bilde om til panelformat og sender det. Fra Macen.
flash_firmware.sh       Kompiler og flash begge brettene med arduino-cli.
oppsett.py              Koordinater, stedsnavn og kontakt, lest fra miljøet.
```

## Den daglige kjeden

```
daily_panel.py
  → compose_branch.py      les birds.json (dagens arter)
                           hver art: 1:1-fugl fra plates/fugler/
                           lim dem på grenmalen i faste festepunkter, skalert etter cm
                           Gemini retusjerer kontaktpunktene, én gang per fuglesett
                           mål tekstsonene → forkast om urent
  → render_daily_panel.py  yr / api.met.no (vær), HTML 1200x1600 i palettfarger
  → render_panel_png.py    headless chromium → PNG, Atkinson-dither, pakk 2 px/byte
  → www/frame.bin
push_to_frame.py           POST http://fugleramme.local/display   (~20–35 s å tegne)
```

Kjeden kjøres tre ganger om dagen fra cron: 07:07, 09:37 og 16:00. Alle tre
tegner dagen som pågår. 09:37 ble lagt til fordi klokka sju hadde bare 5 av
14 dager noe å tegne, mens klokka ni hadde 9; klokka 16 er rundt tre
firedeler av dagens arter hørt. Headeren teller opptakene, så «Hørt i dag» er
sant uansett.

**Gårsdagen er første reserve.** Lytteplanen følger sola, og om vinteren har
utedelen ikke våknet klokka sju. Har dagen ingenting å tegne, tegnes gårsdagen
ferdig i stedet, og har heller ikke den noe, leter kjeden inntil sju dager
bakover etter siste dag som hadde det, med datoen tydelig i overskriften
(`RESERVE_I_GAAR`, `RESERVE_DAGER`). En fugleside fra i forgårs er bedre enn
en tegneseriestokkand.

**AI-bildet er siste reserve, og bare om morgenen.** `daily_panel.py` går bare
ut med 0 hvis `frame.bin` faktisk finnes og er 960 000 byte. Feiler den
klokka 07:07, kjører cron `generate_daily_image.py` i stedet, så det henger et
bilde på veggen i stedet for ingenting. Kjøringene 09:37 og 16:00 har ingen
reserve: feiler de, blir forrige side hengende heller enn at et AI-bilde tar
plassen. Push-steget bryr seg ikke om hvem som lagde fila.

Værfeil stopper ingenting: `get_weather_safe()` prøver tre ganger og
genererer deretter uten værreferanse. `push_to_frame.py` prøver fire ganger.

## Dagens fugleside

Sida er ett fast oppsett: infoboks oppe til venstre, artslista under den,
bunnlinje, og en fugleplansje som fyller resten av arket. Alt er tegnet i
panelets seks farger, så teksten dithres ikke.

**Hovedlista og fotnoten.** BirdNET-konfidens er en score per deteksjon, ikke
sannsynligheten for at arten var der. Arter under `PANEL_SURE_CONF` (0,5) som
bare er hørt i én økt havner i fotnoten «også mulige». Arter på blokklista
(`PANEL_BLOKKERT`, standard myrrikse og rørdrum) tegnes aldri, uansett score,
men står i fotnoten. Sorteringen er etter sikkerhet, ikke belegg: fire svake
treff på samme feil art er fortsatt fire svake treff.

**Å legge til en ny art** er to engangsjobber som gjenbrukes hver dag arten
dukker opp igjen, og `ny_art.py` gjør begge i én kjøring. Detaljene står i
[../plates/README.md](../plates/README.md).

**Fotpunkt, ikke bunnkant.** Nederste piksel i bildet av en skjære er
halespissen. Aligner man på den, lander halen på veden og fuglen henger i
lufta. Samme vannrett: halen drar tyngdepunktet med seg. Hver fugl har derfor
et fotpunkt i sidecar-JSON-en sin, satt av modellen og sjekket med
`compose_branch.py --sjekk-foetter fotpunkter.png`. Ser et feil ut, rett
`fot` og sett `"kilde": "manuell"`, så rører ingen senere kjøring det.

**Størrelser.** Fuglene skaleres etter faktisk kroppslengde (`LENGDE_CM` i
`bird_names.py`, totallengde med hale). Rett proporsjon går ikke, så det
komprimeres:

```
skala = (lengde / 21 cm) ** 0,6,   klemt til 0,55–1,60
```

Med rødvingetrosten som midtpunkt gir det skjære 1,56× og grønnsisik 0,71×.
Største art får den tykkeste greina nederst, minste den tynne kvisten øverst.

**Festepunktene.** `ANKRE` i `compose_branch.py` er en liste
`(x, y, høyde, speilvendt)` sortert nedenfra og opp. `y` snappes til greinas
faktiske overflate, så punktene kan settes omtrentlig; `--kart` viser hvor
grenen har ved ved hver x. Hver fugl prøver ankrene i tur og orden og tar det
første der den får stå i fred, inntil 22 % overlapp.

**Tekstsonen er en hard sperre.** Ingen fugl får overlappe feltet der teksten
står (venstre 48 %, ned til 75 % av høyden). Blir en fugl bred nok til å nå
inn, flyttes den sidelengs og får ny ved under føttene; er den for bred,
krymper den. Etterpå måles sonene uansett, i vannrette bånd: en enslig fugl
midt i artslista ga 1,9 % totalt, under grensen, mens den lå rett oppå fire
linjer tekst. `tekstkollisjon.py` tegner sida én gang uten illustrasjon og
ser bare der bokstavene faktisk er. Sonen som ikke blir ren, får en helt
ugjennomsiktig hvit pute under teksten.

**Kjøre for hånd**, på serveren i bilde-venv-et:

```bash
venv/bin/python daily_panel.py                                   # hele kjeden -> www/frame.bin
venv/bin/python compose_branch.py --birds birds.json --retusj 0  # uten AI-retusj
venv/bin/python render_daily_panel.py --bar paa                  # med konfidens-bar
RETUSJ=0 venv/bin/python daily_panel.py                          # spar et Gemini-kall
```

`--retusj` sender det ferdige arket tilbake til Gemini for å få tærne til å
gripe rundt veden. Retusjen gjøres én gang per fuglesett per dag: sidecar-JSON-en
husker hvilket sett som ble retusjert (`retusj_signatur`), og står de samme
fuglene på de samme plassene i neste kjøring, gjenbrukes arket. Et forkastet
forsøk gjentas ikke; bare et forsøk som feilet (429, nett) får prøve igjen.

**Modellvalget** følger én regel: dyr modell til det som kjører sjelden,
billig til det som kjører hver dag. 1:1-fuglene (`FUGL_MODELL`), retusjen
(`RETUSJ_MODELL`) og reservebildet (`IMAGE_MODEL`) bruker `gemini-3-pro-image`.
Kameraanalysen, som kjører hele dagen, går på `gemini-3.1-flash-lite` uten
tenking i 768 px, med tak per time (`KAMERA_MAKS_PER_TIME`) og pause etter
429 (`KAMERA_PAUSE_429_S`). Tokenforbruket per kall skrives i loggen, så
prisen kan regnes, ikke anslås.

## Lyd og arter

`audio_ingest.py` tar imot `POST /upload` fra utedelen (WAV i kroppen,
helse-JSON i `X-Fugl-Health`), lagrer i `audio/` og kjører
`birdnet_analyze.py` i bakgrunnen, én om gangen, så utedelen slipper å holde
radioen på mens BirdNET tenker. `POST /bilde` gjør det samme for kamerabilder
og `bilde_analyze.py`.

`birdnet_analyze.py` skriver to ting: `data/observations.jsonl`, én linje per
opptak for godt, med arter, antall deteksjoner, lydnivå og brettets helse, og
`birds.json`, dagens aggregerte artsliste som sida lages fra. Opptak svakere
enn `BIRDNET_NORM_PEAK` normaliseres først; INMP441 tar opp lavt, og BirdNET
treffer mye bedre på normalisert signal. Begynner opptaket med et klippet
smell (mikrofonen som ikke er våken når I2S starter, målt på 233 av 293
opptak), kuttes første sekund før måling og analyse.

`lytteplan.py` svarer på `GET /config`: et finvindu fra én time før
soloppgang til fire timer etter, med 10 minutter mellom øktene i vinduet og 20
resten av dagen, trappet ned til 15/30 under 3,80 V og til firmwarens gamle
plan under 3,65 V. Soloppgangen regnes ut med NOAA-formelen, uten nettkall,
fordi et API som er nede ikke skal kunne stoppe brettet i å få en plan.

`bird_stats.py` svarer på de tre spørsmålene fra innkjøringen: hører vi
fugler, er plasseringen OK, holder strømmen. Cron kjører den 22:00.

## Websidene

`frame_server.py` er webappen: galleri over alle genererte bilder, «send til
rammen» per bilde, et skjema for nye bilder, og `POST /generate` for
Siri-snarveien (`docs/On-demand — Siri-kommando.md`). Den tunge jobben går i
en bakgrunnstråd, én om gangen. Undersidene svarer på hvert sitt spørsmål:

| Side | Spørsmål |
|---|---|
| `/helse` | Virker anlegget? Batteri, WiFi-styrke, dekning, siste push, hva vakta har sagt. |
| `/fugler` | Hva har vi hørt i det hele tatt? Arter over uker og måneder, med avspilling. |
| `/dag` | Hva skjedde i dag? Døgnet som forløp, opptak for opptak, med bla-stripe. |

Alle tre er ett HTML-dokument hver, ren `stdlib` på serversiden, SVG tegnet
for hånd. `vakt.py` er det motsatte av en side: den kjører hvert kvarter og
skriver bare når noe er galt, først og fremst stillhet. Med `VARSEL_URL` (for
eksempel en ntfy.sh-kanal) sendes meldinga ut av huset.

## Bildekonvertering

Panelet har seks rene farger, så et bilde må oversettes til dem. Metoden
(`--dither` i `send_to_frame.py`) avgjør hvor pent det blir. Atkinson er
standard og beste allrounder.

| Modus | Best for | Uttrykk |
|---|---|---|
| `atkinson` (standard) | akvarell, foto og tegneserie | rene flater, naturlige farger, lett trykk-tekstur |
| `none` (`--flat`) | flat tegneserie, vektor, plakat | djervest; farger snappes, kan bli posterisert |
| `bluenoise` | foto | naturlig korn, litt uro på store flate flater |
| `ordered` | | retro rutenett-look |
| `floyd` | unngå | overdiffunderer på dette panelet: støy og grønt hudstikk |

```bash
python3 tools/send_to_frame.py bilde.png                              # atkinson
python3 tools/send_to_frame.py bilde.png --dither none                # flat
python3 tools/send_to_frame.py bilde.png --dither bluenoise --preview ut.png
```

Bra: klar blå himmel, grønt løv, rødt, gult, rein hvit bakgrunn, svarte
konturer. Unngå store flater av lilla, turkis, rosa, oransje og rene
gråtoner; de finnes ikke i paletten og blir urolig tekstur. Prompt-maler som
gir gode resultater står i `docs/Prompt-guide — bilder til ePaper-rammen.md`.

## Feilsøking og snurrer

- **`fugleramme.local` er rammen, ikke serveren.** Navnet peker på ESP32-en i
  bilderammen. Rammen får adresse fra DHCP, og da den byttet IP en gang i
  august 2026 feilet pushen åtte døgn på rad med `No route to host` mens alt
  annet gikk som normalt. Bruk navnet (`FRAME_HOST=fugleramme.local`) og sørg
  for at serveren kan slå det opp (`libnss-mdns`). Serveren selv kunngjør
  ikke noe `.local`-navn og nås på IP.
- **«Connection reset» når du sender.** Eldre firmware kalte `client.stop()`
  rett etter svaret uten å flushe. Bildet ble tegnet, men klienten fikk ikke
  lest svaret. Begge sendescriptene skiller «klarte ikke sende» fra «sendte
  ok, fikk ikke lest svaret», og firmwaren flusher nå.
- **«Bekreftet» betyr mottatt, ikke tegnet.** Firmwaren svarer før den tegner.
  Bildet er på veggen når rammen har vært stum på HTTP i rundt 35 sekunder.
- **Grumsete bilde på skjermen er ofte forventet.** Et mykt akvarellbilde ser
  støyete ut fordi dithringen gjør akkurat det den skal på myke flater. Kjør
  `--preview` og se om det er det samme; hold deg til flate, mettede farger.
- **Gråtoner og gjennomsiktighet finnes ikke.** Se «Valgene» i rot-README-en.
- **Prompt-styrt komposisjon er ikke til å stole på.** Derfor `compose_branch.py`.
- **Gemini-regningen er kameraet, ikke fuglesida.** Målt 12. september 2026:
  1559 kamerabilder på åtte dager var 80–90 % av forbruket. Bremsene ligger i
  `bilde_analyze.py`, i kameraets `pause_s` og i retusjen. Forbruket per
  modell står i AI Studio under Usage, ikke på fakturaen.
- **Falske hull i dekningen.** `bird_stats.py` måler mot planen. Byttes
  planen (ny firmware, ny lytteplan) uten at tabellen der følger med, melder
  den hull som ikke finnes.
