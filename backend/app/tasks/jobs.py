def crawl_job(task_id: int) -> dict:
    return {"task_id": task_id, "status": "reserved", "message": "爬虫任务占位，后续由采集组实现。"}


def analyze_job(task_id: int) -> dict:
    return {"task_id": task_id, "status": "reserved", "message": "分析任务占位，后续由算法组实现。"}


def report_job(task_id: int) -> dict:
    return {"task_id": task_id, "status": "reserved", "message": "报告任务占位，后续由报告组实现。"}

