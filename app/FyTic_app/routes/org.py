"""OrgView: clients, folders, files grouped by sections.

Sections are stored as a `group_name` TEXT column on `org_library` (DB migration required).
Clients don't have a group_name column; their section assignment is stored in
organizations.settings['client_sections'] as {client_id: group_name}.
Empty (pending) sections are stored in organizations.settings['pending_org_sections']
as a list of names.

DB migration required before use:
    ALTER TABLE org_library ADD COLUMN IF NOT EXISTS group_name TEXT NOT NULL DEFAULT 'General';

Navigation (folder drill-down is separate from sections):
  parent_id = 'root'          → items where folder_path = ''
  parent_id = '<folder_id>'   → items where folder_path = '<folder_id>'
Items returned include their sectionId (group_name) for frontend grouping.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_admin, require_org, require_write
from app.FyTic_app.models import (
    OrgItem, OrgItemCreate, OrgItemPatch, OrgSection, OrgSectionCreate, OrgSectionPatch,
)

router = APIRouter(tags=["org"])

_DEFAULT_GROUP = "General"


# ─── Settings helpers ─────────────────────────────────────────────────────────

def _load_settings(db, org_id: str) -> dict:
    org = db.table("organizations").select("settings").eq("id", org_id).execute()
    return (org.data[0].get("settings") or {}) if org.data else {}


def _save_settings(db, org_id: str, s: dict) -> None:
    db.table("organizations").update({"settings": s}).eq("id", org_id).execute()


# ─── Sections helpers ─────────────────────────────────────────────────────────

def _all_section_names(db, org_id: str) -> list[str]:
    """Return sorted list of all known group names for this org.
    Sources: org_library.group_name DISTINCT, client_sections values, pending list.
    """
    lib = (
        db.table("org_library")
        .select("group_name")
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    names: set[str] = {_DEFAULT_GROUP}
    for row in lib.data:
        if row.get("group_name"):
            names.add(row["group_name"])

    s = _load_settings(db, org_id)
    for v in s.get("client_sections", {}).values():
        if v:
            names.add(v)
    names.update(s.get("pending_org_sections", []))

    return [_DEFAULT_GROUP] + sorted(n for n in names if n != _DEFAULT_GROUP)


def _section_obj(name: str) -> OrgSection:
    return OrgSection(id=name, parentId="root", name=name, isDefault=(name == _DEFAULT_GROUP))


# ─── Items helpers ───────────────────────────────────────────────────────────

def _client_to_item(c: dict, section: str = _DEFAULT_GROUP) -> OrgItem:
    return OrgItem(
        id=c["id"],
        parentId="root",
        sectionId=section,
        kind="client",
        name=c.get("name", ""),
        icon="briefcase",
        color=c.get("accent_color", "#6366f1"),
        rfc=c.get("rfc"),
        createdAt=c.get("created_at", ""),
    )


def _lib_to_item(row: dict) -> OrgItem:
    folder_path: str = row.get("folder_path", "")
    return OrgItem(
        id=row["id"],
        parentId=folder_path if folder_path else "root",
        sectionId=row.get("group_name") or _DEFAULT_GROUP,
        kind="folder" if not row.get("file_url") else "file",
        name=row.get("name", ""),
        icon="folder" if not row.get("file_url") else "file",
        color=None,
        createdAt=row.get("created_at", ""),
    )


# ─── Items endpoints ─────────────────────────────────────────────────────────

@router.get("/org/items", response_model=dict)
def list_org_items(
    parent_id: str = Query(...),
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()
    items: list[dict] = []

    if parent_id == "root":
        # Load client section assignments once
        settings = _load_settings(db, user.org_id)
        client_sections: dict = settings.get("client_sections", {})

        clients = (
            db.table("clients")
            .select("*")
            .eq("org_id", user.org_id)
            .is_("deleted_at", "null")
            .order("name")
            .execute()
        )
        for c in clients.data:
            section = client_sections.get(c["id"], _DEFAULT_GROUP)
            items.append(_client_to_item(c, section).model_dump())

        lib_items = (
            db.table("org_library")
            .select("*")
            .eq("org_id", user.org_id)
            .eq("folder_path", "")
            .is_("deleted_at", "null")
            .order("name")
            .execute()
        )
        for row in lib_items.data:
            items.append(_lib_to_item(row).model_dump())
    else:
        # Items inside a folder (folder_path = parent_id, any section)
        lib_items = (
            db.table("org_library")
            .select("*")
            .eq("org_id", user.org_id)
            .eq("folder_path", parent_id)
            .is_("deleted_at", "null")
            .order("name")
            .execute()
        )
        for row in lib_items.data:
            items.append(_lib_to_item(row).model_dump())

    return {"items": items}


@router.post("/org/items", status_code=201, response_model=dict)
def create_org_item(body: OrgItemCreate, user: AuthUser = Depends(require_write)) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    folder_path = "" if body.parentId == "root" else body.parentId
    section = body.sectionId or _DEFAULT_GROUP

    if body.kind == "client":
        record = {
            "org_id": user.org_id,
            "name": body.name,
            "initials": body.name[:2].upper() if body.name else "",
            "accent_color": body.color or "#6366f1",
            "rfc": body.rfc,
            "is_active": True,
            "created_by": user.user_id,
            "created_at": now,
        }
        result = db.table("clients").insert(record).select().execute()
        if not result.data:
            raise HTTPException(500, "Insert failed")
        row = result.data[0]
        if section != _DEFAULT_GROUP:
            s = _load_settings(db, user.org_id)
            cs = s.get("client_sections", {})
            cs[row["id"]] = section
            s["client_sections"] = cs
            _save_settings(db, user.org_id, s)
        return {"item": _client_to_item(row, section).model_dump()}

    # folder or file
    record = {
        "org_id": user.org_id,
        "uploaded_by": user.user_id,
        "folder_path": folder_path,
        "group_name": section,
        "name": body.name,
        "file_url": None,
        "file_size_bytes": 0,
        "created_at": now,
    }
    result = db.table("org_library").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    return {"item": _lib_to_item(result.data[0]).model_dump()}


@router.patch("/org/items/{item_id}", response_model=dict)
def update_org_item(
    item_id: str, body: OrgItemPatch, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()

    # Try org_library first
    lib_row = (
        db.table("org_library")
        .select("*")
        .eq("id", item_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if lib_row.data:
        updates: dict = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.parentId is not None:
            updates["folder_path"] = "" if body.parentId == "root" else body.parentId
        if body.sectionId is not None:
            updates["group_name"] = body.sectionId
        if updates:
            db.table("org_library").update(updates).eq("id", item_id).execute()
        updated = db.table("org_library").select("*").eq("id", item_id).execute()
        return {"item": _lib_to_item(updated.data[0]).model_dump()}

    # Try clients
    c_row = (
        db.table("clients")
        .select("*")
        .eq("id", item_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not c_row.data:
        raise HTTPException(404, "Item not found")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.color is not None:
        updates["accent_color"] = body.color
    if updates:
        db.table("clients").update(updates).eq("id", item_id).execute()

    # Handle sectionId for client via settings
    s = _load_settings(db, user.org_id)
    cs: dict = s.get("client_sections", {})
    if body.sectionId is not None:
        if body.sectionId == _DEFAULT_GROUP:
            cs.pop(item_id, None)
        else:
            cs[item_id] = body.sectionId
        s["client_sections"] = cs
        _save_settings(db, user.org_id, s)

    section = cs.get(item_id, _DEFAULT_GROUP)
    updated = db.table("clients").select("*").eq("id", item_id).execute()
    return {"item": _client_to_item(updated.data[0], section).model_dump()}


@router.delete("/org/items/{item_id}", status_code=204)
def delete_org_item(item_id: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    lib_row = (
        db.table("org_library")
        .select("id")
        .eq("id", item_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if lib_row.data:
        db.table("org_library").update({"deleted_at": now}).eq("id", item_id).execute()
        db.table("org_library").update({"deleted_at": now}).eq("folder_path", item_id).eq("org_id", user.org_id).is_("deleted_at", "null").execute()
        return

    c_row = (
        db.table("clients")
        .select("id")
        .eq("id", item_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not c_row.data:
        raise HTTPException(404, "Item not found")
    db.table("clients").update({"deleted_at": now}).eq("id", item_id).execute()
    db.table("contracts").update({"deleted_at": now}).eq("client_id", item_id).is_("deleted_at", "null").execute()
    db.table("org_library").update({"deleted_at": now}).eq("client_id", item_id).is_("deleted_at", "null").execute()
    # Clean up client_sections mapping
    s = _load_settings(db, user.org_id)
    cs = s.get("client_sections", {})
    cs.pop(item_id, None)
    s["client_sections"] = cs
    _save_settings(db, user.org_id, s)


# ─── Sections endpoints ──────────────────────────────────────────────────────

@router.get("/org/sections", response_model=dict)
def list_org_sections(user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    names = _all_section_names(db, user.org_id)
    return {"sections": [_section_obj(n).model_dump() for n in names]}


@router.post("/org/sections", status_code=201, response_model=dict)
def create_org_section(body: OrgSectionCreate, user: AuthUser = Depends(require_admin)) -> dict:
    db = get_db()
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Section name cannot be empty")
    if name == _DEFAULT_GROUP:
        raise HTTPException(400, "A 'General' section already exists")
    existing = _all_section_names(db, user.org_id)
    if name in existing:
        raise HTTPException(409, f"Section '{name}' already exists")
    s = _load_settings(db, user.org_id)
    pending: list = s.get("pending_org_sections", [])
    pending.append(name)
    s["pending_org_sections"] = pending
    _save_settings(db, user.org_id, s)
    return {"section": _section_obj(name).model_dump()}


@router.patch("/org/sections/{section_id}", response_model=dict)
def update_org_section(
    section_id: str, body: OrgSectionPatch, user: AuthUser = Depends(require_admin)
) -> dict:
    if section_id == _DEFAULT_GROUP:
        raise HTTPException(400, "Cannot rename the default section")
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(400, "Section name cannot be empty")
    db = get_db()
    existing = _all_section_names(db, user.org_id)
    if section_id not in existing:
        raise HTTPException(404, "Section not found")
    if new_name in existing and new_name != section_id:
        raise HTTPException(409, f"Section '{new_name}' already exists")

    # Rename in org_library
    db.table("org_library").update({"group_name": new_name}).eq("group_name", section_id).eq("org_id", user.org_id).execute()

    # Rename in client_sections
    s = _load_settings(db, user.org_id)
    cs: dict = s.get("client_sections", {})
    for cid, val in cs.items():
        if val == section_id:
            cs[cid] = new_name
    s["client_sections"] = cs

    # Rename in pending list
    pending: list = s.get("pending_org_sections", [])
    s["pending_org_sections"] = [new_name if p == section_id else p for p in pending]
    _save_settings(db, user.org_id, s)

    return {"section": _section_obj(new_name).model_dump()}


@router.delete("/org/sections/{section_id}", status_code=204)
def delete_org_section(section_id: str, user: AuthUser = Depends(require_admin)) -> None:
    if section_id == _DEFAULT_GROUP:
        raise HTTPException(400, "Cannot delete the default section")
    db = get_db()
    existing = _all_section_names(db, user.org_id)
    if section_id not in existing:
        raise HTTPException(404, "Section not found")

    # Move all library items in this section to General
    db.table("org_library").update({"group_name": _DEFAULT_GROUP}).eq("group_name", section_id).eq("org_id", user.org_id).is_("deleted_at", "null").execute()

    # Reset clients in this section
    s = _load_settings(db, user.org_id)
    cs: dict = s.get("client_sections", {})
    for cid in list(cs):
        if cs[cid] == section_id:
            del cs[cid]
    s["client_sections"] = cs

    # Remove from pending list
    pending: list = s.get("pending_org_sections", [])
    s["pending_org_sections"] = [p for p in pending if p != section_id]
    _save_settings(db, user.org_id, s)
