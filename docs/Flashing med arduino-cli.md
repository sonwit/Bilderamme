# Flashing med arduino-cli

Alt som trengs for å bygge og flashe begge brettene fra Terminal — uten
Arduino IDE. Nyttig når Macen er ny/nullstilt, og fordi board-innstillingene
da ligger i repoet (som FQBN) i stedet for i en meny noen må huske å sette
riktig.

Scriptet er `tools/flash_firmware.sh`. Det kompilerer, finner USB-porten,
laster opp, og kan åpne Serial Monitor etterpå.

---

## 1. Førstegangsoppsett på Macen

```bash
# Homebrew (hopp over hvis du har den: kjør `brew --version`)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install arduino-cli
arduino-cli version                 # skal svare med et versjonsnummer

# Apple Silicon: arduino-cli trenger Rosetta (se under). Spør om passordet ditt.
softwareupdate --install-rosetta --agree-to-license
```

> **Hvorfor Rosetta på en M-Mac?** arduino-cli kjører Arduinos `ctags` som en
> del av kompileringen — den leser skissa og genererer funksjonsprototyper — og
> den finnes bare som Intel-binær. Uten Rosetta stopper byggingen med
> `fork/exec …/ctags: bad CPU type in executable`. `flash_firmware.sh` sjekker
> dette og sier fra. (`universal-ctags` fra Homebrew er *ikke* et alternativ:
> den mangler feltene Arduino bruker til å utlede returtypen, og genererer
> prototyper som `static  wdtFeed();` — koden slutter å kompilere.)

> Vil du unngå Homebrew:
> ```bash
> mkdir -p ~/bin
> curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/bin sh
> echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
> ```

Esp32-kjernen installerer scriptet selv første gang det kjører (≈1 GB, tar
noen minutter). Vil du gjøre det manuelt:

```bash
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
```

Begge skissene er verifisert mot **esp32-kjerne 3.3.11** (2026-08). De bruker
bare biblioteker som følger med kjernen (`WiFi`, `ESPmDNS`, `HTTPClient`,
`ESP_I2S`, `Wire`) — ingen ekstra biblioteker skal installeres.

## 2. WiFi-innstillinger

`config.h` er git-ignorert og finnes derfor ikke i en fersk klone. Scriptet
lager den fra malen første gang og ber deg fylle inn:

```bash
cp firmware/indoor_frame/config.example.h firmware/indoor_frame/config.h
open -e firmware/indoor_frame/config.h      # WIFI_SSID / WIFI_PASS (2,4 GHz-nettet)
```

Utedelen har sin egen: `firmware/outdoor_sensor/config.example.h` -> `config.h`
(WiFi + `INGEST_HOST` til hjemmeserveren).

## 3. Flash

```bash
cd ~/workspace/Bilderamme            # der du klonet repoet

./tools/flash_firmware.sh --sjekk    # kompiler uten brett — sjekker at alt bygger
./tools/flash_firmware.sh            # innedelen (bilderammen), kompiler + last opp
./tools/flash_firmware.sh --monitor  # samme, men åpne Serial Monitor etterpå

./tools/flash_firmware.sh utedel     # utedelen (XIAO ESP32-S3)
```

Etter opplasting av innedelen skal Serial Monitor (115200) vise:

```
WiFi tilkoblet. IP: 192.168.1.xx
mDNS: http://fugleramme.local
Klar. Venter paa bilde...
```

**Noter IP-en.** Får rammen ny DHCP-leie etter reboot, må `FRAME_HOST` på
hjemmeserveren oppdateres — se «Etter flashing» nederst.

## 4. Board-innstillinger, oversatt til FQBN

Dette er den samme tabellen som i `docs/Fase 1 — Kom i gang med
ePaper-skjermen.md`, bare slik arduino-cli vil ha den. Alt som ikke står her
er kjernens standardverdi.

**Innedel — Waveshare ESP32-S3-ePaper-13.3E6:**

```
esp32:esp32:esp32s3:FlashSize=32M,PSRAM=opi,CDCOnBoot=default,PartitionScheme=app5M_fat24M_32MB
```

| Arduino IDE | FQBN-bit |
|---|---|
| Board: ESP32S3 Dev Module | `esp32:esp32:esp32s3` |
| Flash Size: 32MB (256Mb) | `FlashSize=32M` |
| PSRAM: OPI PSRAM | `PSRAM=opi` |
| USB CDC On Boot: Disabled *(serie går via CH343)* | `CDCOnBoot=default` |
| Partition Scheme: 32M Flash (4.8MB APP/22MB FATFS) | `PartitionScheme=app5M_fat24M_32MB` |

**Utedel — Seeed XIAO ESP32-S3:**

```
esp32:esp32:XIAO_ESP32S3:PSRAM=opi
```

