from __future__ import annotations

import math
from threading import RLock

from app.analysis.result import EmbeddingUnavailableError


def normalize_vector(vector) -> list[float]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        raise EmbeddingUnavailableError("嵌入模型返回零向量")
    return [value / norm for value in values]


class BGEEncoder:
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        model_version: str = "default",
        preprocess_version: str = "v1",
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.preprocess_version = preprocess_version
        self._model = None
        self._lock = RLock()

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                raise EmbeddingUnavailableError(str(exc)) from exc
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._load().encode(
                texts,
                batch_size=min(32, max(1, len(texts))),
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return [normalize_vector(vector) for vector in vectors]
        except EmbeddingUnavailableError:
            raise
        except Exception as exc:
            raise EmbeddingUnavailableError(str(exc)) from exc

