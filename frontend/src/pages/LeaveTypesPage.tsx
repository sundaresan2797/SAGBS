import { Banknote, CalendarClock, CalendarRange, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CardGrid, MetaRow } from "@/components/ui/EntityCard";
import { InputField, SelectField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { leaveService } from "@/services/leaveService";
import type { LeaveAccrualFrequency, LeaveType } from "@/types";

export function LeaveTypesPage() {
  const { showToast } = useToast();

  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<LeaveType | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirmingSave, setIsConfirmingSave] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LeaveType | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [isPaid, setIsPaid] = useState(true);
  const [defaultDays, setDefaultDays] = useState("12");
  const [accrual, setAccrual] = useState<LeaveAccrualFrequency>("ANNUAL");
  const [isActive, setIsActive] = useState(true);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setLeaveTypes(await leaveService.listAllTypes());
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load leave types."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setCode("");
    setName("");
    setIsPaid(true);
    setDefaultDays("12");
    setAccrual("ANNUAL");
    setIsActive(true);
    setIsModalOpen(true);
  };

  const openEdit = (leaveType: LeaveType) => {
    setEditing(leaveType);
    setCode(leaveType.code);
    setName(leaveType.name);
    setIsPaid(leaveType.is_paid);
    setDefaultDays(String(leaveType.default_annual_days));
    setAccrual(leaveType.accrual_frequency);
    setIsActive(leaveType.is_active);
    setIsModalOpen(true);
  };

  const handleSaveClick = () => {
    if (!name.trim() || (!editing && !code.trim())) {
      showToast("Please fill in the code and name", "error");
      return;
    }
    // Ask for confirmation before actually writing the change - the form
    // stays filled in behind this dialog, so cancelling just reopens it.
    setIsModalOpen(false);
    setIsConfirmingSave(true);
  };

  const handleConfirmSave = async () => {
    setIsSaving(true);
    try {
      if (editing) {
        await leaveService.updateType(editing.id, {
          name,
          is_paid: isPaid,
          default_annual_days: isPaid ? Number(defaultDays) : 0,
          accrual_frequency: accrual,
          is_active: isActive,
        });
        showToast("Leave type updated", "success");
      } else {
        await leaveService.createType({
          code,
          name,
          is_paid: isPaid,
          default_annual_days: isPaid ? Number(defaultDays) : 0,
          accrual_frequency: accrual,
        });
        showToast("Leave type created!", "success");
      }
      setIsConfirmingSave(false);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setIsConfirmingSave(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await leaveService.deleteType(deleteTarget.id);
      showToast("Leave type deleted", "success");
      setDeleteTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err, "We couldn't delete this leave type."), "error");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <CalendarRange className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">Leave Types</h1>
            <p className="text-sm text-stone-500">The kinds of leave people can request, and how they're earned</p>
          </div>
        </div>
        <Button onClick={openCreate} icon={<Plus className="h-4 w-4" />}>
          Add Leave Type
        </Button>
      </div>

      {isLoading ? (
        <LoadingState label="Loading leave types..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : leaveTypes.length === 0 ? (
        <Card>
          <EmptyState title="No leave types yet" />
        </Card>
      ) : (
        <CardGrid>
          {leaveTypes.map((leaveType) => (
            <div
              key={leaveType.id}
              className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sand-100 text-stone-500">
                    <CalendarRange className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="font-display text-sm font-semibold text-stone-800">{leaveType.name}</p>
                    <p className="text-xs text-stone-400">{leaveType.code}</p>
                  </div>
                </div>
                <Badge status={leaveType.is_active ? "ACTIVE" : "INACTIVE"} />
              </div>
              <MetaRow icon={<Banknote className="h-3.5 w-3.5" />}>
                {leaveType.is_paid ? `${leaveType.default_annual_days} paid days/year` : "Unpaid"}
              </MetaRow>
              {leaveType.is_paid && (
                <MetaRow icon={<CalendarClock className="h-3.5 w-3.5" />}>
                  {leaveType.accrual_frequency === "MONTHLY"
                    ? "Accrues monthly"
                    : "Granted in full at the start of the year"}
                </MetaRow>
              )}
              <div className="flex items-center gap-4 border-t border-sand-100 pt-3">
                <button
                  className="flex items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                  onClick={() => openEdit(leaveType)}
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  Edit
                </button>
                <button
                  className="flex items-center gap-1.5 text-sm font-semibold text-sunset-600 hover:underline"
                  onClick={() => setDeleteTarget(leaveType)}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </CardGrid>
      )}

      <Modal
        title={editing ? "Edit Leave Type" : "Add Leave Type"}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveClick}>Save</Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {!editing && (
            <InputField
              label="Code"
              name="code"
              required
              placeholder="e.g. SABBATICAL"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          )}
          <InputField label="Name" name="name" required value={name} onChange={(e) => setName(e.target.value)} />
          <SelectField
            label="Paid or unpaid"
            name="is_paid"
            value={isPaid ? "true" : "false"}
            onChange={(e) => setIsPaid(e.target.value === "true")}
          >
            <option value="true">Paid</option>
            <option value="false">Unpaid</option>
          </SelectField>
          {editing && (
            <p className="-mt-2 text-xs text-stone-500">
              Paid or unpaid can't be changed once anyone has used this type. Add a new leave type instead.
            </p>
          )}
          {isPaid && (
            <>
              <InputField
                label="Days per year"
                name="default_annual_days"
                type="number"
                min="0"
                max="365"
                value={defaultDays}
                onChange={(e) => setDefaultDays(e.target.value)}
              />
              <SelectField
                label="How it's earned"
                name="accrual_frequency"
                value={accrual}
                onChange={(e) => setAccrual(e.target.value as LeaveAccrualFrequency)}
              >
                <option value="ANNUAL">Granted in full at the start of the year</option>
                <option value="MONTHLY">Accrues monthly (a fraction credited each month)</option>
              </SelectField>
              {editing && (
                <p className="-mt-2 text-xs text-stone-500">
                  A new number of days applies to balances created from now on (next year, and new joiners). Everyone's
                  current balance stays as it is. Changing how it's earned takes effect for everyone straight away.
                </p>
              )}
            </>
          )}
          {editing && (
            <SelectField
              label="Status"
              name="is_active"
              value={isActive ? "true" : "false"}
              onChange={(e) => setIsActive(e.target.value === "true")}
            >
              <option value="true">Active</option>
              <option value="false">Inactive (hidden from new requests)</option>
            </SelectField>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={isConfirmingSave}
        title={editing ? "Save these changes?" : "Create this leave type?"}
        message={
          editing
            ? `Update "${name}"? A new number of days applies to balances created from now on; everyone's current balance stays as it is. Changing how it's earned, or hiding the type, takes effect straight away.`
            : `Create "${name}" (${code.toUpperCase()})? It will become available on the apply-leave form right away.`
        }
        confirmLabel={editing ? "Save Changes" : "Create Leave Type"}
        isLoading={isSaving}
        onConfirm={handleConfirmSave}
        onCancel={() => {
          setIsConfirmingSave(false);
          setIsModalOpen(true);
        }}
      />

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="Delete this leave type?"
        message={`Delete "${deleteTarget?.name}"? This can't be undone. If it already has balances or requests recorded against it, deactivate it instead.`}
        confirmLabel="Delete"
        isDangerous
        isLoading={isDeleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
