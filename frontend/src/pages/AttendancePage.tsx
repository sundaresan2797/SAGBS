import clsx from "clsx";
import { CalendarCheck, CalendarOff, CalendarPlus, CalendarRange, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { AttendanceCalendar } from "@/components/AttendanceCalendar";
import { MissedCheckOutsPanel } from "@/components/MissedCheckOutsPanel";
import { RecordAbsenceSheet, type RecordAbsenceTarget } from "@/components/RecordAbsenceSheet";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/EntityCard";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { Td, Th, TableContainer } from "@/components/ui/Table";
import { useAttendancePolicy } from "@/hooks/useAttendancePolicy";
import { useAuth } from "@/hooks/useAuth";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import type { RollCall, RollCallStatus } from "@/types";
import { formatDuration, formatPermissionLength } from "@/utils/friendly";

const PAGE_SIZE = 25;

const STATUS_LABELS: Record<RollCallStatus, string> = {
  PRESENT: "Present",
  LATE: "Late",
  HALF_DAY: "Half day",
  ON_LEAVE: "On leave",
  NOT_CHECKED_IN: "Not checked in",
  ABSENT: "Absent",
  HOLIDAY: "Day off",
};

// The order the summary chips appear in.
const CHIP_ORDER: RollCallStatus[] = [
  "PRESENT",
  "LATE",
  "HALF_DAY",
  "ON_LEAVE",
  "NOT_CHECKED_IN",
  "ABSENT",
  "HOLIDAY",
];

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
}

