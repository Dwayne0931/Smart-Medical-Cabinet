// ============================================================
// Arduino Uno -
// This board doesn't know anything about WiFi or the web. It just
// waits for a short text command over the serial (TX RX) connection
// from the ESP8266 (e.g. "LED1_ON") and turns the matching LED on
// or off. All the network/WiFi handling happens on the ESP8266 side.
// For testing, only 3 led have been attached
// ============================================================

const int LED1 = 3;
const int LED2 = 4;
const int LED3 = 5;

void setup() {
    pinMode(LED1, OUTPUT);
    pinMode(LED2, OUTPUT);
    pinMode(LED3, OUTPUT);

    // This Serial connection is wired to the ESP8266, not to a computer.
    Serial.begin(9600);
}

void loop() {
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();

        if (command == "LED1_ON") {
            digitalWrite(LED1, HIGH);
        }
        else if (command == "LED1_OFF") {
            digitalWrite(LED1, LOW);
        }
        else if (command == "LED2_ON") {
            digitalWrite(LED2, HIGH);
        }
        else if (command == "LED2_OFF") {
            digitalWrite(LED2, LOW);
        }
        else if (command == "LED3_ON") {
            digitalWrite(LED3, HIGH);
        }
        else if (command == "LED3_OFF") {
            digitalWrite(LED3, LOW);
        }
        // change to switch case later 
    }
}
