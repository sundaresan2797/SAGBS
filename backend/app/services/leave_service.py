from datetime import date, datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.core.redis import CacheKeys, redis_service
from app.models.employee import Employee
from app.models.enums import AuditAction, EmployeeStatus, LeaveAccrualFrequency, LeaveRequestStatus, RoleName
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.models.notification import Notification
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.holiday_repository import HolidayRepository
from app.repositories.leave_repository import LeaveBalanceRepository, LeaveRequestRepository, LeaveTypeRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedData
from app.schemas.leave import (
    LeaveBalanceOut,
    LeaveRecordRequest,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveTypeUpdate,
)
from app.repositories.attendance_repository import AttendanceRepository, ShortPermissionRepository
from app.services.attendance_service import acting_name, ensure_can_correct
from app.services.audit_service import log_action
from app.services.paid_month_guard import ensure_months_not_paid
from app.services.notification_service import add_notification
from app.services.working_days import WEEKLY_OFF_WEEKDAYS
from app.utils.timezone import today_in_org_tz

async def _count_working_days(session: AsyncSession, start_date: date, end_date: date) -> float:
    # Same definition of a day off as attendance and the roll call (see
    # app/services/working_days.py): the weekly holiday plus calendar holidays,
    # but not "optional" holidays, which aren't a day off for everyone.
    holiday_repo = HolidayRepository(session)
    holidays = await holiday_repo.list_between(start_date, end_date)
    holiday_dates = {h.holiday_date for h in holidays if not h.is_optional}

    count = 0
    current = start_date
    while current <= end_date:
        if current.weekday() not in WEEKLY_OFF_WEEKDAYS and current not in holiday_dates:
            count += 1
        current += timedelta(days=1)
    return float(count)


def _effective_allocated_days(leave_type: LeaveType, employee: Employee, year: int) -> float:
    """How many days of this leave type the employee has been credited so far this year.

    ANNUAL types get the full default_annual_days up front. MONTHLY types
    accrue default_annual_days / 12 for each completed month since Jan 1 (or
    the employee's joining month, if they joined partway through the year),
    computed live rather than incremented by a background job.
    """
    if leave_type.accrual_frequency != LeaveAccrualFrequency.MONTHLY:
        return float(leave_type.default_annual_days)

    monthly_rate = float(leave_type.default_annual_days) / 12
    today = date.today()
    start_month = employee.date_of_joining.month if employee.date_of_joining.year == year else 1

    if today.year > year:
        months_elapsed = 12 - start_month + 1
    elif today.year < year:
        months_elapsed = 0
    else:
        months_elapsed = today.month - start_month + 1

    months_elapsed = max(0, min(12, months_elapsed))
    return round(monthly_rate * months_elapsed, 1)


def _resolve_allocated_days(
    leave_type: LeaveType, employee: Employee, year: int, balance: LeaveBalance | None
) -> float:
    """The allocated-days figure to use for balance checks/display.

    MONTHLY types are always computed live (see _effective_allocated_days) -
    pinning them to whatever was stored when the balance row was created
    would freeze accrual at that moment. ANNUAL types trust an existing
    balance row's stored allocated_days, since HR may have adjusted it for
    a specific employee (e.g. a pro-rated first year or a manual grant);
    only fall back to the leave type's blanket default when no row exists.
    """
    if leave_type.accrual_frequency == LeaveAccrualFrequency.MONTHLY:
        return _effective_allocated_days(leave_type, employee, year)
    if balance is not None:
        return float(balance.allocated_days)
    return float(leave_type.default_annual_days)


async def list_leave_types(session: AsyncSession) -> list[LeaveTypeOut]:
    repo = LeaveTypeRepository(session)
    return [LeaveTypeOut.model_validate(lt) for lt in await repo.list_active()]


async def list_all_leave_types(session: AsyncSession) -> list[LeaveTypeOut]:
    repo = LeaveTypeRepository(session)
    return [LeaveTypeOut.model_validate(lt) for lt in await repo.list_all()]


