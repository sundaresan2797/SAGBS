import clsx from "clsx";
import {
  AlertTriangle,
  CalendarOff,
  CheckCircle2,
  CircleDot,
  Clock,
  Hourglass,
  MinusCircle,
  PauseCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

const STATUS_STYLES: Record<string, { classes: string; icon: LucideIcon }> = {
  ACTIVE: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  PRESENT: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  APPROVED: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  COMPLETED: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  PAID: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  RECEIVED: { classes: "bg-success-50 text-success-700 ring-success-600/20", icon: CheckCircle2 },
  ON_LEAVE: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: CalendarOff },
  LATE: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: Clock },
  PENDING: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: Hourglass },
  IN_PROGRESS: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: Hourglass },
  HALF_DAY: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: PauseCircle },
  HOLIDAY: { classes: "bg-sky-50 text-sky-700 ring-sky-600/20", icon: CalendarOff },
  TODO: { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: CircleDot },
  INACTIVE: { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: MinusCircle },
  RESIGNED: { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: MinusCircle },
  CANCELLED: { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: XCircle },
  BLOCKED: { classes: "bg-rose-50 text-rose-700 ring-rose-600/20", icon: AlertTriangle },
  TERMINATED: { classes: "bg-rose-50 text-rose-700 ring-rose-600/20", icon: XCircle },
  REJECTED: { classes: "bg-rose-50 text-rose-700 ring-rose-600/20", icon: XCircle },
  ABSENT: { classes: "bg-rose-50 text-rose-700 ring-rose-600/20", icon: XCircle },
  URGENT: { classes: "bg-rose-50 text-rose-700 ring-rose-600/20", icon: AlertTriangle },
  HIGH: { classes: "bg-sunset-50 text-sunset-700 ring-sunset-600/20", icon: AlertTriangle },
  MEDIUM: { classes: "bg-amber-50 text-amber-700 ring-amber-600/20", icon: CircleDot },
  LOW: { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: CircleDot },
};

const DEFAULT_STYLE = { classes: "bg-stone-100 text-stone-600 ring-stone-400/30", icon: CircleDot };

export function Badge({ status, label, size = "md" }: { status: string; label?: string; size?: "md" | "lg" }) {
  const style = STATUS_STYLES[status] ?? DEFAULT_STYLE;
  const Icon = style.icon;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full font-semibold ring-1 ring-inset",
        size === "lg" ? "px-3 py-1.5 text-sm" : "px-2.5 py-1 text-xs",
        style.classes,
      )}
    >
      <Icon className={size === "lg" ? "h-4 w-4" : "h-3.5 w-3.5"} aria-hidden="true" />
      {label ?? status.replace(/_/g, " ")}
    </span>
  );
}
