import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** The same title block on every screen: icon, big title, one plain sentence, and (optionally) the main action. */
export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  action,
}: {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <Icon className="h-6 w-6" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <h1 className="font-display text-2xl font-bold text-stone-800">{title}</h1>
          {subtitle && <p className="text-base text-stone-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
