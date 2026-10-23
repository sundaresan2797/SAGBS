from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.common import PaginatedData, SuccessResponse
from app.schemas.notification import NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=SuccessResponse[PaginatedData[NotificationOut]], summary="List my notifications")
async def list_notifications(
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await notification_service.list_my_notifications(session, current_user, page, page_size, unread_only)
    return SuccessResponse(data=result)


@router.get("/unread-count", response_model=SuccessResponse[int], summary="Count of unread notifications")
async def unread_count(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    count = await notification_service.get_unread_count(session, current_user)
    return SuccessResponse(data=count)


@router.patch(
    "/{notification_id}/read", response_model=SuccessResponse[NotificationOut], summary="Mark a notification as read"
)
async def mark_read(
    notification_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    result = await notification_service.mark_as_read(session, current_user, notification_id)
    return SuccessResponse(data=result)


@router.patch("/read-all", response_model=SuccessResponse[None], summary="Mark all notifications as read")
async def mark_all_read(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    await notification_service.mark_all_as_read(session, current_user)
    return SuccessResponse(message="All notifications marked as read")
