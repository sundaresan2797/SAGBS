import { Check, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorState, LoadingState } from "@/components/ui/StateViews";
import { Td, Th, TableContainer } from "@/components/ui/Table";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { roleService } from "@/services/roleService";
import type { PermissionsMatrix } from "@/types";

const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Admin",
  FOUNDER: "Founder",
  HR: "HR",
  EXECUTIVE: "Executive",
  ACCOUNTANT: "Accountant",
  MANAGER: "Manager",
  EMPLOYEE: "Employee",
};

interface Target {
  role: string;
  code: string;
  description: string;
  granted: boolean; // the state it's currently in, before this change
}

export function RolesPermissionsPage() {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const [matrix, setMatrix] = useState<PermissionsMatrix | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setMatrix(await roleService.permissionsMatrix());
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load roles and permissions."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConfirm = async () => {
    if (!target) return;
    setIsSaving(true);
    try {
      setMatrix(await roleService.setPermission(target.role, target.code, !target.granted));
      showToast(target.granted ? "Permission removed" : "Permission granted", "success");
      setTarget(null);
    } catch (err) {
      showToast(getErrorMessage(err, "Unable to update that permission."), "error");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <KeyRound className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">Roles &amp; Permissions</h1>
          <p className="text-sm text-stone-500">
            What each login role can do. Click a cell to change it — you can only hand out a permission you have yourself.
          </p>
        </div>
      </div>

      <Card className="p-0">
        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : (
          matrix && (
            <TableContainer>
              <thead>
                <tr>
                  <Th>Permission</Th>
                  {matrix.roles.map((role) => (
                    <Th key={role.role}>{ROLE_LABEL[role.role] ?? role.role}</Th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-100">
                {matrix.permissions.map((permission) => (
                  <tr key={permission.code}>
                    <Td className="font-medium text-stone-800">{permission.description}</Td>
                    {matrix.roles.map((role) => {
                      const granted = role.permission_codes.includes(permission.code);
                      // Revoking is always safe to offer; granting is only offered for a permission the
                      // viewer holds themselves - the server enforces this too, this just avoids a click
                      // that's certain to be refused.
                      const mayToggle = granted || hasPermission(permission.code);
                      return (
                        <Td key={role.role} className="text-center">
                          <button
                            type="button"
                            disabled={!mayToggle}
                            title={mayToggle ? undefined : "You don't have this permission yourself, so you can't grant it"}
                            onClick={() =>
                              setTarget({ role: role.role, code: permission.code, description: permission.description, granted })
                            }
                            className={`mx-auto flex h-8 w-8 items-center justify-center rounded-lg ${
                              mayToggle ? "cursor-pointer hover:bg-sand-100" : "cursor-not-allowed"
                            }`}
                          >
                            {granted ? (
                              <Check className="h-4 w-4 text-brand-600" aria-label="Has this permission" />
                            ) : (
                              <span className={mayToggle ? "text-stone-300" : "text-stone-200"} aria-label="Does not have this permission">
                                —
                              </span>
                            )}
                          </button>
                        </Td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </TableContainer>
          )
        )}
      </Card>

      <ConfirmDialog
        isOpen={target !== null}
        title={target?.granted ? "Remove this permission?" : "Grant this permission?"}
        message={
          target
            ? target.granted
              ? `${ROLE_LABEL[target.role] ?? target.role} will no longer be able to: ${target.description.toLowerCase()}. Anyone currently signed in with that role loses it on their very next action.`
              : `${ROLE_LABEL[target.role] ?? target.role} will be able to: ${target.description.toLowerCase()}. Anyone currently signed in with that role gains it on their very next action.`
            : ""
        }
        confirmLabel={target?.granted ? "Yes, remove it" : "Yes, grant it"}
        isDangerous={target?.granted}
        isLoading={isSaving}
        onConfirm={handleConfirm}
        onCancel={() => setTarget(null)}
      />
    </div>
  );
}
