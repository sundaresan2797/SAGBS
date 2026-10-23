"""The calendar-year option on the lists that grow over time (leave, expense claims, payslips)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.models.enums import ExpenseClaimCategory, ExpenseClaimStatus, LeaveRequestStatus, SalaryPaymentStatus
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import ExpenseClaim, SalaryPayment
from app.models.user import User

IST = ZoneInfo("Asia/Kolkata")


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _ids(response) -> list[int]:
    assert response.status_code == 200, response.text
    return sorted(item["id"] for item in response.json()["data"]["items"])


@pytest.mark.asyncio
async def test_leave_lists_can_be_narrowed_to_a_year(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    leave_type = LeaveType(code="YRTEST", name="Year test", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    made = {}
    for label, start, status in [
        ("dec_2025", date(2025, 12, 30), LeaveRequestStatus.APPROVED),
        ("jan_2026", date(2026, 1, 2), LeaveRequestStatus.APPROVED),
        ("mar_2026", date(2026, 3, 10), LeaveRequestStatus.PENDING),
    ]:
        request = LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=start, end_date=start,
                               number_of_days=1, status=status)
        db_session.add(request)
        await db_session.flush()
        made[label] = request.id

    everything = sorted(made.values())
    for headers, path in [
        (await _login(client, manager_with_team["report_user"], demo_password), "/api/v1/leaves/my"),  # the employee's own
        (await _login(client, manager_with_team["manager_user"], demo_password), "/api/v1/leaves/team"),  # the manager's team
        (await _login(client, hr_user, demo_password), "/api/v1/leaves/requests"),  # HR, company-wide
    ]:
        assert _ids(await client.get(path, headers=headers)) == everything  # no year: all of them
        assert _ids(await client.get(path, params={"year": 2025}, headers=headers)) == [made["dec_2025"]]
        assert _ids(await client.get(path, params={"year": 2026}, headers=headers)) == sorted([made["jan_2026"], made["mar_2026"]])
        assert _ids(await client.get(path, params={"year": 2024}, headers=headers)) == []
        assert (await client.get(path, params={"year": 1999}, headers=headers)).status_code == 422

    # works together with the status filter
    headers = await _login(client, hr_user, demo_password)
    assert _ids(await client.get("/api/v1/leaves/requests", params={"year": 2026, "status": "PENDING"}, headers=headers)) == [made["mar_2026"]]


@pytest.mark.asyncio
async def test_expense_claims_use_the_company_calendar_year(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    made = {}
    # 31 Dec 23:30 IST is still 2025; 1 Jan 00:30 IST is already 2026 - although in UTC both are 31 Dec 2025.
    for label, when in [
        ("late_dec", datetime(2025, 12, 31, 23, 30, tzinfo=IST)),
        ("early_jan", datetime(2026, 1, 1, 0, 30, tzinfo=IST)),
        ("mid_2026", datetime(2026, 6, 15, 12, 0, tzinfo=IST)),
    ]:
        claim = ExpenseClaim(employee_id=report.id, category=ExpenseClaimCategory.TRAVEL, amount=100,
                             status=ExpenseClaimStatus.PENDING, created_at=when, updated_at=when)
        db_session.add(claim)
        await db_session.flush()
        made[label] = claim.id

    for headers, path in [
        (await _login(client, accountant_user, demo_password), "/api/v1/expenses"),
        (await _login(client, manager_with_team["report_user"], demo_password), "/api/v1/expenses/my"),
    ]:
        assert _ids(await client.get(path, headers=headers)) == sorted(made.values())
        assert _ids(await client.get(path, params={"year": 2025}, headers=headers)) == [made["late_dec"]]
        assert _ids(await client.get(path, params={"year": 2026}, headers=headers)) == sorted([made["early_jan"], made["mid_2026"]])
        assert (await client.get(path, params={"year": 2101}, headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_my_payslips_can_be_narrowed_to_a_year(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    report = manager_with_team["report_employee"]
    made = {}
    for year, month in [(2025, 11), (2025, 12), (2026, 1)]:
        payment = SalaryPayment(employee_id=report.id, year=year, month=month, amount=20000, basic_pay=20000,
                                allowances=0, deductions=0, status=SalaryPaymentStatus.PENDING)
        db_session.add(payment)
        await db_session.flush()
        made[(year, month)] = payment.id
    headers = await _login(client, manager_with_team["report_user"], demo_password)
    assert _ids(await client.get("/api/v1/salary-payments/my", headers=headers)) == sorted(made.values())
    assert _ids(await client.get("/api/v1/salary-payments/my", params={"year": 2025}, headers=headers)) == sorted([made[(2025, 11)], made[(2025, 12)]])
    assert _ids(await client.get("/api/v1/salary-payments/my", params={"year": 2026}, headers=headers)) == [made[(2026, 1)]]
