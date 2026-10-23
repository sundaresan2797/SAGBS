from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.enums import ExpenseClaimStatus
from app.models.user import User
from app.schemas.common import PaginatedData, SuccessResponse
from app.schemas.payroll import (
    AttendanceSummaryOut,
    ExpenseClaimCreate,
    ExpenseClaimDecision,
    ExpenseClaimOut,
    PayrollDirectoryEntry,
    RunPayrollRequest,
    SalaryPaymentOut,
    SalaryRecordCreate,
    SalaryRecordOut,
    UnpaidEarlierOut,
)
from app.services import payroll_attendance_service, payroll_service
from app.services.attendance_summary_export import MONTH_NAMES, export_attendance_summary
from app.utils.timezone import get_org_timezone

router = APIRouter(tags=["Payroll"])

VIEW = Depends(require_permission("payroll:view"))
MANAGE = Depends(require_permission("payroll:manage"))


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------


@router.get(
    "/payroll/directory",
    response_model=SuccessResponse[list[PayrollDirectoryEntry]],
    summary="Minimal active-employee directory for assigning salary structures",
    dependencies=[MANAGE],
)
async def get_payroll_directory(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await payroll_service.get_payroll_directory(session))


@router.get(
    "/payroll/attendance-summary",
    response_model=SuccessResponse[AttendanceSummaryOut],
    summary="Each person's month in paid and cut days - the same numbers Run Payroll uses",
    dependencies=[VIEW],
)
async def attendance_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await payroll_attendance_service.get_attendance_summary(session, year, month))


@router.get(
    "/payroll/attendance-summary/export",
    summary="Download the Attendance Summary for one month as an Excel file",
    dependencies=[VIEW],
)
async def export_attendance_summary_excel(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    generated_at = datetime.now(get_org_timezone()).strftime("%d %b %Y, %I:%M %p")
    workbook_bytes = await export_attendance_summary(session, year, month, current_user.email, generated_at)
    filename = f"Attendance_Summary_{MONTH_NAMES[month - 1]}_{year}.xlsx"
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/salary-records", response_model=SuccessResponse[list[SalaryRecordOut]], summary="List salary structures", dependencies=[VIEW]
)
async def list_salary_records(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await payroll_service.list_salary_records(session))


@router.get(
    "/salary-records/my/history",
    response_model=SuccessResponse[list[SalaryRecordOut]],
    summary="My own salary history (every salary I've had, oldest first)",
)
async def my_salary_history(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await payroll_service.get_my_salary_history(session, current_user))


@router.get(
    "/salary-records/{employee_id}/history",
    response_model=SuccessResponse[list[SalaryRecordOut]],
    summary="One employee's salary history (every salary they've had, oldest first)",
    dependencies=[VIEW],
)
async def salary_history(employee_id: int, session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await payroll_service.get_salary_history(session, employee_id))


