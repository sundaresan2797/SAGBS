import { Banknote, Download, FileText, History, Hourglass } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { PageHeader } from "@/components/PageHeader";
import { AmountsProvider, ShowAmountsSwitch } from "@/components/ShowAmounts";
import { Badge } from "@/components/ui/Badge";
import { SalaryHistorySheet } from "@/components/SalaryHistorySheet";
import { attendanceBreakdownLine } from "@/utils/attendanceBreakdown";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { YearFilter, yearParam, type YearValue } from "@/components/YearFilter";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { usePayslipDownload } from "@/hooks/usePayslipDownload";
import { getErrorMessage } from "@/services/api";
import { payrollService } from "@/services/payrollService";
import type { SalaryPayment, SalaryRecord } from "@/types";
import { formatDateLong, monthName } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { SALARY_STATUS_LABEL } from "@/utils/plainWords";

function MyPayslipsContent() {
  const { download, downloadingId } = usePayslipDownload();
  const [record, setRecord] = useState<SalaryRecord | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [payments, setPayments] = useState<SalaryPayment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState<YearValue>(thisYear); // this year to begin with

  // `quiet` refreshes without the loading screen (used when only the year changes).
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [recordData, paymentList] = await Promise.all([
        payrollService.mySalaryRecord(),
        fetchAllPages((page) => payrollService.mySalaryPayments(page, 100, yearParam(year))),
      ]);
      setRecord(recordData);
      setPayments(paymentList);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your payslips."));
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

  // Newest month first, whatever order the server sends them in.
  const sorted = useMemo(() => [...payments].sort((a, b) => b.year * 12 + b.month - (a.year * 12 + a.month)), [payments]);
  const latestPaid = year === "ALL" || year === thisYear ? sorted.find((p) => p.status === "PAID") : undefined;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={Banknote} title="My Payslips" subtitle="Your salary and monthly payslips" />

      <YearFilter value={year} onChange={setYear} className="self-start" />

      {isLoading ? (
        <LoadingState label="Loading your payslips..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : (
        <>
          <div className="flex justify-end">
            <ShowAmountsSwitch />
          </div>

          {latestPaid && (
            <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-base font-semibold text-stone-500">Latest payslip</p>
                <p className="font-display text-2xl font-bold text-stone-800">
                  {monthName(latestPaid.month)} {latestPaid.year}
                </p>
                <p className="text-base text-stone-500">
                  {latestPaid.paid_date ? `Paid on ${formatDateLong(latestPaid.paid_date)}` : "Paid"} ·{" "}
                  <MaskedAmount amount={latestPaid.amount} className="text-stone-800" />
                </p>
              </div>
              <Button size="lg" isLoading={downloadingId === latestPaid.id} onClick={() => download(latestPaid.id)} icon={<Download className="h-5 w-5" />}>
                Download payslip
              </Button>
            </Card>
          )}

          <section aria-label="Salary each month" className="flex flex-col gap-3">
            <h2 className="font-display text-lg font-bold text-stone-800">Month by month</h2>
            {sorted.length === 0 ? (
              <Card>
                <EmptyState
                  title={year === "ALL" ? "No payslips yet" : `No payslips in ${year}`}
                  description={year === "ALL" || year === thisYear ? "Your payslip appears here after your salary for a month is paid." : "Pick another year, or All years, to see older payslips."}
                />
              </Card>
            ) : (
              <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {sorted.map((payment) => (
                  <li key={payment.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-display text-lg font-bold text-stone-800">
                          {monthName(payment.month)} {payment.year}
                        </p>
                        <p className="text-base text-stone-500">
                          {payment.status === "PAID" && payment.paid_date ? `Paid on ${formatDateLong(payment.paid_date)}` : "Salary for this month"}
                        </p>
                      </div>
                      <MaskedAmount amount={payment.amount} className="text-xl text-stone-800" />
                    </div>
                    {attendanceBreakdownLine(payment) && (
                      <p className="text-base text-stone-500">{attendanceBreakdownLine(payment)}</p>
                    )}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Badge status={payment.status} label={SALARY_STATUS_LABEL[payment.status]} size="lg" />
                      {payment.status === "PAID" ? (
                        <Button variant="secondary" isLoading={downloadingId === payment.id} onClick={() => download(payment.id)} icon={<FileText className="h-5 w-5" />}>
                          Payslip (PDF)
                        </Button>
                      ) : (
                        <span className="flex items-center gap-1.5 text-base text-stone-500">
                          <Hourglass className="h-4 w-4" aria-hidden="true" />
                          Payslip comes after payment
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="How your salary is made up" className="flex flex-col gap-3">
            <h2 className="font-display text-lg font-bold text-stone-800">How your salary is made up</h2>
            {!record ? (
              <Card>
                <EmptyState title="Your salary is not set up yet" description="Once the office sets up your salary, the details will show here." />
              </Card>
            ) : (
              <Card>
                <dl className="flex flex-col divide-y divide-sand-100 text-base">
                  <div className="flex items-center justify-between py-3">
                    <dt className="text-stone-600">Basic pay</dt>
                    <dd><MaskedAmount amount={record.basic_pay} className="text-stone-800" /></dd>
                  </div>
                  <div className="flex items-center justify-between py-3">
                    <dt className="text-stone-600">Allowances (added)</dt>
                    <dd><MaskedAmount amount={record.allowances} className="text-stone-800" /></dd>
                  </div>
                  <div className="flex items-center justify-between py-3">
                    <dt className="text-stone-600">Deductions (taken off)</dt>
                    <dd><MaskedAmount amount={record.deductions} className="text-stone-800" /></dd>
                  </div>
                  <div className="flex items-center justify-between py-3">
                    <dt className="font-semibold text-stone-800">You take home each month</dt>
                    <dd><MaskedAmount amount={record.net_pay} className="text-xl text-brand-700" /></dd>
                  </div>
                </dl>
                <p className="mt-1 text-base text-stone-500">Applies from {formatDateLong(record.effective_from)}</p>
                <button
                  type="button"
                  onClick={() => setShowHistory(true)}
                  className="mt-3 flex min-h-[44px] w-fit items-center gap-1.5 border-t border-sand-100 pt-3 text-base font-semibold text-brand-700 hover:underline"
                >
                  <History className="h-5 w-5" aria-hidden="true" />
                  See my salary history
                </button>
              </Card>
            )}
          </section>
        </>
      )}
      <SalaryHistorySheet
        employeeName="you"
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        fetcher={payrollService.mySalaryHistory}
      />
    </div>
  );
}

export function MyPayslipsPage() {
  return (
    <AmountsProvider>
      <MyPayslipsContent />
    </AmountsProvider>
  );
}
