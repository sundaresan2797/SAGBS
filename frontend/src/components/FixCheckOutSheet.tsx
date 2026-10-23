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
import { formatClock, formatDay, hhmmToMinutes } from "@/utils/friendly";

export interface FixTarget {
  attendanceId: number;
  employeeName: string;
  dateIso: string;
  checkIn: string;
  lateMinutes: number;
}

/**
 * A manager/HR setting the check-out someone forgot. Shows what the day will
 * become before saving, and asks for a reason the employee will be able to read.
 */
export function FixCheckOutSheet({
  target,
  onClose,
  onFixed,
}: {
  target: FixTarget | null;
  onClose: () => void;
  onFixed: () => void;
}) {
  const { showToast } = useToast();
  const policy = useAttendancePolicy();
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (target) {
      setTime("");
      setReason("");
      setFormError(null);
    }
  }, [target]);

  const checkInDate = target ? new Date(target.checkIn) : null;
  const checkInMinutes = checkInDate ? checkInDate.getHours() * 60 + checkInDate.getMinutes() : 0;

  // What the day will be recorded as, using the company's rules (the server does the real calculation).
  const preview =
    target && time && policy
      ? previewOutcome(checkInMinutes, hhmmToMinutes(time), policy, target.lateMinutes > 0)
      : null;

  const handleSave = async () => {
    if (!target) return;
    if (!time) return setFormError("Please choose the time the person left.");
    if (reason.trim().length < 3) return setFormError("Please write a short reason. The employee will see it.");
    setFormError(null);
    setIsSaving(true);
    try {
      await attendanceService.fixCheckOut(target.attendanceId, time, reason.trim());
      showToast("Check-out fixed", "success");
      onFixed();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Sheet
      title="Fix check-out"
      isOpen={target !== null}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={onClose}>Not now</Button>
          <Button size="lg" isLoading={isSaving} onClick={handleSave} icon={<Save className="h-5 w-5" />}>
            Save check-out
          </Button>
        </>
      }
    >
      {target && (
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl bg-sand-50 p-4">
            <p className="font-display text-lg font-bold text-stone-800">{target.employeeName}</p>
            <p className="text-base text-stone-600">
              {formatDay(target.dateIso)} · checked in at {formatClock(target.checkIn)}, no check-out
            </p>
          </div>

          <TimeOfDayField
            label="What time did they leave?"
            name="fix_check_out_time"
            value={time}
            onChange={setTime}
          />
          <TextareaField
            label="Reason (the employee will see this)"
            name="fix_check_out_reason"
            placeholder="For example: Forgot to tap, left at 6:10 PM"
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
            Once saved, this cannot be changed again. It is recorded with your name, and the employee is told.
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
