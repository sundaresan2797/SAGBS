import { MessageCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";

import { Avatar } from "@/components/ui/EntityCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { LoadingState } from "@/components/ui/StateViews";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { taskService } from "@/services/taskService";
import { dueLabel } from "@/utils/friendly";
import { PRIORITY_LABEL, TASK_STATUS_LABEL } from "@/utils/plainWords";
import type { Task, TaskComment, TaskStatus } from "@/types";

const STATUS_OPTIONS: TaskStatus[] = ["TODO", "IN_PROGRESS", "COMPLETED", "BLOCKED"];

export function TaskDetailModal({
  taskId,
  onClose,
  onChanged,
}: {
  taskId: number | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [task, setTask] = useState<Task | null>(null);
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!taskId) return;
    setIsLoading(true);
    Promise.all([taskService.getById(taskId), taskService.listComments(taskId)])
      .then(([taskData, commentData]) => {
        setTask(taskData);
        setComments(commentData);
      })
      .catch((err) => showToast(getErrorMessage(err), "error"))
      .finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  if (!taskId) return null;

  const isAssignee = task && user?.employee_id === task.assigned_to;
  // Anyone who can see the task can read the comments, but only the person it is for and the person who
  // gave it can add to them (the server enforces the same rule).
  const canComment = task && (user?.employee_id === task.assigned_to || user?.employee_id === task.assigned_by);

  const handleStatusChange = async (status: TaskStatus) => {
    if (!task) return;
    setIsSaving(true);
    try {
      const updated = await taskService.updateStatus(task.id, status);
      setTask(updated);
      showToast("Task status updated", "success");
      onChanged();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddComment = async () => {
    if (!task || !newComment.trim()) return;
    setIsSaving(true);
    try {
      const comment = await taskService.addComment(task.id, newComment.trim());
      setComments((prev) => [...prev, comment]);
      setNewComment("");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal title={task?.title ?? "Task"} isOpen={Boolean(taskId)} onClose={onClose}>
      {isLoading || !task ? (
        <LoadingState />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge size="lg" status={task.priority} label={PRIORITY_LABEL[task.priority]} />
            <Badge size="lg" status={task.status} label={TASK_STATUS_LABEL[task.status]} />
            {task.due_date && <span className="text-base font-medium text-stone-500">{dueLabel(task.due_date)}</span>}
          </div>
          {task.description && <p className="text-base text-stone-700">{task.description}</p>}
          <p className="text-base text-stone-500">
            Given to {task.assignee_name} by {task.assigner_name}
          </p>

          {isAssignee && (
            <div>
              <p className="mb-2 text-base font-semibold text-stone-700">Where are you with this?</p>
              <div className="flex flex-wrap gap-2">
                {STATUS_OPTIONS.map((status) => (
                  <Button
                    key={status}
                    variant={status === task.status ? "primary" : "secondary"}
                    onClick={() => handleStatusChange(status)}
                    isLoading={isSaving}
                  >
                    {TASK_STATUS_LABEL[status]}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="mb-2 flex items-center gap-2">
              <MessageCircle className="h-4 w-4 text-brand-600" aria-hidden="true" />
              <h3 className="font-display text-base font-bold text-stone-800">Comments</h3>
            </div>
            <div className="flex max-h-48 flex-col gap-2 overflow-y-auto">
              {comments.length === 0 && <p className="text-base text-stone-500">No comments yet. Write the first one below.</p>}
              {comments.map((comment) => (
                <div key={comment.id} className="flex gap-2 rounded-xl bg-sand-50 p-2.5 text-base">
                  <Avatar name={comment.author_name} />
                  <div>
                    <p className="font-semibold text-stone-700">{comment.author_name}</p>
                    <p className="text-stone-600">{comment.comment}</p>
                  </div>
                </div>
              ))}
            </div>
            {!canComment ? (
              <p className="mt-2 text-base text-stone-500">Only {task.assignee_name} and {task.assigner_name} can add comments.</p>
            ) : (
            <div className="mt-2 flex gap-2">
              <input
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="Write a comment..."
                className="min-h-[44px] flex-1 rounded-xl border-2 border-sand-200 px-3.5 py-2.5 text-base focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
              <Button
                onClick={handleAddComment}
                isLoading={isSaving}
                disabled={!newComment.trim()}
                icon={<Send className="h-4 w-4" />}
              >
                Post
              </Button>
            </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