async def create_leave_type(
    session: AsyncSession, payload: LeaveTypeCreate, current_user: User, request: Request | None = None
) -> LeaveTypeOut:
    repo = LeaveTypeRepository(session)
    code = payload.code.upper()
    if await repo.get_by_code(code) is not None:
        raise ConflictError(f"A leave type with code '{code}' already exists.", error_code="LEAVE_TYPE_EXISTS")

    leave_type = LeaveType(
        code=code,
        name=payload.name,
        is_paid=payload.is_paid,
        default_annual_days=payload.default_annual_days if payload.is_paid else 0,
        accrual_frequency=payload.accrual_frequency,
        is_active=True,
    )
    repo.add(leave_type)
    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_LEAVE_TYPE,
        entity_type="LeaveType",
        entity_id=leave_type.id,
        description=f"Created leave type '{leave_type.name}' ({leave_type.code})",
        request=request,
    )
    await session.commit()
    return LeaveTypeOut.model_validate(leave_type)


async def update_leave_type(
    session: AsyncSession,
    leave_type_id: int,
    payload: LeaveTypeUpdate,
    current_user: User,
    request: Request | None = None,
) -> LeaveTypeOut:
    repo = LeaveTypeRepository(session)
    leave_type = await repo.get_by_id(leave_type_id)
    if leave_type is None:
        raise NotFoundError("Leave type not found.", error_code="LEAVE_TYPE_NOT_FOUND")

    if payload.name is not None:
        leave_type.name = payload.name
    if payload.is_paid is not None and payload.is_paid != leave_type.is_paid:
        # Whether leave is paid decides how every request already made is counted in payroll and in the
        # Attendance Summary, so it can't be flipped once anyone has used the type.
        used_by = await repo.request_count(leave_type_id)
        if used_by:
            raise BusinessRuleError(
                f"{used_by} leave request{'s' if used_by != 1 else ''} already use{'' if used_by != 1 else 's'} this type, so it "
                "can't switch between paid and unpaid. Add a new leave type instead.",
                error_code="LEAVE_TYPE_PAID_LOCKED",
            )
        leave_type.is_paid = payload.is_paid
    if payload.default_annual_days is not None:
        leave_type.default_annual_days = payload.default_annual_days
    if payload.accrual_frequency is not None:
        leave_type.accrual_frequency = payload.accrual_frequency
    if payload.is_active is not None:
        leave_type.is_active = payload.is_active

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_LEAVE_TYPE,
        entity_type="LeaveType",
        entity_id=leave_type.id,
        description=f"Updated leave type '{leave_type.name}' ({leave_type.code})",
        request=request,
    )
    await session.commit()
    return LeaveTypeOut.model_validate(leave_type)


async def delete_leave_type(
    session: AsyncSession, leave_type_id: int, current_user: User, request: Request | None = None
) -> None:
    repo = LeaveTypeRepository(session)
    leave_type = await repo.get_by_id(leave_type_id)
    if leave_type is None:
        raise NotFoundError("Leave type not found.", error_code="LEAVE_TYPE_NOT_FOUND")

    if await repo.is_referenced(leave_type_id):
        raise BusinessRuleError(
            "This leave type has balances or requests recorded against it and can't be deleted. "
            "Deactivate it instead to hide it from new requests.",
            error_code="LEAVE_TYPE_IN_USE",
        )

    name, code = leave_type.name, leave_type.code
    await repo.delete(leave_type)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.DELETE_LEAVE_TYPE,
        entity_type="LeaveType",
        entity_id=leave_type_id,
        description=f"Deleted leave type '{name}' ({code})",
        request=request,
    )
    await session.commit()


