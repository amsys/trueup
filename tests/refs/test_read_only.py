"""Integration test that a run leaves the tree unchanged (I-8)."""

import hashlib
import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the child process needs no `cwd`."""


def _tree_digest(root, exclude=None):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path == exclude:
            continue
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_run_leaves_tree_unchanged_apart_from_edge_file(tmp_path):
    """A run leaves the tree unchanged, apart from the edge file it is told to write (I-8).

    arch: I-8
    """
    tree = materialise("read-only-tree", tmp_path)
    edge_file = tree / "edges.json"
    before = _tree_digest(tree, exclude=edge_file)

    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree), "--edges", str(edge_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert edge_file.is_file(), result.stderr

    after = _tree_digest(tree, exclude=edge_file)
    assert before == after
