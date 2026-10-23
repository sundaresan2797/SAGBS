import api from "@/services/api";
import type { ApiSuccess, Notification, PaginatedData } from "@/types";

export const notificationService = {
  async list(unreadOnly = false, page = 1, pageSize = 20): Promise<PaginatedData<Notification>> {
    const response = await api.get<ApiSuccess<PaginatedData<Notification>>>("/notifications", {
      params: { unread_only: unreadOnly, page, page_size: pageSize },
    });
    return response.data.data;
  },
  async unreadCount(): Promise<number> {
    const response = await api.get<ApiSuccess<number>>("/notifications/unread-count");
    return response.data.data;
  },
  async markRead(id: number): Promise<Notification> {
    const response = await api.patch<ApiSuccess<Notification>>(`/notifications/${id}/read`);
    return response.data.data;
  },
  async markAllRead(): Promise<void> {
    await api.patch("/notifications/read-all");
  },
};
