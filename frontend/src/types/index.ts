export type Role = "ADMIN" | "FOUNDER" | "HR" | "EXECUTIVE" | "ACCOUNTANT" | "MANAGER" | "EMPLOYEE";

export interface User {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  employee_id: number | null;
  permissions: string[];
}

export interface PaginatedData<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiSuccess<T> {
  success: true;
  message: string;
  data: T;
}

export interface ApiError {
  success: false;
  message: string;
  error_code: string;
}

export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACT" | "INTERN";
export type EmployeeStatus = "ACTIVE" | "ON_LEAVE" | "RESIGNED" | "TERMINATED" | "INACTIVE";
export type AttendanceStatus = "PRESENT" | "ABSENT" | "LATE" | "HALF_DAY" | "ON_LEAVE" | "HOLIDAY";
export type LeaveRequestStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type TaskStatus = "TODO" | "IN_PROGRESS" | "COMPLETED" | "BLOCKED";

export interface Department {
  id: number;
  name: string;
  description: string | null;
  status: "ACTIVE" | "INACTIVE";
  employee_count: number;
  designation_count: number;
}

export interface Designation {
  id: number;
  name: string;
  description: string | null;
  department_id: number;
  department_name: string;
  status: "ACTIVE" | "INACTIVE";
  employee_count: number;
}

export interface DepartmentBrief {
  id: number;
  name: string;
}

export interface DesignationBrief {
  id: number;
  name: string;
}

export interface ManagerBrief {
  id: number;
  full_name: string;
}

export interface EmployeeListItem {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  department: DepartmentBrief;
  designation: DesignationBrief;
  manager: ManagerBrief | null;
  employment_type: EmploymentType;
  status: EmployeeStatus;
  date_of_joining: string;
  account_role: Role;
  account_active: boolean;
}

/** Who has a profile photo, and which version of it (changes whenever the photo changes). */
export interface PhotoIndexEntry {
  employee_id: number;
  photo_version: string;
}

export interface PhotoResult {
  employee_id: number;
  photo_version: string | null;
}

export interface Employee extends EmployeeListItem {
  phone: string | null;
  date_of_birth: string | null;
  work_location: string | null;
  profile_photo: string | null;
}

export interface LoginRules {
  assignable_roles: string[];
  protected_roles: string[];
}

export interface PermissionDescription {
  code: string;
  description: string;
}

export interface RolePermissions {
  role: string;
  permission_codes: string[];
}

export interface PermissionsMatrix {
  permissions: PermissionDescription[];
  roles: RolePermissions[];
}

export interface EmailChangeResult {
  employee_id: number;
  new_login_email: string;
}

export interface PasswordResetResult {
  login_email: string;
  temporary_password: string;
}

export interface EmployeeCreatedResponse {
  employee: Employee;
  temporary_password: string;
  login_email: string;
}

export interface Attendance {
  id: number;
  employee_id: number;
  attendance_date: string;
  check_in: string | null;
  check_out: string | null;
  working_minutes: number | null;
  late_minutes: number;
  overtime_minutes: number;
  status: AttendanceStatus;
  /** Set when a manager/HR fixed a missed check-out afterwards. */
  corrected_by_name?: string | null;
  corrected_at?: string | null;
  correction_reason?: string | null;
}

/** A record in a manager's/HR's list (it says whose it is). */
export interface AttendanceWithEmployee extends Attendance {
  employee_name: string;
  employee_code: string;
}

/** `total` can exceed `items.length` - the list is capped server-side; the screen says so when it happens. */
export interface MissedCheckOuts {
  items: AttendanceWithEmployee[];
  total: number;
}

export interface OvertimeSummaryEntry {
  employee_id: number;
  employee_code: string;
  employee_name: string;
  overtime_minutes: number;
}

