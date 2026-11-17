"""The slop score: five weighted categories over the plan (D5.7).

`compute` scores only the plan (`error`/`warn`, not kept, D5.4); an `info`
finding never counts. The docs category counts distinct paths, not
findings, so one systemic rule that fires on many lines of one file counts
once (D6.12). The score is a proposal, not a measurement another tool has
checked, and the reference page says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trueup.config import Config
from trueup.findings import Finding
from trueup.health import required_item_count
from trueup.hygiene import ROOT_BUDGET
from trueup.survey import Survey

CATEGORY_WEIGHTS: dict[str, int] = {
    "security": 25,
    "files": 20,
    "docs": 20,
    "root": 15,
    "health": 10,
}
"""The five scored categories and their weight; they sum to 90 (D5.7)."""

TOTAL_WEIGHT: int = sum(CATEGORY_WEIGHTS.values())


@dataclass(frozen=True)
class Score:
    """The slop score of one check run.

    Attributes:
        total: `round(sum(categories.values()) * 100 / 90)`. 0 is best.
        tier: The survey's tier, printed alongside the score.
        categories: Each scored category's own value, already capped at
            its weight.
        raw: Each scored category's raw input text, for example
            `"3 of 40 files"` (D10.8). Keyed by category name, including
            `"setup"`, which carries no weight.
    """

    total: int
    tier: str
    categories: dict[str, float]
    raw: dict[str, str] = field(default_factory=dict)


def _covered_files(plan: list[Finding], survey: Survey) -> int:
    """Count the surveyed files that a files-category finding covers (D15.21).

    A path that ends in `/` covers every surveyed file under it. Another
    path covers itself. A path that is no surveyed file counts 1. Each file
    counts once.

    Args:
        plan: The plan to read.
        survey: The survey that gives the file list.

    Returns:
        The number of covered files.
    """
    covered: set[str] = set()
    for finding in plan:
        if finding.category != "files":
            continue
        path = finding.path
        if path.endswith("/"):
            hits = [name for name in survey.files if name.startswith(path)]
            covered.update(hits or [path])
        else:
            covered.add(path)
    return len(covered)


def compute(plan: list[Finding], survey: Survey, cfg: Config | None) -> Score:
    """Compute the slop score of one check run.

    Args:
        plan: The plan `trueup.findings.build_plan` returned: `error` and
            `warn` findings, kept ones already removed.
        survey: The survey the plan was built from.
        cfg: The loaded `trueup.toml`, or `None` when it is absent.

    Returns:
        The `Score` of this run.
    """
    counts = {category: 0 for category in CATEGORY_WEIGHTS}
    setup_count = 0
    for finding in plan:
        if finding.category in counts:
            counts[finding.category] += 1
        elif finding.category == "setup":
            setup_count += 1
    # D6.12: one systemic docs rule that fires on many lines of one file
    # must count once, so docs scales with distinct paths, not findings.
    distinct_docs_paths = len(
        {finding.path for finding in plan if finding.category == "docs"}
    )
    public = cfg.public if cfg is not None else False
    required = required_item_count(survey.tier, public, survey.tags)
    root_allow = len(cfg.root_allow) if cfg is not None else 0
    budget = ROOT_BUDGET[survey.tier] + root_allow
    entries_over_budget = max(0, len(survey.root_entries) - budget)
    covered = _covered_files(plan, survey)

    categories = {
        "security": 25.0 if counts["security"] > 0 else 0.0,
        "files": 20 * min(1.0, 10 * covered / max(1, len(survey.files))),
        "docs": 20 * min(1.0, distinct_docs_paths / 10),
        "root": 15 * min(1.0, entries_over_budget / 10),
        "health": 10 * min(1.0, counts["health"] / max(1, required)),
    }
    total = round(sum(categories.values()) * 100 / TOTAL_WEIGHT)
    # D10.8/D10.12: the raw input text behind each category's points, for
    # the Markdown and JSON reports.
    raw = {
        "security": f"{counts['security']} findings",
        "files": f"{covered} of {len(survey.files)} files",
        "docs": f"{distinct_docs_paths} paths",
        "root": f"{entries_over_budget} entries, budget {budget}",
        "health": f"{counts['health']} of {required} required",
        "setup": f"{setup_count} findings",
    }
    return Score(total=total, tier=survey.tier, categories=categories, raw=raw)