function shiftDay(iso: string, delta: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

function formatLongDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function AttendancePage() {
  const { hasPermission, user } = useAuth();
  const policy = useAttendancePolicy();
  // Bumped after a check-out is fixed so the missed list and the roll call both refresh.
  const [missedReloadKey, setMissedReloadKey] = useState(0);
  const isTeamView = !hasPermission("attendance:read_all");

  // `day` is null until the user picks one: the server then answers for its
  // own "today", and `today` remembers that date so the picker and the
  // next-day arrow never let anyone go past it.
  const [day, setDay] = useState<string | null>(null);
  const [today, setToday] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [status, setStatus] = useState<RollCallStatus | "">("");
  const [page, setPage] = useState(1);

  const [rollCall, setRollCall] = useState<RollCall | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ id: number; name: string; code: string } | null>(null);
  const [recordTarget, setRecordTarget] = useState<RecordAbsenceTarget | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchText);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchText]);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await attendanceService.rollCall({
        date: day ?? undefined,
        department_id: departmentId ? Number(departmentId) : undefined,
        search: search || undefined,
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setRollCall(result);
      if (day === null) setToday(result.date);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load attendance."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, departmentId, search, status, page]);

  const currentDay = day ?? today;
  const isToday = currentDay !== null && currentDay === today;

  const changeDay = (next: string | null) => {
    setDay(next);
    setPage(1);
  };

  const summary = rollCall?.summary ?? {};
  const everyone = Object.values(summary).reduce((sum, count) => sum + (count ?? 0), 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <CalendarCheck className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">
            {isTeamView ? "Team Attendance" : "Attendance"}
          </h1>
          <p className="text-sm text-stone-500">
            {currentDay ? formatLongDate(currentDay) : "Loading..."} &middot; click anyone to see their monthly calendar
          </p>
        </div>
      </div>

      <MissedCheckOutsPanel
        reloadKey={missedReloadKey}
        onChanged={() => {
          setMissedReloadKey((k) => k + 1);
          load();
        }}
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Previous day"
            disabled={currentDay === null}
            onClick={() => currentDay && changeDay(shiftDay(currentDay, -1))}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-500 hover:bg-sand-100 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <input
            type="date"
            aria-label="Choose a day"
            value={currentDay ?? ""}
            max={today ?? undefined}
            onChange={(e) => e.target.value && changeDay(e.target.value === today ? null : e.target.value)}
            className="rounded-xl border-2 border-sand-200 px-3 py-2 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="button"
            aria-label="Next day"
            disabled={currentDay === null || isToday}
            title={isToday ? "Attendance isn't available for a day that hasn't happened yet" : undefined}
            onClick={() => currentDay && changeDay(shiftDay(currentDay, 1) === today ? null : shiftDay(currentDay, 1))}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-500 hover:bg-sand-100 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          {!isToday && (
            <button
              type="button"
              onClick={() => changeDay(null)}
              className="ml-1 rounded-lg px-2.5 py-1.5 text-sm font-semibold text-brand-600 hover:bg-brand-50"
            >
              Today
            </button>
          )}
        </div>

        <div className="relative min-w-[14rem] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
          <input
            type="text"
            placeholder="Search by name, code or department..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>

        {!isTeamView && rollCall && rollCall.departments.length > 1 && (
          <select
            aria-label="Filter by department"
            value={departmentId}
            onChange={(e) => {
              setDepartmentId(e.target.value);
              setPage(1);
            }}
            className="rounded-xl border-2 border-sand-200 bg-white px-3 py-2 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All departments</option>
            {rollCall.departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {rollCall?.day_off_reason && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          <CalendarOff className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <span>
            <span className="font-semibold">{rollCall.day_off_reason}</span> is a day off, so nobody is expected in.
            Anyone who did come in is still shown as present.
          </span>
        </div>
      )}

      {rollCall && everyone > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          <button
            type="button"
            onClick={() => {
              setStatus("");
              setPage(1);
            }}
            className={clsx(
              "rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-inset transition-colors",
              status === ""
                ? "bg-stone-800 text-white ring-stone-800"
                : "bg-white text-stone-600 ring-sand-200 hover:bg-sand-50",
            )}
          >
            Everyone <span className="ml-1 opacity-70">{everyone}</span>
          </button>
          {CHIP_ORDER.filter((s) => (summary[s] ?? 0) > 0).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setStatus(status === s ? "" : s);
                setPage(1);
              }}
              aria-pressed={status === s}
              className={clsx(
                "rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-inset transition-colors",
                status === s
                  ? "bg-brand-600 text-white ring-brand-600"
                  : "bg-white text-stone-600 ring-sand-200 hover:bg-sand-50",
              )}
            >
              {STATUS_LABELS[s]} <span className="ml-1 opacity-70">{summary[s]}</span>
            </button>
          ))}
        </div>
      )}

      <Card className="p-0">
        {isLoading && !rollCall ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !rollCall || rollCall.items.length === 0 ? (
          <EmptyState
            title="No one matches"
            description={
              everyone === 0
                ? isTeamView
                  ? "You don't have any direct reports on the roll for this day."
                  : "No employees were on the roll for this day."
                : "Try a different search, status or department."
            }
          />
        ) : (
          <div className={clsx(isLoading && "opacity-60 transition-opacity")}>
            <TableContainer>
              <thead>
                <tr>
                  <Th>Employee</Th>
                  <Th>Department</Th>
                  <Th>Check In</Th>
                  <Th>Check Out</Th>
                  <Th>Hours</Th>
                  <Th>Status</Th>
                  <Th></Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-100">
                {rollCall.items.map((entry) => (
                  <tr
                    key={entry.employee_id}
                    onClick={() =>
                      setSelected({ id: entry.employee_id, name: entry.employee_name, code: entry.employee_code })
                    }
                    className="cursor-pointer hover:bg-sand-50"
                  >
                    <Td>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={entry.employee_name} size="sm" employeeId={entry.employee_id} />
                        <div className="flex flex-col">
                          <span className="font-medium text-stone-800">{entry.employee_name}</span>
                          <span className="text-xs text-stone-400">
                            {entry.employee_code} &middot; {entry.designation}
                          </span>
                        </div>
                      </div>
                    </Td>
                    <Td>{entry.department}</Td>
                    <Td>{formatTime(entry.check_in)}</Td>
                    <Td>{formatTime(entry.check_out)}</Td>
                    <Td>
                      <div className="flex flex-col">
                        <span>{entry.working_minutes != null ? formatDuration(entry.working_minutes) : "—"}</span>
                        {entry.overtime_minutes > 0 && (
                          <span className="text-xs font-semibold text-success-700">+{formatDuration(entry.overtime_minutes)} overtime</span>
                        )}
                      </div>
                    </Td>
                    <Td>
                      <div className="flex flex-col items-start gap-1">
                        <Badge status={entry.status} label={STATUS_LABELS[entry.status]} />
                        {entry.half_day_leave && (
                          <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 ring-1 ring-inset ring-sky-600/20">
                            Half-day leave
                          </span>
                        )}
                        {entry.permission_minutes > 0 && (
                          <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 ring-1 ring-inset ring-sky-600/20">
                            Permission {formatPermissionLength(entry.permission_minutes)}
                          </span>
                        )}
                        {entry.missed_check_out && (
                          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                            Missed check-out
                          </span>
                        )}
                        {policy && entry.working_minutes != null && entry.working_minutes > policy.long_day_minutes && (
                          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                            Please check this
                          </span>
                        )}
                      </div>
                    </Td>
                    <Td>
                      <div className="flex flex-col items-start gap-1.5">
                        <span className="flex items-center gap-1 text-xs font-semibold text-brand-600">
                          <CalendarRange className="h-3.5 w-3.5" aria-hidden="true" />
                          Calendar
                        </span>
                        {/* You can record time off for someone else, never for yourself (the server refuses that too). */}
                        {entry.employee_id !== user?.employee_id && (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setRecordTarget({ employeeId: entry.employee_id, employeeName: entry.employee_name, dateIso: rollCall.date });
                            }}
                            className="flex min-h-[32px] items-center gap-1 rounded-lg px-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-50"
                          >
                            <CalendarPlus className="h-3.5 w-3.5" aria-hidden="true" />
                            Leave / permission
                          </button>
                        )}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableContainer>
            <div className="px-4 pb-4">
              <Pagination
                page={rollCall.page}
                totalPages={rollCall.total_pages}
                total={rollCall.total}
                onPageChange={setPage}
              />
            </div>
          </div>
        )}
      </Card>

      <RecordAbsenceSheet
        target={recordTarget}
        onClose={() => setRecordTarget(null)}
        onSaved={() => {
          setRecordTarget(null);
          load();
        }}
      />

      <Modal
        title={selected ? `${selected.name} (${selected.code})` : ""}
        isOpen={selected !== null}
        onClose={() => setSelected(null)}
        maxWidth="max-w-2xl"
      >
        {selected && (
          <AttendanceCalendar
            employeeId={selected.id}
            employeeName={selected.name}
            initialDate={currentDay ?? undefined}
            // You can fix someone else's day, never your own (the server refuses that too).
            canFix={selected.id !== user?.employee_id}
            onFixed={() => {
              setMissedReloadKey((k) => k + 1);
              load();
            }}
          />
        )}
      </Modal>
    </div>
  );
}
