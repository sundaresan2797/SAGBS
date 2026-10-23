from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance, ShortPermission
from app.models.employee import Employee
from app.models.enums import LeaveRequestStatus
from app.models.leave import LeaveRequest


@dataclass
class AttendanceFilters:
    employee_id: int | None = None
    employee_ids: list[int] | None = None
    date_from: date | None = None
    date_to: date | None = None


class AttendanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_employee_and_date(self, employee_id: int, attendance_date: date) -> Attendance | None:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.employee_id == employee_id, Attendance.attendance_date == attendance_date
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, attendance_id: int) -> Attendance | None:
        result = await self.session.execute(
            select(Attendance).options(selectinload(Attendance.employee)).where(Attendance.id == attendance_id)
        )
        return result.scalar_one_or_none()

    async def list_for_employees_between(
        self, employee_ids: list[int], date_from: date, date_to: date
    ) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.employee_id.in_(employee_ids),
                Attendance.attendance_date >= date_from,
                Attendance.attendance_date <= date_to,
            )
        )
        return list(result.scalars().all())

    async def missed_check_outs_by_month(
        self, employee_ids: list[int], before: date, since: date, skip_from: date, skip_to: date
    ) -> list[tuple[int, int, int]]:
        """(year, month, count) of past days with a check-in and no check-out, apart from one month (skip_from..skip_to)."""
        year = func.extract("year", Attendance.attendance_date)
        month = func.extract("month", Attendance.attendance_date)
        result = await self.session.execute(
            select(year, month, func.count())
            .where(
                Attendance.employee_id.in_(employee_ids),
                Attendance.attendance_date < before,
                Attendance.attendance_date >= since,
                Attendance.check_in.is_not(None),
                Attendance.check_out.is_(None),
                ~Attendance.attendance_date.between(skip_from, skip_to),
            )
            .group_by(year, month)
            .order_by(year.desc(), month.desc())
        )
        return [(int(row[0]), int(row[1]), int(row[2])) for row in result.all()]

    def _missed_check_outs_filter(
        self, query, before: date, since: date, employee_ids: list[int] | None, exclude_employee_id: int | None
    ):
        query = query.where(
            Attendance.attendance_date < before,
            Attendance.attendance_date >= since,
            Attendance.check_in.is_not(None),
            Attendance.check_out.is_(None),
        )
        if employee_ids is not None:
            query = query.where(Attendance.employee_id.in_(employee_ids))
        if exclude_employee_id is not None:
            query = query.where(Attendance.employee_id != exclude_employee_id)
        return query

    async def list_missed_check_outs(
        self,
        before: date,
        since: date,
        employee_ids: list[int] | None,
        limit: int,
        exclude_employee_id: int | None = None,
    ) -> list[Attendance]:
        """Past days (before `before`, not older than `since`) that have a check-in but no check-out."""
        query = self._missed_check_outs_filter(
            select(Attendance).options(selectinload(Attendance.employee)), before, since, employee_ids, exclude_employee_id
        )
        result = await self.session.execute(query.order_by(Attendance.attendance_date.desc()).limit(limit))
        return list(result.scalars().all())

    async def count_missed_check_outs(
        self, before: date, since: date, employee_ids: list[int] | None, exclude_employee_id: int | None = None
    ) -> int:
        """How many missed check-outs actually exist, ignoring the `limit` list_missed_check_outs caps at -
        so the screen can say "showing the most recent N of TOTAL" instead of silently truncating."""
        query = self._missed_check_outs_filter(
            select(func.count()).select_from(Attendance), before, since, employee_ids, exclude_employee_id
        )
        return (await self.session.execute(query)).scalar_one()

    async def overtime_totals(self, date_from: date, date_to: date) -> list[tuple[int, str, str, int]]:
        """(employee_id, code, name, total overtime minutes) between two dates, for people who have some."""
        total = func.sum(Attendance.overtime_minutes)
        result = await self.session.execute(
            select(Employee.id, Employee.employee_code, Employee.first_name, Employee.last_name, total)
            .join(Employee, Employee.id == Attendance.employee_id)
            .where(Attendance.attendance_date >= date_from, Attendance.attendance_date <= date_to)
            .group_by(Employee.id, Employee.employee_code, Employee.first_name, Employee.last_name)
            .having(total > 0)
            .order_by(Employee.first_name, Employee.last_name)
        )
        return [(row[0], row[1], f"{row[2]} {row[3]}".strip(), int(row[4])) for row in result.all()]

    def _apply_filters(self, query, filters: AttendanceFilters):
        if filters.employee_id is not None:
            query = query.where(Attendance.employee_id == filters.employee_id)
        if filters.employee_ids is not None:
            query = query.where(Attendance.employee_id.in_(filters.employee_ids))
        if filters.date_from is not None:
            query = query.where(Attendance.attendance_date >= filters.date_from)
        if filters.date_to is not None:
            query = query.where(Attendance.attendance_date <= filters.date_to)
        return query

    async def list_paginated(
        self, filters: AttendanceFilters, page: int, page_size: int
    ) -> tuple[list[Attendance], int]:
        base_query = self._apply_filters(
            select(Attendance).options(selectinload(Attendance.employee)), filters
        )
        count_query = self._apply_filters(select(func.count()).select_from(Attendance), filters)
        total = (await self.session.execute(count_query)).scalar_one()

        base_query = (
            base_query.order_by(Attendance.attendance_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    async def map_for_date(self, attendance_date: date) -> dict[int, Attendance]:
        result = await self.session.execute(select(Attendance).where(Attendance.attendance_date == attendance_date))
        return {row.employee_id: row for row in result.scalars().all()}

    async def employee_ids_on_approved_leave(self, target_date: date) -> set[int]:
        """Who is off for the WHOLE day. A half-day leave is left out: that person still works the other half."""
        result = await self.session.execute(
            select(LeaveRequest.employee_id).where(
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.day_part.is_(None),
                LeaveRequest.start_date <= target_date,
                LeaveRequest.end_date >= target_date,
            )
        )
        return set(result.scalars().all())

    def add(self, attendance: Attendance) -> None:
        self.session.add(attendance)

    async def delete(self, attendance: Attendance) -> None:
        await self.session.delete(attendance)


class ShortPermissionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, permission_id: int) -> ShortPermission | None:
        result = await self.session.execute(select(ShortPermission).where(ShortPermission.id == permission_id))
        return result.scalar_one_or_none()

    async def get_for_day(self, employee_id: int, day: date) -> ShortPermission | None:
        result = await self.session.execute(
            select(ShortPermission).where(ShortPermission.employee_id == employee_id, ShortPermission.permission_date == day)
        )
        return result.scalar_one_or_none()

    async def minutes_for_day(self, employee_id: int, day: date) -> int:
        permission = await self.get_for_day(employee_id, day)
        return permission.minutes if permission is not None else 0

    async def minutes_by_employee_for_day(self, day: date) -> dict[int, int]:
        result = await self.session.execute(
            select(ShortPermission.employee_id, ShortPermission.minutes).where(ShortPermission.permission_date == day)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def list_for_month(self, employee_id: int, year: int, month: int) -> list[ShortPermission]:
        first = date(year, month, 1)
        last = date(year + (month == 12), month % 12 + 1, 1)
        result = await self.session.execute(
            select(ShortPermission)
            .where(
                ShortPermission.employee_id == employee_id,
                ShortPermission.permission_date >= first,
                ShortPermission.permission_date < last,
            )
            .order_by(ShortPermission.permission_date)
        )
        return list(result.scalars().all())

    async def has_between(self, employee_id: int, start: date, end: date) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(ShortPermission)
            .where(
                ShortPermission.employee_id == employee_id,
                ShortPermission.permission_date >= start,
                ShortPermission.permission_date <= end,
            )
        )
        return result.scalar_one() > 0

    def add(self, permission: ShortPermission) -> None:
        self.session.add(permission)

    async def delete(self, permission: ShortPermission) -> None:
        await self.session.delete(permission)
