"""Bring the first real data in from one Excel file: employees (with their salary and manager) and the leave
they have already taken this year.

Three steps, so nothing is ever half-loaded:

1. `build_plan` reads the file and CHECKS it against the database. It changes nothing and reports every problem it
   finds, with the row number, in plain words.
2. `execute_plan` loads a clean plan **all-or-nothing** - either every department, job title, employee, salary and
   leave balance is saved, or none is. It uses the same services as the screens, so every rule (unique email, a
   job title belonging to its department, no manager loops, who may create which role) and every audit-log
   entry is exactly the same as if a person had typed it in.
3. `write_login_sheet` saves the temporary passwords to a private file, to hand over to each person.

The Excel layout is produced by `write_template`.
"""

from __future__ import annotations

import csv
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.enums import AuditAction, EmploymentType, RoleName
from app.models.leave import LeaveBalance, LeaveType
from app.models.user import User
from app.schemas.department import DepartmentCreate
from app.schemas.designation import DesignationCreate
from app.schemas.employee import EmployeeCreate
from app.schemas.payroll import SalaryRecordCreate
from app.services import department_service, designation_service, employee_service, payroll_service
from app.services.audit_service import log_action

MAX_ROWS = 2000

# The people-sheet columns: (header, is_required, help text). Headers are matched ignoring case, spaces and dashes.
EMPLOYEE_COLUMNS: list[tuple[str, bool, str]] = [
    ("email", True, "Their work email. It becomes their sign-in. Must be unique."),
    ("first_name", True, "First name"),
    ("last_name", True, "Last name (or a full stop . if they have none)"),
    ("date_of_joining", True, "The day they joined. Not in the future. Use DD/MM/YYYY or YYYY-MM-DD"),
    ("department", True, "Department name. Created automatically if it does not exist yet"),
    ("job_title", True, "Job title. Created inside that department if it does not exist yet"),
    ("reports_to_email", False, "The email of their direct manager. Leave EMPTY only for the top person (the Founder)"),
    ("role", False, "EMPLOYEE (default), MANAGER, HR, EXECUTIVE, ACCOUNTANT or FOUNDER. Give MANAGER to anyone who has a team"),
    ("employment_type", False, "FULL_TIME (default), PART_TIME, CONTRACT or INTERN"),
    ("phone", False, "Phone number"),
    ("date_of_birth", False, "Date of birth"),
    ("work_location", False, "For example: Head Office"),
    ("basic_pay", False, "Monthly basic pay in rupees. Leave empty to set the salary later"),
    ("allowances", False, "Monthly allowances in rupees (default 0)"),
    ("deductions", False, "Monthly deductions in rupees (default 0)"),
    ("salary_from", False, "The date this salary starts. Empty means their joining date"),
]
LEAVE_COLUMNS: list[tuple[str, bool, str]] = [
    ("email", True, "The employee's email, exactly as on the People sheet"),
    ("leave_type_code", True, "The leave type code, for example CASUAL, SICK or EARNED"),
    ("days_used", True, "Days of that leave already taken THIS year before the switch. Halves are allowed (1.5)"),
]
PEOPLE_SHEET = "People"
LEAVE_SHEET = "Leave already taken"
HELP_SHEET = "Read me first"

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


# --------------------------------------------------------------------------------------------- the plan


@dataclass
class Problem:
    sheet: str
    line: int | None  # the Excel row number, None for a problem with the file as a whole
    message: str

    def __str__(self) -> str:
        where = f"{self.sheet}, row {self.line}" if self.line else self.sheet
        return f"[{where}] {self.message}"


@dataclass
class PersonRow:
    line: int
    email: str
    first_name: str
    last_name: str
    date_of_joining: date
    department: str
    job_title: str
    reports_to_email: str | None
    role: RoleName
    employment_type: EmploymentType
    phone: str | None
    date_of_birth: date | None
    work_location: str | None
    basic_pay: float | None
    allowances: float
    deductions: float
    salary_from: date | None

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class LeaveRow:
    line: int
    email: str
    leave_type_code: str
    days_used: float


