from datetime import date

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.enums import AuditAction
from app.models.holiday import Holiday
from app.models.user import User
from app.repositories.holiday_repository import HolidayRepository
from app.repositories.payroll_repository import SalaryPaymentRepository
from app.schemas.holiday import HolidayCreate, HolidayOut, HolidayUpdate
from app.services.audit_service import log_action
from app.services.payslip_service import MONTH_NAMES


async def _ensure_payroll_not_run_for(session: AsyncSession, day: date) -> None:
    """Holidays decide how each day counts in pay. Once payroll has been run for a month its payslips are
    fixed, so changing that month's holidays would make the Attendance Summary disagree with them."""
    if await SalaryPaymentRepository(session).has_payments(day.year, day.month):
        raise BusinessRuleError(
            f"Payroll for {MONTH_NAMES[day.month - 1]} {day.year} has already been run, so its holidays can't be changed.",
            error_code="HOLIDAY_MONTH_PAYROLL_RUN",
        )


async def list_holidays(session: AsyncSession, year: int | None) -> list[HolidayOut]:
    repo = HolidayRepository(session)
    return [HolidayOut.model_validate(h) for h in await repo.list_all(year)]


async def create_holiday(
    session: AsyncSession, payload: HolidayCreate, current_user: User, request: Request | None = None
) -> HolidayOut:
    repo = HolidayRepository(session)
    await _ensure_payroll_not_run_for(session, payload.holiday_date)
    if await repo.get_by_date(payload.holiday_date) is not None:
        raise ConflictError(
            f"A holiday is already defined for {payload.holiday_date}.", error_code="HOLIDAY_DATE_EXISTS"
        )

    holiday = Holiday(
        name=payload.name,
        holiday_date=payload.holiday_date,
        description=payload.description,
        is_optional=payload.is_optional,
    )
    repo.add(holiday)
    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_HOLIDAY,
        entity_type="Holiday",
        entity_id=holiday.id,
        description=f"Created holiday '{holiday.name}' on {holiday.holiday_date}",
        request=request,
    )
    await session.commit()
    return HolidayOut.model_validate(holiday)


async def update_holiday(
    session: AsyncSession, holiday_id: int, payload: HolidayUpdate, current_user: User, request: Request | None = None
) -> HolidayOut:
    repo = HolidayRepository(session)
    holiday = await repo.get_by_id(holiday_id)
    if holiday is None:
        raise NotFoundError("Holiday not found.", error_code="HOLIDAY_NOT_FOUND")

    date_changes = payload.holiday_date is not None and payload.holiday_date != holiday.holiday_date
    optional_changes = payload.is_optional is not None and payload.is_optional != holiday.is_optional
    if date_changes or optional_changes:
        await _ensure_payroll_not_run_for(session, holiday.holiday_date)
    if date_changes:
        await _ensure_payroll_not_run_for(session, payload.holiday_date)
    if payload.holiday_date is not None and payload.holiday_date != holiday.holiday_date:
        if await repo.get_by_date(payload.holiday_date) is not None:
            raise ConflictError(
                f"A holiday is already defined for {payload.holiday_date}.", error_code="HOLIDAY_DATE_EXISTS"
            )
        holiday.holiday_date = payload.holiday_date

    if payload.name is not None:
        holiday.name = payload.name
    if payload.description is not None:
        holiday.description = payload.description
    if payload.is_optional is not None:
        holiday.is_optional = payload.is_optional

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_HOLIDAY,
        entity_type="Holiday",
        entity_id=holiday.id,
        description=f"Updated holiday '{holiday.name}'",
        request=request,
    )
    await session.commit()
    return HolidayOut.model_validate(holiday)


async def delete_holiday(
    session: AsyncSession, holiday_id: int, current_user: User, request: Request | None = None
) -> None:
    repo = HolidayRepository(session)
    holiday = await repo.get_by_id(holiday_id)
    if holiday is None:
        raise NotFoundError("Holiday not found.", error_code="HOLIDAY_NOT_FOUND")
    await _ensure_payroll_not_run_for(session, holiday.holiday_date)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.DELETE_HOLIDAY,
        entity_type="Holiday",
        entity_id=holiday.id,
        description=f"Deleted holiday '{holiday.name}'",
        request=request,
    )
    await repo.delete(holiday)
    await session.commit()
