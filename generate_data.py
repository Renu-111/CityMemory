"""Simulated Bengaluru civic complaint data for CityMemory.

~250 complaints across ~85 civic assets (roads, drains, streetlights, footpaths).
15 assets are deliberately "chronic": patched again and again over ~14 months.
DATA IS SIMULATED - say this openly in your pitch. A real BBMP / Sahaaya complaint
export plugs into the same `complaints` table.
"""
import math
import os
import random
import sqlite3
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "citymemory.db")

SPOTS = {
    "Silk Board Junction": (12.9172, 77.6228),
    "Hebbal Flyover": (13.0358, 77.5970),
    "KR Puram Bridge": (13.0012, 77.6963),
    "Marathahalli Bridge": (12.9569, 77.7011),
    "Bellandur Gate": (12.9304, 77.6784),
    "Madiwala Market": (12.9226, 77.6174),
    "Electronic City Phase 1": (12.8452, 77.6602),
    "Whitefield Main Road": (12.9698, 77.7500),
    "Jayanagar 4th Block": (12.9250, 77.5938),
    "Indiranagar 100ft Road": (12.9784, 77.6408),
    "Koramangala 80ft Road": (12.9352, 77.6245),
    "Majestic Bus Stand": (12.9767, 77.5713),
    "Yeshwanthpur Circle": (13.0285, 77.5409),
    "Malleshwaram 8th Cross": (13.0035, 77.5710),
    "BTM 2nd Stage": (12.9166, 77.6101),
    "HSR Layout Sector 2": (12.9116, 77.6389),
    "Banashankari Temple Road": (12.9255, 77.5468),
    "Rajajinagar Entrance": (12.9910, 77.5520),
    "Peenya Industrial Area": (13.0285, 77.5197),
    "Domlur Flyover": (12.9609, 77.6387),
}

TEXTS = {
    "pothole": [
        "Big pothole near {s}",
        "Road broken at {s}, two-wheelers skidding",
        "Pothole is back at {s} after the last repair",
        "Deep crater on the road close to {s}",
        "Asphalt patch came off near {s}",
        "Road surface damaged near {s}, water collects in it",
    ],
    "drainage": [
        "Drain overflowing near {s}",
        "Stormwater drain blocked at {s}",
        "Sewage water on road near {s}",
        "Water logging at {s} after light rain",
        "Drain cover missing at {s}",
    ],
    "streetlight": [
        "Streetlight not working near {s}",
        "Street lamp dark at {s}, unsafe at night",
        "Lights out on the stretch near {s}",
        "Streetlight flickering at {s}",
    ],
    "footpath": [
        "Footpath slab broken near {s}",
        "Pedestrians forced onto road at {s}, footpath damaged",
        "Uneven footpath at {s}",
        "Footpath tiles missing near {s}",
    ],
}

ACTIONS = {
    "pothole": ["Temporary asphalt patch", "Cold mix filled", "Pothole patched with gravel"],
    "drainage": ["Silt removed (manual desilting)", "Drain cleaned, no repair", "Cover replaced with cheap slab"],
    "streetlight": ["Bulb replaced", "Fuse replaced", "Loose wiring taped"],
    "footpath": ["Slab re-laid on loose fill", "Broken tiles patched", "Cement filler applied"],
}

COST = {  # rupees per temporary repair (min, max)
    "pothole": (8000, 15000),
    "drainage": (12000, 25000),
    "streetlight": (2000, 5000),
    "footpath": (6000, 12000),
}

START = date(2025, 9, 1)
END = date(2026, 10, 28)


def _dist_m(a, b):
    dlat = (a[0] - b[0]) * 111000
    dlon = (a[1] - b[1]) * 111000 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def _place_assets(rng, n_assets):
    assets = []
    names = list(SPOTS)
    tries = 0
    while len(assets) < n_assets and tries < 5000:
        tries += 1
        spot = rng.choice(names)
        lat0, lon0 = SPOTS[spot]
        lat = lat0 + rng.uniform(-0.003, 0.003)
        lon = lon0 + rng.uniform(-0.003, 0.003)
        cat = rng.choice(list(TEXTS))
        if any(a["cat"] == cat and _dist_m((lat, lon), (a["lat"], a["lon"])) < 90 for a in assets):
            continue
        assets.append({"spot": spot, "lat": lat, "lon": lon, "cat": cat})
    return assets


def _dates_for(rng, chronic):
    if chronic:
        d = START + timedelta(days=rng.randint(0, 80))
        out = [d]
        gap = rng.randint(55, 75)
        n = rng.randint(6, 9)
        while len(out) < n:
            d = d + timedelta(days=gap)
            if d > END:
                break
            out.append(d)
            gap = max(18, int(gap * rng.uniform(0.72, 0.92)))  # failures come faster
        return out
    n = rng.choice([1, 1, 1, 2, 2, 3])
    return sorted(START + timedelta(days=rng.randint(0, (END - START).days)) for _ in range(n))


def generate(db_path=DB_PATH, seed=42):
    rng = random.Random(seed)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.execute(
        """CREATE TABLE complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, text TEXT, lat REAL, lon REAL,
            reported_on TEXT, severity INTEGER, status TEXT,
            repair_action TEXT, repair_cost INTEGER, repaired_on TEXT,
            photo_path TEXT)"""
    )
    assets = _place_assets(rng, 85)
    chronic_idx = set(rng.sample(range(len(assets)), 15))
    rows = []
    for i, a in enumerate(assets):
        chronic = i in chronic_idx
        dates = _dates_for(rng, chronic)
        for k, d in enumerate(dates):
            lat = a["lat"] + rng.uniform(-0.00012, 0.00012)  # ~13 m GPS jitter
            lon = a["lon"] + rng.uniform(-0.00012, 0.00012)
            text = rng.choice(TEXTS[a["cat"]]).format(s=a["spot"])
            if chronic and k >= 2 and rng.random() < 0.5:
                text += " (again!)"
            base = rng.randint(2, 3) if not chronic else min(5, 2 + k // 2)
            sev = max(1, min(5, base + rng.choice([0, 0, 1])))
            last = k == len(dates) - 1
            open_now = last and rng.random() < (0.7 if chronic else 0.3)
            lo, hi = COST[a["cat"]]
            if open_now:
                status, action, cost, rep = "Open", None, None, None
            else:
                status = "Repaired (temporary)"
                action = rng.choice(ACTIONS[a["cat"]])
                cost = int(round(rng.randint(lo, hi), -2))
                rep = (d + timedelta(days=rng.randint(3, 14))).isoformat()
            rows.append((a["cat"], text, lat, lon, d.isoformat(), sev, status, action, cost, rep))
    rows.sort(key=lambda r: r[4])
    con.executemany(
        """INSERT INTO complaints
        (category,text,lat,lon,reported_on,severity,status,repair_action,repair_cost,repaired_on)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    con.commit()
    con.close()
    return len(rows)


if __name__ == "__main__":
    print("Generated", generate(), "complaints ->", DB_PATH)
