import { CalendarDays, CalendarPlus, CheckCircle2, Circle, Clock, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { YearFilter } from "@/components/YearFilter";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField, TextareaField } from "@/components/ui/FormField";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { leaveService } from "@/services/leaveService";
import { formatDateRange, formatDay, formatPermissionLength, leaveLengthLabel, parseIsoDate, plural } from "@/utils/friendly";
import { LEAVE_STATUS_LABEL } from "@/utils/plainWords";
import { fetchAllPages } from "@/utils/paging";
import { toIsoDate } from "@/utils/taskHelpers";
import type { LeaveBalance, LeaveDayPart, LeaveRequest, LeaveRequestStatus, LeaveType, PermissionList } from "@/types";

const GROUPS: { status: LeaveRequestStatus; title: string }[] = [
  { status: "PENDING", title: "Waiting for approval" },
  { status: "APPROVED", title: "Approved" },
  { status: "REJECTED", title: "Not approved" },
  { status: "CANCELLED", title: "Cancelled" },
];

function calendarDays(start: string, end: string): number {
  return Math.round((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / 86_400_000) + 1;
}

export function MyLeavePage() {
  const { showToast } = useToast();
  const { user } = useAuth();
  const todayIso = toIsoDate(new Date());

  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [balances, setBalances] = useState<LeaveBalance[]>([]); // for the year being looked at
  // Balances by year, so the Apply sheet can show the right year's numbers even when the selected
  // start date falls in a year other than the one this page is currently showing (or "this year").
  const [balanceCache, setBalanceCache] = useState<Record<number, LeaveBalance[]>>({});
  const pendingBalanceYears = useRef(new Set<number>());
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [typeId, setTypeId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [halfDay, setHalfDay] = useState(false);
  const [part, setPart] = useState<LeaveDayPart>("FIRST_HALF");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [permissions, setPermissions] = useState<PermissionList | null>(null);

  const [cancelTarget, setCancelTarget] = useState<LeaveRequest | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  // `quiet` refreshes without the loading screen (used when only the year changes).
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [types, balanceData, requestList, thisYearBalances] = await Promise.all([
        leaveService.listTypes(),
        leaveService.myBalance(year),
        fetchAllPages((page) => leaveService.myRequests(page, 100, year)),
        year === thisYear ? Promise.resolve(null) : leaveService.myBalance(thisYear),
      ]);
      setLeaveTypes(types);
      setBalances(balanceData);
      setBalanceCache((cache) => ({
        ...cache,
        [year]: balanceData,
        ...(thisYearBalances ? { [thisYear]: thisYearBalances } : {}),
      }));
      setRequests(requestList);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your leave information."));
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

  // This month's permissions (a few hours off, entered by your manager or HR). Failing to load is not an error
  // worth showing: the card just stays hidden.
  useEffect(() => {
    if (!user?.employee_id) return;
    const now = new Date();
    attendanceService
      .listPermissions(user.employee_id, now.getFullYear(), now.getMonth() + 1)
      .then(setPermissions)
      .catch(() => setPermissions(null));
  }, [user?.employee_id]);

  const openSheet = () => {
    setTypeId("");
    setStart("");
    setEnd("");
    setReason("");
    setHalfDay(false);
    setPart("FIRST_HALF");
    setFormError(null);
    setIsSheetOpen(true);
  };

  // The balance the Apply sheet should show: the year the selected leave actually STARTS in (matching
  // apply_leave's own balance check), falling back to this year before a start date is picked. Applying
  // in December for leave that starts in January needs next year's numbers, not this year's.
  const applyYear = start ? Number(start.slice(0, 4)) : thisYear;

  useEffect(() => {
    if (!isSheetOpen) return;
    if (balanceCache[applyYear] || pendingBalanceYears.current.has(applyYear)) return;
    pendingBalanceYears.current.add(applyYear);
    leaveService
      .myBalance(applyYear)
      .then((data) => setBalanceCache((cache) => ({ ...cache, [applyYear]: data })))
      .catch(() => undefined) // the radio list just falls back to "Paid leave" with no figure - see balanceFor
      .finally(() => pendingBalanceYears.current.delete(applyYear));
  }, [isSheetOpen, applyYear, balanceCache]);

  const balanceFor = (id: number) => balanceCache[applyYear]?.find((b) => b.leave_type_id === id);

  const handleSubmit = async () => {
    if (!typeId) return setFormError("Please choose what kind of leave you want.");
    if (!start) return setFormError("Please choose the first day of your leave.");
    if (start < todayIso) return setFormError("The first day can't be in the past.");
    if (!end) return setFormError("Please choose the last day of your leave.");
    if (end < start) return setFormError("The last day can't be before the first day.");
    if (halfDay && end !== start) return setFormError("A half day is for one day only. Use the same first and last day.");
    setFormError(null);
    setIsSubmitting(true);
    try {
      const created = await leaveService.apply({
        leave_type_id: Number(typeId),
        start_date: start,
        end_date: end,
        reason: reason.trim() || undefined,
        day_part: halfDay ? part : undefined,
      });
      // Only the Founder, with nobody above them, is approved on the spot.
      showToast(created.status === "APPROVED" ? "Your leave is approved" : "Your leave request was sent to your manager", "success");
      setIsSheetOpen(false);
      load();
    } catch (err) {
      // Kept inside the sheet (not just a toast) so the reason - "not enough leave left", "you already have leave on
      // those days" - stays in front of the person while they fix it.
      setFormError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!cancelTarget) return;
    setIsCancelling(true);
    try {
      await leaveService.cancel(cancelTarget.id);
      showToast("Your leave request was cancelled", "success");
      setCancelTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setCancelTarget(null);
    } finally {
      setIsCancelling(false);
    }
  };

  if (isLoading) return <LoadingState label="Loading your leave..." />;
  if (error) return <ErrorState message={error} onRetry={() => load()} />;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={CalendarDays}
        title="My Leave"
        subtitle="Ask for time off and see what happened to your requests"
        action={
          <Button size="lg" onClick={openSheet} icon={<CalendarPlus className="h-5 w-5" />} className="w-full sm:w-auto">
            Apply for leave
          </Button>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold text-stone-800">Your leave in {year}</h2>
        <YearFilter value={year} onChange={(v) => setYear(v === "ALL" ? thisYear : v)} withAll={false} />
      </div>

      {permissions && (
        <Card className="flex items-start gap-4">
          <Clock className="mt-0.5 h-8 w-8 flex-shrink-0 text-brand-600" aria-hidden="true" />
          <div>
            <p className="text-base font-semibold text-stone-600">Permission this month</p>
            <p className="font-display text-2xl font-bold text-stone-800">
              {permissions.used_this_month} of {permissions.monthly_limit} used
            </p>
            <p className="mt-1 text-base text-stone-500">
              A permission is a few hours off (up to {formatPermissionLength(permissions.max_minutes)}), paid. Tell your manager or HR and they will record it.
            </p>
            {permissions.items.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1 text-base text-stone-700">
                {permissions.items.map((p) => (
                  <li key={p.id}>
                    {formatDay(p.permission_date)} · {formatPermissionLength(p.minutes)} · {p.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {balances.map((b) => (
          <Card key={b.leave_type_id}>
            <p className="text-base font-semibold text-stone-600">{b.leave_type_name}</p>
            <p className="mt-1 font-display text-3xl font-bold text-stone-800">
              {b.remaining_days} <span className="text-lg font-semibold text-stone-500">days left</span>
            </p>
            <p className="mt-1 text-base text-stone-500">
              {b.used_days} used of {b.allocated_days}
              {b.accrual_frequency === "MONTHLY" ? " earned so far" : ""}
            </p>
          </Card>
        ))}
      </div>

      {requests.length === 0 ? (
        <Card>
          <EmptyState
            title={year === thisYear ? "You haven't asked for any leave yet" : `No leave requests in ${year}`}
            description={year === thisYear ? "When you do, you'll see what happened to it here." : "Pick another year to see older requests."}
          />
        </Card>
      ) : (
        GROUPS.map((group) => {
          const items = requests.filter((r) => r.status === group.status);
          if (items.length === 0) return null;
          return (
            <section key={group.status}>
              <h2 className="mb-2 font-display text-lg font-bold text-stone-800">
                {group.title} <span className="text-base font-semibold text-stone-400">({items.length})</span>
              </h2>
              <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {items.map((request) => (
                  <li key={request.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="font-display text-xl font-bold text-stone-800">{request.leave_type_name}</p>
                      <Badge size="lg" status={request.status} label={LEAVE_STATUS_LABEL[request.status]} />
                    </div>
                    <p className="flex items-center gap-2 text-base text-stone-700">
                      <CalendarDays className="h-5 w-5 flex-shrink-0 text-stone-400" aria-hidden="true" />
                      {formatDateRange(request.start_date, request.end_date)} · {leaveLengthLabel(request.number_of_days, request.day_part)}
                    </p>
                    {request.recorded_by_name ? (
                      <p className="rounded-xl bg-sky-50 p-3 text-base text-sky-900">
                        <span className="font-semibold">{request.recorded_by_name}</span> recorded this for you
                        {request.reason ? `: "${request.reason}"` : "."}
                      </p>
                    ) : (
                      request.reason && <p className="text-base text-stone-500">You wrote: "{request.reason}"</p>
                    )}
                    {request.status === "REJECTED" && (
                      <div className="rounded-xl bg-rose-50 p-3 text-base text-rose-800">
                        <p className="font-semibold">Why it wasn't approved</p>
                        <p>{request.rejection_reason || "Your manager didn't add a reason. You can ask them directly."}</p>
                      </div>
                    )}
                    {(request.status === "PENDING" || (request.status === "APPROVED" && request.start_date > todayIso)) && (
                      <Button variant="secondary" className="w-fit" onClick={() => setCancelTarget(request)}>
                        Cancel this request
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}

      <Sheet
        title="Apply for leave"
        isOpen={isSheetOpen}
        onClose={() => setIsSheetOpen(false)}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={() => setIsSheetOpen(false)}>Not now</Button>
            <Button size="lg" isLoading={isSubmitting} onClick={handleSubmit} icon={<CalendarPlus className="h-5 w-5" />}>
              Send request
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <fieldset>
            <legend className="mb-2 text-base font-semibold text-stone-700">What kind of leave?</legend>
            <div className="flex flex-col gap-2" role="radiogroup">
              {leaveTypes.map((type) => {
                const selected = String(type.id) === typeId;
                const balance = balanceFor(type.id);
                const Icon = selected ? CheckCircle2 : Circle;
                return (
                  <button
                    key={type.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setTypeId(String(type.id))}
                    className={`flex min-h-[64px] items-center gap-3 rounded-2xl border-2 px-4 py-3 text-left ${
                      selected ? "border-brand-500 bg-brand-50" : "border-sand-200 bg-white"
                    }`}
                  >
                    <Icon className={`h-6 w-6 flex-shrink-0 ${selected ? "text-brand-600" : "text-stone-300"}`} aria-hidden="true" />
                    <span className="flex-1">
                      <span className="block text-base font-semibold text-stone-800">{type.name}</span>
                      <span className="block text-base text-stone-500">
                        {type.is_paid ? (balance ? `${balance.remaining_days} days left` : "Paid leave") : "Unpaid leave - no salary for these days"}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <InputField
              label="First day"
              name="start_date"
              type="date"
              min={todayIso}
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                if (!end || end < e.target.value) setEnd(e.target.value);
              }}
            />
            <InputField
              label="Last day"
              name="end_date"
              type="date"
              min={start || todayIso}
              value={halfDay ? start : end}
              disabled={halfDay}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>

          <label className="flex min-h-[48px] cursor-pointer items-center gap-3 text-base font-semibold text-stone-700">
            <input
              type="checkbox"
              className="h-6 w-6 rounded border-2 border-sand-300 text-brand-600 focus:ring-brand-300"
              checked={halfDay}
              onChange={(e) => {
                setHalfDay(e.target.checked);
                if (e.target.checked) setEnd(start);
              }}
            />
            Only half a day
          </label>
          {halfDay && (
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Which half?">
              {(
                [
                  ["FIRST_HALF", "Morning off"],
                  ["SECOND_HALF", "Afternoon off"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={part === value}
                  onClick={() => setPart(value)}
                  className={`min-h-[48px] rounded-xl border-2 px-3 text-base font-semibold ${
                    part === value ? "border-brand-500 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {start && end && end >= start && (
            <p className="rounded-xl bg-sand-50 p-3 text-base text-stone-700">
              <span className="font-semibold">{formatDateRange(start, end)}</span>
              <br />
              {halfDay ? "Half a day of leave." : `${plural(calendarDays(start, end), "day")} on the calendar. Sundays and holidays are not counted as leave.`}
            </p>
          )}

          <TextareaField label="Reason (optional)" name="reason" value={reason} onChange={(e) => setReason(e.target.value)} />

          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      </Sheet>

      <ConfirmDialog
        isOpen={cancelTarget !== null}
        title="Cancel this leave request?"
        message={
          cancelTarget
            ? `${cancelTarget.leave_type_name}, ${formatDateRange(cancelTarget.start_date, cancelTarget.end_date)}. ${
                cancelTarget.status === "APPROVED" ? "Your leave days will be given back to your balance." : "Your manager will no longer see it."
              }`
            : ""
        }
        confirmLabel="Yes, cancel it"
        isDangerous
        isLoading={isCancelling}
        onConfirm={handleCancel}
        onCancel={() => setCancelTarget(null)}
      />
    </div>
  );
}
