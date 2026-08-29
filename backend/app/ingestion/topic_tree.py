"""Discovers the live topic/category folder tree under the watched roots, for the smart
intake flow's placement suggestion and folder picker (plan.md Phase 8).

Walked from disk at request time rather than a static config — stays correct as the
taxonomy evolves, and matches `folder_watcher.discover_pdfs`'s tolerance for a root that
doesn't exist yet.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopicFolder:
    """One top-level topic folder (e.g. `"05 Finanzierung & Fundraising"`) and the
    categories already filed under it. The ten top-level topics stay fixed in the
    reference deployment — the intake classifier may only propose a new *subfolder*, never
    a new top-level topic (plan.md Phase 8)."""

    name: str
    subfolders: list[str]


def discover_topic_tree(folder_paths: list[str]) -> list[TopicFolder]:
    """One `TopicFolder` per immediate subdirectory of each configured root. A root that
    doesn't exist yet is skipped, not an error."""
    topics: list[TopicFolder] = []
    for raw_root in folder_paths:
        root = Path(raw_root)
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            subfolders = sorted(child.name for child in entry.iterdir() if child.is_dir())
            topics.append(TopicFolder(name=entry.name, subfolders=subfolders))
    return topics
