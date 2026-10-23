import hashlib
import json
import secrets
from dataclasses import asdict

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.core.redis import CacheKeys, CacheTTL, redis_service
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.enums import AuditAction, EmployeeStatus, RoleName
from app.models.rbac import Role
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.repositories.designation_repository import DesignationRepository
from app.repositories.employee_repository import EmployeeFilters, EmployeeRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedData
from app.schemas.employee import (
    EmailChangeResult,
    EmployeeCreate,
    EmployeeCreatedResponse,
    EmployeeListItem,
    EmployeeOut,
    EmployeeStatusUpdate,
    EmployeeUpdate,
    LoginRulesOut,
    PasswordResetResult,
)
from app.services.audit_service import log_action

INACTIVE_STATUSES = {EmployeeStatus.RESIGNED, EmployeeStatus.TERMINATED, EmployeeStatus.INACTIVE}


def _generate_temp_password() -> str:
    return f"Temp-{secrets.token_urlsafe(9)}"


def _filters_cache_key(filters: EmployeeFilters, page: int, page_size: int, sort_by: str, sort_desc: bool, scope: str) -> str:
    payload = {
        "filters": {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(filters).items()},
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_desc": sort_desc,
        "scope": scope,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return CacheKeys.employees_list(digest)


async def _invalidate_employee_caches(employee_id: int | None = None) -> None:
    if employee_id is not None:
        await redis_service.delete(CacheKeys.employee_profile(employee_id))
    await redis_service.delete_pattern(f"{CacheKeys.EMPLOYEES_LIST_PREFIX}*")
    # DASHBOARD_DEPARTMENTS too: a new hire or a department transfer (via
    # update_employee) changes "Team size by department" just as much as it
    # changes the headcount in DASHBOARD_SUMMARY - both must clear together,
    # or the chart can show a stale team size for up to CacheTTL.DASHBOARD.
    await redis_service.delete(CacheKeys.DASHBOARD_SUMMARY, CacheKeys.DASHBOARD_DEPARTMENTS)


async def _apply_role_scope(session: AsyncSession, current_user: User, filters: EmployeeFilters) -> str:
    """Mutates filters in place for role-scoped visibility. Returns a scope tag for cache keying.

    Only MANAGER is narrowed to direct reports here - deliberately, not by omission. FOUNDER, ADMIN
    and HR all need the full company directory to do their jobs, and EXECUTIVE (business leadership -
    CEO/COO/CTO/CFO) is included with them on purpose: browsing the whole staff list is normal for
    that role, even though its authority to *act* on people (approve leave, assign tasks, fix
    attendance) still only reaches its own reports via the manager_id chain elsewhere in this app.
    """
    if current_user.role.name == RoleName.MANAGER.value:
        employee_repo = EmployeeRepository(session)
        own_employee = await employee_repo.get_by_user_id(current_user.id)
        if own_employee is None:
            filters.employee_ids = []
        else:
            filters.manager_id = own_employee.id
        return f"manager:{current_user.id}"
    return "unrestricted"


async def list_employees(
    session: AsyncSession,
    current_user: User,
    filters: EmployeeFilters,
    page: int,
    page_size: int,
    sort_by: str = "id",
    sort_desc: bool = False,
) -> PaginatedData[EmployeeListItem]:
    scope = await _apply_role_scope(session, current_user, filters)
    cache_key = _filters_cache_key(filters, page, page_size, sort_by, sort_desc, scope)

    cached = await redis_service.get(cache_key)
    if cached is not None:
        return PaginatedData[EmployeeListItem].model_validate(cached)

    repo = EmployeeRepository(session)
    if filters.employee_ids == []:
        employees, total = [], 0
    else:
        employees, total = await repo.list_paginated(filters, page, page_size, sort_by, sort_desc)

    items = [EmployeeListItem.from_model(e) for e in employees]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    result = PaginatedData[EmployeeListItem](items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)

    await redis_service.set(cache_key, result.model_dump(mode="json"), CacheTTL.EMPLOYEES_LIST)
    return result


async def get_employee_detail(session: AsyncSession, employee_id: int, current_user: User) -> EmployeeOut:
    repo = EmployeeRepository(session)
    employee = await repo.get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    # Manager only reaches a full profile (phone, date of birth) for themselves or a direct report. Executive
    # has full Founder parity (see migration b5f545e1a157) and is unrestricted here, same as HR/Founder/Admin.
    if current_user.role.name == RoleName.MANAGER.value:
        own_employee = await repo.get_by_user_id(current_user.id)
        is_self = own_employee is not None and own_employee.id == employee.id
        is_direct_report = employee.manager_id is not None and own_employee is not None and employee.manager_id == own_employee.id
        if not (is_self or is_direct_report):
            raise ForbiddenError(
                "You can only view your own profile or your direct reports.", error_code="EMPLOYEE_OUT_OF_SCOPE"
            )

    cache_key = CacheKeys.employee_profile(employee_id)
    cached = await redis_service.get(cache_key)
    if cached is not None:
        return EmployeeOut.model_validate(cached)

    result = EmployeeOut.from_model(employee)
    await redis_service.set(cache_key, result.model_dump(mode="json"), CacheTTL.EMPLOYEE_PROFILE)
    return result


async def get_my_employee_profile(session: AsyncSession, current_user: User) -> EmployeeOut:
    repo = EmployeeRepository(session)
    employee = await repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")
    return EmployeeOut.from_model(employee)


async def create_employee(
    session: AsyncSession, payload: EmployeeCreate, current_user: User, request: Request | None = None
) -> EmployeeCreatedResponse:
    dept_repo = DepartmentRepository(session)
    department = await dept_repo.get_by_id(payload.department_id)
    if department is None:
        raise NotFoundError("Department not found.", error_code="DEPARTMENT_NOT_FOUND")

    desig_repo = DesignationRepository(session)
    designation = await desig_repo.get_by_id(payload.designation_id)
    if designation is None:
        raise NotFoundError("Designation not found.", error_code="DESIGNATION_NOT_FOUND")
    if designation.department_id != payload.department_id:
        raise BusinessRuleError(
            "The selected designation does not belong to the selected department.",
            error_code="DESIGNATION_DEPARTMENT_MISMATCH",
        )

    employee_repo = EmployeeRepository(session)
    if payload.manager_id is not None:
        manager = await employee_repo.get_by_id(payload.manager_id)
        if manager is None:
            raise NotFoundError("Manager not found.", error_code="MANAGER_NOT_FOUND")

    user_repo = UserRepository(session)
    if await user_repo.get_by_email(payload.email) is not None:
        raise ConflictError(f"An account with email '{payload.email}' already exists.", error_code="EMAIL_EXISTS")
    if await employee_repo.get_by_email(payload.email) is not None:
        raise ConflictError(
            f"An employee with email '{payload.email}' already exists.", error_code="EMAIL_EXISTS"
        )

    # Only ADMIN may grant ADMIN, FOUNDER, HR, EXECUTIVE, or ACCOUNTANT access; HR
    # (which also holds employee:create) may only provision MANAGER/EMPLOYEE
    # accounts. EXECUTIVE and ACCOUNTANT are included here because they carry
    # real hierarchical or financial authority - granting either is a
    # leadership decision, not routine HR onboarding. Without this, any HR
    # user could hand themselves or anyone else elevated access simply by
    # creating an "employee" with one of these roles.
    if current_user.role.name != RoleName.ADMIN.value and payload.role in (
        RoleName.ADMIN,
        RoleName.HR,
        RoleName.FOUNDER,
        RoleName.EXECUTIVE,
        RoleName.ACCOUNTANT,
    ):
        raise ForbiddenError(
            "Only an administrator can create Admin, Founder, HR, Executive, or Accountant accounts.",
            error_code="ROLE_ASSIGNMENT_FORBIDDEN",
        )

    role_result = await session.execute(select(Role).where(Role.name == payload.role.value))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.", error_code="ROLE_NOT_FOUND")

    temp_password = _generate_temp_password()
    user = User(
        email=payload.email,
        hashed_password=hash_password(temp_password),
        role_id=role.id,
        is_active=True,
        must_change_password=True,
    )
    session.add(user)
    await session.flush()

    employee = Employee(
        employee_code=f"TEMP-{secrets.token_hex(4)}",
        user_id=user.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        date_of_birth=payload.date_of_birth,
        date_of_joining=payload.date_of_joining,
        department_id=payload.department_id,
        designation_id=payload.designation_id,
        manager_id=payload.manager_id,
        employment_type=payload.employment_type,
        work_location=payload.work_location,
        status=EmployeeStatus.ACTIVE,
    )
    employee_repo.add(employee)
    await session.flush()

    employee.employee_code = f"EMP-{employee.id:04d}"
    employee.department = department
    employee.designation = designation

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_EMPLOYEE,
        entity_type="Employee",
        entity_id=employee.id,
        description=f"Created employee {employee.employee_code} ({employee.email})",
        request=request,
    )
    await session.commit()
    await _invalidate_employee_caches()

    return EmployeeCreatedResponse(
        employee=EmployeeOut.from_model(employee), temporary_password=temp_password, login_email=user.email
    )


