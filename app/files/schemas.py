import uuid
from typing import Optional
from pydantic import BaseModel

from app.db_models import FileRow


class FileItem(BaseModel):
    id: str
    name: str
    type: str  # 'file' | 'folder'
    parentId: Optional[str] = None
    clientId: Optional[str] = None
    path: str
    size: Optional[int] = None
    modifiedAt: str
    mimeType: Optional[str] = None


class FolderCreate(BaseModel):
    name: str
    parentId: Optional[str] = None
    clientSlug: Optional[str] = None


class FileUpdate(BaseModel):
    name: Optional[str] = None
    parentId: Optional[str] = None
    clientSlug: Optional[str] = None


def to_file_item(row: FileRow) -> FileItem:
    return FileItem(
        id=str(row.id),
        name=row.name,
        type=row.type,
        parentId=str(row.parent_id) if row.parent_id else None,
        clientId=str(row.client_id) if row.client_id else None,
        path="/" + row.name,
        size=row.size,
        modifiedAt=row.updated_at.isoformat(),
        mimeType=row.mime_type,
    )
