# AGENTS.md

Konvensjonene i dette repoet, for mennesker og kodeagenter. `CLAUDE.md`
importerer denne fila; andre agenter leser den direkte. Den nærmeste
README-en beskriver hver mappe: start i [README.md](README.md).

## Hva dette er

En e-ink-bilderamme som hver morgen viser fuglene som ble hørt i hagen.
Fire deler: innedel (ESP32-S3 + e-papir), utedel (XIAO ESP32-S3 + mikrofon),
hjemmeserver (Python i `/opt/fugleramme`) og et kamera (Android-app).
Anlegget er i drift; det du endrer, kjører i en hage neste morgen.

## Språk og stil

- Norsk i alt: kode, kommentarer, docs, commit-meldinger.
- Kommentarer og commit-meldinger i `.py`, `.ino` og `.sh` skrives med
  `aa`, `oe`, `ae` i stedet for æøå. Markdown-filer bruker æøå.
- Kommentarene forklarer *hvorfor*, gjerne med dato og målt tall. Et valg
  som ble gjort på grunn av noe som skjedde, får hendelsen med seg.
- Commit-meldinger: én linje som sier hva som er annerledes nå, så et avsnitt
  om hvorfor. Ikke «fix», ikke «oppdatering».
- Filnavn på norsk for det nye (`lytteplan.py`, `tekstkollisjon.py`); de
  engelske navnene som finnes, beholdes.

## Kommandoer

```bash
python3 -m py_compile tools/*.py                                   # alt kompilerer?
python3 tools/render_daily_panel.py --birds test/data/birds-2026-08-28.json \
        --no-weather --out /tmp/panel.html                         # sida uten nett
python3 tools/lytteplan.py 3.9                                      # soloppgang og plan, måned for måned
bash -n deploy/deploy.sh                                            # skallsyntaks
tools/flash_firmware.sh --sjekk                                     # firmware kompilerer, uten brett
kamera-app/kjor.sh bygg                                             # Android-appen
```

Det finnes ingen testsuite. `test/data/` har en dags `birds.json`; rendringen
av sida med den er den raskeste kontrollen på at kjeden ikke er brukket.
Rendring til PNG (`render_panel_png.py`) krever Playwright og kjøres på
serveren.

## Regler

- **Ingenting personlig i koden.** Koordinater, stedsnavn og kontakt leses
  fra miljøet gjennom `tools/oppsett.py`. Serveren din står i
  `deploy/deploy.env` (ignorert av git). Brukernavn, LAN-navn, WiFi-navn og
  e-post hører ikke hjemme i repoet.
- **Hemmeligheter i env-filer, aldri i git.** `firmware/*/config.h`,
  `deploy/deploy.env` og `/opt/fugleramme/frame_server.env` er ignorert med
  vilje. Eksempelfilene ved siden av dem er det som committes.
- **Standardbibliotek på serversidene.** `render_daily_panel.py`, `helse.py`,
  `fugler.py`, `dag.py` og `vakt.py` importerer ingenting utenfor `stdlib`.
  Grafer tegnes som SVG for hånd. Ikke legg til avhengigheter der.
- **Seks farger.** Alt som skal på panelet tegnes i svart, hvitt, rødt, gult,
  blått og grønt. Ingen gråtoner, ingen gjennomsiktighet.
- **Mål, ikke håp.** Komposisjon styres av kode, ikke av prompten. Et bilde
  som skal på veggen måles (`tekstkollisjon.py`) før det godtas.
- **Dyr modell til det sjeldne, billig til det daglige.** Én ny art kan
  koste noen kroner. Noe som kjører hver dag eller hver time skal koste
  nesten ingenting, ha tak per time og pause etter 429.
- **Deploy er `deploy/deploy.sh`.** Den kopierer scriptene i lista si og
  restarter tjenestene. Et nytt script som en tjeneste importerer må inn i
  den lista, ellers svarer serveren 500 mens alt ser friskt ut.
- **Commit på `main`, push bare når eieren ber om det.** Ingen arbeidsgreiner
  for småting. Aldri force-push.

## Verifisering før du sier deg ferdig

- Påstander om hva som virker, sjekkes mot loggene på serveren
  (`logs/daily.log`, `logs/stats.log`, `journalctl -u fugleramme-*`), ikke
  mot dokumentasjonen. Docs beskriver det som var sant da de ble skrevet.
- «Bekreftet» fra rammen betyr *mottatt*, ikke tegnet. Firmwaren svarer før
  den tegner. Et bilde er på veggen når rammen har vært stum på HTTP i rundt
  35 sekunder etterpå.
- En agent kan lese på serveren over SSH hvis den har tilgang, men ikke
  restarte tjenester: `sudo` krever passord. Si fra hva som må restartes.
- Cron kjører `/bin/sh`. Test alltid en cron-endring via cron, ikke bare i
  bash.

## Ikke rør

- `/opt/fugleramme/frame_server.env` og `www/` på serveren. `deploy.sh`
  lar dem være i fred, og det skal du også.
- `plates/*.jpg` og `plates/plates.json`. Nye plansjer kommer inn gjennom
  `fetch_plates.py`, som nekter alt som ikke er public domain.
- Fotpunkter merket `"kilde": "manuell"` i `plates/fugler/*.json`. De er
  satt for hånd og skal overleve alle kjøringer.
