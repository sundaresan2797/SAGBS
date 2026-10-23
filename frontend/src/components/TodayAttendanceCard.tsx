import { AlertTriangle, CheckCircle2, Clock, LogIn, LogOut, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Sheet } from "@/components/ui/Sheet";
import type { DayInfo } from "@/utils/attendanceDays";
import { useAttendancePolicy } from "@/hooks/useAttendancePolicy";
import { lunchMinutesWithin } from "@/utils/attendanceOutcome";
import { formatClock, formatDuration, formatHHMM, formatHoursWords, hhmmToMinutes } from "@/utils/friendly";
import type { Attendance, AttendancePolicy } from "@/types";

type Outcome = { good: boolean; text: string };

const minutesOfDay = (d: Date) => d.getHours() * 60 + d.getMinutes();

/** What tapping "Check in" right now will be recorded as - so nobody is surprised afterwards. */
function checkInOutcome(at: Date, policy: AttendancePolicy | null): Outcome | null {
  if (!policy) return null;
  const minutes = minutesOfDay(at);
  if (minutes > hhmmToMinutes(policy.half_day_after)) {
    return { good: false, text: `It is after ${formatHHMM(policy.half_day_after)}, so today will count as a half day.` };
  }
  if (minutes > hhmmToMinutes(policy.late_after)) {
    const late = formatDuration(minutes - hhmmToMinutes(policy.office_start));
    return { good: false, text: `You will be marked late (${late} after ${formatHHMM(policy.office_start)}).` };
  }
  return { good: true, text: "You are on time." };
}

/**
 * What tapping "Check out" right now will be recorded as. Mirrors attendance_rules.status_at_check_out
 * exactly, same order: half-day-cutoff, then under-minimum, then late, else present - so this can
 * never promise a better outcome than what actually gets saved.
 */
function checkOutOutcome(record: Attendance, at: Date, policy: AttendancePolicy | null): Outcome | null {
  if (!policy || !record.check_in) return null;
  const checkInAt = new Date(record.check_in);
  const rawWorked = (at.getTime() - checkInAt.getTime()) / 60000;
  const worked = rawWorked - lunchMinutesWithin(minutesOfDay(checkInAt), minutesOfDay(at), policy);
  if (minutesOfDay(checkInAt) > hhmmToMinutes(policy.half_day_after)) {
    return { good: false, text: `You checked in after ${formatHHMM(policy.half_day_after)}, so today counts as a half day.` };
  }
  if (worked < policy.full_day_minimum_minutes) {
    return {
      good: false,
      text: `Less than ${formatHoursWords(policy.full_day_minimum_minutes)} counts as a half day. You need ${formatDuration(policy.full_day_minimum_minutes - worked)} more for a full day.`,
    };
  }
  if (minutesOfDay(checkInAt) > hhmmToMinutes(policy.late_after)) {
    const late = formatDuration(minutesOfDay(checkInAt) - hhmmToMinutes(policy.office_start));
    return {
      good: false,
      text: `You checked in late (${late} after ${formatHHMM(policy.office_start)}), so today will be marked Late even though you've completed a full day.`,
    };
  }
  return { good: true, text: "You have completed a full day." };
}

/**
 * The one card for "where am I today?": what to do next (check in / check
 * out) in words, with a big button - and it knows about days off and leave.
 */
