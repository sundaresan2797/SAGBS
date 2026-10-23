import {
  CalendarClock,
  CalendarOff,
  CheckSquare,
  UserCheck,
  UserPlus,
  Users,
  UserX,
  Hourglass,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DocumentsToRenew } from "@/components/DocumentsToRenew";
import { PayrollGlance } from "@/components/PayrollGlance";
import { WaitingForYou } from "@/components/WaitingForYou";
import { Card, StatCard } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { getErrorMessage } from "@/services/api";
import { dashboardService } from "@/services/dashboardService";
import { employeeService } from "@/services/employeeService";
import type { AttendanceTrendPoint, DashboardSummary, DepartmentHeadcount, LeaveTrendPoint } from "@/types";

import { PersonalDashboard } from "./PersonalDashboard";

// What the company-wide dashboard says under the greeting, by login. Admin
// runs the system; Founder/Executive look at how the business is doing.
const COMPANY_SUBTITLES: Record<string, string> = {
  FOUNDER: "Here's how your company is doing today.",
  ADMIN: "Here's an overview of the system and the team.",
  HR: "Here's how the team is doing today.",
  EXECUTIVE: "Here's how the company is doing today.",
};

const ROLE_NAMES: Record<string, string> = {
  FOUNDER: "Founder",
  ADMIN: "Admin",
  HR: "HR",
  EXECUTIVE: "Executive",
};

const CHART_COLORS = { primary: "#149c88", secondary: "#94ecd9", danger: "#f45d1f" };

export function DashboardPage() {
  const { hasPermission } = useAuth();

  if (!hasPermission("report:view")) {
    return <PersonalDashboard />;
  }

  return <HrDashboard />;
}

