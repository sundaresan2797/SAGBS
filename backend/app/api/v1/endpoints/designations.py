from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.designation import DesignationCreate, DesignationOut, DesignationUpdate
from app.services import designation_service

router = APIRouter(prefix="/designations", tags=["Designations"])


@router.get("", response_model=SuccessResponse[list[DesignationOut]], summary="List designations")
async def list_designations(
    department_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    designations = await designation_service.list_designations(session, department_id)
    return SuccessResponse(data=designations)


@router.post(
    "",
    response_model=SuccessResponse[DesignationOut],
    status_code=201,
    summary="Create a designation",
    dependencies=[Depends(require_permission("designation:manage"))],
)
async def create_designation(
    payload: DesignationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    designation = await designation_service.create_designation(session, payload, current_user, request)
    return SuccessResponse(message="Designation created successfully", data=designation)


@router.put(
    "/{designation_id}",
    response_model=SuccessResponse[DesignationOut],
    summary="Update a designation",
    dependencies=[Depends(require_permission("designation:manage"))],
)
async def update_designation(
    designation_id: int,
    payload: DesignationUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    designation = await designation_service.update_designation(session, designation_id, payload, current_user, request)
    return SuccessResponse(message="Designation updated successfully", data=designation)
