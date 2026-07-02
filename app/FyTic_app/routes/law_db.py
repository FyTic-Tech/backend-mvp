from fastapi import APIRouter, Depends

from app.db import get_db
from app.FyTic_app.auth import AuthUser, get_current_user
from app.FyTic_app.models import LawDoc

router = APIRouter(tags=["law-db"])


@router.get("/law-db", response_model=dict)
def list_law_db(user: AuthUser = Depends(get_current_user)) -> dict:
    db = get_db()
    rows = (
        db.table("fytic_library")
        .select("*")
        .eq("is_active", True)
        .order("scope")
        .order("state")
        .order("group_name")
        .order("name")
        .execute()
    )

    # Group by (scope, state, group_name) — three-level hierarchy
    group_map: dict[tuple, list] = {}
    for row in rows.data:
        scope = row.get("scope") or "national"
        state = row.get("state")  # None for national/international
        group_name = row.get("group_name") or "General"
        key = (scope, state, group_name)
        if key not in group_map:
            group_map[key] = []
        publish_date: str = row.get("publish_date") or ""
        year: int | None = int(publish_date[:4]) if publish_date and len(publish_date) >= 4 else None
        group_map[key].append(
            LawDoc(
                id=row["id"],
                name=row.get("name", ""),
                scope=scope,
                state=state,
                year=year,
                vigente=bool(row.get("vigente", True)),
                hasNewReforms=bool(row.get("has_new_reforms", False)),
                url=row.get("url"),
                pdfLink=row.get("pdf_link"),
                otherLink=row.get("other_link"),
                publishDate=row.get("publish_date"),
                lastUpdate=row.get("last_update"),
            ).model_dump()
        )

    groups = [
        {"scope": scope, "state": state, "name": name, "docs": docs}
        for (scope, state, name), docs in group_map.items()
    ]
    return {"groups": groups}
