"""Tests for `trueup.score`: the five-category slop score (D5.7)."""

from __future__ import annotations

from pathlib import Path

from trueup.config import Config
from trueup.findings import Finding
from trueup.health import required_item_count
from trueup.hygiene import ROOT_BUDGET
from trueup.score import compute
from trueup.survey import Survey


def _survey(
    *, files: int, root_entries: int, tier: str = "T2", tags: int = 0
) -> Survey:
    """Build a minimal `Survey` for a `score.compute` test.

    Only the fields `score.compute` reads are given real values; the rest
    take a placeholder, since `trueup.score` never touches them.

    Args:
        files: The number of files to report.
        root_entries: The number of root entries to report.
        tier: The tier to report.
        tags: The tag count to report.

    Returns:
        A `Survey` with `files` and `root_entries` of the given sizes.
    """
    return Survey(
        root=Path("/does-not-matter"),
        files=tuple(f"f{i}.txt" for i in range(files)),
        languages={},
        tools={},
        root_entries=tuple(f"r{i}" for i in range(root_entries)),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=tags,
        tier=tier,
        tier_reason="test",
        counter="built-in",
    )


def _finding(
    category: str, rule: str = "x", severity: str = "error", path: str = ""
) -> Finding:
    """Build a minimal `Finding` for a `score.compute` test.

    Args:
        category: The category to report.
        rule: The rule name, distinct enough to give a unique id.
        severity: The severity to report.
        path: The finding's path. Distinct paths matter for the `docs`
            category, which counts them rather than the finding count
            (D6.12).

    Returns:
        A `Finding` in the given category.
    """
    return Finding(
        id=f"{rule}:{category}",
        rule=rule,
        category=category,
        severity=severity,
        path=path,
        evidence="test evidence",
        action="test action",
        auto=False,
    )


def test_empty_plan_scores_zero() -> None:
    """No findings gives a score of 0 in every category (D5.7).

    arch: D5.7
    """
    survey = _survey(files=10, root_entries=5)
    score = compute([], survey, None)
    assert score.total == 0
    assert all(value == 0 for value in score.categories.values())
    assert score.tier == "T2"


def test_security_is_flat_regardless_of_count() -> None:
    """One security finding fills the whole security weight, and a second adds nothing (D5.7).

    arch: D5.7
    """
    survey = _survey(files=10, root_entries=5)
    one = compute([_finding("security")], survey, None)
    two = compute(
        [_finding("security", rule="a"), _finding("security", rule="b")], survey, None
    )
    assert one.categories["security"] == 25
    assert two.categories["security"] == 25


def test_files_category_scales_with_count_and_caps_at_the_weight() -> None:
    """The `files` category scales with the finding count over the file count, capped at 20 (D5.7).

    arch: D5.7
    """
    survey = _survey(files=100, root_entries=5)
    light = compute([_finding("files")], survey, None)
    assert light.categories["files"] == 2.0  # 20 * min(1, 10*1/100)

    heavy = compute(
        [_finding("files", rule=str(i), path=f"f{i}.txt") for i in range(20)],
        survey,
        None,
    )
    assert heavy.categories["files"] == 20  # 10*20/100 = 2.0, over 1, capped


def test_docs_category_scales_and_caps_at_ten_distinct_paths() -> None:
    """The `docs` category reaches its full weight at 10 distinct paths (D6.12).

    arch: D6.12
    """
    survey = _survey(files=10, root_entries=5)
    five = compute(
        [_finding("docs", rule=str(i), path=f"doc{i}.md") for i in range(5)],
        survey,
        None,
    )
    assert five.categories["docs"] == 10.0  # 20 * 5/10

    ten = compute(
        [_finding("docs", rule=str(i), path=f"doc{i}.md") for i in range(10)],
        survey,
        None,
    )
    assert ten.categories["docs"] == 20  # capped


