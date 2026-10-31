import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

import generate_data

BASE_DIR = Path(__file__).resolve().parent


def get_db_path():
    return Path(generate_data.get_db_path())


DB_PATH = get_db_path()


def get_csv_path():
    custom = os.environ.get("BBMP_CSV_PATH")
    if custom:
        return Path(custom)
    default_csv = BASE_DIR / "data" / "raw" / "bbmp_2025_26_243_wards.csv"
    if default_csv.exists():
        return default_csv
    is_serverless = bool(
        os.environ.get("VERCEL")
        or os.environ.get("VERCEL_ENV")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    )
    if is_serverless or not os.access(str(BASE_DIR), os.W_OK):
        tmp_dir = Path(tempfile.gettempdir()) / "citymemory_data"
        return tmp_dir / "bbmp_2025_26_243_wards.csv"
    return default_csv


CSV_PATH = get_csv_path()

SOURCE_DATASET = "BBMP Work Orders 2025-26 - 243 Wards"
SOURCE_RESOURCE_ID = "6c2e5dfa-845c-440d-808c-3ed45b083059"


def clean_description(value):
    """Remove HTML tags and normalize whitespace."""
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_amount(value):
    """Convert an amount into a number."""
    value = (value or "").strip()

    if not value:
        return None

    value = value.replace(",", "").replace("₹", "").strip()

    try:
        return float(value)
    except ValueError:
        return None


def create_table(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS bbmp_work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_dataset TEXT NOT NULL,
            source_resource_id TEXT NOT NULL,
            source_record_key TEXT NOT NULL UNIQUE,
            work_order_id TEXT,
            ward TEXT,
            work_description TEXT,
            bill_reference TEXT,
            amount REAL,
            net_amount REAL,
            deduction REAL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def import_work_orders(csv_path=None, db_path=None):
    if csv_path is None:
        csv_path = get_csv_path()
    else:
        csv_path = Path(csv_path)

    if db_path is None:
        db_path = get_db_path()
    else:
        db_path = Path(db_path)

    if not csv_path.exists():
        print("CSV file not found:", csv_path)
        return

    if not db_path.exists():
        print("CityMemory database not found. Initializing schema:", db_path)
        generate_data.generate(db_path=str(db_path))

    # Make a separate backup before modifying the database if possible.
    try:
        backup_path = db_path.with_name("citymemory_pre_bbmp_import.db")
        if not backup_path.exists() and db_path.exists():
            shutil.copy2(db_path, backup_path)
            print("Database backup created:", backup_path)
    except Exception as e:
        print(f"Notice: Pre-import backup skipped: {e}")

    inserted = 0
    skipped = 0
    total = 0

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        required = {
            "id", "ward", "wodetails",
            "brnumber", "amount", "nett", "deduction"
        }

        if not required.issubset(set(reader.fieldnames or [])):
            print("CSV columns do not match the expected format.")
            print("Found:", reader.fieldnames)
            return

        with sqlite3.connect(db_path) as connection:

            create_table(connection)

            for row in reader:
                total += 1

                work_order_id = (row.get("id") or "").strip()
                ward = (row.get("ward") or "").strip()

                description = clean_description(
                    row.get("wodetails")
                )

                bill_reference = clean_description(
                    row.get("brnumber")
                )

                amount = clean_amount(row.get("amount"))
                net_amount = clean_amount(row.get("nett"))
                deduction = clean_amount(row.get("deduction"))

                # Ignore completely empty records.
                if not work_order_id and not description:
                    skipped += 1
                    continue

                # Build a stable key to avoid importing the same
                # source record again when Sync is run repeatedly.
                record_data = {
                    "resource": SOURCE_RESOURCE_ID,
                    "work_order_id": work_order_id,
                    "ward": ward,
                    "description": description,
                    "bill_reference": bill_reference,
                    "amount": amount,
                    "net_amount": net_amount,
                    "deduction": deduction
                }

                record_string = json.dumps(
                    record_data,
                    sort_keys=True,
                    ensure_ascii=False
                )

                record_key = hashlib.sha256(
                    record_string.encode("utf-8")
                ).hexdigest()

                cursor = connection.execute("""
                    INSERT OR IGNORE INTO bbmp_work_orders (
                        source_dataset,
                        source_resource_id,
                        source_record_key,
                        work_order_id,
                        ward,
                        work_description,
                        bill_reference,
                        amount,
                        net_amount,
                        deduction
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    SOURCE_DATASET,
                    SOURCE_RESOURCE_ID,
                    record_key,
                    work_order_id,
                    ward,
                    description,
                    bill_reference,
                    amount,
                    net_amount,
                    deduction
                ))

                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1

            connection.commit()

            total_in_database = connection.execute(
                "SELECT COUNT(*) FROM bbmp_work_orders"
            ).fetchone()[0]

    print("\n========== IMPORT SUMMARY ==========")
    print("CSV records processed:", total)
    print("New records inserted:", inserted)
    print("Records skipped:", skipped)
    print("Total BBMP work orders in database:", total_in_database)
    print("Database:", db_path)
    print("Completed at:", datetime.now().strftime("%d-%m-%Y %H:%M:%S"))


if __name__ == "__main__":
    import_work_orders()
