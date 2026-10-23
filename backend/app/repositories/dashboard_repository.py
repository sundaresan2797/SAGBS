from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, EmployeeStatus, LeaveRequestStatus, TaskStatus
from app.models.leave import LeaveRequest
from app.models.task import Task


class DashboardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def total_employees(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Employee))
        return result.scalar_one()

    async def active_employees(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Employee).where(Employee.status == EmployeeStatus.ACTIVE)
        )
        return result.scalar_one()

    async def employees_on_leave(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Employee).where(Employee.status == EmployeeStatus.ON_LEAVE)
        )
        return result.scalar_one()

    async def new_joiners_since(self, since: date) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Employee).where(Employee.date_of_joining >= since)
        )
        return result.scalar_one()

    async def attendance_count_for_date(self, target_date: date, statuses: list[AttendanceStatus]) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Attendance)
            .where(Attendance.attendance_date == target_date, Attendance.status.in_(statuses))
        )
        return result.scalar_one()

    async def employees_on_approved_leave_for_date(self, target_date: date) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(LeaveRequest.employee_id)))
            .select_from(LeaveRequest)
            .where(
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.day_part.is_(None),  # a half-day leave is not "on leave": they work the other half
                LeaveRequest.start_date <= target_date,
                LeaveRequest.end_date >= target_date,
            )
        )
        return result.scalar_one()

    async def approved_leave_ranges(self, start: date, end: date) -> list[tuple[int, date, date]]:
        """Approved leave that overlaps start..end, as (employee_id, first day, last day)."""
        result = await self.session.execute(
            select(LeaveRequest.employee_id, LeaveRequest.start_date, LeaveRequest.end_date).where(
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.day_part.is_(None),
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def active_joining_dates(self) -> list[date]:
        result = await self.session.execute(
            select(Employee.date_of_joining).where(Employee.status == EmployeeStatus.ACTIVE)
        )
        return list(result.scalars().all())

    async def pending_leave_requests(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(LeaveRequest)
            .where(LeaveRequest.status == LeaveRequestStatus.PENDING)
        )
        return result.scalar_one()

    async def pending_tasks(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]))
        )
        return result.scalar_one()

    async def overdue_tasks(self, today: date) -> int:
        """Of the pending tasks, how many are already past their due date. A task with no due date
        is never counted as overdue - there is nothing for it to be late against."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]),
                Task.due_date.is_not(None),
                Task.due_date < today,
            )
        )
        return result.scalar_one()

    async def attendance_trend(self, days: int) -> list[dict]:
        start_date = date.today() - timedelta(days=days - 1)
        result = await self.session.execute(
            select(Attendance.attendance_date, Attendance.status, func.count())
            .where(Attendance.attendance_date >= start_date)
            .group_by(Attendance.attendance_date, Attendance.status)
        )
        rows = result.all()

        by_date: dict[date, dict[str, int]] = {}
        current = start_date
        while current <= date.today():
            by_date[current] = {"present": 0, "absent": 0, "late": 0, "on_leave": 0}
            current += timedelta(days=1)

        for attendance_date, status, count in rows:
            bucket = by_date.setdefault(attendance_date, {"present": 0, "absent": 0, "late": 0, "on_leave": 0})
            if status == AttendanceStatus.PRESENT:
                bucket["present"] += count
            elif status == AttendanceStatus.LATE:
                bucket["present"] += count
                bucket["late"] += count
            elif status == AttendanceStatus.HALF_DAY:
                bucket["present"] += count
            elif status == AttendanceStatus.ABSENT:
                bucket["absent"] += count
            elif status == AttendanceStatus.ON_LEAVE:
                bucket["on_leave"] += count

        return [
            {"date": d.isoformat(), **counts}
            for d, counts in sorted(by_date.items())
        ]

    async def leave_trend(self, months: int) -> list[dict]:
        # Group by start_date (a plain DATE) rather than created_at (a
        # TIMESTAMPTZ): date_trunc() on a timestamptz converts through the
        # session timezone before truncating, which can shift results into
        # the wrong month near zone/month boundaries. DATE columns have no
        # timezone to convert, so this is immune to that class of bug - and
        # it is also the more useful grouping (when leave falls, not when it
        # was requested).
        result = await self.session.execute(
            select(
                func.date_trunc("month", LeaveRequest.start_date).label("month"),
                LeaveRequest.status,
                func.count(),
            ).group_by("month", LeaveRequest.status)
        )
        rows = result.all()

        by_month: dict[str, dict[str, int]] = {}
        for month, status, count in rows:
            key = month.strftime("%Y-%m")
            bucket = by_month.setdefault(key, {"approved": 0, "pending": 0, "rejected": 0})
            if status == LeaveRequestStatus.APPROVED:
                bucket["approved"] += count
            elif status == LeaveRequestStatus.PENDING:
                bucket["pending"] += count
            elif status == LeaveRequestStatus.REJECTED:
                bucket["rejected"] += count

        sorted_months = sorted(by_month.items())[-months:]
        return [{"month": month, **counts} for month, counts in sorted_months]

    async def department_headcounts(self) -> list[dict]:
        result = await self.session.execute(
            select(Department.id, Department.name, func.count(Employee.id))
            .outerjoin(Employee, Employee.department_id == Department.id)
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )
        return [
            {"department_id": dept_id, "department_name": name, "employee_count": count}
            for dept_id, name, count in result.all()
        ]
