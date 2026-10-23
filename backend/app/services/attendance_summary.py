"""Turn one person's month of attendance into paid and cut days.

Pure functions of the data passed in (no database), so the rules can be read
and tested on their own. The day-by-day rule mirrors the calendar screens and
the roll call: a saved attendance record always wins; otherwise a coming day
is "open", a day before joining is not counted, Sundays and company holidays
are paid days off, approved leave is paid or cut by its leave type, and
anything else is absent. A day with a half-day leave counts half for the leave (paid or cut by its leave
type) and half for the half worked (paid if they checked in, otherwise cut as absent).

Pay = monthly take-home / days in the month x payable days (Sundays and
holidays are paid; absent, unpaid leave and half of each half day are cut).
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import AttendanceStatus
from app.services.working_days import WEEKLY_OFF_WEEKDAYS


@dataclass
class MonthCounts:
    total_days: int
    present: int = 0
    late: int = 0
    half_day: int = 0
    paid_leave: int = 0
    unpaid_leave: int = 0
    absent: int = 0
    days_off: int = 0  # Sundays and non-optional holidays - paid
    before_joining: int = 0  # not counted at all
    open_days: int = 0  # still to come (or today, not decided yet)
    # Days the person is expected to work in the month: not a Sunday or company holiday, and not before joining.
    # A calendar fact - independent of attendance and of today's date.
    working_days: int = 0
    # Days with a half-day leave, and how many days of pay they add / take off (each such day adds up to exactly 1).
    half_leave_days: int = 0
    half_leave_payable: float = 0.0
    half_leave_cut: float = 0.0

    @property
    def payable_days(self) -> float:
        return self.days_off + self.present + self.late + self.paid_leave + 0.5 * self.half_day + self.half_leave_payable

    @property
    def cut_days(self) -> float:
        return self.unpaid_leave + self.absent + 0.5 * self.half_day + self.half_leave_cut


def count_month(
    year: int,
    month: int,
    *,
    records: dict[date, AttendanceStatus],
    off_dates: set[date],
    leave_days: dict[date, bool],
    joining: date,
    today: date,
    half_leave_days: dict[date, bool] | None = None,
) -> MonthCounts:
    """`records`: saved status per date. `off_dates`: non-optional holidays.
    `leave_days`: approved whole-day leave date -> is it paid leave.
    `half_leave_days`: approved half-day leave date -> is it paid leave."""
    half_leave_days = half_leave_days or {}
    total = calendar.monthrange(year, month)[1]
    counts = MonthCounts(total_days=total)
    for day_number in range(1, total + 1):
        day = date(year, month, day_number)
        if day >= joining and day not in off_dates and day.weekday() not in WEEKLY_OFF_WEEKDAYS:
            counts.working_days += 1
        status = records.get(day)
        is_working_day = day >= joining and day not in off_dates and day.weekday() not in WEEKLY_OFF_WEEKDAYS
        if day in half_leave_days and is_working_day:
            if status is None and day >= today:
                counts.open_days += 1  # today or later: the other half may still be worked
                continue
            worked = status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY)
            leave_paid = half_leave_days[day]
            counts.half_leave_days += 1
            counts.half_leave_payable += (0.5 if leave_paid else 0.0) + (0.5 if worked else 0.0)
            counts.half_leave_cut += (0.0 if leave_paid else 0.5) + (0.0 if worked else 0.5)
            continue
        if status is not None:
            if status == AttendanceStatus.PRESENT:
                counts.present += 1
            elif status == AttendanceStatus.LATE:
                counts.late += 1
            elif status == AttendanceStatus.HALF_DAY:
                counts.half_day += 1
            elif status == AttendanceStatus.ABSENT:
                counts.absent += 1
            elif status == AttendanceStatus.HOLIDAY:
                counts.days_off += 1
            else:  # ON_LEAVE saved by hand: paid unless the approved leave says otherwise
                counts.paid_leave += 1 if leave_days.get(day, True) else 0
                counts.unpaid_leave += 0 if leave_days.get(day, True) else 1
        elif day > today:
            counts.open_days += 1
        elif day < joining:
            counts.before_joining += 1
        elif day in off_dates or day.weekday() in WEEKLY_OFF_WEEKDAYS:
            counts.days_off += 1
        elif day in leave_days:
            counts.paid_leave += 1 if leave_days[day] else 0
            counts.unpaid_leave += 0 if leave_days[day] else 1
        elif day == today:
            counts.open_days += 1  # today is not over: they may still check in
        else:
            counts.absent += 1
    return counts


def pay_for_month(take_home: float, counts: MonthCounts) -> Decimal | None:
    """The month's pay in whole rupees, or None while days of the month are still open."""
    if counts.open_days > 0:
        return None
    per_day = Decimal(str(take_home)) / counts.total_days
    return (per_day * Decimal(str(counts.payable_days))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
