from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_admin, require_org, require_write
from app.FyTic_app.models import (
    ClientCreate, ClientDetail, ClientListItem, ClientPatch, DocumentListItem,
)
from app.FyTic_app.ai import compute_progress

router = APIRouter(tags=["clients"])


def _doc_count(db, org_id: str, client_id: str) -> int:
    rows = (
        db.table("contracts")
        .select("id")
        .eq("org_id", org_id)
        .eq("client_id", client_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return len(rows.data)


def _to_list_item(row: dict, doc_count: int = 0) -> ClientListItem:
    return ClientListItem(
        id=row["id"],
        name=row["name"],
        rfc=row.get("rfc"),
        initials=row.get("initials"),
        accentColor=row.get("accent_color", "#6366f1"),
        email=row.get("contact_email"),
        contact=row.get("contact_name"),
        caseDescription=row.get("case_description"),
        document_count=doc_count,
    )


def _contract_to_list_item(c: dict) -> DocumentListItem:
    template_vars = c.get("variables") or {}
    template_sigs = c.get("signatures") or {}
    detected = list(template_vars.keys())
    progress = compute_progress(detected, template_vars, [], template_sigs)
    return DocumentListItem(
        id=c["id"],
        templateId=c.get("template_id"),
        clientId=c.get("client_id"),
        title=c.get("title", ""),
        type=c.get("type", "contract"),
        status=c.get("status", "draft"),
        createdAt=c.get("created_at", ""),
        progress=progress,
    )


@router.get("/clients", response_model=dict)
def list_clients(
    with_docs: bool = False,
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()
    rows = (
        db.table("clients")
        .select("*")
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .order("name")
        .execute()
    )
    clients = []
    for row in rows.data:
        count = _doc_count(db, user.org_id, row["id"]) if not with_docs else 0
        item = _to_list_item(row, count)
        clients.append(item.model_dump())
    return {"clients": clients}


@router.get("/clients/{client_id}", response_model=dict)
def get_client(client_id: str, user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    row = (
        db.table("clients")
        .select("*")
        .eq("id", client_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Client not found")
    c = row.data[0]
    contracts = (
        db.table("contracts")
        .select("*")
        .eq("client_id", client_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    docs = [_contract_to_list_item(doc).model_dump() for doc in contracts.data]
    detail = ClientDetail(
        id=c["id"],
        name=c["name"],
        rfc=c.get("rfc"),
        initials=c.get("initials"),
        accentColor=c.get("accent_color", "#6366f1"),
        email=c.get("contact_email"),
        contact=c.get("contact_name"),
        caseDescription=c.get("case_description"),
        address=c.get("address"),
        tags=c.get("tags") or [],
        document_count=len(docs),
        documents=docs,
    )
    return {"client": detail.model_dump()}


@router.post("/clients", status_code=201, response_model=dict)
def create_client(body: ClientCreate, user: AuthUser = Depends(require_write)) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "org_id": user.org_id,
        "name": body.name,
        "rfc": body.rfc,
        "address": body.address,
        "contact_name": body.contact,
        "contact_email": body.email,
        "initials": body.initials or (body.name[:2].upper() if body.name else ""),
        "accent_color": body.accentColor,
        "case_description": body.caseDescription,
        "tags": body.tags or [],
        "is_active": True,
        "created_by": user.user_id,
        "created_at": now,
    }
    result = db.table("clients").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    return {"client": _to_list_item(result.data[0]).model_dump()}


@router.patch("/clients/{client_id}", response_model=dict)
def update_client(
    client_id: str, body: ClientPatch, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    existing = (
        db.table("clients")
        .select("id")
        .eq("id", client_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not existing.data:
        raise HTTPException(404, "Client not found")
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.rfc is not None:
        updates["rfc"] = body.rfc
    if body.address is not None:
        updates["address"] = body.address
    if body.contact is not None:
        updates["contact_name"] = body.contact
    if body.email is not None:
        updates["contact_email"] = body.email
    if body.initials is not None:
        updates["initials"] = body.initials
    if body.accentColor is not None:
        updates["accent_color"] = body.accentColor
    if body.caseDescription is not None:
        updates["case_description"] = body.caseDescription
    if body.tags is not None:
        updates["tags"] = body.tags
    if updates:
        db.table("clients").update(updates).eq("id", client_id).execute()
    row = db.table("clients").select("*").eq("id", client_id).execute()
    count = _doc_count(db, user.org_id, client_id)
    return {"client": _to_list_item(row.data[0], count).model_dump()}


@router.delete("/clients/{client_id}", status_code=204)
def delete_client(client_id: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    existing = (
        db.table("clients")
        .select("id")
        .eq("id", client_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not existing.data:
        raise HTTPException(404, "Client not found")
    now = datetime.now(timezone.utc).isoformat()
    db.table("clients").update({"deleted_at": now}).eq("id", client_id).execute()
    # Cascade soft-delete contracts and org_library items for this client
    db.table("contracts").update({"deleted_at": now}).eq("client_id", client_id).is_("deleted_at", "null").execute()
    db.table("org_library").update({"deleted_at": now}).eq("client_id", client_id).is_("deleted_at", "null").execute()
