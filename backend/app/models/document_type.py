from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class DocumentType(Base, TimestampMixin):
    """A kind of document employees can upload (Resume, ID Proof, ...).

    Managed by Admin/HR like Leave Types, so a new kind is a row, not a code
    change. The code is fixed once created: it is what appears in stored file
    names (RESUME_20260920_9f3a.pdf).
    """

    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
