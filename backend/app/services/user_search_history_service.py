from __future__ import annotations

from app.extensions import db
from app.models import UserSearchHistory


def record_search(user_id: int, keyword: str, platforms: list[str], target_count: int) -> UserSearchHistory:
    row = UserSearchHistory(
        user_id=int(user_id),
        keyword=str(keyword).strip()[:255],
        platforms=list(dict.fromkeys(str(item).strip() for item in platforms if str(item).strip())),
        target_count=max(1, min(200, int(target_count))),
    )
    db.session.add(row)
    db.session.commit()
    return row


def list_search_history(user_id: int, *, page: int = 1, size: int = 20) -> dict:
    page = max(1, int(page)); size = max(1, min(100, int(size)))
    query = UserSearchHistory.query.filter_by(user_id=int(user_id)).order_by(UserSearchHistory.id.desc())
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return {
        "items": [
            {
                "id": row.id,
                "keyword": row.keyword,
                "platforms": row.platforms or [],
                "target_count": row.target_count,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def get_search_history(user_id: int, history_id: int) -> UserSearchHistory:
    row = db.session.get(UserSearchHistory, int(history_id))
    if row is None or row.user_id != int(user_id):
        raise KeyError("搜索记录不存在")
    return row


def delete_search_history(user_id: int, history_id: int) -> None:
    row = get_search_history(user_id, history_id)
    db.session.delete(row)
    db.session.commit()


def repeat_search_payload(user_id: int, history_id: int) -> dict:
    row = get_search_history(user_id, history_id)
    return {"keyword": row.keyword, "platforms": row.platforms or [], "target_count": row.target_count}


__all__ = ["record_search", "list_search_history", "delete_search_history", "repeat_search_payload"]
