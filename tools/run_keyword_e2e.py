from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
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
        TASK_HEARTBEAT_ENABLED="false",
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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def refresh_existing_cycle(
    *,
    api: ApiClient,
    artifact_dir: Path,
    username: str,
    password: str,
    secrets: list[str],
) -> dict[str, Any]:
    manifest = _read_json(artifact_dir / "00_manifest.json")
    ids = manifest.get("ids") or {}
    event_id = int(ids.get("event_id") or 0)
    cluster_id = int(ids.get("cluster_id") or 0)
    if event_id <= 0 or cluster_id <= 0:
        raise RuntimeError("existing E2E manifest does not contain event/cluster ids")

    user = api.login(username, password)
    secrets = [*secrets, password, api.token]
    _write_json(
        artifact_dir / "01_login.json",
        {"status": "success", "user": user, "reused_database": True},
        secrets=secrets,
    )
    published = api.request(
        "POST",
        f"/api/aggregation/clusters/{cluster_id}/publish",
        json_body={},
        timeout=180,
    )
    dashboard = api.request(
        "GET",
        "/api/events",
        params={"page": 1, "size": 100, "keyword": "功夫女足"},
    )
    detail = api.request("GET", f"/api/events/{event_id}", timeout=120)
    propagation = api.request(
        "GET", f"/api/events/{event_id}/propagation", timeout=120
    )
    report = api.request("GET", f"/api/events/{event_id}/report", timeout=120)
    previous_publish = {}
    publish_path = artifact_dir / "09_publish.json"
    if publish_path.exists():
        previous_publish = _read_json(publish_path)
    _write_json(
        publish_path,
        {
            **previous_publish,
            "publish_after_fix": published,
            "reused_database": True,
        },
        secrets=secrets,
    )
    _write_json(artifact_dir / "10_dashboard_api.json", dashboard, secrets=secrets)
    _write_json(artifact_dir / "11_event_detail_api.json", detail, secrets=secrets)
    _write_json(
        artifact_dir / "12_propagation_api.json", propagation, secrets=secrets
    )
    previous_report = {}
    report_path = artifact_dir / "13_report_api.json"
    if report_path.exists():
        previous_report = _read_json(report_path)
    _write_json(
        report_path,
        {**previous_report, "report": report, "reused_database": True},
        secrets=secrets,
    )
    return {
        "task_id": ids.get("task_id"),
        "task_result": {
            "analysis_run_id": ids.get("analysis_run_id"),
            "sentiment_run_id": ids.get("sentiment_run_id"),
        },
        "aggregation_run_id": int(ids.get("aggregation_run_id") or 0),
        "selected_cluster": {"id": cluster_id},
        "event_id": event_id,
        "dashboard": dashboard,
        "detail": detail,
        "propagation": propagation,
        "report": report,
        "qa": _read_json(artifact_dir / "14_qa_api.json")
        if (artifact_dir / "14_qa_api.json").exists()
        else {},
        "secrets": secrets,
    }


def _save_full_page_screenshot(driver, path: Path) -> None:
    original = driver.get_window_size()
    width = max(
        1440,
        int(driver.execute_script("return document.documentElement.scrollWidth") or 0),
    )
    height = max(
        1200,
        int(driver.execute_script("return document.documentElement.scrollHeight") or 0),
    )
    driver.set_window_size(min(width, 1920), min(height, 16000))
    driver.save_screenshot(str(path))
    driver.set_window_size(original["width"], original["height"])


