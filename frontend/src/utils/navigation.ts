import {
  Award,
  Banknote,
  Bell,
  Briefcase,
  Building2,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  CheckSquare,
  ClipboardList,
  Clock,
  House,
  FileCog,
  KeyRound,
  FileText,
  LayoutDashboard,
  ListChecks,
  Receipt,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "@/types";

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
}

const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  // ADMIN runs the system: people records, accounts, org setup, audit. It has
  // no employee profile of its own and no payroll access - the owner's own
  // work lives under FOUNDER below. Nor does it get a Notifications tab: every
  // notification the app sends is addressed to a person with an employee profile.
  ADMIN: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Employees", path: "/employees", icon: Users },
    { label: "Departments", path: "/departments", icon: Building2 },
    { label: "Job Titles", path: "/designations", icon: Briefcase },
    { label: "Attendance", path: "/attendance", icon: Clock },
    { label: "All Leave Requests", path: "/leave/requests", icon: CalendarDays },
    { label: "Leave Types", path: "/leave/types", icon: CalendarRange },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "Document Types", path: "/documents/types", icon: FileCog },
    { label: "Company Tasks", path: "/tasks", icon: ListChecks },
    { label: "Audit Logs", path: "/audit-logs", icon: ScrollText },
    { label: "User Accounts", path: "/user-accounts", icon: ShieldCheck },
    { label: "Roles & Permissions", path: "/roles-permissions", icon: KeyRound },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  FOUNDER: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Employees", path: "/employees", icon: Users },
    { label: "Attendance", path: "/attendance", icon: Clock },
    { label: "My Attendance", path: "/attendance/my", icon: CalendarRange },
    { label: "Leave Requests", path: "/leave/requests", icon: CalendarDays },
    { label: "My Leave", path: "/leave/my", icon: CalendarPlus },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "Company Tasks", path: "/tasks", icon: ListChecks },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "Salary Records", path: "/payroll", icon: Banknote },
    { label: "Attendance Summary", path: "/payroll/attendance", icon: CalendarRange },
    { label: "Expense Claims", path: "/expenses", icon: Receipt },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Audit Logs", path: "/audit-logs", icon: ScrollText },
    { label: "Profile", path: "/profile", icon: ClipboardList },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  HR: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Employees", path: "/employees", icon: Users },
    { label: "Departments", path: "/departments", icon: Building2 },
    { label: "Job Titles", path: "/designations", icon: Briefcase },
    { label: "Attendance", path: "/attendance", icon: Clock },
    { label: "My Attendance", path: "/attendance/my", icon: CalendarRange },
    { label: "Approve Leave", path: "/leave/requests", icon: CalendarDays },
    { label: "My Leave", path: "/leave/my", icon: CalendarPlus },
    { label: "Leave Types", path: "/leave/types", icon: CalendarRange },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "Company Tasks", path: "/tasks", icon: ListChecks },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "Document Types", path: "/documents/types", icon: FileCog },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Audit Logs", path: "/audit-logs", icon: ScrollText },
    { label: "Profile", path: "/profile", icon: ClipboardList },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  ACCOUNTANT: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Salary Records", path: "/payroll", icon: Banknote },
    { label: "Attendance Summary", path: "/payroll/attendance", icon: CalendarRange },
    { label: "Expense Claims", path: "/expenses", icon: Receipt },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "My Attendance", path: "/attendance/my", icon: Clock },
    { label: "My Leave", path: "/leave/my", icon: CalendarPlus },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Profile", path: "/profile", icon: ClipboardList },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  // EXECUTIVE has full FOUNDER parity in permissions (see migration b5f545e1a157) - this list is kept
  // identical to FOUNDER's above for that reason, not a separate editorial choice.
  EXECUTIVE: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Employees", path: "/employees", icon: Users },
    { label: "Attendance", path: "/attendance", icon: Clock },
    { label: "My Attendance", path: "/attendance/my", icon: CalendarRange },
    { label: "Leave Requests", path: "/leave/requests", icon: CalendarDays },
    { label: "My Leave", path: "/leave/my", icon: CalendarPlus },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "Company Tasks", path: "/tasks", icon: ListChecks },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "Salary Records", path: "/payroll", icon: Banknote },
    { label: "Attendance Summary", path: "/payroll/attendance", icon: CalendarRange },
    { label: "Expense Claims", path: "/expenses", icon: Receipt },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Audit Logs", path: "/audit-logs", icon: ScrollText },
    { label: "Profile", path: "/profile", icon: ClipboardList },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  MANAGER: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "My Team", path: "/employees", icon: Users },
    { label: "My Attendance", path: "/attendance/my", icon: Clock },
    { label: "Team Attendance", path: "/attendance", icon: CalendarRange },
    { label: "Leave Requests", path: "/leave/requests", icon: CalendarDays },
    { label: "My Leave", path: "/leave/my", icon: CalendarPlus },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "Team Tasks", path: "/tasks", icon: ListChecks },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Profile", path: "/profile", icon: ClipboardList },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
  EMPLOYEE: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "My Profile", path: "/profile", icon: ClipboardList },
    { label: "My Attendance", path: "/attendance/my", icon: Clock },
    { label: "My Leave", path: "/leave/my", icon: CalendarDays },
    { label: "My Tasks", path: "/tasks/my", icon: CheckSquare },
    { label: "My Documents", path: "/documents", icon: FileText },
    { label: "My Expenses", path: "/expenses/my", icon: Receipt },
    { label: "My Payslips", path: "/salary/my", icon: Banknote },
    { label: "Holidays", path: "/holidays", icon: Award },
    { label: "Notifications", path: "/notifications", icon: Bell },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
};

export function getNavItems(role: Role): NavItem[] {
  return NAV_BY_ROLE[role];
}

// The few things an employee reaches for every day, as a bar at the bottom of
// a phone screen (where a thumb can reach it). Everything else lives under
// "More". Only employees get this bar for now - other roles keep the menu.
const BOTTOM_NAV_BY_ROLE: Partial<Record<Role, NavItem[]>> = {
  EMPLOYEE: [
    { label: "Home", path: "/dashboard", icon: House },
    { label: "Attendance", path: "/attendance/my", icon: Clock },
    { label: "Leave", path: "/leave/my", icon: CalendarDays },
    { label: "Tasks", path: "/tasks/my", icon: CheckSquare },
  ],
};

export function getBottomNavItems(role: Role): NavItem[] | null {
  return BOTTOM_NAV_BY_ROLE[role] ?? null;
}
