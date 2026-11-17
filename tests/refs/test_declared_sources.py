"""Unit tests for the configured reader of design declarations (D16.2)."""

import os
import subprocess
from pathlib import Path

import pytest

from trueup import cli, ref_check, survey
from trueup.ref_check import main, parse_legacy_marker, parse_marker, run

FORMS = '["D<n>.<m>", "D<n>.<m>.<k>", "D-<n>", "I-<n>"]'
"""A form list that holds a two-part, a three-part and a stage id."""

ALL = f'[targets.arch]\nsources = ["docs/*.md"]\nforms = {FORMS}\n'
"""A configuration that reads each page of `docs/` with every form."""


def _tree(root: Path, config: str, pages: dict[str, str], code: str = "") -> None:
    """Write one small repository for the checker.

    Args:
        root: The repository.
        config: The text of `ref_check.toml`. An empty text writes no file.
        pages: The Markdown pages, by the path below the root.
        code: The text of `test_sample.py`. An empty text writes no file.
    """
    if config:
        (root / "ref_check.toml").write_text(config, encoding="utf-8")
    for name, text in pages.items():
        page = root / name
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(text, encoding="utf-8")
    if code:
        (root / "test_sample.py").write_text(code, encoding="utf-8")


def _rows(root: Path) -> list[tuple[str, int, str]]:
    """Run the checker and give the failures in short form.

    Args:
        root: The repository.

    Returns:
        One tuple (path, line, kind) for each failure, in report order.
    """
    return [(item.path, item.line, item.kind) for item in run(root).failures]


def _cite(*idents: str) -> str:
    """Write one comment marker for each id.

    Args:
        *idents: The ids to cite.

    Returns:
        The Python source text, one comment line for each id.
    """
    return "".join(f"# arch: {ident}\n" for ident in idents)


def test_with_no_key_set_the_checker_keeps_todays_rows(tmp_path):
    """With no key set, one page and today's patterns give today's rows.

    arch: D16.2, I-54
    """
    _tree(
        tmp_path,
        "",
        {
            "docs/ARCHITECTURE.md": (
                "## D1.1 A heading of level two\n"
                "### D2.2 A heading of level three\n"
                "| D3.3 | A first cell |\n"
                "- **I-1 A list id.**\n"
                "- **D4.4** A bold lead\n\n"
                "## Verification\n\nD1.1\n"
            ),
            "docs/OTHER.md": "## D5.5 On a second page\n",
        },
        _cite("D1.1", "D2.2", "D3.3", "I-1", "D4.4", "D5.5", "D-1", "D6.6.6"),
    )
    assert _rows(tmp_path) == [
        ("test_sample.py", 2, "unknown-id"),
        ("test_sample.py", 3, "unknown-id"),
        ("test_sample.py", 5, "unknown-id"),
        ("test_sample.py", 6, "unknown-id"),
        ("test_sample.py", 7, "malformed"),
        ("test_sample.py", 8, "malformed"),
    ]
    assert parse_marker("arch: D-1").malformed
    assert parse_legacy_marker("arch: D6.6.6").refs == (("arch", "D6.6"),)


