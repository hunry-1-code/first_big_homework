from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.scheduler import set_daily_hot_schedule


class FakeJob:
    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.next_run_time = "2026-07-15T12:00:00"


class FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.removed = []

    def add_job(self, function, trigger, **kwargs):
        self.jobs[kwargs["id"]] = FakeJob({"trigger": trigger, **kwargs})

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.removed.append(job_id)
        self.jobs.pop(job_id, None)


class App:
    def __init__(self):
        self.config = {"DAILY_HOT_REFRESH_INTERVAL_SECONDS": 900}


def test_daily_hot_schedule_uses_one_existing_scheduler_job():
    app = App()
    scheduler = FakeScheduler()

    set_daily_hot_schedule(app, scheduler, enabled=True, interval_seconds=1800)
    set_daily_hot_schedule(app, scheduler, enabled=True, interval_seconds=3600)

    assert list(scheduler.jobs) == ["daily-hot-refresh"]
    assert scheduler.jobs["daily-hot-refresh"].kwargs["seconds"] == 3600

    set_daily_hot_schedule(app, scheduler, enabled=False, interval_seconds=3600)

    assert scheduler.get_job("daily-hot-refresh") is None
    assert scheduler.removed == ["daily-hot-refresh"]