/** The company's attendance rules. Times are "HH:MM" (24-hour) in the company timezone. */
export interface AttendancePolicy {
  office_start: string;
  grace_minutes: number;
  late_after: string;
  full_day_minimum_minutes: number;
  half_day_after: string;
  standard_shift_minutes: number;
  /** A day longer than this is flagged "please check". */
  long_day_minutes: number;
  /** The company's lunch break ("13:00"), deducted automatically from whatever part of it falls inside a
   * check-in to check-out span - nobody punches out for lunch. */
  lunch_start: string;
  lunch_break_minutes: number;
}

export type RollCallStatus = "PRESENT" | "LATE" | "HALF_DAY" | "ABSENT" | "ON_LEAVE" | "HOLIDAY" | "NOT_CHECKED_IN";

export interface RollCallEntry {
  employee_id: number;
  employee_code: string;
  employee_name: string;
  department: string;
  designation: string;
  status: RollCallStatus;
  check_in: string | null;
  check_out: string | null;
  late_minutes: number;
  working_minutes: number | null;
  overtime_minutes: number;
  /** A past day with a check-in but no check-out. */
  missed_check_out: boolean;
  /** Minutes of approved permission (a few hours off) recorded for this person on this day. */
  permission_minutes: number;
  /** They have a half-day leave on this day and work the other half. */
  half_day_leave: boolean;
}

