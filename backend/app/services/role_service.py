from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.models.enums import AuditAction, RoleName
from app.models.rbac import Permission, Role, RolePermission
from app.models.user import User
from app.schemas.role import PermissionOut, PermissionsMatrixOut, RolePermissionsOut
from app.services.audit_service import log_action
from app.utils.permissions import PERMISSIONS


async def get_permissions_matrix(session: AsyncSession) -> PermissionsMatrixOut:
    """Which permission each role actually has - read live from the role_permissions table, not the
    Python ROLE_PERMISSIONS dict in app/utils/permissions.py. That dict only seeds a brand-new database;
    an already-running database only gets a permission change through its own migration (see e.g.
    a5e3602b0ff8, b5f545e1a157), so the two can drift. Reading the database is what actually reflects
    what a given login can do right now."""
    roles = (await session.execute(select(Role))).scalars().all()
    by_role = {role.name: sorted(p.code for p in role.permissions) for role in roles}
    # RoleName gives a stable, meaningful column order (Admin/Founder first, Employee last) instead of
    # whatever order the database happens to return.
    ordered_role_names = [r.value for r in RoleName if r.value in by_role]

    return PermissionsMatrixOut(
        permissions=[PermissionOut(code=code, description=description) for code, description in PERMISSIONS],
        roles=[RolePermissionsOut(role=name, permission_codes=by_role[name]) for name in ordered_role_names],
    )


async def set_role_permission(
    session: AsyncSession,
    current_user: User,
    role_name: str,
    permission_code: str,
    granted: bool,
    request: Request | None = None,
) -> PermissionsMatrixOut:
    """Grant or revoke one permission for one role, live - the only way (besides a migration) that a
    role's actual power changes. Two guardrails keep this from being able to do real damage:

    1. You can only GRANT a permission you hold yourself - the same "can't give away power you don't
       have" rule as employee_service._may_manage_login_of, just applied to permissions directly instead
       of logins. Without this, an Admin (deliberately given no payroll access) could use this screen to
       hand Founder or anyone else a permission Admin itself was never trusted with.
    2. You can never REVOKE role:manage from its last holder. role:manage is what gates this screen -
       as long as some role keeps it, any other mistake made here (including on role:manage itself, for
       a role that isn't the last holder) can always be undone from this same screen. Losing the very
       last holder would need direct database access to fix, so it's the one case worth hard-blocking.
    """
    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("That role does not exist.", error_code="ROLE_NOT_FOUND")
    permission = (await session.execute(select(Permission).where(Permission.code == permission_code))).scalar_one_or_none()
    if permission is None:
        raise NotFoundError("That permission does not exist.", error_code="PERMISSION_NOT_FOUND")

    existing = (
        await session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)
        )
    ).scalar_one_or_none()

    if granted:
        if existing is not None:
            raise BusinessRuleError(f"{role_name} already has this permission.", error_code="PERMISSION_ALREADY_GRANTED")
        mine = {p.code for p in current_user.role.permissions}
        if permission_code not in mine:
            raise ForbiddenError(
                "You can't grant a permission you don't have yourself.", error_code="PERMISSION_NOT_YOURS_TO_GRANT"
            )
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await log_action(
            session, user_id=current_user.id, action=AuditAction.GRANT_ROLE_PERMISSION, entity_type="Role",
            description=f"Granted {role_name} the {permission_code} permission", request=request,
        )
    else:
        if existing is None:
            raise BusinessRuleError(f"{role_name} doesn't have this permission.", error_code="PERMISSION_NOT_GRANTED")
        if permission_code == "role:manage":
            holders = (
                await session.execute(
                    select(func.count()).select_from(RolePermission).where(RolePermission.permission_id == permission.id)
                )
            ).scalar_one()
            if holders <= 1:
                raise BusinessRuleError(
                    "This is the only role that can manage roles and permissions, so it can't be removed - "
                    "nobody would be able to undo it.",
                    error_code="LAST_ROLE_MANAGER",
                )
        await session.delete(existing)
        await log_action(
            session, user_id=current_user.id, action=AuditAction.REVOKE_ROLE_PERMISSION, entity_type="Role",
            description=f"Revoked the {permission_code} permission from {role_name}", request=request,
        )

    await session.commit()
    # expire_on_commit is off (see database/session.py), so the Role objects just touched would otherwise
    # keep serving their pre-commit .permissions collection - expire the identity map so the matrix below
    # is read fresh, not stale.
    session.expire_all()
    return await get_permissions_matrix(session)
