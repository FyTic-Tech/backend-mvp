# CLAUDE.md — FyTic Backend MVP

## What this is

FastAPI backend in production on Railway. Originally a landing-page API; now a **production auth + profile + referral system** with the landing-page API still living inside it. The actual FyTic SaaS app module (`app/FyTic_app/`) is a registered-but-empty placeholder — all real SaaS logic goes there next.

**Production URL:** `https://backend-mvp-production-8e67.up.railway.app`  
**Interactive docs:** `https://backend-mvp-production-8e67.up.railway.app/docs`  
**Start command (Railway + local):** `python main.py` — reads `PORT` from env; hot-reload only in dev.

---

## Architecture

```
backend-mvp/
├── main.py                   # App factory: CORS middleware + router registration
├── requirements.txt          # fastapi, uvicorn, pydantic, supabase, resend, PyJWT
├── .env.example
│
└── app/
    ├── config.py             # pydantic-settings — reads .env or Railway env vars
    ├── db.py                 # get_db() → lazy Supabase Client singleton (service key)
    │
    ├── landing/              # Landing page + auth/profile API — all current live endpoints
    │   ├── models.py         # All Pydantic I/O models
    │   ├── router.py         # All routes (see API section below)
    │   └── data/
    │       └── content.json  # Static site copy served by GET /api/content
    │
    └── FyTic_app/            # SaaS app module — EMPTY PLACEHOLDER
        └── router.py         # Not yet mounted in main.py; 0 bytes
```

**Module rule:** every new feature area (AI, billing, documents, cases) is a new folder next to `landing/` and `FyTic_app/`. Never add SaaS logic inside `landing/`.

**API prefix separation:**
- `/api` — landing page API (live in production, no versioning)
- `/api/app/v1` — FyTic app API (all new app endpoints go here; namespaced + versioned)

To mount the app module:
```python
# main.py
from app.FyTic_app.router import router as app_router
app.include_router(app_router, prefix="/api/app/v1")
```

---

## Cloud Deployment — Railway

Railway runs a **single service** from this repo. No Docker — Railway auto-detects Python and installs `requirements.txt`.

### How it works
1. **Build:** Railway runs `pip install -r requirements.txt` on every deploy.
2. **Start:** Railway runs `python main.py`, which calls `uvicorn.run("main:app", host="0.0.0.0", port=settings.port)`.
3. **Port:** Railway injects `PORT` as an env var; `settings.port` reads it.
4. **Env vars:** All secrets live in Railway's "Variables" panel — never in source. The `.env.example` is the authoritative list of what Railway must have configured.
5. **Deploys:** Push to the connected GitHub branch → Railway auto-deploys. Zero-downtime rolling restart.

### Startup check
On every startup, `main.py` probes Supabase (`clients` table) and prints the connection result to Railway logs. If you see `FAILED` in logs after a deploy, check `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in Railway Variables.

---

## Integrations

### Supabase

**Purpose:** sole database for all persistent state. Backend uses the **service role key** so every query bypasses Row Level Security — the backend itself is the access-control layer.

**Client:** `app/db.py` → `get_db()` returns a lazy singleton `supabase.Client`. Call it at the top of every route handler, not at module load time (avoids cold-import errors during testing).

**Phase 1 tables (landing/auth — live):**

| Table | Notes |
|---|---|
| `waitlist` | `_config` sentinel row (`id = '_config'`) holds `active bool` — form open/closed. All other rows are survey submissions |
| `users` | One row per registered user. Phase 2 expanded it with `org_id`, `role`, `is_active`, token, and soft-delete fields |
| `contacts` | Contact-form submissions |
| `investors` | Investor interest submissions |

**Phase 2 tables (app — live in DB, not yet served by this backend):** `organizations`, `subscriptions`, `plans`, `clients`, `contracts`, `templates`, `org_library`, `user_library`, `fytic_library`

> **`clients` note:** The original MVP `clients` table (landing-page carousel) was removed. The current `clients` table is the org-scoped app client records — a completely different schema. The landing-page carousel is now hardcoded in `content.json` and served by `GET /api/clients` without any DB call.

**Key `users` columns (Phase 1):** `id`, `email`, `full_name`, `firm_name`, `position`, `practice_area`, `phone`, `team_size`, `ref_code`, `referred_by`, `survey_completed`, `survey_completed_at`, `auth_provider` (`email` | `google`).

**Useful SQL ops:**
```sql
-- Close waitlist
UPDATE waitlist SET active = false WHERE id = '_config';

-- Count real registered users (exclude sentinel rows)
SELECT count(*) FROM users WHERE id NOT LIKE '\_%';

