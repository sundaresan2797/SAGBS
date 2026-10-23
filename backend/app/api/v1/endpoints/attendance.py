from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_any_permission, require_permission
from app.models.user import User
from app.repositories.attendance_repository import AttendanceFilters
from app.schemas.attendance import (
    AttendanceOut,
    AttendancePolicyOut,
    AttendanceWithEmployee,
    CorrectAttendanceIn,
    FixCheckOutIn,
    MarkPresentIn,
    MissedCheckOutsOut,
    OvertimeSummaryEntry,
    PermissionListOut,
    PermissionOut,
    PermissionRecordIn,
    RollCallOut,
    RollCallStatus,
)
from app.schemas.common import PaginatedData, SuccessResponse
from app.services import attendance_service, permission_service

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post(
    "/check-in",
    response_model=SuccessResponse[AttendanceOut],
    summary="Check in for today",
    dependencies=[Depends(require_permission("attendance:mark"))],
)
async def check_in(
    request: Request, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    result = await attendance_service.check_in(session, current_user, request)
    return SuccessResponse(message="Checked in successfully", data=result)


@router.post(
    "/check-out",
    response_model=SuccessResponse[AttendanceOut],
    summary="Check out for today",
    dependencies=[Depends(require_permission("attendance:mark"))],
)
async def check_out(
    request: Request, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    result = await attendance_service.check_out(session, current_user, request)
    return SuccessResponse(message="Checked out successfully", data=result)


@router.get(
    "/policy",
    response_model=SuccessResponse[AttendancePolicyOut],
    summary="The company's attendance rules (office start, grace, half-day limits)",
)
async def attendance_policy(current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=attendance_service.get_policy())


@router.get(
    "/missed-checkouts",
    response_model=SuccessResponse[MissedCheckOutsOut],
    summary="Past days where someone checked in but never checked out (needs fixing)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def missed_check_outs(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await attendance_service.list_missed_check_outs(session, current_user))


@router.get(
    "/overtime-summary",
    response_model=SuccessResponse[list[OvertimeSummaryEntry]],
    summary="Overtime per person for a month (information only)",
    dependencies=[Depends(require_any_permission("payroll:view", "attendance:read_all"))],
)
async def overtime_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await attendance_service.get_overtime_summary(session, year, month))


@router.post(
    "/{attendance_id}/fix-check-out",
    response_model=SuccessResponse[AttendanceOut],
    summary="Fix a missed check-out (manager, HR, Founder, Admin)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def fix_check_out(
    attendance_id: int,
    payload: FixCheckOutIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.fix_check_out(
        session, current_user, attendance_id, payload.check_out_time, payload.reason, request
    )
    return SuccessResponse(message="Check-out fixed", data=result)


@router.post(
    "/mark-present",
    response_model=SuccessResponse[AttendanceOut],
    summary="Record a past day the employee worked but forgot to punch in (manager, HR, Founder, Admin)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def mark_present(
    payload: MarkPresentIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.mark_present(
        session,
        current_user,
        payload.employee_id,
        payload.attendance_date,
        payload.check_in_time,
        payload.check_out_time,
        payload.reason,
        request,
    )
    return SuccessResponse(message="Attendance added", data=result)


@router.post(
    "/correct",
    response_model=SuccessResponse[AttendanceOut | None],
    summary="Correct an already-recorded past day - new times, or clear it back to Absent (manager, HR, Founder, Admin)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def correct_attendance(
    payload: CorrectAttendanceIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.correct_attendance(
        session,
        current_user,
        payload.employee_id,
        payload.attendance_date,
        payload.check_in_time,
        payload.check_out_time,
        payload.reason,
        request,
    )
    return SuccessResponse(message="Attendance cleared" if result is None else "Attendance corrected", data=result)


@router.post(
    "/permissions",
    response_model=SuccessResponse[PermissionOut],
    status_code=201,
    summary="Record a permission - a few hours off - for an employee (manager, HR, Founder, Admin)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def record_permission(
    payload: PermissionRecordIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await permission_service.record_permission(session, current_user, payload, request)
    return SuccessResponse(message="Permission recorded", data=result)


@router.get(
    "/permissions",
    response_model=SuccessResponse[PermissionListOut],
    summary="One person's permissions for a month, and how many of the monthly allowance are used",
)
async def list_permissions(
    employee_id: int = Query(..., ge=1),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await permission_service.list_permissions(session, current_user, employee_id, year, month))


@router.delete(
    "/permissions/{permission_id}",
    response_model=SuccessResponse[None],
    summary="Take back a recorded permission (manager, HR, Founder, Admin)",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def cancel_permission(
    permission_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await permission_service.cancel_permission(session, current_user, permission_id, request)
    return SuccessResponse(message="Permission cancelled", data=None)


@router.get("/me", response_model=SuccessResponse[PaginatedData[AttendanceOut]], summary="My attendance history")
async def my_attendance(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.get_my_attendance(session, current_user, page, page_size)
    return SuccessResponse(data=result)


@router.get(
    "/roll-call",
    response_model=SuccessResponse[RollCallOut],
    summary="Who is present, late, on leave or absent on a given day",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def roll_call(
    roll_date: date | None = Query(default=None, alias="date", description="Defaults to today"),
    department_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    status: RollCallStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.get_roll_call(
        session, current_user, roll_date, department_id, search, status, page, page_size
    )
    return SuccessResponse(data=result)


@router.get(
    "/team",
    response_model=SuccessResponse[PaginatedData[AttendanceWithEmployee]],
    summary="My team's attendance (managers)",
    dependencies=[Depends(require_permission("attendance:read_team"))],
)
async def team_attendance(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.get_team_attendance(session, current_user, page, page_size)
    return SuccessResponse(data=result)


@router.get(
    "",
    response_model=SuccessResponse[PaginatedData[AttendanceWithEmployee]],
    summary="All attendance records (HR/Admin)",
    dependencies=[Depends(require_permission("attendance:read_all"))],
)
async def all_attendance(
    employee_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    filters = AttendanceFilters(employee_id=employee_id, date_from=date_from, date_to=date_to)
    result = await attendance_service.get_all_attendance(session, filters, page, page_size)
    return SuccessResponse(data=result)


@router.get(
    "/employee/{employee_id}/calendar",
    response_model=SuccessResponse[list[AttendanceOut]],
    summary="One employee's attendance calendar for a given month",
)
async def employee_attendance_calendar(
    employee_id: int,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await attendance_service.get_employee_attendance_calendar(session, current_user, employee_id, year, month)
    return SuccessResponse(data=result)
