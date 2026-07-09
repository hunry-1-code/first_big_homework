from apscheduler.schedulers.background import BackgroundScheduler


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return scheduler

