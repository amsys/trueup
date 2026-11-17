"""Integration tests for check i, the root README (D2.14)."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from trueup import ref_check
from tests.refs.conftest import materialise
from trueup.ref_check import load_config, main

REPO = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO / "trueup" / "ref_check.py"
CLEAN = ["ref_check: 0 failures, 0 references"]

EXPECTED = {
    "readme-clean": [],
    "readme-no-readme": ["README.md:1: [no-readme] no README.md at the root"],
    "readme-no-title": ["README.md:1: [no-title] line 1 is not a title"],
    "readme-no-description": [
        "README.md:1: [no-description] no paragraph after the title"
    ],
    "readme-no-section": [
        "README.md:1: [no-section] section is absent: Install",
        "README.md:1: [no-section] section is absent: Usage",
    ],
    "readme-misordered": ["README.md:9: [misordered] License is not the last section"],
    "readme-no-licence-file": [
        "README.md:1: [no-licence-file] no LICENSE, LICENCE or COPYING file at the root",
    ],
    "readme-badges-scattered": [
        "README.md:9: [badges-scattered] badge is outside the block under the title",
        "README.md:11: [badges-scattered] badge is outside the block under the title",
    ],
    "readme-no-index-link": ["README.md:1: [no-index-link] no link to docs/README.md"],
}

MARKDOWN_CASES = {
    "readme-html-title": [],
    "readme-quick-start": [],
    "readme-no-docs-index": [],
}
"""The README trees of D15.18. Each one gave a false failure before."""

COMPLETE = (
    "\n\nDemo checks one tree. Read the [index](docs/README.md).\n\n"
    "## Install\n\nCopy it.\n\n## Usage\n\nRun it.\n\n## License\n\nMIT.\n"
)
"""A README body after the title that obeys the rules 2 to 6."""


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


def _readme_tree(root: Path, data: bytes, licence: str = "LICENSE") -> Path:
    """Write a tree with the switch `readme` on, one README and one licence file.

    Args:
        root: The directory to write into.
        data: The bytes of `README.md`.
        licence: The name of the licence file at the root.

    Returns:
        The root.
    """
    (root / "ref_check.toml").write_text("[checks]\nreadme = true\n", encoding="utf-8")
    (root / "README.md").write_bytes(data)
    (root / licence).write_text("MIT License\n", encoding="utf-8")
    return root


def _add_index(root: Path) -> Path:
    """Write `docs/README.md`, so the rule `no-index-link` applies (D15.18).

    Args:
        root: The tree to write into.

    Returns:
        The root.
    """
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "README.md").write_text("# Index\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_each_readme_tree_gives_its_failure_lines(case, tmp_path):
    """Each fixture tree gives the whole D2.4 line of its kind, and the clean tree gives none.

    arch: D2.14, D2.4
    """
    tree = materialise(case, tmp_path)
    lines = EXPECTED[case]
    summary = f"ref_check: {len(lines)} failures, 0 references"
    assert _check(tree) == (1 if lines else 0, [*lines, summary])


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_readme_absent_gives_no_check_i_failure(case, tmp_path):
    """With no `readme` switch, a tree that breaks the README rules passes (S18).

    arch: D2.5, D2.14
    """
    tree = materialise(case, tmp_path)
    (tree / "ref_check.toml").write_text("[checks]\nlinks = false\n", encoding="utf-8")
    assert _check(tree) == (0, CLEAN)


@pytest.mark.parametrize(
    ("data", "licence"),
    [
        (b"<h1 align='center'>\n  Demo\n</H1>" + COMPLETE.encode(), "COPYING"),
        (b"\xef\xbb\xbf# Demo" + COMPLETE.encode(), "LICENSE.md"),
        (
            b"#  Demo  #" + COMPLETE.replace("Install", "Installation").encode(),
            "LICENSE",
        ),
    ],
)
def test_a_readme_that_obeys_the_rules_gives_no_failure(data, licence, tmp_path):
    """An HTML title, a byte order mark, `Installation` and each licence name pass.

    arch: D2.14
    """
    assert _check(_readme_tree(tmp_path, data, licence)) == (0, CLEAN)


def test_an_html_title_with_no_end_tag_is_not_a_title(tmp_path):
    """An `<h1` on line 1 with no `</h1>` gives `no-title`, and line 1 is then the description.

    arch: D2.14, D2.4
    """
    tree = _readme_tree(tmp_path, b"<h1>Demo" + COMPLETE.encode())
    assert _check(tree) == (
        1,
        [
            "README.md:1: [no-title] line 1 is not a title",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_a_readme_that_does_not_decode_is_unreadable(tmp_path):
    """A `README.md` that is not UTF-8 gives `unreadable`, and the rules do not run (I-4).

    arch: D2.14, I-4
    """
    tree = _readme_tree(tmp_path, b"# Demo\n\n\xff\xfe no text\n")
    assert _check(tree) == (
        1,
        [
            "README.md:1: [unreadable] file cannot be read: UnicodeDecodeError",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_a_link_with_a_null_character_is_not_the_index_link(tmp_path):
    """A link path that holds `%00` is not the index, and the check does not stop.

    The tree holds `docs/README.md`, so the rule `no-index-link` applies.

    arch: D2.14, I-4, D15.18
    """
    _add_index(tmp_path)
    body = COMPLETE.replace("Read the", "See [x](a%00b). Read the")
    assert _check(_readme_tree(tmp_path, b"# Demo" + body.encode())) == (0, CLEAN)
    no_index = body.replace("[index](docs/README.md)", "the index")
    assert _check(_readme_tree(tmp_path, b"# Demo" + no_index.encode())) == (
        1,
        [
            "README.md:1: [no-index-link] no link to docs/README.md",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_a_link_through_a_symlink_loop_is_not_the_index_link(tmp_path):
    """A link path through a symlink loop is not the index, and the check does not stop.

    The tree holds `docs/README.md`, so the rule `no-index-link` applies.

    arch: D2.14, I-4, D15.18
    """
    _add_index(tmp_path)
    (tmp_path / "loop").symlink_to("loop")
    body = COMPLETE.replace("Read the", "See [x](loop). Read the")
    assert _check(_readme_tree(tmp_path, b"# Demo" + body.encode())) == (0, CLEAN)
    no_index = body.replace("[index](docs/README.md)", "the index")
    assert _check(_readme_tree(tmp_path, b"# Demo" + no_index.encode())) == (
        1,
        [
            "README.md:1: [no-index-link] no link to docs/README.md",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_an_empty_readme_gives_each_kind_that_it_breaks(tmp_path):
    """An empty `README.md` has no title, no description, no section and no index link.

    The tree holds `docs/README.md`, so the rule `no-index-link` applies.

    arch: D2.14, D2.4, D15.18
    """
    tree = _add_index(_readme_tree(tmp_path, b""))
    assert _check(tree) == (
        1,
        [
            "README.md:1: [no-description] no paragraph after the title",
            "README.md:1: [no-index-link] no link to docs/README.md",
            "README.md:1: [no-section] section is absent: Install",
            "README.md:1: [no-section] section is absent: License",
            "README.md:1: [no-section] section is absent: Usage",
            "README.md:1: [no-title] line 1 is not a title",
            "ref_check: 6 failures, 0 references",
        ],
    )


def test_the_schema_reads_the_readme_switch(tmp_path):
    """The key `[checks] readme` is in the schema, and it is off when absent.

    arch: D2.5
    """
    assert ref_check.CONFIG_SCHEMA["checks"][-1] == "readme"
    assert not load_config(tmp_path).readme
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nreadme = true\n", encoding="utf-8"
    )
    assert load_config(tmp_path).readme
    (tmp_path / "ref_check.toml").write_text("[checks]\nreadme = 1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 2


def test_the_notice_names_check_i_when_readme_is_off(tmp_path, capsys):
    """The notice gives `i` as the last letter, and `readme` on removes it.

    arch: D2.3
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlinks = true\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().err == "ref_check: checks off: e, f, h, i\n"

    _readme_tree(tmp_path, b"# Demo" + COMPLETE.encode())
    assert main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().err == "ref_check: checks off: e, f, g, h\n"


