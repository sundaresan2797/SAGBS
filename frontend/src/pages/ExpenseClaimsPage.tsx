import clsx from "clsx";
import { Check, Receipt, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Avatar, CardGrid } from "@/components/ui/EntityCard";
import { TextareaField } from "@/components/ui/FormField";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { YearFilter, yearParam, type YearValue } from "@/components/YearFilter";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { payrollService } from "@/services/payrollService";
import type { ExpenseClaim, ExpenseClaimStatus } from "@/types";
import { formatDateLong, formatTimestampDate } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { EXPENSE_CATEGORY_LABEL } from "@/utils/plainWords";

// The list is narrowed with these chips, so a long list stays easy to work through.
const STATUS_FILTERS: { value: ExpenseClaimStatus | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "PENDING", label: "Waiting" },
  { value: "APPROVED", label: "To pay" },
  { value: "PAID", label: "Paid" },
  { value: "REJECTED", label: "Rejected" },
];

// The same words as the filter chips above the list, so a card and its chip never disagree.
const STATUS_LABEL: Record<string, string> = Object.fromEntries(STATUS_FILTERS.map((f) => [f.value, f.label]));

export function ExpenseClaimsPage() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [claims, setClaims] = useState<ExpenseClaim[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<ExpenseClaim | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ExpenseClaimStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [year, setYear] = useState<YearValue>(new Date().getFullYear()); // this year to begin with

  // `quiet` refreshes without the loading screen, so the list keeps its scroll position after Approve / Reject / Paid.
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const items = await fetchAllPages((page) => payrollService.allExpenseClaims(undefined, page, 100, yearParam(year)));
      setClaims(items);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load expense claims."));
    } finally {
      setIsLoading(false);
    }
  };

  // The first load shows the loading screen; a year change refreshes quietly so the filters stay put.
  const loadedOnce = useRef(false);
  useEffect(() => {
    load(loadedOnce.current);
    loadedOnce.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const handleApprove = async (id: number) => {
    setIsProcessing(true);
    try {
      await payrollService.approveExpenseClaim(id);
      showToast("Claim approved", "success");
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsProcessing(false);
    }
  };

  const closeRejectDialog = () => {
    setRejectTarget(null);
    setRejectReason("");
  };

  const handleReject = async () => {
    if (!rejectTarget) return;
    setIsProcessing(true);
    try {
      await payrollService.rejectExpenseClaim(rejectTarget.id, rejectReason.trim() || undefined);
      showToast("Claim rejected", "success");
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsProcessing(false);
      closeRejectDialog();
    }
  };

  const handlePay = async (id: number) => {
    setIsProcessing(true);
    try {
      await payrollService.payExpenseClaim(id);
      showToast("Marked as paid", "success");
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsProcessing(false);
    }
  };

  const pending = claims.filter((c) => c.status === "PENDING");
  const counts = useMemo(() => {
    const result: Record<string, number> = { ALL: claims.length };
    for (const c of claims) result[c.status] = (result[c.status] ?? 0) + 1;
    return result;
  }, [claims]);

  // Waiting claims come first, then the rest, narrowed by the chip and the search box.
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return [...claims.filter((c) => c.status === "PENDING"), ...claims.filter((c) => c.status !== "PENDING")].filter(
      (c) =>
        (statusFilter === "ALL" || c.status === statusFilter) &&
        (!needle || `${c.employee_name} ${c.employee_code}`.toLowerCase().includes(needle)),
    );
  }, [claims, statusFilter, search]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <Receipt className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">Expense Reimbursements</h1>
          <p className="text-sm text-stone-500">{pending.length} waiting for a decision</p>
        </div>
      </div>

      <YearFilter value={year} onChange={setYear} className="self-start" />

      {isLoading ? (
        <LoadingState label="Loading claims..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : claims.length === 0 ? (
        <Card>
          <EmptyState
            title={year === "ALL" ? "No expense claims" : `No expense claims in ${year}`}
            description={year === "ALL" ? "Claims submitted by employees will show up here." : "Pick another year, or All years, to see older claims."}
          />
        </Card>
      ) : (
        <>
          <div role="group" aria-label="Show claims that are" className="flex flex-wrap gap-2">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                aria-pressed={statusFilter === f.value}
                onClick={() => setStatusFilter(f.value)}
                className={clsx(
                  "min-h-[44px] rounded-full px-4 text-sm font-semibold ring-1 ring-inset transition-colors",
                  statusFilter === f.value ? "bg-stone-800 text-white ring-stone-800" : "bg-white text-stone-600 ring-sand-200 hover:bg-sand-50",
                )}
              >
                {f.label} <span className="ml-1 opacity-70">{counts[f.value] ?? 0}</span>
              </button>
            ))}
          </div>

          <div className="relative sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
            <input
              type="search"
              aria-label="Search by name or code"
              placeholder="Search by name or code..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="min-h-[44px] w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>

          {shown.length === 0 ? (
            <Card>
              <EmptyState title="No matches" description="No claims match this filter or search." />
            </Card>
          ) : (
            <div>
              <p className="mb-2 text-xs text-stone-500">
                {shown.length === claims.length ? `${claims.length} claims` : `Showing ${shown.length} of ${claims.length} claims`}
                {shown.length > 6 && " · scroll inside the box to see everyone"}
              </p>
              <ScrollPanel label="Expense claims">
                <CardGrid>
                  {shown.map((claim) => (
                <div key={claim.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <Avatar name={claim.employee_name} employeeId={claim.employee_id} />
                      <div>
                        <p className="font-display text-sm font-semibold text-stone-800">{claim.employee_name}</p>
                        <p className="text-xs text-stone-400">{claim.employee_code}</p>
                      </div>
                    </div>
                    <Badge status={claim.status} label={STATUS_LABEL[claim.status]} />
                  </div>
                  <div className="flex items-center justify-between">
                    <Badge status={claim.category} label={EXPENSE_CATEGORY_LABEL[claim.category] ?? claim.category} />
                    <MaskedAmount amount={claim.amount} className="text-base text-stone-800" />
                  </div>
                  {claim.description && <p className="text-xs italic text-stone-400">"{claim.description}"</p>}
                  <p className="text-xs text-stone-500">
                    Sent on {formatTimestampDate(claim.created_at)}
                    {claim.status === "PAID" && claim.paid_date && ` · Paid on ${formatDateLong(claim.paid_date)}`}
                  </p>
                  {claim.status === "REJECTED" && (
                    <p className="rounded-lg bg-rose-50 p-2 text-xs text-rose-800">
                      <span className="font-semibold">Reason: </span>
                      {claim.rejection_reason || "No reason was written."}
                    </p>
                  )}
                  {claim.status === "PENDING" && claim.employee_id === user?.employee_id && (
                    <p className="border-t border-sand-100 pt-3 text-xs text-stone-500">This is your own claim, so someone else needs to decide on it.</p>
                  )}
                  {claim.status === "PENDING" && claim.employee_id !== user?.employee_id && (
                    <div className="flex gap-2 border-t border-sand-100 pt-3">
                      <Button size="sm" onClick={() => handleApprove(claim.id)} isLoading={isProcessing} icon={<Check className="h-4 w-4" />}>
                        Approve
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => setRejectTarget(claim)} icon={<X className="h-4 w-4" />}>
                        Reject
                      </Button>
                    </div>
                  )}
                  {claim.status === "APPROVED" && (
                    <button
                      className="flex w-fit items-center gap-1.5 border-t border-sand-100 pt-3 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => handlePay(claim.id)}
                    >
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                      Mark as paid
                    </button>
                  )}
                </div>
                  ))}
                </CardGrid>
              </ScrollPanel>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        isOpen={rejectTarget !== null}
        title="Reject this claim?"
        message={`${rejectTarget?.employee_name} will be notified that their claim wasn't approved.`}
        confirmLabel="Reject Claim"
        isDangerous
        isLoading={isProcessing}
        onConfirm={handleReject}
        onCancel={closeRejectDialog}
      >
        <TextareaField
          label="Reason (optional)"
          name="reject_reason"
          placeholder="Let them know why - they'll see this on their claim."
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  );
}
