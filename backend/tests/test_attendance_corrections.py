"""Fixing a missed check-out, the missed list, the roll-call flag and the overtime summary."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus
from app.models.notification import Notification
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository

IST = ZoneInfo("Asia/Kolkata")
PAST = date(2025, 3, 10)  # a Monday
FIX = "/api/v1/attendance/{}/fix-check-out"


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _employee_id(db_session, user: User) -> int:
    return (await EmployeeRepository(db_session).get_by_user_id(user.id)).id


async def _open_day(db_session, employee_id: int, hour=9, minute=2, day: date = PAST, late=0, status=AttendanceStatus.PRESENT):
    """A day with a check-in and no check-out."""
    row = Attendance(
        employee_id=employee_id,
        attendance_date=day,
        check_in=datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST),
        late_minutes=late,
        status=status,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _fix(client, headers, row, time="18:10", reason="Forgot to tap, left at ten past six"):
    return await client.post(FIX.format(row.id), json={"check_out_time": time, "reason": reason}, headers=headers)


# ----- who may fix -----


@pytest.mark.asyncio
async def test_direct_manager_fixes_and_everything_is_recalculated(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    row = await _open_day(db_session, manager_with_team["report_employee"].id)
    headers = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await _fix(client, headers, row)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # 9:02 to 6:10 PM is 9h08m at the gate; minus the 30-minute lunch, 8h38m net. The office starts 9:00
    # with a 10-minute grace, so 9:02 is on time.
    assert data["working_minutes"] == 8 * 60 + 38
    assert data["overtime_minutes"] == 8
    assert data["status"] == "PRESENT"
    assert data["corrected_by_name"] == "Test Manager"
    assert data["correction_reason"] == "Forgot to tap, left at ten past six"
    assert data["corrected_at"] is not None

    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CORRECT_ATTENDANCE"))).scalars().all()
    assert len(audit) == 1 and "TEST-0002" in audit[0].description

    note = (
        await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))
    ).scalar_one()
    assert note.notification_type == "ATTENDANCE_CORRECTED" and "6:10 PM" in note.message

    # The corrected day is now a normal, complete record - and cannot be fixed twice.
    again = await _fix(client, headers, row)
    assert again.status_code == 400 and again.json()["error_code"] == "ALREADY_CHECKED_OUT"


@pytest.mark.asyncio
async def test_hr_admin_and_founder_can_fix_anyone(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, admin_user: User, founder_user: User,
    executive_user: User, demo_password: str,
):
    # The outsider is on nobody's team: only company-wide access can reach them. Executive has full
    # Founder parity (attendance:read_all), so it belongs in this company-wide group too.
    for offset, fixer in enumerate((hr_user, admin_user, founder_user, executive_user)):
        row = await _open_day(db_session, manager_with_team["outsider_employee"].id, day=PAST - timedelta(days=offset))
        response = await _fix(client, await _login(client, fixer, demo_password), row)
        assert response.status_code == 200, f"{fixer.email}: {response.text}"
        assert response.json()["data"]["correction_reason"]


@pytest.mark.asyncio
async def test_hours_count_from_the_minute_of_check_in(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    row = await _open_day(db_session, manager_with_team["report_employee"].id)
    row.check_in = datetime(2025, 3, 10, 19, 40, 30, tzinfo=IST)  # 7:40:30 PM
    await db_session.flush()
    response = await _fix(client, await _login(client, admin_user, demo_password), row, time="21:00")
    assert response.json()["data"]["working_minutes"] == 80  # 1h 20m, as the two clock times read


@pytest.mark.asyncio
async def test_others_cannot_fix(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User,
    demo_password: str,
):
    row = await _open_day(db_session, manager_with_team["report_employee"].id)

    # No attendance access at all
    for user in (accountant_user, manager_with_team["outsider_user"], manager_with_team["report_user"]):
        denied = await _fix(client, await _login(client, user, demo_password), row)
        assert denied.status_code == 403, user.email

    still_open = (await db_session.execute(select(Attendance).where(Attendance.id == row.id))).scalar_one()
    assert still_open.check_out is None


@pytest.mark.asyncio
async def test_nobody_fixes_their_own_record(
    client: AsyncClient, db_session, manager_with_team: dict, hr_employee_user: User, demo_password: str
):
    # A manager, and an HR person with full access, are both refused for their own day.
    for user, employee_id in (
        (manager_with_team["manager_user"], manager_with_team["manager_employee"].id),
        (hr_employee_user, await _employee_id(db_session, hr_employee_user)),
    ):
        row = await _open_day(db_session, employee_id)
        response = await _fix(client, await _login(client, user, demo_password), row)
        assert response.status_code == 403 and response.json()["error_code"] == "ATTENDANCE_SELF_FIX"


# ----- what is refused -----


@pytest.mark.asyncio
async def test_bad_fixes_are_refused_with_clear_errors(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    report_id = manager_with_team["report_employee"].id
    headers = await _login(client, admin_user, demo_password)

    early = await _open_day(db_session, report_id)
    response = await _fix(client, headers, early, time="08:30")
    assert response.status_code == 400 and response.json()["error_code"] == "CHECK_OUT_BEFORE_CHECK_IN"
    assert "9:02 AM" in response.json()["message"]
    assert (await _fix(client, headers, early, time="09:02")).status_code == 400  # same minute is not after

    assert (await _fix(client, headers, early, reason="  ")).status_code == 422
    assert (await _fix(client, headers, early, reason="ok")).status_code == 422
    assert (await _fix(client, headers, early, time="not-a-time")).status_code == 422

    no_check_in = Attendance(employee_id=manager_with_team["outsider_employee"].id, attendance_date=PAST,
                             status=AttendanceStatus.ABSENT)
    db_session.add(no_check_in)
    await db_session.flush()
    response = await _fix(client, headers, no_check_in)
    assert response.status_code == 400 and response.json()["error_code"] == "NO_CHECK_IN"

    missing = await client.post(FIX.format(999999), json={"check_out_time": "18:00", "reason": "reason"}, headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_today_cannot_be_fixed_because_the_employee_can_still_check_out(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    from app.utils.timezone import today_in_org_tz

    row = await _open_day(db_session, manager_with_team["report_employee"].id, day=today_in_org_tz())
    response = await _fix(client, await _login(client, admin_user, demo_password), row)
    assert response.status_code == 400 and response.json()["error_code"] == "DAY_NOT_OVER"


# ----- the same rules as a normal check-out -----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arrive, late, leave, status, overtime",
    [
        ((9, 0), 0, "12:30", "HALF_DAY", 0),  # 3.5 hours at the gate, before lunch even starts
        ((9, 25), 25, "17:45", "LATE", 0),  # late; 8h20m at the gate is 7h50m net of lunch - still a full day, no overtime
        ((8, 45), 0, "17:30", "PRESENT", 0),  # before the 9:00 start; 8h15 net of lunch - under the 8h30 standard shift, so no overtime
        ((13, 31), 271, "20:00", "HALF_DAY", 0),  # came after 1:30: half day however long they stay
    ],
)
async def test_fix_uses_the_normal_status_rules(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str,
    arrive, late, leave, status, overtime,
):
    row = await _open_day(db_session, manager_with_team["report_employee"].id, *arrive, late=late,
                          status=AttendanceStatus.LATE if late else AttendanceStatus.PRESENT)
    response = await _fix(client, await _login(client, admin_user, demo_password), row, time=leave)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == status
    assert response.json()["data"]["overtime_minutes"] == overtime


# ----- the missed list, the roll call and the calendar -----


@pytest.mark.asyncio
async def test_missed_list_scope_and_roll_call_flag(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, employee_user: User, demo_password: str
):
    from app.utils.timezone import today_in_org_tz

    report = manager_with_team["report_employee"]
    outsider = manager_with_team["outsider_employee"]
    await _open_day(db_session, report.id)  # missed, on the manager's team
    await _open_day(db_session, outsider.id)  # missed, not on the manager's team
    db_session.add(Attendance(employee_id=report.id, attendance_date=PAST + timedelta(days=1),
                              check_in=datetime(2025, 3, 11, 9, 0, tzinfo=IST), check_out=datetime(2025, 3, 11, 18, 0, tzinfo=IST),
                              working_minutes=540, status=AttendanceStatus.PRESENT))  # complete: not missed
    await _open_day(db_session, report.id, day=today_in_org_tz())  # today: not missed yet
    await db_session.flush()
    # The lookback is 60 days, so move the fixed old dates into range for the list checks.
    await db_session.execute(update(Attendance).where(Attendance.attendance_date == PAST)
                             .values(attendance_date=today_in_org_tz() - timedelta(days=3)))
    await db_session.flush()

    manager = await _login(client, manager_with_team["manager_user"], demo_password)
    admin = await _login(client, admin_user, demo_password)

    mine = (await client.get("/api/v1/attendance/missed-checkouts", headers=manager)).json()["data"]
    assert [m["employee_code"] for m in mine["items"]] == ["TEST-0002"]
    assert mine["total"] == 1
    everyone = (await client.get("/api/v1/attendance/missed-checkouts", headers=admin)).json()["data"]
    assert sorted(m["employee_code"] for m in everyone["items"]) == ["TEST-0002", "TEST-0003"]
    assert everyone["total"] == 2

    employee_headers = await _login(client, employee_user, demo_password)
    assert (await client.get("/api/v1/attendance/missed-checkouts", headers=employee_headers)).status_code == 403

    # Fixing removes it from the list
    fixed = await _fix(client, manager, (await db_session.execute(select(Attendance).where(
        Attendance.employee_id == report.id, Attendance.attendance_date == today_in_org_tz() - timedelta(days=3)))).scalar_one())
    assert fixed.status_code == 200
    after = (await client.get("/api/v1/attendance/missed-checkouts", headers=manager)).json()["data"]
    assert after == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_missed_check_outs_reports_true_total_even_when_the_list_is_capped(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str, monkeypatch
):
    """MISSED_CHECK_OUTS_LIMIT caps how many rows come back, but `total` must still say how many
    really exist - so the screen can say "showing N of TOTAL" instead of the list quietly looking
    complete when it isn't (see MissedCheckOutsPanel)."""
    from app.services import attendance_service
    from app.utils.timezone import today_in_org_tz

    monkeypatch.setattr(attendance_service, "MISSED_CHECK_OUTS_LIMIT", 2)

    report = manager_with_team["report_employee"]
    today = today_in_org_tz()
    for days_ago in (1, 2, 3):
        await _open_day(db_session, report.id, day=today - timedelta(days=days_ago))
    await db_session.flush()

    admin = await _login(client, admin_user, demo_password)
    data = (await client.get("/api/v1/attendance/missed-checkouts", headers=admin)).json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_roll_call_flags_missed_check_out_and_shows_overtime(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    row = await _open_day(db_session, manager_with_team["report_employee"].id)
    headers = await _login(client, admin_user, demo_password)

    def entry(data):
        return next(i for i in data["items"] if i["employee_id"] == manager_with_team["report_employee"].id)

    before = (await client.get("/api/v1/attendance/roll-call", params={"date": str(PAST)}, headers=headers)).json()["data"]
    assert entry(before)["missed_check_out"] is True

    await _fix(client, headers, row, time="18:30")
    after = (await client.get("/api/v1/attendance/roll-call", params={"date": str(PAST)}, headers=headers)).json()["data"]
    assert entry(after)["missed_check_out"] is False
    # 9:02 to 6:30 PM is 9h28m at the gate; minus the 30-minute lunch, 8h58m net - 28 minutes of overtime.
    assert entry(after)["overtime_minutes"] == 28


@pytest.mark.asyncio
async def test_calendar_shows_who_corrected_a_day(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    row = await _open_day(db_session, manager_with_team["report_employee"].id)
    manager = await _login(client, manager_with_team["manager_user"], demo_password)
    await _fix(client, manager, row)
    calendar = await client.get(
        f"/api/v1/attendance/employee/{manager_with_team['report_employee'].id}/calendar",
        params={"year": 2025, "month": 3}, headers=manager,
    )
    day = calendar.json()["data"][0]
    assert day["corrected_by_name"] == "Test Manager" and day["correction_reason"]


# ----- overtime summary (information only) -----


@pytest.mark.asyncio
async def test_overtime_summary_for_accountant_and_hr_only(
    client: AsyncClient, db_session, manager_with_team: dict, accountant_user: User, employee_user: User, demo_password: str
):
    report = manager_with_team["report_employee"]
    for day, overtime in ((date(2025, 3, 10), 60), (date(2025, 3, 11), 30), (date(2025, 4, 1), 500)):
        db_session.add(Attendance(employee_id=report.id, attendance_date=day, overtime_minutes=overtime,
                                  check_in=datetime(day.year, day.month, day.day, 9, tzinfo=IST),
                                  check_out=datetime(day.year, day.month, day.day, 19, tzinfo=IST),
                                  working_minutes=600, status=AttendanceStatus.PRESENT))
    db_session.add(Attendance(employee_id=manager_with_team["outsider_employee"].id, attendance_date=date(2025, 3, 10),
                              overtime_minutes=0, status=AttendanceStatus.PRESENT))
    await db_session.flush()

    headers = await _login(client, accountant_user, demo_password)
    march = (await client.get("/api/v1/attendance/overtime-summary", params={"year": 2025, "month": 3}, headers=headers)).json()["data"]
    assert march == [{"employee_id": report.id, "employee_code": "TEST-0002", "employee_name": "Direct Report",
                      "overtime_minutes": 90}]  # only March, only people who have some

    denied = await client.get("/api/v1/attendance/overtime-summary", params={"year": 2025, "month": 3},
                              headers=await _login(client, employee_user, demo_password))
    assert denied.status_code == 403


# ----- marking a whole forgotten day present -----

MARK = "/api/v1/attendance/mark-present"


async def _joined_long_ago(db_session) -> None:
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    await db_session.flush()


async def _mark(client, headers, employee_id, day=PAST, check_in="09:05", check_out="18:00", reason="Forgot to punch in, worked all day"):
    return await client.post(
        MARK,
        json={"employee_id": employee_id, "attendance_date": str(day), "check_in_time": check_in,
              "check_out_time": check_out, "reason": reason},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_manager_marks_a_forgotten_day_present(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    manager = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await _mark(client, manager, report.id, check_in="08:50")  # inside the grace period
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "PRESENT" and data["late_minutes"] == 0
    # 8:50 to 6:00 PM is 9h10m at the gate; minus the 30-minute lunch, 8h40m net - 10 minutes of overtime.
    assert data["working_minutes"] == 8 * 60 + 40 and data["overtime_minutes"] == 10
    assert data["corrected_by_name"] == "Test Manager" and "Forgot to punch in" in data["correction_reason"]

    note = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))).scalar_one()
    assert "recorded you as working" in note.message
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CORRECT_ATTENDANCE"))).scalars().all()
    assert len(audit) == 1

    # The day now counts as worked in the roll call, and cannot be added twice.
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    roll = (await client.get("/api/v1/attendance/roll-call", params={"date": str(PAST)},
                             headers=await _login(client, admin_user, demo_password))).json()["data"]
    assert next(i for i in roll["items"] if i["employee_id"] == report.id)["status"] == "PRESENT"
    again = await _mark(client, manager, report.id)
    assert again.status_code == 400 and again.json()["error_code"] == "DAY_HAS_CHECK_IN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "check_in, check_out, status, late",
    [("09:30", "17:45", "LATE", 30), ("09:00", "12:30", "HALF_DAY", 0), ("13:00", "20:00", "HALF_DAY", 240)],
)
async def test_marked_days_use_the_normal_rules(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str,
    check_in, check_out, status, late,
):
    await _joined_long_ago(db_session)
    response = await _mark(client, await _login(client, admin_user, demo_password),
                           manager_with_team["report_employee"].id, check_in=check_in, check_out=check_out)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == status and response.json()["data"]["late_minutes"] == late


