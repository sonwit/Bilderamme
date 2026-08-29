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
#include "cJSON.h"
#include "config.h"

// Europa/Oslo med sommertid — brukes til aa regne ut opptaksplanen lokalt.
static const char *TZ_INFO = "CET-1CEST,M3.5.0,M10.5.0/3";
static const time_t TIME_VALID_AFTER = 1735689600; // 2025-01-01 — foer dette er klokka usynket

// Overlever deep sleep (RTC-minne). boot_count teller oppvaakninger,
// fail-telleren gir oss et blikk paa hvor ofte opplasting ryker.
RTC_DATA_ATTR uint32_t boot_count = 0;
RTC_DATA_ATTR uint32_t uploads_ok = 0;
RTC_DATA_ATTR uint32_t uploads_failed = 0;

// ---------------------------------------------------------------- fjernkonfig
// Justerbare parametre uten reflash: brikken henter GET /config fra serveren
// etter hver opplasting og lagrer i RTC-minne (overlever deep sleep). Nye
// verdier gjelder fra NESTE oekt. Ved stroembrudd faller den tilbake til
// config.h-standardene til foerste vellykkede henting — selvhelende.
// Endres fra Macen:  curl -X POST --data '{"gain_shift":12}' <server>:8091/config
struct RemoteCfg {
  uint32_t magic;
  int32_t rev;                  // versjonsnummer fra serveren — ekkoes i helse-JSON
  int16_t gain_shift, highpass_hz, rec_seconds, test_interval_s;
  int16_t dawn_start, dawn_end, dawn_interval_min, day_start, day_end;
};
#define CFG_MAGIC 0xF00D1E55
RTC_DATA_ATTR RemoteCfg cfg;

static void cfg_defaults() {
  cfg.magic = CFG_MAGIC;
  cfg.rev = 0;
  cfg.gain_shift = GAIN_SHIFT;
  cfg.highpass_hz = HIGHPASS_HZ;
  cfg.rec_seconds = REC_SECONDS;
  cfg.test_interval_s = TEST_INTERVAL_S;
  cfg.dawn_start = DAWN_START_HOUR;
  cfg.dawn_end = DAWN_END_HOUR;
  cfg.dawn_interval_min = DAWN_INTERVAL_MIN;
  cfg.day_start = DAY_START_HOUR;
  cfg.day_end = DAY_END_HOUR;
}

static int16_t clamp16(long v, long lo, long hi) {
  if (v < lo) return (int16_t)lo;
  if (v > hi) return (int16_t)hi;
  return (int16_t)v;
}

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

