# FyTic — Supabase Database Guide

---

## Context: How the DB evolved

FyTic's database did not start from scratch. Before the app existed, there was already a live production system serving the landing page and waitlist. That system had its own tables. The app expansion added entirely new tables alongside those — it did not replace them.

### Phase 1 — MVP / Landing (tables already in production)

| Table | Purpose |
|---|---|
| `waitlist` | Survey submissions from the landing page. Has a `_config` sentinel row (where `id = '_config'`) that controls whether the form is open or closed |
| `users` | One row per registered person. Originally only had landing/auth fields |
| `contacts` | Contact form submissions from the landing page |
| `investors` | Investor interest form submissions from the landing page |

> **Note on `clients`:** The MVP had a `clients` table used for the landing-page law firm carousel (simple name + sort_order rows). That table was **removed** when the app was built. The current `clients` table is the app's org-scoped client records — a completely different schema. The carousel is no longer backed by a DB table.

### Phase 2 — FyTic App (tables added for the product)

These tables were added when the frontend app was built. They represent the actual SaaS product:

`organizations`, `subscriptions`, `plans`, `clients`, `contracts`, `templates`, `org_library`, `user_library`, `fytic_library`

The `users` table was also **expanded** with new columns in this phase (see below).

### Phase 3 — Planned, not yet in DB

| Area | Status |
|---|---|
| AI chat / conversation history | Not yet designed. Will require its own tables (e.g., `conversations`, `messages`) once the AI feature scope is defined |
| Stripe billing events | `subscriptions` table has the Stripe fields stubbed; the webhook handler that populates them is not yet built |

**Sections (OrgView / LibraryView):** The frontend displays items in named visual groups called "sections." Sections are stored as a `group_name TEXT NOT NULL DEFAULT 'General'` column on `org_library` and `user_library`. A section is simply a distinct `group_name` value — no separate sections table exists.

**Required DB migration** (run once in Supabase SQL editor):
```sql
ALTER TABLE org_library  ADD COLUMN IF NOT EXISTS group_name TEXT NOT NULL DEFAULT 'General';
ALTER TABLE user_library ADD COLUMN IF NOT EXISTS group_name TEXT NOT NULL DEFAULT 'General';
```

Key rules:
- "General" is the default section and cannot be renamed or deleted.
- Drag-and-drop to a section → `PATCH /org/items/{id} {sectionId: "Fiscal"}` → updates `group_name` on the item row.
- Empty sections (no items yet) are persisted in `organizations.settings` as `pending_org_sections` (list of names) and `pending_lib_{user_id}` per user.
- `folder_path` is still used for **folder drill-down navigation** (parent/child hierarchy inside a section), completely independent of `group_name`.
- Clients (`clients` table) do not have a `group_name` column; their section assignment is stored in `organizations.settings['client_sections']` as `{client_id: group_name}`.

> **Naming note — `contracts` vs "documents":** The DB table is named `contracts`. The app frontend and API paths use "documents" everywhere (`/api/app/v1/documents`). Both refer to the same `contracts` table. The conceptual model is: a `templates` row is a blank boilerplate with `{{VARIABLE}}` placeholders; a `contracts` row is a filled instance tied to a specific client, created by picking a template. The API calls them "documents" because that is the broader user-facing label. When writing backend code, always use `contracts` as the table name.

---

## 1. Access Levels and RLS

All tables have Row Level Security enabled. The key distinction is which credential context you use.

### End users (lawyers and firm members using the app)

They authenticate via Supabase Auth and get a JWT. Their session is scoped by RLS — they can only see data belonging to their org.

**What they can access:**
- Their own `users` row (read + self-update)
- All rows in their org's `organizations`, `clients`, `contracts`, `templates`, `org_library` (scoped by `org_id`)
- Their own `user_library` rows only
- All `fytic_library` and `plans` rows where `is_active = true` (global read-only)

**What they cannot access:**
- Any other org's data (RLS blocks it at the DB layer)
- `subscriptions` unless their `users.role = 'admin'`
- `waitlist`, `investors`, `contacts` (no SELECT policy for end users)

