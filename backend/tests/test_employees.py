import pytest
from httpx import AsyncClient

from app.models.department import Department
from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_create_and_get_department(client: AsyncClient, admin_user: User, demo_password: str):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post("/api/v1/departments", json={"name": "Engineering"}, headers=headers)
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Engineering"

    dup_response = await client.post("/api/v1/departments", json={"name": "engineering"}, headers=headers)
    assert dup_response.status_code == 409
    assert dup_response.json()["error_code"] == "DEPARTMENT_EXISTS"

    list_response = await client.get("/api/v1/departments", headers=headers)
    assert list_response.status_code == 200
    assert any(d["name"] == "Engineering" for d in list_response.json()["data"])


@pytest.mark.asyncio
async def test_department_requires_permission(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.post(
        "/api/v1/departments", json={"name": "New Dept"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_create_employee_provisions_login(
    client: AsyncClient, admin_user: User, demo_password: str, department: Department, designation
):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "first_name": "New",
            "last_name": "Hire",
            "email": "new.hire@example.org",
            "date_of_joining": "2025-01-01",
            "department_id": department.id,
            "designation_id": designation.id,
            "employment_type": "FULL_TIME",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["employee"]["employee_code"].startswith("EMP-")
    assert body["login_email"] == "new.hire@example.org"
    assert len(body["temporary_password"]) >= 8

    # The generated account should be able to log in immediately.
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": "new.hire@example.org", "password": body["temporary_password"]}
    )
    assert login_response.status_code == 200
    assert login_response.json()["data"]["user"]["must_change_password"] is True


@pytest.mark.asyncio
async def test_creating_employee_invalidates_department_headcount_cache(
    client: AsyncClient, admin_user: User, demo_password: str, department: Department, designation
):
    """A hire changes "Team size by department" on the Dashboard just as much as it changes
    total headcount - both caches must clear together (see _invalidate_employee_caches)."""
    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}

    before = await client.get("/api/v1/dashboard/departments", headers=headers)
    assert before.status_code == 200, before.text
    before_count = next(
        row["employee_count"] for row in before.json()["data"] if row["department_id"] == department.id
    )

    created = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "first_name": "Cache",
            "last_name": "Check",
            "email": "cache.check@example.org",
            "date_of_joining": "2025-01-01",
            "department_id": department.id,
            "designation_id": designation.id,
            "employment_type": "FULL_TIME",
        },
    )
    assert created.status_code == 201, created.text

    after = await client.get("/api/v1/dashboard/departments", headers=headers)
    assert after.status_code == 200, after.text
    after_count = next(
        row["employee_count"] for row in after.json()["data"] if row["department_id"] == department.id
    )
    assert after_count == before_count + 1


@pytest.mark.asyncio
async def test_list_employees_rejects_unrecognized_sort_field(
    client: AsyncClient, admin_user: User, demo_password: str
):
    """sort_by is an allow-list (Literal), not a bare str passed to getattr - an unrecognized
    field must fail cleanly with a 422, not reach the repository at all."""
    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}

    response = await client.get("/api/v1/employees", params={"sort_by": "hashed_password"}, headers=headers)
    assert response.status_code == 422

    ok_response = await client.get("/api/v1/employees", params={"sort_by": "first_name"}, headers=headers)
    assert ok_response.status_code == 200


@pytest.mark.asyncio
async def test_create_employee_duplicate_email_conflicts(
    client: AsyncClient, admin_user: User, demo_password: str, employee_user: User, department: Department, designation
):
    token = await _login(client, admin_user.email, demo_password)
    response = await client.post(
        "/api/v1/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Dup",
            "last_name": "Licate",
            "email": employee_user.email,
            "date_of_joining": "2025-01-01",
            "department_id": department.id,
            "designation_id": designation.id,
            "employment_type": "FULL_TIME",
        },
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_admin_can_create_accountant(
    client: AsyncClient, admin_user: User, demo_password: str, department: Department, designation
):
    token = await _login(client, admin_user.email, demo_password)
    response = await client.post(
        "/api/v1/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "New",
            "last_name": "Accountant",
            "email": "new.accountant@example.org",
            "date_of_joining": "2025-01-01",
            "department_id": department.id,
            "designation_id": designation.id,
            "employment_type": "FULL_TIME",
            "role": "ACCOUNTANT",
        },
    )
    assert response.status_code == 201, response.text

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "new.accountant@example.org", "password": response.json()["data"]["temporary_password"]},
    )
    assert login_response.status_code == 200
    assert login_response.json()["data"]["user"]["role"] == "ACCOUNTANT"


