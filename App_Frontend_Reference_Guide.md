# FyTic App — Frontend API Spec

> Endpoints the frontend app needs from the FastAPI backend.  
> Organized by resource domain. Each entry notes which view(s) use it.
>
> **Frontend App Base URL:** `https://app.fytic.tech`  
> **Backend Base URL:** `https://backend-mvp-production-8e67.up.railway.app`  
> **Landing-page API prefix:** `/api` — existing, live in production  
> **App API prefix:** `/api/app/v1` — versioned + namespaced; all new app endpoints go here

---

## How authentication works (Supabase, not custom)

FyTic uses **Supabase Auth** — there are no `/api/app/v1/auth/login`, `/auth/logout`, or `/auth/refresh` endpoints in the FastAPI backend. The frontend handles authentication entirely through the Supabase JavaScript SDK:

```ts
// Email/password login — handled by Supabase JS, not our backend
supabase.auth.signInWithPassword({ email, password })

// Google OAuth — handled by Supabase JS
supabase.auth.signInWithOAuth({ provider: "google" })

// Logout
supabase.auth.signOut()

// Token refresh — handled automatically by Supabase JS
```

Supabase issues a signed JWT (access token) on login. The frontend sends this token to our FastAPI backend with every request:

```
Authorization: Bearer <supabase_access_token>
```

The backend verifies the JWT using PyJWT + the Supabase JWT secret, extracts the user's `id` (`sub` claim), then queries the `users` table to get `org_id` and `role`.

> **Important:** `org_id` and `role` are NOT embedded in Supabase's default JWT claims. The backend must look them up from the `users` table on every authenticated request (or cache them per request).

---

## Security model

### Tenant isolation

All data (documents/contracts, clients, templates, org library, user library) is scoped to the user's organization. The backend must filter every query by the `org_id` from the `users` table — **never trust an `org_id` from the request body or query string.** A user from org A must never be able to read or write data from org B.

### Roles

There are six roles. The first four are org-scoped (regular users); the last two are platform-wide and restricted to the internal FyTic frontend.

| Role (`users.role`) | Credential requirement | Scope | Access |
|---|---|---|---|
| `super_admin` | Supabase JWT + `X-Internal-Key` header | Platform | Full access to all orgs, all tables, all service ops |
| `admin` | Supabase JWT | Org | Full CRUD on org content, invite/remove/update org members |
| `member` | Supabase JWT | Org | Full CRUD on documents, clients, templates, org view, library, scan |
| `limited` | Supabase JWT | Org | Read + create only — no delete, no member management. Also used for visitors on shared links |
| `internal_dev` | Supabase JWT + `X-Internal-Key` header | Platform | FyTic developer access — internal admin frontend |
| `internal_team` | Supabase JWT + `X-Internal-Key` header | Platform | FyTic team access (support, ops) — internal admin frontend |

**Two-factor check for internal roles:** routes that require `super_admin`, `internal_dev`, or `internal_team` must validate BOTH the Supabase JWT role AND a matching `X-Internal-Key` header (value stored in `INTERNAL_API_KEY` Railway env var). Role alone is not sufficient.

Role annotations used in this doc:

- `🔓 Public` — no auth token needed
- `🔒 Any member` — any org-scoped authenticated user (`admin`, `member`, `limited`)
- `📖 Read-only for limited` — `limited` role can only GET, not mutate
- `🔑 Admin` — requires `role = 'admin'` or `role = 'super_admin'`
- `🏠 Internal` — requires internal role (`super_admin`, `internal_dev`, or `internal_team`) + `X-Internal-Key`

### What to protect against

- Return `404` (not `405`) for routes that don't exist — leaks nothing about your surface area
- Never expose stack traces, API keys, or internal paths in error responses in production
- Validate resource ownership (`org_id`) before returning any data — don't rely on IDs being random
- Supabase access tokens expire in ~1 hour; Supabase JS handles refresh automatically
- Never accept `org_id` or `role` from request body/query params — always derive from `users` table after JWT verification

---

## Backend architecture

The app API (`/api/app/v1`) lives inside the same FastAPI app as the landing API (`/api`). New domains are added as new router modules under `app/FyTic_app/` (see `CLAUDE_st4rtup.md`).

**Stack:**
- FastAPI (router + Pydantic models)
- Supabase Python client (`supabase-py`) — no ORM, direct table queries
- Database: Supabase (PostgreSQL). All tables documented in `DB_Guide_st4rtup.md` — **that file is the source of truth for table names and schemas**
- Auth: JWT verification via PyJWT using the Supabase JWT secret; internal routes also require `X-Internal-Key`

**Pattern per domain:**
- `router.py` — HTTP boundary: validates request shape, calls service, returns response
- `service.py` (to be added per domain) — business logic, DB queries, assembles responses
- `models.py` — Pydantic schemas for request/response shapes

**DB table → API domain mapping:**

