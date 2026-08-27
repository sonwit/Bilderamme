/*
 * Fugleramme — WiFi-mottak for 13.3" Spectra 6 e-Paper (innedel)
 * -------------------------------------------------------------
 * Tar imot en ferdig-pakket bildebuffer (960000 byte) over HTTP POST og
 * viser den med Waveshares fungerende EPD_13IN3E_Display-driver (fra eksempel 03).
 *
 * Sender-siden (tools/send_to_frame.py) gjoer all tung jobb: skalerer bildet til
 * 1200x1600, dithrer til 6 farger og pakker 2 piksler/byte. ESP32-en trenger
 * derfor bare aa motta bytene og skyve dem til panelet.
 *
 * Endepunkter:
 *   GET  /          -> enkel statusside
 *   POST /display   -> body = 960000 raa byte (framebuffer) -> vises paa skjermen
 *
 * Naa til med: http://fugleramme.local  (mDNS) eller IP-en som printes i Serial.
 *
 * Rammen henger i veggen og har ingen resetknapp noen gidder aa trykke paa, saa
 * den passer paa seg selv: en task-watchdog starter brettet paa nytt hvis noe
 * blokkerer (typisk driverens ReadBusyH, som venter i en uendelig loekke hvis
 * BUSY-pinnen aldri slipper), og WiFi-en gjenopprettes — eller brettet startes
 * paa nytt — hvis nettet forsvinner under drift. Se WDT_TIMEOUT_MS under.
 *
 * WiFi-innstillinger ligger i config.h (kopier config.example.h -> config.h).
 */

#include <WiFi.h>
#include <ESPmDNS.h>
#include <esp_task_wdt.h>
#include "config.h"
#include "EPD_13in3e.h"
#include "audio.h"

// Framebuffer: 600 byte/rad * 1600 rader = 960000 byte (2 piksler per byte)
#define FB_SIZE  ((EPD_13IN3E_WIDTH / 2) * EPD_13IN3E_HEIGHT)

// Watchdog: en normal skjermtegning blokkerer i 25-35 s, og EPD_13IN3E_Init()
// kommer i tillegg — derfor 120 s og ikke noe kortere. Henger panelet eller
// nettverksloekken lenger enn det, er brettet uansett dodt for oss, og en
// omstart er bedre enn en ramme som er borte til noen drar ut stroemmen.
#define WDT_TIMEOUT_MS           120000UL

// Faar vi ikke WiFi ved oppstart innen dette, start paa nytt (ruteren kan ha
// vaert nede i et stroembrudd og trenger litt lenger tid enn brettet).
#define WIFI_BOOT_TIMEOUT_MS      60000UL

// Forsvinner WiFi under drift: proev reconnect, og gi opp (= omstart) etter dette.
#define WIFI_RECONNECT_TIMEOUT_MS 120000UL

WiFiServer server(80);
uint8_t   *framebuffer = nullptr;

bool          wdtActive  = false;
unsigned long wifiLostAt = 0;      // millis() da WiFi forsvant, 0 = tilkoblet

// Mat watchdogen. Trygg aa kalle selv om oppsettet feilet.
// (Ingen 'static' paa funksjonene her: Arduinos prototypegenerator lager
// oedelagte prototyper av static-funksjoner i en .ino, og skissa slutter aa
// kompilere. Verifisert 2026-08-27.)
void wdtFeed() {
  if (wdtActive) esp_task_wdt_reset();
}

void wdtSetup() {
  esp_task_wdt_config_t cfg;
  cfg.timeout_ms     = WDT_TIMEOUT_MS;
  cfg.idle_core_mask = 0;               // vi passer paa loop-tasken, ikke idle-taskene
  cfg.trigger_panic  = true;            // panic -> omstart

  // Arduino-kjernen har allerede satt opp task-watchdogen, saa reconfigure()
  // er normalveien. init() foerst ville logget en roed "TWDT already
  // initialized" i bootloggen hver gang, uten at noe var galt.
  esp_err_t err = esp_task_wdt_reconfigure(&cfg);
  if (err == ESP_ERR_INVALID_STATE) err = esp_task_wdt_init(&cfg);
  if (err == ESP_OK) err = esp_task_wdt_add(NULL);   // abonner denne tasken (setup+loop)

  wdtActive = (err == ESP_OK);
  if (wdtActive) Serial.printf("Watchdog paa (%lu s).\n", WDT_TIMEOUT_MS / 1000);
  else           Serial.printf("ADVARSEL: fikk ikke satt opp watchdog (%d).\n", (int)err);
}

