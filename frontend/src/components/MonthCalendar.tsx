import clsx from "clsx";
import { ChevronLeft, ChevronRight, Pencil, Wrench } from "lucide-react";

import { MonthYearSelects } from "@/components/MonthYearPicker";
import { Button } from "@/components/ui/Button";

import { classifyDay, DAY_LABELS, DAY_STYLES, isMissedCheckOut, LEGEND_KINDS, type DayInfo } from "@/utils/attendanceDays";
import { formatClock, formatDay, formatDuration, formatTimestampDate, monthName } from "@/utils/friendly";
import { toIsoDate } from "@/utils/taskHelpers";
import type { Attendance, Holiday, LeaveRequest } from "@/types";

const DAY_HEADERS = ["S", "M", "T", "W", "T", "F", "S"];

interface Props {
  year: number;
  month: number;
  records: Attendance[];
  holidays: Holiday[];
  leaves?: LeaveRequest[];
  joiningDate?: string | null;
  todayIso: string;
  selectedDate: string | null;
  onSelect: (iso: string) => void;
  onPrev: () => void;
  onNext: () => void;
  canGoNext: boolean;
  /** When given, the month title becomes Month and Year drop-downs to jump straight to any month. */
  onJump?: (year: number, month: number) => void;
  /** The earliest year offered when jumping (for example the year the person joined). */
  minYear?: number;
}

export function buildDayContext(records: Attendance[], holidays: Holiday[], todayIso: string, leaves?: LeaveRequest[], joiningDate?: string | null) {
  return {
    records: new Map(records.map((r) => [r.attendance_date, r])),
    holidays: new Map(holidays.map((h) => [h.holiday_date, h])),
    todayIso,
    joiningDate,
    leaves,
  };
}

