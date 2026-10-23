import clsx from "clsx";
import { Eye, EyeOff } from "lucide-react";
import { useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { AmountVisibilityContext } from "@/components/MaskedAmount";

/** Wrap a page in this and every MaskedAmount inside follows one switch (hidden until switched on). */
export function AmountsProvider({ children }: { children: ReactNode }) {
  const [revealed, setRevealed] = useState(false);
  const toggle = useCallback(() => setRevealed((r) => !r), []);
  const value = useMemo(() => ({ revealed, toggle }), [revealed, toggle]);
  return <AmountVisibilityContext.Provider value={value}>{children}</AmountVisibilityContext.Provider>;
}

export function ShowAmountsSwitch({ className }: { className?: string }) {
  const shared = useContext(AmountVisibilityContext);
  if (!shared) return null;
  const Icon = shared.revealed ? Eye : EyeOff;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={shared.revealed}
      onClick={shared.toggle}
      className={clsx(
        "inline-flex min-h-[44px] items-center gap-3 rounded-xl border-2 border-sand-200 bg-white px-4 text-sm font-semibold text-stone-700 hover:border-brand-200",
        className,
      )}
    >
      <Icon className="h-4 w-4 text-stone-500" aria-hidden="true" />
      Show amounts
      <span
        className={clsx(
          "relative h-6 w-11 flex-shrink-0 rounded-full transition-colors",
          shared.revealed ? "bg-brand-600" : "bg-stone-300",
        )}
        aria-hidden="true"
      >
        <span
          className={clsx(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
            shared.revealed ? "left-[22px]" : "left-0.5",
          )}
        />
      </span>
    </button>
  );
}
