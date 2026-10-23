from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ExpenseClaimCategory, ExpenseClaimStatus, SalaryPaymentStatus

# The largest value a numeric(12, 2) column can hold; anything bigger would be a database error.
MAX_MONEY = 9_999_999_999.99


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------


class SalaryRecordCreate(BaseModel):
    employee_id: int
    basic_pay: float = Field(ge=0, le=MAX_MONEY)
    allowances: float = Field(default=0, ge=0, le=MAX_MONEY)
    deductions: float = Field(default=0, ge=0, le=MAX_MONEY)
    effective_from: date

    @model_validator(mode="after")
    def deductions_within_earnings(self) -> "SalaryRecordCreate":
        if self.deductions > self.basic_pay + self.allowances:
            raise ValueError("Deductions can't be more than basic pay plus allowances, or the net pay would be below zero")
        return self


class SalaryRecordOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    basic_pay: float
    allowances: float
    deductions: float
    net_pay: float
    effective_from: date

    @classmethod
    def from_model(cls, record) -> "SalaryRecordOut":
        return cls(
            id=record.id,
            employee_id=record.employee_id,
            employee_name=record.employee.full_name,
            employee_code=record.employee.employee_code,
            basic_pay=float(record.basic_pay),
            allowances=float(record.allowances),
            deductions=float(record.deductions),
            net_pay=record.net_pay,
            effective_from=record.effective_from,
        )


class PayrollDirectoryEntry(BaseModel):
    """Minimal employee picker for the salary/payroll workflow.

    Deliberately excludes phone, address, and other HR-only fields - the
    Accountant role doesn't hold employee:read, so this is the one place it
    can see just enough (name, code, role, department, designation) to
    confidently pick the right person to pay.
    """

    id: int
    employee_code: str
    full_name: str
    role: str
    department: str
    designation: str

    @classmethod
    def from_model(cls, employee) -> "PayrollDirectoryEntry":
        return cls(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            role=employee.user.role.name,
            department=employee.department.name,
            designation=employee.designation.name,
        )


class RunPayrollRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class UnpaidEarlierOut(BaseModel):
    count: int
    total_amount: float


class SalaryPaymentOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    year: int
    month: int
    amount: float
    status: SalaryPaymentStatus
    paid_date: date | None
    # The attendance breakdown behind `amount` - absent only for payments made before pay was
    # attendance-based, when everyone was simply paid their full salary.
    total_days: int | None = None
    present_days: int | None = None
    late_days: int | None = None
    half_days: int | None = None
    half_leave_days: int | None = None
    paid_leave_days: int | None = None
    unpaid_leave_days: int | None = None
    absent_days: int | None = None
    days_off_days: int | None = None
    payable_days: float | None = None
    cut_days: float | None = None

    @classmethod
    def from_model(cls, payment) -> "SalaryPaymentOut":
        return cls(
            id=payment.id,
            employee_id=payment.employee_id,
            employee_name=payment.employee.full_name,
            employee_code=payment.employee.employee_code,
            year=payment.year,
            month=payment.month,
            amount=float(payment.amount),
            status=payment.status,
            paid_date=payment.paid_date,
            total_days=payment.total_days,
            present_days=payment.present_days,
            late_days=payment.late_days,
            half_days=payment.half_days,
            half_leave_days=payment.half_leave_days,
            paid_leave_days=payment.paid_leave_days,
            unpaid_leave_days=payment.unpaid_leave_days,
            absent_days=payment.absent_days,
            days_off_days=payment.days_off_days,
            payable_days=float(payment.payable_days) if payment.payable_days is not None else None,
            cut_days=float(payment.cut_days) if payment.cut_days is not None else None,
        )


# ---------------------------------------------------------------------------
# Expense claims (personal reimbursement)
# ---------------------------------------------------------------------------


class ExpenseClaimCreate(BaseModel):
    category: ExpenseClaimCategory
    amount: float = Field(gt=0, le=MAX_MONEY)
    description: str | None = Field(default=None, max_length=500)


class ExpenseClaimDecision(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=500)


class ExpenseClaimOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    category: ExpenseClaimCategory
    amount: float
    description: str | None
    status: ExpenseClaimStatus
    rejection_reason: str | None
    paid_date: date | None
    created_at: datetime

    @classmethod
    def from_model(cls, claim) -> "ExpenseClaimOut":
        return cls(
            id=claim.id,
            employee_id=claim.employee_id,
            employee_name=claim.employee.full_name,
            employee_code=claim.employee.employee_code,
            category=claim.category,
            amount=float(claim.amount),
            description=claim.description,
            status=claim.status,
            rejection_reason=claim.rejection_reason,
            paid_date=claim.paid_date,
            created_at=claim.created_at,
        )



# ---------------------------------------------------------------------------
# Monthly attendance summary (paid days per person) - the same numbers Run Payroll pays with
# ---------------------------------------------------------------------------


class AttendanceSummaryRow(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    total_days: int  # days in the month
    working_days: int  # of those, the days this person is expected to work (no Sundays, holidays, or days before joining)
    present: int
    late: int
    half_day: int
    half_leave: int = 0
    paid_leave: int
    unpaid_leave: int
    absent: int
    days_off: int  # Sundays and company holidays (paid)
    before_joining: int
    open_days: int  # days of the month that have not happened yet
    payable_days: float
    cut_days: float
    # The full monthly take-home: from that month's payslip if payroll already ran (so a later raise does not
    # rewrite history), otherwise from the current salary structure.
    monthly_salary: float
    pay_for_month: float | None  # pay by attendance; None until the month has ended
    # What Run Payroll actually created for the month (the attendance-based amount; older payslips may differ).
    payslip_id: int | None
    payslip_amount: float | None
    payslip_status: SalaryPaymentStatus | None
    payslip_paid_date: date | None
    difference: float | None  # payslip amount minus pay by attendance; None if either is missing
    missed_check_outs: int
    pending_leave_requests: int


class MonthCount(BaseModel):
    year: int
    month: int
    count: int


class AttendanceSummaryChecklist(BaseModel):
    """Things worth clearing before paying. Counts only - they are warnings, never locks."""

    missed_check_outs: int
    pending_leave_requests: int
    employees_without_salary: int
    absent_days: int
    # Missed check-outs still open in OTHER months (newest first), so nothing hides behind the month being viewed.
    missed_check_outs_in_other_months: list[MonthCount]


class AttendanceSummaryOut(BaseModel):
    year: int
    month: int
    total_days: int
    month_ended: bool
    items: list[AttendanceSummaryRow]
    checklist: AttendanceSummaryChecklist
    total_monthly_salary: float
    total_pay: float | None  # by attendance, once the month has ended
    total_on_payslips: float | None  # None if no payslips exist for the month
    total_difference: float | None  # over people who have both numbers
