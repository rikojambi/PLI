from fastapi import APIRouter

from app.api.v1.endpoints import admin, ai, auth, dashboard, intelligence, learning, ops, portal, privacy, sync

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(portal.router)
api_router.include_router(learning.router)
api_router.include_router(intelligence.router)
api_router.include_router(ai.router)
api_router.include_router(dashboard.router)
api_router.include_router(sync.router)
api_router.include_router(privacy.router)
api_router.include_router(ops.router)
