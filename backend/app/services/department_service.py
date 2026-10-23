from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.redis import CacheKeys, CacheTTL, redis_service
from app.models.department import Department
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services.audit_service import log_action


async def invalidate_department_caches() -> None:
    """Department and job-title changes show up in the department list, the job-title lists, the employee
    list (each row carries its department name) and the dashboard - clear them all together."""
    await redis_service.delete(
        CacheKeys.DEPARTMENTS_LIST,
        CacheKeys.DESIGNATIONS_LIST,
        CacheKeys.DASHBOARD_SUMMARY,
        CacheKeys.DASHBOARD_DEPARTMENTS,
    )
    await redis_service.delete_pattern(f"{CacheKeys.DESIGNATIONS_LIST}:*")
    await redis_service.delete_pattern(f"{CacheKeys.EMPLOYEES_LIST_PREFIX}*")


async def _with_counts(session: AsyncSession, departments: list[DepartmentOut]) -> list[DepartmentOut]:
    """The department list itself is cached, but headcounts change with every hire, so they are read fresh."""
    counts = await DepartmentRepository(session).counts()
    for department in departments:
        department.employee_count, department.designation_count = counts.get(department.id, (0, 0))
    return departments


async def list_departments(session: AsyncSession) -> list[DepartmentOut]:
    cached = await redis_service.get(CacheKeys.DEPARTMENTS_LIST)
    if cached is not None:
        return await _with_counts(session, [DepartmentOut.model_validate(item) for item in cached])

    repo = DepartmentRepository(session)
    departments = await repo.list_all()
    result = [DepartmentOut.model_validate(d) for d in departments]

    await redis_service.set(
        CacheKeys.DEPARTMENTS_LIST, [d.model_dump(mode="json") for d in result], CacheTTL.DEPARTMENT_DESIGNATION
    )
    return await _with_counts(session, result)


async def create_department(
    session: AsyncSession, payload: DepartmentCreate, current_user: User, request: Request | None = None
) -> DepartmentOut:
    repo = DepartmentRepository(session)
    if await repo.get_by_name(payload.name) is not None:
        raise ConflictError(f"A department named '{payload.name}' already exists.", error_code="DEPARTMENT_EXISTS")

    department = Department(name=payload.name, description=payload.description)
    repo.add(department)
    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_DEPARTMENT,
        entity_type="Department",
        entity_id=department.id,
        description=f"Created department '{department.name}'",
        request=request,
    )
    await session.commit()
    await invalidate_department_caches()

    return (await _with_counts(session, [DepartmentOut.model_validate(department)]))[0]


async def update_department(
    session: AsyncSession,
    department_id: int,
    payload: DepartmentUpdate,
    current_user: User,
    request: Request | None = None,
) -> DepartmentOut:
    repo = DepartmentRepository(session)
    department = await repo.get_by_id(department_id)
    if department is None:
        raise NotFoundError("Department not found.", error_code="DEPARTMENT_NOT_FOUND")

    if payload.name and payload.name.lower() != department.name.lower():
        existing = await repo.get_by_name(payload.name)
        if existing is not None and existing.id != department.id:
            raise ConflictError(
                f"A department named '{payload.name}' already exists.", error_code="DEPARTMENT_EXISTS"
            )
        department.name = payload.name

    if payload.description is not None:
        department.description = payload.description
    if payload.status is not None:
        department.status = payload.status

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DEPARTMENT,
        entity_type="Department",
        entity_id=department.id,
        description=f"Updated department '{department.name}'",
        request=request,
    )
    await session.commit()
    await invalidate_department_caches()

    return DepartmentOut.model_validate(department)
