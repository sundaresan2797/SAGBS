import { AlertTriangle, CheckCircle2, Eraser, Save, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { TextareaField } from "@/components/ui/FormField";
import { TimeOfDayField } from "@/components/ui/TimeOfDayField";
import { Sheet } from "@/components/ui/Sheet";
import { useAttendancePolicy } from "@/hooks/useAttendancePolicy";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { DAY_LABELS } from "@/utils/attendanceDays";
import { previewOutcome } from "@/utils/attendanceOutcome";
import { formatDay, hhmmToMinutes } from "@/utils/friendly";
import type { AttendanceStatus } from "@/types";

export interface CorrectAttendanceTarget {
  employeeId: number;
  employeeName: string;
  dateIso: string;
  currentStatus: AttendanceStatus;
  /** ISO timestamps of the existing record, to prefill the time pickers - null for a day with nothing recorded. */
  checkIn: string | null;
  checkOut: string | null;
}

type Mode = "set" | "clear";

function toHHMM(iso: string): string {
  const local = new Date(iso);
  return `${String(local.getHours()).padStart(2, "0")}:${String(local.getMinutes()).padStart(2, "0")}`;
}

/**
 * Correcting a day that is already recorded as Present, Late or Half day - unlike Fix check-out (only for a
 * missed check-out) and Mark as present (only for a day with no check-in at all), this is for a day that
 * already has a real record but the wrong one. Either give the real times - the status (Present/Late/Half
 * day) is worked out by the normal rules, never chosen by hand - or clear the day back to Absent.
 */
export function CorrectAttendanceSheet({
  target,
  onClose,
  onSaved,
}: {
  target: CorrectAttendanceTarget | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const policy = useAttendancePolicy();
  const [mode, setMode] = useState<Mode>("set");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (target) {
      setMode("set");
      setCheckIn(target.checkIn ? toHHMM(target.checkIn) : "");
      setCheckOut(target.checkOut ? toHHMM(target.checkOut) : "");
      setReason("");
      setFormError(null);
    }
  }, [target]);

  const preview =
    mode === "set" && checkIn && checkOut && policy
      ? previewOutcome(hhmmToMinutes(checkIn), hhmmToMinutes(checkOut), policy, hhmmToMinutes(checkIn) > hhmmToMinutes(policy.late_after))
      : null;

  const handleSave = async () => {
    if (!target) return;
    if (mode === "set") {
      if (!checkIn || !checkOut) return setFormError("Please choose both the time they came and the time they left.");
      if (hhmmToMinutes(checkOut) <= hhmmToMinutes(checkIn)) return setFormError("The time they left must be after the time they came.");
    }
    if (reason.trim().length < 3) return setFormError("Please write a short reason. The employee will see it.");
    setFormError(null);
    setIsSaving(true);
    try {
      await attendanceService.correctAttendance({
        employee_id: target.employeeId,
        attendance_date: target.dateIso,
        check_in_time: mode === "set" ? checkIn : undefined,
        check_out_time: mode === "set" ? checkOut : undefined,
        reason: reason.trim(),
      });
      showToast(mode === "set" ? "Attendance corrected" : "Attendance cleared", "success");
      onSaved();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Sheet
      title="Correct attendance"
      isOpen={target !== null}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={onClose}>Not now</Button>
          <Button
            size="lg"
            variant={mode === "clear" ? "danger" : "primary"}
            isLoading={isSaving}
            onClick={handleSave}
            icon={mode === "clear" ? <Eraser className="h-5 w-5" /> : <Save className="h-5 w-5" />}
          >
            {mode === "clear" ? "Clear to Absent" : "Save correction"}
          </Button>
        </>
      }
    >
      {target && (
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl bg-sand-50 p-4">
            <p className="font-display text-lg font-bold text-stone-800">{target.employeeName}</p>
            <p className="text-base text-stone-600">
              {formatDay(target.dateIso)} · currently {DAY_LABELS[target.currentStatus]}
            </p>
          </div>

          <div role="radiogroup" aria-label="What do you want to do?" className="grid grid-cols-2 gap-2">
            {(
              [
                ["set", "Set the correct times"],
                ["clear", "Clear it (mark Absent)"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={mode === value}
                onClick={() => setMode(value)}
                className={`min-h-[52px] rounded-xl border-2 px-3 text-base font-semibold ${
                  mode === value ? "border-brand-500 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === "set" ? (
            <>
              <div className="flex flex-col gap-4">
                <TimeOfDayField label="What time did they come?" name="correct_check_in" value={checkIn} onChange={setCheckIn} />
                <TimeOfDayField label="What time did they leave?" name="correct_check_out" value={checkOut} onChange={setCheckOut} />
              </div>
              {preview && (
                <div
                  className={`flex items-start gap-3 rounded-2xl p-4 text-base font-semibold ${
                    preview.good ? "bg-success-50 text-success-800" : "bg-amber-50 text-amber-900"
                  }`}
                >
                  {preview.good ? (
                    <CheckCircle2 className="mt-0.5 h-6 w-6 flex-shrink-0" aria-hidden="true" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0" aria-hidden="true" />
                  )}
                  {preview.text}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-start gap-3 rounded-2xl bg-amber-50 p-4 text-base font-semibold text-amber-900">
              <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0" aria-hidden="true" />
              This removes the record entirely. The day will count as Absent, the same as if nothing had ever been recorded.
            </div>
          )}

          <TextareaField
            label="Reason (the employee will see this)"
            name="correct_reason"
            placeholder={mode === "set" ? "For example: Actually left at 1pm, half day" : "For example: Wrong person checked in for this day"}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="text-base text-stone-500">It is recorded with your name, and the employee is told.</p>

          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}
