import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  Bell,
  CheckCircle2,
  CheckSquare,
  Download,
  FileWarning,
  Hourglass,
  PartyPopper,
  Receipt,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { buildDayContext } from "@/components/MonthCalendar";
import { MissedCheckOutNotice } from "@/components/MissedCheckOutNotice";
import { PayrollGlance } from "@/components/PayrollGlance";
import { WaitingForYou } from "@/components/WaitingForYou";
import { TodayAttendanceCard } from "@/components/TodayAttendanceCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAttendanceMonth } from "@/hooks/useAttendanceMonth";
import { useAuth } from "@/hooks/useAuth";
import { usePayslipDownload } from "@/hooks/usePayslipDownload";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { documentService } from "@/services/documentService";
import { employeeService } from "@/services/employeeService";
import { holidayService } from "@/services/holidayService";
import { leaveService } from "@/services/leaveService";
import { notificationService } from "@/services/notificationService";
import { payrollService } from "@/services/payrollService";
import { taskService } from "@/services/taskService";
import { classifyDay } from "@/utils/attendanceDays";
import { expiryState } from "@/utils/documentExpiry";
import { daysFromToday, dueLabel, formatDateLong, formatToday, greeting, inDaysLabel, monthName, plural } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { TASK_STATUS_LABEL } from "@/utils/plainWords";
import { isTaskOverdue, toIsoDate } from "@/utils/taskHelpers";
import type { Holiday, LeaveBalance, LeaveRequest, SalaryPayment, Task } from "@/types";

interface Extras {
  balances: LeaveBalance[];
  leaves: LeaveRequest[];
  tasks: Task[];
  unread: number;
  expiredDocs: number;
  expiringDocs: number;
  rejectedClaims: number;
  holidays: Holiday[];
  payments: SalaryPayment[];
  firstName: string | null;
  joiningDate: string | null;
}

const EMPTY: Extras = {
  balances: [], leaves: [], tasks: [], unread: 0, expiredDocs: 0, expiringDocs: 0,
  rejectedClaims: 0, holidays: [], payments: [], firstName: null, joiningDate: null,
};

function AttentionRow({ to, icon, tone, children }: { to: string; icon: ReactNode; tone: "red" | "amber" | "blue"; children: ReactNode }) {
  const tones = { red: "bg-rose-50 text-rose-600", amber: "bg-amber-50 text-amber-600", blue: "bg-sky-50 text-sky-600" };
  return (
    <li>
      <Link to={to} className="flex min-h-[56px] items-center gap-3 rounded-2xl px-2 py-2 hover:bg-sand-50">
        <span className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}>{icon}</span>
        <span className="flex-1 text-base font-semibold text-stone-800">{children}</span>
        <ArrowRight className="h-5 w-5 flex-shrink-0 text-stone-400" aria-hidden="true" />
      </Link>
    </li>
  );
}

