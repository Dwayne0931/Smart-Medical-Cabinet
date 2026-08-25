# Smart Medical Cabinet
a web app for clinic staff to look up medicines, verify them
by barcode before dispensing, and keep track of stock (quantities, expiry dates, batches).
An ESP8266 + Arduino Uno light up a physical LED to help staff find the right medicine.

From, <br>
DWAYNE PAN KAY YOUNG - 18DIT24F1998 (SYSTEM) <br>
PRAVIN A/L LINGESWARAN - 18DIT24F1041 (DEVICE) <br>
PREETHIBA A/P NARAYANAN - 18DIT24F1061 (DOCUMENTATION) <br>

## 1. Project overview

Staff log in, search for a medicine, and can either:
- **Guided Verification** - tick the medicine + dose needed, use "Locate" to light up its
  compartment, then scan its barcode to confirm it's the right one before dispensing.
- **Quick Scan** - scan items one after another with a barcode scanner plugged into the
  computer, review the list, then submit everything at once.

Every stock change (adding new stock, dispensing) is logged, and the dashboard shows
low-stock and expiring-soon warnings.

## 2. Main features

- Staff login and registration
- Dashboard with low-stock and expiry alerts
- Add / edit / delete medicines, with batch tracking (expiry date + quantity per batch)
- Restocking (add a new batch to an existing medicine)
- Barcode verification (Guided Verification and Quick Scan)
- FEFO dispensing (First-Expiry-First-Out - stock is taken from whichever batch expires soonest, and can span multiple batches if one runs out)
- Stock movement reports
- LED locate feature - the medicine's `led_index` in the database tells the ESP8266 which
  physical LED to light up

## 3. Technologies used

- Python + Flask
- MySQL (via XAMPP) + PyMySQL
- HTML, CSS, JavaScript 
- ESP8266 + Arduino Uno (Arduino C++) for the LED hardware


## 4. Create the MySQL database

In phpMyAdmin, create `smart_medicine` as the database name
tables - `init_db.py` does that for you 


## 5. Configure .env

Copy `.env.example` to `.env`:

Open `.env` and set a `SECRET_KEY` any random string works.
The default XAMPP MySQL settings (root user, no password) already match the other values,
so you usually don't need to change `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, or
`DB_NAME` unless your setup is different.

## 6. Initialise the database

With MySQL running in XAMPP:

```
python init_db.py
```

This creates the `users`, `medicines`, `batches`, and `transactions` tables and fills
them with 50 demo medicines, a demo staff account (`staff1` / `password123`), and some
starter stock. Re-running this script wipes and recreates everything - handy if the demo
data gets messy while testing.

## 7. Run the Flask application

```
python app.py
```

## 8. Access the application

Open `http://localhost:5000` in your browser. Log in with `staff1` / `password123`,
or register a new account.

## 9. How the ESP8266/Arduino component works

Two boards work together:

- **ESP8266**: connects to WiFi and runs a tiny web server. When Flask sends a request
  like `http://<esp-ip>/led?led=1&state=on`, it forwards a short text command
  (e.g. `LED1_ON`) to the Arduino Uno over a serial (UART) wire.
- **Arduino Uno**: has no WiFi, just waits for those text commands and turns the matching
  LED on or off with `digitalWrite`.

They're split across two boards because the ESP8266 has very few free GPIO pins for
driving LEDs directly, while the Arduino Uno has plenty of GPIO pins but no WiFi.

# 20/08/2026
Only **3 LEDs** are physically wired up right now for testing. 

After flashing the ESP8266:
1. Open the Serial Monitor for the ESP8266 to see its IP address once it connects.
2. Put that IP address into `ESP8266_BASE_URL` near the top of `app.py`.
