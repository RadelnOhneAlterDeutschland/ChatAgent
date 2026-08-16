"""Recursive splitter: paragraph boundaries first, then sentence, then word (implementation.md §5).

`count_tokens` is injectable so callers (and tests) can swap in a cheap counter; the
default is a real `tiktoken` count against `text-embedding-3-small`'s encoding.

Overlap is reserved out of `target_tokens` up front (`budget = target - overlap`), so a
chunk's own content plus its prepended overlap tail never exceeds `target_tokens`.
"""

import re
from collections.abc import Callable, Sequence

import tiktoken

from app.ingestion.ports import Chunk, Page

TokenCounter = Callable[[str], int]

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

_encoding: tiktoken.Encoding | None = None


def count_tokens(text: str) -> int:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return len(_encoding.encode(text))


def chunk_pages(
    pages: Sequence[Page],
    target_tokens: int,
    overlap_tokens: int,
    count_tokens: TokenCounter = count_tokens,
) -> list[Chunk]:
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be smaller than target_tokens")

    budget = target_tokens - overlap_tokens
    chunks: list[Chunk] = []
    index = 0
    for page in pages:
        for text in _chunk_page_text(page.text, budget, overlap_tokens, count_tokens):
            chunks.append(Chunk(text=text, page=page.number, index=index))
            index += 1
    return chunks


def _chunk_page_text(
    text: str, budget: int, overlap_tokens: int, count_tokens: TokenCounter
) -> list[str]:
    paragraphs = _split(text, _PARAGRAPH_BREAK)
    if not paragraphs:
        return []

    segments = _pack(
        paragraphs,
        joiner="\n\n",
        budget=budget,
        count_tokens=count_tokens,
        oversized_fallback=lambda paragraph: _pack(
            _split(paragraph, _SENTENCE_BREAK),
            joiner=" ",
            budget=budget,
            count_tokens=count_tokens,
            oversized_fallback=lambda sentence: _pack_words(sentence, budget, count_tokens),
        ),
    )
    return _apply_overlap(segments, overlap_tokens)


def _split(text: str, boundary: re.Pattern[str]) -> list[str]:
    return [piece.strip() for piece in boundary.split(text.strip()) if piece.strip()]


def _pack(
    units: list[str],
    joiner: str,
    budget: int,
    count_tokens: TokenCounter,
    oversized_fallback: Callable[[str], list[str]],
) -> list[str]:
    """Greedily join `units` up to `budget`; a single oversized unit is recursed into."""
    segments: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            segments.append(joiner.join(buffer))
            buffer.clear()

    for unit in units:
        candidate = joiner.join([*buffer, unit])
        if count_tokens(candidate) <= budget:
            buffer.append(unit)
            continue

        flush()
        if count_tokens(unit) <= budget:
            buffer.append(unit)
        else:
            segments.extend(oversized_fallback(unit))

    flush()
    return segments


def _pack_words(text: str, budget: int, count_tokens: TokenCounter) -> list[str]:
    return _pack(
        text.split(),
        joiner=" ",
        budget=budget,
        count_tokens=count_tokens,
        # A single word is always kept as-is even if it alone exceeds budget — there is
        # no finer boundary to fall back to.
        oversized_fallback=lambda word: [word],
    )


def _apply_overlap(segments: list[str], overlap_tokens: int) -> list[str]:
    if overlap_tokens <= 0 or len(segments) <= 1:
        return segments

    result = [segments[0]]
    for segment in segments[1:]:
        previous_words = result[-1].split()
        tail = previous_words[-overlap_tokens:] if previous_words else []
        result.append(" ".join([*tail, segment]) if tail else segment)
    return result
