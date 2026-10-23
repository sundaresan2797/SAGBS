import api from "@/services/api";
import type { ApiSuccess, PaginatedData, Task, TaskComment, TaskPriority, TaskStatus } from "@/types";

export const taskService = {
  async create(payload: { title: string; description?: string; assigned_to: number; priority?: TaskPriority; due_date?: string }): Promise<Task> {
    const response = await api.post<ApiSuccess<Task>>("/tasks", payload);
    return response.data.data;
  },
  async myTasks(status?: TaskStatus, page = 1, pageSize = 20): Promise<PaginatedData<Task>> {
    const response = await api.get<ApiSuccess<PaginatedData<Task>>>("/tasks/my", {
      params: { status, page, page_size: pageSize },
    });
    return response.data.data;
  },
  async teamTasks(
    params: {
      status?: TaskStatus;
      due_date_from?: string;
      due_date_to?: string;
      assigned_to?: number;
      page?: number;
      page_size?: number;
    } = {}
  ): Promise<PaginatedData<Task>> {
    const response = await api.get<ApiSuccess<PaginatedData<Task>>>("/tasks/team", {
      params: { page: 1, page_size: 200, ...params },
    });
    return response.data.data;
  },
  async getById(id: number): Promise<Task> {
    const response = await api.get<ApiSuccess<Task>>(`/tasks/${id}`);
    return response.data.data;
  },
  async updateStatus(id: number, status: TaskStatus): Promise<Task> {
    const response = await api.patch<ApiSuccess<Task>>(`/tasks/${id}/status`, { status });
    return response.data.data;
  },
  async listComments(id: number): Promise<TaskComment[]> {
    const response = await api.get<ApiSuccess<TaskComment[]>>(`/tasks/${id}/comments`);
    return response.data.data;
  },
  async addComment(id: number, comment: string): Promise<TaskComment> {
    const response = await api.post<ApiSuccess<TaskComment>>(`/tasks/${id}/comments`, { comment });
    return response.data.data;
  },
};
