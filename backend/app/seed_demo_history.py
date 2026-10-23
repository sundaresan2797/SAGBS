"""Fills a DEMO database with 12 months of realistic history for the people already in it.

    DATABASE_URL_SYNC=postgresql+psycopg2://.../ems_demo python -m app.seed_demo_history --upload-dir ./uploads_demo

It keeps the people, logins, roles, departments, designations and document types, and REPLACES the activity:
attendance, leave (requests and balances), tasks, salary structures and payslips, expense claims, documents,
notifications, audit log and the holiday calendar. Safe by design: it refuses to run unless the database name
ends in "_demo". To put the result into the real database, restore a dump of the verified demo (with a backup of
the real one first) - never run this script on the real database.

Everything is deterministic (fixed random seed), so the same run gives the same data. Attendance is generated with
the company's current rules (app.services.attendance_rules), so every status agrees with what the screens compute.
"""

import argparse
import random
import shutil
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, delete, insert, text
from sqlalchemy.engine import make_url

from app.config import settings
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.document import EmployeeDocument
from app.models.enums import (
    AttendanceStatus,
    ExpenseClaimCategory,
    ExpenseClaimStatus,
    LeaveRequestStatus,
    SalaryPaymentStatus,
    TaskPriority,
    TaskStatus,
)
from app.models.holiday import Holiday
from app.models.leave import LeaveBalance, LeaveRequest
from app.models.notification import Notification
from app.models.payroll import ExpenseClaim, SalaryPayment, SalaryRecord
from app.models.task import Task
from app.services import attendance_rules

IST = ZoneInfo("Asia/Kolkata")
START = date(2025, 10, 1)
SEED = 20261001
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def assert_demo_database(url: str) -> None:
    """The safety guard: only a database whose name ends in _demo may be filled."""
    name = make_url(url).database or ""
    if not name.endswith("_demo"):
        raise SystemExit(
            f"Refusing to run: database '{name}' is not a demo database (its name must end in '_demo'). "
            "This script replaces all activity data. To load it into the real database, restore a dump of the "
            "verified demo instead."
        )


# --------------------------------------------------------------------------- holidays (Tamil Nadu)
# Best-known dates for the period - please check them against the official Tamil Nadu government list.
HOLIDAYS = [
    ("2025-10-01", "Ayudha Pooja", False), ("2025-10-02", "Vijayadasami / Gandhi Jayanti", False),
    ("2025-10-20", "Deepavali", False), ("2025-12-25", "Christmas", False),
    ("2026-01-01", "New Year's Day", True), ("2026-01-14", "Pongal", False), ("2026-01-15", "Thiruvalluvar Day", False),
    ("2026-01-16", "Uzhavar Thirunal", False), ("2026-01-26", "Republic Day", False), ("2026-03-04", "Holi", True),
    ("2026-03-21", "Ramzan", False), ("2026-04-03", "Good Friday", False),
    ("2026-04-14", "Tamil New Year & Dr. Ambedkar Jayanti", False), ("2026-05-01", "May Day", False),
    ("2026-05-28", "Bakrid", False), ("2026-06-26", "Muharram", False), ("2026-08-15", "Independence Day", False),
    ("2026-09-04", "Krishna Jayanthi", False), ("2026-09-14", "Vinayagar Chathurthi", False),
    ("2026-10-02", "Gandhi Jayanti", False), ("2026-10-19", "Ayudha Pooja", False), ("2026-10-20", "Vijayadasami", False),
    ("2026-11-08", "Deepavali", False), ("2026-12-25", "Christmas", False),
]

# --------------------------------------------------------------------------- wording
CASUAL_WHY = ["Family function", "Personal work", "Bank and government office work", "Child's school event",
              "Travel to native place"]
SICK_WHY = ["Fever", "Stomach infection", "Doctor's advice - rest", "Migraine", "Cold and cough"]
EARNED_WHY = ["Trip to native place", "Family vacation", "Temple visit and family function", "Sister's wedding"]
UNPAID_WHY = ["Extended personal work", "Out of station family emergency"]
REJECT_WHY = ["Team is short of staff that week. Please pick another date.",
              "Too many people are already on leave on those days.",
              "Please apply earlier for planned leave.", "Month-end closing. Please reschedule."]
FIX_OUT_WHY = ["Forgot to tap, left at {t}", "Phone battery was dead, left at {t}", "Was in a meeting, left at {t}",
               "Confirmed with the employee: left at {t}"]
FIX_DAY_WHY = ["Phone was off, worked the full day", "Forgot to check in, came at {t}",
               "Network problem in the office, worked normally"]

