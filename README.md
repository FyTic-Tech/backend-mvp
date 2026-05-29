# FyTic Backend MVP

FastAPI backend for the FyTic marketing site. Serves content, client data, and handles waitlist / contact submissions. Designed to scale into an AI SaaS — new feature areas live as sibling modules alongside `app/landing/`, never touching landing-page code.

**Production URL:** `https://backend-mvp-production-8e67.up.railway.app`  
**Interactive docs:** `https://backend-mvp-production-8e67.up.railway.app/docs`

---

## Local development

### First time

```bash
# 1. Create and activate the conda environment
conda create -n fytic python=3.11 -y
conda activate fytic

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env file and fill in your Supabase credentials
cp .env.example .env
```

### Every time

```bash
conda activate fytic
uvicorn main:app --reload --port 8000
```

Server → **`http://localhost:8000`**  
Docs → **`http://localhost:8000/docs`**

---

## Stopping & restarting

Press **`Ctrl+C`** to stop.

**If port 8000 stays occupied** (common on Windows):

```bash
# Find the process holding port 8000
netstat -ano | findstr :8000

# Kill it — replace XXXXX with the PID
taskkill /PID XXXXX /F

# Verify the port is free (should return nothing)
netstat -ano | findstr :8000
```

---

## Deploying to Railway

Railway is already set up and running. These are the environment variables that must be configured in the Railway dashboard → your service → **Variables**:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `FRONTEND_URL` | `https://<your-vercel-url>` — update after Vercel deploy |
| `SUPABASE_URL` | `https://wzevtxexmrisogbpuzmx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | The full service role JWT (single line) |

**Start command in Railway:** `python main.py`  
Railway sets the `PORT` env var automatically — the app reads it via `settings.port`.

### Updating CORS after Vercel deployment

Once your frontend is live on Vercel, set these two variables in Railway:

```
ENVIRONMENT=production
FRONTEND_URL=https://<your-vercel-url>
```

This restricts the backend to only accept requests from your frontend domain.

---

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | Set automatically by Railway in production |
| `ENVIRONMENT` | `development` | `production` enforces strict CORS |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origin in production |
| `SUPABASE_URL` | — | `https://wzevtxexmrisogbpuzmx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | — | From Supabase → Settings → API → service_role. **Must be one unbroken line.** |

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/content` | Full site copy (reads `content.json`) |
| `GET` | `/api/clients` | `{ visible, clients[] }` from Supabase |
| `GET` | `/api/waitlist` | `{ active, count }` from Supabase |
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
├── main.py                  # App factory — CORS + router + startup Supabase check
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

---

## Requirements

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- Python 3.11 (managed by conda)
