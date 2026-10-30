
import csv
from pathlib import Path
import requests

# CityMemory project folder
BASE_DIR = Path(__file__).resolve().parent

# Folder where downloaded datasets will be stored
DATA_DIR = BASE_DIR / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Consolidated BBMP 2025-26 work orders (243 wards)
URL = (
    "https://data.opencity.in/dataset/"
    "280a1196-074e-43ac-acd9-914918b429f5/resource/"
    "6c2e5dfa-845c-440d-808c-3ed45b083059/download/"
    "bbmp-2025-26-243-wards-work-orders.csv"
)

FILE_PATH = DATA_DIR / "bbmp_2025_26_243_wards.csv"


def download_and_inspect():
    print("Downloading BBMP work orders...")

    try:
        response = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=120
        )
        response.raise_for_status()

        # Save downloaded CSV
        FILE_PATH.write_bytes(response.content)

        # Check that the response is actually a CSV
        with FILE_PATH.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline=""
        ) as file:
            reader = csv.DictReader(file)

            columns = reader.fieldnames

            if not columns:
                raise ValueError("CSV does not contain column headers.")

            print("\nCSV downloaded successfully!")
            print("\nCOLUMNS:")
            for column in columns:
                print("-", column)

            print("\nFIRST 3 RECORDS:")
            count = 0
            total = 0

            for row in reader:
                total += 1

                if count < 3:
                    print(row)
                    count += 1

        print("\nTOTAL RECORDS:", total)
        print("SAVED AT:", FILE_PATH)

    except requests.exceptions.RequestException as error:
        print("Download failed:", error)

    except (OSError, ValueError, csv.Error) as error:
        print("File inspection failed:", error)

if __name__ == "__main__":
    download_and_inspect()
