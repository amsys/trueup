"""Integration test for the edge file schema and run-to-run stability (D2.6, I-7)."""

import json
import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise

from trueup.ref_check import format_failure, main, run

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the child process needs no `cwd`."""

EXPECTED_EDGES = [
    {
        "source": "src/gate.py",
        "line": 5,
        "unit": "open_gate",
        "marker": "ref",
        "target": "arch",
        "id": "D1.2",
        "status": "ok",
    },
    {
        "source": "src/gate.py",
        "line": 10,
        "unit": "count_gate",
        "marker": "ref",
        "target": "arch",
        "id": "D9.9",
        "status": "unknown-id",
    },
    {
        "source": "tests/test_gate.py",
        "line": 7,
        "unit": "test_gate_closes",
        "marker": "arch",
        "target": "arch",
        "id": "D1.1",
        "status": "ok",
    },
    {
        "source": "tests/test_gate.py",
        "line": 7,
        "unit": "test_gate_closes",
        "marker": "arch",
        "target": "arch",
        "id": "D1.2",
        "status": "ok",
    },
]
"""The records of the `edges-one-tree` fixture, in the order of D2.6."""

KEY_ORDER = ["source", "line", "unit", "marker", "target", "id", "status"]
"""The key order of one record, from D2.6."""


def test_edge_file_matches_expected_and_is_stable(tmp_path):
    """The edge file of a tree matches the expected file, and two runs give the same bytes (D2.6, I-7).

    arch: D2.6, I-7
    """
    tree = materialise("edges-one-tree", tmp_path)
    edges_a = tree / "edges-a.json"
    edges_b = tree / "edges-b.json"

    subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree), "--edges", str(edges_a)],
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree), "--edges", str(edges_b)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert edges_a.read_bytes() == edges_b.read_bytes()
    record = json.loads(edges_a.read_text(encoding="utf-8"))
    assert record["schema"] == 1
    assert list(record.keys()) == ["schema", "edges"]

    # One record for each reference, in the sort order of D2.6.
    assert record["edges"] == EXPECTED_EDGES
    assert [list(edge.keys()) for edge in record["edges"]] == [KEY_ORDER] * len(
        EXPECTED_EDGES
    )

    # Two spaces of indent, a final newline, and no absolute path (I-7).
    text = edges_a.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[1] == '  "schema": 1,'
    assert lines[4].startswith('      "source"')
    assert text.endswith("}\n")
    assert str(tree) not in text


def test_edge_file_replaces_existing_content(tmp_path):
    """If the --edges file exists, the checker replaces it, not appends (D2.3).

    arch: D2.3, D2.6
    """
    tree = materialise("edges-one-tree", tmp_path)
    edges_file = tree / "edges.json"
    edges_file.write_text("stale content, not a JSON document\n", encoding="utf-8")

    subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree), "--edges", str(edges_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    record = json.loads(edges_file.read_text(encoding="utf-8"))
    assert record["schema"] == 1
    assert list(record.keys()) == ["schema", "edges"]
    assert record["edges"] == EXPECTED_EDGES


def test_a_repeated_id_on_one_marker_is_one_reference_and_one_failure(tmp_path, capsys):
    """A marker that names D9.9 twice gives one edge record and one failure line, and the summary agrees (D2.6, D2.4).

    arch: D2.6, D2.4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## D1.1 — a gate\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_gate.py").write_text(
        'def test_bad():\n    """Bad.\n\n    arch: D9.9, D9.9\n    """\n',
        encoding="utf-8",
    )

    report = run(tmp_path)

    assert [format_failure(failure) for failure in report.failures] == [
        "tests/test_gate.py:4: [unknown-id] test_bad cites D9.9"
    ]
    assert [(edge.line, edge.id, edge.status) for edge in report.edges] == [
        (4, "D9.9", "unknown-id")
    ]
    assert main(["--root", str(tmp_path)]) == 1
    assert (
        capsys.readouterr().out.splitlines()[-1]
        == "ref_check: 1 failures, 1 references"
    )