### FyTic internal team (admin dashboard, data operations)

Uses the **service role key** (also called the Secret Key in Supabase). This bypasses RLS entirely.

**What this unlocks:**
- Full read/write access to all tables, all rows, no org scoping
- Managing `fytic_library` entries
- Managing `plans` (pricing, feature flags)
- Viewing all `waitlist`, `investors`, `contacts` submissions
- Monitoring all orgs and subscriptions
- Running the `create_organization_for_user` RPC

> **Important:** Because RLS is bypassed, any code using the service key must enforce its own data scoping. The DB will not protect you here.

### Backend service (FastAPI server-to-server calls)

Same service role key. Used for operations not tied to a specific logged-in user: syncing profile data after auth, creating ref codes, linking waitlist entries to users, etc. All current landing-page endpoints use this path.

Never put the service key in frontend code or include it in API responses.

---

## 2. Tables — Phase 1 (MVP, already in production)

### `waitlist`
Pre-signup survey capture from the landing page.

| Field | Type | Notes |
|---|---|---|
| `id` | text / uuid | PK. The special row `id = '_config'` controls form state |
| `active` | boolean | On `_config` row only: `true` = form open, `false` = closed |
| `user_id` | uuid | FK → `users.id`. NULL until the person signs up |
| `name` | text | Submitted name |
| `email` | text | Submitted email |
| `role` | text | Self-reported role (`'despacho'`, `'independiente'`, `'corporativo'`, `'becario'`) |
| `area` | text | Practice area |
| `problematic` | text | Pain point description |
| `tools` | text | Current tools they use |
| `process` | text | Current workflow description |
| `ai_question` | text | Response to the AI-readiness question |
| `fytic_question` | text | Response to the FyTic-specific question (added later) |
| `submitted_at` | timestamptz | When the form was submitted |
| `created_at` | timestamptz | Auto-set on insert |

**Key behaviors:**
- INSERT is public (no auth required — landing page form)
- SELECT is restricted to the user's own row via RLS (`user_id = auth.uid()`)
- Service key reads all rows for internal ops
- `user_id` is back-filled after signup via the backend's auth-linking endpoints
- The `_config` row stores `active` only; all other fields are NULL on that row

---

### `users`
One row per registered person. `id` matches `auth.users.id` in Supabase Auth.

**Phase 1 columns (existed from the start):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, matches `auth.users.id` |
| `email` | text | From Supabase Auth |
| `full_name` | text | nullable |
| `firm_name` | text | Used to name the org on creation |
| `position` | text | e.g. `"Socio"`, `"Asociado"` |
| `practice_area` | text | e.g. `"Derecho Civil"` |
| `phone` | text | nullable |
| `team_size` | text | e.g. `"1-5"`, `"10-50"` |
| `auth_provider` | text | `'email'` \| `'google'` |
| `ref_code` | text | Unique. User's own permanent referral code. Generated on demand |
| `referred_by` | text | Stores the `ref_code` string of the person who referred this user. Set at signup from `?ref=` param |
| `survey_completed` | boolean | Whether the waitlist survey was answered |
| `survey_completed_at` | timestamptz | When survey was completed |
| `created_at` | timestamptz | Auto-set on insert |

**Phase 2 columns (added for the app):**

| Field | Type | Notes |
|---|---|---|
| `org_id` | uuid | FK → `organizations.id`. NULL until org is created |
| `role` | text | One of six role values — see table below |
| `is_active` | boolean | `false` = deactivated by admin |
| `tokens_used_today` | int | AI request counter. Resets lazily every 24h |
| `tokens_reset_at` | timestamptz | When the token counter next resets |
| `modified_at` | timestamptz | Auto-updated by trigger on every UPDATE |
| `deleted_at` | timestamptz | Soft delete. NULL = active |

**Role values and credential security:**

