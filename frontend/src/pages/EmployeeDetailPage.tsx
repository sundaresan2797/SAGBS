import { Briefcase, CalendarPlus, CalendarRange, Download, FileText, Mail, User, UserCog } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AttendanceCalendar } from "@/components/AttendanceCalendar";
import { RecordAbsenceSheet, type RecordAbsenceTarget } from "@/components/RecordAbsenceSheet";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmployeePhotoEditor } from "@/components/EmployeePhotoEditor";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getBlobErrorMessage, getErrorMessage } from "@/services/api";
import { documentService } from "@/services/documentService";
import { employeeService } from "@/services/employeeService";
import { expiryState } from "@/utils/documentExpiry";
import { formatDateLong, formatFileSize, formatTimestampDate } from "@/utils/friendly";
import { triggerBlobDownload } from "@/utils/downloadFile";
import { toIsoDate } from "@/utils/taskHelpers";
import type { Employee, EmployeeDocument, EmployeeStatus } from "@/types";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-stone-400">{label}</p>
      <p className="text-sm text-stone-700">{value || "—"}</p>
    </div>
  );
}

export function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingStatus, setPendingStatus] = useState<EmployeeStatus | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [recordTarget, setRecordTarget] = useState<RecordAbsenceTarget | null>(null);

  const load = async () => {
    if (!id) return;
    setIsLoading(true);
    setError(null);
    try {
      setEmployee(await employeeService.getById(Number(id)));
    } catch (err) {
      setError(getErrorMessage(err, "Unable to load this employee."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!employee || employee.id === user?.employee_id || !hasPermission("document:manage_all")) {
      setDocuments([]);
      setIsLoadingDocuments(false);
      return;
    }
    let cancelled = false;
    setIsLoadingDocuments(true);
    setDocumentsError(null);
    documentService
      .list(employee.id)
      .then((result) => {
        if (!cancelled) setDocuments(result);
      })
      .catch((err) => {
        if (!cancelled) setDocumentsError(getErrorMessage(err, "Unable to load this employee's documents."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDocuments(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee?.id, user?.employee_id]);

  const handleDownloadDocument = async (doc: EmployeeDocument) => {
    setDownloadingId(doc.id);
    try {
      triggerBlobDownload(await documentService.download(doc.id), doc.file_name);
    } catch (err) {
      showToast(await getBlobErrorMessage(err, "We couldn't download this document."), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleStatusChange = async () => {
    if (!employee || !pendingStatus) return;
    setIsUpdating(true);
    try {
      const updated = await employeeService.updateStatus(employee.id, pendingStatus);
      setEmployee(updated);
      showToast(`Status updated to ${pendingStatus.replace(/_/g, " ")}`, "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsUpdating(false);
      setPendingStatus(null);
    }
  };

  if (isLoading) return <LoadingState label="Loading employee..." />;
  if (error || !employee) return <ErrorState message={error ?? "Employee not found."} onRetry={load} />;

  const canEdit = hasPermission("employee:update");
  // Mirrors the server: your own photo, or anyone's if you are HR, the Founder or the Admin.
  const canChangePhoto = employee.id === user?.employee_id || canEdit || hasPermission("document:manage_all");
  const canDeactivate = hasPermission("employee:deactivate");
  // Mirrors the backend rule in get_employee_attendance_calendar: only show
  // this section when the viewer can actually load it - their own record,
  // their direct report, or company-wide attendance visibility - rather
  // than rendering it and letting it fail with a 403.
  const canViewAttendance =
    hasPermission("attendance:read_all") ||
    employee.id === user?.employee_id ||
    employee.manager?.id === user?.employee_id;
  // Mirrors the backend rule in attendance_service._ensure_can_correct: HR/Admin/Founder
  // (attendance:read_all) or this person's direct manager may fix a missed check-out or
  // mark a forgotten day present - but never for your own record, even if you'd otherwise
  // qualify (e.g. a Founder viewing their own profile).
  const canFixAttendance =
    employee.id !== user?.employee_id &&
    (hasPermission("attendance:read_all") || employee.manager?.id === user?.employee_id);
  // Mirrors the backend rule in _resolve_target_employee: viewing someone else's uploaded
  // documents requires document:manage_all. Your own documents already live on "My Documents",
  // so this section only ever shows another employee's uploads, not your own.
  const canViewDocuments = employee.id !== user?.employee_id && hasPermission("document:manage_all");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <EmployeePhotoEditor employeeId={employee.id} name={employee.full_name} canEdit={canChangePhoto} />
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">{employee.full_name}</h1>
            <p className="text-sm text-stone-500">
              {employee.employee_code} &middot; {employee.designation.name}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge status={employee.status} />
          {canEdit && (
            <Link to={`/employees/${employee.id}/edit`}>
              <Button variant="secondary" icon={<UserCog className="h-4 w-4" />}>
                Edit
              </Button>
            </Link>
          )}
          {canDeactivate && employee.status === "ACTIVE" && (
            <Button variant="danger" onClick={() => setPendingStatus("TERMINATED")}>
              Deactivate
            </Button>
          )}
          {canDeactivate && employee.status !== "ACTIVE" && (
            <Button variant="secondary" onClick={() => setPendingStatus("ACTIVE")}>
              Reactivate
            </Button>
          )}
        </div>
      </div>

      <Card>
        <div className="mb-4 flex items-center gap-2">
          <User className="h-4 w-4 text-brand-600" aria-hidden="true" />
          <h2 className="font-display text-sm font-semibold text-stone-700">Personal Information</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="First Name" value={employee.full_name.split(" ")[0]} />
          <Field label="Date of Birth" value={employee.date_of_birth} />
          <Field label="Phone" value={employee.phone} />
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center gap-2">
          <Mail className="h-4 w-4 text-brand-600" aria-hidden="true" />
          <h2 className="font-display text-sm font-semibold text-stone-700">Contact Information</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Email" value={employee.email} />
          <Field label="Work Location" value={employee.work_location} />
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center gap-2">
          <Briefcase className="h-4 w-4 text-brand-600" aria-hidden="true" />
          <h2 className="font-display text-sm font-semibold text-stone-700">Employment Information</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Department" value={employee.department.name} />
          <Field label="Designation" value={employee.designation.name} />
          <Field label="Reporting Manager" value={employee.manager?.full_name} />
          <Field label="Employment Type" value={employee.employment_type.replace(/_/g, " ")} />
          <Field label="Date of Joining" value={employee.date_of_joining} />
        </div>
      </Card>

      {canViewAttendance && (
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <CalendarRange className="h-4 w-4 text-brand-600" aria-hidden="true" />
              <h2 className="font-display text-sm font-semibold text-stone-700">Attendance Calendar</h2>
            </div>
            {canFixAttendance && (
              <Button
                variant="secondary"
                size="sm"
                icon={<CalendarPlus className="h-4 w-4" />}
                onClick={() =>
                  setRecordTarget({ employeeId: employee.id, employeeName: employee.full_name, dateIso: toIsoDate(new Date()) })
                }
              >
                Leave / permission
              </Button>
            )}
          </div>
          <AttendanceCalendar employeeId={employee.id} employeeName={employee.full_name} canFix={canFixAttendance} />
        </Card>
      )}

      {canViewDocuments && (
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <FileText className="h-4 w-4 text-brand-600" aria-hidden="true" />
            <h2 className="font-display text-sm font-semibold text-stone-700">Documents</h2>
          </div>
          {isLoadingDocuments ? (
            <LoadingState label="Loading documents..." />
          ) : documentsError ? (
            <ErrorState message={documentsError} />
          ) : documents.length === 0 ? (
            <EmptyState title="No documents uploaded" description={`${employee.full_name} hasn't uploaded any documents yet.`} />
          ) : (
            <ul className="flex flex-col gap-2">
              {documents.map((doc) => {
                const state = expiryState(doc.expiry_date);
                return (
                  <li
                    key={doc.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sand-200 bg-sand-50 p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-stone-800">{doc.file_name}</p>
                      <p className="text-xs text-stone-500">
                        {doc.document_type_name} · {formatFileSize(doc.file_size)} · Added {formatTimestampDate(doc.created_at)}
                        {doc.expiry_date && (
                          <>
                            {" "}
                            ·{" "}
                            <span className={state === "expired" ? "font-semibold text-sunset-600" : state === "soon" ? "font-semibold text-amber-700" : ""}>
                              {state === "expired" ? "Expired" : "Expires"} {formatDateLong(doc.expiry_date)}
                            </span>
                          </>
                        )}
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      isLoading={downloadingId === doc.id}
                      onClick={() => handleDownloadDocument(doc)}
                      icon={<Download className="h-4 w-4" />}
                    >
                      Download
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}

      <RecordAbsenceSheet
        target={recordTarget}
        onClose={() => setRecordTarget(null)}
        onSaved={() => setRecordTarget(null)}
      />

      <ConfirmDialog
        isOpen={pendingStatus !== null}
        title={pendingStatus === "ACTIVE" ? "Reactivate employee" : "Deactivate employee"}
        message={
          pendingStatus === "ACTIVE"
            ? `Reactivate ${employee.full_name}? They will regain login access.`
            : `Deactivate ${employee.full_name}? They will lose login access immediately.`
        }
        confirmLabel={pendingStatus === "ACTIVE" ? "Reactivate" : "Deactivate"}
        isDangerous={pendingStatus !== "ACTIVE"}
        isLoading={isUpdating}
        onConfirm={handleStatusChange}
        onCancel={() => setPendingStatus(null)}
      />
    </div>
  );
}