Bare PSRAM må skrus på — 60 s opptak bor der. Uten den får du «fikk ikke
allokert PSRAM-buffer» i Serial Monitor.

Trenger du å eksperimentere uten å endre scriptet:

```bash
FQBN="esp32:esp32:esp32s3:FlashSize=32M,PSRAM=opi,FlashMode=opi" ./tools/flash_firmware.sh
```

Alle lovlige verdier: `arduino-cli board details --fqbn esp32:esp32:esp32s3`.

## 5. Feilsøking

**Innedelen dukker opp som TO porter — og de gjør ulike ting**
Brettet har en USB-hub med både ESP32-S3-ens innebygde USB og en CH343
USB-serie-brikke. Begge heter `/dev/cu.usbmodemXXXX`, så navnet skiller dem
ikke. Slik finner du ut hvilken som er hvilken:

```bash
arduino-cli board list        # den som sier «ESP32 Family Device» er Espressif-porten
```

- **Espressif-porten** (`ESP32 Family Device`, f.eks. `/dev/cu.usbmodem21101`)
  — **flash hit**.
- **CH343-porten** (`Unknown`, f.eks. `/dev/cu.usbmodem5B901714551`) — **her
  kommer serieutskriften**. FQBN-en har `CDCOnBoot=default` (= USB CDC av), så
  `Serial.print` går ut på UART-en, ikke på Espressif-porten. Kobler du Serial
  Monitor til Espressif-porten får du helt tomt — det betyr *ikke* at brettet
  er dødt.

```bash
./tools/flash_firmware.sh --port /dev/cu.usbmodem21101          # flash
arduino-cli monitor --port /dev/cu.usbmodem5B901714551 \
    --config baudrate=115200                                    # se loggen
```

**«Fant ingen USB-seriellport»**
Sjekk hva Macen ser med `arduino-cli board list`. Er lista tom: prøv en annen
USB-C-kabel (mange er kun strøm). macOS 12+ har CH343-driveren innebygd.

**Opplastingen henger på «Connecting…»**
Hold inne **BOOT**, trykk og slipp **RESET**, slipp så **BOOT**. Brettet står
nå i nedlastingsmodus. Kjør scriptet på nytt.

**Flere porter funnet**
Scriptet nekter å gjette. Kjør `arduino-cli board list` og velg:
`./tools/flash_firmware.sh --port /dev/cu.usbserial-1420`

**Brettet gir ingen serieutskrift etter flashing**
Nesten alltid feil Flash Size eller PSRAM — FQBN-en over har begge riktig, så
sjekk først at du faktisk kjørte scriptet og ikke en gammel IDE-innstilling.
Hjelper ikke det: modulen er en ESP32-S3-WROOM-2 med oktal flash, og et
`FlashMode=opi`-forsøk (se over) er neste ting å prøve. Brettet blir ikke
ødelagt av et feil forsøk — flash på nytt med riktig verdi.

**Serial Monitor uten å flashe**
```bash
arduino-cli monitor --port /dev/cu.usbserial-1420 --config baudrate=115200
```

## 6. Etter flashing av innedelen

Brettet rebooter og ber om ny DHCP-leie — den kan bli en **annen IP enn før**.
Hjemmeserveren pusher til `FRAME_HOST` i `/opt/fugleramme/frame_server.env`,
så hvis IP-en endret seg feiler både cron-jobben 07:07 og webappen/Siri med
`[Errno 113] No route to host`.

```bash
ping -c 3 fugleramme.local                 # fra Macen — Bonjour er innebygd
curl -s http://fugleramme.local/           # statusside med "Fugleramme" + IP
```

Endret IP-en seg, på hjemmeserveren:

```bash
ssh bruker@192.168.1.38
sudo sed -i 's/^FRAME_HOST=.*/FRAME_HOST=192.168.1.NY/' /opt/fugleramme/frame_server.env
sudo systemctl restart fugleramme-frame-server
```

**Dette skal du slippe nå.** `FRAME_HOST` skal stå til `fugleramme.local`, ikke
en IP: `push_to_frame.py` slår opp `.local`-navnet over mDNS selv (`resolve_host`),
uten at serveren trenger `avahi`/`libnss-mdns`, og firmwaren kunngjør navnet
allerede (`indoor_frame.ino`, `MDNS.begin`). Da kan rammen få hvilken IP den vil.

Vil du ha belte *og* bukseseler:

1. **DHCP-reservasjon på ruteren**: Google Home-appen → enheten → statisk IP.
2. **mDNS i selve OS-et på serveren**: `sudo apt install libnss-mdns` drar inn
   avahi og legger `mdns4_minimal` inn i `hosts:`-linja i `/etc/nsswitch.conf`.
   Da løser `.local` seg for alle programmer på serveren, ikke bare våre.
