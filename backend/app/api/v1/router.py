from fastapi import APIRouter

from app.api.v1.routes.curriculum import router as curriculum_router
from app.api.v1.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(curriculum_router, tags=["curriculum"])
