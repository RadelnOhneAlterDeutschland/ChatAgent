"""Inner loop: the recursive splitter. Pure function, no I/O.

Token counting is injected as `count_tokens` so these tests do not depend on tiktoken's
exact vocabulary. The word-count counter used here makes the arithmetic readable.
"""

import pytest

from app.ingestion.chunker import chunk_pages
from app.ingestion.ports import Page


def words(text: str) -> int:
    return len(text.split())


def make_page(number: int, text: str) -> Page:
    return Page(number=number, text=text, needs_ocr=False)


def sentence(word: str, count: int) -> str:
    return " ".join([word] * count) + "."


class TestChunkBoundaries:
    def test_a_page_under_the_target_becomes_one_chunk(self) -> None:
        pages = [make_page(1, "Revenue grew twelve percent.")]

        chunks = chunk_pages(pages, target_tokens=50, overlap_tokens=5, count_tokens=words)

        assert [chunk.text for chunk in chunks] == ["Revenue grew twelve percent."]

    def test_short_paragraphs_are_packed_together_up_to_the_target(self) -> None:
        pages = [make_page(1, "First para.\n\nSecond para.\n\nThird para.")]

        chunks = chunk_pages(pages, target_tokens=50, overlap_tokens=0, count_tokens=words)

        assert len(chunks) == 1

    def test_paragraphs_split_at_the_paragraph_boundary_when_they_exceed_the_target(self) -> None:
        pages = [make_page(1, f"{sentence('alpha', 8)}\n\n{sentence('beta', 8)}")]

        chunks = chunk_pages(pages, target_tokens=10, overlap_tokens=0, count_tokens=words)

        assert len(chunks) == 2
        assert "beta" not in chunks[0].text
        assert "alpha" not in chunks[1].text

    def test_an_oversized_paragraph_falls_back_to_sentence_boundaries(self) -> None:
        paragraph = " ".join([sentence("alpha", 6), sentence("beta", 6), sentence("gamma", 6)])
        pages = [make_page(1, paragraph)]

        chunks = chunk_pages(pages, target_tokens=8, overlap_tokens=0, count_tokens=words)

        assert len(chunks) == 3
        assert all(chunk.text.endswith(".") for chunk in chunks)

    def test_an_oversized_sentence_falls_back_to_word_boundaries(self) -> None:
        pages = [make_page(1, sentence("alpha", 20))]

        chunks = chunk_pages(pages, target_tokens=6, overlap_tokens=0, count_tokens=words)

        assert len(chunks) > 1
        assert all(words(chunk.text) <= 6 for chunk in chunks)

    @pytest.mark.parametrize("target", [5, 12, 40])
    def test_no_chunk_exceeds_the_target(self, target: int) -> None:
        paragraph = " ".join(sentence(word, 9) for word in ["alpha", "beta", "gamma", "delta"])
        pages = [make_page(1, paragraph), make_page(2, paragraph)]

        chunks = chunk_pages(pages, target_tokens=target, overlap_tokens=1, count_tokens=words)

        assert all(words(chunk.text) <= target for chunk in chunks)

    def test_reassembled_chunks_contain_every_word_of_the_source(self) -> None:
        source = " ".join(sentence(word, 7) for word in ["alpha", "beta", "gamma"])
        pages = [make_page(1, source)]

        chunks = chunk_pages(pages, target_tokens=9, overlap_tokens=0, count_tokens=words)

        assert " ".join(chunk.text for chunk in chunks).split() == source.split()


class TestOverlap:
    def test_consecutive_chunks_from_one_page_share_a_tail(self) -> None:
        pages = [make_page(1, " ".join(f"w{i}" for i in range(30)))]

        chunks = chunk_pages(pages, target_tokens=10, overlap_tokens=3, count_tokens=words)

        first_tail = chunks[0].text.split()[-3:]
        assert chunks[1].text.split()[:3] == first_tail

    def test_overlap_does_not_bleed_across_a_page_boundary(self) -> None:
        pages = [make_page(1, sentence("alpha", 20)), make_page(2, sentence("beta", 20))]

        chunks = chunk_pages(pages, target_tokens=8, overlap_tokens=3, count_tokens=words)

        page_two = [chunk for chunk in chunks if chunk.page == 2]
        assert "alpha" not in page_two[0].text

    def test_overlap_at_or_above_the_target_is_rejected(self) -> None:
        pages = [make_page(1, sentence("alpha", 20))]

        with pytest.raises(ValueError, match="overlap"):
            chunk_pages(pages, target_tokens=10, overlap_tokens=10, count_tokens=words)


class TestProvenance:
    def test_every_chunk_keeps_its_page_number(self) -> None:
        pages = [make_page(3, "Alpha text."), make_page(7, "Beta text.")]

        chunks = chunk_pages(pages, target_tokens=50, overlap_tokens=0, count_tokens=words)

        assert [chunk.page for chunk in chunks] == [3, 7]

    def test_chunk_index_is_sequential_across_the_whole_document(self) -> None:
        pages = [make_page(1, sentence("alpha", 20)), make_page(2, sentence("beta", 20))]

        chunks = chunk_pages(pages, target_tokens=8, overlap_tokens=0, count_tokens=words)

        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


class TestEmptyInput:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n\t\n"])
    def test_a_page_with_no_words_produces_no_chunks(self, text: str) -> None:
        chunks = chunk_pages(
            [make_page(1, text)], target_tokens=50, overlap_tokens=0, count_tokens=words
        )

        assert chunks == []

    def test_no_pages_produces_no_chunks(self) -> None:
        assert chunk_pages([], target_tokens=50, overlap_tokens=0, count_tokens=words) == []


class TestRealTokenCounter:
    def test_the_default_counter_keeps_chunks_within_the_target(self) -> None:
        """No injected counter — exercises the tiktoken-backed default."""
        sentence = "The quarterly revenue figure was four point two million dollars. "
        paragraph = (sentence * 60).strip()

        chunks = chunk_pages([make_page(1, paragraph)], target_tokens=100, overlap_tokens=20)

        from app.ingestion.chunker import count_tokens as real_counter

        assert len(chunks) > 1
        assert all(real_counter(chunk.text) <= 100 for chunk in chunks)
