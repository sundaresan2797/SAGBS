import { Building2, Cake, CalendarHeart, Info, MapPin, Pencil, Phone, Mail, Save, UserCircle, UserRound, X, XCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmployeePhotoEditor } from "@/components/EmployeePhotoEditor";
import { InputField } from "@/components/ui/FormField";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { employeeService } from "@/services/employeeService";
import type { Employee } from "@/types";
import { formatDateLong, tenureText } from "@/utils/friendly";
import { EMPLOYMENT_TYPE_LABEL } from "@/utils/plainWords";

function InfoRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-3">
      <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-sand-100 text-stone-500">{icon}</span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-stone-500">{label}</p>
        <div className="break-words text-base font-medium text-stone-800">{children}</div>
      </div>
    </div>
  );
}

export function ProfilePage() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [phone, setPhone] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [notLinked, setNotLinked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    setNotLinked(false);
    try {
      const data = await employeeService.getMe();
      setEmployee(data);
      setPhone(data.phone ?? "");
    } catch (err) {
      const message = getErrorMessage(err, "We couldn't load your profile.");
      if (message.toLowerCase().includes("no employee profile")) {
        setNotLinked(true);
      } else {
        setError(message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const startEditing = () => {
    setPhone(employee?.phone ?? "");
    setFormError(null);
    setIsEditing(true);
  };

  const handleSave = async () => {
    setFormError(null);
    setIsSaving(true);
    try {
      const updated = await employeeService.updateMe(phone);
      setEmployee(updated);
      setPhone(updated.phone ?? "");
      setIsEditing(false);
      showToast("Your phone number was saved", "success");
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <LoadingState label="Loading your profile..." />;
  if (notLinked) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader icon={UserCircle} title="My Profile" />
        <Card>
          <EmptyState
            title="This login has no staff profile"
            description={`${user?.email ?? "This account"} is a system login, so there are no staff details to show.`}
          />
        </Card>
      </div>
    );
  }
  if (error || !employee) return <ErrorState message={error ?? "We couldn't find your profile."} onRetry={load} />;

  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-col items-center gap-3 text-center sm:flex-row sm:items-center sm:text-left">
        <EmployeePhotoEditor employeeId={employee.id} name={employee.full_name} canEdit />
        <div className="min-w-0 flex-1">
          <h1 className="break-words font-display text-2xl font-bold text-stone-800">{employee.full_name}</h1>
          <p className="text-base text-stone-600">
            {employee.designation.name} · {employee.department.name}
          </p>
          <p className="text-base text-stone-500">
            Staff ID {employee.employee_code} · With us for {tenureText(employee.date_of_joining)}
          </p>
        </div>
        <Badge status={employee.status} label={employee.status === "ACTIVE" ? "Working" : undefined} size="lg" />
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <h2 className="font-display text-lg font-bold text-stone-800">My job</h2>
          <div className="mt-1 flex flex-col divide-y divide-sand-100">
            <InfoRow icon={<Building2 className="h-5 w-5" aria-hidden="true" />} label="Department">
              {employee.department.name}
            </InfoRow>
            <InfoRow icon={<UserRound className="h-5 w-5" aria-hidden="true" />} label="I report to">
              {employee.manager
                ? employee.manager.full_name
                : user?.role === "FOUNDER"
                  ? "You lead the company"
                  : "No manager is set for you yet"}
            </InfoRow>
            <InfoRow icon={<CalendarHeart className="h-5 w-5" aria-hidden="true" />} label="Joined on">
              {formatDateLong(employee.date_of_joining)}
            </InfoRow>
            <InfoRow icon={<Info className="h-5 w-5" aria-hidden="true" />} label="Type of job">
              {EMPLOYMENT_TYPE_LABEL[employee.employment_type] ?? employee.employment_type}
            </InfoRow>
            <InfoRow icon={<MapPin className="h-5 w-5" aria-hidden="true" />} label="Where I work">
              {employee.work_location || "Not filled in"}
            </InfoRow>
            {employee.date_of_birth && (
              <InfoRow icon={<Cake className="h-5 w-5" aria-hidden="true" />} label="Date of birth">
                {formatDateLong(employee.date_of_birth)}
              </InfoRow>
            )}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-display text-lg font-bold text-stone-800">How to reach me</h2>
            {!isEditing && (
              <Button variant="secondary" onClick={startEditing} icon={<Pencil className="h-5 w-5" />}>
                Change phone
              </Button>
            )}
          </div>

          <div className="mt-1 flex flex-col divide-y divide-sand-100">
            <InfoRow icon={<Mail className="h-5 w-5" aria-hidden="true" />} label="Email">
              {employee.email}
              <p className="text-sm font-normal text-stone-500">To change your email, please ask HR.</p>
            </InfoRow>
            {!isEditing && (
              <InfoRow icon={<Phone className="h-5 w-5" aria-hidden="true" />} label="Phone number">
                {employee.phone || "Not added yet"}
              </InfoRow>
            )}
          </div>

          {isEditing && (
            <div className="mt-3 flex flex-col gap-4 rounded-2xl bg-sand-50 p-4">
              <InputField
                label="Phone number"
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
              {formError && (
                <div role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
                  <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
                  {formError}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button size="lg" isLoading={isSaving} onClick={handleSave} icon={<Save className="h-5 w-5" />}>
                  Save
                </Button>
                <Button size="lg" variant="secondary" onClick={() => setIsEditing(false)} icon={<X className="h-5 w-5" />}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
