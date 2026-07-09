from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text
