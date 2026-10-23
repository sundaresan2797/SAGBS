import type { Task } from "@/types";

export function toIsoDate(d: Date): string {
  // Format using local date parts, not toISOString() - that converts to
  // UTC first, which silently shifts the date backward for any timezone
  // ahead of UTC (e.g. Asia/Kolkata, UTC+5:30).
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function isTaskOverdue(task: Task): boolean {
  if (!task.due_date || task.status === "COMPLETED") return false;
  return task.due_date < toIsoDate(new Date());
}
