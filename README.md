# Fugleramme

En e-ink-bilderamme på veggen som hver morgen viser hvilke fugler som faktisk
ble hørt i hagen, tegnet i stil med gamle fuglebøker.

Ute henger en liten solcelledrevet lytter. Den våkner etter en plan som følger
soloppgangen, tar opp ett minutt lyd og sender det til en hjemmeserver.
Serveren kjenner igjen artene med BirdNET, henter været fra yr, setter dagens
fugler på en fast gren i et fast oppsett, dithrer sida til panelets seks farger
og pusher den til rammen inne. Rammen tegner og sover til neste morgen. En
telefon i vinduet kan i tillegg ta bilder av materen.

Alt er bygd for å kjøre uten tilsyn på vanlig maskinvare: to ESP32-brett, en
gammel PC som hjemmeserver, en Android-telefon. I drift siden juli 2026
(rammen) og august 2026 (utedelen og fuglesida).

Prosjektet har en enkel nettside på
[sonwit.github.io/fugleramme](https://sonwit.github.io/fugleramme/), med en
[personvernerklæring](https://sonwit.github.io/personvern/) for lydopptakene
i hagen.

## Slik henger delene sammen

```
 [Utedel]   XIAO ESP32-S3 + INMP441-mikrofon, solcelle + LiPo
     │  POST /upload   60 s WAV + helse-JSON; henter GET /config etterpå
     ▼
 [Hjemmeserver]   /opt/fugleramme, to venv-er, systemd + cron
     audio_ingest.py ──► birdnet_analyze.py ──► observations.jsonl, birds.json
     daily_panel.py:  compose_branch ──► render_daily_panel ──► render_panel_png
                      fuglene på grenen   sida som HTML         PNG → dither → frame.bin
     push_to_frame.py ──► POST /display
     frame_server.py: webapp, Siri, /dag, /fugler, /helse       vakt.py: sier fra
     ▲
     │  POST /bilde   JPEG + meta fra kameraet
 [Kamera]   Android-app på en telefon i vinduet
     ▼
 [Innedel]  ESP32-S3 + 13,3" Spectra 6 e-papir i en IKEA-ramme
     HTTP-server: POST /display med 960 000 byte → tegnet på 20–35 s
```

Rammen henter aldri noe selv. Serveren pusher. Det var slik det første
testbildet kom på skjermen, og et brett i en ramme på veggen skal ikke trenge
klokke, plan eller nett for å vise det det sist fikk.

| Del | Hva | Les mer |
|---|---|---|
| Innedel | Waveshare ESP32-S3-ePaper-13.3E6 i en IKEA RÖDALM-ramme. Tar imot en ferdig pakket bildebuffer over HTTP og skyver den til panelet. Passer på seg selv med watchdog og WiFi-gjenoppretting. | [firmware/README.md](firmware/README.md) |
| Utedel | Seeed XIAO ESP32-S3 med INMP441. Deep sleep på ~14 µA mellom øktene, opptaket bor i PSRAM, radioen er av mens det tas opp. Lytteplanen regnes ut på serveren og hentes etter hver opplasting. | [firmware/README.md](firmware/README.md) |
| Server | Alt er Python, og sidene som serveres er ren standardbibliotek. Den daglige kjeden, lyd og arter, webappen, helsesida og vakta. | [tools/README.md](tools/README.md), [deploy/README.md](deploy/README.md) |
| Kamera | En Android-app som overvåker hagen på 1x og tar telebilde ved materen når noe rører seg. Bildene analyseres på serveren. Forgjengeren på Raspberry Pi ligger i `kamera/`. | [kamera-app/README.md](kamera-app/README.md) |
| Plansjer | Skannede plansjer fra Wikimedia Commons, én 1:1-fugl per art med fotpunktet sitt, og grenmalene for årstidene. | [plates/README.md](plates/README.md) |

## Valgene, og hvorfor

**Et fast oppsett i stedet for et fritt AI-bilde.** Fram til august 2026 var
dagens motiv et fritt generert bilde av dagens fugl. Det var pent og
uforutsigbart. Fuglesida er det motsatte: samme oppsett hver dag, artene som
faktisk ble hørt, med norsk og latinsk navn, klokkeslett og sikkerhet. Det
frie bildet lever videre som reserve når fuglesida feiler, og som det Siri og
«lag nytt bilde» i webappen bruker.

**Komposisjon er et regnestykke, ikke en bønn.** Vi prøvde å be modellen
holde venstre halvdel tom for tekst. Samme prompt ga 0,1 % blekk i tekstsonen
ett forsøk og 14,8 % det neste, og med en ferdig gren som referanse tegnet den
sin egen midt på sida. Derfor tegner modellen én fugl om gangen, én gang per
art, og `compose_branch.py` limer dem på grenen selv. Hver fugl har et
fotpunkt, ikke en bunnkant, for nederste piksel på en skjære er halespissen.
Fuglene skaleres etter kroppslengde, med en komprimert skala så gråhegra ikke
gjør grønnsisiken til en flekk. Etterpå måles tekstsonen uansett, og et
forsøk som skitner den til forkastes.

**Seks farger, ingen gråtoner.** Panelet har svart, hvitt, rødt, gult, blått
og grønt. Alt annet må dithres, og dithret tekst er grøt. Hele fuglesida er
derfor tegnet i de seks fargene, og ren hvit bakgrunn treffer paletten eksakt.
Et halvgjennomsiktig felt bak teksten «for lesbarhet» blir en grumsete flekk.

**Plansjer fra gamle fuglebøker.** Wikimedia Commons har en
«(illustrations)»-kategori for nesten hver art, med Gould, Keulemans, Naumann
og Morris. Alle falt i det fri. Skanningene vaskes til rent hvitt papir før
bruk, for kremgult papir finnes ikke i paletten. Kilde og lisens for hver
plansje står i `plates/plates.json`.

**Stedsfilter og blokkliste.** BirdNET får posisjon og dato, så tropiske
feiltreff forsvinner. Det som er igjen av klassiske feil, som myrrikse i en
villahage, står på en blokkliste: de tegnes aldri, men står i fotnoten så det
er synlig at de ble hørt.

**Lytteplanen følger sola og batteriet.** Soloppgangen i Oslo-området
varierer fem timer gjennom året, så en fast morgenrunde treffer morgenkoret i
juni og bekmørke i desember. Serveren regner ut soloppgangen selv, uten
nettkall, legger et finvindu rundt den og trapper ned tettheten når
batterispenningen faller. Firmwaren kjenner bare ett intervall, så serveren
svarer med forskjellig verdi alt etter når brettet spør.

**Dyr modell til det sjeldne, billig til det daglige.** Å tegne en ny art
skjer én gang og får den beste bildemodellen. Kameraanalysen skjer hundre
ganger om dagen og går på den billigste, uten tenking, i lav oppløsning, med
tak per time. Kameraet på Raspberry Pi var 80–90 % av regningen før bremsene
kom på.

**Standardbibliotek på serveren.** Helsesida, fuglesida, dagsoversikten og
vakta er ren `stdlib`, med grafer som håndtegnet SVG. Da kjører de i begge
venv-ene, på Macen og på serveren, og det er ingenting å oppdatere.

**Stillhet er også et signal.** Da utedelen lå femten timer i bootloader
merket ingen det, for det kom jo ingen nye filer å reagere på. Vakta ser
derfor etter det som *ikke* skjer, og er ellers helt stille.

**07:07, ikke 07:00.** Vær-API-er er mest overbelastet på hel time. Jobben på
07:00 ga to dagers 503-stopp i juli 2026.

## Prøvd og forkastet

- **Utedel v1 på Raspberry Pi 3 B.** Trakk ~450 mA i tomgang, fikk
  undervoltage på solcelle og døde 28. juli 2026. Scriptene ligger i `pi/`,
  lærdommene i `docs/Utedel — status og neste steg.md`.
- **Modellen komponerer hele plansjen.** Se over. Verktøyet finnes fortsatt
  som `compose_hero.py`, men er ikke i den daglige kjeden.
- **Kamera på Raspberry Pi med HQ-kamera.** Virket, men kostet for mye i
  modellkall og ble tatt ned i september 2026. `kamera/` er beholdt som
  referanse. Telefonen med telelinse tok over.
- **Plansjer fra en 3D-modell i Blender.** Testet i september 2026 for arter
  uten brukbar plansje på Commons. Streken virket: Freestyle ga både kontur og
  skravur som lignet et stikk. Fjærdrakten ble aldri overbevisende, og hver
  art kostet mer modellering enn den var verdt. Lagt dødt 20. september 2026.

## Kom i gang

1. **Maskinvare.** Innedel: Waveshare ESP32-S3-ePaper-13.3E6 og en ramme
   på 30×40 cm. Utedel: Seeed XIAO ESP32-S3, INMP441, Waveshare Solar Power
   Manager (D), 3,7 V LiPo på 10 Ah og et solcellepanel. Server: en hvilken
   som helst Linux-maskin med Python 3.12.
2. **Flash innedelen.** Kopier `firmware/indoor_frame/config.example.h` til
   `config.h`, fyll inn WiFi (2,4 GHz) og kjør `tools/flash_firmware.sh`.
   Send et testbilde med `tools/send_to_frame.py`. Se
   [firmware/README.md](firmware/README.md).
3. **Sett opp serveren.** `/opt/fugleramme`, to venv-er, `frame_server.env`
   fra eksempelet i `deploy/`, systemd-tjenestene og cron-linja. Se
   [deploy/README.md](deploy/README.md).
4. **Flash utedelen** på samme måte, med `tools/flash_firmware.sh utedel`.
   Oppsett og feilsøking i `docs/Utedel v2 — ESP32-S3 XIAO.md`.
5. **Skaff plansjer** for artene som dukker opp. `tools/ny_art.py` gjør hele
   jobben for én art. Se [plates/README.md](plates/README.md).
6. **Kameraet er valgfritt.** [kamera-app/README.md](kamera-app/README.md).

Koordinatene for hagen, stedsnavnet på sida og kontakten i User-Agent leses fra
miljøet (`tools/oppsett.py`), så ingenting personlig trenger å stå i koden.

## Mappene

| Mappe | Innhold |
|---|---|
| `firmware/` | Arduino-skissene for innedelen og utedelen. [README](firmware/README.md) |
| `tools/` | Alt som kjører på serveren, og verktøyene som kjøres fra Macen. [README](tools/README.md) |
| `deploy/` | deploy.sh, systemd-tjenestefiler og env-eksempler. [README](deploy/README.md) |
| `plates/` | Plansjebiblioteket. [README](plates/README.md) |
| `kamera-app/` | Fuglekameraet som Android-app. [README](kamera-app/README.md) |
| `kamera/` | Fuglekameraet på Raspberry Pi, parkert. [README](kamera/README.md) |
| `pi/` | Utedel v1 på Raspberry Pi, pensjonert. [README](pi/README.md) |
| `design/` | Artboards for de tre layoutretningene. [README](design/README.md) |
| `docs/` | Guider og prosjektnotater, med historikk. [Innhold](docs/README.md) |
| `test/` | Testdata: en dags `birds.json` til å rendre sida med lokalt. |

`AGENTS.md` beskriver konvensjonene i repoet for den som skal jobbe i det, med
eller uten en kodeagent.

## Takk og lisenser

Prosjektet er MIT-lisensiert, se [LICENSE](LICENSE). Det gjelder alt i repoet
som ikke er merket med noe annet:

- `firmware/indoor_frame/DEV_Config.*`, `EPD_13in3e.*` og `Debug.h` er fra
  Waveshare (MIT). `es8311*` er fra Espressif (Apache-2.0).
- Plansjene i `plates/*.jpg` er public domain, hentet fra Wikimedia Commons.
  Kunstner og kildeside for hver står i `plates/plates.json`. Fuglene i
  `plates/fugler/` og malene i `plates/maler/` er tegnet av en bildemodell
  med disse plansjene som forelegg.
- Artsgjenkjenningen er [BirdNET](https://birdnet.cornell.edu/) via
  `birdnetlib`. BirdNET-modellen har sin egen lisens (CC BY-NC-SA 4.0), som
  ikke tillater kommersiell bruk.
- Været kommer fra [MET Norge](https://api.met.no/), som krever en
  identifiserende User-Agent. Sett `FUGLERAMME_KONTAKT` til din egen.
- Fuglene tegnes og kamerabildene tolkes av Googles Gemini-modeller. Det
  krever en egen API-nøkkel og koster penger; se kostnadsregelen over.
