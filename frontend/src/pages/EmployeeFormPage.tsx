import { zodResolver } from "@hookform/resolvers/zod";
import { UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { CredentialModal } from "@/components/CredentialModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { InputField, SelectField } from "@/components/ui/FormField";
import { LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { departmentService, designationService, employeeService } from "@/services/employeeService";
import { fetchAllPages } from "@/utils/paging";
import type { Department, Designation, Employee, EmployeeListItem, Role } from "@/types";

const today = new Date().toISOString().slice(0, 10);

const employeeSchema = z.object({
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  email: z.string().min(1, "Email is required").email("Invalid email address"),
  phone: z.string().optional(),
  date_of_birth: z
    .string()
    .optional()
    .refine((value) => !value || value < today, "Date of birth must be in the past"),
  date_of_joining: z
    .string()
    .min(1, "Date of joining is required")
    .refine((value) => value <= today, "Date of joining cannot be in the future"),
  department_id: z.string().min(1, "Department is required"),
  designation_id: z.string().min(1, "Designation is required"),
  manager_id: z.string().optional(),
  employment_type: z.enum(["FULL_TIME", "PART_TIME", "CONTRACT", "INTERN"]),
  work_location: z.string().optional(),
  // Only chosen when adding someone. Editing has no such field, so it must not be required there - a
  // required hidden field made every edit fail validation silently, and nothing was ever sent.
  role: z.enum(["ADMIN", "FOUNDER", "HR", "EXECUTIVE", "ACCOUNTANT", "MANAGER", "EMPLOYEE"]).optional(),
});

// Mirrors the backend rule in employee_service.create_employee: only an
// Admin can grant Admin/Founder/HR/Executive/Accountant access, so HR only sees the
// roles it's actually allowed to assign. The backend re-checks this
// regardless - this is just so HR doesn't hit a 403 after filling out the
// whole form.
function assignableRoles(currentRole: Role | undefined): Role[] {
  return currentRole === "ADMIN"
    ? ["ADMIN", "FOUNDER", "HR", "EXECUTIVE", "ACCOUNTANT", "MANAGER", "EMPLOYEE"]
    : ["MANAGER", "EMPLOYEE"];
}

type EmployeeFormValues = z.infer<typeof employeeSchema>;

export function EmployeeFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEditMode = Boolean(id);
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { user } = useAuth();
  const roleOptions = assignableRoles(user?.role);

  const [departments, setDepartments] = useState<Department[]>([]);
  const [designations, setDesignations] = useState<Designation[]>([]);
  const [managers, setManagers] = useState<EmployeeListItem[]>([]);
  const [existing, setExisting] = useState<Employee | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [credential, setCredential] = useState<{ email: string; password: string } | null>(null);
  const [createdEmployeeId, setCreatedEmployeeId] = useState<number | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeSchema),
    defaultValues: { employment_type: "FULL_TIME", role: "EMPLOYEE" },
  });

  const selectedDepartmentId = watch("department_id");
  const selectedDesignationId = watch("designation_id");

  useEffect(() => {
    async function loadOptions() {
      setIsLoading(true);
      try {
        const [deptData, managerData] = await Promise.all([
          departmentService.list(),
          // The server sends at most 100 at a time, so keep asking until every person is in the list.
          fetchAllPages((page) => employeeService.list({ page, page_size: 100, status: "ACTIVE" })),
        ]);
        setDepartments(deptData);
        setManagers(managerData);

        if (id) {
          const employee = await employeeService.getById(Number(id));
          setExisting(employee);
          reset({
            first_name: employee.full_name.split(" ")[0],
            last_name: employee.full_name.split(" ").slice(1).join(" "),
            email: employee.email,
            phone: employee.phone ?? "",
            date_of_birth: employee.date_of_birth ?? "",
            date_of_joining: employee.date_of_joining,
            department_id: String(employee.department.id),
            designation_id: String(employee.designation.id),
            manager_id: employee.manager ? String(employee.manager.id) : "",
            employment_type: employee.employment_type,
            work_location: employee.work_location ?? "",
          });
        }
      } catch (err) {
        showToast(getErrorMessage(err, "Unable to load form data."), "error");
      } finally {
        setIsLoading(false);
      }
    }
    loadOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!selectedDepartmentId) {
      setDesignations([]);
      return;
    }
    designationService.list(Number(selectedDepartmentId)).then(setDesignations).catch(() => undefined);
  }, [selectedDepartmentId]);

  const onSubmit = async (values: EmployeeFormValues) => {
    const payload = {
      first_name: values.first_name,
      last_name: values.last_name,
      phone: values.phone || undefined,
      date_of_birth: values.date_of_birth || undefined,
      date_of_joining: values.date_of_joining,
      department_id: Number(values.department_id),
      designation_id: Number(values.designation_id),
      manager_id: values.manager_id ? Number(values.manager_id) : null,
      employment_type: values.employment_type,
      work_location: values.work_location || undefined,
    };

    try {
      if (isEditMode && existing) {
        await employeeService.update(existing.id, payload);
        showToast("Employee updated successfully", "success");
        navigate(`/employees/${existing.id}`);
      } else {
        const result = await employeeService.create({ ...payload, email: values.email, role: values.role ?? "EMPLOYEE" });
        // Shown in a persistent modal (see handleCredentialModalClose), not a
        // toast: the temporary password is unrecoverable once dismissed.
        setCreatedEmployeeId(result.employee.id);
        setCredential({ email: result.login_email, password: result.temporary_password });
      }
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  };

  if (isLoading) return <LoadingState label="Loading form..." />;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <UserPlus className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-stone-800">
            {isEditMode ? "Edit Employee" : "Add Employee"}
          </h1>
          <p className="text-sm text-stone-500">
            {isEditMode ? "Update this person's details" : "Fill in the details to add a new team member"}
          </p>
        </div>
      </div>

      <Card>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <InputField label="First Name" error={errors.first_name?.message} required {...register("first_name")} />
          <InputField label="Last Name" error={errors.last_name?.message} required {...register("last_name")} />
          <InputField
            label="Email"
            type="email"
            error={errors.email?.message}
            required
            disabled={isEditMode}
            {...register("email")}
          />
          <InputField label="Phone" error={errors.phone?.message} {...register("phone")} />
          <InputField
            label="Date of Birth"
            type="date"
            max={today}
            error={errors.date_of_birth?.message}
            {...register("date_of_birth")}
          />
          {!isEditMode && (
            <SelectField label="Login Role" error={errors.role?.message} required {...register("role")}>
              {roleOptions.map((role) => (
                <option key={role} value={role}>
                  {role.charAt(0) + role.slice(1).toLowerCase()}
                </option>
              ))}
            </SelectField>
          )}
          <InputField
            label="Date of Joining"
            type="date"
            max={today}
            error={errors.date_of_joining?.message}
            required
            {...register("date_of_joining")}
          />
          <SelectField label="Employment Type" required {...register("employment_type")}>
            <option value="FULL_TIME">Full Time</option>
            <option value="PART_TIME">Part Time</option>
            <option value="CONTRACT">Contract</option>
            <option value="INTERN">Intern</option>
          </SelectField>
          <SelectField
            label="Department"
            error={errors.department_id?.message}
            required
            {...register("department_id")}
          >
            <option value="">Select department</option>
            {/* Inactive departments aren't offered for a new assignment - except the one this
                employee is already in, so editing them doesn't force a change they didn't ask for. */}
            {departments
              .filter((d) => d.status === "ACTIVE" || String(d.id) === selectedDepartmentId)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {d.status !== "ACTIVE" ? " (inactive)" : ""}
                </option>
              ))}
          </SelectField>
          <SelectField
            label="Designation"
            error={errors.designation_id?.message}
            required
            disabled={!selectedDepartmentId}
            {...register("designation_id")}
          >
            <option value="">Select designation</option>
            {/* Inactive designations aren't offered for a new assignment - except the one this
                employee already holds, so editing them doesn't force a change they didn't ask for. */}
            {designations
              .filter((d) => d.status === "ACTIVE" || String(d.id) === selectedDesignationId)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {d.status !== "ACTIVE" ? " (inactive)" : ""}
                </option>
              ))}
          </SelectField>
          <SelectField label="Reporting Manager" {...register("manager_id")}>
            <option value="">No manager</option>
            {managers.filter((m) => m.id !== existing?.id).map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name}
              </option>
            ))}
          </SelectField>
          <InputField label="Work Location" {...register("work_location")} />

          <div className="col-span-full flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isSubmitting} icon={<UserPlus className="h-4 w-4" />}>
              {isEditMode ? "Save Changes" : "Create Employee"}
            </Button>
          </div>
        </form>
      </Card>

      {credential && (
        <CredentialModal
          isOpen
          title="Employee created"
          email={credential.email}
          password={credential.password}
          onClose={() => {
            setCredential(null);
            if (createdEmployeeId) navigate(`/employees/${createdEmployeeId}`);
          }}
        />
      )}
    </div>
  );
}