function TodayAttendanceCardBody({
  record,
  todayInfo,
  isMarking,
  policy,
  onCheckIn,
  onCheckOut,
}: {
  record: Attendance | null;
  todayInfo: DayInfo;
  isMarking: boolean;
  policy: AttendancePolicy | null;
  onCheckIn: () => void;
  onCheckOut: () => void;
}) {
  const [now, setNow] = useState(() => new Date());
  const working = Boolean(record?.check_in && !record?.check_out);

  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, [working]);

  // 1. Finished for the day
  if (record?.check_out && record.check_in) {
    return (
      <Card className="flex items-start gap-4 border-success-200 bg-success-50/60">
        <CheckCircle2 className="mt-0.5 h-9 w-9 flex-shrink-0 text-success-600" aria-hidden="true" />
        <div>
          <p className="font-display text-xl font-bold text-stone-800">You're done for today</p>
          <p className="mt-1 text-base text-stone-600">
            In at {formatClock(record.check_in)} · Out at {formatClock(record.check_out)}
            {record.working_minutes != null && ` · ${formatDuration(record.working_minutes)} worked`}
            {record.status === "LATE" && " · marked late"}
            {record.status === "HALF_DAY" && " · marked half day"}
          </p>
        </div>
      </Card>
    );
  }

  // 2. At work now
  if (record?.check_in) {
    const minutesSoFar = (now.getTime() - new Date(record.check_in).getTime()) / 60000;
    return (
      <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <Clock className="mt-0.5 h-9 w-9 flex-shrink-0 text-brand-600" aria-hidden="true" />
          <div>
            <p className="font-display text-xl font-bold text-stone-800">You're checked in</p>
            <p className="mt-1 text-base text-stone-600">
              Since {formatClock(record.check_in)} · {formatDuration(minutesSoFar)} so far
              {record.status === "LATE" && " · marked late"}
              {record.status === "HALF_DAY" && " · marked half day"}
            </p>
            {policy && (
              <p className="mt-1 text-base text-stone-500">
                {/* Before check-out, a half day can only come from arriving after the cut-off. */}
                {record.status === "HALF_DAY"
                  ? `You came after ${formatHHMM(policy.half_day_after)}, so today counts as a half day.`
                  : `Working less than ${formatHoursWords(policy.full_day_minimum_minutes)} counts as a half day.`}
              </p>
            )}
          </div>
        </div>
        <Button size="lg" variant="secondary" className="w-full sm:w-auto" isLoading={isMarking} onClick={onCheckOut} icon={<LogOut className="h-5 w-5" />}>
          Check out
        </Button>
      </Card>
    );
  }

  // 3. Not checked in - depends on what kind of day it is
  const isDayOff = todayInfo.kind === "DAY_OFF" || todayInfo.kind === "HOLIDAY";
  if (todayInfo.kind === "ON_LEAVE") {
    return (
      <Card className="flex items-start gap-4 border-sky-200 bg-sky-50/70">
        <Sun className="mt-0.5 h-9 w-9 flex-shrink-0 text-sky-600" aria-hidden="true" />
        <div>
          <p className="font-display text-xl font-bold text-stone-800">You're on leave today</p>
          <p className="mt-1 text-base text-stone-600">Your leave is approved, so there's nothing to do. Enjoy your time off.</p>
        </div>
      </Card>
    );
  }
  if (isDayOff) {
    return (
      <Card className="flex flex-col gap-4 border-sky-200 bg-sky-50/70 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <Sun className="mt-0.5 h-9 w-9 flex-shrink-0 text-sky-600" aria-hidden="true" />
          <div>
            <p className="font-display text-xl font-bold text-stone-800">Today is a day off</p>
            <p className="mt-1 text-base text-stone-600">{todayInfo.kind === "HOLIDAY" ? todayInfo.label : "It's Sunday"} - no need to check in.</p>
          </div>
        </div>
        <Button size="lg" variant="secondary" className="w-full sm:w-auto" isLoading={isMarking} onClick={onCheckIn} icon={<LogIn className="h-5 w-5" />}>
          I'm working today
        </Button>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-4">
        <Clock className="mt-0.5 h-9 w-9 flex-shrink-0 text-stone-400" aria-hidden="true" />
        <div>
          <p className="font-display text-xl font-bold text-stone-800">Ready to start your day?</p>
          <p className="mt-1 text-base text-stone-600">You haven't checked in yet.</p>
          {policy && (
            <div className="mt-2 flex flex-col gap-1 text-base text-stone-500">
              <p>
                Office starts at <span className="font-semibold text-stone-700">{formatHHMM(policy.office_start)}</span>.
                {policy.grace_minutes > 0
                  ? ` Check in by ${formatHHMM(policy.late_after)} to be on time.`
                  : " After that you are marked late."}
              </p>
              <p>
                It counts as a half day if you check in after {formatHHMM(policy.half_day_after)} or work less than{" "}
                {formatHoursWords(policy.full_day_minimum_minutes)}.
              </p>
            </div>
          )}
        </div>
      </div>
      <Button size="lg" className="w-full sm:w-auto" isLoading={isMarking} onClick={onCheckIn} icon={<LogIn className="h-5 w-5" />}>
        Check in
      </Button>
    </Card>
  );
}

