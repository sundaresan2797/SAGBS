"""Attendance-based pay: one calculation, used both by the Attendance Summary preview and by Run Payroll
itself, so the two can never disagree. See `calculate_month_pay` for the shared part.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payroll import SalaryRecord

from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.holiday_repository import HolidayRepository
from app.repositories.leave_repository import LeaveSummaryRepository
from app.repositories.payroll_repository import SalaryPaymentRepository, SalaryRecordRepository
from app.schemas.payroll import AttendanceSummaryChecklist, AttendanceSummaryOut, AttendanceSummaryRow, MonthCount
from app.services.attendance_summary import count_month, pay_for_month
from app.utils.timezone import today_in_org_tz


MISSED_LOOKBACK_DAYS = 366  # the same span the Attendance screen's missed list covers


@dataclass
class EmployeeMonthPay:
    """One employee's attendance-based pay for one month: the exact number Run Payroll pays,
    and the day counts behind it."""

    record: SalaryRecord  # the salary structure that applied when the month ended
    counts: object  # MonthCounts, from attendance_summary.count_month
    pay: Decimal | None  # None only if the month has not ended yet


async def calculate_month_pay(session: AsyncSession, year: int, month: int) -> list["EmployeeMonthPay"]:
    """Every employee's attendance-based pay for one month.

    Scope matches Run Payroll exactly: everyone with a salary structure that had started by the time
    the month ended, and who had joined by then. Nothing here reads what has already been paid - a
    fresh, independent answer to "what should this month's pay be", worked out from attendance alone.
    """
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    today = today_in_org_tz()

    records = [r for r in await SalaryRecordRepository(session).list_current(as_of=last) if r.employee.date_of_joining <= last]
    employee_ids = [r.employee_id for r in records]

    rows_by_employee: dict[int, dict[date, object]] = {}
    leave_by_employee: dict[int, dict[date, bool]] = {}
    half_leave_by_employee: dict[int, dict[date, bool]] = {}
    if employee_ids:
        for row in await AttendanceRepository(session).list_for_employees_between(employee_ids, first, last):
            rows_by_employee.setdefault(row.employee_id, {})[row.attendance_date] = row.status
        leave_repo = LeaveSummaryRepository(session)
        for employee_id, start, end, is_paid, day_part in await leave_repo.approved_overlapping(employee_ids, first, last):
            # A half-day leave is always a single date; it is counted apart from whole-day leave.
            bucket = half_leave_by_employee if day_part is not None else leave_by_employee
            days = bucket.setdefault(employee_id, {})
            day = max(start, first)
            while day <= min(end, last):
                # Overlapping approved leave is prevented when applying; this is only a guard (paid only if both are).
                days[day] = days.get(day, True) and is_paid
                day += timedelta(days=1)

    off_dates = {h.holiday_date for h in await HolidayRepository(session).list_between(first, last) if not h.is_optional}

    results: list[EmployeeMonthPay] = []
    for record in records:
        employee = record.employee
        counts = count_month(
            year,
            month,
            records=rows_by_employee.get(record.employee_id, {}),
            off_dates=off_dates,
            leave_days=leave_by_employee.get(record.employee_id, {}),
            half_leave_days=half_leave_by_employee.get(record.employee_id, {}),
            joining=employee.date_of_joining,
            today=today,
        )
        pay = pay_for_month(record.net_pay, counts)
        results.append(EmployeeMonthPay(record=record, counts=counts, pay=pay))
    return results


def _monthly_salary(record, payment) -> float:
    """The full monthly take-home for the month being looked at.

    If payroll already ran for that month, use the pay structure saved on its payslip, so a raise given later
    does not rewrite an old month. Payslips made before that breakdown was saved paid the full salary, so their
    amount is the salary. With no payslip yet, use the current salary structure.
    """
    if payment is not None:
        if payment.basic_pay is not None:
            return float(payment.basic_pay) + float(payment.allowances or 0) - float(payment.deductions or 0)
        return float(payment.amount)
    return record.net_pay


async def get_attendance_summary(session: AsyncSession, year: int, month: int) -> AttendanceSummaryOut:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    today = today_in_org_tz()

    calculations = await calculate_month_pay(session, year, month)
    employee_ids = [c.record.employee_id for c in calculations]

    missed_by_employee: dict[int, int] = {}
    pending_by_employee: dict[int, int] = {}
    if employee_ids:
        for row in await AttendanceRepository(session).list_for_employees_between(employee_ids, first, last):
            if row.check_in is not None and row.check_out is None and row.attendance_date < today:
                missed_by_employee[row.employee_id] = missed_by_employee.get(row.employee_id, 0) + 1
        pending_by_employee = await LeaveSummaryRepository(session).pending_overlapping(employee_ids, first, last)

    payments = {p.employee_id: p for p in await SalaryPaymentRepository(session).list_for_month(year, month)}

    items: list[AttendanceSummaryRow] = []
    total_pay = Decimal(0)
    total_salary = Decimal(0)
    total_payslips = Decimal(0)
    total_difference = Decimal(0)
    for calc in calculations:
        record, counts = calc.record, calc.counts
        employee = record.employee
        payment = payments.get(record.employee_id)
        # For a month with no payment yet, this is the same value calculate_month_pay just used - so the
        # preview and what Run Payroll will actually pay are identical. Once a payment exists, this instead
        # shows the salary that was ACTUALLY used at the time, even if it has since been corrected.
        monthly_salary = _monthly_salary(record, payment)
        pay = pay_for_month(monthly_salary, counts) if payment is not None else calc.pay
        difference = (Decimal(str(payment.amount)) - pay) if (payment is not None and pay is not None) else None
        total_salary += Decimal(str(monthly_salary))
        if pay is not None:
            total_pay += pay
        if payment is not None:
            total_payslips += Decimal(str(payment.amount))
        if difference is not None:
            total_difference += difference
        items.append(
            AttendanceSummaryRow(
                employee_id=record.employee_id,
                employee_code=employee.employee_code,
                employee_name=employee.full_name,
                total_days=counts.total_days,
                working_days=counts.working_days,
                present=counts.present,
                late=counts.late,
                half_day=counts.half_day,
                half_leave=counts.half_leave_days,
                paid_leave=counts.paid_leave,
                unpaid_leave=counts.unpaid_leave,
                absent=counts.absent,
                days_off=counts.days_off,
                before_joining=counts.before_joining,
                open_days=counts.open_days,
                payable_days=counts.payable_days,
                cut_days=counts.cut_days,
                monthly_salary=monthly_salary,
                pay_for_month=float(pay) if pay is not None else None,
                payslip_id=payment.id if payment is not None else None,
                payslip_amount=float(payment.amount) if payment is not None else None,
                payslip_status=payment.status if payment is not None else None,
                payslip_paid_date=payment.paid_date if payment is not None else None,
                difference=float(difference) if difference is not None else None,
                missed_check_outs=missed_by_employee.get(record.employee_id, 0),
                pending_leave_requests=pending_by_employee.get(record.employee_id, 0),
            )
        )

    # People with something to look at (a cut, or an open issue) come first.
    items.sort(
        key=lambda i: (
            0 if (i.cut_days > 0 or i.missed_check_outs or i.pending_leave_requests) else 1,
            i.employee_name.lower(),
        )
    )
    other_months: list[MonthCount] = []
    if employee_ids:
        found = await AttendanceRepository(session).missed_check_outs_by_month(
            employee_ids, before=today, since=today - timedelta(days=MISSED_LOOKBACK_DAYS), skip_from=first, skip_to=last
        )
        other_months = [MonthCount(year=y, month=m, count=n) for y, m, n in found]
    month_ended = today > last
    return AttendanceSummaryOut(
        year=year,
        month=month,
        total_days=calendar.monthrange(year, month)[1],
        month_ended=month_ended,
        items=items,
        checklist=AttendanceSummaryChecklist(
            missed_check_outs=sum(i.missed_check_outs for i in items),
            pending_leave_requests=sum(i.pending_leave_requests for i in items),
            employees_without_salary=await SalaryRecordRepository(session).count_active_without_record(last),
            absent_days=sum(i.absent for i in items),
            missed_check_outs_in_other_months=other_months,
        ),
        total_monthly_salary=float(total_salary),
        total_pay=float(total_pay) if month_ended and items else None,
        total_on_payslips=float(total_payslips) if payments else None,
        total_difference=float(total_difference) if any(i.difference is not None for i in items) else None,
    )
