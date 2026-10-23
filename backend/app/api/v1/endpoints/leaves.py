from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_any_permission, require_permission
from app.models.enums import LeaveRequestStatus
from app.models.user import User
from app.schemas.common import PaginatedData, SuccessResponse
from app.schemas.leave import (
    LeaveBalanceOut,
    LeaveRecordRequest,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestOut,
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveTypeUpdate,
)
from app.services import leave_service

router = APIRouter(tags=["Leave"])


@router.get("/leave-types", response_model=SuccessResponse[list[LeaveTypeOut]], summary="List active leave types")
async def list_leave_types(session: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=await leave_service.list_leave_types(session))


@router.get(
    "/leave-types/all",
    response_model=SuccessResponse[list[LeaveTypeOut]],
    summary="List all leave types, including inactive (management view)",
    dependencies=[Depends(require_permission("leave_type:manage"))],
)
async def list_all_leave_types(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await leave_service.list_all_leave_types(session))


@router.post(
    "/leave-types",
    response_model=SuccessResponse[LeaveTypeOut],
    status_code=201,
    summary="Create a leave type",
    dependencies=[Depends(require_permission("leave_type:manage"))],
)
async def create_leave_type(
    payload: LeaveTypeCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    leave_type = await leave_service.create_leave_type(session, payload, current_user, request)
    return SuccessResponse(message="Leave type created successfully", data=leave_type)


@router.patch(
    "/leave-types/{leave_type_id}",
    response_model=SuccessResponse[LeaveTypeOut],
    summary="Update a leave type",
    dependencies=[Depends(require_permission("leave_type:manage"))],
)
async def update_leave_type(
    leave_type_id: int,
    payload: LeaveTypeUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    leave_type = await leave_service.update_leave_type(session, leave_type_id, payload, current_user, request)
    return SuccessResponse(message="Leave type updated successfully", data=leave_type)


@router.delete(
    "/leave-types/{leave_type_id}",
    response_model=SuccessResponse[None],
    summary="Delete a leave type",
    dependencies=[Depends(require_permission("leave_type:manage"))],
)
async def delete_leave_type(
    leave_type_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await leave_service.delete_leave_type(session, leave_type_id, current_user, request)
    return SuccessResponse(message="Leave type deleted successfully")


@router.get(
    "/leaves/balance",
    response_model=SuccessResponse[list[LeaveBalanceOut]],
    summary="My leave balances for a year",
)
async def my_leave_balance(
    year: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    target_year = year or date.today().year
    balances = await leave_service.get_my_leave_balances(session, current_user, target_year)
    return SuccessResponse(data=balances)


@router.post(
    "/leaves",
    response_model=SuccessResponse[LeaveRequestOut],
    status_code=201,
    summary="Apply for leave",
    dependencies=[Depends(require_permission("leave:apply"))],
)
async def apply_leave(
    payload: LeaveRequestCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.apply_leave(session, current_user, payload, request)
    return SuccessResponse(message="Leave request submitted successfully", data=result)


@router.post(
    "/leaves/record",
    response_model=SuccessResponse[LeaveRequestOut],
    status_code=201,
    summary="Record leave for an employee who told you (manager, HR, Founder, Admin) - approved immediately",
    dependencies=[Depends(require_any_permission("attendance:read_all", "attendance:read_team"))],
)
async def record_leave(
    payload: LeaveRecordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.record_leave(session, current_user, payload, request)
    return SuccessResponse(message="Leave recorded", data=result)


@router.get("/leaves/my", response_model=SuccessResponse[PaginatedData[LeaveRequestOut]], summary="My leave requests")
async def my_leave_requests(
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only requests that start in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.get_my_leave_requests(session, current_user, page, page_size, year)
    return SuccessResponse(data=result)


@router.get(
    "/leaves/employee/{employee_id}",
    response_model=SuccessResponse[PaginatedData[LeaveRequestOut]],
    summary="One employee's leave requests (your own, your direct reports', or anyone's with attendance:read_all)",
)
async def employee_leave_requests(
    employee_id: int,
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only requests that start in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.get_employee_leave_requests(session, current_user, employee_id, page, page_size, year)
    return SuccessResponse(data=result)


@router.get(
    "/leaves/team",
    response_model=SuccessResponse[PaginatedData[LeaveRequestOut]],
    summary="Team leave requests (managers)",
    dependencies=[Depends(require_permission("leave:approve_team"))],
)
async def team_leave_requests(
    status: LeaveRequestStatus | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only requests that start in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.get_team_leave_requests(session, current_user, page, page_size, status, year)
    return SuccessResponse(data=result)


@router.get(
    "/leaves/requests",
    response_model=SuccessResponse[PaginatedData[LeaveRequestOut]],
    summary="All leave requests (HR/Admin)",
    dependencies=[Depends(require_permission("leave:manage_all"))],
)
async def all_leave_requests(
    status: LeaveRequestStatus | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only requests that start in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.get_all_leave_requests(session, page, page_size, status, year)
    return SuccessResponse(data=result)


@router.patch(
    "/leaves/{request_id}/approve",
    response_model=SuccessResponse[LeaveRequestOut],
    summary="Approve a leave request",
)
async def approve_leave(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.approve_leave(session, current_user, request_id, request)
    return SuccessResponse(message="Leave request approved", data=result)


@router.patch(
    "/leaves/{request_id}/reject",
    response_model=SuccessResponse[LeaveRequestOut],
    summary="Reject a leave request",
)
async def reject_leave(
    request_id: int,
    payload: LeaveRequestDecision,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.reject_leave(session, current_user, request_id, payload.rejection_reason, request)
    return SuccessResponse(message="Leave request rejected", data=result)


@router.patch(
    "/leaves/{request_id}/cancel",
    response_model=SuccessResponse[LeaveRequestOut],
    summary="Cancel my leave request",
)
async def cancel_leave(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await leave_service.cancel_leave(session, current_user, request_id, request)
    return SuccessResponse(message="Leave request cancelled", data=result)
