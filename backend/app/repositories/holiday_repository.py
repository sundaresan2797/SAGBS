from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday import Holiday


class HolidayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, holiday_id: int) -> Holiday | None:
        result = await self.session.execute(select(Holiday).where(Holiday.id == holiday_id))
        return result.scalar_one_or_none()

    async def get_by_date(self, holiday_date: date) -> Holiday | None:
        result = await self.session.execute(select(Holiday).where(Holiday.holiday_date == holiday_date))
        return result.scalar_one_or_none()

    async def list_between(self, start: date, end: date) -> list[Holiday]:
        result = await self.session.execute(
            select(Holiday)
            .where(Holiday.holiday_date >= start, Holiday.holiday_date <= end)
            .order_by(Holiday.holiday_date)
        )
        return list(result.scalars().all())

    async def list_all(self, year: int | None = None) -> list[Holiday]:
        query = select(Holiday).order_by(Holiday.holiday_date)
        if year is not None:
            query = query.where(
                Holiday.holiday_date >= date(year, 1, 1), Holiday.holiday_date <= date(year, 12, 31)
            )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def add(self, holiday: Holiday) -> None:
        self.session.add(holiday)

    async def delete(self, holiday: Holiday) -> None:
        await self.session.delete(holiday)
