import calendar
from datetime import date, datetime, time, timedelta

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.core.redis import CacheKeys, redis_service
from app.models.attendance import Attendance
from app.models.enums import AuditAction, EmployeeStatus
from app.models.notification import Notification
from app.models.user import User
from app.repositories.attendance_repository import AttendanceFilters, AttendanceRepository, ShortPermissionRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.leave_repository import LeaveSummaryRepository
from app.schemas.attendance import (
    AttendanceOut,
    AttendancePolicyOut,
    MissedCheckOutsOut,
    OvertimeSummaryEntry,
    AttendanceWithEmployee,
    RollCallDepartment,
    RollCallEntry,
    RollCallOut,
)
from app.schemas.common import PaginatedData
from app.services import attendance_rules
from app.services.audit_service import log_action
from app.services.working_days import day_off_reason
from app.utils.timezone import get_org_timezone, now_utc, today_in_org_tz


async def _get_own_employee_or_raise(session: AsyncSession, current_user: User):
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")
    return employee


async def check_in(session: AsyncSession, current_user: User, request: Request | None = None) -> AttendanceOut:
    employee = await _get_own_employee_or_raise(session, current_user)

    if employee.status != EmployeeStatus.ACTIVE:
        raise BusinessRuleError("Inactive employees cannot check in.", error_code="EMPLOYEE_INACTIVE")

    attendance_repo = AttendanceRepository(session)
    today = today_in_org_tz()
    existing = await attendance_repo.get_by_employee_and_date(employee.id, today)
    if existing is not None and existing.check_in is not None:
        raise BusinessRuleError("You have already checked in today.", error_code="ALREADY_CHECKED_IN")

    now = now_utc()
    local_now = now.astimezone(get_org_timezone())
    excused = await ShortPermissionRepository(session).minutes_for_day(employee.id, today)
    late_minutes = attendance_rules.late_minutes_for(local_now, excused)
    status = attendance_rules.status_at_check_in(local_now, excused)

    if existing is None:
        attendance = Attendance(
            employee_id=employee.id,
            attendance_date=today,
            check_in=now,
            late_minutes=late_minutes,
            status=status,
        )
        attendance_repo.add(attendance)
    else:
        attendance = existing
        attendance.check_in = now
        attendance.late_minutes = late_minutes
        attendance.status = status

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CHECK_IN,
        entity_type="Attendance",
        entity_id=employee.id,
        description=f"{employee.employee_code} checked in",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return AttendanceOut.model_validate(attendance)


