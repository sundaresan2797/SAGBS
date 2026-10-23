import { Briefcase, Building2, Search, UserPlus, UserRoundCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CardGrid, EntityCard, MetaRow } from "@/components/ui/EntityCard";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { getErrorMessage } from "@/services/api";
import { departmentService, employeeService } from "@/services/employeeService";
import type { Department, EmployeeListItem, EmployeeStatus } from "@/types";

const STATUS_OPTIONS: EmployeeStatus[] = ["ACTIVE", "ON_LEAVE", "RESIGNED", "TERMINATED", "INACTIVE"];

export function EmployeesListPage() {
  const { user, hasPermission, hasRole } = useAuth();
  const [items, setItems] = useState<EmployeeListItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<EmployeeStatus | "">("");
  const [departmentId, setDepartmentId] = useState<string>("");
  // Only worth offering to someone who has direct reports AND sees more than them (a Manager's list already is their team).
  const [teamSize, setTeamSize] = useState(0);
  const [myTeamOnly, setMyTeamOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const canCreate = hasPermission("employee:create");

  useEffect(() => {
    departmentService.list().then(setDepartments).catch(() => undefined);
    if (user?.employee_id && !hasRole("MANAGER")) {
      employeeService
        .list({ manager_id: user.employee_id, page_size: 1 })
        .then((result) => setTeamSize(result.total))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await employeeService.list({
        search: search || undefined,
        status: status || undefined,
        department_id: departmentId ? Number(departmentId) : undefined,
        manager_id: myTeamOnly && user?.employee_id ? user.employee_id : undefined,
        page,
        page_size: 12,
      });
      setItems(result.items);
      setTotalPages(result.total_pages);
      setTotal(result.total);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load the team list. Please try again."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, status, departmentId, myTeamOnly]);

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setPage(1);
    load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <UserRoundCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">
              {hasRole("MANAGER") ? "My Team" : "Employees"}
            </h1>
            <p className="text-sm text-stone-500">
              {total} {total === 1 ? "person" : "people"}
            </p>
          </div>
        </div>
        {canCreate && (
          <Link to="/employees/new">
            <Button icon={<UserPlus className="h-4 w-4" />}>Add Employee</Button>
          </Link>
        )}
      </div>

      <Card>
        <form onSubmit={handleSearchSubmit} className="flex flex-wrap gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, code, or email"
              className="w-full rounded-xl border-2 border-sand-200 py-2.5 pl-10 pr-3.5 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>
          {teamSize > 0 && (
            <button
              type="button"
              aria-pressed={myTeamOnly}
              onClick={() => {
                setMyTeamOnly((on) => !on);
                setPage(1);
              }}
              className={`min-h-[44px] rounded-xl border-2 px-4 text-sm font-semibold transition-colors ${
                myTeamOnly ? "border-stone-800 bg-stone-800 text-white" : "border-sand-200 bg-white text-stone-600 hover:bg-sand-50"
              }`}
            >
              My team ({teamSize})
            </button>
          )}
          <select
            value={departmentId}
            onChange={(e) => {
              setDepartmentId(e.target.value);
              setPage(1);
            }}
            className="rounded-xl border-2 border-sand-200 px-3.5 py-2.5 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All departments</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as EmployeeStatus | "");
              setPage(1);
            }}
            className="rounded-xl border-2 border-sand-200 px-3.5 py-2.5 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <Button type="submit" variant="secondary" icon={<Search className="h-4 w-4" />}>
            Search
          </Button>
        </form>
      </Card>

      {isLoading ? (
        <LoadingState label="Loading people..." />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState title="No one matches your search" description="Try a different name, department, or status." />
        </Card>
      ) : (
        <>
          <CardGrid>
            {items.map((employee) => (
              <EntityCard
                key={employee.id}
                avatarName={employee.full_name}
                avatarEmployeeId={employee.id}
                title={employee.full_name}
                subtitle={employee.employee_code}
                badge={<Badge status={employee.status} />}
                meta={
                  <>
                    <MetaRow icon={<Briefcase className="h-3.5 w-3.5" />}>{employee.designation.name}</MetaRow>
                    <MetaRow icon={<Building2 className="h-3.5 w-3.5" />}>{employee.department.name}</MetaRow>
                    {employee.manager && (
                      <MetaRow icon={<UserRoundCheck className="h-3.5 w-3.5" />}>
                        Reports to {employee.manager.full_name}
                      </MetaRow>
                    )}
                  </>
                }
                actions={
                  <Link to={`/employees/${employee.id}`} className="text-sm font-semibold text-brand-600 hover:underline">
                    View profile
                  </Link>
                }
              />
            ))}
          </CardGrid>
          <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
