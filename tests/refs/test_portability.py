"""Integration test that a copy of the checker still works (D1.1, D2.12, I-11)."""

import shutil
import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the copy does not depend on `cwd`."""


def test_copy_of_checker_runs_directly(tmp_path):
    """A copy of the checker, with a different name in a different tree, runs directly (D1.1, D2.12, I-11).

    arch: D1.1, D2.12, I-11
    """
    tree = materialise("portability-copy", tmp_path)
    copy = tree / "checked_copy.py"
    shutil.copy(CHECKER, copy)

    direct_run = subprocess.run(
        [sys.executable, str(copy)],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert direct_run.returncode == 0


def test_copy_of_checker_passes_under_pytest(tmp_path):
    """A copy of the checker, with a different name in a different tree, passes under `pytest` (D1.1, D2.12, I-11).

    arch: D1.1, D2.12, I-11
    """
    tree = materialise("portability-copy", tmp_path)
    copy = tree / "checked_copy.py"
    shutil.copy(CHECKER, copy)

    pytest_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(copy)],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "10 passed" in pytest_run.stdout