async def check_out(session: AsyncSession, current_user: User, request: Request | None = None) -> AttendanceOut:
    employee = await _get_own_employee_or_raise(session, current_user)

    attendance_repo = AttendanceRepository(session)
    today = today_in_org_tz()
    attendance = await attendance_repo.get_by_employee_and_date(employee.id, today)

    if attendance is None or attendance.check_in is None:
        raise BusinessRuleError("You must check in before checking out.", error_code="NOT_CHECKED_IN")
    if attendance.check_out is not None:
        raise BusinessRuleError("You have already checked out today.", error_code="ALREADY_CHECKED_OUT")

    now = now_utc()
    attendance.check_out = now
    check_in_local = attendance.check_in.astimezone(get_org_timezone())
    check_out_local = now.astimezone(get_org_timezone())
    raw_minutes = int((now - attendance.check_in).total_seconds() // 60)
    working_minutes = raw_minutes - attendance_rules.lunch_break_minutes_within(check_in_local, check_out_local)
    attendance.working_minutes = working_minutes
    attendance.overtime_minutes = attendance_rules.overtime_minutes_for(working_minutes)
    excused = await ShortPermissionRepository(session).minutes_for_day(employee.id, today)
    attendance.status = attendance_rules.status_at_check_out(check_in_local, working_minutes, excused)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CHECK_OUT,
        entity_type="Attendance",
        entity_id=employee.id,
        description=f"{employee.employee_code} checked out",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return AttendanceOut.model_validate(attendance)


def _hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def get_policy() -> AttendancePolicyOut:
    """The attendance rules, so screens can tell people what they are (and never hard-code them)."""
    return AttendancePolicyOut(
        office_start=_hhmm(attendance_rules.workday_start_minutes()),
        grace_minutes=settings.late_grace_minutes,
        late_after=_hhmm(attendance_rules.late_after_minutes()),
        full_day_minimum_minutes=settings.full_day_minimum_minutes,
        half_day_after=_hhmm(attendance_rules.half_day_cutoff_minutes()),
        standard_shift_minutes=settings.standard_shift_minutes,
        long_day_minutes=settings.long_day_flag_minutes,
        lunch_start=_hhmm(settings.lunch_start_hour * 60 + settings.lunch_start_minute),
        lunch_break_minutes=settings.lunch_break_minutes,
    )


async def get_my_attendance(
    session: AsyncSession, current_user: User, page: int, page_size: int
) -> PaginatedData[AttendanceOut]:
    employee = await _get_own_employee_or_raise(session, current_user)
    repo = AttendanceRepository(session)
    filters = AttendanceFilters(employee_id=employee.id)
    records, total = await repo.list_paginated(filters, page, page_size)
    items = [AttendanceOut.model_validate(r) for r in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[AttendanceOut](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


async def get_team_attendance(
    session: AsyncSession, current_user: User, page: int, page_size: int
) -> PaginatedData[AttendanceWithEmployee]:
    # Not gated on role == MANAGER - see the matching note in task_service.
    # list_team_tasks: "has a team" follows the manager_id chain, not a role
    # label, so an ADMIN with direct reports (e.g. the CEO) sees them here too.
    manager_employee = await _get_own_employee_or_raise(session, current_user)
    employee_repo = EmployeeRepository(session)
    report_ids = await employee_repo.get_direct_report_ids(manager_employee.id)

    repo = AttendanceRepository(session)
    filters = AttendanceFilters(employee_ids=report_ids or [-1])
    records, total = await repo.list_paginated(filters, page, page_size)
    items = [AttendanceWithEmployee.from_model(r) for r in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[AttendanceWithEmployee](
        items=items, page=page, page_size=page_size, total=total, total_pages=total_pages
    )


async def get_all_attendance(
    session: AsyncSession, filters: AttendanceFilters, page: int, page_size: int
) -> PaginatedData[AttendanceWithEmployee]:
    repo = AttendanceRepository(session)
    records, total = await repo.list_paginated(filters, page, page_size)
    items = [AttendanceWithEmployee.from_model(r) for r in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[AttendanceWithEmployee](
        items=items, page=page, page_size=page_size, total=total, total_pages=total_pages
    )


async def get_employee_attendance_calendar(
    session: AsyncSession, current_user: User, employee_id: int, year: int, month: int
) -> list[AttendanceOut]:
    """One month of a single employee's daily records, for a calendar view.

    Access follows the same shape as everywhere else in this app: you can
    always see your own; anyone with attendance:read_all (HR/Admin) can see
    anyone; otherwise you must be that employee's direct manager
    (manager_id chain) - the same hierarchy rule used for team tasks,
    attendance and leave.
    """
    employee_repo = EmployeeRepository(session)
    target = await employee_repo.get_by_id(employee_id)
    if target is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    own_employee = await employee_repo.get_by_user_id(current_user.id)
    is_self = own_employee is not None and own_employee.id == employee_id
    permission_codes = {permission.code for permission in current_user.role.permissions}
    is_direct_report = own_employee is not None and target.manager_id == own_employee.id

    if not (is_self or "attendance:read_all" in permission_codes or is_direct_report):
        raise ForbiddenError(
            "You can only view your own attendance calendar or your direct reports'.",
            error_code="ATTENDANCE_FORBIDDEN",
        )

    date_from = date(year, month, 1)
    date_to = date(year, month, calendar.monthrange(year, month)[1])

    repo = AttendanceRepository(session)
    filters = AttendanceFilters(employee_id=employee_id, date_from=date_from, date_to=date_to)
    records, _ = await repo.list_paginated(filters, page=1, page_size=31)
    return [AttendanceOut.model_validate(r) for r in records]


async def get_roll_call(
    session: AsyncSession,
    current_user: User,
    target_date: date | None,
    department_id: int | None,
    search: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> RollCallOut:
    """Everyone who should be at work on one day, with where they stand.

    Unlike the attendance log (which only has rows for people who checked in),
    this starts from the staff list, so people who didn't check in show up
    too. Scope: anyone with attendance:read_all sees the whole company;
    otherwise it's the caller's direct reports (the manager_id chain).

    Deliberately not Redis-cached, unlike employee/department lookups elsewhere in this app: a
    check-in a minute ago must show up immediately, and no TTL is short enough to feel "live"
    for that without effectively being no cache at all. Keep it this way.
    """
    today = today_in_org_tz()
    day = target_date or today
    if day > today:
        raise BusinessRuleError(
            "The roll call is only available for today or an earlier day.", error_code="ROLL_CALL_FUTURE_DATE"
        )

    permission_codes = {permission.code for permission in current_user.role.permissions}
    employee_repo = EmployeeRepository(session)
    manager_id: int | None = None
    if "attendance:read_all" not in permission_codes:
        manager_id = (await _get_own_employee_or_raise(session, current_user)).id

    scope = await employee_repo.list_for_roll_call(day, manager_id)
    departments = sorted({(e.department.id, e.department.name) for e in scope}, key=lambda d: d[1])
    if department_id is not None:
        scope = [e for e in scope if e.department.id == department_id]

    attendance_repo = AttendanceRepository(session)
    rows = await attendance_repo.map_for_date(day)
    on_leave = await attendance_repo.employee_ids_on_approved_leave(day)
    permission_minutes = await ShortPermissionRepository(session).minutes_by_employee_for_day(day)
    half_leave_ids = await LeaveSummaryRepository(session).half_day_employee_ids(day)
    off_reason = await day_off_reason(session, day)

    entries: list[RollCallEntry] = []
    for employee in scope:
        row = rows.get(employee.id)
        if row is not None:
            resolved = row.status.value
        elif off_reason is not None:
            resolved = "HOLIDAY"
        elif employee.id in on_leave:
            resolved = "ON_LEAVE"
        else:
            resolved = "NOT_CHECKED_IN" if day == today else "ABSENT"
        entries.append(
            RollCallEntry(
                employee_id=employee.id,
                employee_code=employee.employee_code,
                employee_name=employee.full_name,
                department=employee.department.name,
                designation=employee.designation.name,
                status=resolved,
                check_in=row.check_in if row else None,
                check_out=row.check_out if row else None,
                late_minutes=row.late_minutes if row else 0,
                working_minutes=row.working_minutes if row else None,
                overtime_minutes=row.overtime_minutes if row else 0,
                missed_check_out=bool(row and row.check_in and row.check_out is None and day < today),
                permission_minutes=permission_minutes.get(employee.id, 0),
                half_day_leave=employee.id in half_leave_ids,
            )
        )

    summary: dict[str, int] = {}
    for entry in entries:
        summary[entry.status] = summary.get(entry.status, 0) + 1

    if status:
        entries = [e for e in entries if e.status == status]
    if search:
        needle = search.strip().lower()
        entries = [
            e
            for e in entries
            if needle in f"{e.employee_name} {e.employee_code} {e.department} {e.designation}".lower()
        ]

    total = len(entries)
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    start = (page - 1) * page_size
    return RollCallOut(
        date=day,
        day_off_reason=off_reason,
        summary=summary,
        departments=[RollCallDepartment(id=i, name=n) for i, n in departments],
        items=entries[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# ----- fixing a missed check-out -----

MISSED_CHECK_OUT_LOOKBACK_DAYS = 366  # a year: every month of payroll history can still be fixed


async def acting_name(session: AsyncSession, current_user: User) -> str:
    """Who to name on a fix. A login with no employee profile (the Admin) has no name to show, so it is
    named by its role ("Admin") rather than by its email address."""
    employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    return employee.full_name if employee is not None else current_user.role.name.replace("_", " ").title()


async def ensure_can_correct(session: AsyncSession, current_user: User, target) -> None:
    """Who may fix an employee's attendance: anyone with attendance:read_all (HR, Admin, Founder) or that
    employee's direct manager - and never for your own record."""
    own_employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    if own_employee is not None and own_employee.id == target.id:
        raise ForbiddenError(
            "You cannot fix your own attendance. Please ask your manager or HR.", error_code="ATTENDANCE_SELF_FIX"
        )
    permission_codes = {permission.code for permission in current_user.role.permissions}
    is_direct_manager = own_employee is not None and target.manager_id == own_employee.id
    if "attendance:read_all" not in permission_codes and not is_direct_manager:
        raise ForbiddenError(
            "Only this person's manager, HR, the Founder or Admin can fix their attendance.",
            error_code="ATTENDANCE_FORBIDDEN",
        )


async def fix_check_out(
    session: AsyncSession,
    current_user: User,
    attendance_id: int,
    check_out_time: time,
    reason: str,
    request: Request | None = None,
) -> AttendanceOut:
    """Set the check-out an employee forgot, then recompute hours, status and overtime with the normal rules.

    Who: anyone with attendance:read_all (HR, Admin, Founder), or the employee's direct
    manager (manager_id chain) - and never for your own record. Only a PAST day that has a
    check-in but no check-out can be fixed; today the employee can still check out themselves.
    """
    repo = AttendanceRepository(session)
    attendance = await repo.get_by_id(attendance_id)
    if attendance is None:
        raise NotFoundError("Attendance record not found.", error_code="ATTENDANCE_NOT_FOUND")

    await ensure_can_correct(session, current_user, attendance.employee)

    if attendance.check_in is None:
        raise BusinessRuleError("This day has no check-in, so there is nothing to fix.", error_code="NO_CHECK_IN")
    if attendance.check_out is not None:
        raise BusinessRuleError("This day already has a check-out.", error_code="ALREADY_CHECKED_OUT")
    if attendance.attendance_date >= today_in_org_tz():
        raise BusinessRuleError(
            "Today is not over yet. The employee can still check out themselves.", error_code="DAY_NOT_OVER"
        )

    tz = get_org_timezone()
    new_check_out = datetime.combine(attendance.attendance_date, check_out_time).replace(tzinfo=tz)
    check_in_local = attendance.check_in.astimezone(tz)
    if new_check_out <= attendance.check_in:
        raise BusinessRuleError(
            f"The check-out must be after the check-in time ({check_in_local.strftime('%I:%M %p').lstrip('0')}).",
            error_code="CHECK_OUT_BEFORE_CHECK_IN",
        )

    # Whole minutes from the minute of check-in, so the number matches the clock times people see.
    raw_minutes = int((new_check_out - attendance.check_in.replace(second=0, microsecond=0)).total_seconds() // 60)
    working_minutes = raw_minutes - attendance_rules.lunch_break_minutes_within(check_in_local, new_check_out)
    attendance.check_out = new_check_out
    attendance.working_minutes = working_minutes
    attendance.overtime_minutes = attendance_rules.overtime_minutes_for(working_minutes)
    excused = await ShortPermissionRepository(session).minutes_for_day(attendance.employee_id, attendance.attendance_date)
    attendance.status = attendance_rules.status_at_check_out(check_in_local, working_minutes, excused)
    attendance.corrected_by_user_id = current_user.id
    attendance.corrected_by_name = (await acting_name(session, current_user))[:150]
    attendance.corrected_at = now_utc()
    attendance.correction_reason = reason

    day_text = f"{attendance.attendance_date.day} {attendance.attendance_date.strftime('%b')}"
    session.add(
        Notification(
            user_id=attendance.employee.user_id,
            title="Your check-out was fixed",
            message=(
                f"{attendance.corrected_by_name} set your check-out for {day_text} to "
                f"{check_out_time.strftime('%I:%M %p').lstrip('0')}. Reason: {reason}"
            ),
            notification_type="ATTENDANCE_CORRECTED",
        )
    )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CORRECT_ATTENDANCE,
        entity_type="Attendance",
        entity_id=attendance.id,
        description=(
            f"Fixed missed check-out for {attendance.employee.employee_code} on {attendance.attendance_date} "
            f"to {check_out_time.strftime('%H:%M')} ({reason})"
        ),
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return AttendanceOut.model_validate(attendance)


MISSED_CHECK_OUTS_LIMIT = 200  # the list is capped here; MissedCheckOutsOut.total says if that cut anything off


async def list_missed_check_outs(session: AsyncSession, current_user: User) -> MissedCheckOutsOut:
    """Past days (last year) with a check-in but no check-out, for the people this user looks after.

    Same scope as the roll call: everyone for attendance:read_all, otherwise direct reports.
    Your own missed days are left out - you cannot fix those, and My Attendance shows them to you.
    """
    permission_codes = {permission.code for permission in current_user.role.permissions}
    employee_repo = EmployeeRepository(session)
    own_employee = await employee_repo.get_by_user_id(current_user.id)

    employee_ids: list[int] | None = None
    if "attendance:read_all" not in permission_codes:
        if own_employee is None:
            return MissedCheckOutsOut(items=[], total=0)
        employee_ids = await employee_repo.get_direct_report_ids(own_employee.id)
        if not employee_ids:
            return MissedCheckOutsOut(items=[], total=0)

    today = today_in_org_tz()
    since = today - timedelta(days=MISSED_CHECK_OUT_LOOKBACK_DAYS)
    exclude_employee_id = own_employee.id if own_employee is not None else None
    repo = AttendanceRepository(session)
    records = await repo.list_missed_check_outs(
        before=today, since=since, employee_ids=employee_ids, limit=MISSED_CHECK_OUTS_LIMIT,
        exclude_employee_id=exclude_employee_id,
    )
    total = await repo.count_missed_check_outs(
        before=today, since=since, employee_ids=employee_ids, exclude_employee_id=exclude_employee_id
    )
    return MissedCheckOutsOut(items=[AttendanceWithEmployee.from_model(r) for r in records], total=total)


async def get_overtime_summary(session: AsyncSession, year: int, month: int) -> list[OvertimeSummaryEntry]:
    """Overtime per person for one month - information only (payroll does not use it)."""
    date_from = date(year, month, 1)
    date_to = date(year, month, calendar.monthrange(year, month)[1])
    rows = await AttendanceRepository(session).overtime_totals(date_from, date_to)
    return [
        OvertimeSummaryEntry(employee_id=i, employee_code=code, employee_name=name, overtime_minutes=minutes)
        for i, code, name, minutes in rows
    ]


async def mark_present(
    session: AsyncSession,
    current_user: User,
    employee_id: int,
    day: date,
    check_in_time: time,
    check_out_time: time,
    reason: str,
    request: Request | None = None,
) -> AttendanceOut:
    """Record a past working day the employee worked but forgot to punch in for (it shows as Absent).

    Same people and the same reason/audit/notification as fixing a check-out. Hours, late minutes,
    overtime and status come from the normal rules. Refused if the day is not over, is before the
    person joined, already has a check-in, or is approved leave (cancel that first - no double counting).
    """
    employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    await ensure_can_correct(session, current_user, employee)

    if day >= today_in_org_tz():
        raise BusinessRuleError(
            "Only a day that is already over can be added. Today the employee can check in themselves.",
            error_code="DAY_NOT_OVER",
        )
    if day < employee.date_of_joining:
        raise BusinessRuleError("That day is before this person joined.", error_code="BEFORE_JOINING")

    tz = get_org_timezone()
    check_in = datetime.combine(day, check_in_time).replace(tzinfo=tz)
    check_out = datetime.combine(day, check_out_time).replace(tzinfo=tz)
    if check_out <= check_in:
        raise BusinessRuleError("The check-out must be after the check-in.", error_code="CHECK_OUT_BEFORE_CHECK_IN")

    repo = AttendanceRepository(session)
    existing = await repo.get_by_employee_and_date(employee.id, day)
    if existing is not None and existing.check_in is not None:
        raise BusinessRuleError(
            "This day already has a check-in. If only the check-out is missing, use Fix check-out.",
            error_code="DAY_HAS_CHECK_IN",
        )
    if employee.id in await repo.employee_ids_on_approved_leave(day):
        raise BusinessRuleError(
            "This day is approved leave. Cancel the leave first if the person actually worked.",
            error_code="DAY_IS_LEAVE",
        )

    raw_minutes = int((check_out - check_in).total_seconds() // 60)
    working_minutes = raw_minutes - attendance_rules.lunch_break_minutes_within(check_in, check_out)
    excused = await ShortPermissionRepository(session).minutes_for_day(employee.id, day)
    values = dict(
        check_in=check_in,
        check_out=check_out,
        working_minutes=working_minutes,
        late_minutes=attendance_rules.late_minutes_for(check_in, excused),
        overtime_minutes=attendance_rules.overtime_minutes_for(working_minutes),
        status=attendance_rules.status_at_check_out(check_in, working_minutes, excused),
        corrected_by_user_id=current_user.id,
        corrected_by_name=(await acting_name(session, current_user))[:150],
        corrected_at=now_utc(),
        correction_reason=reason,
    )
    if existing is None:
        attendance = Attendance(employee_id=employee.id, attendance_date=day, **values)
        repo.add(attendance)
    else:
        attendance = existing
        for key, value in values.items():
            setattr(attendance, key, value)

    day_text = f"{day.day} {day.strftime('%b')}"
    session.add(
        Notification(
            user_id=employee.user_id,
            title="Your attendance was added",
            message=(
                f"{values['corrected_by_name']} recorded you as working on {day_text}, "
                f"{check_in_time.strftime('%I:%M %p').lstrip('0')} to {check_out_time.strftime('%I:%M %p').lstrip('0')}. "
                f"Reason: {reason}"
            ),
            notification_type="ATTENDANCE_CORRECTED",
        )
    )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CORRECT_ATTENDANCE,
        entity_type="Attendance",
        entity_id=employee.id,
        description=(
            f"Marked {employee.employee_code} present on {day} "
            f"({check_in_time.strftime('%H:%M')}-{check_out_time.strftime('%H:%M')}): {reason}"
        ),
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    await session.refresh(attendance)
    return AttendanceOut.model_validate(attendance)


async def correct_attendance(
    session: AsyncSession,
    current_user: User,
    employee_id: int,
    day: date,
    check_in_time: time | None,
    check_out_time: time | None,
    reason: str,
    request: Request | None = None,
) -> AttendanceOut | None:
    """Correct an already-recorded past day (Present/Late/Half day) - unlike `mark_present`, which only ever
    fills in a day with no check-in at all, this one is for a day that already has a real record but the
    wrong one: new check-in/check-out times (the status is worked out by the normal rules, never chosen by
    hand, so it can never disagree with how every other day is judged), or both left empty to clear the day
    back to Absent (there is no stored "Absent" row anywhere in this app - a past working day with nothing
    recorded for it already reads as Absent - so clearing simply removes the record).

    Same people as every other correction: that employee's direct manager, or anyone with
    attendance:read_all (HR, Founder, Admin) - never for yourself.
    """
    employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    await ensure_can_correct(session, current_user, employee)

    if day >= today_in_org_tz():
        raise BusinessRuleError(
            "Only a day that is already over can be corrected. Today the employee can still check in themselves.",
            error_code="DAY_NOT_OVER",
        )
    if day < employee.date_of_joining:
        raise BusinessRuleError("That day is before this person joined.", error_code="BEFORE_JOINING")
    if employee.id in await AttendanceRepository(session).employee_ids_on_approved_leave(day):
        raise BusinessRuleError(
            "This day is approved leave. Cancel the leave first if the person actually worked.",
            error_code="DAY_IS_LEAVE",
        )

    repo = AttendanceRepository(session)
    existing = await repo.get_by_employee_and_date(employee.id, day)
    who = (await acting_name(session, current_user))[:150]
    day_text = f"{day.day} {day.strftime('%b')}"

    if check_in_time is None:  # clear back to Absent
        if existing is None:
            raise BusinessRuleError(
                "This day has no attendance record, so there is nothing to clear. "
                "Use 'Mark as present' if they actually worked this day.",
                error_code="NOTHING_TO_CORRECT",
            )
        cleared_status = existing.status
        cleared_id = existing.id
        await repo.delete(existing)

        if employee.user_id is not None:
            session.add(
                Notification(
                    user_id=employee.user_id,
                    title="Your attendance was corrected",
                    message=f"{who} cleared your attendance for {day_text}. It now counts as Absent. Reason: {reason}",
                    notification_type="ATTENDANCE_CORRECTED",
                )
            )
        await log_action(
            session,
            user_id=current_user.id,
            action=AuditAction.CORRECT_ATTENDANCE,
            entity_type="Attendance",
            entity_id=cleared_id,
            description=(
                f"Cleared attendance for {employee.employee_code} on {day} "
                f"(was {cleared_status.value}, now Absent): {reason}"
            ),
            request=request,
        )
        await session.commit()
        await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
        return None

    tz = get_org_timezone()
    check_in = datetime.combine(day, check_in_time).replace(tzinfo=tz)
    check_out = datetime.combine(day, check_out_time).replace(tzinfo=tz)
    if check_out <= check_in:
        raise BusinessRuleError("The check-out must be after the check-in.", error_code="CHECK_OUT_BEFORE_CHECK_IN")

    raw_minutes = int((check_out - check_in).total_seconds() // 60)
    working_minutes = raw_minutes - attendance_rules.lunch_break_minutes_within(check_in, check_out)
    excused = await ShortPermissionRepository(session).minutes_for_day(employee.id, day)
    previous_status = existing.status.value if existing is not None else None
    values = dict(
        check_in=check_in,
        check_out=check_out,
        working_minutes=working_minutes,
        late_minutes=attendance_rules.late_minutes_for(check_in, excused),
        overtime_minutes=attendance_rules.overtime_minutes_for(working_minutes),
        status=attendance_rules.status_at_check_out(check_in, working_minutes, excused),
        corrected_by_user_id=current_user.id,
        corrected_by_name=who,
        corrected_at=now_utc(),
        correction_reason=reason,
    )
    if existing is None:
        attendance = Attendance(employee_id=employee.id, attendance_date=day, **values)
        repo.add(attendance)
    else:
        attendance = existing
        for key, value in values.items():
            setattr(attendance, key, value)

    if employee.user_id is not None:
        session.add(
            Notification(
                user_id=employee.user_id,
                title="Your attendance was corrected",
                message=(
                    f"{who} corrected your attendance for {day_text} to "
                    f"{check_in_time.strftime('%I:%M %p').lstrip('0')} - {check_out_time.strftime('%I:%M %p').lstrip('0')}. "
                    f"Reason: {reason}"
                ),
                notification_type="ATTENDANCE_CORRECTED",
            )
        )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CORRECT_ATTENDANCE,
        entity_type="Attendance",
        entity_id=employee.id,
        description=(
            f"Corrected attendance for {employee.employee_code} on {day} "
            f"({'was ' + previous_status + ', ' if previous_status else ''}"
            f"now {check_in_time.strftime('%H:%M')}-{check_out_time.strftime('%H:%M')}): {reason}"
        ),
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    await session.refresh(attendance)
    return AttendanceOut.model_validate(attendance)


def recompute_for_permission(attendance: Attendance, excused_minutes: int) -> None:
    """Re-apply the late / half-day rules to a day that already has a check-in, now that a permission was
    recorded (or taken back) for it. Working minutes, overtime and the check times are not touched."""
    if attendance.check_in is None:
        return
    check_in_local = attendance.check_in.astimezone(get_org_timezone())
    attendance.late_minutes = attendance_rules.late_minutes_for(check_in_local, excused_minutes)
    if attendance.check_out is not None:
        attendance.status = attendance_rules.status_at_check_out(
            check_in_local, attendance.working_minutes or 0, excused_minutes
        )
    else:
        attendance.status = attendance_rules.status_at_check_in(check_in_local, excused_minutes)
