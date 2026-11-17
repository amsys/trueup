"""Unit tests for the design id about the design target shape."""

import shutil
from pathlib import Path

from tests.refs.conftest import _excuse_tree

from trueup.ref_check import run

FIXTURES = Path(__file__).parent / "fixtures" / "design_target"


def _copy_case(case: str, dest: Path) -> Path:
    """Copy a fixture tree of this file, dropping the `.txt` suffix (D1.6).

    Args:
        case: The name of the directory under `fixtures/design_target/`.
        dest: The directory to copy the tree into.

    Returns:
        `dest`, with every file of the case copied and renamed.
    """
    source = FIXTURES / case
    for item in source.rglob("*.txt"):
        target = dest / item.relative_to(source).with_suffix("")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
    return dest


def test_declared_ids_claims_and_open_rows(tmp_path):
    """The declared ids, the claims, and the open rows of a given text (D2.8).

    arch: D2.8
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## D1.2 — a heading id\n\n"
        "- **I-1 A list id.** Some text.\n\n"
        "## Verification\n\n"
        "D1.2 is proved by a test. I-1 is claimed but has no test yet.\n",
        encoding="utf-8",
    )
    (tmp_path / "PLAN.md").write_text(
        "| T1 | open | still working on I-1 |\n",
        encoding="utf-8",
    )
    source = tmp_path / "test_sample.py"
    source.write_text(
        "def test_proved():\n"
        '    """A proof of the heading id.\n\n'
        "    arch: D1.2\n"
        '    """\n',
        encoding="utf-8",
    )
    report = run(tmp_path)
    kinds_and_details = {(failure.kind, failure.detail) for failure in report.failures}
    assert ("unproved", "claimed in ## Verification, proved by no test: D1.2") not in (
        kinds_and_details
    )
    assert not any(
        kind == "unproved" and "I-1" in detail for kind, detail in kinds_and_details
    )


def test_check_b_reports_the_unmarked_test_of_a_marked_file(tmp_path):
    """One marked test excuses no sibling test of the same file (D2.8, check b).

    arch: D2.8
    """
    _copy_case("check_b", tmp_path)
    report = run(tmp_path)
    unmarked = {
        failure.detail for failure in report.failures if failure.kind == "unmarked"
    }
    assert "test_unmarked" in unmarked
    assert "test_marked" not in unmarked


def test_check_c_reports_a_verification_claim_with_no_test(tmp_path):
    """A claim under `## Verification` with no citing test is `unproved` (D2.8, check c).

    arch: D2.8
    """
    _copy_case("check_c", tmp_path)
    report = run(tmp_path)
    failure = next(f for f in report.failures if f.kind == "unproved")
    assert failure.path == "docs/ARCHITECTURE.md"
    assert failure.detail == "claimed in ## Verification, proved by no test: D3.1"


def _unreadable_design(root: Path, cite: bool) -> Path:
    """Give a root whose design page cannot be read, with or without a citing test.

    Args:
        root: The directory to fill.
        cite: True to add a test file that cites the claimed id.

    Returns:
        The design file. The caller restores its mode.
    """
    docs = root / "docs"
    docs.mkdir(parents=True)
    design = docs / "ARCHITECTURE.md"
    design.write_text("## D1.1 — Gate\n\n## Verification\n\n- D1.1\n", encoding="utf-8")
    if cite:
        tests = root / "tests"
        tests.mkdir()
        body = (
            "def test_gate():\n    " + '"""Gate.\n\n    ' + "arch" + ': D1.1\n    """\n'
        )
        (tests / "test_gate.py").write_text(body, encoding="utf-8")
    design.chmod(0)
    return design


def test_an_unreadable_design_gives_one_unreadable_failure(tmp_path):
    """A design page that cannot be read gives one `unreadable` line and no false id line (D2.8, I-4).

    arch: D2.8, I-4
    """
    from trueup.ref_check import Failure

    expected = [
        Failure(
            "docs/ARCHITECTURE.md",
            1,
            "unreadable",
            "file cannot be read: PermissionError",
        )
    ]
    for cite in (False, True):
        root = tmp_path / f"cite-{cite}"
        design = _unreadable_design(root, cite)
        try:
            report = run(root)
        finally:
            design.chmod(0o644)
        assert report.failures == expected
        assert [edge.status for edge in report.edges] == (
            ["unreadable"] if cite else []
        )


def test_the_verification_heading_is_case_sensitive(tmp_path):
    """Only the exact line `## Verification` opens the claims, as D2.8 writes it (D2.8).

    D2.8 names the line and says nothing about case. The match stays exact.

    arch: D2.8
    """
    from trueup.ref_check import _read_text, _verification_claims

    design = tmp_path / "ARCHITECTURE.md"
    design.write_text("## verification\n\n- D1.1\n", encoding="utf-8")
    assert _verification_claims(design) == []
    design.write_text("## Verification\n\n- D1.1\n", encoding="utf-8")
    _read_text.cache_clear()  # A new run reads the design again (D4.1).
    assert _verification_claims(design) == [("D1.1", 3)]


def test_a_design_that_is_not_utf8_gives_one_unreadable_failure(tmp_path):
    """A design page that does not decode gives one `unreadable` line (D2.8, I-4).

    arch: D2.8, I-4
    """
    from trueup.ref_check import Failure

    root = tmp_path / "root"
    _unreadable_design(root, cite=True).chmod(0o644)
    (root / "docs" / "ARCHITECTURE.md").write_bytes(b"## D1.1 \xff\n")
    report = run(root)
    assert report.failures == [
        Failure(
            "docs/ARCHITECTURE.md",
            1,
            "unreadable",
            "file cannot be read: UnicodeDecodeError",
        )
    ]


def test_the_report_carries_the_excused_ids(tmp_path):
    """An open row excuses an unproved claim, and the report names it.

    arch: D2.3, D2.8
    """
    report = run(_excuse_tree(tmp_path, cite=False))
    assert report.failures == []
    assert report.excused == ["D1.1"]


def test_an_id_that_a_test_cites_is_not_excused(tmp_path):
    """A claim that a test cites is proved, also when an open row names it.

    arch: D2.3, D2.8
    """
    report = run(_excuse_tree(tmp_path, cite=True))
    assert report.failures == []
    assert report.excused == []


def test_the_excused_ids_are_sorted_as_text(tmp_path):
    """The report gives the excused ids in text order, one time each.

    arch: D2.3, D2.8
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## Verification\n\n- I-1\n- D2.1\n- D10.1\n- D2.1\n", encoding="utf-8"
    )
    (tmp_path / "PLAN.md").write_text(
        "| T1 | I-1 D2.1 D10.1 | open |\n", encoding="utf-8"
    )
    assert run(tmp_path).excused == ["D10.1", "D2.1", "I-1"]
