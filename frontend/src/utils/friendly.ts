import { toIsoDate } from "@/utils/taskHelpers";

// Plain, human wording for dates and times ("Fri, 18 Sep 2026", "9:11 AM",
// "2 hours ago") instead of the raw 2026-09-18 / 9/20/2026, 4:51:50 PM forms.
// Formatted by hand, not with Intl, so the wording is identical in every
// browser and locale.

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKDAYS_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DAY_MS = 86_400_000;

/** "2026-09-18" as a local calendar date (no timezone shift). */
export function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function weekdayName(iso: string): string {
  return WEEKDAYS_LONG[parseIsoDate(iso).getDay()];
}

export function monthName(monthNumber: number): string {
  return MONTHS_LONG[monthNumber - 1];
}

export function isSunday(iso: string): boolean {
  return parseIsoDate(iso).getDay() === 0;
}

/** "Fri, 18 Sep 2026" */
export function formatDay(iso: string): string {
  const d = parseIsoDate(iso);
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** A server timestamp ("2026-09-20T03:30:00Z") as the local calendar date it fell on: "20 Sep 2026". */
export function formatTimestampDate(isoDateTime: string): string {
  return formatDateLong(toIsoDate(new Date(isoDateTime)));
}

/** "Fri, 18 Sep" */
export function formatDayShort(iso: string): string {
  const d = parseIsoDate(iso);
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "18 Sep 2026" */
export function formatDateLong(iso: string): string {
  const d = parseIsoDate(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** "Sunday, 20 September" */
export function formatToday(date: Date = new Date()): string {
  return `${WEEKDAYS_LONG[date.getDay()]}, ${date.getDate()} ${MONTHS_LONG[date.getMonth()]}`;
}

/** One day -> "Mon, 5 Oct 2026"; a range -> "Mon, 5 Oct – Wed, 7 Oct 2026". */
export function formatDateRange(start: string, end: string): string {
  if (start === end) return formatDay(start);
  const s = parseIsoDate(start);
  const e = parseIsoDate(end);
  if (s.getFullYear() === e.getFullYear()) {
    return `${formatDayShort(start)} – ${formatDayShort(end)} ${e.getFullYear()}`;
  }
  return `${formatDay(start)} – ${formatDay(end)}`;
}

/** "9:11 AM" */
export function formatClock(isoDateTime: string): string {
  const d = new Date(isoDateTime);
  const hours = d.getHours();
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${hours % 12 || 12}:${minutes} ${hours >= 12 ? "PM" : "AM"}`;
}

/** "09:10" (24-hour, as the server sends it) -> "9:10 AM" */
export function formatHHMM(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

/** "09:10" -> 550 (minutes since midnight) */
export function hhmmToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** 420 -> "7 hours", 450 -> "7.5 hours" */
export function formatHoursWords(totalMinutes: number): string {
  const hours = Math.round((totalMinutes / 60) * 10) / 10;
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}

/** 548 -> "9h 8m" */
export function formatDuration(totalMinutes: number): string {
  const minutes = Math.max(0, Math.round(totalMinutes));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** Whole calendar days from today to `iso` (negative = in the past). */
export function daysFromToday(iso: string, now: Date = new Date()): number {
  return Math.round((parseIsoDate(iso).getTime() - parseIsoDate(toIsoDate(now)).getTime()) / DAY_MS);
}

/** "Due today", "Due in 3 days", "2 days late" */
export function dueLabel(iso: string): string {
  const days = daysFromToday(iso);
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days > 1) return `Due in ${days} days`;
  return days === -1 ? "1 day late" : `${-days} days late`;
}

/** "in 12 days", "tomorrow", "today" */
export function inDaysLabel(iso: string): string {
  const days = daysFromToday(iso);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days > 1) return `in ${days} days`;
  return days === -1 ? "yesterday" : `${-days} days ago`;
}

/** "Just now", "5 minutes ago", "2 hours ago", "Yesterday", "3 days ago", else "18 Sep 2026" */
export function timeAgo(isoDateTime: string, now: Date = new Date()): string {
  const then = new Date(isoDateTime);
  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24 && then.getDate() === now.getDate()) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  const days = daysFromToday(toIsoDate(then), now) * -1;
  if (days <= 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDateLong(toIsoDate(then));
}

/** Which heading a notification sits under. */
export function dayGroup(isoDateTime: string, now: Date = new Date()): "Today" | "Yesterday" | "Earlier" {
  const days = daysFromToday(toIsoDate(new Date(isoDateTime)), now) * -1;
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return "Earlier";
}

/** Server messages carry raw dates ("from 2026-11-02 to 2026-11-03"); show them the friendly way. */
export function friendlyMessage(text: string): string {
  return text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (match) => formatDateLong(match));
}

export function greeting(now: Date = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/** "5 days", "3 months", "1 year 2 months" */
export function tenureText(joiningIso: string, now: Date = new Date()): string {
  const start = parseIsoDate(joiningIso);
  let months = (now.getFullYear() - start.getFullYear()) * 12 + (now.getMonth() - start.getMonth());
  if (now.getDate() < start.getDate()) months -= 1;
  if (months < 1) {
    const days = Math.max(0, daysFromToday(joiningIso, now) * -1);
    return days === 1 ? "1 day" : `${days} days`;
  }
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const y = years === 1 ? "1 year" : `${years} years`;
  const m = rest === 1 ? "1 month" : `${rest} months`;
  if (years === 0) return m;
  return rest === 0 ? y : `${y} ${m}`;
}

export function plural(count: number, one: string, many: string = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** "480 B", "12.4 KB", "3.1 MB" */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "1 h 30 min" / "2 h" / "45 min" - a permission's length. */
export function formatPermissionLength(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours && rest) return `${hours} h ${rest} min`;
  return hours ? `${hours} h` : `${rest} min`;
}

/** "Half day (morning)" for a half-day leave, otherwise "1 day" / "3 days". */
export function leaveLengthLabel(numberOfDays: number, dayPart: "FIRST_HALF" | "SECOND_HALF" | null): string {
  if (dayPart === "FIRST_HALF") return "Half day (morning)";
  if (dayPart === "SECOND_HALF") return "Half day (afternoon)";
  return `${numberOfDays} ${numberOfDays === 1 ? "day" : "days"}`;
}

/**
 * A starting guess at a company login address from a person's name: "Panneer Selvam S" -> "panneer.selvam@sat.com".
 * Only a suggestion shown in the "Change email" box - never saved on its own, and freely editable, since real
 * names (middle names, initials, spelling) don't always fit one pattern.
 */
export function suggestCompanyEmail(fullName: string, domain = "sat.com"): string {
  const words = fullName
    .trim()
    .split(/\s+/)
    .map((word) => word.replace(/[^a-zA-Z]/g, "").toLowerCase())
    .filter(Boolean);
  if (words.length === 0) return `@${domain}`;
  const local = words.length === 1 ? words[0] : `${words[0]}.${words[1]}`;
  return `${local}@${domain}`;
}
