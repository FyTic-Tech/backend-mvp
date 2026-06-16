"""
Fixtures compartidos para toda la suite de tests.

Requisito previo — crear la base de datos de test una sola vez:
    docker exec fytic_saas_db psql -U fytic -c "CREATE DATABASE fytic_test;"
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.db_models  # noqa: F401 — registra FirmClient y FileRow en Base.metadata
from app.config import settings
from app.database import Base, get_session
from main import app

TEST_DB_URL = "postgresql+psycopg://fytic:fytic@localhost:5432/fytic_test"
DEMO_FIRM_ID = uuid.UUID(settings.demo_firm_id)

_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)


# ─── Setup / teardown de tablas ───────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Crea las tablas al inicio de la sesión y las borra al final."""
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)
    _engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    """Trunca todas las tablas después de cada test para aislamiento."""
    yield
    with _engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE files, firm_clients CASCADE"))
        conn.commit()


# ─── Sesión de BD por test ────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Sesión SQLAlchemy contra la BD de test. Compartida con los route handlers."""
    Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# ─── Cliente HTTP ─────────────────────────────────────────────────────────────

@pytest.fixture
def client(db, tmp_path, monkeypatch):
    """
    TestClient con:
    - get_session overrideado para usar la BD de test.
    - UPLOAD_ROOT redirigido a tmp_path para no tocar var/uploads real.
    """
    import app.files.storage as storage_mod
    import app.files.router as router_mod

    monkeypatch.setattr(storage_mod, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(router_mod, "UPLOAD_ROOT", tmp_path)

    def override_get_session():
        yield db

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


# ─── Datos base ───────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_clients(db):
    """Inserta los 3 clientes demo. La mayoría de tests los necesita."""
    from app.db_models import FirmClient

    data = [
        {"slug": "mendoza-asociados", "name": "Mendoza & Asociados", "color": "#3b82f6", "areas": ["Arrendamiento", "Civil", "Corporativo"]},
        {"slug": "garcia-vargas-s-a", "name": "García Vargas S.A.", "color": "#10b981", "areas": ["Mercantil", "Corporativo", "Fiscal"]},
        {"slug": "ruiz-hernandez", "name": "Ruiz Hernández", "color": "#8b5cf6", "areas": ["Familiar", "Divorcio", "Alimentos"]},
    ]

    clients = []
    for d in data:
        c = FirmClient(firm_id=DEMO_FIRM_ID, **d)
        db.add(c)
        clients.append(c)
    db.commit()
    for c in clients:
        db.refresh(c)
    return clients


# ─── Helpers reutilizables ────────────────────────────────────────────────────

def fake_file(filename: str, content: bytes = b"contenido de prueba") -> dict:
    return {"file": (filename, io.BytesIO(content), "application/octet-stream")}


def upload_pdf(api_client, slug="mendoza-asociados", filename="doc.pdf", parent_id=None):
    data = {"parent_id": parent_id} if parent_id else None
    return api_client.post(
        f"/api/app/clients/{slug}/files",
        files=fake_file(filename),
        data=data,
    )


def make_folder(api_client, name="Contratos", client_slug="mendoza-asociados", parent_id=None):
    body = {"name": name, "clientSlug": client_slug}
    if parent_id:
        body["parentId"] = parent_id
    return api_client.post("/api/app/files", json=body)
