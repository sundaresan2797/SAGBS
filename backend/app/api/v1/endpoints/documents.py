from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.document import DocumentOut, DocumentUploadPolicyOut, ExpiringDocumentsOut
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "/policy",
    response_model=SuccessResponse[DocumentUploadPolicyOut],
    summary="The real upload rules (max size, allowed file types)",
)
async def upload_policy(current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=document_service.get_upload_policy())


@router.post("", response_model=SuccessResponse[DocumentOut], status_code=201, summary="Upload a document")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    document_type_id: int = Form(...),
    expiry_date: date | None = Form(default=None),
    employee_id: int | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await document_service.upload_document(
        session, current_user, file, document_type_id, expiry_date, employee_id, request
    )
    return SuccessResponse(message="Document uploaded successfully", data=result)


@router.get("", response_model=SuccessResponse[list[DocumentOut]], summary="List documents")
async def list_documents(
    employee_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await document_service.list_documents(session, current_user, employee_id)
    return SuccessResponse(data=result)


@router.get(
    "/expiring",
    response_model=SuccessResponse[ExpiringDocumentsOut],
    summary="Documents that have expired or are about to, across the company",
    dependencies=[Depends(require_permission("document:manage_all"))],
)
async def expiring_documents(
    within_days: int = Query(default=30, ge=0, le=365),
    session: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await document_service.list_expiring_documents(session, within_days))


@router.get("/{document_id}/download", summary="Securely download a document")
async def download_document(
    document_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    document, path = await document_service.get_document_for_download(session, current_user, document_id)
    return FileResponse(path=path, filename=document.file_name, media_type=document.mime_type)


@router.delete("/{document_id}", response_model=SuccessResponse[None], summary="Delete a document")
async def delete_document(
    document_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await document_service.delete_document(session, current_user, document_id, request)
    return SuccessResponse(message="Document deleted successfully")
