import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  icon,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
        size === "lg" && "min-h-[52px] px-6 text-base",
        size === "md" && "min-h-[44px] px-4 py-2.5 text-sm",
        size === "sm" && "px-3 py-2 text-xs",
        variant === "primary" && "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800",
        variant === "secondary" &&
          "border-2 border-sand-200 bg-white text-stone-700 hover:border-brand-200 hover:bg-brand-50",
        variant === "danger" && "bg-sunset-600 text-white shadow-sm hover:bg-sunset-700",
        variant === "ghost" && "text-stone-600 hover:bg-sand-100",
        className,
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
