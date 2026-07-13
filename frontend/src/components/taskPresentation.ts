export function formatTaskStatus(status: string): string {
  if (status === "pending") return "等待中";
  if (status === "running") return "进行中";
  if (status === "success" || status === "completed") return "已完成";
  if (status === "failed") return "已失败";
  return status || "未知";
}

export type TaskStatusTag = "primary" | "success" | "warning" | "danger" | "info";

export function getTaskStatusTag(status: string): TaskStatusTag {
  if (status === "pending") return "info";
  if (status === "running") return "warning";
  if (status === "success" || status === "completed") return "success";
  if (status === "failed") return "danger";
  return "info";
}

export function taskKeyword(task: any): string {
  return String(task?.payload?.keyword || "").trim() || "-";
}
