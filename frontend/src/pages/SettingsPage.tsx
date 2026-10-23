import clsx from "clsx";
import { CheckCircle2, Circle, Eye, EyeOff, KeyRound, LogOut, Settings as SettingsIcon, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { inputClasses } from "@/components/ui/FormField";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { authService } from "@/services/authService";
import { ROLE_LABEL } from "@/utils/plainWords";

const MIN_LENGTH = 8;

function PasswordInput({
  id,
  label,
  value,
  onChange,
  autoComplete,
  show,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  show: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-base font-semibold text-stone-700">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputClasses}
      />
    </div>
  );
}

function Check({ ok, children }: { ok: boolean; children: string }) {
  const Icon = ok ? CheckCircle2 : Circle;
  return (
    <li className={clsx("flex items-center gap-2 text-base", ok ? "font-semibold text-success-700" : "text-stone-500")}>
      <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
      {children}
    </li>
  );
}

export function SettingsPage() {
  const { showToast } = useToast();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isChanging, setIsChanging] = useState(false);

  const longEnough = next.length >= MIN_LENGTH;
  const matches = next.length > 0 && next === confirm;
  const different = next.length > 0 && next !== current;

  // Check the form first; only when it is valid do we ask for a deliberate second
  // step, because changing the password signs the person out on every device.
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!current) return setFormError("Please type your current password.");
    if (!longEnough) return setFormError(`Your new password needs at least ${MIN_LENGTH} characters.`);
    if (!different) return setFormError("Your new password must be different from your current one.");
    if (!matches) return setFormError("The two new passwords are not the same. Please type them again.");
    setFormError(null);
    setIsConfirming(true);
  };

  const handleConfirm = async () => {
    setIsChanging(true);
    try {
      await authService.changePassword(current, next);
      // The change invalidates every token issued before it (this session too), so leave
      // straight away with a clear message instead of a page that looks unchanged.
      logout();
      navigate("/login", {
        replace: true,
        state: { notice: "Your password was changed. Please sign in with your new password." },
      });
    } catch (err) {
      setFormError(getErrorMessage(err));
      showToast("Your password was not changed", "error");
      setIsChanging(false);
      setIsConfirming(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-5">
      <PageHeader icon={SettingsIcon} title="Settings" subtitle="Your login and password" />

      {user?.must_change_password && (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <KeyRound className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-600" aria-hidden="true" />
          <p className="text-base text-amber-900">
            <span className="font-semibold">You are using a temporary password.</span> Please choose a new one below before you continue.
            Nothing else opens until you do.
          </p>
        </div>
      )}

      <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-500">You are signed in as</p>
            <p className="break-all font-display text-lg font-bold text-stone-800">{user?.email}</p>
            <p className="text-base text-stone-500">{user ? (ROLE_LABEL[user.role] ?? user.role) : ""} account</p>
          </div>
        </div>
        <Button variant="secondary" size="lg" onClick={handleLogout} icon={<LogOut className="h-5 w-5" />}>
          Log out
        </Button>
      </Card>

      <Card>
        <div className="mb-4 flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-brand-600" aria-hidden="true" />
          <h2 className="font-display text-lg font-bold text-stone-800">Change my password</h2>
        </div>
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          <PasswordInput id="current_password" label="Your current password" value={current} onChange={setCurrent} autoComplete="current-password" show={showPasswords} />
          <PasswordInput id="new_password" label="Your new password" value={next} onChange={setNext} autoComplete="new-password" show={showPasswords} />
          <PasswordInput id="confirm_password" label="Type the new password again" value={confirm} onChange={setConfirm} autoComplete="new-password" show={showPasswords} />

          <button
            type="button"
            aria-pressed={showPasswords}
            onClick={() => setShowPasswords((s) => !s)}
            className="flex min-h-[44px] w-fit items-center gap-2 rounded-xl px-2 text-base font-semibold text-brand-700 hover:bg-brand-50"
          >
            {showPasswords ? <EyeOff className="h-5 w-5" aria-hidden="true" /> : <Eye className="h-5 w-5" aria-hidden="true" />}
            {showPasswords ? "Hide the passwords" : "Show the passwords"}
          </button>

          <ul aria-label="Password checklist" className="flex flex-col gap-1.5 rounded-2xl bg-sand-50 p-4">
            <Check ok={longEnough}>{`At least ${MIN_LENGTH} letters or numbers`}</Check>
            <Check ok={matches}>Both new passwords are the same</Check>
            <Check ok={different}>Different from your current password</Check>
          </ul>

          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}

          <Button type="submit" size="lg" icon={<KeyRound className="h-5 w-5" />}>
            Change my password
          </Button>
        </form>
      </Card>

      <ConfirmDialog
        isOpen={isConfirming}
        title="Change your password?"
        message="You will be signed out on this phone or computer, and on every other device where you are logged in. Then sign in again with your new password."
        confirmLabel="Yes, change it"
        isLoading={isChanging}
        onConfirm={handleConfirm}
        onCancel={() => setIsConfirming(false)}
      />
    </div>
  );
}
