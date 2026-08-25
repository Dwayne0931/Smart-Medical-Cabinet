import os
from datetime import date, timedelta

# for talking to the ESP8266 over WiFi
import urllib.request
import urllib.error

# for MySQL (XAMPP)
import pymysql
import pymysql.cursors

from dotenv import load_dotenv
load_dotenv()  # reads the .env file into environment variables

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable not set. Check your .env file.")

EXPIRY_WARNING_DAYS = 30   # medicines expiring within this many days are flagged
SEARCH_RESULT_LIMIT = 7    # verify page shows at most this many results per search

# ESP8266 network configuration - change this to match your ESP8266's IP address
# Read from .env, but keep the old IP as a safety fallback if the variable is missing
ESP8266_BASE_URL = os.getenv("ESP8266_BASE_URL")
if not ESP8266_BASE_URL:
    raise RuntimeError("ESP8266_BASE_URL environment variable not set. Check your .env file.")

# GLOBAL run for all request - Authenticate session for web access
@app.before_request
def require_login():
    # endpoints public – no login needed
    public_endpoints = ['login', 'register', 'static']

    # If user is not logged in and tries to access a protected endpoint
    if 'username' not in session and request.endpoint not in public_endpoints:
        return redirect(url_for('login'))

# Create and return a connection to the MySQL database
def get_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ---------- AUTH ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # Test the connection to database
        try:
            conn = get_db()
            conn.close()
        except pymysql.Error:
            flash("Database is currently unavailable. Please turn on MySQL Server/contact support.")
    
            
            
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ConfirmPassword = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.")
            return render_template("register.html", form=request.form)
        if password != ConfirmPassword:
            flash("Passwords do not match.")
            return render_template("register.html", form=request.form)
        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return render_template("register.html", form=request.form)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        UserExist = cursor.fetchone()

        if UserExist:
            cursor.close()
            conn.close()
            flash("That username is already taken.")
            return render_template("register.html", form=request.form)
# TODO: change roles/ admin allow register user etc
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'staff')",
            (username, generate_password_hash(password))
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Account created. Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html", form={})


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------

@app.route("/")
def dashboard():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM medicines")
    total_medicines = cursor.fetchone()["c"]

    cursor.execute("""
        SELECT m.medicine_id, m.name, m.dosage, m.low_stock_threshold,
               COALESCE(SUM(b.quantity), 0) AS total_qty
        FROM medicines m
        LEFT JOIN batches b ON m.medicine_id = b.medicine_id
        GROUP BY m.medicine_id
        HAVING total_qty <= m.low_stock_threshold
    """)
    low_stock = cursor.fetchall()

    expiring_cutoff = (date.today() + timedelta(days=EXPIRY_WARNING_DAYS)).isoformat()
    cursor.execute("""
        SELECT b.batch_id, b.expiry_date, b.quantity, m.name, m.dosage, m.medicine_id
        FROM batches b JOIN medicines m ON b.medicine_id = m.medicine_id
        WHERE b.expiry_date <= %s AND b.quantity > 0
        ORDER BY b.expiry_date ASC
    """, (expiring_cutoff,))
    expiring = cursor.fetchall()

    # "remaining" = how much stock is left for that medicine right now,
    # shown next to each transaction so the history makes sense at a glance
    cursor.execute("""
        SELECT t.*, m.name,
               (SELECT COALESCE(SUM(b.quantity), 0)
                FROM batches b
                WHERE b.medicine_id = m.medicine_id) AS remaining
        FROM transactions t
        JOIN medicines m ON t.medicine_id = m.medicine_id
        ORDER BY t.timestamp DESC
        LIMIT 8
    """)
    recent_tx = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("dashboard.html",
                           total_medicines=total_medicines,
                           low_stock=low_stock,
                           expiring=expiring,
                           recent_tx=recent_tx)


# ---------- MEDICINE CRUD ----------

@app.route("/medicines")
def medicines():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, COALESCE(SUM(b.quantity), 0) AS total_qty
        FROM medicines m
        LEFT JOIN batches b ON m.medicine_id = b.medicine_id
        GROUP BY m.medicine_id
        ORDER BY m.name
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("medicines.html", medicines=rows)

