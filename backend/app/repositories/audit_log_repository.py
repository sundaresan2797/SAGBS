from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.user import User


@dataclass
class AuditLogFilters:
    user_id: int | None = None
    action: str | None = None
    entity_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    exclude_actions: list[str] | None = None


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_filters(self, query, filters: AuditLogFilters):
        if filters.user_id is not None:
            query = query.where(AuditLog.user_id == filters.user_id)
        if filters.action is not None:
            query = query.where(AuditLog.action == filters.action)
        if filters.exclude_actions:
            query = query.where(AuditLog.action.not_in(filters.exclude_actions))
        if filters.entity_type is not None:
            query = query.where(AuditLog.entity_type == filters.entity_type)
        if filters.date_from is not None:
            query = query.where(AuditLog.created_at >= filters.date_from)
        if filters.date_to is not None:
            query = query.where(AuditLog.created_at <= filters.date_to)
        return query

    async def list_paginated(
        self, filters: AuditLogFilters, page: int, page_size: int
    ) -> tuple[list[AuditLog], int]:
        base_query = self._apply_filters(select(AuditLog), filters)
        count_query = self._apply_filters(select(func.count()).select_from(AuditLog), filters)
        total = (await self.session.execute(count_query)).scalar_one()

        base_query = base_query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    async def names_for_users(self, user_ids: set[int]) -> dict[int, str]:
        """user id -> the name to show: the employee's full name, or the role ("Admin") for a login that has
        no employee profile."""
        if not user_ids:
            return {}
        employees = await self.session.execute(select(Employee.user_id, Employee.first_name, Employee.last_name).where(Employee.user_id.in_(user_ids)))
        names = {user_id: f"{first} {last}".strip() for user_id, first, last in employees.all()}
        missing = user_ids - set(names)
        if missing:
            users = await self.session.execute(select(User).where(User.id.in_(missing)))
            for user in users.scalars().all():
                names[user.id] = user.role.name.replace("_", " ").title()
        return names
