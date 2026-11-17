"""Tests for path names that are not UTF-8: git readers and output streams (arch: D12.10)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from trueup import apply, hygiene, layout, survey

_BAD_DOC = b"caf\xe9.md"
_BAD_TMP = b"x\xe9.tmp"


def _git(root: Path, *args: str) -> None:
    """Run one git command in the test repository with a fixed signer."""
    subprocess.run(
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
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r"""Build a repository that tracks `caf\\xe9.md` and `x\\xe9.tmp`."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_text(
        "# Demo\n\nSee [cafe](docs/x.md).\n", encoding="utf-8"
    )
    for raw in (_BAD_DOC, _BAD_TMP):
        with open(os.path.join(os.fsencode(root), raw), "wb") as handle:
            handle.write(b"# Note\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_tracked_paths_keep_the_bad_bytes(repo: Path) -> None:
    """arch: D12.10. `_tracked_paths` decodes with surrogateescape and loses no byte."""
    paths = hygiene._tracked_paths(repo)
    assert os.fsdecode(_BAD_DOC) in paths
    assert os.fsdecode(_BAD_TMP) in paths


def test_list_files_keep_the_bad_bytes(repo: Path) -> None:
    """arch: D12.10. `survey._list_files` uses -z and returns the bad names whole."""
    files = survey._list_files(repo, ())
    assert os.fsdecode(_BAD_DOC) in files
    assert os.fsdecode(_BAD_TMP) in files


def test_history_renames_do_not_crash(repo: Path) -> None:
    """arch: D12.10. `_history_renames` reads a rename of a bad name."""
    _git(repo, "mv", os.fsdecode(_BAD_DOC), "renamed.md")
    _git(repo, "commit", "-q", "-m", "rename")
    renames = layout._history_renames(repo)
    assert renames["renamed.md"][0] == os.fsdecode(_BAD_DOC)


def test_staged_rename_of_bad_name_is_read(repo: Path) -> None:
    """arch: D12.10. `_history_renames` decodes a staged rename of a bad name."""
    _git(repo, "mv", os.fsdecode(_BAD_DOC), "renamed.md")
    renames = layout._history_renames(repo)
    assert renames["renamed.md"][0] == os.fsdecode(_BAD_DOC)


def test_apply_git_keeps_the_bad_bytes(repo: Path) -> None:
    """arch: D12.10. `apply._git` decodes git output with surrogateescape."""
    ctx = apply._Context.__new__(apply._Context)
    ctx.root = repo
    result = apply._git(ctx, ["ls-files", "-z"])
    assert os.fsdecode(_BAD_DOC) in result.stdout.split("\0")


_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run `python3 -m trueup` as a process, so the real streams are in use."""
    return subprocess.run(
        ["python3", "-m", "trueup", *args], cwd=_ROOT, capture_output=True
    )


@pytest.mark.parametrize("as_json", [False, True])
def test_check_prints_bad_names(repo: Path, as_json: bool) -> None:
    """arch: D12.10. `check` Markdown and JSON do not crash on a bad name."""
    result = _run_cli("check", "--root", str(repo), *(["--json"] if as_json else []))
    assert b"Traceback" not in result.stderr, result.stderr
    assert result.returncode in (0, 1)


def test_apply_moves_a_bad_name(repo: Path) -> None:
    """arch: D12.10. `apply --ids move:<bad name>` moves the file and does not crash."""
    move_id = "move:" + os.fsdecode(_BAD_DOC)
    plan = _run_cli("check", "--root", str(repo), "--json")
    assert move_id in [m["id"] for m in json.loads(plan.stdout)["moves"]]
    result = _run_cli("apply", "--root", str(repo), "--ids", move_id)
    assert b"Traceback" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert os.path.exists(os.path.join(os.fsencode(repo), b"docs", _BAD_DOC))
    assert not os.path.exists(os.path.join(os.fsencode(repo), _BAD_DOC))


def test_check_out_writes_bad_names(repo: Path, tmp_path: Path) -> None:
    """arch: D12.10. `check --out` writes its report files without a crash."""
    out = tmp_path / "out"
    result = _run_cli("check", "--root", str(repo), "--out", str(out))
    assert b"Traceback" not in result.stderr, result.stderr
    assert any(out.iterdir())


def test_code_mentions_print_bad_names(repo: Path) -> None:
    """arch: D12.10. A code file with a bad name that holds the old path prints through `main`."""
    with open(os.path.join(os.fsencode(repo), b"c\xe9.py"), "wb") as handle:
        handle.write(b"# see old/page.md\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "code")
    script = (
        "import sys; from pathlib import Path; from trueup import apply;"
        "sys.stdout.reconfigure(errors='surrogateescape');"
        "ctx = apply._Context.__new__(apply._Context); ctx.root = Path(sys.argv[1]);"
        "apply._print_code_mentions(ctx, 'old/page.md')"
    )
    result = subprocess.run(
        ["python3", "-c", script, str(repo)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert b"c\xe9.py:1" in result.stdout
