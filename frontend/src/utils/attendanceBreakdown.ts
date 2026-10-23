import { plural } from "@/utils/friendly";
import type { SalaryPayment } from "@/types";

/**
 * "Paid for 27.5 of 30 days: 2 absent, 1 half day." - or null for a payment made before pay was
 * attendance-based (when everyone was simply paid their full salary, with no day breakdown saved).
 */
export function attendanceBreakdownLine(payment: SalaryPayment): string | null {
  if (payment.total_days == null || payment.payable_days == null) return null;
  const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
  const reasons: string[] = [];
  if (payment.absent_days) reasons.push(`${payment.absent_days} absent`);
  if (payment.half_days) reasons.push(plural(payment.half_days, "half day"));
  if (payment.unpaid_leave_days) reasons.push(`${payment.unpaid_leave_days} unpaid leave`);
  const base = `Paid for ${fmt(payment.payable_days)} of ${payment.total_days} days`;
  return reasons.length > 0 ? `${base}: ${reasons.join(", ")}.` : `${base} (full month).`;
}
