import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import { attendanceService } from "@/services/attendanceService";
import { formatDayShort } from "@/utils/friendly";
import { isMissedCheckOut } from "@/utils/attendanceDays";
import { toIsoDate } from "@/utils/taskHelpers";

/**
 * A reminder (never a block) on the employee's own screens: days they checked in
 * but forgot to check out. They cannot fix these themselves - the note says who can.
 */
export function MissedCheckOutNotice() {
  const [days, setDays] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    attendanceService
      .myAttendance(1, 100)
      .then((result) => {
        if (cancelled) return;
        const today = toIsoDate(new Date());
        setDays(result.items.filter((r) => isMissedCheckOut(r, today)).map((r) => r.attendance_date).sort().reverse());
      })
      .catch(() => undefined); // a reminder is a nicety; the page works without it
    return () => {
      cancelled = true;
    };
  }, []);

  if (days.length === 0) return null;
  const shown = days.slice(0, 3).map(formatDayShort).join(", ");
  const extra = days.length > 3 ? ` and ${days.length - 3} more` : "";

  return (
    <div role="status" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-600" aria-hidden="true" />
      <p className="text-base text-amber-900">
        <span className="font-semibold">
          You forgot to check out on {shown}
          {extra}.
        </span>{" "}
        Please ask your manager or HR to fix {days.length === 1 ? "it" : "them"}. You can still check in as usual.
      </p>
    </div>
  );
}
