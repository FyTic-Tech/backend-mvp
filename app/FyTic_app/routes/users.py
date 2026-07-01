from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_admin, require_org
from app.FyTic_app.models import MemberInvite, MemberPatch, OrgMember

router = APIRouter(tags=["users"])

_ORG_ROLES = {"admin", "member", "limited"}
_INTERNAL_ROLES = {"super_admin", "internal_dev", "internal_team"}


def _to_member(row: dict) -> OrgMember:
    full_name = row.get("full_name") or ""
    initials = "".join(p[0].upper() for p in full_name.split() if p)[:2] if full_name else ""
    status = "inactive" if not row.get("is_active") else "active"
    return OrgMember(
        id=row["id"],
        orgId=row.get("org_id"),
        email=row.get("email", ""),
        fullName=full_name or None,
        role=row.get("role", ""),
        position=row.get("position"),
        status=status,
        avatarInitials=initials or None,
        createdAt=row.get("created_at", ""),
        updatedAt=row.get("modified_at"),
    )


@router.get("/users", response_model=dict)
def list_members(user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    rows = (
        db.table("users")
        .select("*")
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .neq("role", "super_admin")
        .neq("role", "internal_dev")
        .neq("role", "internal_team")
        .order("created_at")
        .execute()
    )
    return {"members": [_to_member(r).model_dump() for r in rows.data]}


@router.post("/users", status_code=201, response_model=dict)
def invite_member(body: MemberInvite, user: AuthUser = Depends(require_admin)) -> dict:
    if body.role not in _ORG_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(_ORG_ROLES))}")
    db = get_db()
    # Check if a user with this email already exists
    existing = db.table("users").select("id,org_id").eq("email", body.email).execute()
    if existing.data:
        ex = existing.data[0]
        if ex.get("org_id") and ex["org_id"] != user.org_id:
            raise HTTPException(409, "User already belongs to another organization")
        if ex.get("org_id") == user.org_id:
            raise HTTPException(409, "User is already a member of this org")
        # User exists but has no org — assign them
        updates = {"org_id": user.org_id, "role": body.role}
        if body.full_name:
            updates["full_name"] = body.full_name
        if body.position:
            updates["position"] = body.position
        db.table("users").update(updates).eq("id", ex["id"]).execute()
        row = db.table("users").select("*").eq("id", ex["id"]).execute().data[0]
        return {"member": _to_member(row).model_dump()}

    # New user — create a placeholder row (they'll complete signup via Supabase Auth)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "email": body.email,
        "full_name": body.full_name,
        "position": body.position,
        "org_id": user.org_id,
        "role": body.role,
        "is_active": True,
        "created_at": now,
    }
    result = db.table("users").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    # Resend invitation email — pending implementation
    return {"member": _to_member(result.data[0]).model_dump()}


@router.patch("/users/{member_id}", response_model=dict)
def update_member(
    member_id: str, body: MemberPatch, user: AuthUser = Depends(require_admin)
) -> dict:
    db = get_db()
    row = (
        db.table("users")
        .select("id,org_id,role")
        .eq("id", member_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Member not found")
    m = row.data[0]
    if m.get("role") in _INTERNAL_ROLES:
        raise HTTPException(403, "Cannot modify internal roles through this endpoint")
    if body.role and body.role not in _ORG_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(_ORG_ROLES))}")

    updates: dict = {}
    if body.full_name is not None:
        updates["full_name"] = body.full_name
    if body.role is not None:
        updates["role"] = body.role
    if body.position is not None:
        updates["position"] = body.position
    if body.status is not None:
        updates["is_active"] = body.status == "active"
    if updates:
        db.table("users").update(updates).eq("id", member_id).execute()
    updated = db.table("users").select("*").eq("id", member_id).execute()
    return {"member": _to_member(updated.data[0]).model_dump()}


@router.delete("/users/{member_id}", status_code=204)
def remove_member(member_id: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    row = (
        db.table("users")
        .select("id,role")
        .eq("id", member_id)
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "Member not found")
    m = row.data[0]
    if m.get("role") in _INTERNAL_ROLES:
        raise HTTPException(403, "Cannot remove internal-role users through this endpoint")
    if m.get("role") == "admin" and user.role != "super_admin":
        raise HTTPException(403, "Only super_admin can remove admin members")
    db.table("users").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat(), "org_id": None}
    ).eq("id", member_id).execute()