export function PersonalDashboard() {
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const employeeId = user?.employee_id;
  const now = new Date();
  const todayIso = toIsoDate(now);
  const { download, downloadingId } = usePayslipDownload();

  const month = useAttendanceMonth(employeeId, now.getFullYear(), now.getMonth() + 1);
  const [extras, setExtras] = useState<Extras>(EMPTY);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isMarking, setIsMarking] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    // Each piece loads on its own: one slow or failing section must never blank the whole home screen.
    // Leave requests, tasks and expense claims are fetched in full (fetchAllPages), not just their
    // first page: the server returns each newest-first, so a single capped page would silently drop
    // the OLDEST - i.e. most overdue, most neglected - items from these counts once someone has enough
    // history to exceed one page.
    const results = await Promise.allSettled([
      leaveService.myBalance(),
      fetchAllPages((page) => leaveService.myRequests(page, 100)),
      fetchAllPages((page) => taskService.myTasks(undefined, page, 100)),
      notificationService.unreadCount(),
      documentService.list(),
      fetchAllPages((page) => payrollService.myExpenseClaims(page, 100)),
      holidayService.list(),
      payrollService.mySalaryPayments(1, 6),
      employeeService.getMe(),
    ]);
    const [balances, leaves, tasks, unread, docs, claims, holidays, payments, me] = results;
    if (results.every((r) => r.status === "rejected")) {
      setError(getErrorMessage((results[0] as PromiseRejectedResult).reason, "Unable to load your home screen."));
      setIsLoading(false);
      return;
    }
    const ok = <T,>(r: PromiseSettledResult<T>): T | undefined => (r.status === "fulfilled" ? r.value : undefined);
    const documents = ok(docs) ?? [];
    setExtras({
      balances: ok(balances) ?? [],
      leaves: ok(leaves) ?? [],
      tasks: ok(tasks) ?? [],
      unread: ok(unread) ?? 0,
      expiredDocs: documents.filter((d) => expiryState(d.expiry_date) === "expired").length,
      expiringDocs: documents.filter((d) => expiryState(d.expiry_date) === "soon").length,
      rejectedClaims: (ok(claims) ?? []).filter((c) => c.status === "REJECTED").length,
      holidays: ok(holidays) ?? [],
      payments: ok(payments)?.items ?? [],
      firstName: ok(me)?.full_name.split(" ")[0] ?? null,
      joiningDate: ok(me)?.date_of_joining ?? null,
    });
    setIsLoading(false);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const todayRecord = month.records.find((r) => r.attendance_date === todayIso) ?? null;
  const todayInfo = classifyDay(todayIso, buildDayContext(month.records, month.holidays, todayIso, extras.leaves, extras.joiningDate));

  const mark = async (action: "in" | "out") => {
    setIsMarking(true);
    try {
      if (action === "in") await attendanceService.checkIn();
      else await attendanceService.checkOut();
      showToast(action === "in" ? "Checked in - have a great day!" : "Checked out - see you tomorrow!", "success");
      month.reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsMarking(false);
    }
  };

  const openTasks = useMemo(
    () =>
      extras.tasks
        .filter((t) => t.status !== "COMPLETED")
        .sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999")),
    [extras.tasks],
  );
  const overdue = openTasks.filter(isTaskOverdue).length;
  // openTasks is sorted by due date, so the first of these is the one due soonest.
  const dueSoonTasks = openTasks.filter((t) => t.due_date && !isTaskOverdue(t) && daysFromToday(t.due_date) <= 3);
  const dueSoon = dueSoonTasks.length;
  const dueSoonDate = dueSoonTasks[0]?.due_date ?? null;
  const pendingLeave = extras.leaves.filter((l) => l.status === "PENDING").length;
  const nextHoliday = extras.holidays.filter((h) => h.holiday_date >= todayIso && !h.is_optional).sort((a, b) => a.holiday_date.localeCompare(b.holiday_date))[0];
  const latestPaid = extras.payments.find((p) => p.status === "PAID");

  if (isLoading) return <LoadingState label="Getting your day ready..." />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const greetingName = extras.firstName ?? user?.email.split("@")[0].split(".")[0];
  const attention: ReactNode[] = [];
  if (overdue > 0) attention.push(<AttentionRow key="overdue" to="/tasks/my" tone="red" icon={<AlertTriangle className="h-5 w-5" />}>{plural(overdue, "task")} running late</AttentionRow>);
  if (dueSoon > 0) attention.push(<AttentionRow key="due" to="/tasks/my" tone="amber" icon={<CheckSquare className="h-5 w-5" />}>{dueSoon === 1 ? `1 task due ${inDaysLabel(dueSoonDate!)}` : `${dueSoon} tasks due soon. The first is due ${inDaysLabel(dueSoonDate!)}`}</AttentionRow>);
  if (pendingLeave > 0) attention.push(<AttentionRow key="leave" to="/leave/my" tone="blue" icon={<Hourglass className="h-5 w-5" />}>{plural(pendingLeave, "leave request")} waiting for approval</AttentionRow>);
  if (extras.expiredDocs > 0) attention.push(<AttentionRow key="expired" to="/documents" tone="red" icon={<FileWarning className="h-5 w-5" />}>{plural(extras.expiredDocs, "document")} expired</AttentionRow>);
  if (extras.expiringDocs > 0) attention.push(<AttentionRow key="expiring" to="/documents" tone="amber" icon={<FileWarning className="h-5 w-5" />}>{plural(extras.expiringDocs, "document")} expiring soon</AttentionRow>);
  if (extras.rejectedClaims > 0) attention.push(<AttentionRow key="claims" to="/expenses/my" tone="amber" icon={<Receipt className="h-5 w-5" />}>{plural(extras.rejectedClaims, "expense claim")} not approved</AttentionRow>);
  if (extras.unread > 0) attention.push(<AttentionRow key="unread" to="/notifications" tone="blue" icon={<Bell className="h-5 w-5" />}>{plural(extras.unread, "new notification")}</AttentionRow>);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-3xl font-bold text-stone-800">
          {greeting()}{greetingName ? `, ${greetingName}` : ""}
        </h1>
        <p className="text-base text-stone-500">{formatToday()}</p>
      </div>

      <MissedCheckOutNotice />

      <TodayAttendanceCard
        record={todayRecord}
        todayInfo={todayInfo}
        isMarking={isMarking}
        onCheckIn={() => mark("in")}
        onCheckOut={() => mark("out")}
      />

      {/* Roles with payroll:view but no company-wide dashboard (the Accountant) still see the money picture. */}
      {hasPermission("payroll:view") && <PayrollGlance />}

      <WaitingForYou />

      <Card>
        <h2 className="mb-2 font-display text-lg font-bold text-stone-800">Needs your attention</h2>
        {attention.length === 0 ? (
          <div className="flex items-center gap-3 py-2">
            <CheckCircle2 className="h-8 w-8 flex-shrink-0 text-success-500" aria-hidden="true" />
            <p className="text-base text-stone-600">You're all caught up. Nothing is waiting for you.</p>
          </div>
        ) : (
          <ul className="flex flex-col">{attention}</ul>
        )}
      </Card>

      {extras.balances.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-lg font-bold text-stone-800">Your leave</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {extras.balances.map((b) => (
              <Link key={b.leave_type_id} to="/leave/my" className="rounded-2xl border border-sand-200 bg-white p-4 shadow-sm hover:border-brand-200">
                <p className="text-base font-semibold text-stone-600">{b.leave_type_name}</p>
                <p className="mt-1 font-display text-3xl font-bold text-stone-800">
                  {b.remaining_days} <span className="text-lg font-semibold text-stone-500">days left</span>
                </p>
                <p className="mt-1 text-base text-stone-500">{b.used_days} used of {b.allocated_days}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Card className="flex items-start gap-4">
          <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-violet-50 text-violet-600">
            <PartyPopper className="h-6 w-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold text-stone-500">Next holiday</p>
            {nextHoliday ? (
              <>
                <p className="font-display text-xl font-bold text-stone-800">{nextHoliday.name}</p>
                <p className="text-base text-stone-600">{formatDateLong(nextHoliday.holiday_date)} · {inDaysLabel(nextHoliday.holiday_date)}</p>
              </>
            ) : (
              <p className="text-base text-stone-600">No more holidays are listed for now.</p>
            )}
            <Link to="/holidays" className="mt-1 inline-flex min-h-[44px] items-center text-base font-semibold text-brand-700 hover:underline">
              See all holidays
            </Link>
          </div>
        </Card>

        <Card className="flex items-start gap-4">
          <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <Banknote className="h-6 w-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold text-stone-500">Latest payslip</p>
            {latestPaid ? (
              <>
                <p className="font-display text-xl font-bold text-stone-800">{monthName(latestPaid.month)} {latestPaid.year}</p>
                <Button
                  variant="secondary"
                  className="mt-2"
                  isLoading={downloadingId === latestPaid.id}
                  onClick={() => download(latestPaid.id)}
                  icon={<Download className="h-5 w-5" />}
                >
                  Download payslip
                </Button>
              </>
            ) : (
              <p className="text-base text-stone-600">Your first payslip will appear here once you've been paid.</p>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h2 className="font-display text-lg font-bold text-stone-800">Your tasks</h2>
          <Link to="/tasks/my" className="inline-flex min-h-[44px] items-center text-base font-semibold text-brand-700 hover:underline">See all</Link>
        </div>
        {openTasks.length === 0 ? (
          <p className="py-2 text-base text-stone-500">Nothing to do right now. Enjoy the calm.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-sand-100">
            {openTasks.slice(0, 4).map((task) => (
              <li key={task.id}>
                <Link to="/tasks/my" className="flex min-h-[64px] flex-col justify-center gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-base font-semibold text-stone-800">{task.title}</span>
                  <span className="flex flex-wrap items-center gap-2">
                    {task.due_date && (
                      <span className={`text-base ${isTaskOverdue(task) ? "font-semibold text-sunset-600" : "text-stone-500"}`}>{dueLabel(task.due_date)}</span>
                    )}
                    <Badge size="lg" status={task.status} label={TASK_STATUS_LABEL[task.status]} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
