"""Which days are the company's days off.

Sunday is the weekly holiday, and any date in the holiday calendar is a
company holiday too - except "optional" holidays, which employees may choose
to take but which aren't a day off for everyone. Attendance, the roll call and
the dashboard all share this one rule so they can never disagree.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.holiday_repository import HolidayRepository

WEEKLY_OFF_WEEKDAYS = {6}  # date.weekday(): Monday=0 ... Sunday=6


async def day_off_reason(session: AsyncSession, target: date) -> str | None:
    """The reason `target` is a day off ("Diwali", "Sunday"), or None for a working day."""
    holiday = await HolidayRepository(session).get_by_date(target)
    if holiday is not None and not holiday.is_optional:
        return holiday.name
    if target.weekday() in WEEKLY_OFF_WEEKDAYS:
        return target.strftime("%A")
    return None