async def update_employee(
    session: AsyncSession,
    employee_id: int,
    payload: EmployeeUpdate,
    current_user: User,
    request: Request | None = None,
) -> EmployeeOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    if payload.department_id is not None:
        dept_repo = DepartmentRepository(session)
        department = await dept_repo.get_by_id(payload.department_id)
        if department is None:
            raise NotFoundError("Department not found.", error_code="DEPARTMENT_NOT_FOUND")
        employee.department_id = payload.department_id
        employee.department = department

    if payload.designation_id is not None:
        desig_repo = DesignationRepository(session)
        designation = await desig_repo.get_by_id(payload.designation_id)
        if designation is None:
            raise NotFoundError("Designation not found.", error_code="DESIGNATION_NOT_FOUND")
        employee.designation_id = payload.designation_id
        employee.designation = designation

    # Adding someone checks that the job title belongs to the department; editing must too - changing only
    # the department would otherwise keep a title from a different one.
    if (payload.department_id is not None or payload.designation_id is not None) and (
        employee.designation.department_id != employee.department_id
    ):
        raise BusinessRuleError(
            "The selected designation does not belong to the selected department.",
            error_code="DESIGNATION_DEPARTMENT_MISMATCH",
        )

    # "manager_id": null means "no manager" (clear it); leaving the field out means "leave it alone".
    if "manager_id" in payload.model_fields_set:
        if payload.manager_id is None:
            employee.manager_id = None
            employee.manager = None
        else:
            if payload.manager_id == employee.id:
                raise BusinessRuleError("An employee cannot be their own manager.", error_code="INVALID_MANAGER")
            manager = await employee_repo.get_by_id(payload.manager_id)
            if manager is None:
                raise NotFoundError("Manager not found.", error_code="MANAGER_NOT_FOUND")
            # Walk up from the new manager: reaching this employee means a loop (A under B under A), which
            # would leave nobody able to approve leave or assign tasks for either of them.
            above, steps = manager, 0
            while above is not None and steps < 100:
                if above.id == employee.id:
                    raise BusinessRuleError(
                        f"{manager.full_name} already reports to {employee.full_name} (directly or through others), "
                        "so this would create a loop.",
                        error_code="MANAGER_LOOP",
                    )
                above = await employee_repo.get_by_id(above.manager_id) if above.manager_id is not None else None
                steps += 1
            employee.manager_id = payload.manager_id
            employee.manager = manager

    for field in ("first_name", "last_name", "phone", "date_of_birth", "date_of_joining", "employment_type", "work_location"):
        value = getattr(payload, field)
        if value is not None:
            setattr(employee, field, value)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_EMPLOYEE,
        entity_type="Employee",
        entity_id=employee.id,
        description=f"Updated employee {employee.employee_code}",
        request=request,
    )
    await session.commit()
    await _invalidate_employee_caches(employee.id)

    return EmployeeOut.from_model(employee)


