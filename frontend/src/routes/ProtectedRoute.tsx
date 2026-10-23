import { Navigate, Outlet, useLocation } from "react-router-dom";

import { LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import type { Role } from "@/types";

export function ProtectedRoute() {
  const { user, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <LoadingState label="Checking your session..." />;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  // A temporary or starter password has to be replaced before anything else: Settings is the only screen
  // open until then (the server clears this flag itself when the password is changed).
  if (user?.must_change_password && location.pathname !== "/settings") return <Navigate to="/settings" replace />;

  return <Outlet />;
}

export function RoleRoute({ allowed }: { allowed: Role[] }) {
  const { hasRole } = useAuth();
  if (!hasRole(...allowed)) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

export function PermissionRoute({ permission }: { permission: string }) {
  const { hasPermission } = useAuth();
  if (!hasPermission(permission)) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
