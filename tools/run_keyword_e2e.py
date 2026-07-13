from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validate_backend_live import sanitize_result


E2E_SENSITIVE_KEY = re.compile(
    r"authorization|password|passwd|token|cookie|api[-_]?key|secret",
    re.IGNORECASE,
)
FILM_TERMS = ("电影", "影片", "定档", "上映", "预告", "导演", "主演")


def build_backend_environment(
    base_environment: dict[str, str] | None,
    database_path: str,
) -> dict[str, str]:
    env = dict(base_environment or os.environ)
    normalized = str(database_path).replace("\\", "/")
    env.update(
        DATABASE_URL=f"sqlite:///{normalized}",
        TASK_RECOVER_ON_STARTUP="false",
        TASKS_RUN_SYNC="false",
        AUTO_CREATE_DB="true",
        FLASK_DEBUG="0",
        PYTHONUNBUFFERED="1",
    )
    return env


def build_search_payload(
    keyword: str,
    platforms: list[str],
    target_count: int,
) -> dict[str, Any]:
    return {
        "keyword": str(keyword).strip(),
        "platforms": list(dict.fromkeys(str(item).strip() for item in platforms if str(item).strip())),
        "target_count": max(1, min(int(target_count), 200)),
    }


def summarize_task(task: dict) -> dict[str, Any]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    return {
        "task_id": task.get("id"),
        "status": task.get("status"),
        "progress": int(task.get("progress") or 0),
        "message": str(task.get("message") or "")[:500],
        "result": safe_artifact(result),
        "updated_at": task.get("updated_at"),
    }


def _write_json(
    path: Path,
    value,
    *,
    secrets: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            safe_artifact(value, secrets or []),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) != 0


def _wait_http(url: str, *, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code < 500:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"service did not become ready: {url}: {type(last_error).__name__ if last_error else 'timeout'}"
    )


def _start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    return process, handle


def _stop_process(process, handle) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if handle is not None:
        handle.close()


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token = ""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        params=None,
        timeout: int = 60,
    ):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            json=json_body,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"non-json API response: {path}: HTTP {response.status_code}"
            ) from exc
        message = str(body.get("message") or "")
        code = int(body.get("code") or response.status_code)
        if response.status_code >= 400 or code >= 400:
            raise RuntimeError(
                f"API request failed: {path}: HTTP {response.status_code}: {message[:200]}"
            )
        return body.get("data")

    def login(self, username: str, password: str) -> dict:
        data = self.request(
            "POST",
            "/api/auth/login",
            json_body={"username": username, "password": password},
        )
        token = str((data or {}).get("token") or "")
        if not token:
            raise RuntimeError("login response did not include token")
        self.token = token
        return dict((data or {}).get("user") or {})


def _poll_task(
    api: ApiClient,
    task_id: int,
    *,
    timeout_seconds: int = 900,
) -> tuple[dict, list[dict]]:
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    history = []
    last_signature = None
    while time.monotonic() < deadline:
        task = api.request("GET", f"/api/tasks/{int(task_id)}")
        summary = summarize_task(task or {})
        signature = (
            summary.get("status"),
            summary.get("progress"),
            summary.get("message"),
        )
        if signature != last_signature:
            history.append(
                {
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    **summary,
                }
            )
            last_signature = signature
        if summary.get("status") == "success":
            return task, history
        if summary.get("status") == "failed":
            raise RuntimeError(
                f"keyword task failed: {summary.get('message') or 'unknown'}"
            )
        time.sleep(1)
    raise TimeoutError(f"keyword task timed out: {task_id}")


def _text_snapshot(value: str | None, *, limit: int = 800) -> dict:
    text = str(value or "")
    return {
        "length": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpt": text[:limit],
    }


def _decode_sql_value(key: str, value):
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if key in {"raw_content", "clean_content"}:
        return _text_snapshot(value)
    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in "[{":
            try:
                return json.loads(text)
            except ValueError:
                pass
    return value


def _dump_table(connection: sqlite3.Connection, table: str) -> list[dict]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return []
    rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
    return [
        {
            key: _decode_sql_value(key, row[key])
            for key in row.keys()
            if not E2E_SENSITIVE_KEY.search(key)
        }
        for row in rows
    ]


