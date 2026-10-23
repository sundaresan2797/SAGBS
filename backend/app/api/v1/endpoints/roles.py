from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.role import PermissionsMatrixOut, RolePermissionUpdate
from app.services import role_service

router = APIRouter(prefix="/roles", tags=["Roles"])

MANAGE = Depends(require_permission("role:manage"))


@router.get(
    "/permissions-matrix",
    response_model=SuccessResponse[PermissionsMatrixOut],
    summary="Every permission and which roles actually have it, read live from the database",
    dependencies=[MANAGE],
)
async def permissions_matrix(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await role_service.get_permissions_matrix(session))


@router.put(
    "/{role_name}/permissions/{permission_code}",
    response_model=SuccessResponse[PermissionsMatrixOut],
    summary="Grant or revoke one permission for one role",
    dependencies=[MANAGE],
)
async def set_role_permission(
    role_name: str,
    permission_code: str,
    payload: RolePermissionUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await role_service.set_role_permission(
        session, current_user, role_name, permission_code, payload.granted, request
    )
    return SuccessResponse(message="Updated.", data=result)