| `role` value | Scope | Credential level | Access |
|---|---|---|---|
| `'super_admin'` | Platform-wide | Supabase JWT + mandatory `X-Internal-Key` header | Full platform access — all orgs, all tables, service ops |
| `'admin'` | Org-scoped | Supabase JWT | Full CRUD on org content, invite/remove/update members |
| `'member'` | Org-scoped | Supabase JWT | Full CRUD on documents, clients, templates, org view, library, scan |
| `'limited'` | Org-scoped | Supabase JWT | Read + create only — no delete, no member management. Also used for visitors accessing shared links |
| `'internal_dev'` | Platform-wide | Supabase JWT + mandatory `X-Internal-Key` header | Internal FyTic developer access — for the internal admin frontend |
| `'internal_team'` | Platform-wide | Supabase JWT + mandatory `X-Internal-Key` header | Internal FyTic team access (support, ops) — for the internal admin frontend |

**Credential security for internal roles:** `super_admin`, `internal_dev`, and `internal_team` require BOTH a valid Supabase JWT AND an `X-Internal-Key` header whose value matches a secret stored in Railway env vars (`INTERNAL_API_KEY`). Checking only the JWT role is not enough — the extra key ensures that even if a regular user's role is somehow elevated in the DB, they still cannot access internal routes without the physical key.

**Key behaviors:**
- `org_id` is nullable — a user exists without an org while in the pre-onboarding or waitlist-only state
- `referred_by` stores a `ref_code` string, not a UUID
- Never manually set `modified_at` — trigger handles it
- Always filter `WHERE deleted_at IS NULL` in app queries
- `tokens_used_today` and `tokens_reset_at` exist in the DB but the `consume_token` RPC is not yet implemented. AI token quota is not actively enforced — token-related API responses are hardcoded for now

---

### `contacts`
Landing page contact form submissions.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | |
| `firm` | text | |
| `email` | text | |
| `message` | text | |
| `created_at` | timestamptz | Auto-set |

No SELECT policy — only readable via service key.

---

### `investors`
Landing page investor interest form.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | |
| `email` | text | |
| `submitted_at` | timestamptz | |

No SELECT policy — only readable via service key.

---

## 3. Tables — Phase 2 (FyTic App)

### `organizations`
The tenant. One row per law firm using the product.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | Firm display name, sourced from `users.firm_name` on creation |
| `slug` | text | Unique URL-safe identifier. Auto-generated by RPC — do not set manually |
| `logo_url` | text | Supabase Storage URL, nullable |
| `country` | text | ISO 3166-1 alpha-2, default `'MX'` |
| `industry` | text | `'law_firm'` \| `'notary'` \| `'corp'` \| `'other'` |
| `settings` | jsonb | Org-level config overrides `{}` |
| `used_bytes` | bigint | Running storage total. Updated on every file upload/delete |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

**Key behaviors:**
- Always created via `SELECT create_organization_for_user('<user_id>')` RPC — never insert directly
- The RPC also creates the linked `subscriptions` row and sets `users.org_id` and `users.role = 'admin'`
- `used_bytes` must be updated manually on every file operation in `org_library` and `user_library`

---

