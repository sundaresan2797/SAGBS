import api from "@/services/api";
import type { ApiSuccess, AuditLog, PaginatedData } from "@/types";

export const auditLogService = {
  async list(
    params: {
      user_id?: number;
      action?: string;
      entity_type?: string;
      hide_routine?: boolean;
      date_from?: string;
      date_to?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<PaginatedData<AuditLog>> {
    const response = await api.get<ApiSuccess<PaginatedData<AuditLog>>>("/audit-logs", { params });
    return response.data.data;
  },
};
