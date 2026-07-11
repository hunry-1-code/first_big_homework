from __future__ import annotations

import requests


class LLMUnavailableError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model_name: str = "",
        *,
        timeout: int = 30,
        session=None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = max(1, int(timeout))
        self.session = session or requests.Session()

    def chat(self, messages: list[dict], **kwargs) -> dict:
        if not self.api_key:
            raise LLMUnavailableError("LLM_API_KEY 未配置")
        if not self.base_url:
            raise LLMUnavailableError("LLM_BASE_URL 未配置")
        if not self.model_name:
            raise LLMUnavailableError("LLM_MODEL_NAME 未配置")
        payload = {"model": self.model_name, "messages": messages, **kwargs}
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise LLMUnavailableError(f"LLM 请求失败: {exc}") from exc
        if int(getattr(response, "status_code", 500)) >= 400:
            message = str(getattr(response, "text", ""))[:500]
            raise LLMUnavailableError(
                f"LLM 返回 HTTP {response.status_code}: {message}"
            )
        try:
            raw = response.json()
            choice = (raw.get("choices") or [])[0]
            content = (choice.get("message") or {}).get("content")
        except Exception as exc:
            raise LLMUnavailableError("LLM 返回结构不合法") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError("LLM 返回内容为空")
        return {
            "content": content.strip(),
            "model": raw.get("model") or self.model_name,
            "raw": raw,
        }
