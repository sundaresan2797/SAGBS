import { POWERED_BY } from "@/config/company";

/** A quiet "Powered by ..." credit line; renders nothing when VITE_POWERED_BY is empty. */
export function PoweredBy({ className = "", tone = "light" }: { className?: string; tone?: "light" | "dark" }) {
  if (!POWERED_BY) return null;
  return (
    <p className={`text-xs ${tone === "dark" ? "text-blue-200/60" : "text-stone-400"} ${className}`}>
      Powered by <span className={`font-semibold ${tone === "dark" ? "text-gold-300" : "text-stone-500"}`}>{POWERED_BY}</span>
    </p>
  );
}
