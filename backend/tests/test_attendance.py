from datetime import date

import pytest
from httpx import AsyncClient

from app.models.enums import EmployeeStatus
from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_check_in_then_duplicate_fails(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post("/api/v1/attendance/check-in", headers=headers)
    assert first.status_code == 200
    assert first.json()["data"]["check_in"] is not None

    second = await client.post("/api/v1/attendance/check-in", headers=headers)
    assert second.status_code == 400
    assert second.json()["error_code"] == "ALREADY_CHECKED_IN"


@pytest.mark.asyncio
async def test_check_out_without_check_in_fails(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.post("/api/v1/attendance/check-out", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "NOT_CHECKED_IN"


@pytest.mark.asyncio
async def test_check_out_then_duplicate_fails(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/attendance/check-in", headers=headers)
    first = await client.post("/api/v1/attendance/check-out", headers=headers)
    assert first.status_code == 200
    assert first.json()["data"]["working_minutes"] is not None

    second = await client.post("/api/v1/attendance/check-out", headers=headers)
    assert second.status_code == 400
    assert second.json()["error_code"] == "ALREADY_CHECKED_OUT"


@pytest.mark.asyncio
async def test_inactive_employee_cannot_check_in(
    client: AsyncClient, admin_user: User, employee_user: User, demo_password: str, db_session
):
    from sqlalchemy import select

    from app.models.employee import Employee

    employee = (
        await db_session.execute(select(Employee).where(Employee.user_id == employee_user.id))
    ).scalar_one()
    employee.status = EmployeeStatus.INACTIVE
    await db_session.commit()

    token = await _login(client, employee_user.email, demo_password)
    response = await client.post("/api/v1/attendance/check-in", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_INACTIVE"


@pytest.mark.asyncio
async def test_manager_sees_team_attendance_not_own(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    report_user = manager_with_team["report_user"]
    manager_user = manager_with_team["manager_user"]

    report_token = await _login(client, report_user.email, demo_password)
    await client.post("/api/v1/attendance/check-in", headers={"Authorization": f"Bearer {report_token}"})

    manager_token = await _login(client, manager_user.email, demo_password)
    response = await client.get("/api/v1/attendance/team", headers={"Authorization": f"Bearer {manager_token}"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["employee_code"] == manager_with_team["report_employee"].employee_code


@pytest.mark.asyncio
async def test_own_attendance_calendar(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/attendance/check-in", headers=headers)

    result = await client.get(
        "/api/v1/auth/me",
        headers=headers,
    )
    employee_id = result.json()["data"]["employee_id"]
    today = date.today()

    response = await client.get(
        f"/api/v1/attendance/employee/{employee_id}/calendar",
        params={"year": today.year, "month": today.month},
        headers=headers,
    )
    assert response.status_code == 200
    records = response.json()["data"]
    assert any(r["attendance_date"] == today.isoformat() for r in records)


@pytest.mark.asyncio
async def test_manager_can_view_direct_report_calendar(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    report_user = manager_with_team["report_user"]
    report_employee = manager_with_team["report_employee"]
    manager_user = manager_with_team["manager_user"]

    report_token = await _login(client, report_user.email, demo_password)
    await client.post("/api/v1/attendance/check-in", headers={"Authorization": f"Bearer {report_token}"})

    today = date.today()
    manager_token = await _login(client, manager_user.email, demo_password)
    response = await client.get(
        f"/api/v1/attendance/employee/{report_employee.id}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_manager_cannot_view_outsider_calendar(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    outsider_employee = manager_with_team["outsider_employee"]
    manager_user = manager_with_team["manager_user"]

    today = date.today()
    manager_token = await _login(client, manager_user.email, demo_password)
    response = await client.get(
        f"/api/v1/attendance/employee/{outsider_employee.id}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ATTENDANCE_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_can_view_anyones_calendar(
    client: AsyncClient, admin_user: User, manager_with_team: dict, demo_password: str
):
    outsider_employee = manager_with_team["outsider_employee"]
    today = date.today()
    admin_token = await _login(client, admin_user.email, demo_password)
    response = await client.get(
        f"/api/v1/attendance/employee/{outsider_employee.id}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Roll call: everyone who should be at work on a day, not just check-in rows.
# Fixed past dates keep these independent of the weekday the suite runs on:
#   2025-03-09 Sunday, 2025-03-10 Monday, 2025-03-11 Tuesday, 2025-03-12 Wednesday.
# ---------------------------------------------------------------------------

MONDAY = "2025-03-10"
SUNDAY = "2025-03-09"


async def _backdate_joining(db_session) -> None:
    from sqlalchemy import update

    from app.models.employee import Employee

    # Fixtures create everyone as "joined today", which would exclude them
    # from a roll call for any earlier date.
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    await db_session.flush()


async def _employee_id(db_session, user: User) -> int:
    from app.repositories.employee_repository import EmployeeRepository

    return (await EmployeeRepository(db_session).get_by_user_id(user.id)).id


async def _roll_call(client: AsyncClient, token: str, **params) -> dict:
    response = await client.get(
        "/api/v1/attendance/roll-call", params=params, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_roll_call_lists_people_who_did_not_check_in_as_absent(
    client: AsyncClient, db_session, admin_user: User, employee_user: User, manager_with_team: dict, demo_password: str
):
    from app.models.attendance import Attendance
    from app.models.enums import AttendanceStatus

    await _backdate_joining(db_session)
    present_id = await _employee_id(db_session, employee_user)
    db_session.add(
        Attendance(employee_id=present_id, attendance_date=date(2025, 3, 10), status=AttendanceStatus.PRESENT)
    )
    await db_session.flush()

    token = await _login(client, admin_user.email, demo_password)
    data = await _roll_call(client, token, date=MONDAY)

    assert data["day_off_reason"] is None
    assert data["total"] == 4  # employee + manager + report + outsider - all listed, not just the one with a row
    by_id = {item["employee_id"]: item["status"] for item in data["items"]}
    assert by_id[present_id] == "PRESENT"
    assert sorted(by_id.values()) == ["ABSENT", "ABSENT", "ABSENT", "PRESENT"]
    assert data["summary"] == {"PRESENT": 1, "ABSENT": 3}

    # Search and status filters narrow the list but never the summary counts.
    only_absent = await _roll_call(client, token, date=MONDAY, status="ABSENT")
    assert only_absent["total"] == 3
    assert only_absent["summary"] == {"PRESENT": 1, "ABSENT": 3}
    by_name = await _roll_call(client, token, date=MONDAY, search="test employee")
    assert [i["employee_id"] for i in by_name["items"]] == [present_id]


@pytest.mark.asyncio
async def test_roll_call_treats_sunday_and_calendar_holidays_as_days_off(
    client: AsyncClient, db_session, admin_user: User, employee_user: User, demo_password: str
):
    from app.models.attendance import Attendance
    from app.models.enums import AttendanceStatus
    from app.models.holiday import Holiday

    await _backdate_joining(db_session)
    employee_id = await _employee_id(db_session, employee_user)
    db_session.add_all(
        [
            Holiday(name="Test Holiday", holiday_date=date(2025, 3, 12), is_optional=False),
            Holiday(name="Optional Day", holiday_date=date(2025, 3, 13), is_optional=True),
        ]
    )
    await db_session.flush()
    token = await _login(client, admin_user.email, demo_password)

    sunday = await _roll_call(client, token, date=SUNDAY)
    assert sunday["day_off_reason"] == "Sunday"
    assert {i["status"] for i in sunday["items"]} == {"HOLIDAY"}

    holiday = await _roll_call(client, token, date="2025-03-12")
    assert holiday["day_off_reason"] == "Test Holiday"
    assert {i["status"] for i in holiday["items"]} == {"HOLIDAY"}

    # An optional holiday is not a company-wide day off.
    optional = await _roll_call(client, token, date="2025-03-13")
    assert optional["day_off_reason"] is None
    assert {i["status"] for i in optional["items"]} == {"ABSENT"}

    # Someone who did come in on a day off keeps their real status.
    db_session.add(
        Attendance(employee_id=employee_id, attendance_date=date(2025, 3, 9), status=AttendanceStatus.PRESENT)
    )
    await db_session.flush()
    worked_sunday = await _roll_call(client, token, date=SUNDAY)
    assert {i["employee_id"]: i["status"] for i in worked_sunday["items"]}[employee_id] == "PRESENT"


@pytest.mark.asyncio
async def test_roll_call_shows_approved_leave_and_skips_people_who_had_not_joined(
    client: AsyncClient, db_session, admin_user: User, manager_with_team: dict, demo_password: str
):
    from sqlalchemy import update

    from app.models.employee import Employee
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType

    await _backdate_joining(db_session)
    report = manager_with_team["report_employee"]
    outsider = manager_with_team["outsider_employee"]

    leave_type = LeaveType(code="TESTCL", name="Test Casual", is_paid=True, default_annual_days=12)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(
        LeaveRequest(
            employee_id=report.id,
            leave_type_id=leave_type.id,
            start_date=date(2025, 3, 10),
            end_date=date(2025, 3, 11),
            number_of_days=2,
            status=LeaveRequestStatus.APPROVED,
        )
    )
    # The outsider only joins after the day being looked at.
    await db_session.execute(update(Employee).where(Employee.id == outsider.id).values(date_of_joining=date(2025, 6, 1)))
    await db_session.flush()

    token = await _login(client, admin_user.email, demo_password)
    data = await _roll_call(client, token, date=MONDAY)
    by_id = {item["employee_id"]: item["status"] for item in data["items"]}
    assert by_id[report.id] == "ON_LEAVE"
    assert outsider.id not in by_id


@pytest.mark.asyncio
async def test_roll_call_scope_permissions_and_future_dates(
    client: AsyncClient, db_session, manager_with_team: dict, employee_user: User, admin_user: User, demo_password: str
):
    await _backdate_joining(db_session)
    manager_token = await _login(client, manager_with_team["manager_user"].email, demo_password)

    # A manager's roll call is only their direct reports.
    team = await _roll_call(client, manager_token, date=MONDAY)
    assert [i["employee_id"] for i in team["items"]] == [manager_with_team["report_employee"].id]

    # A plain employee has no roll call at all.
    employee_token = await _login(client, employee_user.email, demo_password)
    denied = await client.get(
        "/api/v1/attendance/roll-call", params={"date": MONDAY}, headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert denied.status_code == 403

    # Nobody can look at a day that hasn't happened yet.
    admin_token = await _login(client, admin_user.email, demo_password)
    future = await client.get(
        "/api/v1/attendance/roll-call", params={"date": "2999-01-01"}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert future.status_code == 400
    assert future.json()["error_code"] == "ROLL_CALL_FUTURE_DATE"


@pytest.mark.asyncio
async def test_dashboard_absent_today_is_zero_on_a_day_off(
    client: AsyncClient, db_session, admin_user: User, employee_user: User, demo_password: str, monkeypatch
):
    from app.core.redis import CacheKeys, redis_service
    from app.services import dashboard_service

    def fake_today(day: date):
        class _FakeDate(date):
            @classmethod
            def today(cls):
                return day

        return _FakeDate

    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(dashboard_service, "date", fake_today(date(2025, 3, 9)))  # a Sunday
    sunday = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert sunday.json()["data"]["absent_today"] == 0

    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY)
    monkeypatch.setattr(dashboard_service, "date", fake_today(date(2025, 3, 10)))  # a Monday
    monday = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert monday.json()["data"]["absent_today"] == 1  # the one active employee, who hasn't checked in
