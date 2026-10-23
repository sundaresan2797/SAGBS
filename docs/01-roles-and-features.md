# Roles and Features — the complete guide

Written for: the owner, and anyone being onboarded as Admin or HR. This is a full, plain-English list of
what each **Login Role** can see and do in the system, as it actually works today.

## First, an important distinction

Every person in the system has **two separate things** attached to them, and it's easy to confuse them:

- **Login Role** — controls what they can *see and do in the system*. There are only 7 of these:
  Founder, Executive, Admin, HR, Accountant, Manager, Employee.
- **Designation and Department** — their actual job title and team (e.g. "Data Entry Supervisor" in
  "Data Entry"). This is just descriptive information. It does **not** affect what buttons they see.

So someone can be a "Data Entry Supervisor" with the Login Role "HR" — the job title says what they do
day to day, the Login Role says what the system lets them do. Changing one never changes the other.

## The 7 roles, at a glance

| Login Role | Who this is for | Sees company-wide data? | Sees money (payroll)? | Runs the system? |
|---|---|---|---|---|
| **Founder** | The business owner | Yes | Full control | No (that's Admin's job) |
| **Executive** | A second owner / co-founder (e.g. CEO, COO) | Yes | Full control | No |
| **Admin** | IT / system administrator | Yes (for people/org data) | No, never | Yes |
| **HR** | Human Resources staff | Yes (for people/attendance/leave) | No | Partly (people & org setup only) |
| **Accountant** | Payroll/finance staff | No (only money matters) | Full control | No |
| **Manager** | Anyone with people reporting to them | Only their own team | No | No |
| **Employee** | Everyone else | Only themselves | No | No |

A full technical breakdown of exactly which of the 29 underlying permissions each role has is always
visible live, inside the app itself: **Admin → Roles & Permissions.**

---

## Founder

**Who this is:** the business owner. Founder is the one role with full control over both the company's
people and its money, but deliberately does **not** administer the system itself (no user accounts, no
org setup) — that split exists so the owner's attention stays on running the business, not configuring
software.

**Dashboard** — the company-wide dashboard: live numbers for the whole company (who's present today,
leave pending, tasks, payroll at a glance), not just their own.

**Employees** — can see every employee's full profile across the whole company (phone number, date of
birth, everything), not just their own team. Can edit an employee's Department and Job Title.

**Attendance** — can see everyone's attendance company-wide, mark someone present who forgot to check
in, fix a missed check-out, and correct an already-recorded day (e.g. change Present to Half Day) for
*anyone* in the company, not just their own reports. Has their own personal "My Attendance" to check
themselves in and out.

**Leave** — can see and act on every leave request in the company, not just their own team's. Can
record a leave or a short permission on behalf of any employee (e.g. someone phoned in sick). Has their
own "My Leave" to apply for their own time off.

**Tasks** — can see and create tasks for the whole company (Company Tasks), plus their own personal task
list (My Tasks).

**Documents** — can see and manage their own uploaded documents (ID proofs, certificates). Does not
manage other people's documents directly (that's HR's job) but — see "Salary Records" below — can see
money-related documents like payslips for anyone.

**Salary Records & Attendance Summary** — full access: can set anyone's salary, run payroll for the
month, mark a payment as paid, and see the Attendance Summary (the same day-count numbers payroll is
based on) for the whole company.

**Expense Claims** — can approve, reject, or mark an expense claim as paid for anyone (except their own
— nobody can approve their own claim).

**My Payslips** — downloads their own payslips once paid.

**Notifications** — gets notified about company-wide events: new leave requests, expense claims, salary
payments, etc.

**Audit Logs** — can see the full history of who did what in the system (every login, every change).

**Cannot do:** create or edit employee accounts, reset anyone's password, change anyone's Login Role,
manage departments/job titles/leave types/holidays, or see the Roles & Permissions screen. All of that
is Admin's job.

---

## Executive

