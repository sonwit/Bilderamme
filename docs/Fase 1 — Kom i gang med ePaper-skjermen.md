# Fase 1 — Kom i gang med ePaper-skjermen

Mål: få Waveshare **ESP32-S3-ePaper-13.3E6** til å vise et bilde. Vi gjør det i to trinn:

1. **Bekreft at skjermen virker** ved å flashe Waveshares innebygde demo over USB (viser et fast test­bilde + grafikk).
2. **Vis ditt eget bilde** via Waveshares WiFi-web-opplaster — et nettleser­grensesnitt der du drar inn et bilde og det dukker opp på skjermen.

Alt gjøres fra Macen med Arduino IDE. Du trenger bare brettet og en USB-C-kabel (data, ikke bare lading).

---

## Om brettet (kjekt å vite)

- Prosessor: ESP32-S3-WROOM-2 med **32 MB Flash** og **16 MB PSRAM**. Disse to verdiene er viktige i board-innstillingene lenger ned.
- USB-C-porten går via en **CH343**-seriell­brikke (ikke ESP32-ens native USB). Det betyr at Macen trenger en driver hvis porten ikke dukker opp (se feilsøking).
- **BOOT-knapp** + **Reset-knapp** brukes for å tvinge brettet i nedlastingsmodus hvis opplasting feiler.
- Skjermen er E Ink Spectra 6 (7 farger). En full oppdatering tar **~20–35 sekunder** — det er helt normalt, ikke en feil. Ikke koble fra under refresh.
- WiFi-en støtter **kun 2,4 GHz** (ikke 5 GHz). Viktig i trinn 2.

---

## Trinn 0 — Installer Arduino IDE + ESP32-støtte

1. Last ned og installer **Arduino IDE 2.x**: https://www.arduino.cc/en/software/
2. Åpne Arduino IDE → **Settings** (⌘,). I feltet **Additional boards manager URLs**, lim inn:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. Gå til **Tools → Board → Boards Manager**, søk etter **esp32**, og installer **"esp32 by Espressif Systems"**.
   - Waveshare-dokumentasjonen anbefaler versjon **3.2.0** for akkurat dette brettet. Velg den versjonen i nedtrekksmenyen hvis du får rare kompileringsfeil på nyere versjoner.

---

## Trinn 1 — Last ned Waveshares eksempelkode

1. Åpne demo-repoet: https://github.com/waveshareteam/ESP32-S3-ePaper-13.3E6
2. Klikk grønn **Code → Download ZIP**, og pakk ut.
3. Eksemplene ligger i **`example/`**-mappen. Vi bruker to av dem:
   - `03_E-Paper_Example` — viser innebygd testbilde + grafikk (trinn 1)
   - `05_Loader_esp32wf` — WiFi-opplaster (trinn 2)

---

## Trinn 2 — Board-innstillinger i Arduino IDE

Koble brettet til Macen med USB-C. Åpne `example/03_E-Paper_Example/…` (`.ino`-fila) i Arduino IDE.

Sett under **Tools**:

| Innstilling | Verdi |
|---|---|
| Board | **ESP32S3 Dev Module** |
| USB CDC On Boot | **Disabled** (serie går via CH343) |
| Flash Size | **32MB (256Mb)** |
| PSRAM | **OPI PSRAM** |
| Partition Scheme | velg en 32 MB-ordning, f.eks. **"32M Flash (4.8MB APP…)"** hvis tilgjengelig |
| Port | den nye porten som dukker opp når du plugger inn (typisk `/dev/cu.wchusbserial…`) |

> Waveshares Arduino-side har et skjermbilde med den fulle, anbefalte konfigurasjonen. Hvis noe kompilerer men ikke kjører, sammenlign innstillingene dine mot det skjermbildet:
> https://docs.waveshare.com/ESP32-S3-ePaper-13.3E6/Development-Environment-Setup-Arduino
>
> De to som oftest er feil er **Flash Size (32MB)** og **PSRAM (OPI)** — dobbeltsjekk dem.

