from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.document_type import DocumentType
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.document_type_repository import DocumentTypeRepository
from app.schemas.document_type import DocumentTypeCreate, DocumentTypeOut, DocumentTypeUpdate
from app.services.audit_service import log_action


async def list_document_types(session: AsyncSession) -> list[DocumentTypeOut]:
    """Active types only - what the upload form offers."""
    return [DocumentTypeOut.model_validate(t) for t in await DocumentTypeRepository(session).list_active()]


async def _with_counts(repo: DocumentTypeRepository, types: list[DocumentTypeOut]) -> list[DocumentTypeOut]:
    counts = await repo.counts()
    for document_type in types:
        document_type.document_count = counts.get(document_type.id, 0)
    return types


async def list_all_document_types(session: AsyncSession) -> list[DocumentTypeOut]:
    """Every type including inactive - the management screen, with how many documents use each."""
    repo = DocumentTypeRepository(session)
    return await _with_counts(repo, [DocumentTypeOut.model_validate(t) for t in await repo.list_all()])


async def create_document_type(
    session: AsyncSession, payload: DocumentTypeCreate, current_user: User, request: Request | None = None
) -> DocumentTypeOut:
    repo = DocumentTypeRepository(session)
    if await repo.get_by_code(payload.code) is not None:
        raise ConflictError(
            f"A document type with code '{payload.code}' already exists.", error_code="DOCUMENT_TYPE_EXISTS"
        )

    document_type = DocumentType(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        requires_expiry=payload.requires_expiry,
        is_active=True,
    )
    repo.add(document_type)
    await session.flush()

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.CREATE_DOCUMENT_TYPE,
        entity_type="DocumentType",
        entity_id=document_type.id,
        description=f"Created document type '{document_type.name}' ({document_type.code})",
        request=request,
    )
    await session.commit()
    return DocumentTypeOut.model_validate(document_type)


async def update_document_type(
    session: AsyncSession,
    document_type_id: int,
    payload: DocumentTypeUpdate,
    current_user: User,
    request: Request | None = None,
) -> DocumentTypeOut:
    repo = DocumentTypeRepository(session)
    document_type = await repo.get_by_id(document_type_id)
    if document_type is None:
        raise NotFoundError("Document type not found.", error_code="DOCUMENT_TYPE_NOT_FOUND")

    if payload.name is not None:
        document_type.name = payload.name
    if "description" in payload.model_fields_set:
        document_type.description = payload.description or None
    if payload.requires_expiry is not None:
        document_type.requires_expiry = payload.requires_expiry
    if payload.is_active is not None:
        document_type.is_active = payload.is_active

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DOCUMENT_TYPE,
        entity_type="DocumentType",
        entity_id=document_type.id,
        description=f"Updated document type '{document_type.name}' ({document_type.code})",
        request=request,
    )
    await session.commit()
    return (await _with_counts(repo, [DocumentTypeOut.model_validate(document_type)]))[0]


async def delete_document_type(
    session: AsyncSession, document_type_id: int, current_user: User, request: Request | None = None
) -> None:
    repo = DocumentTypeRepository(session)
    document_type = await repo.get_by_id(document_type_id)
    if document_type is None:
        raise NotFoundError("Document type not found.", error_code="DOCUMENT_TYPE_NOT_FOUND")

    used = await repo.usage_count(document_type_id)
    if used > 0:
        raise BusinessRuleError(
            f"{used} uploaded document(s) use this type, so it can't be deleted. "
            "Deactivate it instead to hide it from the upload form.",
            error_code="DOCUMENT_TYPE_IN_USE",
        )

    name, code = document_type.name, document_type.code
    await repo.delete(document_type)

    await log_action(
        session,
        user_id=current_user.id,
        action=AuditAction.DELETE_DOCUMENT_TYPE,
        entity_type="DocumentType",
        entity_id=document_type_id,
        description=f"Deleted document type '{name}' ({code})",
        request=request,
    )
    await session.commit()
