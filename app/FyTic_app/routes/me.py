from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.FyTic_app.auth import AuthUser, get_current_user
from app.FyTic_app.models import MePatch, MeResponse

router = APIRouter(tags=["me"])


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
    if u.get("org_id"):
        org = db.table("organizations").select("name").eq("id", u["org_id"]).execute()
        if org.data:
            org_name = org.data[0]["name"]

    date_created = (u.get("created_at") or "")[:10]
    return MeResponse(
        id=user_id,
        email=u.get("email", ""),
        fullName=u.get("full_name"),
        firmName=u.get("firm_name"),
        teamSize=u.get("team_size"),
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
        tokenLimit=None,  # unlimited for now
    )


@router.get("/me", response_model=MeResponse)
def get_me(user: AuthUser = Depends(get_current_user)) -> MeResponse:
    return _build_me(user.user_id, get_db())


@router.patch("/me", response_model=MeResponse)
def patch_me(body: MePatch, user: AuthUser = Depends(get_current_user)) -> MeResponse:
    db = get_db()
    updates: dict = {}
    if body.fullName is not None:
        updates["full_name"] = body.fullName
    if body.firmName is not None:
        updates["firm_name"] = body.firmName
    if body.teamSize is not None:
        updates["team_size"] = body.teamSize
    if body.position is not None:
        updates["position"] = body.position
    if body.practiceArea is not None:
        updates["practice_area"] = body.practiceArea
    if body.phone is not None:
        updates["phone"] = body.phone
    if updates:
        db.table("users").update(updates).eq("id", user.user_id).execute()
    return _build_me(user.user_id, db)