@pytest.mark.asyncio
async def test_an_existing_absent_row_is_filled_in(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    db_session.add(Attendance(employee_id=report.id, attendance_date=PAST, status=AttendanceStatus.ABSENT))
    await db_session.flush()
    response = await _mark(client, await _login(client, admin_user, demo_password), report.id, check_in="08:50")
    assert response.status_code == 200
    rows = (await db_session.execute(select(Attendance).where(Attendance.employee_id == report.id))).scalars().all()
    assert len(rows) == 1 and rows[0].status == AttendanceStatus.PRESENT  # updated, not duplicated


@pytest.mark.asyncio
async def test_only_the_right_people_can_mark_present(
    client: AsyncClient, db_session, manager_with_team: dict, executive_user: User, accountant_user: User,
    hr_employee_user: User, hr_user: User, founder_user: User, demo_password: str,
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    for user in (accountant_user, manager_with_team["outsider_user"], manager_with_team["report_user"]):
        assert (await _mark(client, await _login(client, user, demo_password), report.id)).status_code == 403

    # Nobody adds a day for themselves - not even HR with full access
    own = await _mark(client, await _login(client, hr_employee_user, demo_password), await _employee_id(db_session, hr_employee_user))
    assert own.status_code == 403 and own.json()["error_code"] == "ATTENDANCE_SELF_FIX"

    # Executive has full Founder parity (attendance:read_all), so it joins the company-wide group.
    for offset, user in enumerate((hr_user, founder_user, executive_user)):  # company-wide access reaches anyone
        outsider = manager_with_team["outsider_employee"]
        assert (await _mark(client, await _login(client, user, demo_password), outsider.id,
                            day=PAST - timedelta(days=offset))).status_code == 200


@pytest.mark.asyncio
async def test_bad_mark_present_requests_are_refused(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType
    from app.utils.timezone import today_in_org_tz

    report = manager_with_team["report_employee"]
    headers = await _login(client, admin_user, demo_password)

    today = await _mark(client, headers, report.id, day=today_in_org_tz())
    assert today.status_code == 400 and today.json()["error_code"] == "DAY_NOT_OVER"
    future = await _mark(client, headers, report.id, day=today_in_org_tz() + timedelta(days=2))
    assert future.status_code == 400

    # fixtures create people as "joined today", so an earlier day is before joining
    before = await _mark(client, headers, report.id)
    assert before.status_code == 400 and before.json()["error_code"] == "BEFORE_JOINING"

    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    await db_session.flush()
    backwards = await _mark(client, headers, report.id, check_in="18:00", check_out="09:00")
    assert backwards.status_code == 400 and backwards.json()["error_code"] == "CHECK_OUT_BEFORE_CHECK_IN"
    assert (await _mark(client, headers, report.id, reason="  ")).status_code == 422
    assert (await _mark(client, headers, 999999)).status_code == 404

    leave_type = LeaveType(code="MARKTEST", name="Test leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=PAST, end_date=PAST,
                                number_of_days=1, status=LeaveRequestStatus.APPROVED))
    await db_session.flush()
    on_leave = await _mark(client, headers, report.id)
    assert on_leave.status_code == 400 and on_leave.json()["error_code"] == "DAY_IS_LEAVE"


@pytest.mark.asyncio
async def test_an_admin_fix_is_named_by_role_not_by_email(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    """The Admin has no employee profile, so there is no name to show: the saved "corrected by" name and the
    message to the employee say "Admin", not the login's email address."""
    row = await _open_day(db_session, manager_with_team["outsider_employee"].id)
    response = await _fix(client, await _login(client, admin_user, demo_password), row)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["corrected_by_name"] == "Admin"

    note = (
        await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["outsider_user"].id))
    ).scalar_one()
    assert note.message.startswith("Admin set your check-out")
    assert "@" not in note.message


# ----- correcting an already-recorded day (Present/Late/Half day -> different times, or Absent) -----

CORRECT = "/api/v1/attendance/correct"


async def _correct(client, headers, employee_id, day=PAST, check_in="09:05", check_out="18:00",
                    reason="Actually left at 1pm, half day"):
    """`check_in=None` (with `check_out` also left None) clears the day back to Absent."""
    return await client.post(
        CORRECT,
        json={"employee_id": employee_id, "attendance_date": str(day), "check_in_time": check_in,
              "check_out_time": check_out, "reason": reason},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_manager_corrects_a_present_day_into_a_half_day(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    row = await _open_day(db_session, report.id, hour=9, minute=2, status=AttendanceStatus.PRESENT)
    row.check_out = datetime(PAST.year, PAST.month, PAST.day, 18, 0, tzinfo=IST)
    row.working_minutes = 538
    await db_session.flush()
    manager = await _login(client, manager_with_team["manager_user"], demo_password)

    response = await _correct(client, manager, report.id, check_in="09:00", check_out="12:30")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == row.id  # the same row was updated, not duplicated
    assert data["status"] == "HALF_DAY" and data["working_minutes"] == 3 * 60 + 30
    assert data["corrected_by_name"] == "Test Manager"
    assert data["correction_reason"] == "Actually left at 1pm, half day"

    rows = (await db_session.execute(select(Attendance).where(Attendance.employee_id == report.id))).scalars().all()
    assert len(rows) == 1

    note = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))).scalar_one()
    assert "corrected your attendance" in note.message and "12:30" in note.message
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CORRECT_ATTENDANCE"))).scalar_one()
    assert "was PRESENT" in audit.description and "now 09:00-12:30" in audit.description


