from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import LeaveAccrualFrequency, LeaveDayPart, LeaveRequestStatus


class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_paid: bool
    default_annual_days: float
    accrual_frequency: LeaveAccrualFrequency
    is_active: bool


class LeaveTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=100)
    is_paid: bool = True
    default_annual_days: float = Field(ge=0, le=365)
    accrual_frequency: LeaveAccrualFrequency = LeaveAccrualFrequency.ANNUAL

    @field_validator("code")
    @classmethod
    def normalize_code(cls, code: str) -> str:
        return code.upper()


class LeaveTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_paid: bool | None = None
    default_annual_days: float | None = Field(default=None, ge=0, le=365)
    accrual_frequency: LeaveAccrualFrequency | None = None
    is_active: bool | None = None


class LeaveBalanceOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    accrual_frequency: LeaveAccrualFrequency
    year: int
    allocated_days: float
    used_days: float
    remaining_days: float

    @classmethod
    def from_model(cls, balance, allocated_days: float | None = None) -> "LeaveBalanceOut":
        # For MONTHLY-accrual types, allocated_days is passed in already
        # pro-rated for elapsed months (see leave_service._effective_allocated_days)
        # rather than trusting the stored column, which only ever holds the
        # full annual figure.
        effective_allocated = float(balance.allocated_days) if allocated_days is None else allocated_days
        return cls(
            leave_type_id=balance.leave_type_id,
            leave_type_name=balance.leave_type.name,
            leave_type_code=balance.leave_type.code,
            accrual_frequency=balance.leave_type.accrual_frequency,
            year=balance.year,
            allocated_days=effective_allocated,
            used_days=float(balance.used_days),
            remaining_days=round(effective_allocated - float(balance.used_days), 1),
        )


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=1000)
    # Half-day leave: the first or second half of ONE day. Leave it out for whole days.
    day_part: LeaveDayPart | None = None

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, end_date: date, info) -> date:
        start_date = info.data.get("start_date")
        if start_date is not None and end_date < start_date:
            raise ValueError("End date cannot be before start date")
        return end_date

    @model_validator(mode="after")
    def half_day_is_one_day(self):
        if self.day_part is not None and self.start_date != self.end_date:
            raise ValueError("A half-day leave is for a single day. Use the same start and end date.")
        return self


class LeaveRecordRequest(LeaveRequestCreate):
    """A manager/HR entering leave for an employee who told them (e.g. by phone). The reason is required."""

    employee_id: int
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def tidy_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please write a short reason, for example: informed by phone at 9:10")
        return value


class LeaveRequestDecision(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=1000)


class LeaveRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    leave_type_id: int
    leave_type_name: str
    start_date: date
    end_date: date
    number_of_days: float
    reason: str | None
    status: LeaveRequestStatus
    approved_by: int | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    # Whose decision it is waiting for: the employee's direct manager (None if they have none).
    manager_name: str | None = None
    day_part: LeaveDayPart | None = None
    # Set when a manager/HR entered it for the employee; recorded_late means it was entered for a day already past.
    recorded_by_name: str | None = None
    recorded_late: bool = False

    @classmethod
    def from_model(cls, leave_request) -> "LeaveRequestOut":
        return cls(
            id=leave_request.id,
            employee_id=leave_request.employee_id,
            employee_name=leave_request.employee.full_name,
            employee_code=leave_request.employee.employee_code,
            leave_type_id=leave_request.leave_type_id,
            leave_type_name=leave_request.leave_type.name,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            number_of_days=float(leave_request.number_of_days),
            reason=leave_request.reason,
            status=leave_request.status,
            approved_by=leave_request.approved_by,
            approved_at=leave_request.approved_at,
            rejection_reason=leave_request.rejection_reason,
            created_at=leave_request.created_at,
            manager_name=leave_request.employee.manager.full_name if leave_request.employee.manager else None,
            day_part=leave_request.day_part,
            recorded_by_name=leave_request.recorded_by_name,
            recorded_late=leave_request.recorded_late,
        )
