import clsx from "clsx";
import { Banknote, Bell, CalendarPlus, CheckCheck, CheckCircle2, ChevronRight, ClipboardList, Clock, Receipt, XCircle, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { notificationService } from "@/services/notificationService";
import type { Notification } from "@/types";
import { dayGroup, friendlyMessage, timeAgo } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";

// Each kind of notification gets its own icon, colour and "where it takes you".
const KINDS: Record<string, { icon: LucideIcon; tone: string; to: string; openLabel: string }> = {
  TASK_ASSIGNED: { icon: ClipboardList, tone: "bg-sky-50 text-sky-700", to: "/tasks/my", openLabel: "Open my tasks" },
  LEAVE_APPROVED: { icon: CheckCircle2, tone: "bg-success-50 text-success-700", to: "/leave/my", openLabel: "See my leave" },
  ATTENDANCE_CORRECTED: { icon: Clock, tone: "bg-amber-50 text-amber-700", to: "/attendance/my", openLabel: "See my attendance" },
  LEAVE_REJECTED: { icon: XCircle, tone: "bg-rose-50 text-rose-700", to: "/leave/my", openLabel: "See my leave" },
  LEAVE_REQUESTED: { icon: CalendarPlus, tone: "bg-sky-50 text-sky-700", to: "/leave/requests", openLabel: "Review the request" },
  EXPENSE_SUBMITTED: { icon: Receipt, tone: "bg-amber-50 text-amber-700", to: "/expenses", openLabel: "Review claims" },
  EXPENSE_APPROVED: { icon: CheckCircle2, tone: "bg-success-50 text-success-700", to: "/expenses/my", openLabel: "See my expenses" },
  EXPENSE_REJECTED: { icon: XCircle, tone: "bg-rose-50 text-rose-700", to: "/expenses/my", openLabel: "See my expenses" },
  EXPENSE_PAID: { icon: Banknote, tone: "bg-success-50 text-success-700", to: "/expenses/my", openLabel: "See my expenses" },
  SALARY_PAID: { icon: Banknote, tone: "bg-success-50 text-success-700", to: "/salary/my", openLabel: "See my payslips" },
};
const FALLBACK_KIND = { icon: Bell, tone: "bg-sand-100 text-stone-600", to: "", openLabel: "" };

const GROUP_ORDER = ["Today", "Yesterday", "Earlier"] as const;

// A feed only gets its own scroll box once it is long enough to need one.
const SCROLL_AFTER = 6;

// Tells the header bell (in AppLayout) to re-count what is unread.
function announceChange() {
  window.dispatchEvent(new Event("ems:notifications-changed"));
}

export function NotificationsPage() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onlyNew, setOnlyNew] = useState(false);
  const [isMarkingAll, setIsMarkingAll] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      // The server sends at most 100 at a time, so keep asking until every message is here.
      setNotifications(await fetchAllPages((page) => notificationService.list(false, page, 100)));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your notifications."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const markRead = async (id: number): Promise<boolean> => {
    try {
      await notificationService.markRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      announceChange();
      return true;
    } catch (err) {
      showToast(getErrorMessage(err), "error");
      return false;
    }
  };

  // Tapping a message marks it as read and takes you to the page it is about.
  const open = async (notification: Notification) => {
    const kind = KINDS[notification.notification_type] ?? FALLBACK_KIND;
    if (!notification.is_read) {
      const ok = await markRead(notification.id);
      if (!ok) return;
    }
    if (kind.to) navigate(kind.to);
  };

  const handleMarkAllRead = async () => {
    setIsMarkingAll(true);
    try {
      await notificationService.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      announceChange();
      showToast("All caught up", "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsMarkingAll(false);
    }
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const visible = onlyNew ? notifications.filter((n) => !n.is_read) : notifications;

  const groups = useMemo(() => {
    const now = new Date();
    return GROUP_ORDER.map((title) => ({
      title,
      items: visible.filter((n) => dayGroup(n.created_at, now) === title),
    })).filter((g) => g.items.length > 0);
  }, [visible]);

  const boxed = visible.length > SCROLL_AFTER; // long feeds scroll inside a box, with each day's heading pinned while it is in view

  const feed = (
    <div className="flex flex-col gap-5">
      {groups.map((group) => (
        <section key={group.title} aria-label={group.title} className="flex flex-col gap-3">
          <h2
            className={clsx(
              "font-display text-lg font-bold text-stone-800",
              boxed && "sticky -top-3 z-10 -mx-3 border-b border-sand-200 bg-sand-50 px-3 py-2",
            )}
          >
            {group.title}
          </h2>
          <ul className="flex flex-col gap-3">
            {group.items.map((notification) => {
              const kind = KINDS[notification.notification_type] ?? FALLBACK_KIND;
              const Icon = kind.icon;
              return (
                <li key={notification.id}>
                  <button
                    type="button"
                    onClick={() => open(notification)}
                    className={clsx(
                      "flex w-full items-start gap-3 rounded-2xl border p-4 text-left shadow-sm transition-colors",
                      notification.is_read ? "border-sand-200 bg-white hover:bg-sand-50" : "border-brand-200 bg-brand-50/60 hover:bg-brand-50",
                    )}
                  >
                    <span className={clsx("flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl", kind.tone)}>
                      <Icon className="h-6 w-6" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <span className={clsx("break-words text-base text-stone-800", notification.is_read ? "font-semibold" : "font-bold")}>
                          {notification.title}
                        </span>
                        {!notification.is_read && (
                          <span className="flex-shrink-0 rounded-full bg-sunset-500 px-2.5 py-0.5 text-sm font-semibold text-white">New</span>
                        )}
                      </span>
                      <span className="mt-0.5 block break-words text-base text-stone-600">{friendlyMessage(notification.message)}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-stone-500">
                        {timeAgo(notification.created_at)}
                        {kind.openLabel && (
                          <span className="inline-flex items-center font-semibold text-brand-700">
                            {kind.openLabel}
                            <ChevronRight className="h-4 w-4" aria-hidden="true" />
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={Bell}
        title="Notifications"
        subtitle={unreadCount > 0 ? `${unreadCount} new ${unreadCount === 1 ? "message" : "messages"} for you` : "You have read everything"}
        action={
          unreadCount > 0 && (
            <Button variant="secondary" size="lg" className="w-full sm:w-auto" isLoading={isMarkingAll} onClick={handleMarkAllRead} icon={<CheckCheck className="h-5 w-5" />}>
              Mark all as read
            </Button>
          )
        }
      />

      {isLoading ? (
        <LoadingState label="Loading your messages..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : notifications.length === 0 ? (
        <Card>
          <EmptyState title="Nothing here yet" description="You will be told here when a task is given to you, your leave or expense claim is decided, or your salary is paid." />
        </Card>
      ) : (
        <>
          <div role="group" aria-label="Which messages to show" className="flex gap-2">
            {[
              { label: "All", value: false },
              { label: `New (${unreadCount})`, value: true },
            ].map((option) => (
              <button
                key={option.label}
                type="button"
                aria-pressed={onlyNew === option.value}
                onClick={() => setOnlyNew(option.value)}
                className={clsx(
                  "min-h-[44px] rounded-full px-5 text-base font-semibold ring-1 ring-inset",
                  onlyNew === option.value ? "bg-stone-800 text-white ring-stone-800" : "bg-white text-stone-600 ring-sand-200 hover:bg-sand-50",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>

          {groups.length === 0 ? (
            <Card>
              <EmptyState title="You're all caught up" description="There are no new messages." />
            </Card>
          ) : (
            <div>
              <p className="mb-2 text-xs text-stone-500">
                {visible.length} {visible.length === 1 ? "message" : "messages"}
                {boxed && " · scroll inside the box to see them all"}
              </p>
              {boxed ? (
                <ScrollPanel
                  label="Your notifications"
                  maxHeight="max-h-[min(38rem,70vh)]"
                  boxClass="rounded-2xl border border-sand-200 bg-sand-50 p-3"
                >
                  {feed}
                </ScrollPanel>
              ) : (
                feed
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
