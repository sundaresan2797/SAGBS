"""The attendance policy: 9:00 start, 10-minute grace, half day under 7h45 or after 1:30 PM, and a
13:00-13:30 lunch break that is deducted from whatever part of it someone was clocked in for."""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.enums import AttendanceStatus
from app.models.user import User
from app.services import attendance_rules, attendance_service
from app.utils.timezone import get_org_timezone, today_in_org_tz

P, L, H = AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.HALF_DAY


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime.combine(date(2026, 9, 21), time(hour, minute, second), tzinfo=get_org_timezone())


# ----- late marking: 9:00 start + 10 minutes grace -----


@pytest.mark.parametrize(
    "when, late_minutes, status",
    [
        (at(8, 55), 0, P),
        (at(9, 0), 0, P),
        (at(9, 0, 59), 0, P),  # seconds are ignored
        (at(9, 10), 0, P),  # last minute of the grace period
        (at(9, 10, 59), 0, P),
        (at(9, 11), 11, L),  # late minutes count from 9:00, not from the end of the grace
        (at(9, 25), 25, L),
        (at(13, 30), 270, L),  # exactly the cut-off is still not a half day
        (at(13, 31), 271, H),  # after the cut-off
        (at(14, 0), 300, H),
    ],
)
def test_status_at_check_in(when, late_minutes, status):
    assert attendance_rules.late_minutes_for(when) == late_minutes
    assert attendance_rules.status_at_check_in(when) == status


# ----- check-out: full day needs 7h45, a late-afternoon arrival stays a half day -----


@pytest.mark.parametrize(
    "check_in, worked, status",
    [
        (at(9, 0), 8 * 60 + 40, P),
        (at(9, 0), 7 * 60 + 45, P),  # exactly 7h45 is a full day
        (at(9, 0), 7 * 60 + 45 - 1, H),
        (at(9, 0), 4 * 60, H),  # 9:00 to 1:00 PM
        (at(9, 0), 3 * 60 + 30, H),
        (at(9, 25), 8 * 60, L),  # late but worked a full day
        (at(9, 25), 6 * 60, H),  # half day wins over late
        (at(13, 30), 4 * 60, H),  # 1:30 to 5:30 PM
        (at(13, 30), 7 * 60, H),  # arrived after 1:30, so still a half day however long they stay
    ],
)
def test_status_at_check_out(check_in, worked, status):
    assert attendance_rules.status_at_check_out(check_in, worked) == status


def test_overtime_starts_after_the_standard_shift():
    assert attendance_rules.overtime_minutes_for(8 * 60 + 30) == 0  # the standard shift is 8h30 net of lunch
    assert attendance_rules.overtime_minutes_for(8 * 60 + 55) == 25
    assert attendance_rules.overtime_minutes_for(3 * 60) == 0


# ----- lunch: 1:00-1:30 PM, deducted from whatever part of it the person was clocked in for -----


@pytest.mark.parametrize(
    "check_in, check_out, deducted",
    [
        (at(8, 45), at(17, 30), 30),  # the whole day spans lunch: the full break is deducted
        (at(8, 45), at(12, 45), 0),  # left well before lunch started: nothing to deduct
        (at(8, 45), at(13, 0), 0),  # left exactly as lunch starts: still no overlap
        (at(8, 45), at(13, 15), 15),  # left partway through lunch: only that part
        (at(13, 0), at(17, 0), 30),  # arrived exactly as lunch starts: the whole break overlaps
        (at(13, 15), at(17, 0), 15),  # arrived partway through lunch: only the remaining part
        (at(14, 0), at(17, 0), 0),  # arrived after lunch was over: nothing to deduct
        (at(13, 5), at(13, 20), 15),  # both check-in and check-out fall inside lunch
    ],
)
def test_lunch_break_minutes_within(check_in, check_out, deducted):
    assert attendance_rules.lunch_break_minutes_within(check_in, check_out) == deducted


def test_a_full_standard_day_nets_out_exactly_once_lunch_is_removed():
    """9:00 to 6:00 is 9h at the gate; minus the 30-minute lunch, exactly the 8h30 standard shift - so a
    completely ordinary day produces zero overtime, not 30 minutes of phantom overtime for lunch."""
    check_in, check_out = at(9, 0), at(18, 0)
    raw_minutes = int((check_out - check_in).total_seconds() // 60)
    worked = raw_minutes - attendance_rules.lunch_break_minutes_within(check_in, check_out)
    assert worked == 8 * 60 + 30
    assert attendance_rules.overtime_minutes_for(worked) == 0
    assert attendance_rules.status_at_check_out(check_in, worked) == P


# ----- end to end through the API, with a controlled clock -----


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _clock(monkeypatch, moment: datetime) -> None:
    monkeypatch.setattr(attendance_service, "now_utc", lambda: moment.astimezone(timezone.utc))


def _today_at(hour: int, minute: int) -> datetime:
    return datetime.combine(today_in_org_tz(), time(hour, minute), tzinfo=get_org_timezone())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arrive, stay_minutes, expected_in, expected_out, late, overtime",
    [
        # A plain full day, spanning lunch: 30 minutes of the raw span is lunch, so working_minutes is
        # 30 less than the time actually spent clocked in.
        ((8, 50), 8 * 60 + 30, "PRESENT", "PRESENT", 0, 0),
        ((9, 25), 9 * 60 + 10, "LATE", "LATE", 25, 10),
        ((9, 0), 4 * 60, "PRESENT", "HALF_DAY", 0, 0),
        # 13:30 itself is still "late", not "half day" (the cut-off is exclusive - see test_status_at_check_in);
        # one minute past it is unambiguously a half day.
        ((13, 31), 4 * 60, "HALF_DAY", "HALF_DAY", 271, 0),
    ],
)
async def test_check_in_and_out_follow_the_policy(
    client: AsyncClient,
    employee_user: User,
    demo_password: str,
    monkeypatch,
    arrive,
    stay_minutes,
    expected_in,
    expected_out,
    late,
    overtime,
):
    headers = await _login(client, employee_user, demo_password)
    arrival = _today_at(*arrive)

    _clock(monkeypatch, arrival)
    checked_in = await client.post("/api/v1/attendance/check-in", headers=headers)
    assert checked_in.status_code == 200, checked_in.text
    assert checked_in.json()["data"]["status"] == expected_in
    assert checked_in.json()["data"]["late_minutes"] == late

    departure = arrival + timedelta(minutes=stay_minutes)
    _clock(monkeypatch, departure)
    checked_out = await client.post("/api/v1/attendance/check-out", headers=headers)
    assert checked_out.status_code == 200, checked_out.text
    data = checked_out.json()["data"]
    expected_worked = stay_minutes - attendance_rules.lunch_break_minutes_within(
        arrival.astimezone(get_org_timezone()), departure.astimezone(get_org_timezone())
    )
    assert data["status"] == expected_out
    assert data["working_minutes"] == expected_worked
    assert data["overtime_minutes"] == overtime


@pytest.mark.asyncio
async def test_policy_endpoint_reports_the_rules(client: AsyncClient, employee_user: User, demo_password: str):
    headers = await _login(client, employee_user, demo_password)
    response = await client.get("/api/v1/attendance/policy", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "office_start": "09:00",
        "grace_minutes": 10,
        "late_after": "09:10",
        "full_day_minimum_minutes": 465,
        "half_day_after": "13:30",
        "standard_shift_minutes": 510,
        "long_day_minutes": 720,
        "lunch_start": "13:00",
        "lunch_break_minutes": 30,
    }

    anonymous = await client.get("/api/v1/attendance/policy")
    assert anonymous.status_code in (401, 403)