@dataclass
class ImportPlan:
    people: list[PersonRow] = field(default_factory=list)  # in the order to create them: managers before their teams
    leave_rows: list[LeaveRow] = field(default_factory=list)
    new_departments: list[str] = field(default_factory=list)
    new_job_titles: list[tuple[str, str]] = field(default_factory=list)  # (department, job title)
    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.people)

    def summary(self) -> list[str]:
        with_salary = sum(1 for p in self.people if p.basic_pay is not None)
        return [
            f"{len(self.people)} employees to add ({with_salary} with a salary)",
            f"{len(self.new_departments)} new departments: {', '.join(self.new_departments) or 'none'}",
            f"{len(self.new_job_titles)} new job titles",
            f"{len(self.leave_rows)} leave-already-taken rows",
        ]


@dataclass
class CreatedLogin:
    employee_code: str
    name: str
    email: str
    role: str
    temporary_password: str


@dataclass
class ImportResult:
    departments: int
    job_titles: int
    employees: int
    salaries: int
    leave_balances: int
    logins: list[CreatedLogin]


# --------------------------------------------------------------------------------------------- reading cells


def _norm(header: object) -> str:
    return re.sub(r"[\s\-]+", "_", str(header or "").strip().lower()).strip("_")


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: object) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' is not a date. Use DD/MM/YYYY or YYYY-MM-DD")


def _number(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"'{text}' is not a number") from None


def _rows(sheet, columns: list[tuple[str, bool, str]], problems: list[Problem]) -> list[tuple[int, dict[str, object]]]:
    """The non-empty data rows of a sheet as {column: value}, with their Excel row numbers."""
    iterator = sheet.iter_rows(values_only=True)
    header = next(iterator, None)
    if header is None:
        problems.append(Problem(sheet.title, None, "The sheet is empty."))
        return []
    positions = {_norm(name): i for i, name in enumerate(header) if name is not None}
    missing = [name for name, required, _ in columns if required and name not in positions]
    if missing:
        problems.append(Problem(sheet.title, 1, "These columns are missing from the first row: " + ", ".join(missing)))
        return []
    out: list[tuple[int, dict[str, object]]] = []
    for line, values in enumerate(iterator, start=2):
        row = {name: (values[positions[name]] if name in positions and positions[name] < len(values) else None) for name, _, _ in columns}
        if all(_text(v) is None for v in row.values()):
            continue  # a blank row
        out.append((line, row))
    return out


# --------------------------------------------------------------------------------------------- checking


