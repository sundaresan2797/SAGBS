// The words people actually say for each status, instead of the system's
// ALL_CAPS codes (TODO, IN_PROGRESS, PENDING...). The Badge still gets the
// code so it picks the right colour; only the wording changes.

export const TASK_STATUS_LABEL: Record<string, string> = {
  TODO: "Not started",
  IN_PROGRESS: "In progress",
  COMPLETED: "Done",
  BLOCKED: "Stuck",
};

export const PRIORITY_LABEL: Record<string, string> = {
  LOW: "Low priority",
  MEDIUM: "Medium priority",
  HIGH: "High priority",
  URGENT: "Urgent",
};

export const LEAVE_STATUS_LABEL: Record<string, string> = {
  PENDING: "Waiting for approval",
  APPROVED: "Approved",
  REJECTED: "Not approved",
  CANCELLED: "Cancelled",
};

export const EXPENSE_STATUS_LABEL: Record<string, string> = {
  PENDING: "Waiting for approval",
  APPROVED: "Approved - payment coming",
  REJECTED: "Not approved",
  PAID: "Paid",
};

export const SALARY_STATUS_LABEL: Record<string, string> = {
  PENDING: "Being processed",
  PAID: "Paid",
};

export const EMPLOYMENT_TYPE_LABEL: Record<string, string> = {
  FULL_TIME: "Full time",
  PART_TIME: "Part time",
  CONTRACT: "Contract",
  INTERN: "Intern",
};

export const EXPENSE_CATEGORY_LABEL: Record<string, string> = {
  TRAVEL: "Travel",
  FOOD: "Food",
  MATERIALS: "Materials",
  ACCOMMODATION: "Stay / lodging",
  OTHER: "Other",
};

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Admin",
  HR: "HR",
  FOUNDER: "Founder",
  EXECUTIVE: "Executive",
  ACCOUNTANT: "Accountant",
  MANAGER: "Manager",
  EMPLOYEE: "Employee",
};

// Every AuditAction the backend can log (app/models/enums.py) - the Audit Logs table shows these
// instead of the raw code. Keep this in sync with that enum; an action added there without a
// matching entry here just falls back to showing its own code (see AuditLogsPage), never crashes.
export const AUDIT_ACTION_LABEL: Record<string, string> = {
  LOGIN: "Logged in",
  LOGOUT: "Logged out",
  CREATE_EMPLOYEE: "Added an employee",
  UPDATE_EMPLOYEE: "Edited an employee",
  DEACTIVATE_EMPLOYEE: "Changed an employee's status",
  RESET_USER_PASSWORD: "Reset a password",
  CHANGE_USER_ROLE: "Changed a login's role",
  CREATE_LEAVE: "Applied for leave",
  APPROVE_LEAVE: "Approved leave",
  REJECT_LEAVE: "Rejected leave",
  CANCEL_LEAVE: "Cancelled leave",
  RECORD_LEAVE: "Recorded leave for someone",
  SETUP_SYSTEM: "Set up the system",
  IMPORT_DATA: "Imported employees from a file",
  UPDATE_EMPLOYEE_PHOTO: "Changed a profile photo",
  REMOVE_EMPLOYEE_PHOTO: "Removed a profile photo",
  RECORD_PERMISSION: "Recorded a permission",
  CANCEL_PERMISSION: "Cancelled a permission",
  CHECK_IN: "Checked in",
  CHECK_OUT: "Checked out",
  CORRECT_ATTENDANCE: "Fixed attendance",
  UPLOAD_DOCUMENT: "Uploaded a document",
  DELETE_DOCUMENT: "Deleted a document",
  CREATE_TASK: "Assigned a task",
  UPDATE_TASK: "Updated a task",
  CREATE_DEPARTMENT: "Added a department",
  UPDATE_DEPARTMENT: "Edited a department",
  CREATE_DESIGNATION: "Added a job title",
  UPDATE_DESIGNATION: "Edited a job title",
  CREATE_HOLIDAY: "Added a holiday",
  UPDATE_HOLIDAY: "Edited a holiday",
  DELETE_HOLIDAY: "Deleted a holiday",
  CREATE_LEAVE_TYPE: "Added a leave type",
  UPDATE_LEAVE_TYPE: "Edited a leave type",
  DELETE_LEAVE_TYPE: "Deleted a leave type",
  CREATE_DOCUMENT_TYPE: "Added a document type",
  UPDATE_DOCUMENT_TYPE: "Edited a document type",
  DELETE_DOCUMENT_TYPE: "Deleted a document type",
  CREATE_SALARY_RECORD: "Set a salary",
  UPDATE_SALARY_RECORD: "Changed a salary",
  RUN_PAYROLL: "Ran payroll",
  PAY_SALARY: "Marked a salary as paid",
  CREATE_EXPENSE_CLAIM: "Submitted an expense claim",
  APPROVE_EXPENSE_CLAIM: "Approved an expense claim",
  REJECT_EXPENSE_CLAIM: "Rejected an expense claim",
  PAY_EXPENSE_CLAIM: "Marked an expense claim as paid",
};
