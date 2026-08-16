"""Pinecone-backed `VectorStore` (implementation.md §4, §5). Real adapter.

Exercised by `tests/contract/test_port_contracts.py::TestVectorStoreContract` against a
live index, marked `@pytest.mark.integration` — excluded by default.
"""

from collections.abc import Sequence

from pinecone import Pinecone

from app.ingestion.ports import Match, VectorRecord


class PineconeVectorStore:
    def __init__(self, api_key: str, index_name: str) -> None:
        self._index = Pinecone(api_key=api_key).Index(index_name)

    def upsert(self, records: Sequence[VectorRecord], namespace: str) -> None:
        self._index.upsert(
            vectors=[
                {"id": record.id, "values": record.values, "metadata": record.metadata}
                for record in records
            ],
            namespace=namespace,
        )

    def query(self, vector: Sequence[float], top_k: int, namespace: str) -> list[Match]:
        response = self._index.query(
            vector=list(vector), top_k=top_k, namespace=namespace, include_metadata=True
        )
        return [
            Match(id=match["id"], score=match["score"], metadata=dict(match.get("metadata") or {}))
            for match in response["matches"]
        ]

    def delete(self, ids: Sequence[str], namespace: str) -> None:
        if not ids:
            return
        self._index.delete(ids=list(ids), namespace=namespace)
