from __future__ import annotations

import requests


class DoubaoUnavailableError(RuntimeError):
    pass


class DoubaoClient:
    """火山方舟 Responses API 客户端，仅承载豆包 Web Search 溯源。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model_name: str = "doubao-seed-2-1-pro-260628",
        *,
        timeout: int = 60,
        session=None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = max(1, int(timeout))
        self.session = session or requests.Session()

    def web_search(self, query: str, *, limit: int = 10) -> dict:
        if not self.api_key:
            raise DoubaoUnavailableError("DOUBAO_ARK_API_KEY 未配置")
        if not self.base_url:
            raise DoubaoUnavailableError("DOUBAO_ARK_BASE_URL 未配置")
        if not self.model_name:
            raise DoubaoUnavailableError("DOUBAO_ARK_MODEL 未配置")
        text = str(query or "").strip()
        if not text:
            raise ValueError("豆包联网搜索查询不能为空")

        payload = {
            "model": self.model_name,
            "input": text,
            "tools": [{"type": "web_search", "limit": min(10, max(1, int(limit)))}],
        }
        try:
            response = self.session.post(
                f"{self.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise DoubaoUnavailableError(f"豆包联网搜索请求失败: {exc}") from exc
        if int(getattr(response, "status_code", 500)) >= 400:
            message = str(getattr(response, "text", ""))[:500]
            raise DoubaoUnavailableError(
                f"豆包联网搜索返回 HTTP {response.status_code}: {message}"
            )
        try:
            raw = response.json()
        except Exception as exc:
            raise DoubaoUnavailableError("豆包联网搜索返回结构不合法") from exc

        texts: list[str] = []
        citations: list[dict] = []
        search_calls: list[dict] = []
        for item in raw.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "web_search_call":
                search_calls.append(item)
            if item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict) or content.get("type") != "output_text":
                    continue
                value = str(content.get("text") or "").strip()
                if value:
                    texts.append(value)
                for annotation in content.get("annotations") or []:
                    if not isinstance(annotation, dict) or not annotation.get("url"):
                        continue
                    citation = {
                        "url": str(annotation["url"]),
                        "title": str(annotation.get("title") or ""),
                    }
                    if citation not in citations:
                        citations.append(citation)
        return {
            "text": "\n".join(texts).strip(),
            "citations": citations,
            "search_calls": search_calls,
            "model": raw.get("model") or self.model_name,
            "raw": raw,
        }


__all__ = ["DoubaoClient", "DoubaoUnavailableError"]
