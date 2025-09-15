CV Zebrafish project

Backend quickstart (Flask + SQLite)

1) Create/verify the database
- If starting from CSV, run `backend/DB1.py` once to populate `CV_Zebrafish.db`.
- Or place an existing `CV_Zebrafish.db` at the repository root.

2) Install dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

3) Run the API server

```bash
python backend/app.py
```

Endpoints
- `GET /health` → `{ "status": "ok" }`
- `GET /fish_parts` → `["head", "lefteye", ...]`
- `GET /fish?fish_id=0&part=head&frame_start=0&frame_end=100&limit=500`
  - Returns `{ count, items: [{ fish_id, fish_part, frame, x, y, likelihood }] }`

Notes
- The server auto-ensures the `Fish_Data` table exists.
- CORS is enabled for simple frontend integration.
