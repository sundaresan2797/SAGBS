from app.models.enums import RoleName

# Permission codes used across the API for fine-grained authorization checks.
PERMISSIONS: list[tuple[str, str]] = [
    ("employee:read", "View employees"),
    ("employee:create", "Create employees"),
    ("employee:update", "Edit employees"),
    ("employee:deactivate", "Deactivate/activate employees"),
    ("department:manage", "Manage departments"),
    ("designation:manage", "Manage designations"),
    ("attendance:read_own", "View own attendance"),
    ("attendance:read_team", "View team attendance"),
    ("attendance:read_all", "View all attendance"),
    ("attendance:mark", "Check in / check out"),
    ("leave:apply", "Apply for leave"),
    ("leave:approve_team", "Approve/reject team leave"),
    ("leave:manage_all", "Manage all leave requests"),
    ("leave_type:manage", "Manage leave types (create/edit accrual rules)"),
    ("document_type:manage", "Manage document types (the kinds of document employees can upload)"),
    ("holiday:manage", "Manage holiday calendar"),
    ("task:create", "Create and assign tasks"),
    ("task:read_own", "View own assigned tasks"),
    ("task:read_team", "View team tasks"),
    ("document:manage_own", "View/upload own documents"),
    ("document:manage_all", "Manage all employee documents"),
    ("notification:read", "View notifications"),
    ("report:view", "View reports"),
    ("audit:view", "View audit logs"),
    ("user:manage", "Manage user accounts"),
    ("role:manage", "Manage roles and permissions"),
    ("expense:submit", "Submit personal expense reimbursement claims"),
    ("payroll:view", "View salary records, payroll runs and expense claims"),
    ("payroll:manage", "Set salaries, run payroll, mark salaries paid, and review expense claims"),
]

# Which permission codes each role receives at seed time.
ROLE_PERMISSIONS: dict[RoleName, list[str]] = {
    # ADMIN runs the system (people records, accounts, org setup, audit) but
    # deliberately has no payroll access: salary is confidential, and the
    # owner-level override over it belongs to FOUNDER (plus ACCOUNTANT).
    RoleName.ADMIN: [code for code, _ in PERMISSIONS if not code.startswith("payroll:")],
    # FOUNDER is the business owner: sees the whole company, decides on money
    # (payroll, expense claims) and approves for their direct reports, but
    # does not administer the system (no user accounts, org setup, or
    # employee create/edit - those stay with ADMIN/HR).
    RoleName.FOUNDER: [
        "employee:read",
        "attendance:read_own",
        "attendance:read_team",
        "attendance:read_all",
        "attendance:mark",
        "leave:apply",
        "leave:approve_team",
        "leave:manage_all",
        "task:create",
        "task:read_own",
        "task:read_team",
        "document:manage_own",
        "document:manage_all",
        "notification:read",
        "report:view",
        "audit:view",
        "expense:submit",
        "payroll:view",
        "payroll:manage",
    ],
    RoleName.HR: [
        "employee:read",
        "employee:create",
        "employee:update",
        "employee:deactivate",
        "department:manage",
        "designation:manage",
        "attendance:read_all",
        "attendance:mark",
        "leave:apply",
        "leave:approve_team",  # some HR staff genuinely are someone's manager_id - get_team_leave_requests
        # already scopes by that chain regardless of role, and shows nothing for HR logins with no reports
        "leave:manage_all",
        "leave_type:manage",
        "document_type:manage",
        "holiday:manage",
        "task:create",  # some HR staff genuinely are someone's manager_id (e.g. an HR Head with HR
        # staff reporting to them) - create_task's manager_id check already restricts this to real
        # direct reports regardless of role, same shape as leave:approve_team above
        "task:read_own",
        "task:read_team",  # widened company-wide by report:view in list_team_tasks; also covers HR
        # staff who do have real direct reports via the manager_id chain, same as everyone else
        "document:manage_own",
        "document:manage_all",
        "notification:read",
        "report:view",
        "audit:view",
        "expense:submit",
    ],
    # ACCOUNTANT owns payroll (salary records, running payroll, payslips,
    # reviewing expense claims) plus the same self-service basics every
    # employee has. It does NOT get employee:read/HR-style permissions - an
    # accountant manages money, not people or system configuration.
    RoleName.ACCOUNTANT: [
        "attendance:read_own",
        "attendance:mark",
        "leave:apply",
        "task:read_own",
        "document:manage_own",
        "notification:read",
        "expense:submit",
        "payroll:view",
        "payroll:manage",
    ],
    # EXECUTIVE is for company leadership that should have the exact same powers as FOUNDER (e.g. a second
    # owner/co-founder, not just a department head) - deliberately identical to FOUNDER's list below. It
    # still excludes every system-config permission (department/designation/leave_type/holiday management,
    # user:manage, role:manage) - those stay HR/ADMIN-only so a business role can't also administer the
    # system.
    RoleName.EXECUTIVE: [
        "employee:read",
        "attendance:read_own",
        "attendance:read_team",
        "attendance:read_all",
        "attendance:mark",
        "leave:apply",
        "leave:approve_team",
        "leave:manage_all",
        "task:create",
        "task:read_own",
        "task:read_team",
        "document:manage_own",
        "document:manage_all",
        "notification:read",
        "report:view",
        "audit:view",
        "expense:submit",
        "payroll:view",
        "payroll:manage",
    ],
    RoleName.MANAGER: [
        "employee:read",
        "attendance:read_own",
        "attendance:read_team",
        "attendance:mark",
        "leave:apply",
        "leave:approve_team",
        "task:create",
        "task:read_own",
        "task:read_team",
        "document:manage_own",
        "notification:read",
        "expense:submit",
    ],
    RoleName.EMPLOYEE: [
        "attendance:read_own",
        "attendance:mark",
        "leave:apply",
        "task:read_own",
        "document:manage_own",
        "notification:read",
        "expense:submit",
    ],
}
