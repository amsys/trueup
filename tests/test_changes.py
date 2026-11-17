"""Tests for `trueup.changes`: the D6.17 working-tree change set and the D6.2 session snapshot."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from trueup import changes
from trueup.config import ConfigError


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _commit(root: Path, message: str) -> None:
    """Stage every change under `root` and commit it, with signing off.

    Args:
        root: The repository to commit in.
        message: The commit message.
    """
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", message],
        cwd=root,
        check=True,
    )


def test_working_set_lists_untracked_files(tmp_path: Path) -> None:
    """A freshly initialised repository's files are all untracked (arch: D6.17).

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two\n", encoding="utf-8")
    assert changes.working_set(tmp_path) == frozenset({"a.txt", "b.txt"})


def test_working_set_lists_a_modified_tracked_file(tmp_path: Path) -> None:
    """A tracked file edited after its commit shows in the change set.

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    (tmp_path / "a.txt").write_text("one changed\n", encoding="utf-8")
    assert changes.working_set(tmp_path) == frozenset({"a.txt"})


def test_working_set_gives_no_path_for_an_unchanged_tracked_file(
    tmp_path: Path,
) -> None:
    """A committed file with no further edit does not show in the change set.

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    assert changes.working_set(tmp_path) == frozenset()


def test_working_set_drops_a_deleted_path(tmp_path: Path) -> None:
    """A path deleted from the working tree is left out, not reported as changed.

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two\n", encoding="utf-8")
    _commit(tmp_path, "add a and b")
    (tmp_path / "a.txt").unlink()
    assert changes.working_set(tmp_path) == frozenset()


def test_working_set_gives_the_new_path_of_a_rename(tmp_path: Path) -> None:
    """A renamed tracked file shows only its new path, not the old one.

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "old.txt").write_text("hello\n", encoding="utf-8")
    _commit(tmp_path, "add old")
    subprocess.run(["git", "mv", "old.txt", "new.txt"], cwd=tmp_path, check=True)
    assert changes.working_set(tmp_path) == frozenset({"new.txt"})


def test_working_set_excludes_an_ignored_file(tmp_path: Path) -> None:
    """A file matched by `.gitignore` never enters the change set.

    `git status`'s default output already leaves ignored files out, with no
    extra filtering needed on this side (arch: D6.17).

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    _commit(tmp_path, "add gitignore")
    (tmp_path / "ignored.log").write_text("noise\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("keep\n", encoding="utf-8")
    assert changes.working_set(tmp_path) == frozenset({"kept.txt"})


def test_working_set_uses_no_optional_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every git call `working_set` makes passes `--no-optional-locks` (arch: I-14).

    arch: I-14
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def _spy(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(changes.subprocess, "run", _spy)
    changes.working_set(tmp_path)
    assert calls
    assert all(call[:2] == ["git", "--no-optional-locks"] for call in calls)


def test_working_set_never_refreshes_the_git_index(tmp_path: Path) -> None:
    """`working_set` leaves `.git/index`'s mtime unchanged (arch: I-18, I-14).

    arch: I-18, I-14
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    (tmp_path / "a.txt").write_text("one changed\n", encoding="utf-8")
    index_path = tmp_path / ".git" / "index"
    before = index_path.stat().st_mtime_ns
    changes.working_set(tmp_path)
    assert index_path.stat().st_mtime_ns == before


def test_working_set_is_relative_to_a_subdirectory_root(tmp_path: Path) -> None:
    """A root below the repository top gives paths relative to that root, and only its own.

    arch: D6.17
    """
    _git_init(tmp_path)
    (tmp_path / "top.txt").write_text("top\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.txt").write_text("x\n", encoding="utf-8")
    assert changes.working_set(tmp_path / "sub") == frozenset({"x.txt"})


def test_working_set_outside_a_repository_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root with no git repository gives `ConfigError`, which the CLI maps to exit 2.

    arch: D6.17
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(ConfigError):
        changes.working_set(tmp_path)


