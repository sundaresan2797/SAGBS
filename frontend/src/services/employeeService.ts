import api from "@/services/api";
import type {
  EmailChangeResult,
  ApiSuccess,
  Department,
  Designation,
  Employee,
  EmployeeCreatedResponse,
  EmployeeListItem,
  EmployeeStatus,
  EmploymentType,
  LoginRules,
  PaginatedData,
  PasswordResetResult,
} from "@/types";

export interface EmployeeFilters {
  search?: string;
  department_id?: number;
  designation_id?: number;
  manager_id?: number;
  status?: EmployeeStatus;
  employment_type?: EmploymentType;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_desc?: boolean;
}

export interface EmployeeCreatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  date_of_birth?: string;
  date_of_joining: string;
  department_id: number;
  designation_id: number;
  manager_id?: number | null;
  employment_type: EmploymentType;
  work_location?: string;
  role?: string;
}

export const employeeService = {
  async list(filters: EmployeeFilters): Promise<PaginatedData<EmployeeListItem>> {
    const response = await api.get<ApiSuccess<PaginatedData<EmployeeListItem>>>("/employees", { params: filters });
    return response.data.data;
  },
  async getById(id: number): Promise<Employee> {
    const response = await api.get<ApiSuccess<Employee>>(`/employees/${id}`);
    return response.data.data;
  },
  async getMe(): Promise<Employee> {
    const response = await api.get<ApiSuccess<Employee>>("/employees/me");
    return response.data.data;
  },
  async updateMe(phone: string): Promise<Employee> {
    const response = await api.patch<ApiSuccess<Employee>>("/employees/me", { phone });
    return response.data.data;
  },
  async create(payload: EmployeeCreatePayload): Promise<EmployeeCreatedResponse> {
    const response = await api.post<ApiSuccess<EmployeeCreatedResponse>>("/employees", payload);
    return response.data.data;
  },
  async update(id: number, payload: Partial<EmployeeCreatePayload>): Promise<Employee> {
    const response = await api.put<ApiSuccess<Employee>>(`/employees/${id}`, payload);
    return response.data.data;
  },
  async updateStatus(id: number, status: EmployeeStatus): Promise<Employee> {
    const response = await api.patch<ApiSuccess<Employee>>(`/employees/${id}/status`, { status });
    return response.data.data;
  },
  async loginRules(): Promise<LoginRules> {
    const response = await api.get<ApiSuccess<LoginRules>>("/employees/login-rules");
    return response.data.data;
  },
  async changeRole(id: number, role: string): Promise<void> {
    await api.patch(`/employees/${id}/role`, { role });
  },
  async resetPassword(id: number, newPassword?: string): Promise<PasswordResetResult> {
    const response = await api.post<ApiSuccess<PasswordResetResult>>(`/employees/${id}/reset-password`, {
      new_password: newPassword || undefined,
    });
    return response.data.data;
  },
  async changeEmail(id: number, newEmail: string): Promise<EmailChangeResult> {
    const response = await api.patch<ApiSuccess<EmailChangeResult>>(`/employees/${id}/email`, { new_email: newEmail });
    return response.data.data;
  },
};

export const departmentService = {
  async list(): Promise<Department[]> {
    const response = await api.get<ApiSuccess<Department[]>>("/departments");
    return response.data.data;
  },
  async create(name: string, description?: string): Promise<Department> {
    const response = await api.post<ApiSuccess<Department>>("/departments", { name, description });
    return response.data.data;
  },
  async update(id: number, payload: Partial<{ name: string; description: string; status: string }>): Promise<Department> {
    const response = await api.put<ApiSuccess<Department>>(`/departments/${id}`, payload);
    return response.data.data;
  },
};

export const designationService = {
  async list(departmentId?: number): Promise<Designation[]> {
    const response = await api.get<ApiSuccess<Designation[]>>("/designations", {
      params: departmentId ? { department_id: departmentId } : undefined,
    });
    return response.data.data;
  },
  async create(name: string, departmentId: number, description?: string): Promise<Designation> {
    const response = await api.post<ApiSuccess<Designation>>("/designations", {
      name,
      department_id: departmentId,
      description,
    });
    return response.data.data;
  },
  async update(id: number, payload: Partial<{ name: string; description: string; department_id: number; status: string }>): Promise<Designation> {
    const response = await api.put<ApiSuccess<Designation>>(`/designations/${id}`, payload);
    return response.data.data;
  },
};