@pytest.mark.asyncio
async def test_hr_cannot_create_accountant(
    client: AsyncClient, hr_user: User, demo_password: str, department: Department, designation
):
    token = await _login(client, hr_user.email, demo_password)
    response = await client.post(
        "/api/v1/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Should",
            "last_name": "Fail",
            "email": "should.fail@example.org",
            "date_of_joining": "2025-01-01",
            "department_id": department.id,
            "designation_id": designation.id,
            "employment_type": "FULL_TIME",
            "role": "ACCOUNTANT",
        },
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ROLE_ASSIGNMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_employee_role_cannot_list_employees(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.get("/api/v1/employees", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manager_sees_only_direct_reports(client: AsyncClient, manager_with_team: dict, demo_password: str):
    manager_user = manager_with_team["manager_user"]
    report_employee = manager_with_team["report_employee"]
    outsider_employee = manager_with_team["outsider_employee"]

    token = await _login(client, manager_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    list_response = await client.get("/api/v1/employees", headers=headers)
    assert list_response.status_code == 200
    ids = {item["id"] for item in list_response.json()["data"]["items"]}
    assert report_employee.id in ids
    assert outsider_employee.id not in ids

    forbidden_response = await client.get(f"/api/v1/employees/{outsider_employee.id}", headers=headers)
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error_code"] == "EMPLOYEE_OUT_OF_SCOPE"

    allowed_response = await client.get(f"/api/v1/employees/{report_employee.id}", headers=headers)
    assert allowed_response.status_code == 200


@pytest.mark.asyncio
async def test_deactivating_employee_disables_login(
    client: AsyncClient, admin_user: User, demo_password: str, employee_user: User
):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    emp_token = await _login(client, employee_user.email, demo_password)
    me_response = await client.get("/api/v1/employees/me", headers={"Authorization": f"Bearer {emp_token}"})
    employee_id = me_response.json()["data"]["id"]

    status_response = await client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "TERMINATED"}, headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["status"] == "TERMINATED"

    relogin_response = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password}
    )
    assert relogin_response.status_code == 401
    assert relogin_response.json()["error_code"] == "ACCOUNT_INACTIVE"


