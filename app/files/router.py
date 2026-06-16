import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.db_models import FileRow, FirmClient
from app.files.schemas import FileItem, FileUpdate, FolderCreate, to_file_item
from app.files.storage import UPLOAD_ROOT, delete_file, save_upload

router = APIRouter(tags=["files"])

_DEMO_FIRM_ID = uuid.UUID(settings.demo_firm_id)

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _validate_parent(parent_id: str | None, session: Session) -> uuid.UUID | None:
    if not parent_id:
        return None
    pid = uuid.UUID(parent_id)
    parent = session.get(FileRow, pid)
    if not parent or parent.firm_id != _DEMO_FIRM_ID:
        raise HTTPException(404, "parent folder not found")
    if parent.type != "folder":
        raise HTTPException(400, "parent must be a folder, not a file")
    return pid


def _resolve_client(slug: str, session: Session) -> FirmClient:
    client = session.scalar(
        select(FirmClient).where(
            FirmClient.firm_id == _DEMO_FIRM_ID, FirmClient.slug == slug
        )
    )
    if not client:
        raise HTTPException(404, f"client '{slug}' not found")
    return client


@router.get("/files", response_model=list[FileItem])
def list_files(
    clientSlug: Optional[str] = None,
    session: Session = Depends(get_session),
):
    stmt = select(FileRow).where(FileRow.firm_id == _DEMO_FIRM_ID)
    if clientSlug:
        client = _resolve_client(clientSlug, session)
        stmt = stmt.where(FileRow.client_id == client.id)
    rows = session.scalars(stmt).all()
    return [to_file_item(r) for r in rows]


@router.post("/clients/{slug}/files", response_model=FileItem, status_code=201)
def upload_file(
    slug: str,
    file: UploadFile,
    parent_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    client = _resolve_client(slug, session)
    ext = Path(file.filename or "").suffix.lower()
    file_id = uuid.uuid4()
    storage_path = f"{_DEMO_FIRM_ID}/{client.id}/{file_id}{ext}"
    size, content_hash = save_upload(file, storage_path)

    row = FileRow(
        id=file_id,
        firm_id=_DEMO_FIRM_ID,
        client_id=client.id,
        parent_id=_validate_parent(parent_id, session),
        name=file.filename or f"{file_id}{ext}",
        type="file",
        storage_path=storage_path,
        mime_type=MIME_MAP.get(ext, file.content_type),
        size=size,
        content_hash=content_hash,
        ingestion_status="pending",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_file_item(row)


@router.post("/files", response_model=FileItem, status_code=201)
def create_folder(body: FolderCreate, session: Session = Depends(get_session)):
    client_id = None
    if body.clientSlug:
        client = _resolve_client(body.clientSlug, session)
        client_id = client.id

    row = FileRow(
        firm_id=_DEMO_FIRM_ID,
        client_id=client_id,
        parent_id=_validate_parent(body.parentId, session),
        name=body.name,
        type="folder",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_file_item(row)


@router.patch("/files/{file_id}", response_model=FileItem)
def update_file(
    file_id: uuid.UUID,
    body: FileUpdate,
    session: Session = Depends(get_session),
):
    row = session.get(FileRow, file_id)
    if not row or row.firm_id != _DEMO_FIRM_ID:
        raise HTTPException(404, "file not found")
    if body.name is not None:
        row.name = body.name
    if body.parentId is not None:
        row.parent_id = _validate_parent(body.parentId, session)
    session.commit()
    session.refresh(row)
    return to_file_item(row)


def _collect_storage_paths(file_id: uuid.UUID, session: Session) -> list[str]:
    """Recursively collect storage_path of all file descendants."""
    paths = []
    stack = [file_id]
    while stack:
        current = stack.pop()
        row = session.get(FileRow, current)
        if not row:
            continue
        if row.type == "file" and row.storage_path:
            paths.append(row.storage_path)
        children = session.scalars(
            select(FileRow).where(FileRow.parent_id == current)
        ).all()
        for child in children:
            stack.append(child.id)
    return paths


@router.delete("/files/{file_id}", status_code=204)
def delete_file_endpoint(
    file_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    row = session.get(FileRow, file_id)
    if not row or row.firm_id != _DEMO_FIRM_ID:
        raise HTTPException(404, "file not found")
    for path in _collect_storage_paths(file_id, session):
        delete_file(path)
    session.delete(row)
    session.commit()


@router.get("/files/{file_id}/content")
def download_file(
    file_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    row = session.get(FileRow, file_id)
    if not row or row.firm_id != _DEMO_FIRM_ID:
        raise HTTPException(404, "file not found")
    if row.type != "file" or not row.storage_path:
        raise HTTPException(400, "not a file")
    full_path = (UPLOAD_ROOT / row.storage_path).resolve()
    if not full_path.exists():
        raise HTTPException(404, "file not found on disk")
    return FileResponse(
        path=str(full_path),
        media_type=row.mime_type or "application/octet-stream",
        filename=row.name,
    )
