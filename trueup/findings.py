"""`Finding`, the plan rule and the sort order every check row shares (arch: D5.4).

`hygiene.py`, `health.py`, `docrules.py` and `managed.py` each build a list
of `Finding` in this shape, and `report.collect` merges the four lists.
This module holds that shared shape and the rules a caller applies to the
merged list: `protect_findings` turns a finding that would touch a
`protect` glob into a manual one (I-24), `sorted_findings` gives I-21's fixed
order, and `build_plan` picks the findings the person is asked to act on.
`keep_match` is the one rule that matches a `[[keep]]` id to a finding id,
and `stale_keeps` names each keep that matches no finding (D15.8).
`line_fingerprint` and `number_repeats` build the ids of the rows that
point at one line, so a line that moves keeps its id (D15.8).
`AUTO_RULES` holds one static predicate per rule that `apply` handles, so
`apply --plan` can check a saved row on the tree now with no second
collect (D15.27, I-40).
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from trueup.survey import matches_ignore

CATEGORY_ORDER: tuple[str, ...] = (
    "security",
    "files",
    "docs",
    "root",
    "health",
    "setup",
)
"""The fixed category order findings and the plan sort by (D5.4, I-21)."""


@dataclass(frozen=True)
class Finding:
    """One thing `check` found (D5.4).

    Attributes:
        id: `"<rule>:<path>"`, stable and readable, never a hash. `path` is
            the empty string for a repo-wide finding, so the id ends `:`.
        rule: The rule name, for example `"scratch"` or `"health-license"`.
        category: One of `CATEGORY_ORDER`.
        severity: `"error"`, `"warn"` or `"info"`.
        path: The repo-relative POSIX path, or `""` for a repo-wide finding.
        evidence: One line; never the matched text of a secret (I-23).
        action: One line: what `apply` does, or what the person does.
        auto: True when `apply` can act on this finding with no prose
            judgement from the person.
        line: The 1-based line the finding points at, or 0 when it points
            at no single line (D15.8).
    """

    id: str
    rule: str
    category: str
    severity: str
    path: str
    evidence: str
    action: str
    auto: bool
    line: int = 0


def sort_key(finding: Finding) -> tuple[int, str]:
    """Give the sort key of one finding: category order, then id (D5.4, I-21).

    Args:
        finding: The finding to key.

    Returns:
        The category's index in `CATEGORY_ORDER`, then the finding's id.
    """
    return (CATEGORY_ORDER.index(finding.category), finding.id)


def sorted_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by category order, then by id (D5.4, I-21).

    Args:
        findings: The findings to sort.

    Returns:
        A new list, sorted; `findings` itself is not changed.
    """
    return sorted(findings, key=sort_key)


def keep_match(finding_id: str, keep: Mapping[str, str]) -> str | None:
    """Give the `[[keep]]` id that keeps one finding id, or `None` (D15.8).

    The match is segment-bounded: a keep `k` keeps the id `k` and each id
    that starts with `k + ":"`. So `prose:docs/a` never keeps
    `prose:docs/abc.md`. `ref_check.keep_match` is a copy of this function
    for the checker, and a test pins the two equal.

    Args:
        finding_id: The finding id.
        keep: The `[[keep]]` table: keep id to reason.

    Returns:
        The exact keep id when `keep` holds it, else the longest keep id
        that is a segment prefix of `finding_id`, else `None`.
    """
    if finding_id in keep:
        return finding_id
    prefixes = [k for k in keep if finding_id.startswith(k + ":")]
    return max(prefixes, key=len) if prefixes else None


def build_plan(findings: list[Finding], keep: Mapping[str, str]) -> list[Finding]:
    """Build the plan: `error` and `warn` findings that no keep matches (D5.4, D15.8).

    An `info` finding never joins the plan, no matter what `keep` holds.

    Args:
        findings: Every finding `check` produced.
        keep: The `[[keep]]` table of `trueup.toml`: keep id to the reason
            the person declined it. A keep id matches as `keep_match` says.

    Returns:
        The plan, sorted by category order then id (I-21).
    """
    plan = [
        finding
        for finding in findings
        if finding.severity in ("error", "warn")
        and keep_match(finding.id, keep) is None
    ]
    return sorted_findings(plan)


