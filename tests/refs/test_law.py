"""Unit tests for the design id about the law archive shape."""

from pathlib import Path

from trueup.ref_check import run

FIXTURE = Path(__file__).parent / "fixtures" / "law_archive"


def _copy_fixture(tree: Path, dest: Path) -> None:
    """Copy one fixture tree to `dest`, dropping the `.txt` suffix (D1.6, I-3)."""
    for source in tree.rglob("*.txt"):
        target = dest / source.relative_to(tree).with_suffix("")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _write_root(tmp_path: Path, archive: Path, marker: str) -> Path:
    """Give a minimal root: a design file, a config naming `archive`, and one marker."""
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        f'[targets.law]\narchive = "{archive}"\n', encoding="utf-8"
    )
    source = tmp_path / "sample.py"
    source.write_text(f'"""Module.\n\n# law: {marker}\n"""\n', encoding="utf-8")
    return tmp_path


def test_section_limits_hash_normalisation_and_version_order(tmp_path):
    """Section limits, the hash normalisation, and the order of versions (D2.7).

    arch: D2.7
    """
    archive = tmp_path / "archive"
    _copy_fixture(FIXTURE, archive)

    _write_root(tmp_path, archive, "acts/Sample_Act/v2 s.1")

    report = run(tmp_path)
    kinds = {failure.kind for failure in report.failures}
    ids = {edge.id for edge in report.edges}
    assert "drift" not in kinds
    assert "acts/Sample_Act/v2/s.1" in ids


def test_missing_pinned_document_gives_unknown_id(tmp_path):
    """A `law-key` with no `document.md` fails with `unknown-id` (D2.7, step 1).

    arch: D2.7
    """
    archive = tmp_path / "archive"
    _copy_fixture(FIXTURE, archive)

    _write_root(tmp_path, archive, "acts/Sample_Act/v9 s.1")

    report = run(tmp_path)
    kinds = {failure.kind for failure in report.failures}
    assert "unknown-id" in kinds


def test_missing_section_gives_unknown_id(tmp_path):
    """A section number absent from the pinned file fails with `unknown-id` (D2.7, step 2).

    arch: D2.7
    """
    archive = tmp_path / "archive"
    _copy_fixture(FIXTURE, archive)

    _write_root(tmp_path, archive, "acts/Sample_Act/v2 s.99")

    report = run(tmp_path)
    kinds = {failure.kind for failure in report.failures}
    assert "unknown-id" in kinds


def test_first_match_rule_on_a_repeated_section_number(tmp_path):
    """The first heading that matches is the section, even when the number repeats.

    arch: D2.7
    """
    archive = tmp_path / "archive"
    doc = archive / "acts" / "Repeat_Act" / "base"
    doc.mkdir(parents=True)
    (doc / "document.md").write_text(
        "# Repeat Act\n\n"
        "### 1. Main body section\n\n"
        "Body text.\n\n"
        "### Schedule\n\n"
        "### 1. Schedule item, not a section\n\n"
        "Item text.\n",
        encoding="utf-8",
    )

    _write_root(tmp_path, archive, "acts/Repeat_Act/base s.1")

    report = run(tmp_path)
    kinds = {failure.kind for failure in report.failures}
    ids = {edge.id for edge in report.edges}
    assert "unknown-id" not in kinds
    assert "acts/Repeat_Act/base/s.1" in ids


def test_a_newest_document_that_cannot_be_read_gives_unreadable(tmp_path):
    """Check d gives `unreadable` at the reference when the newest document cannot be read (D4.2, I-4).

    arch: D4.2, I-4
    """
    from trueup.ref_check import Failure

    archive = tmp_path / "archive"
    _copy_fixture(FIXTURE, archive)
    _write_root(tmp_path, archive, "acts/Sample_Act/base s.1")
    newest = archive / "acts" / "Sample_Act" / "v2" / "document.md"
    newest.chmod(0)
    try:
        report = run(tmp_path)
    finally:
        newest.chmod(0o644)
    assert report.failures == [
        Failure("sample.py", 3, "unreadable", "file cannot be read: PermissionError")
    ]


def test_a_version_listing_that_cannot_be_read_gives_unreadable(tmp_path):
    """Check d gives `unreadable` when the version directories cannot be listed (D4.2, I-4).

    arch: D4.2, I-4
    """
    from trueup.ref_check import Failure

    archive = tmp_path / "archive"
    _copy_fixture(FIXTURE, archive)
    root = tmp_path / "root"
    root.mkdir()
    _write_root(root, archive, "acts/Sample_Act/base s.1")
    slug = archive / "acts" / "Sample_Act"
    slug.chmod(0o311)
    try:
        report = run(root)
    finally:
        slug.chmod(0o755)
    assert report.failures == [
        Failure("sample.py", 3, "unreadable", "file cannot be read: PermissionError")
    ]


def test_an_unreadable_pinned_document_gives_unreadable_at_the_reference(tmp_path):
    """A pinned document that cannot be read gives `unreadable`, not `unknown-id` (D2.7).

    arch: D2.7
    """
    from trueup.ref_check import Failure

    archive = tmp_path / "archive"
    doc = archive / "acts" / "Broken_Act" / "base"
    doc.mkdir(parents=True)
    (doc / "document.md").write_bytes(b"### 1. Body\n\n\xff\n")

    _write_root(tmp_path, archive, "acts/Broken_Act/base s.1")

    report = run(tmp_path)
    assert report.failures == [
        Failure("sample.py", 3, "unreadable", "file cannot be read: UnicodeDecodeError")
    ]
