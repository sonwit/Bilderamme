# Utedel (fugle-Pi) — status og neste steg

Sist oppdatert: 2026-07-26 (montert ute på solcelle + batteri, uten kamera)

> **2026-08-04: v1 er PENSJONERT.** Pi-en viste seg å ha vært død siden
> 28. juli (batteriet tomt / SD-korrupsjon — nøyaktig slik strømkapitlet under
> forutså). XIAO ESP32-S3 tok over og er montert ute og i drift — se
> «Utedel v2 — ESP32-S3 XIAO.md». Dette dokumentet beholdes som historikk:
> strømanalysen, Orange Pi-vurderingen og statistikk-verktøyet gjelder fortsatt.

## Arkitektur

BirdNET kjører **på hjemmeserveren**, ikke på Pi-en. Pi-en er en tynn lydsensor.

```
[Pi ute]   cron → arecord 60 s (INMP441, S16_LE 48 kHz) → helse-sidecar
           → scp til serveren (fartsbegrenset) → ssh-trigger analysen
           (feiler nettet: opptaket køes lokalt og sendes ved neste økt)
[Server]   birdnet_analyze.py (venv-birdnet, lat 60.09 lon 10.93, min_conf 0.25,
           peak-normaliserer svake opptak)
             → data/observations.jsonl  (én linje per opptak, for godt)
             → birds.json               (DAGENS aggregerte artsliste)
           07:07 → generate_daily_image.py trekker blant dagens hørte arter
           22:00 → bird_stats.py skriver dagsrapport til logs/stats.log
```

## Filer

| Fil | Hvor | Hva |
|---|---|---|
| `pi/record_and_upload.sh` | Pi: `/home/bruker/` | opptak + opplasting + trigger, med kø |
| `pi/power_tune.sh` | Pi: `/home/bruker/` | strømsparing (kjøres med sudo, én gang) |
| `pi/crontab.txt` | Pi: `crontab -l` | innsamlingsplanen |
| `tools/birdnet_analyze.py` | Server: `/opt/fugleramme/` | BirdNET + observasjonslogg + birds.json |
| `tools/bird_stats.py` | Server: `/opt/fugleramme/` | statistikkrapport |
| `tools/generate_daily_image.py` | Server | `get_heard_bird()` leser birds.json |

Server-scriptene deployes med `deploy/deploy.sh`. Pi-scriptene med `scp`.

## Innsamlingsplan (innkjøringsfase)

```
*/20 3-8 * * *   # dagsangen, hver 20. min  (18 økter)
0 9-21 * * *     # resten av dagen, hver time (13 økter)
```
~31 opptak/døgn à 60 s. Natta er tom: fuglene er stille og batteriet lades ikke.
Når vi har sett noen dagers statistikk kan dette glisnes ut for å spare strøm.

## Strøm — status og tiltak

**Problemet:** Pi 3 B er feil brikke for solcelledrift. Den trakk ~450 mA i
tomgang og hadde **6 undervoltage-hendelser på under to timer** (2026-07-26,
midt på en solrik julidag). Undervoltage = 5V-skinna under ~4,63 V; verste
konsekvens er korrupt SD-kort.

**Gjort (programvare, ~20-30 % mindre forbruk):**
- Wifi power-save PÅ — største enkeltgevinst. Satt både i
  `/etc/NetworkManager/conf.d/wifi-powersave.conf` (overlever at netplan
  regenererer profilen) og på profilen.
- CPU-guvernør `powersave`, statuslysdioder av, Bluetooth-tjenesten av.
- journald logger i RAM + swap av → langt færre SD-skrivinger (brownout-sikring).
- Opptak i S16_LE i stedet for S32_LE → halv fil, halv radiotid.
- `scp -l 4000` → lavere topplast under sending (det er der dippene skjer).
- Alt settes på nytt ved boot av `fugleramme-power.service`. Verifisert
  gjennom en reell reboot.

**Bevisst IKKE gjort:** ingen endringer i `/boot/firmware/config.txt`. En feil
der ville betydd fysisk nedhenting av kassa. `dtoverlay=disable-bt` og
`dtparam=audio=off` tas når riggen uansett er nede. NB: `dtparam=audio=off`
endrer kortnummereringen — scriptet velger derfor lydkort på **navn**
(`plughw:CARD=sndrpigooglevoi`), ikke nummer.

### Hva vi KAN og IKKE KAN måle (viktig)

