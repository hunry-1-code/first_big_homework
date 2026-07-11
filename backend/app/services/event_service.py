from __future__ import annotations


SAMPLE_EVENT = {
    "id": 1,
    "title": "样例舆情事件",
    "summary": "这是用于联调的样例事件。后续由事件聚合和报告生成模块替换。",
    "heat_index": 87.5,
    "lifecycle_stage": "成长期",
    "sentiment_positive": 0.22,
    "sentiment_negative": 0.51,
    "sentiment_neutral": 0.27,
}


def list_events(args) -> dict:
    page = int(args.get("page", 1))
    size = int(args.get("size", 20))
    return {"events": [SAMPLE_EVENT], "total": 1, "page": page, "size": size}


def get_event_detail(event_id: int) -> dict:
    event = {**SAMPLE_EVENT, "id": event_id}
    return {
        **event,
        "report": {
            "overview_text": "报告内容由后台 report 任务生成，这里是接口占位。",
            "risk_data": {"level": "中风险", "score": 55},
        },
        "trend": {"dates": ["2026-07-08", "2026-07-09"], "counts": [12, 35], "key_points": []},
        "sentiment": {
            "positive": event["sentiment_positive"],
            "negative": event["sentiment_negative"],
            "neutral": event["sentiment_neutral"],
            "daily": [],
        },
        "platform": {"platforms": [{"name": "样例数据", "count": 47, "percentage": 1.0}]},
        "keywords": {
            "keywords": [
                {"word": "舆情", "weight": 0.95},
                {"word": "安全", "weight": 0.88},
                {"word": "网络", "weight": 0.82},
                {"word": "监测", "weight": 0.76},
                {"word": "热点", "weight": 0.71},
                {"word": "传播", "weight": 0.65},
                {"word": "大V转发", "weight": 0.58},
                {"word": "评论区", "weight": 0.53},
                {"word": "热度指数", "weight": 0.49},
                {"word": "负面情感", "weight": 0.44},
                {"word": "研判报告", "weight": 0.39},
                {"word": "谣言检测", "weight": 0.34},
                {"word": "置信度", "weight": 0.30},
                {"word": "数据清洗", "weight": 0.26},
                {"word": "博主", "weight": 0.22},
                {"word": "系统预警", "weight": 0.18},
                {"word": "敏感词", "weight": 0.15},
                {"word": "公关", "weight": 0.12}
            ]
        },
        "articles": {
            "articles": [
                {
                    "id": 1,
                    "platform": "sample",
                    "title": "样例报道标题",
                    "clean_content": "样例报道清洗正文，供前端联调。",
                    "sentiment_label": "负面",
                }
            ],
            "total": 1,
        },
    }


def search_events(keyword: str) -> list[dict]:
    if not keyword:
        return [SAMPLE_EVENT]
    return [{**SAMPLE_EVENT, "title": f"{keyword} 相关样例事件"}]

