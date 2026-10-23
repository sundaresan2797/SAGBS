import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_dashboard_summary_counts(client: AsyncClient, admin_user, employee_user, demo_password: str):
    token = await _login(client, admin_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_employees"] == 1
    assert data["active_employees"] == 1
    assert data["present_today"] == 0


@pytest.mark.asyncio
async def test_dashboard_forbidden_for_employee(client: AsyncClient, employee_user, demo_password: str):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.get(
        "/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_cache_invalidated_on_checkin(
    client: AsyncClient, admin_user, employee_user, demo_password: str
):
    admin_token = await _login(client, admin_user.email, demo_password)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    before = await client.get("/api/v1/dashboard/summary", headers=admin_headers)
    assert before.json()["data"]["present_today"] == 0

    employee_token = await _login(client, employee_user.email, demo_password)
    check_in = await client.post(
        "/api/v1/attendance/check-in", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert check_in.status_code == 200

    after = await client.get("/api/v1/dashboard/summary", headers=admin_headers)
    assert after.json()["data"]["present_today"] == 1


@pytest.mark.asyncio
async def test_department_headcounts(client: AsyncClient, admin_user, employee_user, demo_password: str, department):
    token = await _login(client, admin_user.email, demo_password)
    response = await client.get(
        "/api/v1/dashboard/departments", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    matching = next(d for d in response.json()["data"] if d["department_id"] == department.id)
    assert matching["employee_count"] == 1


@pytest.mark.asyncio
async def test_overdue_tasks_only_counts_pending_tasks_past_their_due_date(
    client: AsyncClient, admin_user, employee_user, demo_password: str, db_session
):
    from datetime import date, timedelta

    from app.models.task import Task
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    today = date.today()
    db_session.add_all([
        Task(title="overdue todo", assigned_to=employee.id, assigned_by=employee.id, status="TODO",
             due_date=today - timedelta(days=3)),
        Task(title="overdue blocked", assigned_to=employee.id, assigned_by=employee.id, status="BLOCKED",
             due_date=today - timedelta(days=1)),
        Task(title="due today - not overdue", assigned_to=employee.id, assigned_by=employee.id, status="IN_PROGRESS",
             due_date=today),
        Task(title="due in future", assigned_to=employee.id, assigned_by=employee.id, status="TODO",
             due_date=today + timedelta(days=5)),
        Task(title="no due date", assigned_to=employee.id, assigned_by=employee.id, status="TODO", due_date=None),
        Task(title="overdue but already done", assigned_to=employee.id, assigned_by=employee.id, status="COMPLETED",
             due_date=today - timedelta(days=10)),
    ])
    await db_session.flush()

    token = await _login(client, admin_user.email, demo_password)
    data = (await client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {token}"})).json()["data"]
    assert data["overdue_tasks"] == 2
    assert data["pending_tasks"] == 5  # the 2 overdue + due today + due in future + no due date (not the completed one)


@pytest.mark.asyncio
async def test_attendance_trend_counts_absent_and_on_leave_from_the_days_with_no_row(
    client: AsyncClient, db_session, admin_user, employee_user, demo_password: str
):
    """Absence and leave are never saved as attendance rows, so the chart works them out: on a working day,
    absent = people who had joined, minus present, minus on approved leave. Sundays have nobody absent."""
    from datetime import date, timedelta

    from sqlalchemy import update

    from app.models.attendance import Attendance
    from app.models.employee import Employee
    from app.models.enums import AttendanceStatus, LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    await db_session.execute(update(Employee).where(Employee.id == employee.id).values(date_of_joining=date.today() - timedelta(days=30)))

    def working_day(start: date) -> date:
        day = start
        while day.weekday() == 6:  # Sunday
            day -= timedelta(days=1)
        return day

    leave_day = working_day(date.today() - timedelta(days=2))
    present_day = working_day(leave_day - timedelta(days=1))
    sunday = next(date.today() - timedelta(days=n) for n in range(1, 8) if (date.today() - timedelta(days=n)).weekday() == 6)
    absent_day = working_day(present_day - timedelta(days=1))
    if absent_day in (leave_day, present_day):  # a Sunday pushed two picks together - use an earlier free day
        absent_day = working_day(present_day - timedelta(days=2))

    leave_type = LeaveType(code="TRENDX", name="Trend leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveRequest(employee_id=employee.id, leave_type_id=leave_type.id, start_date=leave_day, end_date=leave_day,
                                number_of_days=1, status=LeaveRequestStatus.APPROVED))
    db_session.add(Attendance(employee_id=employee.id, attendance_date=present_day, status=AttendanceStatus.PRESENT))
    await db_session.flush()

    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    response = await client.get("/api/v1/dashboard/attendance", params={"days": 14}, headers=headers)
    assert response.status_code == 200, response.text
    by_date = {p["date"]: p for p in response.json()["data"]}

    assert by_date[present_day.isoformat()]["present"] == 1
    assert by_date[present_day.isoformat()]["absent"] == 0
    assert by_date[leave_day.isoformat()]["on_leave"] == 1
    assert by_date[leave_day.isoformat()]["absent"] == 0
    assert by_date[absent_day.isoformat()]["absent"] == 1  # joined, no row, no leave
    assert by_date[sunday.isoformat()]["absent"] == 0  # a day off, nobody is expected in


@pytest.mark.asyncio
async def test_on_leave_card_counts_people_on_approved_leave_today(
    client: AsyncClient, db_session, admin_user, employee_user, demo_password: str
):
    from datetime import date

    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    leave_type = LeaveType(code="TODAYX", name="Today leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveRequest(employee_id=employee.id, leave_type_id=leave_type.id, start_date=date.today(), end_date=date.today(),
                                number_of_days=1, status=LeaveRequestStatus.APPROVED))
    await db_session.flush()

    headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    data = (await client.get("/api/v1/dashboard/summary", headers=headers)).json()["data"]
    assert data["employees_on_leave"] == 1
