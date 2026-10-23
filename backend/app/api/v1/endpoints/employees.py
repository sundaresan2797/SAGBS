from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.enums import EmployeeStatus, EmploymentType
from app.models.user import User
from app.repositories.employee_repository import EmployeeFilters
from app.schemas.common import PaginatedData, SuccessResponse
from app.schemas.employee import (
    AdminPasswordResetRequest,
    EmployeeCreate,
    EmailChangeResult,
    EmployeeCreatedResponse,
    EmployeeEmailUpdate,
    EmployeeListItem,
    EmployeeOut,
    EmployeeRoleUpdate,
    EmployeeStatusUpdate,
    EmployeeUpdate,
    LoginRulesOut,
    MyProfileUpdate,
    PasswordResetResult,
    PhotoIndexEntry,
    PhotoOut,
)
from app.services import employee_service, photo_service

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("/me", response_model=SuccessResponse[EmployeeOut], summary="Get my own employee profile")
async def get_my_profile(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    profile = await employee_service.get_my_employee_profile(session, current_user)
    return SuccessResponse(data=profile)


@router.patch("/me", response_model=SuccessResponse[EmployeeOut], summary="Update my own permitted profile fields")
async def update_my_profile(
    payload: MyProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    profile = await employee_service.update_my_profile(session, current_user, payload.phone)
    return SuccessResponse(message="Profile updated successfully", data=profile)


@router.get(
    "/photo-index",
    response_model=SuccessResponse[list[PhotoIndexEntry]],
    summary="Who has a profile photo (and which version), so screens only fetch real photos",
)
async def photo_index(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await photo_service.photo_index(session))


@router.get(
    "/login-rules",
    response_model=SuccessResponse[LoginRulesOut],
    summary="Which roles the caller may hand out, and whose logins they may not touch",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def login_rules(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await employee_service.get_login_rules(session, current_user))


@router.get(
    "",
    response_model=SuccessResponse[PaginatedData[EmployeeListItem]],
    summary="List employees with search, filtering, and pagination",
    dependencies=[Depends(require_permission("employee:read"))],
)
async def list_employees(
    search: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    designation_id: int | None = Query(default=None),
    manager_id: int | None = Query(default=None),
    status: EmployeeStatus | None = Query(default=None),
    employment_type: EmploymentType | None = Query(default=None),
    joined_after: date | None = Query(default=None),
    joined_before: date | None = Query(default=None),
    work_location: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    # An allow-list, not a bare str: list_paginated resolves this with
    # getattr(Employee, sort_by, ...), so an unvalidated value could name any
    # attribute on the model (a relationship, an internal column) instead of
    # failing cleanly. FastAPI rejects anything outside this set with a 422.
    sort_by: Literal["id", "employee_code", "first_name", "last_name", "date_of_joining", "status"] = Query(
        default="id"
    ),
    sort_desc: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    filters = EmployeeFilters(
        search=search,
        department_id=department_id,
        designation_id=designation_id,
        manager_id=manager_id,
        status=status,
        employment_type=employment_type,
        joined_after=joined_after,
        joined_before=joined_before,
        work_location=work_location,
    )
    result = await employee_service.list_employees(
        session, current_user, filters, page, page_size, sort_by, sort_desc
    )
    return SuccessResponse(data=result)


@router.post(
    "",
    response_model=SuccessResponse[EmployeeCreatedResponse],
    status_code=201,
    summary="Create a new employee (also provisions a login account)",
    dependencies=[Depends(require_permission("employee:create"))],
)
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await employee_service.create_employee(session, payload, current_user, request)
    return SuccessResponse(message="Employee created successfully", data=result)


@router.get(
    "/{employee_id}/photo",
    summary="An employee's profile photo (a square JPEG) - any signed-in user",
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_photo(
    employee_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    content, media_type = await photo_service.read_photo(session, employee_id)
    # "private": only the person's own browser may keep it, and never a shared cache.
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.put(
    "/{employee_id}/photo",
    response_model=SuccessResponse[PhotoOut],
    summary="Set a profile photo (your own; HR, Founder and Admin can set anyone's)",
)
async def set_photo(
    employee_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await photo_service.set_photo(session, current_user, employee_id, file, request)
    return SuccessResponse(message="Photo saved", data=result)


@router.delete(
    "/{employee_id}/photo",
    response_model=SuccessResponse[PhotoOut],
    summary="Remove a profile photo (your own; HR, Founder and Admin can remove anyone's)",
)
async def remove_photo(
    employee_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await photo_service.remove_photo(session, current_user, employee_id, request)
    return SuccessResponse(message="Photo removed", data=result)


@router.get(
    "/{employee_id}",
    response_model=SuccessResponse[EmployeeOut],
    summary="Get an employee's profile",
    dependencies=[Depends(require_permission("employee:read"))],
)
async def get_employee(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    employee = await employee_service.get_employee_detail(session, employee_id, current_user)
    return SuccessResponse(data=employee)


@router.put(
    "/{employee_id}",
    response_model=SuccessResponse[EmployeeOut],
    summary="Update an employee",
    dependencies=[Depends(require_permission("employee:update"))],
)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    employee = await employee_service.update_employee(session, employee_id, payload, current_user, request)
    return SuccessResponse(message="Employee updated successfully", data=employee)


@router.patch(
    "/{employee_id}/status",
    response_model=SuccessResponse[EmployeeOut],
    summary="Activate/deactivate or change an employee's status",
    dependencies=[Depends(require_permission("employee:deactivate"))],
)
async def update_employee_status(
    employee_id: int,
    payload: EmployeeStatusUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    employee = await employee_service.update_employee_status(session, employee_id, payload, current_user, request)
    return SuccessResponse(message="Employee status updated successfully", data=employee)


@router.patch(
    "/{employee_id}/role",
    response_model=SuccessResponse[None],
    summary="Change the role of an employee's login",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def change_login_role(
    employee_id: int,
    payload: EmployeeRoleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await employee_service.change_user_role(session, employee_id, payload.role, current_user, request)
    return SuccessResponse(message="Role changed. They will need to sign in again.")


@router.patch(
    "/{employee_id}/email",
    response_model=SuccessResponse[EmailChangeResult],
    summary="Change the login email of an employee's account",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def change_login_email(
    employee_id: int,
    payload: EmployeeEmailUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await employee_service.change_user_email(session, employee_id, payload.new_email, current_user, request)
    return SuccessResponse(message="Email changed. They will need to sign in again with the new address.", data=result)


@router.post(
    "/{employee_id}/reset-password",
    response_model=SuccessResponse[PasswordResetResult],
    summary="Admin-issued password reset for an employee's login",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def reset_employee_password(
    employee_id: int,
    payload: AdminPasswordResetRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await employee_service.admin_reset_password(
        session, employee_id, payload.new_password, current_user, request
    )
    return SuccessResponse(message="Password reset successfully", data=result)
