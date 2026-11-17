"""Unit tests for the design id about the fail-closed read rule."""

import os
import signal

import pytest

from trueup import ref_check
from trueup.ref_check import run


def test_python_syntax_error_gives_unreadable(tmp_path):
    """A Python file with a syntax error gives `unreadable` (I-4).

    arch: I-4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = run(tmp_path)
    matches = [
        failure
        for failure in report.failures
        if failure.kind == "unreadable" and failure.path == "broken.py"
    ]
    assert len(matches) == 1


def test_undecodable_bytes_give_unreadable(tmp_path):
    """A shell file with bytes that are not UTF-8 gives `unreadable` (I-4).

    arch: I-4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    broken = tmp_path / "broken.sh"
    broken.write_bytes(b"#!/bin/sh\n# \xff\xfe not utf-8\n")

    report = run(tmp_path)
    matches = [
        failure
        for failure in report.failures
        if failure.kind == "unreadable" and failure.path == "broken.sh"
    ]
    assert len(matches) == 1


def test_unreadable_file_does_not_stop_the_walk(tmp_path):
    """An unreadable file gives `unreadable` and the walk still checks the rest (I-4).

    arch: I-4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")
    other = tmp_path / "other.py"
    other.write_text('"""Module.\n\narch: D9.9\n"""\n', encoding="utf-8")

    report = run(tmp_path)
    kinds_for_broken = {
        failure.kind for failure in report.failures if failure.path == "broken.py"
    }
    kinds_for_other = {
        failure.kind for failure in report.failures if failure.path == "other.py"
    }
    assert kinds_for_broken == {"unreadable"}
    assert kinds_for_other  # the walk went on and still judged other.py


def test_a_byte_order_mark_keeps_the_markers(tmp_path):
    """A UTF-8 byte order mark at the start of a file hides no marker, id or heading (D1.2, D2.10).

    arch: D1.2, D2.10
    """
    from trueup.ref_check import run

    bom = b"\xef\xbb\xbf"
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlinks = true\n", encoding="utf-8"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_bytes(bom + "## D1.1 — Gate\n".encode())
    (docs / "guide.md").write_bytes(bom + b"# Guide\n\nSee [the top](#guide).\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_bytes(bom + b'"""App.\n\nref: arch/D1.1\n"""\n')
    (src / "tool.sh").write_bytes(bom + b"# ref: arch/D1.1\necho 1\n")

    report = run(tmp_path)
    assert report.failures == []
    assert [(edge.source, edge.line, edge.status) for edge in report.edges] == [
        ("src/app.py", 3, "ok"),
        ("src/tool.sh", 1, "ok"),
    ]


def test_a_latin_1_coding_line_decodes_the_python_file(tmp_path):
    """A `.py` file with a `coding: latin-1` line decodes by that codec (R-12).

    A byte `0xE9` in a string, a comment marker and a docstring marker all
    read, and the file gives no `unreadable` failure.

    arch: D1.2
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## D1.1 — Gate\n", encoding="utf-8")
    source = (
        "# -*- coding: latin-1 -*-\n"
        '"""Module.\n\nref: arch/D1.1\n"""\n'
        'name = "caf\xe9"  # ref: arch/D1.1\n'
    )
    (tmp_path / "legacy.py").write_bytes(source.encode("latin-1"))

    report = run(tmp_path)
    matches = [failure for failure in report.failures if failure.path == "legacy.py"]
    assert matches == []
    assert [edge.line for edge in report.edges if edge.source == "legacy.py"] == [4, 6]


def test_an_unknown_codec_line_gives_unreadable(tmp_path):
    """A `.py` file that names a codec Python does not know gives `unreadable` (R-12).

    arch: D1.2
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    broken = tmp_path / "broken.py"
    broken.write_text("# -*- coding: no-such-codec -*-\npass\n", encoding="utf-8")

    report = run(tmp_path)
    matches = [
        failure
        for failure in report.failures
        if failure.kind == "unreadable" and failure.path == "broken.py"
    ]
    assert len(matches) == 1


def test_a_binary_shell_file_gives_unreadable(tmp_path):
    """A binary `x.sh` file gives `unreadable`, decoder change or not (I-4).

    arch: I-4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    binary = tmp_path / "x.sh"
    binary.write_bytes(bytes(range(256)))

    report = run(tmp_path)
    matches = [
        failure
        for failure in report.failures
        if failure.kind == "unreadable" and failure.path == "x.sh"
    ]
    assert len(matches) == 1


