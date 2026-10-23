import { useCallback, useEffect, useState } from "react";

import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { holidayService } from "@/services/holidayService";
import type { Attendance, Holiday } from "@/types";

// The holiday calendar rarely changes while someone is looking at attendance,
// so each year is fetched once and reused as they page between months.
const holidayCache = new Map<number, Holiday[]>();

async function holidaysFor(year: number): Promise<Holiday[]> {
  const cached = holidayCache.get(year);
  if (cached) return cached;
  const list = await holidayService.list(year);
  holidayCache.set(year, list);
  return list;
}

/** One person's attendance rows for one month, plus that year's holidays (needed to tell a day off from a missed day). */
export function useAttendanceMonth(employeeId: number | null | undefined, year: number, month: number) {
  const [records, setRecords] = useState<Attendance[]>([]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!employeeId) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    Promise.all([attendanceService.calendar(employeeId, year, month), holidaysFor(year).catch(() => [] as Holiday[])])
      .then(([rows, holidayList]) => {
        if (cancelled) return;
        setRecords(rows);
        setHolidays(holidayList);
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, "We couldn't load the attendance calendar."));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId, year, month, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  return { records, holidays, isLoading, error, reload };
}
