import clsx from "clsx";
import { Banknote, Hourglass, Receipt, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { MaskedAmount } from "@/components/MaskedAmount";
import { Card } from "@/components/ui/Card";
import { payrollService } from "@/services/payrollService";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

interface Glance {
  paidCount: number;
  pendingCount: number;
  totalAmount: number;
  pendingAmount: number;
  claimsCount: number;
  // null when there are more claims than one page holds, so a partial sum is never shown as the total.
  claimsAmount: number | null;
  // Salary still unpaid from months before this one - never visible in this month's own counts.
  earlierCount: number;
  earlierAmount: number;
}

function GlanceCard({
  to,
  linkLabel,
  icon: Icon,
  tone = "brand",
  label,
  value,
  children,
}: {
  to: string;
  linkLabel: string;
  icon: LucideIcon;
  tone?: "brand" | "sunset";
  label: string;
  value: string;
  children?: ReactNode;
}) {
  // The card is deliberately not one big link: the masked amount inside is a
  // button, and a button nested in a link would navigate away on every reveal.
  return (
    <Card className="flex h-full items-start gap-4">
      <div
        className={clsx(
          "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl",
          tone === "brand" ? "bg-brand-50 text-brand-600" : "bg-sunset-50 text-sunset-600",
        )}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-stone-500">{label}</span>
        <span className="font-display text-xl font-semibold text-stone-800">{value}</span>
        {children}
        <Link to={to} className="mt-1.5 w-fit text-xs font-semibold text-brand-600 hover:underline">
          {linkLabel}
        </Link>
      </div>
    </Card>
  );
}

// The owner's at-a-glance view of money: this month's payroll and the expense
// claims waiting for a decision. Amounts stay masked like everywhere else.
export function PayrollGlance() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;

  const [glance, setGlance] = useState<Glance | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      payrollService.listSalaryPayments(year, month),
      payrollService.allExpenseClaims("PENDING", 1, 100),
      payrollService.unpaidEarlier(year, month),
    ])
      .then(([payments, claims, earlier]) => {
        if (cancelled) return;
        setGlance({
          paidCount: payments.filter((p) => p.status === "PAID").length,
          pendingCount: payments.filter((p) => p.status === "PENDING").length,
          totalAmount: payments.reduce((sum, p) => sum + p.amount, 0),
          pendingAmount: payments.filter((p) => p.status === "PENDING").reduce((sum, p) => sum + p.amount, 0),
          claimsCount: claims.total,
          claimsAmount:
            claims.items.length === claims.total ? claims.items.reduce((sum, c) => sum + c.amount, 0) : null,
          earlierCount: earlier.count,
          earlierAmount: earlier.total_amount,
        });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [year, month]);

  return (
    <section aria-label="Money this month" className="flex flex-col gap-3">
      <h2 className="font-display text-sm font-semibold text-stone-700">Money this month</h2>
      {failed ? (
        <p className="text-sm text-stone-500">We couldn&apos;t load the payroll summary right now.</p>
      ) : !glance ? (
        <p className="text-sm text-stone-400">Loading...</p>
      ) : (
        <div className={clsx("grid grid-cols-1 gap-3 sm:grid-cols-2", glance.earlierCount > 0 ? "lg:grid-cols-4" : "lg:grid-cols-3")}>
          <GlanceCard
            to="/payroll"
            linkLabel="Open Salary Records"
            icon={Banknote}
            label={`Payroll for ${MONTH_NAMES[month - 1]}`}
            value={
              glance.paidCount + glance.pendingCount === 0
                ? "Not run yet"
                : `${glance.paidCount} of ${glance.paidCount + glance.pendingCount} paid`
            }
          >
            {glance.paidCount + glance.pendingCount > 0 && (
              <span className="flex items-center gap-1 text-xs text-stone-400">
                Total: <MaskedAmount amount={glance.totalAmount} className="text-xs text-stone-600" />
              </span>
            )}
          </GlanceCard>

          <GlanceCard
            to="/payroll"
            linkLabel={glance.pendingCount > 0 ? "Mark people as paid" : "Open Salary Records"}
            icon={Hourglass}
            tone="sunset"
            label="Salary still to pay"
            value={
              glance.paidCount + glance.pendingCount === 0
                ? "Nothing yet"
                : glance.pendingCount === 0
                  ? "All paid"
                  : `${glance.pendingCount} ${glance.pendingCount === 1 ? "person" : "people"}`
            }
          >
            {glance.pendingCount > 0 && (
              <span className="flex items-center gap-1 text-xs text-stone-400">
                Amount: <MaskedAmount amount={glance.pendingAmount} className="text-xs text-stone-600" />
              </span>
            )}
          </GlanceCard>

          {glance.earlierCount > 0 && (
            <GlanceCard
              to="/payroll"
              linkLabel="Open Salary Records"
              icon={Hourglass}
              tone="sunset"
              label="Unpaid from earlier months"
              value={`${glance.earlierCount} ${glance.earlierCount === 1 ? "payment" : "payments"}`}
            >
              <span className="flex items-center gap-1 text-xs text-stone-400">
                Amount: <MaskedAmount amount={glance.earlierAmount} className="text-xs text-stone-600" />
              </span>
            </GlanceCard>
          )}

          <GlanceCard
            to="/expenses"
            linkLabel="Review claims"
            icon={Receipt}
            tone="sunset"
            label="Expense claims waiting"
            value={glance.claimsCount === 0 ? "None waiting" : `${glance.claimsCount} to review`}
          >
            {glance.claimsCount > 0 && glance.claimsAmount !== null && (
              <span className="flex items-center gap-1 text-xs text-stone-400">
                Amount: <MaskedAmount amount={glance.claimsAmount} className="text-xs text-stone-600" />
              </span>
            )}
          </GlanceCard>
        </div>
      )}
    </section>
  );
}
