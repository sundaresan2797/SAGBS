import api from "@/services/api";
import type { ApiSuccess, User } from "@/types";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export const authService = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await api.post<ApiSuccess<LoginResponse>>("/auth/login", { email, password });
    return response.data.data;
  },
  async me(): Promise<User> {
    const response = await api.get<ApiSuccess<User>>("/auth/me");
    return response.data.data;
  },
  async logout(): Promise<void> {
    await api.post("/auth/logout");
  },
  async forgotPassword(email: string): Promise<void> {
    await api.post("/auth/forgot-password", { email });
  },
  async resetPassword(token: string, newPassword: string): Promise<void> {
    await api.post("/auth/reset-password", { token, new_password: newPassword });
  },
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
  },
};