def export_database_stages(
    database_path: Path,
    artifact_dir: Path,
    *,
    secrets: list[str] | None = None,
) -> None:
    connection = sqlite3.connect(str(database_path), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        groups = {
            "04_raw_articles.json": [
                "article",
                "article_snapshot",
            ],
            "05_preprocessing.json": [
                "article",
                "document_features",
            ],
            "06_content_analysis.json": [
                "analysis_run",
                "analysis_run_article",
                "document_features",
                "article_embedding",
            ],
            "07_aggregation.json": [
                "aggregation_run",
                "aggregation_cluster",
                "aggregation_assignment",
                "event_representation",
            ],
            "08_sentiment.json": [
                "sentiment_run",
                "article_sentiment_result",
                "event_sentiment_snapshot",
            ],
            "09_database_publish_state.json": [
                "event",
                "event_article_membership",
                "event_heat_snapshot",
                "report",
                "task",
            ],
        }
        for filename, tables in groups.items():
            _write_json(
                artifact_dir / filename,
                {
                    "database": database_path.name,
                    "tables": {
                        table: _dump_table(connection, table)
                        for table in tables
                    },
                },
                secrets=secrets,
            )
    finally:
        connection.close()


def run_api_cycle(
    *,
    api: ApiClient,
    keyword: str,
    platforms: list[str],
    target_count: int,
    username: str,
    password: str,
    artifact_dir: Path,
    secrets: list[str],
) -> dict[str, Any]:
    user = api.login(username, password)
    secrets = [*secrets, password, api.token]
    _write_json(
        artifact_dir / "01_login.json",
        {"status": "success", "user": user},
        secrets=secrets,
    )
    payload = build_search_payload(keyword, platforms, target_count)
    submission = api.request(
        "POST",
        "/api/crawler/search",
        json_body=payload,
    )
    _write_json(
        artifact_dir / "02_search_submission.json",
        {"request": payload, "response": submission},
        secrets=secrets,
    )
    task_id = (submission or {}).get("task_id")
    if task_id:
        task, history = _poll_task(api, int(task_id))
    elif (submission or {}).get("cached"):
        task = {
            "status": "success",
            "progress": 100,
            "result": {
                "aggregation_run_id": submission.get("aggregation_run_id")
            },
        }
        history = [
            {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "progress": 100,
                "message": "cached search result",
                "result": task["result"],
            }
        ]
    else:
        raise RuntimeError("search response did not provide task or cache")
    _write_json(
        artifact_dir / "03_task_poll_history.json",
        {"task_id": task_id, "history": history, "final": summarize_task(task)},
        secrets=secrets,
    )
    result = dict(task.get("result") or {})
    aggregation_run_id = result.get("aggregation_run_id") or (
        submission or {}
    ).get("aggregation_run_id")
    if not aggregation_run_id:
        raise RuntimeError("search cycle did not produce aggregation run")

    cluster_page = api.request(
        "GET",
        f"/api/aggregation/runs/{int(aggregation_run_id)}/clusters",
        params={"page": 1, "size": 100},
    )
    clusters = list((cluster_page or {}).get("clusters") or [])
    selected = choose_relevant_cluster(clusters, keyword)
    assignments = api.request(
        "GET",
        f"/api/aggregation/runs/{int(aggregation_run_id)}/assignments",
        params={"page": 1, "size": 200},
    )
    aggregation_artifact = {
        "aggregation_run_id": aggregation_run_id,
        "clusters": clusters,
        "assignments": assignments,
        "selected_cluster": selected,
    }
    _write_json(
        artifact_dir / "07_aggregation_api.json",
        aggregation_artifact,
        secrets=secrets,
    )
    if selected is None:
        raise RuntimeError("no sufficiently relevant movie cluster was found")

    cluster_sentiment = None
    try:
        cluster_sentiment = api.request(
            "GET",
            f"/api/aggregation/clusters/{int(selected['id'])}/sentiment",
        )
    except RuntimeError:
        cluster_sentiment = {"status": "unavailable"}
    _write_json(
        artifact_dir / "08_cluster_sentiment_api.json",
        cluster_sentiment,
        secrets=secrets,
    )
    published = api.request(
        "POST",
        f"/api/aggregation/clusters/{int(selected['id'])}/publish",
        json_body={},
        timeout=180,
    )
    event_id = int((published or {}).get("event_id") or 0)
    if event_id <= 0:
        raise RuntimeError("publish response did not include event id")
    _write_json(
        artifact_dir / "09_publish.json",
        {"selected_cluster": selected, "publish": published},
        secrets=secrets,
    )

    dashboard = api.request(
        "GET",
        "/api/events",
        params={"page": 1, "size": 100, "keyword": "功夫女足"},
    )
    detail = api.request("GET", f"/api/events/{event_id}", timeout=120)
    propagation = api.request(
        "GET",
        f"/api/events/{event_id}/propagation",
        timeout=120,
    )
    report = api.request("GET", f"/api/events/{event_id}/report", timeout=120)
    qa = api.request(
        "POST",
        "/api/qa/ask",
        json_body={
            "event_id": event_id,
            "question": (
                "请根据当前报道说明《功夫女足》电影的核心信息、"
                "舆论情绪和数据局限，并区分事实与推断。"
            ),
        },
        timeout=120,
    )
    headers = {"Authorization": f"Bearer {api.token}"}
    export_response = api.session.get(
        f"{api.base_url}/api/events/{event_id}/report/export",
        params={"format": "html"},
        headers=headers,
        timeout=120,
    )
    export_response.raise_for_status()
    export_text = export_response.text
    export_summary = {
        "status_code": export_response.status_code,
        "content_type": export_response.headers.get("Content-Type"),
        "length": len(export_text),
        "sha256": hashlib.sha256(export_text.encode("utf-8")).hexdigest(),
        "excerpt": export_text[:800],
    }
    _write_json(artifact_dir / "10_dashboard_api.json", dashboard, secrets=secrets)
    _write_json(artifact_dir / "11_event_detail_api.json", detail, secrets=secrets)
    _write_json(
        artifact_dir / "12_propagation_api.json",
        propagation,
        secrets=secrets,
    )
    _write_json(
        artifact_dir / "13_report_api.json",
        {"report": report, "export": export_summary},
        secrets=secrets,
    )
    _write_json(artifact_dir / "14_qa_api.json", qa, secrets=secrets)
    return {
        "task_id": task_id,
        "task_result": result,
        "aggregation_run_id": int(aggregation_run_id),
        "selected_cluster": selected,
        "event_id": event_id,
        "dashboard": dashboard,
        "detail": detail,
        "propagation": propagation,
        "report": report,
        "qa": qa,
        "secrets": secrets,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one real keyword through backend and frontend E2E"
    )
    parser.add_argument("--keyword", default="《功夫女足》电影")
    parser.add_argument("--platform", action="append")
    parser.add_argument("--target-count", type=int, default=24)
    parser.add_argument(
        "--artifact-dir",
        default="tests/e2e/kung_fu_women_football",
    )
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--skip-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    artifact_dir = (root / args.artifact_dir).resolve()
    runtime_dir = root / "artifacts" / "kung_fu_women_football"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    database_path = runtime_dir / "kung_fu_women_football.db"
    if database_path.exists():
        database_path.unlink()
    if not _port_is_free("127.0.0.1", 5000):
        raise SystemExit("port 5000 is already in use")

    from dotenv import load_dotenv

    load_dotenv((root / args.env_file).resolve(), override=True)
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.core.config import Config
    from tools.validate_backend_live import configured_secrets

    platforms = args.platform or ["baidu", "weibo", "zhihu", "bilibili"]
    secrets = configured_secrets(Config)
    manifest = {
        "keyword": args.keyword,
        "platforms": platforms,
        "target_count": args.target_count,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
        ).strip(),
        "runtime_database": database_path.name,
        "backend": {"status": "starting"},
        "frontend": {"status": "skipped" if args.skip_browser else "pending"},
    }
    _write_json(artifact_dir / "00_manifest.json", manifest, secrets=secrets)

    backend_process = None
    backend_log = None
    try:
        env = build_backend_environment(os.environ, database_path.as_posix())
        backend_process, backend_log = _start_process(
            [
                sys.executable,
                "-c",
                (
                    "from app import create_app; "
                    "app=create_app(); "
                    "app.run(host='127.0.0.1', port=5000, "
                    "debug=False, use_reloader=False)"
                ),
            ],
            cwd=backend,
            env=env,
            log_path=runtime_dir / "backend.log",
        )
        _wait_http("http://127.0.0.1:5000/api/health", timeout_seconds=90)
        manifest["backend"] = {"status": "ready", "port": 5000}
        api = ApiClient("http://127.0.0.1:5000")
        cycle = run_api_cycle(
            api=api,
            keyword=args.keyword,
            platforms=platforms,
            target_count=args.target_count,
            username=Config.DEMO_ADMIN_USERNAME,
            password=Config.DEMO_ADMIN_PASSWORD,
            artifact_dir=artifact_dir,
            secrets=secrets,
        )
        export_database_stages(
            database_path,
            artifact_dir,
            secrets=cycle["secrets"],
        )
        manifest.update(
            completed_at=datetime.now(timezone.utc).isoformat(),
            backend={"status": "success", "port": 5000},
            ids={
                "task_id": cycle["task_id"],
                "analysis_run_id": cycle["task_result"].get("analysis_run_id"),
                "aggregation_run_id": cycle["aggregation_run_id"],
                "sentiment_run_id": cycle["task_result"].get("sentiment_run_id"),
                "cluster_id": cycle["selected_cluster"].get("id"),
                "event_id": cycle["event_id"],
            },
        )
        _write_json(
            artifact_dir / "00_manifest.json",
            manifest,
            secrets=cycle["secrets"],
        )
        if not args.skip_browser:
            print("API phase completed; browser phase will run after frontend startup.")
        print(
            json.dumps(
                {
                    "status": "success",
                    "event_id": cycle["event_id"],
                    "aggregation_run_id": cycle["aggregation_run_id"],
                    "artifact_dir": str(artifact_dir),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        _stop_process(backend_process, backend_log)


def safe_artifact(value, secrets: list[str] | None = None):
    if isinstance(value, dict):
        return {
            str(key): safe_artifact(item, secrets)
            for key, item in value.items()
            if not E2E_SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [safe_artifact(item, secrets) for item in value]
    return sanitize_result(value, secrets or [])


def _text(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def _cluster_text(cluster: dict) -> str:
    parts = [
        cluster.get("title"),
        cluster.get("name"),
        cluster.get("label"),
        cluster.get("cluster_label"),
        cluster.get("topic_name"),
        cluster.get("summary"),
    ]
    for item in cluster.get("keywords") or []:
        if isinstance(item, dict):
            parts.append(
                item.get("word")
                or item.get("term")
                or item.get("keyword")
            )
        else:
            parts.append(item)
    return " ".join(_text(part) for part in parts if part)


def choose_relevant_cluster(
    clusters: list[dict],
    keyword: str,
) -> dict | None:
    query = _text(keyword)
    tokens = [
        token
        for token in ("功夫女足", "功夫", "女足", "电影")
        if token in query
    ]
    ranked = []
    for cluster in clusters or []:
        combined = _cluster_text(cluster)
        score = 0.0
        reasons = []
        if "功夫女足" in combined:
            score += 10
            reasons.append("exact_phrase")
        has_film = any(term in combined for term in FILM_TERMS)
        if "功夫" in combined and "女足" in combined and has_film:
            score += 6
            reasons.append("movie_context")
        overlap = [token for token in tokens if token in combined]
        score += 2 * len(overlap)
        if overlap:
            reasons.append(f"query_overlap:{','.join(overlap)}")
        try:
            member_count = max(0, int(cluster.get("member_count") or 0))
        except (TypeError, ValueError):
            member_count = 0
        score += min(member_count, 5)
        if ("女足" in combined or "足球" in combined) and not has_film:
            score -= 6
            reasons.append("sports_without_movie")
        if "功夫足球" in combined and "功夫女足" not in combined:
            score -= 4
            reasons.append("old_kung_fu_soccer")
        ranked.append(
            (
                score,
                member_count,
                -int(cluster.get("id") or 0),
                cluster,
                reasons,
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    score, _count, _id_key, selected, reasons = ranked[0]
    if score < 6:
        return None
    return {
        **selected,
        "selection_score": round(score, 4),
        "selection_reasons": reasons,
    }


def _article_relevant(article: dict) -> bool:
    combined = _text(
        f"{article.get('title') or ''} {article.get('clean_content') or ''}"
    )
    return (
        "功夫女足" in combined
        or (
            "功夫" in combined
            and "女足" in combined
            and any(term in combined for term in FILM_TERMS)
        )
    )


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def assess_frontend_data_quality(
    detail: dict,
    propagation: dict | None,
    dom_text: str,
) -> dict[str, Any]:
    propagation = propagation or {}
    passed_rules: list[str] = []
    failed_rules: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    def rule(name: str, passed: bool) -> None:
        (passed_rules if passed else failed_rules).append(name)

    title = _text(detail.get("title"))
    rule(
        "TITLE_RELEVANT",
        "功夫女足" in title or ("功夫" in title and "女足" in title),
    )
    rule("SUMMARY_PRESENT", bool(str(detail.get("summary") or "").strip()))
    rule(
        "LIFECYCLE_PRESENT",
        bool(str(detail.get("lifecycle_stage") or "").strip()),
    )
    rule("HEAT_FINITE", _finite_number(detail.get("heat_index")))

    articles_value = detail.get("articles") or {}
    articles = list(articles_value.get("articles") or [])
    try:
        article_total = int(articles_value.get("total") or 0)
    except (TypeError, ValueError):
        article_total = 0
    relevant_count = sum(1 for article in articles if _article_relevant(article))
    relevance_ratio = relevant_count / len(articles) if articles else 0.0
    metrics.update(
        article_total=article_total,
        inspected_articles=len(articles),
        relevant_articles=relevant_count,
        article_relevance_ratio=round(relevance_ratio, 4),
    )
    rule("ARTICLE_COUNT_SUFFICIENT", article_total >= 3)
    rule("ARTICLE_RELEVANCE_LOW", relevance_ratio >= 0.7)

    platform_rows = list(
        ((detail.get("platform") or {}).get("platforms") or [])
    )
    platform_count = len(platform_rows)
    metrics["platform_count"] = platform_count
    limitations = list(propagation.get("limitations") or [])
    rule(
        "SINGLE_PLATFORM_WITHOUT_LIMITATION",
        platform_count >= 2 or bool(limitations),
    )
    try:
        platform_article_total = sum(
            int(row.get("count") or 0) for row in platform_rows
        )
    except (TypeError, ValueError):
        platform_article_total = -1
    metrics["platform_article_total"] = platform_article_total
    rule(
        "PLATFORM_COUNT_ALIGNED",
        article_total == 0 or platform_article_total == article_total,
    )

    sentiment = [
        detail.get("sentiment_positive"),
        detail.get("sentiment_negative"),
        detail.get("sentiment_neutral"),
    ]
    sentiment_valid = all(_finite_number(value) for value in sentiment)
    sentiment_sum = (
        sum(float(value) for value in sentiment)
        if sentiment_valid
        else float("nan")
    )
    metrics["sentiment_sum"] = (
        round(sentiment_sum, 6) if math.isfinite(sentiment_sum) else None
    )
    rule(
        "SENTIMENT_SUM_INVALID",
        sentiment_valid and abs(sentiment_sum - 1.0) <= 0.05,
    )

    trend = detail.get("trend") or {}
    dates = list(trend.get("dates") or [])
    counts = list(trend.get("counts") or [])
    metrics["trend_points"] = len(dates)
    rule(
        "TREND_LENGTH_MISMATCH",
        bool(dates) and len(dates) == len(counts),
    )

    keywords = list(
        ((detail.get("keywords") or {}).get("keywords") or [])
    )
    non_query = [
        item
        for item in keywords
        if isinstance(item, dict)
        and item.get("word")
        and item.get("source") != "query"
    ]
    metrics["keyword_count"] = len(keywords)
    metrics["non_query_keyword_count"] = len(non_query)
    rule(
        "KEYWORD_DIVERSITY_LOW",
        len(keywords) >= 2 and len(non_query) >= 1,
    )

    report = detail.get("report") or {}
    risk_data = report.get("risk_data") or {}
    rule(
        "RISK_DATA_PRESENT",
        _finite_number(risk_data.get("score"))
        and bool(str(risk_data.get("level") or "").strip()),
    )
    normalized_dom = _text(dom_text)
    fixed_risk = bool(
        re.search(r"(?:虚假风险|持续时间)\s*[:：]?\s*45(?:\D|$)", normalized_dom)
    )
    rule("FIXED_RISK_PLACEHOLDER", not fixed_risk)
    invalid_dom = any(
        marker in normalized_dom
        for marker in ("undefined", "nan", "[object object]")
    )
    rule("DOM_INVALID_VALUE", not invalid_dom)
    rule(
        "RISK_SEMANTICS",
        "风险评估" in normalized_dom or "风险" not in normalized_dom,
    )

    coverage = str(propagation.get("coverage_status") or "")
    rule(
        "PROPAGATION_LIMITATION_EXPLAINED",
        coverage != "insufficient" or bool(limitations),
    )
    if coverage == "insufficient":
        warnings.append("传播关系证据不足，页面应展示限制说明")

    return {
        "passed": not failed_rules,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "metrics": metrics,
        "warnings": warnings,
    }


def safe_slug(keyword: str, *, event_id: int | None = None) -> str:
    text = unicodedata.normalize("NFKC", str(keyword or ""))
    text = re.sub(r"[《》【】（）()\[\]{}<>\"'`]+", "", text)
    text = re.sub(r"[^\w\u3400-\u9fff-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-_") or "keyword-e2e"
    if event_id is not None:
        text = f"{text}-event-{int(event_id)}"
    return text


__all__ = [
    "assess_frontend_data_quality",
    "build_backend_environment",
    "build_search_payload",
    "choose_relevant_cluster",
    "export_database_stages",
    "run_api_cycle",
    "safe_artifact",
    "safe_slug",
    "summarize_task",
]


if __name__ == "__main__":
    raise SystemExit(main())
