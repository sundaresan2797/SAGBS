import { Bell, LogOut, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { BrandMark } from "@/components/BrandMark";
import { Avatar } from "@/components/ui/EntityCard";
import { PoweredBy } from "@/components/PoweredBy";
import { useAuth } from "@/hooks/useAuth";
import { notificationService } from "@/services/notificationService";
import { getBottomNavItems, getNavItems } from "@/utils/navigation";
import { PhoneBottomBar } from "@/layouts/PhoneBottomBar";
import { ROLE_LABEL } from "@/utils/plainWords";

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Notifications are addressed to people with an employee profile, so a login without one (the Admin)
  // has no bell and nothing to poll for.
  const receivesNotifications = Boolean(user?.employee_id);

  useEffect(() => {
    if (!receivesNotifications) return;
    let cancelled = false;
    const refresh = () => {
      notificationService
        .unreadCount()
        .then((count) => {
          if (!cancelled) setUnreadCount(count);
        })
        .catch(() => undefined);
    };
    refresh();
    // The Notifications page announces "something was read" so the bell's
    // number follows along instead of staying stale until the next reload.
    window.addEventListener("ems:notifications-changed", refresh);
    // That event only covers what *this person* just did (marked something read).
    // A new notification from someone else's action (a task assigned, leave
    // decided) needs its own check - this poll is what actually finds those,
    // so the bell doesn't sit on a stale number for the rest of the session.
    const poll = setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.removeEventListener("ems:notifications-changed", refresh);
      clearInterval(poll);
    };
  }, []);

  if (!user) return null;

  // A temporary password has to be replaced first (see ProtectedRoute): until then only Settings opens,
  // so the rest of the menu is shown greyed out instead of looking clickable and bouncing back.
  const isLocked = user.must_change_password;
  const navItems = getNavItems(user.role);
  const bottomItems = getBottomNavItems(user.role);
  const phoneNav = isLocked ? navItems.filter((item) => item.path === "/settings") : navItems;
  const phoneBottom = isLocked ? phoneNav : bottomItems;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-sand-50">
      <div className="flex min-h-screen">
        <aside
          className={`fixed inset-y-0 left-0 z-30 w-64 transform flex flex-col border-r border-brand-800 bg-brand-900 transition-transform lg:static lg:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex h-16 items-center border-b border-white/10 px-5">
            <BrandMark tone="dark" />
          </div>
          <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
            {navItems.map((item) => {
              const Icon = item.icon;
              if (isLocked && item.path !== "/settings") {
                return (
                  <span
                    key={item.path}
                    aria-disabled="true"
                    title="Change your password to unlock this"
                    className="flex min-h-[44px] cursor-not-allowed items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-white/30"
                  >
                    <Icon className="h-[18px] w-[18px] flex-shrink-0" aria-hidden="true" />
                    {item.label}
                  </span>
                );
              }
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `flex min-h-[44px] items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-colors ${
                      isActive ? "bg-white/10 text-white" : "text-blue-100/80 hover:bg-white/5 hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={`h-[18px] w-[18px] flex-shrink-0 ${isActive ? "text-gold-400" : ""}`} aria-hidden="true" />
                      {item.label}
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>
          {isLocked && (
            <p className="mx-3 rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">
              Change your password in Settings to unlock the rest of the menu.
            </p>
          )}
          <PoweredBy tone="dark" className="border-t border-white/10 px-5 py-3" />
        </aside>

        {sidebarOpen && (
          <button
            aria-label="Close sidebar"
            className="fixed inset-0 z-20 bg-stone-900/30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <div className="flex min-h-screen min-w-0 flex-1 flex-col lg:pl-0">
          <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-sand-200 bg-white px-4 sm:px-6">
            {bottomItems ? (
              <div className="lg:hidden">
                <BrandMark />
              </div>
            ) : (
              <button
                aria-label="Open menu"
                className="rounded-xl p-2 text-stone-500 hover:bg-sand-100 lg:hidden"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-5 w-5" aria-hidden="true" />
              </button>
            )}
            <div className="hidden text-sm font-medium text-stone-400 lg:block">
              {ROLE_LABEL[user.role] ?? user.role} workspace
            </div>
            <div className="flex items-center gap-3">
              {receivesNotifications && (
                <NavLink
                  to={isLocked ? "/settings" : "/notifications"}
                  className="relative flex h-11 w-11 items-center justify-center rounded-xl text-stone-500 hover:bg-sand-100"
                  aria-label="Notifications"
                >
                  <Bell className="h-5 w-5" aria-hidden="true" />
                  {unreadCount > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-sunset-500 px-1 text-xs font-bold text-white">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </NavLink>
              )}
              <div className="flex items-center gap-3">
                <div className="hidden text-right sm:block">
                  <p className="text-sm font-semibold text-stone-800">{user.email}</p>
                  <p className="text-sm text-stone-500">{ROLE_LABEL[user.role] ?? user.role}</p>
                </div>
                <Avatar name={user.email} size="sm" employeeId={user.employee_id} />
                <button
                  onClick={handleLogout}
                  className={`min-h-[44px] items-center gap-1.5 rounded-xl border-2 border-sand-200 px-3 py-2 text-sm font-semibold text-stone-600 hover:border-sunset-200 hover:bg-sunset-50 hover:text-sunset-700 ${
                    bottomItems ? "hidden lg:flex" : "flex"
                  }`}
                >
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                  <span className="hidden sm:inline">Log out</span>
                </button>
              </div>
            </div>
          </header>

          <main className={`flex-1 px-4 py-6 sm:px-6 lg:px-8 ${bottomItems ? "pb-28 lg:pb-6" : ""}`}>
            <Outlet />
          </main>
        </div>
      </div>

      {phoneBottom && (
        <PhoneBottomBar
          primaryItems={phoneBottom}
          allItems={phoneNav}
          unreadCount={unreadCount}
          email={user.email}
          roleLabel={ROLE_LABEL[user.role] ?? user.role}
          onLogout={handleLogout}
        />
      )}
    </div>
  );
}
