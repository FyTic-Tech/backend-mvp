import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.db import get_db
from .models import (
    BindUserRequest, CheckEmailRequest, ClientsResponse, ContactCreate, InvestorCreate,
    LinkGoogleRequest, OkResponse, ProfileUpdateRequest, RefCodeRequest, LinkSurveyRequest,
    WaitlistEntryCreate, WaitlistEntryUpdate, WaitlistPostResponse, WaitlistStatusResponse,
)

router = APIRouter()
_DATA = Path(__file__).parent / "data"


def _sync_user_profile(db, user_id: str, ai_question: str, referred_by: str | None) -> None:
    """Update users table after a waitlist submission that has a known user_id.
    Sets survey_completed=True when the survey is answered, and referred_by if provided.
    """
    user_updates: dict = {}
    if ai_question:
        user_updates["survey_completed"] = True
        user_updates["survey_completed_at"] = datetime.now(timezone.utc).isoformat()
    if referred_by:
        # Only set referred_by if not already set (never overwrite)
        existing = db.table("users").select("referred_by").eq("id", user_id).execute()
        if existing.data and not existing.data[0].get("referred_by"):
            user_updates["referred_by"] = referred_by
    if user_updates:
        db.table("users").update(user_updates).eq("id", user_id).execute()


@router.get("/content")
def get_content() -> dict:
    return json.loads((_DATA / "content.json").read_text(encoding="utf-8"))


@router.get("/clients", response_model=ClientsResponse)
def get_clients() -> ClientsResponse:
    db = get_db()
    rows = db.table("clients").select("*").order("sort_order").execute()
    config = next((r for r in rows.data if r["id"] == "_config"), None)
    firms  = [r for r in rows.data if r["id"] != "_config" and r.get("name")]
    return {
        "visible": config["visible"] if config else False,
        "clients": [r["name"] for r in firms],
    }


@router.get("/waitlist", response_model=WaitlistStatusResponse)
def get_waitlist_status() -> WaitlistStatusResponse:
    db = get_db()
    rows = db.table("waitlist").select("id,active").execute()
    config = next((r for r in rows.data if r["id"] == "_config"), None)
    count  = sum(1 for r in rows.data if r["id"] != "_config")
    return {"active": config["active"] if config else True, "count": count}


@router.post("/waitlist", status_code=201, response_model=WaitlistPostResponse)
def submit_waitlist(entry: WaitlistEntryCreate) -> WaitlistPostResponse:
    db = get_db()
    config_rows = db.table("waitlist").select("active").eq("id", "_config").execute()
    config = config_rows.data[0] if config_rows.data else None
    if config and not config.get("active", True):
        raise HTTPException(status_code=403, detail="waitlist is closed")

    record = entry.model_dump()
    user_id   = record.pop("user_id", None)
    referred_by = record.pop("referred_by", None)  # not stored in waitlist table
    record["submitted_at"] = datetime.now(timezone.utc).isoformat()
    if user_id:
        record["user_id"] = user_id

    # UPSERT: if this user_id already has an entry, update it instead of inserting
    if user_id:
        existing = (
            db.table("waitlist").select("id").eq("user_id", user_id).neq("id", "_config").execute()
        )
        if existing.data:
            entry_id = existing.data[0]["id"]
            updates = {k: v for k, v in record.items() if v not in (None, "")}
            updates.pop("user_id", None)
            db.table("waitlist").update(updates).eq("id", entry_id).execute()
            _sync_user_profile(db, user_id, record.get("ai_question", ""), referred_by)
            return {"ok": True, "id": entry_id}

    result = db.table("waitlist").insert(record).select().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="waitlist insert failed")
    if user_id:
        _sync_user_profile(db, user_id, record.get("ai_question", ""), referred_by)
    return {"ok": True, "id": result.data[0]["id"]}


