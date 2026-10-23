from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.models.enums import AuditAction, EmployeeStatus, ExpenseClaimStatus, SalaryPaymentStatus
from app.models.payroll import ExpenseClaim, SalaryPayment, SalaryRecord
from app.models.user import User
from app.repositories.employee_repository import EmployeeFilters, EmployeeRepository
from app.services import payroll_attendance_service
from app.repositories.payroll_repository import (
    ExpenseClaimRepository,
    SalaryPaymentRepository,
    SalaryRecordRepository,
)
from app.schemas.common import PaginatedData
from app.schemas.payroll import (
    ExpenseClaimCreate,
    ExpenseClaimOut,
    PayrollDirectoryEntry,
    RunPayrollRequest,
    SalaryPaymentOut,
    SalaryRecordCreate,
    SalaryRecordOut,
    UnpaidEarlierOut,
)
from app.services import payslip_service
from app.services.audit_service import log_action
from app.services.notification_service import add_notification, user_ids_with_permission


async def _get_own_employee_or_raise(session: AsyncSession, current_user: User):
    employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")
    return employee


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------


async def get_payroll_directory(session: AsyncSession) -> list[PayrollDirectoryEntry]:
    repo = EmployeeRepository(session)
    filters = EmployeeFilters(status=EmployeeStatus.ACTIVE)
    employees, _ = await repo.list_paginated(filters, page=1, page_size=1000, sort_by="first_name", sort_desc=False)
    return [PayrollDirectoryEntry.from_model(e) for e in employees]


async def list_salary_records(session: AsyncSession) -> list[SalaryRecordOut]:
    """Each active person's CURRENT salary (one row per employee) - not their whole history."""
    repo = SalaryRecordRepository(session)
    return [SalaryRecordOut.from_model(r) for r in await repo.list_current()]


async def get_salary_history(session: AsyncSession, employee_id: int) -> list[SalaryRecordOut]:
    """Every salary an employee has ever had, oldest first - so a raise never erases what came before it."""
    employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    records = await SalaryRecordRepository(session).list_history_for_employee(employee_id)
    return [SalaryRecordOut.from_model(r) for r in records]


async def get_my_salary_history(session: AsyncSession, current_user: User) -> list[SalaryRecordOut]:
    employee = await _get_own_employee_or_raise(session, current_user)
    records = await SalaryRecordRepository(session).list_history_for_employee(employee.id)
    return [SalaryRecordOut.from_model(r) for r in records]


