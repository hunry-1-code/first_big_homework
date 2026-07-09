from __future__ import annotations

import re


def segment_text(text: str) -> list[str]:
    """Fallback tokenizer; replace with jieba in the NLP implementation task."""
    return [token for token in re.split(r"\W+", text or "") if token]
