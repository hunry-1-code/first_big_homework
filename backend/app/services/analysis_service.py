def run_analysis_pipeline(task_id: int) -> dict:
    return {
        "task_id": task_id,
        "status": "reserved",
        "steps": ["clean", "segment", "tfidf", "cluster", "sentiment", "report"],
        "message": "分析流水线接口已预留，后续由算法组实现。",
    }

