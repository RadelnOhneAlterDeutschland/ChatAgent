"""PDF text extraction and the scanned-page heuristic (implementation.md §5).

A page whose extractable text layer is near-empty is flagged `needs_ocr` so the
pipeline can route it to Textract before chunking, instead of silently chunking
whatever scrap of text PyMuPDF found.
"""

import fitz

from app.ingestion.ports import Page

# "Near-zero extractable text" (plan.md Phase 2): a page number or watermark can leave a
# few stray characters behind without the page actually being readable.
DEFAULT_MIN_TEXT_CHARS = 20


class UnreadablePdfError(Exception):
    """The bytes handed in are not a PDF PyMuPDF can open."""


def parse_pdf(data: bytes, min_text_chars: int = DEFAULT_MIN_TEXT_CHARS) -> list[Page]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises its own exception types for bad input.
        raise UnreadablePdfError(str(exc)) from exc

    try:
        pages = []
        for index, page in enumerate(document, start=1):
            text = page.get_text()
            pages.append(
                Page(number=index, text=text, needs_ocr=len(text.strip()) < min_text_chars)
            )
        return pages
    finally:
        document.close()
