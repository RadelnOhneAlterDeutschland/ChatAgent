"""Smart intake: stage an uploaded PDF, get an LLM placement suggestion against the live
topic tree, then only write it to disk (and ingest it) once the author confirms — the
suggestion is never auto-applied (plan.md Phase 8).
"""

import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PendingIntake:
    id: str
    filename: str
    data: bytes
    suggested_topic: str
    suggested_subfolder: str | None
    rationale: str


class IntakeStagingStore:
    """Process-local, in-memory — lost on restart. A pending intake that's never confirmed
    just sits here; nothing currently evicts it (**known simplification**, same pattern as
    other tracked gaps in this codebase — e.g. plan.md Phase 2b's deletion sync). Fine at
    this app's scale (single backend process, one author confirming shortly after
    suggesting)."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingIntake] = {}

    def add(
        self,
        filename: str,
        data: bytes,
        suggested_topic: str,
        suggested_subfolder: str | None,
        rationale: str,
    ) -> PendingIntake:
        intake = PendingIntake(
            id=str(uuid.uuid4()),
            filename=filename,
            data=data,
            suggested_topic=suggested_topic,
            suggested_subfolder=suggested_subfolder,
            rationale=rationale,
        )
        self._pending[intake.id] = intake
        return intake

    def pop(self, intake_id: str) -> PendingIntake | None:
        return self._pending.pop(intake_id, None)


def write_confirmed_intake(
    intake: PendingIntake, root: str, topic: str, subfolder: str | None
) -> Path:
    """Writes the staged bytes to `root/topic[/subfolder]/filename` — the real
    OneDrive-synced tree, so it joins the organized library exactly like a manually-filed
    document. A same-name collision is disambiguated with a numeric suffix rather than
    overwriting, the same instinct a human filing it by hand would have."""
    target_dir = Path(root) / topic
    if subfolder:
        target_dir = target_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / intake.filename
    if target_path.exists():
        stem, suffix = Path(intake.filename).stem, Path(intake.filename).suffix
        n = 1
        while target_path.exists():
            target_path = target_dir / f"{stem} ({n}){suffix}"
            n += 1

    target_path.write_bytes(intake.data)
    return target_path
