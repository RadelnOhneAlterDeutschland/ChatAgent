"""One contract per port, run against the fake and against the real adapter.

The real-adapter runs are marked `integration` and excluded by default, so the fakes cannot
silently drift from the services they stand in for.
"""

import uuid

import pytest

from app.ingestion.ports import BlobNotFoundError, VectorRecord
from tests.fakes import FakeBlobStore, FakeVectorStore


def _real_blob_store():
    from app.core.config import get_settings
    from app.ingestion.blob_store import S3BlobStore

    settings = get_settings()
    return S3BlobStore(bucket=settings.s3_bucket_name, region=settings.aws_region)


def _real_vector_store():
    from app.core.config import get_settings
    from app.ingestion.vector_store import PineconeVectorStore

    settings = get_settings()
    return PineconeVectorStore(
        api_key=settings.pinecone_api_key, index_name=settings.pinecone_index_name
    )


@pytest.fixture(
    params=[
        pytest.param(FakeBlobStore, id="fake"),
        pytest.param(_real_blob_store, id="s3", marks=pytest.mark.integration),
    ]
)
def blob_store(request):
    return request.param()


@pytest.fixture(
    params=[
        pytest.param(FakeVectorStore, id="fake"),
        pytest.param(_real_vector_store, id="pinecone", marks=pytest.mark.integration),
    ]
)
def vector_store(request):
    return request.param()


@pytest.fixture
def key() -> str:
    return f"contract-test/{uuid.uuid4()}.pdf"


class TestBlobStoreContract:
    def test_what_was_put_can_be_read_back_byte_for_byte(self, blob_store, key: str) -> None:
        blob_store.put(key, b"%PDF-1.7 payload", "application/pdf")

        assert blob_store.get(key) == b"%PDF-1.7 payload"

        blob_store.delete(key)

    def test_reading_a_missing_key_raises_a_domain_error(self, blob_store) -> None:
        with pytest.raises(BlobNotFoundError):
            blob_store.get(f"contract-test/absent-{uuid.uuid4()}")

    def test_a_deleted_key_is_gone(self, blob_store, key: str) -> None:
        blob_store.put(key, b"payload", "application/pdf")
        blob_store.delete(key)

        with pytest.raises(BlobNotFoundError):
            blob_store.get(key)

    def test_deleting_a_missing_key_is_not_an_error(self, blob_store) -> None:
        blob_store.delete(f"contract-test/absent-{uuid.uuid4()}")


class TestVectorStoreContract:
    @pytest.fixture
    def namespace(self) -> str:
        return f"contract-test-{uuid.uuid4()}"

    @staticmethod
    def _record(vector_id: str, values: list[float], page: int = 1) -> VectorRecord:
        return VectorRecord(
            id=vector_id,
            values=values,
            metadata={"document_id": "doc-1", "page": page, "chunk_index": 0, "owner_id": "u-1"},
        )

    def test_an_upserted_vector_is_returned_by_a_query_for_itself(
        self, vector_store, namespace: str
    ) -> None:
        values = [1.0, 0.0, 0.0]
        vector_store.upsert([self._record("v1", values)], namespace)

        matches = vector_store.query(values, top_k=1, namespace=namespace)

        assert [match.id for match in matches] == ["v1"]

        vector_store.delete(["v1"], namespace)

    def test_query_returns_the_nearest_vector_first(self, vector_store, namespace: str) -> None:
        vector_store.upsert(
            [self._record("near", [1.0, 0.1, 0.0]), self._record("far", [0.0, 0.0, 1.0])],
            namespace,
        )

        matches = vector_store.query([1.0, 0.0, 0.0], top_k=2, namespace=namespace)

        assert matches[0].id == "near"

        vector_store.delete(["near", "far"], namespace)

    def test_query_honours_top_k(self, vector_store, namespace: str) -> None:
        vector_store.upsert(
            [self._record(f"v{i}", [1.0, float(i) / 10, 0.0]) for i in range(5)], namespace
        )

        matches = vector_store.query([1.0, 0.0, 0.0], top_k=2, namespace=namespace)

        assert len(matches) == 2

        vector_store.delete([f"v{i}" for i in range(5)], namespace)

    def test_metadata_survives_the_round_trip(self, vector_store, namespace: str) -> None:
        vector_store.upsert([self._record("v1", [1.0, 0.0, 0.0], page=7)], namespace)

        match = vector_store.query([1.0, 0.0, 0.0], top_k=1, namespace=namespace)[0]

        assert match.metadata["page"] == 7

        vector_store.delete(["v1"], namespace)

    def test_a_namespace_cannot_see_another_namespace_vectors(
        self, vector_store, namespace: str
    ) -> None:
        vector_store.upsert([self._record("mine", [1.0, 0.0, 0.0])], f"{namespace}-a")

        matches = vector_store.query([1.0, 0.0, 0.0], top_k=5, namespace=f"{namespace}-b")

        assert matches == []

        vector_store.delete(["mine"], f"{namespace}-a")

    def test_a_deleted_vector_stops_being_returned(self, vector_store, namespace: str) -> None:
        vector_store.upsert([self._record("v1", [1.0, 0.0, 0.0])], namespace)

        vector_store.delete(["v1"], namespace)

        assert vector_store.query([1.0, 0.0, 0.0], top_k=1, namespace=namespace) == []

    def test_querying_an_unknown_namespace_returns_nothing(self, vector_store) -> None:
        matches = vector_store.query([1.0, 0.0, 0.0], top_k=5, namespace=f"absent-{uuid.uuid4()}")

        assert matches == []
