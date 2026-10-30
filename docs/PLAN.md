# 18-hour plan (solo)

The core app already works. Your hours go into understanding it, owning it, adding one or two extras, and rehearsing.

| Hours | Do this | Done when |
|---|---|---|
| 0-1 | Run it. Click every pin, filter and button. Report a demo repeat. | You can explain each screen without notes |
| 1-3 | Read `analysis.py` top to bottom. Change `CLUSTER_RADIUS_M` and the score weights, watch results move. | You can answer "how do you know it is the same pothole?" |
| 3-5 | Read `generate_data.py`. Add your own area (for example Bidar or Kalaburagi spots) if you want a local angle. | You can explain where real data would plug in |
| 5-10 | Add 1-2 stretch features from the list below | Visible in the demo |
| 10-12 | Make it yours: name, colours, a logo, a short Kannada tagline | Looks like a product |
| 12-13 | Sleep or rest for at least an hour. A tired demo loses. | |
| 13-15 | Slides (5 slides, see PITCH.md) | Deck done |
| 15-17 | Rehearse the demo 5 times out loud with a timer. Record a backup video. | Under 2 minutes, no stumbling |
| 17-18 | Buffer. Fix only bugs. Add no new features. | |

## Stretch features (pick one or two)

1. **CSV import** of a real complaint export, so judges can load their own data.
2. **Photo upload** on the report form, shown in the asset timeline (store the file, no AI needed).
3. **Heatmap layer** of chronic assets by ward.
4. **Department view**: filter by asset type and export the "fix permanently" list as CSV.
5. **Kannada labels** for the tiers and the recommendation text.
6. **Real embeddings** (`USE_EMBEDDINGS=1`) and show the match confidence improving.

## Rules

- Cut features before you cut polish.
- Never claim real data. Always say "simulated".
- If the server or Wi-Fi fails, play the backup video.
