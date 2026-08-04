// outdoor_sensor.ino — fugleramme-utedelen v2 paa Seeed XIAO ESP32-S3.
//
// Erstatter Raspberry Pi 3 B som lydsensor. Pi-en trakk ~450 mA i tomgang og
// fikk undervoltage paa solcelledrift; XIAO-en bruker ~100 mA i noen titalls
// sekunder per oekt og ~14 µA i deep sleep — ekte duty-cycling, som Pi-en
// aldri kunne gi.
//
// Flyt per oppvaakning (timer fra deep sleep):
//   1. Ta opp REC_SECONDS mono 16-bit fra INMP441 (I2S) rett i PSRAM.
//      Opptak foerst, radio av — mikrofonen slipper wifi-stoey, og vi bruker
//      ikke straum paa wifi foer vi maa.
//   2. Koble til wifi, synk klokka (NTP). Systemklokka overlever deep sleep
//      (RTC), men driver — derfor synk hver gang, og tidsstempelet paa
//      opptaket regnes BAKOVER fra synket klokke (alltid riktig stempel).
//   3. POST WAV-en til tools/audio_ingest.py paa hjemmeserveren, med
//      helse-JSON i X-Fugl-Health-headeren (blir sidecar → statistikken).
//   4. Regn ut neste oekt etter planen i config.h og sov til da.
//
// Feiler wifi/opplasting: proev igjen noen ganger, gi saa opp og sov —
// opptaket droppes (dekningsstatistikken paa serveren viser hullet).
// Ingen SD/koe i v1; PSRAM overlever ikke deep sleep.
//
// Bygg: Arduino IDE, board "XIAO_ESP32S3" (esp32-core >= 3.0), PSRAM "OPI PSRAM".
// Se docs/Utedel v2 — ESP32-S3 XIAO.md for alt oppsett.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP_I2S.h>
#include <time.h>
#include "esp_sleep.h"
#include "esp_sntp.h"
#include "config.h"

// Europa/Oslo med sommertid — brukes til aa regne ut opptaksplanen lokalt.
static const char *TZ_INFO = "CET-1CEST,M3.5.0,M10.5.0/3";
static const time_t TIME_VALID_AFTER = 1735689600; // 2025-01-01 — foer dette er klokka usynket

// Overlever deep sleep (RTC-minne). boot_count teller oppvaakninger,
// fail-telleren gir oss et blikk paa hvor ofte opplasting ryker.
RTC_DATA_ATTR uint32_t boot_count = 0;
RTC_DATA_ATTR uint32_t uploads_ok = 0;
RTC_DATA_ATTR uint32_t uploads_failed = 0;

static I2SClass i2s;

static void log_line(const char *fmt, ...) {
  char buf[192];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  Serial.println(buf);
}

// ---------------------------------------------------------------- wifi + tid

static bool wifi_connect(uint32_t timeout_ms = 20000) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < timeout_ms) delay(200);
  if (WiFi.status() == WL_CONNECTED) {
    log_line("WiFi tilkoblet: %s (%d dBm)", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
  }
  log_line("WiFi: fikk ikke kontakt paa %lu ms.", (unsigned long)timeout_ms);
  return false;
}

// Venter paa EKTE SNTP-fullfoering, ikke bare "klokka ser gyldig ut" —
// RTC-tida overlever deep sleep og ser alltid gyldig ut, men driver flere
// minutter per natt. Verifisert 2026-08-04: uten denne ventingen ble et
// 03:45-opptak stemplet 04:00 og kolliderte med den ekte 04:00-oekta.
static bool ntp_sync(uint32_t timeout_ms = 10000) {
  configTzTime(TZ_INFO, "no.pool.ntp.org", "pool.ntp.org", "time.google.com");
  uint32_t t0 = millis();
  while (millis() - t0 < timeout_ms) {
    if (sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED) return true;
    delay(200);
  }
  // Fallback: driftende RTC-tid er bedre enn ingenting (kald natt + svak wifi).
  return time(nullptr) > TIME_VALID_AFTER;
}

// ---------------------------------------------------------------- opptaksplan

// Neste opptaksslot STRENGT etter `now` (lokaltid): 04:00–08:30 hvert 30. min,
// 09:00–21:00 hver hele time, ellers neste morgen 04:00.
static time_t next_slot(time_t now) {
  struct tm lt;
  localtime_r(&now, &lt);

  for (int add_day = 0; add_day < 2; add_day++) {
    struct tm day = lt;
    day.tm_mday += add_day; // mktime normaliserer maanedsskifter
    for (int h = DAWN_START_HOUR; h <= DAY_END_HOUR; h++) {
      int step = (h <= DAWN_END_HOUR) ? DAWN_INTERVAL_MIN : 60;
      if (h < DAWN_START_HOUR || (h > DAWN_END_HOUR && h < DAY_START_HOUR)) continue;
      for (int m = 0; m < 60; m += step) {
        struct tm slot = day;
        slot.tm_hour = h;
        slot.tm_min = m;
        slot.tm_sec = 0;
        slot.tm_isdst = -1; // la mktime avgjoere sommertid
        time_t t = mktime(&slot);
        if (t > now) return t;
      }
    }
  }
  return now + 3600; // skal ikke skje — men sov aldri evig
}

