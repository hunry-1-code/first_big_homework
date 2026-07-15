from __future__ import annotations

import json
import re

from app.llm.client import LLMClient, LLMUnavailableError


def _client_from_config():
    from flask import current_app

    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=current_app.config.get("LLM_REQUEST_TIMEOUT", 30),
    )


def _parse(content: str) -> dict:
    value = str(content or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fenced:
        value = fenced.group(1).strip()
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    risks = payload.get("risks") or []
    if not isinstance(risks, list):
        raise ValueError("risks must be a list")
    return {
        "trend_explanation": str(payload.get("trend_explanation") or "").strip()[:1000],
        "next_stage_reason": str(payload.get("next_stage_reason") or "").strip()[:500],
        "risks": [str(item).strip()[:200] for item in risks[:8] if str(item).strip()],
    }


def explain_lifecycle(
    *,
    event_title: str,
    stage: str,
    confidence: float,
    momentum: float,
    next_stage_hint: str,
    series: dict,
    client=None,
) -> dict:
    result = {
        "status": "unavailable",
        "model": None,
        "rule_stage": stage,
        "trend_explanation": "",
        "next_stage_reason": "",
        "risks": [],
    }
    try:
        selected_client = client or _client_from_config()
        evidence = {
            "event_title": str(event_title or "")[:200],
            "rule_stage": stage,
            "confidence": float(confidence),
            "momentum": float(momentum),
            "next_stage_hint": next_stage_hint,
            "series": {
                key: list(value)[-14:]
                for key, value in (series or {}).items()
                if key in {"dates", "articles", "comments", "sentiment_polarity", "platforms"}
            },
        }
        response = selected_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是舆情趋势解释助手。只能解释输入的时间序列和规则结果，"
                        "不能联网补充事实，也不能更改 rule_stage。只输出 JSON："
                        '{"trend_explanation":"...","next_stage_reason":"...","risks":["样本限制"]}。'
                    ),
                },
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=700,
        )
        result.update(_parse(response.get("content", "")))
        result["status"] = "success"
        result["model"] = response.get("model") or getattr(selected_client, "model_name", None)
    except LLMUnavailableError as exc:
        result["error"] = str(exc)[:240]
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result["status"] = "invalid"
        result["error"] = str(exc)[:240]
    except Exception as exc:
        result["error"] = str(exc)[:240]
    return result


__all__ = ["explain_lifecycle"]
