"""Restructures the org under a COO / CTO / CFO layer between the CEO and
department heads, and splits AI + DevOps out of Engineering and Accounts out
of Finance as full peer departments with their own teams.

Run after app.seed, app.seed_realistic_org, and app.seed_leadership:

    python -m app.seed_org_v2

Idempotent: safe to re-run. Every row here is a normal Department/
Designation/Employee row, editable afterward like any other record through
the app's existing Employees/Departments/Designations pages - nothing here
is hardcoded into the application.

    K Panneer Selvam (Founder)
      -> S Sundaresawaran (CEO)
           -> R Rajendran (COO)      -> HR (J Lokesh), Operations (unchanged pair)
           -> V Venkataraman (CTO)   -> Engineering (Marcus, unchanged team)
                                     -> AI (Vikram Rao's team, moved from Engineering)
                                     -> DevOps (new team)
           -> A Ananthi (CFO)        -> Finance (Rohan, unchanged team)
                                     -> Accounts (Sneha Kulkarni's team, moved from Finance)
           -> Sales, Marketing (unchanged, direct to CEO - not part of this chart)
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, engine
from app.models import Employee, Role
from app.models.enums import EmploymentType, RoleName
from app.seed import (
    DEMO_PASSWORD,
    get_or_create_employee,
    get_or_create_user,
    seed_leave_balances,
    seed_leave_types,
)
from app.seed_leadership import get_or_create_department, get_or_create_designation, next_employee_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("ems.seed_org_v2")


async def get_employee(session: AsyncSession, email: str) -> Employee:
    result = await session.execute(select(Employee).where(Employee.email == email))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise RuntimeError(f"Expected employee {email} to already exist - run earlier seed scripts first.")
    return employee


async def main() -> None:
    async with AsyncSessionLocal() as session:
        roles_result = await session.execute(select(Role))
        roles = {r.name: r for r in roles_result.scalars().all()}
        leave_types = await seed_leave_types(session)

        executive_dept = await get_or_create_department(session, "Executive", "Company leadership")
        coo_designation = await get_or_create_designation(session, "COO", executive_dept)
        cto_designation = await get_or_create_designation(session, "CTO", executive_dept)
        cfo_designation = await get_or_create_designation(session, "CFO", executive_dept)

        ceo = await get_employee(session, "s.sundaresawaran@example.com")

        # --- C-suite: COO, CTO, CFO, all reporting to the CEO ---
        coo_user, _ = await get_or_create_user(session, "r.rajendran@example.com", roles[RoleName.ADMIN.value])
        coo = await get_or_create_employee(
            session, coo_user, await next_employee_code(session), "R", "Rajendran",
            coo_designation, EmploymentType.FULL_TIME, manager_id=ceo.id, work_location="Head Office",
        )

        cto_user, _ = await get_or_create_user(session, "v.venkataraman@example.com", roles[RoleName.ADMIN.value])
        cto = await get_or_create_employee(
            session, cto_user, await next_employee_code(session), "V", "Venkataraman",
            cto_designation, EmploymentType.FULL_TIME, manager_id=ceo.id, work_location="Head Office",
        )

        cfo_user, _ = await get_or_create_user(session, "a.ananthi@example.com", roles[RoleName.ADMIN.value])
        cfo = await get_or_create_employee(
            session, cfo_user, await next_employee_code(session), "A", "Ananthi",
            cfo_designation, EmploymentType.FULL_TIME, manager_id=ceo.id, work_location="Head Office",
        )
        await session.flush()

        # --- AI department: Vikram Rao's existing team moves here from Engineering ---
        ai_dept = await get_or_create_department(session, "AI", "Applied AI and machine learning")
        ai_head_designation = await get_or_create_designation(session, "AI Head", ai_dept)
        ai_engineer_designation = await get_or_create_designation(session, "AI Engineer", ai_dept)
        senior_ai_engineer_designation = await get_or_create_designation(session, "Senior AI Engineer", ai_dept)

        vikram = await get_employee(session, "vikram.rao@example.com")
        vikram.department_id = ai_dept.id
        vikram.designation_id = ai_head_designation.id
        vikram.manager_id = cto.id

        for email, designation in (
            ("karthik.iyer@example.com", ai_engineer_designation),
            ("aditi.bose@example.com", ai_engineer_designation),
            ("manish.patel@example.com", senior_ai_engineer_designation),
        ):
            report = await get_employee(session, email)
            report.department_id = ai_dept.id
            report.designation_id = designation.id
            # manager_id already points at Vikram - unchanged.

        # --- DevOps department: brand-new team ---
        devops_dept = await get_or_create_department(session, "DevOps", "Infrastructure, CI/CD, and cloud operations")
        devops_head_designation = await get_or_create_designation(session, "DevOps Head", devops_dept)
        cloud_engineer_designation = await get_or_create_designation(session, "Cloud Engineer", devops_dept)

        devops_head_user, _ = await get_or_create_user(session, "dinesh.kannan@example.com", roles[RoleName.MANAGER.value])
        devops_head = await get_or_create_employee(
            session, devops_head_user, await next_employee_code(session), "Dinesh", "Kannan",
            devops_head_designation, EmploymentType.FULL_TIME, manager_id=cto.id, work_location="Bangalore Office",
        )
        await session.flush()

        for first, last, email in (
            ("Harish", "Babu", "harish.babu@example.com"),
            ("Meghna", "Iyer", "meghna.iyer@example.com"),
        ):
            user, _ = await get_or_create_user(session, email, roles[RoleName.EMPLOYEE.value])
            await get_or_create_employee(
                session, user, await next_employee_code(session), first, last,
                cloud_engineer_designation, EmploymentType.FULL_TIME,
                manager_id=devops_head.id, work_location="Bangalore Office",
            )

        # --- Accounts department: Sneha Kulkarni's existing team moves here from Finance ---
        accounts_dept = await get_or_create_department(session, "Accounts", "Accounts payable/receivable and bookkeeping")
        accounts_manager_designation = await get_or_create_designation(session, "Accounts Manager", accounts_dept)
        accountant_designation = await get_or_create_designation(session, "Accountant", accounts_dept)
        senior_accountant_designation = await get_or_create_designation(session, "Senior Accountant", accounts_dept)

        sneha = await get_employee(session, "sneha.kulkarni@example.com")
        sneha.department_id = accounts_dept.id
        sneha.designation_id = accounts_manager_designation.id
        sneha.manager_id = cfo.id

        for email, designation in (
            ("tanvi.joshi@example.com", senior_accountant_designation),
            ("rajesh.kumar@example.com", accountant_designation),
        ):
            report = await get_employee(session, email)
            report.department_id = accounts_dept.id
            report.designation_id = designation.id
            # manager_id already points at Sneha - unchanged.

        # --- Re-parent the remaining department heads under the new C-suite ---
        marcus = await get_employee(session, "manager@example.com")
        marcus.manager_id = cto.id

        rohan = await get_employee(session, "rohan.desai@example.com")
        rohan.manager_id = cfo.id

        lokesh = await get_employee(session, "j.lokesh@example.com")
        lokesh.manager_id = coo.id

        for email in ("sanjay.gupta@example.com", "meenal.deshpande@example.com"):
            employee = await get_employee(session, email)
            employee.manager_id = coo.id

        # Sales and Marketing are intentionally left reporting directly to the
        # CEO - they were never part of this chart.

        await session.flush()

        new_people = [coo, cto, cfo, devops_head]
        result = await session.execute(
            select(Employee).where(Employee.email.in_(["harish.babu@example.com", "meghna.iyer@example.com"]))
        )
        new_people.extend(result.scalars().all())
        for employee in new_people:
            await seed_leave_balances(session, employee, leave_types)

        await session.commit()

    await engine.dispose()
    logger.info("Org v2 restructure complete.")
    logger.info(
        "New accounts: r.rajendran@example.com (COO), v.venkataraman@example.com (CTO), "
        "a.ananthi@example.com (CFO), dinesh.kannan@example.com (DevOps Head), "
        "harish.babu@example.com, meghna.iyer@example.com (Cloud Engineers). Password: %s",
        DEMO_PASSWORD,
    )


if __name__ == "__main__":
    asyncio.run(main())
