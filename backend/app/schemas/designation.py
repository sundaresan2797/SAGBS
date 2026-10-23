from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DepartmentStatus


class DesignationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    department_id: int


class DesignationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    department_id: int | None = None
    status: DepartmentStatus | None = None


class DesignationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    department_id: int
    department_name: str
    status: DepartmentStatus
    # Live number, filled in on every list (never cached with the title itself): current staff holding it.
    employee_count: int = 0

    @classmethod
    def from_model(cls, designation) -> "DesignationOut":
        return cls(
            id=designation.id,
            name=designation.name,
            description=designation.description,
            department_id=designation.department_id,
            department_name=designation.department.name,
            status=designation.status,
        )
