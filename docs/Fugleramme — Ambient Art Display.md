  

Et DIY-prosjekt som kombinerer fuglelyd-gjenkjenning, værdata og AI-bildegenerering for å lage et daglig oppdatert kunstbilde på en e-ink bilderamme.

  

---

  

## Konsept

  

Hver morgen:

1. Utendørs-Pi tar opp lyd i hagen i ~10 minutter

2. BirdNET-Analyzer identifiserer hvilke fugler som synger

3. Værdata hentes fra yr (api.met.no) (temperatur, vær, årstid)

4. En prompt bygges basert på fugler + vær

5. Flux/DALL-E genererer et akvarellbilde

6. Bildet sendes over WiFi til e-ink-rammen inne

7. E-ink-rammen oppdaterer seg og viser bildet

  

****Eksempel-prompt:****

> "A misty watercolor painting of a Norwegian suburban garden at dawn. A song thrush perches on a wet branch, a great tit feeds below. Light rain, 8°C, overcast June morning. Soft muted palette, impressionist style."

  

---

  

## Arkitektur

  

```

[Utendørs: Orange Pi Zero 2W]

  → Mikrofon (INMP441 I2S) — tar opp fuglelyd

  → Kamera (RPi Camera Module 3 Wide) — tar bilde

  → BirdNET-Analyzer (Python, lokalt)

  → yr / api.met.no (vær)

  → Replicate API / Flux (bilgegenerering)

  → Sender JPEG over WiFi (HTTP POST)

  

[Innendørs: Waveshare ESP32-S3-ePaper-13.3E6]

  → Mottar JPEG over WiFi

  → Viser på 13.3" fullfarget e-ink skjerm (E Ink Spectra 6, 7 farger)

  → Sover til neste morgen

```

  

---

  

## Komponenter

  

### Innendørs — bilderamme-enhet

| Del | Produkt | Kjøpt fra |

|---|---|---|

| Skjerm + controller | Waveshare ESP32-S3-ePaper-13.3E6 (13.3", 7-farge, WiFi innebygd) | Waveshare |

| Strømadapter | Raspberry Pi 4 USB-C 5V/3A | Waveshare |

| Bilderamme | IKEA RÖDALM 30×40 cm | IKEA |

  

### Utendørs — sensor-enhet

| Del | Produkt | Kjøpt fra |

|---|---|---|

| Mikrodatamaskin | Orange Pi Zero 2W 1GB RAM (Allwinner H618, quad-core 1.5GHz) | AliExpress |

| Kamera | Raspberry Pi Camera Module 3 Wide (12MP, 120°) | Electrokit |

| Mikrofon | INMP441 I2S MEMS (omnidireksjonell, 24-bit) | Electrokit |

| Lagring | MicroSD 32GB (med Raspberry Pi OS — flasher Armbian) | Electrokit |

| Vanntett boks | ABS IP65 200×150×75mm grå | Electrokit |

| Kabelgjennomføringer | PG7 cable gland + hexagonal locknut (×3) | Electrokit |

| Kamerakabel | Raspberry Pi CSI Camera cable 200mm | Electrokit |

| GPIO-kabler | Jumper wire 40-pin 30cm female/female (dupont) | Electrokit |

  

### Solstrømsystem

| Del | Produkt | Kjøpt fra |

|---|---|---|

| Strømstyring | Waveshare Solar Power Manager (D) — MPPT, 5V/3A ut | Waveshare |

| Solcellepanel | Solar Panel 6V 5W (monokrystallinsk) | Waveshare |

| Batteri | 3.7V 10 000mAh LiPo (1260100, PH2.0-kontakt) | AliExpress |

  

---

  

## Software-stack

  

### Utendørs Pi (Armbian på Orange Pi Zero 2W)

- ****OS:**** Armbian (Debian-basert, for Orange Pi)

- ****BirdNET-Analyzer**** — lokal fuglelyd-gjenkjenning (Python, TensorFlow Lite)

- ****libcamera**** — kamerakontroll

- ****yr (api.met.no)**** — gratis værdata, ingen API-nøkkel nødvendig

- ****Replicate API**** — bilgegenerering med Flux-modell (~$0.05/bilde)

- ****Python 3**** med biblioteker: `birdnetlib`, `requests`, `picamera2`, `sounddevice`

- ****Cron-jobb**** — kjøres kl. 06:00 hver morgen

  

### Innendørs skjerm (ESP32-S3)

- ****Arduino IDE**** eller ****ESP-IDF****

- ****Waveshare e-Paper bibliotek****

- WiFi-mottak av JPEG over HTTP

- Deep sleep mellom oppdateringer

  

---

  

## Prompt-strategi

  

Prompten bygges dynamisk fra:

- Liste over identifiserte fugler (norske + latinske navn)

- Temperatur og værbeskrivelse fra yr (api.met.no)

- Årstid og tid på dagen

- Fast stilinstruksjon: akvarell, norsk hage, myk palett

  

```python

prompt = f"""A {weather_desc} watercolor painting of a Norwegian suburban garden 

at {time_of_day}. {bird_description}. {temperature}°C, {season}. 

Soft muted palette, impressionist style, natural light."""

```

  

---

  

## Fase 1 — Test av ESP32-skjermen (første steg)

  

Før alt annet: verifiser at Waveshare ESP32-S3-ePaper-13.3E6 fungerer og kan vise et bilde.

  

****Mål:**** Sende et testbilde fra Mac til ESP32 over WiFi og se det på skjermen.

  

****Trenger:****

- Waveshare ESP32-S3-ePaper-13.3E6 (mottatt ✅)

- USB-C kabel (for programmering)

- Arduino IDE installert på Mac

- Waveshare eksempelkode fra GitHub

  

****Steg:****

1. Installer Arduino IDE + ESP32-støtte (Espressif board manager)

2. Last ned Waveshare sin eksempelkode for ESP32-S3-ePaper-13.3E6

3. Flash et enkelt "Hello World"-eksempel til skjermen

4. Test WiFi-mottak av JPEG og visning på skjermen

  

---

  

## Fase 2 — Utendørs Pi

  

1. Flash Armbian til MicroSD

2. Konfigurer WiFi og SSH

3. Installer BirdNET-Analyzer

4. Test INMP441-mikrofon med I2S

5. Test kamera med libcamera

6. Skriv Python-script for hele flyten

7. Sett opp cron-jobb

  

---

  

## Nyttige lenker

  

- [Waveshare ESP32-S3-ePaper-13.3E6 wiki](https://www.waveshare.com/wiki/ESP32-S3-ePaper-13.3E6)

- [BirdNET-Analyzer GitHub](https://github.com/kahst/BirdNET-Analyzer)

- [MET Locationforecast API (yr)](https://api.met.no/weatherapi/locationforecast/2.0/documentation) — krever identifiserende User-Agent, se ToS

- [Replicate Flux API](https://replicate.com/black-forest-labs/flux-schnell)

- [Armbian for Orange Pi Zero 2W](https://www.armbian.com/orange-pi-zero-2w/)

- [Orange Pi Zero 2W pinout](http://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-Zero-2W.html)

  

---

  

## Totalkostnad

  

| | |

|---|---|

| Waveshare-bestilling | ~3 100 kr |

| Electrokit-bestilling | ~1 260 kr |

| AliExpress-bestilling | ~470 kr |

| IKEA RÖDALM | 129 kr |

| ****Totalt**** | ****~4 960 kr**** |

  

Løpende: ~5–7 kr/mnd (Replicate API, 1 bilde/dag)