| API domain | DB table(s) | Notes |
|---|---|---|
| `/api/app/v1/me` | `users` | Single row by JWT `sub` |
| `/api/app/v1/clients` | `clients` | Scoped by `org_id` |
| `/api/app/v1/documents` | `contracts` | API calls them "documents"; DB table is `contracts` — see below |
| `/api/app/v1/templates` | `templates` | `source='fytic'` (global) + `source='user'` (org-scoped) |
| `/api/app/v1/template-groups` | derived from `DISTINCT group_name FROM templates` | No separate table needed |
| `/api/app/v1/users` | `users` filtered by `org_id` | Not a separate `org_members` table |
| `/api/app/v1/org/items` | `clients` (kind=client) + `org_library` (kind=folder/file) | See org section note below |
| `/api/app/v1/org/sections` | derived from `DISTINCT split_part(folder_path,'/',1) FROM org_library` | Sections are visual labels, not a DB table — see note below |
| `/api/app/v1/library/items` | `user_library` | |
| `/api/app/v1/library/sections` | derived from `DISTINCT split_part(folder_path,'/',1) FROM user_library` | Same as org sections — derived from folder_path |
| `/api/app/v1/law-db` | `fytic_library` | Grouped by `group_name` at response time |

**AI & Content Processing:**

- **Template content format:** stored as `jsonb` array of markdown strings — one element per paragraph/heading/block. No monolithic text blobs. Documents inherit this structure.
- **Variable system:** variables follow `{{VARIABLE_NAME}}` syntax inside content blocks. On every template save or import, the backend runs a regex over all blocks and writes unique names into `detected_variables`. When a document is created from a template, `detected_variables` becomes the keyset of an empty `variables: {}` map. `PATCH /documents/{id}/variables` merges in new values. `progress` (percent filled, missing keys) is computed on every response, never stored.
- **Rendered content:** `GET /documents/{id}` returns both `raw_content` (placeholders intact) and `rendered_content` (placeholders substituted server-side from the current `variables` map). Empty variables render as blank strings. Substitution is never stored.
- **Template import pipeline:** (1) extract raw text from PDF/DOCX/TXT → (2) send to Gemini with a prompt asking to reformat as markdown blocks, detect `{{VARIABLE}}` placeholders, identify signatories, flag risk clauses, suggest a name → (3) parse AI JSON response → (4) save `templates` row. Response includes `detected_variables`, `signatories`, `risk_clauses`, `suggested_name`.
- **Summarize & Analyze:** take the document's current `rendered_content`, send to Gemini with role-specific prompts. Summarize returns plain-language Spanish summary + key points. Analyze returns structured sections (parties, obligations, risks, benefits, clauses). Neither result is stored.
- **Scan / process:** same text-extraction step as template import, but returns extracted markdown + analysis directly without saving anything.
- **Signatory system:** signatories are defined on the template (`key`, `label`, optional `nameVar`). Signatures stored on the document as `key → base64 PNG string`. Progress tracks how many signatory keys have a non-empty entry.
- **PDF / DOCX export:** backend converts `rendered_content` (markdown blocks) into the target format using a document library (`python-docx` for DOCX, `fpdf2` for PDF). Result is streamed as a binary `FileResponse` — nothing saved to disk.
- **Search:** `ILIKE` substring match on document titles, client names, and template names, scoped to `org_id`. Returns two arrays: `documents` and `templates`.
- **AI provider:** Google Gemini (`google-genai` SDK, model `gemini-2.5-flash`). Env var: `GEMINI_API_KEY`.

**"Documents" vs "contracts" — the complete picture:**

- A `templates` row is a blank boilerplate: raw content lines with `{{VARIABLE}}` placeholders, no client, no filled values. The "Plantillas" tab shows these.
- A `contracts` row is what happens when a user picks a template and a client and clicks "crear contrato." The backend copies the template's content, associates it with the client, and creates the `contracts` row with an empty `variables` map. The user then fills in the variables. The "Contratos" tab shows these.
- The `type` field on a `contracts` row (`contract | external | machote`) is a display label the frontend uses to filter and categorize — all are rows in the same `contracts` table.
- When ContractView opens, it calls `GET /api/app/v1/documents/{id}` which returns the `contracts` row plus the original template's raw content, so the frontend can render the filled version by substituting variables client-side.
- The API uses "document(s)" in all paths and response keys. Backend code always uses the `contracts` table name.

---

## Quick reference

