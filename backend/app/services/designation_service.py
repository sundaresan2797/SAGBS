from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.redis import CacheKeys, CacheTTL, redis_service
from app.models.designation import Designation
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.repositories.designation_repository import DesignationRepository
from app.schemas.designation import DesignationCreate, DesignationOut, DesignationUpdate
from app.services.audit_service import log_action
from app.services.department_service import invalidate_department_caches


async def _with_counts(session: AsyncSession, designations: list[DesignationOut]) -> list[DesignationOut]:
    """The lists are cached, but who holds a title changes with every hire, so the counts are read fresh."""
    counts = await DesignationRepository(session).counts()
    for designation in designations:
        designation.employee_count = counts.get(designation.id, 0)
    return designations


async def list_designations(session: AsyncSession, department_id: int | None = None) -> list[DesignationOut]:
    cache_key = CacheKeys.DESIGNATIONS_LIST if department_id is None else f"{CacheKeys.DESIGNATIONS_LIST}:{department_id}"
    cached = await redis_service.get(cache_key)
    if cached is not None:
        return await _with_counts(session, [DesignationOut.model_validate(item) for item in cached])

    repo = DesignationRepository(session)
    designations = await repo.list_all(department_id)
    result = [DesignationOut.from_model(d) for d in designations]

    await redis_service.set(cache_key, [d.model_dump(mode="json") for d in result], CacheTTL.DEPARTMENT_DESIGNATION)
    return await _with_counts(session, result)


async def create_designation(
    session: AsyncSession, payload: DesignationCreate, current_user: User, request: Request | None = None
) -> DesignationOut:
    dept_repo = DepartmentRepository(session)
    department = await dept_repo.get_by_id(payload.department_id)
    if department is None:
        raise NotFoundError("Department not found.", error_code="DEPARTMENT_NOT_FOUND")

    desig_repo = DesignationRepository(session)
    if await desig_repo.get_by_name_and_department(payload.name, payload.department_id) is not None:
        raise ConflictError(
            f"Designation '{payload.name}' already exists in this department.", error_code="DESIGNATION_EXISTS"
        )

    designation = Designation(
        name=payload.name, description=payload.description, department_id=payload.department_id
    )
    desig_repo.add(designation)
    await session.flush()
    designation.department = department

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_DESIGNATION,
        entity_type="Designation",
        entity_id=designation.id,
        description=f"Created designation '{designation.name}'",
        request=request,
    )
    await session.commit()
    await invalidate_department_caches()

    return DesignationOut.from_model(designation)


async def update_designation(
    session: AsyncSession,
    designation_id: int,
    payload: DesignationUpdate,
    current_user: User,
    request: Request | None = None,
) -> DesignationOut:
    desig_repo = DesignationRepository(session)
    designation = await desig_repo.get_by_id(designation_id)
    if designation is None:
        raise NotFoundError("Designation not found.", error_code="DESIGNATION_NOT_FOUND")

    target_department_id = payload.department_id or designation.department_id
    if payload.department_id is not None:
        dept_repo = DepartmentRepository(session)
        if await dept_repo.get_by_id(payload.department_id) is None:
            raise NotFoundError("Department not found.", error_code="DEPARTMENT_NOT_FOUND")

    # Moving a title to another department while people hold it would leave each of them in one department
    # with a title that belongs to another - the same mismatch the employee form refuses.
    if payload.department_id is not None and payload.department_id != designation.department_id:
        holders = await desig_repo.count_holders(designation.id)
        if holders:
            raise BusinessRuleError(
                f"{holders} {'person holds' if holders == 1 else 'people hold'} '{designation.name}'. "
                "Move them to another job title first, then change its department.",
                error_code="DESIGNATION_IN_USE",
            )

    new_name = payload.name or designation.name
    if (payload.name or payload.department_id) and (
        new_name.lower() != designation.name.lower() or target_department_id != designation.department_id
    ):
        existing = await desig_repo.get_by_name_and_department(new_name, target_department_id)
        if existing is not None and existing.id != designation.id:
            raise ConflictError(
                f"Designation '{new_name}' already exists in this department.", error_code="DESIGNATION_EXISTS"
            )

    if payload.name is not None:
        designation.name = payload.name
    if payload.department_id is not None:
        designation.department_id = payload.department_id
    if payload.description is not None:
        designation.description = payload.description
    if payload.status is not None:
        designation.status = payload.status

    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DESIGNATION,
        entity_type="Designation",
        entity_id=designation.id,
        description=f"Updated designation '{designation.name}'",
        request=request,
    )
    await session.commit()
    await invalidate_department_caches()

    return (await _with_counts(session, [DesignationOut.from_model(designation)]))[0]