@pytest.mark.asyncio
async def test_employee_can_update_own_phone_only(client: AsyncClient, employee_user: User, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.patch("/api/v1/employees/me", json={"phone": "9999999999"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["phone"] == "9999999999"


@pytest.mark.asyncio
async def test_admin_can_reset_employee_password(client: AsyncClient, admin_user: User, employee_user: User, demo_password: str):
    admin_token = await _login(client, admin_user.email, demo_password)

    me_response = await client.get(
        "/api/v1/employees/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["id"]

    reset_response = await client.post(
        f"/api/v1/employees/{employee_id}/reset-password",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_response.status_code == 200
    new_password = reset_response.json()["data"]["temporary_password"]
    assert reset_response.json()["data"]["login_email"] == employee_user.email
    assert len(new_password) >= 8

    # Old password no longer works; new one does.
    old_login = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password}
    )
    assert old_login.status_code == 401

    new_login = await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": new_password})
    assert new_login.status_code == 200
    assert new_login.json()["data"]["user"]["must_change_password"] is True


@pytest.mark.asyncio
async def test_admin_can_set_custom_password(client: AsyncClient, admin_user: User, employee_user: User, demo_password: str):
    admin_token = await _login(client, admin_user.email, demo_password)
    employee_token = await _login(client, employee_user.email, demo_password)
    me_response = await client.get("/api/v1/employees/me", headers={"Authorization": f"Bearer {employee_token}"})
    employee_id = me_response.json()["data"]["id"]

    reset_response = await client.post(
        f"/api/v1/employees/{employee_id}/reset-password",
        json={"new_password": "MyCustomPass123!"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["temporary_password"] == "MyCustomPass123!"

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": "MyCustomPass123!"}
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_cannot_reset_password(client: AsyncClient, manager_with_team: dict, demo_password: str):
    manager_token = await _login(client, manager_with_team["manager_user"].email, demo_password)
    report_employee = manager_with_team["report_employee"]

    response = await client.post(
        f"/api/v1/employees/{report_employee.id}/reset-password",
        json={},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_only_admin_can_create_a_founder_account(
    client: AsyncClient, admin_user: User, hr_user: User, demo_password: str, department: Department, designation
):
    payload = {
        "first_name": "New",
        "last_name": "Founder",
        "email": "new.founder@example.org",
        "date_of_joining": "2025-01-01",
        "department_id": department.id,
        "designation_id": designation.id,
        "employment_type": "FULL_TIME",
        "role": "FOUNDER",
    }
    hr_token = await _login(client, hr_user.email, demo_password)
    denied = await client.post("/api/v1/employees", json=payload, headers={"Authorization": f"Bearer {hr_token}"})
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "ROLE_ASSIGNMENT_FORBIDDEN"

    admin_token = await _login(client, admin_user.email, demo_password)
    created = await client.post("/api/v1/employees", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert created.status_code == 201, created.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "new.founder@example.org", "password": created.json()["data"]["temporary_password"]},
    )
    assert login.json()["data"]["user"]["role"] == "FOUNDER"


async def _admin_headers(client: AsyncClient, admin_user: User, demo_password: str) -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_a_manager_can_be_cleared_and_leaving_the_field_out_keeps_it(
    client: AsyncClient, admin_user: User, manager_with_team: dict, demo_password: str
):
    headers = await _admin_headers(client, admin_user, demo_password)
    report = manager_with_team["report_employee"]
    manager = manager_with_team["manager_employee"]

    kept = await client.put(f"/api/v1/employees/{report.id}", json={"work_location": "Head Office"}, headers=headers)
    assert kept.status_code == 200, kept.text
    assert kept.json()["data"]["manager"]["id"] == manager.id  # field left out -> unchanged

    cleared = await client.put(f"/api/v1/employees/{report.id}", json={"manager_id": None}, headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["manager"] is None  # explicit null -> no manager


@pytest.mark.asyncio
async def test_a_manager_loop_is_refused(client: AsyncClient, admin_user: User, manager_with_team: dict, demo_password: str):
    headers = await _admin_headers(client, admin_user, demo_password)
    manager = manager_with_team["manager_employee"]
    report = manager_with_team["report_employee"]

    # The manager already has this person under them - putting them above the manager would close a loop.
    loop = await client.put(f"/api/v1/employees/{manager.id}", json={"manager_id": report.id}, headers=headers)
    assert loop.status_code == 400, loop.text
    assert loop.json()["error_code"] == "MANAGER_LOOP"


@pytest.mark.asyncio
async def test_editing_keeps_the_job_title_inside_its_department(
    client: AsyncClient, db_session, admin_user: User, manager_with_team: dict, demo_password: str
):
    from app.models.department import Department
    from app.models.designation import Designation

    other_department = Department(name="Other Department")
    db_session.add(other_department)
    await db_session.flush()
    other_title = Designation(name="Other Title", department_id=other_department.id)
    db_session.add(other_title)
    await db_session.flush()

    headers = await _admin_headers(client, admin_user, demo_password)
    report = manager_with_team["report_employee"]

    only_department = await client.put(f"/api/v1/employees/{report.id}", json={"department_id": other_department.id}, headers=headers)
    assert only_department.status_code == 400, only_department.text
    assert only_department.json()["error_code"] == "DESIGNATION_DEPARTMENT_MISMATCH"

    both = await client.put(
        f"/api/v1/employees/{report.id}",
        json={"department_id": other_department.id, "designation_id": other_title.id},
        headers=headers,
    )
    assert both.status_code == 200, both.text


@pytest.mark.asyncio
async def test_someone_who_still_manages_people_cannot_be_deactivated(
    client: AsyncClient, admin_user: User, manager_with_team: dict, demo_password: str
):
    headers = await _admin_headers(client, admin_user, demo_password)
    manager = manager_with_team["manager_employee"]
    report = manager_with_team["report_employee"]

    blocked = await client.patch(f"/api/v1/employees/{manager.id}/status", json={"status": "TERMINATED"}, headers=headers)
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error_code"] == "EMPLOYEE_HAS_REPORTS"

    # Once nobody reports to them any more, it goes through.
    await client.put(f"/api/v1/employees/{report.id}", json={"manager_id": None}, headers=headers)
    allowed = await client.patch(f"/api/v1/employees/{manager.id}/status", json={"status": "TERMINATED"}, headers=headers)
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_department_list_carries_live_headcount_and_job_title_counts(
    client: AsyncClient, admin_user: User, manager_with_team: dict, department: Department, designation, demo_password: str
):
    headers = await _admin_headers(client, admin_user, demo_password)

    def mine(payload) -> dict:
        return next(d for d in payload if d["id"] == department.id)

    first = (await client.get("/api/v1/departments", headers=headers)).json()["data"]
    assert mine(first)["employee_count"] == 3  # the manager, their report and the outsider
    assert mine(first)["designation_count"] == 1

    # A person who leaves stops counting straight away - counts are never served from the cached list.
    report = manager_with_team["report_employee"]
    await client.put(f"/api/v1/employees/{report.id}", json={"manager_id": None}, headers=headers)
    await client.patch(f"/api/v1/employees/{report.id}/status", json={"status": "TERMINATED"}, headers=headers)
    after = (await client.get("/api/v1/departments", headers=headers)).json()["data"]
    assert mine(after)["employee_count"] == 2


@pytest.mark.asyncio
async def test_job_title_shows_live_people_count_and_cannot_move_department_while_held(
    client: AsyncClient, db_session, admin_user: User, manager_with_team: dict, department: Department, designation, demo_password: str
):
    from app.models.department import Department as DepartmentModel
    from app.models.designation import Designation

    headers = await _admin_headers(client, admin_user, demo_password)
    other_department = DepartmentModel(name="Elsewhere")
    db_session.add(other_department)
    await db_session.flush()

    listed = (await client.get("/api/v1/designations", headers=headers)).json()["data"]
    assert next(d for d in listed if d["id"] == designation.id)["employee_count"] == 3  # manager, report, outsider

    # Three people hold it, so it can't be moved to another department.
    blocked = await client.put(f"/api/v1/designations/{designation.id}", json={"department_id": other_department.id}, headers=headers)
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error_code"] == "DESIGNATION_IN_USE"

    # Renaming it, or moving a title nobody holds, is fine.
    renamed = await client.put(f"/api/v1/designations/{designation.id}", json={"name": "Renamed Title"}, headers=headers)
    assert renamed.status_code == 200, renamed.text
    unused = Designation(name="Nobody Has This", department_id=department.id)
    db_session.add(unused)
    await db_session.flush()
    moved = await client.put(f"/api/v1/designations/{unused.id}", json={"department_id": other_department.id}, headers=headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["department_id"] == other_department.id


@pytest.mark.asyncio
async def test_admin_can_reset_password_for_every_login_including_payroll_roles(
    client: AsyncClient, db_session, admin_user: User, founder_user: User, accountant_user: User, hr_employee_user: User,
    employee_user: User, demo_password: str,
):
    """Admin is the system's account administrator and can reset any login's password, including Founder,
    Accountant, and Executive - it still has no payroll permission itself (see employee_service.
    _may_manage_login_of), so it gains no access to salary data by doing this, only account-level control."""
    from app.repositories.employee_repository import EmployeeRepository

    headers = await _admin_headers(client, admin_user, demo_password)
    repo = EmployeeRepository(db_session)

    async def reset(user: User):
        employee = await repo.get_by_user_id(user.id)
        return await client.post(f"/api/v1/employees/{employee.id}/reset-password", json={}, headers=headers)

    for allowed in (founder_user, accountant_user, employee_user, hr_employee_user):
        assert (await reset(allowed)).status_code == 200, allowed.email

    rules = (await client.get("/api/v1/employees/login-rules", headers=headers)).json()["data"]
    assert rules["protected_roles"] == []
    assert "FOUNDER" in rules["assignable_roles"] and "MANAGER" in rules["assignable_roles"]


@pytest.mark.asyncio
async def test_admin_can_change_a_role_within_its_own_powers_and_it_takes_effect_after_sign_in(
    client: AsyncClient, db_session, admin_user: User, accountant_user: User, employee_user: User, demo_password: str
):
    from sqlalchemy import select

    from app.models.audit_log import AuditLog
    from app.repositories.employee_repository import EmployeeRepository

    headers = await _admin_headers(client, admin_user, demo_password)
    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    old_token = (await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password})).json()["data"]["access_token"]

    promoted = await client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "MANAGER"}, headers=headers)
    assert promoted.status_code == 200, promoted.text

    # The old session is ended, and signing in again gives the new role.
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})).status_code == 401
    relogin = await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password})
    assert relogin.json()["data"]["user"]["role"] == "MANAGER"

    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CHANGE_USER_ROLE"))).scalars().all()
    assert len(audit) == 1 and "EMPLOYEE to MANAGER" in audit[0].description

    # Refusals: same role, an unknown role. Admin can freely change roles to/from payroll-carrying roles too
    # (it's the system's account administrator - see employee_service._may_manage_login_of).
    same = await client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "MANAGER"}, headers=headers)
    assert same.status_code == 400 and same.json()["error_code"] == "ROLE_UNCHANGED"
    unknown = await client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "NOPE"}, headers=headers)
    assert unknown.status_code == 404
    to_payroll = await client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "ACCOUNTANT"}, headers=headers)
    assert to_payroll.status_code == 200, to_payroll.text
    accountant = await EmployeeRepository(db_session).get_by_user_id(accountant_user.id)
    from_payroll = await client.patch(f"/api/v1/employees/{accountant.id}/role", json={"role": "EMPLOYEE"}, headers=headers)
    assert from_payroll.status_code == 200, from_payroll.text


