from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.FyTic_app.auth import AuthUser, get_current_user
from app.FyTic_app.models import MePatch, MeResponse

router = APIRouter(tags=["me"])

_ROLE_MAP = {
    "despacho":      "Abogado en despacho",
    "independiente": "Abogado independiente",
    "corporativo":   "Abogado corporativo",
    "becario":       "Becario",
}
_AREA_MAP = {
    "civil":       "Derecho civil",
    "mercantil":   "Derecho mercantil",
    "penal":       "Derecho penal",
    "fiscal":      "Derecho fiscal",
    "laboral":     "Derecho laboral",
    "corporativo": "Derecho corporativo",
    "familiar":    "Derecho familiar",
}


def _autofill_from_waitlist(db, user_id: str, u: dict) -> None:
    """Fill empty profile fields from the user's waitlist survey entry."""
    if u.get("full_name") and u.get("position") and u.get("practice_area") and u.get("firm_name"):
        return  # nothing to fill
    wl = (
        db.table("waitlist")
        .select("role,area,name")
        .eq("user_id", user_id)
        .not_.is_("ai_question", "null")
        .neq("ai_question", "")
        .neq("id", "_config")
        .limit(1)
        .execute()
    )
    if not wl.data:
        return
    entry = wl.data[0]
    wl_role = entry.get("role", "")
    wl_area = entry.get("area", "")
    updates: dict = {}
    if not u.get("full_name") and entry.get("name"):
        updates["full_name"] = entry["name"]
        u["full_name"] = entry["name"]
    if not u.get("position") and wl_role in _ROLE_MAP:
        updates["position"] = _ROLE_MAP[wl_role]
        u["position"] = _ROLE_MAP[wl_role]
    if not u.get("practice_area") and wl_area in _AREA_MAP:
        updates["practice_area"] = _AREA_MAP[wl_area]
        u["practice_area"] = _AREA_MAP[wl_area]
    if not u.get("firm_name") and wl_role == "independiente":
        updates["firm_name"] = "Independiente"
        u["firm_name"] = "Independiente"
    if updates:
        db.table("users").update(updates).eq("id", user_id).execute()


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

    try:
        _autofill_from_waitlist(db, user_id, u)
    except Exception:
        pass  # autofill is best-effort; never crash the /me response

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
        tokenLimit=None,  # unlimited for now; token quota not yet enforced
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
