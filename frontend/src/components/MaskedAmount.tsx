import { Eye, EyeOff } from "lucide-react";
import { createContext, useContext, useState } from "react";

/**
 * A page can wrap its content in <AmountsProvider> (see ShowAmounts.tsx) to
 * get ONE "Show amounts" switch for every amount on it. Outside such a page
 * each amount keeps its own tap-to-reveal, exactly as before.
 */
export const AmountVisibilityContext = createContext<{ revealed: boolean; toggle: () => void } | null>(null);

function formatInr(amount: number): string {
  return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/**
 * Amounts are masked by default and only shown after a tap - protects
 * against shoulder-surfing in a shared office, since this is money data.
 */
export function MaskedAmount({ amount, className = "" }: { amount: number; className?: string }) {
  const shared = useContext(AmountVisibilityContext);
  const [revealed, setRevealed] = useState(false);

  if (shared) {
    return (
      <span className={`font-display font-semibold tabular-nums ${className}`}>
        {shared.revealed ? formatInr(amount) : "₹••••••"}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setRevealed((r) => !r)}
      className={`inline-flex items-center gap-1.5 font-display font-semibold tabular-nums ${className}`}
      title={revealed ? "Tap to hide" : "Tap to reveal"}
    >
      {revealed ? formatInr(amount) : "₹••••••"}
      {revealed ? (
        <EyeOff className="h-3.5 w-3.5 flex-shrink-0 text-stone-400" aria-hidden="true" />
      ) : (
        <Eye className="h-3.5 w-3.5 flex-shrink-0 text-stone-400" aria-hidden="true" />
      )}
    </button>
  );
}
