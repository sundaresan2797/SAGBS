import clsx from "clsx";
import { CalendarDays, Check, Eye, Hourglass, Search, Undo2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { leaveService } from "@/services/leaveService";
import type { LeaveRequest, LeaveRequestStatus } from "@/types";
import { formatDateRange, formatTimestampDate, leaveLengthLabel } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { toIsoDate } from "@/utils/taskHelpers";

// The lists are narrowed with these chips, so a long list stays easy to work through.
const STATUS_FILTERS: { value: LeaveRequestStatus | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "PENDING", label: "Waiting" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Not approved" },
  { value: "CANCELLED", label: "Cancelled" },
];

function RequestCard({
  request,
  actionable,
  onApprove,
  onReject,
  isProcessing,
  onTakeBack,
}: {
  request: LeaveRequest;
  actionable: boolean;
  onApprove: (id: number) => void;
  onReject: (request: LeaveRequest) => void;
  isProcessing: boolean;
  /** Given only when the viewer may take back leave that was recorded for someone (never their own). */
  onTakeBack?: (request: LeaveRequest) => void;
}) {
  const todayIso = toIsoDate(new Date());
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <Avatar name={request.employee_name} employeeId={request.employee_id} />
          <div>
            <p className="font-display text-sm font-semibold text-stone-800">{request.employee_name}</p>
            <p className="text-xs text-stone-400">{request.employee_code}</p>
          </div>
        </div>
        <Badge status={request.status} />
      </div>
      <div className="flex flex-col gap-1.5 text-sm text-stone-600">
        <p className="font-medium">{request.leave_type_name}</p>
        <div className="flex items-center gap-1.5 text-xs text-stone-500">
          <CalendarDays className="h-3.5 w-3.5 text-stone-400" aria-hidden="true" />
          {formatDateRange(request.start_date, request.end_date)} &middot; {leaveLengthLabel(request.number_of_days, request.day_part)}
        </div>
        {request.recorded_by_name ? (
          <p className="text-xs font-semibold text-sky-700">
            Recorded by {request.recorded_by_name} on {formatTimestampDate(request.created_at)}
            {request.recorded_late && <span className="text-sunset-600"> &middot; entered for a day already past</span>}
          </p>
        ) : (
          <p className="text-xs text-stone-400">Sent on {formatTimestampDate(request.created_at)}</p>
        )}
        {request.reason && <p className="text-xs italic text-stone-400">"{request.reason}"</p>}
        {request.status === "PENDING" && !actionable && (
          <p className="text-xs font-semibold text-sky-700">
            {request.manager_name ? `Waiting for ${request.manager_name}` : "No manager to decide this"}
            {request.start_date < todayIso && <span className="text-sunset-600"> &middot; Start date has passed</span>}
          </p>
        )}
        {request.status === "REJECTED" && (
          <p className="rounded-lg bg-rose-50 p-2 text-xs text-rose-800">
            <span className="font-semibold">Reason: </span>
            {request.rejection_reason || "No reason was written."}
          </p>
        )}
      </div>
      {onTakeBack && request.status === "APPROVED" && request.recorded_by_name && (
        <div className="border-t border-sand-100 pt-3">
          <Button size="sm" variant="secondary" onClick={() => onTakeBack(request)} icon={<Undo2 className="h-4 w-4" />}>
            Take back
          </Button>
        </div>
      )}
      {actionable && request.status === "PENDING" && (
        <div className="flex gap-2 border-t border-sand-100 pt-3">
          <Button
            size="sm"
            onClick={() => onApprove(request.id)}
            isLoading={isProcessing}
            icon={<Check className="h-4 w-4" />}
          >
            Approve
          </Button>
          <Button size="sm" variant="danger" onClick={() => onReject(request)} icon={<X className="h-4 w-4" />}>
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}

export function LeaveRequestsPage() {
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  // Leave is decided by a direct manager, so a login with no employee profile (the Admin) has no team to show.
  const canApproveTeam = hasPermission("leave:approve_team") && Boolean(user?.employee_id);
  const canViewAll = hasPermission("leave:manage_all");

  const [teamRequests, setTeamRequests] = useState<LeaveRequest[]>([]);
  const [allRequests, setAllRequests] = useState<LeaveRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<LeaveRequest | null>(null);
  const [takeBackTarget, setTakeBackTarget] = useState<LeaveRequest | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusFilter, setStatusFilter] = useState<LeaveRequestStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [year, setYear] = useState<YearValue>(new Date().getFullYear()); // this year to begin with

  // `quiet` refreshes without the loading screen, so a list keeps its scroll position after Approve / Reject.
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [team, all] = await Promise.all([
        canApproveTeam ? fetchAllPages((page) => leaveService.teamRequests(undefined, page, 100, yearParam(year))) : Promise.resolve([]),
        canViewAll ? fetchAllPages((page) => leaveService.allRequests(undefined, page, 100, yearParam(year))) : Promise.resolve([]),
      ]);
      setTeamRequests(team);
      setAllRequests(all);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load leave requests."));
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
  }, [canApproveTeam, canViewAll, year]);

  // Managers, HR, the Founder and Admin may take back leave they recorded by mistake - never their own leave
  // (the server checks the same). It gives the days back to the balance and tells the employee.
  const canTakeBack = hasPermission("attendance:read_all") || hasPermission("attendance:read_team");
  const takeBackFor = (request: LeaveRequest) =>
    canTakeBack && request.employee_id !== user?.employee_id ? setTakeBackTarget : undefined;

  const handleTakeBack = async () => {
    if (!takeBackTarget) return;
    setIsProcessing(true);
    try {
      await leaveService.cancel(takeBackTarget.id);
      showToast("Leave taken back", "success");
      setTakeBackTarget(null);
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setTakeBackTarget(null);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleApprove = async (id: number) => {
    setIsProcessing(true);
    try {
      await leaveService.approve(id);
      showToast("Leave approved!", "success");
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
      await leaveService.reject(rejectTarget.id, rejectReason.trim() || undefined);
      showToast("Leave request rejected", "success");
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsProcessing(false);
      closeRejectDialog();
    }
  };

  const teamIds = new Set(teamRequests.map((r) => r.id));
  const otherCompanyRequests = allRequests.filter((r) => !teamIds.has(r.id));

  const pending = teamRequests.filter((r) => r.status === "PENDING");

  // One status chip and one search box narrow both lists on the page.
  const everyRequest = useMemo(() => [...teamRequests, ...otherCompanyRequests], [teamRequests, otherCompanyRequests]);
  const counts = useMemo(() => {
    const result: Record<string, number> = { ALL: everyRequest.length };
    for (const r of everyRequest) result[r.status] = (result[r.status] ?? 0) + 1;
    return result;
  }, [everyRequest]);
  const matches = (r: LeaveRequest) =>
    (statusFilter === "ALL" || r.status === statusFilter) &&
    (!search.trim() || `${r.employee_name} ${r.employee_code}`.toLowerCase().includes(search.trim().toLowerCase()));
  // Waiting requests come first in the team list.
  const teamShown = [...teamRequests.filter((r) => r.status === "PENDING"), ...teamRequests.filter((r) => r.status !== "PENDING")].filter(matches);
  const companyShown = otherCompanyRequests.filter(matches);

  const isEmpty = teamRequests.length === 0 && otherCompanyRequests.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <Hourglass className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">{canApproveTeam ? "Leave Requests" : "All Leave Requests"}</h1>
          <p className="text-sm text-stone-500">
            {canApproveTeam
              ? `${pending.length} waiting for your decision`
              : `${allRequests.filter((r) => r.status === "PENDING").length} waiting for their managers to decide`}
          </p>
        </div>
      </div>

      <YearFilter value={year} onChange={setYear} className="self-start" />

      {isLoading ? (
        <LoadingState label="Loading requests..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : isEmpty ? (
        <Card>
          <EmptyState
            title={year === "ALL" ? "No leave requests" : `No leave requests in ${year}`}
            description={year === "ALL" ? "Requests from your team will show up here." : "Pick another year, or All years, to see older requests."}
          />
        </Card>
      ) : (
        <>
          <div role="group" aria-label="Show requests that are" className="flex flex-wrap gap-2">
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

          {canApproveTeam && (
            <div className="flex flex-col gap-3">
              <h2 className="font-display text-sm font-semibold text-stone-700">Your team's requests</h2>
              {teamRequests.length === 0 ? (
                <Card>
                  <EmptyState title="No requests from your direct reports yet." />
                </Card>
              ) : teamShown.length === 0 ? (
                <Card>
                  <EmptyState title="No matches" description="No request from your team matches this filter or search." />
                </Card>
              ) : (
                <div>
                  <p className="mb-2 text-xs text-stone-500">
                    {teamShown.length === teamRequests.length ? `${teamRequests.length} requests` : `Showing ${teamShown.length} of ${teamRequests.length} requests`}
                    {teamShown.length > 6 && " · scroll inside the box to see everyone"}
                  </p>
                  <ScrollPanel label="Your team's leave requests">
                    <CardGrid>
                      {teamShown.map((request) => (
                        <RequestCard
                          key={request.id}
                          request={request}
                          actionable
                          onApprove={handleApprove}
                          onReject={setRejectTarget}
                          isProcessing={isProcessing}
                          onTakeBack={takeBackFor(request)}
                        />
                      ))}
                    </CardGrid>
                  </ScrollPanel>
                </div>
              )}
            </div>
          )}

          {canViewAll && otherCompanyRequests.length > 0 && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Eye className="h-4 w-4 text-stone-400" aria-hidden="true" />
                <h2 className="font-display text-sm font-semibold text-stone-700">
                  Company-wide requests <span className="font-normal text-stone-400">(view only)</span>
                </h2>
              </div>
              <p className="-mt-2 text-xs text-stone-400">
                For visibility only. Only an employee's direct manager can approve or reject their leave.
              </p>
              {companyShown.length === 0 ? (
                <Card>
                  <EmptyState title="No matches" description="No company-wide request matches this filter or search." />
                </Card>
              ) : (
                <div>
                  <p className="mb-2 text-xs text-stone-500">
                    {companyShown.length === otherCompanyRequests.length ? `${otherCompanyRequests.length} requests` : `Showing ${companyShown.length} of ${otherCompanyRequests.length} requests`}
                    {companyShown.length > 6 && " · scroll inside the box to see everyone"}
                  </p>
                  <ScrollPanel label="Company-wide leave requests">
                    <CardGrid>
                      {companyShown.map((request) => (
                        <RequestCard
                          key={request.id}
                          request={request}
                          actionable={false}
                          onApprove={handleApprove}
                          onReject={setRejectTarget}
                          isProcessing={isProcessing}
                          onTakeBack={takeBackFor(request)}
                        />
                      ))}
                    </CardGrid>
                  </ScrollPanel>
                </div>
              )}
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        isOpen={takeBackTarget !== null}
        title="Take back this leave?"
        message={`${takeBackTarget?.employee_name}'s ${takeBackTarget?.leave_type_name} (${
          takeBackTarget ? formatDateRange(takeBackTarget.start_date, takeBackTarget.end_date) : ""
        }) will be cancelled and the days given back to their balance. They will be told. This is not possible for a month that has already been paid.`}
        confirmLabel="Yes, take it back"
        isDangerous
        isLoading={isProcessing}
        onConfirm={handleTakeBack}
        onCancel={() => setTakeBackTarget(null)}
      />

      <ConfirmDialog
        isOpen={rejectTarget !== null}
        title="Reject this leave request?"
        message={`${rejectTarget?.employee_name} will be notified that their request for ${rejectTarget?.number_of_days} day(s) of ${rejectTarget?.leave_type_name} was not approved.`}
        confirmLabel="Reject Request"
        isDangerous
        isLoading={isProcessing}
        onConfirm={handleReject}
        onCancel={closeRejectDialog}
      >
        <TextareaField
          label="Reason (optional)"
          name="reject_reason"
          placeholder="Let them know why - they'll see this on their leave request."
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  );
}
