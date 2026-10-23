import api from "@/services/api";
import type {
  AttendanceSummary,
  ApiSuccess,
  ExpenseClaim,
  ExpenseClaimCategory,
  ExpenseClaimStatus,
  PaginatedData,
  PayrollDirectoryEntry,
  SalaryPayment,
  SalaryRecord,
  UnpaidEarlier,
} from "@/types";

export const payrollService = {
  // Salary
  async getPayrollDirectory(): Promise<PayrollDirectoryEntry[]> {
    const response = await api.get<ApiSuccess<PayrollDirectoryEntry[]>>("/payroll/directory");
    return response.data.data;
  },
  async listSalaryRecords(): Promise<SalaryRecord[]> {
    const response = await api.get<ApiSuccess<SalaryRecord[]>>("/salary-records");
    return response.data.data;
  },
  async setSalaryRecord(payload: {
    employee_id: number;
    basic_pay: number;
    allowances: number;
    deductions: number;
    effective_from: string;
  }): Promise<SalaryRecord> {
    const response = await api.post<ApiSuccess<SalaryRecord>>("/salary-records", payload);
    return response.data.data;
  },
  async runPayroll(year: number, month: number): Promise<SalaryPayment[]> {
    const response = await api.post<ApiSuccess<SalaryPayment[]>>("/salary-payments/run", { year, month });
    return response.data.data;
  },
  async attendanceSummary(year: number, month: number): Promise<AttendanceSummary> {
    const response = await api.get<ApiSuccess<AttendanceSummary>>("/payroll/attendance-summary", { params: { year, month } });
    return response.data.data;
  },
  async downloadAttendanceSummary(year: number, month: number): Promise<{ blob: Blob; filename: string }> {
    const response = await api.get("/payroll/attendance-summary/export", { params: { year, month }, responseType: "blob" });
    const disposition = response.headers["content-disposition"] as string | undefined;
    const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? `Attendance_Summary_${year}_${month}.xlsx`;
    return { blob: response.data as Blob, filename };
  },
  async listSalaryPayments(year: number, month: number): Promise<SalaryPayment[]> {
    const response = await api.get<ApiSuccess<SalaryPayment[]>>("/salary-payments", { params: { year, month } });
    return response.data.data;
  },
  async unpaidEarlier(year: number, month: number): Promise<UnpaidEarlier> {
    const response = await api.get<ApiSuccess<UnpaidEarlier>>("/salary-payments/unpaid-earlier", { params: { year, month } });
    return response.data.data;
  },
  async markSalaryPaid(id: number): Promise<SalaryPayment> {
    const response = await api.patch<ApiSuccess<SalaryPayment>>(`/salary-payments/${id}/pay`);
    return response.data.data;
  },
  async downloadPayslip(id: number): Promise<{ blob: Blob; filename: string }> {
    const response = await api.get(`/salary-payments/${id}/payslip`, { responseType: "blob" });
    const disposition = response.headers["content-disposition"] as string | undefined;
    const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? `payslip-${id}.pdf`;
    return { blob: response.data as Blob, filename };
  },
  async mySalaryRecord(): Promise<SalaryRecord | null> {
    const response = await api.get<ApiSuccess<SalaryRecord | null>>("/salary-records/my");
    return response.data.data;
  },
  async mySalaryHistory(): Promise<SalaryRecord[]> {
    const response = await api.get<ApiSuccess<SalaryRecord[]>>("/salary-records/my/history");
    return response.data.data;
  },
  async salaryHistory(employeeId: number): Promise<SalaryRecord[]> {
    const response = await api.get<ApiSuccess<SalaryRecord[]>>(`/salary-records/${employeeId}/history`);
    return response.data.data;
  },
  async mySalaryPayments(page = 1, pageSize = 20, year?: number): Promise<PaginatedData<SalaryPayment>> {
    const response = await api.get<ApiSuccess<PaginatedData<SalaryPayment>>>("/salary-payments/my", {
      params: { page, page_size: pageSize, year },
    });
    return response.data.data;
  },

  // Expense claims
  async submitExpenseClaim(payload: { category: ExpenseClaimCategory; amount: number; description?: string }): Promise<ExpenseClaim> {
    const response = await api.post<ApiSuccess<ExpenseClaim>>("/expenses", payload);
    return response.data.data;
  },
  async myExpenseClaims(page = 1, pageSize = 20, year?: number): Promise<PaginatedData<ExpenseClaim>> {
    const response = await api.get<ApiSuccess<PaginatedData<ExpenseClaim>>>("/expenses/my", {
      params: { page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  async allExpenseClaims(status?: ExpenseClaimStatus, page = 1, pageSize = 20, year?: number): Promise<PaginatedData<ExpenseClaim>> {
    const response = await api.get<ApiSuccess<PaginatedData<ExpenseClaim>>>("/expenses", {
      params: { status, page, page_size: pageSize, year },
    });
    return response.data.data;
  },
  async approveExpenseClaim(id: number): Promise<ExpenseClaim> {
    const response = await api.patch<ApiSuccess<ExpenseClaim>>(`/expenses/${id}/approve`);
    return response.data.data;
  },
  async rejectExpenseClaim(id: number, rejectionReason?: string): Promise<ExpenseClaim> {
    const response = await api.patch<ApiSuccess<ExpenseClaim>>(`/expenses/${id}/reject`, {
      rejection_reason: rejectionReason,
    });
    return response.data.data;
  },
  async payExpenseClaim(id: number): Promise<ExpenseClaim> {
    const response = await api.patch<ApiSuccess<ExpenseClaim>>(`/expenses/${id}/pay`);
    return response.data.data;
  },
};
