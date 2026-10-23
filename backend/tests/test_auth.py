import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user: User, demo_password: str):
    response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == admin_user.email
    assert body["data"]["user"]["role"] == "ADMIN"
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, admin_user: User):
    response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.org", "password": "whatever123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error_code"] == "MISSING_TOKEN"


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient, employee_user: User, demo_password: str):
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password}
    )
    access_token = login_response.json()["data"]["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["email"] == employee_user.email
    assert body["data"]["employee_id"] is not None
    assert "leave:apply" in body["data"]["permissions"]


@pytest.mark.asyncio
async def test_me_rejects_invalid_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient, admin_user: User, demo_password: str):
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password}
    )
    refresh_token = login_response.json()["data"]["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access_token" in response.json()["data"]


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client: AsyncClient, admin_user: User, demo_password: str):
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password}
    )
    access_token = login_response.json()["data"]["access_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient, admin_user: User, db_session, monkeypatch):
    from app.services import auth_service

    # request_password_reset only ever persists a hash of the token (by design,
    # so a DB leak can't be used to reset accounts); pin the raw value here so
    # the test can exercise the real reset-password endpoint with it.
    raw_token = "fixed-test-reset-token"
    monkeypatch.setattr(auth_service.secrets, "token_urlsafe", lambda *_args, **_kwargs: raw_token)

    await auth_service.request_password_reset(db_session, admin_user.email)

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": raw_token, "new_password": "BrandNewPass1!"}
    )
    assert response.status_code == 200

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": "BrandNewPass1!"}
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "SomePass123!"}
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_change_password_invalidates_old_tokens(
    client: AsyncClient, employee_user: User, demo_password: str
):
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password}
    )
    old_access = login_response.json()["data"]["access_token"]
    old_refresh = login_response.json()["data"]["refresh_token"]

    change_response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": demo_password, "new_password": "BrandNewPass1!"},
        headers={"Authorization": f"Bearer {old_access}"},
    )
    assert change_response.status_code == 200

    # The token used to make the change-password call itself was still
    # valid at request time; a *subsequent* request with that same old
    # token must now be rejected.
    me_response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me_response.status_code == 401
    assert me_response.json()["error_code"] == "INVALID_TOKEN"

    refresh_response = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error_code"] == "INVALID_REFRESH_TOKEN"

    # A fresh login with the new password issues tokens that work fine.
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": "BrandNewPass1!"}
    )
    assert new_login.status_code == 200
    new_access = new_login.json()["data"]["access_token"]
    me_again = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me_again.status_code == 200


@pytest.mark.asyncio
async def test_admin_reset_password_invalidates_target_session(
    client: AsyncClient, admin_user: User, employee_user: User, demo_password: str, db_session
):
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password}
    )
    old_access = login_response.json()["data"]["access_token"]

    admin_token_response = await client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": demo_password}
    )
    admin_token = admin_token_response.json()["data"]["access_token"]

    reset_response = await client.post(
        f"/api/v1/employees/{employee.id}/reset-password",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_response.status_code == 200

    me_response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me_response.status_code == 401
    assert me_response.json()["error_code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_a_temporary_password_cannot_be_kept_by_changing_it_to_itself(
    client: AsyncClient, db_session, employee_user: User, demo_password: str
):
    """Someone told to replace a temporary password could otherwise "change" it to the same one, lift the lock and
    carry on with the password everyone knows. The new password has to differ, and a refused attempt changes nothing."""
    from app.models.user import User as UserModel

    user = await db_session.get(UserModel, employee_user.id)
    user.must_change_password = True
    await db_session.flush()

    login = await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password})
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    same = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": demo_password, "new_password": demo_password},
        headers=headers,
    )
    assert same.status_code == 400, same.text
    assert same.json()["error_code"] == "PASSWORD_UNCHANGED"

    # Nothing changed: still flagged, the same token still works, the old password still signs in.
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["data"]["must_change_password"] is True
    assert (await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": demo_password})).status_code == 200

    different = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": demo_password, "new_password": "ADifferentOne#9"},
        headers=headers,
    )
    assert different.status_code == 200, different.text
    relogin = await client.post("/api/v1/auth/login", json={"email": employee_user.email, "password": "ADifferentOne#9"})
    assert relogin.json()["data"]["user"]["must_change_password"] is False
