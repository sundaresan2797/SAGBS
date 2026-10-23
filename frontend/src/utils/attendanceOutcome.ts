import type { AttendancePolicy } from "@/types";
import { formatDuration, formatHHMM, formatHoursWords, hhmmToMinutes } from "@/utils/friendly";

/** How much of the company's lunch break falls inside this check-in to check-out span (same calendar day,
 * minutes since midnight) - mirrors the server's own `lunch_break_minutes_within`, so the preview a manager
 * or employee sees before saving always matches what actually gets recorded. */
export function lunchMinutesWithin(checkInMinutes: number, checkOutMinutes: number, policy: AttendancePolicy): number {
  const lunchStart = hhmmToMinutes(policy.lunch_start);
  const lunchEnd = lunchStart + policy.lunch_break_minutes;
  return Math.max(0, Math.min(checkOutMinutes, lunchEnd) - Math.max(checkInMinutes, lunchStart));
}

/**
 * What a day will be recorded as, using the company's rules, for the "fix" sheets that show it before saving.
 * (The server does the real calculation - this is only the preview.) Times are minutes since midnight.
 */
export function previewOutcome(
  checkInMinutes: number,
  checkOutMinutes: number,
  policy: AttendancePolicy,
  isLate: boolean,
): { good: boolean; text: string } {
  const raw = checkOutMinutes - checkInMinutes;
  if (raw <= 0) return { good: false, text: "The check-out must be after the check-in." };
  const worked = raw - lunchMinutesWithin(checkInMinutes, checkOutMinutes, policy);
  const afterCutoff = checkInMinutes > hhmmToMinutes(policy.half_day_after);
  const overtime = Math.max(0, worked - policy.standard_shift_minutes);
  let result: string;
  let good = true;
  if (afterCutoff || worked < policy.full_day_minimum_minutes) {
    result = `Half day (${afterCutoff ? `came after ${formatHHMM(policy.half_day_after)}` : `under ${formatHoursWords(policy.full_day_minimum_minutes)}`})`;
    good = false;
  } else {
    result = isLate ? "Full day, marked late" : "Full day";
  }
  return { good, text: `${formatDuration(worked)} worked · ${result}${overtime > 0 ? ` · ${formatDuration(overtime)} overtime` : ""}` };
}
