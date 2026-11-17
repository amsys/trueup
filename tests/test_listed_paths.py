"""Tests for the paths that `git status` lists: no FIFO or device reaches git or tokei (D16.10)."""

from __future__ import annotations

import contextlib
import hashlib
import os
import resource
import shutil
import signal
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from trueup import changes, cli, survey

_TIME_LIMIT_SECONDS = 30
"""The longest time one case may run, so a hang fails."""

_MEMORY_LIMIT_BYTES = 4 * 1024 * 1024 * 1024
"""The address space one case may use. Child processes get the same limit,
so a read of /dev/zero fails and does not take the memory of the machine."""


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


def _git(root: Path, *args: str) -> str:
    """Run one git command in a test repository.

    Args:
        root: The repository root.
        *args: The git subcommand and its arguments.

    Returns:
        The standard output of the command.
    """
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _house_repo(tmp_path: Path) -> Path:
    """Make a committed repository with the `house` profile below `tmp_path`.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root, `tmp_path / "repo"`.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    (root / "a.py").write_text('"""A module."""\n\nX = 1\n', encoding="utf-8")
    (root / "README.md").write_text("# Repo\n\nA test repository.\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_an_untracked_fifo_symlink_does_not_hang_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup check` ends when `git status` lists an untracked symlink to a FIFO.

    Nothing is staged: a plain `ln -s` is enough (case U1).

    arch: D16.10, I-50
    """
    root = _house_repo(tmp_path)
    os.mkfifo(tmp_path / "pipe")
    (root / "y.md").symlink_to("../pipe")

    with _bounded_case():
        code = cli.main(["check", "--root", str(root)])

    assert code in (0, 1), capsys.readouterr().err


def test_a_staged_dev_zero_symlink_does_not_fail_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup check` ends with a report when a staged symlink points to /dev/zero.

    Before this row, git read /dev/zero until it ran out of memory (case D2).

    arch: D16.10, I-50
    """
    root = _house_repo(tmp_path)
    (root / "zero.md").symlink_to("/dev/zero")
    _git(root, "add", "zero.md")

    with _bounded_case():
        code = cli.main(["check", "--root", str(root)])

    err = capsys.readouterr().err
    assert code in (0, 1), err
    assert "hash-object" not in err


def test_a_gitignore_fifo_symlink_stops_tokei_at_its_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With tokei on the path, a `.gitignore -> ../pipe` ends the survey at the limit.

    The survey then counts with the built-in counter, as with no tokei, and
    the run prints one line that names tokei and the limit (case GI).

    arch: D16.10, I-50
    """
    if shutil.which("tokei") is None:
        pytest.skip("tokei is not installed, so the .gitignore FIFO case cannot run")
    root = _house_repo(tmp_path)
    os.mkfifo(tmp_path / "pipe")
    (root / ".gitignore").symlink_to("../pipe")
    monkeypatch.setattr(survey, "TOKEI_TIMEOUT_S", 2, raising=False)

    with _bounded_case():
        code = cli.main(["check", "--root", str(root)])
        run_err = capsys.readouterr().err
        stats, counter = survey._language_stats(root, ("a.py",))

    assert code in (0, 1), run_err
    tokei_lines = [line for line in run_err.splitlines() if "tokei" in line]
    assert len(tokei_lines) == 1, run_err
    assert "2 s" in tokei_lines[0]
    assert counter == "built-in"
    assert stats["python"].files == 1


def test_the_identity_of_a_regular_file_is_unchanged(tmp_path: Path) -> None:
    """A tree of regular files keeps the identity of the round before, so a saved plan still applies.

    The expected digest is built here from the formula of D12.1: the raw
    `git status` bytes, then the `git hash-object` sha of each listed file.

    arch: D16.10, D12.1
    """
    root = _house_repo(tmp_path)
    (root / "a.py").write_text('"""A module."""\n\nX = 2\n', encoding="utf-8")
    (root / "new.md").write_text("# New\n", encoding="utf-8")
    raw = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    shas = _git(root, "hash-object", "--no-filters", "a.py", "new.md").split()
    expected = hashlib.sha256(
        raw + b"\0" + b"\0".join(sha.encode("ascii") for sha in shas)
    ).hexdigest()

    identity = changes.tree_identity(root)

    assert identity is not None
    assert identity["status"] == expected


def test_a_symlink_gets_the_blob_sha_of_its_link_text(tmp_path: Path) -> None:
    """A listed symlink is never opened: its sha is the one git stores for the link.

    A new link target of an untracked link changes the tree identity,
    though the `git status` line of the link stays the same.

    arch: D16.10
    """
    root = _house_repo(tmp_path)
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    (root / "c.txt").write_text("c\n", encoding="utf-8")
    _git(root, "add", "b.txt", "c.txt")
    _git(root, "commit", "-q", "-m", "targets")
    (root / "staged.txt").symlink_to("b.txt")
    _git(root, "add", "staged.txt")
    stored = _git(root, "ls-files", "-s", "staged.txt").split()[1]
    assert changes._blob_shas(root, ["staged.txt"]) == [stored]

    (root / "link.txt").symlink_to("b.txt")
    first = changes.tree_identity(root)
    (root / "link.txt").unlink()
    (root / "link.txt").symlink_to("c.txt")
    assert changes.tree_identity(root) != first
