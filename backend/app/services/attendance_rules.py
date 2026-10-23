"""The company's attendance policy, in one place.

Everything here is a pure function of the clock time and the settings, so the
rules can be read and tested without a database. Times are minutes since
midnight in the company's timezone.

- On time: checking in up to `late_grace_minutes` after the workday start.
- Late: checking in after that. Late minutes are counted from the start time
  itself (start 9:00, in at 9:25 -> 25 minutes late).
- Half day: checking in after the half-day cut-off, OR working less than the
  full-day minimum. Payroll does not read attendance, so this is a label for
  screens and reports.
- Permission: a few approved hours off on that day. Every rule below takes `excused_minutes` (0 when there
  is no permission) and moves the line by that much - the late line, the half-day cut-off and the
  full-day minimum - so the person is never marked late or half day for time they were allowed to miss.
- Lunch: the part of the company's lunch break the person was clocked in for is removed from their working
  minutes automatically (see `lunch_break_minutes_within`) - there is no separate punch for it.
"""

from datetime import datetime, timedelta

from app.config import settings
from app.models.enums import AttendanceStatus


def _minutes_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def workday_start_minutes() -> int:
    return settings.workday_start_hour * 60 + settings.workday_start_minute


def late_after_minutes() -> int:
    return workday_start_minutes() + settings.late_grace_minutes


def half_day_cutoff_minutes() -> int:
    return settings.half_day_checkin_after_hour * 60 + settings.half_day_checkin_after_minute


def late_minutes_for(check_in_local: datetime, excused_minutes: int = 0) -> int:
    """0 while inside the grace period, otherwise minutes since the (excused-adjusted) workday start."""
    minutes = _minutes_of_day(check_in_local)
    if minutes <= late_after_minutes() + excused_minutes:
        return 0
    return minutes - workday_start_minutes() - excused_minutes


def checked_in_after_cutoff(check_in_local: datetime, excused_minutes: int = 0) -> bool:
    return _minutes_of_day(check_in_local) > half_day_cutoff_minutes() + excused_minutes


def status_at_check_in(check_in_local: datetime, excused_minutes: int = 0) -> AttendanceStatus:
    if checked_in_after_cutoff(check_in_local, excused_minutes):
        return AttendanceStatus.HALF_DAY
    return AttendanceStatus.LATE if late_minutes_for(check_in_local, excused_minutes) > 0 else AttendanceStatus.PRESENT


def status_at_check_out(check_in_local: datetime, working_minutes: int, excused_minutes: int = 0) -> AttendanceStatus:
    if (
        checked_in_after_cutoff(check_in_local, excused_minutes)
        or working_minutes < settings.full_day_minimum_minutes - excused_minutes
    ):
        return AttendanceStatus.HALF_DAY
    return AttendanceStatus.LATE if late_minutes_for(check_in_local, excused_minutes) > 0 else AttendanceStatus.PRESENT


def lunch_break_minutes_within(check_in_local: datetime, check_out_local: datetime) -> int:
    """How much of the company's lunch break falls inside this check-in to check-out span - the part of the
    break the person was actually clocked in for, so it comes off their paid working time (nobody punches
    out for lunch, so this is the only way it is ever accounted for). Someone who left before lunch, or
    arrived after it, has none of it deducted; someone who left partway through it loses only the part they
    were there for.
    """
    if settings.lunch_break_minutes <= 0:
        return 0
    lunch_start = check_in_local.replace(
        hour=settings.lunch_start_hour, minute=settings.lunch_start_minute, second=0, microsecond=0
    )
    lunch_end = lunch_start + timedelta(minutes=settings.lunch_break_minutes)
    overlap_start = max(check_in_local, lunch_start)
    overlap_end = min(check_out_local, lunch_end)
    return max(0, int((overlap_end - overlap_start).total_seconds() // 60))


def overtime_minutes_for(working_minutes: int) -> int:
    return max(0, working_minutes - settings.standard_shift_minutes)
