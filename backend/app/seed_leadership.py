"""Adds a Founder -> CEO -> department-heads leadership layer on top of the
realistic org built by app.seed_realistic_org.

Run after app.seed and app.seed_realistic_org:

    python -m app.seed_leadership

Idempotent: safe to re-run.

Structure:
    Panneer Selvam (Founder, own founder@example.com login with the FOUNDER
    role - separate from the system admin@example.com account) ->
    Sundareswaran S (CEO, new account) -> the existing top
    manager of every non-HR department (Engineering, Finance, Sales,
    Marketing, Operations) reports directly to the CEO. HR gets one extra
    layer: CEO -> Lokesh Kumar (HR Head, new) -> the existing HR managers
    (Hannah Reyes, Ritu Kapoor).
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, engine
from app.models import Department, Designation, Employee, Role
from app.models.enums import EmploymentType, RoleName
from app.seed import (
    DEMO_PASSWORD,
    get_or_create_employee,
    get_or_create_user,
    seed_leave_balances,
    seed_leave_types,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("ems.seed_leadership")

# Existing top-of-department managers (created by seed_realistic_org) that
# should now report up to the CEO instead of having no manager.
NON_HR_TOP_MANAGERS = [
    "manager@example.com",  # Marcus Nguyen, Engineering
    "vikram.rao@example.com",  # Vikram Rao, Engineering
    "rohan.desai@example.com",  # Finance
    "sneha.kulkarni@example.com",  # Finance
    "ayesha.khan@example.com",  # Sales
    "karan.malhotra@example.com",  # Sales
    "aditya.joshi@example.com",  # Marketing
    "ishita.bansal@example.com",  # Marketing
    "sanjay.gupta@example.com",  # Operations
    "meenal.deshpande@example.com",  # Operations
]

HR_TOP_MANAGERS = [
    "hr@example.com",  # Hannah Reyes
    "ritu.kapoor@example.com",  # Ritu Kapoor
]


async def get_or_create_department(session: AsyncSession, name: str, description: str) -> Department:
    result = await session.execute(select(Department).where(Department.name == name))
    department = result.scalar_one_or_none()
    if department is None:
        department = Department(name=name, description=description)
        session.add(department)
        await session.flush()
        logger.info("Created department %s", name)
    return department


async def get_or_create_designation(session: AsyncSession, name: str, department: Department) -> Designation:
    result = await session.execute(
        select(Designation).where(Designation.name == name, Designation.department_id == department.id)
    )
    designation = result.scalar_one_or_none()
    if designation is None:
        designation = Designation(name=name, department_id=department.id)
        session.add(designation)
        await session.flush()
        logger.info("Created designation %s", name)
    return designation


async def get_employee_by_email(session: AsyncSession, email: str) -> Employee:
    result = await session.execute(select(Employee).where(Employee.email == email))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise RuntimeError(f"Expected employee {email} to already exist - run app.seed_realistic_org first.")
    return employee


async def next_employee_code(session: AsyncSession) -> str:
    result = await session.execute(select(Employee.employee_code))
    codes = [c for c in result.scalars().all() if c.startswith("EMP-")]
    next_number = max((int(c.split("-")[1]) for c in codes), default=0) + 1
    return f"EMP-{next_number:04d}"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        roles_result = await session.execute(select(Role))
        roles = {r.name: r for r in roles_result.scalars().all()}
        leave_types = await seed_leave_types(session)

        executive_dept = await get_or_create_department(session, "Executive", "Company leadership")
        founder_designation = await get_or_create_designation(session, "Founder", executive_dept)
        ceo_designation = await get_or_create_designation(session, "CEO", executive_dept)

        hr_dept = await get_or_create_department(session, "Human Resources", "People operations and talent management")
        hr_head_designation = await get_or_create_designation(session, "HR Head", hr_dept)

        # Founder: their own login with the FOUNDER role. admin@example.com
        # stays a pure system-administration account with no employee profile,
        # so the owner and the system admin never share an identity.
        founder_user, _ = await get_or_create_user(session, "founder@example.com", roles[RoleName.FOUNDER.value])
        founder = await get_or_create_employee(
            session,
            founder_user,
            await next_employee_code(session),
            "K",
            "Panneer Selvam",
            founder_designation,
            EmploymentType.FULL_TIME,
            work_location="Head Office",
        )
        await session.flush()

        # CEO: new account, reports to the Founder.
        ceo_user, _ = await get_or_create_user(session, "s.sundaresawaran@example.com", roles[RoleName.ADMIN.value])
        ceo = await get_or_create_employee(
            session,
            ceo_user,
            await next_employee_code(session),
            "S",
            "Sundaresawaran",
            ceo_designation,
            EmploymentType.FULL_TIME,
            manager_id=founder.id,
            work_location="Head Office",
        )
        await session.flush()

        # HR Head: new account, reports to the CEO.
        hr_head_user, _ = await get_or_create_user(session, "j.lokesh@example.com", roles[RoleName.HR.value])
        hr_head = await get_or_create_employee(
            session,
            hr_head_user,
            await next_employee_code(session),
            "J",
            "Lokesh",
            hr_head_designation,
            EmploymentType.FULL_TIME,
            manager_id=ceo.id,
            work_location="Head Office",
        )
        await session.flush()

        # Re-parent the existing top managers.
        for email in NON_HR_TOP_MANAGERS:
            employee = await get_employee_by_email(session, email)
            employee.manager_id = ceo.id

        for email in HR_TOP_MANAGERS:
            employee = await get_employee_by_email(session, email)
            employee.manager_id = hr_head.id

        await session.flush()

        for employee in (founder, ceo, hr_head):
            await seed_leave_balances(session, employee, leave_types)

        await session.commit()

    await engine.dispose()
    logger.info("Leadership layer seeded: Founder -> CEO -> department heads (HR via HR Head).")
    logger.info("New accounts: s.sundaresawaran@example.com, j.lokesh@example.com (password: %s)", DEMO_PASSWORD)
    logger.info("Founder login: founder@example.com (FOUNDER role, password: %s)", DEMO_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
