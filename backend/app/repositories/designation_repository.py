from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.designation import Designation
from app.models.employee import Employee
from app.models.enums import EmployeeStatus


class DesignationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, designation_id: int) -> Designation | None:
        result = await self.session.execute(select(Designation).where(Designation.id == designation_id))
        return result.scalar_one_or_none()

    async def get_by_name_and_department(self, name: str, department_id: int) -> Designation | None:
        result = await self.session.execute(
            select(Designation).where(
                func.lower(Designation.name) == name.lower(), Designation.department_id == department_id
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self, department_id: int | None = None) -> list[Designation]:
        query = select(Designation).order_by(Designation.name)
        if department_id is not None:
            query = query.where(Designation.department_id == department_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def counts(self) -> dict[int, int]:
        """designation id -> current staff (Active or On leave) holding it."""
        result = await self.session.execute(
            select(Employee.designation_id, func.count())
            .where(Employee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE]))
            .group_by(Employee.designation_id)
        )
        return {designation_id: count for designation_id, count in result.all()}

    async def count_holders(self, designation_id: int) -> int:
        """Everyone holding it, whatever their status - moving the title would leave all of them mismatched."""
        result = await self.session.execute(
            select(func.count()).select_from(Employee).where(Employee.designation_id == designation_id)
        )
        return result.scalar_one()

    def add(self, designation: Designation) -> None:
        self.session.add(designation)
