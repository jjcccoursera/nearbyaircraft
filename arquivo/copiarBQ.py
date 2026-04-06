import sqlite3
import csv
import os

# File paths
DB_FILE = 'voos.db'
CSV_FILE = 'brutos.csv'

def parse_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def main():
    if not os.path.exists(DB_FILE):
        print(f"❌ Database file '{DB_FILE}' not found.")
        return

    if not os.path.exists(CSV_FILE):
        print(f"❌ CSV file '{CSV_FILE}' not found.")
        return

    # Connect to the SQLite database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Clear the existing table
        print("🧹 Clearing existing records from 'brutos' table...")
        cursor.execute("DELETE FROM brutos")
        conn.commit()

        # Open and read the CSV file
        print("📥 Importing data from CSV...")
        with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows_inserted = 0

            for row in reader:
                cursor.execute("""
                    INSERT INTO brutos (
                        timestamp, call_sign, country, distance, altitude,
                        climbing_rate, latitude, longitude, velocidade, tipo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['timestamp'],
                    row['call_sign'].strip() if row['call_sign'] else None,
                    row['country'],
                    parse_float(row['distance']),
                    parse_float(row['altitude']),
                    parse_float(row['climbing_rate']),
                    parse_float(row['latitude']),
                    parse_float(row['longitude']),
                    parse_float(row['velocidade']),
                    int(float(row['tipo'])) if row['tipo'] else None
                ))
                rows_inserted += 1

        conn.commit()
        print(f"✅ Successfully imported {rows_inserted} rows into 'brutos'.")

    except Exception as e:
        print(f"⚠️ Error during import: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
