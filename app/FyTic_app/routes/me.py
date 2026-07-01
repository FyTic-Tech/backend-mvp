from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_org
from app.FyTic_app.models import MePatch, MeResponse

router = APIRouter(tags=["me"])

_HARDCODED_TOKEN_LIMIT = 50


def _build_me(user_id: str, db) -> MeResponse:
    user_row = (
        db.table("users")
        .select("*")
        .eq("id", user_id)
        .execute()
    )
    if not user_row.data:
        raise HTTPException(404, "User not found")
    u = user_row.data[0]

    org_name: str | None = None
    token_limit = _HARDCODED_TOKEN_LIMIT
    if u.get("org_id"):
        org = db.table("organizations").select("name").eq("id", u["org_id"]).execute()
        if org.data:
            org_name = org.data[0]["name"]
        sub = (
            db.table("subscriptions")
            .select("plan_id")
            .eq("org_id", u["org_id"])
            .execute()
        )
        if sub.data:
            plan = db.table("plans").select("tokens_per_day").eq("id", sub.data[0]["plan_id"]).execute()
            if plan.data:
                token_limit = plan.data[0].get("tokens_per_day", _HARDCODED_TOKEN_LIMIT)

    date_created = (u.get("created_at") or "")[:10]
    return MeResponse(
        id=user_id,
        email=u.get("email", ""),
        fullName=u.get("full_name"),
        organization=org_name,
        role=u.get("role", ""),
        position=u.get("position"),
        practiceArea=u.get("practice_area"),
        phone=u.get("phone"),
        loginMethod=u.get("auth_provider"),
        dateCreated=date_created,
        referralCode=u.get("ref_code"),
        referredBy=u.get("referred_by"),
        surveyCompleted=bool(u.get("survey_completed")),
        tokensUsed=u.get("tokens_used_today", 0) or 0,
        tokenLimit=token_limit,
    )


@router.get("/me", response_model=MeResponse)
def get_me(user: AuthUser = Depends(require_org)) -> MeResponse:
    return _build_me(user.user_id, get_db())


@router.patch("/me", response_model=MeResponse)
def patch_me(body: MePatch, user: AuthUser = Depends(require_org)) -> MeResponse:
    db = get_db()
    updates: dict = {}
    if body.fullName is not None:
        updates["full_name"] = body.fullName
    if body.position is not None:
        updates["position"] = body.position
    if body.practiceArea is not None:
        updates["practice_area"] = body.practiceArea
    if body.phone is not None:
        updates["phone"] = body.phone
    if updates:
        db.table("users").update(updates).eq("id", user.user_id).execute()
    return _build_me(user.user_id, db)
