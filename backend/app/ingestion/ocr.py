"""AWS Textract-backed `OcrService` (implementation.md §5). Real adapter.

Only the pages the parser flagged `needs_ocr` are sent here, so this renders just those
pages to images and calls synchronous `DetectDocumentText` per page — Textract's sync API
takes a single image or single-page document, and a handful of scanned pages per upload
does not warrant the async `StartDocumentTextDetection` job + polling loop. Revisit if a
corpus with many scanned pages per document shows up (plan.md's "small corpus" assumption).

No dedicated contract test — the fake (`tests/fakes/ocr.py`) is exercised directly by
`tests/integration/test_ingestion_pipeline.py`; this class is wired only in production.
"""

from collections.abc import Sequence

import boto3
import fitz

# Render at a higher DPI than the PDF default (72) so small scanned text stays legible.
_RENDER_DPI = 300


class TextractOcrService:
    def __init__(self, region: str) -> None:
        self._client = boto3.client("textract", region_name=region)

    def extract_text(self, data: bytes, pages: Sequence[int]) -> dict[int, str]:
        if not pages:
            return {}

        document = fitz.open(stream=data, filetype="pdf")
        try:
            return {page: self._extract_page(document, page) for page in pages}
        finally:
            document.close()

    def _extract_page(self, document: fitz.Document, page_number: int) -> str:
        pixmap = document[page_number - 1].get_pixmap(dpi=_RENDER_DPI)
        response = self._client.detect_document_text(Document={"Bytes": pixmap.tobytes("png")})
        lines = [
            block["Text"]
            for block in response.get("Blocks", [])
            if block.get("BlockType") == "LINE"
        ]
        return "\n".join(lines)