const ATTENDANCE_RANGES = [
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

function HrDashboard() {
  const { user, hasPermission } = useAuth();
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [attendanceTrend, setAttendanceTrend] = useState<AttendanceTrendPoint[]>([]);
  const [attendanceDays, setAttendanceDays] = useState(14);
  const [isTrendLoading, setIsTrendLoading] = useState(false);
  const [leaveTrend, setLeaveTrend] = useState<LeaveTrendPoint[]>([]);
  const [departments, setDepartments] = useState<DepartmentHeadcount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [summaryData, attendanceData, leaveData, departmentData] = await Promise.all([
        dashboardService.summary(),
        dashboardService.attendanceTrend(attendanceDays),
        dashboardService.leaveTrend(6),
        dashboardService.departments(),
      ]);
      setSummary(summaryData);
      setAttendanceTrend(attendanceData);
      setLeaveTrend(leaveData);
      setDepartments(departmentData);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load the dashboard."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // Fetched separately so a login with no employee profile (the system
    // Admin) falls back to its role name instead of failing the whole page.
    if (user?.employee_id) {
      employeeService
        .getMe()
        .then((employee) => setDisplayName(employee.full_name))
        .catch(() => setDisplayName(ROLE_NAMES[user?.role ?? ""] ?? null));
    } else {
      // No employee profile to ask for, so don't make a request that can only fail.
      setDisplayName(ROLE_NAMES[user?.role ?? ""] ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRangeChange = async (days: number) => {
    setAttendanceDays(days);
    setIsTrendLoading(true);
    try {
      setAttendanceTrend(await dashboardService.attendanceTrend(days));
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load the attendance trend."));
    } finally {
      setIsTrendLoading(false);
    }
  };

  if (isLoading) return <LoadingState label="Loading your dashboard..." />;
  if (error || !summary) return <ErrorState message={error ?? "No data available."} onRetry={load} />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-stone-800">
          Welcome back{displayName ? `, ${displayName}` : ""} 👋
        </h1>
        <p className="text-sm text-stone-500">
          {COMPANY_SUBTITLES[user?.role ?? ""] ?? "Here's how the whole company is doing today."}
        </p>
      </div>

      {hasPermission("payroll:view") && <PayrollGlance />}

      <WaitingForYou />

      {hasPermission("document:manage_all") && <DocumentsToRenew />}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Employees" value={summary.total_employees} icon={<Users className="h-5 w-5" />} />
        <StatCard
          label="Active Employees"
          value={summary.active_employees}
          icon={<UserCheck className="h-5 w-5" />}
        />
        <StatCard
          label="On Leave"
          value={summary.employees_on_leave}
          icon={<CalendarOff className="h-5 w-5" />}
          tone="sunset"
        />
        <StatCard
          label="New Joiners (Month)"
          value={summary.new_joiners_this_month}
          icon={<UserPlus className="h-5 w-5" />}
        />
        <StatCard
          label="Present Today"
          value={summary.present_today}
          icon={<UserCheck className="h-5 w-5" />}
        />
        <StatCard
          label="Absent Today"
          value={summary.absent_today}
          icon={<UserX className="h-5 w-5" />}
          tone="sunset"
        />
        <StatCard
          label="Pending Leave"
          value={summary.pending_leave_requests}
          icon={<Hourglass className="h-5 w-5" />}
          tone="sunset"
        />
        {/* Links straight to /tasks, which for a report:view holder like this one shows the exact same
            company-wide count (task_service.list_team_tasks widens scope on that same permission) -
            so this card and the page it opens can never disagree. */}
        <Link to="/tasks" className="block rounded-2xl transition-shadow hover:shadow-md">
          <StatCard
            label="Open Tasks (company-wide)"
            value={summary.pending_tasks}
            hint={summary.overdue_tasks > 0 ? `${summary.overdue_tasks} overdue · view all →` : "None overdue · view all →"}
            icon={<CheckSquare className="h-5 w-5" />}
            tone={summary.overdue_tasks > 0 ? "sunset" : "brand"}
          />
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-brand-600" aria-hidden="true" />
              <h2 className="font-display text-sm font-semibold text-stone-700">
                Attendance, last {attendanceDays} days
              </h2>
            </div>
            <div className="flex gap-1 rounded-lg bg-sand-100 p-1">
              {ATTENDANCE_RANGES.map((range) => (
                <button
                  key={range.days}
                  onClick={() => handleRangeChange(range.days)}
                  disabled={isTrendLoading}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                    attendanceDays === range.days
                      ? "bg-white text-brand-700 shadow-sm"
                      : "text-stone-500 hover:text-stone-700"
                  }`}
                >
                  {range.label}
                </button>
              ))}
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={attendanceTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3efe8" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: "#9c8968" }}
                  tickFormatter={(d: string) => d.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 11, fill: "#9c8968" }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="present" fill={CHART_COLORS.primary} radius={[4, 4, 0, 0]} />
                <Bar dataKey="on_leave" fill={CHART_COLORS.secondary} radius={[4, 4, 0, 0]} />
                <Bar dataKey="absent" fill={CHART_COLORS.danger} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-2">
            <CalendarOff className="h-4 w-4 text-brand-600" aria-hidden="true" />
            <h2 className="font-display text-sm font-semibold text-stone-700">Leave, last 6 months</h2>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={leaveTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3efe8" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9c8968" }} />
                <YAxis tick={{ fontSize: 11, fill: "#9c8968" }} allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="approved" stroke={CHART_COLORS.primary} strokeWidth={2.5} />
                <Line type="monotone" dataKey="pending" stroke={CHART_COLORS.secondary} strokeWidth={2.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <Users className="h-4 w-4 text-brand-600" aria-hidden="true" />
            <h2 className="font-display text-sm font-semibold text-stone-700">Team size by department</h2>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={departments} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f3efe8" />
                <XAxis type="number" tick={{ fontSize: 11, fill: "#9c8968" }} allowDecimals={false} />
                <YAxis dataKey="department_name" type="category" width={120} tick={{ fontSize: 11, fill: "#9c8968" }} />
                <Tooltip />
                <Bar dataKey="employee_count" fill={CHART_COLORS.primary} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
