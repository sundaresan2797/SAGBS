from datetime import date, timedelta
from pathlib import Path

from fastapi import Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.document import EmployeeDocument
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_type_repository import DocumentTypeRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.document import DocumentOut, DocumentUploadPolicyOut, ExpiringDocumentOut, ExpiringDocumentsOut
from app.services.audit_service import log_action
from app.services.storage_service import ALLOWED_EXTENSIONS, storage_service
from app.utils.timezone import today_in_org_tz


def get_upload_policy() -> DocumentUploadPolicyOut:
    """The real upload rules the server enforces (storage_service._validate), so the "Add a
    document" screen never states a size limit or file type that could drift from what upload_document
    actually accepts."""
    return DocumentUploadPolicyOut(
        max_upload_mb=storage_service.max_upload_mb,
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
    )


def _can_manage_all_documents(current_user: User) -> bool:
    return any(p.code == "document:manage_all" for p in current_user.role.permissions)


async def _resolve_target_employee(session: AsyncSession, current_user: User, employee_id: int | None):
    employee_repo = EmployeeRepository(session)
    own_employee = await employee_repo.get_by_user_id(current_user.id)

    if employee_id is None:
        if own_employee is None:
            raise NotFoundError("No employee profile is linked to this account.", error_code="EMPLOYEE_NOT_FOUND")
        return own_employee

    if own_employee is not None and own_employee.id == employee_id:
        return own_employee

    if not _can_manage_all_documents(current_user):
        raise ForbiddenError("You cannot access another employee's documents.", error_code="DOCUMENT_FORBIDDEN")

    target = await employee_repo.get_by_id(employee_id)
    if target is None:
        raise NotFoundError("Employee not found.", error_code="EMPLOYEE_NOT_FOUND")
    return target


async def upload_document(
    session: AsyncSession,
    current_user: User,
    file: UploadFile,
    document_type_id: int,
    expiry_date: date | None,
    employee_id: int | None,
    request: Request | None = None,
) -> DocumentOut:
    target_employee = await _resolve_target_employee(session, current_user, employee_id)

    # Check the type (and its rules) BEFORE writing the file, so a rejected
    # upload never leaves an orphan file on disk.
    document_type = await DocumentTypeRepository(session).get_by_id(document_type_id)
    if document_type is None:
        raise NotFoundError("Document type not found.", error_code="DOCUMENT_TYPE_NOT_FOUND")
    if not document_type.is_active:
        raise BusinessRuleError(
            "This document type is no longer available. Please choose another one.",
            error_code="DOCUMENT_TYPE_INACTIVE",
        )
    if document_type.requires_expiry and expiry_date is None:
        raise ValidationAppError(
            f"{document_type.name} needs an expiry date. Please enter it and try again.",
            error_code="EXPIRY_DATE_REQUIRED",
        )

    relative_path, size, mime_type = await storage_service.save(
        target_employee.employee_code, document_type.code, file
    )

    document = EmployeeDocument(
        employee_id=target_employee.id,
        document_type=document_type,
        file_name=file.filename or "document",
        file_path=relative_path,
        file_size=size,
        mime_type=mime_type,
        expiry_date=expiry_date,
        uploaded_by=current_user.id,
    )
    repo = DocumentRepository(session)
    repo.add(document)
    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPLOAD_DOCUMENT,
        entity_type="EmployeeDocument",
        entity_id=document.id,
        description=f"Uploaded {document_type.name} for {target_employee.employee_code}",
        request=request,
    )
    await session.commit()
    return DocumentOut.from_model(document)


async def list_documents(session: AsyncSession, current_user: User, employee_id: int | None) -> list[DocumentOut]:
    target_employee = await _resolve_target_employee(session, current_user, employee_id)
    repo = DocumentRepository(session)
    documents = await repo.list_for_employee(target_employee.id)
    return [DocumentOut.from_model(d) for d in documents]


EXPIRING_LIST_LIMIT = 50


async def list_expiring_documents(session: AsyncSession, within_days: int) -> ExpiringDocumentsOut:
    """Company-wide: every current employee's document that has expired or expires within `within_days`."""
    today = today_in_org_tz()
    documents, total = await DocumentRepository(session).list_expiring(today + timedelta(days=within_days), EXPIRING_LIST_LIMIT)
    return ExpiringDocumentsOut(items=[ExpiringDocumentOut.from_model(d, today) for d in documents], total=total)


async def get_document_for_download(
    session: AsyncSession, current_user: User, document_id: int
) -> tuple[EmployeeDocument, Path]:
    repo = DocumentRepository(session)
    document = await repo.get_by_id(document_id)
    if document is None:
        raise NotFoundError("Document not found.", error_code="DOCUMENT_NOT_FOUND")

    await _resolve_target_employee(session, current_user, document.employee_id)

    path = storage_service.resolve_path(document.file_path)
    if not path.exists():
        raise NotFoundError("The file for this document could not be found.", error_code="DOCUMENT_FILE_MISSING")

    return document, path


async def delete_document(
    session: AsyncSession, current_user: User, document_id: int, request: Request | None = None
) -> None:
    repo = DocumentRepository(session)
    document = await repo.get_by_id(document_id)
    if document is None:
        raise NotFoundError("Document not found.", error_code="DOCUMENT_NOT_FOUND")

    await _resolve_target_employee(session, current_user, document.employee_id)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.DELETE_DOCUMENT,
        entity_type="EmployeeDocument",
        entity_id=document.id,
        description=f"Deleted document '{document.file_name}'",
        request=request,
    )
    storage_service.delete(document.file_path)
    await repo.delete(document)
    await session.commit()