def stale_keeps(findings: list[Finding], keep: Mapping[str, str]) -> list[Finding]:
    """Give one `keep-stale` row for each `[[keep]]` id that matches no finding (D15.8).

    A keep matches a finding of any severity when the finding's id is the
    keep id or starts with the keep id and `:`. Only a full run may call
    this: a scoped run does not see the findings outside its scope.

    Args:
        findings: Every finding of a full run.
        keep: The `[[keep]]` table of `trueup.toml`.

    Returns:
        The `keep-stale:<id>` info rows on `trueup.toml`, sorted by keep id.
    """
    ids = [finding.id for finding in findings]
    return [
        Finding(
            id=f"keep-stale:{k}",
            rule="keep-stale",
            category="setup",
            severity="info",
            path="trueup.toml",
            evidence="keeps nothing",
            action="remove the [[keep]] entry or fix its id",
            auto=False,
        )
        for k in sorted(keep)
        if not any(found == k or found.startswith(k + ":") for found in ids)
    ]


def line_fingerprint(path: str, line: bytes | str) -> str:
    """Give the fingerprint of one line: 12 hex digits of sha256 (D15.8).

    The hash input is the path, a NUL byte and the stripped line, so the
    fingerprint does not change when the line moves or its indentation
    changes. It is a short digest, never the line text (I-23).

    Args:
        path: The repo-relative POSIX path.
        line: The line, as bytes or text; text is encoded as UTF-8.

    Returns:
        The first 12 hex digits of the digest.
    """
    data = line if isinstance(line, bytes) else line.encode("utf-8")
    digest = hashlib.sha256(path.encode("utf-8") + b"\0" + data.strip())
    return digest.hexdigest()[:12]


def number_repeats(ids: list[str]) -> list[str]:
    """Make equal ids unique: the second gets `:2`, the third `:3` (D15.8).

    Args:
        ids: The ids, in file order.

    Returns:
        The ids in the same order. The first of each equal group stays as
        it is.
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for finding_id in ids:
        seen[finding_id] = seen.get(finding_id, 0) + 1
        count = seen[finding_id]
        result.append(finding_id if count == 1 else f"{finding_id}:{count}")
    return result


APPLY_SIDE_FILES: dict[str, tuple[str, ...]] = {
    "artifact": (".gitignore",),
    "secret-file": (".gitignore",),
    "generated": (".gitattributes",),
}
"""Per rule, the files `apply` also writes beside the finding's own path (D5.6)."""


def touched_paths(finding: Finding) -> tuple[str, ...]:
    """Give every repo path `apply` would change to carry out one finding.

    Args:
        finding: The finding.

    Returns:
        The finding's own path (when it is not repo-wide), then the side
        files of its rule from `APPLY_SIDE_FILES`.
    """
    own = (finding.path,) if finding.path else ()
    return own + APPLY_SIDE_FILES.get(finding.rule, ())


def protect_findings(
    findings: list[Finding], protect: tuple[str, ...]
) -> list[Finding]:
    """Turn each auto finding that would touch a `protect` glob into a manual one (I-24).

    Args:
        findings: The merged findings.
        protect: The `protect` globs of `trueup.toml`.

    Returns:
        A new list in the same order. A finding whose `touched_paths`
        match a glob has `auto=False` and an action that names the glob
        rule; every other finding is returned unchanged.
    """
    result: list[Finding] = []
    for finding in findings:
        if finding.auto and any(
            matches_ignore(path, protect) for path in touched_paths(finding)
        ):
            finding = replace(
                finding,
                auto=False,
                action=f"protected by trueup.toml protect; by hand: {finding.action}",
            )
        result.append(finding)
    return result


@dataclass(frozen=True)
class AutoFacts:
    """The facts of a saved run that an `AUTO_RULES` predicate reads (D15.27).

    Attributes:
        secret_paths: The paths of the saved run's `secret-content`
            findings. An `.env` file is `auto` only when it is in this set.
        rendered: The managed repo paths that the config in force renders.
    """

    secret_paths: frozenset[str] = field(default_factory=frozenset)
    rendered: frozenset[str] = field(default_factory=frozenset)


