from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.landing.router import router as landing_router
from app.FyTic_app.router import router as app_router

app = FastAPI(title="FyTic API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else list(filter(None, [settings.frontend_url, settings.app_frontend_url])),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Internal-Key"],
)

app.include_router(landing_router, prefix="/api")
app.include_router(app_router, prefix="/api/app/v1")


@app.on_event("startup")
async def _check_supabase() -> None:
    url = settings.supabase_url
    key = settings.supabase_service_key
    print(f"\n{'='*55}")
    print(f"  SUPABASE_URL        : {url or '(empty)'}")
    print(f"  SUPABASE_SERVICE_KEY: {key[:30]}..." if key else "  SUPABASE_SERVICE_KEY: (empty)")
    print(f"  JWT_SECRET          : {'set' if settings.supabase_jwt_secret else '(empty — app auth disabled)'}")
    print(f"  GEMINI_API_KEY      : {'set' if settings.gemini_api_key else '(empty — AI disabled)'}")
    try:
        from app.db import get_db
        result = get_db().table("users").select("id").limit(1).execute()
        print(f"  Supabase connection : OK — {len(result.data)} row(s) returned")
    except Exception as exc:
        print(f"  Supabase connection : FAILED — {exc}")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=settings.is_dev)
