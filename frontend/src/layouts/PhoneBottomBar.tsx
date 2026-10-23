import clsx from "clsx";
import { LayoutGrid, LogOut } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { Avatar } from "@/components/ui/EntityCard";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import type { NavItem } from "@/utils/navigation";

/**
 * The phone's bottom bar: four everyday places plus "More", which opens a
 * sheet with every other page as big, labelled tiles and a clear Log out.
 */
export function PhoneBottomBar({
  primaryItems,
  allItems,
  unreadCount,
  email,
  roleLabel,
  onLogout,
}: {
  primaryItems: NavItem[];
  allItems: NavItem[];
  unreadCount: number;
  email: string;
  roleLabel: string;
  onLogout: () => void;
}) {
  const { user } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  const { pathname } = useLocation();
  const primaryPaths = new Set(primaryItems.map((item) => item.path));
  const moreItems = allItems.filter((item) => !primaryPaths.has(item.path));
  const moreIsActive = moreItems.some((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));

  return (
    <>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-sand-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_16px_rgba(0,0,0,0.05)] lg:hidden"
      >
        <ul className="flex">
          {primaryItems.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.path} className="flex-1">
                <NavLink
                  to={item.path}
                  className={({ isActive }) =>
                    clsx(
                      "flex min-h-[64px] flex-col items-center justify-center gap-1 px-1 text-sm font-semibold",
                      isActive ? "text-brand-700" : "text-stone-500",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span
                        className={clsx(
                          "flex h-8 w-14 items-center justify-center rounded-full",
                          isActive && "bg-brand-100",
                        )}
                      >
                        <Icon className="h-6 w-6" aria-hidden="true" />
                      </span>
                      {item.label}
                    </>
                  )}
                </NavLink>
              </li>
            );
          })}
          <li className="flex-1">
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className={clsx(
                "relative flex min-h-[64px] w-full flex-col items-center justify-center gap-1 px-1 text-sm font-semibold",
                moreIsActive ? "text-brand-700" : "text-stone-500",
              )}
            >
              <span className={clsx("relative flex h-8 w-14 items-center justify-center rounded-full", moreIsActive && "bg-brand-100")}>
                <LayoutGrid className="h-6 w-6" aria-hidden="true" />
                {unreadCount > 0 && (
                  <span className="absolute right-2 top-0 h-3 w-3 rounded-full border-2 border-white bg-sunset-500" aria-label="New notifications" />
                )}
              </span>
              More
            </button>
          </li>
        </ul>
      </nav>

      <Sheet title="More" isOpen={moreOpen} onClose={() => setMoreOpen(false)}>
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 rounded-2xl bg-sand-50 p-3">
            <Avatar name={email} employeeId={user?.employee_id} />
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-stone-800">{email}</p>
              <p className="text-sm text-stone-500">{roleLabel}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {moreItems.map((item) => {
              const Icon = item.icon;
              const isNotifications = item.path === "/notifications";
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={() => setMoreOpen(false)}
                  className={({ isActive }) =>
                    clsx(
                      "relative flex min-h-[84px] flex-col items-start justify-between gap-2 rounded-2xl border-2 p-3 text-base font-semibold",
                      isActive ? "border-brand-300 bg-brand-50 text-brand-800" : "border-sand-200 bg-white text-stone-700",
                    )
                  }
                >
                  <Icon className="h-6 w-6 text-brand-600" aria-hidden="true" />
                  {item.label}
                  {isNotifications && unreadCount > 0 && (
                    <span className="absolute right-3 top-3 flex h-6 min-w-6 items-center justify-center rounded-full bg-sunset-500 px-1.5 text-sm font-bold text-white">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </div>

          <Button
            variant="secondary"
            size="lg"
            className="w-full"
            icon={<LogOut className="h-5 w-5" />}
            onClick={() => {
              setMoreOpen(false);
              onLogout();
            }}
          >
            Log out
          </Button>
        </div>
      </Sheet>
    </>
  );
}
