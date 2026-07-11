from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


DEDUP_VERSION = "v1"


@dataclass(slots=True)
class DuplicateComparison:
    is_duplicate: bool
    method: str | None = None
    score: float = 0.0
    content_hash: str | None = None
    simhash: str | None = None
    dedup_pending: bool = False


def compute_content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _features(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", (text or "").lower())
    if len(normalized) < 2:
        return [normalized] if normalized else []
    return [normalized[index : index + 2] for index in range(len(normalized) - 1)]


def title_jaccard(first: str, second: str) -> float:
    left, right = set(_features(first)), set(_features(second))
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def simhash_text(text: str) -> int:
    vector = [0] * 64
    features = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", (text or "").lower())
    for feature in features:
        digest = int(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for index in range(64):
            vector[index] += 1 if digest & (1 << index) else -1
    result = 0
    for index, value in enumerate(vector):
        if value >= 0:
            result |= 1 << index
    return result


def hamming_distance(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def compare_documents(
    first_title: str,
    first_content: str,
    second_title: str,
    second_content: str,
    jaccard_threshold: float = 0.85,
    max_hamming_distance: int = 3,
) -> DuplicateComparison:
    first_hash = compute_content_hash(first_content)
    second_hash = compute_content_hash(second_content)
    first_simhash = simhash_text(first_content)
    if first_hash == second_hash:
        return DuplicateComparison(
            True,
            "hash",
            1.0,
            first_hash,
            f"{first_simhash:016x}",
        )

    effective_title_length = min(
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", first_title or "")),
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", second_title or "")),
    )
    jaccard = title_jaccard(first_title, second_title)
    distance = hamming_distance(first_simhash, simhash_text(second_content))
    if effective_title_length < 10:
        return DuplicateComparison(
            False,
            score=round(1 - distance / 64, 4),
            content_hash=first_hash,
            simhash=f"{first_simhash:016x}",
            dedup_pending=distance <= max_hamming_distance,
        )
    if jaccard >= jaccard_threshold and distance <= max_hamming_distance:
        score = round((jaccard + (1 - distance / 64)) / 2, 4)
        return DuplicateComparison(True, "simhash", score, first_hash, f"{first_simhash:016x}")
    return DuplicateComparison(
        False,
        score=round(jaccard, 4),
        content_hash=first_hash,
        simhash=f"{first_simhash:016x}",
        dedup_pending=jaccard >= jaccard_threshold or distance <= max_hamming_distance,
    )