-- See who referred whom
SELECT email, referred_by, created_at FROM users WHERE referred_by IS NOT NULL ORDER BY created_at DESC;
```

**Why `len(data)` not `count="exact"`:** The Supabase Python SDK's `count="exact"` returns unreliable values; fetching all IDs and calling `len()` is the workaround used throughout this codebase.

### Resend

**Purpose:** transactional email (auth confirmation, password reset, magic link) with FyTic branding.

**Integration path:** Supabase "Send Email" auth hook → calls a backend webhook endpoint → backend calls Resend API. The `RESEND_API_KEY` and `SUPABASE_HOOK_SECRET` env vars are already in config/Railway.

**Current status:** The hook endpoint is **not yet implemented** in the codebase. Supabase is likely using its default email sender in the meantime. When implemented, it goes in `app/landing/router.py` (or a new `app/email/` module) as:
```python
POST /api/hooks/send-email   # Supabase calls this; verify HMAC with SUPABASE_HOOK_SECRET
```

### PyJWT

In `requirements.txt` — for verifying Supabase-issued JWTs (`HS256`, signed with your Supabase JWT secret). Every `/api/app/v1` endpoint must verify the JWT from the `Authorization: Bearer <token>` header, extract the `sub` claim (Supabase user UUID), then query `users` for `org_id` and `role`.

**Important:** Supabase JWTs do not embed `org_id` or `role` as custom claims by default. The backend must always look these up from the `users` table — not trust any `org_id` passed in the request body or query string.

**Six roles** (`users.role`): `super_admin`, `admin`, `member`, `limited`, `internal_dev`, `internal_team`. Three of these (`super_admin`, `internal_dev`, `internal_team`) are internal-only roles that require an additional `X-Internal-Key` header (value = `INTERNAL_API_KEY` env var) on top of a valid JWT. Role alone is not sufficient — the physical key must also be present. Add this env var to Railway when implementing internal routes.

Not yet wired to any route — this is the first thing to implement when building `FyTic_app` endpoints.

---

## Full API Reference

All routes are registered at `/api` prefix.

### Content & Config

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/content` | Returns full `content.json` — all site copy (hero, waitlist labels, etc.) |
| `GET` | `/api/clients` | `{ visible: bool, clients: string[] }` — carousel data. Reads from `content.json`, not DB |
| `GET` | `/api/waitlist` | `{ active: bool, count: int }` — form state + registered user count (from `users` table) |

### Survey / Waitlist

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/waitlist` | Submit or upsert a survey entry. If `user_id` already has a row, updates it. Returns `{ ok, id }`. |
| `PATCH` | `/api/waitlist/{id}` | Update specific fields of a waitlist row. All fields optional. Triggers profile sync if `user_id` is set. |

### Misc Forms

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/contact` | Contact form `{ name, firm, email, message }` → inserts into `contacts`. |
| `POST` | `/api/investors` | Investor interest `{ name, email }` → inserts into `investors`. |

### Profile & Auth Linking

