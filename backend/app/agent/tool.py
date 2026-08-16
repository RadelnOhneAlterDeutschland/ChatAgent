"""A tool the orchestrator can call: its schema plus the callable that runs it.

Convention (implementation.md §7): a tool's `execute` result may include a `"citations"`
key — a list of `{document_id/table, filename/... , page/...}`-shaped dicts — which the
orchestrator collects and surfaces on the final `AgentResult` regardless of whether the
model chose to cite inline. Every future tool (`sql_query`, `flatfile_query`) follows the
same convention rather than inventing its own citation shape.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.agent.providers.base import ToolSpec


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    execute: Callable[[dict], dict]
