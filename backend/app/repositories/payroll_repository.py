from datetime import date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.enums import EmployeeStatus, ExpenseClaimStatus, SalaryPaymentStatus
from app.models.payroll import ExpenseClaim, SalaryPayment, SalaryRecord
from app.utils.timezone import get_org_timezone


class SalaryRecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current(self, employee_id: int, as_of: date | None = None) -> SalaryRecord | None:
        """The salary that applies on `as_of` (default today): the latest effective_from that has arrived."""
        as_of = as_of or date.today()
        result = await self.session.execute(
            select(SalaryRecord)
            .options(selectinload(SalaryRecord.employee))
            .where(SalaryRecord.employee_id == employee_id, SalaryRecord.effective_from <= as_of)
            .order_by(SalaryRecord.effective_from.desc(), SalaryRecord.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_employee_and_date(self, employee_id: int, effective_from: date) -> SalaryRecord | None:
        """An exact-date match, so re-saving the same effective date corrects that entry instead of duplicating it."""
        result = await self.session.execute(
            select(SalaryRecord).where(
                SalaryRecord.employee_id == employee_id, SalaryRecord.effective_from == effective_from
            )
        )
        return result.scalar_one_or_none()

    async def list_current(self, as_of: date | None = None) -> list[SalaryRecord]:
        """One row per employee: whichever salary applies on `as_of` (default today)."""
        as_of = as_of or date.today()
        latest = (
            select(SalaryRecord.employee_id, func.max(SalaryRecord.effective_from).label("effective_from"))
            .where(SalaryRecord.effective_from <= as_of)
            .group_by(SalaryRecord.employee_id)
            .subquery()
        )
        result = await self.session.execute(
            select(SalaryRecord)
            .options(selectinload(SalaryRecord.employee))
            .join(SalaryRecord.employee)
            .join(
                latest,
                (SalaryRecord.employee_id == latest.c.employee_id)
                & (SalaryRecord.effective_from == latest.c.effective_from),
            )
        )
        return list(result.scalars().all())

    async def list_history_for_employee(self, employee_id: int) -> list[SalaryRecord]:
        """Every salary this employee has ever had, oldest first."""
        result = await self.session.execute(
            select(SalaryRecord)
            .options(selectinload(SalaryRecord.employee))
            .where(SalaryRecord.employee_id == employee_id)
            .order_by(SalaryRecord.effective_from, SalaryRecord.id)
        )
        return list(result.scalars().all())

    async def count_active_without_record(self, joined_by: date) -> int:
        """Active employees (who had joined by that date) that have no salary structure yet."""
        has_record = select(SalaryRecord.employee_id)
        result = await self.session.execute(
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.status == EmployeeStatus.ACTIVE,
                Employee.date_of_joining <= joined_by,
                Employee.id.not_in(has_record),
            )
        )
        return int(result.scalar_one())

    def add(self, record: SalaryRecord) -> None:
        self.session.add(record)


class SalaryPaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, payment_id: int) -> SalaryPayment | None:
        result = await self.session.execute(
            select(SalaryPayment).options(selectinload(SalaryPayment.employee)).where(SalaryPayment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get(self, employee_id: int, year: int, month: int) -> SalaryPayment | None:
        result = await self.session.execute(
            select(SalaryPayment).where(
                SalaryPayment.employee_id == employee_id,
                SalaryPayment.year == year,
                SalaryPayment.month == month,
            )
        )
        return result.scalar_one_or_none()

    async def has_payments(self, year: int, month: int) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(SalaryPayment).where(SalaryPayment.year == year, SalaryPayment.month == month)
        )
        return result.scalar_one() > 0

    async def list_for_month(self, year: int, month: int) -> list[SalaryPayment]:
        result = await self.session.execute(
            select(SalaryPayment)
            .options(selectinload(SalaryPayment.employee))
            .where(SalaryPayment.year == year, SalaryPayment.month == month)
            .order_by(SalaryPayment.id)
        )
        return list(result.scalars().all())

    async def unpaid_before(self, year: int, month: int) -> tuple[int, float]:
        """Count and total of PENDING payments for months strictly before year/month."""
        result = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(SalaryPayment.amount), 0)).where(
                SalaryPayment.status == SalaryPaymentStatus.PENDING,
                or_(SalaryPayment.year < year, and_(SalaryPayment.year == year, SalaryPayment.month < month)),
            )
        )
        count, total = result.one()
        return int(count), float(total)

    async def list_for_employee(
        self, employee_id: int, page: int, page_size: int, year: int | None = None
    ) -> tuple[list[SalaryPayment], int]:
        conditions = [SalaryPayment.employee_id == employee_id]
        if year is not None:
            conditions.append(SalaryPayment.year == year)
        count_query = select(func.count()).select_from(SalaryPayment).where(*conditions)
        total = (await self.session.execute(count_query)).scalar_one()

        query = (
            select(SalaryPayment)
            .options(selectinload(SalaryPayment.employee))
            .where(*conditions)
            .order_by(SalaryPayment.year.desc(), SalaryPayment.month.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    def add(self, payment: SalaryPayment) -> None:
        self.session.add(payment)


class ExpenseClaimRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, claim_id: int) -> ExpenseClaim | None:
        result = await self.session.execute(
            select(ExpenseClaim).options(selectinload(ExpenseClaim.employee)).where(ExpenseClaim.id == claim_id)
        )
        return result.scalar_one_or_none()

    def _apply_filters(
        self, query, employee_id: int | None, status: ExpenseClaimStatus | None, year: int | None = None
    ):
        if employee_id is not None:
            query = query.where(ExpenseClaim.employee_id == employee_id)
        if status is not None:
            query = query.where(ExpenseClaim.status == status)
        if year is not None:  # the calendar year (in the company's timezone) the claim was submitted in
            tz = get_org_timezone()
            query = query.where(
                ExpenseClaim.created_at >= datetime(year, 1, 1, tzinfo=tz),
                ExpenseClaim.created_at < datetime(year + 1, 1, 1, tzinfo=tz),
            )
        return query

    async def list_paginated(
        self,
        page: int,
        page_size: int,
        employee_id: int | None = None,
        status: ExpenseClaimStatus | None = None,
        year: int | None = None,
    ) -> tuple[list[ExpenseClaim], int]:
        base_query = self._apply_filters(
            select(ExpenseClaim).options(selectinload(ExpenseClaim.employee)), employee_id, status, year
        )
        count_query = self._apply_filters(select(func.count()).select_from(ExpenseClaim), employee_id, status, year)
        total = (await self.session.execute(count_query)).scalar_one()
        base_query = base_query.order_by(ExpenseClaim.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total
    def add(self, claim: ExpenseClaim) -> None:
        self.session.add(claim)
