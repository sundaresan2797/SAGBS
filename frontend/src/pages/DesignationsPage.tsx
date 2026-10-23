import { Briefcase, Building2, Pencil, Plus, RotateCcw, Ban, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CardGrid, MetaRow } from "@/components/ui/EntityCard";
import { InputField, SelectField, TextareaField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { departmentService, designationService } from "@/services/employeeService";
import type { Department, Designation } from "@/types";
import { plural } from "@/utils/friendly";

export function DesignationsPage() {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const canManage = hasPermission("designation:manage");

  const [designations, setDesignations] = useState<Designation[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<Designation | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [statusTarget, setStatusTarget] = useState<Designation | null>(null);
  const [isChangingStatus, setIsChangingStatus] = useState(false);
  const [search, setSearch] = useState("");
  const [filterDepartmentId, setFilterDepartmentId] = useState("");

  // `quiet` refreshes without the loading screen, so the list keeps its scroll position after a change.
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [desigData, deptData] = await Promise.all([designationService.list(), departmentService.list()]);
      setDesignations(desigData);
      setDepartments(deptData);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load job titles."));
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
    const firstActive = departments.find((d) => d.status === "ACTIVE") ?? departments[0];
    setDepartmentId(firstActive ? String(firstActive.id) : "");
    setIsModalOpen(true);
  };

  const openEdit = (designation: Designation) => {
    setEditing(designation);
    setName(designation.name);
    setDescription(designation.description ?? "");
    setDepartmentId(String(designation.department_id));
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim() || !departmentId) {
      showToast("Please add a title and choose a department", "error");
      return;
    }
    setIsSaving(true);
    try {
      if (editing) {
        await designationService.update(editing.id, { name, description, department_id: Number(departmentId) });
        showToast("Job title updated", "success");
      } else {
        await designationService.create(name, Number(departmentId), description);
        showToast("Job title created!", "success");
      }
      setIsModalOpen(false);
      load(true);
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
      await designationService.update(statusTarget.id, { status: next });
      showToast(next === "ACTIVE" ? "Job title reactivated" : "Job title deactivated", "success");
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsChangingStatus(false);
      setStatusTarget(null);
    }
  };

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return designations.filter(
      (d) =>
        (!filterDepartmentId || String(d.department_id) === filterDepartmentId) &&
        (!needle || `${d.name} ${d.department_name}`.toLowerCase().includes(needle)),
    );
  }, [designations, search, filterDepartmentId]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <Briefcase className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">Job Titles</h1>
            <p className="text-sm text-stone-500">The roles people can hold in each department</p>
          </div>
        </div>
        {canManage && (
          <Button onClick={openCreate} icon={<Plus className="h-4 w-4" />}>
            Add Job Title
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingState label="Loading job titles..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : designations.length === 0 ? (
        <Card>
          <EmptyState title="No job titles yet" />
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
              <input
                type="search"
                aria-label="Search job titles"
                placeholder="Search job titles..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="min-h-[44px] w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>
            <select
              aria-label="Show job titles of"
              value={filterDepartmentId}
              onChange={(e) => setFilterDepartmentId(e.target.value)}
              className="min-h-[44px] rounded-xl border-2 border-sand-200 bg-white px-3.5 text-sm text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              <option value="">All departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <p className="-mb-2 text-xs text-stone-500">
            {shown.length === designations.length ? `${designations.length} job titles` : `Showing ${shown.length} of ${designations.length} job titles`}
            {shown.length > 6 && " · scroll inside the box to see them all"}
          </p>
          {shown.length === 0 ? (
            <Card>
              <EmptyState title="No matches" description="No job title matches this search or department." />
            </Card>
          ) : (
          <ScrollPanel label="Job titles">
        <CardGrid>
          {shown.map((designation) => (
            <div key={designation.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sand-100 text-stone-500">
                    <Briefcase className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <p className="font-display text-sm font-semibold text-stone-800">{designation.name}</p>
                </div>
                <Badge status={designation.status} />
              </div>
              <MetaRow icon={<Building2 className="h-3.5 w-3.5" />}>{designation.department_name}</MetaRow>
              <p className="text-sm font-semibold text-stone-600">{plural(designation.employee_count, "person", "people")}</p>
              {canManage && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sand-100 pt-3">
                  <button
                    className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                    onClick={() => openEdit(designation)}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    Edit
                  </button>
                  {designation.status === "ACTIVE" ? (
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-sunset-600 hover:underline"
                      onClick={() => setStatusTarget(designation)}
                    >
                      <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                      Deactivate
                    </button>
                  ) : (
                    <button
                      className="flex w-fit items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                      onClick={() => setStatusTarget(designation)}
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
          </ScrollPanel>
          )}
        </>
      )}

      <Modal
        title={editing ? "Edit Job Title" : "Add Job Title"}
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
          <InputField label="Title" name="name" required value={name} onChange={(e) => setName(e.target.value)} />
          <SelectField
            label="Department"
            name="department_id"
            required
            value={departmentId}
            onChange={(e) => setDepartmentId(e.target.value)}
          >
            {/* Inactive departments aren't offered for a new job title - except the one this
                job title already belongs to, so editing it doesn't force a change. */}
            {departments
              .filter((d) => d.status === "ACTIVE" || String(d.id) === departmentId)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {d.status !== "ACTIVE" ? " (inactive)" : ""}
                </option>
              ))}
          </SelectField>
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
        title={statusTarget?.status === "ACTIVE" ? "Deactivate this job title?" : "Reactivate this job title?"}
        message={
          statusTarget?.status === "ACTIVE"
            ? `${plural(statusTarget?.employee_count ?? 0, "person", "people")} ${statusTarget?.employee_count === 1 ? "holds" : "hold"} "${statusTarget?.name}". ` +
              "It will no longer be offered when adding or moving an employee. Those already holding it are not affected."
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
