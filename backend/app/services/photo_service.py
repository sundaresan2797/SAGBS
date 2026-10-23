"""Employee photos.

Anyone may set or remove their OWN photo; HR, the Founder and the Admin may set or remove anyone's. Every
photo is checked, cropped to a square and shrunk before it is saved (see StorageService.process_photo), and the
picture is only ever handed to logged-in staff - it is never a public link. The stored path lives in
Employee.profile_photo; its random file name doubles as a "version" so screens know when a photo changed.
"""

import logging
from pathlib import Path

from fastapi import Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.employee import Employee
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository, list_photo_paths
from app.schemas.employee import PhotoIndexEntry, PhotoOut
from app.services.attendance_service import acting_name
from app.services.audit_service import log_action
from app.services.employee_service import _invalidate_employee_caches
from app.services.notification_service import add_notification
from app.services.storage_service import PHOTO_MIME_TYPE, storage_service

logger = logging.getLogger("ems.photos")

# HR, the Founder and the Admin hold one of these; a plain employee or manager holds neither.
MANAGE_ANY_PHOTO = {"employee:update", "document:manage_all"}


def photo_version(stored_path: str | None) -> str | None:
    """"EMP-0003/photo_ab12cd34.jpg" -> "ab12cd34"."""
    return Path(stored_path).stem.split("_")[-1] if stored_path else None


async def _employee_or_raise(session: AsyncSession, employee_id: int) -> Employee:
    employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    return employee


def _ensure_can_change(current_user: User, employee: Employee) -> bool:
    """Raises unless the caller may change this photo. Returns True when it is their own."""
    if employee.user_id is not None and employee.user_id == current_user.id:
        return True
    if MANAGE_ANY_PHOTO & {permission.code for permission in current_user.role.permissions}:
        return False
    raise ForbiddenError(
        "You can change your own photo. Only HR, the Founder or the Admin can change someone else's.",
        error_code="PHOTO_FORBIDDEN",
    )


def _discard(stored_path: str | None) -> None:
    """Delete a stored photo file; a leftover file is harmless, so a failure is only logged."""
    if not stored_path:
        return
    try:
        storage_service.delete(stored_path)
    except OSError:
        logger.warning("Could not delete photo file %s", stored_path)


async def set_photo(
    session: AsyncSession, current_user: User, employee_id: int, file: UploadFile, request: Request | None = None
) -> PhotoOut:
    employee = await _employee_or_raise(session, employee_id)
    is_own = _ensure_can_change(current_user, employee)

    new_path = await storage_service.save_photo(employee.employee_code, file)
    old_path = employee.profile_photo
    try:
        employee.profile_photo = new_path
        if not is_own and employee.user_id is not None:
            add_notification(
                session, employee.user_id, "Your photo was changed",
                f"{await acting_name(session, current_user)} changed your profile photo. "
                "You can change it again from My Profile.", "PROFILE_UPDATED",
            )
        await log_action(
            session,
            user_id=current_user.id,
            action=AuditAction.UPDATE_EMPLOYEE_PHOTO,
            entity_type="Employee",
            entity_id=employee.id,
            description=f"{'Changed own' if is_own else 'Changed'} photo of {employee.employee_code}",
            request=request,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        _discard(new_path)  # nothing points at the new file, so do not leave it behind
        raise
    _discard(old_path)
    await _invalidate_employee_caches(employee.id)
    return PhotoOut(employee_id=employee.id, photo_version=photo_version(new_path))


async def remove_photo(
    session: AsyncSession, current_user: User, employee_id: int, request: Request | None = None
) -> PhotoOut:
    employee = await _employee_or_raise(session, employee_id)
    is_own = _ensure_can_change(current_user, employee)
    old_path = employee.profile_photo
    if old_path is None:
        raise NotFoundError("This person has no photo.", error_code="NO_PHOTO")

    employee.profile_photo = None
    if not is_own and employee.user_id is not None:
        add_notification(
            session, employee.user_id, "Your photo was removed",
            f"{await acting_name(session, current_user)} removed your profile photo. "
            "You can add a new one from My Profile.", "PROFILE_UPDATED",
        )
    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.REMOVE_EMPLOYEE_PHOTO,
        entity_type="Employee",
        entity_id=employee.id,
        description=f"{'Removed own' if is_own else 'Removed'} photo of {employee.employee_code}",
        request=request,
    )
    await session.commit()
    _discard(old_path)
    await _invalidate_employee_caches(employee.id)
    return PhotoOut(employee_id=employee.id, photo_version=None)


async def read_photo(session: AsyncSession, employee_id: int) -> tuple[bytes, str]:
    """The picture's bytes and type, for any logged-in user (the endpoint only checks that you are signed in)."""
    employee = await _employee_or_raise(session, employee_id)
    if employee.profile_photo is None:
        raise NotFoundError("This person has no photo.", error_code="NO_PHOTO")
    path = storage_service.resolve_path(employee.profile_photo)
    if not path.is_file():
        raise NotFoundError("This person has no photo.", error_code="NO_PHOTO")
    return path.read_bytes(), PHOTO_MIME_TYPE


async def photo_index(session: AsyncSession) -> list[PhotoIndexEntry]:
    """Who has a photo and which version, so screens fetch only real photos and refresh changed ones."""
    return [
        PhotoIndexEntry(employee_id=employee_id, photo_version=photo_version(path) or "")
        for employee_id, path in await list_photo_paths(session)
    ]
