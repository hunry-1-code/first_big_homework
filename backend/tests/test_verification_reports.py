from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.verify_fake_detection_pipeline import render_fake_detection_report
from scripts.verify_hdbscan_pipeline import render_hdbscan_report


def test_fake_detection_report_contains_inputs_outputs_and_disclaimer():
    report = render_fake_detection_report(
        event={"id": 1, "title": "测试事件"},
        rows=[
            {
                "article_id": 2,
                "title": "输入标题",
                "platform": "news_people",
                "content_excerpt": "输入正文",
                "score": 55.0,
                "is_suspicious": True,
                "method": "mixed",
                "reason": "交叉验证不足",
                "feature_scores": {"source_traceability": 1.0},
                "llm_review": {"risk_level": "medium"},
            }
        ],
    )

    assert "## 输入" in report
    assert "## 输出判断" in report
    assert "输入标题" in report
    assert "55.0" in report
    assert "可疑风险检测不等同于事实核查" in report


def test_hdbscan_report_contains_feature_dimensions_clusters_and_noise():
    report = render_hdbscan_report(
        analysis_run_id=3,
        aggregation_run_id=4,
        inputs=[
            {
                "article_id": 1,
                "title": "文章一",
                "platform": "news_people",
                "bge_dimension": 384,
                "tfidf_dimension": 12,
            }
        ],
        assignments=[
            {
                "article_id": 1,
                "cluster_index": 0,
                "action": "attach",
                "reasons": ["HDBSCAN_CLUSTER"],
            }
        ],
        warnings=["HDBSCAN: 1 clusters, 0 noise points"],
    )

    assert "BGE 维度" in report
    assert "TF-IDF 维度" in report
    assert "簇分配" in report
    assert "噪声" in report