def test_docs_category_counts_distinct_paths_not_finding_count() -> None:
    """One systemic docs rule that fires on many lines of one file counts once (D6.12).

    arch: D6.12
    """
    survey = _survey(files=10, root_entries=5)
    one_path_many_findings = compute(
        [_finding("docs", rule=str(i), path="one.md") for i in range(40)],
        survey,
        None,
    )
    assert one_path_many_findings.categories["docs"] == 2.0  # 20 * 1/10

    five_paths_ten_findings = compute(
        [_finding("docs", rule=str(i), path=f"doc{i % 5}.md") for i in range(10)],
        survey,
        None,
    )
    assert five_paths_ten_findings.categories["docs"] == 10.0  # 5 distinct paths


def test_root_category_uses_the_tier_budget_and_root_allow() -> None:
    """The `root` category grows with entries over the tier's budget, widened by `[root] allow` (D5.7).

    arch: D5.7
    """
    survey = _survey(files=10, root_entries=ROOT_BUDGET["T2"] + 5, tier="T2")
    over = compute([], survey, None)
    assert over.categories["root"] == 7.5  # 15 * min(1, 5/10)

    cfg = Config(root_allow=("a", "b", "c", "d", "e"))
    widened = compute([], survey, cfg)
    assert widened.categories["root"] == 0  # the 5 extra entries are now inside budget


def test_health_category_uses_required_item_count() -> None:
    """The `health` category is capped by how many health items this tier requires (D5.7).

    arch: D5.7
    """
    survey = _survey(files=10, root_entries=5, tier="T2")
    required = required_item_count("T2", public=False, tags=0)
    assert required > 0
    one = compute([_finding("health")], survey, None)
    assert one.categories["health"] == 10 * min(1.0, 1 / required)

    full = compute(
        [_finding("health", rule=str(i)) for i in range(required)], survey, None
    )
    assert full.categories["health"] == 10


def test_total_is_the_weighted_sum_scaled_to_100() -> None:
    """`total` is `round(sum(categories) * 100 / 90)` (D5.7).

    arch: D5.7
    """
    survey = _survey(files=10, root_entries=5, tier="T2")
    score = compute([_finding("security")], survey, None)
    assert score.total == round(25 * 100 / 90)


def test_raw_counts_default_empty_without_crashing() -> None:
    """An empty plan still gives a `raw` dict with real counts, not an empty map (D10.8).

    arch: D10.8
    """
    survey = _survey(files=10, root_entries=5, tier="T2")
    score = compute([], survey, None)
    assert score.raw["security"] == "0 findings"
    assert score.raw["files"] == f"0 of {len(survey.files)} files"
    assert score.raw["docs"] == "0 paths"
    assert score.raw["setup"] == "0 findings"


def test_raw_counts_text_per_category(tmp_path) -> None:
    """Each category's raw text follows the D10.12 texts exactly (D10.8).

    arch: D10.8
    """
    survey = _survey(files=100, root_entries=ROOT_BUDGET["T2"] + 5, tier="T2")
    required = required_item_count("T2", public=False, tags=0)
    plan = [
        _finding("security", rule="s1"),
        _finding("files", rule="f1", path="f1.txt"),
        _finding("docs", rule="d1", path="doc1.md"),
        _finding("docs", rule="d2", path="doc2.md"),
        _finding("health", rule="h1"),
        _finding("setup", rule="u1"),
    ]
    score = compute(plan, survey, None)
    assert score.raw["security"] == "1 findings"
    assert score.raw["files"] == "1 of 100 files"
    assert score.raw["docs"] == "2 paths"
    budget = ROOT_BUDGET["T2"]
    assert score.raw["root"] == f"5 entries, budget {budget}"
    assert score.raw["health"] == f"1 of {required} required"
    assert score.raw["setup"] == "1 findings"


def test_files_category_counts_covered_files_once() -> None:
    """A directory path covers each surveyed file under it; a file counts once (D15.21).

    arch: D15.21
    """
    survey = _survey(files=0, root_entries=5)
    survey = Survey(**{**survey.__dict__, "files": ("a/x", "a/y", "b/z", "c")})
    plan = [
        _finding("files", rule="r1", path="a/"),
        _finding("files", rule="r2", path="a/x"),
        _finding("files", rule="r3", path="gone.tmp"),
        _finding("files", rule="r4", path="gone.tmp"),
    ]
    score = compute(plan, survey, None)
    assert score.raw["files"] == "3 of 4 files"