def test_the_readme_of_this_repository_follows_the_standard(tmp_path):
    """The root `README.md` and `LICENSE` of this repository give no check i failure.

    arch: D2.14
    """
    tree = tmp_path / "copy"
    tree.mkdir()
    shutil.copy(REPO / "README.md", tree / "README.md")
    shutil.copy(REPO / "LICENSE", tree / "LICENSE")
    (tree / "ref_check.toml").write_text("[checks]\nreadme = true\n", encoding="utf-8")
    assert _check(tree) == (0, CLEAN)


def test_the_readme_entry_point_passes_on_this_repository():
    """The pytest entry point of check i exists and passes on this repository.

    arch: D2.12, D2.14
    """
    ref_check.test_readme_follows_the_standard()


def test_licence_present_matches_any_case_and_extension(tmp_path):
    """`licence_present` accepts `LICENCE`, `copying.txt` and `license.md` at the root.

    arch: D15.14, D15.15
    """
    assert not ref_check.licence_present(tmp_path)
    for name in ("LICENCE", "copying.txt", "license.md"):
        (tmp_path / name).write_text("MIT\n", encoding="utf-8")
        assert ref_check.licence_present(tmp_path)
        (tmp_path / name).unlink()


def test_checks_licence_false_drops_the_licence_failures(tmp_path):
    """`[checks] licence = false` removes `no-licence-file` and the `License` section failure.

    arch: D15.14, D15.15
    """
    tree = _readme_tree(
        tmp_path, b"# Demo" + COMPLETE.replace("## License\n\nMIT.\n", "").encode()
    )
    (tree / "LICENSE").unlink()
    (tree / "ref_check.toml").write_text("[checks]\nreadme = true\n", encoding="utf-8")
    _, lines = _check(tree)
    assert any("no-licence-file" in line for line in lines)
    assert any("section is absent: License" in line for line in lines)
    (tree / "ref_check.toml").write_text(
        "[checks]\nreadme = true\nlicence = false\n", encoding="utf-8"
    )
    assert _check(tree) == (0, CLEAN)


