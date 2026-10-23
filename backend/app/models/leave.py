from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import LeaveAccrualFrequency, LeaveRequestStatus


class LeaveType(Base, TimestampMixin):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_annual_days: Mapped[float] = mapped_column(Numeric(5, 1), default=0, nullable=False)
    accrual_frequency: Mapped[LeaveAccrualFrequency] = mapped_column(
        SAEnum(LeaveAccrualFrequency, name="leave_accrual_frequency", native_enum=True),
        default=LeaveAccrualFrequency.ANNUAL,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LeaveBalance(Base, TimestampMixin):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance_employee_type_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    allocated_days: Mapped[float] = mapped_column(Numeric(5, 1), default=0, nullable=False)
    used_days: Mapped[float] = mapped_column(Numeric(5, 1), default=0, nullable=False)

    leave_type: Mapped["LeaveType"] = relationship(lazy="selectin")

    @property
    def remaining_days(self) -> float:
        return float(self.allocated_days) - float(self.used_days)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    number_of_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))

    status: Mapped[LeaveRequestStatus] = mapped_column(
        SAEnum(LeaveRequestStatus, name="leave_request_status", native_enum=True),
        default=LeaveRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))

    # Half-day leave: one date, number_of_days 0.5, and which half. None means whole days.
    day_part: Mapped[str | None] = mapped_column(String(12))
    # Set when a manager/HR entered this leave for the employee (e.g. they phoned in), instead of the employee applying.
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recorded_by_name: Mapped[str | None] = mapped_column(String(150))
    # True when it was entered after the leave day had already started to pass (a past day).
    recorded_late: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    employee: Mapped["Employee"] = relationship(lazy="selectin")
    leave_type: Mapped["LeaveType"] = relationship(lazy="selectin")
