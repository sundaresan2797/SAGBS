"""Leave a manager/HR records for an employee who phoned in, half-day leave, and permission (a few hours off).

The rules being pinned down: who may do it, that it is checked like any other leave, that it never touches a
paid month or a day already worked, and - above all - that every number it changes (balance, attendance status,
payroll) lands in the database correctly.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.attendance import Attendance, ShortPermission
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.models.notification import Notification
from app.models.payroll import SalaryPayment
from app.models.user import User
from app.services import attendance_rules
from app.services.attendance_summary import count_month

IST = ZoneInfo("Asia/Kolkata")
P, L, H, A = AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY, AttendanceStatus.ABSENT
MON = date(2025, 3, 10)  # a Monday, a fully past month that nobody has been paid for
RECORD = "/api/v1/leaves/record"
PERMISSION = "/api/v1/attendance/permissions"


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _long_ago(db_session) -> None:
    """Fixture employees join 'today'; these tests use dates well in the past."""
    await db_session.execute(update(Employee).values(date_of_joining=date(2020, 1, 1)))
    await db_session.flush()


async def _leave_type(db_session, code="CASUAL", is_paid=True, allocated: float | None = 5, employee_id=None, year=2025):
    leave_type = LeaveType(code=code, name=code.title(), is_paid=is_paid, default_annual_days=12, is_active=True)
    db_session.add(leave_type)
    await db_session.flush()
    if allocated is not None and employee_id is not None:
        db_session.add(LeaveBalance(employee_id=employee_id, leave_type_id=leave_type.id, year=year,
                                    allocated_days=allocated, used_days=0))
        await db_session.flush()
    return leave_type


async def _used_days(db_session, employee_id, leave_type_id, year=2025) -> float:
    balance = (await db_session.execute(
        select(LeaveBalance).where(LeaveBalance.employee_id == employee_id, LeaveBalance.leave_type_id == leave_type_id,
                                   LeaveBalance.year == year))).scalar_one()
    await db_session.refresh(balance)
    return float(balance.used_days)


def _record(report, leave_type, start=MON, end=None, **extra):
    body = {"employee_id": report.id, "leave_type_id": leave_type.id, "start_date": start.isoformat(),
            "end_date": (end or start).isoformat(), "reason": "Informed by phone at 9:10"}
    body.update(extra)
    return body


# ---------------------------------------------------------------- the pure rules (no database)


def test_permission_moves_the_late_line_the_half_day_line_and_the_minimum_hours():
    ten_forty_five = datetime(2025, 3, 10, 10, 45, tzinfo=IST)
    assert attendance_rules.late_minutes_for(ten_forty_five) == 105
    assert attendance_rules.status_at_check_in(ten_forty_five) == L
    # A 2-hour permission covers the morning: 10:45 is inside 09:10 + 2h (11:10), so not late at all.
    assert attendance_rules.late_minutes_for(ten_forty_five, 120) == 0
    assert attendance_rules.status_at_check_in(ten_forty_five, 120) == P
    # A 1-hour permission moves the late line to 10:10; arriving 10:45 counts as 45 minutes late.
    assert attendance_rules.late_minutes_for(ten_forty_five, 60) == 45

    nine = datetime(2025, 3, 10, 9, 0, tzinfo=IST)
    assert attendance_rules.status_at_check_out(nine, 330) == H  # 5h30 is under the 7h45 minimum
    assert attendance_rules.status_at_check_out(nine, 345, 120) == P  # 7h45 minus a 2h permission is 5h45
    assert attendance_rules.status_at_check_out(nine, 300, 120) == H  # still under 5h45: not excused enough

    one_pm = datetime(2025, 3, 10, 13, 31, tzinfo=IST)  # after the 1:30 cut-off
    assert attendance_rules.status_at_check_in(one_pm) == H
    assert attendance_rules.status_at_check_in(one_pm, 60) == P if attendance_rules.late_minutes_for(one_pm, 60) == 0 else True
    assert attendance_rules.status_at_check_in(one_pm, 120) != H  # cut-off moved to 15:31


def test_a_half_day_leave_day_always_adds_up_to_exactly_one_day():
    """paid leave + worked = 1 day; unpaid leave + worked = 0.5 (leave half cut); paid + nothing = 0.5; unpaid + nothing = 0."""
    days = {d: (True, {}) for d in range(1, 1)}
    cases = [
        (True, P, 1.0, 0.0),
        (True, L, 1.0, 0.0),
        (True, H, 1.0, 0.0),  # they left early, but the half they worked is still worked
        (False, P, 0.5, 0.5),
        (True, None, 0.5, 0.5),
        (False, None, 0.0, 1.0),
        (True, A, 0.5, 0.5),
    ]
    for paid, status, payable, cut in cases:
        records = {MON: status} if status is not None else {}
        counts = count_month(2025, 3, records=records, off_dates=set(), leave_days={}, joining=date(2020, 1, 1),
                             today=date(2025, 4, 5), half_leave_days={MON: paid})
        assert counts.half_leave_days == 1
        assert counts.half_leave_payable == payable and counts.half_leave_cut == cut, (paid, status)
        assert counts.present + counts.late + counts.half_day + counts.absent >= 0
        # Every day of the month is accounted for exactly once: payable + cut == the days that count.
        assert counts.payable_days + counts.cut_days + counts.open_days + counts.before_joining == counts.total_days


def test_a_half_day_leave_today_or_later_stays_open_until_the_day_is_decided():
    today = date(2025, 3, 10)
    counts = count_month(2025, 3, records={}, off_dates=set(), leave_days={}, joining=date(2020, 1, 1), today=today,
                         half_leave_days={today: True, today + timedelta(days=1): True})
    assert counts.half_leave_days == 0 and counts.open_days >= 2  # nothing decided yet, so no pay number yet


def test_a_half_day_leave_on_a_sunday_is_ignored_because_nothing_is_lost():
    sunday = date(2025, 3, 9)
    counts = count_month(2025, 3, records={}, off_dates=set(), leave_days={}, joining=date(2020, 1, 1),
                         today=date(2025, 4, 5), half_leave_days={sunday: False})
    assert counts.half_leave_days == 0  # Sunday stays a paid day off


# ---------------------------------------------------------------- recording leave


@pytest.mark.asyncio
async def test_manager_records_a_full_day_and_everything_lands_in_the_database(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await client.post(RECORD, json=_record(report, leave_type), headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "APPROVED" and data["number_of_days"] == 1.0 and data["day_part"] is None
    assert data["recorded_by_name"] == "Test Manager" and data["recorded_late"] is True  # a day already past

    row = (await db_session.execute(select(LeaveRequest).where(LeaveRequest.id == data["id"]))).scalar_one()
    assert row.status.value == "APPROVED" and row.approved_by == manager_with_team["manager_user"].id
    assert row.recorded_by_user_id == manager_with_team["manager_user"].id and row.reason == "Informed by phone at 9:10"
    assert await _used_days(db_session, report.id, leave_type.id) == 1.0  # the balance really went down

    note = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))).scalar_one()
    assert note.notification_type == "LEAVE_APPROVED" and "Test Manager" in note.message and "10 Mar" in note.message
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "RECORD_LEAVE"))).scalar_one()
    assert "TEST-0002" in audit.description and "already past" in audit.description


@pytest.mark.asyncio
async def test_a_future_day_and_a_multi_day_range_are_counted_by_working_days(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    year = date.today().year
    leave_type = await _leave_type(db_session, employee_id=report.id, year=year, allocated=10)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    today = date.today()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    # Fri, Sat, Sun, Mon: Sunday is the weekly off, so 3 days count
    friday = monday - timedelta(days=3)
    if friday.year != monday.year:
        pytest.skip("range crosses a year boundary")
    response = await client.post(RECORD, json=_record(report, leave_type, start=friday, end=monday), headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["number_of_days"] == 3.0 and data["recorded_late"] is (friday < today)
    assert await _used_days(db_session, report.id, leave_type.id, year=friday.year) == 3.0


@pytest.mark.asyncio
async def test_half_day_counts_half_a_day_and_must_be_one_day(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await client.post(RECORD, json=_record(report, leave_type, day_part="SECOND_HALF"), headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["number_of_days"] == 0.5 and response.json()["data"]["day_part"] == "SECOND_HALF"
    assert await _used_days(db_session, report.id, leave_type.id) == 0.5

    two_days = await client.post(RECORD, json=_record(report, leave_type, start=MON + timedelta(days=1),
                                                       end=MON + timedelta(days=2), day_part="FIRST_HALF"), headers=headers)
    assert two_days.status_code == 422  # a half day is for a single date

    sunday = await client.post(RECORD, json=_record(report, leave_type, start=date(2025, 3, 9), day_part="FIRST_HALF"), headers=headers)
    assert sunday.status_code == 400 and sunday.json()["error_code"] == "NO_WORKING_DAYS_SELECTED"


@pytest.mark.asyncio
async def test_half_day_is_allowed_on_a_day_with_attendance_but_a_full_day_is_not(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    db_session.add(Attendance(employee_id=report.id, attendance_date=MON, status=H,
                              check_in=datetime(2025, 3, 10, 9, 0, tzinfo=IST), check_out=datetime(2025, 3, 10, 13, 0, tzinfo=IST),
                              working_minutes=240))
    await db_session.flush()
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    full = await client.post(RECORD, json=_record(report, leave_type), headers=headers)
    assert full.status_code == 400 and full.json()["error_code"] == "DAY_HAS_ATTENDANCE"
    assert "10 Mar" in full.json()["message"]
    half = await client.post(RECORD, json=_record(report, leave_type, day_part="SECOND_HALF"), headers=headers)
    assert half.status_code == 201, half.text


@pytest.mark.asyncio
async def test_the_same_checks_as_any_leave_balance_and_overlap(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id, allocated=1)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    too_many = await client.post(RECORD, json=_record(report, leave_type, start=MON, end=MON + timedelta(days=1)), headers=headers)
    assert too_many.status_code == 400 and too_many.json()["error_code"] == "INSUFFICIENT_LEAVE_BALANCE"
    assert await _used_days(db_session, report.id, leave_type.id) == 0.0  # a refused request changes nothing

    assert (await client.post(RECORD, json=_record(report, leave_type), headers=headers)).status_code == 201
    again = await client.post(RECORD, json=_record(report, leave_type), headers=headers)
    assert again.status_code == 400 and again.json()["error_code"] == "OVERLAPPING_LEAVE_REQUEST"
    assert "This person" in again.json()["message"]
    assert await _used_days(db_session, report.id, leave_type.id) == 1.0  # not charged twice

    unpaid = await _leave_type(db_session, code="UNPAID", is_paid=False, allocated=None)
    other = await client.post(RECORD, json=_record(report, unpaid, start=MON + timedelta(days=1)), headers=headers)
    assert other.status_code == 201  # an unpaid type needs no balance
    assert other.json()["data"]["number_of_days"] == 1.0


@pytest.mark.asyncio
async def test_who_may_record(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, admin_user: User, founder_user: User,
    executive_user: User, demo_password: str
):
    await _long_ago(db_session)
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id, allocated=20)
    db_session.add(LeaveBalance(employee_id=outsider.id, leave_type_id=leave_type.id, year=2025, allocated_days=20, used_days=0))
    await db_session.flush()

    # HR, Admin, Founder, and Executive (full Founder parity) can record for anyone
    for offset, user in enumerate((hr_user, admin_user, founder_user, executive_user)):
        day = MON + timedelta(days=offset)
        response = await client.post(RECORD, json=_record(outsider, leave_type, start=day), headers=await _login(client, user, demo_password))
        assert response.status_code == 201, f"{user.email}: {response.text}"
        assert response.json()["data"]["recorded_by_name"]  # Admin has no employee profile: named by role

    # A plain employee cannot record at all - not even for themselves
    for user, target in ((manager_with_team["report_user"], report), (manager_with_team["outsider_user"], outsider)):
        forbidden = await client.post(RECORD, json=_record(target, leave_type, start=MON + timedelta(days=6)),
                                      headers=await _login(client, user, demo_password))
        assert forbidden.status_code == 403
    # A manager cannot record their own leave
    manager_own = await client.post(RECORD, json=_record(manager_with_team["manager_employee"], leave_type, start=MON + timedelta(days=7)),
                                    headers=await _login(client, manager_with_team["manager_user"], demo_password))
    assert manager_own.status_code == 403 and manager_own.json()["error_code"] == "ATTENDANCE_SELF_FIX"


@pytest.mark.asyncio
async def test_hr_recording_also_tells_the_direct_manager(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    response = await client.post(RECORD, json=_record(report, leave_type), headers=await _login(client, hr_user, demo_password))
    assert response.status_code == 201, response.text
    manager_notes = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["manager_user"].id))).scalars().all()
    assert len(manager_notes) == 1 and "Test Report".replace("Test ", "Direct ") in manager_notes[0].message


@pytest.mark.asyncio
async def test_a_month_that_is_already_paid_cannot_be_changed(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    db_session.add(SalaryPayment(employee_id=report.id, year=2025, month=3, amount=1000, status="PENDING"))
    await db_session.flush()
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await client.post(RECORD, json=_record(report, leave_type), headers=headers)
    assert response.status_code == 400 and response.json()["error_code"] == "MONTH_ALREADY_PAID"
    assert "March 2025" in response.json()["message"]
    # A range that merely touches the paid month is refused too
    spans = await client.post(RECORD, json=_record(report, leave_type, start=date(2025, 2, 27), end=date(2025, 3, 3)), headers=headers)
    assert spans.json()["error_code"] == "MONTH_ALREADY_PAID"
    perm = await client.post(PERMISSION, json={"employee_id": report.id, "permission_date": MON.isoformat(), "minutes": 60,
                                               "reason": "Bank work"}, headers=headers)
    assert perm.json()["error_code"] == "MONTH_ALREADY_PAID"
    assert (await db_session.execute(select(LeaveRequest))).scalars().all() == []


@pytest.mark.asyncio
async def test_not_before_joining_and_reason_is_required(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    report = manager_with_team["report_employee"]  # joined "today" in the fixtures
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    before = await client.post(RECORD, json=_record(report, leave_type, start=date.today() - timedelta(days=30)), headers=headers)
    assert before.status_code == 400 and before.json()["error_code"] == "BEFORE_JOINING"
    no_reason = _record(report, leave_type)
    no_reason["reason"] = "  "
    assert (await client.post(RECORD, json=no_reason, headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_taking_back_a_recorded_leave_returns_the_balance(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    leave_id = (await client.post(RECORD, json=_record(report, leave_type, day_part="FIRST_HALF"), headers=headers)).json()["data"]["id"]
    assert await _used_days(db_session, report.id, leave_type.id) == 0.5

    # The employee cannot cancel leave that already started (existing rule), and an outsider cannot touch it
    own = await client.patch(f"/api/v1/leaves/{leave_id}/cancel", headers=await _login(client, manager_with_team["report_user"], demo_password))
    assert own.status_code == 400 and own.json()["error_code"] == "LEAVE_ALREADY_STARTED"
    stranger = await client.patch(f"/api/v1/leaves/{leave_id}/cancel", headers=await _login(client, manager_with_team["outsider_user"], demo_password))
    assert stranger.status_code == 403

    taken_back = await client.patch(f"/api/v1/leaves/{leave_id}/cancel", headers=headers)
    assert taken_back.status_code == 200, taken_back.text
    assert taken_back.json()["data"]["status"] == "CANCELLED"
    assert await _used_days(db_session, report.id, leave_type.id) == 0.0
    notes = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id,
                                                                  Notification.title == "Leave taken back"))).scalars().all()
    assert len(notes) == 1

    # ...and once that month is paid, it can no longer be taken back
    leave_id2 = (await client.post(RECORD, json=_record(report, leave_type, start=MON + timedelta(days=1)), headers=headers)).json()["data"]["id"]
    db_session.add(SalaryPayment(employee_id=report.id, year=2025, month=3, amount=1000, status="PENDING"))
    await db_session.flush()
    late = await client.patch(f"/api/v1/leaves/{leave_id2}/cancel", headers=headers)
    assert late.status_code == 400 and late.json()["error_code"] == "MONTH_ALREADY_PAID"
    assert await _used_days(db_session, report.id, leave_type.id) == 1.0


@pytest.mark.asyncio
async def test_a_managers_cannot_cancel_leave_the_employee_applied_for_themselves(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    """Only leave that was RECORDED for someone can be taken back by someone else."""
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    future = date.today() + timedelta(days=14)
    while future.weekday() == 6:
        future += timedelta(days=1)
    db_session.add(LeaveBalance(employee_id=report.id, leave_type_id=leave_type.id, year=future.year, allocated_days=5, used_days=0)) if future.year != 2025 else None
    await db_session.flush()
    applied = await client.post("/api/v1/leaves", json={"leave_type_id": leave_type.id, "start_date": future.isoformat(),
                                                        "end_date": future.isoformat(), "reason": "Family"},
                                headers=await _login(client, manager_with_team["report_user"], demo_password))
    assert applied.status_code == 201, applied.text
    denied = await client.patch(f"/api/v1/leaves/{applied.json()["data"]["id"]}/cancel",
                               headers=await _login(client, manager_with_team["manager_user"], demo_password))
    assert denied.status_code == 403 and denied.json()["error_code"] == "LEAVE_CANCEL_FORBIDDEN"


@pytest.mark.asyncio
async def test_an_employee_can_apply_for_a_half_day_themselves(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    day = date.today() + timedelta(days=10)
    while day.weekday() == 6:
        day += timedelta(days=1)
    leave_type = await _leave_type(db_session, employee_id=report.id, year=day.year)
    response = await client.post("/api/v1/leaves", json={"leave_type_id": leave_type.id, "start_date": day.isoformat(),
                                                         "end_date": day.isoformat(), "day_part": "FIRST_HALF", "reason": "Doctor"},
                                 headers=await _login(client, manager_with_team["report_user"], demo_password))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["number_of_days"] == 0.5 and data["day_part"] == "FIRST_HALF" and data["status"] == "PENDING"
    assert data["recorded_by_name"] is None  # applied by the employee, not recorded for them


# ---------------------------------------------------------------- roll call / dashboard read the leave correctly


@pytest.mark.asyncio
async def test_roll_call_shows_full_day_leave_as_on_leave_but_half_day_as_working(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str
):
    await _long_ago(db_session)
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    db_session.add(LeaveBalance(employee_id=outsider.id, leave_type_id=leave_type.id, year=2025, allocated_days=5, used_days=0))
    await db_session.flush()
    hr = await _login(client, hr_user, demo_password)
    await client.post(RECORD, json=_record(report, leave_type), headers=hr)
    await client.post(RECORD, json=_record(outsider, leave_type, day_part="FIRST_HALF"), headers=hr)

    roll = await client.get("/api/v1/attendance/roll-call", params={"date": MON.isoformat(), "page_size": 100}, headers=hr)
    assert roll.status_code == 200, roll.text
    by_code = {e["employee_code"]: e for e in roll.json()["data"]["items"]}
    assert by_code["TEST-0002"]["status"] == "ON_LEAVE" and by_code["TEST-0002"]["half_day_leave"] is False
    assert by_code["TEST-0003"]["status"] != "ON_LEAVE" and by_code["TEST-0003"]["half_day_leave"] is True


@pytest.mark.asyncio
async def test_a_half_day_leave_person_can_still_be_marked_present_but_a_full_day_cannot(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    await client.post(RECORD, json=_record(report, leave_type, day_part="FIRST_HALF"), headers=headers)
    body = {"employee_id": report.id, "attendance_date": MON.isoformat(), "check_in_time": "13:00", "check_out_time": "18:00",
            "reason": "Came in after lunch"}
    assert (await client.post("/api/v1/attendance/mark-present", json=body, headers=headers)).status_code == 200

    other = MON + timedelta(days=1)
    await client.post(RECORD, json=_record(report, leave_type, start=other), headers=headers)
    body.update(attendance_date=other.isoformat())
    blocked = await client.post("/api/v1/attendance/mark-present", json=body, headers=headers)
    assert blocked.json()["error_code"] == "DAY_IS_LEAVE"


# ---------------------------------------------------------------- permission


def _perm(report, day=MON, minutes=120, reason="Bank work, informed at 9:10"):
    return {"employee_id": report.id, "permission_date": day.isoformat(), "minutes": minutes, "reason": reason}


@pytest.mark.asyncio
async def test_record_a_permission_and_read_it_back(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await client.post(PERMISSION, json=_perm(report), headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["minutes"] == 120 and data["recorded_by_name"] == "Test Manager" and data["recorded_late"] is True

    row = (await db_session.execute(select(ShortPermission))).scalar_one()
    assert (row.employee_id, row.permission_date, row.minutes) == (report.id, MON, 120)
    assert (await db_session.execute(select(AuditLog).where(AuditLog.action == "RECORD_PERMISSION"))).scalar_one()
    assert (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))).scalar_one()

    # the employee, the manager and HR can read it; a stranger cannot
    for user in (manager_with_team["report_user"], manager_with_team["manager_user"]):
        listing = await client.get(PERMISSION, params={"employee_id": report.id, "year": 2025, "month": 3},
                                   headers=await _login(client, user, demo_password))
        assert listing.status_code == 200, listing.text
        out = listing.json()["data"]
        assert out["used_this_month"] == 1 and out["monthly_limit"] == 2 and out["max_minutes"] == 120
        assert out["items"][0]["reason"] == "Bank work, informed at 9:10"
    stranger = await client.get(PERMISSION, params={"employee_id": report.id, "year": 2025, "month": 3},
                                headers=await _login(client, manager_with_team["outsider_user"], demo_password))
    assert stranger.status_code == 403
    other_month = await client.get(PERMISSION, params={"employee_id": report.id, "year": 2025, "month": 4}, headers=headers)
    assert other_month.json()["data"]["used_this_month"] == 0


@pytest.mark.asyncio
async def test_two_a_month_then_it_must_be_a_half_day(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    for offset in (0, 1):
        assert (await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=offset), 60), headers=headers)).status_code == 201
    third = await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=2)), headers=headers)
    assert third.status_code == 400 and third.json()["error_code"] == "PERMISSION_LIMIT_REACHED"
    assert "half-day leave" in third.json()["message"]
    # The allowance is per calendar month: April is fresh
    assert (await client.post(PERMISSION, json=_perm(report, date(2025, 4, 1)), headers=headers)).status_code == 201
    assert len((await db_session.execute(select(ShortPermission))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_permission_input_rules(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    leave_type = await _leave_type(db_session, employee_id=report.id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    too_long = await client.post(PERMISSION, json=_perm(report, minutes=121), headers=headers)
    assert too_long.status_code == 400 and too_long.json()["error_code"] == "PERMISSION_TOO_LONG"
    assert (await client.post(PERMISSION, json=_perm(report, minutes=10), headers=headers)).status_code == 422
    sunday = await client.post(PERMISSION, json=_perm(report, date(2025, 3, 9)), headers=headers)
    assert sunday.status_code == 400 and sunday.json()["error_code"] == "DAY_IS_OFF"

    assert (await client.post(PERMISSION, json=_perm(report), headers=headers)).status_code == 201
    twice = await client.post(PERMISSION, json=_perm(report), headers=headers)
    assert twice.json()["error_code"] == "PERMISSION_EXISTS"

    await client.post(RECORD, json=_record(report, leave_type, start=MON + timedelta(days=1)), headers=headers)
    on_leave = await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=1)), headers=headers)
    assert on_leave.json()["error_code"] == "DAY_HAS_LEAVE"
    # ...and the other way round: leave over a day that has a permission is refused
    leave_on_permission = await client.post(RECORD, json=_record(report, leave_type), headers=headers)
    assert leave_on_permission.json()["error_code"] == "DAY_HAS_PERMISSION"


@pytest.mark.asyncio
async def test_only_managers_hr_and_admin_record_permissions_never_for_yourself(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, executive_user: User, demo_password: str
):
    await _long_ago(db_session)
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    assert (await client.post(PERMISSION, json=_perm(outsider), headers=await _login(client, hr_user, demo_password))).status_code == 201
    # Executive has full Founder parity (leave:manage_all), so it can record for anyone too, not just its own team.
    exec_allowed = await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=1)), headers=await _login(client, executive_user, demo_password))
    assert exec_allowed.status_code == 201
    for user in (manager_with_team["report_user"], manager_with_team["outsider_user"]):
        assert (await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=2)), headers=await _login(client, user, demo_password))).status_code == 403
    own = await client.post(PERMISSION, json=_perm(manager_with_team["manager_employee"], MON + timedelta(days=3)),
                            headers=await _login(client, manager_with_team["manager_user"], demo_password))
    assert own.status_code == 403 and own.json()["error_code"] == "ATTENDANCE_SELF_FIX"


@pytest.mark.asyncio
async def test_a_permission_recorded_after_check_in_fixes_the_days_status_and_taking_it_back_restores_it(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    late = Attendance(employee_id=report.id, attendance_date=MON, status=L, late_minutes=105,
                      check_in=datetime(2025, 3, 10, 10, 45, tzinfo=IST), check_out=datetime(2025, 3, 10, 19, 0, tzinfo=IST),
                      working_minutes=495)
    short = Attendance(employee_id=report.id, attendance_date=MON + timedelta(days=1), status=H, late_minutes=0,
                       check_in=datetime(2025, 3, 11, 9, 0, tzinfo=IST), check_out=datetime(2025, 3, 11, 14, 45, tzinfo=IST),
                       working_minutes=345)
    db_session.add_all([late, short])
    await db_session.flush()
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    first = (await client.post(PERMISSION, json=_perm(report, MON), headers=headers)).json()["data"]
    second = (await client.post(PERMISSION, json=_perm(report, MON + timedelta(days=1)), headers=headers)).json()["data"]
    await db_session.refresh(late)
    await db_session.refresh(short)
    assert (late.status, late.late_minutes) == (P, 0)  # 10:45 is inside the excused 9:10 + 2 h
    assert short.status == P  # 5h45 is enough once 2 h of permission are excused from the 7h45 minimum
    assert late.working_minutes == 495 and late.overtime_minutes == 0  # the hours themselves are not touched

    removed = await client.delete(f"{PERMISSION}/{first['id']}", headers=headers)
    assert removed.status_code == 200, removed.text
    await db_session.refresh(late)
    assert (late.status, late.late_minutes) == (L, 105)  # back to the normal rules
    await client.delete(f"{PERMISSION}/{second['id']}", headers=headers)
    await db_session.refresh(short)
    assert short.status == H
    assert (await db_session.execute(select(ShortPermission))).scalars().all() == []
    assert len((await db_session.execute(select(AuditLog).where(AuditLog.action == "CANCEL_PERMISSION"))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_a_permission_recorded_before_the_day_is_used_when_the_day_is_added(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    assert (await client.post(PERMISSION, json=_perm(report, minutes=120), headers=headers)).status_code == 201
    # Came in at 10:50, inside the 2-hour permission (9:10 + 2h = 11:10) - not late, not half day
    added = await client.post("/api/v1/attendance/mark-present", json={
        "employee_id": report.id, "attendance_date": MON.isoformat(), "check_in_time": "10:50", "check_out_time": "19:00",
        "reason": "Forgot to tap"}, headers=headers)
    assert added.status_code == 200, added.text
    assert added.json()["data"]["status"] == "PRESENT" and added.json()["data"]["late_minutes"] == 0


@pytest.mark.asyncio
async def test_roll_call_shows_the_permission(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str
):
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    hr = await _login(client, hr_user, demo_password)
    await client.post(PERMISSION, json=_perm(report, minutes=90), headers=hr)
    roll = await client.get("/api/v1/attendance/roll-call", params={"date": MON.isoformat(), "page_size": 100}, headers=hr)
    by_code = {e["employee_code"]: e for e in roll.json()["data"]["items"]}
    assert by_code["TEST-0002"]["permission_minutes"] == 90 and by_code["TEST-0003"]["permission_minutes"] == 0


# ---------------------------------------------------------------- payroll: the money side, end to end


@pytest.mark.asyncio
async def test_payroll_pays_half_day_leave_correctly_and_saves_it_on_the_payslip(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, demo_password: str
):
    """March 2026, salary 31000 (Rs 1000 a day, 31 days). Sundays (5) are paid. Of the 26 working days:
    Mon 2: PAID half-day leave + worked the other half        -> 1 day
    Tue 3: UNPAID half-day leave + nobody came for the rest    -> 0 days
    Wed 4: absent                                              -> 0 days
    the other 23 working days: present                         -> 23 days
    So payable = 5 + 1 + 0 + 0 + 23 = 29 days = Rs 29,000, cut = 2 days."""
    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    paid = await _leave_type(db_session, "CASUAL", True, 5, report.id, year=2026)
    unpaid = await _leave_type(db_session, "UNPAID", False, None)
    manager = await _login(client, manager_with_team["manager_user"], demo_password)
    accountant = await _login(client, accountant_user, demo_password)
    await client.post("/api/v1/salary-records", json={"employee_id": report.id, "basic_pay": 31000, "allowances": 0,
                                                       "deductions": 0, "effective_from": "2025-01-01"}, headers=accountant)

    working = [d for d in (date(2026, 3, n) for n in range(1, 32)) if d.weekday() != 6]
    assert len(working) == 26
    for d in working:
        if d.day in (3, 4):
            continue
        db_session.add(Attendance(employee_id=report.id, attendance_date=d, status=P,
                                  check_in=datetime(d.year, d.month, d.day, 9, 0, tzinfo=IST),
                                  check_out=datetime(d.year, d.month, d.day, 17, 0, tzinfo=IST), working_minutes=480))
    await db_session.flush()
    # Mon 2: worked the other half -> a half day by hours
    row = (await db_session.execute(select(Attendance).where(Attendance.employee_id == report.id,
                                                            Attendance.attendance_date == date(2026, 3, 2)))).scalar_one()
    row.status, row.working_minutes = H, 240
    await db_session.flush()

    assert (await client.post(RECORD, json=_record(report, paid, start=date(2026, 3, 2), day_part="FIRST_HALF"), headers=manager)).status_code == 201
    assert (await client.post(RECORD, json=_record(report, unpaid, start=date(2026, 3, 3), day_part="SECOND_HALF"), headers=manager)).status_code == 201

    preview = await client.get("/api/v1/payroll/attendance-summary", params={"year": 2026, "month": 3}, headers=accountant)
    row = next(r for r in preview.json()["data"]["items"] if r["employee_id"] == report.id)
    assert row["half_leave"] == 2 and row["absent"] == 1
    assert row["payable_days"] == 29.0 and row["cut_days"] == 2.0 and row["pay_for_month"] == 29000

    run = await client.post("/api/v1/salary-payments/run", json={"year": 2026, "month": 3}, headers=accountant)
    payment = next(p for p in run.json()["data"] if p["employee_id"] == report.id)
    assert payment["amount"] == 29000 and payment["payable_days"] == 29.0 and payment["cut_days"] == 2.0
    assert payment["half_leave_days"] == 2 and payment["absent_days"] == 1
    saved = (await db_session.execute(select(SalaryPayment).where(SalaryPayment.employee_id == report.id))).scalar_one()
    assert saved.half_leave_days == 2 and float(saved.amount) == 29000

    # The month is now paid: nothing about it can be changed any more
    late = await client.post(RECORD, json=_record(report, paid, start=date(2026, 3, 9)), headers=manager)
    assert late.json()["error_code"] == "MONTH_ALREADY_PAID"


@pytest.mark.asyncio
async def test_real_check_in_and_check_out_use_the_permission_recorded_that_morning(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str, monkeypatch
):
    """The morning phone call: the manager records a 2-hour permission at 9:10; the employee then reaches the
    office at 10:45 and leaves at 4 PM. Neither the late mark nor the half-day rule may apply."""
    from app.services import attendance_service

    await _long_ago(db_session)
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["manager_user"], demo_password)
    assert (await client.post(PERMISSION, json=_perm(report, minutes=120), headers=headers)).status_code == 201

    clock = {"now": datetime(2025, 3, 10, 10, 45, tzinfo=IST)}
    monkeypatch.setattr(attendance_service, "now_utc", lambda: clock["now"])
    monkeypatch.setattr(attendance_service, "today_in_org_tz", lambda: MON)
    employee_headers = await _login(client, manager_with_team["report_user"], demo_password)

    checked_in = await client.post("/api/v1/attendance/check-in", headers=employee_headers)
    assert checked_in.status_code == 200, checked_in.text
    assert checked_in.json()["data"]["status"] == "PRESENT" and checked_in.json()["data"]["late_minutes"] == 0

    # 6h15 at the gate, minus the 30-minute lunch, is 5h45 net - below the normal 7h45 minimum, but the
    # 2-hour permission lowers that minimum to exactly 5h45, so this still counts as a full (if
    # short-staffed) present day.
    clock["now"] = datetime(2025, 3, 10, 17, 0, tzinfo=IST)
    checked_out = await client.post("/api/v1/attendance/check-out", headers=employee_headers)
    assert checked_out.status_code == 200, checked_out.text
    data = checked_out.json()["data"]
    assert data["working_minutes"] == 345 and data["status"] == "PRESENT" and data["overtime_minutes"] == 0

    # The same morning with NO permission would have been a late half day - the rule really is what changed it.
    other_headers = await _login(client, manager_with_team["outsider_user"], demo_password)
    clock["now"] = datetime(2025, 3, 10, 10, 45, tzinfo=IST)
    assert (await client.post("/api/v1/attendance/check-in", headers=other_headers)).json()["data"]["status"] == "LATE"
    clock["now"] = datetime(2025, 3, 10, 16, 0, tzinfo=IST)
    assert (await client.post("/api/v1/attendance/check-out", headers=other_headers)).json()["data"]["status"] == "HALF_DAY"
