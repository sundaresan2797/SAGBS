import clsx from "clsx";
import { useEffect, useState } from "react";

import { FieldWrapper, inputClasses } from "@/components/ui/FormField";

/**
 * A clock time picker built from three plain dropdowns (hour, minute, AM/PM), so it looks and works the
 * same on every device - unlike the browser's native <input type="time">, whose AM/PM display depends on
 * the computer's own language and region setting and can silently switch to a 24-hour clock with no AM/PM
 * shown at all. `value`/`onChange` still use the same "HH:MM" (24-hour) text every other clock time in
 * this app uses, so nothing downstream needs to change.
 *
 * Picking the three dropdowns one at a time keeps its own state (`local`): a time isn't complete, and so
 * isn't reported upward, until all three are chosen. If the component derived its display straight from
 * `value` on every render, choosing only the hour would round-trip through the parent as "" (incomplete)
 * and immediately reset that hour back to blank. `value` still drives the field from outside - opening it
 * for a new person, or pre-filling an existing time - by resyncing whenever the CALLER changes it.
 */

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1); // 1..12
const MINUTES = Array.from({ length: 60 }, (_, i) => i); // 0..59

type Meridiem = "AM" | "PM";
type Parts = { hour12: number | null; minute: number | null; meridiem: Meridiem | null };

function parseValue(value: string): Parts {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (!match) return { hour12: null, minute: null, meridiem: null };
  const hour24 = Number(match[1]);
  const minute = Number(match[2]);
  if (hour24 > 23 || minute > 59) return { hour12: null, minute: null, meridiem: null };
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return { hour12, minute, meridiem: hour24 >= 12 ? "PM" : "AM" };
}

function toValue({ hour12, minute, meridiem }: Parts): string {
  if (hour12 == null || minute == null || meridiem == null) return "";
  const hour24 = meridiem === "AM" ? (hour12 === 12 ? 0 : hour12) : hour12 === 12 ? 12 : hour12 + 12;
  return `${String(hour24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function TimeOfDayField({
  label,
  name,
  value,
  onChange,
  required,
  error,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  error?: string;
}) {
  const [local, setLocal] = useState<Parts>(() => parseValue(value));

  // Resync only when the caller changes `value` from the outside (a fresh target, or a prefilled time) -
  // not on every render, or a partial selection below would be wiped out before the third part is picked.
  useEffect(() => {
    setLocal(parseValue(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const update = (patch: Partial<Parts>) => {
    const next = { ...local, ...patch };
    setLocal(next);
    onChange(toValue(next));
  };

  const selectClasses = clsx(inputClasses, "bg-white px-2 text-center");

  return (
    <FieldWrapper label={label} htmlFor={`${name}_hour`} required={required} error={error}>
      <div className="grid grid-cols-3 gap-2">
        <select
          id={`${name}_hour`}
          aria-label={`${label} - hour`}
          className={selectClasses}
          value={local.hour12 ?? ""}
          onChange={(e) => update({ hour12: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">HH</option>
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
        <select
          id={`${name}_minute`}
          aria-label={`${label} - minute`}
          className={selectClasses}
          value={local.minute ?? ""}
          onChange={(e) => update({ minute: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">MM</option>
          {MINUTES.map((m) => (
            <option key={m} value={m}>
              {String(m).padStart(2, "0")}
            </option>
          ))}
        </select>
        <select
          id={`${name}_meridiem`}
          aria-label={`${label} - AM or PM`}
          className={selectClasses}
          value={local.meridiem ?? ""}
          onChange={(e) => update({ meridiem: (e.target.value || null) as Meridiem | null })}
        >
          <option value="">--</option>
          <option value="AM">AM</option>
          <option value="PM">PM</option>
        </select>
      </div>
    </FieldWrapper>
  );
}