| Method | Path | Role | Used by |
|---|---|---|---|
| `GET` | `/api/app/v1/me` | 🔒 Any member | Settings → Perfil |
| `PATCH` | `/api/app/v1/me` | 🔒 Any member | Settings → Perfil |
| `GET` | `/api/app/v1/clients` | 🔒 Any member | HomeView, ContractView |
| `POST` | `/api/app/v1/clients` | 📖 Read-only for limited | HomeView |
| `GET` | `/api/app/v1/clients/{id}` | 🔒 Any member | HomeView |
| `PATCH` | `/api/app/v1/clients/{id}` | 📖 Read-only for limited | HomeView |
| `DELETE` | `/api/app/v1/clients/{id}` | 🔑 Admin | HomeView |
| `GET` | `/api/app/v1/documents` | 🔒 Any member | HomeView |
| `POST` | `/api/app/v1/documents` | 📖 Read-only for limited | HomeView |
| `GET` | `/api/app/v1/documents/{id}` | 🔒 Any member | ContractView |
| `PATCH` | `/api/app/v1/documents/{id}` | 📖 Read-only for limited | ContractView, HomeView |
| `DELETE` | `/api/app/v1/documents/{id}` | 🔑 Admin | HomeView |
| `PATCH` | `/api/app/v1/documents/{id}/variables` | 📖 Read-only for limited | ContractView |
| `POST` | `/api/app/v1/documents/{id}/signatures` | 📖 Read-only for limited | ContractView |
| `DELETE` | `/api/app/v1/documents/{id}/signatures/{key}` | 📖 Read-only for limited | ContractView |
| `POST` | `/api/app/v1/documents/{id}/summarize` | 🔒 Any member | ContractView |
| `POST` | `/api/app/v1/documents/{id}/analyze` | 🔒 Any member | ContractView |
| `POST` | `/api/app/v1/documents/{id}/share` | 🔒 Any member | ContractView |
| `POST` | `/api/app/v1/documents/{id}/copy-as-template` | 📖 Read-only for limited | ContractView |
| `GET` | `/api/app/v1/templates` | 🔒 Any member | HomeView |
| `POST` | `/api/app/v1/templates/import` | 📖 Read-only for limited | HomeView |
| `PATCH` | `/api/app/v1/templates/{id}` | 📖 Read-only for limited | HomeView |
| `DELETE` | `/api/app/v1/templates/{id}` | 🔑 Admin | HomeView |
| `GET` | `/api/app/v1/template-groups` | 🔒 Any member | HomeView |
| `POST` | `/api/app/v1/template-groups` | 🔑 Admin | HomeView |
| `PATCH` | `/api/app/v1/template-groups/{name}` | 🔑 Admin | HomeView |
| `DELETE` | `/api/app/v1/template-groups/{name}` | 🔑 Admin | HomeView |
| `POST` | `/api/app/v1/scan/process` | 🔒 Any member | ScanView |
| `GET` | `/api/app/v1/search` | 🔒 Any member | ScanView |
| `GET` | `/api/app/v1/users` | 🔒 Any member | Settings → Equipo |
| `POST` | `/api/app/v1/users` | 🔑 Admin | Settings → Equipo |
| `PATCH` | `/api/app/v1/users/{id}` | 🔑 Admin | Settings → Equipo |
| `DELETE` | `/api/app/v1/users/{id}` | 🔑 Admin | Settings → Equipo |
| `GET` | `/api/app/v1/org/items` | 🔒 Any member | OrgView |
| `POST` | `/api/app/v1/org/items` | 📖 Read-only for limited | OrgView |
| `PATCH` | `/api/app/v1/org/items/{id}` | 📖 Read-only for limited | OrgView |
| `DELETE` | `/api/app/v1/org/items/{id}` | 🔑 Admin | OrgView |
| `GET` | `/api/app/v1/org/sections` | 🔒 Any member | OrgView |
| `POST` | `/api/app/v1/org/sections` | 🔑 Admin | OrgView |
| `PATCH` | `/api/app/v1/org/sections/{id}` | 🔑 Admin | OrgView |
| `DELETE` | `/api/app/v1/org/sections/{id}` | 🔑 Admin | OrgView |
| `GET` | `/api/app/v1/library/items` | 🔒 Any member | LibraryView |
| `POST` | `/api/app/v1/library/items` | 🔒 Any member | LibraryView |
| `POST` | `/api/app/v1/library/upload` | 🔒 Any member | LibraryView |
| `PATCH` | `/api/app/v1/library/items/{id}` | 🔒 Any member | LibraryView |
| `DELETE` | `/api/app/v1/library/items/{id}` | 🔒 Any member | LibraryView |
| `GET` | `/api/app/v1/library/sections` | 🔒 Any member | LibraryView |
| `POST` | `/api/app/v1/library/sections` | 🔒 Any member | LibraryView |
| `PATCH` | `/api/app/v1/library/sections/{id}` | 🔒 Any member | LibraryView |
| `DELETE` | `/api/app/v1/library/sections/{id}` | 🔒 Any member | LibraryView |
| `GET` | `/api/app/v1/law-db` | 🔒 Any member | DbView |

---

## Current user (`/me`)

> Used by: Settings → Perfil, Cuenta, Tokens, Referidos  
> DB table: `users`

### `GET /api/app/v1/me` — 🔒 Any member

The backend extracts `user_id` from the JWT `sub` claim, then fetches the row from `users` joined with `organizations` for the org name and `plans` for token limits.

**Response `200`**
```json
{
  "id": "uuid-from-supabase-auth",
  "email": "luism@despacho.mx",
  "fullName": "Luis M. Delgadillo",
  "organization": "FyTic Legal Services",
  "role": "admin",
  "position": "Fundador",
  "practiceArea": "Derecho Corporativo",
  "phone": "+52 55 1234 5678",
  "loginMethod": "google",
  "dateCreated": "2024-03-15",
  "referralCode": "abc123de",
  "referredBy": null,
  "surveyCompleted": true,
  "tokensUsed": 12450,
  "tokenLimit": 50000
}
```

**DB field mapping:**

| Response field | DB column |
|---|---|
| `id` | `users.id` |
| `email` | `users.email` |
| `fullName` | `users.full_name` |
| `organization` | `organizations.name` (via `users.org_id`) |
| `role` | `users.role` — one of `super_admin`, `admin`, `member`, `limited`, `internal_dev`, `internal_team` |
| `position` | `users.position` |
| `practiceArea` | `users.practice_area` |
| `phone` | `users.phone` |
| `loginMethod` | `users.auth_provider` |
| `referralCode` | `users.ref_code` |
| `referredBy` | `users.referred_by` |
| `surveyCompleted` | `users.survey_completed` |
| `tokensUsed` | `users.tokens_used_today` |
| `tokenLimit` | `plans.tokens_per_day` (via `subscriptions.plan_id`) |