async def set_salary_record(
    session: AsyncSession, payload: SalaryRecordCreate, current_user: User, request: Request | None = None
) -> SalaryRecordOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_id(payload.employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    # Whoever sets pay can't set their own - someone else does that.
    own_employee = await employee_repo.get_by_user_id(current_user.id)
    if own_employee is not None and own_employee.id == employee.id:
        raise ForbiddenError(
            "You can't set your own salary. Someone else needs to do that.", error_code="SALARY_OWN_RECORD"
        )

    repo = SalaryRecordRepository(session)
    # Re-saving the same effective date corrects that entry; any other date is a new point in the
    # person's salary history, so their earlier salary is kept rather than overwritten.
    existing_any = await repo.list_history_for_employee(payload.employee_id)
    record = await repo.get_by_employee_and_date(payload.employee_id, payload.effective_from)
    action = AuditAction.UPDATE_SALARY_RECORD if (record or existing_any) else AuditAction.CREATE_SALARY_RECORD
    if record is None:
        record = SalaryRecord(employee_id=payload.employee_id, effective_from=payload.effective_from)
        repo.add(record)

    record.basic_pay = payload.basic_pay
    record.allowances = payload.allowances
    record.deductions = payload.deductions

    await session.flush()
    await log_action(
        session,
        user_id=current_user.id,
        action=action,
        entity_type="SalaryRecord",
        entity_id=record.id,
        description=f"Set salary structure for {employee.employee_code}",
        request=request,
    )
    await session.commit()
    await session.refresh(record, ["employee"])
    return SalaryRecordOut.from_model(record)


def _month_has_ended(year: int, month: int) -> bool:
    month_end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return month_end < date.today()


async def run_payroll(
    session: AsyncSession, payload: RunPayrollRequest, current_user: User, request: Request | None = None
) -> list[SalaryPaymentOut]:
    """Pays each person for the days they actually worked that month (present/late/paid leave/holidays
    in full, a half day at half pay, absent or unpaid leave not paid) - the same numbers the Attendance
    Summary preview already shows, from `calculate_month_pay`. The month must be completely over first:
    part-way through, some days are still "not decided yet" and there is no correct number to pay.
    """
    if not _month_has_ended(payload.year, payload.month):
        raise BusinessRuleError(
            "Payroll can only be run once the month is completely over, so every day's attendance is settled.",
            error_code="PAYROLL_MONTH_NOT_ENDED",
        )

    payment_repo = SalaryPaymentRepository(session)
    calculations = await payroll_attendance_service.calculate_month_pay(session, payload.year, payload.month)

    created: list[SalaryPayment] = []
    for calc in calculations:
        record = calc.record
        existing = await payment_repo.get(record.employee_id, payload.year, payload.month)
        if existing is not None:
            continue
        # The month has ended, so calculate_month_pay always returns a real number here - never None.
        assert calc.pay is not None
        counts = calc.counts
        payment = SalaryPayment(
            employee_id=record.employee_id,
            year=payload.year,
            month=payload.month,
            amount=float(calc.pay),
            basic_pay=record.basic_pay,
            allowances=record.allowances,
            deductions=record.deductions,
            status=SalaryPaymentStatus.PENDING,
            total_days=counts.total_days,
            present_days=counts.present,
            late_days=counts.late,
            half_days=counts.half_day,
            half_leave_days=counts.half_leave_days,
            paid_leave_days=counts.paid_leave,
            unpaid_leave_days=counts.unpaid_leave,
            absent_days=counts.absent,
            days_off_days=counts.days_off,
            payable_days=counts.payable_days,
            cut_days=counts.cut_days,
        )
        payment_repo.add(payment)
        created.append(payment)

    await session.flush()
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.RUN_PAYROLL,
        entity_type="SalaryPayment",
        entity_id=None,
        description=f"Ran payroll for {payload.month}/{payload.year}: {len(created)} new payment(s) generated",
        request=request,
    )
    await session.commit()

    all_payments = await payment_repo.list_for_month(payload.year, payload.month)
    return [SalaryPaymentOut.from_model(p) for p in all_payments]


async def list_salary_payments(session: AsyncSession, year: int, month: int) -> list[SalaryPaymentOut]:
    repo = SalaryPaymentRepository(session)
    return [SalaryPaymentOut.from_model(p) for p in await repo.list_for_month(year, month)]


async def get_unpaid_earlier(session: AsyncSession, year: int, month: int) -> UnpaidEarlierOut:
    count, total = await SalaryPaymentRepository(session).unpaid_before(year, month)
    return UnpaidEarlierOut(count=count, total_amount=total)


async def get_payslip_pdf(session: AsyncSession, payment_id: int, current_user: User) -> tuple[bytes, str]:
    payment = await SalaryPaymentRepository(session).get_by_id(payment_id)
    if payment is None:
        raise NotFoundError("Salary payment not found.", error_code="SALARY_PAYMENT_NOT_FOUND")

    has_payroll_view = any(p.code == "payroll:view" for p in current_user.role.permissions)
    if not has_payroll_view:
        own_employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
        if own_employee is None or own_employee.id != payment.employee_id:
            raise ForbiddenError("You can only download your own payslip.", error_code="PAYSLIP_OUT_OF_SCOPE")

    if payment.status != SalaryPaymentStatus.PAID:
        raise BusinessRuleError(
            "This payslip isn't available until the salary has been marked as paid.",
            error_code="PAYSLIP_NOT_PAID",
        )

    pdf_bytes = payslip_service.render_payslip_pdf(payment)
    filename = f"Payslip_{payment.employee.employee_code}_{payslip_service.MONTH_NAMES[payment.month - 1]}{payment.year}.pdf"
    return pdf_bytes, filename


async def get_my_salary_record(session: AsyncSession, current_user: User) -> SalaryRecordOut | None:
    employee = await _get_own_employee_or_raise(session, current_user)
    record = await SalaryRecordRepository(session).get_current(employee.id)
    return SalaryRecordOut.from_model(record) if record else None


