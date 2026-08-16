"""Inner loop: PDF text extraction and the scanned-page heuristic.

Test PDFs are built with PyMuPDF at runtime — real files, no fixtures to keep in sync.
"""

import fitz
import pytest

from app.ingestion.parser import UnreadablePdfError, parse_pdf


def build_pdf(page_texts: list[str]) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    return document.tobytes()


class TestPageExtraction:
    def test_each_pdf_page_becomes_one_page_object(self) -> None:
        data = build_pdf(["First page text", "Second page text", "Third page text"])

        pages = parse_pdf(data)

        assert len(pages) == 3

    def test_page_numbers_are_one_based_to_match_what_a_reader_sees(self) -> None:
        data = build_pdf(["First page text", "Second page text"])

        pages = parse_pdf(data)

        assert [page.number for page in pages] == [1, 2]

    def test_extracted_text_is_returned_for_a_text_layer_page(self) -> None:
        data = build_pdf(["Revenue grew twelve percent"])

        pages = parse_pdf(data)

        assert "Revenue grew twelve percent" in pages[0].text


class TestScannedPageDetection:
    def test_a_page_with_no_text_layer_is_flagged_for_ocr(self) -> None:
        data = build_pdf([""])

        pages = parse_pdf(data)

        assert pages[0].needs_ocr is True

    def test_a_page_with_a_full_text_layer_is_not_flagged_for_ocr(self) -> None:
        data = build_pdf(["This page has plenty of real extractable text on it already"])

        pages = parse_pdf(data)

        assert pages[0].needs_ocr is False

    def test_a_page_with_only_a_stray_artefact_is_flagged_for_ocr(self) -> None:
        """Scanned pages often carry a page number or watermark but no real content."""
        data = build_pdf(["12"])

        pages = parse_pdf(data)

        assert pages[0].needs_ocr is True

    def test_the_ocr_threshold_is_configurable(self) -> None:
        data = build_pdf(["Short text"])

        assert parse_pdf(data, min_text_chars=5)[0].needs_ocr is False
        assert parse_pdf(data, min_text_chars=500)[0].needs_ocr is True

    def test_only_the_flagged_pages_are_reported_as_needing_ocr(self) -> None:
        data = build_pdf(["", "This page has plenty of real extractable text on it", ""])

        pages = parse_pdf(data)

        assert [page.number for page in pages if page.needs_ocr] == [1, 3]


class TestBrokenInput:
    def test_bytes_that_are_not_a_pdf_raise_a_domain_error(self) -> None:
        with pytest.raises(UnreadablePdfError):
            parse_pdf(b"this is not a pdf at all")

    def test_empty_bytes_raise_a_domain_error(self) -> None:
        with pytest.raises(UnreadablePdfError):
            parse_pdf(b"")

    def test_a_pdf_with_no_pages_yields_no_pages(self) -> None:
        # `fitz.open().tobytes()` refuses to save a zero-page document on this PyMuPDF
        # version ("cannot save with zero pages"), so build the bytes by hand instead.
        empty_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"trailer\n<</Root 1 0 R>>\n%%EOF"
        )

        assert parse_pdf(empty_pdf) == []