def test_a_latin_1_shell_file_gives_unreadable(tmp_path):
    """A latin-1 `x.sh` file still gives `unreadable`: only `.py` gets the new decoder (R-12).

    arch: D1.2
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    shell = tmp_path / "x.sh"
    shell.write_bytes("# caf\xe9\n".encode("latin-1"))

    report = run(tmp_path)
    matches = [
        failure
        for failure in report.failures
        if failure.kind == "unreadable" and failure.path == "x.sh"
    ]
    assert len(matches) == 1


def test_a_docstring_marker_reports_its_source_line(tmp_path):
    """An escaped line end in a docstring does not move the line of a later marker (D2.4).

    arch: D2.4
    """
    from trueup.ref_check import Failure

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## D1.1 — Gate\n", encoding="utf-8")
    source = (
        "def gate():\n"
        '    """Gate.\\n\\nMore text, one source line.\n'
        "\n"
        "    ref: arch/D9.9\n"
        '    """\n'
    )
    (tmp_path / "sample.py").write_text(source, encoding="utf-8")
    report = run(tmp_path)
    assert report.failures == [Failure("sample.py", 4, "unknown-id", "gate cites D9.9")]


def test_a_heredoc_line_is_no_marker_position(tmp_path):
    """A shell heredoc body gives no marker and no suppression; the lines after it still do.

    The tree has a `<<WORD` heredoc, a `<<-'WORD'` heredoc closed by a tab
    and the word, and an arithmetic shift that opens no heredoc, because no
    later line closes it.

    arch: D15.18
    """
    from tests.refs.conftest import materialise
    from trueup.ref_check import format_failure

    tree = materialise("shell-heredoc", tmp_path)
    report = run(tree)
    assert [format_failure(failure) for failure in report.failures] == [
        "gen.sh:11: [no-reason] -: suppression has no reason: shellcheck disable=SC2034",
        "gen.sh:12: [unknown-id] - cites D7.7",
    ]


def test_rust_doc_comments_are_marker_positions(tmp_path):
    """A `//!` and a `///` doc comment give their edges, and a doc comment gets no tag rule.

    The `NOTE:` tag in a `///` line is prose, as in a Python docstring, so
    the registry gives no `unregistered` failure for it.

    arch: D15.19
    """
    from tests.refs.conftest import materialise

    tree = materialise("rust-doc-leaders", tmp_path)
    report = run(tree)
    assert report.failures == []
    assert [
        (edge.line, edge.marker, edge.target, edge.id) for edge in report.edges
    ] == [
        (1, "arch", "arch", "D1.1"),
        (3, "arch", "arch", "D1.2"),
        (7, "ref", "arch", "D1.1"),
    ]


def test_the_rust_reader_strips_the_longest_leader(tmp_path):
    """The Rust reader strips `///`, `//!` or `//`, and only the first two are doc lines.

    arch: D15.19
    """
    from trueup.ref_check import READERS, MarkerPosition

    source = tmp_path / "lib.rs"
    source.write_text(
        "/// doc line\n//! inner doc\n// plain\n//// four slashes\nfn f() {}\n",
        encoding="utf-8",
    )
    assert READERS["rust"](source) == [
        MarkerPosition(1, "-", "doc line", True),
        MarkerPosition(2, "-", "inner doc", True),
        MarkerPosition(3, "-", "plain", False),
        MarkerPosition(4, "-", "// four slashes", False),
    ]


class _TimeLimitExpired(BaseException):
    """The run ended past its time limit. An `except OSError` cannot catch it."""


def _design(root):
    """Write the smallest design page that a run accepts.

    Args:
        root: The repository root.
    """
    docs = root / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")


def _run_under_limit(root):
    """Run the checker, and fail when it does not end in time.

    Args:
        root: The repository root.

    Returns:
        The report of the run.
    """

    def expired(_signum, _frame):
        raise _TimeLimitExpired("the checker passed its time limit")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(30)
    try:
        return run(root)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _unreadable(report):
    """List the paths that a report calls `unreadable`.

    Args:
        report: The report of a run.

    Returns:
        The set of paths.
    """
    return {failure.path for failure in report.failures if failure.kind == "unreadable"}


