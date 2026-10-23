from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    assigned_to: int
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskCommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class TaskCommentOut(BaseModel):
    id: int
    author_id: int
    author_name: str
    comment: str
    created_at: datetime

    @classmethod
    def from_model(cls, comment) -> "TaskCommentOut":
        return cls(
            id=comment.id,
            author_id=comment.author_id,
            author_name=comment.author.full_name,
            comment=comment.comment,
            created_at=comment.created_at,
        )


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    assigned_to: int
    assignee_name: str
    assigned_by: int
    assigner_name: str
    priority: TaskPriority
    status: TaskStatus
    due_date: date | None
    created_at: datetime

    @classmethod
    def from_model(cls, task) -> "TaskOut":
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            assigned_to=task.assigned_to,
            assignee_name=task.assignee.full_name,
            assigned_by=task.assigned_by,
            assigner_name=task.assigner.full_name,
            priority=task.priority,
            status=task.status,
            due_date=task.due_date,
            created_at=task.created_at,
        )
