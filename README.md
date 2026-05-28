# FyTic Backend MVP

FastAPI backend for the FyTic marketing site. Serves site content, client data, and handles waitlist submissions. Designed to scale into an AI SaaS — new feature areas are added as sibling modules alongside `app/landing/`, never touching the landing-page code.

---

## Quick start

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment file
cp .env.example .env

# 4. Run (hot-reload enabled in development)
python main.py
```

Server starts at **`http://localhost:8000`**.
Interactive API docs at **`http://localhost:8000/docs`**.

---

## Environment variables

Copy `.env.example` → `.env` and edit as needed.

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | Server port |
| `ENVIRONMENT` | `development` | Set to `production` to enforce strict CORS |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origin in production |

In `development`, CORS allows all origins (`*`). In `production`, only `FRONTEND_URL` is allowed.

---

## API reference

All routes are under `/api`.

### `GET /api/content`

Returns the full site content object (all marketing copy, navigation labels, feature descriptions, etc.).

Used by the frontend to hydrate pages from a single source of truth. Text lives in `app/landing/data/content.json` — edit it there to change any site copy.

```json
{
  "seo": { "title": "...", "description": "..." },
  "brand": { "name": "FyTic", "tagline": "..." },
  "hero": { "headline1": "Primera", "headlineEm": "IA jurídica", ... },
  "features": [{ "number": "01", "tag": "Research AI", "imageKey": "constitution", ... }],
  ...
}
```

### `GET /api/clients`

Returns the client carousel data.

```json
{ "visible": false, "clients": [] }
```

Set `"visible": true` and add firm names to `"clients"` in `app/landing/data/clients.json` to show the carousel on the site.

### `GET /api/waitlist`

Returns whether the waitlist is currently accepting entries.

```json
{ "active": true }
```

### `POST /api/waitlist`

Submit a waitlist entry.

**Request body:**
```json
{
  "name": "María García",
  "email": "maria@despacho.mx",
  "role": "despacho",
  "position": "socio",
  "caseload": "6-20"
}
```

**Responses:**
- `201 Created` → `{ "ok": true }` — entry saved
- `403 Forbidden` → `{ "detail": "waitlist is closed" }` — `active` is false
- `422 Unprocessable Entity` — validation error (missing name, invalid email, etc.)

---

## Data files

These JSON files act as the data layer (Supabase replaces them when integrated).

| File | Controls |
|---|---|
| `app/landing/data/content.json` | All site copy — edit here to update marketing text |
| `app/landing/data/clients.json` | Client carousel (`visible` flag + `clients` array) |
| `app/landing/data/waitlist.json` | Active flag + submitted entries — **not committed to git** |

### Toggle behaviour

| File | Change | Effect |
|---|---|---|
| `clients.json` | `"visible": false` | Hides the client carousel section entirely |
| `clients.json` | `"clients": []` | Also hides carousel (empty array check) |
| `waitlist.json` | `"active": false` | Shows "waitlist closed" view instead of form |

---

## Project structure

```
backend-mvp/
├── main.py                  # App factory — CORS middleware + router registration
├── requirements.txt
├── .env.example
└── app/
    ├── config.py            # Settings via pydantic-settings (reads .env)
    └── landing/             # Landing-page module — isolated, keep it simple
        ├── models.py        # Pydantic request/response models
        ├── router.py        # 4 routes (content, clients, waitlist ×2)
        └── data/
            ├── content.json
            ├── clients.json
            └── waitlist.json  # gitignored — grows with real entries
```

### Adding a new feature module

```python
# 1. Create app/<feature>/__init__.py, models.py, router.py
# 2. Register in main.py:
from app.<feature>.router import router as <feature>_router
app.include_router(<feature>_router, prefix="/api/<feature>")
```

The `landing/` module is never modified when adding SaaS features.

---

## Supabase migration (pending)

When ready, replace `_load` / `_save` calls in `app/landing/router.py` with Supabase queries. `models.py` and `main.py` require no changes.

---

## Requirements

- Python 3.11+
- All deps in `requirements.txt` — install with `pip install -r requirements.txt`