def run_browser_cycle(
    *,
    base_url: str,
    keyword: str,
    event_id: int,
    task_id: int | None,
    username: str,
    password: str,
    artifact_dir: Path,
    detail: dict,
    propagation: dict,
    secrets: list[str],
) -> dict[str, Any]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    chrome_binary = Path(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    if not chrome_binary.exists():
        raise RuntimeError(f"Chrome binary not found: {chrome_binary}")

    names = browser_artifact_names(keyword, event_id=event_id)
    options = webdriver.ChromeOptions()
    options.binary_location = str(chrome_binary)
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    visible: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="kung-fu-e2e-chrome-") as profile:
        options.add_argument(f"--user-data-dir={profile}")
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 60)
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Math.random = () => 0.1;"},
            )
            driver.get(f"{base_url}/#/login")
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".login-form"))
            )
            inputs = driver.find_elements(By.CSS_SELECTOR, ".login-form input")
            if len(inputs) < 3:
                raise RuntimeError("login form did not expose username/password/captcha")
            for item, value in (
                (inputs[0], username),
                (inputs[1], password),
                (inputs[2], "1111"),
            ):
                item.click()
                item.send_keys(Keys.CONTROL, "a")
                item.send_keys(Keys.BACKSPACE)
                item.send_keys(value)
            login_diagnostics = {
                "inputs": [
                    {
                        "index": index,
                        "type": item.get_attribute("type"),
                        "placeholder": item.get_attribute("placeholder"),
                        "value_length": len(item.get_attribute("value") or ""),
                        "matches_username": item.get_attribute("value") == username,
                        "matches_password_length": len(item.get_attribute("value") or "")
                        == len(password),
                    }
                    for index, item in enumerate(inputs)
                ]
            }
            login_button = driver.find_element(
                By.XPATH,
                "//button[.//span[contains(normalize-space(.),'登录')]]",
            )
            login_button.click()
            WebDriverWait(driver, 20).until(
                lambda current: (
                    "#/login" not in current.current_url
                    or "用户名或密码错误"
                    in current.find_element(By.TAG_NAME, "body").text
                    or "登录失败" in current.find_element(By.TAG_NAME, "body").text
                )
            )
            if "#/login" in driver.current_url:
                login_diagnostics["body_excerpt"] = driver.find_element(
                    By.TAG_NAME, "body"
                ).text[:2000]
                login_diagnostics["console"] = driver.get_log("browser")
                _write_json(
                    artifact_dir / "15_login_failure.json",
                    login_diagnostics,
                    secrets=secrets,
                )
                driver.save_screenshot(
                    str(artifact_dir / "15_login_failure.png")
                )
                raise RuntimeError("frontend login failed; diagnostics saved")

            analysis_url = f"{base_url}/#/analysis"
            if task_id:
                analysis_url += f"?taskId={int(task_id)}"
            driver.get(analysis_url)
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), "事件定向分析"
                )
            )
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), "我的分析任务历史"
                )
            )
            analysis_body = driver.find_element(By.TAG_NAME, "body").text
            visible["analysis"] = {
                "url": driver.current_url,
                "has_keyword": "功夫女足" in analysis_body,
                "has_history": "我的分析任务历史" in analysis_body,
                "has_success_state": "成功" in analysis_body or "100%" in analysis_body,
            }
            _save_full_page_screenshot(driver, artifact_dir / names["analysis"])

            driver.get(f"{base_url}/#/dashboard")
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), "舆情事件看板"
                )
            )
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), "功夫女足"
                )
            )
            dashboard_body = driver.find_element(By.TAG_NAME, "body").text
            visible["dashboard"] = {
                "url": driver.current_url,
                "has_event": "功夫女足" in dashboard_body,
                "has_summary": str(detail.get("summary") or "")[:20]
                in dashboard_body,
                "body_excerpt": dashboard_body[:3000],
            }
            _save_full_page_screenshot(driver, artifact_dir / names["dashboard"])

            driver.get(f"{base_url}/#/events/{int(event_id)}")
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), str(detail.get("title") or "功夫女足")
                )
            )
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "body"), "多维舆情画像"
                )
            )
            detail_body = driver.find_element(By.TAG_NAME, "body").text
            dom = driver.page_source
            visible["detail"] = {
                "url": driver.current_url,
                "title": detail.get("title"),
                "article_total": (detail.get("articles") or {}).get("total"),
                "lifecycle_stage": detail.get("lifecycle_stage"),
                "risk": (detail.get("report") or {}).get("risk_data"),
                "section_checks": {
                    section: section in detail_body
                    for section in (
                        "舆情传播趋势与情感变化",
                        "情感极性占比",
                        "传播平台分布",
                        "多维舆情画像",
                        "AI 研判与核心摘要",
                        "热点关键词云",
                        "关联舆情报道列表",
                    )
                },
                "body_excerpt": detail_body[:5000],
            }
            (artifact_dir / "15_frontend_dom.html").write_text(
                dom, encoding="utf-8"
            )
            _save_full_page_screenshot(driver, artifact_dir / names["detail"])
            visible["detail"]["middle_scroll"] = driver.execute_script(
                """
                const candidates = Array.from(document.querySelectorAll('.el-scrollbar__wrap'))
                  .sort((a, b) => b.scrollHeight - a.scrollHeight);
                const target = candidates[0];
                if (!target) return {found: false};
                target.scrollTop = Math.floor((target.scrollHeight - target.clientHeight) / 2);
                return {
                  found: true,
                  scrollTop: target.scrollTop,
                  scrollHeight: target.scrollHeight,
                  clientHeight: target.clientHeight
                };
                """
            )
            time.sleep(1)
            driver.save_screenshot(str(artifact_dir / names["detail_middle"]))
            visible["detail"]["lower_scroll"] = driver.execute_script(
                """
                const candidates = Array.from(document.querySelectorAll('.el-scrollbar__wrap'))
                  .sort((a, b) => b.scrollHeight - a.scrollHeight);
                const target = candidates[0];
                if (!target) return {found: false};
                target.scrollTop = target.scrollHeight;
                return {
                  found: true,
                  scrollTop: target.scrollTop,
                  scrollHeight: target.scrollHeight,
                  clientHeight: target.clientHeight
                };
                """
            )
            time.sleep(1)
            driver.save_screenshot(str(artifact_dir / names["detail_lower"]))
            console = safe_artifact(driver.get_log("browser"), secrets)
        finally:
            driver.quit()

    assessment = assess_frontend_data_quality(detail, propagation, detail_body)
    console_issues = browser_console_issues(console)
    visible["console_issues"] = console_issues
    frontend_checks = {
        "analysis_keyword_visible": visible["analysis"]["has_keyword"],
        "analysis_history_visible": visible["analysis"]["has_history"],
        "analysis_success_visible": visible["analysis"]["has_success_state"],
        "dashboard_event_visible": visible["dashboard"]["has_event"],
        "dashboard_summary_visible": visible["dashboard"]["has_summary"],
        "detail_sections_visible": all(
            visible["detail"]["section_checks"].values()
        ),
        "browser_console_clean": not console_issues,
    }
    failed_frontend = [key for key, value in frontend_checks.items() if not value]
    assessment["frontend_checks"] = frontend_checks
    assessment["failed_frontend_checks"] = failed_frontend
    assessment["passed"] = assessment["passed"] and not failed_frontend
    _write_json(
        artifact_dir / "16_browser_console.json", console, secrets=secrets
    )
    _write_json(
        artifact_dir / "17_frontend_visible_state.json", visible, secrets=secrets
    )
    _write_json(
        artifact_dir / "18_quality_assessment.json", assessment, secrets=secrets
    )
    return assessment


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
    parser.add_argument(
        "--reuse-database",
        action="store_true",
        help="Reuse the existing isolated E2E database and refresh published outputs",
    )
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
    if args.reuse_database and not database_path.exists():
        raise SystemExit(f"E2E database does not exist: {database_path}")
    if database_path.exists() and not args.reuse_database:
        database_path.unlink()
    if not _port_is_free("127.0.0.1", 5000):
        raise SystemExit("port 5000 is already in use")
    if not args.skip_browser and not _port_is_free("127.0.0.1", 8848):
        raise SystemExit("port 8848 is already in use")

    from dotenv import load_dotenv

    load_dotenv((root / args.env_file).resolve(), override=True)
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.core.config import Config
    from tools.validate_backend_live import configured_secrets

    platforms = args.platform or ["baidu", "weibo", "zhihu", "bilibili"]
    secrets = configured_secrets(Config)
    existing_ids = {}
    if args.reuse_database and (artifact_dir / "00_manifest.json").exists():
        existing_ids = (_read_json(artifact_dir / "00_manifest.json").get("ids") or {})
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
        "reused_database": bool(args.reuse_database),
        "backend": {"status": "starting"},
        "frontend": {"status": "skipped" if args.skip_browser else "pending"},
    }
    if existing_ids:
        manifest["ids"] = existing_ids
    _write_json(artifact_dir / "00_manifest.json", manifest, secrets=secrets)

    backend_process = None
    backend_log = None
    frontend_process = None
    frontend_log = None
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
        if args.reuse_database:
            cycle = refresh_existing_cycle(
                api=api,
                artifact_dir=artifact_dir,
                username=Config.DEMO_ADMIN_USERNAME,
                password=Config.DEMO_ADMIN_PASSWORD,
                secrets=secrets,
            )
        else:
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
        if not args.skip_browser:
            frontend_process, frontend_log = _start_process(
                [
                    shutil.which("node.exe") or shutil.which("node") or "node",
                    str(root / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8848",
                    "--strictPort",
                ],
                cwd=root / "frontend",
                env=dict(os.environ),
                log_path=runtime_dir / "frontend.log",
            )
            _wait_http("http://127.0.0.1:8848", timeout_seconds=120)
            manifest["frontend"] = {"status": "ready", "port": 8848}
            assessment = run_browser_cycle(
                base_url="http://127.0.0.1:8848",
                keyword=args.keyword,
                event_id=cycle["event_id"],
                task_id=cycle["task_id"],
                username=Config.DEMO_ADMIN_USERNAME,
                password=Config.DEMO_ADMIN_PASSWORD,
                artifact_dir=artifact_dir,
                detail=cycle["detail"],
                propagation=cycle["propagation"],
                secrets=cycle["secrets"],
            )
            manifest["frontend"] = {
                "status": "success" if assessment["passed"] else "quality_failed",
                "port": 8848,
            }
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(
            artifact_dir / "00_manifest.json",
            manifest,
            secrets=cycle["secrets"],
        )
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
        _stop_process(frontend_process, frontend_log)
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
    normalized_dom = _text(dom_text)

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
    low_volume = bool((detail.get("lifecycle_evidence") or {}).get("low_volume"))
    rule(
        "LIFECYCLE_LIMITATION_VISIBLE",
        not low_volume or "样本量有限" in normalized_dom,
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
        (
            "风险评估" in normalized_dom
            or "舆情画像" in normalized_dom
            or "风险" not in normalized_dom
        ),
    )

    coverage = str(propagation.get("coverage_status") or "")
    limitation_visible = (
        "传播证据不足" in normalized_dom
        and "不代表已验证传播路径" in normalized_dom
    )
    rule(
        "PROPAGATION_LIMITATION_EXPLAINED",
        coverage != "insufficient" or (bool(limitations) and limitation_visible),
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


def browser_artifact_names(keyword: str, *, event_id: int) -> dict[str, str]:
    slug = safe_slug(keyword, event_id=event_id)
    return {
        "analysis": f"15_{slug}_analysis.png",
        "dashboard": f"15_{slug}_dashboard.png",
        "detail": f"15_{slug}_detail.png",
        "detail_middle": f"15_{slug}_detail_middle.png",
        "detail_lower": f"15_{slug}_detail_lower.png",
    }


def browser_console_issues(entries: list[dict] | None) -> list[dict]:
    return [
        item
        for item in (entries or [])
        if str(item.get("level") or "").upper() in {"WARNING", "SEVERE"}
        and not (
            "data-insp-path" in str(item.get("message") or "")
            and "Extraneous non-props attributes"
            in str(item.get("message") or "")
        )
    ]


__all__ = [
    "assess_frontend_data_quality",
    "build_backend_environment",
    "build_search_payload",
    "browser_artifact_names",
    "browser_console_issues",
    "choose_relevant_cluster",
    "export_database_stages",
    "run_api_cycle",
    "safe_artifact",
    "safe_slug",
    "summarize_task",
]


if __name__ == "__main__":
    raise SystemExit(main())
