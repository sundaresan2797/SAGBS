import api from "@/services/api";
import type { ApiSuccess, DocumentTypeOption, DocumentUploadPolicy, EmployeeDocument, ExpiringDocuments } from "@/types";

export const documentService = {
  async policy(): Promise<DocumentUploadPolicy> {
    const response = await api.get<ApiSuccess<DocumentUploadPolicy>>("/documents/policy");
    return response.data.data;
  },
  async list(employeeId?: number): Promise<EmployeeDocument[]> {
    const response = await api.get<ApiSuccess<EmployeeDocument[]>>("/documents", {
      params: employeeId ? { employee_id: employeeId } : undefined,
    });
    return response.data.data;
  },
  async expiring(withinDays: number): Promise<ExpiringDocuments> {
    const response = await api.get<ApiSuccess<ExpiringDocuments>>("/documents/expiring", { params: { within_days: withinDays } });
    return response.data.data;
  },
  async upload(file: File, documentTypeId: number, expiryDate?: string, employeeId?: number): Promise<EmployeeDocument> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("document_type_id", String(documentTypeId));
    if (expiryDate) formData.append("expiry_date", expiryDate);
    if (employeeId) formData.append("employee_id", String(employeeId));

    const response = await api.post<ApiSuccess<EmployeeDocument>>("/documents", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data.data;
  },
  async download(id: number): Promise<Blob> {
    const response = await api.get(`/documents/${id}/download`, { responseType: "blob" });
    return response.data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(`/documents/${id}`);
  },
  // Document types (the dropdown on the upload form, and the Admin/HR management screen)
  async listTypes(): Promise<DocumentTypeOption[]> {
    const response = await api.get<ApiSuccess<DocumentTypeOption[]>>("/document-types");
    return response.data.data;
  },
  async listAllTypes(): Promise<DocumentTypeOption[]> {
    const response = await api.get<ApiSuccess<DocumentTypeOption[]>>("/document-types/all");
    return response.data.data;
  },
  async createType(payload: {
    code: string;
    name: string;
    description?: string;
    requires_expiry: boolean;
  }): Promise<DocumentTypeOption> {
    const response = await api.post<ApiSuccess<DocumentTypeOption>>("/document-types", payload);
    return response.data.data;
  },
  async updateType(
    id: number,
    payload: Partial<{ name: string; description: string | null; requires_expiry: boolean; is_active: boolean }>,
  ): Promise<DocumentTypeOption> {
    const response = await api.patch<ApiSuccess<DocumentTypeOption>>(`/document-types/${id}`, payload);
    return response.data.data;
  },
  async deleteType(id: number): Promise<void> {
    await api.delete(`/document-types/${id}`);
  },
};