@router.patch("/waitlist/{entry_id}", status_code=200, response_model=OkResponse)
def update_waitlist(entry_id: str, entry: WaitlistEntryUpdate) -> OkResponse:
    db = get_db()
    updates = entry.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    result = (
        db.table("waitlist")
        .update(updates)
        .eq("id", entry_id)
        .neq("id", "_config")
        .select("user_id, ai_question")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="entry not found")
    # If this PATCH set a user_id (e.g. from auth/callback after OAuth), sync the profile
    row = result.data[0]
    if row.get("user_id") and "user_id" in updates:
        _sync_user_profile(db, row["user_id"], row.get("ai_question", ""), None)
    return {"ok": True}


@router.post("/profile/autofill")
def autofill_profile(body: RefCodeRequest) -> dict:
    """Reads the user's waitlist survey answers and fills any empty profile fields.
    Called when the user visits /perfil and has incomplete profile data."""
    db = get_db()
    user_id = body.user_id

    # Only fill fields that are currently NULL
    profile = db.table("users").select("practice_area, position, firm_name").eq("id", user_id).execute()
    if not profile.data:
        return {"ok": False, "suggestions": {}}

    current = profile.data[0]

    # Fetch the completed waitlist entry for this user
    waitlist = db.table("waitlist").select("role, area") \
      .eq("user_id", user_id).not_.is_("ai_question", "null") \
      .neq("ai_question", "").neq("id", "_config").execute()
    if not waitlist.data:
        return {"ok": True, "suggestions": {}}

    entry = waitlist.data[0]
    role = entry.get("role", "")
    area = entry.get("area", "")

    ROLE_TO_POSITION = {
        "despacho":      "Abogado en despacho",
        "independiente": "Abogado independiente",
        "corporativo":   "Abogado corporativo",
        "becario":       "Becario",
    }
    AREA_TO_PRACTICE = {
        "civil":       "Derecho civil",
        "mercantil":   "Derecho mercantil",
        "penal":       "Derecho penal",
        "fiscal":      "Derecho fiscal",
        "laboral":     "Derecho laboral",
        "corporativo": "Derecho corporativo",
        "familiar":    "Derecho familiar",
    }

    suggestions: dict = {}
    if not current.get("position") and role in ROLE_TO_POSITION:
        suggestions["position"] = ROLE_TO_POSITION[role]
    if not current.get("practice_area") and area in AREA_TO_PRACTICE:
        suggestions["practice_area"] = AREA_TO_PRACTICE[area]
    if not current.get("firm_name") and role == "independiente":
        suggestions["firm_name"] = "Independiente"

    if suggestions:
        db.table("users").update(suggestions).eq("id", user_id).execute()

    return {"ok": True, "suggestions": suggestions}


@router.patch("/profile/update")
def update_profile(body: ProfileUpdateRequest) -> dict:
    """Update editable profile fields for a user."""
    db = get_db()
    updates = {k: v for k, v in body.model_dump(exclude={"user_id"}).items() if v is not None}
    if not updates:
        return {"ok": True}
    db.table("users").update(updates).eq("id", body.user_id).execute()
    return {"ok": True}


@router.get("/profile/referrals/{ref_code}")
def get_referrals(ref_code: str) -> dict:
    """Returns the list of users who registered via this referral link."""
    db = get_db()
    result = db.table("users") \
      .select("email, full_name, created_at") \
      .eq("referred_by", ref_code) \
      .order("created_at", desc=True) \
      .execute()
    return {"referrals": result.data or []}


@router.post("/profile/check-email")
def check_email(body: CheckEmailRequest) -> dict:
    """Checks if an email is already registered and returns its auth provider.
    Used by the frontend to show the correct login method before attempting signup."""
    db = get_db()
    result = db.table("users").select("auth_provider").eq("email", body.email).execute()
    if result.data:
        return {"exists": True, "provider": result.data[0].get("auth_provider", "email")}
    return {"exists": False, "provider": None}


