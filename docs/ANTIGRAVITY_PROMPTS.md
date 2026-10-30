# Prompts to paste into the Antigravity agent

Open the `citymemory` folder as the workspace first. Run one prompt at a time and test in the browser after each. Copy the folder before big changes.

## 0. Orient yourself
```
Read app.py, analysis.py, generate_data.py and templates/index.html. Explain in simple words how a complaint becomes part of an asset's history. Do not change any code.
```

## 1. CSV import of real complaints
```
Add a POST /api/import endpoint that accepts a CSV with columns category, text, lat, lon, reported_on, severity, status, repair_action, repair_cost. Insert the rows into the complaints table. Add an "Import CSV" button in the header of templates/index.html. Validate columns and show a clear error message. Do not change anything else.
```

## 2. Photo upload
```
Add an optional photo upload to the "Report a complaint" form. Save files in a static/uploads folder, store the file name in a new photo column in the complaints table, and show the photo in the asset timeline. Handle the old database that has no photo column. Do not change anything else.
```

## 3. Kannada labels
```
Add a language toggle (English / ಕನ್ನಡ) for the tier names, the recommendation text and the stat card labels in templates/index.html using a JavaScript dictionary. Do not change the Python code.
```

## 4. CSV export of the action list
```
Add an "Export fix-permanently list" button that downloads the currently filtered list (asset id, type, location title, complaints, total spent, wasted, priority score, recommendation) as a CSV. Do it client-side in templates/index.html.
```

## 5. Real embeddings
```
Confirm that analysis.py uses sentence-transformers when the environment variable USE_EMBEDDINGS=1 is set and falls back to TF-IDF otherwise. Show me how to run it on Windows PowerShell. Do not change anything else.
```

## 6. Bug hunt
```
Run python app.py, open every button, filter and the report panel, and list anything that errors or looks broken. Fix only real bugs. Do not refactor.
```

## Tips

- Say "do not change anything else" in every prompt.
- If the agent breaks something, undo and give a smaller prompt.
- Stop adding features about 2 hours before the demo.
