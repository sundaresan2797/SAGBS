import logo from "@/assets/sat-logo.jpg";
import { COMPANY_NAME } from "@/config/company";

/** The company logo (and, unless `logoOnly`, its name): the one place the brand is drawn inside the app. */
export function BrandMark({ logoOnly = false, size = "md", tone = "light" }: { logoOnly?: boolean; size?: "md" | "lg"; tone?: "light" | "dark" }) {
  const box = size === "lg" ? "h-14 w-14 rounded-2xl" : "h-9 w-9 rounded-xl";
  return (
    <div className="flex items-center gap-2.5">
      <img src={logo} alt={logoOnly ? `${COMPANY_NAME} logo` : ""} className={`${box} flex-shrink-0 object-cover shadow-sm ${tone === "dark" ? "ring-1 ring-white/20" : ""}`} />
      {!logoOnly && <span className={`truncate font-display text-lg font-bold ${tone === "dark" ? "text-white" : "text-stone-800"}`}>{COMPANY_NAME}</span>}
    </div>
  );
}
