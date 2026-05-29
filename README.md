# FyTic Backend MVP

FastAPI backend for the FyTic marketing site. Serves content, client data, and handles waitlist / contact submissions. Designed to scale into an AI SaaS — new feature areas live as sibling modules alongside `app/landing/`, never touching landing-page code.

---

## Quick start

### First time

```bash
# 1. Create and activate the conda environment
conda create -n fytic python=3.11 -y
conda activate fytic

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the env file and fill in your Supabase credentials
cp .env.example .env
```

Open `.env` and set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (see Environment variables below).

### Every time

```bash
conda activate fytic
uvicorn main:app --reload --port 8000
```

Server → **`http://localhost:8000`**  
Interactive docs → **`http://localhost:8000/docs`**

---

## Stopping & restarting

Press **`Ctrl+C`** in the terminal to stop uvicorn.

**If the port stays occupied after stopping** (common on Windows), find and kill the leftover process:

```bash
# Find what is holding port 8000
netstat -ano | findstr :8000

# Kill it — replace XXXXX with the PID from the output above
taskkill /PID XXXXX /F

# Verify the port is free (should return nothing)
netstat -ano | findstr :8000
```

Then start fresh with `uvicorn main:app --reload --port 8000`.

---

## Environment variables

Copy `.env.example` → `.env` and edit.

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | Server port |
| `ENVIRONMENT` | `development` | `production` enforces strict CORS |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origin in production |
| `SUPABASE_URL` | — | `https://wzevtxexmrisogbpuzmx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | — | From Supabase → Settings → API → service_role. **Must be one unbroken line — never press Enter inside the value.** |

In `development`, CORS allows all origins (`*`). In `production`, only `FRONTEND_URL` is allowed.

---

## API reference

All routes are under `/api`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/content` | Full site copy (reads `content.json`) |
| `GET` | `/api/clients` | `{ visible, clients[] }` — carousel data from Supabase |
| `GET` | `/api/waitlist` | `{ active, count }` — form status + entry count |
| `POST` | `/api/waitlist` | Submit `{ name, email, role, position, caseload }` |
| `POST` | `/api/contact` | Submit `{ name, firm, email, message }` |

### Supabase toggles

```sql
-- Turn waitlist off
UPDATE waitlist SET active = false WHERE id = '_config';

-- Show client carousel
UPDATE clients SET visible = true WHERE id = '_config';

-- Add a law firm
INSERT INTO clients (name, sort_order) VALUES ('Nombre del Despacho', 1);
```

---

## Project structure

```
backend-mvp/
├── main.py                  # App factory — CORS + router registration + startup check
├── requirements.txt
├── .env.example
└── app/
    ├── config.py            # Settings via pydantic-settings (reads .env)
    ├── db.py                # Supabase client singleton — get_db()
    └── landing/             # Landing-page module — isolated, never modify for SaaS
        ├── models.py        # Pydantic request/response models
        ├── router.py        # 5 routes (content, clients, waitlist ×2, contact)
        └── data/
            └── content.json # All marketing copy — edit here to update site text
```

### Adding a new feature module

```python
# 1. Create app/<feature>/__init__.py, models.py, router.py
# 2. Register in main.py:
from app.<feature>.router import router as <feature>_router
app.include_router(<feature>_router, prefix="/api/<feature>")
```

---

## Requirements

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- Python 3.11 (managed by conda)