async def update_my_profile(session: AsyncSession, current_user: User, phone: str | None) -> EmployeeOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_user_id(current_user.id)
    if employee is None:
        raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")

    if phone is not None:
        employee.phone = phone

    await session.commit()
    await _invalidate_employee_caches(employee.id)

    return EmployeeOut.from_model(employee)


async def _role_permissions(session: AsyncSession) -> dict[str, set[str]]:
    roles = (await session.execute(select(Role))).scalars().all()
    return {role.name: {p.code for p in role.permissions} for role in roles}


def _may_manage_login_of(actor: User, actor_permissions: set[str], role_permissions: set[str]) -> bool:
    """Admin is the system's account administrator and may manage any login - reset its password, change
    its role, change its email - regardless of what that login can do; Admin still has no payroll
    permission itself, so it gains no access to salary data by doing this, only account-level control.
    Everyone else may only manage a login whose powers are all powers they hold themselves, so e.g. HR
    (which has no payroll access) still can't take over the Founder's or the Accountant's login."""
    if actor.role.name == RoleName.ADMIN.value:
        return True
    return role_permissions <= actor_permissions


async def get_login_rules(session: AsyncSession, current_user: User) -> LoginRulesOut:
    by_role = await _role_permissions(session)
    mine = {p.code for p in current_user.role.permissions}
    return LoginRulesOut(
        assignable_roles=sorted(r for r, perms in by_role.items() if _may_manage_login_of(current_user, mine, perms)),
        protected_roles=sorted(r for r, perms in by_role.items() if not _may_manage_login_of(current_user, mine, perms)),
    )


