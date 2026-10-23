import { AlertTriangle, Download, FileText, FileUp, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField, SelectField } from "@/components/ui/FormField";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useDocumentPolicy } from "@/hooks/useDocumentPolicy";
import { useToast } from "@/hooks/useToast";
import { getBlobErrorMessage, getErrorMessage } from "@/services/api";
import { documentService } from "@/services/documentService";
import { daysFromToday, formatDateLong, formatFileSize, formatTimestampDate, plural } from "@/utils/friendly";
import { triggerBlobDownload } from "@/utils/downloadFile";
import { EXPIRY_WARNING_DAYS, expiryState, type ExpiryState } from "@/utils/documentExpiry";
import type { DocumentTypeOption, EmployeeDocument } from "@/types";

// Used only until useDocumentPolicy's real fetch of /documents/policy resolves - a conservative
// stand-in for that brief window, never the number actually shown or enforced against a file.
const FALLBACK_MAX_UPLOAD_MB = 5;
const FALLBACK_ALLOWED_EXTENSIONS = [".pdf"];

function expiryOf(doc: EmployeeDocument): { state: ExpiryState; text: string } {
  const state = expiryState(doc.expiry_date);
  if (state === "none") return { state, text: "No expiry date" };
  const days = daysFromToday(doc.expiry_date as string);
  if (state === "expired") return { state, text: `Expired on ${formatDateLong(doc.expiry_date as string)} (${plural(-days, "day")} ago)` };
  if (state === "soon") {
    return { state, text: `Expires on ${formatDateLong(doc.expiry_date as string)} (${days === 0 ? "today" : `in ${plural(days, "day")}`})` };
  }
  return { state, text: `Expires on ${formatDateLong(doc.expiry_date as string)}` };
}

const EXPIRY_ORDER: Record<ExpiryState, number> = { expired: 0, soon: 1, ok: 2, none: 2 };