### `subscriptions`
One-to-one with `organizations`. Created automatically by the org-creation RPC.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id`, UNIQUE |
| `plan_id` | text | FK → `plans.id`. Default `'free'` |
| `status` | text | `'active'` \| `'trialing'` \| `'past_due'` \| `'canceled'` |
| `current_period_start` | timestamptz | Set by Stripe webhook |
| `current_period_end` | timestamptz | Set by Stripe webhook |
| `stripe_customer_id` | text | Set when Stripe customer is created |
| `stripe_subscription_id` | text | Set on Stripe subscription creation |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |

**Key behaviors:**
- Only org admins can SELECT this row via RLS
- The Stripe webhook handler (not yet built) will update `plan_id`, `status`, `stripe_*`, and period fields
- Never create or delete manually — the RPC manages this

---

### `plans`
Global. Static rows managed by FyTic internally.

| Field | Type | Notes |
|---|---|---|
| `id` | text | PK: `'free'` \| `'pro'` \| `'enterprise'` |
| `name` | text | Display name |
| `max_users` | int | `-1` = unlimited |
| `max_clients` | int | `-1` = unlimited |
| `max_storage_gb` | int | Storage cap in GB |
| `tokens_per_day` | int | `-1` = unlimited. Free: `50`, Pro: `500`, Enterprise: `-1` |
| `features` | jsonb | Feature flags e.g. `{"scanner": true, "e_sign": true}` |
| `price_monthly_usd` | numeric(10,2) | `0` for free |
| `created_at` | timestamptz | Auto-set |

**Key behaviors:**
- Read-only for all authenticated users via RLS
- Only updated via service key (internal dashboard or direct SQL)
- `tokens_per_day = -1` means skip the quota check entirely (enterprise)

---

### `clients`
A firm's client and case records. **This is an app table, not the landing page carousel.**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id` |
| `name` | text | Full legal name of the client |
| `initials` | text | Auto-generated or user-set e.g. `"AB"` |
| `accent_color` | text | Hex color for the avatar chip, default `'#6366f1'` |
| `rfc` | text | Mexican tax ID, nullable |
| `address` | text | nullable |
| `contact_name` | text | Primary contact person |
| `contact_email` | text | nullable |
| `contact_phone` | text | nullable |
| `case_description` | text | Brief matter description |
| `tags` | jsonb | String array e.g. `["urgente", "fiscal"]` |
| `is_active` | boolean | Soft-hide without deleting |
| `created_by` | uuid | FK → `users.id` |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

---

### `contracts`
Instantiated legal documents. The core business object.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id` |
| `client_id` | uuid | FK → `clients.id`. **Nullable** — null = no client attached |
| `template_id` | uuid | FK → `templates.id`. NULL if created from scratch |
| `created_by` | uuid | FK → `users.id` |
| `owner_scope` | text | `'org'` (firm-wide) \| `'user'` (private draft) |
| `title` | text | |
| `status` | text | `'draft'` \| `'active'` \| `'signed'` \| `'archived'` |
| `variables` | jsonb | Filled values e.g. `{"NOMBRE_CLIENTE": "Juan García"}` |
| `signatures` | jsonb | `{"client": {"name": "Juan", "dataUrl": "...", "signed_at": "..."}}` |
| `content` | jsonb | Array of markdown line strings (editable body) |
| `file_url` | text | Supabase Storage URL. Only set for uploaded contracts |
| `file_type` | text | `'pdf'` \| `'docx'`. Only set when `file_url` is set |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

**Key behaviors:**
- `client_id` nullable: a contract without a client is a universal/internal document
- `owner_scope = 'user'`: RLS restricts SELECT/UPDATE to `created_by` only
- `owner_scope = 'org'`: all org members can read and update
- A contract is either built from a template (`content` + `variables` populated, `file_url` null) or uploaded as a finished file (`file_url` set, `content` null). Both are never populated at the same time
- Status flow: `draft` → `active` → `signed` → `archived`

---

### `templates`
Reusable document stencils. Unified table for FyTic system templates and org custom templates.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id`. NULL when `source = 'fytic'` |
| `source` | text | `'fytic'` (system-provided) \| `'user'` (org custom) |
| `source_contract_id` | uuid | FK → `contracts.id`. Set when promoted from a contract |
| `name` | text | Template name |
| `group_name` | text | Display category, free text |
| `signatories` | jsonb | `[{"key": "client", "label": "Cliente"}, ...]` |
| `content` | jsonb | Array of markdown line strings |
| `variables` | jsonb | Detected variable keys e.g. `["NOMBRE_CLIENTE", "FECHA"]` |
| `is_active` | boolean | Soft-hide |
| `created_by` | uuid | FK → `users.id`. NULL for fytic templates |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

**Key behaviors:**
- `source = 'fytic'` rows: `org_id = NULL`, read-only for all users via RLS
- `source = 'user'` rows: fully editable by their org
- Promoting a contract to a template: insert a new row with `source = 'user'` and `source_contract_id` pointing to the original

---

