from fastapi import APIRouter

from app.api.routes import (
    auth,
    dashboard,
    expenses,
    notifications,
    projects,
    reconciliations,
    reports,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(expenses.router)
api_router.include_router(reports.router)
api_router.include_router(reconciliations.router)
api_router.include_router(dashboard.router)
api_router.include_router(notifications.router)
