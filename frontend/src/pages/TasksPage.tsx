import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, CalendarDays, CheckSquare, ListTodo, Loader2, Plus, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { TaskCard } from "@/components/TaskCard";
import { TaskDetailModal } from "@/components/TaskDetailModal";
import { Button } from "@/components/ui/Button";
import { Card, StatCard } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/EntityCard";
import { InputField, SelectField } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { employeeService } from "@/services/employeeService";
import { taskService } from "@/services/taskService";
import { fetchAllPages } from "@/utils/paging";
import { isTaskOverdue, toIsoDate } from "@/utils/taskHelpers";
import type { EmployeeListItem, Task, TaskStatus } from "@/types";

const taskSchema = z.object({
  title: z.string().min(1, "Please give the task a title"),
  assigned_to: z.string().min(1, "Please choose who this is for"),
  priority: z.enum(["LOW", "MEDIUM", "HIGH", "URGENT"]),
  due_date: z.string().optional(),
  description: z.string().optional(),
});

type TaskFormValues = z.infer<typeof taskSchema>;

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "TODO", label: "To Do" },
  { status: "IN_PROGRESS", label: "In Progress" },
  { status: "COMPLETED", label: "Completed" },
  { status: "BLOCKED", label: "Blocked" },
];

type RangeKey = "all" | "today" | "this_week" | "last_week" | "this_month" | "this_year" | "last_year" | "custom";

const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: "all", label: "All time" },
  { key: "today", label: "Today" },
  { key: "this_week", label: "This week" },
  { key: "last_week", label: "Last week" },
  { key: "this_month", label: "This month" },
  { key: "this_year", label: "This year" },
  { key: "last_year", label: "Last year" },
  { key: "custom", label: "Custom" },
];

function startOfWeek(d: Date): Date {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day; // Monday as the first day of the week
  date.setDate(date.getDate() + diff);
  return date;
}

function computeRange(key: RangeKey, customFrom: string, customTo: string): { from?: string; to?: string } {
  const today = new Date();
  if (key === "all") return {};
  if (key === "today") return { from: toIsoDate(today), to: toIsoDate(today) };
  if (key === "this_week") {
    const start = startOfWeek(today);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }
  if (key === "last_week") {
    const start = startOfWeek(today);
    start.setDate(start.getDate() - 7);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }
  if (key === "this_month") {
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }
  if (key === "this_year" || key === "last_year") {
    const y = today.getFullYear() - (key === "last_year" ? 1 : 0);
    return { from: toIsoDate(new Date(y, 0, 1)), to: toIsoDate(new Date(y, 11, 31)) };
  }
  return { from: customFrom || undefined, to: customTo || undefined };
}

