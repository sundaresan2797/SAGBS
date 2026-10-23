import { AlertTriangle, CalendarDays, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { isTaskOverdue } from "@/utils/taskHelpers";
import type { Task } from "@/types";

export function TaskCard({ task, personName, onClick }: { task: Task; personName: string; onClick: () => void }) {
  const overdue = isTaskOverdue(task);
  return (
    <button
      onClick={onClick}
      className={`flex w-full flex-col gap-2 rounded-xl border bg-white p-3 text-left shadow-sm transition-shadow hover:shadow-md ${
        overdue ? "border-sunset-300" : "border-sand-200"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-stone-800">{task.title}</p>
        <Badge status={task.priority} />
      </div>
      <div className="flex items-center gap-1.5 text-xs text-stone-500">
        <UserRound className="h-3.5 w-3.5 text-stone-400" aria-hidden="true" />
        {personName}
      </div>
      {task.due_date && (
        <div className={`flex items-center gap-1.5 text-xs ${overdue ? "font-semibold text-sunset-600" : "text-stone-500"}`}>
          {overdue ? (
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <CalendarDays className="h-3.5 w-3.5 text-stone-400" aria-hidden="true" />
          )}
          {overdue ? "Overdue" : "Due"} {task.due_date}
        </div>
      )}
    </button>
  );
}