def test_a_design_on_many_pages_declares_each_id(tmp_path):
    """Sources are a union, and an id on two sources is declared.

    arch: D16.2
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["docs/ARCHITECTURE.md", "plans/*/design.md"]\n',
        {
            "docs/ARCHITECTURE.md": "## D1.1 First\n\n## D3.3 On two pages\n",
            "plans/a/design.md": "## D2.1 Second\n\n## D3.3 On two pages\n",
            "plans/b/design.md": "## D2.2 Third\n",
        },
        _cite("D1.1", "D2.1", "D2.2", "D3.3"),
    )
    assert _rows(tmp_path) == []


def test_a_three_part_id_is_one_id(tmp_path):
    """A three-part id declares and cites as a whole.

    arch: D16.2
    """
    _tree(
        tmp_path,
        ALL,
        {"docs/a.md": "### D15.3.7 CLI\n\n## D15.3 Parent\n"},
        '"""A test file.\n\narch: D15.3.7\n"""\n' + _cite("D15.3.7", "D15.3"),
    )
    report = run(tmp_path)
    assert report.failures == []
    assert {edge.id for edge in report.edges} == {"D15.3.7", "D15.3"}


def test_a_three_part_heading_does_not_declare_its_parent(tmp_path):
    """With no three-part form, `### D15.3.7` declares nothing.

    arch: D16.2, I-55
    """
    _tree(
        tmp_path,
        '[targets.arch]\nforms = ["D<n>.<m>"]\n',
        {"docs/ARCHITECTURE.md": "### D15.3.7 CLI\n"},
        _cite("D15.3"),
    )
    assert _rows(tmp_path) == [("test_sample.py", 1, "unknown-id")]


@pytest.mark.parametrize(
    ("line", "ident"),
    [
        ("# D1.1 Level one", "D1.1"),
        ("###### D1.2 Level six", "D1.2"),
        ("## D-301 — RULED", "D-301"),
        ("## D1.3", "D1.3"),
        ("| D8.1 | Plain first cell |", "D8.1"),
        ("| **D8.2** | Bold first cell |", "D8.2"),
        ("- **D9.3** A bold lead of a list item", "D9.3"),
        ("**D9.4 A bold lead of a paragraph.** More text", "D9.4"),
        ("- **I-3 An invariant.**", "I-3"),
        ("  1. **D9.5** A numbered item", "D9.5"),
    ],
)
def test_each_declaration_shape_declares(tmp_path, line, ident):
    """A heading of any level, a first cell and a bold lead each declare.

    arch: D16.2
    """
    _tree(tmp_path, ALL, {"docs/a.md": f"{line}\n"}, _cite(ident))
    assert _rows(tmp_path) == []


@pytest.mark.parametrize(
    ("line", "ident"),
    [
        ("See D5.5 in the prose.", "D5.5"),
        ("## About D5.6", "D5.6"),
        ("| T1 | D5.7 |", "D5.7"),
        ("| D5.8 and more text | second |", "D5.8"),
        ("- An item with **D5.9** inside", "D5.9"),
        ("Text before **D5.1**", "D5.1"),
        ("## D5.2x Glued text", "D5.2"),
        ("## XD5.3 Glued text", "D5.3"),
    ],
)
def test_a_mention_does_not_declare(tmp_path, line, ident):
    """An id anywhere but in a declaration shape does not declare.

    arch: D16.2, I-55
    """
    _tree(tmp_path, ALL, {"docs/a.md": f"{line}\n"}, _cite(ident))
    assert _rows(tmp_path) == [("test_sample.py", 1, "unknown-id")]


def test_a_fenced_block_does_not_declare(tmp_path):
    """A declaration shape in a fenced code block does not declare.

    arch: D16.2, I-55
    """
    page = "```text\n## D6.6 In a fence\n```\n\n~~~\n- **D6.7** In a fence\n~~~\n"
    _tree(tmp_path, ALL, {"docs/a.md": page}, _cite("D6.6", "D6.7"))
    assert _rows(tmp_path) == [
        ("test_sample.py", 1, "unknown-id"),
        ("test_sample.py", 2, "unknown-id"),
    ]


def test_a_typo_id_fails_at_each_citation(tmp_path):
    """An id that no source declares gives one row per citation.

    arch: D16.2, I-55
    """
    _tree(
        tmp_path,
        ALL,
        {"docs/a.md": "## D12.9 Real\n"},
        _cite("D12.9", "D12.99", "D12.99"),
    )
    report = run(tmp_path)
    assert [(item.line, item.kind) for item in report.failures] == [
        (2, "unknown-id"),
        (3, "unknown-id"),
    ]
    assert "D12.99" in report.failures[0].detail


def test_a_missing_source_fails_with_one_row_per_entry(tmp_path, capsys):
    """Each missing entry gives one row, and no citation gives `unknown-id`.

    arch: D16.2, I-56
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["docs/a.md", "gone/page.md", "plans/*/none.md"]\n',
        {"docs/a.md": "## D1.1 Real\n"},
        _cite("D1.1", "D1.2", "D1.3"),
    )
    report = run(tmp_path)
    assert [(i.path, i.line, i.kind, i.detail) for i in report.failures] == [
        (
            "gone/page.md",
            1,
            "no-target",
            "declared source not found: gone/page.md; 2 citations not checked",
        ),
        (
            "plans/*/none.md",
            1,
            "no-target",
            "declared source not found: plans/*/none.md; 2 citations not checked",
        ),
    ]
    assert main(["--root", str(tmp_path)]) == 1
    capsys.readouterr()


