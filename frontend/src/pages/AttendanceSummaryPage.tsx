import clsx from "clsx";
import { AlertTriangle, CalendarRange, CheckCircle2, Download, Info, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { MonthYearPicker } from "@/components/MonthYearPicker";
import { PageHeader } from "@/components/PageHeader";
import { AmountsProvider, ShowAmountsSwitch } from "@/components/ShowAmounts";
import { Card } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/EntityCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { Td } from "@/components/ui/Table";
import { usePayslipDownload } from "@/hooks/usePayslipDownload";
import { useToast } from "@/hooks/useToast";
import { getBlobErrorMessage, getErrorMessage } from "@/services/api";
import { payrollService } from "@/services/payrollService";
import type { AttendanceSummary, AttendanceSummaryRow } from "@/types";
import { formatDateLong, monthName, plural } from "@/utils/friendly";
import { triggerBlobDownload } from "@/utils/downloadFile";

// Header cells stay visible when the table is scrolled down; the Employee column also when it is scrolled right.
const HEAD_CELL =
  "sticky top-0 z-20 whitespace-nowrap border-b border-sand-200 bg-white px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-stone-500";
const HEAD_COLUMNS = ["Total days", "Working days", "Present", "Late", "Half day", "Paid leave", "Unpaid leave", "Absent", "Days off", "Payable days", "Days cut", "Monthly salary", "Pay by attendance", "On payslip", "Difference"];

const days = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

function Count({ n, tone }: { n: number; tone?: "bad" | "good" }) {
  return <span className={clsx("tabular-nums", n === 0 && "text-stone-300", n > 0 && tone === "bad" && "font-semibold text-rose-700")}>{n}</span>;
}

function IssueChips({ row }: { row: AttendanceSummaryRow }) {
  if (!row.missed_check_outs && !row.pending_leave_requests) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {row.missed_check_outs > 0 && (
        <span className="rounded-full bg-amber-50 px-2.5 py-1 text-sm font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
          {plural(row.missed_check_outs, "missed check-out")}
        </span>
      )}
      {row.pending_leave_requests > 0 && (
        <span className="rounded-full bg-sky-50 px-2.5 py-1 text-sm font-semibold text-sky-800 ring-1 ring-inset ring-sky-600/20">
          {plural(row.pending_leave_requests, "leave request")} waiting
        </span>
      )}
    </div>
  );
}

/** Payslip minus pay by attendance: amber if the payslip pays more, blue if less, green when they match. */
function Difference({ value }: { value: number | null }) {
  if (value === null) return <span className="text-stone-400">-</span>;
  if (value === 0) return <span className="font-semibold text-success-700">Matches</span>;
  return (
    <span className={clsx("inline-flex items-center gap-0.5 font-semibold", value > 0 ? "text-amber-700" : "text-sky-700")}>
      {value > 0 ? "+" : "-"}
      <MaskedAmount amount={Math.abs(value)} className={value > 0 ? "text-amber-700" : "text-sky-700"} />
    </span>
  );
}

/** What Run Payroll made for the month: the amount, whether it is paid, and the PDF once it is. */
function PayslipCell({ row, onDownload, isDownloading }: { row: AttendanceSummaryRow; onDownload: (id: number) => void; isDownloading: boolean }) {
  if (row.payslip_amount === null) return <span className="text-stone-400">Not created yet</span>;
  return (
    <div className="flex flex-col items-start gap-1">
      <MaskedAmount amount={row.payslip_amount} className="text-stone-800" />
      <span
        className={clsx(
          "rounded-full px-2.5 py-0.5 text-sm font-semibold ring-1 ring-inset",
          row.payslip_status === "PAID" ? "bg-success-50 text-success-800 ring-success-600/20" : "bg-sunset-50 text-sunset-800 ring-sunset-600/20",
        )}
      >
        {row.payslip_status === "PAID" ? `Paid${row.payslip_paid_date ? ` ${formatDateLong(row.payslip_paid_date)}` : ""}` : "Pending"}
      </span>
      {row.payslip_status === "PAID" && row.payslip_id !== null && (
        <button
          type="button"
          onClick={() => onDownload(row.payslip_id as number)}
          disabled={isDownloading}
          className="inline-flex min-h-[44px] items-center gap-1.5 text-base font-semibold text-brand-700 hover:underline disabled:opacity-50"
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          {isDownloading ? "Preparing..." : "Payslip"}
        </button>
      )}
    </div>
  );
}

