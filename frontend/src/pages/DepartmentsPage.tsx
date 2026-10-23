import { Building2, Pencil, Plus, RotateCcw, Ban } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CardGrid } from "@/components/ui/EntityCard";
import { InputField, TextareaField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { departmentService } from "@/services/employeeService";
import type { Department } from "@/types";
import { plural } from "@/utils/friendly";

export function DepartmentsPage() {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const canManage = hasPermission("department:manage");

  const [departments, setDepartments] = useState<Department[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<Department | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [statusTarget, setStatusTarget] = useState<Department | null>(null);
  const [isChangingStatus, setIsChangingStatus] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setDepartments(await departmentService.list());
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load departments."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setName("");
    setDescription("");
    setIsModalOpen(true);
  };

  const openEdit = (department: Department) => {
    setEditing(department);
    setName(department.name);
    setDescription(department.description ?? "");
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      showToast("Please give the department a name", "error");
      return;
    }
    setIsSaving(true);
    try {
      if (editing) {
        await departmentService.update(editing.id, { name, description });
        showToast("Department updated", "success");
      } else {
        await departmentService.create(name, description);
        showToast("Department created!", "success");
      }
      setIsModalOpen(false);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsSaving(false);
    }
  };

  const handleChangeStatus = async () => {
    if (!statusTarget) return;
    setIsChangingStatus(true);
    try {
      const next = statusTarget.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
      await departmentService.update(statusTarget.id, { status: next });
      showToast(next === "ACTIVE" ? "Department reactivated" : "Department deactivated", "success");
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsChangingStatus(false);
      setStatusTarget(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <Building2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">Departments</h1>
            <p className="text-sm text-stone-500">The teams that make up the company</p>
          </div>
        </div>
        {canManage && (
          <Button onClick={openCreate} icon={<Plus className="h-4 w-4" />}>
            Add Department
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingState label="Loading departments..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : departments.length === 0 ? (
        <Card>
          <EmptyState title="No departments yet" />
        </Card>
      ) : (
        <CardGrid>
          {departments.map((department) => (
            <div key={department.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sand-100 text-stone-500">
                    <Building2 className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <p className="font-display text-sm font-semibold text-stone-800">{department.name}</p>
                </div>
                <Badge status={department.status} />
              </div>
              {department.description && <p className="text-sm text-stone-500">{department.description}</p>}
              <p className="text-sm font-semibold text-stone-600">
                {plural(department.employee_count, "person", "people")} &middot; {plural(department.designation_count, "job title")}
              </p>
              {canManage && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sand-100 pt-3">
                  <button
                    className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                    onClick={() => openEdit(department)}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    Edit
                  </button>
                  {department.status === "ACTIVE" ? (
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-sunset-600 hover:underline"
                      onClick={() => setStatusTarget(department)}
                    >
                      <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                      Deactivate
                    </button>
                  ) : (
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => setStatusTarget(department)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                      Reactivate
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </CardGrid>
      )}

      <Modal
        title={editing ? "Edit Department" : "Add Department"}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} isLoading={isSaving}>
              Save
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <InputField label="Name" name="name" required value={name} onChange={(e) => setName(e.target.value)} />
          <TextareaField
            label="Description"
            name="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={statusTarget !== null}
        title={statusTarget?.status === "ACTIVE" ? "Deactivate this department?" : "Reactivate this department?"}
        message={
          statusTarget?.status === "ACTIVE"
            ? `"${statusTarget?.name}" has ${plural(statusTarget?.employee_count ?? 0, "person", "people")} and ${plural(statusTarget?.designation_count ?? 0, "job title")}. ` +
              "It will no longer be offered when adding or moving an employee. Everyone already in it, and its existing job titles, are not affected."
            : `"${statusTarget?.name}" will be offered again when adding or moving an employee.`
        }
        confirmLabel={statusTarget?.status === "ACTIVE" ? "Yes, deactivate it" : "Yes, reactivate it"}
        isDangerous={statusTarget?.status === "ACTIVE"}
        isLoading={isChangingStatus}
        onConfirm={handleChangeStatus}
        onCancel={() => setStatusTarget(null)}
      />
    </div>
  );
}