@pytest.mark.parametrize("case", sorted(MARKDOWN_CASES))
def test_each_d15_readme_tree_gives_no_false_failure(case, tmp_path):
    """An HTML block before the title, `Quick Start`, and no docs index give no failure.

    arch: D15.18
    """
    tree = materialise(case, tmp_path)
    lines = MARKDOWN_CASES[case]
    summary = f"ref_check: {len(lines)} failures, 0 references"
    assert _check(tree) == (1 if lines else 0, [*lines, summary])


@pytest.mark.parametrize("heading", ["Quick Start", "Quickstart", "Getting Started"])
def test_each_quick_start_heading_counts_as_install(heading, tmp_path):
    """`Quick Start`, `Quickstart` and `Getting Started` each count as the `Install` section.

    arch: D15.18
    """
    body = COMPLETE.replace("## Install", f"## {heading}")
    tree = _add_index(_readme_tree(tmp_path, b"# Demo" + body.encode()))
    assert _check(tree) == (0, CLEAN)


def test_a_paragraph_before_the_title_is_still_no_title(tmp_path):
    """Only HTML block lines and blank lines may come before the title; a paragraph may not.

    arch: D15.18
    """
    data = b"<p>logo</p>\n\nSome text.\n\n# Demo" + COMPLETE.encode()
    tree = _add_index(_readme_tree(tmp_path, data))
    assert _check(tree) == (
        1,
        [
            "README.md:1: [no-title] line 1 is not a title",
            "ref_check: 1 failures, 0 references",
        ],
    )


def test_an_html_block_that_holds_the_title_gives_no_failure(tmp_path):
    """An `<h1>` inside an HTML block before the content is the title.

    arch: D15.18
    """
    data = b'<div align="center">\n<h1>Demo</h1>\n</div>' + COMPLETE.encode()
    tree = _add_index(_readme_tree(tmp_path, data))
    assert _check(tree) == (0, CLEAN)
