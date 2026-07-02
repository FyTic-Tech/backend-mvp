import time

from fastapi import APIRouter, Depends

from app.db import get_db
from app.FyTic_app.auth import AuthUser, get_current_user
from app.FyTic_app.models import LawDoc

router = APIRouter(tags=["law-db"])

# ─── In-memory cache for scope stats ─────────────────────────────────────────

_stats_cache: dict | None = None
_stats_cache_ts: float = 0.0
_STATS_TTL = 1800  # 30 minutes


@router.get("/law-db/scope-stats", response_model=dict)
def law_db_scope_stats(user: AuthUser = Depends(get_current_user)) -> dict:
    global _stats_cache, _stats_cache_ts

    if _stats_cache is not None and (time.time() - _stats_cache_ts) < _STATS_TTL:
        return _stats_cache

    db = get_db()
    rows = (
        db.table("fytic_library")
        .select("scope, state, group_name")
        .eq("is_active", True)
        .range(0, 9999)
        .execute()
    )

    national_groups: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    international_groups: dict[str, int] = {}

    for row in rows.data:
        scope = row.get("scope") or "national"
        state = row.get("state")
        group = row.get("group_name") or "General"

        if scope == "national":
            national_groups[group] = national_groups.get(group, 0) + 1
        elif scope == "state":
            key = state or "unknown"
            state_counts[key] = state_counts.get(key, 0) + 1
        elif scope == "international":
            international_groups[group] = international_groups.get(group, 0) + 1

    result = {
        "national": {
            "total": sum(national_groups.values()),
            "groups": [{"name": k, "count": v} for k, v in sorted(national_groups.items())],
        },
        "state": {
            "total": sum(state_counts.values()),
            "states": [{"key": k, "count": v} for k, v in sorted(state_counts.items())],
        },
        "international": {
            "total": sum(international_groups.values()),
            "groups": [{"name": k, "count": v} for k, v in sorted(international_groups.items())],
        },
    }

    _stats_cache = result
    _stats_cache_ts = time.time()
    return result


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
        .range(0, 9999)
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
