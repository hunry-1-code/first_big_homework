class CrawlerError(RuntimeError):
    def __init__(
        self,
        platform: str,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.platform = platform
        self.code = code
        self.message = message
        self.retryable = retryable


def raise_for_api_error(payload: dict, platform: str) -> None:
    code = payload.get("code", payload.get("Code"))
    if code is None:
        return
    if str(code).lower() in {"0", "200", "ok", "success"}:
        return
    message = (
        payload.get("message")
        or payload.get("Message")
        or payload.get("msg")
        or f"API returned code {code}"
    )
    raise CrawlerError(platform, f"CRAWL_API_{code}", str(message), False)


def detect_blocked_content(text: str | None) -> str | None:
    value = (text or "").lower()
    visible = " ".join(value.replace("<", " ").replace(">", " ").split())
    effective_length = len(visible)
    captcha_challenge = any(
        token in visible
        for token in (
            "请完成安全验证",
            "输入验证码",
            "完成验证码",
            "拖动滑块",
            "验证后继续",
            "captcha challenge",
        )
    )
    if captcha_challenge or (
        effective_length < 300 and any(token in visible for token in ("验证码", "安全验证", "captcha"))
    ):
        return "CRAWL_CAPTCHA"
    if effective_length < 500 and any(
        token in visible for token in ("sina visitor system", "登录后查看", "请先登录")
    ):
        return "CRAWL_LOGIN_REQUIRED"
    if effective_length < 500 and any(
        token in visible for token in ("访问异常", "访问受限", "403 forbidden")
    ):
        return "CRAWL_BLOCKED_PAGE"
    return None
