"""Entry point for `python3 trueup <command>`.

Python runs a directory given on the command line by adding that directory
to `sys.path` and executing its `__main__.py` as the top-level module. That
leaves the directory's own parent off `sys.path`, so a plain `import
trueup.cli` would fail here. This module adds the parent directory first,
then delegates to `trueup.cli.main`, so the same package serves the CLI,
the guard hooks and the test suite.

Two gates run before any trueup import (D15.7). A Python older than 3.11
cannot load the package, so the launcher stops there. A `hook` call in a
repository with no `trueup.toml` does nothing, so the launcher exits 0
without loading the CLI. The fast path uses only the standard library.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_PARENT_DIR = str(_PACKAGE_DIR.parent)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)


def find_root(start: str | None) -> Path | None:
    """Find the repository root a hook payload points at (same walk as `hooks._find_root`).

    Args:
        start: The payload `cwd`, or `None` or empty for the process's own
            working directory.

    Returns:
        The first of that directory and its parents that holds a `.git`
        entry, or `None` when none does.
    """
    cwd = (Path(start) if start else Path(os.getcwd())).resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def early_exit(argv: list[str], version: tuple[int, ...], read_stdin) -> int | None:
    """Decide whether the launcher can end before it imports the CLI (D15.7).

    Args:
        argv: The command line, program name first.
        version: The interpreter version, as `sys.version_info` gives it.
        read_stdin: A function that reads the whole stdin text once.

    Returns:
        An exit code when the launcher must stop, or `None` to go on. The
        text read for a `hook` call is left in `sys.stdin` as an
        `io.StringIO`, so the CLI reads it again.
    """
    is_hook = len(argv) > 1 and argv[1] == "hook"
    if tuple(version[:2]) < (3, 11):
        if is_hook:
            return 0
        found = ".".join(str(part) for part in version[:3])
        print(f"trueup: needs Python 3.11 or later, this is {found}", file=sys.stderr)
        return 2
    if not is_hook:
        return None
    text = read_stdin()
    try:
        payload = json.loads(text) if text.strip() else {}
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    start = payload.get("cwd")
    root = find_root(start if isinstance(start, str) else None)
    if root is None or not (root / "trueup.toml").exists():
        return 0
    sys.stdin = io.StringIO(text)
    return None


if __name__ == "__main__":
    _code = early_exit(sys.argv, tuple(sys.version_info), sys.stdin.read)
    if _code is not None:
        raise SystemExit(_code)
    from trueup.cli import main

    raise SystemExit(main())
