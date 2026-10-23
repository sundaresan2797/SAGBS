from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import EmployeeDocument
from app.models.employee import Employee
from app.models.enums import EmployeeStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, document_id: int) -> EmployeeDocument | None:
        result = await self.session.execute(
            select(EmployeeDocument)
            .options(selectinload(EmployeeDocument.employee))
            .where(EmployeeDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def list_for_employee(self, employee_id: int) -> list[EmployeeDocument]:
        result = await self.session.execute(
            select(EmployeeDocument)
            .where(EmployeeDocument.employee_id == employee_id)
            .order_by(EmployeeDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_expiring(self, up_to: date, limit: int) -> tuple[list[EmployeeDocument], int]:
        """Documents of current staff that have already expired or expire on or before `up_to`, soonest first."""
        conditions = [
            EmployeeDocument.expiry_date.is_not(None),
            EmployeeDocument.expiry_date <= up_to,
            Employee.status == EmployeeStatus.ACTIVE,
        ]
        total = (
            await self.session.execute(
                select(func.count()).select_from(EmployeeDocument).join(Employee, Employee.id == EmployeeDocument.employee_id).where(*conditions)
            )
        ).scalar_one()
        result = await self.session.execute(
            select(EmployeeDocument)
            .join(Employee, Employee.id == EmployeeDocument.employee_id)
            .where(*conditions)
            .order_by(EmployeeDocument.expiry_date, EmployeeDocument.id)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    def add(self, document: EmployeeDocument) -> None:
        self.session.add(document)

    async def delete(self, document: EmployeeDocument) -> None:
        await self.session.delete(document)
