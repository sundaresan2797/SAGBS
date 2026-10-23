from datetime import date, datetime

from pydantic import BaseModel


class DocumentUploadPolicyOut(BaseModel):
    max_upload_mb: int
    allowed_extensions: list[str]


class DocumentOut(BaseModel):
    id: int
    employee_id: int
    document_type_id: int
    document_type: str  # the type's code, e.g. RESUME
    document_type_name: str  # what people read, e.g. Resume
    file_name: str
    file_size: int
    mime_type: str
    expiry_date: date | None
    uploaded_by: int | None
    created_at: datetime

    @classmethod
    def from_model(cls, document) -> "DocumentOut":
        return cls(
            id=document.id,
            employee_id=document.employee_id,
            document_type_id=document.document_type_id,
            document_type=document.document_type.code,
            document_type_name=document.document_type.name,
            file_name=document.file_name,
            file_size=document.file_size,
            mime_type=document.mime_type,
            expiry_date=document.expiry_date,
            uploaded_by=document.uploaded_by,
            created_at=document.created_at,
        )


class ExpiringDocumentOut(BaseModel):
    document_id: int
    employee_id: int
    employee_name: str
    employee_code: str
    document_type_name: str
    file_name: str
    expiry_date: date
    days_left: int  # negative once it has expired

    @classmethod
    def from_model(cls, document, today: date) -> "ExpiringDocumentOut":
        return cls(
            document_id=document.id,
            employee_id=document.employee_id,
            employee_name=document.employee.full_name,
            employee_code=document.employee.employee_code,
            document_type_name=document.document_type.name,
            file_name=document.file_name,
            expiry_date=document.expiry_date,
            days_left=(document.expiry_date - today).days,
        )


class ExpiringDocumentsOut(BaseModel):
    items: list[ExpiringDocumentOut]
    total: int