---

## Trinn 3 — Flash testbildet (bekreft at skjermen virker)

1. Med `03_E-Paper_Example` åpen, trykk **Upload** (pilen ▶ oppe til venstre).
2. Hvis opplasting henger på "Connecting…": hold inne **BOOT**, trykk og slipp **Reset**, slipp så **BOOT** — nå er brettet i nedlastingsmodus. Prøv Upload igjen.
3. Etter opplasting rebooter brettet, og skjermen begynner å oppdatere. **Vent 20–35 sekunder.** Du skal se: en tømming (blink mellom farger), et innebygd bilde, deretter figurer/tekst ("Waveshare" i flere farger).

✅ Ser du dette, virker skjermen, controlleren og strømmen. Det er den viktigste milepælen i hele prosjektet.

Åpne gjerne **Tools → Serial Monitor** (baud **115200**) for å se logg mens det skjer.

---

## Trinn 4 — Vis ditt eget bilde over WiFi

Nå bruker vi `05_Loader_esp32wf`, som gjør brettet til en liten webserver der du laster opp bilder fra nettleseren.

1. Åpne `example/05_Loader_esp32wf/…` i Arduino IDE.
2. Finn fila **`srvr.h`** (egen fane øverst). Endre WiFi-navn og passord til ditt **2,4 GHz**-nett:
   ```c
   const char* ssid     = "DITT_WIFI_NAVN";
   const char* password = "DITT_WIFI_PASSORD";
   ```
   (Brettet kobler seg til nettet ditt som klient — det lager ikke sitt eget hotspot.)
3. **Upload** (samme BOOT/Reset-triks ved behov).
4. Åpne **Serial Monitor** (115200). Etter oppstart skriver brettet ut sin **IP-adresse**, f.eks. `192.168.1.42`.
5. På Macen (koblet til **samme WiFi**), åpne en nettleser og gå til den IP-adressen. Du får opp Waveshares opplastings­grensesnitt.
6. I grensesnittet:
   - Klikk **Select image file** (eller dra bildet inn i "Original image"-området).
   - I modell­valget, velg **13.3E**.
   - Velg behandlings­algoritme **Dithering: color** (gir best fargegjengivelse på 7-farge­skjermen).
   - Klikk **Upload image**. Framdrift vises nederst; skjermen oppdaterer seg på ~20–35 sek.

✅ Nå har du vist ditt eget bilde over WiFi — nøyaktig samme mekanisme utendørs-Pi-en skal bruke senere for å sende det AI-genererte akvarell­bildet.

