from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.logging import configure_logging
from app.core.redis import redis_service
from app.middleware.error_handlers import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_service.ping()
    yield
    await redis_service.close()


tags_metadata = [
    {"name": "Authentication", "description": "Login, tokens, and password management."},
    {"name": "Users", "description": "User account administration."},
    {"name": "Employees", "description": "Employee records and profiles."},
    {"name": "Departments", "description": "Department management."},
    {"name": "Designations", "description": "Designation management."},
    {"name": "Attendance", "description": "Check-in/check-out and attendance history."},
    {"name": "Leave", "description": "Leave types, balances, and requests."},
    {"name": "Holidays", "description": "Company holiday calendar."},
    {"name": "Tasks", "description": "Task assignment and tracking."},
    {"name": "Documents", "description": "Employee document management."},
    {"name": "Notifications", "description": "In-app notifications."},
    {"name": "Dashboard", "description": "HR dashboard summaries and charts."},
    {"name": "Audit Logs", "description": "System audit trail."},
    {"name": "System", "description": "Health and readiness checks."},
]

app = FastAPI(
    title=settings.app_name,
    description="A modular-monolith Employee Management System API.",
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this, a browser on a different origin (a separate frontend port, like this app's own
    # setup) cannot read the filename a download responds with - it silently falls back to a generic
    # name. Affects the payslip PDF and the Attendance Summary Excel download.
    expose_headers=["Content-Disposition"],
)
app.add_middleware(RequestLoggingMiddleware)

register_exception_handlers(app)

app.include_router(api_router)


@app.get("/api/v1/health", tags=["System"], summary="Health check")
async def health_check() -> dict:
    redis_ok = await redis_service.ping()
    return {
        "success": True,
        "message": "Service is healthy",
        "data": {"status": "ok", "redis": "connected" if redis_ok else "unavailable"},
    }
