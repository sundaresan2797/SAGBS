import api from "@/services/api";
import type { ApiSuccess, PhotoIndexEntry, PhotoResult } from "@/types";

export const photoService = {
  async index(): Promise<PhotoIndexEntry[]> {
    const response = await api.get<ApiSuccess<PhotoIndexEntry[]>>("/employees/photo-index");
    return response.data.data;
  },
  /** The picture itself. It needs the sign-in token, so it is fetched as data rather than put in an <img src>. */
  async fetchBlob(employeeId: number): Promise<Blob> {
    const response = await api.get<Blob>(`/employees/${employeeId}/photo`, { responseType: "blob" });
    return response.data;
  },
  async upload(employeeId: number, file: File): Promise<PhotoResult> {
    const form = new FormData();
    form.append("file", file);
    // Same as document uploads: without this header the shared client would send the form as JSON.
    const response = await api.put<ApiSuccess<PhotoResult>>(`/employees/${employeeId}/photo`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data.data;
  },
  async remove(employeeId: number): Promise<PhotoResult> {
    const response = await api.delete<ApiSuccess<PhotoResult>>(`/employees/${employeeId}/photo`);
    return response.data.data;
  },
};
