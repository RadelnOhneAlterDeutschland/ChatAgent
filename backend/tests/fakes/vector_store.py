"""In-memory VectorStore with real cosine ranking, so retrieval assertions mean something.

Kept honest by tests/contract/test_vector_store_contract.py.
"""

import math
from collections.abc import Sequence

from app.ingestion.ports import Match, VectorRecord


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class FakeVectorStore:
    def __init__(self) -> None:
        # namespace -> vector id -> record
        self.namespaces: dict[str, dict[str, VectorRecord]] = {}
        self.upsert_batch_sizes: list[int] = []

    def upsert(self, records: Sequence[VectorRecord], namespace: str) -> None:
        self.upsert_batch_sizes.append(len(records))
        bucket = self.namespaces.setdefault(namespace, {})
        for record in records:
            bucket[record.id] = record

    def query(self, vector: Sequence[float], top_k: int, namespace: str) -> list[Match]:
        bucket = self.namespaces.get(namespace, {})
        scored = [
            Match(id=record.id, score=_cosine(vector, record.values), metadata=record.metadata)
            for record in bucket.values()
        ]
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:top_k]

    def delete(self, ids: Sequence[str], namespace: str) -> None:
        bucket = self.namespaces.get(namespace, {})
        for vector_id in ids:
            bucket.pop(vector_id, None)