---

### `PATCH /api/app/v1/me` — 🔒 Any member

Users can only edit their own profile fields. Role and org membership cannot be changed here — those go through `/api/app/v1/users/{id}` (admin only).

**Body** — all fields optional
```json
{
  "fullName": "Luis Delgadillo",
  "position": "CEO",
  "practiceArea": "Derecho Corporativo",
  "phone": "+52 55 9999 0000"
}
```

**Response `200`** — same shape as `GET /api/app/v1/me`

---

## Clients

> Used by: HomeView (Contratos tab), ContractView (client picker)  
> DB table: `clients`

### `GET /api/app/v1/clients` — 🔒 Any member

| Query param | Type | Description |
|---|---|---|
| `with_docs` | bool | Embed full document list per client (default: false) |

**Response `200`**
```json
{
  "clients": [
    {
      "id": "uuid",
      "name": "Constructora Ramírez S.A. de C.V.",
      "rfc": "CRA123456ABC",
      "initials": "CR",
      "accentColor": "#6366f1",
      "email": "contacto@ramirez.mx",
      "contact": "Ing. Ramírez",
      "caseDescription": "Contratación de servicios legales",
      "document_count": 2
    }
  ]
}
```

> `email` → `clients.contact_email`, `contact` → `clients.contact_name`, `document_count` is computed from `contracts` rows where `client_id` matches and `deleted_at IS NULL`.

---

### `GET /api/app/v1/clients/{id}` — 🔒 Any member

**Response `200`**
```json
{
  "id": "uuid",
  "name": "Constructora Ramírez S.A. de C.V.",
  "rfc": "CRA123456ABC",
  "initials": "CR",
  "accentColor": "#6366f1",
  "email": "contacto@ramirez.mx",
  "contact": "Ing. Ramírez",
  "caseDescription": "...",
  "documents": [
    {
      "id": "uuid",
      "templateId": "uuid",
      "title": "Contrato de Servicios",
      "type": "contract",
      "status": "active",
      "createdAt": "2024-03-15T10:00:00Z",
      "variables": { "NOMBRE_CLIENTE": "Constructora Ramírez" },
      "signatures": {}
    }
  ]
}
```

**Errors:** `404`

---

### `POST /api/app/v1/clients` — 📖 Read-only for limited

**Body**
```json
{
  "name": "Empresa XYZ S.A.",
  "rfc": "EXY123456ABC",
  "address": "Av. Reforma 100, CDMX",
  "contact": "Lic. González",
  "email": "gonzalez@xyz.mx",
  "initials": "EX",
  "accentColor": "#6366f1",
  "caseDescription": "Consultoría corporativa"
}
```
Only `name` is required. Backend auto-sets `org_id` from the JWT — never accept `org_id` from the body.

**Response `201`** `{ "client": Client }`

---

### `PATCH /api/app/v1/clients/{id}` — 📖 Read-only for limited

Same fields as `POST`, all optional.

**Response `200`** `{ "client": Client }`  **Errors:** `404`

---

### `DELETE /api/app/v1/clients/{id}` — 🔑 Admin

Soft-deletes the client (`deleted_at = now()`). Cascades: also soft-deletes the client's contracts and org_library rows.

**Response `204`**  **Errors:** `404`

---

## Documents

> Used by: HomeView (Contratos tab), ContractView  
> DB table: `contracts` — the frontend calls these "documents" throughout

### `GET /api/app/v1/documents` — 🔒 Any member

| Query param | Type | Description |
|---|---|---|
| `client_id` | string | Filter by client |
| `status` | `draft\|active\|signed\|archived` | Filter by status |
| `type` | `contract\|template\|external\|machote` | Filter by document type |
| `search` | string | Full-text search on title and client name |

**Response `200`**
```json
{
  "documents": [
    {
      "id": "uuid",
      "templateId": "uuid",
      "clientId": "uuid",
      "clientName": "Constructora Ramírez",
      "clientInitials": "CR",
      "clientAccentColor": "#6366f1",
      "title": "Contrato de Servicios",
      "type": "contract",
      "status": "active",
      "createdAt": "2024-03-15T10:00:00Z",
      "progress": {
        "total_vars": 5,
        "filled_vars": 4,
        "percent": 80,
        "missing": ["FIRMA_FECHA"],
        "total_sigs": 2,
        "filled_sigs": 1
      }
    }
  ],
  "total": 1
}
```

> `progress` is computed from `contracts.variables` (count non-empty values) and `contracts.signatures` (count non-empty keys). Computed at response time — not stored.

---

### `POST /api/app/v1/documents` — 📖 Read-only for limited

**Body**
```json
{
  "clientId": "uuid",
  "templateId": "uuid",
  "title": "Contrato de Servicios — Ramírez 2024",
  "type": "contract",
  "variables": { "NOMBRE_CLIENTE": "Constructora Ramírez" }
}
```
`type` and `variables` are optional. Backend auto-sets `org_id` and `created_by` from the JWT.

**Response `201`** `{ "document": DocumentListItem }`  **Errors:** `404` if client or template not found

---

### `GET /api/app/v1/documents/{id}` — 🔒 Any member

