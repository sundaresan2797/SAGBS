import { CheckSquare, ChevronDown, ChevronUp, LayoutGrid, List, Search } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { TaskCard } from "@/components/TaskCard";
import { TaskDetailModal } from "@/components/TaskDetailModal";
import { TaskRow } from "@/components/TaskRow";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScrollPanel } from "@/components/ui/ScrollPanel";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { taskService } from "@/services/taskService";
import { daysFromToday } from "@/utils/friendly";
import { fetchAllPages } from "@/utils/paging";
import { TASK_STATUS_LABEL } from "@/utils/plainWords";
import { isTaskOverdue } from "@/utils/taskHelpers";
import type { Task, TaskStatus } from "@/types";

const COLUMNS: TaskStatus[] = ["TODO", "IN_PROGRESS", "COMPLETED", "BLOCKED"];

// A list only gets its own scroll box once it is long enough to need one.
const SCROLL_AFTER = 6;

const ADVANCE_MESSAGE: Partial<Record<TaskStatus, string>> = {
  IN_PROGRESS: "Task started",
  COMPLETED: "Well done - task marked as done",
};

export function MyTasksPage() {
  const { showToast } = useToast();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [view, setView] = useState<"list" | "board">("list");
  const [showDone, setShowDone] = useState(false);
  const [search, setSearch] = useState("");

  // `quiet` refreshes without the loading screen, so the lists keep their scroll positions.
  const load = async (quiet = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      // The server sends at most 100 at a time, so keep asking until every task is here.
      setTasks(await fetchAllPages((page) => taskService.myTasks(undefined, page, 100)));
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your tasks."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const advance = async (task: Task, next: TaskStatus) => {
    setBusyId(task.id);
    try {
      const updated = await taskService.updateStatus(task.id, next);
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      showToast(ADVANCE_MESSAGE[next] ?? "Task updated", "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return needle ? tasks.filter((t) => `${t.title} ${t.assigner_name}`.toLowerCase().includes(needle)) : tasks;
  }, [tasks, search]);

  const groups = useMemo(() => {
    const open = shown
      .filter((t) => t.status !== "COMPLETED")
      .sort((a, b) => (a.due_date ?? "9999-12-31").localeCompare(b.due_date ?? "9999-12-31"));
    return {
      overdue: open.filter(isTaskOverdue),
      thisWeek: open.filter((t) => !isTaskOverdue(t) && t.due_date && daysFromToday(t.due_date) <= 7),
      later: open.filter((t) => !isTaskOverdue(t) && !(t.due_date && daysFromToday(t.due_date) <= 7)),
      done: shown.filter((t) => t.status === "COMPLETED"),
    };
  }, [shown]);

  const openCount = groups.overdue.length + groups.thisWeek.length + groups.later.length;
  const openTotal = tasks.filter((t) => t.status !== "COMPLETED").length; // the header counts everything, not just what the search shows

  const withScroll = (label: string, count: number, node: ReactNode) =>
    count > SCROLL_AFTER ? <ScrollPanel label={label}>{node}</ScrollPanel> : node;

  const renderGroup = (title: string, items: Task[], tone?: "red") => {
    if (items.length === 0) return null;
    return (
      <section key={title}>
        <h2 className={`mb-2 font-display text-lg font-bold ${tone === "red" ? "text-sunset-700" : "text-stone-800"}`}>
          {title} <span className="text-base font-semibold text-stone-400">({items.length})</span>
        </h2>
        {withScroll(
          title,
          items.length,
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {items.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                busy={busyId === task.id}
                onOpen={() => setSelectedTaskId(task.id)}
                onAdvance={(next) => advance(task, next)}
              />
            ))}
          </ul>,
        )}
      </section>
    );
  };

  // Only worth showing once there are enough tasks to search through.
  const searchBox =
    tasks.length > 8 ? (
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
          <input
            type="search"
            aria-label="Search your tasks"
            placeholder="Search tasks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-h-[44px] w-full rounded-xl border-2 border-sand-200 py-2 pl-9 pr-3 text-base text-stone-800 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>
        {shown.length !== tasks.length && <p className="text-sm text-stone-500">Showing {shown.length} of {tasks.length} tasks</p>}
      </div>
    ) : null;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        icon={CheckSquare}
        title="My Tasks"
        subtitle={isLoading || error ? "What's on your plate" : openTotal === 0 ? "You have nothing left to do" : `${openTotal} to do`}
        action={
          tasks.length > 0 ? (
            <div className="hidden rounded-xl border-2 border-sand-200 bg-white p-1 lg:flex" role="group" aria-label="How to show tasks">
              <Button size="md" variant={view === "list" ? "primary" : "ghost"} onClick={() => setView("list")} icon={<List className="h-4 w-4" />}>List</Button>
              <Button size="md" variant={view === "board" ? "primary" : "ghost"} onClick={() => setView("board")} icon={<LayoutGrid className="h-4 w-4" />}>Board</Button>
            </div>
          ) : undefined
        }
      />

      {isLoading ? (
        <LoadingState label="Loading your tasks..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : tasks.length === 0 ? (
        <Card>
          <EmptyState title="You're all caught up!" description="No tasks have been given to you right now." />
        </Card>
      ) : shown.length === 0 ? (
        <>
          {searchBox}
          <Card>
            <EmptyState title="No matches" description="No task matches your search." />
          </Card>
        </>
      ) : view === "board" ? (
        <>
          {searchBox}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
            {COLUMNS.map((status) => {
              const columnTasks = shown.filter((t) => t.status === status);
              return (
                <div key={status} className="flex flex-col gap-3 rounded-2xl bg-sand-100/60 p-3">
                  <div className="flex items-center justify-between px-1">
                    <h2 className="font-display text-base font-bold text-stone-700">{TASK_STATUS_LABEL[status]}</h2>
                    <span className="rounded-full bg-white px-2.5 py-0.5 text-sm font-semibold text-stone-500 shadow-sm">{columnTasks.length}</span>
                  </div>
                  {columnTasks.length === 0 ? (
                    <p className="px-1 text-base text-stone-400">Nothing here.</p>
                  ) : (
                    <ScrollPanel
                      label={`${TASK_STATUS_LABEL[status]} tasks`}
                      maxHeight="max-h-[min(24rem,55vh)] lg:max-h-[min(32rem,62vh)]"
                      boxClass="pr-1"
                    >
                      <div className="flex flex-col gap-3">
                        {columnTasks.map((task) => (
                          <TaskCard key={task.id} task={task} personName={`From ${task.assigner_name}`} onClick={() => setSelectedTaskId(task.id)} />
                        ))}
                      </div>
                    </ScrollPanel>
                  )}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <>
          {searchBox}
          {openCount === 0 && (
            <Card>
              <EmptyState title="Everything is done" description="Nice work. New tasks will show up here." />
            </Card>
          )}
          {renderGroup("Running late", groups.overdue, "red")}
          {renderGroup("Due in the next 7 days", groups.thisWeek)}
          {renderGroup("Later or no date", groups.later)}
          {groups.done.length > 0 && (
            <section>
              <Button
                variant="secondary"
                onClick={() => setShowDone((s) => !s)}
                icon={showDone ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
              >
                {showDone ? "Hide" : "Show"} completed tasks ({groups.done.length})
              </Button>
              {showDone && (
                <div className="mt-3">
                  {withScroll(
                    "Completed tasks",
                    groups.done.length,
                    <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                      {groups.done.map((task) => (
                        <TaskRow key={task.id} task={task} busy={false} onOpen={() => setSelectedTaskId(task.id)} onAdvance={() => undefined} />
                      ))}
                    </ul>,
                  )}
                </div>
              )}
            </section>
          )}
        </>
      )}

      <TaskDetailModal taskId={selectedTaskId} onClose={() => setSelectedTaskId(null)} onChanged={() => load(true)} />
    </div>
  );
}