@router.post("/profile/link-google")
def link_google(body: LinkGoogleRequest) -> dict:
    """Links a Google OAuth user to their pre-registration waitlist entry by row ID.
    Called from auth/callback after Google OAuth completes.
    Uses the service key — bypasses RLS for both waitlist and users writes."""
    db = get_db()

    # 1. Update waitlist entry by row ID (not email — Google entries have email: "")
    result = db.table("waitlist") \
      .update({"user_id": body.user_id, "email": body.email}) \
      .eq("id", body.waitlist_id) \
      .neq("id", "_config") \
      .select("ai_question") \
      .execute()

    if not result.data:
        return {"ok": False, "error": "waitlist entry not found"}

    ai_question = result.data[0].get("ai_question", "")

    # 2. Update users: survey_completed + referred_by in one call
    _sync_user_profile(db, body.user_id, ai_question, body.referred_by)

    return {"ok": True}


@router.post("/profile/bind-user")
def bind_user(body: BindUserRequest) -> dict:
    """Transfers anonymous survey data to a new permanent user after email confirmation.
    Called when anonymous_id != new_user_id (email/password signup path only)."""
    db = get_db()

    # Read anonymous user's data before deleting
    anon = db.table("users").select("referred_by").eq("id", body.anonymous_id).execute()
    anon_referred_by = (anon.data[0].get("referred_by") or "") if anon.data else ""

    # Move waitlist entries from anonymous user to permanent user
    db.table("waitlist").update({"user_id": body.new_user_id}) \
      .eq("user_id", body.anonymous_id).execute()

    # Sync profile: survey_completed + referred_by
    entries = db.table("waitlist").select("ai_question").eq("user_id", body.new_user_id).execute()
    user_updates: dict = {}
    if entries.data and any(e.get("ai_question") for e in entries.data):
        user_updates["survey_completed"] = True
        user_updates["survey_completed_at"] = datetime.now(timezone.utc).isoformat()
    if anon_referred_by:
        user_updates["referred_by"] = anon_referred_by
    if user_updates:
        db.table("users").update(user_updates).eq("id", body.new_user_id).execute()

    # Clean up anonymous user row
    db.table("users").delete().eq("id", body.anonymous_id).execute()

    return {"ok": True}


@router.post("/profile/link-survey")
def link_survey(body: LinkSurveyRequest) -> dict:
    """Links anonymous waitlist entries (by email) to a registered user.
    Also marks survey_completed and sets referred_by — using the service key
    so both writes bypass RLS (no client session required)."""
    db = get_db()
    result = db.table("waitlist") \
      .update({"user_id": body.user_id}) \
      .eq("email", body.email) \
      .filter("user_id", "is", "null") \
      .neq("id", "_config") \
      .select("ai_question") \
      .execute()

    user_updates: dict = {}

    if result.data and any(r.get("ai_question") for r in result.data):
        user_updates["survey_completed"] = True
        user_updates["survey_completed_at"] = datetime.now(timezone.utc).isoformat()

    if body.referred_by:
        user_updates["referred_by"] = body.referred_by

    if user_updates:
        db.table("users").update(user_updates).eq("id", body.user_id).execute()

    return {"ok": True}


@router.post("/profile/ref-code")
def get_or_create_ref_code(body: RefCodeRequest) -> dict:
    import hashlib
    db = get_db()
    result = db.table("users").select("ref_code").eq("id", body.user_id).execute()
    if result.data and result.data[0].get("ref_code"):
        return {"ref_code": result.data[0]["ref_code"]}
    ref_code = hashlib.md5(body.user_id.encode()).hexdigest()[:8]
    db.table("users").update({"ref_code": ref_code}).eq("id", body.user_id).execute()
    return {"ref_code": ref_code}


@router.post("/investors", status_code=201, response_model=OkResponse)
def submit_investor(investor: InvestorCreate) -> OkResponse:
    db = get_db()
    record = investor.model_dump()
    record["submitted_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("investors").insert(record).select().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="investor insert failed")
    return {"ok": True}


@router.post("/contact", status_code=201, response_model=OkResponse)
def submit_contact(contact: ContactCreate) -> OkResponse:
    db = get_db()
    result = db.table("contacts").insert(contact.model_dump()).select().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="contact insert failed")
    return {"ok": True}
