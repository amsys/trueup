"""Integration test for the legacy selftest and the shim."""

import ast
import hashlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests" / "refs" / "legacy" / "test-arch-refs.sh"
CHECKER = ROOT / "trueup" / "ref_check.py"
PINNED_SHA256 = "84bf5d91df201500638b0823f84139e184b6505d6634ca803abe073fed87ce8e"


def test_legacy_selftest_hash_and_pass(tmp_path):
    """The copied selftest keeps its pinned hash, and it still passes.

    arch: D1.7, D4.4, I-5, D2.12
    """
    digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert digest == PINNED_SHA256, f"{SCRIPT} changed: {digest}"

    shutil.copyfile(SCRIPT, tmp_path / SCRIPT.name)
    shutil.copyfile(CHECKER, tmp_path / "arch_refs.py")
    done = subprocess.run(
        ["bash", str(tmp_path / SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_shim_defines_no_test_of_its_own():
    """The entry point holds the names of the checker and nothing else.

    arch: D1.7, D2.12
    """
    shim = ROOT / "tests" / "refs" / "test_arch_refs.py"
    tree = ast.parse(shim.read_text())
    defined = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    assert defined == [], f"the shim defines {defined}"

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "trueup.ref_check"
        for alias in node.names
    }
    assert imported == {
        "test_cited_ids_exist_in_the_design",
        "test_every_test_in_a_marked_file_has_a_marker",
        "test_verification_claims_have_a_test",
    }
