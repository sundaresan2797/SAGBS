import api from "@/services/api";
import type { ApiSuccess, PermissionsMatrix } from "@/types";

export const roleService = {
  async permissionsMatrix(): Promise<PermissionsMatrix> {
    const response = await api.get<ApiSuccess<PermissionsMatrix>>("/roles/permissions-matrix");
    return response.data.data;
  },
  async setPermission(role: string, code: string, granted: boolean): Promise<PermissionsMatrix> {
    const response = await api.put<ApiSuccess<PermissionsMatrix>>(
      `/roles/${role}/permissions/${encodeURIComponent(code)}`,
      { granted },
    );
    return response.data.data;
  },
};
