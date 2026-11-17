"""Guard against two sections or two invariants sharing one design id (arch: D2.8)."""

from __future__ import annotations

import collections
from pathlib import Path

from trueup.ref_check import _DESIGN_HEADING, _DESIGN_INVARIANT

ARCHITECTURE = Path(__file__).resolve().parent.parent / "docs" / "ARCHITECTURE.md"
"""The merged page, meridian's sections and trueup's own, by id (arch: D2.8)."""


def test_each_declared_id_occurs_once() -> None:
    """Guard against a repeated design id that check c cannot see.

    Check c of `ref_check.py` reasons about id sets, so a page with the
    same design id declared twice gives it no failure: a test that cites
    the id proves one declaration and hides the other. This test counts
    each declared id with the checker's own two patterns and fails on a
    repeat.

    arch: D2.8
    """
    text = ARCHITECTURE.read_text(encoding="utf-8")
    ids = _DESIGN_HEADING.findall(text) + _DESIGN_INVARIANT.findall(text)
    counts = collections.Counter(ids)
    repeats = {name: count for name, count in counts.items() if count > 1}
    assert repeats == {}
