from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, notification_id: int) -> Notification | None:
        result = await self.session.execute(select(Notification).where(Notification.id == notification_id))
        return result.scalar_one_or_none()

    async def list_paginated(
        self, user_id: int, page: int, page_size: int, unread_only: bool = False
    ) -> tuple[list[Notification], int]:
        query = select(Notification).where(Notification.user_id == user_id)
        count_query = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
            count_query = count_query.where(Notification.is_read.is_(False))

        total = (await self.session.execute(count_query)).scalar_one()
        query = query.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def unread_count(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        return result.scalar_one()

    async def mark_all_read(self, user_id: int) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
