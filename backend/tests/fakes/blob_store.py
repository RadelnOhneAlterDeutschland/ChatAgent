"""In-memory BlobStore. Kept honest by tests/contract/test_blob_store_contract.py."""

from app.ingestion.ports import BlobNotFoundError


class FakeBlobStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self.objects[key] = data
        self.content_types[key] = content_type

    def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError:
            raise BlobNotFoundError(key) from None

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.content_types.pop(key, None)
