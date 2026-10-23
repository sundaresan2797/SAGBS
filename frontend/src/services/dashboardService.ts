import api from "@/services/api";
import type {
  ApiSuccess,
  AttendanceTrendPoint,
  DashboardSummary,
  DepartmentHeadcount,
  LeaveTrendPoint,
} from "@/types";

export const dashboardService = {
  async summary(): Promise<DashboardSummary> {
    const response = await api.get<ApiSuccess<DashboardSummary>>("/dashboard/summary");
    return response.data.data;
  },
  async attendanceTrend(days = 14): Promise<AttendanceTrendPoint[]> {
    const response = await api.get<ApiSuccess<AttendanceTrendPoint[]>>("/dashboard/attendance", { params: { days } });
    return response.data.data;
  },
  async leaveTrend(months = 6): Promise<LeaveTrendPoint[]> {
    const response = await api.get<ApiSuccess<LeaveTrendPoint[]>>("/dashboard/leave", { params: { months } });
    return response.data.data;
  },
  async departments(): Promise<DepartmentHeadcount[]> {
    const response = await api.get<ApiSuccess<DepartmentHeadcount[]>>("/dashboard/departments");
    return response.data.data;
  },
};
