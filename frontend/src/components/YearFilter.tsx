import clsx from "clsx";

/** A calendar year, or every year. */
export type YearValue = number | "ALL";

/** How many past years the pickers offer, besides this one ("All years" covers anything older). */
export const YEARS_BACK = 4;

/** This year first, then back a few years. */
export function yearOptions(now: Date = new Date()): number[] {
  return Array.from({ length: YEARS_BACK + 1 }, (_, i) => now.getFullYear() - i);
}

/** What to send to the server: a number, or nothing for "All years". */
export function yearParam(value: YearValue): number | undefined {
  return value === "ALL" ? undefined : value;
}

const SELECT_CLASSES =
  "min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-3 text-base font-semibold text-stone-700 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100";

/**
 * "Year" drop-down for lists that grow over time. Starts on the current calendar year (the caller sets that);
 * `withAll` adds an "All years" choice.
 */
export function YearFilter({
  value,
  onChange,
  withAll = true,
  label = "Year",
  className,
}: {
  value: YearValue;
  onChange: (value: YearValue) => void;
  withAll?: boolean;
  label?: string;
  className?: string;
}) {
  const thisYear = new Date().getFullYear();
  return (
    <label className={clsx("flex items-center gap-2 text-base font-semibold text-stone-600", className)}>
      {label}
      <select
        aria-label={label}
        value={String(value)}
        onChange={(e) => onChange(e.target.value === "ALL" ? "ALL" : Number(e.target.value))}
        className={SELECT_CLASSES}
      >
        {yearOptions().map((year) => (
          <option key={year} value={year}>
            {year === thisYear ? `${year} (this year)` : year}
          </option>
        ))}
        {withAll && <option value="ALL">All years</option>}
      </select>
    </label>
  );
}