export function TasksPage() {
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const canCreate = hasPermission("task:create");
  // report:view widens list_team_tasks server-side to every task in the company
  // (see task_service.list_team_tasks) - the page's wording and person-filter
  // follow that same widening so nothing here implies a scope the data isn't.
  const isCompanyWide = hasPermission("report:view");

  const [teamMembers, setTeamMembers] = useState<EmployeeListItem[]>([]);
  const [filterMembers, setFilterMembers] = useState<EmployeeListItem[]>([]);
  // The people who report to you. Only used to offer "My team" on a company-wide board - a Manager's
  // board is already just their team, so there is nothing to narrow.
  const [myReports, setMyReports] = useState<EmployeeListItem[]>([]);
  const [myTeamOnly, setMyTeamOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);

  const [rangeKey, setRangeKey] = useState<RangeKey>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [memberFilter, setMemberFilter] = useState("");
  const [search, setSearch] = useState("");

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TaskFormValues>({ resolver: zodResolver(taskSchema), defaultValues: { priority: "MEDIUM" } });

  // Fetched unfiltered by date - the time-period filter is applied client
  // side (see `tasks` below) so we can tell the difference between "nothing
  // due in this period" and "some tasks have no due date at all" instead of
  // silently dropping the latter with no explanation.
  const [allTasks, setAllTasks] = useState<Task[]>([]);

  // `quiet` refreshes without the loading screen, so the board keeps its scroll positions after a change.
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      // The server sends at most 200 at a time, so keep asking until every task is here.
      setAllTasks(
        await fetchAllPages((page) =>
          taskService.teamTasks({ assigned_to: memberFilter ? Number(memberFilter) : undefined, page, page_size: 200 }),
        ),
      );
    } catch (err) {
      setError(getErrorMessage(err, isCompanyWide ? "We couldn't load the company's tasks." : "We couldn't load your team's tasks."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // The "Assign a Task" list always stays direct-reports-only, regardless
    // of read scope - who you can personally hand a task to is a separate,
    // narrower rule (see the comment in task_service.create_task).
    if (canCreate && user?.employee_id) {
      employeeService
        .list({ manager_id: user.employee_id, page_size: 100, status: "ACTIVE" })
        .then((employees) => setTeamMembers(employees.items))
        .catch(() => undefined);
    }
    // The "filter by person" list mirrors the board's own read scope instead:
    // every active employee when the board is company-wide, direct reports otherwise.
    // page_size caps at 100 here (unlike /tasks/team's 200) - GET /employees itself enforces that limit.
    if (isCompanyWide) {
      fetchAllPages((page) => employeeService.list({ page, page_size: 100, status: "ACTIVE" }))
        .then(setFilterMembers)
        .catch(() => undefined);
      if (user?.employee_id) {
        employeeService
          .list({ manager_id: user.employee_id, page_size: 100 })
          .then((result) => setMyReports(result.items))
          .catch(() => undefined);
      }
    } else if (user?.employee_id) {
      employeeService
        .list({ manager_id: user.employee_id, page_size: 100, status: "ACTIVE" })
        .then((employees) => setFilterMembers(employees.items))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberFilter]);

  const { from: rangeFrom, to: rangeTo } = computeRange(rangeKey, customFrom, customTo);
  const teamIds = useMemo(() => new Set(myReports.map((m) => m.id)), [myReports]);
  // "My team" narrows the whole board - cards, counts and the workload panel - to your direct reports.
  const scopedTasks = useMemo(
    () => (myTeamOnly ? allTasks.filter((t) => teamIds.has(t.assigned_to)) : allTasks),
    [allTasks, myTeamOnly, teamIds],
  );
  const personOptions = myTeamOnly ? filterMembers.filter((m) => teamIds.has(m.id)) : filterMembers;
  const tasks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return scopedTasks.filter((t) => {
      if (needle && !`${t.title} ${t.assignee_name}`.toLowerCase().includes(needle)) return false;
      if (rangeKey === "all") return true;
      if (!t.due_date) return false;
      if (rangeFrom && t.due_date < rangeFrom) return false;
      if (rangeTo && t.due_date > rangeTo) return false;
      return true;
    });
  }, [scopedTasks, rangeKey, rangeFrom, rangeTo, search]);

  const undatedCount = useMemo(() => scopedTasks.filter((t) => !t.due_date).length, [scopedTasks]);

  const onCreate = async (values: TaskFormValues) => {
    try {
      await taskService.create({
        title: values.title,
        description: values.description || undefined,
        assigned_to: Number(values.assigned_to),
        priority: values.priority,
        due_date: values.due_date || undefined,
      });
      showToast("Task assigned!", "success");
      setIsCreateOpen(false);
      reset();
      load(true);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  };

  const stats = useMemo(() => {
    const byStatus = (status: TaskStatus) => tasks.filter((t) => t.status === status).length;
    return {
      todo: byStatus("TODO"),
      inProgress: byStatus("IN_PROGRESS"),
      completed: byStatus("COMPLETED"),
      blocked: byStatus("BLOCKED"),
      overdue: tasks.filter(isTaskOverdue).length,
    };
  }, [tasks]);

  const perPerson = useMemo(() => {
    // Grouped by employee id, not name: two different people can share a display name (this
    // company genuinely has two "Sundareswaran S", in different departments) - grouping by name
    // would silently merge their task counts into one row.
    const byId = new Map<number, { name: string; assigned: number; completed: number; overdue: number }>();
    for (const task of tasks) {
      const entry = byId.get(task.assigned_to) ?? { name: task.assignee_name, assigned: 0, completed: 0, overdue: 0 };
      entry.assigned += 1;
      if (task.status === "COMPLETED") entry.completed += 1;
      if (isTaskOverdue(task)) entry.overdue += 1;
      byId.set(task.assigned_to, entry);
    }

    // Only disambiguate when a name is actually shared, so the common case stays uncluttered.
    const nameCounts = new Map<string, number>();
    for (const entry of byId.values()) nameCounts.set(entry.name, (nameCounts.get(entry.name) ?? 0) + 1);
    const codeById = new Map(filterMembers.map((m) => [m.id, m.employee_code]));

    return Array.from(byId.entries())
      .map(([id, stat]) => {
        const code = (nameCounts.get(stat.name) ?? 0) > 1 ? codeById.get(id) : undefined;
        return {
          id,
          name: code ? `${stat.name} (${code})` : stat.name,
          assigned: stat.assigned,
          completed: stat.completed,
          overdue: stat.overdue,
          rate: stat.assigned > 0 ? Math.round((stat.completed / stat.assigned) * 100) : 0,
        };
      })
      .sort((a, b) => b.assigned - a.assigned);
  }, [tasks, filterMembers]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
            <CheckSquare className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-stone-800">{isCompanyWide ? "Company Tasks" : "Team Tasks"}</h1>
            <p className="text-sm text-stone-500">
              {isCompanyWide ? "Every task assigned to anyone in the company" : "Tasks you've handed to your direct reports"}
            </p>
          </div>
        </div>
        {/* Same "only once there's something to show" pattern as the Person filter below:
            canCreate is a role-wide permission, but with zero direct reports there's nobody
            to actually assign to - hiding it avoids a button that opens to an empty dropdown. */}
        {canCreate && teamMembers.length > 0 && (
          <Button onClick={() => setIsCreateOpen(true)} icon={<Plus className="h-4 w-4" />}>
            Assign a Task
          </Button>
        )}
      </div>

      <Card className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold uppercase tracking-wide text-stone-400">Time period</label>
          <div className="flex flex-wrap gap-1 rounded-lg bg-sand-100 p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                onClick={() => setRangeKey(opt.key)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                  rangeKey === opt.key ? "bg-white text-brand-700 shadow-sm" : "text-stone-500 hover:text-stone-700"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        {rangeKey === "custom" && (
          <>
            <InputField
              label="From"
              name="custom_from"
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
            />
            <InputField
              label="To"
              name="custom_to"
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
            />
          </>
        )}
        <div className="min-w-[200px] flex-1 sm:max-w-xs">
          <InputField
            label="Search"
            name="task_search"
            type="search"
            placeholder="Task or person..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {myReports.length > 0 && (
          <button
            type="button"
            aria-pressed={myTeamOnly}
            onClick={() => {
              const next = !myTeamOnly;
              setMyTeamOnly(next);
              // A person picked from the whole company may not be on your team - go back to everyone.
              if (next && memberFilter && !teamIds.has(Number(memberFilter))) setMemberFilter("");
            }}
            className={`min-h-[44px] rounded-xl border-2 px-4 text-sm font-semibold transition-colors ${
              myTeamOnly ? "border-stone-800 bg-stone-800 text-white" : "border-sand-200 bg-white text-stone-600 hover:bg-sand-50"
            }`}
          >
            My team ({myReports.length})
          </button>
        )}
        {filterMembers.length > 0 && (
          <div className="min-w-[200px]">
            <SelectField
              label={isCompanyWide ? "Person" : "Team member"}
              name="member_filter"
              value={memberFilter}
              onChange={(e) => setMemberFilter(e.target.value)}
            >
              <option value="">Everyone</option>
              {personOptions.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.full_name}
                </option>
              ))}
            </SelectField>
          </div>
        )}
      </Card>

      {!isLoading && rangeKey !== "all" && undatedCount > 0 && (
        <div className="flex items-center gap-2 rounded-xl bg-sky-50 px-4 py-2.5 text-sm text-sky-800">
          <CalendarDays className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          {undatedCount} task{undatedCount === 1 ? "" : "s"} with no due date {undatedCount === 1 ? "isn't" : "aren't"} shown for
          this time period &mdash; switch to <button className="font-semibold underline" onClick={() => setRangeKey("all")}>All time</button> to see {undatedCount === 1 ? "it" : "them"}.
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Loading tasks..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : tasks.length === 0 ? (
        <Card>
          <EmptyState title="No tasks in this period" description="Try a different time range, or assign a new task." />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard label="To Do" value={stats.todo} icon={<ListTodo className="h-5 w-5" />} />
            <StatCard label="In Progress" value={stats.inProgress} icon={<Loader2 className="h-5 w-5" />} />
            <StatCard label="Completed" value={stats.completed} icon={<CheckSquare className="h-5 w-5" />} />
            <StatCard label="Blocked" value={stats.blocked} icon={<ShieldAlert className="h-5 w-5" />} tone="sunset" />
            <StatCard label="Overdue" value={stats.overdue} icon={<AlertTriangle className="h-5 w-5" />} tone="sunset" />
          </div>

          <p className="-mb-1 text-xs text-stone-500">
            {tasks.length === scopedTasks.length ? `${scopedTasks.length} tasks` : `Showing ${tasks.length} of ${scopedTasks.length} tasks`}
            {" · scroll inside a column to see all its tasks"}
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {COLUMNS.map((column) => {
              const columnTasks = tasks.filter((t) => t.status === column.status);
              return (
                <div key={column.status} className="flex flex-col gap-3 rounded-2xl bg-sand-100/60 p-3">
                  <div className="flex items-center justify-between px-1">
                    <h2 className="font-display text-sm font-semibold text-stone-700">{column.label}</h2>
                    <span className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-stone-500 shadow-sm">
                      {columnTasks.length}
                    </span>
                  </div>
                  {columnTasks.length === 0 ? (
                    <p className="px-1 text-xs text-stone-400">Nothing here.</p>
                  ) : (
                    <ScrollPanel
                      label={`${column.label} tasks`}
                      maxHeight="max-h-[min(24rem,55vh)] lg:max-h-[min(32rem,62vh)]"
                      boxClass="pr-1"
                    >
                      <div className="flex flex-col gap-2">
                        {columnTasks.map((task) => (
                          <TaskCard key={task.id} task={task} personName={task.assignee_name} onClick={() => setSelectedTaskId(task.id)} />
                        ))}
                      </div>
                    </ScrollPanel>
                  )}
                </div>
              );
            })}
          </div>

          {perPerson.length > 1 && (
            <Card>
              <h2 className="mb-4 font-display text-sm font-semibold text-stone-700">Workload by person</h2>
              <ScrollPanel label="Workload by person" maxHeight="max-h-[min(22rem,55vh)]">
                <div className="flex flex-col gap-3">
                  {perPerson.map((person) => (
                    <div key={person.id} className="flex flex-wrap items-center gap-3 border-b border-sand-100 pb-3 last:border-0 last:pb-0">
                      <Avatar name={person.name} employeeId={person.id} />
                      <div className="min-w-[140px] flex-1">
                        <p className="text-sm font-semibold text-stone-800">{person.name}</p>
                        <p className="text-xs text-stone-400">
                          {person.assigned} assigned &middot; {person.completed} completed
                          {person.overdue > 0 && <span className="text-sunset-600"> &middot; {person.overdue} overdue</span>}
                        </p>
                      </div>
                      <div className="flex w-full items-center gap-2 sm:w-48">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-sand-100">
                          <div
                            className="h-full rounded-full bg-brand-500"
                            style={{ width: `${person.rate}%` }}
                          />
                        </div>
                        <span className="w-10 text-right text-xs font-semibold text-stone-500">{person.rate}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollPanel>
            </Card>
          )}
        </>
      )}

      <Modal
        title="Assign a Task"
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSubmit(onCreate)} isLoading={isSubmitting}>
              Assign Task
            </Button>
          </>
        }
      >
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onCreate)} noValidate>
          <InputField label="What needs to be done?" error={errors.title?.message} required {...register("title")} />
          <SelectField label="Who's this for?" error={errors.assigned_to?.message} required {...register("assigned_to")}>
            <option value="">Choose a team member</option>
            {teamMembers.map((member) => (
              <option key={member.id} value={member.id}>
                {member.full_name}
              </option>
            ))}
          </SelectField>
          <SelectField label="How urgent is it?" {...register("priority")}>
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
            <option value="URGENT">Urgent</option>
          </SelectField>
          <InputField label="Due date (optional)" type="date" {...register("due_date")} />
        </form>
      </Modal>

      <TaskDetailModal taskId={selectedTaskId} onClose={() => setSelectedTaskId(null)} onChanged={() => load(true)} />
    </div>
  );
}
