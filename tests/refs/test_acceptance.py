"""Acceptance tests, one for each criterion S13 to S22 of the brief.

Each test materialises its fixture tree and runs the checker as a child
process (D4.3). It asserts the exit code and the exact failure lines of
D2.4. The acceptance tests of S11 and S12 run the lint commands of the
comment standard page. They moved to the trueup repository, together
with that page and the lint configurations.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise
from trueup.ref_check import run

REPO = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO / "trueup" / "ref_check.py"
LEGACY_SCRIPT = REPO / "tests" / "refs" / "legacy" / "test-arch-refs.sh"
LEGACY_SHA256 = "84bf5d91df201500638b0823f84139e184b6505d6634ca803abe073fed87ce8e"
CLEAN = ["ref_check: 0 failures, 0 references"]


def _check(tree: Path, *flags: str) -> tuple[int, list[str]]:
    """Run the checker on one tree as a child process.

    Args:
        tree: The root to examine.
        *flags: More flags of D2.3, for example `--edges FILE`.

    Returns:
        The exit code and the lines of standard output.
    """
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree), *flags],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    return result.returncode, result.stdout.splitlines()


def test_s3_closed_registry(tmp_path):
    """A marker that is not in the registry fails.

    arch: D2.2
    """
    tree = materialise("s13-closed-registry", tmp_path)

    assert _check(tree) == (
        1,
        [
            "src/gate.py:6: [unregistered] open_gate: marker not in the registry: FIXME",
            "src/gate.py:12: [unregistered] close_gate: marker not in the registry: refs",
            "ref_check: 2 failures, 1 references",
        ],
    )


def test_s4_id_exists(tmp_path):
    """A reference to an id that is not in its target fails.

    arch: D1.3
    """
    design = materialise("s14-id-exists/arch", tmp_path / "arch")
    law = materialise("s14-id-exists/law", tmp_path / "law")

    assert _check(design) == (
        1,
        [
            "src/gate.py:12: [unknown-id] close_gate cites D9.9",
            "ref_check: 1 failures, 2 references",
        ],
    )
    assert _check(law) == (
        1,
        [
            "src/levy.py:12: [unknown-id] ninth_levy cites acts/Sample_Act/base/s.9",
            "ref_check: 1 failures, 2 references",
        ],
    )


def test_s5_marked_files(tmp_path):
    """In a marked file, a unit with no marker fails. A file with no marker passes.

    arch: D2.8
    """
    tree = materialise("s15-marked-files", tmp_path)

    assert _check(tree) == (
        1,
        [
            "tests/test_marked.py:12: [unmarked] test_gate_closes",
            "ref_check: 1 failures, 1 references",
        ],
    )


def test_s6_design_to_code(tmp_path):
    """A design id under `## Verification` with no citing test fails.

    arch: D2.8
    """
    tree = materialise("s16-design-to-code", tmp_path)

    assert _check(tree) == (
        1,
        [
            "docs/ARCHITECTURE.md:18: [unproved] claimed in ## Verification,"
            " proved by no test: D1.2",
            "ref_check: 1 failures, 1 references",
        ],
    )


def test_s7_drift(tmp_path):
    """A pinned reference reports drift when the cited section text changed.

    arch: D4.2
    """
    tree = materialise("s17-drift", tmp_path)

    assert _check(tree) == (
        1,
        [
            "src/levy.py:6: [drift] first_levy: section text changed in v2:"
            " acts/Sample_Act/base/s.1",
            "ref_check: 1 failures, 2 references",
        ],
    )


def test_s8_zero_at_the_start(tmp_path):
    """The checker exits 0 and prints no failure on a repository with no marker.

    arch: I-6
    """
    empty = materialise("s18-empty", tmp_path / "empty")
    coded = materialise("s18-coded-no-marker", tmp_path / "coded")

    # Git keeps no empty directory, so the empty tree holds one file that no reader selects.
    assert sorted(path.name for path in empty.rglob("*")) == ["README"]
    assert _check(empty) == (0, CLEAN)
    assert _check(coded) == (0, CLEAN)


def test_s8_switches_off_by_default(tmp_path):
    """A bare suppression, a tag comment and no header pass while the switches are off.

    The tree has no marker and no `ref_check.toml`, so checks e and f are off
    (D2.5). The same tree with the two switches on gives the three failures.

    arch: I-6, D2.5
    """
    tree = materialise("s18-switches-off", tmp_path)
    assert not (tree / "ref_check.toml").exists()
    assert _check(tree) == (0, CLEAN)

    (tree / "ref_check.toml").write_text(
        "[checks]\nregistry = true\ncomments = true\n", encoding="utf-8"
    )
    assert _check(tree) == (
        1,
        [
            "src/app.py:3: [no-reason] module: suppression has no reason: noqa: F401",
            "src/app.py:8: [unregistered] number: marker not in the registry: NOTE",
            "src/tool.sh:1: [no-header] file has no header comment",
            "ref_check: 3 failures, 0 references",
        ],
    )


def test_s9_self_check():
    """The checker passes on this repository with all switches on.

    arch: D5.1, D4.1
    """
    report = run(REPO)
    assert report.failures == []


def test_s10_old_markers(tmp_path):
    """The unchanged selftest of the existing reference checker still passes.

    arch: D1.7, D4.4, I-5
    """
    digest = hashlib.sha256(LEGACY_SCRIPT.read_bytes()).hexdigest()
    assert digest == LEGACY_SHA256, f"{LEGACY_SCRIPT} changed: {digest}"
    selftest = tmp_path / "selftest"
    selftest.mkdir()
    shutil.copyfile(LEGACY_SCRIPT, selftest / LEGACY_SCRIPT.name)
    shutil.copyfile(CHECKER, selftest / "arch_refs.py")
    done = subprocess.run(
        ["bash", str(selftest / LEGACY_SCRIPT.name)],
        capture_output=True,
        text=True,
        check=False,
        cwd=selftest,
    )
    assert done.returncode == 0, done.stdout + done.stderr

    tree = materialise("s20-old-markers", tmp_path / "tree")
    assert _check(tree) == (
        1,
        [
            "docs/ARCHITECTURE.md:17: [unproved] claimed in ## Verification,"
            " proved by no test: D1.2",
            "tests/test_gate.py:7: [unknown-id] test_bad cites D9.9",
            "tests/test_gate.py:11: [unmarked] test_unmarked",
            "ref_check: 3 failures, 3 references",
        ],
    )


def test_s11_edge_file(tmp_path):
    """One run writes an edge file with one record for each reference.

    arch: D2.6
    """
    tree = materialise("s21-edge-file", tmp_path / "tree")
    edges = tmp_path / "edges.json"

    assert _check(tree, "--edges", str(edges)) == (
        1,
        [
            "src/gate.py:12: [unknown-id] count_gate cites D7.7",
            "ref_check: 1 failures, 4 references",
        ],
    )
    keys = ("source", "line", "unit", "marker", "target", "id", "status")
    rows = [
        ("src/gate.py", 6, "open_gate", "ref", "arch", "D1.1", "ok"),
        ("src/gate.py", 12, "count_gate", "ref", "arch", "D7.7", "unknown-id"),
        ("tests/test_gate.py", 7, "test_gate_counts", "arch", "arch", "D1.1", "ok"),
        ("tests/test_gate.py", 7, "test_gate_counts", "arch", "arch", "D1.2", "ok"),
    ]
    assert json.loads(edges.read_text(encoding="utf-8")) == {
        "schema": 1,
        "edges": [dict(zip(keys, row, strict=True)) for row in rows],
    }


def test_s12_document_links(tmp_path):
    """A relative link or fragment in `docs/` that does not resolve fails.

    arch: D2.10
    """
    tree = materialise("s22-document-links", tmp_path)

    assert _check(tree) == (
        1,
        [
            "docs/index.md:5: [broken-link] link does not resolve: missing.md",
            "docs/index.md:6: [broken-link] link does not resolve: guide.md#install",
            "ref_check: 2 failures, 0 references",
        ],
    )
