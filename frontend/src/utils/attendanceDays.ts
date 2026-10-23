import { isSunday } from "@/utils/friendly";
import type { Attendance, Holiday, LeaveRequest } from "@/types";

/**
 * What kind of day was it for one person? Follows the company rule: Sunday is
 * the weekly holiday (Saturday is a working day), and non-optional entries in
 * the holiday calendar are days off. Stored attendance always wins - if
 * someone worked on a Sunday, that shows as worked.
 */
export type DayKind =
  | "PRESENT"
  | "LATE"
  | "HALF_DAY"
  | "ON_LEAVE"
  | "HOLIDAY"
  | "DAY_OFF"
  | "ABSENT"
  | "TODAY_OPEN"
  | "UPCOMING"
  | "BEFORE_JOINING"
  | "UNKNOWN";

export interface DayInfo {
  kind: DayKind;
  label: string;
  record?: Attendance;
}

export interface DayContext {
  records: Map<string, Attendance>;
  holidays: Map<string, Holiday>;
  todayIso: string;
  joiningDate?: string | null;
  /** When given (the person's own approved leave), a working day with no record can be called "Absent". */
  leaves?: LeaveRequest[];
}

const STATUS_KIND: Record<Attendance["status"], DayKind> = {
  PRESENT: "PRESENT",
  LATE: "LATE",
  HALF_DAY: "HALF_DAY",
  ON_LEAVE: "ON_LEAVE",
  HOLIDAY: "HOLIDAY",
  ABSENT: "ABSENT",
};

export const DAY_LABELS: Record<DayKind, string> = {
  PRESENT: "Present",
  LATE: "Late",
  HALF_DAY: "Half day",
  ON_LEAVE: "On leave",
  HOLIDAY: "Holiday",
  DAY_OFF: "Day off",
  ABSENT: "Absent",
  TODAY_OPEN: "Not checked in yet",
  UPCOMING: "Coming up",
  BEFORE_JOINING: "Before you joined",
  UNKNOWN: "No record",
};

export function classifyDay(iso: string, ctx: DayContext): DayInfo {
  const record = ctx.records.get(iso);
  if (record) {
    const kind = STATUS_KIND[record.status];
    return { kind, label: DAY_LABELS[kind], record };
  }
  if (iso > ctx.todayIso) return { kind: "UPCOMING", label: DAY_LABELS.UPCOMING };
  if (ctx.joiningDate && iso < ctx.joiningDate) return { kind: "BEFORE_JOINING", label: DAY_LABELS.BEFORE_JOINING };

  const holiday = ctx.holidays.get(iso);
  if (holiday && !holiday.is_optional) return { kind: "HOLIDAY", label: holiday.name };
  if (isSunday(iso)) return { kind: "DAY_OFF", label: "Sunday - day off" };

  // A half-day leave is not a day off: the person works the other half, so it never turns a day into "On leave".
  if (ctx.leaves?.some((l) => l.status === "APPROVED" && !l.day_part && l.start_date <= iso && iso <= l.end_date)) {
    return { kind: "ON_LEAVE", label: DAY_LABELS.ON_LEAVE };
  }
  if (iso === ctx.todayIso) return { kind: "TODAY_OPEN", label: DAY_LABELS.TODAY_OPEN };
  return ctx.leaves ? { kind: "ABSENT", label: DAY_LABELS.ABSENT } : { kind: "UNKNOWN", label: DAY_LABELS.UNKNOWN };
}

