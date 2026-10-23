import { AtSign, Briefcase, Building2, KeyRound, Mail, Search, ShieldCheck, SquarePen, UserCog } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { CredentialModal } from "@/components/CredentialModal";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Avatar, CardGrid, MetaRow } from "@/components/ui/EntityCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField, SelectField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { employeeService } from "@/services/employeeService";
import { suggestCompanyEmail } from "@/utils/friendly";
import type { EmployeeListItem, LoginRules } from "@/types";
import { ROLE_LABEL } from "@/utils/plainWords";

export function UserAccountsPage() {
  const { showToast } = useToast();
  const [items, setItems] = useState<EmployeeListItem[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [resetTarget, setResetTarget] = useState<EmployeeListItem | null>(null);
  const [customPassword, setCustomPassword] = useState("");
  const [isResetting, setIsResetting] = useState(false);
  const [credential, setCredential] = useState<{ email: string; password: string } | null>(null);

  // Which roles may be handed out, and whose logins this person may not touch - worked out by the server
  // from the roles' real permissions (the Admin has no payroll powers, so it can't touch payroll logins).
  const [rules, setRules] = useState<LoginRules | null>(null);
  const [roleTarget, setRoleTarget] = useState<EmployeeListItem | null>(null);
  const [newRole, setNewRole] = useState("");
  const [isConfirmingRole, setIsConfirmingRole] = useState(false);
  const [isChangingRole, setIsChangingRole] = useState(false);

  const [emailTarget, setEmailTarget] = useState<EmployeeListItem | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [isChangingEmail, setIsChangingEmail] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await employeeService.list({ search: search || undefined, page, page_size: 12 });
      setItems(result.items);
      setTotalPages(result.total_pages);
      setTotal(result.total);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load the accounts list."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  useEffect(() => {
    employeeService.loginRules().then(setRules).catch(() => undefined);
  }, []);

  const openRole = (employee: EmployeeListItem) => {
    setRoleTarget(employee);
    setNewRole(employee.account_role);
  };

  const handleRoleConfirm = async () => {
    if (!roleTarget) return;
    setIsChangingRole(true);
    try {
      await employeeService.changeRole(roleTarget.id, newRole);
      showToast(`${roleTarget.full_name} is now ${ROLE_LABEL[newRole] ?? newRole}`, "success");
      setIsConfirmingRole(false);
      setRoleTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setIsConfirmingRole(false);
    } finally {
      setIsChangingRole(false);
    }
  };

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setPage(1);
    load();
  };

  const openEmail = (employee: EmployeeListItem) => {
    setEmailTarget(employee);
    setNewEmail(suggestCompanyEmail(employee.full_name));
  };

  const handleEmailChange = async () => {
    if (!emailTarget || !newEmail.trim()) return;
    setIsChangingEmail(true);
    try {
      const result = await employeeService.changeEmail(emailTarget.id, newEmail.trim());
      showToast(`${emailTarget.full_name}'s login is now ${result.new_login_email}`, "success");
      setEmailTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsChangingEmail(false);
    }
  };

  const openReset = (employee: EmployeeListItem) => {
    setResetTarget(employee);
    setCustomPassword("");
  };

  const handleReset = async () => {
    if (!resetTarget) return;
    if (customPassword && customPassword.length < 8) {
      showToast("Password must be at least 8 characters", "error");
      return;
    }
    setIsResetting(true);
    try {
      const result = await employeeService.resetPassword(resetTarget.id, customPassword || undefined);
      setCredential({ email: result.login_email, password: result.temporary_password });
      setResetTarget(null);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">User Accounts</h1>
          <p className="text-sm text-stone-500">Reset passwords and change Login Roles - their job title and department are shown for context</p>
        </div>
      </div>

      <Card>
        <form onSubmit={handleSearchSubmit} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, code, or email"
              className="w-full rounded-xl border-2 border-sand-200 py-2.5 pl-10 pr-3.5 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <Button type="submit" variant="secondary" icon={<Search className="h-4 w-4" />}>
            Search
          </Button>
        </form>
      </Card>

      {isLoading ? (
        <LoadingState label="Loading accounts..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState title="No accounts found" description="Try a different search." />
        </Card>
      ) : (
        <>
          <CardGrid>
            {items.map((employee) => (
              <div key={employee.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-3">
                  <Avatar name={employee.full_name} employeeId={employee.id} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-display text-sm font-semibold text-stone-800">{employee.full_name}</p>
                    <p className="truncate text-xs text-stone-400">{employee.employee_code}</p>
                  </div>
                </div>
                <MetaRow icon={<Briefcase className="h-3.5 w-3.5" />}>{employee.designation.name}</MetaRow>
                <MetaRow icon={<Building2 className="h-3.5 w-3.5" />}>{employee.department.name}</MetaRow>
                <MetaRow icon={<Mail className="h-3.5 w-3.5" />}>{employee.email}</MetaRow>
                <div className="flex items-center gap-2">
                  <Badge status={employee.account_role} label={`Login Role: ${ROLE_LABEL[employee.account_role] ?? employee.account_role}`} />
                  {employee.account_active ? (
                    <Badge status="ACTIVE" label="Can sign in" />
                  ) : (
                    <Badge status="INACTIVE" label="Sign-in disabled" />
                  )}
                </div>
                {rules?.protected_roles.includes(employee.account_role) ? (
                  <>
                    <p className="text-xs text-stone-500">
                      This login carries powers you don't have (such as payroll), so only its owner can change it. They
                      can use "Forgot password" on the sign-in page.
                    </p>
                    <div className="flex items-center gap-x-4 border-t border-sand-100 pt-3">
                      <Link
                        to={`/employees/${employee.id}/edit`}
                        className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      >
                        <SquarePen className="h-4 w-4" aria-hidden="true" />
                        Edit job title / department
                      </Link>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sand-100 pt-3">
                    <Link
                      to={`/employees/${employee.id}/edit`}
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                    >
                      <SquarePen className="h-4 w-4" aria-hidden="true" />
                      Edit job title / department
                    </Link>
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => openReset(employee)}
                    >
                      <KeyRound className="h-4 w-4" aria-hidden="true" />
                      Reset password
                    </button>
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => openRole(employee)}
                    >
                      <UserCog className="h-4 w-4" aria-hidden="true" />
                      Change role
                    </button>
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => openEmail(employee)}
                    >
                      <AtSign className="h-4 w-4" aria-hidden="true" />
                      Change email
                    </button>
                  </div>
                )}
              </div>
            ))}
          </CardGrid>
          <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
        </>
      )}

      <Modal
        title="Reset Password"
        isOpen={resetTarget !== null}
        onClose={() => setResetTarget(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setResetTarget(null)}>
              Cancel
            </Button>
            <Button onClick={handleReset} isLoading={isResetting} icon={<KeyRound className="h-4 w-4" />}>
              Reset Password
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-stone-600">
            Reset the login password for <span className="font-semibold">{resetTarget?.full_name}</span> (
            {resetTarget?.email}). Their current password will stop working right away.
          </p>
          <InputField
            label="Custom password (optional)"
            name="custom_password"
            type="text"
            placeholder="Leave blank to generate one automatically"
            value={customPassword}
            onChange={(e) => setCustomPassword(e.target.value)}
          />
          <p className="text-xs text-stone-400">If left blank, we'll generate a secure password for you.</p>
        </div>
      </Modal>

      <Modal
        title="Change role"
        isOpen={roleTarget !== null && !isConfirmingRole}
        onClose={() => setRoleTarget(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRoleTarget(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => setIsConfirmingRole(true)}
              disabled={!roleTarget || newRole === roleTarget.account_role}
              icon={<UserCog className="h-4 w-4" />}
            >
              Continue
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-stone-600">
            Choose what <span className="font-semibold">{roleTarget?.full_name}</span> can see and do. Today their Login
            Role is <span className="font-semibold">{roleTarget ? (ROLE_LABEL[roleTarget.account_role] ?? roleTarget.account_role) : ""}</span>.
          </p>
          {roleTarget && (
            <div className="flex flex-col gap-1.5 rounded-xl border border-sand-200 bg-sand-50 p-3">
              <MetaRow icon={<Briefcase className="h-3.5 w-3.5" />}>{roleTarget.designation.name}</MetaRow>
              <MetaRow icon={<Building2 className="h-3.5 w-3.5" />}>{roleTarget.department.name}</MetaRow>
            </div>
          )}
          <p className="text-xs text-stone-400">
            Login Role controls what they can see and do in the system - it's separate from their job title and
            department above, which this doesn't change.
          </p>
          <SelectField label="New role" name="new_role" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
            {(rules?.assignable_roles ?? []).map((role) => (
              <option key={role} value={role}>
                {ROLE_LABEL[role] ?? role}
              </option>
            ))}
          </SelectField>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={isConfirmingRole}
        title={`Make ${roleTarget?.full_name} ${ROLE_LABEL[newRole] ?? newRole}?`}
        message="This changes what they can see and do. They will be signed out on every device, and the new role applies when they sign in again. It is recorded in the audit log."
        confirmLabel="Yes, change the role"
        isLoading={isChangingRole}
        onConfirm={handleRoleConfirm}
        onCancel={() => setIsConfirmingRole(false)}
      >
        {roleTarget && (
          <div className="flex flex-col gap-1.5 rounded-xl border border-sand-200 bg-sand-50 p-3">
            <MetaRow icon={<Briefcase className="h-3.5 w-3.5" />}>{roleTarget.designation.name}</MetaRow>
            <MetaRow icon={<Building2 className="h-3.5 w-3.5" />}>{roleTarget.department.name}</MetaRow>
          </div>
        )}
      </ConfirmDialog>

      <Modal
        title="Change login email"
        isOpen={emailTarget !== null}
        onClose={() => setEmailTarget(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEmailTarget(null)}>
              Cancel
            </Button>
            <Button onClick={handleEmailChange} isLoading={isChangingEmail} icon={<AtSign className="h-4 w-4" />}>
              Change email
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-stone-600">
            Move <span className="font-semibold">{emailTarget?.full_name}</span>'s login off{" "}
            <span className="font-semibold">{emailTarget?.email}</span> onto a company address. They will be signed
            out on every device and sign in again with the new address and their same password.
          </p>
          <InputField
            label="New login email"
            name="new_email"
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
          />
          <p className="text-xs text-stone-400">
            Suggested from their name ({"firstname.lastname@sat.com"}) - change it if it doesn't fit them.
          </p>
        </div>
      </Modal>

      {credential && (
        <CredentialModal
          isOpen
          title="Password reset"
          email={credential.email}
          password={credential.password}
          onClose={() => setCredential(null)}
        />
      )}
    </div>
  );
}