Returns the full document including template content for rendering. Backend joins `contracts` + `templates` and renders `content` by substituting `variables`.

**Response `200`**
```json
{
  "document": {
    "id": "uuid",
    "templateId": "uuid",
    "clientId": "uuid",
    "clientName": "Constructora Ramírez",
    "title": "Contrato de Servicios",
    "type": "contract",
    "status": "active",
    "createdAt": "2024-03-15T10:00:00Z",
    "variables": { "NOMBRE_CLIENTE": "Constructora Ramírez" },
    "signatures": { "CLIENTE": "data:image/png;base64,..." }
  },
  "template": {
    "id": "uuid",
    "name": "Servicios Legales",
    "signatories": [
      { "key": "CLIENTE", "label": "Cliente", "nameVar": "NOMBRE_CLIENTE" }
    ],
    "raw_content": ["# Contrato de Servicios", "El cliente **{{NOMBRE_CLIENTE}}**..."]
  },
  "rendered_content": ["# Contrato de Servicios", "El cliente **Constructora Ramírez**..."],
  "progress": {
    "total_vars": 5, "filled_vars": 5, "percent": 100,
    "missing": [], "total_sigs": 1, "filled_sigs": 1
  }
}
```

**Errors:** `404`

---

### `PATCH /api/app/v1/documents/{id}` — 📖 Read-only for limited

**Body** — all optional
```json
{
  "title": "Nuevo título",
  "status": "signed",
  "client_id": "uuid",
  "doc_type": "contract"
}
```

**Response `200`** `{ "document": DocumentListItem }`  **Errors:** `404`

---

### `DELETE /api/app/v1/documents/{id}` — 🔑 Admin

Soft-deletes (`contracts.deleted_at = now()`).

**Response `204`**  **Errors:** `404`

---

### `PATCH /api/app/v1/documents/{id}/variables` — 📖 Read-only for limited

Merges new values into `contracts.variables` — does not overwrite keys not mentioned.

**Body**
```json
{ "variables": { "NOMBRE_CLIENTE": "Constructora Ramírez", "FECHA": "15 de enero de 2025" } }
```

**Response `200`**
```json
{
  "variables": { "NOMBRE_CLIENTE": "Constructora Ramírez", "FECHA": "15 de enero de 2025", "OTRA_VAR": "" },
  "progress": { "total_vars": 3, "filled_vars": 2, "percent": 66, "missing": ["OTRA_VAR"], "total_sigs": 1, "filled_sigs": 0 }
}
```

---

### `POST /api/app/v1/documents/{id}/signatures` — 📖 Read-only for limited

Adds or replaces a signatory's signature in `contracts.signatures`.

**Body**
```json
{
  "signatory_key": "CLIENTE",
  "signature_data": "data:image/png;base64,iVBORw0KGgo..."
}
```

**Response `200`** `{ "signatures": { "CLIENTE": "data:image/png;base64,..." } }`

---

### `DELETE /api/app/v1/documents/{id}/signatures/{key}` — 📖 Read-only for limited

Removes one key from `contracts.signatures`.

**Response `200`** `{ "signatures": { ...remaining } }`

---

### `POST /api/app/v1/documents/{id}/summarize` — 🔒 Any member

AI: generate a Spanish plain-language summary using Gemini. Token quota check is not yet enforced (hardcoded response for now).

**Response `200`**
```json
{
  "summary": "El presente contrato establece los términos de la prestación de servicios...",
  "key_points": ["Duración: 12 meses", "Honorarios: $50,000 MXN"],
  "word_count": 1240
}
```

---

### `POST /api/app/v1/documents/{id}/analyze` — 🔒 Any member

AI: structured legal analysis using Gemini. Token quota not yet enforced.

**Response `200`**
```json
{
  "sections": [
    { "type": "benefits",  "title": "Beneficios",      "items": ["Cláusula de confidencialidad clara"] },
    { "type": "risks",     "title": "Riesgos",          "items": ["Penalización excesiva por incumplimiento"] },
    { "type": "clauses",   "title": "Cláusulas clave",  "items": ["Vigencia: artículo 4°"] }
  ]
}
```

---

### `POST /api/app/v1/documents/{id}/share` — 🔒 Any member

**Body**
```json
{
  "method": "pdf",
  "email": "cliente@empresa.mx",
  "message": "Adjunto el contrato."
}
```

| `method` | Response |
|---|---|
| `"link"` | `{ "method": "link", "url": "https://..." }` |
| `"md"` | `{ "method": "md", "content": "# Contrato..." }` |
| `"docx"` | Binary file stream (`application/vnd.openxmlformats-officedocument...`) |
| `"pdf"` | Binary file stream (`application/pdf`) |
| `"email"` | `{ "method": "email", "recipient": "cliente@empresa.mx" }` — uses Resend |

---

### `POST /api/app/v1/documents/{id}/copy-as-template` — 📖 Read-only for limited

Promotes a contract to a user template. Inserts into `templates` with `source = 'user'` and `source_contract_id` pointing to this document.

**Body**
```json
{ "name": "Mi plantilla de NDA", "group": "Corporativo" }
```

**Response `200`** `{ "template": UserTemplate }`

---

## Templates

> Used by: HomeView (Plantillas tab)  
> DB table: `templates`

### `GET /api/app/v1/templates` — 🔒 Any member

