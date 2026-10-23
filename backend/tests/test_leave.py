from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import update

from app.models.employee import Employee
from app.models.leave import LeaveBalance, LeaveType
from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


async def _report_to(db_session: AsyncSession, employee_id: int, boss: Employee) -> None:
    """Applying for leave is refused when nobody could decide on it, so tests that apply as a plain
    employee first make them report to someone (see the boss_employee fixture)."""
    await db_session.execute(update(Employee).where(Employee.id == employee_id).values(manager_id=boss.id))
    await db_session.flush()


@pytest.fixture
def next_monday() -> date:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


async def _seed_leave_type(db_session: AsyncSession, code: str = "CASUAL", is_paid: bool = True) -> LeaveType:
    leave_type = LeaveType(code=code, name=code.title(), is_paid=is_paid, default_annual_days=12, is_active=True)
    db_session.add(leave_type)
    await db_session.flush()
    return leave_type


async def _seed_balance(db_session: AsyncSession, employee_id: int, leave_type: LeaveType, year: int, allocated: float):
    balance = LeaveBalance(employee_id=employee_id, leave_type_id=leave_type.id, year=year, allocated_days=allocated, used_days=0)
    db_session.add(balance)
    await db_session.flush()
    return balance


@pytest.mark.asyncio
async def test_apply_leave_insufficient_balance(
    client: AsyncClient, boss_employee: Employee, employee_user: User, demo_password: str, db_session: AsyncSession, next_monday: date
):
    from app.repositories.employee_repository import EmployeeRepository

    leave_type = await _seed_leave_type(db_session)
    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    await _report_to(db_session, employee.id, boss_employee)
    await _seed_balance(db_session, employee.id, leave_type, next_monday.year, allocated=1)

    token = await _login(client, employee_user.email, demo_password)
    response = await client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_type.id,
            "start_date": next_monday.isoformat(),
            "end_date": (next_monday + timedelta(days=4)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "INSUFFICIENT_LEAVE_BALANCE"


@pytest.mark.asyncio
async def test_apply_approve_updates_balance(
    client: AsyncClient, manager_with_team: dict, demo_password: str, db_session: AsyncSession, next_monday: date
):
    report_user = manager_with_team["report_user"]
    report_employee = manager_with_team["report_employee"]
    manager_user = manager_with_team["manager_user"]

    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, report_employee.id, leave_type, next_monday.year, allocated=10)

    report_token = await _login(client, report_user.email, demo_password)
    apply_response = await client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_type.id,
            "start_date": next_monday.isoformat(),
            "end_date": next_monday.isoformat(),
        },
        headers={"Authorization": f"Bearer {report_token}"},
    )
    assert apply_response.status_code == 201, apply_response.text
    request_id = apply_response.json()["data"]["id"]
    assert apply_response.json()["data"]["number_of_days"] == 1.0

    manager_token = await _login(client, manager_user.email, demo_password)
    approve_response = await client.patch(
        f"/api/v1/leaves/{request_id}/approve", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["data"]["status"] == "APPROVED"

    balance_response = await client.get(
        "/api/v1/leaves/balance", headers={"Authorization": f"Bearer {report_token}"}
    )
    balances = balance_response.json()["data"]
    matching = next(b for b in balances if b["leave_type_id"] == leave_type.id)
    assert matching["used_days"] == 1.0
    assert matching["remaining_days"] == 9.0


@pytest.mark.asyncio
async def test_manager_cannot_approve_outside_team(
    client: AsyncClient, boss_employee: Employee, manager_with_team: dict, demo_password: str, db_session: AsyncSession, next_monday: date
):
    outsider_user = manager_with_team["outsider_user"]
    outsider_employee = manager_with_team["outsider_employee"]
    await _report_to(db_session, outsider_employee.id, boss_employee)
    manager_user = manager_with_team["manager_user"]

    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, outsider_employee.id, leave_type, next_monday.year, allocated=10)

    outsider_token = await _login(client, outsider_user.email, demo_password)
    apply_response = await client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_type.id,
            "start_date": next_monday.isoformat(),
            "end_date": next_monday.isoformat(),
        },
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    request_id = apply_response.json()["data"]["id"]

    manager_token = await _login(client, manager_user.email, demo_password)
    approve_response = await client.patch(
        f"/api/v1/leaves/{request_id}/approve", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert approve_response.status_code == 403
    assert approve_response.json()["error_code"] == "LEAVE_APPROVAL_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_cannot_approve_outside_own_team(
    client: AsyncClient, boss_employee: Employee,
    manager_with_team: dict,
    admin_user: User,
    demo_password: str,
    db_session: AsyncSession,
    next_monday: date,
):
    # Regression test: ADMIN (and, by the same code path, HR) must not be
    # able to approve/reject leave for someone who isn't their direct
    # report. Approval authority is hierarchy-based only - see the note in
    # leave_service._authorize_decision.
    outsider_user = manager_with_team["outsider_user"]
    outsider_employee = manager_with_team["outsider_employee"]
    await _report_to(db_session, outsider_employee.id, boss_employee)

    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, outsider_employee.id, leave_type, next_monday.year, allocated=10)

    outsider_token = await _login(client, outsider_user.email, demo_password)
    apply_response = await client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_type.id,
            "start_date": next_monday.isoformat(),
            "end_date": next_monday.isoformat(),
        },
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    request_id = apply_response.json()["data"]["id"]

    admin_token = await _login(client, admin_user.email, demo_password)
    approve_response = await client.patch(
        f"/api/v1/leaves/{request_id}/approve", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert approve_response.status_code == 403
    assert approve_response.json()["error_code"] == "LEAVE_APPROVAL_FORBIDDEN"


@pytest.mark.asyncio
async def test_hr_can_approve_own_direct_reports_leave(
    client: AsyncClient,
    hr_employee_user: User,
    manager_with_team: dict,
    demo_password: str,
    db_session: AsyncSession,
    next_monday: date,
):
    """Some real HR staff genuinely manage people (the manager_id chain), not just oversee the
    company - leave:approve_team lets them act on their own reports' leave, exactly like any other
    manager. This isn't a blanket HR override: approval authority stays hierarchy-based only (see
    test_admin_cannot_approve_outside_own_team for the negative case, which still holds for HR too)."""
    from sqlalchemy import update

    from app.models.employee import Employee
    from app.repositories.employee_repository import EmployeeRepository

    hr_employee = await EmployeeRepository(db_session).get_by_user_id(hr_employee_user.id)
    report_user = manager_with_team["report_user"]
    report_employee = manager_with_team["report_employee"]

    # Make this HR employee the report's actual manager.
    await db_session.execute(
        update(Employee).where(Employee.id == report_employee.id).values(manager_id=hr_employee.id)
    )
    await db_session.flush()

    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, report_employee.id, leave_type, next_monday.year, allocated=10)

    report_token = await _login(client, report_user.email, demo_password)
    apply_response = await client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_type.id,
            "start_date": next_monday.isoformat(),
            "end_date": next_monday.isoformat(),
        },
        headers={"Authorization": f"Bearer {report_token}"},
    )
    assert apply_response.status_code == 201, apply_response.text
    request_id = apply_response.json()["data"]["id"]

    hr_token = await _login(client, hr_employee_user.email, demo_password)
    team_response = await client.get("/api/v1/leaves/team", headers={"Authorization": f"Bearer {hr_token}"})
    assert team_response.status_code == 200, team_response.text
    assert any(r["id"] == request_id for r in team_response.json()["data"]["items"])

    approve_response = await client.patch(
        f"/api/v1/leaves/{request_id}/approve", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["data"]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_hr_with_no_reports_sees_an_empty_team_list(client: AsyncClient, hr_employee_user: User, demo_password: str):
    """An HR login who isn't anyone's manager still reaches /leaves/team fine now that HR holds
    leave:approve_team - it's just empty, never a 403 or an error."""
    hr_token = await _login(client, hr_employee_user.email, demo_password)
    response = await client.get("/api/v1/leaves/team", headers={"Authorization": f"Bearer {hr_token}"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_overlapping_leave_request_rejected(
    client: AsyncClient, boss_employee: Employee, employee_user: User, demo_password: str, db_session: AsyncSession, next_monday: date
):
    leave_type = await _seed_leave_type(db_session)
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    await _report_to(db_session, employee.id, boss_employee)
    await _seed_balance(db_session, employee.id, leave_type, next_monday.year, allocated=20)

    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "leave_type_id": leave_type.id,
        "start_date": next_monday.isoformat(),
        "end_date": (next_monday + timedelta(days=2)).isoformat(),
    }
    first = await client.post("/api/v1/leaves", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/leaves",
        json={**payload, "start_date": (next_monday + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert second.status_code == 400
    assert second.json()["error_code"] == "OVERLAPPING_LEAVE_REQUEST"


@pytest.mark.asyncio
async def test_leave_days_follow_the_company_rule_sunday_off_saturday_working(
    client: AsyncClient, employee_user: User, demo_password: str, db_session: AsyncSession, boss_employee: Employee
):
    from app.models.holiday import Holiday
    from app.repositories.employee_repository import EmployeeRepository

    # A stretch of next year, so nothing here is ever "in the past".
    saturday = date(date.today().year + 1, 2, 1)
    while saturday.weekday() != 5:
        saturday += timedelta(days=1)
    sunday, monday, wednesday, thursday = (saturday + timedelta(days=n) for n in (1, 2, 4, 5))

    leave_type = await _seed_leave_type(db_session)
    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    await _report_to(db_session, employee.id, boss_employee)
    await _seed_balance(db_session, employee.id, leave_type, saturday.year, allocated=30)
    db_session.add_all(
        [
            Holiday(name="Optional Day", holiday_date=wednesday, is_optional=True),
            Holiday(name="Company Holiday", holiday_date=thursday, is_optional=False),
        ]
    )
    await db_session.flush()
    headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}

    async def apply(start: date, end: date):
        return await client.post(
            "/api/v1/leaves",
            json={"leave_type_id": leave_type.id, "start_date": start.isoformat(), "end_date": end.isoformat()},
            headers=headers,
        )

    # Sunday is the weekly holiday: a Sunday-only request has no working days.
    sunday_only = await apply(sunday, sunday)
    assert sunday_only.status_code == 400
    assert sunday_only.json()["error_code"] == "NO_WORKING_DAYS_SELECTED"

    # Saturday is a working day; Sat + Sun + Mon counts Saturday and Monday only.
    weekend = await apply(saturday, monday)
    assert weekend.status_code == 201, weekend.text
    assert weekend.json()["data"]["number_of_days"] == 2

    # An optional holiday is still a working day; a company holiday is not.
    holidays = await apply(wednesday, thursday)
    assert holidays.status_code == 201, holidays.text
    assert holidays.json()["data"]["number_of_days"] == 1


@pytest.mark.asyncio
async def test_leave_is_refused_when_nobody_could_ever_approve_it(
    client: AsyncClient,
    employee_user: User,
    demo_password: str,
    db_session: AsyncSession,
    next_monday: date,
):
    """Only a direct manager can decide on leave. With no manager set, a request would sit PENDING forever
    (and payroll counts undecided leave as absent), so applying is refused with a clear reason instead."""
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, employee.id, leave_type, next_monday.year, allocated=10)
    await db_session.execute(update(Employee).where(Employee.id == employee.id).values(manager_id=None))
    await db_session.flush()

    token = await _login(client, employee_user.email, demo_password)
    body = {"leave_type_id": leave_type.id, "start_date": next_monday.isoformat(), "end_date": next_monday.isoformat()}
    refused = await client.post("/api/v1/leaves", json=body, headers={"Authorization": f"Bearer {token}"})
    assert refused.status_code == 400
    assert refused.json()["error_code"] == "NO_LEAVE_APPROVER"


@pytest.mark.asyncio
async def test_founder_leave_is_approved_automatically_and_can_be_cancelled(
    client: AsyncClient,
    founder_user: User,
    demo_password: str,
    db_session: AsyncSession,
    next_monday: date,
):
    """The Founder has nobody above them, so their leave can't wait for a manager: it approves itself,
    uses up the balance exactly like a manager's approval would, and cancelling gives the days back."""
    from app.repositories.employee_repository import EmployeeRepository

    founder = await EmployeeRepository(db_session).get_by_user_id(founder_user.id)
    assert founder.manager_id is None
    leave_type = await _seed_leave_type(db_session)
    balance = await _seed_balance(db_session, founder.id, leave_type, next_monday.year, allocated=10)

    headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}
    applied = await client.post(
        "/api/v1/leaves",
        json={"leave_type_id": leave_type.id, "start_date": next_monday.isoformat(), "end_date": next_monday.isoformat()},
        headers=headers,
    )
    assert applied.status_code == 201, applied.text
    data = applied.json()["data"]
    assert data["status"] == "APPROVED"
    await db_session.refresh(balance)
    assert float(balance.used_days) == 1.0

    cancelled = await client.patch(f"/api/v1/leaves/{data['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    await db_session.refresh(balance)
    assert float(balance.used_days) == 0.0


@pytest.mark.asyncio
async def test_manager_is_told_when_a_report_applies_for_leave(
    client: AsyncClient, manager_with_team: dict, demo_password: str, db_session: AsyncSession, next_monday: date
):
    report_user = manager_with_team["report_user"]
    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, manager_with_team["report_employee"].id, leave_type, next_monday.year, allocated=10)

    report_token = await _login(client, report_user.email, demo_password)
    applied = await client.post(
        "/api/v1/leaves",
        json={"leave_type_id": leave_type.id, "start_date": next_monday.isoformat(), "end_date": next_monday.isoformat()},
        headers={"Authorization": f"Bearer {report_token}"},
    )
    assert applied.status_code == 201, applied.text

    manager_token = await _login(client, manager_with_team["manager_user"].email, demo_password)
    notes = (await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {manager_token}"})).json()["data"]["items"]
    requested = [n for n in notes if n["notification_type"] == "LEAVE_REQUESTED"]
    assert len(requested) == 1
    assert "Direct Report" in requested[0]["message"]


@pytest.mark.asyncio
async def test_waiting_requests_are_counted_so_leave_cannot_be_overdrawn(
    client: AsyncClient, manager_with_team: dict, demo_password: str, db_session: AsyncSession, next_monday: date
):
    """Two requests that each fit the balance on their own must not both get through: the first one's days
    are spoken for while it waits, so the second is refused instead of overdrawing the balance."""
    report_user = manager_with_team["report_user"]
    report_employee = manager_with_team["report_employee"]
    leave_type = await _seed_leave_type(db_session)
    balance = await _seed_balance(db_session, report_employee.id, leave_type, next_monday.year, allocated=3)

    headers = {"Authorization": f"Bearer {await _login(client, report_user.email, demo_password)}"}

    async def apply(day: date):
        return await client.post(
            "/api/v1/leaves",
            json={"leave_type_id": leave_type.id, "start_date": day.isoformat(), "end_date": (day + timedelta(days=1)).isoformat()},
            headers=headers,
        )

    first = await apply(next_monday)                              # Mon-Tue: 2 of the 3 days
    assert first.status_code == 201, first.text
    second = await apply(next_monday + timedelta(days=7))         # another 2 days: only 1 is left
    assert second.status_code == 400, second.text
    assert second.json()["error_code"] == "INSUFFICIENT_LEAVE_BALANCE"
    assert "already waiting" in second.json()["message"]

    # And approving re-checks the real balance: if it was used up some other way meanwhile, approval is refused.
    balance.used_days = 2
    await db_session.flush()
    manager_headers = {"Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"}
    refused = await client.patch(f"/api/v1/leaves/{first.json()['data']['id']}/approve", headers=manager_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["error_code"] == "INSUFFICIENT_LEAVE_BALANCE"
    await db_session.refresh(balance)
    assert float(balance.used_days) == 2.0


@pytest.mark.asyncio
async def test_company_wide_requests_say_whose_decision_they_wait_for(
    client: AsyncClient, manager_with_team: dict, admin_user: User, demo_password: str, db_session: AsyncSession, next_monday: date
):
    """The Admin can't decide leave, but can see who is holding a request up: each request carries its
    employee's manager name."""
    leave_type = await _seed_leave_type(db_session)
    await _seed_balance(db_session, manager_with_team["report_employee"].id, leave_type, next_monday.year, allocated=5)
    report_headers = {"Authorization": f"Bearer {await _login(client, manager_with_team['report_user'].email, demo_password)}"}
    body = {"leave_type_id": leave_type.id, "start_date": next_monday.isoformat(), "end_date": next_monday.isoformat()}
    assert (await client.post("/api/v1/leaves", json=body, headers=report_headers)).status_code == 201

    admin_headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    items = (await client.get("/api/v1/leaves/requests", headers=admin_headers)).json()["data"]["items"]
    assert [i["manager_name"] for i in items] == ["Test Manager"]
