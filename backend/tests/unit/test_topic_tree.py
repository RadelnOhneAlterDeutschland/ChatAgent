"""Inner loop: `discover_topic_tree` walks the live folder taxonomy for the smart intake
flow (plan.md Phase 8)."""

from pathlib import Path

from app.ingestion.topic_tree import discover_topic_tree


def test_no_configured_folders_returns_no_topics() -> None:
    assert discover_topic_tree([]) == []


def test_a_root_that_does_not_exist_yet_is_skipped(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert discover_topic_tree([str(missing)]) == []


def test_files_directly_in_the_root_are_not_topics(tmp_path: Path) -> None:
    (tmp_path / "loose.pdf").write_bytes(b"x")

    assert discover_topic_tree([str(tmp_path)]) == []


def test_each_top_level_subdirectory_is_a_topic(tmp_path: Path) -> None:
    (tmp_path / "05 Finanzierung").mkdir()
    (tmp_path / "09 Rechtliches").mkdir()

    topics = discover_topic_tree([str(tmp_path)])

    assert {topic.name for topic in topics} == {"05 Finanzierung", "09 Rechtliches"}


def test_a_topic_lists_its_own_subfolders_as_categories(tmp_path: Path) -> None:
    topic_dir = tmp_path / "05 Finanzierung"
    topic_dir.mkdir()
    (topic_dir / "Foerderantraege").mkdir()
    (topic_dir / "Spendenbescheinigungen").mkdir()
    (topic_dir / "some-file.pdf").write_bytes(b"x")  # not a category

    topics = discover_topic_tree([str(tmp_path)])

    assert topics[0].subfolders == ["Foerderantraege", "Spendenbescheinigungen"]


def test_a_topic_with_no_subfolders_yet_has_an_empty_list(tmp_path: Path) -> None:
    (tmp_path / "10 Verschiedenes").mkdir()

    topics = discover_topic_tree([str(tmp_path)])

    assert topics[0].subfolders == []


def test_topics_across_multiple_roots_are_all_included(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    (root_a / "Topic A").mkdir(parents=True)
    (root_b / "Topic B").mkdir(parents=True)

    topics = discover_topic_tree([str(root_a), str(root_b)])

    assert {topic.name for topic in topics} == {"Topic A", "Topic B"}