@pytest.mark.asyncio
async def test_correcting_can_also_turn_a_recorded_day_into_absent(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    row = await _open_day(db_session, report.id, status=AttendanceStatus.PRESENT)
    row.check_out = datetime(PAST.year, PAST.month, PAST.day, 18, 0, tzinfo=IST)
    await db_session.flush()
    row_id = row.id
    headers = await _login(client, admin_user, demo_password)

    response = await _correct(client, headers, report.id, check_in=None, check_out=None,
                              reason="Wrong person checked in for this day")
    assert response.status_code == 200, response.text
    assert response.json()["data"] is None  # nothing left to return - the row is gone

    remaining = (await db_session.execute(select(Attendance).where(Attendance.employee_id == report.id))).scalars().all()
    assert remaining == []

    # the roll call and the missed-day roster both now treat the day as a plain, ordinary Absent
    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    roll = (await client.get("/api/v1/attendance/roll-call", params={"date": str(PAST)}, headers=headers)).json()["data"]
    assert next(i for i in roll["items"] if i["employee_id"] == report.id)["status"] == "ABSENT"

    note = (await db_session.execute(select(Notification).where(Notification.user_id == manager_with_team["report_user"].id))).scalar_one()
    assert "cleared your attendance" in note.message and "now counts as Absent" in note.message
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "CORRECT_ATTENDANCE"))).scalar_one()
    assert "Cleared attendance" in audit.description and "was PRESENT, now Absent" in audit.description
    assert audit.entity_id == row_id


