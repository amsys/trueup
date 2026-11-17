"""Tests for `trueup.findings`: the line field, keep matches, fingerprints and stale keeps (arch: D15.8)."""

from __future__ import annotations

import hashlib

import pytest

from trueup import findings as findings_mod, ref_check
from trueup.findings import Finding, build_plan, keep_match


def _finding(finding_id: str, severity: str = "error") -> Finding:
    """Build one finding with the given id.

    Args:
        finding_id: The id; the rule is the text before the first `:`.
        severity: `error`, `warn` or `info`.

    Returns:
        The finding.
    """
    return Finding(
        id=finding_id,
        rule=finding_id.split(":", 1)[0],
        category="docs",
        severity=severity,
        path=finding_id.split(":")[1] if ":" in finding_id else "",
        evidence="x",
        action="x",
        auto=False,
    )


def test_a_finding_has_line_zero_by_default() -> None:
    """`Finding` gains a last field `line`, 0 when the row names no line.

    arch: D15.3, D15.8
    """
    finding = _finding("scratch:a.tmp")
    assert finding.line == 0
    assert Finding("a:b", "a", "docs", "info", "b", "e", "x", False, 4).line == 4


_KEEP_TABLE: list[tuple[str, dict[str, str], str | None]] = [
    ("prose:docs/a.md", {"prose:docs/a.md": "r"}, "prose:docs/a.md"),
    ("prose:docs/abc.md", {"prose:docs/a": "r"}, None),
    ("prose:docs/a.md", {"prose": "r"}, "prose"),
    (
        "refcheck:docs/a.md:3:unknown-id",
        {"refcheck:docs/a.md": "r"},
        "refcheck:docs/a.md",
    ),
    (
        "refcheck:docs/a.md:3:unknown-id",
        {"refcheck:docs/a.md": "r", "refcheck:docs/a.md:3": "r"},
        "refcheck:docs/a.md:3",
    ),
    (
        "refcheck:docs/a.md:3",
        {"refcheck:docs/a.md": "r", "refcheck:docs/a.md:3": "r"},
        "refcheck:docs/a.md:3",
    ),
    ("refcheck:docs/a.md:30:x", {"refcheck:docs/a.md:3": "r"}, None),
    ("scratch:a.tmp", {}, None),
    ("scratch:a.tmp", {"scratch:a.tmp:": "r"}, None),
]
"""Finding id, keep table, the keep id that must match (or `None`)."""


@pytest.mark.parametrize(("finding_id", "keep", "expected"), _KEEP_TABLE)
def test_keep_match_is_exact_first_then_the_longest_segment_prefix(
    finding_id: str, keep: dict[str, str], expected: str | None
) -> None:
    """A keep matches its own id, or every id below it at a `:` boundary.

    `prose:docs/a` never keeps `prose:docs/abc.md`.

    arch: D15.3, D15.8
    """
    assert keep_match(finding_id, keep) == expected


@pytest.mark.parametrize(("finding_id", "keep", "expected"), _KEEP_TABLE)
def test_the_checker_copy_of_keep_match_gives_the_same_answer(
    finding_id: str, keep: dict[str, str], expected: str | None
) -> None:
    """`ref_check.py` holds its own copy of `keep_match`; both agree on the table.

    arch: D15.3, D15.8
    """
    assert ref_check.keep_match(finding_id, frozenset(keep)) == expected


def test_build_plan_holds_out_a_finding_that_a_prefix_keep_names() -> None:
    """A prefix keep holds every finding below it out of the plan.

    arch: D15.3, D15.8
    """
    found = [
        _finding("refcheck:docs/a.md:1:no-front-matter"),
        _finding("refcheck:docs/a.md:9:broken-link"),
        _finding("refcheck:docs/abc.md:1:no-front-matter"),
    ]
    plan = build_plan(found, {"refcheck:docs/a.md": "fixed page"})
    assert [finding.id for finding in plan] == [
        "refcheck:docs/abc.md:1:no-front-matter"
    ]


def test_line_fingerprint_is_twelve_hex_of_the_path_and_the_stripped_line() -> None:
    """The fingerprint is sha256 of `path NUL stripped-line`, first 12 hex digits.

    It does not change when the line moves or gets other indentation.

    arch: D15.3, D15.8
    """
    expected = hashlib.sha256(b"a.py\x00KEY = 1").hexdigest()[:12]
    assert findings_mod.line_fingerprint("a.py", b"  KEY = 1\n") == expected
    assert findings_mod.line_fingerprint("a.py", "KEY = 1") == expected
    assert findings_mod.line_fingerprint("b.py", "KEY = 1") != expected


def test_number_repeats_adds_a_count_to_the_second_and_later_equal_ids() -> None:
    """Equal ids get `:2`, `:3` in the given order; the first one stays bare.

    arch: D15.3, D15.8
    """
    ids = ["c:a.py:f1", "c:a.py:f2", "c:a.py:f1", "c:a.py:f1"]
    assert findings_mod.number_repeats(ids) == [
        "c:a.py:f1",
        "c:a.py:f2",
        "c:a.py:f1:2",
        "c:a.py:f1:3",
    ]


def test_stale_keeps_name_each_keep_that_matches_no_finding() -> None:
    """A keep that matches no finding gives one `keep-stale` info row on `trueup.toml`.

    A keep that matches an `info` finding is used too.

    arch: D15.3, D15.8
    """
    found = [_finding("prose:docs/a.md"), _finding("health-x:", severity="info")]
    keep = {"prose:docs": "r", "prose:docs/a.md": "r", "health-x:": "r", "gone:x": "r"}
    stale = findings_mod.stale_keeps(found, keep)
    assert stale == [
        Finding(
            id="keep-stale:gone:x",
            rule="keep-stale",
            category="setup",
            severity="info",
            path="trueup.toml",
            evidence="keeps nothing",
            action="remove the [[keep]] entry or fix its id",
            auto=False,
        ),
        Finding(
            id="keep-stale:prose:docs",
            rule="keep-stale",
            category="setup",
            severity="info",
            path="trueup.toml",
            evidence="keeps nothing",
            action="remove the [[keep]] entry or fix its id",
            auto=False,
        ),
    ]
