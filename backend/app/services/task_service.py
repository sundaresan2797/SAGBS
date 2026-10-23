from datetime import date

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.redis import CacheKeys, redis_service
from app.models.enums import AuditAction, RoleName, TaskStatus
from app.models.notification import Notification
from app.models.task import Task, TaskComment
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.task_repository import TaskCommentRepository, TaskFilters, TaskRepository
from app.schemas.common import PaginatedData
from app.schemas.task import TaskCommentCreate, TaskCommentOut, TaskCreate, TaskOut, TaskStatusUpdate
from app.services.audit_service import log_action


async def _get_own_employee_or_raise(session: AsyncSession, current_user: User):
    employee = await EmployeeRepository(session).get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")
    return employee


async def create_task(
    session: AsyncSession, current_user: User, payload: TaskCreate, request: Request | None = None
) -> TaskOut:
    assigner = await _get_own_employee_or_raise(session, current_user)

    employee_repo = EmployeeRepository(session)
    assignee = await employee_repo.get_by_id(payload.assigned_to)
    if assignee is None:
        raise NotFoundError("Assignee not found.", error_code="EMPLOYEE_NOT_FOUND")

    # Task assignment always follows the real reporting line, for every role
    # including ADMIN - consistent with the Team Tasks view, which likewise
    # only ever shows direct reports. Admin's broader powers (employee/
    # department management, audit logs, etc.) are untouched; this is
    # specifically about who *you personally* can hand a task to.
    if assignee.manager_id != assigner.id:
        raise ForbiddenError(
            "You can only assign tasks to your direct reports.", error_code="TASK_ASSIGNEE_OUT_OF_SCOPE"
        )

    task = Task(
        title=payload.title,
        description=payload.description,
        assigned_to=payload.assigned_to,
        assigned_by=assigner.id,
        priority=payload.priority,
        status=TaskStatus.TODO,
        due_date=payload.due_date,
    )
    task_repo = TaskRepository(session)
    task_repo.add(task)
    await session.flush()
    task.assignee = assignee
    task.assigner = assigner

    session.add(
        Notification(
            user_id=assignee.user_id,
            title="New task assigned",
            message=f"You have been assigned: {task.title}",
            notification_type="TASK_ASSIGNED",
        )
    )

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_TASK,
        entity_type="Task",
        entity_id=task.id,
        description=f"Assigned task '{task.title}' to {assignee.employee_code}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return TaskOut.from_model(task)


async def update_task_status(
    session: AsyncSession, current_user: User, task_id: int, payload: TaskStatusUpdate, request: Request | None = None
) -> TaskOut:
    employee = await _get_own_employee_or_raise(session, current_user)

    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise NotFoundError("Task not found.", error_code="TASK_NOT_FOUND")

    if task.assigned_to != employee.id:
        raise ForbiddenError("You can only update the status of tasks assigned to you.", error_code="TASK_FORBIDDEN")

    task.status = payload.status

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_TASK,
        entity_type="Task",
        entity_id=task.id,
        description=f"Updated task '{task.title}' status to {payload.status.value}",
        request=request,
    )
    await session.commit()
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    return TaskOut.from_model(task)


async def _ensure_can_view_task(session: AsyncSession, current_user: User, task: Task) -> None:
    """Anyone who can see a task on their board may open it and read its comments: the person it is for,
    the person who gave it, the assignee's direct manager, and anyone with company-wide visibility
    (report:view, the same permission that widens the Company Tasks board). Admin sees everything."""
    if current_user.role.name == RoleName.ADMIN.value:
        return
    employee = await _get_own_employee_or_raise(session, current_user)
    if employee.id in (task.assigned_to, task.assigned_by) or task.assignee.manager_id == employee.id:
        return
    if any(permission.code == "report:view" for permission in current_user.role.permissions):
        return
    raise ForbiddenError("You do not have access to this task.", error_code="TASK_FORBIDDEN")


async def get_task_detail(session: AsyncSession, current_user: User, task_id: int) -> TaskOut:
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise NotFoundError("Task not found.", error_code="TASK_NOT_FOUND")

    await _ensure_can_view_task(session, current_user, task)
    return TaskOut.from_model(task)