export interface RollCall {
  date: string;
  day_off_reason: string | null;
  summary: Partial<Record<RollCallStatus, number>>;
  departments: { id: number; name: string }[];
  items: RollCallEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type LeaveAccrualFrequency = "ANNUAL" | "MONTHLY";

export interface LeaveType {
  id: number;
  code: string;
  name: string;
  is_paid: boolean;
  default_annual_days: number;
  accrual_frequency: LeaveAccrualFrequency;
  is_active: boolean;
}

export interface LeaveBalance {
  leave_type_id: number;
  leave_type_name: string;
  leave_type_code: string;
  accrual_frequency: LeaveAccrualFrequency;
  year: number;
  allocated_days: number;
  used_days: number;
  remaining_days: number;
}

export type LeaveDayPart = "FIRST_HALF" | "SECOND_HALF";

export interface ShortPermission {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  permission_date: string;
  minutes: number;
  reason: string;
  recorded_by_name: string;
  recorded_late: boolean;
  created_at: string;
}

export interface PermissionList {
  items: ShortPermission[];
  used_this_month: number;
  monthly_limit: number;
  max_minutes: number;
}

export interface LeaveRequest {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  leave_type_id: number;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  number_of_days: number;
  reason: string | null;
  status: LeaveRequestStatus;
  approved_by: number | null;
  approved_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  manager_name: string | null;
  /** Set for a half-day leave: the first or second half of the day. */
  day_part: LeaveDayPart | null;
  /** Set when a manager/HR entered this leave for the employee. `recorded_late` = for a day already past. */
  recorded_by_name: string | null;
  recorded_late: boolean;
}

export interface Holiday {
  id: number;
  name: string;
  holiday_date: string;
  description: string | null;
  is_optional: boolean;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  assigned_to: number;
  assignee_name: string;
  assigned_by: number;
  assigner_name: string;
  priority: TaskPriority;
  status: TaskStatus;
  due_date: string | null;
  created_at: string;
}

export interface TaskComment {
  id: number;
  author_id: number;
  author_name: string;
  comment: string;
  created_at: string;
}

/** The real upload rules the server enforces - fetched, not hardcoded, so the upload screen can
 * never state a limit or file type the server doesn't actually accept. */
export interface DocumentUploadPolicy {
  max_upload_mb: number;
  allowed_extensions: string[];
}

export interface DocumentTypeOption {
  id: number;
  code: string;
  name: string;
  description: string | null;
  requires_expiry: boolean;
  is_active: boolean;
  document_count?: number; // only on the management list
}

export interface ExpiringDocument {
  document_id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  document_type_name: string;
  file_name: string;
  expiry_date: string;
  days_left: number;
}

export interface ExpiringDocuments {
  items: ExpiringDocument[];
  total: number;
}

export interface EmployeeDocument {
  id: number;
  employee_id: number;
  document_type_id: number;
  document_type: string;
  document_type_name: string;
  file_name: string;
  file_size: number;
  mime_type: string;
  expiry_date: string | null;
  uploaded_by: number | null;
  created_at: string;
}

export interface Notification {
  id: number;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  user_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  description: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface DashboardSummary {
  total_employees: number;
  active_employees: number;
  employees_on_leave: number;
  new_joiners_this_month: number;
  present_today: number;
  absent_today: number;
  pending_leave_requests: number;
  pending_tasks: number;
  overdue_tasks: number;
}

export interface AttendanceTrendPoint {
  date: string;
  present: number;
  absent: number;
  late: number;
  on_leave: number;
}

export interface LeaveTrendPoint {
  month: string;
  approved: number;
  pending: number;
  rejected: number;
}

export interface DepartmentHeadcount {
  department_id: number;
  department_name: string;
  employee_count: number;
}

// --- Payroll module ---

export type ExpenseClaimCategory = "TRAVEL" | "FOOD" | "MATERIALS" | "ACCOMMODATION" | "OTHER";
export type ExpenseClaimStatus = "PENDING" | "APPROVED" | "REJECTED" | "PAID";
export type SalaryPaymentStatus = "PENDING" | "PAID";

export interface PayrollDirectoryEntry {
  id: number;
  employee_code: string;
  full_name: string;
  role: string;
  department: string;
  designation: string;
}

export interface SalaryRecord {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  basic_pay: number;
  allowances: number;
  deductions: number;
  net_pay: number;
  effective_from: string;
}

export interface UnpaidEarlier {
  count: number;
  total_amount: number;
}

export interface SalaryPayment {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  year: number;
  month: number;
  amount: number;
  status: SalaryPaymentStatus;
  paid_date: string | null;
  /** The attendance breakdown behind `amount` - absent for a payment made before pay was attendance-based. */
  total_days: number | null;
  present_days: number | null;
  late_days: number | null;
  half_days: number | null;
  half_leave_days: number | null;
  paid_leave_days: number | null;
  unpaid_leave_days: number | null;
  absent_days: number | null;
  days_off_days: number | null;
  payable_days: number | null;
  cut_days: number | null;
}

export interface ExpenseClaim {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code: string;
  category: ExpenseClaimCategory;
  amount: number;
  description: string | null;
  status: ExpenseClaimStatus;
  rejection_reason: string | null;
  paid_date: string | null;
  created_at: string;
}

/** One person's month in paid and cut days (view only - it does not change pay yet). */
export interface AttendanceSummaryRow {
  employee_id: number;
  employee_code: string;
  employee_name: string;
  total_days: number;
  /** Of those, the days this person is expected to work (no Sundays, holidays, or days before joining). */
  working_days: number;
  present: number;
  late: number;
  half_day: number;
  half_leave: number;
  paid_leave: number;
  unpaid_leave: number;
  absent: number;
  days_off: number;
  before_joining: number;
  open_days: number;
  payable_days: number;
  cut_days: number;
  /** The full monthly take-home (from that month's payslip if payroll already ran). */
  monthly_salary: number;
  /** Pay by attendance; null until the month has ended. */
  pay_for_month: number | null;
  payslip_id: number | null;
  payslip_amount: number | null;
  payslip_status: "PENDING" | "PAID" | null;
  payslip_paid_date: string | null;
  /** Payslip amount minus pay by attendance. */
  difference: number | null;
  missed_check_outs: number;
  pending_leave_requests: number;
}

export interface AttendanceSummary {
  year: number;
  month: number;
  total_days: number;
  month_ended: boolean;
  items: AttendanceSummaryRow[];
  checklist: {
    missed_check_outs: number;
    pending_leave_requests: number;
    employees_without_salary: number;
    absent_days: number;
    /** Missed check-outs still open in other months, newest first. */
    missed_check_outs_in_other_months: { year: number; month: number; count: number }[];
  };
  total_monthly_salary: number;
  total_pay: number | null;
  total_on_payslips: number | null;
  total_difference: number | null;
}
