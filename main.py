from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.landing.router import router as landing_router

app = FastAPI(title="FyTic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else [settings.frontend_url],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(landing_router, prefix="/api")


@app.on_event("startup")
async def _check_supabase() -> None:
    url = settings.supabase_url
    key = settings.supabase_service_key
    print(f"\n{'='*55}")
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
