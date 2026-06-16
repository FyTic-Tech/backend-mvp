from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

UPLOAD_ROOT = Path(settings.upload_root).resolve()
ALLOWED_EXT = {".pdf", ".docx"}


def _resolve(storage_path: str) -> Path:
    target = (UPLOAD_ROOT / storage_path).resolve()
    if not target.is_relative_to(UPLOAD_ROOT):
        raise HTTPException(400, "invalid storage path")
    return target


def save_upload(file: UploadFile, storage_path: str) -> tuple[int, str]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"tipo no permitido: {ext}")
    target = _resolve(storage_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    hasher, size = sha256(), 0
    with target.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            hasher.update(chunk)
            out.write(chunk)
    return size, hasher.hexdigest()


def delete_file(storage_path: str) -> None:
    p = _resolve(storage_path)
    p.unlink(missing_ok=True)