**Who this is:** a second owner — e.g. a CEO, COO, or CFO who should have exactly the same authority as
the Founder, not a scaled-down version of it. Today, Executive's permissions are **identical to
Founder's, permission for permission** — this was a deliberate decision, not an accident.

Executive has every feature listed above under **Founder** — the same Dashboard, the same company-wide
Attendance and Leave access, the same full Salary Records / Attendance Summary / Expense Claims control,
the same Audit Logs. The only difference between Founder and Executive is the person signing in; the
powers are the same.

**Cannot do:** the exact same list as Founder cannot do — no user account management, no system/org
setup, no Roles & Permissions screen.

---

## Admin

**Who this is:** whoever runs the system day to day — IT support, or the person who sets things up and
keeps them running. Admin deliberately has **zero payroll access** — it can see that salary records
exist, but never the actual numbers, never who got paid what. This is a separation-of-duties choice: the
person who controls the software should not also control the money.

**Dashboard** — the company-wide dashboard, same breadth as Founder, minus any money figures.

**Employees** — full control: create a new employee, edit anyone's details, deactivate someone who's
left, see everyone's full profile.

**Departments & Job Titles** — create and edit departments and job titles (designations).

**Attendance** — company-wide: fix anyone's missed check-out, mark someone present, correct a
recorded day, for anyone in the company.

**All Leave Requests** — sees and can act on every leave request company-wide; can also record a leave
or permission on someone's behalf.

**Leave Types** — defines the kinds of leave the company offers (Casual, Sick, Unpaid, etc.) and how
many days each gives per year.

**Holidays** — manages the company holiday calendar.

**Document Types** — defines what kinds of documents employees can upload (ID proof, certificates, etc.)
and whether each one needs an expiry date tracked.

**Company Tasks** — sees and creates company-wide tasks.

**Audit Logs** — the full history of every action taken in the system.

**User Accounts** — the one screen only Admin has: **reset anyone's password, change anyone's Login
Role, change anyone's login email** — including Founder, Executive, and Accountant logins. (This was a
deliberate choice made this year: Admin is trusted to manage every login, even though it still can't see
any payroll data itself.)

**Roles & Permissions** — the other Admin-only screen: a live, editable grid showing exactly which of
the 29 permissions each of the 7 roles has, with the ability to grant or remove one directly. Two
safety rules are built in: Admin can only hand out a permission it already holds itself (so it still
can never grant itself or anyone else payroll access this way), and the very last role holding the
"manage roles" permission itself can never be stripped of it, so nobody can accidentally lock everyone
out of this screen for good.

**Cannot do:** anything involving money — cannot open Salary Records, cannot run payroll, cannot see a
single payslip number, cannot approve an expense claim.

---

## HR

**Who this is:** Human Resources staff. HR has almost everything Admin has for *people and
organization*, but — unlike Admin — cannot manage user accounts or touch the Roles & Permissions screen.

**Dashboard** — the company-wide dashboard, same as Admin.

**Employees** — full control: create, edit, deactivate employees, see everyone's full profile.

**Departments & Job Titles** — create and edit these.

**Attendance** — company-wide: fix missed check-outs, mark present, correct a recorded day, for
anyone. Has their own "My Attendance" too.

