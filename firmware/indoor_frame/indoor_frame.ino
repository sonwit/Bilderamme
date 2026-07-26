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
 * WiFi-innstillinger ligger i config.h (kopier config.example.h -> config.h).
 */

#include <WiFi.h>
#include <ESPmDNS.h>
#include "config.h"
#include "EPD_13in3e.h"
#include "audio.h"

// Framebuffer: 600 byte/rad * 1600 rader = 960000 byte (2 piksler per byte)
#define FB_SIZE  ((EPD_13IN3E_WIDTH / 2) * EPD_13IN3E_HEIGHT)

WiFiServer server(80);
uint8_t   *framebuffer = nullptr;

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
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
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
        delay(1);
      }
    }

    if (got != FB_SIZE) {
      client.printf("HTTP/1.1 500 Internal Error\r\nConnection: close\r\n\r\n"
                    "Mottok bare %u byte\r\n", (unsigned)got);
      client.stop();
      Serial.printf("Ufullstendig: %u/%d byte\n", (unsigned)got, FB_SIZE);
      return;
    }

    client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nOK\r\n");
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
    client.stop();
  }
}
