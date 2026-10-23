import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { ApiError, ApiSuccess } from "@/types";
import { tokenStorage } from "@/utils/tokenStorage";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return null;

  try {
    const response = await axios.post<ApiSuccess<{ access_token: string }>>(
      `${API_BASE_URL}/auth/refresh`,
      { refresh_token: refreshToken },
    );
    const newToken = response.data.data.access_token;
    tokenStorage.setAccessToken(newToken);
    return newToken;
  } catch {
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;

      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const newToken = await refreshPromise;

      if (newToken) {
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }

      tokenStorage.clear();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  },
);

export function getErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError(error)) {
    const apiError = error.response?.data as ApiError | undefined;
    if (apiError?.message) return apiError.message;
    if (error.code === "ERR_NETWORK") return "Unable to reach the server. Check your connection.";
  }
  return fallback;
}

// A `responseType: "blob"` request (file downloads) gets its error body back
// as a Blob too, so the normal JSON-shaped getErrorMessage can't read it -
// this reads the blob's text and parses it the same way instead.
export async function getBlobErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): Promise<string> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      const text = await error.response.data.text();
      const parsed = JSON.parse(text) as ApiError;
      if (parsed?.message) return parsed.message;
    } catch {
      // fall through to the generic message below
    }
  }
  return getErrorMessage(error, fallback);
}

export default api;
