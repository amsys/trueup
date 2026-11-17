"""The self-check of I-27: `check` on a copy of this repository gives an empty plan.

The test copies the files of this repository that a commit of the working
tree holds into `tmp_path`, commits them, and runs `report.collect` in
process. The developer's dirty tree, the git index and the ignored files
of this checkout stay out of the run (D15.38).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from trueup import report

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str) -> str:
    """Run one git command, with a fixed signer and no signing.

    Args:
        root: The repository to run in.
        *args: The git arguments after `git`.

    Returns:
        The standard output of the command.
    """
    return subprocess.run(
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
    ).stdout


def _committable(root: Path) -> list[str]:
    """Give the paths that `git add -A` and a commit would hold.

    Args:
        root: The repository.

    Returns:
        The tracked paths and the untracked paths that no ignore rule
        names, each present in the working tree.
    """
    listed = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [
        rel for rel in sorted(set(listed.split("\0"))) if rel and (root / rel).is_file()
    ]


def test_check_on_a_committed_copy_of_this_repository_has_an_empty_plan(
    tmp_path: Path,
) -> None:
    """I-27: `check` on a committed copy of this repository finds nothing to do.

    arch: I-27
    arch: D15.38
    """
    copy = tmp_path / "trueup"
    for rel in _committable(REPO_ROOT):
        target = copy / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, target, follow_symlinks=False)
    _git(copy, "init", "-q")
    _git(copy, "add", "-A")
    _git(copy, "commit", "-q", "-m", "copy")
    run = report.collect(copy)
    assert [finding.id for finding in run.plan] == []
