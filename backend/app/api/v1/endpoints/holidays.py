from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.holiday import HolidayCreate, HolidayOut, HolidayUpdate
from app.services import holiday_service

router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.get("", response_model=SuccessResponse[list[HolidayOut]], summary="List holidays")
async def list_holidays(
    year: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await holiday_service.list_holidays(session, year))


@router.post(
    "",
    response_model=SuccessResponse[HolidayOut],
    status_code=201,
    summary="Add a holiday",
    dependencies=[Depends(require_permission("holiday:manage"))],
)
async def create_holiday(
    payload: HolidayCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await holiday_service.create_holiday(session, payload, current_user, request)
    return SuccessResponse(message="Holiday created successfully", data=result)


@router.put(
    "/{holiday_id}",
    response_model=SuccessResponse[HolidayOut],
    summary="Update a holiday",
    dependencies=[Depends(require_permission("holiday:manage"))],
)
async def update_holiday(
    holiday_id: int,
    payload: HolidayUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await holiday_service.update_holiday(session, holiday_id, payload, current_user, request)
    return SuccessResponse(message="Holiday updated successfully", data=result)


@router.delete(
    "/{holiday_id}",
    response_model=SuccessResponse[None],
    summary="Delete a holiday",
    dependencies=[Depends(require_permission("holiday:manage"))],
)
async def delete_holiday(
    holiday_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await holiday_service.delete_holiday(session, holiday_id, current_user, request)
    return SuccessResponse(message="Holiday deleted successfully")
