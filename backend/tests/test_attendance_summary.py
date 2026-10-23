"""The monthly attendance summary: paid days, cut days and the pay for the month."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, LeaveRequestStatus
from app.models.holiday import Holiday
from app.models.leave import LeaveRequest, LeaveType
from app.models.enums import SalaryPaymentStatus
from app.models.payroll import SalaryPayment, SalaryRecord
from app.models.user import User
from app.services.attendance_summary import count_month, pay_for_month

P, L, H, A = AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY, AttendanceStatus.ABSENT
IST = ZoneInfo("Asia/Kolkata")
LONG_AGO = date(2020, 1, 1)


def d(y, m, day):
    return date(y, m, day)


# ----- the counting rules -----


def test_september_example_comes_to_24292():
    """30 days, 4 Sundays; 19 present + 2 late + 1 half day + 2 paid leave + 2 absent (Mon-Sat = 26 days)."""
    records = {}
    working = [d(2026, 9, n) for n in range(1, 31) if d(2026, 9, n).weekday() != 6]
    assert len(working) == 26
    for day in working[:19]:
        records[day] = P
    records[working[19]] = L
    records[working[20]] = L
    records[working[21]] = H
    leave = {working[22]: True, working[23]: True}  # 2 paid leave days; the last two working days are absent
    counts = count_month(2026, 9, records=records, off_dates=set(), leave_days=leave, joining=LONG_AGO, today=d(2026, 10, 5))

    assert (counts.total_days, counts.present, counts.late, counts.half_day) == (30, 19, 2, 1)
    assert (counts.paid_leave, counts.unpaid_leave, counts.absent, counts.days_off) == (2, 0, 2, 4)
    assert counts.payable_days == 27.5 and counts.cut_days == 2.5
    assert counts.payable_days + counts.cut_days == counts.total_days
    assert pay_for_month(26500, counts) == Decimal("24292")
    assert counts.working_days == 26  # 30 days - 4 Sundays


def test_unfinished_month_has_open_days_and_no_pay():
    counts = count_month(2026, 9, records={d(2026, 9, 1): P}, off_dates=set(), leave_days={}, joining=LONG_AGO,
                         today=d(2026, 9, 10))
    assert counts.open_days == 21  # 10th itself is not over yet, so 10..30
    assert counts.working_days == 26  # a calendar fact: it does not depend on today's date
    assert pay_for_month(26500, counts) is None
    assert counts.payable_days + counts.cut_days + counts.before_joining + counts.open_days == counts.total_days


def test_a_new_joiner_is_paid_only_from_the_joining_date():
    # Joined Wed 16 Sep. Present every working day after that; Sundays 20 and 27 are paid days off.
    records = {d(2026, 9, n): P for n in range(16, 31) if d(2026, 9, n).weekday() != 6}
    counts = count_month(2026, 9, records=records, off_dates=set(), leave_days={}, joining=d(2026, 9, 16), today=d(2026, 10, 2))
    assert counts.before_joining == 15 and counts.absent == 0 and counts.days_off == 2 and counts.present == 13
    assert counts.payable_days == 15 and counts.cut_days == 0
    assert counts.working_days == 13  # only the days from joining, minus the two Sundays
    assert pay_for_month(30000, counts) == Decimal("15000")  # half the month


def test_leave_holidays_and_sundays():
    off = {d(2026, 9, 14)}  # a company holiday on a Monday
    leave = {d(2026, 9, 13): False, d(2026, 9, 14): True, d(2026, 9, 15): False, d(2026, 9, 16): True}  # Sun, holiday, Tue, Wed
    counts = count_month(2026, 9, records={}, off_dates=off, leave_days=leave, joining=LONG_AGO, today=d(2026, 10, 1))
    # leave on a Sunday or a holiday is just a day off; only Tue (unpaid) and Wed (paid) are leave days
    assert counts.unpaid_leave == 1 and counts.paid_leave == 1
    assert counts.days_off == 4 + 1  # 4 Sundays + the holiday
    assert counts.working_days == 30 - 4 - 1  # a day off is never a working day, leave or not


def test_saved_record_wins_even_on_a_day_off():
    records = {d(2026, 9, 13): P}  # someone worked a Sunday
    counts = count_month(2026, 9, records=records, off_dates=set(), leave_days={}, joining=LONG_AGO, today=d(2026, 10, 1))
    assert counts.present == 1 and counts.days_off == 3  # counted once, as worked


def test_february_and_leap_year_lengths():
    assert count_month(2026, 2, records={}, off_dates=set(), leave_days={}, joining=LONG_AGO, today=d(2026, 3, 5)).total_days == 28
    assert count_month(2028, 2, records={}, off_dates=set(), leave_days={}, joining=LONG_AGO, today=d(2028, 3, 5)).total_days == 29


def test_pay_rounds_half_up_to_whole_rupees():
    counts = count_month(2026, 9, records={}, off_dates=set(), leave_days={}, joining=LONG_AGO, today=d(2026, 10, 1))
    counts.absent, counts.days_off = 0, 30  # everyone paid for everything
    assert pay_for_month(26500, counts) == Decimal("26500")
    counts.days_off, counts.absent = 29, 1
    assert pay_for_month(10000, counts) == Decimal("9667")  # 10000/30*29 = 9666.67


# ----- through the API -----

MARCH = {"year": 2025, "month": 3}


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_summary_for_a_month_end_to_end(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    db_session.add(SalaryRecord(employee_id=report.id, basic_pay=24000, allowances=4000, deductions=1500,
                                effective_from=date(2025, 1, 1)))
    for day, status, has_out in [(3, P, True), (4, L, True), (5, H, True), (6, P, False)]:  # 6th: forgot to check out
        db_session.add(Attendance(
            employee_id=report.id, attendance_date=d(2025, 3, day), status=status,
            check_in=datetime(2025, 3, day, 9, 0, tzinfo=IST),
            check_out=datetime(2025, 3, day, 18, 0, tzinfo=IST) if has_out else None))
    db_session.add_all([Holiday(name="Test Holiday", holiday_date=d(2025, 3, 7), is_optional=False),
                        Holiday(name="Optional Day", holiday_date=d(2025, 3, 8), is_optional=True)])
    paid = LeaveType(code="PAIDT", name="Paid test", is_paid=True)
    unpaid = LeaveType(code="UNPAIDT", name="Unpaid test", is_paid=False)
    db_session.add_all([paid, unpaid])
    await db_session.flush()
    for start, end, kind, status in [(10, 11, paid, LeaveRequestStatus.APPROVED), (12, 12, unpaid, LeaveRequestStatus.APPROVED),
                                     (13, 13, paid, LeaveRequestStatus.PENDING)]:
        db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=kind.id, start_date=d(2025, 3, start),
                                    end_date=d(2025, 3, end), number_of_days=end - start + 1, status=status))
    await db_session.flush()

    headers = await _login(client, accountant_user, demo_password)
    response = await client.get("/api/v1/payroll/attendance-summary", params=MARCH, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total_days"] == 31 and data["month_ended"] is True

    row = next(i for i in data["items"] if i["employee_id"] == report.id)
    assert row["total_days"] == 31
    assert (row["present"], row["late"], row["half_day"]) == (2, 1, 1)
    assert (row["paid_leave"], row["unpaid_leave"], row["days_off"]) == (2, 1, 6)  # 5 Sundays + the holiday
    assert row["absent"] == 18  # includes the optional holiday and the pending-leave day
    assert row["working_days"] == 25  # 31 days - 5 Sundays - 1 holiday (the optional holiday is still a working day)
    assert row["payable_days"] == 11.5 and row["cut_days"] == 19.5
    assert row["payable_days"] + row["cut_days"] == row["total_days"]
    assert row["monthly_salary"] == 26500 and row["pay_for_month"] == 9831  # 26500 / 31 x 11.5
    assert row["payslip_id"] is None and row["payslip_amount"] is None and row["difference"] is None  # payroll not run
    assert row["missed_check_outs"] == 1 and row["pending_leave_requests"] == 1
    assert data["total_pay"] == 9831

    checklist = data["checklist"]
    assert checklist["missed_check_outs"] == 1 and checklist["pending_leave_requests"] == 1
    assert checklist["absent_days"] == 18
    assert checklist["employees_without_salary"] >= 1  # the other active people have no salary set


@pytest.mark.asyncio
async def test_current_month_shows_no_pay_yet(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    from app.utils.timezone import today_in_org_tz

    db_session.add(SalaryRecord(employee_id=manager_with_team["report_employee"].id, basic_pay=20000, allowances=0,
                                deductions=0, effective_from=date(2025, 1, 1)))
    await db_session.flush()
    today = today_in_org_tz()
    response = await client.get("/api/v1/payroll/attendance-summary", params={"year": today.year, "month": today.month},
                                headers=await _login(client, accountant_user, demo_password))
    data = response.json()["data"]
    assert data["month_ended"] is False and data["total_pay"] is None
    assert data["items"][0]["pay_for_month"] is None


@pytest.mark.asyncio
async def test_only_payroll_viewers_see_the_summary(
    client: AsyncClient, manager_with_team: dict, accountant_user: User, founder_user: User, hr_user: User,
    admin_user: User, executive_user: User, employee_user: User, demo_password: str,
):
    # Executive gets the same read-only money visibility as Founder (payroll:view) - it just can't
    # manage any of it (covered in test_payroll.py's test_executive_can_view_payroll_but_cannot_manage_it).
    for user in (accountant_user, founder_user, executive_user):
        ok = await client.get("/api/v1/payroll/attendance-summary", params=MARCH, headers=await _login(client, user, demo_password))
        assert ok.status_code == 200, user.email
    for user in (hr_user, admin_user, employee_user, manager_with_team["manager_user"]):
        denied = await client.get("/api/v1/payroll/attendance-summary", params=MARCH, headers=await _login(client, user, demo_password))
        assert denied.status_code == 403, user.email
    assert (await client.get("/api/v1/payroll/attendance-summary", params=MARCH)).status_code in (401, 403)
    bad = await client.get("/api/v1/payroll/attendance-summary", params={"year": 2025, "month": 13},
                           headers=await _login(client, accountant_user, demo_password))
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_money_columns_compare_the_payslip_with_pay_by_attendance(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """Everyone is present all month, so pay by attendance is the full salary unless days are cut."""
    report, manager, outsider = (manager_with_team[k] for k in ("report_employee", "manager_employee", "outsider_employee"))
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    # Their standing salary structure, already in effect by March (a later raise is covered separately,
    # in test_payroll_uses_the_salary_that_applied_when_the_month_ended): 30000 each
    for employee in (report, manager, outsider):
        db_session.add(SalaryRecord(employee_id=employee.id, basic_pay=30000, allowances=0, deductions=0,
                                    effective_from=date(2025, 1, 1)))
    # March payslips: report - made at 26500 before the raise (with the breakdown saved), PENDING;
    # manager - an old payslip with no breakdown (amount 20000), PAID; outsider - payroll not run.
    db_session.add(SalaryPayment(employee_id=report.id, year=2025, month=3, amount=26500, basic_pay=24000,
                                 allowances=4000, deductions=1500, status=SalaryPaymentStatus.PENDING))
    db_session.add(SalaryPayment(employee_id=manager.id, year=2025, month=3, amount=20000,
                                 status=SalaryPaymentStatus.PAID, paid_date=date(2025, 4, 2)))
    await db_session.flush()
    # 31 days, nobody has any attendance: 5 Sundays are paid, 26 days absent -> payable 5, cut 26

    headers = await _login(client, accountant_user, demo_password)
    data = (await client.get("/api/v1/payroll/attendance-summary", params=MARCH, headers=headers)).json()["data"]
    rows = {i["employee_id"]: i for i in data["items"]}

    r = rows[report.id]  # salary comes from the March payslip (26500), not the current 30000 structure
    assert r["monthly_salary"] == 26500 and r["pay_for_month"] == 4274  # 26500 / 31 x 5 = 4274.19
    assert r["payslip_amount"] == 26500 and r["payslip_status"] == "PENDING" and r["payslip_id"]
    assert r["difference"] == 22226  # 26500 - 4274

    m = rows[manager.id]  # old payslip with no breakdown: its amount is that month's salary
    assert m["monthly_salary"] == 20000 and m["pay_for_month"] == 3226  # 20000 / 31 x 5 = 3225.8
    assert m["payslip_status"] == "PAID" and str(m["payslip_paid_date"]) == "2025-04-02"
    assert m["difference"] == 16774

    o = rows[outsider.id]  # no payslip yet: today's salary, nothing to compare
    assert o["monthly_salary"] == 30000 and o["pay_for_month"] == 4839  # 30000 / 31 x 5 = 4838.7
    assert o["payslip_amount"] is None and o["payslip_status"] is None and o["difference"] is None

    assert data["total_monthly_salary"] == 26500 + 20000 + 30000
    assert data["total_pay"] == 4274 + 3226 + 4839
    assert data["total_on_payslips"] == 26500 + 20000  # only payslips that exist
    assert data["total_difference"] == 22226 + 16774  # only people who have both numbers


@pytest.mark.asyncio
async def test_a_month_with_no_payslips_has_no_payslip_total(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    db_session.add(SalaryRecord(employee_id=manager_with_team["report_employee"].id, basic_pay=31000, allowances=0,
                                deductions=0, effective_from=date(2025, 1, 1)))
    await db_session.flush()
    data = (await client.get("/api/v1/payroll/attendance-summary", params=MARCH,
                             headers=await _login(client, accountant_user, demo_password))).json()["data"]
    assert data["total_on_payslips"] is None and data["total_difference"] is None
    assert data["total_monthly_salary"] == 31000


def _month_start(today: date, months_back: int) -> date:
    index = today.year * 12 + (today.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


@pytest.mark.asyncio
async def test_open_missed_check_outs_in_other_months_are_reported_not_hidden(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """The checklist counts the month being viewed, and names the other months that still have some."""
    from app.utils.timezone import today_in_org_tz

    report = manager_with_team["report_employee"]
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    db_session.add(SalaryRecord(employee_id=report.id, basic_pay=20000, allowances=0, deductions=0,
                                effective_from=date(2020, 1, 1)))
    today = today_in_org_tz()
    viewed, one_before, two_before, long_ago = (_month_start(today, n) for n in (1, 2, 3, 14))
    for month_start, extra in ((viewed, 0), (one_before, 0), (two_before, 1), (long_ago, 0)):
        for offset in range(1 + extra):  # 1 open day in the viewed and previous months, 2 in the one before that
            day = month_start.replace(day=10 + offset)
            db_session.add(Attendance(employee_id=report.id, attendance_date=day, status=P,
                                      check_in=datetime(day.year, day.month, day.day, 9, 0, tzinfo=IST)))
    await db_session.flush()

    data = (await client.get("/api/v1/payroll/attendance-summary", params={"year": viewed.year, "month": viewed.month},
                             headers=await _login(client, accountant_user, demo_password))).json()["data"]
    checklist = data["checklist"]
    assert checklist["missed_check_outs"] == 1  # only the month being viewed
    assert checklist["missed_check_outs_in_other_months"] == [
        {"year": one_before.year, "month": one_before.month, "count": 1},
        {"year": two_before.year, "month": two_before.month, "count": 2},
    ]  # newest first; the one from 14 months ago is past the one-year window


@pytest.mark.asyncio
async def test_missed_list_covers_a_full_year(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    from datetime import timedelta

    from app.utils.timezone import today_in_org_tz

    report = manager_with_team["report_employee"]
    today = today_in_org_tz()
    for days_ago in (200, 400):
        day = today - timedelta(days=days_ago)
        db_session.add(Attendance(employee_id=report.id, attendance_date=day, status=P,
                                  check_in=datetime(day.year, day.month, day.day, 9, 0, tzinfo=IST)))
    await db_session.flush()
    listed = (await client.get("/api/v1/attendance/missed-checkouts",
                               headers=await _login(client, manager_with_team["manager_user"], demo_password))).json()["data"]
    assert [str(today - timedelta(days=200))] == [m["attendance_date"] for m in listed["items"]]  # 200 days old shown, 400 not
    assert listed["total"] == 1