### `org_library`
Firm-wide file storage. Any file type — not just contracts.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id` |
| `client_id` | uuid | FK → `clients.id`. **Nullable** |
| `uploaded_by` | uuid | FK → `users.id` |
| `folder_path` | text | e.g. `'fiscal/2024'`. Empty string = root |
| `name` | text | Display name |
| `description` | text | nullable |
| `file_url` | text | Supabase Storage URL |
| `file_type` | text | `'pdf'` \| `'docx'` \| `'xlsx'` \| etc. |
| `file_size_bytes` | bigint | Used to update `organizations.used_bytes` |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

**Key behaviors:**
- Visible to all org members — no per-user scoping
- After insert: add `file_size_bytes` to `organizations.used_bytes`
- After soft-delete: subtract `file_size_bytes` from `organizations.used_bytes`
- Filter by `client_id` to show files attached to a specific client
- Filter by `folder_path LIKE 'fiscal/%'` to list folder contents

---

### `user_library`
Private per-user file storage. Same shape as `org_library` but scoped to a single user.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `org_id` | uuid | FK → `organizations.id` |
| `user_id` | uuid | FK → `users.id`. Owner |
| `client_id` | uuid | FK → `clients.id`. **Nullable** |
| `folder_path` | text | Same pattern as `org_library` |
| `name` | text | Display name |
| `description` | text | nullable |
| `file_url` | text | Supabase Storage URL |
| `file_type` | text | `'pdf'` \| `'docx'` \| etc. |
| `file_size_bytes` | bigint | |
| `created_at` | timestamptz | Auto-set |
| `modified_at` | timestamptz | Auto-updated by trigger |
| `deleted_at` | timestamptz | Soft delete |

**Key behaviors:**
- RLS restricts all operations to `user_id = auth.uid()` — no other org member can see this
- Same storage accounting: update `organizations.used_bytes` on insert/delete

---

### `fytic_library`
Global legal reference corpus. FyTic-managed, read-only for all users.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, auto-generated |
| `name` | text | Law/document title |
| `group_name` | text | Legal category e.g. `'Derecho Civil'` |
| `scope` | text | `'national'` \| `'state'` \| `'international'` |
| `state` | text | Mexican estado slug. Only set when `scope = 'state'`. NULL otherwise |
| `url` | text | Official publication page URL |
| `pdf_link` | text | Direct PDF link |
| `other_link` | text | Any other format (HTML, DOC, etc.) |
| `publish_date` | date | Original publication date |
| `last_update` | timestamptz | Last time FyTic verified/updated this entry |
| `has_new_reforms` | boolean | True = this law has recent reforms not yet fully processed |
| `vigente` | boolean | True = law currently in force |
| `is_active` | boolean | False = hidden from app without deleting |
| `created_at` | timestamptz | Auto-set |

**Key behaviors:**
- No `org_id` — global, not org-scoped
- DB constraint: `scope = 'state'` requires `state` non-null; all other scopes require `state` null
- Unique constraint on `(name, scope, state)` — use for upsert on bulk ingestion
- Updated only via service key (internal dashboard or SQL ingest)
- All authenticated users can SELECT where `is_active = true`

---

## 4. Relationships Summary

```
── Phase 1 (MVP) ──────────────────────────────────────────
waitlist
  └── users (user_id, nullable, back-filled on signup)

users (self-referencing for referrals)
  └── users (referred_by → ref_code)

contacts       ← standalone, landing page only
investors      ← standalone, landing page only

── Phase 2 (App) ──────────────────────────────────────────
plans ──────────────────────── subscriptions (plan_id)

organizations
  ├── subscriptions        (org_id, 1:1, auto-created by RPC)
  ├── users                (org_id, nullable until onboarding)
  ├── clients              (org_id)
  ├── templates            (org_id, only source='user')
  ├── contracts            (org_id)
  ├── org_library          (org_id)
  └── user_library         (org_id)

clients
  ├── contracts            (client_id, nullable)
  ├── org_library          (client_id, nullable)
  └── user_library         (client_id, nullable)

