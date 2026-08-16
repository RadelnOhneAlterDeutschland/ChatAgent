"""Deterministic bag-of-words embedder.

Not a random stub: texts sharing words get similar vectors, so retrieval ordering in the
fake reflects the ordering the real embedder would produce for obvious cases.
"""

import hashlib
from collections.abc import Sequence

from app.ingestion.ports import EMBEDDING_DIMENSION


class FakeEmbedder:
    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension
        self.batch_sizes: list[int] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.batch_sizes.append(len(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return vector
