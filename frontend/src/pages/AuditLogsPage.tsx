import { ScrollText } from "lucide-react";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { YearFilter, yearParam, type YearValue } from "@/components/YearFilter";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { Td, Th, TableContainer } from "@/components/ui/Table";
import { getErrorMessage } from "@/services/api";
import { auditLogService } from "@/services/auditLogService";
import type { AuditLog } from "@/types";
import { AUDIT_ACTION_LABEL } from "@/utils/plainWords";

export function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<YearValue>(new Date().getFullYear()); // this year to begin with
  const [from, setFrom] = useState(""); // optional: narrow further inside the chosen year (or across all years)
  const [to, setTo] = useState("");
  const [action, setAction] = useState(""); // "" = every kind of action
  // Almost all of the log is check-ins and sign-ins, which bury the entries that matter - hidden unless asked for.
  const [hideRoutine, setHideRoutine] = useState(true);

  // The range sent to the server: the dates typed win, otherwise the whole chosen year. Times are the
  // viewer's own midnight / end of day.
  const range = () => {
    const y = yearParam(year);
    const start = from ? new Date(`${from}T00:00:00`) : y ? new Date(y, 0, 1) : undefined;
    const end = to ? new Date(`${to}T23:59:59.999`) : y ? new Date(y, 11, 31, 23, 59, 59, 999) : undefined;
    return { date_from: start?.toISOString(), date_to: end?.toISOString() };
  };

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await auditLogService.list({
        page,
        page_size: 25,
        action: action || undefined,
        hide_routine: action ? undefined : hideRoutine,
        ...range(),
      });
      setLogs(result.items);
      setTotalPages(result.total_pages);
      setTotal(result.total);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load audit logs."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, year, from, to, action, hideRoutine]);

  const changeFilter = (apply: () => void) => {
    apply();
    setPage(1); // a new filter starts again from the first page
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <ScrollText className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">Audit Logs</h1>
          <p className="text-sm text-stone-500">{total} entries</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <YearFilter value={year} onChange={(v) => changeFilter(() => setYear(v))} />
        <label className="flex items-center gap-2 text-base font-semibold text-stone-600">
          From
          <input type="date" value={from} max={to || undefined} onChange={(e) => changeFilter(() => setFrom(e.target.value))}
            className="min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-3 text-base text-stone-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100" />
        </label>
        <label className="flex items-center gap-2 text-base font-semibold text-stone-600">
          To
          <input type="date" value={to} min={from || undefined} onChange={(e) => changeFilter(() => setTo(e.target.value))}
            className="min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-3 text-base text-stone-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100" />
        </label>
        <label className="flex items-center gap-2 text-base font-semibold text-stone-600">
          Action
          <select
            value={action}
            onChange={(e) => changeFilter(() => setAction(e.target.value))}
            className="min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-3 text-base text-stone-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            <option value="">Everything</option>
            {Object.entries(AUDIT_ACTION_LABEL)
              .sort((a, b) => a[1].localeCompare(b[1]))
              .map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
          </select>
        </label>
        <label className={`flex min-h-[44px] cursor-pointer items-center gap-2 text-base font-semibold ${action ? "text-stone-300" : "text-stone-600"}`}>
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-2 border-sand-300 text-brand-600 focus:ring-brand-300"
            checked={hideRoutine}
            disabled={Boolean(action)}
            onChange={(e) => changeFilter(() => setHideRoutine(e.target.checked))}
          />
          Hide check-ins and sign-ins
        </label>
        {(from || to) && (
          <button type="button" onClick={() => changeFilter(() => { setFrom(""); setTo(""); })}
            className="min-h-[44px] rounded-xl px-3 text-base font-semibold text-brand-700 hover:bg-brand-50">
            Clear dates
          </button>
        )}
      </div>

      <Card className="p-0">
        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : logs.length === 0 ? (
          <EmptyState title="No audit log entries." />
        ) : (
          <>
            <TableContainer>
              <thead>
                <tr>
                  <Th>Time</Th>
                  <Th>Who</Th>
                  <Th>Action</Th>
                  <Th>Entity</Th>
                  <Th>Description</Th>
                  <Th>IP Address</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-100">
                {logs.map((log) => (
                  <tr key={log.id}>
                    <Td>{new Date(log.created_at).toLocaleString()}</Td>
                    <Td className="font-medium text-stone-800">{log.user_name ?? "—"}</Td>
                    <Td className="font-medium text-stone-800">{AUDIT_ACTION_LABEL[log.action] ?? log.action}</Td>
                    <Td>
                      {log.entity_type ? `${log.entity_type}${log.entity_id ? ` #${log.entity_id}` : ""}` : "—"}
                    </Td>
                    <Td className="max-w-xs truncate">{log.description ?? "—"}</Td>
                    <Td>{log.ip_address ?? "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </TableContainer>
            <div className="px-4 pb-4">
              <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
