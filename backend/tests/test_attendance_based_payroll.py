"""Step 3: Run Payroll pays by attendance, using the exact same numbers the Attendance Summary
preview shows - and only for months that have completely finished."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, LeaveRequestStatus
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import SalaryPayment, SalaryRecord
from app.models.user import User

IST = ZoneInfo("Asia/Kolkata")
P, L, H = AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY
YEAR, MONTH = 2026, 3  # a fully-ended month relative to "today" in this test run


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _day(n: int) -> date:
    return date(YEAR, MONTH, n)


@pytest.mark.asyncio
async def test_payroll_amount_matches_the_attendance_summary_preview_exactly(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """The whole point of Step 3: nobody should ever see one number on the preview and get paid another."""
    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records",
                      json={"employee_id": report.id, "basic_pay": 24000, "allowances": 4000, "deductions": 1500,
                            "effective_from": "2025-01-01"}, headers=headers)

    # A realistic mixed month: some present, one late, one half day, two absent, the rest untouched (weekends/Sundays).
    for n, status in [(2, P), (3, P), (4, L), (5, H)]:
        db_session.add(Attendance(employee_id=report.id, attendance_date=_day(n), status=status,
                                  check_in=datetime(YEAR, MONTH, n, 9, 5, tzinfo=IST),
                                  check_out=datetime(YEAR, MONTH, n, 18, 0, tzinfo=IST) if status != H else datetime(YEAR, MONTH, n, 12, 0, tzinfo=IST)))
    await db_session.flush()

    preview = await client.get("/api/v1/payroll/attendance-summary", params={"year": YEAR, "month": MONTH}, headers=headers)
    preview_row = next(r for r in preview.json()["data"]["items"] if r["employee_id"] == report.id)
    assert preview_row["pay_for_month"] is not None  # the month has ended, so this must be a real number

    run = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    assert run.status_code == 200, run.text
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)

    assert payment["amount"] == preview_row["pay_for_month"]
    assert payment["payable_days"] == preview_row["payable_days"]
    assert payment["cut_days"] == preview_row["cut_days"]
    assert payment["absent_days"] == preview_row["absent"]
    assert payment["half_days"] == preview_row["half_day"]
    assert payment["present_days"] == preview_row["present"]
    assert payment["late_days"] == preview_row["late"]
    assert payment["total_days"] == preview_row["total_days"]
    # sanity: two real absences and a half day mean real money was actually cut, not the full salary
    assert payment["amount"] < 26500 and payment["cut_days"] > 0


@pytest.mark.asyncio
async def test_absent_days_genuinely_reduce_pay_present_days_dont(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records",
                      json={"employee_id": report.id, "basic_pay": 31000, "allowances": 0, "deductions": 0,
                            "effective_from": "2025-01-01"}, headers=headers)

    # Present every working day of March 2026 except two absences.
    from app.services.working_days import WEEKLY_OFF_WEEKDAYS
    import calendar as cal
    absent_days = {5, 12}
    for n in range(1, cal.monthrange(YEAR, MONTH)[1] + 1):
        d = _day(n)
        if d.weekday() in WEEKLY_OFF_WEEKDAYS or n in absent_days:
            continue
        db_session.add(Attendance(employee_id=report.id, attendance_date=d, status=P,
                                  check_in=datetime(YEAR, MONTH, n, 9, 5, tzinfo=IST),
                                  check_out=datetime(YEAR, MONTH, n, 18, 0, tzinfo=IST)))
    await db_session.flush()

    run = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)
    assert payment["absent_days"] == 2
    expected = round(31000 / 31 * (31 - 2))
    assert payment["amount"] == expected, f"expected {expected}, got {payment['amount']}"
    assert payment["amount"] < 31000


@pytest.mark.asyncio
async def test_a_paid_month_never_changes_even_if_attendance_is_corrected_afterwards(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """The whole reason for snapshotting the breakdown onto the payment row."""
    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records",
                      json={"employee_id": report.id, "basic_pay": 20000, "allowances": 0, "deductions": 0,
                            "effective_from": "2025-01-01"}, headers=headers)
    db_session.add(Attendance(employee_id=report.id, attendance_date=_day(2), status=AttendanceStatus.ABSENT))
    await db_session.flush()

    run = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)
    original_amount = payment["amount"]
    await client.patch(f"/api/v1/salary-payments/{payment['id']}/pay", headers=headers)

    # HR/manager later marks that day present (a correction) - the ALREADY-PAID payment must be untouched.
    row = (await db_session.execute(select(Attendance).where(
        Attendance.employee_id == report.id, Attendance.attendance_date == _day(2)))).scalar_one()
    row.status = AttendanceStatus.PRESENT
    row.check_in = datetime(YEAR, MONTH, 2, 9, 0, tzinfo=IST)
    row.check_out = datetime(YEAR, MONTH, 2, 18, 0, tzinfo=IST)
    await db_session.flush()

    unchanged = await client.get("/api/v1/salary-payments/my", headers=await _login(client, manager_with_team["report_user"], demo_password))
    stored = next(p for p in unchanged.json()["data"]["items"] if p["year"] == YEAR and p["month"] == MONTH)
    assert stored["amount"] == original_amount
    assert stored["status"] == "PAID"

    # Re-running payroll for that month again creates nothing new and does not touch the paid row.
    rerun = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    rerun_payment = next(p for p in rerun.json()["data"] if p["employee_id"] == report.id)
    assert rerun_payment["amount"] == original_amount and rerun_payment["status"] == "PAID"


@pytest.mark.asyncio
async def test_full_day_of_leave_holiday_and_sunday_are_all_paid_in_full(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    from app.models.holiday import Holiday

    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records",
                      json={"employee_id": report.id, "basic_pay": 30000, "allowances": 0, "deductions": 0,
                            "effective_from": "2025-01-01"}, headers=headers)
    db_session.add(Holiday(name="Test Holiday", holiday_date=_day(10), is_optional=False))
    leave_type = LeaveType(code="FULLPAYTEST2", name="Test paid leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=_day(1),
                                end_date=_day(31), number_of_days=31, status=LeaveRequestStatus.APPROVED))
    await db_session.flush()

    run = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)
    assert payment["amount"] == 30000 and payment["cut_days"] == 0 and payment["absent_days"] == 0


@pytest.mark.asyncio
async def test_half_day_costs_exactly_half_a_day(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records",
                      json={"employee_id": report.id, "basic_pay": 31000, "allowances": 0, "deductions": 0,
                            "effective_from": "2025-01-01"}, headers=headers)
    leave_type = LeaveType(code="HALFDAYTEST", name="Test paid leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    # cover every day except the 2nd with paid leave, and make the 2nd a half day
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=_day(3),
                                end_date=_day(31), number_of_days=29, status=LeaveRequestStatus.APPROVED))
    db_session.add(Attendance(employee_id=report.id, attendance_date=_day(2), status=H,
                              check_in=datetime(YEAR, MONTH, 2, 9, 0, tzinfo=IST), check_out=datetime(YEAR, MONTH, 2, 12, 0, tzinfo=IST)))
    await db_session.flush()

    run = await client.post("/api/v1/salary-payments/run", json={"year": YEAR, "month": MONTH}, headers=headers)
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)
    assert payment["cut_days"] == 0.5
    assert payment["amount"] == round(31000 / 31 * 30.5)


@pytest.mark.asyncio
async def test_a_payment_made_before_step_3_has_no_breakdown_and_is_never_backfilled(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """Old, already-paid payments (made when everyone got their full salary) must stay exactly as they were -
    nothing retroactively rewrites them with a breakdown they never had."""
    report = manager_with_team["report_employee"]
    db_session.add(SalaryPayment(employee_id=report.id, year=2025, month=1, amount=25000, basic_pay=25000,
                                 allowances=0, deductions=0, status=__import__("app.models.enums", fromlist=["SalaryPaymentStatus"]).SalaryPaymentStatus.PAID))
    await db_session.flush()
    response = await client.get("/api/v1/salary-payments/my", headers=await _login(client, manager_with_team["report_user"], demo_password))
    old = next(p for p in response.json()["data"]["items"] if p["year"] == 2025 and p["month"] == 1)
    assert old["total_days"] is None and old["payable_days"] is None and old["amount"] == 25000


def test_payslip_attendance_summary_formats_whole_and_fractional_days_cleanly():
    """A Decimal like 28.0 must print as "28", not "28.0" - and 27.5 must keep its .5."""
    from app.services.payslip_service import _attendance_summary
    from app.models.payroll import SalaryPayment

    whole = SalaryPayment(total_days=31, payable_days=28.0, cut_days=3.0, present_days=28, late_days=0, half_days=0,
                          half_leave_days=0, paid_leave_days=0, unpaid_leave_days=0, absent_days=3, days_off_days=0)
    left, right, payable = _attendance_summary(whole)
    assert payable == "28 of 31 days"
    assert ["Absent", "3"] in left

    fractional = SalaryPayment(total_days=30, payable_days=27.5, cut_days=2.5, present_days=27, late_days=0, half_days=1,
                               half_leave_days=0, paid_leave_days=0, unpaid_leave_days=0, absent_days=2, days_off_days=0)
    left, right, payable = _attendance_summary(fractional)
    assert payable == "27.5 of 30 days"
    assert ["Half day", "1"] in left

    full_month = SalaryPayment(total_days=30, payable_days=30, cut_days=0, present_days=30, late_days=0, half_days=0,
                               half_leave_days=0, paid_leave_days=0, unpaid_leave_days=0, absent_days=0, days_off_days=0)
    left, right, payable = _attendance_summary(full_month)
    assert payable == "30 of 30 days"

    before_step_3 = SalaryPayment(total_days=None, payable_days=None)
    assert _attendance_summary(before_step_3) is None
