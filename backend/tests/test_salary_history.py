"""salary_records is a history now (one row per change), not one row overwritten on every raise."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.payroll import SalaryRecord
from app.models.user import User


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _set(client, headers, employee_id, basic, effective_from, allowances=0, deductions=0):
    return await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": basic, "allowances": allowances, "deductions": deductions,
              "effective_from": effective_from},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_a_raise_keeps_the_old_salary_instead_of_erasing_it(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, accountant_user, demo_password)

    first = await _set(client, headers, report.id, 24000, "2025-01-01")
    assert first.status_code == 201 and first.json()["data"]["net_pay"] == 24000

    raise_ = await _set(client, headers, report.id, 30000, "2026-04-01")
    assert raise_.status_code == 201

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(SalaryRecord).where(SalaryRecord.employee_id == report.id)
    )).scalars().all()
    assert sorted((r.effective_from, float(r.basic_pay)) for r in rows) == [
        (date(2025, 1, 1), 24000.0), (date(2026, 4, 1), 30000.0)
    ]  # the original was NOT overwritten

    # "current" (the list Accountant/Founder see) shows only the latest
    listing = await client.get("/api/v1/salary-records", headers=headers)
    row = next(r for r in listing.json()["data"] if r["employee_id"] == report.id)
    assert row["basic_pay"] == 30000 and row["effective_from"] == "2026-04-01"

    # the full history, oldest first
    history = await client.get(f"/api/v1/salary-records/{report.id}/history", headers=headers)
    assert history.status_code == 200
    assert [h["basic_pay"] for h in history.json()["data"]] == [24000, 30000]
    assert [h["effective_from"] for h in history.json()["data"]] == ["2025-01-01", "2026-04-01"]


@pytest.mark.asyncio
async def test_re_saving_the_same_date_corrects_it_instead_of_duplicating(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, accountant_user, demo_password)

    await _set(client, headers, report.id, 24000, "2026-01-01")
    fixed = await _set(client, headers, report.id, 24500, "2026-01-01")  # a typo correction, same date
    assert fixed.status_code == 201

    history = await client.get(f"/api/v1/salary-records/{report.id}/history", headers=headers)
    assert [h["basic_pay"] for h in history.json()["data"]] == [24500]  # one row, updated - not two


@pytest.mark.asyncio
async def test_only_the_owner_and_payroll_viewers_see_history(
    client: AsyncClient, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    await _set(client, await _login(client, accountant_user, demo_password), report.id, 24000, "2026-01-01")

    own = await client.get("/api/v1/salary-records/my/history", headers=await _login(client, manager_with_team["report_user"], demo_password))
    assert own.status_code == 200 and len(own.json()["data"]) == 1

    outsider = await client.get(f"/api/v1/salary-records/{report.id}/history", headers=await _login(client, manager_with_team["manager_user"], demo_password))
    assert outsider.status_code == 403  # a manager has no payroll:view

    missing = await client.get("/api/v1/salary-records/999999/history", headers=await _login(client, accountant_user, demo_password))
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_payroll_uses_the_salary_that_applied_when_the_month_ended(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """A raise effective next month must not leak into a month run today, and running an old month later
    must use what applied THEN, not today's current salary."""
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType

    report = manager_with_team["report_employee"]
    await db_session.execute(__import__("sqlalchemy").update(Employee).values(date_of_joining=date(2025, 1, 1)))
    headers = await _login(client, accountant_user, demo_password)
    await _set(client, headers, report.id, 24000, "2025-01-01")
    await _set(client, headers, report.id, 30000, "2026-04-01")  # a future-dated raise relative to March

    # A full month of paid leave in both months, so pay comes out to exactly the salary being tested -
    # attendance-based cuts are covered elsewhere; this test is only about which salary gets picked.
    leave_type = LeaveType(code="MONTHENDTEST", name="Test paid leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    for start, end in [(date(2026, 3, 1), date(2026, 3, 31)), (date(2026, 4, 1), date(2026, 4, 30))]:
        db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=start, end_date=end,
                                    number_of_days=(end - start).days + 1, status=LeaveRequestStatus.APPROVED))
    await db_session.flush()

    march = await client.post("/api/v1/salary-payments/run", json={"year": 2026, "month": 3}, headers=headers)
    assert next(p for p in march.json()["data"] if p["employee_id"] == report.id)["amount"] == 24000

    april = await client.post("/api/v1/salary-payments/run", json={"year": 2026, "month": 4}, headers=headers)
    assert next(p for p in april.json()["data"] if p["employee_id"] == report.id)["amount"] == 30000

    # Give another raise now; re-running (already-created) payments must NOT retroactively change March or April.
    await _set(client, headers, report.id, 50000, "2026-09-01")
    rerun_march = await client.post("/api/v1/salary-payments/run", json={"year": 2026, "month": 3}, headers=headers)
    assert next(p for p in rerun_march.json()["data"] if p["employee_id"] == report.id)["amount"] == 24000


@pytest.mark.asyncio
async def test_audit_log_records_each_salary_change(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, accountant_user, demo_password)
    await _set(client, headers, report.id, 24000, "2025-01-01")
    await _set(client, headers, report.id, 30000, "2026-04-01")
    logs = (await db_session.execute(
        __import__("sqlalchemy").select(AuditLog).where(AuditLog.entity_type == "SalaryRecord")
    )).scalars().all()
    assert len(logs) == 2