async def build_plan(session: AsyncSession, path: Path) -> ImportPlan:
    """Read the workbook and check every row against the file and the database. Changes nothing."""
    plan = ImportPlan()
    try:
        workbook = load_workbook(path, data_only=True, read_only=True)
    except Exception as error:  # a damaged or wrong kind of file
        plan.errors.append(Problem("File", None, f"This is not a readable Excel (.xlsx) file: {error}"))
        return plan
    if PEOPLE_SHEET not in workbook.sheetnames:
        plan.errors.append(Problem("File", None, f"The workbook has no sheet named '{PEOPLE_SHEET}'."))
        return plan

    raw_people = _rows(workbook[PEOPLE_SHEET], EMPLOYEE_COLUMNS, plan.errors)
    raw_leave = _rows(workbook[LEAVE_SHEET], LEAVE_COLUMNS, plan.errors) if LEAVE_SHEET in workbook.sheetnames else []
    if len(raw_people) > MAX_ROWS:
        plan.errors.append(Problem(PEOPLE_SHEET, None, f"More than {MAX_ROWS} rows. Split the file."))
        return plan
    if not raw_people and not plan.errors:
        plan.errors.append(Problem(PEOPLE_SHEET, None, "There are no employees in the file."))
        return plan

    # What already exists in the database
    taken_emails = {e.lower() for e in (await session.execute(select(User.email))).scalars()}
    taken_emails |= {e.lower() for e in (await session.execute(select(Employee.email))).scalars()}
    db_people = {e.email.lower(): e for e in (await session.execute(select(Employee))).scalars()}
    departments = {d.name.lower(): d for d in (await session.execute(select(Department))).scalars()}
    existing_titles = {(d.name.lower(), t.name.lower()) for t, d in (await session.execute(select(Designation, Department).join(Department))).all()}
    leave_types = {lt.code.upper(): lt for lt in (await session.execute(select(LeaveType))).scalars()}
    today = date.today()

    seen_emails: dict[str, int] = {}
    people: list[PersonRow] = []
    for line, row in raw_people:
        before = len(plan.errors)

        def bad(message: str, _line: int = line) -> None:
            plan.errors.append(Problem(PEOPLE_SHEET, _line, message))

        email_text = _text(row["email"])
        email = None
        if email_text is None:
            bad("The email is missing.")
        elif email_text.lower().startswith("example-delete.this.row"):
            bad("This is the example row from the template. Delete it, or replace it with a real person.")
        else:
            try:
                email = validate_email(email_text, check_deliverability=False).normalized.lower()
            except EmailNotValidError:
                bad(f"'{email_text}' is not a valid email address.")
        if email:
            if email in seen_emails:
                bad(f"The email {email} is already used in row {seen_emails[email]} of this file.")
            elif email in taken_emails:
                bad(f"The email {email} already has a login in the system.")
            seen_emails.setdefault(email, line)

        first, last = _text(row["first_name"]), _text(row["last_name"])
        if not first:
            bad("The first name is missing.")
        if not last:
            bad("The last name is missing. Put a full stop (.) if they have none.")

        try:
            joined = _date(row["date_of_joining"])
        except ValueError as error:
            joined = None
            bad(f"Date of joining: {error}.")
        else:
            if joined is None:
                bad("The date of joining is missing.")
            elif joined > today:
                bad(f"The date of joining ({joined:%d/%m/%Y}) is in the future.")
        try:
            born = _date(row["date_of_birth"])
            if born is not None and born >= today:
                bad("The date of birth must be in the past.")
        except ValueError as error:
            born = None
            bad(f"Date of birth: {error}.")

        department, title = _text(row["department"]), _text(row["job_title"])
        if not department or len(department) < 2:
            bad("The department is missing (at least 2 letters).")
        if not title or len(title) < 2:
            bad("The job title is missing (at least 2 letters).")

        role_text = (_text(row["role"]) or "EMPLOYEE").upper().replace(" ", "_")
        try:
            role = RoleName(role_text)
            if role == RoleName.ADMIN:
                bad("The ADMIN login is created by the setup step. Add more Admins later, on the User Accounts screen.")
        except ValueError:
            role = RoleName.EMPLOYEE
            bad(f"The role '{role_text}' is not valid. Use EMPLOYEE, MANAGER, HR, EXECUTIVE, ACCOUNTANT or FOUNDER.")
        type_text = (_text(row["employment_type"]) or "FULL_TIME").upper().replace(" ", "_").replace("-", "_")
        try:
            employment = EmploymentType(type_text)
        except ValueError:
            employment = EmploymentType.FULL_TIME
            bad(f"The employment type '{type_text}' is not valid. Use FULL_TIME, PART_TIME, CONTRACT or INTERN.")

        reports_to = _text(row["reports_to_email"])
        reports_to = reports_to.lower() if reports_to else None

        basic = allowances = deductions = None
        salary_from = None
        try:
            basic = _number(row["basic_pay"])
            allowances = _number(row["allowances"]) or 0.0
            deductions = _number(row["deductions"]) or 0.0
            salary_from = _date(row["salary_from"])
        except ValueError as error:
            bad(f"Salary: {error}.")
        if basic is not None:
            if min(basic, allowances or 0, deductions or 0) < 0:
                bad("Salary amounts cannot be negative.")
            elif (deductions or 0) > basic + (allowances or 0):
                bad("The deductions are more than the basic pay plus allowances.")
        elif (allowances or deductions) and basic is None:
            bad("Allowances or deductions are given but the basic pay is empty.")

        if len(plan.errors) == before and email and first and last and joined and department and title:
            people.append(
                PersonRow(
                    line=line, email=email, first_name=first, last_name=last, date_of_joining=joined,
                    department=department, job_title=title, reports_to_email=reports_to, role=role,
                    employment_type=employment, phone=_text(row["phone"]), date_of_birth=born,
                    work_location=_text(row["work_location"]), basic_pay=basic, allowances=allowances or 0.0,
                    deductions=deductions or 0.0, salary_from=salary_from,
                )
            )

    # Reporting lines: the manager must exist, and there must be no loop.
    in_file = {p.email: p for p in people}
    for person in people:
        manager = person.reports_to_email
        if manager is None:
            continue
        if manager == person.email:
            plan.errors.append(Problem(PEOPLE_SHEET, person.line, "A person cannot report to themselves."))
        elif manager not in in_file and manager not in db_people:
            plan.errors.append(
                Problem(PEOPLE_SHEET, person.line, f"The manager {manager} is not in this file and not in the system.")
            )
    ordered: list[PersonRow] = []
    placed: set[str] = set()
    remaining = list(people)
    while remaining:
        progressed = False
        for person in list(remaining):
            manager = person.reports_to_email
            if manager is None or manager in placed or manager in db_people or manager not in in_file:
                ordered.append(person)
                placed.add(person.email)
                remaining.remove(person)
                progressed = True
        if not progressed:
            names = ", ".join(p.email for p in remaining)
            plan.errors.append(Problem(PEOPLE_SHEET, remaining[0].line, f"These people report to each other in a circle: {names}."))
            break

    # Warnings: things that are legal but usually a mistake
    founders = [p for p in people if p.role == RoleName.FOUNDER]
    if people and len(founders) != 1:
        plan.warnings.append(
            Problem(PEOPLE_SHEET, None, f"There are {len(founders)} people with the role FOUNDER. Normally there is exactly one, at the top.")
        )
    has_team = {p.reports_to_email for p in people if p.reports_to_email}
    for person in people:
        if person.reports_to_email is None and person.role != RoleName.FOUNDER:
            plan.warnings.append(
                Problem(PEOPLE_SHEET, person.line, f"{person.name} has no manager. Nobody could approve their leave (only the Founder's own leave is approved automatically).")
            )
        if person.email in has_team and person.role == RoleName.EMPLOYEE:
            plan.warnings.append(
                Problem(PEOPLE_SHEET, person.line, f"{person.name} has people reporting to them but the role is EMPLOYEE. Give MANAGER so they can approve leave and assign tasks.")
            )
        if person.basic_pay is None:
            plan.warnings.append(Problem(PEOPLE_SHEET, person.line, f"{person.name} has no salary. The Accountant must set it before payroll."))

    # New departments and job titles
    for person in people:
        if person.department.lower() not in departments and person.department not in plan.new_departments:
            if person.department.lower() not in {d.lower() for d in plan.new_departments}:
                plan.new_departments.append(person.department)
    for person in people:
        key = (person.department.lower(), person.job_title.lower())
        if key not in existing_titles and (person.department, person.job_title) not in plan.new_job_titles:
            if key not in {(d.lower(), t.lower()) for d, t in plan.new_job_titles}:
                plan.new_job_titles.append((person.department, person.job_title))

    # Leave already taken this year
    seen_leave: set[tuple[str, str]] = set()
    for line, row in raw_leave:
        def bad_leave(message: str, _line: int = line) -> None:
            plan.errors.append(Problem(LEAVE_SHEET, _line, message))

        email = (_text(row["email"]) or "").lower()
        code = (_text(row["leave_type_code"]) or "").upper()
        try:
            days = _number(row["days_used"])
        except ValueError as error:
            days = None
            bad_leave(f"Days: {error}.")
        if email not in in_file and email not in db_people:
            bad_leave(f"{email or 'The email'} is not on the People sheet.")
        leave_type = leave_types.get(code)
        if leave_type is None:
            bad_leave(f"The leave type '{code}' does not exist. Existing codes: {', '.join(sorted(leave_types)) or 'none'}.")
        if days is None:
            if _text(row["days_used"]) is None:
                bad_leave("Days used is missing.")
        elif days < 0 or (days * 2) % 1 != 0:
            bad_leave("Days used must be 0 or more, in whole or half days.")
        elif leave_type is not None and leave_type.is_paid and days > float(leave_type.default_annual_days):
            bad_leave(f"{days:g} days is more than the yearly {leave_type.name} quota ({float(leave_type.default_annual_days):g}).")
        if (email, code) in seen_leave:
            bad_leave(f"{email} / {code} is listed twice.")
        seen_leave.add((email, code))
        if leave_type is not None and not leave_type.is_paid:
            plan.warnings.append(Problem(LEAVE_SHEET, line, f"{leave_type.name} is unpaid leave, which has no balance, so this row is ignored."))
        elif email in in_file and days is not None and code in leave_types:
            plan.leave_rows.append(LeaveRow(line=line, email=email, leave_type_code=code, days_used=days))

    plan.people = ordered if not any(e.sheet == PEOPLE_SHEET for e in plan.errors) else people
    return plan


