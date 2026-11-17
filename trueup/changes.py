"""The D6.17 change set and the D6.2 session snapshot.

`report.collect`'s `only` parameter and `trueup check --changed` both scope
a run to `working_set(root)`, so a scoped check reads the same files `git
status` names. The session hooks keep one snapshot file per agent session
below `$CLAUDE_PLUGIN_DATA`, and `session_set` gives the files that the
session changed. Every git call here passes `--no-optional-locks`, so it
never refreshes `.git/index` (arch: I-14).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from trueup.config import ConfigError

_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
"""The only session ids that get a snapshot file (arch: D6.2)."""

_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
"""A snapshot file older than this is deleted at the next write (arch: D6.2)."""


@dataclass
class Snapshot:
    """The state of one repository when an agent session started (arch: D6.2).

    Attributes:
        root: The absolute repository root the snapshot is for.
        head: The `HEAD` commit sha at the start, or `""` with no commit.
        dirty: Each path of `working_set(root)` at the start, with its blob sha.
        reminded: The paths the interface reminder already named (D6.4).
        version: The file schema version, always 1.
    """

    root: str
    head: str
    dirty: dict[str, str] = field(default_factory=dict)
    reminded: list[str] = field(default_factory=list)
    version: int = 1


def working_set(root: Path) -> frozenset[str]:
    """Give the working-tree change set: dirty tracked files, plus untracked ones (arch: D6.17).

    Runs `git rev-parse --show-prefix`, then one `git status --porcelain=v1
    -z --untracked-files=all -- .` call against `root`. Git already leaves
    ignored files out of that output, so the change set never holds an
    ignored path. The `.` pathspec keeps the call to paths below `root`.
    Git prints each path relative to the repository top, so when `root` is
    a subdirectory this function strips the prefix, and each path matches
    the survey's own root-relative paths.

    Args:
        root: The target repository root, or a directory inside one.

    Returns:
        Each changed or untracked path, relative to `root` and POSIX. A
        renamed or copied entry gives its new path only; a deleted path is
        left out.

    Raises:
        trueup.config.ConfigError: `root` is not inside a git repository,
            or git cannot run.
    """
    prefix = _git(root, "rev-parse", "--show-prefix").rstrip(b"\n")
    raw = _git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."
    )
    paths = _parse_porcelain_z(raw)
    if not prefix:
        return paths
    text_prefix = prefix.decode("utf-8", errors="surrogateescape")
    return frozenset(
        path[len(text_prefix) :] for path in paths if path.startswith(text_prefix)
    )


def tree_identity(root: Path) -> dict[str, str] | None:
    r"""Give the identity of the working tree that a saved plan is bound to (arch: D12.1).

    The hash input is the raw bytes of `git status --porcelain=v1 -z
    --untracked-files=all -- .`, then `b"\0"`, then the blob sha of each
    listed path that is on disk and is not a directory, joined by `b"\0"`.
    The blob shas make a second edit of a file that is already modified
    change the hash, since the porcelain line of that file stays the same.
    A symlink gives the sha of its link text, and a FIFO, a device or a
    socket gives the fixed `""`, so the identity never opens one (D16.10).
    Git leaves ignored paths out, so a plan file under an ignored path does
    not change the hash. The reads write no object and do not refresh
    `.git/index` (I-18).

    Args:
        root: The target root, or a directory inside a work tree.

    Returns:
        `{"head": <HEAD sha or "">, "status": <sha256 hex>}`, or `None`
        when `root` is not inside a git work tree.
    """
    try:
        top_raw = _git(root, "rev-parse", "--show-toplevel").rstrip(b"\n")
        raw = _git(
            root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."
        )
    except ConfigError:
        return None
    # Porcelain paths and `hash-object --stdin-paths` both use the top of
    # the work tree, not `root`, so the blobs are read from the top.
    top = Path(top_raw.decode("utf-8", errors="surrogateescape"))
    listed = _porcelain_listed(raw)
    present = [
        path
        for path in listed
        if os.path.islink(top / path)
        or (os.path.lexists(top / path) and not os.path.isdir(top / path))
    ]
    shas = _blob_shas(top, present)
    digest = hashlib.sha256(
        raw + b"\0" + b"\0".join(sha.encode("ascii") for sha in shas)
    ).hexdigest()
    return {"head": _head(root), "status": digest}


def _porcelain_listed(raw: bytes) -> list[str]:
    """List every path of one `git status --porcelain=v1 -z` run, both rename sides (arch: D12.2).

    Args:
        raw: The standard output of the `git status` call.

    Returns:
        Each path once, in output order, as git prints it (relative to the
        top of the work tree). A rename or copy record gives its new path
        and its old path. A deleted path is kept.
    """
    tokens = raw.split(b"\0")
    raw_paths: list[bytes] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        raw_paths.append(token[3:])
        if b"R" in token[:2] or b"C" in token[:2]:
            # The old-path record that follows carries no status.
            raw_paths.append(tokens[index] if index < len(tokens) else b"")
            index += 1
    listed: list[str] = []
    for raw_path in raw_paths:
        name = raw_path.decode("utf-8", errors="surrogateescape")
        if name and name not in listed:
            listed.append(name)
    return listed


def dirty_paths(root: Path) -> frozenset[str]:
    """Give every path with uncommitted changes below `root` (arch: D12.2).

    The paths come from `git status --porcelain=v1 -z --untracked-files=all
    -- .`: modified, added, deleted and untracked paths, and both sides of a
    rename. Git leaves ignored paths out. The read refreshes no index
    (I-18).

    Args:
        root: The target root, or a directory inside a work tree.

    Returns:
        The paths relative to `root`, POSIX, decoded with `surrogateescape`.

    Raises:
        trueup.config.ConfigError: A git call fails, for example outside a
            work tree. An empty set would read as a clean tree (arch: D15.2).
    """
    prefix = _git(root, "rev-parse", "--show-prefix").rstrip(b"\n")
    raw = _git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."
    )
    text_prefix = prefix.decode("utf-8", errors="surrogateescape")
    return frozenset(
        path[len(text_prefix) :]
        for path in _porcelain_listed(raw)
        if path.startswith(text_prefix)
    )


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """Run one read-only git command against `root` and give its output (arch: I-14).

    Every call passes `--no-optional-locks`, so `git status` never
    refreshes `.git/index` (I-18).

    Args:
        root: The directory to run git in.
        *args: The git subcommand and its arguments.
        stdin: The bytes to send on the command's standard input, or `None`.

    Returns:
        The command's standard output, as bytes.

    Raises:
        trueup.config.ConfigError: git cannot run, or exits non-zero. The
            message is `git <cmd> failed in <root>: <first stderr line>`
            (arch: D15.1).
    """
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            input=stdin,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", None) or b""
        lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
        reason = lines[0] if lines else str(exc)
        raise ConfigError(f"git {args[0]} failed in {root}: {reason}") from exc
    return result.stdout


def _parse_porcelain_z(raw: bytes) -> frozenset[str]:
    """Parse one `git status --porcelain=v1 -z` run into a path set (arch: D6.17).

    Each record is a two-byte status, a space, then a path, NUL-terminated.
    A rename or copy record (an `R` or `C` in the status) is followed by one
    more NUL-terminated record, the old path, which this function drops.

    Args:
        raw: The standard output of the `git status` call.

    Returns:
        The new (or untracked) path of every record whose status holds no
        `D`; a deleted path is left out.
    """
    tokens = raw.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        status, path = token[:2], token[3:]
        if b"R" in status or b"C" in status:
            index += 1  # the old-path record that follows carries no status
        if b"D" in status:
            continue
        paths.add(path.decode("utf-8", errors="surrogateescape"))
    return frozenset(paths)


def snapshot_path(session_id: str) -> Path | None:
    """Give the snapshot file of one session (arch: D6.2).

    Args:
        session_id: The `session_id` of the hook payload.

    Returns:
        `$CLAUDE_PLUGIN_DATA/sessions/<session_id>.json`, or `None` when
        `$CLAUDE_PLUGIN_DATA` is not set or empty, or when `session_id` is
        not a string that matches `^[A-Za-z0-9_-]{1,128}$`.
    """
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data or not isinstance(session_id, str):
        return None
    if not _SESSION_ID.fullmatch(session_id):
        return None
    return Path(data) / "sessions" / f"{session_id}.json"


def write_snapshot(root: Path, session_id: str) -> None:
    """Write the snapshot of `root` for one session, and replace an old one (arch: D6.2).

    The caller decides when to replace a file that exists: the `session`
    hook calls this for the source `startup` or `clear`, and for the other
    sources only when no file exists. This function also deletes each
    other snapshot file that is older than 7 days.

    Args:
        root: The repository root.
        session_id: The `session_id` of the hook payload.

    Raises:
        trueup.config.ConfigError: git cannot run in `root`.
        OSError: the snapshot directory cannot be written.
    """
    path = snapshot_path(session_id)
    if path is None:
        return
    root = root.resolve()
    dirty_paths = sorted(working_set(root))
    snapshot = Snapshot(
        root=str(root),
        head=_head(root),
        dirty=dict(zip(dirty_paths, _blob_shas(root, dirty_paths))),
    )
    _save(path, snapshot)
    _prune(path)


def read_snapshot(session_id: str) -> Snapshot | None:
    """Read the snapshot file of one session (arch: D6.2).

    Args:
        session_id: The `session_id` of the hook payload.

    Returns:
        The snapshot, or `None` when there is no path for the id, no file,
        or the file does not hold a version 1 snapshot.
    """
    path = snapshot_path(session_id)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            return None
        dirty = data.get("dirty", {})
        reminded = data.get("reminded", [])
        snapshot = Snapshot(
            root=str(data["root"]),
            head=str(data.get("head", "")),
            dirty={str(key): str(value) for key, value in dirty.items()},
            reminded=[str(item) for item in reminded],
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return snapshot


def session_set(root: Path, session_id: str) -> frozenset[str]:
    """Give the paths that one agent session changed below `root` (arch: D6.2).

    With a snapshot for this root and a start commit, the set is `git diff
    --name-only <head>` (so a commit made in the session counts) plus the
    untracked files, minus each path whose blob sha is equal to the one
    the snapshot holds for it, minus the deleted paths.

    Args:
        root: The repository root.
        session_id: The `session_id` of the hook payload.

    Returns:
        The repo-relative POSIX paths. With no snapshot, a snapshot for
        another root, or a snapshot with no start commit, this is
        `working_set(root)`.

    Raises:
        trueup.config.ConfigError: git cannot run in `root`.
    """
    root = root.resolve()
    snapshot = read_snapshot(session_id)
    if snapshot is None or snapshot.root != str(root) or not snapshot.head:
        return working_set(root)
    tracked = _git(
        root,
        "diff",
        "--name-only",
        "-z",
        "--relative",
        "--diff-filter=d",
        snapshot.head,
        "--",
        ".",
    )
    untracked = _git(
        root, "ls-files", "--others", "--exclude-standard", "-z", "--", "."
    )
    candidates = {
        item.decode("utf-8", errors="surrogateescape")
        for item in (tracked + b"\0" + untracked).split(b"\0")
        if item
    }
    present = sorted(path for path in candidates if os.path.lexists(root / path))
    known = [path for path in present if path in snapshot.dirty]
    same = {
        path
        for path, sha in zip(known, _blob_shas(root, known))
        if sha == snapshot.dirty[path]
    }
    return frozenset(path for path in present if path not in same)


def mark_reminded(root: Path, session_id: str, path: str) -> bool:
    """Add one path to the `reminded` list of a session's snapshot (arch: D6.4).

    With no snapshot file yet, this writes a new one with an empty `head`
    and no `dirty` paths, so `session_set` gives `working_set(root)`, the
    same as with no file.

    Args:
        root: The repository root.
        session_id: The `session_id` of the hook payload.
        path: The repo-relative POSIX path to add.

    Returns:
        True when the path is now in the list, False when the session has
        no snapshot path (`snapshot_path` gives `None`).

    Raises:
        OSError: the snapshot file cannot be written.
    """
    file_path = snapshot_path(session_id)
    if file_path is None:
        return False
    snapshot = read_snapshot(session_id) or Snapshot(root=str(root.resolve()), head="")
    if path not in snapshot.reminded:
        snapshot.reminded.append(path)
    _save(file_path, snapshot)
    return True


def _head(root: Path) -> str:
    """Give the `HEAD` commit sha of `root`, or `""` when there is no commit yet.

    Args:
        root: The repository root.

    Returns:
        The full sha, or `""`.
    """
    try:
        raw = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    except ConfigError:
        return ""
    return raw.decode("ascii", errors="replace").strip()


def _blob_shas(root: Path, paths: list[str]) -> list[str]:
    """Give the blob sha of each path, from one `git hash-object` call (arch: D6.2).

    Only a regular file goes to git: `--no-filters` hashes the bytes on
    disk, so no clean filter runs. The call has no `-w`, so it writes no
    object. A symlink is never opened: its sha is the blob sha of its link
    text, the same sha that git stores for the link (D16.10). Any other
    path (a directory such as a submodule, a FIFO, a device, a socket, or
    a path that `os.lstat` cannot see) gets `""`, which is never equal to
    a real sha.

    Args:
        root: The repository root; each path is relative to it.
        paths: The repo-relative paths.

    Returns:
        One sha per path, in the same order.

    Raises:
        trueup.config.ConfigError: git cannot run.
    """
    regular: list[str] = []
    links: dict[str, bytes] = {}
    for path in paths:
        try:
            mode = os.lstat(root / path).st_mode
            if stat.S_ISLNK(mode):
                links[path] = os.fsencode(os.readlink(root / path))
            elif stat.S_ISREG(mode):
                regular.append(path)
        except OSError:
            continue
    shas: dict[str, str] = {}
    if regular:
        stdin = "".join(f"{path}\n" for path in regular).encode(
            "utf-8", "surrogateescape"
        )
        raw = _git(root, "hash-object", "--no-filters", "--stdin-paths", stdin=stdin)
        shas = dict(zip(regular, raw.decode("ascii", errors="replace").split()))
    if links:
        algorithm = _object_format(root)
        for path, text in links.items():
            header = b"blob %d\0" % len(text)
            shas[path] = hashlib.new(algorithm, header + text).hexdigest()
    return [shas.get(path, "") for path in paths]


def _object_format(root: Path) -> str:
    """Give the hash algorithm of the repository's objects (arch: D16.10).

    Args:
        root: The repository root.

    Returns:
        `"sha256"` for a SHA-256 repository, else `"sha1"`. A git that does
        not know `--show-object-format` has only SHA-1.
    """
    try:
        raw = _git(root, "rev-parse", "--show-object-format")
    except ConfigError:
        return "sha1"
    return "sha256" if raw.strip() == b"sha256" else "sha1"


def _save(path: Path, snapshot: Snapshot) -> None:
    """Write one snapshot file through a temporary file and a rename.

    `os.replace` puts the full file in place in one step, so a reader never
    sees a half-written file.

    Args:
        path: The snapshot file.
        snapshot: The data to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": snapshot.version,
        "root": snapshot.root,
        "head": snapshot.head,
        "dirty": snapshot.dirty,
        "reminded": snapshot.reminded,
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _prune(keep: Path) -> None:
    """Delete each snapshot file next to `keep` that is older than 7 days (arch: D6.2).

    Args:
        keep: The snapshot file just written; it is never deleted.
    """
    cutoff = time.time() - _MAX_AGE_SECONDS
    for sibling in keep.parent.glob("*.json"):
        if sibling == keep:
            continue
        try:
            if sibling.stat().st_mtime < cutoff:
                sibling.unlink()
        except OSError:
            continue