// ---------------------------------------------------------------- opptak

// Tar opp `seconds` sekunder mono 16-bit i `pcm`. Returnerer antall samples.
static size_t record_audio(int16_t *pcm, uint32_t seconds) {
  i2s.setPins(PIN_I2S_SCK, PIN_I2S_WS, -1, PIN_I2S_SD);
  if (!i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO)) {
    log_line("FEIL: I2S start feilet — sjekk pinner/ledninger.");
    return 0;
  }

  const size_t total = (size_t)SAMPLE_RATE * seconds;
  const size_t CHUNK = 1024;               // rammer per lesing
  static int32_t raw[CHUNK];
  size_t got = 0;

  // INMP441 trenger et lite oeyeblikk paa aa vaakne; kast foerste ~100 ms.
  for (int i = 0; i < 5; i++) i2s.readBytes((char *)raw, sizeof(raw));

  // 1. ordens hoeypass (~HIGHPASS_HZ) FOER gain: vind paa membranen lager
  // enorm rumling under 100 Hz som ellers klipper opptaket og drukner
  // fuglesangen (verifisert 2026-08-04 — BirdNET tolket vindstoetene som
  // myrrikse). Fugler synger fra ~1 kHz, saa filteret koster ingenting.
  const float hp_a = 1.0f - 6.2832f * HIGHPASS_HZ / SAMPLE_RATE;
  float hp_y = 0, hp_px = 0;
  bool hp_primed = false;  // start paa foerste sample — ellers gir DC-nivaaet
                           // ett fullskala-sprett i starten av hvert opptak
  while (got < total) {
    size_t want = min(CHUNK, total - got);
    size_t n = i2s.readBytes((char *)raw, want * sizeof(int32_t)) / sizeof(int32_t);
    if (n == 0) { log_line("FEIL: I2S ga ingen data — avbryter opptaket."); break; }
    for (size_t i = 0; i < n; i++) {
      float xs = (float)raw[i];
      int32_t v;
      if (HIGHPASS_HZ > 0) {
        if (!hp_primed) { hp_px = xs; hp_primed = true; }
        hp_y = hp_a * (hp_y + xs - hp_px);
        hp_px = xs;
        v = (int32_t)hp_y >> GAIN_SHIFT;
      } else {
        v = raw[i] >> GAIN_SHIFT;          // 24-bit i 32-bit ramme -> 16 bit (+gain)
      }
      if (v > 32767) v = 32767;
      if (v < -32768) v = -32768;
      pcm[got + i] = (int16_t)v;
    }
    got += n;
  }
  i2s.end();
  return got;
}

// Standard 44-byte PCM WAV-header rett i bufferet (mono 16-bit).
static void wav_header(uint8_t *h, uint32_t samples) {
  uint32_t data_bytes = samples * 2;
  uint32_t byte_rate = SAMPLE_RATE * 2;
  memcpy(h, "RIFF", 4);
  uint32_t riff = 36 + data_bytes;      memcpy(h + 4, &riff, 4);
  memcpy(h + 8, "WAVEfmt ", 8);
  uint32_t fmtlen = 16;                 memcpy(h + 16, &fmtlen, 4);
  uint16_t pcmfmt = 1, ch = 1;          memcpy(h + 20, &pcmfmt, 2); memcpy(h + 22, &ch, 2);
  uint32_t rate = SAMPLE_RATE;          memcpy(h + 24, &rate, 4);
  memcpy(h + 28, &byte_rate, 4);
  uint16_t align = 2, bits = 16;        memcpy(h + 32, &align, 2); memcpy(h + 34, &bits, 2);
  memcpy(h + 36, "data", 4);            memcpy(h + 40, &data_bytes, 4);
}

// ---------------------------------------------------------------- helse + opplasting

static String health_json(uint32_t awake_ms) {
  String j = "{";
  j += "\"host\": \"" HOSTNAME "\", \"model\": \"XIAO ESP32S3\", \"fw\": \"utedel-v2\"";
  j += ", \"wifi_dbm\": " + String(WiFi.RSSI());
  j += ", \"boot_count\": " + String(boot_count);
  j += ", \"uploads_ok\": " + String(uploads_ok);
  j += ", \"uploads_failed\": " + String(uploads_failed);
  j += ", \"awake_ms\": " + String(awake_ms);
  j += ", \"temp_c\": " + String(temperatureRead(), 1);
  j += ", \"duration_req_s\": " + String(REC_SECONDS);
  j += ", \"gain_shift\": " + String(GAIN_SHIFT);
#if BATT_ADC_PIN >= 0
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(BATT_ADC_PIN);
  j += ", \"volt\": " + String((mv / 8) * BATT_DIVIDER / 1000.0, 2);
#endif
  j += "}";
  return j;
}