TASKS = {
    "Sales": ["Follow up with 10 pending leads", "Prepare the quote for a new client", "Update the customer visit report",
              "Collect payment reminders for overdue accounts", "Plan next week's client meetings",
              "Share the monthly sales numbers", "Renew the contract with a regular client", "Call back missed enquiries"],
    "Human Resources": ["Schedule interviews for open roles", "Update the leave policy document", "Collect joining documents",
                        "Prepare the attendance report", "Organise the staff feedback survey", "Verify new employee records",
                        "Send offer letters to shortlisted candidates", "Close pending exit formalities"],
    "Operations": ["Update the vehicle schedule", "Check delivery reports for the week", "Follow up with the warehouse team",
                   "Reconcile trip sheets", "Prepare the route plan for next week", "Inspect the loading bay checklist",
                   "Confirm pickup slots with customers", "Update the fuel usage sheet"],
    "Marketing": ["Prepare the monthly newsletter", "Update the website banners", "Plan the social media calendar",
                  "Collect customer testimonials", "Design the festival offer poster", "Review the campaign results",
                  "Order printed brochures", "Update the company profile deck"],
    "Executive": ["Review the monthly business report", "Prepare the board meeting notes", "Approve the pending vendor list",
                  "Plan the quarterly targets", "Review the department budgets", "Meet the regional heads"],
    "Finance": ["Reconcile the bank statement", "Prepare the GST return data", "Review pending vendor invoices",
                "Update the cash flow sheet", "Verify the expense claims", "Prepare the monthly budget report",
                "Follow up on customer payments", "Close the month-end books"],
    "AI": ["Improve the route prediction model", "Clean the delivery dataset", "Write the model evaluation report",
           "Test the demand forecast", "Review the data pipeline errors", "Document the prediction API"],
    "Accounts": ["Record the day's payments", "Check the petty cash balance", "Prepare salary sheets", "File the TDS records",
                 "Match invoices with receipts", "Update the fixed assets list", "Prepare the payment vouchers"],
    "Engineering": ["Fix the login timeout issue", "Review a pull request", "Update the admin dashboard page",
                    "Add a new report export", "Write unit tests for the payroll module", "Improve the search speed",
                    "Fix the mobile layout bug"],
    "DevOps": ["Renew the server certificates", "Check the nightly backup", "Update the monitoring alerts",
               "Patch the staging server", "Review the disk usage report", "Automate the deployment steps"],
}
EXPENSE = {
    ExpenseClaimCategory.TRAVEL: (120, 2600, ["Auto fare to client site", "Cab to the airport", "Bus tickets for a site visit",
                                              "Toll charges", "Fuel for the company bike", "Metro and auto for meetings"]),
    ExpenseClaimCategory.FOOD: (150, 1800, ["Team lunch during the review", "Tea and snacks for visitors",
                                            "Working dinner at the site", "Refreshments for the training"]),
    ExpenseClaimCategory.MATERIALS: (200, 4500, ["Stationery for the office", "Printer cartridges", "Cables and adapters",
                                                 "Packing tape and labels", "Whiteboard markers and files"]),
    ExpenseClaimCategory.ACCOMMODATION: (1500, 6500, ["Hotel stay for the outstation visit", "Guest house for two nights"]),
    ExpenseClaimCategory.OTHER: (100, 1500, ["Courier charges", "Phone recharge for official calls",
                                             "Photocopy and lamination", "Parking charges"]),
}
EXPENSE_REJECT = ["Personal expense - not claimable.", "Bill is missing. Please attach it and claim again.",
                  "Amount is more than the approved limit.", "Already claimed earlier."]
FIELD_DEPARTMENTS = {"Sales", "Marketing", "Operations"}


