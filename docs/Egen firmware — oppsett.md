# Egen firmware — WiFi-mottak med den fungerende driveren

Dette erstatter Waveshares buggy web-loader (05). I stedet gjoer **Python-scriptet** all bildebehandling, og **ESP32-en** tar bare imot en ferdig buffer og viser den med den samme driveren som fungerte i eksempel 03. Resultatet er rene bilder uten forskyvning — og det er akkurat samme flyt som utendoers-Pi-en skal bruke automatisk senere.

## Delene

- **Firmware:** `example/Arduino-3.2.0/examples/07_Fugleramme_WiFi/` (i ESP32-repoet)
  Tar imot 960000 byte via `POST /display` og viser med `EPD_13IN3E_Display`.
- **Sender:** `send_to_frame.py` (i denne mappen)
  Skalerer bildet til 1200×1600, dithrer til de 6 panel-fargene, pakker 2 piksler/byte, og sender.

---

## Steg 1 — Flash firmwaren

1. Aapne `07_Fugleramme_WiFi/07_Fugleramme_WiFi.ino` i Arduino IDE.
2. Oeverst i fila, sett WiFi-en din:
   ```cpp
   #define WIFI_SSID   "hjemmenettet"
   #define WIFI_PASS   "DITT_WIFI_PASSORD"
   #define MDNS_NAME   "fugleramme"        // gir http://fugleramme.local
   ```
3. Samme board-innstillinger som foer (ESP32S3 Dev Module, Flash 32MB, PSRAM OPI).
4. **Upload**, deretter **Reset**.
5. I Serial Monitor (115200) skal det staa `WiFi tilkoblet. IP: …`, `mDNS: http://fugleramme.local`, og `Klar. Venter paa bilde...`. Skjermen blankes hvit ved oppstart.

## Steg 2 — Send et bilde fra Macen

I Terminal:
```bash
pip install pillow numpy requests          # foerste gang
python3 send_to_frame.py mittbilde.jpg
```
Scriptet bruker `http://fugleramme.local` som standard. Virker ikke mDNS-navnet paa maskinen din, bruk IP-en fra Serial Monitor i stedet:
```bash
python3 send_to_frame.py mittbilde.jpg --host 192.168.1.159
```
Skjermen oppdaterer seg paa ~30 sek. Ferdig.

> Vil du bare lage bufferen uten aa sende (for feilsoeking):
> `python3 send_to_frame.py bilde.jpg --out buffer.bin` → skal gi en fil paa noeyaktig 960000 byte.

---

## Hvorfor dette er bedre

- **Ingen forskyvning:** bruker `EPD_13IN3E_Display` fra eksempel 03, som splitter master/slave-halvdelene riktig.
- **Robust overfoering:** ESP32-en leser noeyaktig 960000 byte og avviser alt annet — ingen «noen byte forsvant»-glidning.
- **Rett vei mot maalet:** utendoers-Pi-en kan kjoere `send_to_frame.py` (eller samme logikk) i det daglige scriptet og poste bildet automatisk. Ingenting maa gjoeres om.

## Fargejustering (hvis noe ser rart ut)
Panelet bruker 6 faste farger. Scriptet dithrer mot disse. Ser fargene byttet ut, kan rekkefoelgen paa nibblene i `pack()` snus (bytt `hi`/`lo`), men verifisert oppsett er: **hoey nibble = venstre piksel**, koder BLACK 0x0, WHITE 0x1, YELLOW 0x2, RED 0x3, BLUE 0x5, GREEN 0x6.

## Neste steg
Naar dette viser et rent bilde: sett brettet i **deep sleep** mellom oppdateringer for lavt stroemforbruk, og legg `send_to_frame.py`-kallet inn i Pi-ens morgen-cron sammen med BirdNET + vaer + bildegenerering.
