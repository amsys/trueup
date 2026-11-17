"""Integration test for the drift check of a law reference (D4.2, I-10)."""

import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the child process needs no `cwd`."""


def _check(tree: Path) -> tuple[int, str]:
    """Run the checker on one tree as a child process.

    Args:
        tree: The root to examine.

    Returns:
        The exit code and the standard output.
    """
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout


def test_drift_changed_unchanged_absent_and_pinned_newest(tmp_path):
    """A changed section, an unchanged section, an absent section, and a pin that is the newest version (D4.2, I-10).

    arch: D4.2, I-10
    """
    changed = materialise("drift-changed", tmp_path / "changed")
    unchanged = materialise("drift-unchanged", tmp_path / "unchanged")
    absent = materialise("drift-absent", tmp_path / "absent")
    newest_pin = materialise("drift-pinned-newest", tmp_path / "newest")
    clean = "ref_check: 0 failures, 1 references\n"

    assert _check(changed) == (
        1,
        "sample.py:3: [drift] module: section text changed in v2: acts/Sample_Act/base/s.1\n"
        "ref_check: 1 failures, 1 references\n",
    )
    assert _check(unchanged) == (0, clean)
    assert _check(absent) == (
        1,
        "sample.py:3: [unknown-id] module: section absent in v2: acts/Sample_Act/base/s.1\n"
        "ref_check: 1 failures, 1 references\n",
    )
    assert _check(newest_pin) == (0, clean)
