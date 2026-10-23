from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import require_permission
from app.schemas.common import SuccessResponse
from app.schemas.dashboard import AttendanceTrendPoint, DashboardSummary, DepartmentHeadcount, LeaveTrendPoint
from app.services import dashboard_service

router = APIRouter(
    prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(require_permission("report:view"))]
)


@router.get("/summary", response_model=SuccessResponse[DashboardSummary], summary="Dashboard summary cards")
async def summary(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await dashboard_service.get_summary(session))


@router.get(
    "/attendance", response_model=SuccessResponse[list[AttendanceTrendPoint]], summary="Attendance trend chart"
)
async def attendance_trend(days: int = Query(default=14, ge=1, le=90), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await dashboard_service.get_attendance_trend(session, days))


@router.get("/leave", response_model=SuccessResponse[list[LeaveTrendPoint]], summary="Leave trend chart")
async def leave_trend(months: int = Query(default=6, ge=1, le=24), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await dashboard_service.get_leave_trend(session, months))


@router.get(
    "/departments", response_model=SuccessResponse[list[DepartmentHeadcount]], summary="Employees by department"
)
async def departments(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await dashboard_service.get_department_headcounts(session))
