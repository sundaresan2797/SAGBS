"""Permission: an approved absence of a few hours on one day (bank work, a school meeting, a doctor's visit).

Paid, and it excuses that many minutes of lateness / short hours (see attendance_rules), so the person is not
marked late or half day for time they were allowed to miss. A manager/HR/Founder/Admin enters it when the
employee tells them - the same people who may fix attendance, and never for yourself. Each person may have
`permission_monthly_limit` a month; beyond that the time off must be recorded as a half-day leave instead.
"""

import calendar
from datetime import date

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.core.redis import CacheKeys, redis_service
from app.models.attendance import ShortPermission
from app.models.enums import AuditAction, EmployeeStatus
from app.repositories.attendance_repository import AttendanceRepository, ShortPermissionRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.leave_repository import LeaveRequestRepository
from app.schemas.attendance import PermissionListOut, PermissionOut, PermissionRecordIn
from app.services.attendance_service import acting_name, ensure_can_correct, recompute_for_permission
from app.services.audit_service import log_action
from app.services.notification_service import add_notification
from app.services.paid_month_guard import ensure_months_not_paid
from app.services.working_days import day_off_reason
from app.models.user import User
from app.utils.timezone import today_in_org_tz


def _hours_text(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours} h {rest} min"
    return f"{hours} h" if hours else f"{rest} min"


def _day_text(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


async def record_permission(
    session: AsyncSession, current_user: User, payload: PermissionRecordIn, request: Request | None = None
) -> PermissionOut:
    employee = await EmployeeRepository(session).get_by_id(payload.employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    await ensure_can_correct(session, current_user, employee)
    if employee.status != EmployeeStatus.ACTIVE:
        raise BusinessRuleError("This employee is not active.", error_code="EMPLOYEE_INACTIVE")

    day = payload.permission_date
    if day < employee.date_of_joining:
        raise BusinessRuleError("That is before this person joined.", error_code="BEFORE_JOINING")
    if payload.minutes > settings.permission_max_minutes:
        raise BusinessRuleError(
            f"A permission can be at most {_hours_text(settings.permission_max_minutes)}. "
            "For longer time off, record a half-day leave.",
            error_code="PERMISSION_TOO_LONG",
        )
    off_reason = await day_off_reason(session, day)
    if off_reason is not None:
        raise BusinessRuleError(f"{_day_text(day)} is a day off ({off_reason}).", error_code="DAY_IS_OFF")
    if await LeaveRequestRepository(session).has_overlapping_request(employee.id, day, day):
        raise BusinessRuleError(
            "This person already has leave on that day, so no permission is needed.", error_code="DAY_HAS_LEAVE"
        )
    await ensure_months_not_paid(session, employee.id, day, day)

    repo = ShortPermissionRepository(session)
    if await repo.get_for_day(employee.id, day) is not None:
        raise BusinessRuleError("This person already has a permission on that day.", error_code="PERMISSION_EXISTS")
    used = len(await repo.list_for_month(employee.id, day.year, day.month))
    if used >= settings.permission_monthly_limit:
        raise BusinessRuleError(
            f"{employee.full_name} has already used {used} of {settings.permission_monthly_limit} permissions "
            f"this month. Please record a half-day leave instead.",
            error_code="PERMISSION_LIMIT_REACHED",
        )

    who = (await acting_name(session, current_user))[:150]
    permission = ShortPermission(
        employee_id=employee.id,
        permission_date=day,
        minutes=payload.minutes,
        reason=payload.reason,
        recorded_by_user_id=current_user.id,
        recorded_by_name=who,
        recorded_late=day < today_in_org_tz(),
    )
    repo.add(permission)
    await session.flush()
    permission.employee = employee

    # If they already checked in that day, re-apply the late / half-day rules with the excused time.
    attendance = await AttendanceRepository(session).get_by_employee_and_date(employee.id, day)
    if attendance is not None:
        recompute_for_permission(attendance, payload.minutes)

    if employee.user_id is not None:
        add_notification(
            session,
            employee.user_id,
            "Permission recorded for you",
            f"{who} recorded a {_hours_text(payload.minutes)} permission for you on {_day_text(day)}. "
            f"Reason: {payload.reason}",
            "ATTENDANCE_CORRECTED",
        )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.RECORD_PERMISSION,
        entity_type="ShortPermission",
        entity_id=permission.id,
        description=(
            f"Recorded {_hours_text(payload.minutes)} permission for {employee.employee_code} on {day}: {payload.reason}"
            + (" [entered for a day already past]" if permission.recorded_late else "")
        ),
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return PermissionOut.from_model(permission)


async def cancel_permission(
    session: AsyncSession, current_user: User, permission_id: int, request: Request | None = None
) -> None:
    repo = ShortPermissionRepository(session)
    permission = await repo.get_by_id(permission_id)
    if permission is None:
        raise NotFoundError("Permission not found.", error_code="PERMISSION_NOT_FOUND")
    employee = permission.employee
    await ensure_can_correct(session, current_user, employee)
    await ensure_months_not_paid(session, employee.id, permission.permission_date, permission.permission_date)

    day = permission.permission_date
    code, minutes = employee.employee_code, permission.minutes
    await repo.delete(permission)
    await session.flush()
    # Without the permission the day's late / half-day rules apply again as normal.
    attendance = await AttendanceRepository(session).get_by_employee_and_date(employee.id, day)
    if attendance is not None:
        recompute_for_permission(attendance, 0)

    who = (await acting_name(session, current_user))[:150]
    if employee.user_id is not None:
        add_notification(
            session,
            employee.user_id,
            "Permission taken back",
            f"{who} cancelled the permission recorded for you on {_day_text(day)}.",
            "ATTENDANCE_CORRECTED",
        )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CANCEL_PERMISSION,
        entity_type="ShortPermission",
        entity_id=permission_id,
        description=f"Cancelled {_hours_text(minutes)} permission for {code} on {day}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)


async def list_permissions(
    session: AsyncSession, current_user: User, employee_id: int, year: int, month: int
) -> PermissionListOut:
    """One person's permissions for a month. Same access as the attendance calendar: yourself, your direct
    reports, or anyone if you have attendance:read_all."""
    employee_repo = EmployeeRepository(session)
    target = await employee_repo.get_by_id(employee_id)
    if target is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    own = await employee_repo.get_by_user_id(current_user.id)
    codes = {permission.code for permission in current_user.role.permissions}
    allowed = (
        (own is not None and (own.id == target.id or target.manager_id == own.id)) or "attendance:read_all" in codes
    )
    if not allowed:
        raise ForbiddenError(
            "You can only see your own permissions or your direct reports'.", error_code="ATTENDANCE_FORBIDDEN"
        )
    if not 1 <= month <= 12:
        raise BusinessRuleError("Month must be 1 to 12.", error_code="INVALID_MONTH")
    calendar.monthrange(year, month)  # raises for an impossible year
    items = await ShortPermissionRepository(session).list_for_month(employee_id, year, month)
    return PermissionListOut(
        items=[PermissionOut.from_model(p) for p in items],
        used_this_month=len(items),
        monthly_limit=settings.permission_monthly_limit,
        max_minutes=settings.permission_max_minutes,
    )