async def get_my_leave_balances(session: AsyncSession, current_user: User, year: int) -> list[LeaveBalanceOut]:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")

    leave_type_repo = LeaveTypeRepository(session)
    leave_types = [lt for lt in await leave_type_repo.list_active() if lt.is_paid]

    balance_repo = LeaveBalanceRepository(session)
    balances_by_type = {b.leave_type_id: b for b in await balance_repo.list_for_employee(employee.id, year)}

    results: list[LeaveBalanceOut] = []
    for leave_type in leave_types:
        balance = balances_by_type.get(leave_type.id)
        allocated = _resolve_allocated_days(leave_type, employee, year, balance)
        if balance is not None:
            results.append(LeaveBalanceOut.from_model(balance, allocated_days=allocated))
        else:
            # No balance row yet - e.g. a leave type created after this
            # employee joined, or nothing approved for it this year. Show a
            # virtual zero-used balance instead of requiring every employee
            # to have a pre-seeded row for every leave type.
            results.append(
                LeaveBalanceOut(
                    leave_type_id=leave_type.id,
                    leave_type_name=leave_type.name,
                    leave_type_code=leave_type.code,
                    accrual_frequency=leave_type.accrual_frequency,
                    year=year,
                    allocated_days=allocated,
                    used_days=0.0,
                    remaining_days=allocated,
                )
            )
    return results


async def _check_leave_and_count_days(
    session: AsyncSession, employee: Employee, payload: LeaveRequestCreate, *, own: bool
) -> tuple[LeaveType, float]:
    """The checks every new leave goes through (asked for by the employee, or recorded by a manager/HR):
    the leave type is usable, no overlap with other leave, there are working days in the range, and a paid
    type has enough balance left. Returns the leave type and how many days it counts (0.5 for a half day)."""
    subject = "You already have" if own else "This person already has"
    leave_type = await LeaveTypeRepository(session).get_by_id(payload.leave_type_id)
    if leave_type is None or not leave_type.is_active:
        raise NotFoundError("Leave type not found.", error_code="LEAVE_TYPE_NOT_FOUND")

    request_repo = LeaveRequestRepository(session)
    if await request_repo.has_overlapping_request(employee.id, payload.start_date, payload.end_date):
        raise BusinessRuleError(
            f"{subject} a pending or approved leave request that overlaps these dates.",
            error_code="OVERLAPPING_LEAVE_REQUEST",
        )

    working_days = await _count_working_days(session, payload.start_date, payload.end_date)
    if working_days <= 0:
        raise BusinessRuleError(
            "The selected date range contains no working days.", error_code="NO_WORKING_DAYS_SELECTED"
        )
    number_of_days = 0.5 if payload.day_part is not None else working_days

    if leave_type.is_paid:
        balance = await LeaveBalanceRepository(session).get(employee.id, leave_type.id, payload.start_date.year)
        allocated = _resolve_allocated_days(leave_type, employee, payload.start_date.year, balance)
        used = float(balance.used_days) if balance is not None else 0.0
        # Days already asked for and still waiting are spoken for too, or several small requests could
        # each pass on their own and together take the balance below zero once approved.
        waiting = await request_repo.pending_days(employee.id, leave_type.id, payload.start_date.year)
        remaining = round(allocated - used - waiting, 1)
        if number_of_days > remaining:
            raise BusinessRuleError(
                f"Insufficient leave balance: {remaining} day(s) remaining"
                + (f" after {'your ' if own else ''}{waiting:g} day(s) already waiting for approval" if waiting else "")
                + f", {number_of_days} requested.",
                error_code="INSUFFICIENT_LEAVE_BALANCE",
            )
    return leave_type, number_of_days


