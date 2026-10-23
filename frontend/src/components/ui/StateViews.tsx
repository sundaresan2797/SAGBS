import { Inbox, RefreshCw, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/Button";

export function LoadingState({ label = "Just a moment..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-stone-500">
      <span className="h-8 w-8 animate-spin rounded-full border-[3px] border-sand-200 border-t-brand-500" />
      {label}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sand-100 text-stone-400">
        <Inbox className="h-7 w-7" aria-hidden="true" />
      </div>
      <p className="mt-1 font-display text-base font-semibold text-stone-700">{title}</p>
      {description && <p className="max-w-sm text-sm text-stone-400">{description}</p>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sunset-50 text-sunset-500">
        <WifiOff className="h-7 w-7" aria-hidden="true" />
      </div>
      <p className="max-w-sm text-sm font-medium text-stone-600">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} icon={<RefreshCw className="h-4 w-4" />}>
          Try again
        </Button>
      )}
    </div>
  );
}