async def change_user_role(
    session: AsyncSession, employee_id: int, role_name: str, current_user: User, request: Request | None = None
) -> None:
    employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    user = await UserRepository(session).get_by_id(employee.user_id)
    if user is None:
        raise NotFoundError("No login account is linked to this employee.", error_code="EMPLOYEE_NOT_FOUND")

    by_role = await _role_permissions(session)
    if role_name not in by_role:
        raise NotFoundError("That role does not exist.", error_code="ROLE_NOT_FOUND")
    if role_name == user.role.name:
        raise BusinessRuleError("They already have that role.", error_code="ROLE_UNCHANGED")

    mine = {p.code for p in current_user.role.permissions}
    if not _may_manage_login_of(current_user, mine, by_role[user.role.name]) or not _may_manage_login_of(current_user, mine, by_role[role_name]):
        raise ForbiddenError(
            "You can't change roles to or from one that carries powers you don't have yourself (such as payroll).",
            error_code="ROLE_CHANGE_PROTECTED",
        )
    if user.role.name == RoleName.ADMIN.value:
        admins = (await session.execute(select(func.count()).select_from(User).join(Role).where(Role.name == RoleName.ADMIN.value, User.is_active.is_(True)))).scalar_one()
        if admins <= 1:
            raise BusinessRuleError("This is the only Admin login, so it can't be changed.", error_code="LAST_ADMIN")

    previous = user.role.name
    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one()
    user.role_id = role.id
    user.role = role
    user.token_version += 1  # ends their sessions, so the new role applies from their next sign-in

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CHANGE_USER_ROLE,
        entity_type="User",
        entity_id=user.id,
        description=f"Changed role of {employee.employee_code} ({user.email}) from {previous} to {role_name}",
        request=request,
    )
    await session.commit()
    await _invalidate_employee_caches(employee.id)


