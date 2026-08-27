// config.example.h — kopier denne til config.h og fyll inn dine egne verdier.
// config.h er git-ignorert, saa passordet ditt havner aldri i repoet.
#pragma once

// ---------------------------------------------------------------- nettverk
#define WIFI_SSID     "DITT_WIFI_NAVN"        // maa vaere 2,4 GHz
#define WIFI_PASS     "DITT_WIFI_PASSORD"

// Hjemmeserveren som kjoerer tools/audio_ingest.py
#define INGEST_HOST   "192.168.1.38"
#define INGEST_PORT   8091
#define INGEST_TOKEN  ""                      // valgfri delt hemmelighet (matcher INGEST_TOKEN paa serveren)

#define HOSTNAME      "fugleramme-esp"        // vises i helse-JSON og statistikk

// ---------------------------------------------------------------- opptak
#define SAMPLE_RATE   48000                   // Hz — samme som Pi-pipelinen
#define REC_SECONDS   60                      // sekunder per oekt

// INMP441 gir 24-bit data i 32-bit rammer. Vi skifter ned til 16 bit:
//   16 = raatt nivaa (identisk med Pi-ens S32->S16), 14 = +12 dB, 12 = +24 dB.
// Mikrofonen tar opp lavt og serveren peak-normaliserer uansett, men litt
// digital gain her bevarer flere signalbiter. 14 er trygt mot klipping.
#define GAIN_SHIFT    14

// Hoeypassfilter (Hz) foer gain — kutter vindrumling (<100 Hz) som ellers
// klipper opptaket og drukner fuglesangen. 0 = av. 150 er trygt: fugler
// synger fra ~1 kHz og oppover.
#define HIGHPASS_HZ   150

// ---------------------------------------------------------------- pinner
// XIAO ESP32-S3: D1=GPIO2, D2=GPIO3, D3=GPIO4 (se docs/Utedel v2).
// INMP441: VDD->3V3, GND->GND, L/R->GND, SCK->D1, WS->D2, SD->D3.
#define PIN_I2S_SCK   2                       // BCLK  (INMP441 SCK)
#define PIN_I2S_WS    3                       // LRCLK (INMP441 WS)
#define PIN_I2S_SD    4                       // DATA  (INMP441 SD)

// ---------------------------------------------------------------- batteri (valgfritt)
// Maal batterispenningen: lodd 2 like motstander (f.eks. 220k + 220k) som
// spenningsdeler fra BAT+ til GND, midtpunktet til en ADC-pinne (A0 = GPIO1).
// Sett -1 for aa slaa av (da rapporteres ingen "volt" i helse-JSON).
#define BATT_ADC_PIN  -1
#define BATT_DIVIDER  2.0                     // (R1+R2)/R2 — 2.0 ved like motstander.
                                              // Verdt aa kalibrere mot et multimeter:
                                              // brettet i drift bruker 2.004.

// ---------------------------------------------------------------- opptaksplan
// Samme plan som Pi-ens crontab: dagsang hvert 30. min 04:00–08:30,
// resten av dagen hver hele time 09:00–21:00. Natta sover vi.
#define DAWN_START_HOUR    4
#define DAWN_END_HOUR      8                  // til og med — siste halvtimesoekt 08:30
#define DAWN_INTERVAL_MIN  30
#define DAY_START_HOUR     9
#define DAY_END_HOUR       21                 // siste oekt 21:00

// Benketesting: > 0 = ignorer planen og kjoer en oekt saa ofte (sekunder).
// 0 = normal drift etter planen over.
#define TEST_INTERVAL_S    0
