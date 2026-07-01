from fastapi import APIRouter

from app.FyTic_app.routes.me import router as me_router
from app.FyTic_app.routes.clients import router as clients_router
from app.FyTic_app.routes.documents import router as documents_router
from app.FyTic_app.routes.templates import router as templates_router
from app.FyTic_app.routes.users import router as users_router
from app.FyTic_app.routes.org import router as org_router
from app.FyTic_app.routes.library import router as library_router
from app.FyTic_app.routes.law_db import router as law_db_router
from app.FyTic_app.routes.scan import router as scan_router

router = APIRouter()

router.include_router(me_router)
router.include_router(clients_router)
router.include_router(documents_router)
router.include_router(templates_router)
router.include_router(users_router)
router.include_router(org_router)
router.include_router(library_router)
router.include_router(law_db_router)
router.include_router(scan_router)
