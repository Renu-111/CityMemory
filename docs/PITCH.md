# Pitch kit

Numbers below come from the simulated data (seed 42). Check them on screen before you quote them.

## 2-minute demo script

1. **Hook (10 s).** "Every city handles complaints one at a time and forgets the history. The same road gets 'fixed' again and again. We built CityMemory so the city remembers."
2. **The big picture (15 s).** Point at the stat cards. "In this simulated Bengaluru dataset, 88% of complaints are repeats, and about ₹14 lakh went into repairs that did not last."
3. **One asset (30 s).** Click the biggest red pin. "This footpath at Majestic has failed 9 times. The gap between failures keeps getting shorter. Here is every repair and what it cost. The system says: stop patching, do a permanent fix."
4. **The live catch (25 s).** Report a complaint, Fill demo repeat, Submit. "A citizen reports it as a new problem. Without CityMemory it would be a fresh ticket. With it, the officer sees complaint number 10 and ₹74,800 already spent."
5. **The action list (20 s).** Filter to Chronic. "Fix the top 10 permanently and save roughly ₹12 lakh a year at the current repair rate."
6. **Close (5 s).** "Cities handle complaints. We give them memory."

## 5 slides

1. Problem: same asset repaired again and again, history scattered across departments.
2. Solution: link complaints to physical assets, show history and wasted money.
3. How it works: geo-clustering, new-complaint matching, priority score.
4. Demo (live).
5. Next steps: load a real municipal complaint export, photo evidence, pilot with one ward.

Do not invent statistics. Quote only the numbers your own dashboard shows, and say they are simulated.

## Likely judge questions

**Is the data real?** No, it is simulated, and we say so. The `complaints` table has a simple schema, so a real municipal export can be loaded.

**How do you know two complaints are the same asset?** Same category and within about 40 metres, grouped by DBSCAN. On the simulated data this recovers every asset exactly. On real data we would tune the radius and validate with officers.

**Why not just use the complaint ID?** Different citizens file different tickets for the same asset, so there is no shared ID. Location plus category is the link.

**Where does AI come in?** Clustering and text similarity link reports to history, and the priority score ranks what to fix first. Text matching can use sentence embeddings. We kept the scoring rule-based so every ranking is explainable to an officer.

**Are the repair costs real?** They are illustrative averages. Real work-order costs would replace them.

**What if the GPS is wrong?** That is why matching uses a distance band plus text and category, and why we show a match confidence instead of claiming certainty.

**Who uses it?** Municipal engineers and ward officers for planning, and the public for transparency.

## Backup plan

The map needs internet. Record the full demo as a video and keep it on your phone and laptop.
