import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.db_models import FileRow, FirmClient
from app.app_clients.schemas import ClientOut
from app.files.schemas import FileItem, to_file_item

router = APIRouter(tags=["clients"])

_DEMO_FIRM_ID = uuid.UUID(settings.demo_firm_id)


@router.get("/clients", response_model=list[ClientOut])
def list_clients(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(FirmClient).where(FirmClient.firm_id == _DEMO_FIRM_ID)
    ).all()
    return rows


@router.get("/clients/{slug}/files", response_model=list[FileItem])
def list_client_files(
    slug: str,
    type: Optional[str] = None,
    session: Session = Depends(get_session),
):
    client = session.scalar(
        select(FirmClient).where(
            FirmClient.firm_id == _DEMO_FIRM_ID, FirmClient.slug == slug
        )
    )
    if not client:
        raise HTTPException(404, f"client '{slug}' not found")

    stmt = select(FileRow).where(
        FileRow.firm_id == _DEMO_FIRM_ID, FileRow.client_id == client.id
    )
    if type:
        stmt = stmt.where(FileRow.type == type)

    rows = session.scalars(stmt).all()
    return [to_file_item(r) for r in rows]