/**
 * Shows today's attendance and asks "are you sure?" before the tap that
 * cannot be undone (one check-in and one check-out a day), spelling out
 * how the day will be recorded.
 */
export function TodayAttendanceCard({
  record,
  todayInfo,
  isMarking,
  onCheckIn,
  onCheckOut,
}: {
  record: Attendance | null;
  todayInfo: DayInfo;
  isMarking: boolean;
  onCheckIn: () => void;
  onCheckOut: () => void;
}) {
  const policy = useAttendancePolicy();
  const [asking, setAsking] = useState<"in" | "out" | null>(null);
  const [askedAt, setAskedAt] = useState(() => new Date()); // freezes the time shown in the question
  const ask = (kind: "in" | "out") => {
    setAskedAt(new Date());
    setAsking(kind);
  };
  const confirm = () => {
    const kind = asking;
    setAsking(null);
    if (kind === "in") onCheckIn();
    else if (kind === "out") onCheckOut();
  };

  const checkingIn = asking === "in";
  const outcome = checkingIn ? checkInOutcome(askedAt, policy) : record ? checkOutOutcome(record, askedAt, policy) : null;
  const isDayOff = todayInfo.kind === "DAY_OFF" || todayInfo.kind === "HOLIDAY";

  return (
    <>
      <TodayAttendanceCardBody
        record={record}
        todayInfo={todayInfo}
        isMarking={isMarking}
        policy={policy}
        onCheckIn={() => ask("in")}
        onCheckOut={() => ask("out")}
      />
      <Sheet
        title={checkingIn ? (isDayOff ? "Work today?" : "Check in now?") : "Check out now?"}
        isOpen={asking !== null}
        onClose={() => setAsking(null)}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={() => setAsking(null)}>
              Not yet
            </Button>
            <Button size="lg" onClick={confirm} icon={checkingIn ? <LogIn className="h-5 w-5" /> : <LogOut className="h-5 w-5" />}>
              {checkingIn ? "Yes, check in" : "Yes, check out"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <div>
            <p className="text-base text-stone-500">{checkingIn ? "Your check-in time will be" : "Your check-out time will be"}</p>
            <p className="font-display text-4xl font-bold text-stone-800">{formatClock(askedAt.toISOString())}</p>
            {!checkingIn && record?.check_in && (
              <p className="mt-1 text-base text-stone-600">
                You came in at {formatClock(record.check_in)} and have worked{" "}
                {formatDuration((askedAt.getTime() - new Date(record.check_in).getTime()) / 60000)} today.
              </p>
            )}
            {checkingIn && isDayOff && (
              <p className="mt-1 text-base text-stone-600">Today is a day off. Check in only if you are working today.</p>
            )}
          </div>
          {outcome && (
            <div
              className={`flex items-start gap-3 rounded-2xl p-4 text-base font-semibold ${
                outcome.good ? "bg-success-50 text-success-800" : "bg-amber-50 text-amber-900"
              }`}
            >
              {outcome.good ? (
                <CheckCircle2 className="mt-0.5 h-6 w-6 flex-shrink-0" aria-hidden="true" />
              ) : (
                <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0" aria-hidden="true" />
              )}
              {outcome.text}
            </div>
          )}
          <p className="text-base text-stone-500">
            {checkingIn
              ? "You can check in only once a day, so please tap “Yes” only when you are ready."
              : "You can check out only once a day, and you cannot check in again after that."}
          </p>
        </div>
      </Sheet>
    </>
  );
}
