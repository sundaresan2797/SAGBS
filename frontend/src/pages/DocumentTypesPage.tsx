import { CalendarClock, FileCog, Pencil, Plus, Trash2 } from "lucide-react";
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
import { documentService } from "@/services/documentService";
import type { DocumentTypeOption } from "@/types";
import { plural } from "@/utils/friendly";

// "Bank Passbook" -> "BANK_PASSBOOK": a starting suggestion for the code, so nobody has to invent one.
function suggestCode(name: string): string {
  return name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 30);
}

export function DocumentTypesPage() {
  const { showToast } = useToast();

  const [types, setTypes] = useState<DocumentTypeOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<DocumentTypeOption | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirmingSave, setIsConfirmingSave] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentTypeOption | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [codeEdited, setCodeEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [requiresExpiry, setRequiresExpiry] = useState(false);
  const [isActive, setIsActive] = useState(true);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setTypes(await documentService.listAllTypes());
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load document types."));
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
    setCode("");
    setCodeEdited(false);
    setDescription("");
    setRequiresExpiry(false);
    setIsActive(true);
    setIsModalOpen(true);
  };

  const openEdit = (type: DocumentTypeOption) => {
    setEditing(type);
    setName(type.name);
    setCode(type.code);
    setDescription(type.description ?? "");
    setRequiresExpiry(type.requires_expiry);
    setIsActive(type.is_active);
    setIsModalOpen(true);
  };

  const handleNameChange = (value: string) => {
    setName(value);
    if (!editing && !codeEdited) setCode(suggestCode(value));
  };

  const handleSaveClick = () => {
    if (name.trim().length < 2 || (!editing && code.trim().length < 2)) {
      showToast("Please fill in the name and code (at least 2 characters each)", "error");
      return;
    }
    if (!editing && !/^[A-Za-z0-9_]+$/.test(code)) {
      showToast("The code can only use letters, numbers and underscores", "error");
      return;
    }
    // Same two-step pattern as Leave Types: the form stays filled in behind the
    // confirmation, so cancelling just brings it back.
    setIsModalOpen(false);
    setIsConfirmingSave(true);
  };

  const handleConfirmSave = async () => {
    setIsSaving(true);
    try {
      if (editing) {
        await documentService.updateType(editing.id, {
          name: name.trim(),
          description: description.trim() || null,
          requires_expiry: requiresExpiry,
          is_active: isActive,
        });
        showToast("Document type updated", "success");
      } else {
        await documentService.createType({
          code,
          name: name.trim(),
          description: description.trim() || undefined,
          requires_expiry: requiresExpiry,
        });
        showToast("Document type created!", "success");
      }
      setIsConfirmingSave(false);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setIsConfirmingSave(false);
      setIsModalOpen(true);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await documentService.deleteType(deleteTarget.id);
      showToast("Document type deleted", "success");
      setDeleteTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err, "We couldn't delete this document type."), "error");
      setDeleteTarget(null);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <FileCog className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">Document Types</h1>
            <p className="text-sm text-stone-500">The kinds of document people can choose when they upload a file</p>
          </div>
        </div>
        <Button onClick={openCreate} icon={<Plus className="h-4 w-4" />}>
          Add Document Type
        </Button>
      </div>

      {isLoading ? (
        <LoadingState label="Loading document types..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : types.length === 0 ? (
        <Card>
          <EmptyState title="No document types yet" description="Add one so people can upload documents." />
        </Card>
      ) : (
        <CardGrid>
          {types.map((type) => (
            <div key={type.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-sand-100 text-stone-500">
                    <FileCog className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <p className="break-words font-display text-sm font-semibold text-stone-800">{type.name}</p>
                    {/* A zero-width space after each underscore lets a long code wrap between words, not mid-word. */}
                    <p className="break-words text-xs text-stone-400">{type.code.replace(/_/g, "_\u200b")}</p>
                  </div>
                </div>
                <span className="flex-shrink-0">
                  <Badge status={type.is_active ? "ACTIVE" : "INACTIVE"} />
                </span>
              </div>
              {type.description && <p className="text-xs text-stone-500">{type.description}</p>}
              <MetaRow icon={<CalendarClock className="h-3.5 w-3.5" />}>
                {type.requires_expiry ? "Expiry date is required" : "Expiry date is optional"}
              </MetaRow>
              <p className="text-sm font-semibold text-stone-600">{plural(type.document_count ?? 0, "document")} uploaded</p>
              <div className="flex items-center gap-4 border-t border-sand-100 pt-3">
                <button
                  className="flex items-center gap-1.5 text-sm font-semibold text-brand-600 hover:underline"
                  onClick={() => openEdit(type)}
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  Edit
                </button>
                <button
                  className="flex items-center gap-1.5 text-sm font-semibold text-sunset-600 hover:underline"
                  onClick={() => setDeleteTarget(type)}
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
        title={editing ? "Edit Document Type" : "Add Document Type"}
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
          <InputField
            label="Name"
            name="name"
            required
            placeholder="e.g. Bank Passbook"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
          />
          {editing ? (
            <p className="text-xs text-stone-400">
              Code: <span className="font-semibold text-stone-600">{editing.code}</span> (fixed, because it appears in
              saved file names)
            </p>
          ) : (
            <InputField
              label="Code"
              name="code"
              required
              placeholder="e.g. BANK_PASSBOOK"
              value={code}
              onChange={(e) => {
                setCode(e.target.value.toUpperCase());
                setCodeEdited(true);
              }}
            />
          )}
          <InputField
            label="Short description (optional)"
            name="description"
            placeholder="What is this document used for?"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <SelectField
            label="Expiry date"
            name="requires_expiry"
            value={requiresExpiry ? "true" : "false"}
            onChange={(e) => setRequiresExpiry(e.target.value === "true")}
          >
            <option value="false">Optional</option>
            <option value="true">Required (the person must enter one when uploading)</option>
          </SelectField>
          {editing && (
            <SelectField
              label="Status"
              name="is_active"
              value={isActive ? "true" : "false"}
              onChange={(e) => setIsActive(e.target.value === "true")}
            >
              <option value="true">Active</option>
              <option value="false">Inactive (hidden from the upload form)</option>
            </SelectField>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={isConfirmingSave}
        title={editing ? "Save these changes?" : "Create this document type?"}
        message={
          editing
            ? `Update "${name}"? The change shows on the upload form right away.`
            : `Create "${name.trim()}" (${code})? People will be able to choose it on the upload form right away.`
        }
        confirmLabel={editing ? "Save Changes" : "Create Document Type"}
        isLoading={isSaving}
        onConfirm={handleConfirmSave}
        onCancel={() => {
          setIsConfirmingSave(false);
          setIsModalOpen(true);
        }}
      />

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="Delete this document type?"
        message={
          (deleteTarget?.document_count ?? 0) > 0
            ? `${plural(deleteTarget?.document_count ?? 0, "document")} use "${deleteTarget?.name}", so it can't be deleted. Set its status to Inactive instead, to hide it from the upload form.`
            : `Delete "${deleteTarget?.name}"? Nobody has uploaded this type, so nothing is lost. This can't be undone.`
        }
        confirmLabel="Delete"
        isDangerous
        isLoading={isDeleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