@router.post(
    "/salary-records",
    response_model=SuccessResponse[SalaryRecordOut],
    status_code=201,
    summary="Set an employee's salary structure",
    dependencies=[MANAGE],
)
async def set_salary_record(
    payload: SalaryRecordCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.set_salary_record(session, payload, current_user, request)
    return SuccessResponse(message="Salary structure saved", data=result)


@router.post(
    "/salary-payments/run",
    response_model=SuccessResponse[list[SalaryPaymentOut]],
    summary="Run payroll for a month",
    dependencies=[MANAGE],
)
async def run_payroll(
    payload: RunPayrollRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.run_payroll(session, payload, current_user, request)
    return SuccessResponse(message="Payroll run complete", data=result)


@router.get(
    "/salary-payments",
    response_model=SuccessResponse[list[SalaryPaymentOut]],
    summary="List salary payments for a month",
    dependencies=[VIEW],
)
async def list_salary_payments(
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await payroll_service.list_salary_payments(session, year, month))


@router.get(
    "/salary-payments/unpaid-earlier",
    response_model=SuccessResponse[UnpaidEarlierOut],
    summary="Salary still unpaid from months before the given one",
    dependencies=[VIEW],
)
async def unpaid_earlier_salary(
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await payroll_service.get_unpaid_earlier(session, year, month))


@router.get(
    "/salary-payments/{payment_id}/payslip",
    summary="Download a PAID salary payment's payslip as a PDF",
)
async def download_payslip(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await payroll_service.get_payslip_pdf(session, payment_id, current_user)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/salary-records/my",
    response_model=SuccessResponse[SalaryRecordOut | None],
    summary="My own salary structure",
)
async def my_salary_record(
    current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    return SuccessResponse(data=await payroll_service.get_my_salary_record(session, current_user))


@router.get(
    "/salary-payments/my",
    response_model=SuccessResponse[PaginatedData[SalaryPaymentOut]],
    summary="My own payslip history",
)
async def my_salary_payments(
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only requests that start in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.get_my_salary_payments(session, current_user, page, page_size, year)
    return SuccessResponse(data=result)


@router.patch(
    "/salary-payments/{payment_id}/pay",
    response_model=SuccessResponse[SalaryPaymentOut],
    summary="Mark a salary payment as paid",
    dependencies=[MANAGE],
)
async def mark_salary_paid(
    payment_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.mark_salary_paid(session, payment_id, current_user, request)
    return SuccessResponse(message="Salary marked as paid", data=result)


# ---------------------------------------------------------------------------
# Expense claims
# ---------------------------------------------------------------------------


@router.post(
    "/expenses",
    response_model=SuccessResponse[ExpenseClaimOut],
    status_code=201,
    summary="Submit an expense reimbursement claim",
    dependencies=[Depends(require_permission("expense:submit"))],
)
async def submit_expense_claim(
    payload: ExpenseClaimCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.submit_expense_claim(session, current_user, payload, request)
    return SuccessResponse(message="Expense claim submitted", data=result)


@router.get(
    "/expenses/my", response_model=SuccessResponse[PaginatedData[ExpenseClaimOut]], summary="My expense claims"
)
async def my_expense_claims(
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only claims submitted in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.get_my_expense_claims(session, current_user, page, page_size, year)
    return SuccessResponse(data=result)


@router.get(
    "/expenses",
    response_model=SuccessResponse[PaginatedData[ExpenseClaimOut]],
    summary="All expense claims (Accountant/Admin)",
    dependencies=[VIEW],
)
async def all_expense_claims(
    status: ExpenseClaimStatus | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100, description="Only claims submitted in this calendar year"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.get_all_expense_claims(session, page, page_size, status, year)
    return SuccessResponse(data=result)


@router.patch(
    "/expenses/{claim_id}/approve",
    response_model=SuccessResponse[ExpenseClaimOut],
    summary="Approve an expense claim",
    dependencies=[MANAGE],
)
async def approve_expense_claim(
    claim_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.approve_expense_claim(session, claim_id, current_user, request)
    return SuccessResponse(message="Expense claim approved", data=result)


@router.patch(
    "/expenses/{claim_id}/reject",
    response_model=SuccessResponse[ExpenseClaimOut],
    summary="Reject an expense claim",
    dependencies=[MANAGE],
)
async def reject_expense_claim(
    claim_id: int,
    payload: ExpenseClaimDecision,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.reject_expense_claim(session, claim_id, payload.rejection_reason, current_user, request)
    return SuccessResponse(message="Expense claim rejected", data=result)


@router.patch(
    "/expenses/{claim_id}/pay",
    response_model=SuccessResponse[ExpenseClaimOut],
    summary="Mark an approved expense claim as paid",
    dependencies=[MANAGE],
)
async def pay_expense_claim(
    claim_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await payroll_service.pay_expense_claim(session, claim_id, current_user, request)
    return SuccessResponse(message="Expense claim paid", data=result)
