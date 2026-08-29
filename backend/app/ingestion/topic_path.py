"""Derives a human-readable topic/category path from a document's absolute
`source_path`, relative to whichever configured watch-folder root it lives under
(plan.md Phase 8). Pure function, no filesystem access — the path was already resolved
when the document was ingested.
"""

from pathlib import PurePath


def topic_path_for(source_path: str | None, folder_paths: list[str]) -> str | None:
    """`None` if `source_path` is unset, or doesn't live under any configured root (e.g. a
    document from before Phase 2b, or the roots were reconfigured since ingestion)."""
    if not source_path:
        return None

    resolved = PurePath(source_path)
    for raw_root in folder_paths:
        root = PurePath(raw_root)
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        parts = relative.parts[:-1]  # drop the filename, keep only the folder portion
        return "/".join(parts) if parts else None
    return None
