from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import AttendanceStatus


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    working_minutes: Mapped[int | None] = mapped_column(Integer)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, name="attendance_status", native_enum=True), nullable=False
    )

    # Set when someone else fixed a missed check-out afterwards (see attendance_service.fix_check_out).
    corrected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    corrected_by_name: Mapped[str | None] = mapped_column(String(150))
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correction_reason: Mapped[str | None] = mapped_column(String(255))

    employee: Mapped["Employee"] = relationship(lazy="selectin")


class ShortPermission(Base, TimestampMixin):
    """An approved absence of a few hours on one day ("permission"). Paid, and it excuses that many minutes of
    lateness / short hours on the day (see attendance_rules). Always entered by a manager/HR/Founder/Admin."""

    __tablename__ = "short_permissions"
    __table_args__ = (UniqueConstraint("employee_id", "permission_date", name="uq_short_permission_employee_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recorded_by_name: Mapped[str] = mapped_column(String(150), nullable=False)
    recorded_late: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    employee: Mapped["Employee"] = relationship(lazy="selectin")
