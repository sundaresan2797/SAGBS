import { useEffect, useState } from "react";

import { CorrectAttendanceSheet, type CorrectAttendanceTarget } from "@/components/CorrectAttendanceSheet";
import { FixCheckOutSheet, type FixTarget } from "@/components/FixCheckOutSheet";
import { MarkPresentSheet, type MarkPresentTarget } from "@/components/MarkPresentSheet";

import { DayDetail, MonthCalendar, buildDayContext } from "@/components/MonthCalendar";
import { LoadingState } from "@/components/ui/StateViews";
import { useAttendanceMonth } from "@/hooks/useAttendanceMonth";
import { useAttendancePolicy } from "@/hooks/useAttendancePolicy";
import { leaveService } from "@/services/leaveService";
import { classifyDay } from "@/utils/attendanceDays";
import { fetchAllPages } from "@/utils/paging";
import { toIsoDate } from "@/utils/taskHelpers";
import type { LeaveRequest } from "@/types";

/**
 * One person's month, loading its own data. Used where a manager/HR opens
 * someone else's calendar; My Attendance builds the same pieces itself
 * because it also needs the numbers for its summary.
 */
export function AttendanceCalendar({
  employeeId,
  employeeName,
  canFix = false,
  initialDate,
  onFixed,
}: {
  employeeId: number;
  /** Open on this day's month with the day already selected (for example the roll-call date). */
  initialDate?: string;
  employeeName?: string;
  /** True for a manager/HR looking at someone else: shows Fix check-out and the long-day flag. */
  canFix?: boolean;
  onFixed?: () => void;
}) {
  const policy = useAttendancePolicy();
  const [fixTarget, setFixTarget] = useState<FixTarget | null>(null);
  const [markTarget, setMarkTarget] = useState<MarkPresentTarget | null>(null);
  const [correctTarget, setCorrectTarget] = useState<CorrectAttendanceTarget | null>(null);
  const now = new Date();
  const todayIso = toIsoDate(now);
  const [year, setYear] = useState(initialDate ? Number(initialDate.slice(0, 4)) : now.getFullYear());
  const [month, setMonth] = useState(initialDate ? Number(initialDate.slice(5, 7)) : now.getMonth() + 1);
  const [selected, setSelected] = useState<string | null>(initialDate ?? null);
  const [leaves, setLeaves] = useState<LeaveRequest[] | undefined>(undefined);
  const { records, holidays, isLoading, error, reload } = useAttendanceMonth(employeeId, year, month);

  // Loaded once per person, independent of which month is showing - the same list tells "blank = Absent"
  // from "blank = On leave" apart, whichever month you scroll to.
  useEffect(() => {
    setLeaves(undefined);
    fetchAllPages((page) => leaveService.forEmployee(employeeId, page, 100)).then(setLeaves).catch(() => undefined);
  }, [employeeId]);

  const canGoNext = year < now.getFullYear() || (year === now.getFullYear() && month < now.getMonth() + 1);

  const go = (delta: number) => {
    let m = month + delta;
    let y = year;
    if (m < 1) {
      m = 12;
      y -= 1;
    } else if (m > 12) {
      m = 1;
      y += 1;
    }
    setMonth(m);
    setYear(y);
    setSelected(null);
  };

  if (error) return <p className="py-6 text-center text-base text-sunset-600">{error}</p>;

  return (
    <div className="flex flex-col gap-3">
      {isLoading ? (
        <LoadingState label="Loading calendar..." />
      ) : (
        <MonthCalendar
          year={year}
          month={month}
          records={records}
          holidays={holidays}
          leaves={leaves}
          todayIso={todayIso}
          selectedDate={selected}
          onSelect={setSelected}
          onPrev={() => go(-1)}
          onNext={() => go(1)}
          canGoNext={canGoNext}
          onJump={(y, m) => {
            setYear(y);
            setMonth(m);
            setSelected(null);
          }}
        />
      )}
      {selected && !isLoading && (
        <DayDetail
          iso={selected}
          info={classifyDay(selected, buildDayContext(records, holidays, todayIso, leaves))}
          manager={
            canFix
              ? {
                  longDayMinutes: policy?.long_day_minutes,
                  onMarkPresent: (iso) =>
                    setMarkTarget({ employeeId, employeeName: employeeName ?? "This employee", dateIso: iso }),
                  onFix: (record) =>
                    record.check_in &&
                    setFixTarget({
                      attendanceId: record.id,
                      employeeName: employeeName ?? "This employee",
                      dateIso: record.attendance_date,
                      checkIn: record.check_in,
                      lateMinutes: record.late_minutes,
                    }),
                  onCorrect: (iso, record) =>
                    setCorrectTarget({
                      employeeId,
                      employeeName: employeeName ?? "This employee",
                      dateIso: iso,
                      currentStatus: record?.status ?? "ABSENT",
                      checkIn: record?.check_in ?? null,
                      checkOut: record?.check_out ?? null,
                    }),
                }
              : undefined
          }
        />
      )}
      <MarkPresentSheet
        target={markTarget}
        onClose={() => setMarkTarget(null)}
        onSaved={() => {
          setMarkTarget(null);
          reload();
          onFixed?.();
        }}
      />
      <FixCheckOutSheet
        target={fixTarget}
        onClose={() => setFixTarget(null)}
        onFixed={() => {
          setFixTarget(null);
          reload();
          onFixed?.();
        }}
      />
      <CorrectAttendanceSheet
        target={correctTarget}
        onClose={() => setCorrectTarget(null)}
        onSaved={() => {
          setCorrectTarget(null);
          reload();
          onFixed?.();
        }}
      />
    </div>
  );
}
