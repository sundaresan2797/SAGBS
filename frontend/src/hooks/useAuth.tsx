import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { authService } from "@/services/authService";
import type { User } from "@/types";
import { tokenStorage } from "@/utils/tokenStorage";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  hasPermission: (code: string) => boolean;
  hasRole: (...roles: User["role"][]) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => tokenStorage.getUser());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      if (!tokenStorage.getAccessToken()) {
        setIsLoading(false);
        return;
      }
      try {
        const freshUser = await authService.me();
        if (!cancelled) setUser(freshUser);
      } catch {
        if (!cancelled) {
          tokenStorage.clear();
          setUser(null);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authService.login(email, password);
    tokenStorage.setSession(result.access_token, result.refresh_token, result.user);
    setUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
    authService.logout().catch(() => undefined);
  }, []);

  const hasPermission = useCallback((code: string) => Boolean(user?.permissions.includes(code)), [user]);
  const hasRole = useCallback((...roles: User["role"][]) => Boolean(user && roles.includes(user.role)), [user]);

  const value = useMemo(
    () => ({ user, isLoading, isAuthenticated: Boolean(user), login, logout, hasPermission, hasRole }),
    [user, isLoading, login, logout, hasPermission, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
