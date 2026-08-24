// ============================================================
// ESP8266 - WiFi bridge for the Smart Medicinal Cabinet
//
// What this board does:
//   1. Connects to WiFi.
//   2. Runs a small web server that listens for requests like:
//        http://<esp-ip>/led?led=1&state=on
//   3. When it gets a request like that, it forwards a short text
//      command ("LED1_ON") to the Arduino Uno over the serial (TX RX)
//      wire. The Arduino Uno is the one that actually turns the LED
//      on or off - this board is just relaying the message over WiFi.
//
// Why two boards instead of one?
//   The ESP8266 does WiFi but only has a couple of usable GPIO pins,
//   so it can't handle many LEDs. The Arduino Uno has plenty
//   of GPIO pins but no WiFi. Splitting the job between them is the
//   simplest way to get both WiFi control and enough LED pins.
// ============================================================

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

#define WIFI_SSID "networkname"
#define WIFI_PASSWORD "wifipassword"


ESP8266WebServer server(80);

// Handles GET /led?led=1&state=on
void handleLed() {
    if (!server.hasArg("led") || !server.hasArg("state")) {
        server.send(400, "text/plain", "Missing led or state");
        return;
    }

    int led = server.arg("led").toInt();
    String state = server.arg("state");
    state.toUpperCase();

    // Builds command "LED1_ON" and sends it to the Arduino Uno
    String command = "LED" + String(led) + "_" + state;
    Serial.println(command);

    server.send(200, "text/plain", command);
}

void handleRoot() {
    server.send(200, "text/plain", "Smart Medical Cabinet ESP8266");
}

void setup() {
    // This Serial connection goes to the Arduino Uno
    Serial.begin(9600);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        Serial.println("Connecting to WiFi");
        delay(500);
    }

    Serial.println();
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());  // check this in the Serial Monitor,
                                       // then put it in ESP8266_BASE_URL in app.py

    server.on("/led", HTTP_GET, handleLed);
    server.begin();

    Serial.println("HTTP server started");
}

void loop() {
    server.handleClient();
}
