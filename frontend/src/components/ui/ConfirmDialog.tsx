import { AlertTriangle, HelpCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = "Confirm",
  isDangerous = false,
  isLoading = false,
  onConfirm,
  onCancel,
  children,
}: {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  isDangerous?: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Extra content below the message - e.g. an optional reason field before a reject/deactivate. */
  children?: ReactNode;
}) {
  const Icon = isDangerous ? AlertTriangle : HelpCircle;
  return (
    <Modal
      title={title}
      isOpen={isOpen}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
            Cancel
          </Button>
          <Button variant={isDangerous ? "danger" : "primary"} onClick={onConfirm} isLoading={isLoading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex gap-3">
          <div
            className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full ${
              isDangerous ? "bg-sunset-50 text-sunset-500" : "bg-brand-50 text-brand-600"
            }`}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          <p className="pt-2 text-sm text-stone-600">{message}</p>
        </div>
        {children}
      </div>
    </Modal>
  );
}
