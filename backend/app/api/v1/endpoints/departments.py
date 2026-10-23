from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.department import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services import department_service

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=SuccessResponse[list[DepartmentOut]], summary="List all departments")
async def list_departments(
    current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    departments = await department_service.list_departments(session)
    return SuccessResponse(data=departments)


@router.post(
    "",
    response_model=SuccessResponse[DepartmentOut],
    status_code=201,
    summary="Create a department",
    dependencies=[Depends(require_permission("department:manage"))],
)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    department = await department_service.create_department(session, payload, current_user, request)
    return SuccessResponse(message="Department created successfully", data=department)


@router.put(
    "/{department_id}",
    response_model=SuccessResponse[DepartmentOut],
    summary="Update a department",
    dependencies=[Depends(require_permission("department:manage"))],
)
async def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    department = await department_service.update_department(session, department_id, payload, current_user, request)
    return SuccessResponse(message="Department updated successfully", data=department)
