from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.notification import Notification
from app.models.rbac import Permission, RolePermission
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.schemas.common import PaginatedData
from app.schemas.notification import NotificationOut


async def list_my_notifications(
    session: AsyncSession, current_user: User, page: int, page_size: int, unread_only: bool
) -> PaginatedData[NotificationOut]:
    repo = NotificationRepository(session)
    records, total = await repo.list_paginated(current_user.id, page, page_size, unread_only)
    items = [NotificationOut.model_validate(n) for n in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[NotificationOut](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


async def get_unread_count(session: AsyncSession, current_user: User) -> int:
    repo = NotificationRepository(session)
    return await repo.unread_count(current_user.id)


async def mark_as_read(session: AsyncSession, current_user: User, notification_id: int) -> NotificationOut:
    repo = NotificationRepository(session)
    notification = await repo.get_by_id(notification_id)
    if notification is None:
        raise NotFoundError("Notification not found.", error_code="NOTIFICATION_NOT_FOUND")
    if notification.user_id != current_user.id:
        raise ForbiddenError("You cannot access another user's notifications.", error_code="NOTIFICATION_FORBIDDEN")

    notification.is_read = True
    await session.commit()
    return NotificationOut.model_validate(notification)


async def mark_all_as_read(session: AsyncSession, current_user: User) -> None:
    repo = NotificationRepository(session)
    await repo.mark_all_read(current_user.id)
    await session.commit()


def add_notification(session: AsyncSession, user_id: int, title: str, message: str, notification_type: str) -> None:
    """Queue one notification; it is saved with the caller's own commit, so it never outlives a failed action."""
    session.add(Notification(user_id=user_id, title=title, message=message, notification_type=notification_type))


async def user_ids_with_permission(session: AsyncSession, permission_code: str) -> list[int]:
    """Every active login whose role holds the permission - who to tell about work that needs their decision."""
    result = await session.execute(
        select(User.id)
        .join(RolePermission, RolePermission.role_id == User.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == permission_code, User.is_active.is_(True))
    )
    return list(result.scalars().all())
