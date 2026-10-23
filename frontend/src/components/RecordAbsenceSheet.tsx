import clsx from "clsx";
import { CalendarOff, Clock, Save, Sun, Trash2, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { InputField, SelectField, TextareaField } from "@/components/ui/FormField";
import { Sheet } from "@/components/ui/Sheet";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { attendanceService } from "@/services/attendanceService";
import { leaveService } from "@/services/leaveService";
import type { LeaveDayPart, LeaveType, PermissionList } from "@/types";
import { formatDay, formatPermissionLength } from "@/utils/friendly";

export interface RecordAbsenceTarget {
  employeeId: number;
  employeeName: string;
  dateIso: string;
}

type Kind = "FULL" | "HALF" | "PERMISSION";

const KINDS: { value: Kind; label: string; hint: string; icon: typeof CalendarOff }[] = [
  { value: "FULL", label: "Leave", hint: "One or more whole days", icon: CalendarOff },
  { value: "HALF", label: "Half day", hint: "Morning or afternoon off", icon: Sun },
  { value: "PERMISSION", label: "Permission", hint: "A few hours off", icon: Clock },
];

/** Permission lengths to offer: every half hour up to the company's limit. */
function lengthOptions(maxMinutes: number): number[] {
  const steps: number[] = [];
  for (let m = 30; m <= maxMinutes; m += 30) steps.push(m);
  if (steps[steps.length - 1] !== maxMinutes && maxMinutes >= 15) steps.push(maxMinutes);
  return steps;
}

/**
 * A manager/HR entering time off for someone who told them (usually a phone call in the morning):
 * a whole-day leave, a half day, or a permission of a few hours. It is checked like any other leave,
 * approved on the spot, saved with the recorder's name and the employee is told.
 */
export function RecordAbsenceSheet({
  target,
  onClose,
  onSaved,
}: {
  target: RecordAbsenceTarget | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const [kind, setKind] = useState<Kind>("FULL");
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [typeId, setTypeId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [part, setPart] = useState<LeaveDayPart>("FIRST_HALF");
  const [minutes, setMinutes] = useState("60");
  const [reason, setReason] = useState("");
  const [permissions, setPermissions] = useState<PermissionList | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!target) return;
    setKind("FULL");
    setStart(target.dateIso);
    setEnd(target.dateIso);
    setPart("FIRST_HALF");
    setMinutes("60");
    setReason("");
    setFormError(null);
    setPermissions(null);
    leaveService
      .listTypes()
      .then((types) => {
        setLeaveTypes(types);
        setTypeId((current) => current || String(types.find((t) => t.is_paid)?.id ?? types[0]?.id ?? ""));
      })
      .catch(() => setLeaveTypes([]));
  }, [target]);

  const permissionMonth = start ? start.slice(0, 7) : "";
  const loadPermissions = useCallback(async () => {
    if (!target || !permissionMonth) return;
    const [year, month] = permissionMonth.split("-").map(Number);
    try {
      setPermissions(await attendanceService.listPermissions(target.employeeId, year, month));
    } catch {
      setPermissions(null);
    }
  }, [target, permissionMonth]);

  useEffect(() => {
    if (kind === "PERMISSION") loadPermissions();
  }, [kind, loadPermissions]);

  const atLimit = permissions !== null && permissions.used_this_month >= permissions.monthly_limit;

  const handleSave = async () => {
    if (!target) return;
    if (!start) return setFormError("Please choose the day.");
    if (reason.trim().length < 3) return setFormError("Please write a short reason, for example: informed by phone at 9:10.");
    if (kind !== "PERMISSION" && !typeId) return setFormError("Please choose the kind of leave.");
    if (kind === "FULL" && (!end || end < start)) return setFormError("The last day cannot be before the first day.");
    setFormError(null);
    setIsSaving(true);
    try {
      if (kind === "PERMISSION") {
        await attendanceService.recordPermission({
          employee_id: target.employeeId,
          permission_date: start,
          minutes: Number(minutes),
          reason: reason.trim(),
        });
        showToast("Permission recorded", "success");
      } else {
        await leaveService.record({
          employee_id: target.employeeId,
          leave_type_id: Number(typeId),
          start_date: start,
          end_date: kind === "HALF" ? start : end,
          reason: reason.trim(),
          day_part: kind === "HALF" ? part : undefined,
        });
        showToast(kind === "HALF" ? "Half-day leave recorded" : "Leave recorded", "success");
      }
      onSaved();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelPermission = async (id: number) => {
    try {
      await attendanceService.cancelPermission(id);
      showToast("Permission cancelled", "success");
      await loadPermissions();
      onSaved();
    } catch (err) {
      setFormError(getErrorMessage(err));
    }
  };

  return (
    <Sheet
      title="Record leave or permission"
      isOpen={target !== null}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={onClose}>Not now</Button>
          <Button size="lg" isLoading={isSaving} onClick={handleSave} icon={<Save className="h-5 w-5" />} disabled={kind === "PERMISSION" && atLimit}>
            Save
          </Button>
        </>
      }
    >
      {target && (
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl bg-sand-50 p-4">
            <p className="font-display text-lg font-bold text-stone-800">{target.employeeName}</p>
            <p className="text-base text-stone-600">Use this when they told you they will be away, for example by phone.</p>
          </div>

          <div role="radiogroup" aria-label="What are you recording?" className="grid grid-cols-3 gap-2">
            {KINDS.map((option) => {
              const Icon = option.icon;
              const selected = kind === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => {
                    setKind(option.value);
                    setFormError(null);
                  }}
                  className={clsx(
                    "flex min-h-[76px] flex-col items-center justify-center gap-1 rounded-2xl border-2 px-2 py-2 text-center",
                    selected ? "border-brand-500 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700",
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  <span className="text-base font-semibold">{option.label}</span>
                  <span className="text-xs text-stone-500">{option.hint}</span>
                </button>
              );
            })}
          </div>

          {kind !== "PERMISSION" && (
            <SelectField label="Kind of leave" name="record_leave_type" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
              {leaveTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name} {type.is_paid ? "(paid)" : "(unpaid)"}
                </option>
              ))}
            </SelectField>
          )}

          {kind === "FULL" ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <InputField
                label="First day"
                name="record_start"
                type="date"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  if (!end || end < e.target.value) setEnd(e.target.value);
                }}
              />
              <InputField label="Last day" name="record_end" type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          ) : (
            <InputField label="Which day?" name="record_day" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          )}

          {kind === "HALF" && (
            <fieldset>
              <legend className="mb-2 text-base font-semibold text-stone-700">Which half?</legend>
              <div className="grid grid-cols-2 gap-2" role="radiogroup">
                {(
                  [
                    ["FIRST_HALF", "Morning off"],
                    ["SECOND_HALF", "Afternoon off"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={part === value}
                    onClick={() => setPart(value)}
                    className={clsx(
                      "min-h-[48px] rounded-xl border-2 px-3 text-base font-semibold",
                      part === value ? "border-brand-500 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-base text-stone-500">Counts as half a day of leave. They work the other half.</p>
            </fieldset>
          )}

          {kind === "PERMISSION" && (
            <>
              <SelectField label="How long?" name="record_minutes" value={minutes} onChange={(e) => setMinutes(e.target.value)}>
                {lengthOptions(permissions?.max_minutes ?? 120).map((m) => (
                  <option key={m} value={m}>
                    {formatPermissionLength(m)}
                  </option>
                ))}
              </SelectField>
              {permissions && (
                <div className={clsx("rounded-2xl p-4 text-base", atLimit ? "bg-amber-50 text-amber-900" : "bg-sand-50 text-stone-700")}>
                  <p className="font-semibold">
                    {permissions.used_this_month} of {permissions.monthly_limit} permissions used this month
                  </p>
                  {atLimit ? (
                    <p className="mt-1">
                      The monthly limit is reached, so record this as a{" "}
                      <button type="button" className="font-semibold underline" onClick={() => setKind("HALF")}>
                        half-day leave
                      </button>{" "}
                      instead.
                    </p>
                  ) : (
                    <p className="mt-1 text-stone-500">Permission is paid. They will not be marked late or half day for the time they were allowed to miss.</p>
                  )}
                  {permissions.items.length > 0 && (
                    <ul className="mt-3 flex flex-col gap-2">
                      {permissions.items.map((p) => (
                        <li key={p.id} className="flex items-center justify-between gap-2 rounded-xl bg-white px-3 py-2 text-base">
                          <span>
                            {formatDay(p.permission_date)} · {formatPermissionLength(p.minutes)}
                          </span>
                          <button
                            type="button"
                            aria-label={`Cancel the permission on ${formatDay(p.permission_date)}`}
                            onClick={() => handleCancelPermission(p.id)}
                            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-rose-700 hover:bg-rose-50"
                          >
                            <Trash2 className="h-5 w-5" aria-hidden="true" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}

          <TextareaField
            label="Reason (the employee will see this)"
            name="record_reason"
            placeholder="For example: Informed by phone at 9:10, fever"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="text-base text-stone-500">
            It is approved right away, saved with your name, and the employee is told. It cannot be added for a month that has already been paid.
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
