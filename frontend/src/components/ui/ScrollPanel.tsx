import clsx from "clsx";
import type { ReactNode } from "react";

/**
 * A fixed-height box that scrolls on its own, so a long list does not stretch the whole page.
 * By default it is at most 34rem tall and never more than about two thirds of the screen, inside a soft bordered box.
 * `maxHeight` and `boxClass` REPLACE those defaults (adding a conflicting class would not reliably win).
 * Keyboard users can focus the box and scroll it with the arrow keys.
 */
export function ScrollPanel({
  label,
  children,
  className,
  maxHeight = "max-h-[min(34rem,65vh)]",
  boxClass = "rounded-2xl border border-sand-200 bg-sand-50/70 p-3",
}: {
  label: string;
  children: ReactNode;
  className?: string;
  maxHeight?: string;
  boxClass?: string;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={clsx(
        maxHeight,
        boxClass,
        "overflow-y-auto overscroll-contain focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300",
        className,
      )}
    >
      {children}
    </div>
  );
}
