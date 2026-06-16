"""
Seed 3 demo clients for DEMO_FIRM_ID. Safe to run multiple times (upsert by slug).

Usage (from backend-mvp/):
    python scripts/seed_demo.py
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import SessionLocal
from app.db_models import FirmClient

DEMO_FIRM_ID = uuid.UUID(settings.demo_firm_id)

CLIENTS = [
    {
        "slug": "mendoza-asociados",
        "name": "Mendoza & Asociados",
        "color": "#3b82f6",
        "areas": ["Arrendamiento", "Civil", "Corporativo"],
    },
    {
        "slug": "garcia-vargas-s-a",
        "name": "García Vargas S.A.",
        "color": "#10b981",
        "areas": ["Mercantil", "Corporativo", "Fiscal"],
    },
    {
        "slug": "ruiz-hernandez",
        "name": "Ruiz Hernández",
        "color": "#8b5cf6",
        "areas": ["Familiar", "Divorcio", "Alimentos"],
    },
]


def main():
    with SessionLocal() as session:
        for c in CLIENTS:
            stmt = (
                insert(FirmClient)
                .values(
                    id=uuid.uuid4(),
                    firm_id=DEMO_FIRM_ID,
                    slug=c["slug"],
                    name=c["name"],
                    color=c["color"],
                    areas=c["areas"],
                )
                .on_conflict_do_update(
                    index_elements=["firm_id", "slug"],
                    set_={"name": c["name"], "color": c["color"], "areas": c["areas"]},
                )
            )
            session.execute(stmt)
        session.commit()
        print(f"Seeded {len(CLIENTS)} clients for firm {DEMO_FIRM_ID}")


if __name__ == "__main__":
    main()
