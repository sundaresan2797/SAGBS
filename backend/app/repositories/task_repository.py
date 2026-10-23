from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import TaskStatus
from app.models.task import Task, TaskComment

TASK_EAGER_OPTIONS = (selectinload(Task.assignee), selectinload(Task.assigner))


@dataclass
class TaskFilters:
    assigned_to: int | None = None
    assigned_to_in: list[int] | None = None
    assigned_by: int | None = None
    status: TaskStatus | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, task_id: int) -> Task | None:
        result = await self.session.execute(
            select(Task).options(*TASK_EAGER_OPTIONS).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    def _apply_filters(self, query, filters: TaskFilters):
        if filters.assigned_to is not None:
            query = query.where(Task.assigned_to == filters.assigned_to)
        if filters.assigned_to_in is not None:
            query = query.where(Task.assigned_to.in_(filters.assigned_to_in))
        if filters.assigned_by is not None:
            query = query.where(Task.assigned_by == filters.assigned_by)
        if filters.status is not None:
            query = query.where(Task.status == filters.status)
        if filters.due_date_from is not None:
            query = query.where(Task.due_date >= filters.due_date_from)
        if filters.due_date_to is not None:
            query = query.where(Task.due_date <= filters.due_date_to)
        return query

    async def list_paginated(self, filters: TaskFilters, page: int, page_size: int) -> tuple[list[Task], int]:
        base_query = self._apply_filters(select(Task).options(*TASK_EAGER_OPTIONS), filters)
        count_query = self._apply_filters(select(func.count()).select_from(Task), filters)
        total = (await self.session.execute(count_query)).scalar_one()

        base_query = base_query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    def add(self, task: Task) -> None:
        self.session.add(task)


class TaskCommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_task(self, task_id: int) -> list[TaskComment]:
        result = await self.session.execute(
            select(TaskComment)
            .options(selectinload(TaskComment.author))
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        )
        return list(result.scalars().all())

    def add(self, comment: TaskComment) -> None:
        self.session.add(comment)
