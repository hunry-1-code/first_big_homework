from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Thread
from typing import Callable


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="opinion-task")
_PENDING_SLOTS = BoundedSemaphore(100)


def _heartbeat_loop(app, task_id: int, lease_token: str, stop_event, interval: int) -> None:
    from app.services.task_service import touch_task

    while not stop_event.wait(interval):
        try:
            with app.app_context():
                if not touch_task(task_id, lease_token):
                    return
        except Exception as exc:
            app.logger.warning("任务 %s 心跳更新失败，将继续重试: %s", task_id, exc)


def _execute(app, function: Callable, task_id: int) -> object:
    with app.app_context():
        from app.services.task_service import claim_task

        lease_token = claim_task(task_id)
        if not lease_token:
            return None

    stop_heartbeat = Event()
    database_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    heartbeat_thread = None
    if not (app.config.get("TASKS_RUN_SYNC", False) and database_uri.startswith("sqlite")):
        heartbeat_thread = Thread(
            target=_heartbeat_loop,
            args=(app, task_id, lease_token, stop_heartbeat, app.config.get("TASK_HEARTBEAT_INTERVAL_SECONDS", 30)),
            name=f"opinion-task-heartbeat-{task_id}",
            daemon=True,
        )
        heartbeat_thread.start()
    from app.services.task_service import (
        StaleTaskLeaseError,
        activate_task_lease,
        reset_task_lease,
        update_task,
    )

    context_token = activate_task_lease(lease_token)
    try:
        with app.app_context():
            return function(task_id)
    except StaleTaskLeaseError:
        return None
    except Exception as exc:
        with app.app_context():
            try:
                update_task(
                    task_id,
                    lease_token=lease_token,
                    status="failed",
                    progress=100,
                    message=f"后台任务异常: {exc}",
                    result={"error": f"后台任务异常: {exc}"},
                )
            except StaleTaskLeaseError:
                pass
        return None
    finally:
        reset_task_lease(context_token)
        stop_heartbeat.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)


def _mark_failed(app, task_id: int, message: str) -> None:
    from app.services.task_service import update_task

    with app.app_context():
        update_task(
            task_id,
            status="failed",
            progress=100,
            message=message,
            result={"error": message},
        )


def submit_background_job(
    app,
    function: Callable,
    task_id: int,
    mark_failed_if_full: bool = True,
) -> Future | None:
    if app.config.get("TASKS_RUN_SYNC", False):
        try:
            _execute(app, function, task_id)
        except Exception as exc:
            _mark_failed(app, task_id, f"后台任务异常: {exc}")
        return None

    if not _PENDING_SLOTS.acquire(blocking=False):
        if mark_failed_if_full:
            _mark_failed(app, task_id, "后台任务队列已满，请稍后重试。")
        return None

    future = _EXECUTOR.submit(_execute, app, function, task_id)

    def completed(done: Future) -> None:
        try:
            error = done.exception()
            if error is not None:
                _mark_failed(app, task_id, f"后台任务异常: {error}")
        finally:
            _PENDING_SLOTS.release()

    future.add_done_callback(completed)
    return future


def shutdown_runner(wait: bool = True) -> None:
    _EXECUTOR.shutdown(wait=wait, cancel_futures=False)


def recover_background_jobs(app, job_registry: dict[str, Callable] | None = None) -> int:
    if job_registry is None:
        from app.tasks.jobs import (
            aggregation_job,
            analyze_job,
            crawl_job,
            hotspot_job,
            import_job,
            sentiment_job,
        )

        job_registry = {
            "crawl": crawl_job,
            "import": import_job,
            "analysis": analyze_job,
            "hotspot": hotspot_job,
            "aggregation": aggregation_job,
            "sentiment": sentiment_job,
        }

    from app.services.task_service import recoverable_task_ids

    with app.app_context():
        from app.models import Task

        task_ids = recoverable_task_ids(
            list(job_registry),
            app.config.get("TASK_RUNNING_TIMEOUT_SECONDS", 3600),
        )
        task_types = {
            task.id: task.task_type
            for task in Task.query.filter(Task.id.in_(task_ids))
        }

    submitted = 0
    for task_id in task_ids:
        function = job_registry.get(task_types.get(task_id))
        if function is not None:
            future = submit_background_job(
                app,
                function,
                task_id,
                mark_failed_if_full=False,
            )
            if app.config.get("TASKS_RUN_SYNC", False) or future is not None:
                submitted += 1
            else:
                break
    return submitted


def start_recovery_scheduler(app, scheduler=None):
    if scheduler is None:
        from app.tasks.scheduler import create_scheduler

        scheduler = create_scheduler()
    scheduler.add_job(
        lambda: recover_background_jobs(app),
        "interval",
        seconds=app.config.get("TASK_RECOVERY_SCAN_SECONDS", 60),
        id="task-recovery-scan",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    app.extensions["task_recovery_scheduler"] = scheduler
    return scheduler
