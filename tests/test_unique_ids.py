"""Guard the declared ids and the claims of the design pages (arch: D2.8, D16.2)."""

from __future__ import annotations

import collections
from pathlib import Path

from trueup.ref_check import (
    _ANY_ID,
    _DESIGN_HEADING,
    _DESIGN_INVARIANT,
    _VERIFICATION,
    _claims_in_text,
    _read_declared_sources,
    load_config,
)

ROOT = Path(__file__).resolve().parent.parent
"""The root of this repository."""

ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
"""The merged page, meridian's sections and trueup's own, by id (arch: D2.8)."""

MIN_CLAIMS = 200
"""The lowest count of claimed ids that the guard accepts; 223 on 2026-11-21."""


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


def test_check_c_reads_the_claims_of_this_repository() -> None:
    """Guard against claims that move out of the pages that check c reads.

    Check c passes when no page it reads holds `## Verification`, so a
    move of the section to a page that the config does not name drops
    each claim with no failure. This test reads the pages that check c
    reads for this repository: the sources of `[targets.arch]` when the
    configured reader is on, else `ARCHITECTURE.md`. Exactly one page
    must hold the section, and the section must claim at least
    `MIN_CLAIMS` ids.

    arch: D2.8
    arch: D16.2
    """
    declared = _read_declared_sources(ROOT, load_config(ROOT))
    if declared is None:
        texts = [("docs/ARCHITECTURE.md", ARCHITECTURE.read_text(encoding="utf-8"))]
        any_id = _ANY_ID
    else:
        assert declared.missing == ()
        assert declared.unreadable == ()
        texts = list(declared.texts)
        any_id = declared.grammar.anywhere
    holders = [shown for shown, text in texts if _VERIFICATION.search(text)]
    assert len(holders) == 1, holders
    text = dict(texts)[holders[0]]
    assert len(_claims_in_text(text, any_id)) >= MIN_CLAIMS