async def get_my_salary_payments(
    session: AsyncSession, current_user: User, page: int, page_size: int, year: int | None = None
) -> PaginatedData[SalaryPaymentOut]:
    employee = await _get_own_employee_or_raise(session, current_user)
    records, total = await SalaryPaymentRepository(session).list_for_employee(employee.id, page, page_size, year)
    return _paginate([SalaryPaymentOut.from_model(r) for r in records], page, page_size, total)


async def mark_salary_paid(
    session: AsyncSession, payment_id: int, current_user: User, request: Request | None = None
) -> SalaryPaymentOut:
    repo = SalaryPaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        raise NotFoundError("Salary payment not found.", error_code="SALARY_PAYMENT_NOT_FOUND")
    if payment.status == SalaryPaymentStatus.PAID:
        raise BusinessRuleError("This salary payment is already marked as paid.", error_code="ALREADY_PAID")
    # Whoever handles the money can't confirm their own pay - someone else does that.
    own_employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    if own_employee is not None and own_employee.id == payment.employee_id:
        raise ForbiddenError(
            "You can't mark your own salary as paid. Someone else needs to do that.",
            error_code="SALARY_OWN_PAYMENT",
        )
    # Same rule as running payroll: until the month is over the amount isn't final, so nothing can be paid yet.
    if not _month_has_ended(payment.year, payment.month):
        raise BusinessRuleError(
            "This salary can only be paid once the month is completely over, so the amount is final.",
            error_code="SALARY_MONTH_NOT_ENDED",
        )

    payment.status = SalaryPaymentStatus.PAID
    payment.paid_date = date.today()

    add_notification(
        session,
        payment.employee.user_id,
        "Salary paid",
        f"Your salary for {payslip_service.MONTH_NAMES[payment.month - 1]} {payment.year} was paid. Your payslip is ready.",
        "SALARY_PAID",
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.PAY_SALARY,
        entity_type="SalaryPayment",
        entity_id=payment.id,
        description=f"Paid salary to {payment.employee.employee_code} for {payment.month}/{payment.year}",
        request=request,
    )
    await session.commit()
    return SalaryPaymentOut.from_model(payment)


# ---------------------------------------------------------------------------
# Expense claims
# ---------------------------------------------------------------------------


async def submit_expense_claim(
    session: AsyncSession, current_user: User, payload: ExpenseClaimCreate, request: Request | None = None
) -> ExpenseClaimOut:
    employee = await _get_own_employee_or_raise(session, current_user)

    claim = ExpenseClaim(
        employee_id=employee.id,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        status=ExpenseClaimStatus.PENDING,
    )
    ExpenseClaimRepository(session).add(claim)
    await session.flush()
    claim.employee = employee

    for reviewer_id in await user_ids_with_permission(session, "payroll:manage"):
        if reviewer_id != current_user.id:
            add_notification(
                session,
                reviewer_id,
                "New expense claim",
                f"{employee.full_name} sent a {payload.category.value.lower()} claim of \u20b9{payload.amount:g} for review.",
                "EXPENSE_SUBMITTED",
            )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_EXPENSE_CLAIM,
        entity_type="ExpenseClaim",
        entity_id=claim.id,
        description=f"{employee.employee_code} submitted a {payload.category.value.lower()} claim of {payload.amount}",
        request=request,
    )
    await session.commit()
    return ExpenseClaimOut.from_model(claim)


async def get_my_expense_claims(
    session: AsyncSession, current_user: User, page: int, page_size: int, year: int | None = None
) -> PaginatedData[ExpenseClaimOut]:
    employee = await _get_own_employee_or_raise(session, current_user)
    repo = ExpenseClaimRepository(session)
    records, total = await repo.list_paginated(page, page_size, employee_id=employee.id, year=year)
    return _paginate([ExpenseClaimOut.from_model(r) for r in records], page, page_size, total)


async def get_all_expense_claims(
    session: AsyncSession, page: int, page_size: int, status: ExpenseClaimStatus | None, year: int | None = None
) -> PaginatedData[ExpenseClaimOut]:
    repo = ExpenseClaimRepository(session)
    records, total = await repo.list_paginated(page, page_size, status=status, year=year)
    return _paginate([ExpenseClaimOut.from_model(r) for r in records], page, page_size, total)