# Shared validation for the add/edit medicine forms. Returns (errors, cleaned_values)
def _validate_medicine_fields(f, cursor, medicine_id_to_exclude=None):
    name = f.get("name", "").strip()
    dosage = f.get("dosage", "").strip()
    barcode = f.get("barcode", "").strip()
    category = f.get("category", "").strip()
    location = f.get("location", "").strip()

    errors = []
    if not name or not dosage or not barcode:
        errors.append("Name, dosage, and barcode are required.")

    try:
        threshold = int(f.get("low_stock_threshold") or 20)
        if threshold < 0:
            errors.append("Low stock threshold cannot be negative.")
    except ValueError:
        threshold = None
        errors.append("Low stock threshold must be a whole number.")

# LED index is optional - leave blank if this medicine has no
# physical LED wired up, If it is filled in, it must be a number.
    led_index_raw = f.get("led_index", "").strip()
    if led_index_raw == "":
        led_index = None
    else:
        try:
            led_index = int(led_index_raw)
            if led_index < 0:
                errors.append("LED index cannot be negative.")
        except ValueError:
            led_index = None
            errors.append("LED index must be a whole number (or left blank).")

    if barcode:
        query = "SELECT 1 FROM medicines WHERE barcode = %s"
        params = [barcode]
        if medicine_id_to_exclude:
            query += " AND medicine_id != %s"
            params.append(medicine_id_to_exclude)
        cursor.execute(query, params)
        if cursor.fetchone():
            errors.append(f"Barcode {barcode} is already assigned to another medicine.")

    return errors, {
        "name": name, "dosage": dosage, "barcode": barcode,
        "category": category, "location": location,
        "threshold": threshold, "led_index": led_index
    }