export function MonthCalendar({
  year,
  month,
  records,
  holidays,
  leaves,
  joiningDate,
  todayIso,
  selectedDate,
  onSelect,
  onPrev,
  onNext,
  canGoNext,
  onJump,
  minYear,
}: Props) {
  const ctx = buildDayContext(records, holidays, todayIso, leaves, joiningDate);
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const cells: (number | null)[] = [...Array(firstWeekday).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onPrev}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-stone-600 hover:bg-sand-100"
          aria-label="Previous month"
        >
          <ChevronLeft className="h-6 w-6" />
        </button>
        {onJump ? (
          <MonthYearSelects year={year} month={month} onChange={onJump} minYear={minYear} />
        ) : (
          <p className="font-display text-lg font-bold text-stone-800">
            {monthName(month)} {year}
          </p>
        )}
        <button
          type="button"
          onClick={onNext}
          disabled={!canGoNext}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-stone-600 hover:bg-sand-100 disabled:opacity-30 disabled:hover:bg-transparent"
          aria-label="Next month"
        >
          <ChevronRight className="h-6 w-6" />
        </button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5" aria-label="What the colours mean">
        {LEGEND_KINDS.map((kind) => (
          <span key={kind} className="flex items-center gap-1.5 text-sm text-stone-600">
            <span className={clsx("h-3 w-3 rounded-full", DAY_STYLES[kind].dot)} aria-hidden="true" />
            {DAY_LABELS[kind]}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1.5">
        {DAY_HEADERS.map((label, i) => (
          <div key={i} className="pb-0.5 text-center text-sm font-semibold text-stone-400">
            {label}
          </div>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <div key={`blank-${i}`} />;
          const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
          const info = classifyDay(iso, ctx);
          const selected = iso === selectedDate;
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onSelect(iso)}
              aria-label={`${formatDay(iso)}: ${info.label}`}
              aria-pressed={selected}
              className={clsx(
                "flex aspect-square min-h-[44px] items-center justify-center rounded-xl text-base font-semibold transition-shadow",
                DAY_STYLES[info.kind].cell,
                iso === todayIso && "ring-2 ring-brand-500",
                selected && "shadow-[0_0_0_3px_rgba(15,23,42,0.85)]",
              )}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * What happened on the day you tapped. `manager` is passed only when a manager/HR is looking at
 * someone else's day: it adds the "Fix check-out" button and the long-day flag.
 */
export function DayDetail({
  iso,
  info,
  manager,
}: {
  iso: string;
  info: DayInfo;
  manager?: {
    onFix?: (record: Attendance) => void;
    onMarkPresent?: (iso: string) => void;
    onCorrect?: (iso: string, record: Attendance | null) => void;
    longDayMinutes?: number;
  };
}) {
  const record = info.record;
  const missed = isMissedCheckOut(record, toIsoDate(new Date()));
  const isPastDay = iso < toIsoDate(new Date());
  const isLongDay = Boolean(manager?.longDayMinutes && record?.working_minutes && record.working_minutes > manager.longDayMinutes);
  return (
    <div className="rounded-2xl bg-sand-50 p-4">
      <p className="text-sm font-semibold text-stone-500">{formatDay(iso)}</p>
      <p className="mt-0.5 flex flex-wrap items-center gap-2 font-display text-xl font-bold text-stone-800">
        {info.label}
        <span className={clsx("h-3 w-3 rounded-full", DAY_STYLES[info.kind].dot)} aria-hidden="true" />
      </p>
      {record?.check_in ? (
        <div className="mt-1 flex flex-col gap-1 text-base text-stone-600">
          <p>
            In at {formatClock(record.check_in)}
            {record.check_out ? ` · Out at ${formatClock(record.check_out)}` : missed ? " · No check-out" : " · Not checked out yet"}
            {record.working_minutes != null ? ` · ${formatDuration(record.working_minutes)} worked` : ""}
            {record.late_minutes > 0 ? ` · ${formatDuration(record.late_minutes)} late` : ""}
          </p>
          {record.overtime_minutes > 0 && (
            <p className="font-semibold text-success-700">Overtime: {formatDuration(record.overtime_minutes)}</p>
          )}
          {missed && (
            <p className="font-semibold text-amber-700">
              {manager ? "Missed check-out. The hours are missing until it is fixed." : "You forgot to check out. Please ask your manager or HR to fix it."}
            </p>
          )}
          {isLongDay && <p className="font-semibold text-amber-700">Very long day. Please check the check-out time.</p>}
          {record.corrected_by_name && (
            <p className="text-stone-500">
              Corrected by {record.corrected_by_name}
              {record.corrected_at ? ` on ${formatTimestampDate(record.corrected_at)}` : ""}: “{record.correction_reason}”
            </p>
          )}
          {missed && manager?.onFix && (
            <div className="mt-2">
              <Button variant="secondary" icon={<Wrench className="h-5 w-5" />} onClick={() => manager.onFix?.(record)}>
                Fix check-out
              </Button>
            </div>
          )}
          {manager?.onCorrect && isPastDay && (
            <div className="mt-2">
              <Button variant="secondary" icon={<Pencil className="h-5 w-5" />} onClick={() => manager.onCorrect?.(iso, record ?? null)}>
                Correct attendance
              </Button>
              <p className="mt-1 text-sm text-stone-500">Change the times, or clear this day back to Absent.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-1 flex flex-col gap-2">
          <p className="text-base text-stone-500">
            {info.kind === "ABSENT" ? "No check-in was recorded on this day." : "Nothing recorded for this day."}
          </p>
          {manager?.onMarkPresent && iso < toIsoDate(new Date()) && (info.kind === "ABSENT" || info.kind === "UNKNOWN") && (
            <div>
              <Button variant="secondary" icon={<Wrench className="h-5 w-5" />} onClick={() => manager.onMarkPresent?.(iso)}>
                Mark as present
              </Button>
              <p className="mt-1 text-sm text-stone-500">Use this only if the person really worked but forgot to check in.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
