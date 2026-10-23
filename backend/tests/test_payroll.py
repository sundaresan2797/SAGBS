from datetime import date

import pytest
from httpx import AsyncClient

from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


async def _cover_whole_month_with_paid_leave(db_session, employee_id: int, year: int, month: int) -> None:
    """So attendance-based pay for that month comes out to the full salary - lets tests that are about
    something else (marking paid, downloading a payslip, permissions) keep a simple, round amount."""
    import calendar as _calendar
    from sqlalchemy import update

    from app.models.employee import Employee
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType

    await db_session.execute(update(Employee).where(Employee.id == employee_id).values(date_of_joining=date(2020, 1, 1)))
    leave_type = LeaveType(code=f"FULLPAY{year}{month}", name="Test paid leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    last_day = _calendar.monthrange(year, month)[1]
    db_session.add(LeaveRequest(
        employee_id=employee_id, leave_type_id=leave_type.id, start_date=date(year, month, 1),
        end_date=date(year, month, last_day), number_of_days=last_day, status=LeaveRequestStatus.APPROVED,
    ))
    await db_session.flush()


# A definitely-ended month, used wherever a test needs to actually run payroll for something other
# than testing the attendance-based math itself (that math has its own tests in test_salary_history.py).
ENDED_YEAR, ENDED_MONTH = 2025, 3



@pytest.mark.asyncio
async def test_employee_cannot_access_payroll_management_endpoints(
    client: AsyncClient, employee_user: User, demo_password: str
):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/salary-records", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/salary-payments", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/expenses", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_expense_claim_full_lifecycle(
    client: AsyncClient, accountant_user: User, employee_user: User, demo_password: str
):
    employee_token = await _login(client, employee_user.email, demo_password)
    submit_response = await client.post(
        "/api/v1/expenses",
        json={"category": "TRAVEL", "amount": 1500, "description": "Client site visit"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert submit_response.status_code == 201
    claim_id = submit_response.json()["data"]["id"]
    assert submit_response.json()["data"]["status"] == "PENDING"

    accountant_token = await _login(client, accountant_user.email, demo_password)
    accountant_headers = {"Authorization": f"Bearer {accountant_token}"}

    # Employee cannot approve their own claim - only payroll:manage holders can.
    forbidden_response = await client.patch(
        f"/api/v1/expenses/{claim_id}/approve", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert forbidden_response.status_code == 403

    approve_response = await client.patch(f"/api/v1/expenses/{claim_id}/approve", headers=accountant_headers)
    assert approve_response.status_code == 200
    assert approve_response.json()["data"]["status"] == "APPROVED"

    pay_response = await client.patch(f"/api/v1/expenses/{claim_id}/pay", headers=accountant_headers)
    assert pay_response.status_code == 200
    assert pay_response.json()["data"]["status"] == "PAID"
    assert pay_response.json()["data"]["paid_date"] is not None


@pytest.mark.asyncio
async def test_cannot_approve_already_decided_claim(
    client: AsyncClient, accountant_user: User, employee_user: User, demo_password: str
):
    employee_token = await _login(client, employee_user.email, demo_password)
    submit_response = await client.post(
        "/api/v1/expenses",
        json={"category": "FOOD", "amount": 500},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    claim_id = submit_response.json()["data"]["id"]

    accountant_token = await _login(client, accountant_user.email, demo_password)
    headers = {"Authorization": f"Bearer {accountant_token}"}

    reject_response = await client.patch(
        f"/api/v1/expenses/{claim_id}/reject", json={"rejection_reason": "Missing receipt"}, headers=headers
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["status"] == "REJECTED"

    second_approve = await client.patch(f"/api/v1/expenses/{claim_id}/approve", headers=headers)
    assert second_approve.status_code == 400
    assert second_approve.json()["error_code"] == "INVALID_CLAIM_STATUS"


@pytest.mark.asyncio
async def test_payroll_directory_lists_active_employees_with_details(
    client: AsyncClient, accountant_user: User, employee_user: User, demo_password: str
):
    accountant_token = await _login(client, accountant_user.email, demo_password)
    response = await client.get(
        "/api/v1/payroll/directory", headers={"Authorization": f"Bearer {accountant_token}"}
    )
    assert response.status_code == 200
    entries = response.json()["data"]
    entry = next(e for e in entries if e["employee_code"] == "TEST-0001")
    assert entry["full_name"] == "Test Employee"
    assert entry["role"] == "EMPLOYEE"
    assert entry["department"] == "Test Department"
    assert entry["designation"] == "Test Designation"

    # A plain employee (who lacks employee:read and payroll:manage) cannot
    # browse the directory, even though it's a lighter-weight endpoint than
    # the full employee list.
    employee_token = await _login(client, employee_user.email, demo_password)
    forbidden_response = await client.get(
        "/api/v1/payroll/directory", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert forbidden_response.status_code == 403


@pytest.mark.asyncio
async def test_payroll_cannot_be_run_until_the_month_has_ended(
    client: AsyncClient, accountant_user: User, employee_user: User, demo_password: str
):
    accountant_token = await _login(client, accountant_user.email, demo_password)
    headers = {"Authorization": f"Bearer {accountant_token}"}

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["employee_id"]
    await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 30000, "allowances": 0, "deductions": 0, "effective_from": "2026-01-01"},
        headers=headers,
    )

    today = date.today()
    future_year, future_month = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    future = await client.post(
        "/api/v1/salary-payments/run", json={"year": future_year, "month": future_month}, headers=headers
    )
    assert future.status_code == 400
    assert future.json()["error_code"] == "PAYROLL_MONTH_NOT_ENDED"

    # The CURRENT month, still in progress, is refused too - some of its days are not decided yet.
    current = await client.post(
        "/api/v1/salary-payments/run", json={"year": today.year, "month": today.month}, headers=headers
    )
    assert current.status_code == 400
    assert current.json()["error_code"] == "PAYROLL_MONTH_NOT_ENDED"


@pytest.mark.asyncio
async def test_salary_record_and_payroll_run(
    client: AsyncClient, db_session, accountant_user: User, employee_user: User, demo_password: str
):
    accountant_token = await _login(client, accountant_user.email, demo_password)
    headers = {"Authorization": f"Bearer {accountant_token}"}

    # Need the employee's numeric employee_id, not their user id.
    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["employee_id"]

    salary_response = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 40000, "allowances": 5000, "deductions": 2000, "effective_from": "2025-01-01"},
        headers=headers,
    )
    assert salary_response.status_code == 201
    assert salary_response.json()["data"]["net_pay"] == 43000.0
    await _cover_whole_month_with_paid_leave(db_session, employee_id, ENDED_YEAR, ENDED_MONTH)

    run_response = await client.post(
        "/api/v1/salary-payments/run", json={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=headers
    )
    assert run_response.status_code == 200, run_response.text
    payments = run_response.json()["data"]
    matching = next(p for p in payments if p["employee_id"] == employee_id)
    assert matching["amount"] == 43000.0  # a full month of paid leave = full salary
    assert matching["status"] == "PENDING"
    assert matching["total_days"] == 31 and matching["payable_days"] == 31 and matching["cut_days"] == 0
    assert matching["paid_leave_days"] + matching["days_off_days"] == 31

    pay_response = await client.patch(f"/api/v1/salary-payments/{matching['id']}/pay", headers=headers)
    assert pay_response.status_code == 200
    assert pay_response.json()["data"]["status"] == "PAID"

    # Running payroll again for the same month must not create a duplicate.
    rerun_response = await client.post(
        "/api/v1/salary-payments/run", json={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=headers
    )
    rerun_payments = [p for p in rerun_response.json()["data"] if p["employee_id"] == employee_id]
    assert len(rerun_payments) == 1
    assert rerun_payments[0]["status"] == "PAID"

    # The employee themselves can see their own payslip history and structure.
    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    my_record_response = await client.get("/api/v1/salary-records/my", headers=employee_headers)
    assert my_record_response.status_code == 200
    assert my_record_response.json()["data"]["net_pay"] == 43000.0

    my_payments_response = await client.get("/api/v1/salary-payments/my", headers=employee_headers)
    assert my_payments_response.status_code == 200
    my_items = my_payments_response.json()["data"]["items"]
    assert any(p["year"] == ENDED_YEAR and p["month"] == ENDED_MONTH and p["status"] == "PAID" for p in my_items)


@pytest.mark.asyncio
async def test_payslip_only_downloadable_once_paid_and_scoped_to_owner(
    client: AsyncClient, db_session, accountant_user: User, employee_user: User, manager_with_team: dict, demo_password: str
):
    accountant_token = await _login(client, accountant_user.email, demo_password)
    accountant_headers = {"Authorization": f"Bearer {accountant_token}"}

    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    me_response = await client.get("/api/v1/auth/me", headers=employee_headers)
    employee_id = me_response.json()["data"]["employee_id"]

    await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 40000, "allowances": 5000, "deductions": 2000, "effective_from": "2025-01-01"},
        headers=accountant_headers,
    )
    await _cover_whole_month_with_paid_leave(db_session, employee_id, ENDED_YEAR, ENDED_MONTH)
    run_response = await client.post(
        "/api/v1/salary-payments/run", json={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=accountant_headers
    )
    payment_id = next(p["id"] for p in run_response.json()["data"] if p["employee_id"] == employee_id)

    # Not paid yet - nobody can download it, even the accountant.
    pending_download = await client.get(
        f"/api/v1/salary-payments/{payment_id}/payslip", headers=accountant_headers
    )
    assert pending_download.status_code == 400
    assert pending_download.json()["error_code"] == "PAYSLIP_NOT_PAID"

    # A different employee (a manager, unrelated to this payment and without
    # payroll:view) cannot download someone else's payslip.
    other_headers = {
        "Authorization": f"Bearer {await _login(client, manager_with_team['manager_user'].email, demo_password)}"
    }
    await client.patch(f"/api/v1/salary-payments/{payment_id}/pay", headers=accountant_headers)
    scoped_response = await client.get(f"/api/v1/salary-payments/{payment_id}/payslip", headers=other_headers)
    assert scoped_response.status_code == 403
    assert scoped_response.json()["error_code"] == "PAYSLIP_OUT_OF_SCOPE"

    # Now that it's paid, the owning employee can download their own payslip.
    owner_response = await client.get(f"/api/v1/salary-payments/{payment_id}/payslip", headers=employee_headers)
    assert owner_response.status_code == 200
    assert owner_response.headers["content-type"] == "application/pdf"
    assert owner_response.content.startswith(b"%PDF")

    # And the accountant (payroll:view) can download anyone's payslip.
    accountant_response = await client.get(
        f"/api/v1/salary-payments/{payment_id}/payslip", headers=accountant_headers
    )
    assert accountant_response.status_code == 200
    assert accountant_response.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_employee_without_salary_record_gets_null_not_error(
    client: AsyncClient, employee_user: User, demo_password: str
):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.get("/api/v1/salary-records/my", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"] is None


@pytest.mark.asyncio
async def test_admin_cannot_access_payroll_but_founder_can(
    client: AsyncClient, admin_user: User, founder_user: User, demo_password: str
):
    admin_headers = {"Authorization": f"Bearer {await _login(client, admin_user.email, demo_password)}"}
    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}

    for path in ("/api/v1/salary-records", "/api/v1/salary-payments", "/api/v1/expenses", "/api/v1/payroll/directory"):
        assert (await client.get(path, headers=admin_headers)).status_code == 403, path
        assert (await client.get(path, headers=founder_headers)).status_code == 200, path


@pytest.mark.asyncio
async def test_executive_has_full_founder_parity_over_payroll(
    client: AsyncClient, db_session, executive_user: User, employee_user: User, demo_password: str
):
    # Executive is deliberately given full Founder parity (see migration b5f545e1a157): it can see AND
    # move money - set a salary, run payroll, mark a payment paid, approve/pay an expense claim - the
    # same way Founder can. Only the system-config/admin side (department, designation, user accounts,
    # role management) stays out of reach.
    executive_headers = {"Authorization": f"Bearer {await _login(client, executive_user.email, demo_password)}"}

    for path in ("/api/v1/salary-records", "/api/v1/salary-payments", "/api/v1/expenses", "/api/v1/payroll/directory"):
        assert (await client.get(path, headers=executive_headers)).status_code == 200, path
    attendance_summary = await client.get(
        "/api/v1/payroll/attendance-summary", params={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=executive_headers
    )
    assert attendance_summary.status_code == 200

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    )
    employee_id = me_response.json()["data"]["employee_id"]
    set_salary = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 40000, "allowances": 0, "deductions": 0, "effective_from": "2025-01-01"},
        headers=executive_headers,
    )
    assert set_salary.status_code == 201, set_salary.text

    await _cover_whole_month_with_paid_leave(db_session, employee_id, ENDED_YEAR, ENDED_MONTH)
    run_response = await client.post(
        "/api/v1/salary-payments/run", json={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=executive_headers
    )
    assert run_response.status_code == 200, run_response.text
    payment_id = next(p for p in run_response.json()["data"] if p["employee_id"] == employee_id)["id"]
    assert (await client.patch(f"/api/v1/salary-payments/{payment_id}/pay", headers=executive_headers)).status_code == 200

    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    claim_id = (await client.post(
        "/api/v1/expenses", json={"category": "FOOD", "amount": 250}, headers=employee_headers
    )).json()["data"]["id"]
    assert (await client.patch(f"/api/v1/expenses/{claim_id}/approve", headers=executive_headers)).status_code == 200
    assert (await client.patch(f"/api/v1/expenses/{claim_id}/pay", headers=executive_headers)).status_code == 200


@pytest.mark.asyncio
async def test_founder_can_run_payroll_and_download_any_payslip(
    client: AsyncClient, db_session, founder_user: User, employee_user: User, demo_password: str
):
    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}
    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    employee_id = (await client.get("/api/v1/auth/me", headers=employee_headers)).json()["data"]["employee_id"]

    set_response = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 20000, "allowances": 0, "deductions": 0, "effective_from": "2025-01-01"},
        headers=founder_headers,
    )
    assert set_response.status_code == 201, set_response.text
    await _cover_whole_month_with_paid_leave(db_session, employee_id, ENDED_YEAR, ENDED_MONTH)

    run = await client.post(
        "/api/v1/salary-payments/run", json={"year": ENDED_YEAR, "month": ENDED_MONTH}, headers=founder_headers
    )
    payment_id = next(p["id"] for p in run.json()["data"] if p["employee_id"] == employee_id)
    assert (await client.patch(f"/api/v1/salary-payments/{payment_id}/pay", headers=founder_headers)).status_code == 200

    payslip = await client.get(f"/api/v1/salary-payments/{payment_id}/payslip", headers=founder_headers)
    assert payslip.status_code == 200
    assert payslip.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_money_amounts_above_what_the_database_can_hold_are_a_clean_422(
    client: AsyncClient, employee_user: User, accountant_user: User, demo_password: str
):
    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}

    too_big = await client.post(
        "/api/v1/expenses", json={"category": "OTHER", "amount": 10_000_000_000}, headers=employee_headers
    )
    assert too_big.status_code == 422  # used to be a 500 from the database

    biggest_allowed = await client.post(
        "/api/v1/expenses", json={"category": "OTHER", "amount": 9_999_999_999.99}, headers=employee_headers
    )
    assert biggest_allowed.status_code == 201

    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    employee_id = (await client.get("/api/v1/auth/me", headers=employee_headers)).json()["data"]["employee_id"]
    salary = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 10_000_000_000, "effective_from": "2026-01-01"},
        headers=accountant_headers,
    )
    assert salary.status_code == 422