async def change_user_email(
    session: AsyncSession,
    employee_id: int,
    new_email: str,
    current_user: User,
    request: Request | None = None,
) -> EmailChangeResult:
    """Change an employee's login email (e.g. moving them off a personal address onto a company one).

    Same protection as resetting a password or changing a role: you may only touch a login whose powers
    are all powers you hold yourself. The employee's own record and their login are kept in sync - they
    are two copies of the same address today - and changing it ends their current sessions, the same as a
    password reset, since it is a new identity for the login going forward.
    """
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(employee.user_id)
    if user is None:
        raise NotFoundError("No login account is linked to this employee.", error_code="EMPLOYEE_NOT_FOUND")

    by_role = await _role_permissions(session)
    if not _may_manage_login_of(current_user, {p.code for p in current_user.role.permissions}, by_role[user.role.name]):
        raise ForbiddenError(
            "You can't change this login's email: it carries powers you don't have yourself (such as payroll).",
            error_code="LOGIN_PROTECTED",
        )

    if new_email == user.email:
        raise BusinessRuleError("This is already their email.", error_code="EMAIL_UNCHANGED")
    existing_user = await user_repo.get_by_email(new_email)
    if existing_user is not None and existing_user.id != user.id:
        raise ConflictError(f"An account with email '{new_email}' already exists.", error_code="EMAIL_EXISTS")
    existing_employee = await employee_repo.get_by_email(new_email)
    if existing_employee is not None and existing_employee.id != employee.id:
        raise ConflictError(f"An employee with email '{new_email}' already exists.", error_code="EMAIL_EXISTS")

    old_email = user.email
    user.email = new_email
    employee.email = new_email
    user.token_version += 1  # ends their sessions - they sign in again with the new address

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CHANGE_USER_EMAIL,
        entity_type="User",
        entity_id=user.id,
        description=f"Changed login email for {employee.employee_code} from {old_email} to {new_email}",
        request=request,
    )
    await session.commit()
    await _invalidate_employee_caches(employee.id)

    return EmailChangeResult(employee_id=employee.id, new_login_email=new_email)


async def admin_reset_password(
    session: AsyncSession,
    employee_id: int,
    new_password: str | None,
    current_user: User,
    request: Request | None = None,
) -> PasswordResetResult:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(employee.user_id)
    if user is None:
        raise NotFoundError("No login account is linked to this employee.", error_code="EMPLOYEE_NOT_FOUND")

    by_role = await _role_permissions(session)
    if not _may_manage_login_of(current_user, {p.code for p in current_user.role.permissions}, by_role[user.role.name]):
        raise ForbiddenError(
            "You can't reset this login's password: it carries powers you don't have yourself (such as payroll). "
            "They can use \"Forgot password\" on the sign-in page.",
            error_code="LOGIN_PROTECTED",
        )

    password = new_password or _generate_temp_password()
    user.hashed_password = hash_password(password)
    user.must_change_password = True
    user.token_version += 1

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.RESET_USER_PASSWORD,
        entity_type="User",
        entity_id=user.id,
        description=f"Reset login password for {employee.employee_code} ({user.email})",
        request=request,
    )
    await session.commit()

    return PasswordResetResult(login_email=user.email, temporary_password=password)


async def update_employee_status(
    session: AsyncSession,
    employee_id: int,
    payload: EmployeeStatusUpdate,
    current_user: User,
    request: Request | None = None,
) -> EmployeeOut:
    employee_repo = EmployeeRepository(session)
    employee = await employee_repo.get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")

    if payload.status in INACTIVE_STATUSES and employee.status not in INACTIVE_STATUSES:
        still_managing = await employee_repo.count_active_direct_reports(employee.id)
        if still_managing:
            raise BusinessRuleError(
                f"{employee.full_name} still manages {still_managing} "
                f"{'person' if still_managing == 1 else 'people'}. Move them to another manager first, "
                "or nobody could approve their leave or give them tasks.",
                error_code="EMPLOYEE_HAS_REPORTS",
            )

    employee.status = payload.status

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(employee.user_id)
    if user is not None:
        user.is_active = payload.status not in INACTIVE_STATUSES

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.DEACTIVATE_EMPLOYEE if payload.status in INACTIVE_STATUSES else AuditAction.UPDATE_EMPLOYEE,
        entity_type="Employee",
        entity_id=employee.id,
        description=f"Changed status of {employee.employee_code} to {payload.status.value}",
        request=request,
    )
    await session.commit()
    await _invalidate_employee_caches(employee.id)

    return EmployeeOut.from_model(employee)
