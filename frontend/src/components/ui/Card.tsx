import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx("rounded-2xl border border-sand-200 bg-white p-5 shadow-sm", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "brand",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  tone?: "brand" | "sunset";
}) {
  return (
    <Card className="flex items-start gap-4">
      {icon && (
        <div
          className={clsx(
            "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl",
            tone === "brand" ? "bg-brand-50 text-brand-600" : "bg-sunset-50 text-sunset-600",
          )}
        >
          {icon}
        </div>
      )}
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-stone-500">{label}</span>
        <span className="font-display text-2xl font-semibold text-stone-800">{value}</span>
        {hint && <span className="text-xs text-stone-400">{hint}</span>}
      </div>
    </Card>
  );
}
