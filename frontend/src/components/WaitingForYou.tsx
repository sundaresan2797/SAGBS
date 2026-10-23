import { CalendarClock, Receipt, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { useAuth } from "@/hooks/useAuth";
import { leaveService } from "@/services/leaveService";
import { payrollService } from "@/services/payrollService";
import { plural } from "@/utils/friendly";

function Row({ to, icon: Icon, children }: { to: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <li>
      <Link to={to} className="flex min-h-[48px] items-center gap-3 rounded-xl px-2 py-2 hover:bg-sand-50">
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-600">
          <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold text-stone-800">{children}</span>
      </Link>
    </li>
  );
}

// What is waiting for THIS person's decision - not the company's totals: leave from their own direct
// reports, and (for those who decide on claims) expense claims from everyone but themselves.
// Nothing is shown when nothing is waiting.
export function WaitingForYou() {
  const { user, hasPermission } = useAuth();
  // Leave is decided by a direct manager, so a login with no employee profile (the Admin) has nobody to ask about.
  const canApproveLeave = hasPermission("leave:approve_team") && Boolean(user?.employee_id);
  const canDecideClaims = hasPermission("payroll:manage");
  const [leave, setLeave] = useState(0);
  const [claims, setClaims] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (canApproveLeave) {
      leaveService
        .teamRequests("PENDING", 1, 1)
        .then((result) => !cancelled && setLeave(result.total))
        .catch(() => undefined);
    }
    if (canDecideClaims) {
      payrollService
        .allExpenseClaims("PENDING", 1, 100)
        .then((result) => !cancelled && setClaims(result.items.filter((c) => c.employee_id !== user?.employee_id).length))
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (leave === 0 && claims === 0) return null;

  return (
    <Card>
      <h2 className="mb-1 font-display text-sm font-semibold text-stone-700">Waiting for your decision</h2>
      <ul className="flex flex-col">
        {leave > 0 && (
          <Row to="/leave/requests" icon={CalendarClock}>
            {plural(leave, "leave request")} from your team
          </Row>
        )}
        {claims > 0 && (
          <Row to="/expenses" icon={Receipt}>
            {plural(claims, "expense claim")} to review
          </Row>
        )}
      </ul>
    </Card>
  );
}