/** Colors for a day, used by the calendar cells, the legend and the history list. */
export const DAY_STYLES: Record<DayKind, { cell: string; dot: string; pill: string }> = {
  PRESENT: { cell: "bg-success-100 text-success-900", dot: "bg-success-400", pill: "bg-success-50 text-success-800 ring-success-600/20" },
  LATE: { cell: "bg-sunset-100 text-sunset-900", dot: "bg-sunset-400", pill: "bg-sunset-50 text-sunset-800 ring-sunset-600/20" },
  HALF_DAY: { cell: "bg-amber-100 text-amber-900", dot: "bg-amber-400", pill: "bg-amber-50 text-amber-800 ring-amber-600/20" },
  ON_LEAVE: { cell: "bg-sky-100 text-sky-900", dot: "bg-sky-400", pill: "bg-sky-50 text-sky-800 ring-sky-600/20" },
  HOLIDAY: { cell: "bg-violet-100 text-violet-900", dot: "bg-violet-400", pill: "bg-violet-50 text-violet-800 ring-violet-600/20" },
  DAY_OFF: { cell: "bg-sand-200 text-stone-500", dot: "bg-sand-300", pill: "bg-stone-100 text-stone-600 ring-stone-400/30" },
  ABSENT: { cell: "bg-rose-100 text-rose-900", dot: "bg-rose-400", pill: "bg-rose-50 text-rose-800 ring-rose-600/20" },
  TODAY_OPEN: { cell: "bg-white text-stone-700", dot: "bg-stone-300", pill: "bg-stone-100 text-stone-600 ring-stone-400/30" },
  UPCOMING: { cell: "bg-transparent text-stone-400", dot: "bg-stone-200", pill: "bg-stone-100 text-stone-500 ring-stone-400/30" },
  BEFORE_JOINING: { cell: "bg-transparent text-stone-300", dot: "bg-stone-200", pill: "bg-stone-100 text-stone-500 ring-stone-400/30" },
  UNKNOWN: { cell: "bg-white text-stone-700", dot: "bg-stone-200", pill: "bg-stone-100 text-stone-600 ring-stone-400/30" },
};

export const LEGEND_KINDS: DayKind[] = ["PRESENT", "LATE", "HALF_DAY", "ON_LEAVE", "HOLIDAY", "ABSENT", "DAY_OFF"];

/** A past day where the person checked in but never checked out (today is not "missed" yet). */
export function isMissedCheckOut(record: { attendance_date: string; check_in: string | null; check_out: string | null } | null | undefined, todayIso: string): boolean {
  return Boolean(record && record.check_in && !record.check_out && record.attendance_date < todayIso);
}

export interface MonthSummary {
  totalDays: number;
  /** Days this person is expected to work: no Sundays, no company holidays, nothing before they joined. */
  workingDays: number;
  sundays: number;
  holidayNames: string[];
  daysBeforeJoining: number;
  /** Working days already decided: before today, or today once there is a record. */
  passed: number;
  toCome: number;
  counts: Record<"PRESENT" | "LATE" | "HALF_DAY" | "ABSENT" | "ON_LEAVE", number>;
  /** Present + Late + half a day for each Half day - the same weighting payroll uses. */
  worked: number;
  /** Saved attendance on a Sunday or holiday (extra effort, not part of the working days). */
  workedOnDaysOff: number;
}

/**
 * One month in working days. Same rule as the roll call and the payroll summary: Sunday is the weekly
 * holiday, non-optional entries in the holiday calendar are days off, optional holidays are working days.
 * Present + Late + Half day + Absent + On leave always add up to `passed`.
 */
export function summarizeMonth(year: number, month: number, ctx: DayContext): MonthSummary {
  const total = new Date(year, month, 0).getDate();
  const counts = { PRESENT: 0, LATE: 0, HALF_DAY: 0, ABSENT: 0, ON_LEAVE: 0 };
  const holidayNames: string[] = [];
  let workingDays = 0;
  let passed = 0;
  let sundays = 0;
  let daysBeforeJoining = 0;
  let workedOnDaysOff = 0;

  for (let day = 1; day <= total; day++) {
    const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    if (ctx.joiningDate && iso < ctx.joiningDate) {
      daysBeforeJoining++;
      continue;
    }
    const holiday = ctx.holidays.get(iso);
    const isHoliday = Boolean(holiday && !holiday.is_optional);
    if (isSunday(iso) || isHoliday) {
      if (isSunday(iso)) sundays++;
      else holidayNames.push(holiday!.name);
      const status = ctx.records.get(iso)?.status;
      if (status === "PRESENT" || status === "LATE" || status === "HALF_DAY") workedOnDaysOff++;
      continue;
    }
    workingDays++;
    const kind = classifyDay(iso, ctx).kind;
    if (kind in counts) {
      counts[kind as keyof typeof counts]++;
      passed++;
    }
  }
  return {
    totalDays: total,
    workingDays,
    sundays,
    holidayNames,
    daysBeforeJoining,
    passed,
    toCome: workingDays - passed,
    counts,
    worked: counts.PRESENT + counts.LATE + 0.5 * counts.HALF_DAY,
    workedOnDaysOff,
  };
}
