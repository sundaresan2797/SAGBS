import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/layouts/AppLayout";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { PhotosProvider } from "@/hooks/usePhotos";
import { ToastProvider } from "@/hooks/useToast";
import { AuditLogsPage } from "@/pages/AuditLogsPage";
import { AttendanceSummaryPage } from "@/pages/AttendanceSummaryPage";
import { AttendancePage } from "@/pages/AttendancePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { DesignationsPage } from "@/pages/DesignationsPage";
import { DocumentTypesPage } from "@/pages/DocumentTypesPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { EmployeeDetailPage } from "@/pages/EmployeeDetailPage";
import { EmployeeFormPage } from "@/pages/EmployeeFormPage";
import { EmployeesListPage } from "@/pages/EmployeesListPage";
import { ExpenseClaimsPage } from "@/pages/ExpenseClaimsPage";
import { HolidaysPage } from "@/pages/HolidaysPage";
import { LeaveRequestsPage } from "@/pages/LeaveRequestsPage";
import { LeaveTypesPage } from "@/pages/LeaveTypesPage";
import { LoginPage } from "@/pages/LoginPage";
import { MyAttendancePage } from "@/pages/MyAttendancePage";
import { MyExpensesPage } from "@/pages/MyExpensesPage";
import { MyLeavePage } from "@/pages/MyLeavePage";
import { MyPayslipsPage } from "@/pages/MyPayslipsPage";
import { MyTasksPage } from "@/pages/MyTasksPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { SalaryPage } from "@/pages/SalaryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TasksPage } from "@/pages/TasksPage";
import { RolesPermissionsPage } from "@/pages/RolesPermissionsPage";
import { UserAccountsPage } from "@/pages/UserAccountsPage";
import { PermissionRoute, ProtectedRoute } from "@/routes/ProtectedRoute";
import { COMPANY_NAME } from "@/config/company";
import { LoadingState } from "@/components/ui/StateViews";

function AppRoutes() {
  const { isLoading } = useAuth();
  if (isLoading) return <LoadingState label={`Loading ${COMPANY_NAME}...`} />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />

          <Route element={<PermissionRoute permission="employee:read" />}>
            <Route path="/employees" element={<EmployeesListPage />} />
            <Route path="/employees/:id" element={<EmployeeDetailPage />} />
          </Route>
          <Route element={<PermissionRoute permission="employee:create" />}>
            <Route path="/employees/new" element={<EmployeeFormPage />} />
          </Route>
          <Route element={<PermissionRoute permission="employee:update" />}>
            <Route path="/employees/:id/edit" element={<EmployeeFormPage />} />
          </Route>

          <Route element={<PermissionRoute permission="department:manage" />}>
            <Route path="/departments" element={<DepartmentsPage />} />
            <Route path="/designations" element={<DesignationsPage />} />
          </Route>

          <Route path="/attendance" element={<AttendancePage />} />
          <Route path="/attendance/my" element={<MyAttendancePage />} />

          <Route path="/leave/my" element={<MyLeavePage />} />
          <Route path="/leave/requests" element={<LeaveRequestsPage />} />
          <Route element={<PermissionRoute permission="leave_type:manage" />}>
            <Route path="/leave/types" element={<LeaveTypesPage />} />
          </Route>

          <Route path="/holidays" element={<HolidaysPage />} />

          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/tasks/my" element={<MyTasksPage />} />

          <Route path="/documents" element={<DocumentsPage />} />
          <Route element={<PermissionRoute permission="document_type:manage" />}>
            <Route path="/documents/types" element={<DocumentTypesPage />} />
          </Route>
          <Route path="/notifications" element={<NotificationsPage />} />

          <Route path="/expenses/my" element={<MyExpensesPage />} />
          <Route path="/salary/my" element={<MyPayslipsPage />} />
          <Route element={<PermissionRoute permission="payroll:view" />}>
            <Route path="/payroll" element={<SalaryPage />} />
            <Route path="/payroll/attendance" element={<AttendanceSummaryPage />} />
            <Route path="/expenses" element={<ExpenseClaimsPage />} />
          </Route>

          <Route element={<PermissionRoute permission="audit:view" />}>
            <Route path="/audit-logs" element={<AuditLogsPage />} />
          </Route>

          <Route element={<PermissionRoute permission="user:manage" />}>
            <Route path="/user-accounts" element={<UserAccountsPage />} />
          </Route>

          <Route element={<PermissionRoute permission="role:manage" />}>
            <Route path="/roles-permissions" element={<RolesPermissionsPage />} />
          </Route>

          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <PhotosProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
      </PhotosProvider>
    </AuthProvider>
  );
}

export default App;
