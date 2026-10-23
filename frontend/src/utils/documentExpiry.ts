import { daysFromToday } from "@/utils/friendly";

// The single definition of "expiring soon" for a document, shared by My Documents and the
// personal dashboard - so the two screens can never disagree about which documents need
// attention (previously each one had its own copy of this number and this math).
export const EXPIRY_WARNING_DAYS = 30;

export type ExpiryState = "expired" | "soon" | "ok" | "none";

export function expiryState(expiryDate: string | null): ExpiryState {
  if (!expiryDate) return "none";
  const days = daysFromToday(expiryDate);
  if (days < 0) return "expired";
  if (days <= EXPIRY_WARNING_DAYS) return "soon";
  return "ok";
}
