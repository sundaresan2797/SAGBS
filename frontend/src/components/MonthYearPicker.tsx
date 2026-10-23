import clsx from "clsx";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { yearOptions } from "@/components/YearFilter";
import { monthName } from "@/utils/friendly";

const SELECT_CLASSES =
  "min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-2 text-base font-semibold text-stone-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100";

/** Month and Year drop-downs: jump straight to any month up to this one (no future months). */
export function MonthYearSelects({
  year,
  month,
  onChange,
  minYear,
}: {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
  /** The earliest year worth offering (for example the year someone joined). */
  minYear?: number;
}) {
  const now = new Date();
  const thisYear = now.getFullYear();
  const thisMonth = now.getMonth() + 1;
  const years = yearOptions(now).filter((y) => !minYear || y >= minYear);
  if (!years.includes(year)) years.push(year); // never lose the year being shown
  years.sort((a, b) => b - a);

  const pick = (nextYear: number, nextMonth: number) => {
    // A month that has not started yet cannot be shown, so land on the latest month instead.
    onChange(nextYear, nextYear === thisYear && nextMonth > thisMonth ? thisMonth : nextMonth);
  };

  return (
    <div className="flex items-center gap-2">
      <select aria-label="Month" value={month} onChange={(e) => pick(year, Number(e.target.value))} className={SELECT_CLASSES}>
        {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
          <option key={m} value={m} disabled={year === thisYear && m > thisMonth}>
            {monthName(m)}
          </option>
        ))}
      </select>
      <select aria-label="Year" value={year} onChange={(e) => pick(Number(e.target.value), month)} className={SELECT_CLASSES}>
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Previous / next arrows around the Month and Year drop-downs. */
export function MonthYearPicker({
  year,
  month,
  onChange,
  minYear,
  className,
}: {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
  minYear?: number;
  className?: string;
}) {
  const now = new Date();
  const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1;
  const step = (delta: number) => {
    const index = year * 12 + (month - 1) + delta;
    onChange(Math.floor(index / 12), (index % 12) + 1);
  };
  const arrow = "flex h-11 w-11 items-center justify-center rounded-xl border-2 border-sand-200 bg-white text-stone-600 hover:bg-sand-50 disabled:cursor-not-allowed disabled:opacity-30";
  return (
    <div className={clsx("flex flex-wrap items-center gap-2", className)}>
      <button type="button" aria-label="Previous month" onClick={() => step(-1)} className={arrow}>
        <ChevronLeft className="h-5 w-5" aria-hidden="true" />
      </button>
      <MonthYearSelects year={year} month={month} onChange={onChange} minYear={minYear} />
      <button
        type="button"
        aria-label="Next month"
        disabled={isCurrent}
        title={isCurrent ? "Nothing to show for a month that has not started" : undefined}
        onClick={() => step(1)}
        className={arrow}
      >
        <ChevronRight className="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  );
}
