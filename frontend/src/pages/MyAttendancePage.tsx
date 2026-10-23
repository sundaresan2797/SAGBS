import { CalendarClock, ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MissedCheckOutNotice } from "@/components/MissedCheckOutNotice";
import { PageHeader } from "@/components/PageHeader";
import { DayDetail, MonthCalendar, buildDayContext } from "@/components/MonthCalendar";
import { TodayAttendanceCard } from "@/components/TodayAttendanceCard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAttendanceMonth } from "@/hooks/useAttendanceMonth";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { employeeService } from "@/services/employeeService";
import { leaveService } from "@/services/leaveService";
import { classifyDay, DAY_LABELS, DAY_STYLES, isMissedCheckOut, summarizeMonth, type DayKind } from "@/utils/attendanceDays";
import { formatClock, formatDayShort, formatDuration, monthName, parseIsoDate, plural } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { toIsoDate } from "@/utils/taskHelpers";
import type { LeaveRequest } from "@/types";

// "Day by day" starts with the latest week; the rest is one tap away, a week at a time.
const DAYS_PER_PAGE = 7;

export function MyAttendancePage() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const employeeId = user?.employee_id;

  const now = new Date();
  const todayIso = toIsoDate(now);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selected, setSelected] = useState<string | null>(null);
  const [visibleDays, setVisibleDays] = useState(DAYS_PER_PAGE);
  const [isMarking, setIsMarking] = useState(false);
  const [joiningDate, setJoiningDate] = useState<string | null>(null);
  const [leaves, setLeaves] = useState<LeaveRequest[] | undefined>(undefined);

  const viewingCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;
  // Today's card always needs the current month; the viewed month reuses it when they are the same.
  const current = useAttendanceMonth(employeeId, now.getFullYear(), now.getMonth() + 1);
  const other = useAttendanceMonth(viewingCurrentMonth ? null : employeeId, year, month);
  const view = viewingCurrentMonth ? current : other;

  useEffect(() => {
    // These only sharpen the picture (days before joining, approved leave); the page works without them.
    employeeService.getMe().then((e) => setJoiningDate(e.date_of_joining)).catch(() => undefined);
    // The server sends at most 100 at a time; every page is needed so old approved leave still shows as leave.
    fetchAllPages((page) => leaveService.myRequests(page, 100)).then(setLeaves).catch(() => undefined);
  }, []);

  const todayRecord = current.records.find((r) => r.attendance_date === todayIso) ?? null;
  const todayInfo = classifyDay(todayIso, buildDayContext(current.records, current.holidays, todayIso, leaves, joiningDate));

  const dayContext = useMemo(
    () => buildDayContext(view.records, view.holidays, todayIso, leaves, joiningDate),
    [view.records, view.holidays, todayIso, leaves, joiningDate],
  );

  // Every day of the viewed month up to today, classified once.
  const days = useMemo(() => {
    const total = new Date(year, month, 0).getDate();
    return Array.from({ length: total }, (_, i) => {
      const iso = `${year}-${String(month).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
      return { iso, info: classifyDay(iso, dayContext) };
    }).filter((d) => d.iso <= todayIso);
  }, [year, month, dayContext, todayIso]);

  // The month in working days (Sundays and holidays excluded), for the tiles and the headline.
  const summary = useMemo(() => summarizeMonth(year, month, dayContext), [year, month, dayContext]);
  const fmtDays = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
  const overtimeTotal = view.records.reduce((sum, r) => sum + (r.overtime_minutes ?? 0), 0);
  const historyDays = days.filter((d) => !["DAY_OFF", "HOLIDAY", "BEFORE_JOINING", "UPCOMING", "UNKNOWN"].includes(d.info.kind) || d.info.record).reverse();

  const mark = async (action: "in" | "out") => {
    setIsMarking(true);
    try {
      if (action === "in") await attendanceService.checkIn();
      else await attendanceService.checkOut();
      showToast(action === "in" ? "Checked in - have a great day!" : "Checked out - see you tomorrow!", "success");
      current.reload();
      other.reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsMarking(false);
    }
  };

  const goMonth = (delta: number) => {
    let m = month + delta;
    let y = year;
    if (m < 1) { m = 12; y -= 1; } else if (m > 12) { m = 1; y += 1; }
    setMonth(m);
    setYear(y);
    setSelected(null);
    setVisibleDays(DAYS_PER_PAGE);
  };

  // Jump straight to any month (the Month and Year drop-downs); same resets as stepping a month.
  const jumpTo = (y: number, m: number) => {
    setYear(y);
    setMonth(m);
    setSelected(null);
    setVisibleDays(DAYS_PER_PAGE);
  };

  const canGoNext = year < now.getFullYear() || (year === now.getFullYear() && month < now.getMonth() + 1);

  if (!employeeId) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader icon={CalendarClock} title="My Attendance" />
        <Card><EmptyState title="No employee profile linked" description="This account has no attendance of its own." /></Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={CalendarClock} title="My Attendance" subtitle="Check in and out, and see how your month is going" />

      <MissedCheckOutNotice />

      <TodayAttendanceCard
        record={todayRecord}
        todayInfo={todayInfo}
        isMarking={isMarking}
        onCheckIn={() => mark("in")}
        onCheckOut={() => mark("out")}
      />

      <Card>
        {view.isLoading ? (
          <LoadingState label="Loading your month..." />
        ) : view.error ? (
          <ErrorState message={view.error} onRetry={view.reload} />
        ) : (
          <div className="flex flex-col gap-5">
            <div>
              <p className="font-display text-lg font-bold text-stone-800">
                {summary.passed === 0
                  ? `No working days have passed yet in ${monthName(month)}`
                  : `You worked ${fmtDays(summary.worked)} of ${plural(summary.passed, "working day")}${summary.toCome > 0 ? " so far" : ` in ${monthName(month)}`}`}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
                <div className="col-span-2 rounded-2xl bg-stone-100 px-4 py-3 text-stone-800 ring-1 ring-inset ring-stone-400/30 sm:col-span-1">
                  <p className="font-display text-2xl font-bold">{summary.workingDays}</p>
                  <p className="text-sm font-semibold">Working days</p>
                  <p className="text-sm text-stone-500">{summary.toCome > 0 ? `${summary.passed} done so far` : `in ${monthName(month)}`}</p>
                </div>
                {(["PRESENT", "LATE", "HALF_DAY", "ABSENT"] as DayKind[]).map((kind) => (
                  <div key={kind} className={`rounded-2xl px-4 py-3 ring-1 ring-inset ${DAY_STYLES[kind].pill}`}>
                    <p className="font-display text-2xl font-bold">{summary.counts[kind as "PRESENT" | "LATE" | "HALF_DAY" | "ABSENT"]}</p>
                    <p className="text-sm font-semibold">{DAY_LABELS[kind]}</p>
                  </div>
                ))}
              </div>
              {summary.toCome > 0 && (
                <p className="mt-2 text-base text-stone-600">
                  {summary.passed} of {summary.workingDays} working days done so far · {plural(summary.toCome, "day")} still to come.
                </p>
              )}
              {summary.counts.ON_LEAVE > 0 && (
                <p className="mt-1 text-base text-stone-600">{plural(summary.counts.ON_LEAVE, "day")} of these {summary.counts.ON_LEAVE === 1 ? "was" : "were"} approved leave.</p>
              )}
              {summary.workedOnDaysOff > 0 && (
                <p className="mt-1 text-base text-stone-600">You also worked {plural(summary.workedOnDaysOff, "day")} on a day off.</p>
              )}
              <details className="group mt-2">
                <summary className="flex min-h-[44px] w-fit cursor-pointer list-none items-center gap-1 text-base font-semibold text-brand-700 hover:underline">
                  <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
                  How is this counted?
                </summary>
                <div className="flex flex-col gap-1 pb-1 text-base text-stone-600">
                  <p>
                    {monthName(month)} has {summary.totalDays} days = {summary.workingDays} working days + {plural(summary.sundays, "Sunday")}
                    {summary.holidayNames.length > 0 && ` + ${plural(summary.holidayNames.length, "holiday")} (${summary.holidayNames.join(", ")})`}
                    {summary.daysBeforeJoining > 0 && ` + ${plural(summary.daysBeforeJoining, "day")} before you joined`}.
                  </p>
                  <p>Sundays and company holidays are not working days. Present + Late + Half day + Absent + On leave add up to the working days so far.</p>
                </div>
              </details>
              {overtimeTotal > 0 && (
                <p className="mt-2 text-base font-semibold text-success-700">Overtime this month: {formatDuration(overtimeTotal)}</p>
              )}
            </div>

            <MonthCalendar
              year={year}
              month={month}
              records={view.records}
              holidays={view.holidays}
              leaves={leaves}
              joiningDate={joiningDate}
              todayIso={todayIso}
              selectedDate={selected}
              onSelect={setSelected}
              onPrev={() => goMonth(-1)}
              onNext={() => goMonth(1)}
              canGoNext={canGoNext}
              onJump={jumpTo}
              minYear={joiningDate ? Number(joiningDate.slice(0, 4)) : undefined}
            />
            {selected ? (
              <DayDetail iso={selected} info={classifyDay(selected, dayContext)} />
            ) : (
              <p className="text-base text-stone-500">Tap any day to see what happened.</p>
            )}
          </div>
        )}
      </Card>

      {!view.isLoading && !view.error && (
        <div>
          <h2 className="mb-3 font-display text-lg font-bold text-stone-800">Day by day</h2>
          {historyDays.length === 0 ? (
            <Card><EmptyState title="Nothing to show yet" description="Your days will appear here as you check in." /></Card>
          ) : (
            <>
            <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {historyDays.slice(0, visibleDays).map(({ iso, info }) => {
                const r = info.record;
                const isAbsent = info.kind === "ABSENT";
                const missed = isMissedCheckOut(r, todayIso);
                return (
                  <li key={iso}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(iso);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className="flex w-full flex-col gap-2 rounded-2xl border border-sand-200 bg-white p-4 text-left shadow-sm sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="text-base font-semibold text-stone-800">
                          {formatDayShort(iso)}
                          {parseIsoDate(iso).getDay() === 6 && <span className="ml-2 text-sm font-normal text-stone-400">Saturday</span>}
                        </p>
                        <p className="text-base text-stone-500">
                          {r?.check_in
                            ? `${formatClock(r.check_in)} → ${r.check_out ? formatClock(r.check_out) : missed ? "no check-out" : "not checked out yet"}${r.working_minutes != null ? ` · ${formatDuration(r.working_minutes)}` : ""}`
                            : isAbsent
                              ? "No check-in recorded"
                              : info.label}
                        </p>
                        {r && r.overtime_minutes > 0 && (
                          <p className="text-base font-semibold text-success-700">Overtime {formatDuration(r.overtime_minutes)}</p>
                        )}
                        {missed && (
                          <p className="text-base font-semibold text-amber-700">You forgot to check out. Please ask your manager or HR to fix it.</p>
                        )}
                        {r?.corrected_by_name && (
                          <p className="text-base text-stone-500">Corrected by {r.corrected_by_name}: “{r.correction_reason}”</p>
                        )}
                      </div>
                      <span className={`inline-flex w-fit items-center rounded-full px-3 py-1.5 text-sm font-semibold ring-1 ring-inset ${DAY_STYLES[info.kind].pill}`}>
                        {info.label}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {historyDays.length > DAYS_PER_PAGE && (
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <p className="text-base text-stone-500">
                  Showing {Math.min(visibleDays, historyDays.length)} of {historyDays.length} days
                </p>
                {visibleDays < historyDays.length && (
                  <Button variant="secondary" onClick={() => setVisibleDays((n) => n + DAYS_PER_PAGE)} icon={<ChevronDown className="h-5 w-5" />}>
                    Show {Math.min(DAYS_PER_PAGE, historyDays.length - visibleDays)} more
                  </Button>
                )}
                {visibleDays > DAYS_PER_PAGE && (
                  <Button variant="ghost" onClick={() => setVisibleDays(DAYS_PER_PAGE)} icon={<ChevronUp className="h-5 w-5" />}>
                    Show fewer
                  </Button>
                )}
              </div>
            )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
