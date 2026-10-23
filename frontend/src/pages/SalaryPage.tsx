import { Banknote, Check, ChevronRight, Download, History, PlayCircle, Search, Wallet } from "lucide-react";
import { useEffect, useState } from "react";

import { MaskedAmount } from "@/components/MaskedAmount";
import { MonthYearPicker } from "@/components/MonthYearPicker";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Avatar, CardGrid } from "@/components/ui/EntityCard";
import { InputField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { SalaryHistorySheet } from "@/components/SalaryHistorySheet";
import { attendanceBreakdownLine } from "@/utils/attendanceBreakdown";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getBlobErrorMessage, getErrorMessage } from "@/services/api";
import { formatDuration } from "@/utils/friendly";
import { attendanceService } from "@/services/attendanceService";
import { payrollService } from "@/services/payrollService";
import type { PayrollDirectoryEntry, SalaryPayment, SalaryRecord } from "@/types";
import { triggerBlobDownload } from "@/utils/downloadFile";
import { ROLE_LABEL } from "@/utils/plainWords";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export function SalaryPage() {
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const canManage = hasPermission("payroll:manage");

  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);

  const [records, setRecords] = useState<SalaryRecord[]>([]);
  const [payments, setPayments] = useState<SalaryPayment[]>([]);
  // Overtime minutes per employee for the viewed month - shown for information, never added to pay.
  const [overtime, setOvertime] = useState<Map<number, number>>(new Map());
  const [employees, setEmployees] = useState<PayrollDirectoryEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isSetOpen, setIsSetOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [employeeId, setEmployeeId] = useState("");
  const [basicPay, setBasicPay] = useState("");
  const [allowances, setAllowances] = useState("0");
  const [deductions, setDeductions] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().slice(0, 10));
  const [pendingSalary, setPendingSalary] = useState<{
    employeeId: number; name: string; code: string; basicPay: number; allowances: number; deductions: number;
    effectiveFrom: string; previous: SalaryRecord | null;
  } | null>(null);
  const [historyFor, setHistoryFor] = useState<{ id: number; name: string } | null>(null);
  const [runIssues, setRunIssues] = useState<{ missed: number; pending: number; noSalary: number } | null>(null);
  const [isCheckingIssues, setIsCheckingIssues] = useState(false);

  const [isRunConfirmOpen, setIsRunConfirmOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [markPaidTarget, setMarkPaidTarget] = useState<SalaryPayment | null>(null);
  const [isMarkingPaid, setIsMarkingPaid] = useState(false);

  const [paymentSearch, setPaymentSearch] = useState("");
  const [structureSearch, setStructureSearch] = useState("");

  // You can't set your own pay (the server refuses it too), so you are not offered in the list.
  const settableEmployees = employees.filter((e) => e.id !== user?.employee_id);
  const selectedEmployee = employees.find((e) => String(e.id) === employeeId);
  // Pay is worked out from attendance, so a month still in progress has no correct number yet -
  // payroll can only be run once every day of it is settled.
  const hasMonthEnded = (y: number, m: number) => y < today.getFullYear() || (y === today.getFullYear() && m < today.getMonth() + 1);
  const monthHasEnded = hasMonthEnded(year, month);

  const matchesSearch = (name: string, code: string, query: string) =>
    `${name} ${code}`.toLowerCase().includes(query.trim().toLowerCase());

  const filteredPayments = payments.filter((p) => matchesSearch(p.employee_name, p.employee_code, paymentSearch));
  const filteredRecords = records.filter((r) => matchesSearch(r.employee_name, r.employee_code, structureSearch));

  const paidCount = payments.filter((p) => p.status === "PAID").length;
  const pendingCount = payments.filter((p) => p.status === "PENDING").length;
  const totalPayrollAmount = payments.reduce((sum, p) => sum + p.amount, 0);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [recordList, paymentList, directory] = await Promise.all([
        payrollService.listSalaryRecords(),
        payrollService.listSalaryPayments(year, month),
        payrollService.getPayrollDirectory(),
      ]);
      setRecords(recordList);
      setPayments(paymentList);
      setEmployees(directory);
      // A nicety: if overtime can't be loaded the page works exactly as before.
      attendanceService
        .overtimeSummary(year, month)
        .then((rows) => setOvertime(new Map(rows.map((r) => [r.employee_id, r.overtime_minutes]))))
        .catch(() => setOvertime(new Map()));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load salary information."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month]);

  const openSet = () => {
    setEmployeeId("");
    setBasicPay("");
    setAllowances("0");
    setDeductions("0");
    setEffectiveFrom(new Date().toISOString().slice(0, 10));
    setIsSetOpen(true);
  };

  // Save just reviews it first - the ConfirmDialog below is what actually sends it, so nothing
  // changes anyone's pay until that second, deliberate tap.
  const handleReviewSet = () => {
    if (!employeeId || !basicPay) {
      showToast("Please choose an employee and enter the basic pay", "error");
      return;
    }
    if (Number(deductions || 0) > Number(basicPay) + Number(allowances || 0)) {
      showToast("Deductions can't be more than basic pay plus allowances", "error");
      return;
    }
    const employee = employees.find((e) => String(e.id) === employeeId);
    setPendingSalary({
      employeeId: Number(employeeId),
      name: employee?.full_name ?? "This employee",
      code: employee?.employee_code ?? "",
      basicPay: Number(basicPay),
      allowances: Number(allowances || 0),
      deductions: Number(deductions || 0),
      effectiveFrom,
      previous: records.find((r) => r.employee_id === Number(employeeId)) ?? null,
    });
    setIsSetOpen(false);
  };

  const handleConfirmSet = async () => {
    if (!pendingSalary) return;
    setIsSaving(true);
    try {
      await payrollService.setSalaryRecord({
        employee_id: pendingSalary.employeeId,
        basic_pay: pendingSalary.basicPay,
        allowances: pendingSalary.allowances,
        deductions: pendingSalary.deductions,
        effective_from: pendingSalary.effectiveFrom,
      });
      showToast(pendingSalary.previous ? "Salary updated" : "Salary set", "success");
      setPendingSalary(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsSaving(false);
    }
  };

  // Before asking "are you sure", look up whether anything is still open for this month (missed
  // check-outs, pending leave, people with no salary set) so it's not a surprise after the fact.
  const openRunConfirm = async () => {
    setIsRunConfirmOpen(true);
    setIsCheckingIssues(true);
    setRunIssues(null);
    try {
      const summary = await payrollService.attendanceSummary(year, month);
      setRunIssues({
        missed: summary.checklist.missed_check_outs,
        pending: summary.checklist.pending_leave_requests,
        noSalary: summary.checklist.employees_without_salary,
      });
    } catch {
      setRunIssues(null); // a nicety - Run Payroll still works if this lookup fails
    } finally {
      setIsCheckingIssues(false);
    }
  };

  const handleRunPayroll = async () => {
    setIsRunning(true);
    try {
      await payrollService.runPayroll(year, month);
      showToast("Payroll run complete", "success");
      setIsRunConfirmOpen(false);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsRunning(false);
    }
  };

  const handleMarkPaid = async () => {
    if (!markPaidTarget) return;
    setIsMarkingPaid(true);
    try {
      await payrollService.markSalaryPaid(markPaidTarget.id);
      showToast("Salary marked as paid", "success");
      setMarkPaidTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsMarkingPaid(false);
    }
  };

  const handleDownload = async (payment: SalaryPayment) => {
    setDownloadingId(payment.id);
    try {
      const { blob, filename } = await payrollService.downloadPayslip(payment.id);
      triggerBlobDownload(blob, filename);
    } catch (err) {
      showToast(await getBlobErrorMessage(err, "Couldn't download this payslip."), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <Banknote className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">Salary Records</h1>
            <p className="text-sm text-stone-500">Employee pay structures and monthly payroll</p>
          </div>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={openSet} icon={<Wallet className="h-4 w-4" />}>
              Set Salary
            </Button>
            <Button
              onClick={openRunConfirm}
              disabled={!monthHasEnded}
              title={monthHasEnded ? undefined : `Payroll can be run once ${MONTH_NAMES[month - 1]} ends, so every day's attendance is settled.`}
              icon={<PlayCircle className="h-4 w-4" />}
            >
              Run Payroll ({MONTH_NAMES[month - 1]})
            </Button>
          </div>
        )}
      </div>

      {canManage && (
        <div className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-sand-50 p-4 sm:flex-row sm:items-center sm:gap-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">1</span>
            <div>
              <p className="text-sm font-semibold text-stone-700">Set Salary</p>
              <p className="text-xs text-stone-500">Define what someone earns</p>
            </div>
          </div>
          <ChevronRight className="hidden h-4 w-4 shrink-0 text-stone-300 sm:block" aria-hidden="true" />
          <div className="flex items-center gap-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">2</span>
            <div>
              <p className="text-sm font-semibold text-stone-700">Run Payroll</p>
              <p className="text-xs text-stone-500">Generate this month's pay list</p>
            </div>
          </div>
          <ChevronRight className="hidden h-4 w-4 shrink-0 text-stone-300 sm:block" aria-hidden="true" />
          <div className="flex items-center gap-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">3</span>
            <div>
              <p className="text-sm font-semibold text-stone-700">Mark as Paid</p>
              <p className="text-xs text-stone-500">Confirm payment sent, unlocks payslip</p>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Loading..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <>
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-sm font-semibold text-stone-700">
                {MONTH_NAMES[month - 1]} {year} payroll
              </h2>
              <MonthYearPicker year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); }} />
            </div>
            <p className="mb-3 text-xs text-stone-500">
              This month's actual payments, generated by Run Payroll and confirmed one by one as Mark as Paid.
            </p>

            {payments.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-stone-500">
                <span>
                  <span className="font-semibold text-success-600">{paidCount}</span> paid
                </span>
                <span>
                  <span className="font-semibold text-sunset-600">{pendingCount}</span> pending
                </span>
                <span className="flex items-center gap-1">
                  Total this month:
                  <MaskedAmount amount={totalPayrollAmount} className="text-xs font-semibold text-stone-700" />
                </span>
              </div>
            )}

            {payments.length > 3 && (
              <div className="relative mb-3">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <input
                  type="text"
                  placeholder="Search this month's payments by name or code..."
                  value={paymentSearch}
                  onChange={(e) => setPaymentSearch(e.target.value)}
                  className="w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            )}

            {payments.length === 0 ? (
              <Card>
                <EmptyState
                  title={monthHasEnded ? "Payroll hasn't been run yet" : `${MONTH_NAMES[month - 1]} isn't over yet`}
                  description={
                    monthHasEnded
                      ? "Click Run Payroll to generate this month's payments."
                      : `Payroll can be run once ${MONTH_NAMES[month - 1]} ends, so every day's attendance is settled.`
                  }
                />
              </Card>
            ) : filteredPayments.length === 0 ? (
              <Card>
                <EmptyState title="No matches" description="No one in this month's payroll matches your search." />
              </Card>
            ) : (
              <>
                <p className="mb-2 text-xs text-stone-500">
                  {filteredPayments.length === payments.length
                    ? `${payments.length} payments`
                    : `Showing ${filteredPayments.length} of ${payments.length} payments`}
                  {filteredPayments.length > 6 && " · scroll inside the box to see everyone"}
                </p>
                <ScrollPanel label={`${MONTH_NAMES[month - 1]} ${year} payments`}>
                  <CardGrid>
                    {filteredPayments.map((payment) => (
                      <div key={payment.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center gap-3">
                          <Avatar name={payment.employee_name} employeeId={payment.employee_id} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-display text-sm font-semibold text-stone-800">{payment.employee_name}</p>
                            <p className="text-xs text-stone-400">{payment.employee_code}</p>
                          </div>
                          <Badge status={payment.status} />
                        </div>
                        <MaskedAmount amount={payment.amount} className="text-lg text-stone-800" />
                        {attendanceBreakdownLine(payment) && (
                          <p className="text-sm text-stone-500">{attendanceBreakdownLine(payment)}</p>
                        )}
                        {(overtime.get(payment.employee_id) ?? 0) > 0 && (
                          <p className="text-sm text-stone-500">
                            Overtime this month: <span className="font-semibold text-stone-700">{formatDuration(overtime.get(payment.employee_id) ?? 0)}</span>{" "}
                            (for information, not added to pay)
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sand-100 pt-3">
                          {canManage && payment.status === "PENDING" && !hasMonthEnded(payment.year, payment.month) && (
                            <span className="text-sm text-stone-500">
                              Can be paid once {MONTH_NAMES[payment.month - 1]} ends
                            </span>
                          )}
                          {canManage && payment.status === "PENDING" && hasMonthEnded(payment.year, payment.month) && payment.employee_id === user?.employee_id && (
                            <span className="text-sm text-stone-500">This is your own salary, so someone else needs to mark it as paid</span>
                          )}
                          {canManage && payment.status === "PENDING" && hasMonthEnded(payment.year, payment.month) && payment.employee_id !== user?.employee_id && (
                            <button
                              className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                              onClick={() => setMarkPaidTarget(payment)}
                            >
                              <Check className="h-3.5 w-3.5" aria-hidden="true" />
                              Mark as paid
                            </button>
                          )}
                          {payment.status === "PAID" && (
                            <button
                              className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline disabled:opacity-50"
                              onClick={() => handleDownload(payment)}
                              disabled={downloadingId === payment.id}
                            >
                              <Download className="h-3.5 w-3.5" aria-hidden="true" />
                              {downloadingId === payment.id ? "Preparing..." : "Download payslip"}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </CardGrid>
                </ScrollPanel>
              </>
            )}
          </div>

          <div>
            <h2 className="font-display text-sm font-semibold text-stone-700">What each employee earns</h2>
            <p className="mb-3 text-xs text-stone-500">
              Their standing pay rate — this doesn't change month to month unless you update it here.
            </p>

            {records.length > 3 && (
              <div className="relative mb-3">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <input
                  type="text"
                  placeholder="Search by name or code..."
                  value={structureSearch}
                  onChange={(e) => setStructureSearch(e.target.value)}
                  className="w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            )}

            {records.length === 0 ? (
              <Card>
                <EmptyState title="No salary structures set yet" description="Set a salary for someone to get started." />
              </Card>
            ) : filteredRecords.length === 0 ? (
              <Card>
                <EmptyState title="No matches" description="No one's pay rate matches your search." />
              </Card>
            ) : (
              <>
                <p className="mb-2 text-xs text-stone-500">
                  {filteredRecords.length === records.length
                    ? `${records.length} people`
                    : `Showing ${filteredRecords.length} of ${records.length} people`}
                  {filteredRecords.length > 6 && " · scroll inside the box to see everyone"}
                </p>
                <ScrollPanel label="Pay structures">
                  <CardGrid>
                    {filteredRecords.map((record) => (
                      <div key={record.id} className="flex flex-col gap-2 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center gap-3">
                          <Avatar name={record.employee_name} employeeId={record.employee_id} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-display text-sm font-semibold text-stone-800">{record.employee_name}</p>
                            <p className="text-xs text-stone-400">{record.employee_code}</p>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-xs text-stone-500">
                          <span>Net pay</span>
                          <MaskedAmount amount={record.net_pay} className="text-sm text-stone-800" />
                        </div>
                        <button
                          type="button"
                          onClick={() => setHistoryFor({ id: record.employee_id, name: record.employee_name })}
                          className="flex w-fit items-center gap-1.5 border-t border-sand-100 pt-2 text-xs font-semibold text-brand-600 hover:underline"
                        >
                          <History className="h-3.5 w-3.5" aria-hidden="true" />
                          Salary history
                        </button>
                      </div>
                    ))}
                  </CardGrid>
                </ScrollPanel>
              </>
            )}
          </div>
        </>
      )}

      <Modal
        title="Set Salary Structure"
        isOpen={isSetOpen}
        onClose={() => setIsSetOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsSetOpen(false)}>Cancel</Button>
            <Button onClick={handleReviewSet}>Review &amp; save</Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <SearchableSelect
            label="Employee"
            name="employee_id"
            required
            placeholder="Search by name, code, or department..."
            emptyLabel="Choose an employee"
            value={employeeId}
            onChange={setEmployeeId}
            options={settableEmployees}
            getId={(e) => String(e.id)}
            getLabel={(e) => `${e.full_name} (${e.employee_code})`}
            getDescription={(e) => `${e.designation}, ${e.department}`}
            getSearchText={(e) => `${e.full_name} ${e.employee_code} ${e.department} ${e.designation} ${e.role}`}
          />
          {selectedEmployee && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-2xl border border-sand-200 bg-sand-50 p-3 text-xs text-stone-600">
              <span className="text-stone-400">Role</span>
              <span className="font-semibold text-stone-700">{ROLE_LABEL[selectedEmployee.role] ?? selectedEmployee.role}</span>
              <span className="text-stone-400">Department</span>
              <span className="font-semibold text-stone-700">{selectedEmployee.department}</span>
              <span className="text-stone-400">Designation</span>
              <span className="font-semibold text-stone-700">{selectedEmployee.designation}</span>
              <span className="text-stone-400">Employee code</span>
              <span className="font-semibold text-stone-700">{selectedEmployee.employee_code}</span>
            </div>
          )}
          <InputField label="Basic pay" name="basic_pay" type="number" required value={basicPay} onChange={(e) => setBasicPay(e.target.value)} />
          <InputField label="Allowances" name="allowances" type="number" value={allowances} onChange={(e) => setAllowances(e.target.value)} />
          <InputField label="Deductions" name="deductions" type="number" value={deductions} onChange={(e) => setDeductions(e.target.value)} />
          <InputField label="Effective from" name="effective_from" type="date" required value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={pendingSalary !== null}
        title={pendingSalary ? `${pendingSalary.previous ? "Change" : "Set"} ${pendingSalary.name}'s salary?` : ""}
        message={
          pendingSalary
            ? `This ${pendingSalary.previous ? "changes" : "sets"} their net pay, starting from ${pendingSalary.effectiveFrom}.` +
              (pendingSalary.previous ? " Their earlier salary is kept in their history, not erased." : "")
            : ""
        }
        confirmLabel={pendingSalary?.previous ? "Yes, change it" : "Yes, set it"}
        isLoading={isSaving}
        onConfirm={handleConfirmSet}
        onCancel={() => {
          setPendingSalary(null);
          setIsSetOpen(true);
        }}
      >
        {/* The message above deliberately leaves the actual figures out - every other amount on this
            page stays masked until tapped, and this confirmation is no different. */}
        {pendingSalary && (
          <div className="flex items-center gap-2 rounded-xl bg-sand-50 p-3 text-sm text-stone-600">
            {pendingSalary.previous && (
              <>
                <MaskedAmount amount={pendingSalary.previous.net_pay} />
                <span aria-hidden="true">→</span>
              </>
            )}
            <MaskedAmount amount={pendingSalary.basicPay + pendingSalary.allowances - pendingSalary.deductions} />
            <span>net pay</span>
          </div>
        )}
      </ConfirmDialog>

      <SalaryHistorySheet
        employeeName={historyFor?.name ?? ""}
        isOpen={historyFor !== null}
        onClose={() => setHistoryFor(null)}
        fetcher={() => payrollService.salaryHistory(historyFor!.id)}
      />

      <ConfirmDialog
        isOpen={isRunConfirmOpen}
        title={`Run payroll for ${MONTH_NAMES[month - 1]} ${year}?`}
        message={
          "Each person is paid for the days they actually worked that month, not a flat salary - absent and " +
          "unpaid-leave days are not paid, and a half day is paid at half. It won't pay anyone automatically " +
          "— you still mark each one as paid." +
          (isCheckingIssues
            ? ""
            : runIssues && (runIssues.missed || runIssues.pending || runIssues.noSalary)
              ? "\n\nStill open for this month: " +
                [
                  runIssues.missed ? `${runIssues.missed} missed check-out${runIssues.missed === 1 ? "" : "s"}` : null,
                  runIssues.pending ? `${runIssues.pending} pending leave request${runIssues.pending === 1 ? "" : "s"}` : null,
                  runIssues.noSalary ? `${runIssues.noSalary} ${runIssues.noSalary === 1 ? "person" : "people"} with no salary set` : null,
                ]
                  .filter(Boolean)
                  .join(", ") +
                ". These affect pay for the days involved. You can run payroll anyway and fix them for next time."
              : ""
          )
        }
        confirmLabel="Run Payroll"
        isLoading={isRunning || isCheckingIssues}
        onConfirm={handleRunPayroll}
        onCancel={() => setIsRunConfirmOpen(false)}
      />

      <ConfirmDialog
        isOpen={markPaidTarget !== null}
        title={
          markPaidTarget
            ? `Mark ${markPaidTarget.employee_name}'s ${MONTH_NAMES[markPaidTarget.month - 1]} ${markPaidTarget.year} salary as paid?`
            : ""
        }
        message="This confirms the payment was actually made. It cannot be easily undone, and it unlocks their downloadable payslip."
        confirmLabel="Mark as Paid"
        isLoading={isMarkingPaid}
        onConfirm={handleMarkPaid}
        onCancel={() => setMarkPaidTarget(null)}
      />
    </div>
  );
}
