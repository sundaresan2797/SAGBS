from collections.abc import AsyncGenerator
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.redis import redis_service
from app.core.security import hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import Department, Designation, DocumentType, Employee, Permission, Role, RolePermission, User
from app.models.enums import EmploymentType, RoleName
from app.utils.permissions import PERMISSIONS, ROLE_PERMISSIONS


@pytest_asyncio.fixture
async def test_engine():
    # Function-scoped (not session-scoped): pytest-asyncio 0.25 gives every
    # test its own event loop by default, and asyncpg connections can't be
    # reused across loops. Recreating the schema per test keeps the engine,
    # its connections, and the test itself on the same loop.
    engine = create_async_engine(settings.database_url_test)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    connection = await test_engine.connect()
    outer_transaction = await connection.begin()

    session_factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    session = session_factory()

    await session.begin_nested()

    @event.listens_for(session.sync_session, "after_transaction_end")
    def restart_savepoint(sync_session, transaction):
        if transaction.nested and not transaction._parent.nested:
            sync_session.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    # storage_service is a process-wide singleton pointed at the real
    # ./uploads directory; redirect it to a throwaway tmp dir per test so
    # document tests never touch (or collide with) real dev/prod uploads.
    from app.services.storage_service import storage_service

    monkeypatch.setattr(storage_service, "base_dir", tmp_path)


@pytest_asyncio.fixture(autouse=True)
async def redis_isolation() -> AsyncGenerator[None, None]:
    # redis_service is a process-wide singleton whose client is bound to
    # whichever event loop first used it; since every test here gets its own
    # loop, the client must be reset each time or it raises "Event loop is
    # closed". Each test also gets a completely fresh Postgres schema, but
    # Redis is a real shared instance across tests (and the local dev
    # server) - without clearing every "ems:*" key (rate limits, dashboard
    # cache, employee/department list cache), a cached result computed from
    # one test's data can leak into and corrupt the next test's assertions.
    await redis_service.reset()
    await redis_service.delete_pattern("ems:*")
    yield
    await redis_service.delete_pattern("ems:*")
    await redis_service.reset()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def seed_roles_permissions(session: AsyncSession) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for role_name in RoleName:
        role = Role(name=role_name.value, description=f"{role_name.value} role")
        session.add(role)
        roles[role_name.value] = role
    await session.flush()

    permissions: dict[str, Permission] = {}
    for code, description in PERMISSIONS:
        permission = Permission(code=code, description=description)
        session.add(permission)
        permissions[code] = permission
    await session.flush()

    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles[role_name.value]
        for code in codes:
            session.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))
    await session.flush()

    return roles


@pytest_asyncio.fixture
async def roles(db_session: AsyncSession) -> dict[str, Role]:
    return await seed_roles_permissions(db_session)


@pytest_asyncio.fixture
async def document_types(db_session: AsyncSession) -> dict[str, DocumentType]:
    # The six built-in kinds (what the migration and seed create), keyed by code.
    kinds = {}
    for code, name in (
        ("OFFER_LETTER", "Offer Letter"),
        ("EMPLOYMENT_CONTRACT", "Employment Contract"),
        ("ID_PROOF", "ID Proof"),
        ("RESUME", "Resume"),
        ("CERTIFICATION", "Certification"),
        ("OTHER", "Other"),
    ):
        kind = DocumentType(code=code, name=name, requires_expiry=False, is_active=True)
        db_session.add(kind)
        kinds[code] = kind
    await db_session.flush()
    return kinds