def _session_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make a repository with one commit, and point `CLAUDE_PLUGIN_DATA` outside it.

    The commit holds `kept.txt` and `dirty.txt`. After the commit,
    `dirty.txt` is edited and `old_untracked.txt` is added, so both are
    dirt from before the session.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: The fixture that sets the environment variable.

    Returns:
        The repository root, `tmp_path / "repo"`.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    (root / "kept.txt").write_text("kept\n", encoding="utf-8")
    (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    _commit(root, "start")
    (root / "dirty.txt").write_text("dirty before the session\n", encoding="utf-8")
    (root / "old_untracked.txt").write_text("old\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    return root


def test_snapshot_path_needs_plugin_data_and_a_safe_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`snapshot_path` gives `None` with no `CLAUDE_PLUGIN_DATA` or an unsafe id.

    arch: D6.2, D6.3, D6.4
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    assert changes.snapshot_path("abc") is None
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    for bad in ("", "../x", "a/b", "a.b", "x" * 129, None):
        assert changes.snapshot_path(bad) is None, bad  # type: ignore[arg-type]
    assert changes.snapshot_path("ab_C-9") == tmp_path / "sessions" / "ab_C-9.json"


def test_write_snapshot_records_head_and_dirty_blob_shas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The snapshot holds the root, `HEAD` and one blob sha per dirty path.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    changes.write_snapshot(root, "s1")
    snapshot = changes.read_snapshot("s1")
    assert snapshot is not None
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    sha = subprocess.run(
        ["git", "hash-object", "dirty.txt"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert snapshot.root == str(root.resolve())
    assert snapshot.head == head
    assert set(snapshot.dirty) == {"dirty.txt", "old_untracked.txt"}
    assert snapshot.dirty["dirty.txt"] == sha
    assert snapshot.reminded == []
    assert list((tmp_path / "data" / "sessions").iterdir()) == [
        tmp_path / "data" / "sessions" / "s1.json"
    ]


def test_session_set_drops_unchanged_pre_session_dirt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dirt from before the session with an unchanged blob sha is not in `session_set`.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    changes.write_snapshot(root, "s1")
    assert changes.session_set(root, "s1") == frozenset()
    (root / "new_file.txt").write_text("new\n", encoding="utf-8")
    assert changes.session_set(root, "s1") == frozenset({"new_file.txt"})


def test_session_set_holds_edits_commits_and_drops_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edited dirt, a file committed in the session and a new file are in the set; a deleted file is not.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    changes.write_snapshot(root, "s1")
    (root / "dirty.txt").write_text("edited in the session\n", encoding="utf-8")
    (root / "committed.txt").write_text("c\n", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "in session"],
        cwd=root,
        check=True,
    )
    (root / "kept.txt").unlink()
    assert changes.session_set(root, "s1") == frozenset({"dirty.txt", "committed.txt"})


def test_session_set_falls_back_to_the_working_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No snapshot, a snapshot of another root, or no start commit give `working_set`.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    expected = changes.working_set(root)
    assert expected == frozenset({"dirty.txt", "old_untracked.txt"})
    assert changes.session_set(root, "none") == expected
    other = tmp_path / "other"
    other.mkdir()
    _git_init(other)
    (other / "x.txt").write_text("x\n", encoding="utf-8")
    _commit(other, "other")
    changes.write_snapshot(other, "s2")
    assert changes.session_set(root, "s2") == expected
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _git_init(fresh)
    (fresh / "a.txt").write_text("a\n", encoding="utf-8")
    changes.write_snapshot(fresh, "s3")
    snapshot = changes.read_snapshot("s3")
    assert snapshot is not None and snapshot.head == ""
    assert changes.session_set(fresh, "s3") == frozenset({"a.txt"})


def test_write_snapshot_prunes_files_older_than_seven_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write deletes other snapshot files older than 7 days and keeps newer ones.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    sessions = tmp_path / "data" / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / "old.json"
    recent = sessions / "recent.json"
    old.write_text("{}", encoding="utf-8")
    recent.write_text("{}", encoding="utf-8")
    eight_days_ago = time.time() - 8 * 24 * 60 * 60
    os.utime(old, (eight_days_ago, eight_days_ago))
    changes.write_snapshot(root, "s1")
    assert not old.exists()
    assert recent.exists()
    assert (sessions / "s1.json").exists()


def test_read_snapshot_rejects_a_broken_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad JSON, a wrong version or a missing root give `None`, not an error.

    arch: D6.2, D6.3, D6.4
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for text in ("{bad", '{"version": 2, "root": "/"}', '{"version": 1}', "[]"):
        (sessions / "s.json").write_text(text, encoding="utf-8")
        assert changes.read_snapshot("s") is None, text


def test_mark_reminded_adds_a_path_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mark_reminded` keeps the snapshot and adds each path one time.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    changes.write_snapshot(root, "s1")
    head = changes.read_snapshot("s1").head  # type: ignore[union-attr]
    assert changes.mark_reminded(root, "s1", "cli.py")
    assert changes.mark_reminded(root, "s1", "cli.py")
    snapshot = changes.read_snapshot("s1")
    assert snapshot is not None
    assert snapshot.reminded == ["cli.py"]
    assert snapshot.head == head
    assert changes.mark_reminded(root, "new", "x.py")
    assert changes.read_snapshot("new").head == ""  # type: ignore[union-attr]
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA")
    assert not changes.mark_reminded(root, "s1", "y.py")


def test_snapshot_git_calls_use_no_optional_locks_and_keep_the_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_snapshot` and `session_set` pass `--no-optional-locks` and leave `.git/index` as it is.

    arch: D6.2, D6.3, D6.4, I-14
    """
    root = _session_repo(tmp_path, monkeypatch)
    index_path = root / ".git" / "index"
    before = index_path.stat().st_mtime_ns
    calls: list[list[str]] = []
    real_run = subprocess.run

    def _spy(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(changes.subprocess, "run", _spy)
    changes.write_snapshot(root, "s1")
    (root / "dirty.txt").write_text("edited\n", encoding="utf-8")
    changes.session_set(root, "s1")
    assert {call[4] for call in calls} >= {"status", "diff", "hash-object"}
    assert all(call[:2] == ["git", "--no-optional-locks"] for call in calls)
    assert index_path.stat().st_mtime_ns == before


def test_tree_identity_is_none_outside_a_git_work_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root with no git repository has no tree identity, so a plan saved there is refused.

    arch: D12.1, I-40
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    assert changes.tree_identity(tmp_path) is None


def test_tree_identity_gives_head_and_a_status_hash(tmp_path: Path) -> None:
    """The identity holds the `HEAD` sha and a sha256 hex of the status; two reads agree.

    arch: D12.1
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    identity = changes.tree_identity(tmp_path)
    assert identity is not None
    assert set(identity) == {"head", "status"}
    assert identity["head"] == head
    assert len(identity["status"]) == 64
    assert int(identity["status"], 16) >= 0
    assert changes.tree_identity(tmp_path) == identity


def test_tree_identity_changes_on_a_second_edit_of_a_modified_file(
    tmp_path: Path,
) -> None:
    """A second edit of a file that is already modified changes the hash, though porcelain stays the same.

    arch: D12.1, I-40
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    (tmp_path / "a.txt").write_text("edit one\n", encoding="utf-8")
    porcelain = changes._git(tmp_path, "status", "--porcelain=v1", "-z")
    first = changes.tree_identity(tmp_path)
    (tmp_path / "a.txt").write_text("edit two\n", encoding="utf-8")
    assert changes._git(tmp_path, "status", "--porcelain=v1", "-z") == porcelain
    second = changes.tree_identity(tmp_path)
    assert first is not None and second is not None
    assert first["head"] == second["head"]
    assert first["status"] != second["status"]


def test_tree_identity_changes_with_a_new_untracked_file(tmp_path: Path) -> None:
    """An untracked file that appears changes the hash; an ignored one does not.

    arch: D12.1
    """
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text(".scratch/\n", encoding="utf-8")
    _commit(tmp_path, "ignore")
    clean = changes.tree_identity(tmp_path)
    (tmp_path / ".scratch").mkdir()
    (tmp_path / ".scratch" / "plan.json").write_text("{}\n", encoding="utf-8")
    assert changes.tree_identity(tmp_path) == clean
    (tmp_path / "plan.json").write_text("{}\n", encoding="utf-8")
    assert changes.tree_identity(tmp_path) != clean


def test_tree_identity_works_from_a_subdirectory_root(tmp_path: Path) -> None:
    """A root below the repository top hashes the blobs of its own changed files.

    arch: D12.1
    """
    _git_init(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.txt").write_text("x\n", encoding="utf-8")
    _commit(tmp_path, "add x")
    (tmp_path / "sub" / "x.txt").write_text("x one\n", encoding="utf-8")
    first = changes.tree_identity(tmp_path / "sub")
    (tmp_path / "sub" / "x.txt").write_text("x two\n", encoding="utf-8")
    second = changes.tree_identity(tmp_path / "sub")
    assert first is not None and second is not None
    assert first["status"] != second["status"]


def test_tree_identity_writes_no_object_and_keeps_the_index(tmp_path: Path) -> None:
    """The read writes no git object and leaves `.git/index` as it is, so `check` stays read-only.

    arch: D12.1, I-18, I-14
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _commit(tmp_path, "add a")
    (tmp_path / "a.txt").write_text("edit\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")
    objects = tmp_path / ".git" / "objects"
    before_objects = sorted(path for path in objects.rglob("*") if path.is_file())
    index_before = (tmp_path / ".git" / "index").stat().st_mtime_ns
    assert changes.tree_identity(tmp_path) is not None
    after_objects = sorted(path for path in objects.rglob("*") if path.is_file())
    assert after_objects == before_objects
    assert (tmp_path / ".git" / "index").stat().st_mtime_ns == index_before


def test_a_git_failure_is_worded_without_the_changed_flag(tmp_path: Path) -> None:
    """`_git` names the command and the root, and keeps `--changed` out of the text.

    arch: D15.1, D15.2
    """
    with pytest.raises(ConfigError) as excinfo:
        changes._git(tmp_path / "missing", "status")
    text = str(excinfo.value)
    assert "git status failed in" in text
    assert str(tmp_path / "missing") in text
    assert "--changed" not in text


def test_dirty_paths_raises_when_git_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dirty_paths` raises on a git failure; an empty set would hide the dirty tree.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(ConfigError, match="git rev-parse failed"):
        changes.dirty_paths(tmp_path)
