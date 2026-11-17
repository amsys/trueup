"""Tests for the reader-change warning list of the checker (D16.3)."""

import pytest

from trueup import ref_check
from trueup.ref_check import MarkerPosition, load_config, main, run

_CHANGE = "rust-doc-position"


def _rust_doc(language: str, position: MarkerPosition) -> bool:
    """Match a Rust doc comment, the position that D15.19 added."""
    return language == "rust" and position.docstring


def _tree(tmp_path, accepted: bool = False):
    """Build a root with one Rust doc comment that cites an id nothing declares."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## D1.1 Real\n\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.rs").write_text("/// arch: D9.9\nfn f() {}\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[targets.arch]\naccepted = " + (f'["{_CHANGE}"]' if accepted else "[]") + "\n",
        encoding="utf-8",
    )
    return tmp_path


def _law_tree(tmp_path, pinned, newest=None, accepted=False):
    """Build a root with one Rust doc comment that cites a law section."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.rs").write_text(
        "/// ref: law/acts/X/v1/s.1\nfn f() {}\n", encoding="utf-8"
    )
    act = tmp_path / "archive" / "acts" / "X"
    for version, body in (("v1", pinned), ("v2", newest)):
        if body is not None:
            (act / version).mkdir(parents=True)
            (act / version / "document.md").write_bytes(body)
    (tmp_path / "ref_check.toml").write_text(
        '[targets.law]\narchive = "archive"\n[targets.arch]\naccepted = '
        + (f'["{_CHANGE}"]' if accepted else "[]")
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


_SECTION = b"### 1. First\n\nText.\n"
_NOT_UTF8 = b"\xff\n"
_MARKER_READS = pytest.mark.parametrize(
    ("pinned", "newest"),
    [(_NOT_UTF8, None), (_SECTION, _NOT_UTF8)],
    ids=["check-a", "check-d"],
)


@pytest.fixture
def fake_change(monkeypatch):
    """Register one fake change with the D15.19 shape."""
    monkeypatch.setitem(ref_check.READER_CHANGES, _CHANGE, _rust_doc)


def test_the_registry_ships_empty():
    """The change table is empty in this release.

    arch: D16.3
    """
    assert ref_check.READER_CHANGES == {}


def test_a_registered_change_turns_its_failure_into_a_warning(tmp_path, fake_change):
    """A failure from a position that a registered change matches is a warning.

    arch: D16.3, I-58
    """
    report = run(_tree(tmp_path))
    assert report.failures == []
    assert [(name, f.kind, f.path, f.line) for name, f in report.warnings] == [
        (_CHANGE, "unknown-id", "src/lib.rs", 1)
    ]


def test_an_accepted_change_fails_again(tmp_path, fake_change):
    """After the target accepts the change, the same failure fails (I-58).

    arch: D16.3, I-58
    """
    report = run(_tree(tmp_path, accepted=True))
    assert [f.kind for f in report.failures] == ["unknown-id"]
    assert report.warnings == []


def test_a_marker_at_another_position_still_fails(tmp_path, fake_change):
    """A plain comment is not a doc position, so its failure stays a failure.

    arch: D16.3, I-58
    """
    root = _tree(tmp_path)
    (root / "src" / "lib.rs").write_text("// arch: D9.9\nfn f() {}\n", encoding="utf-8")
    report = run(root)
    assert [f.kind for f in report.failures] == ["unknown-id"]
    assert report.warnings == []


def test_no_registered_change_gives_no_warning(tmp_path):
    """With the empty table the failure fails, as before this round.

    arch: D16.3
    """
    report = run(_tree(tmp_path))
    assert [f.kind for f in report.failures] == ["unknown-id"]
    assert report.warnings == []


def test_the_command_prints_the_warning_and_exits_0(tmp_path, fake_change, capsys):
    """`main` prints each warning and one line per change, and exits 0 (I-58).

    arch: D16.3, I-58
    """
    root = _tree(tmp_path)
    assert main(["--root", str(root)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("warning: src/lib.rs:1: [unknown-id] ")
    assert lines[1] == (
        f"ref_check: 1 warnings from reader change {_CHANGE}; "
        "add it to [refs] accepted_reader_changes to fail on them"
    )
    assert lines[2].startswith("ref_check: 0 failures")


def test_the_command_exits_1_for_an_accepted_change(tmp_path, fake_change, capsys):
    """An accepted change prints no warning and exits 1 (I-58).

    arch: D16.3, I-58
    """
    assert main(["--root", str(_tree(tmp_path, accepted=True))]) == 1
    assert "warning:" not in capsys.readouterr().out


def test_the_loader_reads_accepted(tmp_path):
    """`[targets.arch] accepted` loads as a set of names; the default is empty.

    arch: D16.3
    """
    assert ref_check.Config().accepted == frozenset()
    root = _tree(tmp_path, accepted=True)
    assert load_config(root).accepted == frozenset({_CHANGE})


@pytest.mark.parametrize("value", ["1", "[1]", '[""]', '["a b"]', '["a,b"]'])
def test_the_loader_rejects_a_bad_accepted_value(tmp_path, value):
    """A bad `accepted` value stops the run with a config error.

    arch: D16.3
    """
    (tmp_path / "ref_check.toml").write_text(
        f"[targets.arch]\naccepted = {value}\n", encoding="utf-8"
    )
    with pytest.raises(ref_check.ConfigError):
        load_config(tmp_path)


def test_a_malformed_marker_at_a_matched_position_is_a_warning(tmp_path, fake_change):
    """A `malformed` failure at a matched position warns, like `unknown-id`.

    arch: D16.3, I-58
    """
    root = _tree(tmp_path)
    (root / "src" / "lib.rs").write_text("/// arch: x\nfn f() {}\n", encoding="utf-8")
    report = run(root)
    assert report.failures == []
    assert [(name, f.kind) for name, f in report.warnings] == [(_CHANGE, "malformed")]


def test_a_failure_of_another_kind_stays_a_failure(tmp_path, monkeypatch):
    """A failure that is not about a marker is never a warning, even on a matched line.

    arch: D16.3, I-58
    """
    monkeypatch.setitem(ref_check.READER_CHANGES, _CHANGE, lambda _l, _p: True)
    root = _tree(tmp_path)
    (root / "src" / "lib.rs").unlink()
    (root / "src" / "run.sh").write_text("echo hi\n# arch: D9.9\n", encoding="utf-8")
    (root / "src" / "a.py").write_text(
        '"""Doc."""\nimport os  # noqa: F401\n', encoding="utf-8"
    )
    (root / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n[targets.arch]\naccepted = []\n",
        encoding="utf-8",
    )
    report = run(root)
    assert [(f.kind, f.path, f.line) for f in report.failures] == [
        ("no-reason", "src/a.py", 2),
        ("no-header", "src/run.sh", 1),
    ]
    assert [f.kind for _, f in report.warnings] == ["unknown-id"]


def test_the_change_kinds_are_the_marker_kinds():
    """These five kinds warn by kind; `unreadable` warns only from a marker.

    arch: D16.3
    """
    assert ref_check._CHANGE_KINDS == {
        "unknown-id",
        "no-target",
        "malformed",
        "unregistered",
        "drift",
    }


@_MARKER_READS
def test_a_read_that_a_marker_asked_for_is_a_warning(
    tmp_path, fake_change, pinned, newest
):
    """An `unreadable` failure from a marker at a matched position warns.

    arch: D16.3, I-58
    """
    report = run(_law_tree(tmp_path, pinned, newest))
    assert report.failures == []
    assert [(name, f.kind, f.path, f.line) for name, f in report.warnings] == [
        (_CHANGE, "unreadable", "src/lib.rs", 1)
    ]


@_MARKER_READS
def test_an_accepted_change_fails_on_a_marker_read(
    tmp_path, fake_change, pinned, newest
):
    """After the target accepts the change, the `unreadable` failure fails.

    arch: D16.3, I-58
    """
    report = run(_law_tree(tmp_path, pinned, newest, accepted=True))
    assert [(f.kind, f.path, f.line) for f in report.failures] == [
        ("unreadable", "src/lib.rs", 1)
    ]
    assert report.warnings == []


def test_an_unreadable_from_another_check_stays_a_failure(
    tmp_path, fake_change, monkeypatch
):
    """An `unreadable` failure of another check stays a failure on a matched line.

    arch: D16.3, I-58
    """
    other = ref_check.Failure(
        "src/lib.rs", 1, "unreadable", "file cannot be read: OSError"
    )
    monkeypatch.setattr(ref_check, "_check_g", lambda _root, _config: [other])
    root = _tree(tmp_path)
    (root / "src" / "lib.rs").write_text(
        "/// arch: D1.1\nfn f() {}\n", encoding="utf-8"
    )
    report = run(root)
    assert report.failures == [other]
    assert report.warnings == []
