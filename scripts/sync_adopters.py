"""Copy the `trueup.toml` of each adopter into `tests/fixtures/adopters/` (D15.38).

`tests/test_adopters.py` round-trips each snapshot through `config.render`.
A snapshot starts with one header line that names its source and the date
of the copy. The rest of the snapshot is the source file, byte for byte.

Usage: python3 scripts/sync_adopters.py [--check]
With no flag, the script writes each snapshot. With `--check`, it writes
nothing and prints each snapshot that differs from its source.
Exit codes: 0 all snapshots match, 1 a snapshot differs, 2 a source file
is absent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAPSHOTS = REPO / "tests" / "fixtures" / "adopters"

ADOPTERS: dict[str, str] = {
    "trueup": "trueup.toml",
}
"""Snapshot directory name to the adopter file it copies. A relative path
is relative to this repository. The snapshots `target-web`,
`target-web-3d` and `target-rust-src` come from private repositories:
their names are replaced, and this script does not write them."""

HEADER_START = "# Snapshot of "
"""The start of the header line of each snapshot."""


def header(source: str, day: date) -> str:
    """Give the header line of one snapshot.

    Args:
        source: The adopter file, as `ADOPTERS` names it.
        day: The date of the copy.

    Returns:
        The line, with its newline.
    """
    return (
        f"{HEADER_START}{source}, copied {day.isoformat()} by "
        "scripts/sync_adopters.py; do not edit.\n"
    )


def body(snapshot: str) -> str:
    """Give the snapshot text without its header line.

    Args:
        snapshot: The text of a snapshot file.

    Returns:
        The text after the first line when that line is a header line,
        else the whole text.
    """
    first, _, rest = snapshot.partition("\n")
    return rest if first.startswith(HEADER_START) else snapshot


def main(argv: list[str] | None = None) -> int:
    """Write or check each snapshot that `ADOPTERS` names.

    Args:
        argv: The arguments after the script name; `None` reads `sys.argv`.

    Returns:
        The exit code: 0, 1 or 2 as the module docstring gives.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="write nothing; report drift"
    )
    args = parser.parse_args(argv)
    code = 0
    for name, source in ADOPTERS.items():
        path = REPO / Path(source).expanduser()
        if not path.is_file():
            print(f"{name}: source {source} is absent", file=sys.stderr)
            code = 2
            continue
        text = path.read_text(encoding="utf-8")
        target = SNAPSHOTS / name / "trueup.toml"
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current is not None and body(current) == text:
            continue
        if args.check:
            print(f"{name}: snapshot differs from {source}")
            code = max(code, 1)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(header(source, date.today()) + text, encoding="utf-8")
        print(f"{name}: copied {source}")
    return code


if __name__ == "__main__":
    sys.exit(main())
