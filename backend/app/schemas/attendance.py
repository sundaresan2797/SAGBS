from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AttendanceStatus


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    attendance_date: date
    check_in: datetime | None
    check_out: datetime | None
    working_minutes: int | None
    late_minutes: int
    overtime_minutes: int
    status: AttendanceStatus
    corrected_by_name: str | None = None
    corrected_at: datetime | None = None
    correction_reason: str | None = None


class AttendancePolicyOut(BaseModel):
    """The company's attendance rules. Times are "HH:MM" in the company timezone."""

    office_start: str
    grace_minutes: int
    late_after: str
    full_day_minimum_minutes: int
    half_day_after: str
    standard_shift_minutes: int
    long_day_minutes: int
    lunch_start: str
    lunch_break_minutes: int


class FixCheckOutIn(BaseModel):
    """A manager/HR fixing a check-out the employee forgot. Time is HH:MM on the same day."""

    check_out_time: time
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _tidy_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please write a short reason (at least 3 letters).")
        return value


class MarkPresentIn(BaseModel):
    """A manager/HR recording a day the employee worked but forgot to punch at all. Times are HH:MM."""

    employee_id: int
    attendance_date: date
    check_in_time: time
    check_out_time: time
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _tidy_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please write a short reason (at least 3 letters).")
        return value


class CorrectAttendanceIn(BaseModel):
    """A manager/HR/Founder/Admin correcting an already-recorded past day: new check-in and check-out
    times (the status - Present/Late/Half day - is worked out the normal way from those, never chosen by
    hand), or both left empty to clear the day back to Absent."""

    employee_id: int
    attendance_date: date
    check_in_time: time | None = None
    check_out_time: time | None = None
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _tidy_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please write a short reason (at least 3 letters).")
        return value

    @model_validator(mode="after")
    def _both_times_or_neither(self) -> "CorrectAttendanceIn":
        if (self.check_in_time is None) != (self.check_out_time is None):
            raise ValueError("Give both a check-in and check-out time, or leave both empty to clear the day to Absent.")
        return self


class OvertimeSummaryEntry(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    overtime_minutes: int


class AttendanceWithEmployee(AttendanceOut):
    employee_id: int
    employee_name: str
    employee_code: str

    @classmethod
    def from_model(cls, attendance) -> "AttendanceWithEmployee":
        return cls(
            id=attendance.id,
            employee_id=attendance.employee_id,
            employee_name=attendance.employee.full_name,
            employee_code=attendance.employee.employee_code,
            attendance_date=attendance.attendance_date,
            check_in=attendance.check_in,
            check_out=attendance.check_out,
            working_minutes=attendance.working_minutes,
            late_minutes=attendance.late_minutes,
            overtime_minutes=attendance.overtime_minutes,
            status=attendance.status,
            corrected_by_name=attendance.corrected_by_name,
            corrected_at=attendance.corrected_at,
            correction_reason=attendance.correction_reason,
        )


class MissedCheckOutsOut(BaseModel):
    items: list[AttendanceWithEmployee]
    total: int  # how many actually exist (before the cap) - lets the screen say so if `items` was truncated


# A person's status on one day. The first six are stored attendance statuses
# or are derived from leave/holidays; NOT_CHECKED_IN is only ever "today, and
# they haven't checked in yet" - on a past working day the same situation is
# ABSENT.
RollCallStatus = Literal["PRESENT", "LATE", "HALF_DAY", "ABSENT", "ON_LEAVE", "HOLIDAY", "NOT_CHECKED_IN"]


class RollCallEntry(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department: str
    designation: str
    status: RollCallStatus
    check_in: datetime | None
    check_out: datetime | None
    late_minutes: int
    working_minutes: int | None
    overtime_minutes: int = 0
    # A past day with a check-in but no check-out: someone needs to fix it.
    missed_check_out: bool = False
    # Minutes of approved permission (a few hours off) recorded for this person on this day, 0 if none.
    permission_minutes: int = 0
    # True when this person has a half-day leave on this day (they work the other half).
    half_day_leave: bool = False


class RollCallDepartment(BaseModel):
    id: int
    name: str


class RollCallOut(BaseModel):
    date: date
    day_off_reason: str | None
    summary: dict[str, int]
    departments: list[RollCallDepartment]
    items: list[RollCallEntry]
    page: int
    page_size: int
    total: int
    total_pages: int


class PermissionRecordIn(BaseModel):
    """A manager/HR entering a permission (a few hours off) for an employee who asked for it."""

    employee_id: int
    permission_date: date
    minutes: int = Field(ge=15)
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _tidy_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please write a short reason, for example: bank work, informed at 9:10")
        return value


class PermissionOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    permission_date: date
    minutes: int
    reason: str
    recorded_by_name: str
    recorded_late: bool
    created_at: datetime

    @classmethod
    def from_model(cls, permission) -> "PermissionOut":
        return cls(
            id=permission.id,
            employee_id=permission.employee_id,
            employee_name=permission.employee.full_name,
            employee_code=permission.employee.employee_code,
            permission_date=permission.permission_date,
            minutes=permission.minutes,
            reason=permission.reason,
            recorded_by_name=permission.recorded_by_name,
            recorded_late=permission.recorded_late,
            created_at=permission.created_at,
        )


class PermissionListOut(BaseModel):
    """One person's permissions for a month, with how many of the monthly allowance are used."""

    items: list[PermissionOut]
    used_this_month: int
    monthly_limit: int
    max_minutes: int
