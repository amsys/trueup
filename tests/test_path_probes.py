"""Tests that a path below an unreadable directory does not raise (D16.1)."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from trueup import cli
from trueup.ref_check import run


@pytest.fixture
def locked_repo(tmp_path: Path) -> Iterator[Path]:
    """Make a repository that tracks a file below a mode-000 directory.

    Args:
        tmp_path: The test directory.

    Yields:
        The repository root. The directory is made readable again after the test.
    """
    if os.geteuid() == 0:
        pytest.skip("root reads a mode-000 directory")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n\nText.\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text("", encoding="utf-8")
    locked = tmp_path / "src" / "locked"
    locked.mkdir(parents=True)
    (locked / "hidden.py").write_text('"""Hidden."""\n', encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    locked.chmod(0)
    try:
        yield tmp_path
    finally:
        locked.chmod(0o755)


@pytest.mark.parametrize("command", ["check", "lint"])
def test_a_command_does_not_raise_below_an_unreadable_directory(
    locked_repo: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup check` and `trueup lint` give no internal error for a locked tree.

    arch: D16.1
    """
    code = cli.main([command, "--root", str(locked_repo)])
    assert code != 2
    assert "internal error" not in capsys.readouterr().err


def test_ref_check_does_not_raise_below_an_unreadable_directory(
    locked_repo: Path,
) -> None:
    """`ref_check.run` returns a report for a locked tree.

    arch: D16.1
    """
    report = run(locked_repo)
    assert report is not None
