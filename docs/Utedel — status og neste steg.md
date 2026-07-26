# Utedel (fugle-Pi) — status og neste steg

Sist oppdatert: 2026-07-26 (montert ute på solcelle + batteri, uten kamera)

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

Rapporten svarer på tre ting:
- **Hører vi fugler?** arter, deteksjoner, døgnrytme (histogram per time).
- **Er plasseringen OK?** RMS-nivå i dBFS per økt. Under −55 dBFS = i praksis
  stillhet (flytt mikrofonen nærmere foringsplass/busker). Over −12 dBFS eller
  klipping = for høyt / vindstøy. Målt så langt: **−38 dBFS, ingen klipping** —
  det er et sunt nivå.
- **Holder strømmen?** undervoltage-hendelser, throttling, temperatur per økt.

## Neste steg ⬜

1. **Se på første døgns statistikk** (dagsangen 03–08 er den viktige).
   Ingen arter tross bra lydnivå ⇒ mikrofonen står for langt fra fuglene.
2. **Bytt til Pi Zero 2W** — største strømgevinst.
3. **Vurder Witty Pi / PiJuice** hvis batteriet fortsatt ikke holder gjennom
   natta og gråværsdager.
4. Glisne ut innsamlingen når vi vet når fuglene faktisk synger her.
5. Kamera: senere. Fungerer på Pi 3 (`rpicam-still`), ikke koblet inn noe sted.

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
