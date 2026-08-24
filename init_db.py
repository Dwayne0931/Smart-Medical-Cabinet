import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

load_dotenv()  # reads DB_HOST, DB_USER, etc. from the .env file

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "smart_medicine"),
}


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Remove existing tables so the database can be recreated cleanly.
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    cursor.execute("DROP TABLE IF EXISTS transactions")
    cursor.execute("DROP TABLE IF EXISTS batches")
    cursor.execute("DROP TABLE IF EXISTS medicines")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    # ---------------------------------------------------------
    # Users table
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'staff'
        ) ENGINE=InnoDB CHARACTER SET utf8mb4
    """)

    # ---------------------------------------------------------
    # Medicines table
    # led_index is which physical LED lights up for this medicine.
    # It is NULL for medicines that don't have a real LED wired up yet
    # (right now only 3 LEDs are actually connected to the ESP8266/Arduino).
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE medicines (
            medicine_id VARCHAR(20) PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            dosage VARCHAR(50) NOT NULL,
            category VARCHAR(100),
            barcode VARCHAR(100) UNIQUE NOT NULL,
            location VARCHAR(150),
            led_index INT NULL,
            low_stock_threshold INT DEFAULT 20
        ) ENGINE=InnoDB CHARACTER SET utf8mb4
    """)

    # ---------------------------------------------------------
    # Batches table
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE batches (
            batch_id VARCHAR(50) PRIMARY KEY,
            medicine_id VARCHAR(20) NOT NULL,
            expiry_date DATE NOT NULL,
            quantity INT NOT NULL DEFAULT 0,
            FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
        ) ENGINE=InnoDB CHARACTER SET utf8mb4
    """)

    # ---------------------------------------------------------
    # Transactions table
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id VARCHAR(20) NOT NULL,
            batch_id VARCHAR(50),
            change_qty INT NOT NULL,
            action VARCHAR(30) NOT NULL,
            performed_by VARCHAR(100),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
        ) ENGINE=InnoDB CHARACTER SET utf8mb4
    """)

    # ---------------------------------------------------------
    # Demo staff account
    # ---------------------------------------------------------
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        ("staff1", generate_password_hash("password123"), "staff")
    )

    # ---------------------------------------------------------
    # First five medicines
    # Column order: medicine_id, name, dosage, category, barcode,
    #               location, led_index, low_stock_threshold
    #
    # Only M001, M002 and M003 get a real led_index (1, 2, 3), because
    # only 3 LEDs are physically wired up right now. The rest are NULL,
    # which api_locate() treats as "no hardware for this one yet".
    # ---------------------------------------------------------
    medicines = [
        ("M001", "Paracetamol", "500mg", "Pain Relief", "8991234500017", "Pain Relief Cabinet A2", 1, 30),
        ("M002", "Metformin", "500mg", "Diabetes", "8991234500024", "Chronic Meds B1", 2, 20),
        ("M003", "Metformin", "850mg", "Diabetes", "8991234500031", "Chronic Meds B1", 3, 20),
        ("M004", "Metformin", "1000mg", "Diabetes", "8991234500048", "Chronic Meds B1", None, 20),
        ("M005", "Amoxicillin", "250mg", "Antibiotic", "8991234500055", "Antibiotics C3", None, 15),
    ]

    # ---------------------------------------------------------
    # Additional dummy medicines (name, dosage, category only - the rest
    # is generated in the loop below)
    # ---------------------------------------------------------
    more_medicines = [
        ("Ibuprofen", "200mg", "Pain Relief"),
        ("Aspirin", "300mg", "Pain Relief"),
        ("Azithromycin", "500mg", "Antibiotic"),
        ("Ciprofloxacin", "500mg", "Antibiotic"),
        ("Doxycycline", "100mg", "Antibiotic"),
        ("Cephalexin", "500mg", "Antibiotic"),
        ("Lisinopril", "10mg", "Hypertension"),
        ("Amlodipine", "5mg", "Hypertension"),
        ("Losartan", "50mg", "Hypertension"),
        ("Atorvastatin", "20mg", "Cholesterol"),
        ("Simvastatin", "20mg", "Cholesterol"),
        ("Metoprolol", "50mg", "Cardiac"),
        ("Omeprazole", "20mg", "Gastrointestinal"),
        ("Ranitidine", "150mg", "Gastrointestinal"),
        ("Loperamide", "2mg", "Gastrointestinal"),
        ("Cetirizine", "10mg", "Allergy"),
        ("Loratadine", "10mg", "Allergy"),
        ("Diphenhydramine", "25mg", "Allergy"),
        ("Salbutamol", "100mcg", "Respiratory"),
        ("Montelukast", "10mg", "Respiratory"),
        ("Prednisone", "5mg", "Respiratory"),
        ("Levothyroxine", "50mcg", "Thyroid"),
        ("Insulin Glargine", "100u/ml", "Diabetes"),
        ("Gliclazide", "80mg", "Diabetes"),
        ("Warfarin", "5mg", "Cardiac"),
        ("Clopidogrel", "75mg", "Cardiac"),
        ("Furosemide", "40mg", "Cardiac"),
        ("Hydrochlorothiazide", "25mg", "Hypertension"),
        ("Spironolactone", "25mg", "Cardiac"),
        ("Vitamin C", "500mg", "Vitamins"),
        ("Vitamin D3", "1000IU", "Vitamins"),
        ("Multivitamin", "1 tablet", "Vitamins"),
        ("Folic Acid", "5mg", "Vitamins"),
        ("Ferrous Sulfate", "200mg", "Vitamins"),
        ("Calcium Carbonate", "500mg", "Vitamins"),
        ("Zinc Sulfate", "220mg", "Vitamins"),
        ("Fluconazole", "150mg", "Antifungal"),
        ("Acyclovir", "400mg", "Antiviral"),
        ("Metronidazole", "400mg", "Antibiotic"),
        ("Clindamycin", "300mg", "Antibiotic"),
        ("Erythromycin", "250mg", "Antibiotic"),
        ("Naproxen", "250mg", "Pain Relief"),
        ("Diclofenac", "50mg", "Pain Relief"),
        ("Tramadol", "50mg", "Pain Relief"),
        ("Codeine Phosphate", "30mg", "Pain Relief"),
    ]

    # ---------------------------------------------------------
    # Storage location for each category
    # ---------------------------------------------------------
    category_location = {
        "Pain Relief": "Pain Relief Cabinet A2",
        "Diabetes": "Chronic Meds B1",
        "Antibiotic": "Antibiotics C3",
        "Hypertension": "Cardiac Cabinet D1",
        "Cholesterol": "Cardiac Cabinet D1",
        "Cardiac": "Cardiac Cabinet D1",
        "Gastrointestinal": "GI Cabinet E1",
        "Allergy": "Allergy Cabinet F1",
        "Respiratory": "Respiratory Cabinet G1",
        "Thyroid": "Endocrine Cabinet H1",
        "Vitamins": "Vitamins Shelf I1",
        "Antifungal": "Antimicrobials C4",
        "Antiviral": "Antimicrobials C4",
    }

    today = date.today()

    # ---------------------------------------------------------
    # Initial batches
    # ---------------------------------------------------------
    batches = [
        ("PCM001", "M001", today + timedelta(days=200), 100),
        ("PCM002", "M001", today + timedelta(days=15), 40),      # expiring soon
        ("MET500-01", "M002", today + timedelta(days=300), 60),
        ("MET850-01", "M003", today + timedelta(days=10), 12),   # expiring + low stock
        ("MET1000-01", "M004", today + timedelta(days=400), 8),  # low stock
        ("AMX250-01", "M005", today + timedelta(days=250), 50),
    ]

    # ---------------------------------------------------------
    # Generate the remaining 45 medicines and batches.
    # None of these get a led_index - only the first 3 medicines above
    # have a physical LED wired up right now.
    # ---------------------------------------------------------
    for i, (name, dosage, category) in enumerate(more_medicines):
        number = i + 6
        medicine_id = f"M{number:03d}"
        barcode = f"9000000{number:04d}"
        location = category_location.get(category, "General Storage")

        medicines.append((medicine_id, name, dosage, category, barcode, location, None, 20))

        # Every 6th medicine is set up as low stock, every 8th as expiring
        # soon, so the dashboard has something to show for the demo.
        if number % 6 == 0:
            quantity = 5
        else:
            quantity = 40 + (number * 3) % 60

        if number % 8 == 0:
            expiry_days = 20
        else:
            expiry_days = 180 + (number * 5) % 400

        batch_id = f"B{number:03d}-01"
        batches.append((batch_id, medicine_id, today + timedelta(days=expiry_days), quantity))

    # ---------------------------------------------------------
    # Insert medicines and batches
    # ---------------------------------------------------------
    cursor.executemany(
        """
        INSERT INTO medicines
            (medicine_id, name, dosage, category, barcode, location, led_index, low_stock_threshold)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        medicines
    )

    cursor.executemany(
        "INSERT INTO batches (batch_id, medicine_id, expiry_date, quantity) VALUES (%s, %s, %s, %s)",
        batches
    )

    # ---------------------------------------------------------
    # Log an "ADD" transaction for every batch, so Reports has a
    # full history from day one instead of starting empty.
    # ---------------------------------------------------------
    initial_transactions = [
        (batch[1], batch[0], batch[3], "ADD", "system", "Initial stock")
        for batch in batches
    ]
    cursor.executemany(
        """
        INSERT INTO transactions (medicine_id, batch_id, change_qty, action, performed_by, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        initial_transactions
    )

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Database initialized: {len(medicines)} medicines, {len(batches)} batches")


if __name__ == "__main__":
    init_db()
