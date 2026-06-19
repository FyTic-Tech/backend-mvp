import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.db import get_db
from .models import (
    ClientsResponse, ContactCreate, InvestorCreate, OkResponse, RefCodeRequest,
    WaitlistEntryCreate, WaitlistEntryUpdate, WaitlistPostResponse, WaitlistStatusResponse,
)

router = APIRouter()
_DATA = Path(__file__).parent / "data"


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
    user_id = record.get("user_id")
    record["submitted_at"] = datetime.now(timezone.utc).isoformat()

    # UPSERT: if this user_id already has an entry, update it instead of inserting
    if user_id:
        existing = (
            db.table("waitlist").select("id").eq("user_id", user_id).neq("id", "_config").execute()
        )
        if existing.data:
            entry_id = existing.data[0]["id"]
            updates = {k: v for k, v in record.items() if v not in (None, "")}
            updates.pop("user_id", None)  # user_id is already correct
            db.table("waitlist").update(updates).eq("id", entry_id).execute()
            return {"ok": True, "id": entry_id}

    result = db.table("waitlist").insert(record).select().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="waitlist insert failed")
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
        .select()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="entry not found")
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
