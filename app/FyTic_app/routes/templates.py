from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_admin, require_org, require_write
from app.FyTic_app.models import TemplateGroupCreate, TemplateGroupRename, TemplatePatch
from app.FyTic_app.ai import ai_import_template, extract_text_from_bytes, extract_variables

router = APIRouter(tags=["templates"])

_FYTIC_SOURCE = "fytic"
_USER_SOURCE = "user"


def _to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row.get("name", ""),
        "group": row.get("group_name"),
        "source": row.get("source", _USER_SOURCE),
        "content": row.get("content") or [],
        "signatories": row.get("signatories") or [],
        "detected_variables": row.get("variables") or [],
    }


@router.get("/templates", response_model=dict)
def list_templates(
    group: str | None = None,
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()
    fytic_q = (
        db.table("templates")
        .select("*")
        .eq("source", _FYTIC_SOURCE)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("name")
    )
    user_q = (
        db.table("templates")
        .select("*")
        .eq("source", _USER_SOURCE)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .order("name")
    )
    if group:
        user_q = user_q.eq("group_name", group)

    fytic_rows = fytic_q.execute()
    user_rows = user_q.execute()
    return {
        "fytic": [_to_dict(r) for r in fytic_rows.data],
        "user": [_to_dict(r) for r in user_rows.data],
    }


@router.post("/templates/import", response_model=dict)
async def import_template(
    file: UploadFile = File(...),
    name: str = Query(...),
    group: str | None = Query(default=None),
    user: AuthUser = Depends(require_write),
) -> dict:
    db = get_db()
    data = await file.read()
    raw_text = extract_text_from_bytes(file.filename or "upload.txt", data)
    parsed = ai_import_template(raw_text, file.filename or name)

    content: list = parsed.get("content") or [raw_text[:2000]]
    detected = parsed.get("variables") or extract_variables(content)
    signatories = parsed.get("signatories") or []
    suggested_name = parsed.get("name") or name
    risk_clauses = parsed.get("risk_clauses") or []

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "org_id": user.org_id,
        "source": _USER_SOURCE,
        "name": name,
        "group_name": group or "",
        "content": content,
        "variables": detected,
        "signatories": signatories,
        "is_active": True,
        "created_by": user.user_id,
        "created_at": now,
    }
    result = db.table("templates").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    t = result.data[0]
    return {
        "template": {
            **_to_dict(t),
            "suggested_name": suggested_name,
            "risk_clauses": risk_clauses,
        }
    }


@router.patch("/templates/{template_id}", response_model=dict)
def update_template(
    template_id: str, body: TemplatePatch, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    row = (
        db.table("templates")
        .select("id,source,org_id")
        .eq("id", template_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Template not found")
    t = row.data[0]
    if t.get("source") == _FYTIC_SOURCE:
        raise HTTPException(403, "FyTic system templates cannot be modified")
    if t.get("org_id") != user.org_id:
        raise HTTPException(403, "Not your template")
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.group is not None:
        updates["group_name"] = body.group
    if updates:
        db.table("templates").update(updates).eq("id", template_id).execute()
    updated = db.table("templates").select("*").eq("id", template_id).execute()
    return {"template": _to_dict(updated.data[0])}


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    row = (
        db.table("templates")
        .select("id,source,org_id")
        .eq("id", template_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Template not found")
    t = row.data[0]
    if t.get("source") == _FYTIC_SOURCE:
        raise HTTPException(403, "FyTic system templates cannot be deleted")
    if t.get("org_id") != user.org_id:
        raise HTTPException(403, "Not your template")
    db.table("templates").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", template_id).execute()


# ─── Template groups ─────────────────────────────────────────────────────────

def _get_groups(db, org_id: str) -> list[str]:
    rows = (
        db.table("templates")
        .select("group_name")
        .eq("source", _USER_SOURCE)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    seen: set = set()
    result: list[str] = []
    for r in rows.data:
        g = r.get("group_name") or ""
        if g and g not in seen:
            seen.add(g)
            result.append(g)
    return sorted(result)


@router.get("/template-groups", response_model=dict)
def list_groups(user: AuthUser = Depends(require_org)) -> dict:
    return {"groups": _get_groups(get_db(), user.org_id)}


@router.post("/template-groups", status_code=201, response_model=dict)
def create_group(body: TemplateGroupCreate, user: AuthUser = Depends(require_admin)) -> dict:
    db = get_db()
    groups = _get_groups(db, user.org_id)
    if body.name not in groups:
        groups.append(body.name)
        groups.sort()
    return {"groups": groups}


@router.patch("/template-groups/{name}", response_model=dict)
def rename_group(
    name: str, body: TemplateGroupRename, user: AuthUser = Depends(require_admin)
) -> dict:
    db = get_db()
    rows = (
        db.table("templates")
        .select("id")
        .eq("source", _USER_SOURCE)
        .eq("org_id", user.org_id)
        .eq("group_name", name)
        .is_("deleted_at", "null")
        .execute()
    )
    if not rows.data:
        raise HTTPException(404, f"Group '{name}' not found")
    db.table("templates").update({"group_name": body.new_name}).eq("group_name", name).eq("org_id", user.org_id).execute()
    return {"groups": _get_groups(db, user.org_id)}


@router.delete("/template-groups/{name}", status_code=204)
def delete_group(name: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    rows = (
        db.table("templates")
        .select("id")
        .eq("source", _USER_SOURCE)
        .eq("org_id", user.org_id)
        .eq("group_name", name)
        .is_("deleted_at", "null")
        .execute()
    )
    if not rows.data:
        raise HTTPException(404, f"Group '{name}' not found")
    db.table("templates").update({"group_name": ""}).eq("group_name", name).eq("org_id", user.org_id).execute()
