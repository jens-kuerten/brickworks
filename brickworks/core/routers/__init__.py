from fastapi import APIRouter

from .auth_router import auth_router

core_router = APIRouter(prefix="/core", tags=["core"])

core_router.include_router(auth_router)
