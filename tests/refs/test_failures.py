"""Unit tests for the design id about the failure line format."""

import re
from pathlib import Path

from trueup.ref_check import KINDS, Failure, format_failure, run

ARCHITECTURE = Path(__file__).resolve().parents[2] / "docs" / "ARCHITECTURE.md"
"""The design page that holds the D2.4 format and kind table."""

GATE = '''"""The gate fixture."""


def test_bad():
    """A marker with an unknown id.

    arch: D9.9
    """


def test_unmarked():
    """No marker here."""
'''

DESIGN = "## D1.2 — a design id\n\n## Verification\n\nD1.2\n"

DETAILS = {
    "unknown-id": "test_bad cites D9.9",
    "no-target": "test_bad: target law is not configured: acts/A/v1/s.1",
    "malformed": "test_bad: marker does not parse: ref: not-a-body",
    "unmarked": "test_unmarked",
    "unproved": "claimed in ## Verification, proved by no test: D1.2",
    "drift": "main: section text changed in v13: acts/A/v13/s.1",
    "unregistered": "main: marker not in the registry: refs",
    "no-reason": "main: suppression has no reason: # noqa",
    "no-header": "file has no header comment",
    "broken-link": "link does not resolve: docs/gone.md",
    "unreadable": "file cannot be read: SyntaxError",
    "no-front-matter": "file has no front matter",
    "bad-field": "value is not allowed: status: done",
    "misplaced": "page of type how-to is not below docs/how-to/",
    "unindexed": "docs/README.md has no link to this page",
    "duplicate-id": "id is also on docs/how-to/a.md: use",
    "stale-pin": "pinned section changed: docs/ARCHITECTURE.md#d11--the-checker",
    "no-readme": "no README.md at the root",
    "no-title": "line 1 is not a title",
    "no-description": "no paragraph after the title",
    "no-section": "section is absent: Usage",
    "misordered": "License is not the last section",
    "no-licence-file": "no LICENSE, LICENSE.md or COPYING at the root",
    "badges-scattered": "badge is outside the block under the title",
    "no-index-link": "no link to docs/README.md",
}


def _build(tmp_path):
    """Write the gate tree that the three legacy patterns need.

    arch: none - a helper, not a test.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(DESIGN, encoding="utf-8")
    (tmp_path / "test_gate.py").write_text(GATE, encoding="utf-8")
    return [format_failure(failure) for failure in run(tmp_path).failures]


def _d24_section() -> str:
    """Return the text of the D2.4 heading of `docs/ARCHITECTURE.md`, up to the next heading."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    match = re.search(r"\n## D2\.4 — Failure line format\n(.*?)\n## ", text, re.S)
    assert match, "D2.4 heading not found in docs/ARCHITECTURE.md"
    return match.group(1)


def _d24_table_kinds(section: str) -> set[str]:
    """Return the kinds named by the `| `<kind>` | <detail> |` rows of the D2.4 table."""
    return set(re.findall(r"^\| `([a-z][a-z-]*)` \|", section, re.M))


def _d24_line_regex(section: str) -> re.Pattern[str]:
    """Build a regex for the line format from the fenced example under the D2.4 heading."""
    match = re.search(r"```\n(<path>:<line>: \[<kind>\] <detail>)\n```", section)
    assert match, "D2.4 line format example not found"
    pattern = re.escape(match.group(1))
    groups = {"path": ".+", "line": r"\d+", "kind": "[^]]+", "detail": ".+"}
    for name, body in groups.items():
        pattern = pattern.replace(f"<{name}>", f"(?P<{name}>{body})")
    return re.compile("^" + pattern + "$")


def test_failure_line_format_for_each_kind():
    """The printed line matches the D2.4 format, for the D2.4 kinds (D2.4).

    arch: D2.4
    """
    assert len(KINDS) == 25
    assert len(set(KINDS)) == 25
    section = _d24_section()
    assert _d24_table_kinds(section) == set(KINDS)
    line_regex = _d24_line_regex(section)
    for kind in KINDS:
        line = format_failure(Failure("a/b.py", 7, kind, DETAILS[kind]))
        match = line_regex.match(line)
        assert match, line
        assert match["path"] == "a/b.py"
        assert match["line"] == "7"
        assert match["kind"] == kind
        assert match["detail"] == DETAILS[kind]


def test_a_failure_with_an_id_ends_with_that_id():
    """When the failure has an id, the id is the last text of the line (D2.4).

    arch: D2.4
    """
    for kind in ("unknown-id", "no-target", "unproved", "drift"):
        line = format_failure(Failure("a/b.py", 7, kind, DETAILS[kind]))
        assert re.search(r"(?:D\d+\.\d+|s\.\d+)$", line), line


def test_the_three_patterns_of_the_legacy_selftest_match(tmp_path):
    """The lines of checks a, b and c match the three greps of the selftest (D2.4).

    arch: D2.4
    """
    lines = _build(tmp_path)
    for pattern in (
        r"test_gate\.py:.* test_bad cites D9\.9",
        r"test_gate\.py:.* test_unmarked",
        r"proved by no test: D1\.2$",
    ):
        assert any(re.search(pattern, line) for line in lines), (pattern, lines)


def test_the_unproved_line_names_the_design_file_and_the_claim_line(tmp_path):
    """Check c gives one line for each id, at the line that names it (D2.4).

    arch: D2.4
    """
    lines = _build(tmp_path)
    unproved = [line for line in lines if "[unproved]" in line]
    expected = (
        "docs/ARCHITECTURE.md:5: [unproved] "
        "claimed in ## Verification, proved by no test: D1.2"
    )
    assert unproved == [expected]


def test_failures_print_in_the_sort_order_of_their_fields(tmp_path):
    """The report sorts by path, then line, then kind, then detail (D2.4).

    arch: D2.4
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(DESIGN, encoding="utf-8")
    (tmp_path / "test_gate.py").write_text(GATE, encoding="utf-8")
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    failures = run(tmp_path).failures
    keys = [(item.path, item.line, item.kind, item.detail) for item in failures]
    assert keys == sorted(keys)
    assert len(keys) > 2
