# CLAUDE.md — FyTic Backend MVP

## Overview

FastAPI backend for FyTic. Currently serves the landing page (`fytic-website-mvp`).
Designed to scale into an AI SaaS — new feature areas are added as separate modules, never touching `app/landing/`.

---

## Architecture

```
backend-mvp/
├── main.py                  # App factory: registers middleware + routers
├── requirements.txt
├── .env.example
│
└── app/
    ├── config.py            # Pydantic-settings (reads .env)
    │
    ├── landing/             # Landing-page API — self-contained, keep it simple
    │   ├── models.py        # Pydantic I/O models
    │   ├── router.py        # 4 routes (content, clients, waitlist ×2)
    │   └── data/            # JSON data files (Supabase-ready, see below)
    │       ├── content.json # Full site copy served to frontend
    │       ├── clients.json # Client carousel visibility + names
    │       └── waitlist.json  # NOT committed (grows with real entries)
    │
    # Future modules go here at the same level as landing/:
    # ├── ai/
    # ├── auth/
    # ├── billing/
    # └── ...
```

**Rule:** every new feature area is a new module folder next to `landing/`. Never add SaaS logic inside `landing/`.

---

## API — Landing Page

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/content` | Full `SiteContent` JSON (all site copy) |
| `GET` | `/api/clients` | `{ visible, clients[] }` — controls carousel section |
| `GET` | `/api/waitlist` | `{ active }` — controls form vs closed-state |
| `POST` | `/api/waitlist` | Submit entry `{ name, email, role, position, caseload }` |

### Toggle behaviour via data files

| File | Key | Effect |
|---|---|---|
| `app/landing/data/clients.json` | `"visible": false` | Hides the entire clients carousel |
| `app/landing/data/waitlist.json` | `"active": false` | Shows "waitlist closed" view instead of form |

---

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Copy env and edit as needed
cp .env.example .env

# Run (dev — hot reload enabled)
python main.py
# or: uvicorn main:app --reload --port 8000
```

Server starts at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | Server port |
| `ENVIRONMENT` | `development` | Set to `production` to enforce CORS |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed origin in production |

---

## Supabase Migration (pending)

When ready, replace `_load` / `_save` calls in `app/landing/router.py` with Supabase calls.
No changes needed to `models.py` or `main.py`.

---

## Adding a New Feature Module

1. Create `app/<feature>/` with `__init__.py`, `models.py`, `router.py`
2. Add `app.include_router(feature_router, prefix="/api/<feature>")` in `main.py`
3. Done — `landing/` is untouched
