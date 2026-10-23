from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DepartmentStatus


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: DepartmentStatus | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: DepartmentStatus
    # Live numbers, filled in on every list (never cached with the department itself): current staff in it,
    # and its active job titles.
    employee_count: int = 0
    designation_count: int = 0