### Tips for gode bilder
- Skjermen er **1200×1600 px** (13,3", stående). Beskjær bildet til det formatet før opplasting for best resultat.
- 7-farge e-ink har begrenset palett. Myke, akvarell­aktige motiv med lav metning (som prosjektets stil) ser mye bedre ut enn skarpe fotografier. `Dithering: color` hjelper.

---

## Feilsøking

**Porten dukker ikke opp under Tools → Port**
CH343-driveren mangler kanskje. Installer WCH CH34x-driver for macOS, eller prøv en annen USB-C-**data**kabel (mange kabler er kun strøm). Sjekk også at brettet vises: kjør i Terminal `ls /dev/cu.*` før og etter du plugger inn.

**"Failed to connect" / "Timed out waiting for packet header"**
Bruk BOOT+Reset-sekvensen fra Trinn 3.2 for å tvinge nedlastingsmodus.

**Kompilerer, men skjermen forblir hvit/blank**
Nesten alltid feil **Flash Size** eller **PSRAM**. Sett Flash = 32MB, PSRAM = OPI PSRAM, last opp på nytt.

**Kommer ikke på WiFi**
Bekreft at nettet er 2,4 GHz. Mange rutere kringkaster 2,4 og 5 GHz under samme navn — da må du enten skille dem, eller bruke et gjeste-/telefon-hotspot på 2,4 GHz for test.

**Skjermen "blinker" mellom farger under oppdatering**
Normalt for E Ink Spectra 6. Ikke avbryt.

---

## ⚠️ Må løses: to nettverk under samme navn

Under første WiFi-test dukket det opp et nettverksproblem som må ryddes opp i før det permanente oppsettet:

- **Macen** var på `192.168.1.x` (ruter `192.168.1.1` — en **Google Nest / Google WiFi**).
- **ePaper-brettet** fikk `192.168.61.x`.

Begge var koblet til «hjemmenettet», men havnet på **to forskjellige subnett**. Det betyr at det hjemme finnes **to rutere/aksesspunkter som kringkaster samme WiFi-navn** (typisk en ISP-ruter *og* Google Nest-en, i et dobbelt-NAT-oppsett). Mac og brett endte på hver sin ruter og kunne derfor ikke nå hverandre.

**Midlertidig fiks (for test):** telefon-hotspot (2,4 GHz). Sett `ssid`/`password` i `srvr.h` til hotspotet, koble Macen til samme hotspot, bruk IP-en fra Serial Monitor.

### Anbefalt permanent løsning

Målet i det ferdige prosjektet er at **utendørs-Pi-en** skal sende bildet til brettet automatisk — så de to må garantert være på samme nett, og brettet må ha en **forutsigbar adresse**. Anbefaling, i prioritert rekkefølge:

1. **Fjern det doble nettverket (rot­årsaken).** Bestem hvilken ruter som skal styre nettet — sannsynligvis Google Nest-en. Sett den *andre* ruteren i **bridge-modus** (eller slå av DHCP på den), så det bare finnes **ett subnett** og **ett DHCP** hjemme. Da får alle enheter (Mac, brett, Pi) adresser i samme `192.168.1.x`-serie, og «to nett med samme navn»-problemet forsvinner.

2. **Gi brettet en fast IP via DHCP-reservasjon.** I ruterens innstillinger, bind brettets **MAC-adresse** til en fast IP (f.eks. `192.168.1.50`). Da endrer aldri adressen seg, og Pi-en vet alltid hvor den skal sende bildet. (Brettets MAC finner du i Serial Monitor ved oppstart, eller i ruterens liste over tilkoblede enheter — det er *ikke* MAC-en `fc:b2:14…` som stod i Mac-panelet, den er Macens.)

3. **Best: bruk et navn i stedet for IP (mDNS).** Legg til mDNS i firmwaren så brettet melder seg som f.eks. `fugleramme.local`. Da kan Pi-en poste til `http://fugleramme.local` uansett hvilken IP den får — helt uavhengig av ruter-fikling. Dette gjør oppsettet mest robust på sikt.

Kortversjon: **ett nett hjemme (bridge den ene ruteren) + fast adresse til brettet (DHCP-reservasjon), og gjerne `fugleramme.local` (mDNS) på toppen.**

---

## Når dette virker → neste steg

Da er Fase 1 ferdig, og veien videre er:
- Bytte ut den manuelle nettleser-opplastingen med et **HTTP POST**-endepunkt så utendørs-Pi-en kan sende bildet automatisk hver morgen (samme `05`-firmware er utgangspunktet — den har allerede web/HTTP-mottak innebygd).
- Sette opp **deep sleep** mellom oppdateringer for lavt strømforbruk.

Si ifra når skjermen viser testbildet, så tar vi neste kobling derfra.

---

### Kilder (offisiell Waveshare-dokumentasjon)
- Produktoversikt: https://docs.waveshare.com/ESP32-S3-ePaper-13.3E6
- Arduino-oppsett og eksempler: https://docs.waveshare.com/ESP32-S3-ePaper-13.3E6/Development-Environment-Setup-Arduino
- Ressurser/nedlastinger: https://docs.waveshare.com/ESP32-S3-ePaper-13.3E6/Resources-And-Documents
- Demo-kode (GitHub): https://github.com/waveshareteam/ESP32-S3-ePaper-13.3E6
