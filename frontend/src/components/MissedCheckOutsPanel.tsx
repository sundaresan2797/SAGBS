import { AlertTriangle, Wrench } from "lucide-react";
import { useEffect, useState } from "react";

import { FixCheckOutSheet, type FixTarget } from "@/components/FixCheckOutSheet";
import { Button } from "@/components/ui/Button";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { attendanceService } from "@/services/attendanceService";
import type { AttendanceWithEmployee } from "@/types";
import { formatClock, formatDay, formatDayShort, plural } from "@/utils/friendly";

// The list now covers a year, so dates from an earlier year say which year.
const dayLabel = (iso: string) => (Number(iso.slice(0, 4)) === new Date().getFullYear() ? formatDayShort(iso) : formatDay(iso));

const SHOWN_AT_FIRST = 5;

/** For managers, HR, Founder and Admin: everyone in their care who forgot to check out, each with a Fix button. */
export function MissedCheckOutsPanel({ reloadKey, onChanged }: { reloadKey: number; onChanged: () => void }) {
  const [items, setItems] = useState<AttendanceWithEmployee[]>([]);
  // How many actually exist server-side, before the list gets capped - lets us say so instead of
  // silently showing a partial list as if it were the whole thing.
  const [total, setTotal] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const [target, setTarget] = useState<FixTarget | null>(null);

  useEffect(() => {
    let cancelled = false;
    attendanceService
      .missedCheckOuts()
      .then((result) => {
        if (cancelled) return;
        setItems(result.items);
        setTotal(result.total);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  if (items.length === 0 && !target) return null;
  const visible = showAll ? items : items.slice(0, SHOWN_AT_FIRST);

  const rows = (
    <ul className="flex flex-col gap-2">
      {visible.map((item) => (
        <li key={item.id} className="flex flex-col gap-2 rounded-xl bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="break-words text-base font-semibold text-stone-800">{item.employee_name}</p>
            <p className="text-base text-stone-500">
              {dayLabel(item.attendance_date)} · in at {item.check_in ? formatClock(item.check_in) : "?"} · no check-out
            </p>
          </div>
          <Button
            variant="secondary"
            icon={<Wrench className="h-5 w-5" />}
            onClick={() =>
              item.check_in &&
              setTarget({
                attendanceId: item.id,
                employeeName: item.employee_name,
                dateIso: item.attendance_date,
                checkIn: item.check_in,
                lateMinutes: item.late_minutes,
              })
            }
          >
            Fix check-out
          </Button>
        </li>
      ))}
    </ul>
  );

  return (
    <section aria-label="Missed check-outs" className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-600" aria-hidden="true" />
        <div>
          <h2 className="font-display text-lg font-bold text-amber-900">{plural(total, "missed check-out")} to fix</h2>
          <p className="text-base text-amber-900">These people checked in but never checked out. Their hours are missing until you fix it.</p>
        </div>
      </div>
      {showAll ? (
        <ScrollPanel
          label="All missed check-outs"
          className="mt-3"
          maxHeight="max-h-[min(26rem,60vh)]"
          boxClass="rounded-2xl border border-amber-200 bg-white/60 p-3"
        >
          {rows}
        </ScrollPanel>
      ) : (
        <div className="mt-3">{rows}</div>
      )}
      {items.length > SHOWN_AT_FIRST && (
        <button
          type="button"
          onClick={() => setShowAll((s) => !s)}
          className="mt-2 min-h-[44px] rounded-xl px-3 text-base font-semibold text-amber-900 hover:bg-amber-100"
        >
          {showAll ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
      {/* total can exceed the capped list (see attendance_service.MISSED_CHECK_OUTS_LIMIT) - say so
          rather than let the list quietly look complete when it isn't. */}
      {total > items.length && (
        <p className="mt-2 text-sm text-amber-800">
          Showing the most recent {items.length} of {total} - fix some of these to see the rest.
        </p>
      )}
      <FixCheckOutSheet
        target={target}
        onClose={() => setTarget(null)}
        onFixed={() => {
          setTarget(null);
          onChanged();
        }}
      />
    </section>
  );
}