Returns two sets: FyTic system templates (`source = 'fytic'`, `org_id = NULL`) and this org's user templates (`source = 'user'`, `org_id = <org_id>`).

| Query param | Type | Description |
|---|---|---|
| `group` | string | Filter user templates by `group_name` |

**Response `200`**
```json
{
  "fytic": [
    {
      "id": "uuid",
      "name": "Servicios Legales",
      "signatories": [{ "key": "CLIENTE", "label": "Cliente", "nameVar": "NOMBRE_CLIENTE" }],
      "content": ["# Contrato de Servicios", "El cliente **{{NOMBRE_CLIENTE}}**..."],
      "group": "General",
      "source": "fytic"
    }
  ],
  "user": [
    {
      "id": "uuid",
      "name": "Mi NDA",
      "group": "Corporativo",
      "content": ["..."],
      "signatories": [],
      "detected_variables": ["NOMBRE_CLIENTE", "FECHA"],
      "source": "user"
    }
  ]
}
```

> `group` → `templates.group_name`

---

### `POST /api/app/v1/templates/import` — 📖 Read-only for limited

Upload a file and extract it as a user template using Gemini AI. Token quota not yet enforced.

**Form data** (multipart)
- `file` — uploaded file (PDF, DOCX, or TXT)
- `name` (query param, required) — template name
- `group` (query param, optional) — group to assign

**Response `200`**
```json
{
  "template": {
    "id": "uuid",
    "name": "Mi NDA",
    "group": "Corporativo",
    "source": "imported",
    "signatories": [{ "key": "CLIENTE", "label": "Cliente", "nameVar": "NOMBRE_CLIENTE" }],
    "content": ["# Acuerdo de Confidencialidad", "..."],
    "detected_variables": ["NOMBRE_CLIENTE", "FECHA"],
    "suggested_name": "NDA Corporativo",
    "risk_clauses": ["Cláusula 5 — penalización sin tope"]
  }
}
```

---

### `PATCH /api/app/v1/templates/{id}` — 📖 Read-only for limited

Update a user template's name or group. FyTic built-ins (`source = 'fytic'`) cannot be modified — return `403`.

**Body** — at least one required
```json
{ "name": "Nuevo nombre", "group": "Corporativo" }
```

**Response `200`** `{ "template": UserTemplate }`  **Errors:** `404`, `403` if FyTic template

---

### `DELETE /api/app/v1/templates/{id}` — 🔑 Admin

Soft-deletes (`templates.deleted_at = now()`). FyTic built-ins cannot be deleted — return `403`.

**Response `204`**  **Errors:** `404`, `403` if FyTic template

---

## Template groups

> Used by: HomeView (Plantillas tab)  
> Groups are derived from distinct `templates.group_name` values — no separate DB table. Managing groups means renaming or clearing `group_name` on the matching template rows.

### `GET /api/app/v1/template-groups` — 🔒 Any member

**Response `200`** `{ "groups": ["General", "Corporativo", "Laboral"] }`

> Backend: `SELECT DISTINCT group_name FROM templates WHERE org_id = <org_id> AND deleted_at IS NULL`

---

### `POST /api/app/v1/template-groups` — 🔑 Admin

Creates a group name — effectively a no-op in the DB until templates are assigned to it. Or optionally rejects if no templates are being assigned simultaneously.

**Body** `{ "name": "Fiscal" }`

**Response `201`** `{ "groups": ["General", "Corporativo", "Fiscal"] }`

---

### `PATCH /api/app/v1/template-groups/{name}` — 🔑 Admin

Renames the group: updates `group_name` on all matching template rows.

**Body** `{ "new_name": "Fiscal y Tributario" }`

**Response `200`** `{ "groups": [...updatedList] }`  **Errors:** `404` if group doesn't exist

---

### `DELETE /api/app/v1/template-groups/{name}` — 🔑 Admin

Sets `group_name = ''` on all templates in the deleted group.

**Response `204`**  **Errors:** `404`

---

## Scan & Search

> Used by: ScanView  
> AI provider: Google Gemini (`google-genai` SDK). Token quota is not yet enforced (hardcoded for now)

### `POST /api/app/v1/scan/process` — 🔒 Any member

Upload any document, get AI-structured analysis via Gemini. Token quota not yet enforced.

**Form data** (multipart) — `file`: the uploaded document

**Response `200`**
```json
{
  "filename": "contrato.pdf",
  "markdown": "# Contrato\n\nEl presente contrato...",
  "analysis": {
    "sections": [
      { "type": "parties",      "title": "Partes",       "items": ["Vendedor: Empresa A", "Comprador: Empresa B"] },
      { "type": "obligations",  "title": "Obligaciones", "items": ["Entregar en 30 días"] },
      { "type": "risks",        "title": "Riesgos",      "items": ["Sin cláusula de limitación de daños"] }
    ]
  }
}
```

---

### `GET /api/app/v1/search` — 🔒 Any member

Full-text search across documents (`contracts`) and user templates, scoped to the user's org.

| Query param | Type | Required | Description |
|---|---|---|---|
| `q` | string | ✅ | Search query |
| `client_id` | string | — | Restrict document results to this client |

**Response `200`**
```json
{
  "documents": [ ...DocumentListItem[] ],
  "templates": [ ...UserTemplate[] ]
}
```

---

## Org members