These endpoints are called by the frontend during auth flows. They do not require a JWT yet — they rely on the frontend passing correct IDs (see Security section).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/profile/ref-code` | Get or create a referral code for `user_id`. Idempotent: returns existing if already set. |
| `GET` | `/api/profile/referrals/{ref_code}` | List users who registered via this referral code. |
| `POST` | `/api/profile/autofill` | Read user's waitlist answers and fill empty `users` profile fields (position, practice_area, firm_name). |
| `PATCH` | `/api/profile/update` | Update editable profile fields (full_name, firm_name, position, practice_area, phone, team_size). |
| `POST` | `/api/profile/check-email` | Check if email is already registered; returns `{ exists, provider }`. Used before signup to show correct login method. |
| `POST` | `/api/profile/link-google` | After Google OAuth: link `waitlist_id` row to `user_id` + email. Sets `referred_by` in users. |
| `POST` | `/api/profile/bind-user` | Email/password path: transfer anonymous user's survey data to the permanent user after email confirmation. Deletes the anonymous row. |
| `POST` | `/api/profile/link-survey` | Link anonymous waitlist entries (by email) to a registered user. Sets `survey_completed` + `referred_by`. |

### Internal helpers

| Function | Location | Description |
|---|---|---|
| `_sync_user_profile(db, user_id, ai_question, referred_by)` | `landing/router.py` | Sets `survey_completed=True` and `referred_by` on the `users` row. Called by POST/PATCH waitlist and all auth-linking endpoints. |

---

## Pydantic Models (`app/landing/models.py`)

| Model | Used by | Notes |
|---|---|---|
| `WaitlistEntryCreate` | `POST /api/waitlist` | All fields `str = ""`, email validated by regex. `user_id` and `referred_by` are `Optional[str]`. |
| `WaitlistEntryUpdate` | `PATCH /api/waitlist/{id}` | All fields `Optional`, only non-null fields trigger DB update. |
| `WaitlistPostResponse` | `POST /api/waitlist` | `{ ok: bool, id: str }` — ID stored by frontend for subsequent PATCH. |
| `WaitlistStatusResponse` | `GET /api/waitlist` | `{ active: bool, count: int }` |
| `ContactCreate` | `POST /api/contact` | All fields required, email validated. |
| `InvestorCreate` | `POST /api/investors` | `{ name, email }` both required + validated. |
| `CheckEmailRequest` | `POST /api/profile/check-email` | `{ email: str }` |
| `ProfileUpdateRequest` | `PATCH /api/profile/update` | `user_id` required; all other fields optional. |
| `RefCodeRequest` | `POST /api/profile/ref-code`, `POST /api/profile/autofill` | `{ user_id: str }` |
| `LinkSurveyRequest` | `POST /api/profile/link-survey` | `{ user_id, email, referred_by? }` |
| `BindUserRequest` | `POST /api/profile/bind-user` | `{ anonymous_id, new_user_id }` |
| `LinkGoogleRequest` | `POST /api/profile/link-google` | `{ waitlist_id, user_id, email, referred_by? }` |
| `OkResponse` | PATCH routes, contact, investors | `{ ok: bool }` |
| `ClientsResponse` | `GET /api/clients` | `{ visible: bool, clients: string[] }` |

---

## Security

### Current posture
The backend uses the Supabase **service role key** — this bypasses all RLS. The backend IS the authorization boundary.

### Known risks

**No JWT verification on profile endpoints (HIGH)**  
`/api/profile/ref-code`, `/api/profile/autofill`, `/api/profile/update`, `/api/profile/bind-user`, `/api/profile/link-google`, `/api/profile/link-survey` all accept `user_id` as a plain body parameter with no authentication. Any caller who knows (or guesses) a UUID can mutate another user's profile, generate ref codes for other users, or trigger `bind-user` to delete an anonymous row.

*Fix:* Extract the Supabase JWT from `Authorization: Bearer <token>` header, verify it with PyJWT + your Supabase JWT secret, and compare the `sub` claim against the `user_id` in the body. PyJWT is already in requirements.

**No rate limiting (MEDIUM)**  
`POST /api/waitlist` and `POST /api/investors` can be spammed without limit. This inflates user counts and wastes Supabase quota.

*Fix:* Add `slowapi` (a FastAPI-native rate limiter based on `limits`) — e.g., 5 req/minute per IP on write endpoints.

**`/api/profile/bind-user` deletes rows without auth (HIGH)**  
This endpoint deletes the anonymous user row from `users` and reassigns their waitlist entries. If called with a valid `anonymous_id` (even accidentally), it causes permanent data loss.

*Fix:* Same JWT verification as above — only the authenticated user matching `new_user_id` should be able to call this.

**No input length caps (LOW)**  
Free-text fields (`ai_question`, `problematic`, `message`) have no `max_length` validation. Long payloads waste DB storage and could cause issues in admin views.

*Fix:* Add `@field_validator` or Pydantic `Field(max_length=2000)` on open-text fields.

**CORS is fully open in development (INFORMATIONAL)**  
`allow_origins=["*"]` in dev is intentional and safe locally. Confirm `ENVIRONMENT=production` is set in Railway Variables so production always uses `[settings.frontend_url]`.

**Service key in Railway Variables (MANAGED RISK)**  
The `SUPABASE_SERVICE_KEY` is a secret that bypasses RLS. It's stored in Railway's encrypted secrets vault — never in source. Do not log it (the startup check in `main.py` already truncates it to 30 chars).

---

## Environment Variables

| Variable | Default | Required in prod | Notes |
|---|---|---|---|
| `PORT` | `8000` | Injected by Railway | Do not set manually on Railway |
| `ENVIRONMENT` | `development` | `production` | Locks CORS to `FRONTEND_URL` |
| `FRONTEND_URL` | `http://localhost:5173` | Your Vercel/custom domain | No trailing slash |
| `SUPABASE_URL` | `""` | Yes | Project URL from Settings → API |
| `SUPABASE_SERVICE_KEY` | `""` | Yes | Service role key — bypasses RLS |
| `RESEND_API_KEY` | `""` | When email hook is live | From resend.com dashboard |
| `SUPABASE_HOOK_SECRET` | `""` | When email hook is live | Auth → Hooks → reveal secret |
| `SUPABASE_WEBHOOK_SECRET` | `""` | When DB webhooks are live | Any string you set in Supabase webhook headers |
| `INTERNAL_API_KEY` | `""` | When internal routes are live | Secret checked in `X-Internal-Key` header for `super_admin`/`internal_dev`/`internal_team` routes |
| `GEMINI_API_KEY` | `""` | When AI endpoints are live | Google Gemini API key — used by scan, summarize, analyze, and template import endpoints |

---

## Setup (local)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in SUPABASE_URL + SUPABASE_SERVICE_KEY
python main.py
```

Server: `http://localhost:8000` — docs at `http://localhost:8000/docs`.

---

## Adding a New Module

1. Create `app/<feature>/` with `__init__.py`, `models.py`, `router.py`
2. In `main.py`, add:
   ```python
   from app.<feature>.router import router as <feature>_router
   app.include_router(<feature>_router, prefix="/api/<feature>")
   ```
3. Done — `landing/` is untouched.

**Planned modules (not yet implemented):**

| Module | Prefix | What it will do |
|---|---|---|
| `FyTic_app` | `/api/app` | Core SaaS: document management, case tracking, AI search |
| `email` | `/api/hooks` | Resend-powered transactional email via Supabase Send Email hook |
| `billing` | `/api/billing` | Stripe subscription management |
| `ai` | `/api/ai` | Gemini-powered legal research, summarization, drafting |
