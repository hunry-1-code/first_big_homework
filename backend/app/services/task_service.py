from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from threading import RLock

from flask import has_app_context

from app.extensions import db


_TASKS: list[dict] = []
_LOCK = RLock()
_CREATION_LOCK = RLock()
_CURRENT_TASK_LEASE: ContextVar[str | None] = ContextVar(
    "current_task_lease", default=None
)


class StaleTaskLeaseError(RuntimeError):
    pass


def activate_task_lease(lease_token: str) -> Token:
    return _CURRENT_TASK_LEASE.set(lease_token)


def reset_task_lease(context_token: Token) -> None:
    _CURRENT_TASK_LEASE.reset(context_token)


def assert_task_lease(task_id: int | None, lease_token: str | None = None) -> None:
    effective_lease = lease_token or _CURRENT_TASK_LEASE.get()
    if task_id is None or not effective_lease:
        return

    if has_app_context():
        from app.models.task import Task

        task = Task.query.filter(
            Task.id == task_id,
            Task.status == "running",
            Task.lease_token == effective_lease,
        ).with_for_update().first()
        if task is None:
            raise StaleTaskLeaseError(f"task lease expired: {task_id}")
        return

    with _LOCK:
        task = next((item for item in _TASKS if item["id"] == task_id), None)
        if (
            task is None
            or task["status"] != "running"
            or task.get("lease_token") != effective_lease
        ):
            raise StaleTaskLeaseError(f"task lease expired: {task_id}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(task) -> dict:
    return {
        "id": task.id,
        "type": task.task_type,
        "task_type": task.task_type,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "payload": task.payload or {},
        "result": task.result,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat(timespec="seconds") if task.created_at else None,
        "started_at": task.started_at.isoformat(timespec="seconds") if task.started_at else None,
        "heartbeat_at": task.heartbeat_at.isoformat(timespec="seconds") if task.heartbeat_at else None,
        "finished_at": task.finished_at.isoformat(timespec="seconds") if task.finished_at else None,
    }


def sanitize_task(task: dict | None) -> dict | None:
    if task is None:
        return None
    public = dict(task)
    payload = dict(public.get("payload") or {})
    if "documents" in payload:
        payload["document_count"] = len(payload.pop("documents") or [])
    public["payload"] = payload
    return public


def create_task(task_type: str, created_by: int, payload: dict | None = None) -> dict:
    now = _utcnow()
    if has_app_context():
        from app.models.task import Task

        task = Task(
            task_type=task_type,
            status="pending",
            progress=0,
            message="任务已创建，等待后台调度执行。",
            payload=payload or {},
            created_by=created_by,
            created_at=now,
        )
        db.session.add(task)
        db.session.commit()
        return _serialize(task)

    with _LOCK:
        task = {
            "id": len(_TASKS) + 1,
            "type": task_type,
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待后台调度执行。",
            "payload": payload or {},
            "result": None,
            "created_by": created_by,
            "created_at": now.isoformat(timespec="seconds"),
            "started_at": None,
            "heartbeat_at": None,
            "lease_token": None,
            "attempt": 0,
            "finished_at": None,
        }
        _TASKS.append(task)
        return task


def claim_task(task_id: int) -> str | None:
    now = _utcnow()
    lease_token = uuid.uuid4().hex
    if has_app_context():
        from app.models.task import Task

        updated = Task.query.filter(
            Task.id == task_id,
            Task.status == "pending",
        ).update(
            {
                Task.status: "running",
                Task.progress: 1,
                Task.message: "后台任务已领取，准备执行。",
                Task.started_at: now,
                Task.heartbeat_at: now,
                Task.lease_token: lease_token,
                Task.attempt: db.func.coalesce(Task.attempt, 0) + 1,
            },
            synchronize_session=False,
        )
        db.session.commit()
        return lease_token if updated == 1 else None

    with _LOCK:
        task = next((item for item in _TASKS if item["id"] == task_id), None)
        if task is None or task["status"] != "pending":
            return False
        task.update(
            status="running",
            progress=1,
            message="后台任务已领取，准备执行。",
            started_at=now.isoformat(timespec="seconds"),
            heartbeat_at=now.isoformat(timespec="seconds"),
            lease_token=lease_token,
            attempt=int(task.get("attempt") or 0) + 1,
        )
        return lease_token


def touch_task(task_id: int, lease_token: str | None = None) -> bool:
    now = _utcnow()
    effective_lease = lease_token or _CURRENT_TASK_LEASE.get()
    if not effective_lease:
        return False
    if has_app_context():
        from app.models.task import Task

        updated = Task.query.filter(
            Task.id == task_id,
            Task.status == "running",
            Task.lease_token == effective_lease,
        ).update(
            {Task.heartbeat_at: now},
            synchronize_session=False,
        )
        db.session.commit()
        return updated == 1

    with _LOCK:
        task = next((item for item in _TASKS if item["id"] == task_id), None)
        if (
            task is None
            or task["status"] != "running"
            or task.get("lease_token") != effective_lease
        ):
            return False
        task["heartbeat_at"] = now.isoformat(timespec="seconds")
        return True


def recoverable_task_ids(task_types: list[str], stale_after_seconds: int) -> list[int]:
    if not has_app_context():
        return []

    from sqlalchemy import or_

    from app.models.task import Task

    cutoff = _utcnow() - timedelta(seconds=max(1, stale_after_seconds))
    last_seen = db.func.coalesce(Task.heartbeat_at, Task.started_at)
    Task.query.filter(
        Task.task_type.in_(task_types),
        Task.status == "running",
        or_(last_seen.is_(None), last_seen <= cutoff),
    ).update(
        {
            Task.status: "pending",
            Task.progress: 0,
            Task.message: "检测到上次进程中断，任务已重新排队。",
            Task.started_at: None,
            Task.heartbeat_at: None,
            Task.lease_token: None,
            Task.finished_at: None,
        },
        synchronize_session=False,
    )
    db.session.commit()
    return [
        task.id
        for task in Task.query.filter(
            Task.task_type.in_(task_types),
            Task.status == "pending",
        )
        .order_by(Task.id)
        .all()
    ]


def _normalized_payload(payload: dict | None) -> dict:
    normalized = dict(payload or {})
    keyword = normalized.get("keyword")
    if isinstance(keyword, str):
        normalized["keyword"] = " ".join(keyword.split()).casefold()
    platforms = normalized.get("platforms")
    if isinstance(platforms, list):
        normalized["platforms"] = sorted(
            {
                item.strip().casefold()
                for item in platforms
                if isinstance(item, str) and item.strip()
            }
        )
    return normalized


def find_recent_equivalent_task(
    task_type: str,
    created_by: int,
    payload: dict,
    within_seconds: int,
) -> dict | None:
    cutoff = _utcnow() - timedelta(seconds=max(1, within_seconds))
    expected = _normalized_payload(payload)
    statuses = {"pending", "running", "success"}

    if has_app_context():
        from app.models.task import Task

        candidates = Task.query.filter(
            Task.task_type == task_type,
            Task.created_by == created_by,
            Task.status.in_(statuses),
            Task.created_at >= cutoff,
        ).order_by(Task.id.desc()).all()
        for task in candidates:
            if _normalized_payload(task.payload) == expected:
                return _serialize(task)
        return None

    with _LOCK:
        for task in reversed(_TASKS):
            created_at = datetime.fromisoformat(task["created_at"])
            if (
                task["task_type"] == task_type
                and task["created_by"] == created_by
                and task["status"] in statuses
                and created_at >= cutoff
                and _normalized_payload(task.get("payload")) == expected
            ):
                return task
    return None


def _task_lock_name(task_type: str, created_by: int, payload: dict) -> str:
    signature = json.dumps(
        [task_type, created_by, _normalized_payload(payload)],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"opinion-task-{hashlib.sha256(signature.encode('utf-8')).hexdigest()[:48]}"


@contextmanager
def _equivalent_task_lock(lock_name: str):
    if has_app_context() and db.engine.dialect.name == "mysql":
        from sqlalchemy import text

        connection = db.engine.connect()
        acquired = connection.execute(
            text("SELECT GET_LOCK(:lock_name, 5)"), {"lock_name": lock_name}
        ).scalar()
        if acquired != 1:
            connection.close()
            raise TimeoutError("cannot acquire equivalent task creation lock")
        try:
            yield
        finally:
            connection.execute(
                text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name}
            )
            connection.close()
        return

    with _CREATION_LOCK:
        yield


def create_or_reuse_recent_task(
    task_type: str,
    created_by: int,
    payload: dict,
    within_seconds: int,
) -> tuple[dict, bool]:
    lock_name = _task_lock_name(task_type, created_by, payload)
    with _equivalent_task_lock(lock_name):
        existing = find_recent_equivalent_task(
            task_type,
            created_by,
            payload,
            within_seconds,
        )
        if existing is not None:
            return existing, True
        return create_task(task_type, created_by, payload), False


def reset_task_store() -> None:
    with _LOCK:
        _TASKS.clear()


def get_task(task_id: int) -> dict | None:
    if has_app_context():
        from app.models.task import Task

        task = db.session.get(Task, task_id)
        return _serialize(task) if task else None
    with _LOCK:
        return next((task for task in _TASKS if task["id"] == task_id), None)


def update_task(task_id: int, lease_token: str | None = None, **changes) -> dict:
    if "progress" in changes:
        changes["progress"] = max(0, min(100, int(changes["progress"])))
    now = _utcnow()
    effective_lease = lease_token or _CURRENT_TASK_LEASE.get()

    if has_app_context():
        from app.models.task import Task

        query = Task.query.filter(Task.id == task_id)
        if effective_lease:
            query = query.filter(Task.lease_token == effective_lease)
        task = query.with_for_update().first()
        if task is None:
            db.session.rollback()
            if effective_lease:
                raise StaleTaskLeaseError(f"task lease expired: {task_id}")
            raise KeyError(f"task not found: {task_id}")
        if changes.get("status") == "running" and task.started_at is None:
            changes.setdefault("started_at", now)
        if task.status == "running" and changes.get("status") not in {"success", "failed"}:
            changes.setdefault("heartbeat_at", now)
        if changes.get("status") in {"success", "failed"}:
            changes.setdefault("finished_at", now)
            changes.setdefault("lease_token", None)
        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)
        db.session.commit()
        return _serialize(task)

    with _LOCK:
        task = next((item for item in _TASKS if item["id"] == task_id), None)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        if effective_lease and task.get("lease_token") != effective_lease:
            raise StaleTaskLeaseError(f"task lease expired: {task_id}")
        if changes.get("status") == "running" and task.get("started_at") is None:
            changes.setdefault("started_at", now.isoformat(timespec="seconds"))
        if task["status"] == "running" and changes.get("status") not in {"success", "failed"}:
            changes.setdefault("heartbeat_at", now.isoformat(timespec="seconds"))
        if changes.get("status") in {"success", "failed"}:
            changes.setdefault("finished_at", now.isoformat(timespec="seconds"))
            changes.setdefault("lease_token", None)
        task.update(changes)
        return task


def list_tasks(created_by: int | None = None) -> list[dict]:
    if has_app_context():
        from app.models.task import Task

        query = Task.query
        if created_by is not None:
            query = query.filter(Task.created_by == created_by)
        return [_serialize(task) for task in query.order_by(Task.id.desc()).all()]
    with _LOCK:
        if created_by is None:
            return list(_TASKS)
        return [task for task in _TASKS if task["created_by"] == created_by]


def latest_status(created_by: int | None = None) -> dict:
    if has_app_context():
        from app.models.task import Task

        query = Task.query.filter(Task.task_type == "crawl")
        if created_by is not None:
            query = query.filter(Task.created_by == created_by)
        task = query.order_by(Task.id.desc()).first()
        latest = _serialize(task) if task else None
    else:
        with _LOCK:
            candidates = [task for task in _TASKS if task["task_type"] == "crawl"]
            if created_by is not None:
                candidates = [task for task in candidates if task["created_by"] == created_by]
            latest = candidates[-1] if candidates else None
    return {"latest_task": sanitize_task(latest), "crawl_enabled": True}
