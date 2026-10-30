"""CityMemory core intelligence.

1. Geo-clustering (DBSCAN, haversine) groups complaints that hit the same physical asset.
2. Text similarity (TF-IDF by default, sentence embeddings if enabled) matches NEW complaints
   to existing assets, so "road broken at Silk Board bus stand" links to its history.
3. Priority score + wasted-money maths turn history into an action list.
"""
import math
import os
import sqlite3
from datetime import date

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

EARTH_R = 6371000.0
CLUSTER_RADIUS_M = 40.0
MATCH_RADIUS_M = 70.0

# Set USE_EMBEDDINGS=1 (and `pip install sentence-transformers`) for real semantic embeddings.
_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None and os.environ.get("USE_EMBEDDINGS") == "1":
        try:
            from sentence_transformers import SentenceTransformer

            _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:  # fall back silently to TF-IDF
            print("Embeddings unavailable, using TF-IDF:", exc)
            _EMBEDDER = False
    return _EMBEDDER or None


def text_similarity(query, docs):
    """Cosine similarity of `query` against each text in `docs` (list)."""
    if not docs:
        return []
    emb = _get_embedder()
    if emb is not None:
        vecs = emb.encode([query] + docs, normalize_embeddings=True)
        return (vecs[1:] @ vecs[0]).tolist()
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit(docs + [query])
    except ValueError:  # empty vocabulary
        return [0.0] * len(docs)
    m = vec.transform(docs + [query])
    return cosine_similarity(m[-1], m[:-1])[0].tolist()


def load_complaints(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM complaints ORDER BY id")]
    con.close()
    return rows


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def _parse(d):
    return date.fromisoformat(d)


def build_assets(complaints):
    """Cluster complaints into assets and compute metrics + priority score."""
    if not complaints:
        return []
    ref_day = max(_parse(c["reported_on"]) for c in complaints)
    groups = []  # (category, [complaints])
    for cat in sorted({c["category"] for c in complaints}):
        subset = [c for c in complaints if c["category"] == cat]
        coords = np.radians([[c["lat"], c["lon"]] for c in subset])
        labels = DBSCAN(
            eps=CLUSTER_RADIUS_M / EARTH_R, min_samples=1, metric="haversine", algorithm="ball_tree"
        ).fit_predict(coords)
        by_label = {}
        for c, lab in zip(subset, labels):
            by_label.setdefault(lab, []).append(c)
        groups.extend((cat, v) for v in by_label.values())

    assets = []
    for cat, items in groups:
        items.sort(key=lambda c: (c["reported_on"], c["id"]))
        n = len(items)
        dates = [_parse(c["reported_on"]) for c in items]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, n)]
        costs = [c["repair_cost"] for c in items if c["repair_cost"]]
        total_spent = int(sum(costs))
        avg_cost = (total_spent / len(costs)) if costs else 0
        wasted = int(total_spent - costs[0]) if len(costs) > 1 else 0
        span = max((dates[-1] - dates[0]).days, 30)
        avg_sev = sum(c["severity"] for c in items) / n
        days_since = (ref_day - dates[-1]).days
        recency = math.exp(-days_since / 90.0)

        shrinking = False
        if n >= 3 and len(gaps) >= 2:
            earlier = gaps[:-1]
            shrinking = gaps[-1] < (sum(earlier) / len(earlier))
        shrink_factor = 1.0 if shrinking else (0.4 if n >= 3 else 0.0)
        repeat_part = 40 * (min(n, 8) - 1) / 7 if n >= 2 else 0
        score = round(repeat_part + 20 * recency + 25 * (avg_sev / 5) + 15 * shrink_factor, 1)

        tier = "Chronic" if n >= 5 else "Recurring" if n >= 3 else "Watch" if n == 2 else "Isolated"
        lat = sum(c["lat"] for c in items) / n
        lon = sum(c["lon"] for c in items) / n
        annual_waste = int((n - 1) / span * 365 * avg_cost) if n >= 2 else 0

        if tier == "Chronic":
            rec = "Stop patching. Order a root-cause inspection and a permanent fix (reconstruction / proper drainage / new fixture)."
        elif tier == "Recurring":
            rec = "Third or fourth complaint on this asset. Inspect the underlying cause before the next patch."
        elif tier == "Watch":
            rec = "Second complaint. Log it as a repeat and monitor."
        else:
            rec = "Single complaint. Routine repair."

        assets.append(
            {
                "id": f"A-{items[0]['id']:04d}",
                "category": cat,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "complaints": n,
                "open_now": any(c["status"] == "Open" for c in items),
                "first_reported": dates[0].isoformat(),
                "last_reported": dates[-1].isoformat(),
                "avg_gap_days": round(sum(gaps) / len(gaps)) if gaps else None,
                "gap_shrinking": shrinking,
                "avg_severity": round(avg_sev, 1),
                "total_spent": total_spent,
                "wasted": wasted,
                "projected_annual_waste": annual_waste,
                "score": score,
                "tier": tier,
                "recommendation": rec,
                "title": items[-1]["text"].replace(" (again!)", ""),
                "_items": items,
            }
        )
    assets.sort(key=lambda a: a["score"], reverse=True)
    return assets


def public_asset(a, with_timeline=False):
    out = {k: v for k, v in a.items() if k != "_items"}
    if with_timeline:
        out["timeline"] = [
            {
                "id": c["id"],
                "date": c["reported_on"],
                "text": c["text"],
                "severity": c["severity"],
                "status": c["status"],
                "repair_action": c["repair_action"],
                "repair_cost": c["repair_cost"],
                "repaired_on": c["repaired_on"],
                "photo_path": c.get("photo_path"),
            }
            for c in a["_items"]
        ]
    return out

def summary(assets, top_n=10):
    chronic = [a for a in assets if a["tier"] == "Chronic"]
    top = assets[:top_n]
    total = sum(a["complaints"] for a in assets)
    return {
        "total_complaints": total,
        "total_assets": len(assets),
        "chronic_assets": len(chronic),
        "recurring_assets": len([a for a in assets if a["tier"] == "Recurring"]),
        "total_spent": sum(a["total_spent"] for a in assets),
        "total_wasted": sum(a["wasted"] for a in assets),
        "top_n": top_n,
        "top_n_annual_waste": sum(a["projected_annual_waste"] for a in top),
        "repeat_share_pct": round(100 * sum(a["complaints"] for a in assets if a["complaints"] >= 2) / max(1, total)),
    }


def match_complaint(text, category, lat, lon, assets):
    """Find the existing asset a NEW complaint most likely belongs to (or None)."""
    best, best_score = None, 0.0
    for a in assets:
        d = dist_m(lat, lon, a["lat"], a["lon"])
        if d > MATCH_RADIUS_M:
            continue
        geo = 1 - d / MATCH_RADIUS_M
        sim = max(text_similarity(text, [c["text"] for c in a["_items"]]) or [0.0])
        cat_bonus = 0.25 if a["category"] == category else 0.0
        score = 0.5 * geo + 0.25 * sim + cat_bonus
        if score > best_score:
            best, best_score = a, score
    if best is None or best_score < 0.45:
        return None, round(best_score, 2)
    return best, round(best_score, 2)
