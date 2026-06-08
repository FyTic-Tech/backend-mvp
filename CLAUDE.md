# CLAUDE.md — FyTic Backend MVP

## Overview

FastAPI backend for FyTic. Serves the landing page (`fytic-website-mvp`).
Designed to scale into an AI SaaS — new feature areas are added as separate modules, never touching `app/landing/`.

**Production URL:** `https://backend-mvp-production-8e67.up.railway.app` (Railway)  
**Docs:** `https://backend-mvp-production-8e67.up.railway.app/docs`  
**Start command (Railway + local):** `python main.py` — reads `PORT` from env, hot-reload only in development.

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
    │   ├── models.py        # Pydantic I/O models (see Models section below)
    │   ├── router.py        # 6 routes (content, clients, waitlist GET/POST/PATCH, contact)
    │   └── data/
    │       └── content.json # Full site copy served to frontend (waitlist/clients in Supabase)
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
| `GET` | `/api/waitlist` | `{ active, count }` — form vs closed-state + submission count |
| `POST` | `/api/waitlist` | Submit survey entry (all fields optional); returns `{ ok, id }` |
| `PATCH` | `/api/waitlist/{id}` | Update specific fields of an existing entry; all body fields optional |
| `POST` | `/api/contact` | Submit contact form `{ name, firm, email, message }` |

### Models (`app/landing/models.py`)

| Model | Purpose |
|---|---|
| `WaitlistEntryCreate` | POST body — all fields `str = ""` (name/email optional for declined entries) |
| `WaitlistEntryUpdate` | PATCH body — all fields `Optional[str] = None`; only non-null fields update the row |
| `WaitlistPostResponse` | POST response — `{ ok: bool, id: str }` — ID used by frontend for PATCH |
| `WaitlistStatusResponse` | GET response — `{ active: bool, count: int }` |
| `OkResponse` | Generic `{ ok: bool }` for PATCH/contact |
| `ContactCreate` | POST /api/contact body — all fields required, email validated |

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
| `SUPABASE_URL` | `""` | Project URL from Settings → API |
| `SUPABASE_SERVICE_KEY` | `""` | Service role key from Settings → API (secret) |

---

## Supabase

**Status:** Integrated for waitlist, clients, and contacts. `content.json` remains a static file (site copy).

### Tables (3 total)

Each table uses a `_config` sentinel row (where applicable) so one table handles both settings and data.

| Table | `id = '_config'` row | Other rows |
|---|---|---|
| `waitlist` | `active bool` — toggles form open/closed | One row per waitlist submission |
| `clients` | `visible bool` — toggles carousel visibility | One row per law firm client |
| `contacts` | — (no config needed) | One row per contact-form submission |

**Toggle waitlist off:**
```sql
update waitlist set active = false where id = '_config';
```
**Show clients carousel:**
```sql
update clients set visible = true where id = '_config';
```
**Add a law firm:**
```sql
insert into clients (name, sort_order) values ('Nombre del Despacho', 1);
```

**Client:** `app/db.py` exposes `get_db() -> Client` (lazy singleton, uses `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` env vars).

**Key:** Always use the **service role key** (Settings → API → Service Role) — never the publishable key — so the backend can bypass RLS.

---

## Adding a New Feature Module

1. Create `app/<feature>/` with `__init__.py`, `models.py`, `router.py`
2. Add `app.include_router(feature_router, prefix="/api/<feature>")` in `main.py`
3. Done — `landing/` is untouched