@app.route("/medicines/add", methods=["GET", "POST"])
def add_medicine():
    if request.method == "POST":
        f = request.form
        medicine_id = f.get("medicine_id", "").strip()
        batch_id = f.get("batch_id", "").strip()
        expiry_date_str = f.get("expiry_date", "").strip()

        conn = get_db()
        cursor = conn.cursor()
        errors, values = _validate_medicine_fields(f, cursor)

        if not medicine_id or not batch_id:
            errors.append("Medicine ID and Batch ID are required.")

        try:
            quantity = int(f.get("quantity", ""))
            if quantity < 0:
                errors.append("Quantity cannot be negative.")
        except ValueError:
            quantity = None
            errors.append("Quantity must be a whole number.")

        if not expiry_date_str:
            errors.append("Expiry date is required.")
        else:
            try:
                expiry = date.fromisoformat(expiry_date_str)
                if expiry < date.today():
                    errors.append("Expiry date cannot be in the past.")
            except ValueError:
                errors.append("Expiry date is invalid.")

        if medicine_id:
            cursor.execute("SELECT 1 FROM medicines WHERE medicine_id = %s", (medicine_id,))
            if cursor.fetchone():
                errors.append(f"Medicine ID {medicine_id} already exists.")
        if batch_id:
            cursor.execute("SELECT 1 FROM batches WHERE batch_id = %s", (batch_id,))
            if cursor.fetchone():
                errors.append(f"Batch ID {batch_id} already exists.")

        if errors:
            cursor.close()
            conn.close()
            for e in errors:
                flash(e)
            return render_template("medicine_form.html", form=f)

        cursor.execute(
            "INSERT INTO medicines (medicine_id, name, dosage, category, barcode, location, led_index, low_stock_threshold) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (medicine_id, values["name"], values["dosage"], values["category"],
             values["barcode"], values["location"], values["led_index"], values["threshold"])
        )
        cursor.execute(
            "INSERT INTO batches (batch_id, medicine_id, expiry_date, quantity) VALUES (%s, %s, %s, %s)",
            (batch_id, medicine_id, expiry_date_str, quantity)
        )
        cursor.execute(
            "INSERT INTO transactions (medicine_id, batch_id, change_qty, action, performed_by, note) "
            "VALUES (%s, %s, %s, 'ADD', %s, 'New medicine registered')",
            (medicine_id, batch_id, quantity, session["username"])
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Medicine {values['name']} added.")
        return redirect(url_for("medicines"))
    return render_template("medicine_form.html", form={})


@app.route("/medicines/<medicine_id>/edit", methods=["GET", "POST"])
def edit_medicine(medicine_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medicines WHERE medicine_id = %s", (medicine_id,))
    medicine = cursor.fetchone()

    if not medicine:
        cursor.close()
        conn.close()
        flash("Medicine not found.")
        return redirect(url_for("medicines"))

    if request.method == "POST":
        f = request.form
        errors, values = _validate_medicine_fields(f, cursor, medicine_id_to_exclude=medicine_id)

        if errors:
            cursor.execute("SELECT * FROM batches WHERE medicine_id = %s ORDER BY expiry_date", (medicine_id,))
            batches = cursor.fetchall()
            cursor.close()
            conn.close()
            for e in errors:
                flash(e)
            return render_template("medicine_edit.html", medicine=medicine, form=f, batches=batches)

        cursor.execute("""
            UPDATE medicines
            SET name=%s, dosage=%s, category=%s, barcode=%s, location=%s, led_index=%s, low_stock_threshold=%s
            WHERE medicine_id=%s
        """, (values["name"], values["dosage"], values["category"], values["barcode"],
              values["location"], values["led_index"], values["threshold"], medicine_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Medicine {values['name']} updated.")
        return redirect(url_for("medicines"))

    cursor.execute("SELECT * FROM batches WHERE medicine_id = %s ORDER BY expiry_date", (medicine_id,))
    batches = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("medicine_edit.html", medicine=medicine, form=None, batches=batches)


@app.route("/medicines/<medicine_id>/add_batch", methods=["POST"])
def add_batch(medicine_id):
    f = request.form
    batch_id = f.get("batch_id", "").strip()
    expiry_date_str = f.get("expiry_date", "").strip()

    try:
        quantity = int(f.get("quantity", ""))
    except ValueError:
        quantity = None

    errors = []
    if not batch_id:
        errors.append("Batch ID is required.")
    if quantity is None or quantity < 0:
        errors.append("Quantity must be a non-negative whole number.")
    if not expiry_date_str:
        errors.append("Expiry date is required.")
    else:
        try:
            expiry = date.fromisoformat(expiry_date_str)
            if expiry < date.today():
                errors.append("Expiry date cannot be in the past.")
        except ValueError:
            errors.append("Expiry date is invalid.")

    conn = get_db()
    cursor = conn.cursor()
    if batch_id:
        cursor.execute("SELECT 1 FROM batches WHERE batch_id = %s", (batch_id,))
        if cursor.fetchone():
            errors.append(f"Batch ID {batch_id} already exists.")

    if errors:
        cursor.close()
        conn.close()
        for e in errors:
            flash(e)
        return redirect(url_for("edit_medicine", medicine_id=medicine_id))

    cursor.execute(
        "INSERT INTO batches (batch_id, medicine_id, expiry_date, quantity) VALUES (%s, %s, %s, %s)",
        (batch_id, medicine_id, expiry_date_str, quantity)
    )
    cursor.execute(
        "INSERT INTO transactions (medicine_id, batch_id, change_qty, action, performed_by, note) "
        "VALUES (%s, %s, %s, 'ADD', %s, 'Restock batch added')",
        (medicine_id, batch_id, quantity, session["username"])
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Batch {batch_id} added.")
    return redirect(url_for("edit_medicine", medicine_id=medicine_id))


@app.route("/medicines/<medicine_id>/delete", methods=["POST"])
def delete_medicine(medicine_id):
    conn = get_db()
    cursor = conn.cursor()
    # Transactions and batches both reference medicines via a foreign key.
    # so the medicine's history has to be deleted first, then its batches,
    # and only then the medicine itself.
    cursor.execute("DELETE FROM transactions WHERE medicine_id = %s", (medicine_id,))
    cursor.execute("DELETE FROM batches WHERE medicine_id = %s", (medicine_id,))
    cursor.execute("DELETE FROM medicines WHERE medicine_id = %s", (medicine_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Medicine removed.")
    return redirect(url_for("medicines"))


# ---------- CSV IMPORT (not implemented) ----------

REQUIRED_IMPORT_COLUMNS = [
    "medicine_id", "name", "dosage", "category", "barcode",
    "location", "low_stock_threshold", "batch_id", "expiry_date", "quantity"
]


@app.route("/medicines/import", methods=["GET", "POST"])
def import_medicines():
    if request.method == "POST":
        flash("CSV import is not implemented yet.")
    return render_template("medicine_import.html")


# ---------- SEARCH, LOCATE n BARCODE VERIFICATION ----------

@app.route("/scan")
def scan():
    # Combined search -> select -> locate -> verify flow, plus a Quick Scan mode
    return render_template("scan.html", search_limit=SEARCH_RESULT_LIMIT)


@app.route("/api/medicines/search")
def api_medicines_search():
    q = request.args.get("q", "").strip()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM medicines WHERE name LIKE %s", (f"%{q}%",))
    total = cursor.fetchone()["c"]

    cursor.execute("""
        SELECT m.medicine_id, m.name, m.dosage, m.barcode, m.location,
               COALESCE(SUM(b.quantity), 0) AS total_qty
        FROM medicines m
        LEFT JOIN batches b ON m.medicine_id = b.medicine_id AND b.quantity > 0
        WHERE m.name LIKE %s
        GROUP BY m.medicine_id
        ORDER BY m.name, m.dosage
        LIMIT %s
    """, (f"%{q}%", SEARCH_RESULT_LIMIT))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()
    return jsonify({"results": rows, "total": total, "limit": SEARCH_RESULT_LIMIT})


# ---------- Communication with ESP8266 ------------
# NEED VERIFY Connection and popup if comms fail
@app.route("/api/locate", methods=["POST"])
def api_locate():
# Turns a medicine's LED on or off by sending a request to the ESP8266.
# Which physical LED to use comes from the medicine's led_index in the database 
    data = request.get_json(silent=True) or {}
    medicine_id = str(data.get("medicine_id", "")).strip()
    state = str(data.get("state", "")).lower().strip()

    if not medicine_id:
        return jsonify({"success": False, "message": "Medicine ID is required."}), 400
    if state not in ("on", "off"):
        return jsonify({"success": False, "message": "State must be 'on' or 'off'."}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT medicine_id, name, led_index FROM medicines WHERE medicine_id = %s", (medicine_id,))
    medicine = cursor.fetchone()
    cursor.close()
    conn.close()

    if not medicine:
        return jsonify({"success": False, "message": "Medicine not found."}), 404

    led = medicine["led_index"]

    esp_url = f"{ESP8266_BASE_URL}/led?led={led}&state={state}"

    try:
        with urllib.request.urlopen(esp_url, timeout=3) as response:
            esp_response = response.read().decode("utf-8")
        return jsonify({
            "success": True,
            "medicine_id": medicine_id,
            "led": led,
            "state": state,
            "esp_response": esp_response
        })
    except urllib.error.URLError as e:
        return jsonify({"success": False, "message": f"Could not connect to ESP8266: {e}"}), 502


@app.route("/api/scan", methods=["POST"])
def api_scan():
# Handles the barcode scan receives the code the scanner types 
# and query database
    barcode = request.json.get("barcode", "").strip()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM medicines WHERE barcode = %s", (barcode,))
    medicine = cursor.fetchone()

    if not medicine:
        cursor.close()
        conn.close()
        return jsonify({"found": False, "message": "No medicine matches this barcode."})

    cursor.execute(
        "SELECT * FROM batches WHERE medicine_id = %s AND quantity > 0 ORDER BY expiry_date ASC",
        (medicine["medicine_id"],)
    )
    batches = cursor.fetchall()

    cursor.close()
    conn.close()
    return jsonify({
        "found": True,
        "medicine": medicine,
        "batches": batches,
        "expiry_warning_days": EXPIRY_WARNING_DAYS
    })


@app.route("/api/dispense", methods=["POST"])
def api_dispense():
    data = request.json
    medicine_id = data["medicine_id"]
    batch_id = data["batch_id"]
    qty = int(data["quantity"])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM batches WHERE batch_id = %s", (batch_id,))
    batch = cursor.fetchone()

    if not batch or batch["quantity"] < qty:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Insufficient stock in this batch."})

    cursor.execute("UPDATE batches SET quantity = quantity - %s WHERE batch_id = %s", (qty, batch_id))
    cursor.execute(
        "INSERT INTO transactions (medicine_id, batch_id, change_qty, action, performed_by, note) "
        "VALUES (%s, %s, %s, 'DISPENSE', %s, 'Verified by barcode scan')",
        (medicine_id, batch_id, -qty, session["username"])
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Dispensed {qty} unit(s). Inventory updated."})


def _dispense_fefo(cursor, medicine_id, qty, performed_by, note):
# Dispenses qty units of a medicine using first-expiry-first-out across
# whichever batches have stock, logging one transaction per batch touched
    cursor.execute(
        "SELECT * FROM batches WHERE medicine_id = %s AND quantity > 0 ORDER BY expiry_date ASC",
        (medicine_id,)
    )
    batches = cursor.fetchall()

    total_available = sum(b["quantity"] for b in batches)
    if total_available < qty:
        return False, f"Insufficient stock: requested {qty}, only {total_available} available."

    remaining = qty
    for b in batches:
        if remaining <= 0:
            break
        take = min(b["quantity"], remaining)
        cursor.execute("UPDATE batches SET quantity = quantity - %s WHERE batch_id = %s", (take, b["batch_id"]))
        cursor.execute(
            "INSERT INTO transactions (medicine_id, batch_id, change_qty, action, performed_by, note) "
            "VALUES (%s, %s, %s, 'DISPENSE', %s, %s)",
            (medicine_id, b["batch_id"], -take, performed_by, note)
        )
        remaining -= take
    return True, "OK"


@app.route("/api/bulk_dispense", methods=["POST"])
def api_bulk_dispense():
# Used by Quick Scan: takes a list of {medicine_id, quantity} from
# repeated scans and updates the database for all of them in one confirmation
    items = request.json.get("items", [])
    conn = get_db()
    cursor = conn.cursor()
    results = []

    for item in items:
        med_id = item.get("medicine_id")
        try:
            qty = int(item.get("quantity", 0))
        except (ValueError, TypeError):
            qty = 0

        cursor.execute("SELECT name, dosage FROM medicines WHERE medicine_id = %s", (med_id,))
        medicine = cursor.fetchone()

        if not medicine:
            results.append({"medicine_id": med_id, "success": False, "message": "Medicine not found."})
            continue
        if qty <= 0:
            results.append({"medicine_id": med_id, "name": medicine["name"], "dosage": medicine["dosage"],
                             "success": False, "message": "Invalid quantity."})
            continue

        ok, msg = _dispense_fefo(cursor, med_id, qty, session["username"], "Confirmed via Quick Scan")
        results.append({"medicine_id": med_id, "name": medicine["name"], "dosage": medicine["dosage"],
                         "success": ok, "message": msg})

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"results": results})


# ---------- REPORTS ----------

@app.route("/reports")
def reports():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.name, m.dosage, m.location, b.batch_id, b.expiry_date, b.quantity
        FROM batches b JOIN medicines m ON b.medicine_id = m.medicine_id
        WHERE b.quantity > 0
        ORDER BY m.name, b.expiry_date
    """)
    inventory = cursor.fetchall()

    cursor.execute("""
        SELECT t.timestamp, m.name, t.change_qty, t.action, t.performed_by, t.note,
               (SELECT COALESCE(SUM(b.quantity), 0)
                FROM batches b
                WHERE b.medicine_id = m.medicine_id) AS remaining
        FROM transactions t
        JOIN medicines m ON t.medicine_id = m.medicine_id
        ORDER BY t.timestamp DESC
    """)
    history = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("reports.html", inventory=inventory, history=history)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