async def _ensure_not_own_claim(session: AsyncSession, claim: ExpenseClaim, current_user: User) -> None:
    """Whoever handles money can still claim expenses, but someone else must decide on it."""
    own_employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    if own_employee is not None and own_employee.id == claim.employee_id:
        raise ForbiddenError(
            "You can't approve or reject your own claim. Someone else needs to decide on it.",
            error_code="EXPENSE_OWN_CLAIM",
        )


async def approve_expense_claim(
    session: AsyncSession, claim_id: int, current_user: User, request: Request | None = None
) -> ExpenseClaimOut:
    repo = ExpenseClaimRepository(session)
    claim = await repo.get_by_id(claim_id)
    if claim is None:
        raise NotFoundError("Expense claim not found.", error_code="EXPENSE_CLAIM_NOT_FOUND")
    if claim.status != ExpenseClaimStatus.PENDING:
        raise BusinessRuleError("Only pending claims can be approved.", error_code="INVALID_CLAIM_STATUS")
    await _ensure_not_own_claim(session, claim, current_user)

    claim.status = ExpenseClaimStatus.APPROVED
    claim.reviewed_by = current_user.id
    claim.reviewed_at = dt.now(timezone.utc)

    add_notification(
        session,
        claim.employee.user_id,
        "Expense claim approved",
        f"Your {claim.category.value.lower()} claim of \u20b9{float(claim.amount):g} was approved. The money will be paid to you soon.",
        "EXPENSE_APPROVED",
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.APPROVE_EXPENSE_CLAIM,
        entity_type="ExpenseClaim",
        entity_id=claim.id,
        description=f"Approved expense claim for {claim.employee.employee_code}",
        request=request,
    )
    await session.commit()
    return ExpenseClaimOut.from_model(claim)


async def reject_expense_claim(
    session: AsyncSession,
    claim_id: int,
    rejection_reason: str | None,
    current_user: User,
    request: Request | None = None,
) -> ExpenseClaimOut:
    repo = ExpenseClaimRepository(session)
    claim = await repo.get_by_id(claim_id)
    if claim is None:
        raise NotFoundError("Expense claim not found.", error_code="EXPENSE_CLAIM_NOT_FOUND")
    if claim.status != ExpenseClaimStatus.PENDING:
        raise BusinessRuleError("Only pending claims can be rejected.", error_code="INVALID_CLAIM_STATUS")
    await _ensure_not_own_claim(session, claim, current_user)

    claim.status = ExpenseClaimStatus.REJECTED
    claim.rejection_reason = rejection_reason
    claim.reviewed_by = current_user.id
    claim.reviewed_at = dt.now(timezone.utc)

    add_notification(
        session,
        claim.employee.user_id,
        "Expense claim not approved",
        f"Your {claim.category.value.lower()} claim of \u20b9{float(claim.amount):g} was not approved."
        + (f" Reason: {rejection_reason}" if rejection_reason else ""),
        "EXPENSE_REJECTED",
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.REJECT_EXPENSE_CLAIM,
        entity_type="ExpenseClaim",
        entity_id=claim.id,
        description=f"Rejected expense claim for {claim.employee.employee_code}",
        request=request,
    )
    await session.commit()
    return ExpenseClaimOut.from_model(claim)


async def pay_expense_claim(
    session: AsyncSession, claim_id: int, current_user: User, request: Request | None = None
) -> ExpenseClaimOut:
    repo = ExpenseClaimRepository(session)
    claim = await repo.get_by_id(claim_id)
    if claim is None:
        raise NotFoundError("Expense claim not found.", error_code="EXPENSE_CLAIM_NOT_FOUND")
    if claim.status != ExpenseClaimStatus.APPROVED:
        raise BusinessRuleError("Only approved claims can be marked as paid.", error_code="INVALID_CLAIM_STATUS")

    claim.status = ExpenseClaimStatus.PAID
    claim.paid_date = date.today()

    add_notification(
        session,
        claim.employee.user_id,
        "Expense claim paid",
        f"Your {claim.category.value.lower()} claim of \u20b9{float(claim.amount):g} has been paid to you.",
        "EXPENSE_PAID",
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.PAY_EXPENSE_CLAIM,
        entity_type="ExpenseClaim",
        entity_id=claim.id,
        description=f"Paid expense claim for {claim.employee.employee_code}",
        request=request,
    )
    await session.commit()
    return ExpenseClaimOut.from_model(claim)


def _paginate(items: list, page: int, page_size: int, total: int) -> PaginatedData:
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
