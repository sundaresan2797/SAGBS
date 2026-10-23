import api from "@/services/api";
import type { ApiSuccess, Holiday } from "@/types";

export const holidayService = {
  async list(year?: number): Promise<Holiday[]> {
    const response = await api.get<ApiSuccess<Holiday[]>>("/holidays", { params: year ? { year } : undefined });
    return response.data.data;
  },
  async create(payload: { name: string; holiday_date: string; description?: string; is_optional?: boolean }): Promise<Holiday> {
    const response = await api.post<ApiSuccess<Holiday>>("/holidays", payload);
    return response.data.data;
  },
  async update(id: number, payload: Partial<{ name: string; holiday_date: string; description: string; is_optional: boolean }>): Promise<Holiday> {
    const response = await api.put<ApiSuccess<Holiday>>(`/holidays/${id}`, payload);
    return response.data.data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(`/holidays/${id}`);
  },
};
