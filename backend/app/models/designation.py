from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import DepartmentStatus


class Designation(Base, TimestampMixin):
    __tablename__ = "designations"
    __table_args__ = (UniqueConstraint("name", "department_id", name="uq_designation_name_department"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[DepartmentStatus] = mapped_column(
        Enum(DepartmentStatus, name="department_status", native_enum=True, create_type=False),
        default=DepartmentStatus.ACTIVE,
        nullable=False,
    )

    department: Mapped["Department"] = relationship(back_populates="designations", lazy="selectin")
