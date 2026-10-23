import api from "@/services/api";
import type {
  ApiSuccess,
  Attendance,
  AttendancePolicy,
  MissedCheckOuts,
  OvertimeSummaryEntry,
  PaginatedData,
  PermissionList,
  RollCall,
  RollCallStatus,
  ShortPermission,
} from "@/types";

export const attendanceService = {
  async checkIn(): Promise<Attendance> {
    const response = await api.post<ApiSuccess<Attendance>>("/attendance/check-in");
    return response.data.data;
  },
  async checkOut(): Promise<Attendance> {
    const response = await api.post<ApiSuccess<Attendance>>("/attendance/check-out");
    return response.data.data;
  },
  async policy(): Promise<AttendancePolicy> {
    const response = await api.get<ApiSuccess<AttendancePolicy>>("/attendance/policy");
    return response.data.data;
  },
  async missedCheckOuts(): Promise<MissedCheckOuts> {
    const response = await api.get<ApiSuccess<MissedCheckOuts>>("/attendance/missed-checkouts");
    return response.data.data;
  },
  async fixCheckOut(attendanceId: number, checkOutTime: string, reason: string): Promise<Attendance> {
    const response = await api.post<ApiSuccess<Attendance>>(`/attendance/${attendanceId}/fix-check-out`, {
      check_out_time: checkOutTime,
      reason,
    });
    return response.data.data;
  },
  async markPresent(payload: {
    employee_id: number;
    attendance_date: string;
    check_in_time: string;
    check_out_time: string;
    reason: string;
  }): Promise<Attendance> {
    const response = await api.post<ApiSuccess<Attendance>>("/attendance/mark-present", payload);
    return response.data.data;
  },
  /** Correct an already-recorded day: new times (`check_in_time`/`check_out_time` given), or both left out
   * to clear the day back to Absent. Returns the corrected record, or null when the day was cleared. */
  async correctAttendance(payload: {
    employee_id: number;
    attendance_date: string;
    check_in_time?: string;
    check_out_time?: string;
    reason: string;
  }): Promise<Attendance | null> {
    const response = await api.post<ApiSuccess<Attendance | null>>("/attendance/correct", payload);
    return response.data.data;
  },
  async recordPermission(payload: {
    employee_id: number;
    permission_date: string;
    minutes: number;
    reason: string;
  }): Promise<ShortPermission> {
    const response = await api.post<ApiSuccess<ShortPermission>>("/attendance/permissions", payload);
    return response.data.data;
  },
  async listPermissions(employeeId: number, year: number, month: number): Promise<PermissionList> {
    const response = await api.get<ApiSuccess<PermissionList>>("/attendance/permissions", {
      params: { employee_id: employeeId, year, month },
    });
    return response.data.data;
  },
  async cancelPermission(id: number): Promise<void> {
    await api.delete(`/attendance/permissions/${id}`);
  },
  async overtimeSummary(year: number, month: number): Promise<OvertimeSummaryEntry[]> {
    const response = await api.get<ApiSuccess<OvertimeSummaryEntry[]>>("/attendance/overtime-summary", {
      params: { year, month },
    });
    return response.data.data;
  },
  async myAttendance(page = 1, pageSize = 20): Promise<PaginatedData<Attendance>> {
    const response = await api.get<ApiSuccess<PaginatedData<Attendance>>>("/attendance/me", {
      params: { page, page_size: pageSize },
    });
    return response.data.data;
  },
  async rollCall(params: {
    date?: string;
    department_id?: number;
    search?: string;
    status?: RollCallStatus;
    page?: number;
    page_size?: number;
  }): Promise<RollCall> {
    const response = await api.get<ApiSuccess<RollCall>>("/attendance/roll-call", { params });
    return response.data.data;
  },
  async calendar(employeeId: number, year: number, month: number): Promise<Attendance[]> {
    const response = await api.get<ApiSuccess<Attendance[]>>(`/attendance/employee/${employeeId}/calendar`, {
      params: { year, month },
    });
    return response.data.data;
  },
};
