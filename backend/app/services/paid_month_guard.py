"""Once a person's payslip exists for a month, that month's attendance and leave are settled.

The payslip is a snapshot of the days counted when payroll ran, so changing a leave or permission afterwards
would leave the attendance screens and the payslip disagreeing. Everything that records or cancels leave or
permission for a past or current day asks this first.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError
from app.repositories.payroll_repository import SalaryPaymentRepository

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


async def ensure_months_not_paid(session: AsyncSession, employee_id: int, start: date, end: date) -> None:
    """Raise if this employee already has a payslip for any month from `start` to `end`."""
    repo = SalaryPaymentRepository(session)
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        if await repo.get(employee_id, year, month) is not None:
            raise BusinessRuleError(
                f"{_MONTHS[month - 1]} {year} is already paid, so its attendance can no longer be changed. "
                "Ask HR or the Accountant to adjust it in next month's pay.",
                error_code="MONTH_ALREADY_PAID",
            )
        month += 1
        if month == 13:
            year, month = year + 1, 1
