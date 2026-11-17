"""Tier health files and the agent-file check (D5.4).

Every item in `_items` is a community-health file that a person writes by
hand; `health_findings` (through `_item_finding`) reports it missing at the
tier that requires it, and as an `info` finding one tier early, so the
report can say "available at the next tier" (D5.4). `.editorconfig` is the
one health-table item this module does not check: D5.4 marks it managed,
so `managed.py` (out of this row's scope) owns that finding. The agent-file
check at the end is narrower than the health table: it only ever reports,
and trueup never writes `AGENTS.md` or `CLAUDE.md` itself. A public
repository also gets a `SECURITY.md` requirement at every tier (D7.6) and
three manual `platform:*` findings for settings trueup cannot read from the
tree: branch protection, organization MFA and collaborator access (D7.9).
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from trueup import docrules, fsread
from trueup.config import Config, public_is_false
from trueup.findings import Finding
from trueup.ref_check import licence_present
from trueup.survey import Survey

_TIER_ORDER: tuple[str, ...] = ("T0", "T1", "T2", "T3")

Requirement = Callable[[str, bool, int], bool]
"""A per-item requirement: `(tier, public, tags) -> required now`."""


def _readme_required(_tier: str, _public: bool, _tags: int) -> bool:
    """Say a README is required at every tier."""
    return True


def _gitignore_required(_tier: str, _public: bool, _tags: int) -> bool:
    """Say a `.gitignore` is required at every tier."""
    return True


def _license_required(tier: str, public: bool, _tags: int) -> bool:
    """Say a licence is required from T1 up, and at T0 only when public."""
    return public if tier == "T0" else True


def _changelog_required(tier: str, _public: bool, tags: int) -> bool:
    """Say a changelog is required at T3, and at T1/T2 once a tag exists."""
    if tier == "T3":
        return True
    return tier in ("T1", "T2") and tags > 0


def _contributing_required(tier: str, _public: bool, _tags: int) -> bool:
    """Say a contributing guide is required from T2 up."""
    return tier in ("T2", "T3")


def _security_required(_tier: str, public: bool, _tags: int) -> bool:
    """Say a security policy is required at every tier, only when public (D7.6).

    A rule that holds at T0 and T2 but not at T1 has no reason, so the
    requirement no longer depends on the tier once the repository is public.
    """
    return public


def _code_of_conduct_required(tier: str, public: bool, _tags: int) -> bool:
    """Say a code of conduct is required from T2 up, only when public."""
    return public and tier in ("T2", "T3")


def _issue_template_required(tier: str, public: bool, _tags: int) -> bool:
    """Say an issue template is required from T2 up, only when public."""
    return public and tier in ("T2", "T3")


def _pr_template_required(tier: str, public: bool, _tags: int) -> bool:
    """Say a pull-request template is required from T2 up, only when public."""
    return public and tier in ("T2", "T3")


def _codeowners_required(tier: str, _public: bool, _tags: int) -> bool:
    """Say a CODEOWNERS file is required at T3."""
    return tier == "T3"


class _Item:
    """One row of the D5.4 health table.

    Attributes:
        rule: The finding `rule` this item reports under.
        candidates: Repo-relative paths or patterns, any of which
            satisfies the item (see `_present`).
        required: The `(tier, public, tags) -> bool` requirement function.
        action: The action text, naming `trueup template <name>` when a
            skeleton exists for this item.
    """

    def __init__(
        self, rule: str, candidates: tuple[str, ...], required: Requirement, action: str
    ) -> None:
        self.rule = rule
        self.candidates = candidates
        self.required = required
        self.action = action


def _items(docs_dir: str) -> tuple[_Item, ...]:
    """Build the D5.4 health table for one docs directory (D14.4).

    Args:
        docs_dir: The docs directory name (`cfg.layout_docs_dir`).

    Returns:
        The items, with each docs-directory candidate built from `docs_dir`.
    """
    d = docs_dir
    return (
        _Item("health-readme", ("README.md",), _readme_required, "write README.md"),
        _Item(
            "health-gitignore", (".gitignore",), _gitignore_required, "write .gitignore"
        ),
        _Item(
            "health-license",
            ("LICENSE", "LICENCE", "COPYING"),
            _license_required,
            "add a LICENSE file",
        ),
        _Item(
            "health-changelog",
            ("CHANGELOG.md", "CHANGES.md", f"{d}/CHANGELOG.md"),
            _changelog_required,
            "write CHANGELOG.md; run trueup template changelog",
        ),
        _Item(
            "health-contributing",
            (
                "CONTRIBUTING.md",
                "CONTRIBUTING.rst",
                ".github/CONTRIBUTING.md",
                f"{d}/CONTRIBUTING.md",
            ),
            _contributing_required,
            "write CONTRIBUTING.md; run trueup template contributing, or add a README '## Contributing' section",
        ),
        _Item(
            "health-security",
            ("SECURITY.md", ".github/SECURITY.md", f"{d}/SECURITY.md"),
            _security_required,
            "write SECURITY.md; run trueup template security",
        ),
        _Item(
            "health-code-of-conduct",
            (
                "CODE_OF_CONDUCT.md",
                ".github/CODE_OF_CONDUCT.md",
                f"{d}/CODE_OF_CONDUCT.md",
            ),
            _code_of_conduct_required,
            "write CODE_OF_CONDUCT.md; run trueup template code-of-conduct",
        ),
        _Item(
            "health-issue-template",
            (
                ".github/ISSUE_TEMPLATE.md",
                ".github/ISSUE_TEMPLATE/*.md",
                ".github/ISSUE_TEMPLATE/*.yml",
            ),
            _issue_template_required,
            "add an issue template; run trueup template issue-template",
        ),
        _Item(
            "health-pr-template",
            (
                ".github/pull_request_template.*",
                "pull_request_template.*",
                f"{d}/pull_request_template.*",
                ".github/PULL_REQUEST_TEMPLATE/*",
                "PULL_REQUEST_TEMPLATE/*",
                f"{d}/PULL_REQUEST_TEMPLATE/*",
            ),
            _pr_template_required,
            "add a pull-request template; run trueup template pr-template",
        ),
        _Item(
            "health-codeowners",
            ("CODEOWNERS", ".github/CODEOWNERS", f"{d}/CODEOWNERS"),
            _codeowners_required,
            "add a CODEOWNERS file",
        ),
    )


def _contributing_satisfied(root: Path, item: _Item) -> bool:
    """Say whether a contributing guide, or a README section, is present.

    A README `## Contributing` heading stands in for a separate file.

    Args:
        root: The repository root.
        item: The `health-contributing` item.

    Returns:
        True when one of `item.candidates` exists, or `README.md` holds a
        `## Contributing` heading.
    """
    if _present(root, item.candidates):
        return True
    readme = root / "README.md"
    if not os.path.isfile(readme):
        return False
    text = fsread.read_text_capped(root, "README.md", docrules._TEXT_READ_CAP)
    if text is None:
        return False
    return any(line.strip().lower() == "## contributing" for line in text.splitlines())


_NOT_A_TEMPLATE: frozenset[str] = frozenset({"config.yml", "config.yaml"})
"""File names in a template directory that configure the template chooser.
They are not templates, so they do not satisfy a template item."""


def _present(root: Path, candidates: tuple[str, ...]) -> bool:
    """Say whether any candidate path exists on disk.

    Presence is checked on disk, not against `Survey.files`, so a
    git-ignored health file (for example a local `CODEOWNERS` not yet
    tracked) still counts, matching the agent-file check's own "on disk"
    rule (D5.4).

    Every part of a candidate matches without case (D15.14). A candidate
    whose last part holds `*` is a pattern. `config.yml` and `config.yaml`
    never match a pattern.

    Args:
        root: The repository root.
        candidates: Repo-relative paths or patterns to check.

    Returns:
        True when at least one candidate exists.
    """
    return any(_candidate_present(root, candidate) for candidate in candidates)


def _candidate_present(root: Path, candidate: str) -> bool:
    """Say whether one candidate path exists, matching every part without case (D15.14).

    Args:
        root: The repository root.
        candidate: A repo-relative path; a last part with `*` is a pattern.

    Returns:
        True when the path exists. Each directory part and the last part
        match a directory entry in any case.
    """
    *directories, name = candidate.split("/")
    folder = root
    for part in directories:
        folder = _entry_named(folder, part)
        if folder is None or not os.path.isdir(folder):
            return False
    if "*" not in name:
        return _entry_named(folder, name) is not None
    try:
        entries = list(folder.iterdir())
    except OSError:
        return False
    return any(
        os.path.isfile(entry)
        and entry.name.lower() not in _NOT_A_TEMPLATE
        and fnmatch.fnmatch(entry.name.lower(), name.lower())
        for entry in entries
    )


def _entry_named(folder: Path, name: str) -> Path | None:
    """Find the entry of `folder` whose name equals `name` without case.

    Args:
        folder: The directory to list.
        name: The entry name to find.

    Returns:
        The entry, or `None` when none matches or the directory is unreadable.
    """
    exact = folder / name
    if os.path.exists(exact):
        return exact
    try:
        for entry in folder.iterdir():
            if entry.name.lower() == name.lower():
                return entry
    except OSError:
        return None
    return None


def _next_tier(tier: str) -> str | None:
    """Give the tier one step above `tier`.

    Args:
        tier: The current tier.

    Returns:
        The next tier, or `None` when `tier` is already the highest.
    """
    index = _TIER_ORDER.index(tier)
    if index + 1 >= len(_TIER_ORDER):
        return None
    return _TIER_ORDER[index + 1]


def _item_finding(
    root: Path, item: _Item, tier: str, public: bool, tags: int
) -> Finding | None:
    """Build the finding for one health item, if any.

    Args:
        root: The repository root.
        item: The item to check.
        tier: The survey's tier.
        public: `trueup.toml`'s `public` value.
        tags: The survey's `tags` count.

    Returns:
        An `error` finding when the item is required now and missing, an
        `info` finding when it is required only at the next tier and
        missing, or `None` when it is present or not required soon.
    """
    if item.rule == "health-contributing":
        satisfied = _contributing_satisfied(root, item)
    elif item.rule == "health-license":
        satisfied = licence_present(root)
    else:
        satisfied = _present(root, item.candidates)
    if satisfied:
        return None
    if item.required(tier, public, tags):
        return Finding(
            id=f"{item.rule}:",
            rule=item.rule,
            category="health",
            severity="error",
            path="",
            evidence=f"none of {', '.join(item.candidates)} is present",
            action=item.action,
            auto=False,
        )
    next_tier = _next_tier(tier)
    if next_tier is not None and item.required(next_tier, public, tags):
        return Finding(
            id=f"{item.rule}:",
            rule=item.rule,
            category="health",
            severity="info",
            path="",
            evidence=f"required at {next_tier}, not at {tier}",
            action=item.action,
            auto=False,
        )
    return None


def required_item_count(
    tier: str,
    public: bool,
    tags: int,
    *,
    agents: bool = False,
    files: str = "tier",
    licence: bool = True,
) -> int:
    """Count the health items required at one tier (for `score.py`, D5.7, D15.14).

    Args:
        tier: The tier to count against.
        public: `trueup.toml`'s `public` value.
        tags: The survey's `tags` count.
        agents: True when `[health] agents` is on. Then `agents-missing` and
            `claude-not-linked` join the count, except at T0.
        files: `[health] files`; `"readme"` counts the README only.
        licence: False when the target file sets `public = false`; the
            licence row is then not counted.

    Returns:
        The number of `_items` whose `required` function is true at
        `tier`, plus 2 for the agent rows when they apply.
    """
    count = sum(
        1
        for item in _items("docs")
        if _item_wanted(item, files, licence) and item.required(tier, public, tags)
    )
    if agents and tier != "T0":
        count += 2
    return count


def _item_wanted(item: _Item, files: str, licence: bool) -> bool:
    """Say whether config leaves an item in the table (D15.14).

    Args:
        item: The item to test.
        files: `[health] files`.
        licence: False when the licence row is off.

    Returns:
        False for any item but the README under `files = "readme"`, and for
        the licence item when `licence` is false.
    """
    if files == "readme" and item.rule != "health-readme":
        return False
    return licence or item.rule != "health-license"


def _agents_findings(root: Path, tier: str) -> list[Finding]:
    """The agent-file check: `AGENTS.md` and `CLAUDE.md`, from T1 (D5.4).

    Args:
        root: The repository root.
        tier: The survey's tier.

    Returns:
        A `warn` finding for a missing `AGENTS.md`, and a `warn` finding
        for a `CLAUDE.md` that neither links to nor names it; trueup never
        writes either file.
    """
    if tier == "T0":
        return []
    findings: list[Finding] = []
    agents_path = root / "AGENTS.md"
    if not os.path.isfile(agents_path):
        findings.append(
            Finding(
                id="agents-missing:",
                rule="agents-missing",
                category="health",
                severity="warn",
                path="",
                evidence="AGENTS.md is not on disk",
                action="run the agent-file generator",
                auto=False,
            )
        )
    claude_path = root / "CLAUDE.md"
    if os.path.exists(claude_path) and not _claude_links_to_agents(claude_path):
        findings.append(
            Finding(
                id="claude-not-linked:",
                rule="claude-not-linked",
                category="health",
                severity="warn",
                path="CLAUDE.md",
                evidence="CLAUDE.md is neither a symlink to AGENTS.md nor names it",
                action="make CLAUDE.md a symlink to AGENTS.md, or add '@AGENTS.md' to it",
                auto=False,
            )
        )
    return findings


def _claude_links_to_agents(claude_path: Path) -> bool:
    """Say whether `CLAUDE.md` is a symlink to `AGENTS.md`, or names it.

    Args:
        claude_path: The `CLAUDE.md` path to check.

    Returns:
        True when `claude_path` is a symlink resolving to a file named
        `AGENTS.md`, or its text contains `@AGENTS.md`.
    """
    if os.path.islink(claude_path):
        try:
            return claude_path.resolve().name == "AGENTS.md"
        except OSError:
            return False
    text = fsread.read_text_capped(
        claude_path.parent, claude_path.name, docrules._TEXT_READ_CAP
    )
    return text is not None and "@AGENTS.md" in text


_PLACEHOLDER_OWNER = "OWNER"
_PLACEHOLDER_REPO = "REPO"
_PLACEHOLDER_ORG = "ORG"
_PLACEHOLDER_BRANCH = "BRANCH"

_GITHUB_REMOTE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
"""A `github.com` origin, https or ssh form (D7.9)."""

_PLATFORM_ROWS: tuple[tuple[str, str], ...] = (
    (
        "platform:branch-protection",
        "gh api -X PUT repos/{owner}/{repo}/branches/{branch}/protection "
        "-F 'required_pull_request_reviews[required_approving_review_count]=1' "
        "-F enforce_admins=true -F required_status_checks=null "
        "-F restrictions=null -F allow_force_pushes=false -F allow_deletions=false",
    ),
    (
        "platform:mfa",
        "check: gh api orgs/{org} --jq .two_factor_requirement_enabled; "
        "the API cannot set it, so the action also names "
        "https://github.com/organizations/{org}/settings/security",
    ),
    (
        "platform:least-privilege",
        "list: gh api repos/{owner}/{repo}/collaborators --jq "
        "'.[] | select(.permissions.admin) | .login'; "
        "lower one: gh api -X PUT repos/{owner}/{repo}/collaborators/USER "
        "-f permission=push",
    ),
)
"""The rule and the action template of each D7.9 platform row.

