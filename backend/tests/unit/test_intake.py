"""Inner loop: staging a submitted document and writing a confirmed placement to disk
(plan.md Phase 8)."""

from pathlib import Path

from app.ingestion.intake import IntakeStagingStore, write_confirmed_intake


class TestIntakeStagingStore:
    def test_a_staged_intake_can_be_popped_back_out(self) -> None:
        store = IntakeStagingStore()
        intake = store.add(
            filename="grant.pdf",
            data=b"pdf bytes",
            suggested_topic="05 Finanzierung",
            suggested_subfolder="Foerderantraege",
            rationale="It's a grant application.",
        )

        popped = store.pop(intake.id)

        assert popped is intake
        assert popped.filename == "grant.pdf"

    def test_popping_removes_it_so_it_cannot_be_confirmed_twice(self) -> None:
        store = IntakeStagingStore()
        intake = store.add("grant.pdf", b"x", "05 Finanzierung", None, "x")

        store.pop(intake.id)

        assert store.pop(intake.id) is None

    def test_an_unknown_id_returns_none(self) -> None:
        store = IntakeStagingStore()

        assert store.pop("does-not-exist") is None

    def test_each_staged_intake_gets_a_distinct_id(self) -> None:
        store = IntakeStagingStore()
        first = store.add("a.pdf", b"x", "topic", None, "x")
        second = store.add("b.pdf", b"x", "topic", None, "x")

        assert first.id != second.id


class TestWriteConfirmedIntake:
    def _intake(self, filename: str = "grant.pdf", data: bytes = b"pdf bytes"):
        store = IntakeStagingStore()
        return store.add(filename, data, "05 Finanzierung", None, "x")

    def test_writes_the_file_under_the_chosen_topic(self, tmp_path: Path) -> None:
        intake = self._intake()

        target = write_confirmed_intake(intake, str(tmp_path), "05 Finanzierung", None)

        assert target == tmp_path / "05 Finanzierung" / "grant.pdf"
        assert target.read_bytes() == b"pdf bytes"

    def test_writes_the_file_under_the_chosen_subfolder_when_given(self, tmp_path: Path) -> None:
        intake = self._intake()

        target = write_confirmed_intake(intake, str(tmp_path), "05 Finanzierung", "Foerderantraege")

        assert target == tmp_path / "05 Finanzierung" / "Foerderantraege" / "grant.pdf"

    def test_creates_a_brand_new_subfolder_if_it_does_not_exist_yet(self, tmp_path: Path) -> None:
        intake = self._intake()

        target = write_confirmed_intake(intake, str(tmp_path), "05 Finanzierung", "Neue Kategorie")

        assert target.parent.is_dir()
        assert target.parent.name == "Neue Kategorie"

    def test_a_filename_collision_gets_a_numeric_suffix_instead_of_overwriting(
        self, tmp_path: Path
    ) -> None:
        existing_dir = tmp_path / "05 Finanzierung"
        existing_dir.mkdir()
        (existing_dir / "grant.pdf").write_bytes(b"the original file")
        intake = self._intake(data=b"a different file, same name")

        target = write_confirmed_intake(intake, str(tmp_path), "05 Finanzierung", None)

        assert target.name == "grant (1).pdf"
        assert (existing_dir / "grant.pdf").read_bytes() == b"the original file"
        assert target.read_bytes() == b"a different file, same name"