@pytest.mark.asyncio
async def test_only_someone_with_user_manage_can_change_roles(
    client: AsyncClient, hr_user: User, employee_user: User, db_session, demo_password: str
):
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    response = await client.post("/api/v1/auth/login", json={"email": hr_user.email, "password": demo_password})
    hr_headers = {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
    assert (await client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "MANAGER"}, headers=hr_headers)).status_code == 403
    assert (await client.get("/api/v1/employees/login-rules", headers=hr_headers)).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_correct_date_of_joining(client: AsyncClient, admin_user: User, demo_password: str, employee_user: User):
    """The joining date is a fact that must be fixable (a data-entry mistake, or first-time setup), but
    still never a future date - the same rule as when the employee was first created."""
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}
    emp_token = await _login(client, employee_user.email, demo_password)
    employee_id = (await client.get("/api/v1/employees/me", headers={"Authorization": f"Bearer {emp_token}"})).json()["data"]["id"]

    response = await client.put(
        f"/api/v1/employees/{employee_id}", json={"date_of_joining": "2020-01-15"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["date_of_joining"] == "2020-01-15"

    refetched = await client.get(f"/api/v1/employees/{employee_id}", headers=headers)
    assert refetched.json()["data"]["date_of_joining"] == "2020-01-15"  # the change really was saved, not just echoed back

    future = await client.put(
        f"/api/v1/employees/{employee_id}", json={"date_of_joining": "2999-01-01"}, headers=headers
    )
    assert future.status_code == 422

    unrelated = await client.put(f"/api/v1/employees/{employee_id}", json={"phone": "9998887777"}, headers=headers)
    assert unrelated.status_code == 200
    assert unrelated.json()["data"]["date_of_joining"] == "2020-01-15"  # untouched when the field is simply left out


@pytest.mark.asyncio
async def test_admin_can_change_login_email(client: AsyncClient, admin_user: User, employee_user: User, demo_password: str):
    # Captured up front: `employee_user` and the row the service loads are the same in-memory object in
    # this test (one shared session), so its .email attribute would silently follow the change otherwise.
    old_email = employee_user.email
    admin_token = await _login(client, admin_user.email, demo_password)
    employee_token = await _login(client, employee_user.email, demo_password)
    me_response = await client.get("/api/v1/employees/me", headers={"Authorization": f"Bearer {employee_token}"})
    employee_id = me_response.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/employees/{employee_id}/email",
        json={"new_email": "priya.selvam@sat.com"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["new_login_email"] == "priya.selvam@sat.com"

    # The old address no longer signs in, and the change forced their session to end...
    old_login = await client.post("/api/v1/auth/login", json={"email": old_email, "password": demo_password})
    assert old_login.status_code == 401

    # ...but the new address, same password, works.
    new_login = await client.post("/api/v1/auth/login", json={"email": "priya.selvam@sat.com", "password": demo_password})
    assert new_login.status_code == 200

    # Both the login and the employee record were updated, and their own profile now shows it.
    fresh_token = new_login.json()["data"]["access_token"]
    profile = await client.get("/api/v1/employees/me", headers={"Authorization": f"Bearer {fresh_token}"})
    assert profile.json()["data"]["email"] == "priya.selvam@sat.com"


@pytest.mark.asyncio
async def test_email_change_rejects_a_duplicate_or_unchanged_address(
    client: AsyncClient, admin_user: User, employee_user: User, manager_with_team: dict, demo_password: str
):
    original_email = employee_user.email
    admin_token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {admin_token}"}
    me_response = await client.get(
        "/api/v1/employees/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["id"]

    same = await client.patch(f"/api/v1/employees/{employee_id}/email", json={"new_email": original_email}, headers=headers)
    assert same.status_code == 400 and same.json()["error_code"] == "EMAIL_UNCHANGED"

    other_email = manager_with_team["report_user"].email
    taken = await client.patch(f"/api/v1/employees/{employee_id}/email", json={"new_email": other_email}, headers=headers)
    assert taken.status_code == 409 and taken.json()["error_code"] == "EMAIL_EXISTS"

    bad = await client.patch(f"/api/v1/employees/{employee_id}/email", json={"new_email": "not-an-email"}, headers=headers)
    assert bad.status_code == 422

    # None of the refused attempts changed anything.
    still_works = await client.post("/api/v1/auth/login", json={"email": original_email, "password": demo_password})
    assert still_works.status_code == 200


@pytest.mark.asyncio
async def test_email_change_is_admin_only_and_reaches_every_login(
    client: AsyncClient, db_session, admin_user: User, founder_user: User, accountant_user: User,
    manager_with_team: dict, demo_password: str,
):
    from app.repositories.employee_repository import EmployeeRepository

    admin_headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}

    # A manager (not user:manage) can't change anyone's login email, even their own report's.
    manager_headers = {"Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"}
    denied = await client.patch(
        f"/api/v1/employees/{manager_with_team['report_employee'].id}/email",
        json={"new_email": "someone@sat.com"}, headers=manager_headers,
    )
    assert denied.status_code == 403

    # Admin can change the email of any login, including ones that carry payroll powers it doesn't have
    # itself - it's the system's account administrator (see employee_service._may_manage_login_of).
    for offset, protected_user in enumerate((founder_user, accountant_user)):
        employee = await EmployeeRepository(db_session).get_by_user_id(protected_user.id)
        response = await client.patch(
            f"/api/v1/employees/{employee.id}/email", json={"new_email": f"new.address{offset}@sat.com"}, headers=admin_headers,
        )
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_email_change_is_audit_logged(client: AsyncClient, db_session, admin_user: User, employee_user: User, demo_password: str):
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    admin_headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    me_response = await client.get(
        "/api/v1/employees/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["id"]

    await client.patch(f"/api/v1/employees/{employee_id}/email", json={"new_email": "test.employee@sat.com"}, headers=admin_headers)

    entry = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CHANGE_USER_EMAIL"))).scalar_one()
    assert employee_user.email in entry.description and "test.employee@sat.com" in entry.description


@pytest.mark.asyncio
async def test_executive_has_full_founder_parity_for_the_staff_list_and_profile_detail(
    client: AsyncClient, db_session, roles, demo_password: str, department, designation
):
    """Executive is deliberately given full Founder parity (see migration b5f545e1a157): both the
    company-wide staff LIST and a stranger's full profile (phone, date of birth) are unrestricted, same
    as Founder/HR/Admin - unlike Manager, which stays scoped to itself and its direct reports."""
    from app.models.enums import RoleName
    from tests.conftest import _create_employee

    exec_user, exec_employee = await _create_employee(
        db_session, roles, demo_password, department, designation,
        email="ceo@example.org", role_name=RoleName.EXECUTIVE.value, employee_code="TEST-EXEC-01",
        first_name="Test", last_name="Exec",
    )
    report_user, report_employee = await _create_employee(
        db_session, roles, demo_password, department, designation,
        email="exec-report@example.org", role_name=RoleName.EMPLOYEE.value, employee_code="TEST-EXEC-02",
        first_name="Reports", last_name="ToExec", manager_id=exec_employee.id,
    )
    outsider_user, outsider_employee = await _create_employee(
        db_session, roles, demo_password, department, designation,
        email="exec-outsider@example.org", role_name=RoleName.EMPLOYEE.value, employee_code="TEST-EXEC-03",
        first_name="Not", last_name="OnTeam",
    )

    headers = {"Authorization": f"Bearer {await _login(client, exec_user.email, demo_password)}"}

    # The company-wide list is unrestricted for Executive - same as Founder.
    listed = await client.get("/api/v1/employees", headers=headers)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["data"]["items"]}
    assert outsider_employee.id in ids and report_employee.id in ids

    # A stranger's full profile, a direct report's, and their own are all fine - no scoping, unlike Manager.
    assert (await client.get(f"/api/v1/employees/{outsider_employee.id}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/employees/{report_employee.id}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/employees/{exec_employee.id}", headers=headers)).status_code == 200
