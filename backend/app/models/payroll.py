from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import (
    ExpenseClaimCategory,
    ExpenseClaimStatus,
    SalaryPaymentStatus,
)

# All money columns use Numeric(12, 2), never Float - exact decimal
# arithmetic matters for anything the Accountant reports as a real amount.


class SalaryRecord(Base, TimestampMixin):
    """An employee's current salary structure. One active row per employee -
    a raise updates this row rather than creating a new one, keeping "what
    do they currently earn" a single lookup.
    """

    __tablename__ = "salary_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    # No longer unique: this is a HISTORY of every salary this employee has had, one row per change,
    # each with its own effective_from. "Current" is whichever row has the latest effective_from
    # that has already arrived (see SalaryRecordRepository.get_current / list_current).
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    basic_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    allowances: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    employee: Mapped["Employee"] = relationship(lazy="selectin")

    @property
    def net_pay(self) -> float:
        return float(self.basic_pay) + float(self.allowances) - float(self.deductions)


class SalaryPayment(Base, TimestampMixin):
    """One month's payroll disbursement record for one employee."""

    __tablename__ = "salary_payments"
    __table_args__ = (UniqueConstraint("employee_id", "year", "month", name="uq_salary_payment_employee_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # Snapshotted from the employee's SalaryRecord at the moment payroll ran,
    # so a payslip always shows what was actually earned/deducted that
    # month - not whatever the salary structure happens to say today after
    # a later raise or correction. Nullable only because rows created before
    # this column existed have no snapshot to backfill.
    basic_pay: Mapped[float | None] = mapped_column(Numeric(12, 2))
    allowances: Mapped[float | None] = mapped_column(Numeric(12, 2))
    deductions: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[SalaryPaymentStatus] = mapped_column(
        SAEnum(SalaryPaymentStatus, name="salary_payment_status", native_enum=True),
        default=SalaryPaymentStatus.PENDING,
        nullable=False,
    )
    paid_date: Mapped[date | None] = mapped_column(Date)

    # The attendance breakdown behind `amount`, snapshotted at the moment payroll ran (nullable:
    # older payments, made before pay was attendance-based, simply have none of these - their
    # `amount` was the full salary, full stop). Once saved these never change, even if the
    # employee's attendance is corrected afterwards - a paid month stays paid at what it paid.
    total_days: Mapped[int | None] = mapped_column(Integer)
    present_days: Mapped[int | None] = mapped_column(Integer)
    late_days: Mapped[int | None] = mapped_column(Integer)
    half_days: Mapped[int | None] = mapped_column(Integer)
    half_leave_days: Mapped[int | None] = mapped_column(Integer)  # days with a half-day leave (see attendance_summary)
    paid_leave_days: Mapped[int | None] = mapped_column(Integer)
    unpaid_leave_days: Mapped[int | None] = mapped_column(Integer)
    absent_days: Mapped[int | None] = mapped_column(Integer)
    days_off_days: Mapped[int | None] = mapped_column(Integer)
    payable_days: Mapped[float | None] = mapped_column(Numeric(5, 1))
    cut_days: Mapped[float | None] = mapped_column(Numeric(5, 1))

    employee: Mapped["Employee"] = relationship(lazy="selectin")


class ExpenseClaim(Base, TimestampMixin):
    """A personal reimbursement claim submitted by an employee - travel,
    food, materials, etc.
    """

    __tablename__ = "expense_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[ExpenseClaimCategory] = mapped_column(
        SAEnum(ExpenseClaimCategory, name="expense_claim_category", native_enum=True), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ExpenseClaimStatus] = mapped_column(
        SAEnum(ExpenseClaimStatus, name="expense_claim_status", native_enum=True),
        default=ExpenseClaimStatus.PENDING,
        nullable=False,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_date: Mapped[date | None] = mapped_column(Date)

    employee: Mapped["Employee"] = relationship(lazy="selectin")
