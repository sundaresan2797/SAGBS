"""GET /leaves/employee/{id}: one employee's leave requests, for the calendar pop-up to correctly tell an
Absent day apart from an On-leave day (see CorrectAttendanceSheet / classifyDay on the frontend)."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.models.user import User


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _leave_type(db_session, employee_id: int, year: int) -> LeaveType:
    leave_type = LeaveType(code="ELREQTEST", name="Test leave", is_paid=True, default_annual_days=12, is_active=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveBalance(employee_id=employee_id, leave_type_id=leave_type.id, year=year, allocated_days=12, used_days=0))
    await db_session.flush()
    return leave_type


@pytest.mark.asyncio
async def test_an_employee_sees_their_own_leave_requests(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    report = manager_with_team["report_employee"]
    start = date.today() + timedelta(days=10)
    leave_type = await _leave_type(db_session, report.id, start.year)
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=start, end_date=start,
                                number_of_days=1, status="APPROVED"))
    await db_session.flush()

    response = await client.get(
        f"/api/v1/leaves/employee/{report.id}",
        headers=await _login(client, manager_with_team["report_user"], demo_password),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == 1 and items[0]["start_date"] == start.isoformat() and items[0]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_a_manager_sees_their_reports_leave_but_not_an_outsiders(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    start = date.today() + timedelta(days=5)
    leave_type = await _leave_type(db_session, report.id, start.year)
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=start, end_date=start,
                                number_of_days=1, status="APPROVED"))
    await db_session.flush()
    manager_headers = await _login(client, manager_with_team["manager_user"], demo_password)

    ok = await client.get(f"/api/v1/leaves/employee/{report.id}", headers=manager_headers)
    assert ok.status_code == 200 and len(ok.json()["data"]["items"]) == 1

    denied = await client.get(f"/api/v1/leaves/employee/{outsider.id}", headers=manager_headers)
    assert denied.status_code == 403 and denied.json()["error_code"] == "ATTENDANCE_FORBIDDEN"


@pytest.mark.asyncio
async def test_hr_and_admin_see_anyones_leave(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, admin_user: User, demo_password: str
):
    outsider = manager_with_team["outsider_employee"]
    for user in (hr_user, admin_user):
        response = await client.get(
            f"/api/v1/leaves/employee/{outsider.id}", headers=await _login(client, user, demo_password)
        )
        assert response.status_code == 200, f"{user.email}: {response.text}"


@pytest.mark.asyncio
async def test_an_outsider_cannot_see_someone_elses_leave(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    response = await client.get(
        f"/api/v1/leaves/employee/{manager_with_team['report_employee'].id}",
        headers=await _login(client, manager_with_team["outsider_user"], demo_password),
    )
    assert response.status_code == 403 and response.json()["error_code"] == "ATTENDANCE_FORBIDDEN"


@pytest.mark.asyncio
async def test_unknown_employee_is_a_clean_404(client: AsyncClient, admin_user: User, demo_password: str):
    response = await client.get("/api/v1/leaves/employee/999999", headers=await _login(client, admin_user, demo_password))
    assert response.status_code == 404
