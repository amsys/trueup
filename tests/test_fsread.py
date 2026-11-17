"""Tests for `trueup.fsread`: the bounded reader (D15.22)."""

from __future__ import annotations

import builtins
import contextlib
import io
import os
import resource
import signal
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from trueup import apply as apply_mod
from trueup import baseline, docrules, fsread, health, managed, report

_TIME_LIMIT_SECONDS = 60
"""The longest time one bounded-read case may run, so a hang fails."""

_ONE_MIB = 1024 * 1024
"""The cap of a text read, as the reference page states it (D16.10)."""

_PRESENT_CODE_LINES = 60
"""A size over the survey limit, so Python counts as present and the
baseline measures the docstring ratchet."""

_MEMORY_LIMIT_BYTES = 4 * 1024 * 1024 * 1024
"""The address space one bounded-read case may use, so a read of /dev/zero
fails with MemoryError and does not take the memory of the machine."""


class _TimeLimitExpired(BaseException):
    """The case ran past its time limit. No `except OSError` in the code can catch it."""


@contextlib.contextmanager
def _bounded_case() -> Iterator[None]:
    """Fail the enclosed code on a hang or on an unbounded read.

    Yields:
        Nothing. The time limit and the memory limit hold in the block.
    """

    def expired(_signum: int, _frame: object) -> None:
        raise _TimeLimitExpired("the case passed its time limit")

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    previous = signal.signal(signal.SIGALRM, expired)
    resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, hard))
    signal.alarm(_TIME_LIMIT_SECONDS)
    try:
        yield
    finally:
        signal.alarm(0)
        resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
        signal.signal(signal.SIGALRM, previous)


def _record_opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every path that `open`, `io.open` and `os.open` get from now on.

    `pathlib.Path` calls `io.open`, so a spy on `builtins.open` alone does
    not see `Path.read_text` or `Path.read_bytes`.

    Args:
        monkeypatch: The pytest fixture that replaces these functions.

    Returns:
        The list that receives each path.
    """
    opened: list[str] = []
    real_open = builtins.open
    real_os_open = os.open

    def spy_open(file: object, *args: object, **kwargs: object) -> object:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    def spy_os_open(path: object, *args: object, **kwargs: object) -> int:
        opened.append(str(path))
        return real_os_open(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    return opened


def _commit_all(root: Path) -> None:
    """Stage every file of a test repository and commit it.

    Args:
        root: The repository root.
    """
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        cwd=root,
        check=True,
    )


def test_read_capped_returns_a_file_within_the_cap(tmp_path: Path) -> None:
    """A file at or under the cap comes back whole; one byte over gives None.

    arch: D15.22, I-50
    """
    (tmp_path / "a.txt").write_bytes(b"12345")
    assert fsread.read_capped(tmp_path, "a.txt", 5) == b"12345"
    assert fsread.read_capped(tmp_path, "a.txt", 4) is None
    assert fsread.read_text_capped(tmp_path, "a.txt", 5) == "12345"


def test_read_head_has_no_length_limit(tmp_path: Path) -> None:
    """`read_head` gives the first n bytes of a longer file.

    arch: D15.22
    """
    (tmp_path / "a.bin").write_bytes(b"abcdef" * 1000)
    assert fsread.read_head(tmp_path, "a.bin", 4) == b"abcd"


def test_missing_path_and_directory_give_none(tmp_path: Path) -> None:
    """A path `lstat` cannot see, or a directory, gives None.

    arch: D15.22
    """
    (tmp_path / "d").mkdir()
    assert fsread.read_capped(tmp_path, "missing", 10) is None
    assert fsread.read_head(tmp_path, "d", 10) is None


def test_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    """A FIFO gives None and does not block.

    arch: D15.22, I-50
    """
    os.mkfifo(tmp_path / "pipe")
    assert fsread.read_head(tmp_path, "pipe", 10) is None


def test_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """A symlink to a file outside the root or to a device gives None; one inside is read.

    arch: D15.22, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    (root / "inside.txt").write_text("ok", encoding="utf-8")
    (root / "out.txt").symlink_to(tmp_path / "outside.txt")
    (root / "zero.txt").symlink_to("/dev/zero")
    (root / "in.txt").symlink_to("inside.txt")
    assert fsread.read_capped(root, "out.txt", 100) is None
    assert fsread.read_head(root, "zero.txt", 10) is None
    assert fsread.read_capped(root, "in.txt", 100) == b"ok"


