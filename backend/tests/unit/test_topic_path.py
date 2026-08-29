"""Inner loop: `topic_path_for` derives a citation-friendly topic/category path from a
document's absolute `source_path` (plan.md Phase 8)."""

from app.ingestion.topic_path import topic_path_for


def test_source_path_under_a_root_returns_its_folder_portion() -> None:
    result = topic_path_for(
        "/watched/05 Finanzierung & Fundraising/Foerderantraege/grant.pdf", ["/watched"]
    )

    assert result == "05 Finanzierung & Fundraising/Foerderantraege"


def test_source_path_directly_in_the_root_returns_none() -> None:
    result = topic_path_for("/watched/grant.pdf", ["/watched"])

    assert result is None


def test_none_source_path_returns_none() -> None:
    assert topic_path_for(None, ["/watched"]) is None


def test_source_path_outside_every_configured_root_returns_none() -> None:
    result = topic_path_for("/elsewhere/grant.pdf", ["/watched"])

    assert result is None


def test_matches_the_first_root_the_path_falls_under() -> None:
    result = topic_path_for("/second-root/topic/grant.pdf", ["/first-root", "/second-root"])

    assert result == "topic"
