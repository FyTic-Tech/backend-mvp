from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.landing.router import router as landing_router
from app.app_clients.router import router as app_clients_router
from app.files.router import router as files_router

app = FastAPI(title="FyTic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else [settings.frontend_url],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(landing_router, prefix="/api")
app.include_router(app_clients_router, prefix="/api/app")
app.include_router(files_router, prefix="/api/app")


@app.on_event("startup")
async def _startup() -> None:
    # Ensure upload directory exists
    Path(settings.upload_root).mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")

    # SaaS Postgres check
    try:
        from app.database import engine
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        print("  SaaS Postgres       : OK")
    except Exception as exc:
        print(f"  SaaS Postgres       : FAILED — {exc}")

    # Supabase (landing) check
    url = settings.supabase_url
    key = settings.supabase_service_key
    print(f"  SUPABASE_URL        : {url or '(empty)'}")
    print(f"  SUPABASE_SERVICE_KEY: {key[:30]}..." if key else "  SUPABASE_SERVICE_KEY: (empty)")
    try:
        from app.db import get_db
        result = get_db().table("clients").select("id").limit(1).execute()
        print(f"  Supabase connection : OK — {len(result.data)} row(s) returned")
    except Exception as exc:
        print(f"  Supabase connection : FAILED — {exc}")

    print(f"{'='*55}\n")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=settings.is_dev)
