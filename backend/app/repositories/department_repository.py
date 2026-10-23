from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.enums import DepartmentStatus, EmployeeStatus


class DepartmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, department_id: int) -> Department | None:
        result = await self.session.execute(select(Department).where(Department.id == department_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Department | None:
        result = await self.session.execute(
            select(Department).where(func.lower(Department.name) == name.lower())
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Department]:
        result = await self.session.execute(select(Department).order_by(Department.name))
        return list(result.scalars().all())

    async def counts(self) -> dict[int, tuple[int, int]]:
        """department id -> (current staff, active job titles)."""
        people = await self.session.execute(
            select(Employee.department_id, func.count()).where(
                Employee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE])
            ).group_by(Employee.department_id)
        )
        titles = await self.session.execute(
            select(Designation.department_id, func.count()).where(Designation.status == DepartmentStatus.ACTIVE).group_by(Designation.department_id)
        )
        result: dict[int, tuple[int, int]] = {}
        for department_id, count in people.all():
            result[department_id] = (count, 0)
        for department_id, count in titles.all():
            result[department_id] = (result.get(department_id, (0, 0))[0], count)
        return result

    def add(self, department: Department) -> None:
        self.session.add(department)
