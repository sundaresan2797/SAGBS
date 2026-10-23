from fastapi import APIRouter

from app.api.v1.endpoints import (
    attendance,
    audit_logs,
    auth,
    dashboard,
    departments,
    designations,
    document_types,
    documents,
    employees,
    holidays,
    leaves,
    notifications,
    payroll,
    roles,
    tasks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(departments.router)
api_router.include_router(designations.router)
api_router.include_router(employees.router)
api_router.include_router(attendance.router)
api_router.include_router(leaves.router)
api_router.include_router(holidays.router)
api_router.include_router(tasks.router)
api_router.include_router(documents.router)
api_router.include_router(document_types.router)
api_router.include_router(notifications.router)
api_router.include_router(audit_logs.router)
api_router.include_router(dashboard.router)
api_router.include_router(payroll.router)
api_router.include_router(roles.router)