def test_a_glob_with_one_match_is_found(tmp_path):
    """A glob that matches a file is a found source, as a whole.

    arch: D16.2, I-55
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["plans/*/design.md"]\n',
        {"plans/a/design.md": "## D1.1 Real\n", "plans/b/notes.md": "text\n"},
        _cite("D1.1", "D1.2"),
    )
    assert _rows(tmp_path) == [("test_sample.py", 2, "unknown-id")]


def test_a_source_outside_the_root_is_read(tmp_path):
    """A `..` segment names a source outside the root.

    arch: D16.2
    """
    root = tmp_path / "repo" / "src"
    root.mkdir(parents=True)
    _tree(
        tmp_path / "repo",
        "",
        {".state/runs/a/03-design.md": "## D1.1 Outside\n"},
    )
    _tree(
        root,
        '[targets.arch]\nsources = ["../.state/runs/*/03-design.md", "../NOTES.md"]\n',
        {},
        _cite("D1.1"),
    )
    (tmp_path / "repo" / "NOTES.md").write_text("## D1.2 Literal\n", encoding="utf-8")
    assert _rows(root) == []


def test_a_clone_without_the_outside_source_fails_with_one_row(tmp_path):
    """A clone that lacks the outside source fails loud, with one row.

    arch: D16.2, I-56
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["../absent-ledger/*/design.md"]\n',
        {},
        _cite("D1.1", "D1.2", "D1.3"),
    )
    report = run(tmp_path)
    assert [item.kind for item in report.failures] == ["no-target"]
    assert report.failures[0].detail.endswith("; 3 citations not checked")


