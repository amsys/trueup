"""Tests for the dirty-tree refusal, `--allow-dirty` and the run-date stamp of `apply` (arch: D12.2)."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest
from test_apply import _git, _messy
from test_move import _repo

from trueup import apply as apply_mod
from trueup import changes, cli, config, report

TODAY = date(2026, 10, 10)
"""The run date of every `apply` call here."""

LAST_LINE = "trueup: commit or stash them, or pass --allow-dirty"
"""The last refusal line (D12.2)."""


FAKE_KEY = "AKIA" + "QY7TM2PL" + "ZK4XW6RB"
"""A key-shaped value built at run time, so the `.env` row is automatic (D15.10)."""


def _committed_messy(tmp_path: Path) -> Path:
    """Build the messy fixture with every file committed, so the tree is clean.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    root = _messy(tmp_path)
    # D15.9: a compound scratch name is manual, so use a whole-stem name.
    (root / "tmp.md").write_text(
        (root / "tmp-draft.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "tmp-draft.md").unlink()
    # D15.10: only a `.env` that holds a secret is automatic.
    (root / ".env").write_text(f"KEY={FAKE_KEY}\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _run(root: Path, *ids: str, allow_dirty: bool = False) -> int:
    """Run `apply --ids` with a fixed date.

    Args:
        root: The target root.
        *ids: The finding ids.
        allow_dirty: Pass `--allow-dirty`.

    Returns:
        The exit code.
    """
    return apply_mod.run(
        root,
        ids=list(ids),
        all_auto=False,
        mode_args=[],
        set_args=[],
        today=TODAY,
        allow_dirty=allow_dirty,
    )


def _run_all_auto(root: Path) -> int:
    """Run `apply --all-auto` with a fixed date.

    Args:
        root: The target root.

    Returns:
        The exit code.
    """
    return apply_mod.run(
        root, ids=None, all_auto=True, mode_args=[], set_args=[], today=TODAY
    )


def test_dirty_paths_lists_modified_untracked_and_both_rename_sides(
    tmp_path: Path,
) -> None:
    """`dirty_paths` holds a modified file, an untracked file and both sides of a rename.

    arch: D12.2
    """
    root = _repo(tmp_path, {"a.md": "a\n", "b.md": "b\n", "c.md": "c\n"})
    (root / "a.md").write_text("changed\n", encoding="utf-8")
    (root / "new.md").write_text("new\n", encoding="utf-8")
    _git(root, "mv", "c.md", "d.md")
    assert changes.dirty_paths(root) == {"a.md", "new.md", "c.md", "d.md"}


def test_dirty_paths_is_empty_outside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dirty_paths` raises where no git work tree exists; D15.2 inverts the empty set.

    The test name is from before that decision.

    arch: D12.2, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(config.ConfigError):
        changes.dirty_paths(tmp_path)


def test_apply_refuses_a_finding_path_with_uncommitted_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dirty scratch file gives exit 2, two refusal lines and no write.

    arch: D12.2, I-41
    """
    root = _committed_messy(tmp_path)
    (root / "tmp.md").write_text("edited by hand\n", encoding="utf-8")
    assert _run(root, "scratch:tmp.md") == 2
    err = capsys.readouterr().err.splitlines()
    assert err == [
        "trueup: tmp.md has changes that are not committed",
        LAST_LINE,
    ]
    assert (root / "tmp.md").read_text(encoding="utf-8") == "edited by hand\n"
    assert not (root / "trueup.toml").exists()
    tracked = subprocess.run(
        ["git", "ls-files", "--", "tmp.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked.strip() == "tmp.md"


def test_apply_refuses_a_side_file_with_uncommitted_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dirty `.gitignore` blocks a finding that appends to it.

    arch: D12.2, I-41
    """
    root = _committed_messy(tmp_path)
    (root / ".gitignore").write_text("mine\n", encoding="utf-8")
    assert _run(root, "secret-file:.env") == 2
    assert ".gitignore has changes that are not committed" in capsys.readouterr().err
    assert (root / ".gitignore").read_text(encoding="utf-8") == "mine\n"


def test_allow_dirty_lets_the_run_continue(tmp_path: Path) -> None:
    """With `allow_dirty` the same dirty tree is handled.

    arch: D12.2
    """
    root = _committed_messy(tmp_path)
    (root / ".env").write_text(f"KEY={FAKE_KEY} edited\n", encoding="utf-8")
    assert _run(root, "secret-file:.env") == 2
    assert _run(root, "secret-file:.env", allow_dirty=True) == 0


def test_a_dirty_path_the_run_does_not_touch_is_no_reason_to_refuse(
    tmp_path: Path,
) -> None:
    """A dirty file outside the touched set does not stop the run.

    arch: D12.2
    """
    root = _committed_messy(tmp_path)
    (root / "README.md").write_text("# edited\n", encoding="utf-8")
    assert _run(root, "scratch:tmp.md") == 0


def test_move_refuses_a_dirty_page_whose_link_it_would_rewrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A move touches each Markdown page whose links it rewrites.

    arch: D12.2, I-41
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n\nSee [notes](NOTES.md).\n",
            "NOTES.md": "# Notes\n",
            "LICENSE.md": "licence\n",
        },
    )
    (root / "README.md").write_text(
        "# Readme\n\nSee [notes](NOTES.md). Mine.\n", encoding="utf-8"
    )
    assert _run(root, "move:NOTES.md") == 2
    assert "README.md has changes that are not committed" in capsys.readouterr().err
    assert (root / "NOTES.md").is_file()
    assert _run(root, "move:NOTES.md", allow_dirty=True) == 0
    assert "(docs/NOTES.md)" in (root / "README.md").read_text(encoding="utf-8")


def test_move_refuses_a_dirty_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dirty file that a move would relocate stops the run.

    arch: D12.2, I-41
    """
    root = _repo(
        tmp_path,
        {"README.md": "# Readme\n", "NOTES.md": "# Notes\n", "LICENSE.md": "l\n"},
    )
    (root / "NOTES.md").write_text("# Notes\n\nunsaved thought\n", encoding="utf-8")
    assert _run(root, "move:NOTES.md") == 2
    assert "NOTES.md has changes that are not committed" in capsys.readouterr().err
    assert not (root / "docs").exists()


def test_a_dirty_managed_file_with_the_header_is_not_a_conflict(
    tmp_path: Path,
) -> None:
    """The output of an earlier run is exempt, so a second run on the same file works.

    arch: D12.2, D14.8, I-41
    """
    root = _committed_messy(tmp_path)
    (root / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\n\n[refs]\nmode = "copy"\n', encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    assert _run_all_auto(root) == 0
    target = "ref_check.py"
    assert target in changes.dirty_paths(root), "the first run wrote no managed file"
    original = (root / target).read_bytes()
    (root / target).write_bytes(original + b"\n# edited by hand\n")
    ids = [
        finding.id
        for finding in report.collect(root).plan
        if finding.rule == "file-managed" and finding.path == target
    ]
    assert ids, "the stale managed file gives no finding"
    assert _run(root, *ids) == 0
    assert (root / target).read_bytes() == original


def test_stamp_edits_only_the_run_date_line(tmp_path: Path) -> None:
    """The stamp keeps a hand-made comment in a dirty `trueup.toml` and counts as no touch.

    arch: D12.2
    """
    root = _committed_messy(tmp_path)
    (root / "trueup.toml").write_text(
        'version = 1\nrun_date = "2026-01-01"\n# my own note\n', encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    text = (root / "trueup.toml").read_text(encoding="utf-8")
    (root / "trueup.toml").write_text(text + "# unsaved note\n", encoding="utf-8")
    assert _run(root, "scratch:tmp.md") == 0
    after = (root / "trueup.toml").read_text(encoding="utf-8")
    assert after == (
        'version = 1\nrun_date = "2026-10-10"\n# my own note\n# unsaved note\n'
    )
    assert config.load(root).run_date == "2026-10-10"


def test_cli_passes_allow_dirty(tmp_path: Path) -> None:
    """`trueup apply --allow-dirty` reaches `apply.run`.

    arch: D12.2
    """
    root = _committed_messy(tmp_path)
    (root / ".env").write_text(f"KEY={FAKE_KEY} edited\n", encoding="utf-8")
    argv = ["apply", "--root", str(root), "--ids", "secret-file:.env"]
    assert cli.main(argv) == 2
    assert cli.main([*argv, "--allow-dirty"]) == 0


def test_dirty_paths_outside_git_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a work tree `dirty_paths` raises instead of reporting a clean tree.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(config.ConfigError, match="git rev-parse failed"):
        changes.dirty_paths(tmp_path)
