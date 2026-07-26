// audio.cpp — lyd-feedback via ES8311-codec + NS4150B-forsterker.
// Syntetiserer korte toner i koden (ingen store lydfiler noedvendig).
// Codec-oppsett og pinner er hentet fra Waveshares eksempel 02_Audio_out.

#include <Arduino.h>
#include <math.h>
#include "ESP_I2S.h"
#include "Wire.h"
#include "es8311.h"
#include "audio.h"

// I2C (codec-config) og I2S (lyddata) — pinner fra eksempel 02
#define I2C_SDA      41
#define I2C_SCL      42
#define I2S_MCK_PIN  14
#define I2S_BCK_PIN  21
#define I2S_LRCK_PIN 47
#define I2S_DOUT_PIN 45
#define I2S_DIN_PIN  48
#define PA_CTRL      13   // forsterker paa/av

#define SAMPLE_RATE  24000
#define MCLK_MULT    256
#define VOLUME       70    // codec-volum 0..100

static I2SClass i2s;
static bool audioReady = false;

static bool codecInit() {
  es8311_handle_t h = es8311_create(I2C_NUM_0, ES8311_ADDRESS_0);
  if (!h) { Serial.println("Lyd: es8311_create feilet"); return false; }

  es8311_clock_config_t clk = {
    .mclk_inverted     = false,
    .sclk_inverted     = false,
    .mclk_from_mclk_pin = true,
    .mclk_frequency    = SAMPLE_RATE * MCLK_MULT,
    .sample_frequency  = SAMPLE_RATE
  };
  if (es8311_init(h, &clk, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16) != ESP_OK) {
    Serial.println("Lyd: es8311_init feilet");
    return false;
  }
  es8311_voice_volume_set(h, VOLUME, NULL);
  es8311_microphone_config(h, false);
  return true;
}

void audioInit() {
  Wire.begin(I2C_SDA, I2C_SCL);
  pinMode(PA_CTRL, OUTPUT);
  digitalWrite(PA_CTRL, HIGH);          // forsterker paa

  if (!codecInit()) return;

  i2s.setPins(I2S_BCK_PIN, I2S_LRCK_PIN, I2S_DOUT_PIN, I2S_DIN_PIN, I2S_MCK_PIN);
  if (!i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT,
                 I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("Lyd: I2S begin feilet");
    return;
  }
  audioReady = true;
  Serial.println("Lyd klar");
}

// Spill en sinus-tone med kort inn/ut-fade (unngaar klikk).
static void playTone(float freqHz, int ms, float vol) {
  if (!audioReady) return;
  const int n    = (int)((long)SAMPLE_RATE * ms / 1000);
  const int fade = SAMPLE_RATE * 5 / 1000;   // 5 ms fade
  const float amp = 12000.0f * vol;          // godt under 32767 -> ingen klipping

  int16_t *buf = (int16_t *) malloc(n * sizeof(int16_t));
  if (!buf) return;

  for (int i = 0; i < n; i++) {
    float env = 1.0f;
    if (i < fade)          env = (float)i / fade;
    else if (i > n - fade) env = (float)(n - i) / fade;
    buf[i] = (int16_t)(amp * env * sinf(2.0f * PI * freqHz * i / SAMPLE_RATE));
  }
  i2s.write((uint8_t *)buf, n * sizeof(int16_t));   // blokkerer til ferdig spilt
  free(buf);
}

void audioStartupChime() {
  // Stigende C-E-G
  playTone(523.25f, 120, 0.7f);
  playTone(659.25f, 120, 0.7f);
  playTone(783.99f, 170, 0.7f);
}

void audioImageChime() {
  // Kjapp "pling" (G -> C)
  playTone(783.99f, 90, 0.7f);
  playTone(1046.5f, 150, 0.7f);
}
