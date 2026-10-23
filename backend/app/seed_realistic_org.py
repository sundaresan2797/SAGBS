"""Adds a realistic multi-department org hierarchy on top of the base seed.

Run after `python -m app.seed` (which must have already created the 4 demo
accounts and department/designation reference data):

    python -m app.seed_realistic_org

Idempotent like app.seed: re-running it does not create duplicates, since
every user/employee lookup is by unique email/user_id first.

Builds two managers per department (Engineering/HR extend the two existing
demo accounts - manager@example.com and hr@example.com - rather than
duplicating them) plus 5-8 direct reports split across those two managers,
for a total of 44 employees across 6 departments.
"""

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, engine
from app.models import Designation, Employee, Role
from app.models.enums import EmploymentType, RoleName
from app.seed import (
    DEMO_PASSWORD,
    get_or_create_employee,
    get_or_create_user,
    seed_departments_and_designations,
    seed_leave_balances,
    seed_leave_types,
    seed_roles_and_permissions,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("ems.seed_realistic_org")

TODAY = date.today()


def months_ago(months: int) -> date:
    return TODAY - timedelta(days=months * 30)


# (email, first, last, designation_key, role, months_since_joining, work_location)
Manager = tuple[str, str, str, str, RoleName, int, str]
# (email, first, last, designation_key, months_since_joining, work_location, manager_email)
Report = tuple[str, str, str, str, int, str, str]

DEPARTMENTS: dict[str, dict] = {
    "Engineering": {
        "existing_managers": {"manager@example.com"},  # Marcus Nguyen, already seeded
        "existing_reports": {"employee@example.com": "manager@example.com"},  # Elena Ford -> Marcus
        "new_managers": [
            ("vikram.rao@example.com", "Vikram", "Rao", "Engineering:Tech Lead", RoleName.MANAGER, 20, "Head Office"),
        ],
        "new_reports": [
            ("sara.khan@example.com", "Sara", "Khan", "Engineering:Software Engineer", 10, "Head Office", "manager@example.com"),
            ("rahul.verma@example.com", "Rahul", "Verma", "Engineering:Software Engineer", 8, "Remote", "manager@example.com"),
            ("karthik.iyer@example.com", "Karthik", "Iyer", "Engineering:Software Engineer", 14, "Head Office", "vikram.rao@example.com"),
            ("aditi.bose@example.com", "Aditi", "Bose", "Engineering:Software Engineer", 6, "Remote", "vikram.rao@example.com"),
            ("manish.patel@example.com", "Manish", "Patel", "Engineering:Senior Software Engineer", 18, "Head Office", "vikram.rao@example.com"),
        ],
    },
    "Human Resources": {
        "existing_managers": {"hr@example.com"},  # Hannah Reyes, already seeded
        "existing_reports": {},
        "new_managers": [
            ("ritu.kapoor@example.com", "Ritu", "Kapoor", "Human Resources:HR Business Partner", RoleName.HR, 16, "Head Office"),
        ],
        "new_reports": [
            ("divya.nair@example.com", "Divya", "Nair", "Human Resources:HR Executive", 9, "Head Office", "hr@example.com"),
            ("farhan.sheikh@example.com", "Farhan", "Sheikh", "Human Resources:HR Executive", 7, "Head Office", "hr@example.com"),
            ("naina.verma@example.com", "Naina", "Verma", "Human Resources:HR Executive", 4, "Remote", "hr@example.com"),
            ("lakshmi.narayan@example.com", "Lakshmi", "Narayan", "Human Resources:HR Executive", 11, "Head Office", "ritu.kapoor@example.com"),
            ("om.prakash@example.com", "Om", "Prakash", "Human Resources:HR Executive", 5, "Head Office", "ritu.kapoor@example.com"),
        ],
    },
    "Finance": {
        "existing_managers": set(),
        "existing_reports": {},
        "new_managers": [
            ("rohan.desai@example.com", "Rohan", "Desai", "Finance:Finance Manager", RoleName.MANAGER, 22, "Head Office"),
            ("sneha.kulkarni@example.com", "Sneha", "Kulkarni", "Finance:Finance Team Lead", RoleName.MANAGER, 15, "Head Office"),
        ],
        "new_reports": [
            ("meera.pillai@example.com", "Meera", "Pillai", "Finance:Accountant", 12, "Head Office", "rohan.desai@example.com"),
            ("abhinav.singh@example.com", "Abhinav", "Singh", "Finance:Accountant", 9, "Head Office", "rohan.desai@example.com"),
            ("nikhil.bhatt@example.com", "Nikhil", "Bhatt", "Finance:Accountant", 3, "Remote", "rohan.desai@example.com"),
            ("tanvi.joshi@example.com", "Tanvi", "Joshi", "Finance:Senior Accountant", 17, "Head Office", "sneha.kulkarni@example.com"),
            ("rajesh.kumar@example.com", "Rajesh", "Kumar", "Finance:Accountant", 6, "Head Office", "sneha.kulkarni@example.com"),
        ],
    },
    "Sales": {
        "existing_managers": set(),
        "existing_reports": {},
        "new_managers": [
            ("ayesha.khan@example.com", "Ayesha", "Khan", "Sales:Sales Manager", RoleName.MANAGER, 24, "Head Office"),
            ("karan.malhotra@example.com", "Karan", "Malhotra", "Sales:Regional Sales Manager", RoleName.MANAGER, 19, "Bangalore Office"),
        ],
        "new_reports": [
            ("vivek.kumar@example.com", "Vivek", "Kumar", "Sales:Sales Executive", 13, "Head Office", "ayesha.khan@example.com"),
            ("neha.reddy@example.com", "Neha", "Reddy", "Sales:Sales Executive", 8, "Head Office", "ayesha.khan@example.com"),
            ("suresh.pillai@example.com", "Suresh", "Pillai", "Sales:Sales Executive", 5, "Remote", "ayesha.khan@example.com"),
            ("anjali.gupta@example.com", "Anjali", "Gupta", "Sales:Senior Sales Executive", 16, "Bangalore Office", "karan.malhotra@example.com"),
            ("deepak.chawla@example.com", "Deepak", "Chawla", "Sales:Sales Executive", 10, "Bangalore Office", "karan.malhotra@example.com"),
            ("priyanka.rao@example.com", "Priyanka", "Rao", "Sales:Sales Executive", 4, "Bangalore Office", "karan.malhotra@example.com"),
        ],
    },
    "Marketing": {
        "existing_managers": set(),
        "existing_reports": {},
        "new_managers": [
            ("aditya.joshi@example.com", "Aditya", "Joshi", "Marketing:Marketing Manager", RoleName.MANAGER, 21, "Head Office"),
            ("ishita.bansal@example.com", "Ishita", "Bansal", "Marketing:Marketing Team Lead", RoleName.MANAGER, 13, "Remote"),
        ],
        "new_reports": [
            ("kavya.menon@example.com", "Kavya", "Menon", "Marketing:Marketing Executive", 11, "Head Office", "aditya.joshi@example.com"),
            ("rohit.saxena@example.com", "Rohit", "Saxena", "Marketing:Marketing Executive", 7, "Head Office", "aditya.joshi@example.com"),
            ("tara.iyer@example.com", "Tara", "Iyer", "Marketing:Marketing Executive", 2, "Remote", "aditya.joshi@example.com"),
            ("simran.chopra@example.com", "Simran", "Chopra", "Marketing:Senior Marketing Executive", 14, "Remote", "ishita.bansal@example.com"),
            ("yash.trivedi@example.com", "Yash", "Trivedi", "Marketing:Marketing Executive", 6, "Head Office", "ishita.bansal@example.com"),
        ],
    },
    "Operations": {
        "existing_managers": set(),
        "existing_reports": {},
        "new_managers": [
            ("sanjay.gupta@example.com", "Sanjay", "Gupta", "Operations:Operations Manager", RoleName.MANAGER, 23, "Head Office"),
            ("meenal.deshpande@example.com", "Meenal", "Deshpande", "Operations:Operations Team Lead", RoleName.MANAGER, 12, "Head Office"),
        ],
        "new_reports": [
            ("pooja.shah@example.com", "Pooja", "Shah", "Operations:Operations Executive", 9, "Head Office", "sanjay.gupta@example.com"),
            ("naveen.reddy@example.com", "Naveen", "Reddy", "Operations:Operations Executive", 5, "Head Office", "sanjay.gupta@example.com"),
            ("ajay.nair@example.com", "Ajay", "Nair", "Operations:Operations Executive", 3, "Remote", "sanjay.gupta@example.com"),
            ("ramesh.iyer@example.com", "Ramesh", "Iyer", "Operations:Senior Operations Executive", 15, "Head Office", "meenal.deshpande@example.com"),
            ("swati.agarwal@example.com", "Swati", "Agarwal", "Operations:Operations Executive", 7, "Head Office", "meenal.deshpande@example.com"),
        ],
    },
}


async def next_employee_code(session: AsyncSession) -> str:
    result = await session.execute(select(Employee.employee_code))
    codes = [c for c in result.scalars().all() if c.startswith("EMP-")]
    next_number = max((int(c.split("-")[1]) for c in codes), default=0) + 1
    return f"EMP-{next_number:04d}"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        roles = await seed_roles_and_permissions(session)
        designations = await seed_departments_and_designations(session)
        leave_types = await seed_leave_types(session)
        await session.commit()

        # employee_code lookups by email, populated as we go so "manager_email"
        # references (which may point at a manager created earlier in this
        # same run, or an existing demo account) always resolve correctly.
        employee_by_email: dict[str, Employee] = {}

        # Pick up the 3 pre-existing demo employees so cross-department
        # manager references work identically whether the manager already
        # existed or is new.
        for email in ("hr@example.com", "manager@example.com", "employee@example.com"):
            result = await session.execute(select(Employee).where(Employee.email == email))
            existing = result.scalar_one_or_none()
            if existing is not None:
                employee_by_email[email] = existing

        created_count = 0

        for dept_name, spec in DEPARTMENTS.items():
            for email, first, last, desig_key, role_name, months, location in spec["new_managers"]:
                if email in employee_by_email:
                    continue
                user, _ = await get_or_create_user(session, email, roles[role_name.value])
                code = await next_employee_code(session)
                employee = await get_or_create_employee(
                    session,
                    user,
                    code,
                    first,
                    last,
                    designations[desig_key],
                    EmploymentType.FULL_TIME,
                    date_of_joining=months_ago(months),
                    work_location=location,
                )
                employee_by_email[email] = employee
                created_count += 1

            for email, first, last, desig_key, months, location, manager_email in spec["new_reports"]:
                if email in employee_by_email:
                    continue
                manager = employee_by_email.get(manager_email)
                if manager is None:
                    raise RuntimeError(f"Manager {manager_email} must be created before report {email}")

                report_role = roles[RoleName.HR.value] if dept_name == "Human Resources" else roles[RoleName.EMPLOYEE.value]
                user, _ = await get_or_create_user(session, email, report_role)
                code = await next_employee_code(session)
                employee = await get_or_create_employee(
                    session,
                    user,
                    code,
                    first,
                    last,
                    designations[desig_key],
                    EmploymentType.FULL_TIME,
                    manager_id=manager.id,
                    date_of_joining=months_ago(months),
                    work_location=location,
                )
                employee_by_email[email] = employee
                created_count += 1

            # Wire the pre-existing demo employees into this department's
            # hierarchy (Elena Ford -> Marcus Nguyen) rather than leaving
            # them dangling outside the new reporting structure.
            for report_email, manager_email in spec["existing_reports"].items():
                report = employee_by_email.get(report_email)
                manager = employee_by_email.get(manager_email)
                if report is not None and manager is not None and report.manager_id != manager.id:
                    report.manager_id = manager.id

        await session.flush()

        for employee in employee_by_email.values():
            await seed_leave_balances(session, employee, leave_types)

        await session.commit()

    await engine.dispose()

    total = len(employee_by_email)
    logger.info("Realistic org seed complete: %d new employee(s) created, %d total across the org.", created_count, total)
    logger.info("All new accounts share the password: %s", DEMO_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
