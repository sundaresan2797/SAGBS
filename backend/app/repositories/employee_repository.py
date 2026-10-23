from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.enums import EmployeeStatus, EmploymentType

EMPLOYEE_EAGER_OPTIONS = (
    selectinload(Employee.department),
    selectinload(Employee.designation),
    selectinload(Employee.manager),
    selectinload(Employee.user),
)


@dataclass
class EmployeeFilters:
    search: str | None = None
    department_id: int | None = None
    designation_id: int | None = None
    manager_id: int | None = None
    status: EmployeeStatus | None = None
    employment_type: EmploymentType | None = None
    joined_after: date | None = None
    joined_before: date | None = None
    work_location: str | None = None
    employee_ids: list[int] | None = None


class EmployeeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_filters(self, query, filters: EmployeeFilters):
        if filters.search:
            like = f"%{filters.search.lower()}%"
            query = query.where(
                or_(
                    func.lower(Employee.first_name).like(like),
                    func.lower(Employee.last_name).like(like),
                    func.lower(Employee.employee_code).like(like),
                    func.lower(Employee.email).like(like),
                )
            )
        if filters.department_id is not None:
            query = query.where(Employee.department_id == filters.department_id)
        if filters.designation_id is not None:
            query = query.where(Employee.designation_id == filters.designation_id)
        if filters.manager_id is not None:
            query = query.where(Employee.manager_id == filters.manager_id)
        if filters.status is not None:
            query = query.where(Employee.status == filters.status)
        if filters.employment_type is not None:
            query = query.where(Employee.employment_type == filters.employment_type)
        if filters.joined_after is not None:
            query = query.where(Employee.date_of_joining >= filters.joined_after)
        if filters.joined_before is not None:
            query = query.where(Employee.date_of_joining <= filters.joined_before)
        if filters.work_location:
            query = query.where(func.lower(Employee.work_location) == filters.work_location.lower())
        if filters.employee_ids is not None:
            query = query.where(Employee.id.in_(filters.employee_ids))
        return query

    async def list_paginated(
        self, filters: EmployeeFilters, page: int, page_size: int, sort_by: str = "id", sort_desc: bool = False
    ) -> tuple[list[Employee], int]:
        base_query = self._apply_filters(select(Employee).options(*EMPLOYEE_EAGER_OPTIONS), filters)

        count_query = self._apply_filters(select(func.count()).select_from(Employee), filters)
        total = (await self.session.execute(count_query)).scalar_one()

        sort_column = getattr(Employee, sort_by, Employee.id)
        order = sort_column.desc() if sort_desc else sort_column.asc()
        base_query = base_query.order_by(order).offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    async def get_by_id(self, employee_id: int) -> Employee | None:
        result = await self.session.execute(
            select(Employee).options(*EMPLOYEE_EAGER_OPTIONS).where(Employee.id == employee_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> Employee | None:
        result = await self.session.execute(
            select(Employee).options(*EMPLOYEE_EAGER_OPTIONS).where(Employee.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Employee | None:
        result = await self.session.execute(
            select(Employee).options(*EMPLOYEE_EAGER_OPTIONS).where(Employee.email == email)
        )
        return result.scalar_one_or_none()

    async def list_for_roll_call(self, joined_on_or_before: date, manager_id: int | None = None) -> list[Employee]:
        """Everyone who should be at work on a given day: current staff who had already joined by then."""
        query = (
            select(Employee)
            .options(*EMPLOYEE_EAGER_OPTIONS)
            .where(
                Employee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE]),
                Employee.date_of_joining <= joined_on_or_before,
            )
            .order_by(Employee.employee_code)
        )
        if manager_id is not None:
            query = query.where(Employee.manager_id == manager_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_active_direct_reports(self, manager_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Employee).where(
                Employee.manager_id == manager_id,
                Employee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE]),
            )
        )
        return result.scalar_one()

    async def get_direct_report_ids(self, manager_id: int) -> list[int]:
        result = await self.session.execute(select(Employee.id).where(Employee.manager_id == manager_id))
        return list(result.scalars().all())

    def add(self, employee: Employee) -> None:
        self.session.add(employee)


async def list_photo_paths(session: AsyncSession) -> list[tuple[int, str]]:
    """(employee id, stored photo path) for everyone who has a photo."""
    result = await session.execute(select(Employee.id, Employee.profile_photo).where(Employee.profile_photo.is_not(None)))
    return [(row[0], row[1]) for row in result.all()]