templates ←→ contracts
  contracts.template_id        → template it was built from
  templates.source_contract_id → contract it was promoted from

users
  ├── contracts            (created_by)
  ├── org_library          (uploaded_by)
  ├── user_library         (user_id, ownership)
  ├── clients              (created_by)
  └── templates            (created_by)
```

---

## 5. Core Data Flows

### New user signs up
1. Supabase Auth creates `auth.users` row
2. Backend creates `users` row with `org_id = NULL`
3. If `?ref=<code>` was in the URL, set `referred_by = <code>` in `users`
4. Backend links any existing `waitlist` row to this `user_id` (by email)
5. User completes onboarding survey → `survey_completed = true`, `survey_completed_at = now()`
6. When ready to activate → call `SELECT create_organization_for_user('<user_id>')`
7. RPC creates `organizations` row + `subscriptions` row (free plan), sets `users.org_id` and `users.role = 'admin'`

### AI token check (not yet enforced)

The `users` table has `tokens_used_today` and `tokens_reset_at` columns for quota tracking. The `consume_token` RPC that would manage these is **not yet implemented**. Until it is, AI endpoints skip quota enforcement and return hardcoded token usage values. When the RPC is eventually built:
```sql
SELECT consume_token('user_id_here');
-- Returns true (allowed, counter incremented) or false (quota exceeded)
```

### File upload (org_library)
1. Upload file to Supabase Storage at `org-files/{org_id}/library/{file_id}`
2. Insert row into `org_library` with `file_url`, `file_size_bytes`
3. Increment `organizations.used_bytes`:
```sql
UPDATE organizations SET used_bytes = used_bytes + <file_size_bytes> WHERE id = <org_id>;
```

### Soft delete a file
1. Set `org_library.deleted_at = now()`
2. Decrement `organizations.used_bytes`:
```sql
UPDATE organizations SET used_bytes = used_bytes - <file_size_bytes> WHERE id = <org_id>;
```

### Contract from template
1. Fetch `templates` row — includes `content`, `variables`, `signatories`
2. Insert into `contracts` with `template_id` set, copy `content`, leave `variables = {}`
3. User fills variables → update `contracts.variables`
4. User signs → update `contracts.signatures` and `contracts.status = 'signed'`

### Promote contract to template
1. Fetch the `contracts` row
2. Insert into `templates` with `source = 'user'`, `org_id` set, `source_contract_id` pointing to the original, copy `content` and `variables`

### Waitlist activation (manual internal flow)
1. Internal dashboard finds a waitlist entry to activate
2. Set `waitlist.active = true`, `waitlist.activated_at = now()`
3. Send invite email to `waitlist.email`
4. When user signs up with that email, backend back-fills `waitlist.user_id` with the new user's id

---

## 6. Query Filters — Always Apply These

```python
# Soft deletes — never return deleted rows
.eq("deleted_at", None)             # supabase-py
WHERE deleted_at IS NULL            # raw SQL

# Tenant isolation — always scope to org
.eq("org_id", current_user.org_id)

# User-private vs org-wide contracts
.or_("owner_scope.eq.org,created_by.eq." + user_id)

# fytic_library — only active entries
.eq("is_active", True)
```

RLS enforces these automatically when using the publishable key + user JWT. When using the service key (internal ops, backend service calls), **RLS is bypassed and these filters are your responsibility in code.**

---

## 7. Useful SQL (Supabase SQL editor)

```sql
-- Toggle waitlist form closed
UPDATE waitlist SET active = false WHERE id = '_config';

-- Count registered users (real users only, exclude any sentinel rows)
SELECT count(*) FROM users WHERE id NOT LIKE '\_%';

-- See referral chain
SELECT email, referred_by, created_at FROM users
WHERE referred_by IS NOT NULL ORDER BY created_at DESC;

-- Check an org's storage usage
SELECT name, used_bytes, used_bytes / 1e9 AS gb FROM organizations WHERE id = '<org_id>';

-- See all members of an org
SELECT id, email, role, is_active FROM users WHERE org_id = '<org_id>' AND deleted_at IS NULL;
```