@pytest.mark.asyncio
async def test_correcting_a_blank_day_with_real_times_creates_a_fresh_record(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    """No Attendance row at all yet (an ordinary Absent day) - correcting it with times works exactly like
    filling in a fresh record; this is deliberately allowed too, so one tool covers every case."""
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    response = await _correct(client, await _login(client, admin_user, demo_password), report.id,
                              check_in="09:30", check_out="17:45", reason="Confirmed worked, add the day")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "LATE"


@pytest.mark.asyncio
async def test_clearing_a_day_with_no_record_is_refused(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    await _joined_long_ago(db_session)
    response = await _correct(client, await _login(client, admin_user, demo_password), manager_with_team["report_employee"].id,
                              check_in=None, check_out=None)
    assert response.status_code == 400 and response.json()["error_code"] == "NOTHING_TO_CORRECT"


@pytest.mark.asyncio
async def test_correction_input_and_leave_and_permission_rules(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    from app.models.enums import LeaveRequestStatus
    from app.models.leave import LeaveRequest, LeaveType
    from app.utils.timezone import today_in_org_tz

    report = manager_with_team["report_employee"]
    headers = await _login(client, admin_user, demo_password)

    # giving only one of the two times is rejected before it ever reaches the service
    only_one = await client.post(CORRECT, json={"employee_id": report.id, "attendance_date": str(PAST),
                                                "check_in_time": "09:00", "reason": "partial"}, headers=headers)
    assert only_one.status_code == 422

    today = await _correct(client, headers, report.id, day=today_in_org_tz())
    assert today.status_code == 400 and today.json()["error_code"] == "DAY_NOT_OVER"

    before = await _correct(client, headers, report.id, day=date(2020, 1, 1))
    assert before.status_code == 400 and before.json()["error_code"] == "BEFORE_JOINING"

    await db_session.execute(update(Employee).values(date_of_joining=date(2025, 1, 1)))
    await db_session.flush()
    backwards = await _correct(client, headers, report.id, check_in="18:00", check_out="09:00")
    assert backwards.status_code == 400 and backwards.json()["error_code"] == "CHECK_OUT_BEFORE_CHECK_IN"
    assert (await _correct(client, headers, report.id, reason=" a ")).status_code == 422
    assert (await _correct(client, headers, 999999)).status_code == 404

    leave_type = LeaveType(code="CORRECTTEST", name="Test leave", is_paid=True)
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(LeaveRequest(employee_id=report.id, leave_type_id=leave_type.id, start_date=PAST, end_date=PAST,
                                number_of_days=1, status=LeaveRequestStatus.APPROVED))
    await db_session.flush()
    on_leave = await _correct(client, headers, report.id)
    assert on_leave.status_code == 400 and on_leave.json()["error_code"] == "DAY_IS_LEAVE"
    on_leave_clear = await _correct(client, headers, report.id, check_in=None, check_out=None)
    assert on_leave_clear.status_code == 400 and on_leave_clear.json()["error_code"] == "DAY_IS_LEAVE"


@pytest.mark.asyncio
async def test_only_the_right_people_can_correct_attendance(
    client: AsyncClient, db_session, manager_with_team: dict, executive_user: User, accountant_user: User,
    hr_employee_user: User, hr_user: User, founder_user: User, demo_password: str,
):
    await _joined_long_ago(db_session)
    report = manager_with_team["report_employee"]
    await _open_day(db_session, report.id, status=AttendanceStatus.PRESENT)
    await db_session.flush()

    for user in (accountant_user, manager_with_team["outsider_user"], manager_with_team["report_user"]):
        assert (await _correct(client, await _login(client, user, demo_password), report.id)).status_code == 403

    # nobody corrects their own day - not even HR with full access
    own_id = await _employee_id(db_session, hr_employee_user)
    await _open_day(db_session, own_id, status=AttendanceStatus.PRESENT, day=PAST - timedelta(days=1))
    await db_session.flush()
    own = await _correct(client, await _login(client, hr_employee_user, demo_password), own_id, day=PAST - timedelta(days=1))
    assert own.status_code == 403 and own.json()["error_code"] == "ATTENDANCE_SELF_FIX"

    # Executive has full Founder parity (attendance:read_all), so it joins the company-wide group.
    for offset, user in enumerate((hr_user, founder_user, executive_user)):  # company-wide access reaches anyone
        outsider = manager_with_team["outsider_employee"]
        day = PAST - timedelta(days=offset + 2)
        await _open_day(db_session, outsider.id, status=AttendanceStatus.PRESENT, day=day)
        await db_session.flush()
        assert (await _correct(client, await _login(client, user, demo_password), outsider.id, day=day)).status_code == 200


@pytest.mark.asyncio
async def test_a_permission_is_taken_into_account_when_correcting(
    client: AsyncClient, db_session, manager_with_team: dict, admin_user: User, demo_password: str
):
    """A 2-hour permission recorded for the day excuses that much lateness, same as check-in and mark-present."""
    await _joined_long_ago(db_session)
    from app.models.attendance import ShortPermission

    report = manager_with_team["report_employee"]
    db_session.add(ShortPermission(employee_id=report.id, permission_date=PAST, minutes=120,
                                   recorded_by_name="Test Manager", reason="Bank work"))
    await db_session.flush()
    response = await _correct(client, await _login(client, admin_user, demo_password), report.id,
                              check_in="10:45", check_out="19:00", reason="Corrected times")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "PRESENT" and response.json()["data"]["late_minutes"] == 0
