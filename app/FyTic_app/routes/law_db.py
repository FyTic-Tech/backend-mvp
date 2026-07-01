from fastapi import APIRouter, Depends

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_org
from app.FyTic_app.models import LawDoc, LawGroup

router = APIRouter(tags=["law-db"])


@router.get("/law-db", response_model=dict)
def list_law_db(user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    rows = (
        db.table("fytic_library")
        .select("*")
        .eq("is_active", True)
        .order("group_name")
        .order("name")
        .execute()
    )
    groups: dict[str, list] = {}
    for row in rows.data:
        group_name = row.get("group_name") or "General"
        if group_name not in groups:
            groups[group_name] = []
        publish_date: str = row.get("publish_date") or ""
        year: int | None = int(publish_date[:4]) if publish_date and len(publish_date) >= 4 else None
        groups[group_name].append(
            LawDoc(
                id=row["id"],
                name=row.get("name", ""),
                scope=row.get("scope", "national"),
                year=year,
                vigente=bool(row.get("vigente", True)),
                hasNewReforms=bool(row.get("has_new_reforms", False)),
                url=row.get("url"),
                pdfLink=row.get("pdf_link"),
            ).model_dump()
        )
    return {"groups": [{"name": k, "docs": v} for k, v in groups.items()]}