// Neste opptaksslot etter `now` (lokaltid), etter planen i cfg.
//
// Slottet maa ligge et stykke fram, ikke bare i framtida. Deep-sleep-timeren
// gaar paa en intern RC-oscillator som bommer 2-7 % og UFORUTSIGBART: fire
// naesten like lange soevner 29. august bommet 28, 38, 84 og 87 sekunder for
// tidlig. Naar brikka vaakner mer enn en oektlengde for tidlig, er den ferdig
// FOER slottet -- og med den gamle testen (t > now) siktet den da paa slottet
// den nettopp hadde dekket, sov noen sekunder, og tok opp én gang til.
//
//   13:18:33  vaakner 87 s for tidlig
//   13:19:38  ferdig, 22 s foer slottet 13:20
//   13:20:01  samme slott én gang til        <- dublett
//
// Halvparten av dagene i timesplanen gikk slik, og to av fire slott i
// tjueminuttersplanen. Marginen er halve intervallet, men aldri mer enn fire
// minutter: halve intervallet alene ville faatt en treg oekt (wifi-retry) til
// aa hoppe over en hel time, og en fast margin ville stjaalet annethvert
// slott ved fem minutters intervall.
static time_t next_slot(time_t now) {
  struct tm lt;
  localtime_r(&now, &lt);

  for (int add_day = 0; add_day < 2; add_day++) {
    struct tm day = lt;
    day.tm_mday += add_day; // mktime normaliserer maanedsskifter
    for (int h = cfg.dawn_start; h <= cfg.day_end; h++) {
      int step = (h <= cfg.dawn_end) ? cfg.dawn_interval_min : 60;
      if (h < cfg.dawn_start || (h > cfg.dawn_end && h < cfg.day_start)) continue;
      for (int m = 0; m < 60; m += step) {
        struct tm slot = day;
        slot.tm_hour = h;
        slot.tm_min = m;
        slot.tm_sec = 0;
        slot.tm_isdst = -1; // la mktime avgjoere sommertid
        time_t t = mktime(&slot);
        long margin = step * 30L;              // halve intervallet, i sekunder
        if (margin > SLOT_MARGIN_MAX_S) margin = SLOT_MARGIN_MAX_S;
        if (t > now + margin) return t;
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
  const float hp_a = 1.0f - 6.2832f * cfg.highpass_hz / SAMPLE_RATE;
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
      if (cfg.highpass_hz > 0) {
        if (!hp_primed) { hp_px = xs; hp_primed = true; }
        hp_y = hp_a * (hp_y + xs - hp_px);
        hp_px = xs;
        v = (int32_t)hp_y >> cfg.gain_shift;
      } else {
        v = raw[i] >> cfg.gain_shift;      // 24-bit i 32-bit ramme -> 16 bit (+gain)
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
  j += ", \"duration_req_s\": " + String(cfg.rec_seconds);
  j += ", \"gain_shift\": " + String(cfg.gain_shift);
  j += ", \"cfg_rev\": " + String(cfg.rev);
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

// Hent fjernkonfig fra serveren (kalles mens wifi likevel er oppe, etter
// opplasting). Ukjente/utelatte noekler beholder gjeldende verdi; alle
// verdier klemmes til trygge omraader (rec_seconds er PSRAM-begrenset).
static void fetch_config() {
  String url = String("http://") + INGEST_HOST + ":" + String(INGEST_PORT) + "/config";
  if (strlen(INGEST_TOKEN)) url += String("?token=") + INGEST_TOKEN;
  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(url)) return;
  int code = http.GET();
  String body = (code == 200) ? http.getString() : "";
  http.end();
  if (code != 200 || !body.length()) return;

  cJSON *root = cJSON_Parse(body.c_str());
  if (!root) { log_line("Fjernkonfig: ugyldig JSON — ignorert."); return; }
  struct { const char *key; int16_t *dst; long lo, hi; } fields[] = {
    {"gain_shift",        &cfg.gain_shift,        8, 16},
    {"highpass_hz",       &cfg.highpass_hz,       0, 2000},
    {"rec_seconds",       &cfg.rec_seconds,      10, 75},
    {"test_interval_s",   &cfg.test_interval_s,   0, 3600},
    {"dawn_start",        &cfg.dawn_start,        0, 23},
    {"dawn_end",          &cfg.dawn_end,          0, 23},
    {"dawn_interval_min", &cfg.dawn_interval_min, 5, 60},
    {"day_start",         &cfg.day_start,         0, 23},
    {"day_end",           &cfg.day_end,           0, 23},
  };
  for (auto &f : fields) {
    cJSON *v = cJSON_GetObjectItem(root, f.key);
    if (cJSON_IsNumber(v)) *f.dst = clamp16((long)v->valuedouble, f.lo, f.hi);
  }
  cJSON *rev = cJSON_GetObjectItem(root, "rev");
  if (cJSON_IsNumber(rev) && (int32_t)rev->valuedouble != cfg.rev) {
    cfg.rev = (int32_t)rev->valuedouble;
    log_line("Fjernkonfig rev %ld tatt i bruk (gain %d, hp %d Hz, %d s, plan %02d-%02d/%d+%02d-%02d).",
             (long)cfg.rev, cfg.gain_shift, cfg.highpass_hz, cfg.rec_seconds,
             cfg.dawn_start, cfg.dawn_end, cfg.dawn_interval_min, cfg.day_start, cfg.day_end);
  }
  cJSON_Delete(root);
}

// ---------------------------------------------------------------- hovedloep

static void go_to_sleep(time_t now) {
  uint64_t sleep_s;
  if (cfg.test_interval_s > 0) {
    sleep_s = cfg.test_interval_s;
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
  if (cfg.magic != CFG_MAGIC) cfg_defaults(); // kaldstart/stroembrudd -> config.h
  boot_count++;
  bool cold_boot = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED;
  if (cold_boot) delay(2500); // gi USB-serial tid til aa koble til ved benken

  log_line("=== fugleramme utedel v2 — oppvaakning #%lu (%s) ===",
           (unsigned long)boot_count, cold_boot ? "kaldstart" : "timer");

  // Batterilinja gjenskapt 27.08.2026 fra brettets egen flash. Formatstrengen
  // "Batteri: %.2f V (ADC-pinne %d, deler %.3f)" laa i binaeren, men fantes
  // ikke i noen commit — den ble flashet fra en ucommittet endring paa Macen,
  // og forsvant da Macen ble nullstilt. Koden rundt er rekonstruert; utskriften
  // er verifisert identisk med brettets ("Batteri: 4.07 V (ADC-pinne 1, deler 2.004)").
  //
  // Behold den. Da Macen ble nullstilt var config.h borte, og det var NETTOPP
  // denne linja som fortalte oss hvilken ADC-pinne og hvilken delerverdi
  // brettet faktisk brukte — helse-JSON-en rapporterer bare resultatet.
#if BATT_ADC_PIN >= 0
  {
    uint32_t mv = 0;
    for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(BATT_ADC_PIN);
    log_line("Batteri: %.2f V (ADC-pinne %d, deler %.3f)",
             (mv / 8) * BATT_DIVIDER / 1000.0, BATT_ADC_PIN, (double)BATT_DIVIDER);
  }
#endif

  // Kaldstart uten gyldig klokke: synk foerst, saa vi kan stemple og planlegge.
  if (time(nullptr) < TIME_VALID_AFTER) {
    if (wifi_connect()) ntp_sync();
  }

  // --- 1. opptak (radio roeres ikke — stille og stroemgjerrig) --------------
  const size_t samples_wanted = (size_t)SAMPLE_RATE * cfg.rec_seconds;
  const size_t wav_bytes = 44 + samples_wanted * 2;
  uint8_t *wav = (uint8_t *)ps_malloc(wav_bytes);
  if (!wav) {
    log_line("FEIL: fikk ikke %u kB PSRAM — er PSRAM slaatt paa (OPI PSRAM)?",
             (unsigned)(wav_bytes / 1024));
    go_to_sleep(time(nullptr));
  }
  log_line("Tar opp %d s @ %d Hz (gain %d, hp %d Hz, cfg rev %ld) ...",
           cfg.rec_seconds, SAMPLE_RATE, cfg.gain_shift, cfg.highpass_hz, (long)cfg.rev);
  uint32_t rec_start_ms = millis();
  size_t samples = record_audio((int16_t *)(wav + 44), cfg.rec_seconds);
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
    fetch_config(); // mens radioen likevel er paa — gjelder fra neste oekt
  } else {
    log_line("Ingen nett/klokke — opptaket droppes (vises som hull i dekningen).");
    uploads_failed++;
  }
  free(wav);

  // --- 4. sov til neste oekt ----------------------------------------------
  go_to_sleep(time(nullptr));
}

void loop() {} // naas aldri — vi sover fra setup()
