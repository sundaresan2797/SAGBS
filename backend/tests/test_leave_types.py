from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave import LeaveBalance, LeaveType
from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_create_leave_type_requires_permission(
    client: AsyncClient, employee_user: User, demo_password: str
):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.post(
        "/api/v1/leave-types",
        json={"code": "SABBATICAL", "name": "Sabbatical", "is_paid": True, "default_annual_days": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_executive_cannot_manage_leave_types(
    client: AsyncClient, executive_user: User, demo_password: str
):
    # A business-leadership account (e.g. CEO/COO) has hierarchy-based
    # authority over their own reports but no system-config permissions -
    # leave type administration stays HR/ADMIN-only.
    token = await _login(client, executive_user.email, demo_password)
    response = await client.post(
        "/api/v1/leave-types",
        json={"code": "EXECTEST", "name": "Exec Test", "is_paid": True, "default_annual_days": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_and_update_leave_type(
    client: AsyncClient, admin_user: User, demo_password: str
):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/leave-types",
        json={
            "code": "sabbatical",
            "name": "Sabbatical Leave",
            "is_paid": True,
            "default_annual_days": 30,
            "accrual_frequency": "ANNUAL",
        },
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    data = create_response.json()["data"]
    assert data["code"] == "SABBATICAL"
    assert data["is_active"] is True
    leave_type_id = data["id"]

    duplicate_response = await client.post(
        "/api/v1/leave-types",
        json={"code": "SABBATICAL", "name": "Duplicate", "is_paid": True, "default_annual_days": 5},
        headers=headers,
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error_code"] == "LEAVE_TYPE_EXISTS"

    update_response = await client.patch(
        f"/api/v1/leave-types/{leave_type_id}",
        json={"accrual_frequency": "MONTHLY", "default_annual_days": 12},
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["accrual_frequency"] == "MONTHLY"
    assert updated["default_annual_days"] == 12.0

    deactivate_response = await client.patch(
        f"/api/v1/leave-types/{leave_type_id}", json={"is_active": False}, headers=headers
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["data"]["is_active"] is False

    # A deactivated type drops out of the active list used by the apply-leave form...
    active_list = await client.get("/api/v1/leave-types", headers=headers)
    assert all(lt["id"] != leave_type_id for lt in active_list.json()["data"])

    # ...but still shows up in the management view for HR/Admin to reactivate later.
    all_list = await client.get("/api/v1/leave-types/all", headers=headers)
    assert any(lt["id"] == leave_type_id for lt in all_list.json()["data"])


@pytest.mark.asyncio
async def test_admin_can_delete_unused_leave_type(client: AsyncClient, admin_user: User, demo_password: str):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/leave-types",
        json={"code": "TEMP", "name": "Temp Leave", "is_paid": False, "default_annual_days": 0},
        headers=headers,
    )
    leave_type_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(f"/api/v1/leave-types/{leave_type_id}", headers=headers)
    assert delete_response.status_code == 200, delete_response.text

    all_list = await client.get("/api/v1/leave-types/all", headers=headers)
    assert all(lt["id"] != leave_type_id for lt in all_list.json()["data"])


@pytest.mark.asyncio
async def test_cannot_delete_leave_type_with_balances(
    client: AsyncClient, admin_user: User, employee_user: User, demo_password: str, db_session: AsyncSession
):
    leave_type = LeaveType(code="INUSE", name="In Use Leave", is_paid=True, default_annual_days=5, is_active=True)
    db_session.add(leave_type)
    await db_session.flush()

    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    db_session.add(
        LeaveBalance(employee_id=employee.id, leave_type_id=leave_type.id, year=date.today().year, allocated_days=5, used_days=0)
    )
    await db_session.flush()

    token = await _login(client, admin_user.email, demo_password)
    delete_response = await client.delete(
        f"/api/v1/leave-types/{leave_type.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 400
    assert delete_response.json()["error_code"] == "LEAVE_TYPE_IN_USE"


@pytest.mark.asyncio
async def test_monthly_accrual_prorates_by_elapsed_months(
    client: AsyncClient, employee_user: User, demo_password: str, db_session: AsyncSession
):
    # A monthly-accrual type with 12 days/year credits 1 day/month. An
    # employee who joined this calendar year only starts accruing from
    # their joining month, not from January.
    today = date.today()
    leave_type = LeaveType(
        code="MONTHLYTEST",
        name="Monthly Test Leave",
        is_paid=True,
        default_annual_days=12,
        accrual_frequency="MONTHLY",
        is_active=True,
    )
    db_session.add(leave_type)
    await db_session.flush()

    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    employee.date_of_joining = today.replace(day=1)
    await db_session.flush()

    token = await _login(client, employee_user.email, demo_password)
    response = await client.get("/api/v1/leaves/balance", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    balances = response.json()["data"]
    matching = next(b for b in balances if b["leave_type_id"] == leave_type.id)
    # Joined this month -> exactly 1 month has elapsed -> 1 day accrued.
    assert matching["allocated_days"] == 1.0
    assert matching["remaining_days"] == 1.0
    assert matching["accrual_frequency"] == "MONTHLY"


@pytest.mark.asyncio
async def test_paid_or_unpaid_is_locked_once_a_request_uses_the_type(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, manager_with_team: dict, demo_password: str
):
    """Paid or unpaid decides how every request already made is counted in payroll, so it can't be flipped
    once anyone has used the type. Renaming or changing the days stays allowed, and an unused type can flip."""
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest

    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    used = LeaveType(code="USEDTYPE", name="Used type", is_paid=True, default_annual_days=5, is_active=True)
    unused = LeaveType(code="FREETYPE", name="Free type", is_paid=True, default_annual_days=5, is_active=True)
    db_session.add_all([used, unused])
    await db_session.flush()
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    db_session.add(LeaveRequest(
        employee_id=manager_with_team["report_employee"].id, leave_type_id=used.id, start_date=monday, end_date=monday,
        number_of_days=1, status=LeaveRequestStatus.PENDING,
    ))
    await db_session.flush()

    flip = await client.patch(f"/api/v1/leave-types/{used.id}", json={"is_paid": False}, headers=headers)
    assert flip.status_code == 400, flip.text
    assert flip.json()["error_code"] == "LEAVE_TYPE_PAID_LOCKED"

    same = await client.patch(f"/api/v1/leave-types/{used.id}", json={"is_paid": True, "name": "Renamed", "default_annual_days": 8}, headers=headers)
    assert same.status_code == 200, same.text  # not a flip, so nothing is locked

    free = await client.patch(f"/api/v1/leave-types/{unused.id}", json={"is_paid": False}, headers=headers)
    assert free.status_code == 200, free.text
    assert free.json()["data"]["is_paid"] is False