The action text only names a `gh` command for a person to run by hand;
trueup itself never calls `gh` (I-31).
"""


def _git_read(root: Path, *args: str) -> str | None:
    """Run one read-only git command and give its trimmed output (D7.9).

    Every call carries `--no-optional-locks`, so it never refreshes
    `.git/index` (I-14).

    Args:
        root: The repository root.
        *args: The git subcommand and its arguments.

    Returns:
        The command's standard output, stripped, or `None` when git is not
        on the path, the command times out, or it exits non-zero.
    """
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _repo_identity(root: Path) -> tuple[str, str, str, str]:
    """Give OWNER, REPO, ORG and BRANCH for the platform action commands (D7.9).

    OWNER, REPO and ORG come from `git remote get-url origin`, read only
    when the remote is a `github.com` URL; ORG is the same text as OWNER,
    GitHub's own namespace. BRANCH comes from `git symbolic-ref --short
    refs/remotes/origin/HEAD`, with the `origin/` prefix removed. A value
    git cannot give, or a remote that is not GitHub, keeps its placeholder.

    Args:
        root: The repository root.

    Returns:
        `(owner, repo, org, branch)`, each a placeholder when unavailable.
    """
    owner, repo, org = _PLACEHOLDER_OWNER, _PLACEHOLDER_REPO, _PLACEHOLDER_ORG
    url = _git_read(root, "remote", "get-url", "origin")
    if url is not None:
        match = _GITHUB_REMOTE.match(url)
        if match is not None:
            owner = match.group("owner")
            repo = match.group("repo").removesuffix(".git")
            org = owner
    branch = _PLACEHOLDER_BRANCH
    ref = _git_read(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ref is not None and ref.startswith("origin/"):
        branch = ref.removeprefix("origin/")
    return owner, repo, org, branch


def _platform_findings(root: Path) -> list[Finding]:
    """Build the three manual platform-control findings (D7.9).

    trueup cannot read branch protection, organization MFA or collaborator
    permissions itself, so each finding only names the `gh` command a
    person runs by hand; trueup never runs `gh` (I-31).

    Args:
        root: The repository root, to read the git remote and branch from.

    Returns:
        One `info` finding per row of `_PLATFORM_ROWS`, each `path=""`.
    """
    owner, repo, org, branch = _repo_identity(root)
    findings: list[Finding] = []
    for rule, action_template in _PLATFORM_ROWS:
        findings.append(
            Finding(
                id=f"{rule}:",
                rule=rule,
                category="security",
                severity="info",
                path="",
                evidence="trueup cannot read this setting; check it on the platform",
                action=action_template.format(
                    owner=owner, repo=repo, org=org, branch=branch
                ),
                auto=False,
            )
        )
    return findings


def health_findings(survey: Survey, cfg: Config | None) -> list[Finding]:
    """Run the D5.4 health table and the agent-file check over one survey.

    `[health] files = "readme"` keeps only the README row. A target file
    that sets `public = false` drops the licence row (D15.14).

    Args:
        survey: The survey to check.
        cfg: The loaded `trueup.toml`, or `None` when it is absent, in
            which case `public` defaults to `False`.

    Returns:
        The findings of every health item and the agent-file check,
        unsorted; `report.py` sorts them (I-21).
    """
    public = cfg.public if cfg is not None else False
    findings: list[Finding] = []
    docs_dir = cfg.layout_docs_dir if cfg is not None else "docs"
    files = cfg.health_files if cfg is not None else "tier"
    licence = cfg is None or not public_is_false(cfg, survey.root)
    for item in _items(docs_dir):
        if not _item_wanted(item, files, licence):
            continue
        finding = _item_finding(survey.root, item, survey.tier, public, survey.tags)
        if finding is not None:
            findings.append(finding)
    if cfg is None or cfg.health_agents:
        findings.extend(_agents_findings(survey.root, survey.tier))
    if public:
        findings.extend(_platform_findings(survey.root))
    return findings
