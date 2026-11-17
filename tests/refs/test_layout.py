"""Integration tests for check h, the document layout (D2.13)."""

import subprocess
import sys
from pathlib import Path

import pytest

from trueup import ref_check
from tests.refs.conftest import materialise
from trueup.ref_check import format_failure, load_config, main, run

REPO = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO / "trueup" / "ref_check.py"
CLEAN = ["ref_check: 0 failures, 0 references"]

EXPECTED = {
    "layout-clean": [],
    "layout-no-front-matter": [
        "docs/how-to/loose.md:1: [no-front-matter] file has no front matter",
        "docs/how-to/open.md:1: [no-front-matter] file has no front matter",
        "docs/how-to/use.md:1: [no-front-matter] file has no front matter",
    ],
    "layout-bad-field": [
        "docs/how-to/more.md:2: [bad-field] value is not allowed: id: More_Page",
        "docs/how-to/more.md:6: [bad-field] value is not allowed: last_reviewed: 2026-02-30",
        "docs/how-to/use.md:1: [bad-field] field is absent: status",
        "docs/how-to/use.md:4: [bad-field] value is not allowed: audience: [maintainer, robot]",
    ],
    "layout-misplaced": [
        "docs/loose.md:3: [misplaced] page of type explanation is not below docs/explanation/",
        "docs/reference/use.md:3: [misplaced] page of type how-to is not below docs/how-to/",
    ],
    "layout-unindexed": [
        "docs/how-to/extra.md:1: [unindexed] docs/README.md has no link to this page",
    ],
    "layout-duplicate-id": [
        "docs/how-to/use.md:2: [duplicate-id] id is also on docs/how-to/again.md: use",
    ],
}


def _check(tree: Path) -> tuple[int, list[str]]:
    """Run the checker on one tree as a child process.

    Args:
        tree: The root to examine.

    Returns:
        The exit code and the lines of standard output.
    """
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    return result.returncode, result.stdout.splitlines()


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_each_layout_tree_gives_its_failure_lines(case, tmp_path):
    """Each fixture tree gives the whole D2.4 line of its kind, and the clean tree gives none.

    arch: D2.13, D2.4
    """
    tree = materialise(case, tmp_path)
    lines = EXPECTED[case]
    summary = f"ref_check: {len(lines)} failures, 0 references"
    assert _check(tree) == (1 if lines else 0, [*lines, summary])


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_layout_absent_gives_no_check_h_failure(case, tmp_path):
    """With no `layout` switch, a tree that breaks the page rules passes (S18).

    arch: D2.5, D2.13
    """
    tree = materialise(case, tmp_path)
    (tree / "ref_check.toml").write_text("[checks]\nlinks = false\n", encoding="utf-8")
    assert _check(tree) == (0, CLEAN)


