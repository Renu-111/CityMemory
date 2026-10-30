
import csv
import sqlite3
from pathlib import Path

import requests
import generate_data
from import_workorders import import_work_orders

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(generate_data.DB_PATH)

API_URL = "https://data.opencity.in/api/3/action/package_show"

PACKAGE_ID = "280a1196-074e-43ac-acd9-914918b429f5"

RESOURCE_ID = "6c2e5dfa-845c-440d-808c-3ed45b083059"

CSV_PATH = BASE_DIR / "data" / "raw" / "bbmp_2025_26_243_wards.csv"

REQUIRED_COLUMNS = {
    "id", "ward", "wodetails",
    "brnumber", "amount", "nett", "deduction"
}


def get_existing_count():
    with sqlite3.connect(DB_PATH) as con:
        result = con.execute(
            "SELECT COUNT(*) FROM bbmp_work_orders"
        ).fetchone()
        return result[0]


def sync_workorders():

    print("Connecting to OpenCity...")

    # 1. Discover the latest download URL for this resource.
    response = requests.get(
        API_URL,
        params={"id": PACKAGE_ID},
        timeout=30
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError("OpenCity API returned an unsuccessful response.")

    resources = data["result"]["resources"]

    resource = next(
        (r for r in resources if r.get("id") == RESOURCE_ID),
        None
    )

    if not resource or not resource.get("url"):
        raise RuntimeError("BBMP work-order download resource not found.")

    download_url = resource["url"]

    print("Downloading:", resource.get("name"))

    # 2. Download the CSV.
    download = requests.get(
        download_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=120
    )
    download.raise_for_status()

    # 3. Validate the CSV before replacing the existing file.
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = CSV_PATH.with_name(CSV_PATH.name + ".tmp")
    temp_path.write_bytes(download.content)

    try:
        with temp_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            columns = set(reader.fieldnames or [])

            if not REQUIRED_COLUMNS.issubset(columns):
                raise ValueError(
                    "Downloaded CSV has unexpected columns: "
                    + str(reader.fieldnames)
                )

            downloaded_rows = sum(1 for _ in reader)

            if downloaded_rows == 0:
                raise ValueError("Downloaded CSV contains no records.")

        # Replace old CSV only after validation succeeds.
        temp_path.replace(CSV_PATH)

    finally:
        if temp_path.exists():
            temp_path.unlink()

    print("Downloaded records:", downloaded_rows)

    # 4. Import into the separate BBMP table.
    before = get_existing_count()

    import_work_orders()

    after = get_existing_count()

    result = {
        "downloaded_records": downloaded_rows,
        "new_records": after - before,
        "total_records": after
    }

    print("\n========== SYNC RESULT ==========")
    print("Downloaded:", result["downloaded_records"])
    print("New records:", result["new_records"])
    print("Total in database:", result["total_records"])

    return result


if __name__ == "__main__":
    try:
        sync_workorders()
    except Exception as error:
        print("SYNC FAILED:", error)
        raise SystemExit(1)
