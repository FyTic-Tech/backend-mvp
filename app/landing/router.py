import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .models import ClientsResponse, OkResponse, WaitlistEntryCreate, WaitlistStatusResponse

router = APIRouter()
_DATA = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


def _save(name: str, data: dict) -> None:
    (_DATA / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@router.get("/content")
def get_content() -> dict:
    return _load("content.json")


@router.get("/clients", response_model=ClientsResponse)
def get_clients() -> ClientsResponse:
    return _load("clients.json")


@router.get("/waitlist", response_model=WaitlistStatusResponse)
def get_waitlist_status() -> WaitlistStatusResponse:
    return {"active": _load("waitlist.json")["active"]}


@router.post("/waitlist", status_code=201, response_model=OkResponse)
def submit_waitlist(entry: WaitlistEntryCreate) -> OkResponse:
    data = _load("waitlist.json")
    if not data["active"]:
        raise HTTPException(status_code=403, detail="waitlist is closed")
    record = entry.model_dump()
    record["submittedAt"] = datetime.now(timezone.utc).isoformat()
    data["entries"].append(record)
    _save("waitlist.json", data)
    return {"ok": True}
