import api from "@/services/api";
import type {
  ApiSuccess,
  LeaveAccrualFrequency,
  LeaveBalance,
  LeaveDayPart,
  LeaveRequest,
  LeaveRequestStatus,
  LeaveType,
  PaginatedData,
} from "@/types";

export const leaveService = {
  async listTypes(): Promise<LeaveType[]> {
    const response = await api.get<ApiSuccess<LeaveType[]>>("/leave-types");
    return response.data.data;
  },
  async listAllTypes(): Promise<LeaveType[]> {
    const response = await api.get<ApiSuccess<LeaveType[]>>("/leave-types/all");
    return response.data.data;
  },
  async createType(payload: {
    code: string;
    name: string;
    is_paid: boolean;
    default_annual_days: number;
    accrual_frequency: LeaveAccrualFrequency;
  }): Promise<LeaveType> {
    const response = await api.post<ApiSuccess<LeaveType>>("/leave-types", payload);
    return response.data.data;
  },
  async updateType(
    id: number,
    payload: Partial<{
      name: string;
      is_paid: boolean;
      default_annual_days: number;
      accrual_frequency: LeaveAccrualFrequency;
      is_active: boolean;
    }>
  ): Promise<LeaveType> {
    const response = await api.patch<ApiSuccess<LeaveType>>(`/leave-types/${id}`, payload);
    return response.data.data;
  },
  async deleteType(id: number): Promise<void> {
    await api.delete(`/leave-types/${id}`);
  },
  async myBalance(year?: number): Promise<LeaveBalance[]> {
    const response = await api.get<ApiSuccess<LeaveBalance[]>>("/leaves/balance", { params: { year } });
    return response.data.data;
  },
  async apply(payload: {
    leave_type_id: number;
    start_date: string;
    end_date: string;
    reason?: string;
    day_part?: LeaveDayPart;
  }): Promise<LeaveRequest> {
    const response = await api.post<ApiSuccess<LeaveRequest>>("/leaves", payload);
    return response.data.data;
  },
  /** A manager/HR entering leave for an employee who told them (approved at once). */
  async record(payload: {
    employee_id: number;
    leave_type_id: number;
    start_date: string;
    end_date: string;
    reason: string;
    day_part?: LeaveDayPart;
  }): Promise<LeaveRequest> {
    const response = await api.post<ApiSuccess<LeaveRequest>>("/leaves/record", payload);
    return response.data.data;
  },
  async myRequests(page = 1, pageSize = 20, year?: number): Promise<PaginatedData<LeaveRequest>> {
    const response = await api.get<ApiSuccess<PaginatedData<LeaveRequest>>>("/leaves/my", {
      params: { page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  /** One employee's leave requests (your own, your direct reports', or anyone's with attendance:read_all) -
   * used to correctly tell an Absent day apart from an On-leave day on their calendar. */
  async forEmployee(employeeId: number, page = 1, pageSize = 20, year?: number): Promise<PaginatedData<LeaveRequest>> {
    const response = await api.get<ApiSuccess<PaginatedData<LeaveRequest>>>(`/leaves/employee/${employeeId}`, {
      params: { page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  async teamRequests(status?: LeaveRequestStatus, page = 1, pageSize = 20, year?: number): Promise<PaginatedData<LeaveRequest>> {
    const response = await api.get<ApiSuccess<PaginatedData<LeaveRequest>>>("/leaves/team", {
      params: { status, page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  async allRequests(status?: LeaveRequestStatus, page = 1, pageSize = 20, year?: number): Promise<PaginatedData<LeaveRequest>> {
    const response = await api.get<ApiSuccess<PaginatedData<LeaveRequest>>>("/leaves/requests", {
      params: { status, page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  async approve(id: number): Promise<LeaveRequest> {
    const response = await api.patch<ApiSuccess<LeaveRequest>>(`/leaves/${id}/approve`);
    return response.data.data;
  },
  async reject(id: number, rejectionReason?: string): Promise<LeaveRequest> {
    const response = await api.patch<ApiSuccess<LeaveRequest>>(`/leaves/${id}/reject`, {
      rejection_reason: rejectionReason,
    });
    return response.data.data;
  },
  async cancel(id: number): Promise<LeaveRequest> {
    const response = await api.patch<ApiSuccess<LeaveRequest>>(`/leaves/${id}/cancel`);
    return response.data.data;
  },
};
