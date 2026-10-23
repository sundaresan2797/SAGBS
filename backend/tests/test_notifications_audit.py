import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_notification_mark_read_and_read_all(client: AsyncClient, db_session, employee_user, demo_password: str):
    from app.models.notification import Notification

    db_session.add(
        Notification(
            user_id=employee_user.id, title="Test", message="Hello", notification_type="OTHER", is_read=False
        )
    )
    db_session.add(
        Notification(
            user_id=employee_user.id, title="Test 2", message="Hello 2", notification_type="OTHER", is_read=False
        )
    )
    await db_session.commit()

    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    unread_response = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert unread_response.json()["data"] == 2

    list_response = await client.get("/api/v1/notifications", headers=headers)
    notification_id = list_response.json()["data"]["items"][0]["id"]

    mark_response = await client.patch(f"/api/v1/notifications/{notification_id}/read", headers=headers)
    assert mark_response.status_code == 200
    assert mark_response.json()["data"]["is_read"] is True

    mark_all_response = await client.patch("/api/v1/notifications/read-all", headers=headers)
    assert mark_all_response.status_code == 200

    final_unread = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert final_unread.json()["data"] == 0


@pytest.mark.asyncio
async def test_notification_forbidden_for_other_user(
    client: AsyncClient, db_session, admin_user, employee_user, demo_password: str
):
    from app.models.notification import Notification

    notification = Notification(
        user_id=admin_user.id, title="Admin only", message="Secret", notification_type="OTHER", is_read=False
    )
    db_session.add(notification)
    await db_session.commit()

    employee_token = await _login(client, employee_user.email, demo_password)
    response = await client.patch(
        f"/api/v1/notifications/{notification.id}/read", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "NOTIFICATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_login_creates_audit_log_and_requires_permission(
    client: AsyncClient, admin_user, employee_user, demo_password: str
):
    await client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password})

    admin_token = await _login(client, admin_user.email, demo_password)
    response = await client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["data"]["items"]}
    assert "LOGIN" in actions

    employee_token = await _login(client, employee_user.email, demo_password)
    forbidden_response = await client.get(
        "/api/v1/audit-logs", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert forbidden_response.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_names_who_acted_and_can_hide_routine_activity(
    client: AsyncClient, admin_user, founder_user, employee_user, demo_password: str
):
    """Each entry says who did it (the person's name, or "Admin" for a login without a profile), and the
    everyday check-ins and sign-ins can be left out so the entries that matter aren't buried. The Founder
    holds audit:view too, so sees the same log."""
    async def headers_for(email: str) -> dict:
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": demo_password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}

    employee_headers = await headers_for(employee_user.email)
    assert (await client.post("/api/v1/attendance/check-in", headers=employee_headers)).status_code == 200

    admin_headers = await headers_for(admin_user.email)
    assert (await client.post("/api/v1/holidays", json={"name": "Founders Day", "holiday_date": "2027-09-01"}, headers=admin_headers)).status_code == 201

    everything = (await client.get("/api/v1/audit-logs", params={"page_size": 100}, headers=admin_headers)).json()["data"]["items"]
    by_action = {}
    for entry in everything:
        by_action.setdefault(entry["action"], entry)
    assert by_action["CHECK_IN"]["user_name"] == "Test Employee"
    assert by_action["CREATE_HOLIDAY"]["user_name"] == "Admin"

    quiet = (await client.get("/api/v1/audit-logs", params={"page_size": 100, "hide_routine": True}, headers=admin_headers)).json()["data"]["items"]
    actions = {entry["action"] for entry in quiet}
    assert "CREATE_HOLIDAY" in actions
    assert not actions & {"CHECK_IN", "CHECK_OUT", "LOGIN", "LOGOUT"}

    # The Founder can read the same log.
    founder_view = await client.get("/api/v1/audit-logs", params={"hide_routine": True}, headers=await headers_for(founder_user.email))
    assert founder_view.status_code == 200
    # Someone without audit:view cannot.
    assert (await client.get("/api/v1/audit-logs", headers=employee_headers)).status_code == 403