> Used by: Settings → Equipo  
> DB table: `users` filtered by `org_id`

### `GET /api/app/v1/users` — 🔒 Any member

**Response `200`**
```json
{
  "members": [
    {
      "id": "uuid",
      "orgId": "uuid",
      "email": "luism@despacho.mx",
      "fullName": "Luis M. Delgadillo",
      "role": "admin",
      "position": "Fundador",
      "status": "active",
      "avatarInitials": "LD",
      "createdAt": "2025-01-01T00:00:00Z",
      "updatedAt": "2025-01-01T00:00:00Z"
    }
  ]
}
```

> `avatarInitials` is computed from `full_name`. `status` derives from `users.is_active` (`true` → `"active"`, `false` → `"inactive"`) plus a `"pending"` state for invited-but-unconfirmed members. Only org-scoped roles (`admin`, `member`, `limited`) appear here — internal roles are not org members.

---

### `POST /api/app/v1/users` — 🔑 Admin

Invite a member to the org. Sends an invitation email via Resend (pending implementation). Status defaults to `"pending"` until the invitation is accepted.

**Body**
```json
{
  "email": "nuevo@despacho.mx",
  "full_name": "María López",
  "role": "member",
  "position": "Abogada Laboral"
}
```
`role` defaults to `"member"` if omitted. Valid org-scoped roles: `admin | member | limited`. Internal roles (`super_admin`, `internal_dev`, `internal_team`) cannot be assigned through this endpoint.

**Response `201`** `{ "member": OrgMember }`

---

### `PATCH /api/app/v1/users/{id}` — 🔑 Admin

**Body** — all optional
```json
{
  "full_name": "María López Ruiz",
  "role": "admin",
  "position": "Socia Laboral",
  "status": "active"
}
```
Valid statuses: `active | pending | inactive`. Valid roles: `admin | member | limited`. Internal roles cannot be set through this endpoint.

**Response `200`** `{ "member": OrgMember }`  **Errors:** `404`

---

### `DELETE /api/app/v1/users/{id}` — 🔑 Admin

Soft-deletes the member from the org (`users.deleted_at = now()`). An `admin` cannot delete another `admin` through this endpoint — that requires `super_admin`. Internal roles (`super_admin`, `internal_dev`, `internal_team`) cannot be removed through this endpoint.

**Response `204`**  **Errors:** `404`, `403` if attempting to remove an admin or internal-role user

---

## Organization file system (`/org/*`)

> Used by: OrgView  
> Two-level file manager: sections contain clients and folders; folders can be navigated into.  
> DB tables: `clients` (for `kind = "client"` items), `org_library` (for `kind = "folder"` and `kind = "file"` items)
>
> **Sections model:** Sections are a visual-only grouping — there is no `org_sections` DB table. Sections are derived at response time from the `folder_path` field in `org_library`: the first path component is the section name. E.g., `folder_path = 'fiscal/2024'` → section `"fiscal"`. Items with `folder_path = ''` belong to the default section (`"General"`). Creating/renaming a section updates `folder_path` on the matching items. The path is the source of truth; sections are a computed label from it.

### `GET /api/app/v1/org/items` — 🔒 Any member

| Query param | Type | Required |
|---|---|---|
| `parent_id` | string | ✅ — `"root"` or a folder item id |

