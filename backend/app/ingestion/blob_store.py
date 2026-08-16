"""S3-backed `BlobStore` (implementation.md §5, §10). Real adapter for PDF bytes.

Exercised by `tests/contract/test_port_contracts.py::TestBlobStoreContract` against a
live bucket, marked `@pytest.mark.integration` — excluded by default.
"""

import boto3
from botocore.exceptions import ClientError

from app.ingestion.ports import BlobNotFoundError


class S3BlobStore:
    def __init__(self, bucket: str, region: str) -> None:
        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise BlobNotFoundError(key) from None
            raise
        return response["Body"].read()

    def delete(self, key: str) -> None:
        # S3 DeleteObject is idempotent — a missing key is not an error (matches the
        # BlobStore contract).
        self._client.delete_object(Bucket=self._bucket, Key=key)
