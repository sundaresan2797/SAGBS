import clsx from "clsx";
import { Bus, CircleHelp, Hotel, Package, Plus, Receipt, Send, Utensils, XCircle, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { PageHeader } from "@/components/PageHeader";
import { AmountsProvider, ShowAmountsSwitch } from "@/components/ShowAmounts";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { YearFilter, yearParam, type YearValue } from "@/components/YearFilter";
import { InputField, TextareaField } from "@/components/ui/FormField";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { payrollService } from "@/services/payrollService";
import type { ExpenseClaim, ExpenseClaimCategory } from "@/types";
import { formatDateLong, formatTimestampDate, plural } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { EXPENSE_CATEGORY_LABEL, EXPENSE_STATUS_LABEL } from "@/utils/plainWords";

const CATEGORIES: { value: ExpenseClaimCategory; icon: LucideIcon }[] = [
  { value: "TRAVEL", icon: Bus },
  { value: "FOOD", icon: Utensils },
  { value: "MATERIALS", icon: Package },
  { value: "ACCOMMODATION", icon: Hotel },
  { value: "OTHER", icon: CircleHelp },
];

// What each status means for the person's money, in one line.
function statusNote(claim: ExpenseClaim): string | null {
  if (claim.status === "PAID") return claim.paid_date ? `Paid to you on ${formatDateLong(claim.paid_date)}` : "Paid to you";
  if (claim.status === "APPROVED") return "Approved. The money will be paid to you soon.";
  if (claim.status === "PENDING") return "The office is checking this.";
  return null;
}

function MyExpensesContent() {
  const { showToast } = useToast();
  const [claims, setClaims] = useState<ExpenseClaim[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [category, setCategory] = useState<ExpenseClaimCategory>("TRAVEL");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [year, setYear] = useState<YearValue>(new Date().getFullYear()); // this year to begin with

  // `quiet` refreshes without the loading screen (used when only the year changes).
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      setClaims(await fetchAllPages((page) => payrollService.myExpenseClaims(page, 100, yearParam(year))));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your expense claims."));
    } finally {
      setIsLoading(false);
    }
  };

  const loadedOnce = useRef(false);
  useEffect(() => {
    load(loadedOnce.current);
    loadedOnce.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const openSheet = () => {
    setCategory("TRAVEL");
    setAmount("");
    setDescription("");
    setFormError(null);
    setIsSheetOpen(true);
  };

  const handleSubmit = async () => {
    const value = Number(amount);
    if (!amount.trim() || !Number.isFinite(value) || value <= 0) {
      return setFormError("Please enter the amount you spent, for example 250.");
    }
    setFormError(null);
    setIsSubmitting(true);
    try {
      await payrollService.submitExpenseClaim({ category, amount: value, description: description.trim() || undefined });
      showToast("Your claim was sent", "success");
      setIsSheetOpen(false);
      load(true);
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const waiting = useMemo(() => claims.filter((c) => c.status === "PENDING" || c.status === "APPROVED"), [claims]);
  const sorted = useMemo(() => [...claims].sort((a, b) => b.created_at.localeCompare(a.created_at)), [claims]);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={Receipt}
        title="My Expenses"
        subtitle="Get back the money you spent for work"
        action={
          <Button size="lg" className="w-full sm:w-auto" onClick={openSheet} icon={<Plus className="h-5 w-5" />}>
            New claim
          </Button>
        }
      />

      <YearFilter value={year} onChange={setYear} className="self-start" />

      {isLoading ? (
        <LoadingState label="Loading your expenses..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : claims.length === 0 ? (
        <Card>
          <EmptyState
            title={year === "ALL" ? "No claims yet" : `No claims in ${year}`}
            description={year === new Date().getFullYear() || year === "ALL" ? "Spent money for work? Tap “New claim” to ask for it back." : "Pick another year, or All years, to see older claims."}
          />
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-base text-stone-600">
              {waiting.length > 0 ? (
                <>
                  <span className="font-semibold text-stone-800">{plural(waiting.length, "claim")}</span> still to be paid or decided
                </>
              ) : (
                "Nothing is waiting. All your claims are settled."
              )}
            </p>
            <ShowAmountsSwitch />
          </div>

          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {sorted.map((claim) => {
              const note = statusNote(claim);
              return (
                <li key={claim.id} className="flex flex-col gap-2 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-display text-lg font-bold text-stone-800">{EXPENSE_CATEGORY_LABEL[claim.category] ?? claim.category}</p>
                      <p className="text-base text-stone-500">Sent on {formatTimestampDate(claim.created_at)}</p>
                    </div>
                    <MaskedAmount amount={claim.amount} className="text-xl text-stone-800" />
                  </div>
                  {claim.description && <p className="break-words text-base text-stone-600">“{claim.description}”</p>}
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge status={claim.status} label={EXPENSE_STATUS_LABEL[claim.status]} size="lg" />
                  </div>
                  {note && <p className="text-base text-stone-500">{note}</p>}
                  {claim.status === "REJECTED" && (
                    <p className="rounded-xl bg-rose-50 p-3 text-base text-rose-800">
                      <span className="font-semibold">Why it wasn't approved: </span>
                      {claim.rejection_reason || "No reason was written. Please ask the accounts office."}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}

      <Sheet
        title="New expense claim"
        isOpen={isSheetOpen}
        onClose={() => setIsSheetOpen(false)}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={() => setIsSheetOpen(false)}>Not now</Button>
            <Button size="lg" isLoading={isSubmitting} onClick={handleSubmit} icon={<Send className="h-5 w-5" />}>
              Send claim
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <fieldset>
            <legend className="mb-2 text-base font-semibold text-stone-700">What did you spend on?</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {CATEGORIES.map(({ value, icon: Icon }) => (
                <label
                  key={value}
                  className={clsx(
                    "flex min-h-[64px] cursor-pointer items-center gap-3 rounded-xl border-2 px-3 py-2 text-base font-semibold",
                    category === value ? "border-brand-500 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700 hover:border-brand-200",
                  )}
                >
                  <input type="radio" name="category" value={value} checked={category === value} onChange={() => setCategory(value)} className="sr-only" />
                  <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                  {EXPENSE_CATEGORY_LABEL[value]}
                </label>
              ))}
            </div>
          </fieldset>

          <InputField
            label="How much did you spend? (₹)"
            name="amount"
            type="number"
            inputMode="decimal"
            min="1"
            placeholder="For example 250"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <TextareaField label="What was it for? (optional)" name="description" value={description} onChange={(e) => setDescription(e.target.value)} />

          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      </Sheet>
    </div>
  );
}

export function MyExpensesPage() {
  return (
    <AmountsProvider>
      <MyExpensesContent />
    </AmountsProvider>
  );
}
