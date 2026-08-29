"""The MVP's only tool (plan.md Phase 4): search the caller's own uploaded PDFs.

Wraps `IngestionPipeline.search` (built in Phase 2 ahead of this tool) rather than
re-implementing retrieval — see implementation.md §6.
"""

import uuid

from app.agent.providers.base import ToolSpec
from app.agent.tool import Tool
from app.core.config import get_settings
from app.ingestion.topic_path import topic_path_for

PDF_SEARCH_SPEC = ToolSpec(
    name="pdf_search",
    description=(
        "Search the user's own uploaded PDF documents for passages relevant to a query. "
        "Returns matching excerpts with their source filename and page number."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "top_k": {
                "type": "integer",
                "description": "How many passages to return.",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)


def make_pdf_search_tool(pipeline, db, owner_id: uuid.UUID) -> Tool:
    """`pipeline`/`db`/`owner_id` are bound per-request (implementation.md §7) — the tool
    itself only ever sees the model's `query`/`top_k` arguments."""
    folder_paths = [
        path.strip() for path in get_settings().ingestion_folder_paths.split(",") if path.strip()
    ]

    def execute(arguments: dict) -> dict:
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)
        matches = pipeline.search(db, owner_id, query, top_k=top_k)

        for match in matches:
            match["topic_path"] = topic_path_for(match.get("source_path"), folder_paths)

        citations = []
        for match in matches:
            citation = {
                "document_id": match["document_id"],
                "filename": match["filename"],
                "page": match["page"],
                "uploaded_at": match.get("uploaded_at"),
                "topic_path": match.get("topic_path"),
            }
            if citation not in citations:
                citations.append(citation)

        return {"results": matches, "citations": citations}

    return Tool(spec=PDF_SEARCH_SPEC, execute=execute)