def test_a_symlink_source_is_followed(tmp_path):
    """A symlink to a regular file outside the root is read.

    arch: D16.2
    """
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "ledger.md"
    outside.write_text("## D1.1 Outside\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "a.md").symlink_to(outside)
    _tree(root, ALL, {}, _cite("D1.1"))
    assert _rows(root) == []


def test_a_source_that_is_not_a_file_gives_one_unreadable_row(tmp_path):
    """A directory, a FIFO or text that is not UTF-8 is one `unreadable` row.

    arch: D16.2
    """
    _tree(tmp_path, ALL, {"docs/good.md": "## D1.1 Real\n"}, _cite("D1.1", "D1.2"))
    (tmp_path / "docs" / "dir.md").mkdir()
    os.mkfifo(tmp_path / "docs" / "fifo.md")
    (tmp_path / "docs" / "latin.md").write_bytes(b"\xff\xfe## D1.2\n")
    assert _rows(tmp_path) == [
        ("docs/dir.md", 1, "unreadable"),
        ("docs/fifo.md", 1, "unreadable"),
        ("docs/latin.md", 1, "unreadable"),
    ]


def test_a_source_over_the_read_cap_gives_one_unreadable_row(tmp_path, monkeypatch):
    """A source larger than the cap is one `unreadable` row.

    arch: D16.2
    """
    monkeypatch.setattr(ref_check, "_READ_CAP", 14)
    _tree(tmp_path, ALL, {"docs/big.md": "## D1.1 Real and long\n"}, _cite("D1.1"))
    assert _rows(tmp_path) == [("docs/big.md", 1, "unreadable")]


def test_checks_a_and_c_read_the_same_sources_and_forms(tmp_path):
    """Check c reads each source that has the section, with the configured forms.

    arch: D16.2, I-57
    """
    _tree(
        tmp_path,
        ALL,
        {
            "docs/a.md": (
                "## D1.1.1 Three parts\n\n## Verification\n\n"
                "D1.1.1 is proved. D-7 is not.\n"
            ),
            "docs/b.md": (
                "## D-7 A stage id\n\n## D-8 Another\n\n## Verification\n\nD-8\n"
            ),
            "docs/c.md": "## D2.2 No section here\n",
        },
        _cite("D1.1.1", "D2.2"),
    )
    report = run(tmp_path)
    assert [(i.path, i.line, i.kind) for i in report.failures] == [
        ("docs/a.md", 5, "unproved"),
        ("docs/b.md", 7, "unproved"),
    ]
    assert report.failures[0].detail.endswith(": D-7")
    assert report.failures[1].detail.endswith(": D-8")


def test_an_open_plan_row_excuses_a_configured_form(tmp_path):
    """An open row of `PLAN.md` excuses a claim in a configured form.

    arch: D16.2, I-57
    """
    _tree(
        tmp_path,
        ALL,
        {
            "docs/a.md": "## D-7 A stage id\n\n## Verification\n\nD-7\n",
            "PLAN.md": "| T1 | open | still owns D-7 |\n",
        },
        _cite("D-7"),
    )
    (tmp_path / "test_sample.py").unlink()
    report = run(tmp_path)
    assert report.failures == []
    assert report.excused == ["D-7"]


def test_id_forms_alone_reads_the_design_page_of_the_docs_dir(tmp_path):
    """With only `forms` set, the source is `<docs_dir>/ARCHITECTURE.md`.

    arch: D16.2
    """
    _tree(
        tmp_path,
        '[layout]\ndocs_dir = "pages"\n\n[targets.arch]\nforms = ["D-<n>"]\n',
        {
            "pages/ARCHITECTURE.md": "## D-1 Real\n",
            "docs/ARCHITECTURE.md": "## D-2 No\n",
        },
        _cite("D-1", "D-2"),
    )
    assert _rows(tmp_path) == [("test_sample.py", 2, "unknown-id")]


def test_declared_alone_reads_the_two_default_forms(tmp_path):
    """With only `sources` set, the forms are `D<n>.<m>` and `I-<n>`.

    arch: D16.2
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["a.md"]\n',
        {"a.md": "| D1.1 | Cell |\n\n- **I-2** Lead\n"},
        _cite("D1.1", "I-2", "D-3"),
    )
    assert _rows(tmp_path) == [("test_sample.py", 3, "malformed")]


def test_a_configured_form_reaches_each_marker_kind(tmp_path):
    """A `ref:` marker, a misspelled keyword and a test docstring read the forms.

    arch: D16.2
    """
    _tree(
        tmp_path,
        "[checks]\nregistry = true\n\n" + ALL,
        {"docs/a.md": "## D-1 Real\n\n## D15.3.7 Real\n"},
        (
            '"""A module.\n\narch: D15.3.7, D-1\n"""\n'
            "# ref: arch/D-1\n"
            "# refs: arch/D-1\n"
        ),
    )
    report = run(tmp_path)
    assert [(i.line, i.kind) for i in report.failures] == [(6, "unregistered")]
    assert ("D15.3.7" in {edge.id for edge in report.edges}) is True


def test_a_byte_order_mark_keeps_a_first_line_declaration(tmp_path):
    """A source that starts with a byte order mark declares its first line.

    arch: D16.2
    """
    _tree(
        tmp_path,
        '[targets.arch]\nsources = ["a.md"]\n',
        {"a.md": "\ufeff## D1.1 First line\n"},
        _cite("D1.1"),
    )
    assert _rows(tmp_path) == []


def test_a_directory_source_closes_its_descriptor(tmp_path, monkeypatch):
    """A refused directory gives its descriptor back.

    arch: D16.2
    """
    opened: list[int] = []
    real_open = os.open

    def spy(*args, **kwargs):
        """Record each descriptor that the reader opens.

        Args:
            *args: The arguments of `os.open`.
            **kwargs: The keyword arguments of `os.open`.

        Returns:
            The descriptor.
        """
        opened.append(real_open(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(ref_check.os, "open", spy)
    with pytest.raises(IsADirectoryError):
        ref_check._read_capped(tmp_path)
    monkeypatch.undo()
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


def _t0_target(root: Path) -> None:
    """Write one adopted T0 target that sets both reader keys.

    Args:
        root: The repository.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    _tree(
        root,
        "",
        {
            "trueup.toml": (
                '[refs]\ndeclared = ["design/a.md"]\n'
                'id_forms = ["D-<n>", "D<n>.<m>.<k>"]\n'
            ),
            "design/a.md": "## D-7 A stage id\n\n## D1.2.3 Three parts\n",
        },
        _cite("D-7", "D1.2.3", "D-99"),
    )
    assert survey.run(root).tier == "T0"


@pytest.mark.parametrize("command", ["refs", "check"])
def test_the_keys_reach_the_checker_below_the_tier_gate(tmp_path, capsys, command):
    """At T0 the commands read the configured ids, and D-99 still fails.

    arch: D16.2, I-55
    """
    _t0_target(tmp_path)
    assert cli.main([command, "--root", str(tmp_path)]) != 0
    shown = capsys.readouterr().out
    assert "malformed" not in shown
    assert shown.count("[unknown-id]") == 1
    assert "D-99" in shown
