from fastapi import APIRouter

from src.api.v1.analysis import router as analysis_router
from src.api.v1.health import router as health_router
from src.api.v1.hitl import router as hitl_router
from src.api.v1.reports import router as reports_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(analysis_router)
router.include_router(hitl_router)
router.include_router(reports_router)
