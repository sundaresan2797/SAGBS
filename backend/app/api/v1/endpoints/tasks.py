from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.enums import TaskStatus
from app.models.user import User
from app.schemas.common import PaginatedData, SuccessResponse
from app.schemas.task import TaskCommentCreate, TaskCommentOut, TaskCreate, TaskOut, TaskStatusUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    response_model=SuccessResponse[TaskOut],
    status_code=201,
    summary="Create and assign a task",
    dependencies=[Depends(require_permission("task:create"))],
)
async def create_task(
    payload: TaskCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await task_service.create_task(session, current_user, payload, request)
    return SuccessResponse(message="Task created successfully", data=result)


@router.get(
    "/my",
    response_model=SuccessResponse[PaginatedData[TaskOut]],
    summary="My assigned tasks",
    dependencies=[Depends(require_permission("task:read_own"))],
)
async def my_tasks(
    status: TaskStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await task_service.list_my_tasks(session, current_user, status, page, page_size)
    return SuccessResponse(data=result)


@router.get(
    "/team",
    response_model=SuccessResponse[PaginatedData[TaskOut]],
    summary="My team's tasks (managers)",
    dependencies=[Depends(require_permission("task:read_team"))],
)
async def team_tasks(
    status: TaskStatus | None = Query(default=None),
    due_date_from: date | None = Query(default=None),
    due_date_to: date | None = Query(default=None),
    assigned_to: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await task_service.list_team_tasks(
        session, current_user, status, page, page_size, due_date_from, due_date_to, assigned_to
    )
    return SuccessResponse(data=result)


@router.get("/{task_id}", response_model=SuccessResponse[TaskOut], summary="Get a task")
async def get_task(
    task_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    result = await task_service.get_task_detail(session, current_user, task_id)
    return SuccessResponse(data=result)


@router.patch("/{task_id}/status", response_model=SuccessResponse[TaskOut], summary="Update task status")
async def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await task_service.update_task_status(session, current_user, task_id, payload, request)
    return SuccessResponse(message="Task status updated successfully", data=result)


@router.get(
    "/{task_id}/comments", response_model=SuccessResponse[list[TaskCommentOut]], summary="List task comments"
)
async def list_comments(
    task_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    result = await task_service.list_comments(session, current_user, task_id)
    return SuccessResponse(data=result)


@router.post(
    "/{task_id}/comments",
    response_model=SuccessResponse[TaskCommentOut],
    status_code=201,
    summary="Add a task comment",
)
async def add_comment(
    task_id: int,
    payload: TaskCommentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await task_service.add_comment(session, current_user, task_id, payload, request)
    return SuccessResponse(message="Comment added successfully", data=result)
