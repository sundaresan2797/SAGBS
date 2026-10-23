import type { ReactNode } from "react";

import { useEmployeePhoto } from "@/hooks/usePhotos";

export function CardGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

const AVATAR_TONES = [
  "bg-brand-100 text-brand-700",
  "bg-sunset-100 text-sunset-700",
  "bg-amber-100 text-amber-700",
  "bg-sky-100 text-sky-700",
  "bg-rose-100 text-rose-700",
];

function toneFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[hash % AVATAR_TONES.length];
}

/**
 * A person's picture, or their initials in a coloured square when they have no photo (or it has not loaded yet).
 * Pass `employeeId` wherever it is known so the photo can be shown.
 */
export function Avatar({
  name,
  icon,
  size = "md",
  employeeId,
}: {
  name: string;
  icon?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  employeeId?: number | null;
}) {
  const photo = useEmployeePhoto(employeeId);
  const sizeClasses = {
    sm: "h-9 w-9 text-xs",
    md: "h-11 w-11 text-sm",
    lg: "h-14 w-14 text-base",
    xl: "h-24 w-24 text-2xl",
  }[size];
  if (photo && !icon) {
    return <img src={photo} alt="" className={`flex-shrink-0 rounded-xl object-cover ${sizeClasses}`} />;
  }
  return (
    <div
      className={`flex flex-shrink-0 items-center justify-center rounded-xl font-display font-semibold ${sizeClasses} ${toneFor(name)}`}
    >
      {icon ?? initials(name)}
    </div>
  );
}

export function MetaRow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-stone-500">
      <span className="text-stone-400">{icon}</span>
      <span className="truncate">{children}</span>
    </div>
  );
}

export function EntityCard({
  avatarName,
  avatarIcon,
  avatarEmployeeId,
  title,
  subtitle,
  badge,
  meta,
  actions,
  onClick,
}: {
  avatarName: string;
  avatarIcon?: ReactNode;
  avatarEmployeeId?: number | null;
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  onClick?: () => void;
}) {
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      onClick={onClick}
      className={`flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 text-left shadow-sm transition-shadow ${
        onClick ? "cursor-pointer hover:shadow-md hover:border-brand-200" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <Avatar name={avatarName} icon={avatarIcon} employeeId={avatarEmployeeId} />
          <div className="flex flex-col">
            <span className="font-display text-sm font-semibold text-stone-800">{title}</span>
            {subtitle && <span className="text-xs text-stone-400">{subtitle}</span>}
          </div>
        </div>
        {badge}
      </div>
      {meta && <div className="flex flex-col gap-1.5">{meta}</div>}
      {actions && <div className="flex items-center gap-3 border-t border-sand-100 pt-3">{actions}</div>}
    </Wrapper>
  );
}
