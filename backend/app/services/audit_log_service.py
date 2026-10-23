from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_log_repository import AuditLogFilters, AuditLogRepository
from app.schemas.audit_log import AuditLogOut
from app.schemas.common import PaginatedData


async def list_audit_logs(
    session: AsyncSession, filters: AuditLogFilters, page: int, page_size: int
) -> PaginatedData[AuditLogOut]:
    repo = AuditLogRepository(session)
    records, total = await repo.list_paginated(filters, page, page_size)
    names = await repo.names_for_users({r.user_id for r in records if r.user_id is not None})
    items = [AuditLogOut.model_validate(r) for r in records]
    for item in items:
        item.user_name = names.get(item.user_id) if item.user_id is not None else None
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[AuditLogOut](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
