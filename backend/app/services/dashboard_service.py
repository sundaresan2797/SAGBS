from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import CacheKeys, CacheTTL, redis_service
from app.models.enums import AttendanceStatus
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import AttendanceTrendPoint, DashboardSummary, DepartmentHeadcount, LeaveTrendPoint
from app.repositories.holiday_repository import HolidayRepository
from app.services.working_days import WEEKLY_OFF_WEEKDAYS, day_off_reason

PRESENT_LIKE_STATUSES = [AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY]


async def get_summary(session: AsyncSession) -> DashboardSummary:
    cached = await redis_service.get(CacheKeys.DASHBOARD_SUMMARY)
    if cached is not None:
        return DashboardSummary.model_validate(cached)

    repo = DashboardRepository(session)
    today = date.today()
    month_start = today.replace(day=1)

    total_employees = await repo.total_employees()
    active_employees = await repo.active_employees()
    present_today = await repo.attendance_count_for_date(today, PRESENT_LIKE_STATUSES)
    on_leave_today = await repo.employees_on_approved_leave_for_date(today)
    # On a Sunday or holiday nobody is expected in, so nobody is absent.
    if await day_off_reason(session, today) is not None:
        absent_today = 0
    else:
        absent_today = max(0, active_employees - present_today - on_leave_today)

    summary = DashboardSummary(
        total_employees=total_employees,
        active_employees=active_employees,
        employees_on_leave=on_leave_today,
        new_joiners_this_month=await repo.new_joiners_since(month_start),
        present_today=present_today,
        absent_today=absent_today,
        pending_leave_requests=await repo.pending_leave_requests(),
        pending_tasks=await repo.pending_tasks(),
        overdue_tasks=await repo.overdue_tasks(today),
    )

    await redis_service.set(CacheKeys.DASHBOARD_SUMMARY, summary.model_dump(mode="json"), CacheTTL.DASHBOARD)
    return summary


async def _fill_absent_and_leave(
    session: AsyncSession, repo: DashboardRepository, points: list[AttendanceTrendPoint]
) -> None:
    """Absence and leave are never saved as attendance rows - they are the days with no row. So for each
    working day: on leave = people on approved leave that day, absent = everyone who had joined by then,
    minus those present, minus those on leave. Sundays and holidays have nobody absent or on leave."""
    if not points:
        return
    first, last = date.fromisoformat(points[0].date), date.fromisoformat(points[-1].date)
    leave_ranges = await repo.approved_leave_ranges(first, last)
    joining_dates = await repo.active_joining_dates()
    off_dates = {
        h.holiday_date for h in await HolidayRepository(session).list_between(first, last) if not h.is_optional
    }
    for point in points:
        day = date.fromisoformat(point.date)
        if day in off_dates or day.weekday() in WEEKLY_OFF_WEEKDAYS:
            point.absent = 0
            point.on_leave = 0
            continue
        point.on_leave = len({employee_id for employee_id, start, end in leave_ranges if start <= day <= end})
        expected = sum(1 for joined in joining_dates if joined <= day)
        point.absent = max(0, expected - point.present - point.on_leave)


async def get_attendance_trend(session: AsyncSession, days: int = 14) -> list[AttendanceTrendPoint]:
    cache_key = f"{CacheKeys.DASHBOARD_ATTENDANCE}:{days}"
    cached = await redis_service.get(cache_key)
    if cached is not None:
        return [AttendanceTrendPoint.model_validate(item) for item in cached]

    repo = DashboardRepository(session)
    points = [AttendanceTrendPoint.model_validate(p) for p in await repo.attendance_trend(days)]
    await _fill_absent_and_leave(session, repo, points)

    await redis_service.set(cache_key, [p.model_dump(mode="json") for p in points], CacheTTL.DASHBOARD)
    return points


async def get_leave_trend(session: AsyncSession, months: int = 6) -> list[LeaveTrendPoint]:
    cache_key = f"{CacheKeys.DASHBOARD_LEAVE}:{months}"
    cached = await redis_service.get(cache_key)
    if cached is not None:
        return [LeaveTrendPoint.model_validate(item) for item in cached]

    repo = DashboardRepository(session)
    points = [LeaveTrendPoint.model_validate(p) for p in await repo.leave_trend(months)]

    await redis_service.set(cache_key, [p.model_dump(mode="json") for p in points], CacheTTL.DASHBOARD)
    return points


async def get_department_headcounts(session: AsyncSession) -> list[DepartmentHeadcount]:
    cached = await redis_service.get(CacheKeys.DASHBOARD_DEPARTMENTS)
    if cached is not None:
        return [DepartmentHeadcount.model_validate(item) for item in cached]

    repo = DashboardRepository(session)
    headcounts = [DepartmentHeadcount.model_validate(d) for d in await repo.department_headcounts()]

    await redis_service.set(
        CacheKeys.DASHBOARD_DEPARTMENTS, [h.model_dump(mode="json") for h in headcounts], CacheTTL.DASHBOARD
    )
    return headcounts
