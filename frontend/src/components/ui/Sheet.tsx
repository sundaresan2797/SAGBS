import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

/**
 * A panel that slides up from the bottom on a phone (easy to reach with a
 * thumb) and sits centred on a bigger screen. Used for "apply", "add" and
 * "new" forms so the page behind stays put.
 */
export function Sheet({
  title,
  isOpen,
  onClose,
  children,
  footer,
}: {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-stone-900/40 backdrop-blur-[2px] sm:items-center sm:p-4">
      <button aria-label="Close" className="absolute inset-0 cursor-default" onClick={onClose} tabIndex={-1} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative flex max-h-[92vh] w-full flex-col rounded-t-3xl bg-white shadow-xl sm:max-w-lg sm:rounded-3xl"
      >
        <div className="flex items-center justify-between gap-3 px-5 pb-2 pt-5">
          <h2 className="font-display text-xl font-bold text-stone-800">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-11 w-11 items-center justify-center rounded-full text-stone-500 hover:bg-sand-100"
          >
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 pb-5 pt-2">{children}</div>
        {footer && (
          <div className="flex flex-col-reverse gap-2 border-t border-sand-100 px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4 sm:flex-row sm:justify-end">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
