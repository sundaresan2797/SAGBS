from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import EmployeeDocument
from app.models.document_type import DocumentType


class DocumentTypeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, document_type_id: int) -> DocumentType | None:
        result = await self.session.execute(select(DocumentType).where(DocumentType.id == document_type_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> DocumentType | None:
        result = await self.session.execute(select(DocumentType).where(DocumentType.code == code))
        return result.scalar_one_or_none()

    # Ordered by id: the original six keep their familiar order and new ones follow.
    async def list_active(self) -> list[DocumentType]:
        result = await self.session.execute(
            select(DocumentType).where(DocumentType.is_active.is_(True)).order_by(DocumentType.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[DocumentType]:
        result = await self.session.execute(select(DocumentType).order_by(DocumentType.id))
        return list(result.scalars().all())

    async def counts(self) -> dict[int, int]:
        """document type id -> how many uploaded documents use it."""
        result = await self.session.execute(
            select(EmployeeDocument.document_type_id, func.count()).group_by(EmployeeDocument.document_type_id)
        )
        return {type_id: count for type_id, count in result.all()}

    async def usage_count(self, document_type_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(EmployeeDocument).where(EmployeeDocument.document_type_id == document_type_id)
        )
        return result.scalar_one()

    def add(self, document_type: DocumentType) -> None:
        self.session.add(document_type)

    async def delete(self, document_type: DocumentType) -> None:
        await self.session.delete(document_type)
