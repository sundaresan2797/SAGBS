"""Idempotent seed script for local/dev environments.

Run with:
    python -m app.seed

Seeds roles, permissions, departments, designations, leave types, and a
demo user per role. Safe to re-run - existing rows are left untouched.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.database.session import AsyncSessionLocal, engine
from app.models import (
    Department,
    Designation,
    DocumentType,
    Employee,
    LeaveBalance,
    LeaveType,
    Permission,
    Role,
    RolePermission,
    User,
)
from app.models.enums import EmploymentType, RoleName
from app.utils.permissions import PERMISSIONS, ROLE_PERMISSIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("ems.seed")

DEMO_PASSWORD = "ChangeMe123!"

DEPARTMENTS = [
    ("Engineering", "Product engineering and platform teams"),
    ("Human Resources", "People operations and talent management"),
    ("Finance", "Accounting, payroll, and financial planning"),
    ("Sales", "Revenue and client acquisition"),
    ("Marketing", "Brand, content, and demand generation"),
    ("Operations", "Business operations and facilities"),
]

DESIGNATIONS = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Tech Lead", "Engineering Manager"],
    "Human Resources": ["HR Executive", "HR Manager", "HR Business Partner"],
    "Finance": ["Accountant", "Senior Accountant", "Finance Manager", "Finance Team Lead"],
    "Sales": ["Sales Executive", "Senior Sales Executive", "Sales Manager", "Regional Sales Manager"],
    "Marketing": ["Marketing Executive", "Senior Marketing Executive", "Marketing Manager", "Marketing Team Lead"],
    "Operations": ["Operations Executive", "Senior Operations Executive", "Operations Manager", "Operations Team Lead"],
}

DOCUMENT_TYPES = [
    ("OFFER_LETTER", "Offer Letter"),
    ("EMPLOYMENT_CONTRACT", "Employment Contract"),
    ("ID_PROOF", "ID Proof"),
    ("RESUME", "Resume"),
    ("CERTIFICATION", "Certification"),
    ("OTHER", "Other"),
]

LEAVE_TYPES = [
    ("CASUAL", "Casual Leave", True, 12),
    ("SICK", "Sick Leave", True, 10),
    ("EARNED", "Earned Leave", True, 15),
    ("UNPAID", "Unpaid Leave", False, 0),
]


async def get_or_create_role(session: AsyncSession, name: str, description: str) -> Role:
    result = await session.execute(select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=description)
        session.add(role)
        await session.flush()
        logger.info("Created role %s", name)
    return role


async def get_or_create_permission(session: AsyncSession, code: str, description: str) -> Permission:
    result = await session.execute(select(Permission).where(Permission.code == code))
    permission = result.scalar_one_or_none()
    if permission is None:
        permission = Permission(code=code, description=description)
        session.add(permission)
        await session.flush()
    return permission


async def seed_roles_and_permissions(session: AsyncSession) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for role_name in RoleName:
        roles[role_name.value] = await get_or_create_role(session, role_name.value, f"{role_name.value.title()} role")

    permissions: dict[str, Permission] = {}
    for code, description in PERMISSIONS:
        permissions[code] = await get_or_create_permission(session, code, description)

    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles[role_name.value]
        for code in codes:
            permission = permissions[code]
            exists = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id, RolePermission.permission_id == permission.id
                )
            )
            if exists.scalar_one_or_none() is None:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    await session.flush()
    logger.info("Seeded %d roles and %d permissions", len(roles), len(permissions))
    return roles


async def seed_departments_and_designations(session: AsyncSession) -> dict[str, Designation]:
    designations_by_name: dict[str, Designation] = {}

    for dept_name, description in DEPARTMENTS:
        result = await session.execute(select(Department).where(Department.name == dept_name))
        department = result.scalar_one_or_none()
        if department is None:
            department = Department(name=dept_name, description=description)
            session.add(department)
            await session.flush()
            logger.info("Created department %s", dept_name)

        for desig_name in DESIGNATIONS[dept_name]:
            result = await session.execute(
                select(Designation).where(
                    Designation.name == desig_name, Designation.department_id == department.id
                )
            )
            designation = result.scalar_one_or_none()
            if designation is None:
                designation = Designation(name=desig_name, department_id=department.id)
                session.add(designation)
                await session.flush()
            designations_by_name[f"{dept_name}:{desig_name}"] = designation

    await session.flush()
    return designations_by_name


async def seed_document_types(session: AsyncSession) -> None:
    for code, name in DOCUMENT_TYPES:
        result = await session.execute(select(DocumentType).where(DocumentType.code == code))
        if result.scalar_one_or_none() is None:
            session.add(DocumentType(code=code, name=name, requires_expiry=False, is_active=True))
            await session.flush()
            logger.info("Created document type %s", code)


async def seed_leave_types(session: AsyncSession) -> list[LeaveType]:
    leave_types: list[LeaveType] = []
    for code, name, is_paid, default_days in LEAVE_TYPES:
        result = await session.execute(select(LeaveType).where(LeaveType.code == code))
        leave_type = result.scalar_one_or_none()
        if leave_type is None:
            leave_type = LeaveType(
                code=code, name=name, is_paid=is_paid, default_annual_days=default_days, is_active=True
            )
            session.add(leave_type)
            await session.flush()
            logger.info("Created leave type %s", code)
        leave_types.append(leave_type)
    return leave_types


async def seed_leave_balances(session: AsyncSession, employee: Employee, leave_types: list[LeaveType]) -> None:
    year = date.today().year
    for leave_type in leave_types:
        if not leave_type.is_paid:
            continue
        result = await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee.id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.year == year,
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(
                LeaveBalance(
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=year,
                    allocated_days=leave_type.default_annual_days,
                    used_days=0,
                )
            )
    await session.flush()


async def get_or_create_user(
    session: AsyncSession, email: str, role: Role, password: str = DEMO_PASSWORD
) -> tuple[User, bool]:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role_id=role.id,
            is_active=True,
            must_change_password=True,
        )
        session.add(user)
        await session.flush()
        return user, True
    return user, False


async def get_or_create_employee(
    session: AsyncSession,
    user: User,
    code: str,
    first_name: str,
    last_name: str,
    designation: Designation,
    employment_type: EmploymentType,
    manager_id: int | None = None,
    date_of_joining: date | None = None,
    work_location: str = "Head Office",
) -> Employee:
    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is None:
        employee = Employee(
            employee_code=code,
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            email=user.email,
            date_of_joining=date_of_joining or date.today(),
            department_id=designation.department_id,
            designation_id=designation.id,
            manager_id=manager_id,
            employment_type=employment_type,
            work_location=work_location,
        )
        session.add(employee)
        await session.flush()
        logger.info("Created employee record for %s", user.email)
    return employee


async def seed_demo_users(
    session: AsyncSession, roles: dict[str, Role], designations: dict[str, Designation], leave_types: list[LeaveType]
) -> None:
    admin_user, created = await get_or_create_user(session, "admin@example.com", roles[RoleName.ADMIN.value])
    if created:
        logger.info("Created demo admin user admin@example.com")

    hr_user, _ = await get_or_create_user(session, "hr@example.com", roles[RoleName.HR.value])
    manager_user, _ = await get_or_create_user(session, "manager@example.com", roles[RoleName.MANAGER.value])
    employee_user, _ = await get_or_create_user(session, "employee@example.com", roles[RoleName.EMPLOYEE.value])
    accountant_user, _ = await get_or_create_user(
        session, "accountant@example.com", roles[RoleName.ACCOUNTANT.value]
    )

    hr_designation = designations["Human Resources:HR Manager"]
    manager_designation = designations["Engineering:Engineering Manager"]
    employee_designation = designations["Engineering:Software Engineer"]
    accountant_designation = designations["Finance:Accountant"]

    hr_employee = await get_or_create_employee(
        session, hr_user, "EMP-0001", "Hannah", "Reyes", hr_designation, EmploymentType.FULL_TIME
    )

    manager_employee = await get_or_create_employee(
        session, manager_user, "EMP-0002", "Marcus", "Nguyen", manager_designation, EmploymentType.FULL_TIME
    )

    employee_employee = await get_or_create_employee(
        session,
        employee_user,
        "EMP-0003",
        "Elena",
        "Ford",
        employee_designation,
        EmploymentType.FULL_TIME,
        manager_id=manager_employee.id,
    )

    accountant_employee = await get_or_create_employee(
        session, accountant_user, "EMP-ACCT1", "Priya", "Shankar", accountant_designation, EmploymentType.FULL_TIME
    )

    for employee in (hr_employee, manager_employee, employee_employee, accountant_employee):
        await seed_leave_balances(session, employee, leave_types)

    await session.flush()


async def main() -> None:
    async with AsyncSessionLocal() as session:
        roles = await seed_roles_and_permissions(session)
        designations = await seed_departments_and_designations(session)
        leave_types = await seed_leave_types(session)
        await seed_document_types(session)
        await seed_demo_users(session, roles, designations, leave_types)
        await session.commit()

    await engine.dispose()

    logger.info("Seed complete.")
    logger.info("Demo accounts (password: %s - change immediately):", DEMO_PASSWORD)
    logger.info("  admin@example.com      (ADMIN)")
    logger.info("  hr@example.com         (HR)")
    logger.info("  manager@example.com    (MANAGER)")
    logger.info("  employee@example.com   (EMPLOYEE)")
    logger.info("  accountant@example.com (ACCOUNTANT)")


if __name__ == "__main__":
    asyncio.run(main())