static bool upload(uint8_t *wav, size_t len, const char *stamp, const String &health) {
  String url = String("http://") + INGEST_HOST + ":" + String(INGEST_PORT) +
               "/upload?stamp=" + stamp;
  if (strlen(INGEST_TOKEN)) url += String("&token=") + INGEST_TOKEN;

  for (int attempt = 1; attempt <= 3; attempt++) {
    if (!wifi_connect()) { delay(3000); continue; }
    HTTPClient http;
    http.setTimeout(45000); // 5,7 MB over svak wifi tar tid
    if (!http.begin(url)) { log_line("FEIL: http.begin"); return false; }
    http.addHeader("Content-Type", "audio/wav");
    http.addHeader("X-Fugl-Health", health);
    int code = http.POST(wav, len);
    String body = (code > 0) ? http.getString() : http.errorToString(code);
    http.end();
    if (code == 200) {
      log_line("Opplastet (%u kB): %s", (unsigned)(len / 1024), body.c_str());
      return true;
    }
    log_line("Opplasting forsoek %d feilet (%d: %s)", attempt, code, body.c_str());
    delay(5000);
  }
  return false;
}

// ---------------------------------------------------------------- hovedloep

static void go_to_sleep(time_t now) {
  uint64_t sleep_s;
  if (TEST_INTERVAL_S > 0) {
    sleep_s = TEST_INTERVAL_S;
    log_line("TESTMODUS: sover %llu s.", (unsigned long long)sleep_s);
  } else if (now > TIME_VALID_AFTER) {
    time_t nxt = next_slot(now);
    sleep_s = (uint64_t)(nxt - now);
    struct tm lt;
    localtime_r(&nxt, &lt);
    log_line("Neste oekt %02d:%02d (om %llu min). God natt.",
             lt.tm_hour, lt.tm_min, (unsigned long long)(sleep_s / 60));
  } else {
    // Klokka er aldri blitt synket (wifi nede fra kaldstart) — proev igjen om en time.
    sleep_s = 3600;
    log_line("Klokka usynket — sover 1 time og proever igjen.");
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(sleep_s * 1000000ULL);
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  boot_count++;
  bool cold_boot = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED;
  if (cold_boot) delay(2500); // gi USB-serial tid til aa koble til ved benken

  log_line("=== fugleramme utedel v2 — oppvaakning #%lu (%s) ===",
           (unsigned long)boot_count, cold_boot ? "kaldstart" : "timer");

  // Kaldstart uten gyldig klokke: synk foerst, saa vi kan stemple og planlegge.
  if (time(nullptr) < TIME_VALID_AFTER) {
    if (wifi_connect()) ntp_sync();
  }

  // --- 1. opptak (radio roeres ikke — stille og stroemgjerrig) --------------
  const size_t samples_wanted = (size_t)SAMPLE_RATE * REC_SECONDS;
  const size_t wav_bytes = 44 + samples_wanted * 2;
  uint8_t *wav = (uint8_t *)ps_malloc(wav_bytes);
  if (!wav) {
    log_line("FEIL: fikk ikke %u kB PSRAM — er PSRAM slaatt paa (OPI PSRAM)?",
             (unsigned)(wav_bytes / 1024));
    go_to_sleep(time(nullptr));
  }
  log_line("Tar opp %d s @ %d Hz ...", REC_SECONDS, SAMPLE_RATE);
  uint32_t rec_start_ms = millis();
  size_t samples = record_audio((int16_t *)(wav + 44), REC_SECONDS);
  if (samples < (size_t)SAMPLE_RATE * 5) { // < 5 s er ikke verdt aa analysere
    log_line("Opptaket ble for kort (%u samples) — dropper oekten.", (unsigned)samples);
    free(wav);
    go_to_sleep(time(nullptr));
  }
  wav_header(wav, samples);

  // --- 2. wifi + klokke ----------------------------------------------------
  bool online = wifi_connect();
  if (online) ntp_sync();

  // Stempel = naar opptaket STARTET, regnet bakover fra (nylig synket) klokke.
  time_t now = time(nullptr);
  time_t started = now - (time_t)((millis() - rec_start_ms) / 1000);
  char stamp[20];
  struct tm lt;
  localtime_r(&started, &lt);
  strftime(stamp, sizeof(stamp), "%Y%m%d_%H%M%S", &lt);

  // --- 3. opplasting -------------------------------------------------------
  if (online && now > TIME_VALID_AFTER) {
    String health = health_json(millis());
    if (upload(wav, 44 + samples * 2, stamp, health)) uploads_ok++;
    else uploads_failed++;
  } else {
    log_line("Ingen nett/klokke — opptaket droppes (vises som hull i dekningen).");
    uploads_failed++;
  }
  free(wav);

  // --- 4. sov til neste oekt ----------------------------------------------
  go_to_sleep(time(nullptr));
}

void loop() {} // naas aldri — vi sover fra setup()