@pytest_asyncio.fixture
async def demo_password() -> str:
    return "TestPass123!"


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, roles: dict[str, Role], demo_password: str) -> User:
    user = User(
        email="admin@example.org",
        hashed_password=hash_password(demo_password),
        role_id=roles[RoleName.ADMIN.value].id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def hr_user(db_session: AsyncSession, roles: dict[str, Role], demo_password: str) -> User:
    user = User(
        email="hr@example.org",
        hashed_password=hash_password(demo_password),
        role_id=roles[RoleName.HR.value].id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def founder_user(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> User:
    user, _ = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="founder@example.org",
        role_name=RoleName.FOUNDER.value,
        employee_code="TEST-FNDR-0001",
        first_name="Test",
        last_name="Founder",
    )
    return user


@pytest_asyncio.fixture
async def hr_employee_user(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> User:
    user, _ = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="hr.staff@example.org",
        role_name=RoleName.HR.value,
        employee_code="TEST-HR-0001",
        first_name="Test",
        last_name="HRStaff",
    )
    return user


@pytest_asyncio.fixture
async def accountant_user(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> User:
    user, _ = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="accountant@example.org",
        role_name=RoleName.ACCOUNTANT.value,
        employee_code="TEST-ACCT-0001",
        first_name="Test",
        last_name="Accountant",
    )
    return user


@pytest_asyncio.fixture
async def executive_user(db_session: AsyncSession, roles: dict[str, Role], demo_password: str) -> User:
    # A business-leadership account (e.g. CEO/COO) - hierarchy-based authority
    # only, deliberately without any system-config permissions.
    user = User(
        email="executive@example.org",
        hashed_password=hash_password(demo_password),
        role_id=roles[RoleName.EXECUTIVE.value].id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def department(db_session: AsyncSession) -> Department:
    dept = Department(name="Test Department")
    db_session.add(dept)
    await db_session.flush()
    return dept


@pytest_asyncio.fixture
async def designation(db_session: AsyncSession, department: Department) -> Designation:
    desig = Designation(name="Test Designation", department_id=department.id)
    db_session.add(desig)
    await db_session.flush()
    return desig


async def _create_employee(
    db_session: AsyncSession,
    roles: dict[str, Role],
    demo_password: str,
    department: Department,
    designation: Designation,
    *,
    email: str,
    role_name: str,
    employee_code: str,
    first_name: str,
    last_name: str,
    manager_id: int | None = None,
) -> tuple[User, Employee]:
    user = User(
        email=email,
        hashed_password=hash_password(demo_password),
        role_id=roles[role_name].id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()

    employee = Employee(
        employee_code=employee_code,
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        email=user.email,
        date_of_joining=date.today(),
        department_id=department.id,
        designation_id=designation.id,
        employment_type=EmploymentType.FULL_TIME,
        manager_id=manager_id,
    )
    db_session.add(employee)
    await db_session.flush()

    return user, employee


@pytest_asyncio.fixture
async def boss_employee(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> Employee:
    """Someone to report to. Leave can only be decided by a direct manager, and applying is refused when
    there isn't one, so a test that applies for leave as a plain employee makes them report to this person.
    Not part of the shared employee fixtures: an extra employee would change every headcount-based test."""
    _, employee = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="boss@example.org",
        role_name=RoleName.MANAGER.value,
        employee_code="TEST-BOSS-0001",
        first_name="Test",
        last_name="Boss",
    )
    return employee


@pytest_asyncio.fixture
async def employee_user(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> User:
    user, _ = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="employee@example.org",
        role_name=RoleName.EMPLOYEE.value,
        employee_code="TEST-0001",
        first_name="Test",
        last_name="Employee",
    )
    return user


@pytest_asyncio.fixture
async def manager_with_team(
    db_session: AsyncSession, roles: dict[str, Role], demo_password: str, department: Department, designation: Designation
) -> dict[str, User | Employee]:
    manager_user, manager_employee = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="manager@example.org",
        role_name=RoleName.MANAGER.value,
        employee_code="TEST-MGR-0001",
        first_name="Test",
        last_name="Manager",
    )
    report_user, report_employee = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="report@example.org",
        role_name=RoleName.EMPLOYEE.value,
        employee_code="TEST-0002",
        first_name="Direct",
        last_name="Report",
        manager_id=manager_employee.id,
    )
    outsider_user, outsider_employee = await _create_employee(
        db_session,
        roles,
        demo_password,
        department,
        designation,
        email="outsider@example.org",
        role_name=RoleName.EMPLOYEE.value,
        employee_code="TEST-0003",
        first_name="Not",
        last_name="OnTeam",
    )
    return {
        "manager_user": manager_user,
        "manager_employee": manager_employee,
        "report_user": report_user,
        "report_employee": report_employee,
        "outsider_user": outsider_user,
        "outsider_employee": outsider_employee,
    }