def test_a_symlink_to_a_fifo_gives_unreadable_and_no_hang(tmp_path):
    """A source file that is a symlink to a FIFO gives `unreadable` and the run ends.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    os.mkfifo(tmp_path / "pipe")
    (root / "pipe.sh").symlink_to(tmp_path / "pipe")
    (root / "pipe.py").symlink_to(tmp_path / "pipe")

    report = _run_under_limit(root)

    assert {"pipe.sh", "pipe.py"} <= _unreadable(report)


def test_a_fifo_at_the_root_gives_unreadable_and_no_hang(tmp_path):
    """A FIFO that the walk lists gives `unreadable` and the run ends.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    os.mkfifo(root / "pipe.sh")

    report = _run_under_limit(root)

    assert "pipe.sh" in _unreadable(report)


def test_a_symlink_out_of_the_root_gives_unreadable(tmp_path):
    """A source file that links out of the root gives `unreadable`.

    A symlink to a file inside the root is read as before.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    (tmp_path / "outside.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "out.sh").symlink_to(tmp_path / "outside.sh")
    (root / "real.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "in.sh").symlink_to(root / "real.sh")

    report = _run_under_limit(root)

    assert "out.sh" in _unreadable(report)
    assert "in.sh" not in _unreadable(report)


def test_a_file_over_the_read_cap_gives_unreadable(tmp_path, monkeypatch):
    """A source file and a design page over the cap give `unreadable`.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    (root / "big.sh").write_text("#!/bin/sh\n# padding\n", encoding="utf-8")
    (root / "small.sh").write_text("#\n", encoding="utf-8")
    monkeypatch.setattr(ref_check, "_READ_CAP", 8)

    report = _run_under_limit(root)

    assert "big.sh" in _unreadable(report)
    assert "small.sh" not in _unreadable(report)
    assert "docs/ARCHITECTURE.md" in _unreadable(report)


def test_a_plan_symlink_to_a_fifo_does_not_stop_the_run(tmp_path):
    """A `PLAN.md` that links to a FIFO does not block the claim check.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "ARCHITECTURE.md").write_text(
        "## D1.1 - x\n\n## Verification\n\n- D1.1: covered by a test\n",
        encoding="utf-8",
    )
    os.mkfifo(tmp_path / "pipe")
    (root / "PLAN.md").symlink_to(tmp_path / "pipe")

    report = _run_under_limit(root)

    assert report is not None


def _only_check(root, switch):
    """Write a `ref_check.toml` that turns on one check and turns off the rest.

    Args:
        root: The repository root.
        switch: The `[checks]` key to turn on.
    """
    lines = [
        f"{key} = {'true' if key == switch else 'false'}\n"
        for key in ref_check.CONFIG_SCHEMA["checks"]
    ]
    (root / ref_check.CONFIG_NAME).write_text(
        "[checks]\n" + "".join(lines), encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("switch", "page"),
    [("links", "page.md"), ("layout", "docs/out.md"), ("readme", "README.md")],
)
def test_a_page_out_of_the_root_gives_unreadable_under_its_own_check(
    tmp_path, switch, page
):
    """Checks g, h and i each give `unreadable` for a page that links out of the root.

    Only the check under test is on, so no other check reads the page first.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    _only_check(root, switch)
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")
    (root / page).symlink_to(tmp_path / "outside.md")

    report = _run_under_limit(root)

    assert page in _unreadable(report)


def test_a_config_that_links_out_of_the_root_does_not_load(tmp_path):
    """A `ref_check.toml` that links out of the root stops the run, as a config that does not parse.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    _design(root)
    (tmp_path / "outside.toml").write_text(
        "[checks]\nreadme = true\n", encoding="utf-8"
    )
    (root / ref_check.CONFIG_NAME).symlink_to(tmp_path / "outside.toml")

    with pytest.raises(ref_check.ConfigError, match="does not parse"):
        _run_under_limit(root)


@pytest.mark.parametrize("suffix", [".md", ".sh", ".py"])
def test_a_bounded_read_keeps_the_newline_translation(tmp_path, suffix):
    """The bounded read gives each file the universal newlines of `Path.read_text`.

    arch: D16.10
    """
    path = tmp_path / f"a{suffix}"
    path.write_bytes(b"x = 1\r\ny = 2\rz = 3\n")

    assert ref_check._read_text(path) == "x = 1\ny = 2\nz = 3\n"
