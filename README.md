# CityMemory (Pothole Memory for Bengaluru)

Hackathon problem statement #9. Cities handle complaints one at a time and forget the history.
CityMemory links every complaint to the **physical asset** it is about, so a municipal team can see:
*"This road has been 'fixed' 9 times in 10 months and ₹65,000 has been wasted. Stop patching it."*

## Run it (Windows, Antigravity / VS Code terminal)

```
cd citymemory
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

(Mac/Linux: `source venv/bin/activate`.) The map needs internet (Leaflet and OpenStreetMap tiles),
so test your venue Wi-Fi early and keep a recorded backup demo.

## What is inside

| File | Job |
|---|---|
| `generate_data.py` | Simulated Bengaluru data: 235 complaints, 85 assets (roads, drains, streetlights, footpaths), 15 chronic hotspots. Creates `citymemory.db` on first run |
| `analysis.py` | DBSCAN geo-clustering, complaint-to-asset matching, priority score, wasted-money maths |
| `app.py` | Flask API and page |
| `templates/index.html` | Dashboard: stat cards, ranked list, Leaflet map, asset timeline, "report a complaint" panel |
| `docs/` | Build plan, pitch script, judge Q&A, Antigravity prompts |

## How it works

1. **Group complaints into assets.** Complaints of the same type within about 40 m are clustered (DBSCAN, haversine distance). On the simulated data this recovers all 85 assets and all 15 chronic hotspots.
2. **Match new complaints to history.** A new report is scored on distance (50%), text similarity (25%) and category (25%). If it matches, the officer sees "This is NOT a new problem. Complaint #10 on this asset, ₹74,800 already spent."
3. **Prioritise.** Score 0-100 from repeat count (40), recency (20), severity (25) and whether failures are coming faster (15).
4. **Quantify waste.** Money spent on repairs after the first one, plus projected waste per year at the current failure rate.

Tiers: Chronic (5+ complaints), Recurring (3-4), Watch (2), Isolated (1).

## Demo in 90 seconds

1. Point at the top stat cards: how many repeats, how much money wasted.
2. Click the biggest red pin. Show the timeline of repairs and the recommendation.
3. Click **Report a complaint**, then **Fill demo repeat**, then **Check history and submit**. The system catches the repeat instantly.
4. Filter the list to **Chronic**. This is the "fix permanently first" list.

## Honest limits (say these to the judges)

- All data is simulated. A real municipal complaint export plugs into the same `complaints` table.
- Text matching uses TF-IDF by default. For real semantic embeddings: `pip install sentence-transformers`, then run with the environment variable `USE_EMBEDDINGS=1`. It is a large download, so only do this if you have time and good internet.
- Repair costs are illustrative averages, not real tender rates.
- Photos are not analysed in this version (see the stretch ideas in `docs/PLAN.md`).

## Troubleshooting

- `ModuleNotFoundError` means the venv is not active. Run `venv\Scripts\activate` again.
- Blank map: no internet, or the CDN is blocked. Try a phone hotspot.
- Port 5000 busy: change `port=5000` in the last line of `app.py`.
- To get fresh data: click **Reset demo data**, or delete `citymemory.db` and restart.
