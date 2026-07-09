from __future__ import annotations

import re


def extract_main_text(raw_content: str) -> str:
    """Temporary HTML stripping fallback before readability/newspaper3k integration."""
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw_content or "", flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
