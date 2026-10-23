import { History } from "lucide-react";
import { useEffect, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { getErrorMessage } from "@/services/api";
import type { SalaryRecord } from "@/types";
import { formatDateLong } from "@/utils/friendly";

/**
 * Every salary someone has ever had, oldest first - so a raise never hides what they started on.
 * `fetcher` is either "this one employee" (Accountant/Founder) or "my own" (My Payslips).
 */
export function SalaryHistorySheet({
  employeeName,
  isOpen,
  onClose,
  fetcher,
}: {
  /** A name ("Sara Khan"), or "you" for the employee's own history - the wording adjusts either way. */
  employeeName: string;
  isOpen: boolean;
  onClose: () => void;
  fetcher: () => Promise<SalaryRecord[]>;
}) {
  const isSelf = employeeName === "you";
  const [rows, setRows] = useState<SalaryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setRows(null);
    setError(null);
    fetcher()
      .then(setRows)
      .catch((err) => setError(getErrorMessage(err, "We couldn't load the salary history.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  return (
    <Sheet title="Salary history" isOpen={isOpen} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p className="text-base text-stone-600">
          Every salary {isSelf ? "you have had" : `${employeeName} has had`}, from when {isSelf ? "you started" : "they started"} to now.
        </p>
        {error ? (
          <ErrorState message={error} />
        ) : rows === null ? (
          <LoadingState label="Loading history..." />
        ) : rows.length === 0 ? (
          <EmptyState title="No salary has been set yet" description="Once a salary is set, it will show up here." />
        ) : (
          <ol className="flex flex-col gap-3">
            {rows.map((record, i) => {
              const isCurrent = i === rows.length - 1;
              return (
                <li key={record.id} className="flex items-start gap-3 rounded-2xl border border-sand-200 bg-white p-4">
                  <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-sand-100 text-stone-500">
                    <History className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-display text-lg font-bold text-stone-800">
                        {i === 0 ? "Started at" : "Changed to"} <MaskedAmount amount={record.net_pay} className="text-stone-800" />
                      </p>
                      {isCurrent && (
                        <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-sm font-semibold text-brand-800 ring-1 ring-inset ring-brand-600/20">
                          Current
                        </span>
                      )}
                    </div>
                    <p className="text-base text-stone-500">From {formatDateLong(record.effective_from)}</p>
                    <p className="mt-1 text-sm text-stone-500">
                      Basic <MaskedAmount amount={record.basic_pay} className="text-sm text-stone-600" /> · Allowances{" "}
                      <MaskedAmount amount={record.allowances} className="text-sm text-stone-600" /> · Deductions{" "}
                      <MaskedAmount amount={record.deductions} className="text-sm text-stone-600" />
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </Sheet>
  );
}