**Riggen har ingen batterimåler.** Begge I2C-bussene er skannet og er helt
tomme — ingen INA219, ingen fuel gauge. Pi 3 kan heller ikke lese sin egen
5V-inngangsspenning (`vcgencmd measure_volts` gir kjerne-/SDRAM-spenning, ikke
inngangen). Vi kan altså **ikke** lese ladningsnivå, panelstrøm eller
energibalanse direkte.

Det vi måler i stedet er *utfall*, via tre kilder:
1. **Hjerteslag** hvert 15. min (`pi/heartbeat.sh` → `data/heartbeat-*.log`).
   Lokal skriving, ingen radio. Gir nøyaktig når strømmen tok slutt og når den
   kom tilbake — ikke bare at nattopptakene manglet.
2. **Dekning** — hvor mange planlagte opptak som faktisk kom inn.
3. **Undervoltage-flagget** — eneste signal Pi-en har om 5V-skinna.

Vil du ha ekte energidata, må det maskinvare til: en INA219/INA226 på I2C
mellom batteri og Pi (~100 kr) gir spenning, strøm og effekt, og kan logges
inn i samme observasjonslogg.

### Orange Pi Zero 2W: undersøkt og forkastet (2026-07-26)

Vi har en Orange Pi Zero 2W (Allwinner H618) liggende. **Ikke bruk den med
INMP441-mikrofonen.** I2S på H618 er et uløst driverproblem, ikke en
overlay-jobb:

- Armbian-tråden om nøyaktig dette endte uløst — pinnene PI0–PI4 lot seg ikke
  binde til I2S-driveren, og konklusjonen fra Armbian-hold var at `sun4i-i2s`
  mangler støtte og «further development is required».
- Det finnes ingen `sun50i-h618-i2s.dtbo` i Armbian i det hele tatt.
- Flere 2025-tråder viser folk som ikke får selv enkel **avspilling** til å
  virke (MAX98357A, PCM5102) på dette brettet.
- Eneste dokumenterte H618-suksess er et overlay for Orange Pi Zero **3** som
  gir I2S3 **output** på en gammel 5.4-vendorkjerne — altså feil brett, feil
  retning, feil kjerne.

Avgjørende: avspilling er den *lette* retningen og virker ikke engang. Opptak
er den vanskeligere halvdelen av `sun4i-i2s`. Vil man likevel bruke brettet, er
veien **USB-lydkort/USB-mikrofon** — det omgår I2S helt og dukker opp som et
vanlig ALSA-kort (og `record_and_upload.sh` finner kortet på navn).