@pytest.mark.asyncio
async def test_unpaid_earlier_counts_only_pending_salary_from_before_the_given_month(
    client: AsyncClient, db_session, accountant_user: User, employee_user: User, demo_password: str
):
    """The dashboard's "Unpaid from earlier months" card: a month's own counts never show last month's
    forgotten payments, so this endpoint totals PENDING ones strictly before the month asked about -
    not the month itself, not later months, and never PAID ones."""
    from app.models.enums import SalaryPaymentStatus
    from app.models.payroll import SalaryPayment
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    for year, month, status, amount in [
        (2025, 12, SalaryPaymentStatus.PENDING, 1000),  # earlier year, unpaid - counts
        (2026, 1, SalaryPaymentStatus.PENDING, 250),  # earlier month, unpaid - counts
        (2026, 2, SalaryPaymentStatus.PAID, 999),  # earlier but paid - ignored
        (2026, 3, SalaryPaymentStatus.PENDING, 500),  # the month asked about - ignored
        (2026, 4, SalaryPaymentStatus.PENDING, 700),  # a later month - ignored
    ]:
        db_session.add(SalaryPayment(employee_id=employee.id, year=year, month=month, amount=amount, status=status))
    await db_session.flush()

    headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    response = await client.get("/api/v1/salary-payments/unpaid-earlier", params={"year": 2026, "month": 3}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"count": 2, "total_amount": 1250.0}

    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    forbidden = await client.get("/api/v1/salary-payments/unpaid-earlier", headers=employee_headers)
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_salary_cannot_be_marked_paid_until_its_month_has_ended(
    client: AsyncClient, db_session, accountant_user: User, employee_user: User, demo_password: str
):
    """Run Payroll already refuses a month that isn't over; marking a payment paid must follow the same
    rule, or an early/leftover row could be paid out while its amount is still changing."""
    from app.models.enums import SalaryPaymentStatus
    from app.models.payroll import SalaryPayment
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    today = date.today()
    running = SalaryPayment(employee_id=employee.id, year=today.year, month=today.month, amount=1000, status=SalaryPaymentStatus.PENDING)
    over = SalaryPayment(employee_id=employee.id, year=ENDED_YEAR, month=ENDED_MONTH, amount=1000, status=SalaryPaymentStatus.PENDING)
    db_session.add_all([running, over])
    await db_session.flush()

    headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    refused = await client.patch(f"/api/v1/salary-payments/{running.id}/pay", headers=headers)
    assert refused.status_code == 400
    assert refused.json()["error_code"] == "SALARY_MONTH_NOT_ENDED"

    allowed = await client.patch(f"/api/v1/salary-payments/{over.id}/pay", headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["status"] == "PAID"


@pytest.mark.asyncio
async def test_nobody_can_approve_or_reject_their_own_expense_claim(
    client: AsyncClient, accountant_user: User, founder_user: User, demo_password: str
):
    """The Accountant handles the company's money but can claim expenses like anyone else - someone
    else (here the Founder) must decide on it. Rejecting is a decision too, so it is blocked the same way."""
    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}

    async def submit() -> int:
        response = await client.post(
            "/api/v1/expenses", json={"category": "TRAVEL", "amount": 130}, headers=accountant_headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["id"]

    claim_id = await submit()
    for action in ("approve", "reject"):
        blocked = await client.patch(f"/api/v1/expenses/{claim_id}/{action}", json={}, headers=accountant_headers)
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["error_code"] == "EXPENSE_OWN_CLAIM"

    # Still pending after the refusals, and the Founder can decide on it.
    approved = await client.patch(f"/api/v1/expenses/{claim_id}/approve", headers=founder_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "APPROVED"

    # Paying an already-approved claim isn't a decision, so the Accountant may still do that.
    paid = await client.patch(f"/api/v1/expenses/{claim_id}/pay", headers=accountant_headers)
    assert paid.status_code == 200, paid.text


@pytest.mark.asyncio
async def test_nobody_can_mark_their_own_salary_as_paid(
    client: AsyncClient, db_session, accountant_user: User, founder_user: User, demo_password: str
):
    """The Accountant marks everyone's salary paid, but confirming their own pay needs a second person."""
    from app.models.enums import SalaryPaymentStatus
    from app.models.payroll import SalaryPayment
    from app.repositories.employee_repository import EmployeeRepository

    accountant_employee = await EmployeeRepository(db_session).get_by_user_id(accountant_user.id)
    own = SalaryPayment(
        employee_id=accountant_employee.id, year=ENDED_YEAR, month=ENDED_MONTH, amount=1000, status=SalaryPaymentStatus.PENDING
    )
    db_session.add(own)
    await db_session.flush()

    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    blocked = await client.patch(f"/api/v1/salary-payments/{own.id}/pay", headers=accountant_headers)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error_code"] == "SALARY_OWN_PAYMENT"

    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}
    allowed = await client.patch(f"/api/v1/salary-payments/{own.id}/pay", headers=founder_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["status"] == "PAID"


async def _notification_types(client: AsyncClient, email: str, password: str) -> list[str]:
    headers = {"Authorization": f"Bearer {await _login(client, email, password)}"}
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return [n["notification_type"] for n in response.json()["data"]["items"]]


@pytest.mark.asyncio
async def test_money_events_notify_the_right_people(
    client: AsyncClient, db_session, accountant_user: User, founder_user: User, employee_user: User, demo_password: str
):
    """Nobody should have to open a page to find out: the deciders hear about a new claim (not the person
    who sent it), and the employee hears when their claim is decided or paid and when their salary is paid."""
    from app.models.enums import SalaryPaymentStatus
    from app.models.payroll import SalaryPayment
    from app.repositories.employee_repository import EmployeeRepository

    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}

    async def send_claim() -> int:
        response = await client.post("/api/v1/expenses", json={"category": "FOOD", "amount": 250}, headers=employee_headers)
        assert response.status_code == 201, response.text
        return response.json()["data"]["id"]

    approved_id, rejected_id = await send_claim(), await send_claim()

    # Both people who decide on claims are told; the person who sent them is not.
    assert "EXPENSE_SUBMITTED" in await _notification_types(client, accountant_user.email, demo_password)
    assert "EXPENSE_SUBMITTED" in await _notification_types(client, founder_user.email, demo_password)
    assert "EXPENSE_SUBMITTED" not in await _notification_types(client, employee_user.email, demo_password)

    assert (await client.patch(f"/api/v1/expenses/{approved_id}/approve", headers=accountant_headers)).status_code == 200
    assert (await client.patch(f"/api/v1/expenses/{approved_id}/pay", headers=accountant_headers)).status_code == 200
    rejected = await client.patch(
        f"/api/v1/expenses/{rejected_id}/reject", json={"rejection_reason": "No receipt"}, headers=accountant_headers
    )
    assert rejected.status_code == 200, rejected.text

    listing = (await client.get("/api/v1/notifications", headers=employee_headers)).json()["data"]["items"]
    types = [n["notification_type"] for n in listing]
    assert {"EXPENSE_APPROVED", "EXPENSE_PAID", "EXPENSE_REJECTED"} <= set(types)
    assert any("No receipt" in n["message"] for n in listing if n["notification_type"] == "EXPENSE_REJECTED")

    # Salary paid -> the employee is told their payslip is ready.
    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    payment = SalaryPayment(
        employee_id=employee.id, year=ENDED_YEAR, month=ENDED_MONTH, amount=1000, status=SalaryPaymentStatus.PENDING
    )
    db_session.add(payment)
    await db_session.flush()
    assert (await client.patch(f"/api/v1/salary-payments/{payment.id}/pay", headers=accountant_headers)).status_code == 200
    assert "SALARY_PAID" in await _notification_types(client, employee_user.email, demo_password)


@pytest.mark.asyncio
async def test_nobody_can_set_their_own_salary(
    client: AsyncClient, db_session, accountant_user: User, founder_user: User, demo_password: str
):
    """Whoever sets everyone's pay can't set their own - someone else (here the Founder) does that."""
    from app.repositories.employee_repository import EmployeeRepository

    accountant_employee = await EmployeeRepository(db_session).get_by_user_id(accountant_user.id)
    body = {"employee_id": accountant_employee.id, "basic_pay": 30000, "allowances": 0, "deductions": 0, "effective_from": "2026-01-01"}

    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    blocked = await client.post("/api/v1/salary-records", json=body, headers=accountant_headers)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error_code"] == "SALARY_OWN_RECORD"

    founder_headers = {"Authorization": f"Bearer {await _login(client, founder_user.email, demo_password)}"}
    allowed = await client.post("/api/v1/salary-records", json=body, headers=founder_headers)
    assert allowed.status_code == 200 or allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_salary_cannot_have_deductions_above_earnings(
    client: AsyncClient, accountant_user: User, employee_user: User, demo_password: str
):
    """A structure whose deductions exceed basic pay plus allowances would give a negative payslip."""
    headers = {"Authorization": f"Bearer {await _login(client, accountant_user.email, demo_password)}"}
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"})
    employee_id = me.json()["data"]["employee_id"]

    too_much = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 10000, "allowances": 500, "deductions": 10600, "effective_from": "2026-01-01"},
        headers=headers,
    )
    assert too_much.status_code == 422, too_much.text

    exactly_equal = await client.post(
        "/api/v1/salary-records",
        json={"employee_id": employee_id, "basic_pay": 10000, "allowances": 500, "deductions": 10500, "effective_from": "2026-01-01"},
        headers=headers,
    )
    assert exactly_equal.status_code in (200, 201), exactly_equal.text