**Response `200`**
```json
{
  "items": [
    {
      "id": "uuid",
      "parentId": "root",
      "sectionId": "os-general",
      "kind": "client",
      "name": "Empresa Alpha",
      "icon": "briefcase",
      "color": "#6366f1",
      "rfc": "EAL123456ABC",
      "createdAt": "2025-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "parentId": "root",
      "sectionId": "os-general",
      "kind": "folder",
      "name": "Proyectos 2025",
      "icon": "folder",
      "color": "#f59e0b",
      "createdAt": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

### `POST /api/app/v1/org/items` — 📖 Read-only for limited

**Body**
```json
{
  "parentId": "root",
  "sectionId": "os-general",
  "kind": "client",
  "name": "Empresa Beta",
  "icon": "briefcase",
  "color": "#6366f1",
  "rfc": "EBE123456ABC"
}
```
`kind` is one of `client | folder | file`. `rfc`, `icon`, `color` are optional.

**Response `201`** `{ "item": OrgItem }`

---

### `PATCH /api/app/v1/org/items/{id}` — 📖 Read-only for limited

**Body** — all optional
```json
{ "name": "Nuevo nombre", "sectionId": "os-activos", "color": "#10b981" }
```

**Response `200`** `{ "item": OrgItem }`  **Errors:** `404`

---

### `DELETE /api/app/v1/org/items/{id}` — 🔑 Admin

Soft-deletes. Cascades to child items if the item is a folder.

**Response `204`**  **Errors:** `404`

---

### `GET /api/app/v1/org/sections` — 🔒 Any member

| Query param | Type | Required |
|---|---|---|
| `parent_id` | string | ✅ |

**Response `200`**
```json
{
  "sections": [
    { "id": "os-general",  "parentId": "root", "name": "General",  "isDefault": true },
    { "id": "os-activos",  "parentId": "root", "name": "Activos",  "isDefault": false }
  ]
}
```

---

### `POST /api/app/v1/org/sections` — 🔑 Admin

**Body** `{ "parentId": "root", "name": "Inactivos" }`

**Response `201`** `{ "section": OrgSection }`

---

### `PATCH /api/app/v1/org/sections/{id}` — 🔑 Admin

**Body** `{ "name": "Nuevo nombre" }`

**Response `200`** `{ "section": OrgSection }`  **Errors:** `404`

---

### `DELETE /api/app/v1/org/sections/{id}` — 🔑 Admin

Items in the deleted section are reassigned to the default section.

**Response `204`**  **Errors:** `404`, `400` if attempting to delete the default section

---

## Personal library (`/library/*`)

> Used by: LibraryView  
> Personal document library scoped to the individual user — not shared across the org.  
> DB table: `user_library`
>
> **Sections model:** Same as org sections — sections are derived from `folder_path` in `user_library`. No separate DB table. Section names = first component of `folder_path`; `folder_path = ''` → default section `"General"`.

### `GET /api/app/v1/library/items` — 🔒 Any member

| Query param | Type | Required |
|---|---|---|
| `parent_id` | string | ✅ — `"root"` or folder id |

**Response `200`**
```json
{
  "items": [
    {
      "id": "uuid",
      "parentId": "root",
      "sectionId": "ls-general",
      "kind": "folder",
      "name": "Contratos 2024",
      "createdAt": "2025-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "parentId": "root",
      "sectionId": "ls-general",
      "kind": "file",
      "name": "NDA_Empresa_A.pdf",
      "fileType": "pdf",
      "size": 204800,
      "downloadUrl": "/api/app/v1/library/items/<id>/download",
      "createdAt": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

### `POST /api/app/v1/library/items` — 🔒 Any member

Create a folder. Use `/library/upload` for files.

**Body**
```json
{
  "parentId": "root",
  "sectionId": "ls-general",
  "name": "Documentos Fiscales"
}
```

**Response `201`** `{ "item": LibraryItem }`

---

### `POST /api/app/v1/library/upload` — 🔒 Any member

Upload a file to Supabase Storage under `user-files/{user_id}/{file_id}`, then insert a row into `user_library`. Also updates `organizations.used_bytes`.

> **Storage prerequisite:** This endpoint requires a Supabase Storage bucket named `user-files` to exist. Verify in the Supabase dashboard → Storage before testing uploads. Similarly, org-level file uploads require an `org-files` bucket.

**Form data** (multipart)
- `file` — the file to upload
- `parent_id` (query param) — `"root"` or a folder id
- `section_id` (query param, optional)
- `name` (query param, optional) — override the filename

**Response `201`** `{ "item": LibraryItem }`

---

### `PATCH /api/app/v1/library/items/{id}` — 🔒 Any member

**Body** — all optional
```json
{ "name": "Nuevo nombre.pdf", "sectionId": "ls-fiscal", "parentId": "uuid" }
```

**Response `200`** `{ "item": LibraryItem }`  **Errors:** `404`

---

### `DELETE /api/app/v1/library/items/{id}` — 🔒 Any member

Soft-deletes. If the item is a file, subtracts `file_size_bytes` from `organizations.used_bytes`.

**Response `204`**  **Errors:** `404`

---

### `GET /api/app/v1/library/sections` — 🔒 Any member

| Query param | Type | Required |
|---|---|---|
| `parent_id` | string | ✅ |

**Response `200`**
```json
{
  "sections": [
    { "id": "ls-general", "parentId": "root", "name": "General", "isDefault": true },
    { "id": "ls-fiscal",  "parentId": "root", "name": "Fiscal",  "isDefault": false }
  ]
}
```

---

### `POST /api/app/v1/library/sections` — 🔒 Any member

**Body** `{ "parentId": "root", "name": "Contratos" }`

**Response `201`** `{ "section": LibrarySection }`

---

### `PATCH /api/app/v1/library/sections/{id}` — 🔒 Any member

**Body** `{ "name": "Nuevo nombre" }`

**Response `200`** `{ "section": LibrarySection }`  **Errors:** `404`

---

### `DELETE /api/app/v1/library/sections/{id}` — 🔒 Any member

Items reassigned to the default section.

**Response `204`**  **Errors:** `404`, `400` if deleting the default section

---

## Law reference database

> Used by: DbView (Biblioteca Legal)  
> DB table: `fytic_library`  
> Read-only for all app users. Managed internally via service key.

### `GET /api/app/v1/law-db` — 🔒 Any member

Returns the full structured catalog of Mexican legal references, grouped by `group_name`.

**Response `200`**
```json
{
  "groups": [
    {
      "name": "Derecho Civil",
      "docs": [
        {
          "id": "uuid",
          "name": "Código Civil Federal",
          "scope": "national",
          "year": 1928,
          "vigente": true,
          "hasNewReforms": false,
          "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/2_110121.pdf",
          "pdfLink": "https://..."
        }
      ]
    }
  ]
}
```

**DB field mapping:**

| Response field | DB column |
|---|---|
| `name` | `fytic_library.name` |
| `scope` | `fytic_library.scope` |
| `year` | `fytic_library.publish_date` (year extracted) |
| `vigente` | `fytic_library.vigente` |
| `hasNewReforms` | `fytic_library.has_new_reforms` |
| `url` | `fytic_library.url` |
| `pdfLink` | `fytic_library.pdf_link` |

> Backend: `SELECT * FROM fytic_library WHERE is_active = true ORDER BY group_name, name`. Group them in Python before returning.