async def apply_leave(
    session: AsyncSession, current_user: User, payload: LeaveRequestCreate, request: Request | None = None
) -> LeaveRequestOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")

    # Only a direct manager can decide on leave (see _authorize_decision), so a request from someone with
    # no manager could never be approved - it would sit PENDING forever and count as absent in payroll.
    # The Founder is the one person with nobody above them, so their leave approves itself (below).
    is_founder_at_the_top = employee.manager_id is None and current_user.role.name == RoleName.FOUNDER.value
    if employee.manager_id is None and not is_founder_at_the_top:
        raise BusinessRuleError(
            "You don't have a reporting manager, so nobody can approve your leave yet. "
            "Please ask HR to set your manager first.",
            error_code="NO_LEAVE_APPROVER",
        )

    if payload.start_date < date.today():
        raise BusinessRuleError("Leave start date cannot be in the past.", error_code="INVALID_LEAVE_DATES")

    leave_type, number_of_days = await _check_leave_and_count_days(session, employee, payload, own=True)
    request_repo = LeaveRequestRepository(session)

    leave_request = LeaveRequest(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        number_of_days=number_of_days,
        reason=payload.reason,
        status=LeaveRequestStatus.PENDING,
        day_part=payload.day_part.value if payload.day_part is not None else None,
    )
    request_repo.add(leave_request)
    await session.flush()
    leave_request.employee = employee
    leave_request.leave_type = leave_type

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_LEAVE,
        entity_type="LeaveRequest",
        entity_id=leave_request.id,
        description=f"{employee.employee_code} applied for {number_of_days} day(s) of {leave_type.name}",
        request=request,
    )
    if employee.manager_id is not None:
        manager = await employee_repo.get_by_id(employee.manager_id)
        if manager is not None and manager.user_id is not None:
            add_notification(
                session,
                manager.user_id,
                "Leave request to review",
                f"{employee.full_name} asked for leave from {payload.start_date} to {payload.end_date}.",
                "LEAVE_REQUESTED",
            )

    if is_founder_at_the_top:
        await _use_up_balance(session, leave_request)
        leave_request.status = LeaveRequestStatus.APPROVED
        leave_request.approved_by = current_user.id
        leave_request.approved_at = datetime.now(timezone.utc)
        await log_action(
            session,
            user_id=current_user.id,
            action=AuditAction.APPROVE_LEAVE,
            entity_type="LeaveRequest",
            entity_id=leave_request.id,
            description=f"Leave for {employee.employee_code} approved automatically (nobody is above the Founder)",
            request=request,
        )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return LeaveRequestOut.from_model(leave_request)


