from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.enums import LeaveRequestStatus
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType

# The employee's manager is loaded too: every leave request names whose decision it waits for, and an
# async session cannot fetch it lazily at the moment the response is built.
LEAVE_REQUEST_EAGER_OPTIONS = (
    selectinload(LeaveRequest.employee).selectinload(Employee.manager),
    selectinload(LeaveRequest.leave_type),
)


class LeaveTypeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, leave_type_id: int) -> LeaveType | None:
        result = await self.session.execute(select(LeaveType).where(LeaveType.id == leave_type_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> LeaveType | None:
        result = await self.session.execute(select(LeaveType).where(LeaveType.code == code))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[LeaveType]:
        result = await self.session.execute(
            select(LeaveType).where(LeaveType.is_active.is_(True)).order_by(LeaveType.name)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[LeaveType]:
        result = await self.session.execute(select(LeaveType).order_by(LeaveType.name))
        return list(result.scalars().all())

    async def is_referenced(self, leave_type_id: int) -> bool:
        balance_count = await self.session.execute(
            select(func.count()).select_from(LeaveBalance).where(LeaveBalance.leave_type_id == leave_type_id)
        )
        if balance_count.scalar_one() > 0:
            return True
        request_count = await self.session.execute(
            select(func.count()).select_from(LeaveRequest).where(LeaveRequest.leave_type_id == leave_type_id)
        )
        return request_count.scalar_one() > 0

    async def request_count(self, leave_type_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(LeaveRequest).where(LeaveRequest.leave_type_id == leave_type_id)
        )
        return result.scalar_one()

    def add(self, leave_type: LeaveType) -> None:
        self.session.add(leave_type)

    async def delete(self, leave_type: LeaveType) -> None:
        await self.session.delete(leave_type)


class LeaveBalanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, employee_id: int, leave_type_id: int, year: int) -> LeaveBalance | None:
        result = await self.session.execute(
            select(LeaveBalance)
            .options(selectinload(LeaveBalance.leave_type))
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_employee(self, employee_id: int, year: int) -> list[LeaveBalance]:
        result = await self.session.execute(
            select(LeaveBalance)
            .options(selectinload(LeaveBalance.leave_type))
            .where(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
        )
        return list(result.scalars().all())

    def add(self, balance: LeaveBalance) -> None:
        self.session.add(balance)


class LeaveRequestRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, request_id: int) -> LeaveRequest | None:
        result = await self.session.execute(
            select(LeaveRequest).options(*LEAVE_REQUEST_EAGER_OPTIONS).where(LeaveRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def pending_days(self, employee_id: int, leave_type_id: int, year: int) -> float:
        """Days already asked for, and still waiting for a decision, for one leave type in one year."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(LeaveRequest.number_of_days), 0)).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type_id == leave_type_id,
                LeaveRequest.status == LeaveRequestStatus.PENDING,
                func.extract("year", LeaveRequest.start_date) == year,
            )
        )
        return float(result.scalar_one())

    async def has_overlapping_request(
        self, employee_id: int, start_date: date, end_date: date, exclude_id: int | None = None
    ) -> bool:
        query = select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if exclude_id is not None:
            query = query.where(LeaveRequest.id != exclude_id)
        result = await self.session.execute(query)
        return result.scalar_one() > 0

    def _apply_filters(
        self,
        query,
        employee_id: int | None,
        employee_ids: list[int] | None,
        status: LeaveRequestStatus | None,
        year: int | None = None,
    ):
        if employee_id is not None:
            query = query.where(LeaveRequest.employee_id == employee_id)
        if employee_ids is not None:
            query = query.where(LeaveRequest.employee_id.in_(employee_ids))
        if status is not None:
            query = query.where(LeaveRequest.status == status)
        if year is not None:  # a request belongs to the calendar year it starts in (leave balances work the same way)
            query = query.where(LeaveRequest.start_date >= date(year, 1, 1), LeaveRequest.start_date <= date(year, 12, 31))
        return query

    async def list_paginated(
        self,
        page: int,
        page_size: int,
        employee_id: int | None = None,
        employee_ids: list[int] | None = None,
        status: LeaveRequestStatus | None = None,
        year: int | None = None,
    ) -> tuple[list[LeaveRequest], int]:
        base_query = self._apply_filters(
            select(LeaveRequest).options(*LEAVE_REQUEST_EAGER_OPTIONS), employee_id, employee_ids, status, year
        )
        count_query = self._apply_filters(
            select(func.count()).select_from(LeaveRequest), employee_id, employee_ids, status, year
        )
        total = (await self.session.execute(count_query)).scalar_one()

        base_query = (
            base_query.order_by(LeaveRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    def add(self, leave_request: LeaveRequest) -> None:
        self.session.add(leave_request)


class LeaveSummaryRepository:
    """Leave facts the monthly attendance summary needs (kept apart from the request CRUD above)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def approved_overlapping(
        self, employee_ids: list[int], date_from: date, date_to: date
    ) -> list[tuple[int, date, date, bool, str | None]]:
        """(employee_id, start, end, is_paid, day_part) of approved leave that touches the date range.
        day_part is None for whole days, or FIRST_HALF / SECOND_HALF for a half-day leave."""
        result = await self.session.execute(
            select(
                LeaveRequest.employee_id,
                LeaveRequest.start_date,
                LeaveRequest.end_date,
                LeaveType.is_paid,
                LeaveRequest.day_part,
            )
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.employee_id.in_(employee_ids),
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.start_date <= date_to,
                LeaveRequest.end_date >= date_from,
            )
        )
        return [(row[0], row[1], row[2], bool(row[3]), row[4]) for row in result.all()]

    async def half_day_employee_ids(self, target_date: date) -> set[int]:
        """Who has an approved half-day leave on this date."""
        result = await self.session.execute(
            select(LeaveRequest.employee_id).where(
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.day_part.is_not(None),
                LeaveRequest.start_date == target_date,
            )
        )
        return set(result.scalars().all())

    async def pending_overlapping(self, employee_ids: list[int], date_from: date, date_to: date) -> dict[int, int]:
        """How many waiting (not yet decided) leave requests each employee has touching the date range."""
        result = await self.session.execute(
            select(LeaveRequest.employee_id, func.count())
            .where(
                LeaveRequest.employee_id.in_(employee_ids),
                LeaveRequest.status == LeaveRequestStatus.PENDING,
                LeaveRequest.start_date <= date_to,
                LeaveRequest.end_date >= date_from,
            )
            .group_by(LeaveRequest.employee_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}