export function DocumentsPage() {
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const policy = useDocumentPolicy();
  const maxUploadMb = policy?.max_upload_mb ?? FALLBACK_MAX_UPLOAD_MB;
  const allowedExtensions = policy?.allowed_extensions ?? FALLBACK_ALLOWED_EXTENSIONS;

  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [types, setTypes] = useState<DocumentTypeOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [documentTypeId, setDocumentTypeId] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<EmployeeDocument | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [documentList, typeList] = await Promise.all([documentService.list(), documentService.listTypes()]);
      setDocuments(documentList);
      setTypes(typeList);
      setDocumentTypeId((current) => (typeList.some((t) => String(t.id) === current) ? current : String(typeList[0]?.id ?? "")));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your documents."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const selectedType = types.find((t) => String(t.id) === documentTypeId);

  const openSheet = () => {
    setFile(null);
    setExpiryDate("");
    setFormError(null);
    setIsSheetOpen(true);
  };

  const chooseFile = (picked: File | null | undefined) => {
    if (!picked) return;
    const name = picked.name.toLowerCase();
    if (!allowedExtensions.some((ext) => name.endsWith(ext))) {
      setFile(null);
      setFormError(`Only ${allowedExtensions.join(", ")} files can be uploaded. Please choose one of those.`);
      return;
    }
    if (picked.size > maxUploadMb * 1024 * 1024) {
      setFile(null);
      setFormError(`This file is ${formatFileSize(picked.size)}. The maximum allowed is ${maxUploadMb} MB.`);
      return;
    }
    setFormError(null);
    setFile(picked);
  };

  const handleUpload = async () => {
    if (!selectedType) return setFormError("Please choose a document type first.");
    if (!file) return setFormError("Please choose a PDF file first.");
    if (selectedType.requires_expiry && !expiryDate) {
      return setFormError(`${selectedType.name} needs an expiry date. Please enter it and try again.`);
    }
    setFormError(null);
    setIsUploading(true);
    try {
      await documentService.upload(file, selectedType.id, expiryDate || undefined);
      showToast("Your document was added", "success");
      setIsSheetOpen(false);
      load();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDownload = async (doc: EmployeeDocument) => {
    setDownloadingId(doc.id);
    try {
      triggerBlobDownload(await documentService.download(doc.id), doc.file_name);
    } catch (err) {
      showToast(await getBlobErrorMessage(err, "We couldn't download this document."), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await documentService.remove(deleteTarget.id);
      showToast("Document deleted", "success");
      setDeleteTarget(null);
      load();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      setDeleteTarget(null);
    } finally {
      setIsDeleting(false);
    }
  };

  // Papers that need attention first, then newest.
  const sorted = useMemo(
    () =>
      [...documents].sort(
        (a, b) => EXPIRY_ORDER[expiryOf(a).state] - EXPIRY_ORDER[expiryOf(b).state] || b.created_at.localeCompare(a.created_at),
      ),
    [documents],
  );
  const expired = documents.filter((d) => expiryOf(d).state === "expired").length;
  const expiringSoon = documents.filter((d) => expiryOf(d).state === "soon").length;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={FileText}
        title="My Documents"
        subtitle="Keep your important papers safe in one place"
        action={
          <Button size="lg" className="w-full sm:w-auto" onClick={openSheet} disabled={types.length === 0} icon={<Plus className="h-5 w-5" />}>
            Add a document
          </Button>
        }
      />

      {(expired > 0 || expiringSoon > 0) && (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-600" aria-hidden="true" />
          <p className="text-base text-amber-900">
            {expired > 0 && <span className="font-semibold">{plural(expired, "document")} expired. </span>}
            {expiringSoon > 0 && <span className="font-semibold">{plural(expiringSoon, "document")} will expire within {EXPIRY_WARNING_DAYS} days. </span>}
            Please upload the renewed copy.
          </p>
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Loading your documents..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : documents.length === 0 ? (
        <Card>
          <EmptyState title="No documents yet" description="Tap “Add a document” to upload your first PDF." />
        </Card>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {sorted.map((doc) => {
            const expiry = expiryOf(doc);
            return (
              <li key={doc.id} className="flex flex-col gap-3 rounded-2xl border border-sand-200 bg-white p-4 shadow-sm">
                <div className="flex items-start gap-3">
                  <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600">
                    <FileText className="h-6 w-6" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="break-words font-display text-lg font-bold text-stone-800">{doc.file_name}</p>
                    <p className="text-base text-stone-500">
                      {doc.document_type_name} · {formatFileSize(doc.file_size)} · Added {formatTimestampDate(doc.created_at)}
                    </p>
                  </div>
                </div>
                {expiry.state !== "none" && (
                  <p
                    className={`flex items-center gap-2 text-base font-semibold ${
                      expiry.state === "expired" ? "text-sunset-600" : expiry.state === "soon" ? "text-amber-700" : "text-stone-500"
                    }`}
                  >
                    {expiry.state !== "ok" && <AlertTriangle className="h-5 w-5" aria-hidden="true" />}
                    {expiry.text}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" className="flex-1 sm:flex-none" isLoading={downloadingId === doc.id} onClick={() => handleDownload(doc)} icon={<Download className="h-5 w-5" />}>
                    Download
                  </Button>
                  <Button variant="ghost" className="flex-1 text-sunset-600 hover:bg-sunset-50 sm:flex-none" onClick={() => setDeleteTarget(doc)} icon={<Trash2 className="h-5 w-5" />}>
                    Delete
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Sheet
        title="Add a document"
        isOpen={isSheetOpen}
        onClose={() => setIsSheetOpen(false)}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={() => setIsSheetOpen(false)}>Not now</Button>
            <Button size="lg" isLoading={isUploading} onClick={handleUpload} icon={<FileUp className="h-5 w-5" />}>
              Upload document
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <SelectField label="What kind of document is it?" name="document_type_id" value={documentTypeId} onChange={(e) => setDocumentTypeId(e.target.value)}>
            {types.map((type) => (
              <option key={type.id} value={type.id}>{type.name}</option>
            ))}
          </SelectField>
          {selectedType?.description && <p className="-mt-3 text-base text-stone-500">{selectedType.description}</p>}

          <InputField
            label={selectedType?.requires_expiry ? "Expiry date (required)" : "Expiry date (optional)"}
            name="expiry_date"
            type="date"
            required={selectedType?.requires_expiry}
            value={expiryDate}
            onChange={(e) => setExpiryDate(e.target.value)}
          />

          <div>
            <p className="mb-2 text-base font-semibold text-stone-700">Your file</p>
            <label
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => { e.preventDefault(); setIsDragging(false); chooseFile(e.dataTransfer.files[0]); }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center ${
                isDragging ? "border-brand-500 bg-brand-50" : file ? "border-brand-300 bg-brand-50/50" : "border-sand-300 bg-sand-50"
              }`}
            >
              <FileUp className="h-9 w-9 text-brand-600" aria-hidden="true" />
              {file ? (
                <>
                  <span className="break-all text-base font-semibold text-stone-800">{file.name}</span>
                  <span className="text-base text-stone-500">{formatFileSize(file.size)} · tap to choose a different file</span>
                </>
              ) : (
                <>
                  <span className="text-base font-semibold text-stone-800">Tap here to choose a PDF</span>
                  <span className="text-base text-stone-500">
                    {allowedExtensions.join(", ")} files only · up to {maxUploadMb} MB
                  </span>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept={allowedExtensions.join(",")}
                className="sr-only"
                onChange={(e) => chooseFile(e.target.files?.[0])}
              />
            </label>
          </div>

          {formError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      </Sheet>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="Delete this document?"
        message={`"${deleteTarget?.file_name}" will be removed for good. You can upload it again later if you still have the file.`}
        confirmLabel="Yes, delete it"
        isDangerous
        isLoading={isDeleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