def _git_tracks(root: Path, path: str) -> bool:
    """Say whether git tracks one path (D15.27).

    Args:
        root: The repository root.
        path: The repo-relative POSIX path.

    Returns:
        True when `git ls-files --error-unmatch` finds the path.
    """
    result = subprocess.run(
        ["git", "--literal-pathspecs", "ls-files", "--error-unmatch", "--", path],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _scratch_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`scratch`: the name proves scratch and git tracks the file (D15.27).

    Args:
        root: The repository root.
        finding: The saved row.
        facts: The saved run's facts; not read.

    Returns:
        True when `hygiene.scratch_proven` passes and the path is tracked.
    """
    from trueup import hygiene  # lazy: hygiene imports this module

    del facts
    return hygiene.scratch_proven(finding.path) and _git_tracks(root, finding.path)


def _artifact_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`artifact`: the path is a build or cache directory, or build output (D15.27).

    Args:
        root: The repository root.
        finding: The saved row. A directory row's path ends in `/`.
        facts: The saved run's facts; not read.

    Returns:
        True when the artifact pattern of the `artifact` row matches.
    """
    from trueup import hygiene  # lazy: hygiene imports this module

    del facts
    has_cargo, has_manifest = hygiene._artifact_markers(root)
    if finding.path.endswith("/"):
        parts = (*Path(finding.path).parts, "x")
        found = hygiene._artifact_directory(parts, has_cargo, has_manifest)
        return found is not None and found[0] == finding.path
    return hygiene._is_artifact_path(finding.path, has_cargo, has_manifest)


def _secret_file_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`secret-file`: the content test rates the file `auto` (D15.27).

    Args:
        root: The repository root.
        finding: The saved row.
        facts: The saved run's facts; `secret_paths` rates an `.env` file.

    Returns:
        True when `hygiene._secret_file_kind` gives `"auto"`.
    """
    from trueup import hygiene  # lazy: hygiene imports this module

    return hygiene._secret_file_kind(root, finding.path, facts.secret_paths) == "auto"


def _generated_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`generated`: a generated-file marker is in the first 5 lines (D15.27).

    Args:
        root: The repository root.
        finding: The saved row.
        facts: The saved run's facts; not read.

    Returns:
        True when the marker of the `generated` row is there. A secret
        file is never opened (I-23).
    """
    from trueup import fsread, hygiene  # lazy: hygiene imports this module

    del facts
    if hygiene._is_secret_basename(Path(finding.path).name):
        return False
    text = fsread.read_text_capped(root, finding.path, hygiene._TEXT_READ_CAP)
    if text is None:
        return False
    head = "\n".join(text.splitlines()[:5])
    return hygiene._GENERATED_MARKER.search(head) is not None or "@generated" in head


def _gitignore_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`gitignore`: the path is `.gitignore` (D15.27).

    Args:
        root: The repository root; not read.
        finding: The saved row.
        facts: The saved run's facts; not read.

    Returns:
        True when the path is `.gitignore`.
    """
    del root, facts
    return finding.path == ".gitignore"


def _file_managed_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`file-managed`: the config in force renders the path (D15.27).

    Args:
        root: The repository root; not read.
        finding: The saved row.
        facts: The saved run's facts; `rendered` holds the managed paths.

    Returns:
        True when the path is in `facts.rendered`.
    """
    del root
    return finding.path in facts.rendered


def _config_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """`config`: the id starts with `config:` (D15.27).

    Args:
        root: The repository root; not read.
        finding: The saved row.
        facts: The saved run's facts; not read.

    Returns:
        True when the id starts with `config:`.
    """
    del root, facts
    return finding.id.startswith("config:")


AUTO_RULES: Mapping[str, Callable[[Path, Finding, AutoFacts], bool]] = {
    "file-managed": _file_managed_holds,
    "artifact": _artifact_holds,
    "secret-file": _secret_file_holds,
    "scratch": _scratch_holds,
    "generated": _generated_holds,
    "gitignore": _gitignore_holds,
    "config": _config_holds,
}
"""Per rule that `apply` handles, the static test a saved `auto` row must
pass on the tree now (D15.27). A rule that is not here is never `auto` in a
saved plan."""


def auto_row_holds(root: Path, finding: Finding, facts: AutoFacts) -> bool:
    """Say whether one saved `auto` row holds on the tree now (D15.27, I-40).

    Args:
        root: The repository root.
        finding: The saved row.
        facts: The saved run's facts.

    Returns:
        True when the row is `auto`, its rule is in `AUTO_RULES`, its id
        is `<rule>:<path>` (a `config` id only starts with `config:`), and
        the predicate of its rule passes.
    """
    predicate = AUTO_RULES.get(finding.rule)
    if predicate is None or not finding.auto:
        return False
    if finding.rule != "config" and finding.id != f"{finding.rule}:{finding.path}":
        return False
    return predicate(root, finding, facts)