// Holder WiFi i live mellom bilder. Rammen staar stille i doegn av gangen, og
// en droppet forbindelse som aldri kom tilbake er nettopp naar den blir borte.
void wifiKeepAlive() {
  if (WiFi.status() == WL_CONNECTED) {
    if (wifiLostAt) {
      Serial.print("WiFi tilbake. IP: ");
      Serial.println(WiFi.localIP());
      wifiLostAt = 0;
    }
    return;
  }

  if (wifiLostAt == 0) {
    wifiLostAt = millis();
    if (wifiLostAt == 0) wifiLostAt = 1;      // millis()-wrap: 0 betyr "tilkoblet"
    Serial.println("WiFi borte — kobler til paa nytt...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASS);
  } else if (millis() - wifiLostAt > WIFI_RECONNECT_TIMEOUT_MS) {
    Serial.println("WiFi kom ikke tilbake — starter brettet paa nytt.");
    Serial.flush();
    ESP.restart();
  }
  delay(200);
}

void renderFramebuffer() {
  Serial.println("Rendering...");
  EPD_13IN3E_Init();
  EPD_13IN3E_Display(framebuffer);
  EPD_13IN3E_Sleep();
  Serial.println("Display done!");
}

void setup() {
  Serial.begin(115200);
  delay(200);

  wdtSetup();

  DEV_Module_Init();
  audioInit();

  // Framebuffer i PSRAM (brettet har 16 MB PSRAM)
  framebuffer = (uint8_t *) ps_malloc(FB_SIZE);
  if (!framebuffer) {
    Serial.println("FEIL: fikk ikke allokert PSRAM-buffer");
    while (1) delay(1000);
  }
  // Fyll hvitt (0x1 i begge nibbler)
  memset(framebuffer, (EPD_13IN3E_WHITE << 4) | EPD_13IN3E_WHITE, FB_SIZE);

  // WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Kobler til WiFi");
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - wifiStart > WIFI_BOOT_TIMEOUT_MS) {
      Serial.printf("\nFikk ikke WiFi paa %lu s — starter paa nytt.\n",
                    WIFI_BOOT_TIMEOUT_MS / 1000);
      Serial.flush();
      ESP.restart();
    }
    wdtFeed();
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi tilkoblet. IP: ");
  Serial.println(WiFi.localIP());

  // mDNS -> http://fugleramme.local
  if (MDNS.begin(MDNS_NAME)) {
    MDNS.addService("http", "tcp", 80);
    Serial.print("mDNS: http://");
    Serial.print(MDNS_NAME);
    Serial.println(".local");
  }

  server.begin();

  // MERK: vi blanker IKKE skjermen ved oppstart. E-ink beholder forrige bilde
  // uten stroem, saa etter et stroembrudd skal det staa som det var. Init skjer
  // i renderFramebuffer() rett foer et nytt bilde tegnes.
  Serial.println("Klar. Venter paa bilde...");
  audioStartupChime();
}

void loop() {
  wdtFeed();
  wifiKeepAlive();

  WiFiClient client = server.available();
  if (!client) return;

  client.setTimeout(5);

  // --- Les foerste linje (request line) ---
  String reqLine = client.readStringUntil('\n');
  bool isPost    = reqLine.startsWith("POST");
  bool isDisplay = reqLine.indexOf("/display") >= 0;

  // --- Les headere, finn Content-Length ---
  long contentLength = 0;
  while (client.connected()) {
    String line = client.readStringUntil('\n');
    if (line == "\r" || line.length() <= 1) break;   // tom linje = slutt paa headere
    line.toLowerCase();
    int idx = line.indexOf("content-length:");
    if (idx >= 0) contentLength = line.substring(idx + 15).toInt();
  }

  if (isPost && isDisplay) {
    if (contentLength != FB_SIZE) {
      client.printf("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
                    "Forventet %d byte, fikk %ld\r\n", FB_SIZE, contentLength);
      client.flush();
      delay(5);
      client.stop();
      Serial.printf("Feil stoerrelse: %ld (skal vaere %d)\n", contentLength, FB_SIZE);
      return;
    }

    // --- Les body direkte inn i PSRAM-bufferet ---
    size_t got = 0;
    unsigned long lastData = millis();
    while (got < FB_SIZE && (millis() - lastData) < 30000) {
      int avail = client.available();
      if (avail > 0) {
        int n = client.read(framebuffer + got, FB_SIZE - got);
        if (n > 0) { got += n; lastData = millis(); }
      } else {
        wdtFeed();
        delay(1);
      }
    }

    if (got != FB_SIZE) {
      client.printf("HTTP/1.1 500 Internal Error\r\nConnection: close\r\n\r\n"
                    "Mottok bare %u byte\r\n", (unsigned)got);
      client.flush();
      delay(5);
      client.stop();
      Serial.printf("Ufullstendig: %u/%d byte\n", (unsigned)got, FB_SIZE);
      return;
    }

    client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nOK\r\n");
    client.flush();
    delay(5);
    client.stop();

    audioImageChime();     // "pling" med en gang bildet er mottatt
    renderFramebuffer();
  } else {
    // Statusside
    client.print("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n");
    client.print("<html><body style='font-family:sans-serif'>");
    client.print("<h2>Fugleramme</h2><p>Klar. POST ");
    client.print(FB_SIZE);
    client.print(" byte til <code>/display</code>.</p><p>IP: ");
    client.print(WiFi.localIP().toString());
    client.print("</body></html>");
    client.flush();
    delay(5);
    client.stop();
  }
}
