from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    requires_expiry: bool
    is_active: bool
    # Live number, filled in on the management list: uploaded documents of this type.
    document_count: int = 0


class DocumentTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    requires_expiry: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, code: str) -> str:
        return code.upper()

    @field_validator("name")
    @classmethod
    def strip_name(cls, name: str) -> str:
        return name.strip()


# The code is deliberately not editable: it appears in stored file names.
class DocumentTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    requires_expiry: bool | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, name: str | None) -> str | None:
        return name.strip() if name else name
