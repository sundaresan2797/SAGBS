import { AlertTriangle, CalendarDays, Play, CheckCircle2, RotateCcw, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { dueLabel } from "@/utils/friendly";
import { PRIORITY_LABEL, TASK_STATUS_LABEL } from "@/utils/plainWords";
import { isTaskOverdue } from "@/utils/taskHelpers";
import type { Task, TaskStatus } from "@/types";

// What to do next, in one word. "Done" tasks need no button.
const NEXT_STEP: Partial<Record<TaskStatus, { next: TaskStatus; label: string; icon: typeof Play }>> = {
  TODO: { next: "IN_PROGRESS", label: "Start", icon: Play },
  IN_PROGRESS: { next: "COMPLETED", label: "Mark as done", icon: CheckCircle2 },
  BLOCKED: { next: "IN_PROGRESS", label: "Start again", icon: RotateCcw },
};

export function TaskRow({
  task,
  busy,
  onOpen,
  onAdvance,
}: {
  task: Task;
  busy: boolean;
  onOpen: () => void;
  onAdvance: (next: TaskStatus) => void;
}) {
  const overdue = isTaskOverdue(task);
  const step = NEXT_STEP[task.status];
  const StepIcon = step?.icon;
  return (
    <li
      className={`flex flex-col gap-3 rounded-2xl border bg-white p-4 shadow-sm ${overdue ? "border-sunset-300 bg-rose-50/40" : "border-sand-200"}`}
    >
      <button type="button" onClick={onOpen} className="flex flex-col gap-2 text-left">
        <span className="font-display text-lg font-bold text-stone-800">{task.title}</span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge size="lg" status={task.status} label={TASK_STATUS_LABEL[task.status]} />
          <Badge size="lg" status={task.priority} label={PRIORITY_LABEL[task.priority]} />
        </span>
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-base text-stone-600">
          <span className="flex items-center gap-1.5">
            <UserRound className="h-5 w-5 text-stone-400" aria-hidden="true" />
            From {task.assigner_name}
          </span>
          {task.due_date && (
            <span className={`flex items-center gap-1.5 ${overdue ? "font-semibold text-sunset-600" : ""}`}>
              {overdue ? <AlertTriangle className="h-5 w-5" aria-hidden="true" /> : <CalendarDays className="h-5 w-5 text-stone-400" aria-hidden="true" />}
              {task.status === "COMPLETED" ? `Was due ${task.due_date}` : dueLabel(task.due_date)}
            </span>
          )}
        </span>
      </button>
      <div className="flex flex-wrap gap-2">
        {step && StepIcon && (
          <Button className="flex-1 sm:flex-none" isLoading={busy} onClick={() => onAdvance(step.next)} icon={<StepIcon className="h-5 w-5" />}>
            {step.label}
          </Button>
        )}
        <Button variant="secondary" className="flex-1 sm:flex-none" onClick={onOpen}>
          Details and comments
        </Button>
      </div>
    </li>
  );
}