**Approve Leave** — sees and acts on every leave request company-wide (the tab is labeled "Approve
Leave" instead of "All Leave Requests" since that's HR's main day-to-day job here); can record a leave
or permission for someone who phoned in.

**Leave Types** — defines the company's leave categories.

**Holidays** — manages the holiday calendar.

**Document Types** — defines what kinds of documents can be uploaded.

**Company Tasks** — sees and creates company-wide tasks.

**Audit Logs** — the full action history.

**My Documents, My Expenses, My Payslips, My Leave** — their own personal self-service items, same as
any employee.

**Cannot do:** nothing involving money (no Salary Records, no payroll, no expense approval), and —
unlike Admin — cannot reset anyone's password, change anyone's Login Role, or open the Roles &
Permissions screen. HR manages *people's records*; Admin manages *logins*.

---

## Accountant

**Who this is:** payroll and finance staff. Accountant is the mirror image of HR: full control over
money, almost nothing else. It doesn't even get a general "Employees" list — its entire view of a
person is through their salary and expenses.

**Dashboard** — their own, personal dashboard (not the company-wide one — Accountant doesn't have the
`report:view` permission that widens it).

**Salary Records** — sets anyone's salary structure (basic pay, allowances, deductions).

**Attendance Summary** — sees the same day-count numbers (present/absent/leave/payable days) that
payroll is calculated from, for everyone — this is how Accountant checks a payroll run is correct
*without* needing general attendance-management access.

**Run payroll / Salary Payments** — runs the month's payroll, marks each payment as paid, downloads any
employee's payslip.

**Expense Claims** — approves, rejects, or marks an expense claim as paid (except their own).

**My Attendance, My Leave, My Tasks, My Documents, My Expenses, My Payslips** — their own personal
self-service items.

**Cannot do:** see the general Employees list, edit anyone's profile, touch attendance correction tools,
approve leave for anyone, or see Audit Logs. Accountant's world is money, not people-management.

---

## Manager

**Who this is:** anyone who has people reporting to them — this isn't a fixed list of people, it's
automatic. The moment someone is set as another employee's manager (via the "Reports to" field on their
profile), that person gets Manager-level authority **over their own direct reports only** — determined
by the real reporting line, not by any extra setup.

**Dashboard** — their own personal dashboard (not company-wide).

**My Team** — the Employees screen, but labeled "My Team." Same company-wide list everyone with
`employee:read` sees, but opening someone's *full* profile (phone, date of birth) is only allowed for
themselves or someone who reports to them directly — a stranger's private details stay private.

**My Attendance / Team Attendance** — checks themselves in/out, and separately can fix a missed
check-out, mark present, or correct a day — but **only for their own direct reports**, never for anyone
outside their team.

**Leave Requests** — approves or rejects leave requests from their own direct reports only.

**My Leave** — applies for their own time off.

**My Tasks / Team Tasks** — creates and assigns tasks to their own team; sees their own assigned tasks.

**My Documents, My Expenses, My Payslips** — their own personal items.

**Cannot do:** see anyone's attendance/leave/tasks outside their own reporting line, see or manage any
payroll information, manage departments/job titles/leave types/holidays, or see Audit Logs.

---

## Employee

**Who this is:** everyone else — the default role, and the baseline every other role builds on.

**Dashboard** — their own personal dashboard: today's attendance, their own leave balance, their own
tasks.

**My Profile** — their own details.

**My Attendance** — checks themselves in and out each day; sees their own attendance history and
calendar.

**My Leave** — applies for leave or views their leave balance and history. (Cannot record their own
phone-in absence after the fact — that has to be entered by their manager or HR, since the system is
used from inside the office.)

**My Tasks** — sees tasks assigned to them.

**My Documents** — uploads and manages their own documents (ID proof, certificates).

**My Expenses** — submits an expense reimbursement claim.

**My Payslips** — downloads their own payslips once paid.

**Holidays** — sees the company holiday calendar (view only).

**Notifications** — their own notifications.

**Cannot do:** see anyone else's information at all — not even a colleague's attendance or profile.
Everything here is scoped to themselves only.

---

## Rules that apply no matter the role

A few things are true for *everyone*, regardless of Login Role, because they're built into the system
itself rather than tied to any one permission:

- **Nobody can approve their own leave, mark their own expense claim paid, or correct their own
  attendance** — even a Founder. Any action that approves or corrects "yourself" is refused, full stop.
- **Office hours are the same for everyone**: 9:00 AM start (10 minutes' grace), 1:00–1:30 PM lunch
  (automatically deducted from worked hours), checking in after 1:30 PM is a half day.
- **A paid month is locked.** Once payroll has been run and paid for a month, nothing about that month's
  leave or attendance can be changed — corrections move to the next month instead.
- Every sensitive action — a password reset, a role change, a salary set, a leave approval, an
  attendance correction — is written to the **Audit Log**, visible to Founder, Executive, Admin, and HR.
