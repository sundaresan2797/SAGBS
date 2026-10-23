import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_holiday_duplicate_date_conflicts(client: AsyncClient, admin_user, demo_password: str):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post(
        "/api/v1/holidays", json={"name": "New Year", "holiday_date": "2027-01-01"}, headers=headers
    )
    assert first.status_code == 201

    dup = await client.post(
        "/api/v1/holidays", json={"name": "Also New Year", "holiday_date": "2027-01-01"}, headers=headers
    )
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "HOLIDAY_DATE_EXISTS"


@pytest.mark.asyncio
async def test_manager_can_only_assign_tasks_to_direct_reports(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    manager_user = manager_with_team["manager_user"]
    report_employee = manager_with_team["report_employee"]
    outsider_employee = manager_with_team["outsider_employee"]

    token = await _login(client, manager_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    ok_response = await client.post(
        "/api/v1/tasks",
        json={"title": "Do the thing", "assigned_to": report_employee.id},
        headers=headers,
    )
    assert ok_response.status_code == 201

    forbidden_response = await client.post(
        "/api/v1/tasks",
        json={"title": "Should fail", "assigned_to": outsider_employee.id},
        headers=headers,
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error_code"] == "TASK_ASSIGNEE_OUT_OF_SCOPE"


@pytest.mark.asyncio
async def test_only_assignee_can_update_task_status(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    manager_user = manager_with_team["manager_user"]
    report_user = manager_with_team["report_user"]
    report_employee = manager_with_team["report_employee"]

    manager_token = await _login(client, manager_user.email, demo_password)
    create_response = await client.post(
        "/api/v1/tasks",
        json={"title": "Ship the feature", "assigned_to": report_employee.id},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    task_id = create_response.json()["data"]["id"]

    manager_update = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_update.status_code == 403
    assert manager_update.json()["error_code"] == "TASK_FORBIDDEN"

    report_token = await _login(client, report_user.email, demo_password)
    report_update = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": f"Bearer {report_token}"},
    )
    assert report_update.status_code == 200
    assert report_update.json()["data"]["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_team_tasks_due_date_range_filter(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    manager_user = manager_with_team["manager_user"]
    report_employee = manager_with_team["report_employee"]

    manager_token = await _login(client, manager_user.email, demo_password)
    headers = {"Authorization": f"Bearer {manager_token}"}

    await client.post(
        "/api/v1/tasks",
        json={"title": "Due this week", "assigned_to": report_employee.id, "due_date": "2027-03-10"},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Due next month", "assigned_to": report_employee.id, "due_date": "2027-04-15"},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/tasks/team",
        params={"due_date_from": "2027-03-01", "due_date_to": "2027-03-31"},
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Due this week"


@pytest.mark.asyncio
async def test_team_tasks_assigned_to_filter_cannot_leak_outsider(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    manager_user = manager_with_team["manager_user"]
    report_employee = manager_with_team["report_employee"]
    outsider_employee = manager_with_team["outsider_employee"]

    manager_token = await _login(client, manager_user.email, demo_password)
    headers = {"Authorization": f"Bearer {manager_token}"}

    await client.post(
        "/api/v1/tasks",
        json={"title": "My report's task", "assigned_to": report_employee.id},
        headers=headers,
    )

    # Filtering by an id that isn't actually a direct report should fall
    # back to the full (still hierarchy-scoped) team list, not error and
    # not leak the outsider's tasks.
    response = await client.get(
        "/api/v1/tasks/team", params={"assigned_to": outsider_employee.id}, headers=headers
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert all(item["assigned_to"] != outsider_employee.id for item in items)
    assert any(item["title"] == "My report's task" for item in items)


@pytest.mark.asyncio
async def test_task_comment_visible_to_assignee_and_assigner(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    manager_user = manager_with_team["manager_user"]
    report_user = manager_with_team["report_user"]
    outsider_user = manager_with_team["outsider_user"]
    report_employee = manager_with_team["report_employee"]

    manager_token = await _login(client, manager_user.email, demo_password)
    create_response = await client.post(
        "/api/v1/tasks",
        json={"title": "Review PR", "assigned_to": report_employee.id},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    task_id = create_response.json()["data"]["id"]

    report_token = await _login(client, report_user.email, demo_password)
    comment_response = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"comment": "On it"},
        headers={"Authorization": f"Bearer {report_token}"},
    )
    assert comment_response.status_code == 201

    outsider_token = await _login(client, outsider_user.email, demo_password)
    forbidden_response = await client.get(
        f"/api/v1/tasks/{task_id}/comments", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert forbidden_response.status_code == 403


@pytest.mark.asyncio
async def test_hr_staff_can_see_tasks_assigned_to_them(
    client: AsyncClient, db_session, hr_employee_user, manager_with_team: dict, demo_password: str
):
    from sqlalchemy import update

    from app.models.employee import Employee

    # HR staff are employees too: a task their manager assigns must show up under "My Tasks".
    hr_headers = {"Authorization": f"Bearer {await _login(client, hr_employee_user.email, demo_password)}"}
    hr_employee_id = (await client.get("/api/v1/employees/me", headers=hr_headers)).json()["data"]["id"]
    await db_session.execute(
        update(Employee)
        .where(Employee.id == hr_employee_id)
        .values(manager_id=manager_with_team["manager_employee"].id)
    )
    await db_session.flush()

    manager_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    created = await client.post(
        "/api/v1/tasks", json={"title": "Prepare onboarding pack", "assigned_to": hr_employee_id}, headers=manager_headers
    )
    assert created.status_code == 201, created.text

    response = await client.get("/api/v1/tasks/my", headers=hr_headers)
    assert response.status_code == 200, response.text
    titles = [t["title"] for t in response.json()["data"]["items"]]
    assert titles == ["Prepare onboarding pack"]


@pytest.mark.asyncio
async def test_hr_can_only_create_tasks_for_own_direct_reports(
    client: AsyncClient, db_session, hr_employee_user, manager_with_team: dict, demo_password: str
):
    """Some real HR staff genuinely manage people (the manager_id chain), not just oversee the
    company - task:create lets them assign to their own reports, exactly like any other manager.
    This isn't a blanket HR override: create_task's manager_id check still blocks anyone outside
    their own team, same as test_manager_can_only_assign_tasks_to_direct_reports."""
    from sqlalchemy import update

    from app.models.employee import Employee

    hr_headers = {"Authorization": f"Bearer {await _login(client, hr_employee_user.email, demo_password)}"}
    hr_employee_id = (await client.get("/api/v1/employees/me", headers=hr_headers)).json()["data"]["id"]
    report_employee = manager_with_team["report_employee"]
    outsider_employee = manager_with_team["outsider_employee"]

    await db_session.execute(
        update(Employee).where(Employee.id == report_employee.id).values(manager_id=hr_employee_id)
    )
    await db_session.flush()

    ok_response = await client.post(
        "/api/v1/tasks", json={"title": "Collect joining documents", "assigned_to": report_employee.id}, headers=hr_headers
    )
    assert ok_response.status_code == 201, ok_response.text

    forbidden_response = await client.post(
        "/api/v1/tasks", json={"title": "Should fail", "assigned_to": outsider_employee.id}, headers=hr_headers
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error_code"] == "TASK_ASSIGNEE_OUT_OF_SCOPE"


@pytest.mark.asyncio
async def test_founder_sees_every_company_task_via_team_tasks(
    client: AsyncClient, founder_user, manager_with_team: dict, demo_password: str
):
    """report:view widens /tasks/team to the whole company. The Founder fixture has
    zero direct reports of their own, so seeing this task at all proves the scope
    really is company-wide, not just "your team plus nothing"."""
    manager_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    created = await client.post(
        "/api/v1/tasks",
        json={"title": "Ship the report", "assigned_to": manager_with_team["report_employee"].id},
        headers=manager_headers,
    )
    assert created.status_code == 201, created.text

    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}
    response = await client.get("/api/v1/tasks/team", headers=founder_headers)
    assert response.status_code == 200, response.text
    titles = [t["title"] for t in response.json()["data"]["items"]]
    assert "Ship the report" in titles


@pytest.mark.asyncio
async def test_hr_sees_every_company_task_via_team_tasks(
    client: AsyncClient, hr_employee_user, manager_with_team: dict, demo_password: str
):
    """HR has report:view but, like Founder, no direct reports either - this only
    works now that HR also holds task:read_team (migration d6e2f8a4c913)."""
    manager_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    created = await client.post(
        "/api/v1/tasks",
        json={"title": "Prepare the audit", "assigned_to": manager_with_team["report_employee"].id},
        headers=manager_headers,
    )
    assert created.status_code == 201, created.text

    hr_headers = {"Authorization": f"Bearer {await _login(client, hr_employee_user.email, demo_password)}"}
    response = await client.get("/api/v1/tasks/team", headers=hr_headers)
    assert response.status_code == 200, response.text
    titles = [t["title"] for t in response.json()["data"]["items"]]
    assert "Prepare the audit" in titles


@pytest.mark.asyncio
async def test_plain_manager_is_not_widened_by_report_view(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    """A plain Manager (no report:view) must stay scoped to their own direct
    reports only - completely unaffected by the widening added for
    Founder/HR/Admin/Executive."""
    from app.models.enums import TaskStatus
    from app.models.task import Task

    # A task entirely outside the manager's team - self-assigned so it needs no
    # extra fixture, since the point is only that it exists and isn't theirs.
    outsider_task = Task(
        title="Not this manager's task",
        assigned_to=manager_with_team["outsider_employee"].id,
        assigned_by=manager_with_team["outsider_employee"].id,
        status=TaskStatus.TODO,
    )
    db_session.add(outsider_task)
    await db_session.flush()

    manager_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    response = await client.get("/api/v1/tasks/team", headers=manager_headers)
    assert response.status_code == 200, response.text
    titles = [t["title"] for t in response.json()["data"]["items"]]
    assert "Not this manager's task" not in titles


@pytest.mark.asyncio
async def test_anyone_who_can_see_a_task_can_open_it_but_only_its_two_people_can_comment(
    client: AsyncClient, db_session, hr_employee_user, boss_employee, manager_with_team: dict, demo_password: str
):
    """The Company Tasks board shows every task to people with report:view (and a manager sees their
    report's tasks), so opening a card has to work for them too - not just for the person it is for and
    the person who gave it. Commenting stays with those two."""
    from sqlalchemy import update

    from app.models.employee import Employee

    async def headers_for(email: str) -> dict:
        return {"Authorization": f"Bearer {await _login(client, email, demo_password)}"}

    manager_headers = await headers_for(manager_with_team["manager_user"].email)
    created = await client.post(
        "/api/v1/tasks",
        json={"title": "Reconcile the accounts", "assigned_to": manager_with_team["report_employee"].id},
        headers=manager_headers,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["data"]["id"]

    # HR holds report:view, so the task is on their Company Tasks board and opens.
    hr_headers = await headers_for(hr_employee_user.email)
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=hr_headers)).status_code == 200
    assert (await client.get(f"/api/v1/tasks/{task_id}/comments", headers=hr_headers)).status_code == 200
    # ...but reading is all they get: only the two people on the task may add comments.
    blocked = await client.post(f"/api/v1/tasks/{task_id}/comments", json={"comment": "hello"}, headers=hr_headers)
    assert blocked.status_code == 403

    # The assignee's direct manager (here not the person who gave the task) can open it too.
    await db_session.execute(
        update(Employee).where(Employee.id == manager_with_team["report_employee"].id).values(manager_id=boss_employee.id)
    )
    await db_session.flush()
    boss_headers = await headers_for("boss@example.org")
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=boss_headers)).status_code == 200

    # Someone with no connection to the task still cannot.
    outsider_headers = await headers_for(manager_with_team["outsider_user"].email)
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=outsider_headers)).status_code == 403
    assert (await client.get(f"/api/v1/tasks/{task_id}/comments", headers=outsider_headers)).status_code == 403


@pytest.mark.asyncio
async def test_holidays_cannot_change_in_a_month_where_payroll_already_ran(
    client: AsyncClient, db_session, admin_user, employee_user, demo_password: str
):
    """Payslips are fixed once payroll has run, so adding, moving, un-marking or deleting a holiday in that month
    would make the Attendance Summary disagree with them. Months with no payroll stay editable."""
    from datetime import date

    from app.models.enums import SalaryPaymentStatus
    from app.models.payroll import SalaryPayment
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    db_session.add(SalaryPayment(employee_id=employee.id, year=2025, month=3, amount=1000, status=SalaryPaymentStatus.PAID))
    await db_session.flush()

    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}

    blocked = await client.post("/api/v1/holidays", json={"name": "Late add", "holiday_date": "2025-03-14"}, headers=headers)
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error_code"] == "HOLIDAY_MONTH_PAYROLL_RUN"
    assert "March 2025" in blocked.json()["message"]

    free = await client.post("/api/v1/holidays", json={"name": "Open month", "holiday_date": "2027-05-01"}, headers=headers)
    assert free.status_code == 201, free.text
    holiday_id = free.json()["data"]["id"]

    # Moving an editable holiday INTO a paid month is refused too; renaming it is fine.
    moved = await client.put(f"/api/v1/holidays/{holiday_id}", json={"holiday_date": "2025-03-20"}, headers=headers)
    assert moved.status_code == 400 and moved.json()["error_code"] == "HOLIDAY_MONTH_PAYROLL_RUN"
    renamed = await client.put(f"/api/v1/holidays/{holiday_id}", json={"name": "May Day"}, headers=headers)
    assert renamed.status_code == 200, renamed.text
    assert (await client.delete(f"/api/v1/holidays/{holiday_id}", headers=headers)).status_code == 200

    # A holiday that already sits in a paid month can't be deleted or made optional.
    from app.models.holiday import Holiday
    old = Holiday(name="Old", holiday_date=date(2025, 3, 5), is_optional=False)
    db_session.add(old)
    await db_session.flush()
    assert (await client.delete(f"/api/v1/holidays/{old.id}", headers=headers)).status_code == 400
    flip = await client.put(f"/api/v1/holidays/{old.id}", json={"is_optional": True}, headers=headers)
    assert flip.status_code == 400 and flip.json()["error_code"] == "HOLIDAY_MONTH_PAYROLL_RUN"


@pytest.mark.asyncio
async def test_admin_without_an_employee_profile_can_load_the_company_board(
    client: AsyncClient, admin_user, manager_with_team: dict, demo_password: str
):
    """The Admin holds report:view (company-wide) but has no employee profile. The board never needs that profile
    for company-wide callers, so it must load - and a plain manager, who does need one, still gets only their team."""
    manager_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    created = await client.post(
        "/api/v1/tasks", json={"title": "Close the books", "assigned_to": manager_with_team["report_employee"].id}, headers=manager_headers
    )
    assert created.status_code == 201, created.text

    admin_headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    response = await client.get("/api/v1/tasks/team", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert [t["title"] for t in response.json()["data"]["items"]] == ["Close the books"]

    # Narrowing to one person works for the Admin too.
    one = await client.get(
        "/api/v1/tasks/team", params={"assigned_to": manager_with_team["report_employee"].id}, headers=admin_headers
    )
    assert one.status_code == 200 and one.json()["data"]["total"] == 1
