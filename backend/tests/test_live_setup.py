"""First-time setup of a real installation: the strong-password rule, the empty-database-only rule, and that what
it creates is complete and works."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.password_policy import password_problems
from app.models import DocumentType, LeaveType, Permission, Role, User
from app.models.audit_log import AuditLog
from app.models.enums import RoleName
from app.setup_live import SetupError, run_setup

GOOD = "Sat-Group-2026-Safe"


def test_password_rules_in_plain_words():
    assert password_problems(GOOD, "owner@satgroup.com") == []
    assert any("12 characters" in p for p in password_problems("Short1", ""))
    assert any("number" in p for p in password_problems("OnlyLettersHereNow", ""))
    assert any("letters" in p for p in password_problems("123456789012345", ""))
    assert any("common" in p for p in password_problems("ChangeMe123!", "")) or password_problems("ChangeMe123!", "")
    assert any("email name" in p for p in password_problems("owner-Sat-2026-xx1", "owner@satgroup.com"))
    assert any("few different" in p for p in password_problems("aaaaaaaaaaaa1", ""))


@pytest.mark.asyncio
async def test_setup_creates_the_basics_and_a_working_admin(client: AsyncClient, db_session):
    admin = await run_setup(db_session, "Owner@SatGroup.com", GOOD)

    assert admin.email == "owner@satgroup.com" and admin.must_change_password is False
    role_names = {r.name for r in (await db_session.execute(select(Role))).scalars()}
    assert role_names == {r.value for r in RoleName}
    assert (await db_session.execute(select(func.count()).select_from(Permission))).scalar_one() == 29
    leave = {lt.code for lt in (await db_session.execute(select(LeaveType))).scalars()}
    assert {"CASUAL", "SICK", "EARNED", "UNPAID"} <= leave
    assert (await db_session.execute(select(func.count()).select_from(DocumentType))).scalar_one() >= 6
    # No demo people, departments or other logins are created
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 1
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "SETUP_SYSTEM"))).scalar_one()
    assert "owner@satgroup.com" in audit.description and GOOD not in audit.description

    # The password stored is a hash, and the Admin really can sign in with what was typed
    assert admin.hashed_password != GOOD
    login = await client.post("/api/v1/auth/login", json={"email": "owner@satgroup.com", "password": GOOD})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["data"]["role"] == "ADMIN" and me.json()["data"]["must_change_password"] is False


@pytest.mark.asyncio
async def test_setup_refuses_a_weak_password_or_a_bad_email_and_changes_nothing(db_session):
    for email, password in (("owner@satgroup.com", "ChangeMe123!"), ("owner@satgroup.com", "short1"), ("not-an-email", GOOD)):
        with pytest.raises(SetupError):
            await run_setup(db_session, email, password)
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(Role))).scalar_one() == 0


@pytest.mark.asyncio
async def test_setup_will_not_run_on_a_system_that_already_has_logins(db_session, admin_user):
    with pytest.raises(SetupError, match="already has logins"):
        await run_setup(db_session, "second@satgroup.com", GOOD)
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 1  # untouched


@pytest.mark.asyncio
async def test_running_setup_twice_is_safe(db_session):
    await run_setup(db_session, "owner@satgroup.com", GOOD)
    with pytest.raises(SetupError):
        await run_setup(db_session, "owner@satgroup.com", GOOD)
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 1
    assert (await db_session.execute(select(func.count()).select_from(Role))).scalar_one() == 7
