from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.document_type import DocumentTypeCreate, DocumentTypeOut, DocumentTypeUpdate
from app.services import document_type_service

router = APIRouter(prefix="/document-types", tags=["Document types"])

MANAGE = Depends(require_permission("document_type:manage"))


@router.get("", response_model=SuccessResponse[list[DocumentTypeOut]], summary="List active document types")
async def list_document_types(session: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=await document_type_service.list_document_types(session))


@router.get(
    "/all",
    response_model=SuccessResponse[list[DocumentTypeOut]],
    summary="List all document types, including inactive (management view)",
    dependencies=[MANAGE],
)
async def list_all_document_types(session: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=await document_type_service.list_all_document_types(session))


@router.post(
    "",
    response_model=SuccessResponse[DocumentTypeOut],
    status_code=201,
    summary="Create a document type",
    dependencies=[MANAGE],
)
async def create_document_type(
    payload: DocumentTypeCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await document_type_service.create_document_type(session, payload, current_user, request)
    return SuccessResponse(message="Document type created successfully", data=result)


@router.patch(
    "/{document_type_id}",
    response_model=SuccessResponse[DocumentTypeOut],
    summary="Update a document type",
    dependencies=[MANAGE],
)
async def update_document_type(
    document_type_id: int,
    payload: DocumentTypeUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await document_type_service.update_document_type(session, document_type_id, payload, current_user, request)
    return SuccessResponse(message="Document type updated successfully", data=result)


@router.delete(
    "/{document_type_id}",
    response_model=SuccessResponse[None],
    summary="Delete a document type",
    dependencies=[MANAGE],
)
async def delete_document_type(
    document_type_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await document_type_service.delete_document_type(session, document_type_id, current_user, request)
    return SuccessResponse(message="Document type deleted successfully")