# --------------------------------------------------------------------------------------------- loading


async def execute_plan(session: AsyncSession, plan: ImportPlan, actor: User) -> ImportResult:
    """Load a plan that has no errors, ALL-OR-NOTHING: any failure rolls everything back."""
    if plan.errors or not plan.people:
        raise ValueError("A plan with errors, or with no people, must not be loaded.")

    real_commit = session.commit
    # The services commit after each action. Turn those into flushes so everything stays in ONE transaction:
    # any failure undoes the whole import, and one real commit is made at the very end.
    session.commit = session.flush  # type: ignore[method-assign]
    try:
        made_departments, made_titles, logins, salaries, balances = await _load_everything(session, plan, actor)
        await real_commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        del session.commit  # back to the normal commit

    return ImportResult(
        departments=made_departments, job_titles=made_titles, employees=len(logins), salaries=salaries,
        leave_balances=balances, logins=logins,
    )


async def _load_everything(session: AsyncSession, plan: ImportPlan, actor: User):
    """The work of the import, inside the caller's savepoint. Returns the counts and the created logins."""
    dept_ids: dict[str, int] = {d.name.lower(): d.id for d in (await session.execute(select(Department))).scalars()}
    title_ids: dict[tuple[str, str], int] = {
        (d.name.lower(), t.name.lower()): t.id
        for t, d in (await session.execute(select(Designation, Department).join(Department))).all()
    }
    made_departments = made_titles = 0
    for name in plan.new_departments:
        created = await department_service.create_department(session, DepartmentCreate(name=name), actor)
        dept_ids[name.lower()] = created.id
        made_departments += 1
    for department, title in plan.new_job_titles:
        created = await designation_service.create_designation(
            session, DesignationCreate(name=title, department_id=dept_ids[department.lower()]), actor
        )
        title_ids[(department.lower(), title.lower())] = created.id
        made_titles += 1

    ids_by_email: dict[str, int] = {e.email.lower(): e.id for e in (await session.execute(select(Employee))).scalars()}
    logins: list[CreatedLogin] = []
    salaries = 0
    for person in plan.people:
        created_employee = await employee_service.create_employee(
            session,
            EmployeeCreate(
                first_name=person.first_name, last_name=person.last_name, email=person.email, phone=person.phone,
                date_of_birth=person.date_of_birth, date_of_joining=person.date_of_joining,
                department_id=dept_ids[person.department.lower()],
                designation_id=title_ids[(person.department.lower(), person.job_title.lower())],
                manager_id=ids_by_email.get(person.reports_to_email) if person.reports_to_email else None,
                employment_type=person.employment_type, work_location=person.work_location, role=person.role,
            ),
            actor,
        )
        employee_id = created_employee.employee.id
        ids_by_email[person.email] = employee_id
        logins.append(
            CreatedLogin(
                employee_code=created_employee.employee.employee_code, name=person.name, email=person.email,
                role=person.role.value, temporary_password=created_employee.temporary_password,
            )
        )
        if person.basic_pay is not None:
            await payroll_service.set_salary_record(
                session,
                SalaryRecordCreate(
                    employee_id=employee_id, basic_pay=person.basic_pay, allowances=person.allowances,
                    deductions=person.deductions, effective_from=person.salary_from or person.date_of_joining,
                ),
                actor,
            )
            salaries += 1

    leave_types = {lt.code.upper(): lt for lt in (await session.execute(select(LeaveType))).scalars()}
    year = date.today().year
    balances = 0
    for leave in plan.leave_rows:
        leave_type = leave_types[leave.leave_type_code]
        session.add(
            LeaveBalance(
                employee_id=ids_by_email[leave.email], leave_type_id=leave_type.id, year=year,
                allocated_days=leave_type.default_annual_days, used_days=leave.days_used,
            )
        )
        balances += 1
    await session.flush()

    await log_action(
        session,
        user_id=actor.id,
        action=AuditAction.IMPORT_DATA,
        entity_type="Employee",
        entity_id=None,
        description=(
            f"Imported {len(logins)} employees, {made_departments} departments, {made_titles} job titles, "
            f"{salaries} salary records and {balances} leave balances from a file"
        ),
        request=None,
    )
    return made_departments, made_titles, logins, salaries, balances


