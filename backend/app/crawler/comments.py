from dataclasses import dataclass, field
from typing import Any

@dataclass
class RawComment:
    platform: str
    source_comment_id: str
    content: str
    parent_source_comment_id: str | None = None
    author: str | None = None
    likes_count: int = 0
    replies_count: int = 0
    content_kind: str = "comment"
    raw_json: dict[str, Any] = field(default_factory=dict)
