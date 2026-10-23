import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyToClipboard(value);
    setCopied(ok);
    if (ok) setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-stone-400">{label}</p>
      <div className="mt-1 flex items-center gap-2">
        <code className="flex-1 select-all rounded-lg border border-sand-200 bg-sand-50 px-3 py-2 text-sm text-stone-700">
          {value}
        </code>
        <Button type="button" variant="secondary" size="sm" onClick={handleCopy}>
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

// Deliberately NOT a toast: a generated/reset password is shown exactly once
// and is unrecoverable afterward (we only ever store the hash). A 4-second
// auto-dismissing toast means a slow admin loses it forever. This modal stays
// open until explicitly closed, with copy buttons for both fields.
export function CredentialModal({
  isOpen,
  onClose,
  email,
  password,
  title = "Login credentials",
}: {
  isOpen: boolean;
  onClose: () => void;
  email: string;
  password: string;
  title?: string;
}) {
  return (
    <Modal
      title={title}
      isOpen={isOpen}
      onClose={onClose}
      footer={<Button onClick={onClose}>Done</Button>}
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-stone-600">
          Share this password with the employee through a secure channel. It will not be shown again —
          if it's lost, you'll need to reset it here.
        </p>
        <CopyRow label="Login Email" value={email} />
        <CopyRow label="Temporary Password" value={password} />
        <p className="text-xs text-stone-400">
          The employee will be required to change this password after their first login.
        </p>
      </div>
    </Modal>
  );
}