function ChecklistRow({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  const Icon = ok ? CheckCircle2 : AlertTriangle;
  return (
    <li className={clsx("flex items-start gap-3 text-base", ok ? "text-stone-500" : "font-semibold text-amber-900")}>
      <Icon className={clsx("mt-0.5 h-5 w-5 flex-shrink-0", ok ? "text-success-500" : "text-amber-600")} aria-hidden="true" />
      <span>{children}</span>
    </li>
  );
}

function AttendanceSummaryContent() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<AttendanceSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const { download, downloadingId } = usePayslipDownload();
  const { showToast } = useToast();
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const { blob, filename } = await payrollService.downloadAttendanceSummary(year, month);
      triggerBlobDownload(blob, filename);
    } catch (err) {
      showToast(await getBlobErrorMessage(err, "We couldn't download the Excel file."), "error");
    } finally {
      setIsExporting(false);
    }
  };

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setData(await payrollService.attendanceSummary(year, month));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load the attendance summary."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (data?.items ?? []).filter((r) => !needle || `${r.employee_name} ${r.employee_code}`.toLowerCase().includes(needle));
  }, [data, search]);

  const c = data?.checklist;
  const nothingOpen =
    c && !c.missed_check_outs && !c.pending_leave_requests && !c.employees_without_salary && c.missed_check_outs_in_other_months.length === 0;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={CalendarRange} title="Attendance Summary" subtitle="Days worked and pay for each person, month by month" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <MonthYearPicker year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); }} />
          <p className="text-base text-stone-500">{data ? `${data.total_days} days in this month` : " "}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleExport}
            disabled={isExporting || !data}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border-2 border-sand-200 bg-white px-4 text-base font-semibold text-stone-700 hover:border-brand-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-5 w-5 text-stone-500" aria-hidden="true" />
            {isExporting ? "Preparing..." : "Download Excel"}
          </button>
          <ShowAmountsSwitch />
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-base text-sky-900">
        <Info className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
        <p>
          {data && !data.month_ended ? (
            <>
              <span className="font-semibold">{monthName(month)} is still in progress.</span> These are the days so far; the pay for the month is worked out once it ends.
            </>
          ) : (
            <>
              <span className="font-semibold">These are the real numbers.</span> This is exactly what Run Payroll pays for {monthName(month)} {year} - not just a preview.
            </>
          )}
        </p>
      </div>

      {isLoading ? (
        <LoadingState label="Counting the days..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !data ? null : (
        <>
          <Card>
            <h2 className="font-display text-lg font-bold text-stone-800">Before you pay</h2>
            <p className="mb-3 text-base text-stone-500">These are warnings, not locks. Please clear them where you can.</p>
            <ul className="flex flex-col gap-2.5">
              <ChecklistRow ok={c!.missed_check_outs === 0}>
                {c!.missed_check_outs === 0
                  ? `No missed check-outs in ${monthName(month)} ${year}.`
                  : `${plural(c!.missed_check_outs, "missed check-out")} in ${monthName(month)} ${year}. Managers or HR can fix them so the hours are right.`}
              </ChecklistRow>
              {c!.missed_check_outs_in_other_months.length > 0 && (
                <li className="flex items-start gap-3 text-base font-semibold text-amber-900">
                  <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" aria-hidden="true" />
                  <div>
                    <p>Still open in other months. These are not counted above because they belong to those months:</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {c!.missed_check_outs_in_other_months.map((m) => (
                        <button
                          key={`${m.year}-${m.month}`}
                          type="button"
                          onClick={() => {
                            setYear(m.year);
                            setMonth(m.month);
                          }}
                          className="min-h-[44px] rounded-full bg-amber-50 px-4 text-sm font-semibold text-amber-900 ring-1 ring-inset ring-amber-600/30 hover:bg-amber-100"
                        >
                          {monthName(m.month)} {m.year} · {m.count}
                        </button>
                      ))}
                    </div>
                  </div>
                </li>
              )}
              <ChecklistRow ok={c!.pending_leave_requests === 0}>
                {c!.pending_leave_requests === 0 ? "No leave requests waiting." : `${plural(c!.pending_leave_requests, "leave request")} still waiting. Until decided, those days count as absent.`}
              </ChecklistRow>
              <ChecklistRow ok={c!.employees_without_salary === 0}>
                {c!.employees_without_salary === 0 ? "Everyone has a salary set." : `${plural(c!.employees_without_salary, "active employee")} ${c!.employees_without_salary === 1 ? "has" : "have"} no salary set, so ${c!.employees_without_salary === 1 ? "is" : "are"} not listed below.`}
              </ChecklistRow>
              <ChecklistRow ok={c!.absent_days === 0}>
                {c!.absent_days === 0 ? "No absent days." : `${plural(c!.absent_days, "absent day")} in total. Please make sure none are mistakes: a manager or HR can mark a day as present if someone forgot to check in.`}
              </ChecklistRow>
            </ul>
            {nothingOpen && <p className="mt-3 text-base font-semibold text-success-700">Nothing is waiting. The numbers below are ready to check.</p>}
          </Card>

          <Card>
            <h2 className="font-display text-lg font-bold text-stone-800">For everyone ({plural(data.items.length, "person", "people")})</h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                ["Monthly salary", data.total_monthly_salary, "The full salary, before any cut"],
                ["Pay by attendance", data.total_pay, data.month_ended ? "After the cut for absent days" : "Shows after the month ends"],
                ["On payslips", data.total_on_payslips, data.total_on_payslips === null ? "Payroll has not run for this month" : "What Run Payroll created"],
              ].map(([label, value, note]) => (
                <div key={label as string} className="rounded-2xl bg-sand-50 p-3">
                  <dt className="text-sm font-semibold text-stone-500">{label}</dt>
                  <dd className="font-display text-xl font-bold text-stone-800">
                    {value !== null ? <MaskedAmount amount={value as number} className="text-stone-800" /> : <span className="text-stone-400">-</span>}
                  </dd>
                  <p className="text-sm text-stone-500">{note}</p>
                </div>
              ))}
              <div className="rounded-2xl bg-sand-50 p-3">
                <dt className="text-sm font-semibold text-stone-500">Difference</dt>
                <dd className="font-display text-xl font-bold"><Difference value={data.total_difference} /></dd>
                <p className="text-sm text-stone-500">Payslip minus pay by attendance</p>
              </div>
            </dl>
            <p className="mt-3 text-base text-stone-500">
              A difference here usually means this payslip was created before payroll started paying by attendance - recalculating it with
              today's rule gives a different number. A payslip from a new payroll run should normally match exactly.
            </p>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" aria-hidden="true" />
              <input
                type="search"
                aria-label="Search by name or code"
                placeholder="Search by name or code..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="min-h-[48px] w-full rounded-xl border-2 border-sand-200 py-2 pl-10 pr-3 text-base text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>
          </div>

          {rows.length === 0 ? (
            <Card>
              <EmptyState
                title={data.items.length === 0 ? "No one to show" : "No matches"}
                description={data.items.length === 0 ? "Set up salaries first. People appear here once they have a salary." : "No one matches your search."}
              />
            </Card>
          ) : (
            <>
              <p className="text-xs text-stone-500">
                {rows.length === data.items.length ? `${data.items.length} people` : `Showing ${rows.length} of ${data.items.length} people`}
                {rows.length > 6 && " · scroll inside the box to see everyone"}
              </p>

              {/* Big screens: one row per person, in a table that scrolls inside its own box */}
              <div
                role="region"
                aria-label="Attendance summary table"
                tabIndex={0}
                className="hidden max-h-[min(38rem,68vh)] overflow-auto overscroll-contain rounded-2xl border border-sand-200 bg-white shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 lg:block"
              >
                <table className="min-w-full text-sm">
                  <thead>
                    <tr>
                      <th className={clsx(HEAD_CELL, "left-0 z-30 border-r border-sand-100")}>Employee</th>
                      {HEAD_COLUMNS.map((label) => (
                        <th key={label} className={HEAD_CELL}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-sand-100 text-base">
                    {rows.map((r) => (
                      <tr key={r.employee_id}>
                        <Td className="sticky left-0 z-10 min-w-[11rem] whitespace-normal border-r border-sand-100 bg-white">
                          <p className="font-semibold text-stone-800">{r.employee_name}</p>
                          <p className="text-sm text-stone-500">{r.employee_code}</p>
                          <IssueChips row={r} />
                        </Td>
                        <Td className="font-semibold tabular-nums">{r.total_days}</Td>
                        <Td className="font-semibold tabular-nums">{r.working_days}</Td>
                        <Td><Count n={r.present} /></Td>
                        <Td><Count n={r.late} /></Td>
                        <Td><Count n={r.half_day} /></Td>
                        <Td><Count n={r.paid_leave} /></Td>
                        <Td><Count n={r.unpaid_leave} tone="bad" /></Td>
                        <Td><Count n={r.absent} tone="bad" /></Td>
                        <Td><Count n={r.days_off} /></Td>
                        <Td className="font-semibold tabular-nums text-brand-800">{days(r.payable_days)}</Td>
                        <Td className={clsx("tabular-nums", r.cut_days > 0 ? "font-semibold text-rose-700" : "text-stone-300")}>{days(r.cut_days)}</Td>
                        <Td><MaskedAmount amount={r.monthly_salary} className="text-stone-800" /></Td>
                        <Td>{r.pay_for_month !== null ? <MaskedAmount amount={r.pay_for_month} className="text-stone-800" /> : <span className="text-stone-400">After month ends</span>}</Td>
                        <Td className="whitespace-normal"><PayslipCell row={r} onDownload={download} isDownloading={downloadingId === r.payslip_id} /></Td>
                        <Td><Difference value={r.difference} /></Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Phones and tablets: one card per person, in a box that scrolls on its own */}
              <ScrollPanel label="Attendance summary cards" className="lg:hidden">
                  <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {rows.map((r) => (
                      <li key={r.employee_id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                        <div className="flex items-start gap-3">
                          <Avatar name={r.employee_name} employeeId={r.employee_id} />
                          <div className="min-w-0 flex-1">
                            <p className="break-words font-display text-lg font-bold text-stone-800">{r.employee_name}</p>
                            <p className="text-base text-stone-500">{r.employee_code}</p>
                            <IssueChips row={r} />
                          </div>
                        </div>
                        <p className="text-base text-stone-700">
                          {r.open_days > 0 ? (
                            <>
                              Paid so far for <span className="font-bold text-success-800">{days(r.payable_days)}</span> days
                              {r.cut_days > 0 && <span className="font-semibold text-rose-700"> · {days(r.cut_days)} cut</span>}
                              <span className="text-stone-500"> · {plural(r.open_days, "day")} still to come</span>
                            </>
                          ) : (
                            <>
                              Paid for <span className="font-bold text-success-800">{days(r.payable_days)}</span> of {r.total_days} days
                              {r.cut_days > 0 && <span className="font-semibold text-rose-700"> · {days(r.cut_days)} cut</span>}
                            </>
                          )}
                        </p>
                        <dl className="grid grid-cols-3 gap-2 text-center">
                          {[
                            ["Total days", r.total_days],
                          ["Working days", r.working_days],
                            ["Present", r.present],
                            ["Late", r.late],
                            ["Half day", r.half_day],
                            ["Paid leave", r.paid_leave],
                            ["Unpaid leave", r.unpaid_leave],
                            ["Half-day leave", r.half_leave],
                            ["Absent", r.absent],
                            ["Days off", r.days_off],
                          ].map(([label, value]) => (
                            <div key={label as string} className="rounded-xl bg-sand-50 px-2 py-2">
                              <dd className="font-display text-xl font-bold tabular-nums text-stone-800">{value}</dd>
                              <dt className="text-sm text-stone-500">{label}</dt>
                            </div>
                          ))}
                        </dl>
                        <div className="grid grid-cols-2 gap-3 border-t border-sand-100 pt-3 text-base">
                          <div>
                            <p className="text-sm font-semibold text-stone-500">Monthly salary</p>
                            <MaskedAmount amount={r.monthly_salary} className="text-lg text-stone-800" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-stone-500">Pay by attendance</p>
                            {r.pay_for_month !== null ? <MaskedAmount amount={r.pay_for_month} className="text-lg text-stone-800" /> : <span className="text-stone-400">After the month ends</span>}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-stone-500">On payslip</p>
                            <PayslipCell row={r} onDownload={download} isDownloading={downloadingId === r.payslip_id} />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-stone-500">Difference</p>
                            <Difference value={r.difference} />
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
              </ScrollPanel>
            </>
          )}
        </>
      )}
    </div>
  );
}

export function AttendanceSummaryPage() {
  return (
    <AmountsProvider>
      <AttendanceSummaryContent />
    </AmountsProvider>
  );
}
