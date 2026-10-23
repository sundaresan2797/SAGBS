"""The Roles & Permissions matrix: who may see and edit it, and the two guardrails on editing it."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.user import User

SET = "/api/v1/roles/{}/permissions/{}"


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _set(client: AsyncClient, headers: dict, role: str, code: str, granted: bool):
    return await client.put(SET.format(role, code), json={"granted": granted}, headers=headers)


@pytest.mark.asyncio
async def test_only_admin_can_see_the_matrix(
    client: AsyncClient, admin_user: User, founder_user: User, hr_user: User, demo_password: str
):
    admin_headers = await _login(client, admin_user, demo_password)
    assert (await client.get("/api/v1/roles/permissions-matrix", headers=admin_headers)).status_code == 200

    for other in (founder_user, hr_user):
        headers = await _login(client, other, demo_password)
        assert (await client.get("/api/v1/roles/permissions-matrix", headers=headers)).status_code == 403

    assert (await client.get("/api/v1/roles/permissions-matrix")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_matrix_reflects_the_real_database_not_just_the_python_defaults(
    client: AsyncClient, db_session, admin_user: User, demo_password: str
):
    """Executive's payroll:view came from a migration (a5e3602b0ff8), not from editing a Python dict in
    place - the matrix must show what the database actually has, the same thing the API itself enforces."""
    headers = await _login(client, admin_user, demo_password)
    response = await client.get("/api/v1/roles/permissions-matrix", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]

    codes = {p["code"] for p in data["permissions"]}
    assert "payroll:view" in codes and "payroll:manage" in codes and "attendance:mark" in codes

    by_role = {r["role"]: set(r["permission_codes"]) for r in data["roles"]}
    assert "EXECUTIVE" in by_role and "payroll:view" in by_role["EXECUTIVE"] and "payroll:manage" in by_role["EXECUTIVE"]
    assert "ADMIN" in by_role and "payroll:view" not in by_role["ADMIN"]  # Admin deliberately has no payroll access
    assert by_role["EXECUTIVE"] == by_role["FOUNDER"]  # full parity, see migration b5f545e1a157

    # Role order is meaningful (leadership first, Employee last), not whatever the database happened to return.
    assert [r["role"] for r in data["roles"]][0] == "ADMIN"
    assert [r["role"] for r in data["roles"]][-1] == "EMPLOYEE"


@pytest.mark.asyncio
async def test_admin_can_grant_and_revoke_a_permission_it_already_holds(
    client: AsyncClient, db_session, admin_user: User, demo_password: str
):
    headers = await _login(client, admin_user, demo_password)

    granted = await _set(client, headers, "MANAGER", "holiday:manage", True)
    assert granted.status_code == 200, granted.text
    by_role = {r["role"]: set(r["permission_codes"]) for r in granted.json()["data"]["roles"]}
    assert "holiday:manage" in by_role["MANAGER"]

    revoked = await _set(client, headers, "MANAGER", "holiday:manage", False)
    assert revoked.status_code == 200
    by_role = {r["role"]: set(r["permission_codes"]) for r in revoked.json()["data"]["roles"]}
    assert "holiday:manage" not in by_role["MANAGER"]

    actions = (await db_session.execute(
        select(AuditLog).where(AuditLog.action.in_(["GRANT_ROLE_PERMISSION", "REVOKE_ROLE_PERMISSION"]))
    )).scalars().all()
    assert len(actions) == 2
    assert "MANAGER" in actions[0].description and "holiday:manage" in actions[0].description


@pytest.mark.asyncio
async def test_admin_cannot_grant_payroll_access_it_does_not_have_itself(
    client: AsyncClient, admin_user: User, demo_password: str
):
    """Admin deliberately has no payroll:view/manage - it must not be able to use this screen to hand
    that power to someone else either, the same "can't give away what you don't have" rule as
    employee_service._may_manage_login_of."""
    headers = await _login(client, admin_user, demo_password)
    response = await _set(client, headers, "MANAGER", "payroll:view", True)
    assert response.status_code == 403 and response.json()["error_code"] == "PERMISSION_NOT_YOURS_TO_GRANT"


@pytest.mark.asyncio
async def test_the_last_holder_of_role_manage_cannot_be_stripped_of_it(
    client: AsyncClient, admin_user: User, demo_password: str
):
    """Admin is the only role with role:manage by default - removing it would lock everyone out of this
    screen for good, recoverable only with direct database access."""
    headers = await _login(client, admin_user, demo_password)
    response = await _set(client, headers, "ADMIN", "role:manage", False)
    assert response.status_code == 400 and response.json()["error_code"] == "LAST_ROLE_MANAGER"


@pytest.mark.asyncio
async def test_role_manage_can_be_revoked_once_another_role_holds_it(
    client: AsyncClient, admin_user: User, demo_password: str
):
    headers = await _login(client, admin_user, demo_password)
    # Give FOUNDER role:manage too - Admin holds it itself, so this grant is allowed.
    assert (await _set(client, headers, "FOUNDER", "role:manage", True)).status_code == 200
    # Now ADMIN is no longer the last holder, so it can give it up.
    response = await _set(client, headers, "ADMIN", "role:manage", False)
    assert response.status_code == 200
    by_role = {r["role"]: set(r["permission_codes"]) for r in response.json()["data"]["roles"]}
    assert "role:manage" not in by_role["ADMIN"] and "role:manage" in by_role["FOUNDER"]


@pytest.mark.asyncio
async def test_duplicate_grant_and_empty_revoke_are_refused_cleanly(
    client: AsyncClient, admin_user: User, demo_password: str
):
    headers = await _login(client, admin_user, demo_password)
    already = await _set(client, headers, "ADMIN", "employee:read", True)
    assert already.status_code == 400 and already.json()["error_code"] == "PERMISSION_ALREADY_GRANTED"
    nothing = await _set(client, headers, "EMPLOYEE", "payroll:manage", False)
    assert nothing.status_code == 400 and nothing.json()["error_code"] == "PERMISSION_NOT_GRANTED"


@pytest.mark.asyncio
async def test_unknown_role_or_permission_is_a_clean_404(client: AsyncClient, admin_user: User, demo_password: str):
    headers = await _login(client, admin_user, demo_password)
    assert (await _set(client, headers, "NOPE", "employee:read", True)).status_code == 404
    assert (await _set(client, headers, "MANAGER", "nope:nope", True)).status_code == 404


@pytest.mark.asyncio
async def test_only_admin_can_edit_the_matrix(client: AsyncClient, founder_user: User, demo_password: str):
    headers = await _login(client, founder_user, demo_password)
    response = await _set(client, headers, "MANAGER", "holiday:manage", True)
    assert response.status_code == 403