Kilder: [Armbian: enable i2s on OPi Zero 2W](https://forum.armbian.com/topic/48406-enable-i2s-on-orange-pi-zero-2w/),
[Armbian: MAX98357A](https://forum.armbian.com/topic/50228-i2s-audio-not-working-on-orange-pi-zero-2w-allwinner-h618-with-max98357a/),
[Armbian: PCM5102](https://forum.armbian.com/topic/56135-no-audio-output-via-i%C2%B2s-pcm5102-on-orange-pi-zero-2w-h618/),
[elkoni/Opi_Zero_3_I2S3_5.4](https://github.com/elkoni/Opi_Zero_3_I2S3_5.4).

**Det som faktisk løser strømproblemet:**
1. **Bytt til Pi Zero 2W** (~3× lavere forbruk). Alt overføres 1:1: kopier
   `record_and_upload.sh` + `power_tune.sh`, SSH-nøkkel til serveren, crontab.
2. **Sjekk USB-kabelen.** Tynn/lang kabel gir spenningsfall og er den
   vanligste årsaken til undervoltage. Kort kabel med tykke ledere (20 AWG).
3. **Wifi-signalet er svakt: -72 til -75 dBm.** Svakt signal ⇒ høyere
   sendeeffekt og flere retransmisjoner ⇒ mer strøm og flere dipp. En
   repeater eller bedre antenneplassering hjelper både på strøm og stabilitet.

**Ekte sovemodus finnes ikke på en Pi.** Den har ingen sleep-tilstand — bare
av og på. «Våkne kl. 04 for å ta opp» krever ekstra maskinvare som kutter og
slår på strømmen: Witty Pi 4, PiJuice, eller en TPL5110-timer. Det er den
eneste veien til virkelig duty-cycling. Uten sånt utstyr er alternativet å
holde den på og trimme forbruket (det vi har gjort).

## Statistikk

```bash
ssh bruker@192.168.1.38 'cd /opt/fugleramme && python3 bird_stats.py'            # 7 dager
ssh bruker@192.168.1.38 'cd /opt/fugleramme && python3 bird_stats.py --day 2026-07-27'
ssh bruker@192.168.1.38 'cd /opt/fugleramme && python3 bird_stats.py --all --json'
ssh bruker@192.168.1.38 'tail -60 /opt/fugleramme/logs/stats.log'               # daglig digest
```

Rapporten svarer på tre ting, og avslutter med en **Vurdering**-seksjon som
konkluderer direkte:
- **Hører vi fugler?** arter, deteksjoner, døgnrytme (histogram per time).
- **Er plasseringen OK?** RMS-nivå i dBFS per økt. Under −55 dBFS = i praksis
  stillhet (flytt mikrofonen nærmere foringsplass/busker). Over −12 dBFS eller
  klipping = for høyt / vindstøy. Målt så langt: **−34 dBFS, ingen klipping** —
  et sunt nivå.
- **Holder strømmen?** Nøkkeltallet er **dekning**: hvor mange av opptakene
  cron lovte som faktisk kom inn. Hull om natta = Pi-en var død. I tillegg
  undervoltage *per time* og antall omstarter — begge summert korrekt på tvers
  av oppstarter (`undervoltage_events` nullstilles ved boot, så rapporten deler
  i boot-økter og summerer; ellers ville en brownout-restart skjult trenden).

Dekningen justeres for at inneværende time er halvferdig og for at planen ikke
fantes før første opptak. Manuelle testopptak teller også med i `actual`, så
tallet klampes til 100 %.

## Neste steg ⬜

**Beslutning 2026-07-26: samle data først, så velge maskinvare.** Pi 3-en blir
stående ute til vi har noen døgn med statistikk.

1. **Se på statistikken etter 2–3 døgn** (dagsangen 03–08 er den viktige):
   ```bash
   ssh bruker@192.168.1.38 'cd /opt/fugleramme && python3 bird_stats.py'
   ```
   Les «Vurdering»-seksjonen. Den sier direkte om riggen holder strømmen og om
   vi faktisk hører fugler.
2. **Da tas maskinvarevalget:**
   - Dekning under ~80 % eller omstarter om natta ⇒ batteriet holder ikke.
     Bytt til **Raspberry Pi Zero 2W** (1:1-flytt, ~3× lavere forbruk), eller
     styrk panel/batteri/kabel.
   - Null arter tross lydnivå over −55 dBFS ⇒ **flytt mikrofonen** nærmere
     foringsplass/busker.
   - Alt grønt ⇒ la det stå, og glisne ut innsamlingen for å spare batteri.
3. **Vurder Witty Pi / PiJuice** hvis batteriet ikke holder selv med Zero 2W —
   det er eneste vei til ekte duty-cycling.
4. Kamera: senere. Fungerer på Pi 3 (`rpicam-still`), ikke koblet inn noe sted.

## Maskiner

- **Pi ute:** Raspberry Pi 3 B, `ssh bruker@192.168.1.225` (`fugleramme-pi`,
  Raspberry Pi OS 64-bit/trixie). INMP441 på I2S (`googlevoicehat-soundcard`,
  card 1). Har SSH-nøkkel til serveren. Passordfri sudo.
- **Server:** `ssh bruker@192.168.1.38`, `/opt/fugleramme`, venv `venv`
  (bilde) + `venv-birdnet` (BirdNET).

## Nyttige kommandoer

```bash
ssh bruker@192.168.1.225 'FUGLE_DURATION=15 /home/bruker/record_and_upload.sh'  # manuell økt
ssh bruker@192.168.1.225 'tail -20 /home/bruker/fugl.log'                       # Pi-logg
ssh bruker@192.168.1.225 'vcgencmd get_throttled; dmesg | grep -ci undervolt'   # strømhelse
ssh bruker@192.168.1.225 'ls /home/bruker/queue/'                               # køede opptak
ssh bruker@192.168.1.38 'cat /opt/fugleramme/birds.json'                        # dagens arter
```

Throttled-flagget tolkes slik: `0x50000` = har hatt undervoltage (bit 16) og
throttling (bit 18) siden boot. Lav nibble (`0x1/0x4`) betyr at det skjer *nå*.
