from __future__ import annotations


class LLMClient:
    def __init__(self, api_key: str = "", base_url: str = "", model_name: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    def chat(self, messages: list[dict], **kwargs) -> dict:
        return {
            "content": "LLM 客户端占位，后续按 OpenAI 兼容格式接入 DeepSeek。",
            "model": self.model_name or "stub",
            "raw": {"messages": messages, "options": kwargs},
        }
