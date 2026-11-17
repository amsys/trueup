"""Tests for the checker speed rules: one parse for each file and no quadratic scans."""

import ast
import tokenize
from pathlib import Path

import pytest

from trueup import ref_check
from trueup.ref_check import Failure, failure_ids, run

SOURCE = '''"""Module doc.

arch: D1.2
"""


def test_one():
    """Uses é and an escape \\
    on one line.

    arch: D1.2
    """
    # a comment
    return "café"
'''

DESIGN = "## D1.2 — a design id\n\n## Verification\n\nD1.2\n"


def _tree(root: Path, files: int = 3) -> None:
    (root / "docs").mkdir()
    (root / "docs" / "ARCHITECTURE.md").write_text(DESIGN, encoding="utf-8")
    for index in range(files):
        (root / f"test_f{index}.py").write_text(SOURCE, encoding="utf-8")


def _old_failure_ids(failures: list[Failure]) -> list[str]:
    bases = [f"{item.path}:{item.line}:{item.kind}" for item in failures]
    ids = []
    for base, item in zip(bases, failures, strict=True):
        if bases.count(base) > 1:
            tail = item.detail.rsplit(": ", 1)[-1].strip()
            base = f"{base}:{ref_check._ID_SEPARATORS.sub('-', tail)}"
        ids.append(base)
    counts: dict[str, int] = {}
    unique = []
    for failure_id in ids:
        if ids.count(failure_id) > 1:
            counts[failure_id] = counts.get(failure_id, 0) + 1
            unique.append(f"{failure_id}:{counts[failure_id]}")
        else:
            unique.append(failure_id)
    return unique


def test_docstring_lines_need_no_get_source_segment(tmp_path, monkeypatch):
    """The docstring line numbers come from the line table, not `ast.get_source_segment`.

    arch: D15.23
    """
    _tree(tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("get_source_segment called")

    monkeypatch.setattr(ast, "get_source_segment", boom)
    assert run(tmp_path).failures == []


def test_source_segment_equals_the_standard_one():
    """The cached cut equals `ast.get_source_segment` on text with non-ASCII characters.

    arch: D15.23
    """
    tree = ast.parse(SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert ref_check._source_segment(SOURCE, node) == ast.get_source_segment(
                SOURCE, node
            )


def test_each_python_file_parses_and_tokenizes_once(tmp_path, monkeypatch):
    """A run parses each `.py` file once and tokenizes it once, for all checks.

    arch: D15.23
    """
    _tree(tmp_path, files=4)
    parses: list[str] = []
    tokenizes: list[int] = []
    real_parse = ast.parse
    real_tokens = tokenize.generate_tokens

    def spy_parse(source, filename="<unknown>", *args, **kwargs):
        parses.append(str(filename))
        return real_parse(source, filename, *args, **kwargs)

    def spy_tokens(readline):
        tokenizes.append(1)
        return real_tokens(readline)

    monkeypatch.setattr(ast, "parse", spy_parse)
    monkeypatch.setattr(tokenize, "generate_tokens", spy_tokens)
    run(tmp_path)
    mine = [name for name in parses if name.startswith(str(tmp_path))]
    assert len(mine) == len(set(mine)) == 4
    assert len(tokenizes) == 4


def test_failure_ids_equal_the_old_function_on_5000_failures():
    """`failure_ids` gives the ids of the earlier two-scan version for 5,000 failures.

    arch: D15.23
    """
    failures = [
        Failure(f"f{index % 50}.md", index % 7, "unmarked", f"a: tail {index % 3}")
        for index in range(5000)
    ]
    assert failure_ids(failures) == _old_failure_ids(failures)


@pytest.mark.parametrize(
    ("lines", "line", "expected"),
    [(8, 1, "module"), (8, 3, "A"), (8, 5, "A.f"), (8, 8, "module")],
)
def test_unit_at_gives_the_innermost_span(lines, line, expected):
    """`unit_at` returns the innermost span by bisect, `module` outside every span.

    arch: D15.23
    """
    units = [(2, 6, "A"), (4, 6, "A.f")]
    assert ref_check.unit_at(units, line) == expected


def test_walk_does_not_enter_a_directory_covered_by_a_prefix_glob(
    tmp_path, monkeypatch
):
    """A `<prefix>/**` ignore glob prunes the directory; the glob matcher never sees its files.

    arch: D15.23
    """
    (tmp_path / "gen" / "deep").mkdir(parents=True)
    (tmp_path / "gen" / "deep" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    seen: list[str] = []
    real = ref_check.matches_ignore

    def spy(path, patterns):
        seen.append(path)
        return real(path, patterns)

    monkeypatch.setattr(ref_check, "matches_ignore", spy)
    files = ref_check._iter_source_files(tmp_path, [], ["gen/**"])
    assert [p.name for p, _ in files] == ["keep.py"]
    assert not any(name.startswith("gen/") for name in seen)