@pytest.mark.parametrize("house", [False, True], ids=["no-config", "house"])
def test_a_run_over_symlinks_opens_neither_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, house: bool
) -> None:
    """`report.collect` ends on tracked symlinks to /dev/zero and to a file outside; neither is opened.

    With no `trueup.toml` the run has the `minimal` profile, which reads no
    prose. Under `house` the prose row and the page rows read every page.

    arch: D15.20, D15.22, D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "real.md").write_text("# Real\n", encoding="utf-8")
    if house:
        (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside\n", encoding="utf-8")
    for name, target in (
        ("zero.txt", "/dev/zero"),
        ("outside.txt", str(tmp_path / "outside.txt")),
        ("zero.md", "/dev/zero"),
        ("zero.py", "/dev/zero"),
        ("README.md", "/dev/zero"),
        ("CHANGELOG.md", "/dev/zero"),
        ("package.json", "/dev/zero"),
        ("docs/page.md", "/dev/zero"),
    ):
        (root / name).symlink_to(target)
    subprocess.run(["git", "add", "."], cwd=root, check=True)

    opened = _record_opens(monkeypatch)
    with _bounded_case():
        report.collect(root)

    joined = "\n".join(opened)
    assert "/dev/zero" not in joined
    assert str(tmp_path / "outside.txt") not in joined
    assert not [
        path
        for path in opened
        if Path(path).name
        in {
            "zero.txt",
            "outside.txt",
            "zero.md",
            "zero.py",
            "README.md",
            "CHANGELOG.md",
            "package.json",
            "page.md",
        }
        and Path(path).parent in {root, root / "docs"}
    ]


def test_a_house_run_opens_no_managed_or_health_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`report.collect` opens no managed or health path that is a symlink out of the root.

    The run reads `.gitignore`, `README.md`, the copy-mode checker and each
    legacy path. These sites first ask `is_file`, so the target is a regular
    file: a device stops at that test and proves nothing.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "trueup.toml").write_text(
        'profile = "house"\n\n[refs]\nmode = "copy"\n', encoding="utf-8"
    )
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    links = {".gitignore", "README.md", "ref_check.py", *managed.LEGACY_PATHS}
    links.discard(managed.ESLINT_PACKAGES_DIR)
    for name in links:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).symlink_to(outside)
    subprocess.run(["git", "add", "."], cwd=root, check=True)

    opened = _record_opens(monkeypatch)
    with _bounded_case():
        report.collect(root)

    assert str(outside) not in opened
    assert not [
        path for path in opened if Path(path) in {root / name for name in links}
    ]


def test_a_baseline_over_symlinks_ends_and_opens_neither_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`baseline.write` under `house` ends on `.py` symlinks to a device and to a FIFO.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "trueup.toml").write_text(
        'profile = "house"\n\n[languages]\npython = "clean"\n', encoding="utf-8"
    )
    code_lines = "".join(f"VALUE_{n} = {n}\n" for n in range(_PRESENT_CODE_LINES))
    (root / "real.py").write_text(f'"""A module."""\n{code_lines}', encoding="utf-8")
    os.mkfifo(tmp_path / "pipe")
    (root / "zero.py").symlink_to("/dev/zero")
    (root / "pipe.py").symlink_to(tmp_path / "pipe")
    _commit_all(root)

    opened = _record_opens(monkeypatch)
    with _bounded_case():
        baseline.write(root)

    written = baseline.load(root)
    assert written is not None
    assert written["ratchet"]["python"]["docstring"] == 100.0
    assert "/dev/zero" not in "\n".join(opened)
    assert not [path for path in opened if Path(path).name in {"zero.py", "pipe.py"}]


def test_a_move_over_symlinks_ends_and_rewrites_the_real_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `move:` id under `house` ends on Markdown symlinks and still rewrites a real page.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    (root / "README.md").write_text(
        "# Readme\n\nSee [notes](NOTES.md) for more.\n", encoding="utf-8"
    )
    (root / "NOTES.md").write_text("# Notes\n\ncontent\n", encoding="utf-8")
    os.mkfifo(tmp_path / "pipe")
    (root / "zero.md").symlink_to("/dev/zero")
    (root / "pipe.md").symlink_to(tmp_path / "pipe")
    _commit_all(root)

    opened = _record_opens(monkeypatch)
    with _bounded_case():
        code = apply_mod.run(
            root, ids=["move:NOTES.md"], all_auto=False, mode_args=[], set_args=[]
        )

    assert code == 0
    assert (root / "docs" / "NOTES.md").is_file()
    assert "[notes](docs/NOTES.md)" in (root / "README.md").read_text(encoding="utf-8")
    assert "/dev/zero" not in "\n".join(opened)
    assert not [path for path in opened if Path(path).name in {"zero.md", "pipe.md"}]


def test_a_move_refuses_a_page_link_out_of_the_root_and_opens_no_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `move:` id stops at a Markdown symlink to a file outside; the file is not opened.

    arch: D16.10, I-50, I-51
    """
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    (root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (root / "NOTES.md").write_text("# Notes\n\ncontent\n", encoding="utf-8")
    (tmp_path / "outside.md").write_text("[notes](NOTES.md)\n", encoding="utf-8")
    (root / "out.md").symlink_to(tmp_path / "outside.md")
    _commit_all(root)

    opened = _record_opens(monkeypatch)
    with _bounded_case():
        code = apply_mod.run(
            root, ids=["move:NOTES.md"], all_auto=False, mode_args=[], set_args=[]
        )

    assert code != 0
    assert (root / "NOTES.md").is_file()
    assert not [path for path in opened if Path(path).name == "outside.md"]
    assert (tmp_path / "outside.md").read_text(
        encoding="utf-8"
    ) == "[notes](NOTES.md)\n"


def _move_repo(root: Path) -> None:
    """Make a repository that has one page to move, `NOTES.md`.

    Args:
        root: The directory to make. The caller adds pages and commits.
    """
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    (root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (root / "NOTES.md").write_text("# Notes\n\ncontent\n", encoding="utf-8")


def _run_note_move(root: Path) -> int:
    """Approve the `move:` id of `NOTES.md`, under the time and memory limits.

    Args:
        root: The repository.

    Returns:
        The exit code of the run.
    """
    with _bounded_case():
        return apply_mod.run(
            root, ids=["move:NOTES.md"], all_auto=False, mode_args=[], set_args=[]
        )


def _page_of_size(size: int) -> bytes:
    """Give a Markdown page of exactly `size` bytes with one link to `NOTES.md`.

    Args:
        size: The length of the page in bytes.

    Returns:
        The bytes of the page.
    """
    head = b"[notes](NOTES.md)\n"
    return head + b"x" * (size - len(head))


def test_a_move_refuses_a_page_over_the_cap_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `move:` id stops at a regular page that the cap hides, so no link breaks silently.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    _move_repo(root)
    page = _page_of_size(_ONE_MIB + 1)
    (root / "BIG.md").write_bytes(page)
    _commit_all(root)

    code = _run_note_move(root)

    assert code != 0
    assert (root / "NOTES.md").is_file()
    assert not (root / "docs" / "NOTES.md").exists()
    assert (root / "BIG.md").read_bytes() == page
    output = capsys.readouterr().out
    assert "BIG.md" in output
    assert "over the read cap" in output


def test_a_move_refuses_a_link_to_a_page_over_the_cap_inside_the_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `move:` id stops at a symlink whose target inside the root is over the cap.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    _move_repo(root)
    (root / "big.txt").write_bytes(_page_of_size(_ONE_MIB + 1))
    (root / "link.md").symlink_to("big.txt")
    _commit_all(root)

    code = _run_note_move(root)

    assert code != 0
    assert not (root / "docs" / "NOTES.md").exists()
    output = capsys.readouterr().out
    assert "link.md" in output
    assert "over the read cap" in output


def test_a_move_still_rewrites_a_page_at_the_cap(tmp_path: Path) -> None:
    """A page of exactly the cap reads, so its link gets the rewrite.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    _move_repo(root)
    (root / "BIG.md").write_bytes(_page_of_size(_ONE_MIB))
    _commit_all(root)

    code = _run_note_move(root)

    assert code == 0
    assert (root / "docs" / "NOTES.md").is_file()
    assert (root / "BIG.md").read_bytes().startswith(b"[notes](docs/NOTES.md)\n")


def test_a_move_skips_a_page_that_does_not_decode(tmp_path: Path) -> None:
    """Bad bytes hold no link that the run can rewrite, in a page or behind a link.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    _move_repo(root)
    (root / "latin.md").write_bytes(b"caf\xe9 [notes](NOTES.md)\n")
    (root / "latin.txt").write_bytes(b"caf\xe9 [notes](NOTES.md)\n")
    (root / "link.md").symlink_to("latin.txt")
    _commit_all(root)

    code = _run_note_move(root)

    assert code == 0
    assert (root / "docs" / "NOTES.md").is_file()
    assert (root / "latin.md").read_bytes() == b"caf\xe9 [notes](NOTES.md)\n"


def test_read_text_refuses_what_the_rows_must_not_open(tmp_path: Path) -> None:
    """`docrules._read_text` gives no text for a FIFO, a device, an absent path or a long file.

    arch: D16.10, I-50
    """
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "at-cap.md").write_bytes(b"a" * _ONE_MIB)
    (tmp_path / "over-cap.md").write_bytes(b"a" * (_ONE_MIB + 1))
    (tmp_path / "crlf.md").write_bytes(b"one\r\ntwo\r\n")

    with _bounded_case():
        assert docrules._read_text(tmp_path / "pipe") is None
        assert docrules._read_text(Path("/dev/zero")) is None
    assert docrules._read_text(tmp_path / "absent.md") is None
    assert docrules._read_text(tmp_path / "over-cap.md") is None
    assert docrules._read_text(tmp_path / "at-cap.md") == "a" * _ONE_MIB
    assert docrules._read_text(tmp_path / "crlf.md") == "one\ntwo\n"


def test_read_page_stays_below_the_root(tmp_path: Path) -> None:
    """`docrules._read_page` refuses a path or a symlink out of the root, and a FIFO.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")
    (root / "link.md").symlink_to(tmp_path / "outside.md")
    (root / "page.md").write_text("# Page\n", encoding="utf-8")
    os.mkfifo(root / "pipe.md")

    with _bounded_case():
        assert docrules._read_page(root, root / "pipe.md") is None
    assert docrules._read_page(root, tmp_path / "outside.md") is None
    assert docrules._read_page(root, root / "link.md") is None
    assert docrules._read_page(root, root / "page.md") == "# Page\n"


def test_the_report_read_has_its_own_larger_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`baseline._read` reads a report over 1 MiB, and refuses a FIFO and a device.

    arch: D16.10, I-50
    """
    os.mkfifo(tmp_path / "pipe")
    report_text = "a" * (2 * _ONE_MIB)
    (tmp_path / "coverage.xml").write_text(report_text, encoding="utf-8")

    with _bounded_case():
        assert baseline._read(tmp_path / "pipe") is None
        assert baseline._read(Path("/dev/zero")) is None
    assert baseline._read(tmp_path / "absent.xml") is None
    assert baseline._read(tmp_path / "coverage.xml") == report_text

    monkeypatch.setattr(baseline, "_REPORT_READ_CAP", 2 * _ONE_MIB - 1)
    assert baseline._read(tmp_path / "coverage.xml") is None


def test_the_report_read_refuses_a_symlink_out_of_the_root(tmp_path: Path) -> None:
    """`baseline._read` gives no text for a report that links out of the root.

    A report that links to a file in the same directory is still read.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.xml").write_text("OUTSIDE", encoding="utf-8")
    (root / "coverage.xml").symlink_to(tmp_path / "outside.xml")
    (root / "real.info").write_text("INSIDE", encoding="utf-8")
    (root / "lcov.info").symlink_to("real.info")

    assert baseline._read(root / "coverage.xml") is None
    assert baseline._read(root / "lcov.info") == "INSIDE"


def test_the_claude_link_read_refuses_a_fifo_and_a_long_file(tmp_path: Path) -> None:
    """`health._claude_links_to_agents` does not block on a FIFO and reads no text over the cap.

    arch: D16.10, I-50
    """
    for name in ("fifo", "long", "short"):
        (tmp_path / name).mkdir()
    os.mkfifo(tmp_path / "fifo" / "CLAUDE.md")
    (tmp_path / "long" / "CLAUDE.md").write_text(
        "@AGENTS.md\n" + "x" * (2 * _ONE_MIB), encoding="utf-8"
    )
    (tmp_path / "short" / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

    with _bounded_case():
        assert health._claude_links_to_agents(tmp_path / "fifo" / "CLAUDE.md") is False
    assert health._claude_links_to_agents(tmp_path / "long" / "CLAUDE.md") is False
    assert health._claude_links_to_agents(tmp_path / "short" / "CLAUDE.md") is True


def test_a_managed_file_that_links_out_of_the_root_does_not_stay(
    tmp_path: Path,
) -> None:
    """`managed._on_disk_stays` does not read a managed header through a symlink out of the root.

    The same header in a regular file inside the root keeps the path.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    (root / "lint").mkdir(parents=True)
    text = f"{managed.header_line('lint/x.toml')}\nx = 1\n"
    (tmp_path / "outside.toml").write_text(text, encoding="utf-8")
    (root / "lint" / "out.toml").symlink_to(tmp_path / "outside.toml")
    (root / "lint" / "in.toml").write_text(text, encoding="utf-8")

    assert managed._on_disk_stays(root, "lint/out.toml", "") is False
    assert managed._on_disk_stays(root, "lint/in.toml", "") is True


def test_a_dirty_managed_path_that_the_read_refuses_is_a_conflict(
    tmp_path: Path,
) -> None:
    """`_dirty_conflicts` does not open a FIFO symlink; the path stays a conflict.

    arch: D16.10, I-50
    """
    root = tmp_path / "repo"
    root.mkdir()
    os.mkfifo(tmp_path / "pipe")
    (root / "setup.cfg").symlink_to(tmp_path / "pipe")

    with _bounded_case():
        conflicts = apply_mod._dirty_conflicts(
            {"setup.cfg"}, frozenset({"setup.cfg"}), {"setup.cfg": "rendered"}, root
        )

    assert conflicts == ["setup.cfg"]
