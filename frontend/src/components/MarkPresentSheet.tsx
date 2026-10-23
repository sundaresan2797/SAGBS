import { AlertTriangle, CheckCircle2, Save, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { TextareaField } from "@/components/ui/FormField";
import { TimeOfDayField } from "@/components/ui/TimeOfDayField";
import { Sheet } from "@/components/ui/Sheet";
import { useAttendancePolicy } from "@/hooks/useAttendancePolicy";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { previewOutcome } from "@/utils/attendanceOutcome";
import { formatDay, hhmmToMinutes } from "@/utils/friendly";

export interface MarkPresentTarget {
  employeeId: number;
  employeeName: string;
  dateIso: string;
}

/**
 * A manager/HR recording a past day the person worked but forgot to punch in for (it shows as Absent).
 * Shows how the day will be recorded before saving, and needs a reason the employee can read.
 */
export function MarkPresentSheet({
  target,
  onClose,
  onSaved,
}: {
  target: MarkPresentTarget | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const policy = useAttendancePolicy();
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (target) {
      setCheckIn("");
      setCheckOut("");
      setReason("");
      setFormError(null);
    }
  }, [target]);

  const preview =
    checkIn && checkOut && policy
      ? previewOutcome(hhmmToMinutes(checkIn), hhmmToMinutes(checkOut), policy, hhmmToMinutes(checkIn) > hhmmToMinutes(policy.late_after))
      : null;

  const handleSave = async () => {
    if (!target) return;
    if (!checkIn || !checkOut) return setFormError("Please choose both the time they came and the time they left.");
    if (hhmmToMinutes(checkOut) <= hhmmToMinutes(checkIn)) return setFormError("The time they left must be after the time they came.");
    if (reason.trim().length < 3) return setFormError("Please write a short reason. The employee will see it.");
    setFormError(null);
    setIsSaving(true);
    try {
      await attendanceService.markPresent({
        employee_id: target.employeeId,
        attendance_date: target.dateIso,
        check_in_time: checkIn,
        check_out_time: checkOut,
        reason: reason.trim(),
      });
      showToast("Attendance added", "success");
      onSaved();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Sheet
      title="Mark as present"
      isOpen={target !== null}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={onClose}>Not now</Button>
          <Button size="lg" isLoading={isSaving} onClick={handleSave} icon={<Save className="h-5 w-5" />}>
            Save attendance
          </Button>
        </>
      }
    >
      {target && (
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl bg-sand-50 p-4">
            <p className="font-display text-lg font-bold text-stone-800">{target.employeeName}</p>
            <p className="text-base text-stone-600">{formatDay(target.dateIso)} · no check-in was recorded</p>
          </div>

          <div className="flex flex-col gap-4">
            <TimeOfDayField label="What time did they come?" name="mark_check_in" value={checkIn} onChange={setCheckIn} />
            <TimeOfDayField label="What time did they leave?" name="mark_check_out" value={checkOut} onChange={setCheckOut} />
          </div>
          <TextareaField
            label="Reason (the employee will see this)"
            name="mark_reason"
            placeholder="For example: Phone was off, worked the full day"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />

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
          <p className="text-base text-stone-500">
            This day will stop counting as absent. It is recorded with your name, and the employee is told.
          </p>

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
