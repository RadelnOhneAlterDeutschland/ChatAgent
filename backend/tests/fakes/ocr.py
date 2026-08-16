"""Fake Textract. Returns whatever text the test declares for a page number."""

from collections.abc import Sequence


class FakeOcrService:
    def __init__(self, page_text: dict[int, str] | None = None) -> None:
        self.page_text = page_text or {}
        self.requested_pages: list[int] = []

    def extract_text(self, data: bytes, pages: Sequence[int]) -> dict[int, str]:
        self.requested_pages.extend(pages)
        return {page: self.page_text.get(page, "") for page in pages}
