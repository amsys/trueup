"""One bounded file reader for every content read of trueup (D15.22).

A read here never follows a symlink out of the root, never opens a device,
FIFO or socket, and never returns more than its cap (I-50).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _open_regular(root: Path, rel: str) -> int | None:
    """Open a tracked file for reading, or refuse it.

    Args:
        root: The repository root.
        rel: The repo-relative path.

    Returns:
        A read-only file descriptor of a regular file inside `root`, or
        `None` when `lstat` cannot see the path, it is a device, FIFO,
        socket or directory, or it is a symlink that resolves outside
        `root` or to something that is not a regular file.
    """
    full = root / rel
    try:
        info = os.lstat(full)
        if stat.S_ISLNK(info.st_mode):
            target = full.resolve(strict=True)
            if not target.is_relative_to(root.resolve()):
                return None
            if not stat.S_ISREG(os.stat(target).st_mode):
                return None
        elif not stat.S_ISREG(info.st_mode):
            return None
        descriptor = os.open(full, os.O_RDONLY | os.O_NONBLOCK)
    except (OSError, RuntimeError):
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None
    except OSError:
        os.close(descriptor)
        return None
    return descriptor


def _read_up_to(descriptor: int, count: int) -> bytes:
    """Read at most `count` bytes from `descriptor`, then close it.

    Args:
        descriptor: An open file descriptor.
        count: The most bytes to read.

    Returns:
        The bytes read.
    """
    chunks: list[bytes] = []
    remaining = count
    try:
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def read_capped(root: Path, rel: str, max_bytes: int) -> bytes | None:
    """Read at most `max_bytes` of a tracked file under `root`.

    Args:
        root: The repository root.
        rel: The repo-relative path.
        max_bytes: The longest file, in bytes, to return.

    Returns:
        The bytes, or `None` for a path that `lstat` cannot see; a device,
        FIFO or socket; a symlink whose resolved target is outside the
        root or is not a regular file; or a file longer than `max_bytes`.
    """
    descriptor = _open_regular(root, rel)
    if descriptor is None:
        return None
    try:
        data = _read_up_to(descriptor, max_bytes + 1)
    except OSError:
        return None
    return None if len(data) > max_bytes else data


def read_text_capped(root: Path, rel: str, max_bytes: int) -> str | None:
    """Read `read_capped` and decode it as UTF-8, ignoring bad bytes.

    Args:
        root: The repository root.
        rel: The repo-relative path.
        max_bytes: The longest file, in bytes, to return.

    Returns:
        The text, or `None` where `read_capped` gives `None`.
    """
    data = read_capped(root, rel, max_bytes)
    return None if data is None else data.decode("utf-8", errors="ignore")


def read_head(root: Path, rel: str, n: int) -> bytes | None:
    """Read the first `n` bytes of a tracked file under `root`.

    Args:
        root: The repository root.
        rel: The repo-relative path.
        n: The number of bytes to read.

    Returns:
        Up to `n` bytes, with no limit on the file length, or `None` for
        the refusals of `read_capped` other than length.
    """
    descriptor = _open_regular(root, rel)
    if descriptor is None:
        return None
    try:
        return _read_up_to(descriptor, n)
    except OSError:
        return None
