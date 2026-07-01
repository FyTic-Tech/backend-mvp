"""Personal library (user_library).

Sections are stored as a `group_name` TEXT column on `user_library` (DB migration required).
Empty (pending) sections stored in organizations.settings['pending_lib_{user_id}'].
File uploads require Supabase Storage buckets — returns 503 until configured.

DB migration required before use:
    ALTER TABLE user_library ADD COLUMN IF NOT EXISTS group_name TEXT NOT NULL DEFAULT 'General';

Navigation:
  parent_id = 'root'         → items where folder_path = ''
  parent_id = '<folder_id>'  → items where folder_path = '<folder_id>'
Items carry their sectionId (group_name) for frontend grouping.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_org
from app.FyTic_app.models import (
    LibraryItem, LibraryItemCreate, LibraryItemPatch,
    LibrarySection, LibrarySectionCreate, LibrarySectionPatch,
)

router = APIRouter(tags=["library"])

_DEFAULT_GROUP = "General"


# ─── Settings helpers ─────────────────────────────────────────────────────────

def _pending_key(user_id: str) -> str:
    return f"pending_lib_{user_id}"


def _load_settings(db, org_id: str) -> dict:
    org = db.table("organizations").select("settings").eq("id", org_id).execute()
    return (org.data[0].get("settings") or {}) if org.data else {}


def _save_settings(db, org_id: str, s: dict) -> None:
    db.table("organizations").update({"settings": s}).eq("id", org_id).execute()


# ─── Sections helpers ─────────────────────────────────────────────────────────

def _all_section_names(db, org_id: str, user_id: str) -> list[str]:
    lib = (
        db.table("user_library")
        .select("group_name")
        .eq("user_id", user_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    names: set[str] = {_DEFAULT_GROUP}
    for row in lib.data:
        if row.get("group_name"):
            names.add(row["group_name"])

    s = _load_settings(db, org_id)
    names.update(s.get(_pending_key(user_id), []))

    return [_DEFAULT_GROUP] + sorted(n for n in names if n != _DEFAULT_GROUP)


def _section_obj(name: str) -> LibrarySection:
    return LibrarySection(id=name, parentId="root", name=name, isDefault=(name == _DEFAULT_GROUP))


# ─── Items helpers ───────────────────────────────────────────────────────────

def _to_item(row: dict) -> LibraryItem:
    folder_path: str = row.get("folder_path", "")
    is_file = bool(row.get("file_url"))
    return LibraryItem(
        id=row["id"],
        parentId=folder_path if folder_path else "root",
        sectionId=row.get("group_name") or _DEFAULT_GROUP,
        kind="file" if is_file else "folder",
        name=row.get("name", ""),
        fileType=row.get("file_type") if is_file else None,
        size=row.get("file_size_bytes") if is_file else None,
        downloadUrl=row.get("file_url") if is_file else None,
        createdAt=row.get("created_at", ""),
    )


# ─── Items endpoints ─────────────────────────────────────────────────────────

@router.get("/library/items", response_model=dict)
def list_library_items(
    parent_id: str = Query(...),
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()
    folder_path = "" if parent_id == "root" else parent_id
    rows = (
        db.table("user_library")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("org_id", user.org_id)
        .eq("folder_path", folder_path)
        .is_("deleted_at", "null")
        .order("name")
        .execute()
    )
    return {"items": [_to_item(r).model_dump() for r in rows.data]}


@router.post("/library/items", status_code=201, response_model=dict)
def create_folder(body: LibraryItemCreate, user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "org_id": user.org_id,
        "user_id": user.user_id,
        "folder_path": "" if body.parentId == "root" else body.parentId,
        "group_name": body.sectionId or _DEFAULT_GROUP,
        "name": body.name,
        "file_url": None,
        "file_size_bytes": 0,
        "created_at": now,
    }
    result = db.table("user_library").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    return {"item": _to_item(result.data[0]).model_dump()}


@router.post("/library/upload", status_code=201, response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    parent_id: str = Query(default="root"),
    section_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
    user: AuthUser = Depends(require_org),
) -> dict:
    raise HTTPException(
        503,
        "File uploads require Supabase Storage buckets to be configured. "
        "Create a 'user-files' bucket in Supabase Storage dashboard first.",
    )


@router.patch("/library/items/{item_id}", response_model=dict)
def update_library_item(
    item_id: str, body: LibraryItemPatch, user: AuthUser = Depends(require_org)
) -> dict:
    db = get_db()
    row = (
        db.table("user_library")
        .select("id")
        .eq("id", item_id)
        .eq("user_id", user.user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Item not found")
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.parentId is not None:
        updates["folder_path"] = "" if body.parentId == "root" else body.parentId
    if body.sectionId is not None:
        updates["group_name"] = body.sectionId
    if updates:
        db.table("user_library").update(updates).eq("id", item_id).execute()
    updated = db.table("user_library").select("*").eq("id", item_id).execute()
    return {"item": _to_item(updated.data[0]).model_dump()}


@router.delete("/library/items/{item_id}", status_code=204)
def delete_library_item(item_id: str, user: AuthUser = Depends(require_org)) -> None:
    db = get_db()
    row = (
        db.table("user_library")
        .select("id,file_size_bytes")
        .eq("id", item_id)
        .eq("user_id", user.user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Item not found")
    now = datetime.now(timezone.utc).isoformat()
    db.table("user_library").update({"deleted_at": now}).eq("id", item_id).execute()
    db.table("user_library").update({"deleted_at": now}).eq("folder_path", item_id).eq("user_id", user.user_id).is_("deleted_at", "null").execute()
    size = row.data[0].get("file_size_bytes") or 0
    if size and user.org_id:
        org = db.table("organizations").select("used_bytes").eq("id", user.org_id).execute()
        if org.data:
            current = org.data[0].get("used_bytes") or 0
            db.table("organizations").update(
                {"used_bytes": max(0, current - size)}
            ).eq("id", user.org_id).execute()


# ─── Sections endpoints ──────────────────────────────────────────────────────

@router.get("/library/sections", response_model=dict)
def list_library_sections(user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    names = _all_section_names(db, user.org_id, user.user_id)
    return {"sections": [_section_obj(n).model_dump() for n in names]}


@router.post("/library/sections", status_code=201, response_model=dict)
def create_library_section(
    body: LibrarySectionCreate, user: AuthUser = Depends(require_org)
) -> dict:
    db = get_db()
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Section name cannot be empty")
    if name == _DEFAULT_GROUP:
        raise HTTPException(400, "A 'General' section already exists")
    existing = _all_section_names(db, user.org_id, user.user_id)
    if name in existing:
        raise HTTPException(409, f"Section '{name}' already exists")
    s = _load_settings(db, user.org_id)
    key = _pending_key(user.user_id)
    pending: list = s.get(key, [])
    pending.append(name)
    s[key] = pending
    _save_settings(db, user.org_id, s)
    return {"section": _section_obj(name).model_dump()}


@router.patch("/library/sections/{section_id}", response_model=dict)
def update_library_section(
    section_id: str, body: LibrarySectionPatch, user: AuthUser = Depends(require_org)
) -> dict:
    if section_id == _DEFAULT_GROUP:
        raise HTTPException(400, "Cannot rename the default section")
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(400, "Section name cannot be empty")
    db = get_db()
    existing = _all_section_names(db, user.org_id, user.user_id)
    if section_id not in existing:
        raise HTTPException(404, "Section not found")
    if new_name in existing and new_name != section_id:
        raise HTTPException(409, f"Section '{new_name}' already exists")

    # Rename in user_library rows
    db.table("user_library").update({"group_name": new_name}).eq("group_name", section_id).eq("user_id", user.user_id).execute()

    # Rename in pending list
    s = _load_settings(db, user.org_id)
    key = _pending_key(user.user_id)
    s[key] = [new_name if p == section_id else p for p in s.get(key, [])]
    _save_settings(db, user.org_id, s)

    return {"section": _section_obj(new_name).model_dump()}


@router.delete("/library/sections/{section_id}", status_code=204)
def delete_library_section(
    section_id: str, user: AuthUser = Depends(require_org)
) -> None:
    if section_id == _DEFAULT_GROUP:
        raise HTTPException(400, "Cannot delete the default section")
    db = get_db()
    existing = _all_section_names(db, user.org_id, user.user_id)
    if section_id not in existing:
        raise HTTPException(404, "Section not found")

    # Move items back to General
    db.table("user_library").update({"group_name": _DEFAULT_GROUP}).eq("group_name", section_id).eq("user_id", user.user_id).is_("deleted_at", "null").execute()

    # Remove from pending list
    s = _load_settings(db, user.org_id)
    key = _pending_key(user.user_id)
    s[key] = [p for p in s.get(key, []) if p != section_id]
    _save_settings(db, user.org_id, s)