# --------------------------------------------------------------------------- helpers
def at(day: date, minute_of_day: int, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, minute_of_day // 60, minute_of_day % 60, second, tzinfo=IST)


def hhmm(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0")


def make_pdf(title: str, lines: list[str]) -> bytes:
    """A small valid one-page PDF (so it opens in a browser), for the sample documents."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text_ops = ["BT", "/F1 18 Tf", "72 760 Td", f"({esc(title)}) Tj", "/F1 12 Tf"]
    for line in lines:
        text_ops += ["0 -24 Td", f"({esc(line)}) Tj"]
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def salary_band(designation: str, role: str) -> tuple[int, int]:
    d = designation.lower()
    if "founder" in d or d == "ceo":
        return 200000, 260000
    if d in {"coo", "cto", "cfo"}:
        return 150000, 190000
    if "head" in d:
        return 110000, 140000
    if "manager" in d and "accounts" not in d:
        return 65000, 95000
    if "accounts manager" in d:
        return 52000, 62000
    if "team lead" in d:
        return 55000, 70000
    if "senior accountant" in d:
        return 38000, 44000
    if "accountant" in d:
        return 26000, 34000
    if "senior" in d:
        return 45000, 65000
    if "engineer" in d:
        return 40000, 60000
    if "partner" in d:
        return 40000, 46000
    if "executive" in d:
        return 22000, 34000
    return 25000, 35000


# --------------------------------------------------------------------------- the generator
class Demo:
    def __init__(self, conn, upload_dir: Path, today: date):
        self.conn = conn
        self.upload_dir = upload_dir
        self.today = today
        self.last_day = today - timedelta(days=1)  # attendance is complete through yesterday
        self.rng = random.Random(SEED)
        self.audit: list[dict] = []
        self.notes: list[dict] = []

    # ---- people and reference data
    def load(self):
        rows = self.conn.execute(text("""
            select e.id, e.employee_code, e.first_name, e.last_name, e.user_id, e.manager_id, e.date_of_joining,
                   d.name as dept, g.name as desig, r.name as role, u.email
            from employees e join users u on u.id = e.user_id join roles r on r.id = u.role_id
            join departments d on d.id = e.department_id join designations g on g.id = e.designation_id
            order by e.id""")).mappings().all()
        self.people = [dict(r, full_name=f"{r['first_name']} {r['last_name']}") for r in rows]
        self.by_id = {p["id"]: p for p in self.people}
        self.leave_types = {r["code"]: r for r in self.conn.execute(text(
            "select id, code, name, is_paid, default_annual_days from leave_types where is_active")).mappings().all()}
        self.doc_types = {r["code"]: r["id"] for r in self.conn.execute(text("select id, code from document_types")).mappings()}

        def one(sql):
            row = self.conn.execute(text(sql)).first()
            return row[0] if row else None

        self.accountant_user = one("select u.id from users u join roles r on r.id=u.role_id where r.name='ACCOUNTANT' "
                                   "order by (u.email='accountant@example.com') desc, u.id limit 1")
        self.hr_user = one("select u.id from users u join roles r on r.id=u.role_id where r.name='HR' "
                           "order by (u.email='hr@example.com') desc, u.id limit 1")
        self.founder_user = one("select u.id from users u join roles r on r.id=u.role_id where r.name='FOUNDER' limit 1")

    def wipe(self):
        c = self.conn
        for table in ("task_comments", "tasks", "attendance", "leave_requests", "leave_balances", "expense_claims",
                      "salary_payments", "salary_records", "notifications", "employee_documents", "audit_logs", "holidays"):
            c.execute(text(f"delete from {table}"))
        # the leftover test leave type, now that nothing refers to it
        c.execute(text("delete from leave_types where code = 'REWERW'"))
        # names asked for by the owner: the CEO is "Sundareswaran S"
        c.execute(text("update employees set first_name='Sundareswaran', last_name='S' where employee_code='EMP-0046'"))
        self.spread_joining_dates()
        if self.upload_dir.exists():
            assert "demo" in self.upload_dir.name, "refusing to empty a folder that is not a demo uploads folder"
            shutil.rmtree(self.upload_dir)
        self.upload_dir.mkdir(parents=True)

    def spread_joining_dates(self):
        """Most current people are given joining dates before this period, like a real 55-person company;
        about ten stay recent joiners (so joining-date proration is still exercised). Names and logins are untouched."""
        c = self.conn
        rows = c.execute(text("""
            select e.id, e.employee_code, e.date_of_joining, r.name as role,
                   exists (select 1 from employees x where x.manager_id = e.id) as manages
            from employees e join users u on u.id = e.user_id join roles r on r.id = u.role_id order by e.id""")).mappings().all()
        recent_ok = [r for r in rows if r["date_of_joining"] >= START and r["role"] == "EMPLOYEE" and not r["manages"]
                     and r["employee_code"] != "EMP-0003"]
        keep = {r["id"] for r in random.Random(SEED).sample(recent_ok, min(9, len(recent_ok)))}
        keep |= {r["id"] for r in rows if r["employee_code"] == "EMP-0005"}  # the demo employee who joined in Nov 2025
        for r in rows:
            if r["date_of_joining"] < START or r["id"] in keep:
                continue
            g = random.Random(f"{SEED}-join-{r['id']}")
            if r["role"] in ("FOUNDER", "EXECUTIVE"):
                lo, hi = date(2015, 1, 1), date(2020, 12, 31)
            elif r["manages"]:
                lo, hi = date(2018, 1, 1), date(2023, 12, 31)
            else:
                lo, hi = date(2019, 6, 1), date(2025, 8, 31)
            c.execute(text("update employees set date_of_joining = :d where id = :i"),
                      {"d": lo + timedelta(days=g.randint(0, (hi - lo).days)), "i": r["id"]})

    def audit_add(self, user_id, action, entity_type, entity_id, description, when):
        self.audit.append(dict(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                               description=description[:1000], ip_address=f"10.0.{self.rng.randint(0, 3)}.{self.rng.randint(2, 250)}",
                               user_agent="Mozilla/5.0 (demo data)", created_at=when))

    def note_add(self, user_id, title, message, kind, when, read):
        self.notes.append(dict(user_id=user_id, title=title, message=message, notification_type=kind, is_read=read,
                               created_at=when, updated_at=when))

    def fixer_for(self, person):
        manager = self.by_id.get(person["manager_id"]) if person["manager_id"] else None
        if manager:
            return manager["user_id"], manager["full_name"]
        hr = self.conn.execute(text("select u.id, coalesce(e.first_name||' '||e.last_name, u.email) from users u "
                                    "left join employees e on e.user_id=u.id where u.id=:i"), {"i": self.hr_user}).first()
        return hr[0], hr[1]

    # ---- holidays
    def holidays(self):
        rows = [dict(name=n, holiday_date=date.fromisoformat(d), description="Tamil Nadu holiday", is_optional=opt,
                     created_at=at(START, 9 * 60), updated_at=at(START, 9 * 60)) for d, n, opt in HOLIDAYS]
        self.conn.execute(insert(Holiday.__table__), rows)
        self.off_dates = {date.fromisoformat(d) for d, _, opt in HOLIDAYS if not opt}

    def is_off(self, d: date) -> bool:
        return d.weekday() == 6 or d in self.off_dates

    def working_days_between(self, start: date, end: date) -> int:
        return sum(1 for i in range((end - start).days + 1) if not self.is_off(start + timedelta(days=i)))

    # ---- leave
    def leave(self):
        rng, today = self.rng, self.today
        self.leave_days: dict[int, set[date]] = defaultdict(set)  # approved leave, so attendance skips it
        taken: dict[int, set[date]] = defaultdict(set)
        used: dict[tuple, float] = defaultdict(float)
        alloc: dict[tuple, float] = {}
        paid_types = [t for t in self.leave_types.values() if t["is_paid"] and float(t["default_annual_days"]) > 0]

        def allocation(person, leave_type, year):
            default = float(leave_type["default_annual_days"])
            join = person["date_of_joining"]
            if join.year < year:
                return default
            return round(default * (13 - join.month) / 12 * 2) / 2

        balances = []
        for p in self.people:
            for year in (2025, 2026):
                if p["date_of_joining"].year > year:
                    continue
                for t in paid_types:
                    alloc[(p["id"], t["code"], year)] = allocation(p, t, year)

        plan = {"CASUAL": (3, 6, [1, 1, 1, 2, 2, 3], CASUAL_WHY), "SICK": (2, 4, [1, 1, 2, 3], SICK_WHY),
                "EARNED": (0, 2, [3, 4, 5, 6], EARNED_WHY), "UNPAID": (0, 1, [1, 2], UNPAID_WHY)}
        requests = []
        for p in self.people:
            first = max(START, p["date_of_joining"] + timedelta(days=7))
            if first > today or not p["manager_id"]:
                continue  # no manager means nobody to approve, so the top people take no leave here
            for code, (lo, hi, lengths, reasons) in plan.items():
                if code not in self.leave_types:
                    continue
                if code == "UNPAID" and rng.random() > 0.12:
                    continue
                if code == "EARNED" and (today - p["date_of_joining"]).days < 180:
                    continue
                tenure_scale = min(1.0, max(0.25, ((today - first).days + 1) / 365))
                count = max(0, round(rng.randint(lo, hi) * tenure_scale)) if code != "UNPAID" else 1
                for _ in range(count):
                    for _try in range(12):
                        start = first + timedelta(days=rng.randint(0, (today + timedelta(days=21) - first).days))
                        length = rng.choice(lengths)
                        end = start + timedelta(days=length - 1)
                        if start.year != end.year or self.is_off(start):
                            continue
                        span = {start + timedelta(days=i) for i in range(length)}
                        if span & taken[p["id"]]:
                            continue
                        days = self.working_days_between(start, end)
                        if days == 0:
                            continue
                        lt = self.leave_types[code]
                        key = (p["id"], code, start.year)
                        if lt["is_paid"] and (key not in alloc or used[key] + days > alloc[key]):
                            continue
                        created = at(max(p["date_of_joining"], start - timedelta(days=rng.randint(1, 9))), rng.randint(9 * 60, 17 * 60))
                        if start > today:
                            # future leave: mostly still waiting for a decision if applied recently
                            status = LeaveRequestStatus.PENDING if rng.random() < 0.6 else LeaveRequestStatus.APPROVED
                            created = at(today - timedelta(days=rng.randint(0, 6)), rng.randint(9 * 60, 17 * 60))
                        else:
                            roll = rng.random()
                            status = (LeaveRequestStatus.APPROVED if roll < 0.84 else
                                      LeaveRequestStatus.REJECTED if roll < 0.92 else LeaveRequestStatus.CANCELLED)
                        if status in (LeaveRequestStatus.APPROVED, LeaveRequestStatus.PENDING, LeaveRequestStatus.REJECTED, LeaveRequestStatus.CANCELLED):
                            taken[p["id"]] |= span
                        requests.append((p, code, start, end, days, rng.choice(reasons), status, created))
                        if status == LeaveRequestStatus.APPROVED and lt["is_paid"]:
                            used[key] += days
                        break

        rows = []
        for p, code, start, end, days, why, status, created in requests:
            lt = self.leave_types[code]
            manager = self.by_id[p["manager_id"]]
            decided = min(created + timedelta(hours=rng.randint(2, 40)), at(today, 9 * 60))
            row = dict(employee_id=p["id"], leave_type_id=lt["id"], start_date=start, end_date=end, number_of_days=days,
                       reason=why, status=status, approved_by=None, approved_at=None, rejection_reason=None,
                       created_at=created, updated_at=created)
            self.audit_add(p["user_id"], "CREATE_LEAVE", "LeaveRequest", None, f"{p['employee_code']} applied for {lt['name']} {start} to {end}", created)
            if status in (LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED):
                row.update(approved_by=manager["user_id"], approved_at=decided, updated_at=decided)
                old = (decided.date() < today - timedelta(days=5))
                if status == LeaveRequestStatus.APPROVED:
                    self.note_add(p["user_id"], "Leave request approved", f"Your leave request from {start} to {end} was approved.", "LEAVE_APPROVED", decided, old)
                    self.audit_add(manager["user_id"], "APPROVE_LEAVE", "LeaveRequest", None, f"Approved leave request for {p['employee_code']}", decided)
                else:
                    reason = rng.choice(REJECT_WHY)
                    row["rejection_reason"] = reason
                    self.note_add(p["user_id"], "Leave request rejected", f"Your leave request from {start} to {end} was not approved. Reason: {reason}", "LEAVE_REJECTED", decided, old)
                    self.audit_add(manager["user_id"], "REJECT_LEAVE", "LeaveRequest", None, f"Rejected leave request for {p['employee_code']}", decided)
            if status == LeaveRequestStatus.CANCELLED:
                self.audit_add(p["user_id"], "CANCEL_LEAVE", "LeaveRequest", None, f"{p['employee_code']} cancelled leave {start}", decided)
            if row["status"] == LeaveRequestStatus.APPROVED:
                for i in range((end - start).days + 1):
                    self.leave_days[p["id"]].add(start + timedelta(days=i))
            rows.append(row)
        self.conn.execute(insert(LeaveRequest.__table__), rows)

        # balances follow what was actually approved
        approved_used: dict[tuple, float] = defaultdict(float)
        for row in rows:
            if row["status"] == LeaveRequestStatus.APPROVED and self.leave_types_by_id(row["leave_type_id"])["is_paid"]:
                approved_used[(row["employee_id"], self.leave_types_by_id(row["leave_type_id"])["code"], row["start_date"].year)] += float(row["number_of_days"])
        for (emp_id, code, year), allocated in alloc.items():
            lt = self.leave_types[code]
            stamp = at(max(date(year, 1, 1), self.by_id[emp_id]["date_of_joining"]), 9 * 60)
            balances.append(dict(employee_id=emp_id, leave_type_id=lt["id"], year=year, allocated_days=allocated,
                                 used_days=approved_used.get((emp_id, code, year), 0.0), created_at=stamp, updated_at=stamp))
        self.conn.execute(insert(LeaveBalance.__table__), balances)
        self.n_leave, self.n_balances = len(rows), len(balances)

    def leave_types_by_id(self, type_id):
        return next(t for t in self.leave_types.values() if t["id"] == type_id)

    # ---- attendance
    def attendance(self):
        rng, today = self.rng, self.today
        rows = []
        for p in self.people:
            r = random.Random(f"{SEED}-{p['id']}")
            late_p = r.choices([0.03, 0.07, 0.15, 0.30], weights=[50, 25, 15, 10])[0]
            busy = p["dept"] in {"Operations", "DevOps"}
            first = max(START, p["date_of_joining"])
            fixer_id, fixer_name = self.fixer_for(p)
            d = first
            while d <= self.last_day:
                day = d
                d += timedelta(days=1)
                if day in self.leave_days[p["id"]]:
                    continue
                if self.is_off(day):
                    if not (busy and rng.random() < 0.012):
                        continue
                    minute, worked = 9 * 60 + rng.randint(0, 60), rng.randint(180, 330)
                else:
                    u = rng.random()
                    if u < 0.015:
                        continue  # absent without a record
                    if u < 0.019:  # forgot to check in at all
                        if rng.random() < (0.85 if (self.today - day).days > 7 else 0.3):
                            minute, worked = 8 * 60 + rng.randint(40, 75), rng.randint(470, 540)
                            rows.append(self.fixed_day(p, day, minute, worked, fixer_id, fixer_name))
                        continue
                    if rng.random() < 0.005:
                        minute = 12 * 60 + rng.randint(35, 120)  # came in the afternoon
                        worked = rng.randint(200, 330)
                    else:
                        minute = (9 * 60 + rng.randint(11, 95)) if rng.random() < late_p else (8 * 60 + rng.randint(38, 70))
                        worked = 480 + int(rng.gauss(15, 25))
                        worked = max(400, min(560, worked))
                        if rng.random() < 0.012:
                            worked = rng.randint(150, 400)  # left early
                        elif rng.random() < (0.16 if busy else 0.10):
                            worked += rng.randint(45, 150)  # stayed late
                        elif rng.random() < 0.003:
                            worked = rng.randint(780, 900)  # a very long day
                second = rng.randint(0, 59)
                check_in = at(day, minute, second)
                if check_in + timedelta(minutes=worked) > at(day, 23 * 60 + 50):
                    worked = int((at(day, 23 * 60 + 50) - check_in).total_seconds() // 60)
                check_out = check_in + timedelta(minutes=worked, seconds=rng.randint(0, 59))
                working = int((check_out - check_in).total_seconds() // 60)
                late = attendance_rules.late_minutes_for(check_in)
                row = dict(employee_id=p["id"], attendance_date=day, check_in=check_in, check_out=check_out,
                           working_minutes=working, late_minutes=late,
                           overtime_minutes=attendance_rules.overtime_minutes_for(working),
                           status=attendance_rules.status_at_check_out(check_in, working),
                           corrected_by_user_id=None, corrected_by_name=None, corrected_at=None, correction_reason=None,
                           created_at=check_in, updated_at=check_out)
                if rng.random() < 0.012 and not self.is_off(day):  # forgot to check out
                    row.update(check_out=None, working_minutes=None, overtime_minutes=0,
                               status=attendance_rules.status_at_check_in(check_in), updated_at=check_in)
                    recent = (today - day).days <= 10
                    if rng.random() < (0.3 if recent else 0.85):  # a manager fixed it afterwards
                        out_min = minute + rng.randint(470, 560)
                        out = at(day, min(out_min, 23 * 60 + 30), rng.randint(0, 59))
                        fixed_at = at(day + timedelta(days=rng.randint(1, 3)), rng.randint(10 * 60, 17 * 60))
                        if fixed_at.date() >= today:
                            fixed_at = at(today - timedelta(days=0), 10 * 60)
                        working = int((out - check_in.replace(second=0)).total_seconds() // 60)
                        why = rng.choice(FIX_OUT_WHY).format(t=hhmm(out))
                        row.update(check_out=out, working_minutes=working, overtime_minutes=attendance_rules.overtime_minutes_for(working),
                                   status=attendance_rules.status_at_check_out(check_in, working), corrected_by_user_id=fixer_id,
                                   corrected_by_name=fixer_name[:150], corrected_at=fixed_at, correction_reason=why, updated_at=fixed_at)
                        self.note_add(p["user_id"], "Your check-out was fixed", f"{fixer_name} set your check-out for {day.day} {day.strftime('%b')} to {hhmm(out)}. Reason: {why}", "ATTENDANCE_CORRECTED", fixed_at, (today - fixed_at.date()).days > 5)
                        self.audit_add(fixer_id, "CORRECT_ATTENDANCE", "Attendance", None, f"Fixed missed check-out for {p['employee_code']} on {day} to {out.strftime('%H:%M')} ({why})", fixed_at)
                rows.append(row)
        self.attendance_rows = rows
        # every stored status must agree with the rules the screens use
        for row in rows:
            ci = row["check_in"]
            expected = (attendance_rules.status_at_check_out(ci, row["working_minutes"]) if row["check_out"]
                        else attendance_rules.status_at_check_in(ci))
            assert row["status"] == expected, (row["employee_id"], row["attendance_date"], row["status"], expected)
        for start in range(0, len(rows), 3000):
            self.conn.execute(insert(Attendance.__table__), rows[start:start + 3000])
        self.n_attendance = len(rows)

    def fixed_day(self, p, day, minute, worked, fixer_id, fixer_name):
        """A day the person worked but forgot to punch in for; a manager added it afterwards."""
        rng = self.rng
        check_in = at(day, minute, rng.randint(0, 59))
        check_out = check_in + timedelta(minutes=worked)
        working = int((check_out - check_in.replace(second=0)).total_seconds() // 60)
        fixed_at = min(at(day + timedelta(days=rng.randint(1, 3)), rng.randint(10 * 60, 17 * 60)), at(self.today, 10 * 60))
        why = rng.choice(FIX_DAY_WHY).format(t=hhmm(check_in))
        self.note_add(p["user_id"], "Your attendance was added", f"{fixer_name} recorded you as working on {day.day} {day.strftime('%b')}, {hhmm(check_in)} to {hhmm(check_out)}. Reason: {why}", "ATTENDANCE_CORRECTED", fixed_at, (self.today - fixed_at.date()).days > 5)
        self.audit_add(fixer_id, "CORRECT_ATTENDANCE", "Attendance", None, f"Marked {p['employee_code']} present on {day} ({why})", fixed_at)
        return dict(employee_id=p["id"], attendance_date=day, check_in=check_in, check_out=check_out, working_minutes=working,
                    late_minutes=attendance_rules.late_minutes_for(check_in),
                    overtime_minutes=attendance_rules.overtime_minutes_for(working),
                    status=attendance_rules.status_at_check_out(check_in, working), corrected_by_user_id=fixer_id,
                    corrected_by_name=fixer_name[:150], corrected_at=fixed_at, correction_reason=why, created_at=fixed_at, updated_at=fixed_at)

    def attendance_audit(self):
        """Check-in / check-out / login lines, the way the real system would have written them."""
        by_id = self.by_id
        for row in self.attendance_rows:
            p = by_id[row["employee_id"]]
            if row["corrected_at"] is not None and row["created_at"] == row["corrected_at"]:
                continue  # added by hand: no punch happened
            if self.rng.random() < 0.85:
                self.audit_add(p["user_id"], "LOGIN", None, None, f"User {p['email']} logged in", row["check_in"] - timedelta(minutes=self.rng.randint(1, 12)))
            self.audit_add(p["user_id"], "CHECK_IN", "Attendance", p["id"], f"{p['employee_code']} checked in", row["check_in"])
            if row["check_out"] is not None and row["corrected_at"] is None:
                self.audit_add(p["user_id"], "CHECK_OUT", "Attendance", p["id"], f"{p['employee_code']} checked out", row["check_out"])

    # ---- salary and payslips
    def payroll(self):
        rng = self.rng
        records, structures = [], {}
        for p in self.people:
            r = random.Random(f"{SEED}-pay-{p['id']}")
            lo, hi = salary_band(p["desig"], p["role"])
            gross = round_to(r.uniform(lo, hi), 500)
            raised = p["date_of_joining"] <= date(2026, 1, 31) and r.random() < 0.62
            new_gross = round_to(gross * (1 + r.uniform(0.05, 0.12)), 500) if raised else gross

            def split(g):
                basic = round_to(g * 0.5, 100)
                return basic, g - basic, round_to(basic * 0.12, 10) + 200

            old = split(gross)
            new = split(new_gross)
            structures[p["id"]] = (old, new, raised)
            effective = date(2026, 4, 1) if raised else max(START, p["date_of_joining"])
            stamp = at(effective, 10 * 60)
            records.append(dict(employee_id=p["id"], basic_pay=new[0], allowances=new[1], deductions=new[2],
                                effective_from=effective, created_at=stamp, updated_at=stamp))
        self.conn.execute(insert(SalaryRecord.__table__), records)

        months = [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 9)]
        pending_pool = {p["id"] for p in rng.sample(self.people, 6)}
        payments = []
        for year, month in months:
            last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
            run_day = last + timedelta(days=1)
            self.audit_add(self.accountant_user, "RUN_PAYROLL", "SalaryPayment", None, f"Ran payroll for {month}/{year}", at(run_day, 11 * 60))
            for p in self.people:
                if p["date_of_joining"] > last:
                    continue
                old, new, raised = structures[p["id"]]
                basic, allow, deduct = new if (raised and (year, month) >= (2026, 4)) else old
                pending = (year, month) == (2026, 8) and p["id"] in pending_pool
                paid_day = run_day + timedelta(days=rng.randint(1, 5)) if not pending else None
                amount = basic + allow - deduct
                payments.append(dict(employee_id=p["id"], year=year, month=month, amount=amount, basic_pay=basic,
                                     allowances=allow, deductions=deduct,
                                     status=SalaryPaymentStatus.PENDING if pending else SalaryPaymentStatus.PAID,
                                     paid_date=paid_day, created_at=at(run_day, 11 * 60),
                                     updated_at=at(paid_day, 15 * 60) if paid_day else at(run_day, 11 * 60)))
                if paid_day:
                    self.audit_add(self.accountant_user, "PAY_SALARY", "SalaryPayment", None,
                                   f"Marked salary paid for {p['employee_code']} ({MONTH_NAMES[month - 1]} {year})", at(paid_day, 15 * 60))
        self.conn.execute(insert(SalaryPayment.__table__), payments)
        self.n_payments = len(payments)

    # ---- expense claims
    def expenses(self):
        rng, today = self.rng, self.today
        rows = []
        for p in self.people:
            field = p["dept"] in FIELD_DEPARTMENTS
            d = max(START, p["date_of_joining"])
            month_start = date(d.year, d.month, 1)
            while month_start <= today:
                if rng.random() < (0.30 if field else 0.10):
                    month_end = min(today, (date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1) - timedelta(days=1)))
                    day = month_start + timedelta(days=rng.randint(0, max(0, (month_end - month_start).days)))
                    if day >= d and day <= today:
                        weights = ([45, 25, 5, 10, 15] if field else [20, 20, 40, 0, 20])
                        cat = rng.choices(list(EXPENSE), weights=weights)[0]
                        lo, hi, texts = EXPENSE[cat]
                        amount = round_to(rng.uniform(lo, hi), 10)
                        created = at(day, rng.randint(10 * 60, 18 * 60))
                        age = (today - day).days
                        roll = rng.random()
                        if age > 40:
                            status = ExpenseClaimStatus.PAID if roll < 0.88 else ExpenseClaimStatus.REJECTED
                        elif age > 10:
                            status = (ExpenseClaimStatus.APPROVED if roll < 0.4 else ExpenseClaimStatus.PAID if roll < 0.85 else ExpenseClaimStatus.REJECTED)
                        else:
                            status = (ExpenseClaimStatus.PENDING if roll < 0.65 else ExpenseClaimStatus.APPROVED if roll < 0.9 else ExpenseClaimStatus.REJECTED)
                        reviewed = min(created + timedelta(days=rng.randint(1, 4)), at(today, 9 * 60)) if status != ExpenseClaimStatus.PENDING else None
                        if reviewed is not None and reviewed < created:
                            reviewed = created
                        paid = (reviewed.date() + timedelta(days=rng.randint(2, 9))) if status == ExpenseClaimStatus.PAID else None
                        if paid and paid > today:
                            paid = today
                        rows.append(dict(employee_id=p["id"], category=cat, amount=amount, description=rng.choice(texts), status=status,
                                         rejection_reason=rng.choice(EXPENSE_REJECT) if status == ExpenseClaimStatus.REJECTED else None,
                                         reviewed_by=self.accountant_user if reviewed else None, reviewed_at=reviewed, paid_date=paid,
                                         created_at=created, updated_at=reviewed or created))
                        self.audit_add(p["user_id"], "CREATE_EXPENSE_CLAIM", "ExpenseClaim", None, f"{p['employee_code']} submitted a {cat.value.lower()} claim of {amount}", created)
                        if reviewed:
                            act = "REJECT_EXPENSE_CLAIM" if status == ExpenseClaimStatus.REJECTED else "APPROVE_EXPENSE_CLAIM"
                            self.audit_add(self.accountant_user, act, "ExpenseClaim", None, f"Reviewed claim of {p['employee_code']}", reviewed)
                month_start = date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)
        self.conn.execute(insert(ExpenseClaim.__table__), rows)
        self.n_expenses = len(rows)

    # ---- tasks
    def tasks(self):
        rng, today = self.rng, self.today
        rows = []
        for p in self.people:
            r = random.Random(f"{SEED}-task-{p['id']}")
            first = max(START, p["date_of_joining"])
            months = max(1, (today - first).days // 30)
            manager = self.by_id.get(p["manager_id"]) if p["manager_id"] else p
            titles = TASKS.get(p["dept"], TASKS["Operations"])
            for _ in range(min(12, max(2, int(months * 0.7)))):
                created = at(first + timedelta(days=r.randint(0, max(0, (today - first).days))), r.randint(9 * 60, 17 * 60))
                age = (today - created.date()).days
                roll = r.random()
                if age > 45:
                    status = (TaskStatus.COMPLETED if roll < 0.85 else TaskStatus.BLOCKED if roll < 0.88 else TaskStatus.IN_PROGRESS if roll < 0.95 else TaskStatus.TODO)
                elif age > 15:
                    status = (TaskStatus.COMPLETED if roll < 0.55 else TaskStatus.IN_PROGRESS if roll < 0.8 else TaskStatus.TODO if roll < 0.92 else TaskStatus.BLOCKED)
                else:
                    status = (TaskStatus.TODO if roll < 0.4 else TaskStatus.IN_PROGRESS if roll < 0.8 else TaskStatus.COMPLETED if roll < 0.95 else TaskStatus.BLOCKED)
                due = created.date() + timedelta(days=r.randint(3, 21))
                priority = r.choices([TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH, TaskPriority.URGENT], weights=[20, 50, 25, 5])[0]
                updated = created + timedelta(days=r.randint(1, 12)) if status != TaskStatus.TODO else created
                updated = max(created, min(updated, at(today, 9 * 60)))
                title = r.choice(titles)
                rows.append(dict(title=title, description=None, assigned_to=p["id"], assigned_by=manager["id"], priority=priority,
                                 status=status, due_date=due, created_at=created, updated_at=updated))
                self.note_add(p["user_id"], "New task assigned", f"You have been assigned: {title}", "TASK_ASSIGNED", created, age > 14 or r.random() < 0.4)
                self.audit_add(manager["user_id"], "CREATE_TASK", "Task", None, f"Assigned '{title}' to {p['employee_code']}", created)
        self.conn.execute(insert(Task.__table__), rows)
        self.n_tasks = len(rows)

    # ---- documents (real small PDFs on disk)
    def documents(self):
        rng, today = self.rng, self.today
        rows = []
        certs = [p for p in self.people if rng.random() < 0.42]
        expiring = {p["id"]: ("expired" if i < 8 else "soon" if i < 16 else "later") for i, p in enumerate(certs)}
        for p in self.people:
            kinds = [("OFFER_LETTER", "Offer Letter"), ("ID_PROOF", "Aadhaar Card"), ("RESUME", "Resume")]
            if p["id"] in expiring:
                kinds.append(("CERTIFICATION", "Certificate"))
            first = max(START, p["date_of_joining"])
            for code, label in kinds:
                if code not in self.doc_types:
                    continue
                day = first + timedelta(days=rng.randint(0, min(14, max(0, (today - first).days))))
                expiry = None
                if code == "CERTIFICATION":
                    when = expiring[p["id"]]
                    expiry = (today - timedelta(days=rng.randint(3, 200)) if when == "expired"
                              else today + timedelta(days=rng.randint(2, 28)) if when == "soon"
                              else today + timedelta(days=rng.randint(60, 700)))
                folder = self.upload_dir / p["employee_code"]
                folder.mkdir(exist_ok=True)
                name = f"{code}_{day.strftime('%Y%m%d')}_{uuid.UUID(int=rng.getrandbits(128)).hex[:4]}.pdf"
                pdf = make_pdf(f"{label} - {p['full_name']}", [f"Staff ID: {p['employee_code']}", f"Department: {p['dept']}",
                                                             "Sample document created for demonstration only."])
                (folder / name).write_bytes(pdf)
                stamp = at(day, rng.randint(10 * 60, 17 * 60))
                rows.append(dict(employee_id=p["id"], document_type_id=self.doc_types[code], file_name=f"{label} - {p['full_name']}.pdf",
                                 file_path=f"{p['employee_code']}/{name}", file_size=len(pdf), mime_type="application/pdf",
                                 expiry_date=expiry, uploaded_by=p["user_id"], created_at=stamp, updated_at=stamp))
                self.audit_add(p["user_id"], "UPLOAD_DOCUMENT", "EmployeeDocument", None, f"{p['employee_code']} uploaded {label}", stamp)
        self.conn.execute(insert(EmployeeDocument.__table__), rows)
        self.n_documents = len(rows)

    # ---- notifications and audit are collected along the way and written last
    def flush_side_tables(self):
        self.audit.sort(key=lambda r: r["created_at"])
        for start in range(0, len(self.audit), 5000):
            self.conn.execute(insert(AuditLog.__table__), self.audit[start:start + 5000])
        for start in range(0, len(self.notes), 5000):
            self.conn.execute(insert(Notification.__table__), self.notes[start:start + 5000])
        self.n_audit, self.n_notes = len(self.audit), len(self.notes)

    # ---- checks
    def verify(self) -> list[str]:
        problems = []

        def check(label, sql):
            n = self.conn.execute(text(sql)).scalar_one()
            if n:
                problems.append(f"{label}: {n}")

        check("check-out before check-in", "select count(*) from attendance where check_out is not null and check_out <= check_in")
        check("attendance before joining", "select count(*) from attendance a join employees e on e.id=a.employee_id where a.attendance_date < e.date_of_joining")
        check("attendance on approved leave days", """select count(*) from attendance a join leave_requests l on l.employee_id=a.employee_id
            and l.status='APPROVED' and a.attendance_date between l.start_date and l.end_date""")
        check("leave balance used != approved days", """select count(*) from leave_balances b join leave_types t on t.id=b.leave_type_id
            where b.used_days <> coalesce((select sum(number_of_days) from leave_requests l where l.employee_id=b.employee_id
            and l.leave_type_id=b.leave_type_id and l.status='APPROVED' and extract(year from l.start_date)=b.year),0)""")
        check("leave balance over-used", "select count(*) from leave_balances where used_days > allocated_days")
        check("paid payslip without paid date", "select count(*) from salary_payments where status='PAID' and paid_date is null")
        check("pending payslip with paid date", "select count(*) from salary_payments where status='PENDING' and paid_date is not null")
        check("payslip amount != its saved structure", "select count(*) from salary_payments where amount <> basic_pay + allowances - deductions")
        check("payslip before joining", """select count(*) from salary_payments p join employees e on e.id=p.employee_id
            where make_date(p.year,p.month,1) < date_trunc('month', e.date_of_joining)""")
        check("correction without a reason", "select count(*) from attendance where corrected_at is not null and (correction_reason is null or corrected_by_name is null)")
        check("approved leave with no approver", "select count(*) from leave_requests where status='APPROVED' and approved_by is null")
        return problems


def run(upload_dir: Path) -> None:
    url = settings.database_url_sync
    assert_demo_database(url)
    engine = create_engine(url)
    today = date.today()
    with engine.begin() as conn:
        demo = Demo(conn, upload_dir, today)
        demo.wipe()
        demo.load()
        demo.holidays()
        demo.leave()
        demo.attendance()
        demo.attendance_audit()
        demo.payroll()
        demo.expenses()
        demo.tasks()
        demo.documents()
        demo.flush_side_tables()
        problems = demo.verify()
        if problems:
            raise SystemExit("Verification failed, nothing was saved:\n  " + "\n  ".join(problems))
        print(f"OK - {url.rsplit('/', 1)[-1]} now has 12 months of history to {today}:")
        for label, n in [("people kept", len(demo.people)), ("attendance days", demo.n_attendance), ("leave requests", demo.n_leave),
                         ("leave balances", demo.n_balances), ("payslips", demo.n_payments), ("expense claims", demo.n_expenses),
                         ("tasks", demo.n_tasks), ("documents (PDF files)", demo.n_documents), ("notifications", demo.n_notes),
                         ("audit log lines", demo.n_audit), ("holidays", len(HOLIDAYS))]:
            print(f"  {label:<24}{n:>8}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upload-dir", default="./uploads_demo", help="where the sample PDFs go (its name must contain 'demo')")
    run(Path(parser.parse_args().upload_dir).resolve())
