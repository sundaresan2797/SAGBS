import { useEffect, useState } from "react";

import { attendanceService } from "@/services/attendanceService";
import type { AttendancePolicy } from "@/types";

// The rules change rarely, so one fetch per page load is plenty.
let cached: AttendancePolicy | null = null;

/** The company's attendance rules, or null while loading / if they could not be loaded (screens then just leave the rule text out). */
export function useAttendancePolicy(): AttendancePolicy | null {
  const [policy, setPolicy] = useState<AttendancePolicy | null>(cached);

  useEffect(() => {
    if (cached) return;
    let cancelled = false;
    attendanceService
      .policy()
      .then((result) => {
        cached = result;
        if (!cancelled) setPolicy(result);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return policy;
}
