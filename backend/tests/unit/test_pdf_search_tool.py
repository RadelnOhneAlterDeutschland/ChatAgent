"""Inner loop: the pdf_search tool wraps `IngestionPipeline.search` per the citation
convention in `app/agent/tool.py`. `pipeline.search` itself is exercised end to end in
`tests/integration/test_ingestion_pipeline.py`; here it's stubbed out."""

import uuid

from app.agent.tools.pdf_search import make_pdf_search_tool


class StubPipeline:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.calls: list[tuple] = []

    def search(self, db, owner_id, query, top_k=5):
        self.calls.append((db, owner_id, query, top_k))
        return self.results


def test_the_tool_name_is_pdf_search() -> None:
    tool = make_pdf_search_tool(StubPipeline([]), db=None, owner_id=uuid.uuid4())

    assert tool.spec.name == "pdf_search"


def test_query_is_required_in_the_schema() -> None:
    tool = make_pdf_search_tool(StubPipeline([]), db=None, owner_id=uuid.uuid4())

    assert tool.spec.parameters["required"] == ["query"]


def test_executing_calls_pipeline_search_with_the_bound_owner_and_db() -> None:
    owner_id = uuid.uuid4()
    pipeline = StubPipeline([])
    tool = make_pdf_search_tool(pipeline, db="the-db-session", owner_id=owner_id)

    tool.execute({"query": "quarterly revenue"})

    assert pipeline.calls == [("the-db-session", owner_id, "quarterly revenue", 5)]


def test_top_k_is_passed_through_when_given() -> None:
    pipeline = StubPipeline([])
    tool = make_pdf_search_tool(pipeline, db=None, owner_id=uuid.uuid4())

    tool.execute({"query": "x", "top_k": 2})

    assert pipeline.calls[0][3] == 2


def test_the_raw_matches_are_returned_under_results() -> None:
    matches = [
        {"document_id": "d1", "filename": "revenue.pdf", "page": 1, "text": "...", "score": 0.9}
    ]
    tool = make_pdf_search_tool(StubPipeline(matches), db=None, owner_id=uuid.uuid4())

    result = tool.execute({"query": "x"})

    assert result["results"] == matches


def test_a_citation_is_derived_from_each_match() -> None:
    matches = [
        {"document_id": "d1", "filename": "revenue.pdf", "page": 1, "text": "...", "score": 0.9}
    ]
    tool = make_pdf_search_tool(StubPipeline(matches), db=None, owner_id=uuid.uuid4())

    result = tool.execute({"query": "x"})

    assert result["citations"] == [{"document_id": "d1", "filename": "revenue.pdf", "page": 1}]


def test_no_matches_means_no_citations() -> None:
    tool = make_pdf_search_tool(StubPipeline([]), db=None, owner_id=uuid.uuid4())

    result = tool.execute({"query": "x"})

    assert result["citations"] == []
    assert result["results"] == []


def test_duplicate_pages_from_different_matches_produce_one_citation() -> None:
    matches = [
        {"document_id": "d1", "filename": "revenue.pdf", "page": 1, "text": "a", "score": 0.9},
        {"document_id": "d1", "filename": "revenue.pdf", "page": 1, "text": "b", "score": 0.8},
    ]
    tool = make_pdf_search_tool(StubPipeline(matches), db=None, owner_id=uuid.uuid4())

    result = tool.execute({"query": "x"})

    assert result["citations"] == [{"document_id": "d1", "filename": "revenue.pdf", "page": 1}]