def write_login_sheet(result: ImportResult, folder: Path) -> Path:
    """Save the temporary passwords to a private CSV, to be handed to each person and then deleted."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"temporary_logins_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(2)}.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["employee_code", "name", "email", "role", "temporary_password"])
        for login in result.logins:
            writer.writerow([login.employee_code, login.name, login.email, login.role, login.temporary_password])
    path.chmod(0o600)  # only the person who ran the import can read it
    return path


# --------------------------------------------------------------------------------------------- the template


def write_template(path: Path) -> None:
    """A ready-to-fill workbook: a Read-me sheet, the People sheet with a sample row, and the leave sheet."""
    workbook = Workbook()
    header_fill = PatternFill("solid", fgColor="0B3A82")
    optional_fill = PatternFill("solid", fgColor="5F7290")
    header_font = Font(color="FFFFFF", bold=True)

    help_sheet = workbook.active
    help_sheet.title = HELP_SHEET
    lines = [
        ("How to fill this file", True),
        ("1. Fill the 'People' sheet: one row per employee. Delete the grey EXAMPLE row first.", False),
        ("2. Columns with a dark blue heading are REQUIRED. Grey headings are optional.", False),
        ("3. Put the top person (the Founder) first, with 'reports_to_email' EMPTY. Everyone else names their manager's email.", False),
        ("4. Give the role MANAGER to anyone who has people reporting to them, so they can approve leave and assign tasks.", False),
        ("5. Departments and job titles you type here are created automatically. Spell each one the same way every time.", False),
        ("6. Dates: DD/MM/YYYY (for example 25/12/2022) or YYYY-MM-DD.", False),
        ("7. Money: plain numbers in rupees per MONTH, for example 45000. No currency signs.", False),
        ("8. Leave sheet (optional): if you start in the middle of a year, list the leave people have ALREADY taken this year.", False),
        ("9. Then run:  python -m app.import_employees check your_file.xlsx   (it only checks, and changes nothing).", False),
        ("10. When the check says OK, take a backup, then:  python -m app.import_employees load your_file.xlsx", False),
        ("", False),
        ("This file holds salaries and personal details. Keep it private and delete it when you are done.", True),
    ]
    for row, (text, bold) in enumerate(lines, start=1):
        cell = help_sheet.cell(row=row, column=1, value=text)
        cell.font = Font(bold=bold, size=13 if bold else 11)
    help_sheet.column_dimensions["A"].width = 130

    def build_sheet(title: str, columns: list[tuple[str, bool, str]], example: list[object]) -> None:
        sheet = workbook.create_sheet(title)
        for index, (name, required, hint) in enumerate(columns, start=1):
            cell = sheet.cell(row=1, column=index, value=name)
            cell.fill = header_fill if required else optional_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            sheet.cell(row=2, column=index, value=example[index - 1])
            sheet.cell(row=2, column=index).font = Font(italic=True, color="7B8EA9")
            sheet.column_dimensions[get_column_letter(index)].width = max(16, len(name) + 4)
            sheet.cell(row=1, column=index).comment = None
        sheet.freeze_panes = "A2"
        sheet.row_dimensions[1].height = 32

    build_sheet(
        PEOPLE_SHEET, EMPLOYEE_COLUMNS,
        ["EXAMPLE-delete.this.row@company.com", "Example", "Person", "25/12/2022", "Operations", "Operations Manager",
         "", "MANAGER", "FULL_TIME", "9876543210", "14/03/1990", "Head Office", 45000, 5000, 1500, ""],
    )
    build_sheet(LEAVE_SHEET, LEAVE_COLUMNS, ["EXAMPLE-delete.this.row@company.com", "CASUAL", 2])

    people = workbook[PEOPLE_SHEET]
    roles = DataValidation(type="list", formula1='"EMPLOYEE,MANAGER,HR,EXECUTIVE,ACCOUNTANT,FOUNDER"', allow_blank=True)
    types = DataValidation(type="list", formula1='"FULL_TIME,PART_TIME,CONTRACT,INTERN"', allow_blank=True)
    people.add_data_validation(roles)
    people.add_data_validation(types)
    role_col = get_column_letter([c[0] for c in EMPLOYEE_COLUMNS].index("role") + 1)
    type_col = get_column_letter([c[0] for c in EMPLOYEE_COLUMNS].index("employment_type") + 1)
    roles.add(f"{role_col}2:{role_col}{MAX_ROWS}")
    types.add(f"{type_col}2:{type_col}{MAX_ROWS}")
    workbook.save(path)