async def record_leave(
    session: AsyncSession, current_user: User, payload: LeaveRecordRequest, request: Request | None = None
) -> LeaveRequestOut:
    """A manager/HR/Founder/Admin enters leave for an employee who told them (e.g. phoned in this morning).

    It goes through exactly the same checks as a leave the employee applies for (balance, overlap, working
    days) and is approved on the spot, because the person entering it is the one who would approve it. Who
    can do it is the same as for fixing attendance: that employee's direct manager, HR, the Founder or the
    Admin, never for yourself. It can be for today, a coming day, or a past day - but never for a month that
    already has the employee's payslip, and never over a day the person has already worked.
    """
    employee = await EmployeeRepository(session).get_by_id(payload.employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    await ensure_can_correct(session, current_user, employee)
    if employee.status != EmployeeStatus.ACTIVE:
        raise BusinessRuleError("This employee is not active.", error_code="EMPLOYEE_INACTIVE")
    if payload.start_date < employee.date_of_joining:
        raise BusinessRuleError("That is before this person joined.", error_code="BEFORE_JOINING")

    await ensure_months_not_paid(session, employee.id, payload.start_date, payload.end_date)

    # Whole days off must not sit on top of days the person already worked (or any saved attendance).
    # A half day may: the person works the other half.
    if payload.day_part is None:
        saved = await AttendanceRepository(session).list_for_employees_between(
            [employee.id], payload.start_date, payload.end_date
        )
        if saved:
            first_day = min(row.attendance_date for row in saved)
            raise BusinessRuleError(
                f"{employee.full_name} already has attendance on {first_day.day} {first_day.strftime('%b')}. "
                "If they only worked part of the day, record a half-day leave instead.",
                error_code="DAY_HAS_ATTENDANCE",
            )
    if await ShortPermissionRepository(session).has_between(employee.id, payload.start_date, payload.end_date):
        raise BusinessRuleError(
            "This person has a permission on one of these days. Cancel the permission first.",
            error_code="DAY_HAS_PERMISSION",
        )

    leave_type, number_of_days = await _check_leave_and_count_days(session, employee, payload, own=False)

    who = (await acting_name(session, current_user))[:150]
    now = datetime.now(timezone.utc)
    leave_request = LeaveRequest(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        number_of_days=number_of_days,
        reason=payload.reason,
        status=LeaveRequestStatus.APPROVED,
        approved_by=current_user.id,
        approved_at=now,
        day_part=payload.day_part.value if payload.day_part is not None else None,
        recorded_by_user_id=current_user.id,
        recorded_by_name=who,
        recorded_late=payload.start_date < today_in_org_tz(),
    )
    LeaveRequestRepository(session).add(leave_request)
    await session.flush()
    leave_request.employee = employee
    leave_request.leave_type = leave_type
    await _use_up_balance(session, leave_request)

    when = _describe_leave_dates(leave_request)
    if employee.user_id is not None:
        add_notification(
            session,
            employee.user_id,
            "Leave recorded for you",
            f"{who} recorded {leave_type.name} for you: {when}. Reason: {payload.reason}",
            "LEAVE_APPROVED",
        )
    # Tell the direct manager too when someone else (HR, the Founder, the Admin) entered it.
    if employee.manager_id is not None:
        manager = await EmployeeRepository(session).get_by_id(employee.manager_id)
        if manager is not None and manager.user_id is not None and manager.user_id != current_user.id:
            add_notification(
                session,
                manager.user_id,
                "Leave recorded for your team member",
                f"{who} recorded {leave_type.name} for {employee.full_name}: {when}. Reason: {payload.reason}",
                "LEAVE_APPROVED",
            )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.RECORD_LEAVE,
        entity_type="LeaveRequest",
        entity_id=leave_request.id,
        description=(
            f"Recorded {number_of_days:g} day(s) of {leave_type.name} for {employee.employee_code} ({when}): "
            f"{payload.reason}"
            + (" [entered for a day already past]" if leave_request.recorded_late else "")
        ),
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return LeaveRequestOut.from_model(leave_request)


def _describe_leave_dates(leave_request: LeaveRequest) -> str:
    start = f"{leave_request.start_date.day} {leave_request.start_date.strftime('%b')}"
    if leave_request.day_part is not None:
        half = "morning" if leave_request.day_part == "FIRST_HALF" else "afternoon"
        return f"{start} ({half} half day)"
    if leave_request.end_date == leave_request.start_date:
        return start
    return f"{start} to {leave_request.end_date.day} {leave_request.end_date.strftime('%b')}"


async def _authorize_decision(session: AsyncSession, current_user: User, leave_request: LeaveRequest) -> None:
    # Approval authority follows the manager_id chain for every role, with no
    # ADMIN/HR bypass: only the employee's direct manager may approve or
    # reject their leave, matching the same rule used for team tasks and
    # attendance. HR/ADMIN retain read-only visibility into all requests via
    # leave:manage_all (see get_all_leave_requests) but cannot act on a
    # request unless they are that employee's actual manager.
    employee_repo = EmployeeRepository(session)
    manager_employee = await employee_repo.get_by_user_id(current_user.id)
    if manager_employee is not None and leave_request.employee.manager_id == manager_employee.id:
        return
    raise ForbiddenError(
        "Only this employee's direct manager can approve or reject their leave request.",
        error_code="LEAVE_APPROVAL_FORBIDDEN",
    )


async def _use_up_balance(session: AsyncSession, leave_request: LeaveRequest) -> None:
    """Take an approved paid leave's days off the employee's balance."""
    if not leave_request.leave_type.is_paid:
        return
    balance_repo = LeaveBalanceRepository(session)
    balance = await balance_repo.get(
        leave_request.employee_id, leave_request.leave_type_id, leave_request.start_date.year
    )
    if balance is None:
        balance = LeaveBalance(
            employee_id=leave_request.employee_id,
            leave_type_id=leave_request.leave_type_id,
            year=leave_request.start_date.year,
            allocated_days=leave_request.leave_type.default_annual_days,
            used_days=0,
        )
        balance_repo.add(balance)
        await session.flush()
    balance.used_days = float(balance.used_days) + float(leave_request.number_of_days)


async def approve_leave(
    session: AsyncSession, current_user: User, request_id: int, request: Request | None = None
) -> LeaveRequestOut:
    request_repo = LeaveRequestRepository(session)
    leave_request = await request_repo.get_by_id(request_id)
    if leave_request is None:
        raise NotFoundError("Leave request not found.", error_code="LEAVE_REQUEST_NOT_FOUND")
    if leave_request.status != LeaveRequestStatus.PENDING:
        raise BusinessRuleError("Only pending leave requests can be approved.", error_code="INVALID_LEAVE_STATUS")

    await _authorize_decision(session, current_user, leave_request)

    # Re-check at the moment of approval: the balance may have changed since the request was made.
    if leave_request.leave_type.is_paid:
        balance = await LeaveBalanceRepository(session).get(
            leave_request.employee_id, leave_request.leave_type_id, leave_request.start_date.year
        )
        allocated = _resolve_allocated_days(
            leave_request.leave_type, leave_request.employee, leave_request.start_date.year, balance
        )
        remaining = round(allocated - (float(balance.used_days) if balance is not None else 0.0), 1)
        if float(leave_request.number_of_days) > remaining:
            raise BusinessRuleError(
                f"Not enough leave left to approve this: {remaining} day(s) remaining, "
                f"{leave_request.number_of_days} requested.",
                error_code="INSUFFICIENT_LEAVE_BALANCE",
            )

    await _use_up_balance(session, leave_request)

    leave_request.status = LeaveRequestStatus.APPROVED
    leave_request.approved_by = current_user.id
    leave_request.approved_at = datetime.now(timezone.utc)

    session.add(
        Notification(
            user_id=leave_request.employee.user_id,
            title="Leave request approved",
            message=f"Your leave request from {leave_request.start_date} to {leave_request.end_date} was approved.",
            notification_type="LEAVE_APPROVED",
        )
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.APPROVE_LEAVE,
        entity_type="LeaveRequest",
        entity_id=leave_request.id,
        description=f"Approved leave request for {leave_request.employee.employee_code}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return LeaveRequestOut.from_model(leave_request)


async def reject_leave(
    session: AsyncSession,
    current_user: User,
    request_id: int,
    rejection_reason: str | None,
    request: Request | None = None,
) -> LeaveRequestOut:
    request_repo = LeaveRequestRepository(session)
    leave_request = await request_repo.get_by_id(request_id)
    if leave_request is None:
        raise NotFoundError("Leave request not found.", error_code="LEAVE_REQUEST_NOT_FOUND")
    if leave_request.status != LeaveRequestStatus.PENDING:
        raise BusinessRuleError("Only pending leave requests can be rejected.", error_code="INVALID_LEAVE_STATUS")

    await _authorize_decision(session, current_user, leave_request)

    leave_request.status = LeaveRequestStatus.REJECTED
    leave_request.rejection_reason = rejection_reason

    session.add(
        Notification(
            user_id=leave_request.employee.user_id,
            title="Leave request rejected",
            message=f"Your leave request from {leave_request.start_date} to {leave_request.end_date} was rejected.",
            notification_type="LEAVE_REJECTED",
        )
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.REJECT_LEAVE,
        entity_type="LeaveRequest",
        entity_id=leave_request.id,
        description=f"Rejected leave request for {leave_request.employee.employee_code}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return LeaveRequestOut.from_model(leave_request)


async def cancel_leave(
    session: AsyncSession, current_user: User, request_id: int, request: Request | None = None
) -> LeaveRequestOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)

    request_repo = LeaveRequestRepository(session)
    leave_request = await request_repo.get_by_id(request_id)
    if leave_request is None:
        raise NotFoundError("Leave request not found.", error_code="LEAVE_REQUEST_NOT_FOUND")
    is_owner = employee is not None and leave_request.employee_id == employee.id
    if not is_owner and leave_request.recorded_by_user_id is None:
        raise ForbiddenError("You can only cancel your own leave requests.", error_code="LEAVE_CANCEL_FORBIDDEN")
    if leave_request.status not in (LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED):
        raise BusinessRuleError(
            "Only pending or approved leave requests can be cancelled.", error_code="INVALID_LEAVE_STATUS"
        )
    if not is_owner:
        # Leave that a manager/HR entered for the employee can be taken back by the people who may enter it
        # (in case it was a mistake) - at any time, as long as that month has not been paid.
        await ensure_can_correct(session, current_user, leave_request.employee)
        await ensure_months_not_paid(
            session, leave_request.employee_id, leave_request.start_date, leave_request.end_date
        )
    elif leave_request.status == LeaveRequestStatus.APPROVED and leave_request.start_date <= date.today():
        raise BusinessRuleError(
            "Approved leave that has already started cannot be cancelled.", error_code="LEAVE_ALREADY_STARTED"
        )

    if leave_request.status == LeaveRequestStatus.APPROVED and leave_request.leave_type.is_paid:
        balance_repo = LeaveBalanceRepository(session)
        balance = await balance_repo.get(
            leave_request.employee_id, leave_request.leave_type_id, leave_request.start_date.year
        )
        if balance is not None:
            balance.used_days = max(0.0, float(balance.used_days) - float(leave_request.number_of_days))

    leave_request.status = LeaveRequestStatus.CANCELLED

    if not is_owner and leave_request.employee.user_id is not None:
        add_notification(
            session,
            leave_request.employee.user_id,
            "Leave taken back",
            f"{(await acting_name(session, current_user))} cancelled the leave recorded for you "
            f"({_describe_leave_dates(leave_request)}).",
            "LEAVE_REJECTED",
        )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CANCEL_LEAVE,
        entity_type="LeaveRequest",
        entity_id=leave_request.id,
        description=f"Cancelled leave request for {leave_request.employee.employee_code}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return LeaveRequestOut.from_model(leave_request)


async def get_my_leave_requests(
    session: AsyncSession, current_user: User, page: int, page_size: int, year: int | None = None
) -> PaginatedData[LeaveRequestOut]:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")

    repo = LeaveRequestRepository(session)
    records, total = await repo.list_paginated(page, page_size, employee_id=employee.id, year=year)
    return _paginate(records, page, page_size, total)


async def get_team_leave_requests(
    session: AsyncSession,
    current_user: User,
    page: int,
    page_size: int,
    status: LeaveRequestStatus | None,
    year: int | None = None,
) -> PaginatedData[LeaveRequestOut]:
    # Not gated on role == MANAGER - see the matching note in task_service.
    # list_team_tasks: "has a team" follows the manager_id chain, not a role
    # label, so an ADMIN with direct reports (e.g. the CEO) sees them here too.
    employee_repo = EmployeeRepository(session)
    manager_employee = await employee_repo.get_by_user_id(current_user.id)
    if manager_employee is None:
        return PaginatedData[LeaveRequestOut](items=[], page=page, page_size=page_size, total=0, total_pages=0)

    report_ids = await employee_repo.get_direct_report_ids(manager_employee.id)
    repo = LeaveRequestRepository(session)
    records, total = await repo.list_paginated(
        page, page_size, employee_ids=report_ids or [-1], status=status, year=year
    )
    return _paginate(records, page, page_size, total)


async def get_employee_leave_requests(
    session: AsyncSession, current_user: User, employee_id: int, page: int, page_size: int, year: int | None = None
) -> PaginatedData[LeaveRequestOut]:
    """One employee's leave requests, for a calendar view of their days.

    Access follows the same shape as the attendance calendar: you can always see your own; anyone with
    attendance:read_all (HR/Admin) can see anyone; otherwise you must be that employee's direct manager
    (manager_id chain).
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
            "You can only view your own leave requests or your direct reports'.",
            error_code="ATTENDANCE_FORBIDDEN",
        )

    repo = LeaveRequestRepository(session)
    records, total = await repo.list_paginated(page, page_size, employee_id=employee_id, year=year)
    return _paginate(records, page, page_size, total)


async def get_all_leave_requests(
    session: AsyncSession, page: int, page_size: int, status: LeaveRequestStatus | None, year: int | None = None
) -> PaginatedData[LeaveRequestOut]:
    repo = LeaveRequestRepository(session)
    records, total = await repo.list_paginated(page, page_size, status=status, year=year)
    return _paginate(records, page, page_size, total)


def _paginate(records: list[LeaveRequest], page: int, page_size: int, total: int) -> PaginatedData[LeaveRequestOut]:
    items = [LeaveRequestOut.from_model(r) for r in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[LeaveRequestOut](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
