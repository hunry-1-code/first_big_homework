from __future__ import annotations

from datetime import datetime


_TASKS: list[dict] = []


def create_task(task_type: str, created_by: int, payload: dict | None = None) -> dict:
    task = {
        "id": len(_TASKS) + 1,
        "type": task_type,
        "task_type": task_type,
        "status": "pending",
        "progress": 0,
        "message": "任务已创建，等待后台调度执行。",
        "payload": payload or {},
        "created_by": created_by,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": None,
        "finished_at": None,
    }
    _TASKS.append(task)
    return task


def reset_task_store() -> None:
    _TASKS.clear()


def get_task(task_id: int) -> dict | None:
    return next((task for task in _TASKS if task["id"] == task_id), None)


def update_task(task_id: int, **changes) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    if "progress" in changes:
        changes["progress"] = max(0, min(100, int(changes["progress"])))
    if changes.get("status") == "running" and task.get("started_at") is None:
        changes.setdefault("started_at", datetime.now().isoformat(timespec="seconds"))
    if changes.get("status") in {"success", "failed"}:
        changes.setdefault("finished_at", datetime.now().isoformat(timespec="seconds"))
    task.update(changes)
    return task


def list_tasks(created_by: int | None = None) -> list[dict]:
    if created_by is None:
        return list(_TASKS)
    return [task for task in _TASKS if task["created_by"] == created_by]


def latest_status() -> dict:
    latest = _TASKS[-1] if _TASKS else None
    return {"latest_task": latest, "crawl_enabled": True}