def test_a_nul_byte_in_a_link_target_does_not_crash_check_h(tmp_path):
    """A link path that holds a NUL byte after decoding does not raise while indexing (I-4, D2.13).

    arch: D2.4, D2.13
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    how_to = docs / "how-to"
    how_to.mkdir()

    # Front matter template for D2.13
    front = (
        "---\nid: {id}\ntype: {type}\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-09-22\n---\n\n"
    )

    # README with a link containing NUL byte
    # After percent-decoding, %00 becomes a NUL byte, so the link is broken
    (docs / "README.md").write_text(
        front.format(id="docs-index", type="reference") + "[x](how-to/ab%00c.md)\n",
        encoding="utf-8",
    )

    # Create the page that would be named without the NUL
    # Since the link is broken (has NUL), this page won't be indexed
    (how_to / "ab.md").write_text(
        front.format(id="ab-page", type="how-to") + "# Ab page\n", encoding="utf-8"
    )

    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\nlinks = false\n", encoding="utf-8"
    )

    assert _check(tmp_path) == (
        1,
        [
            "docs/how-to/ab.md:1: [unindexed] docs/README.md has no link to this page",
            "ref_check: 1 failures, 0 references",
        ],
    )

    # Also verify the run directly to check stderr, stdout, and exit code
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    assert (
        result.stdout
        == "docs/how-to/ab.md:1: [unindexed] docs/README.md has no link to this page\nref_check: 1 failures, 0 references\n"
    )


def test_a_symlink_loop_in_an_index_link_does_not_crash_check_h(tmp_path):
    """An index link through a symlink loop adds nothing to the index; the named page stays unindexed (I-4, D2.13).

    arch: D2.4, D2.13
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "loop.md").symlink_to(vendor / "loop.md")
    front = (
        "---\nid: {id}\ntype: {kind}\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-09-22\n---\n\n# {title}\n"
    )
    (docs / "README.md").write_text(
        front.format(id="docs-index", kind="reference", title="Index")
        + "\n[loop](../vendor/loop.md)\n",
        encoding="utf-8",
    )
    how_to = docs / "how-to"
    how_to.mkdir()
    (how_to / "extra.md").write_text(
        front.format(id="extra", kind="how-to", title="Extra"), encoding="utf-8"
    )
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n", encoding="utf-8"
    )

    assert _check(tmp_path) == (
        1,
        [
            "docs/how-to/extra.md:1: [unindexed] docs/README.md has no link to this page",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_a_page_that_does_not_decode_gives_unreadable_not_a_skip(tmp_path):
    """A docs page that does not decode fails closed with `unreadable`, not a silent skip (I-4, D2.13).

    arch: D2.4, D2.13
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "p.md").write_bytes(b"\xff")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n", encoding="utf-8"
    )

    returncode, lines = _check(tmp_path)
    assert (returncode, lines) == (
        1,
        [
            "docs/p.md:1: [unreadable] file cannot be read: UnicodeDecodeError",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_the_schema_reads_the_layout_switch(tmp_path):
    """The key `[checks] layout` is in the schema, and it is off when absent.

    arch: D2.5
    """
    assert not load_config(tmp_path).layout
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n", encoding="utf-8"
    )
    assert load_config(tmp_path).layout
    (tmp_path / "ref_check.toml").write_text("[checks]\nlayout = 1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 2


def test_the_notice_names_check_h_when_layout_is_off(tmp_path, capsys):
    """The notice gives `h` in its place, and four switches on leave only `i` off.

    arch: D2.3
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\nlinks = true\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().err == "ref_check: checks off: f, h, i\n"

    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().err == "ref_check: checks off: e, f, g, i\n"

    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\ncomments = true\nlinks = true\nlayout = true\n",
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 0 references\n"
    assert captured.err == "ref_check: checks off: i\n"


def test_the_layout_entry_point_passes_on_this_repository():
    """The pytest entry point of check h passes on this repository, which sets `layout = true`.

    arch: D2.12, D2.13
    """
    assert load_config(REPO).layout
    ref_check.test_documents_follow_the_layout()


_SWITCH_KINDS = {
    "front_matter": ("no-front-matter", "bad-field", "duplicate-id"),
    "types": ("misplaced",),
    "index": ("unindexed",),
}
"""The failure kinds of check h that each `[layout]` switch turns off (D14.5)."""


def _add_config(tree: Path, text: str) -> None:
    """Append text to the `ref_check.toml` of one tree.

    Args:
        tree: The root that holds the configuration file.
        text: The TOML text to add at the end.
    """
    config = tree / "ref_check.toml"
    old = config.read_text(encoding="utf-8") if config.exists() else ""
    config.write_text(old + text, encoding="utf-8")


@pytest.mark.parametrize("switch", sorted(_SWITCH_KINDS))
@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_a_layout_switch_off_removes_only_the_rows_of_its_rules(case, switch, tmp_path):
    """`[layout] <switch> = false` removes the rows of its rules and keeps the rows of the others (D14.5).

    arch: D14.5
    """
    tree = materialise(case, tmp_path)
    _add_config(tree, f"\n[layout]\n{switch} = false\n")
    lines = [
        line
        for line in EXPECTED[case]
        if not any(f"[{kind}]" in line for kind in _SWITCH_KINDS[switch])
    ]
    summary = f"ref_check: {len(lines)} failures, 0 references"
    assert _check(tree) == (1 if lines else 0, [*lines, summary])


def test_the_layout_master_switch_off_turns_the_five_rules_off(tmp_path):
    """`[checks] layout = false` gives no check h row, whatever `[layout]` holds (D14.5).

    arch: D14.5
    """
    tree = materialise("layout-bad-field", tmp_path)
    (tree / "ref_check.toml").write_text(
        "[checks]\nlayout = false\n\n[layout]\n"
        "front_matter = true\ntypes = true\nindex = true\n",
        encoding="utf-8",
    )
    assert _check(tree) == (0, CLEAN)


def test_front_matter_off_keeps_the_index_rule_for_a_page_with_no_front_matter(
    tmp_path,
):
    """With `front_matter = false`, a page with no front matter still gets `unindexed` (D14.5).

    arch: D14.5
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("# Index\n\n[Used](used.md)\n", encoding="utf-8")
    (docs / "used.md").write_text("# Used\n", encoding="utf-8")
    (docs / "lost.md").write_text("# Lost\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n\n[layout]\nfront_matter = false\n",
        encoding="utf-8",
    )
    assert _check(tmp_path) == (
        1,
        [
            "docs/lost.md:1: [unindexed] docs/README.md has no link to this page",
            "ref_check: 1 failures, 0 references",
        ],
    )


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_docs_dir_moves_the_pages_of_check_h(case, tmp_path):
    """With `[layout] docs_dir`, check h reads that directory and names it in each row (D14.5).

    A broken page under `docs/` is then not a page.

    arch: D14.5
    """
    tree = materialise(case, tmp_path)
    (tree / "docs").rename(tree / "handbook")
    (tree / "docs").mkdir()
    (tree / "docs" / "stray.md").write_text("no front matter\n", encoding="utf-8")
    _add_config(tree, '\n[layout]\ndocs_dir = "handbook"\n')
    lines = [line.replace("docs/", "handbook/") for line in EXPECTED[case]]
    summary = f"ref_check: {len(lines)} failures, 0 references"
    assert _check(tree) == (1 if lines else 0, [*lines, summary])


def test_docs_dir_moves_the_design_of_checks_a_and_c(tmp_path):
    """An `arch` reference and the claims of `## Verification` read `ARCHITECTURE.md` of `docs_dir` (D14.5).

    arch: D14.5
    """
    handbook = tmp_path / "handbook"
    handbook.mkdir()
    (handbook / "ARCHITECTURE.md").write_text(
        "## D1.1 — a gate\n\n## D1.2 — a door\n\n## Verification\n\n- D1.1\n- D1.2\n",
        encoding="utf-8",
    )
    (tmp_path / "test_gate.py").write_text(
        'def test_gate():\n    """Prove the gate.\n\n    arch: D1.1\n    """\n',
        encoding="utf-8",
    )
    (tmp_path / "ref_check.toml").write_text(
        '[layout]\ndocs_dir = "handbook"\n', encoding="utf-8"
    )
    report = run(tmp_path)
    assert [edge.status for edge in report.edges] == ["ok"]
    assert [format_failure(failure) for failure in report.failures] == [
        "handbook/ARCHITECTURE.md:8: [unproved] "
        "claimed in ## Verification, proved by no test: D1.2"
    ]
    (tmp_path / "ref_check.toml").unlink()
    assert [failure.kind for failure in run(tmp_path).failures] == ["no-target"]


def test_the_index_switch_and_docs_dir_drive_the_index_link_of_check_i(tmp_path):
    """Check i looks for a link to `README.md` of `docs_dir`, and `index = false` turns the rule off (D14.5).

    arch: D14.5
    """
    tree = materialise("readme-clean", tmp_path)
    _add_config(tree, '\n[layout]\ndocs_dir = "handbook"\n')
    assert _check(tree) == (
        1,
        [
            "README.md:1: [no-index-link] no link to handbook/README.md",
            "ref_check: 1 failures, 0 references",
        ],
    )
    _add_config(tree, "index = false\n")
    assert _check(tree) == (0, CLEAN)