async def list_my_tasks(
    session: AsyncSession, current_user: User, status: TaskStatus | None, page: int, page_size: int
) -> PaginatedData[TaskOut]:
    employee = await _get_own_employee_or_raise(session, current_user)
    repo = TaskRepository(session)
    records, total = await repo.list_paginated(TaskFilters(assigned_to=employee.id, status=status), page, page_size)
    return _paginate(records, page, page_size, total)


async def list_team_tasks(
    session: AsyncSession,
    current_user: User,
    status: TaskStatus | None,
    page: int,
    page_size: int,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
    assigned_to: int | None = None,
) -> PaginatedData[TaskOut]:
    # Deliberately not gated on role == MANAGER: "has a team" is a fact about
    # the manager_id chain, not a fixed role label. An ADMIN who also manages
    # people directly (e.g. a CEO with the COO/CTO/CFO reporting to them)
    # must see their team here too - the task:read_team permission (route
    # level) already keeps EMPLOYEE out. Nobody with zero reports just gets
    # an empty list, not a 403.
    #
    # report:view widens this further to every task in the company, not just
    # direct reports - the same shape as attendance_service.get_roll_call's
    # use of attendance:read_all. Held today by Founder, HR, Admin and
    # Executive; a plain Manager or Accountant still only sees their own
    # direct reports, exactly as before.
    permission_codes = {permission.code for permission in current_user.role.permissions}

    if "report:view" in permission_codes:
        # Company-wide: no manager_id filter at all. assigned_to, if given,
        # just narrows to that one person - anyone can be looked up, since
        # the caller can already see everyone. Nothing here needs the caller's own employee
        # profile, so a login without one (the Admin) can load the board too.
        scoped_ids = [assigned_to] if assigned_to is not None else None
    else:
        # Only a manager's own team needs to know who the caller is.
        manager_employee = await _get_own_employee_or_raise(session, current_user)
        employee_repo = EmployeeRepository(session)
        report_ids = await employee_repo.get_direct_report_ids(manager_employee.id)
        # assigned_to narrows the board to one direct report - but only if that
        # person actually IS a direct report, otherwise silently fall back to
        # the full team scope rather than let the param peek outside it.
        scoped_ids = [assigned_to] if assigned_to is not None and assigned_to in report_ids else report_ids
        scoped_ids = scoped_ids or [-1]

    repo = TaskRepository(session)
    records, total = await repo.list_paginated(
        TaskFilters(
            assigned_to_in=scoped_ids,
            status=status,
            due_date_from=due_date_from,
            due_date_to=due_date_to,
        ),
        page,
        page_size,
    )
    return _paginate(records, page, page_size, total)


async def add_comment(
    session: AsyncSession, current_user: User, task_id: int, payload: TaskCommentCreate, request: Request | None = None
) -> TaskCommentOut:
    employee = await _get_own_employee_or_raise(session, current_user)

    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise NotFoundError("Task not found.", error_code="TASK_NOT_FOUND")
    if employee.id not in (task.assigned_to, task.assigned_by):
        raise ForbiddenError("You do not have access to this task.", error_code="TASK_FORBIDDEN")

    comment_repo = TaskCommentRepository(session)
    comment = TaskComment(task_id=task.id, author_id=employee.id, comment=payload.comment)
    comment_repo.add(comment)
    await session.flush()
    comment.author = employee
    await session.commit()
    return TaskCommentOut.from_model(comment)


async def list_comments(session: AsyncSession, current_user: User, task_id: int) -> list[TaskCommentOut]:
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise NotFoundError("Task not found.", error_code="TASK_NOT_FOUND")
    await _ensure_can_view_task(session, current_user, task)

    comment_repo = TaskCommentRepository(session)
    comments = await comment_repo.list_for_task(task_id)
    return [TaskCommentOut.from_model(c) for c in comments]


def _paginate(records: list[Task], page: int, page_size: int, total: int) -> PaginatedData[TaskOut]:
    items = [TaskOut.from_model(t) for t in records]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedData[TaskOut](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
