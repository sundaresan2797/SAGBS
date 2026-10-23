from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import EmployeeStatus, EmploymentType


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)

    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    designation_id: Mapped[int] = mapped_column(ForeignKey("designations.id", ondelete="RESTRICT"), nullable=False)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)

    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type", native_enum=True), nullable=False
    )
    work_location: Mapped[str | None] = mapped_column(String(150))
    profile_photo: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(EmployeeStatus, name="employee_status", native_enum=True),
        default=EmployeeStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="employee", lazy="selectin")
    department: Mapped["Department"] = relationship(lazy="selectin")
    designation: Mapped["Designation"] = relationship(lazy="selectin")
    manager: Mapped["Employee | None"] = relationship(
        remote_side=[id], back_populates="direct_reports", lazy="selectin"
    )
    direct_reports: Mapped[list["Employee"]] = relationship(back_populates="manager")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
