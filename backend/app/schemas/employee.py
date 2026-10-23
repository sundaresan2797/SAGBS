from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import EmployeeStatus, EmploymentType, RoleName


class EmployeeCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    date_of_joining: date
    department_id: int
    designation_id: int
    manager_id: int | None = None
    employment_type: EmploymentType
    work_location: str | None = Field(default=None, max_length=150)
    role: RoleName = RoleName.EMPLOYEE

    @field_validator("date_of_joining")
    @classmethod
    def joining_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Date of joining cannot be in the future")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def birth_date_in_past(cls, value: date | None) -> date | None:
        if value is not None and value >= date.today():
            raise ValueError("Date of birth must be in the past")
        return value


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    date_of_joining: date | None = None
    department_id: int | None = None
    designation_id: int | None = None
    manager_id: int | None = None
    employment_type: EmploymentType | None = None
    work_location: str | None = Field(default=None, max_length=150)

    @field_validator("date_of_joining")
    @classmethod
    def joining_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Date of joining cannot be in the future")
        return value


class EmployeeStatusUpdate(BaseModel):
    status: EmployeeStatus


class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class DesignationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class ManagerBrief(BaseModel):
    id: int
    full_name: str


class EmployeeListItem(BaseModel):
    id: int
    employee_code: str
    full_name: str
    email: str
    department: DepartmentBrief
    designation: DesignationBrief
    manager: ManagerBrief | None
    employment_type: EmploymentType
    status: EmployeeStatus
    date_of_joining: date
    account_role: str
    account_active: bool

    @classmethod
    def from_model(cls, employee) -> "EmployeeListItem":
        return cls(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            email=employee.email,
            department=DepartmentBrief.model_validate(employee.department),
            designation=DesignationBrief.model_validate(employee.designation),
            manager=ManagerBrief(id=employee.manager.id, full_name=employee.manager.full_name)
            if employee.manager
            else None,
            employment_type=employee.employment_type,
            status=employee.status,
            date_of_joining=employee.date_of_joining,
            account_role=employee.user.role.name,
            account_active=employee.user.is_active,
        )


class EmployeeOut(EmployeeListItem):
    phone: str | None
    date_of_birth: date | None
    work_location: str | None
    profile_photo: str | None

    @classmethod
    def from_model(cls, employee) -> "EmployeeOut":
        base = EmployeeListItem.from_model(employee)
        return cls(
            **base.model_dump(),
            phone=employee.phone,
            date_of_birth=employee.date_of_birth,
            work_location=employee.work_location,
            profile_photo=employee.profile_photo,
        )


class MyProfileUpdate(BaseModel):
    phone: str | None = Field(default=None, max_length=20)


class EmployeeCreatedResponse(BaseModel):
    employee: EmployeeOut
    temporary_password: str
    login_email: str


class AdminPasswordResetRequest(BaseModel):
    new_password: str | None = Field(default=None, min_length=8)


class EmployeeRoleUpdate(BaseModel):
    role: str = Field(min_length=2, max_length=50)


class EmployeeEmailUpdate(BaseModel):
    new_email: EmailStr


class EmailChangeResult(BaseModel):
    employee_id: int
    new_login_email: str


class LoginRulesOut(BaseModel):
    """What the caller may do to other people's logins, worked out from the roles' real permissions."""

    assignable_roles: list[str]  # roles the caller may give someone
    protected_roles: list[str]  # roles whose logins the caller may NOT reset or change (they carry powers the caller lacks)


class PasswordResetResult(BaseModel):
    login_email: str
    temporary_password: str



class PhotoOut(BaseModel):
    employee_id: int
    # Changes every time the photo changes, so screens know when to load the new picture.
    photo_version: str | None


class PhotoIndexEntry(BaseModel):
    employee_id: int
    photo_version: str
