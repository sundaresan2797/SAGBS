from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import DepartmentStatus


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[DepartmentStatus] = mapped_column(
        Enum(DepartmentStatus, name="department_status", native_enum=True),
        default=DepartmentStatus.ACTIVE,
        nullable=False,
    )

    designations: Mapped[list["Designation"]] = relationship(back_populates="department")
