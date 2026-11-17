"""Tests for `trueup.health`: the D5.4 health table and the agent-file check."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from trueup import health, survey as survey_mod
from trueup.config import load as load_config

_TRUEUP_PACKAGE = Path(__file__).resolve().parent.parent / "trueup"
_PLATFORM_RULES = (
    "platform:branch-protection",
    "platform:mfa",
    "platform:least-privilege",
)


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _write_config(
    root: Path, tier: str, public: bool | None = None, extra: str = ""
) -> None:
    """Write a `trueup.toml` that pins `tier` and `public`, for a deterministic test tier.

    Args:
        root: The repository root.
        tier: The tier to pin: `T0`, `T1`, `T2` or `T3`.
        public: The `public` value to write, or `None` to leave the key out.
        extra: Further TOML text to append.
    """
    line = "" if public is None else f"public = {'true' if public else 'false'}\n"
    (root / "trueup.toml").write_text(
        f'version = 1\ntier = "{tier}"\n{line}{extra}', encoding="utf-8"
    )


def _set_github_origin(root: Path, owner: str, repo: str, branch: str) -> None:
    """Add a `github.com` origin to `root` and point its default branch (D7.9).

    `git symbolic-ref` accepts a ref name that points to no object, so this
    needs no fetch and no real GitHub remote.

    Args:
        root: The git repository, already initialised.
        owner: The GitHub owner (or organization) segment of the origin URL.
        repo: The repository name segment of the origin URL.
        branch: The default branch name.
    """
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{owner}/{repo}.git"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            f"refs/remotes/origin/{branch}",
        ],
        cwd=root,
        check=True,
    )


def _findings_by_rule(root: Path, rule: str) -> list:
    """Survey and check `root`, and give the `health_findings` of one rule.

    Args:
        root: The repository root.
        rule: The rule name to filter on.

    Returns:
        The findings whose `rule` equals `rule`.
    """
    survey = survey_mod.run(root)
    cfg = load_config(root)
    return [
        finding
        for finding in health.health_findings(survey, cfg)
        if finding.rule == rule
    ]


def test_readme_and_gitignore_required_at_t0(tmp_path: Path) -> None:
    """`README.md` and `.gitignore` are required at every tier, T0 included (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T0")
    assert len(_findings_by_rule(tmp_path, "health-readme")) == 1
    assert len(_findings_by_rule(tmp_path, "health-gitignore")) == 1
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-readme") == []
    assert _findings_by_rule(tmp_path, "health-gitignore") == []


def test_license_required_at_t1_not_at_t0_unless_public(tmp_path: Path) -> None:
    """A licence is an `error` from T1 up, and at T0 only when the repo is public (D5.4).

    A private T0 repo still gets an `info` finding, because T1 (the next
    tier) requires a licence; `info` never joins the plan (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T0", public=None)
    findings = _findings_by_rule(tmp_path, "health-license")
    assert len(findings) == 1
    assert findings[0].severity == "info"

    _write_config(tmp_path, "T0", public=True)
    findings = _findings_by_rule(tmp_path, "health-license")
    assert len(findings) == 1
    assert findings[0].severity == "error"

    _write_config(tmp_path, "T1", public=None)
    findings = _findings_by_rule(tmp_path, "health-license")
    assert len(findings) == 1

    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-license") == []


def test_changelog_required_at_t3_and_conditionally_before_that(tmp_path: Path) -> None:
    """A changelog is required at T3 always, and at T1/T2 only once a tag exists (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2")
    findings = _findings_by_rule(tmp_path, "health-changelog")
    assert len(findings) == 1
    assert findings[0].severity == "info"  # required at T3, the next tier

    # `-c commit.gpgsign=false` and `-c tag.gpgsign=false` override this
    # machine's global signing config for this one call only, so the test
    # does not need a GPG key to make a commit and a lightweight tag.
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "x",
            "-q",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "tag.gpgsign=false", "tag", "v0.1.0"], cwd=tmp_path, check=True
    )
    findings = _findings_by_rule(tmp_path, "health-changelog")
    assert len(findings) == 1
    assert findings[0].severity == "error"

    _write_config(tmp_path, "T3")
    assert len(_findings_by_rule(tmp_path, "health-changelog")) == 1


def test_contributing_satisfied_by_readme_section(tmp_path: Path) -> None:
    """A README `## Contributing` heading satisfies the contributing item (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2")
    assert len(_findings_by_rule(tmp_path, "health-contributing")) == 1
    (tmp_path / "README.md").write_text(
        "# Project\n\n## Contributing\n\nSee below.\n", encoding="utf-8"
    )
    assert _findings_by_rule(tmp_path, "health-contributing") == []


def test_security_and_templates_require_public(tmp_path: Path) -> None:
    """Code-of-conduct and the issue and PR templates are required only when public, from T2 (D5.4).

    `health-security` is the one item of this group that D7.6 lifts to every
    tier, so it is checked on its own in
    `test_security_required_at_every_tier_when_public`.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2", public=False)
    for rule in (
        "health-code-of-conduct",
        "health-issue-template",
        "health-pr-template",
    ):
        assert _findings_by_rule(tmp_path, rule) == [], rule

    _write_config(tmp_path, "T2", public=True)
    for rule in (
        "health-code-of-conduct",
        "health-issue-template",
        "health-pr-template",
    ):
        findings = _findings_by_rule(tmp_path, rule)
        assert len(findings) == 1, rule
        assert findings[0].severity == "error"


def test_issue_template_satisfied_by_any_template_in_the_issue_template_folder(
    tmp_path: Path,
) -> None:
    """Any `.md` or `.yml` template in `.github/ISSUE_TEMPLATE/` satisfies the item (D5.4).

    GitHub reads every template in that folder, not only `bug_report.md`.
    The chooser file `config.yml` alone is not a template.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2", public=True)
    folder = tmp_path / ".github" / "ISSUE_TEMPLATE"
    folder.mkdir(parents=True)
    (folder / "config.yml").write_text(
        "blank_issues_enabled: false\n", encoding="utf-8"
    )
    assert len(_findings_by_rule(tmp_path, "health-issue-template")) == 1
    (folder / "feature.yml").write_text("name: Feature\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-issue-template") == []


def test_pr_template_satisfied_at_each_location_github_reads(tmp_path: Path) -> None:
    """A pull request template counts at the root, in `docs/` or in `.github/`, in any case (D5.4).

    GitHub also reads a `PULL_REQUEST_TEMPLATE/` folder in each of the
    three places, and a `.txt` template.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2", public=True)
    assert len(_findings_by_rule(tmp_path, "health-pr-template")) == 1
    for rel in (
        "PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.txt",
        ".github/PULL_REQUEST_TEMPLATE/feature.md",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("## Summary\n", encoding="utf-8")
        assert _findings_by_rule(tmp_path, "health-pr-template") == [], rel
        path.unlink()


def test_security_required_at_every_tier_when_public(tmp_path: Path) -> None:
    """`SECURITY.md` is required at every tier once the repository is public, T0 through T3 (D7.6).

    A rule that held at T0 and T2 but not at T1 had no reason, so D7.6 drops
    the tier condition: the requirement now follows `public` alone, at every
    tier `_TIER_ORDER` names.

    arch: D7.6
    """
    _git_init(tmp_path)
    for tier in ("T0", "T1", "T2", "T3"):
        _write_config(tmp_path, tier, public=False)
        assert _findings_by_rule(tmp_path, "health-security") == [], tier

        _write_config(tmp_path, tier, public=True)
        findings = _findings_by_rule(tmp_path, "health-security")
        assert len(findings) == 1, tier
        assert findings[0].severity == "error"

    (tmp_path / "SECURITY.md").write_text("report issues privately\n", encoding="utf-8")
    _write_config(tmp_path, "T0", public=True)
    assert _findings_by_rule(tmp_path, "health-security") == []


def test_codeowners_required_only_at_t3(tmp_path: Path) -> None:
    """`CODEOWNERS` is required only at T3 (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2")
    findings = _findings_by_rule(tmp_path, "health-codeowners")
    assert len(findings) == 1
    assert findings[0].severity == "info"  # required at T3, the next tier
    _write_config(tmp_path, "T3")
    assert len(_findings_by_rule(tmp_path, "health-codeowners")) == 1


def test_item_required_at_next_tier_is_info_not_error(tmp_path: Path) -> None:
    """An item required only at the next tier is an `info` finding, and never joins the plan.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1")
    findings = _findings_by_rule(tmp_path, "health-contributing")
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "T2" in findings[0].evidence


def test_agents_missing_warns_from_t1(tmp_path: Path) -> None:
    """A missing `AGENTS.md` is a `warn` from T1, and no finding at T0 (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T0")
    assert _findings_by_rule(tmp_path, "agents-missing") == []
    _write_config(tmp_path, "T1")
    findings = _findings_by_rule(tmp_path, "agents-missing")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].auto is False


def test_claude_md_present_and_unlinked_warns(tmp_path: Path) -> None:
    """A `CLAUDE.md` that neither symlinks to nor names `AGENTS.md` is a `warn` (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1")
    (tmp_path / "AGENTS.md").write_text("agent notes\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("unrelated notes\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "claude-not-linked")
    assert len(findings) == 1
    assert findings[0].severity == "warn"


def test_claude_md_naming_agents_is_satisfied(tmp_path: Path) -> None:
    """A `CLAUDE.md` that contains `@AGENTS.md` is treated as linked (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1")
    (tmp_path / "AGENTS.md").write_text("agent notes\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "claude-not-linked") == []


def test_claude_md_symlink_to_agents_is_satisfied(tmp_path: Path) -> None:
    """A `CLAUDE.md` symlink to `AGENTS.md` is treated as linked (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1")
    (tmp_path / "AGENTS.md").write_text("agent notes\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").symlink_to(tmp_path / "AGENTS.md")
    assert _findings_by_rule(tmp_path, "claude-not-linked") == []


def test_required_item_count_matches_the_tier_table() -> None:
    """`required_item_count` counts README, .gitignore, the licence and the security policy at T0 for a public repo (D5.7, D7.6).

    The count is 4, not 3, because D7.6 makes `SECURITY.md` required at
    every tier once the repository is public, T0 included.

    arch: D5.7, D7.6
    """
    assert health.required_item_count("T0", public=False, tags=0) == 2
    assert health.required_item_count("T0", public=True, tags=0) == 4


def test_platform_findings_fire_with_filled_values_when_public(tmp_path: Path) -> None:
    """A public repository gets the three `platform:*` findings, with OWNER, REPO, ORG and BRANCH filled in (D7.9).

    arch: D7.9
    """
    _git_init(tmp_path)
    _set_github_origin(tmp_path, "acme", "widget", "main")
    _write_config(tmp_path, "T0", public=True)
    findings = {
        finding.rule: finding
        for finding in health.health_findings(
            survey_mod.run(tmp_path), load_config(tmp_path)
        )
        if finding.rule in _PLATFORM_RULES
    }
    assert set(findings) == set(_PLATFORM_RULES)
    for finding in findings.values():
        assert finding.category == "security"
        assert finding.severity == "info"  # D15.15
        assert finding.auto is False
        assert finding.path == ""
        assert "OWNER" not in finding.action
        assert "REPO" not in finding.action
        assert "ORG" not in finding.action
        assert "BRANCH" not in finding.action

    branch_protection = findings["platform:branch-protection"].action
    assert "repos/acme/widget/branches/main/protection" in branch_protection
    assert "gh api orgs/acme" in findings["platform:mfa"].action
    assert "organizations/acme/settings/security" in findings["platform:mfa"].action
    assert (
        "repos/acme/widget/collaborators" in findings["platform:least-privilege"].action
    )


def test_platform_findings_use_placeholders_with_no_github_origin(
    tmp_path: Path,
) -> None:
    """A public repository with no GitHub origin keeps the OWNER/REPO/ORG/BRANCH placeholders (D7.9).

    arch: D7.9
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T0", public=True)
    action = next(
        finding.action
        for finding in health.health_findings(
            survey_mod.run(tmp_path), load_config(tmp_path)
        )
        if finding.rule == "platform:branch-protection"
    )
    assert "repos/OWNER/REPO/branches/BRANCH/protection" in action


def test_platform_findings_absent_when_private(tmp_path: Path) -> None:
    """A private repository gets none of the three `platform:*` findings (D7.9).

    arch: D7.9
    """
    _git_init(tmp_path)
    _set_github_origin(tmp_path, "acme", "widget", "main")
    _write_config(tmp_path, "T0", public=False)
    findings = health.health_findings(survey_mod.run(tmp_path), load_config(tmp_path))
    assert not any(finding.rule in _PLATFORM_RULES for finding in findings)


def test_trueup_never_calls_gh() -> None:
    """No `trueup/*.py` subprocess call runs `gh` (I-31).

    The platform findings only print a `gh` command in prose, as the action
    text of a manual finding; trueup runs no such command itself. This ast
    scan is the inline enforcement of that invariant.

    arch: I-31
    """
    offenders = []
    for path in sorted(_TRUEUP_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_subprocess_call = (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ) or (isinstance(func, ast.Name) and func.id in ("run", "call", "Popen"))
            if not is_subprocess_call or not node.args:
                continue
            first_arg = node.args[0]
            if (
                isinstance(first_arg, ast.List)
                and first_arg.elts
                and isinstance(first_arg.elts[0], ast.Constant)
                and first_arg.elts[0].value == "gh"
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_contributing_found_under_the_configured_docs_dir(tmp_path: Path) -> None:
    """A guide under `[layout] docs_dir` satisfies the contributing row.

    arch: D14.4, D14.9
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T2")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CONTRIBUTING.md").write_text("x\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-contributing") == []
    (tmp_path / "docs" / "CONTRIBUTING.md").rename(tmp_path / "docs" / "other.md")
    (tmp_path / "trueup.toml").write_text(
        'tier = "T2"\n\n[layout]\ndocs_dir = "manual"\n', encoding="utf-8"
    )
    (tmp_path / "manual").mkdir()
    (tmp_path / "manual" / "CONTRIBUTING.md").write_text("x\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-contributing") == []


def test_agents_rows_follow_health_agents(tmp_path: Path) -> None:
    """`[health] agents = false` drops the agent-file rows.

    arch: D14.4, D14.9
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1")
    assert len(_findings_by_rule(tmp_path, "agents-missing")) == 1
    (tmp_path / "trueup.toml").write_text(
        'tier = "T1"\n\n[health]\nagents = false\n', encoding="utf-8"
    )
    assert _findings_by_rule(tmp_path, "agents-missing") == []


def test_health_actions_name_trueup_template(tmp_path: Path) -> None:
    """The action text names `trueup template <name>`, not a template path.

    arch: D14.4, D14.9
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T3")
    action = _findings_by_rule(tmp_path, "health-contributing")[0].action
    assert "trueup template contributing" in action
    assert "templates/health" not in action


def test_health_names_match_without_case_and_with_the_extra_candidates(
    tmp_path: Path,
) -> None:
    """Every health candidate matches in any case; `LICENCE`, `.rst` and `CHANGES.md` count.

    arch: D15.14, D15.15
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T3")
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-readme") == []
    (tmp_path / "Licence.txt").write_text("MIT\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-license") == []
    (tmp_path / "contributing.rst").write_text("how\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-contributing") == []
    assert len(_findings_by_rule(tmp_path, "health-changelog")) == 1
    (tmp_path / "CHANGES.md").write_text("x\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-changelog") == []
    (tmp_path / "CHANGES.md").unlink()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "changelog.md").write_text("x\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "health-changelog") == []


def test_public_false_in_the_target_file_drops_the_licence_row(tmp_path: Path) -> None:
    """An explicit `public = false` suppresses `health-license`; an unset `public` keeps it.

    arch: D15.14, D15.15
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T1", public=None)
    assert len(_findings_by_rule(tmp_path, "health-license")) == 1
    _write_config(tmp_path, "T1", public=False)
    assert _findings_by_rule(tmp_path, "health-license") == []


def test_health_files_readme_requires_the_readme_only(tmp_path: Path) -> None:
    """`[health] files = "readme"` leaves `health-readme` as the only health row.

    arch: D15.14, D15.15
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T3", extra='[health]\nfiles = "readme"\n')
    rules = {
        finding.rule
        for finding in health.health_findings(
            survey_mod.run(tmp_path), load_config(tmp_path)
        )
        if finding.rule.startswith("health-")
    }
    assert rules == {"health-readme"}


def test_required_item_count_counts_the_agent_rows_and_the_config(
    tmp_path: Path,
) -> None:
    """The agent rows join the count above T0; `files` and `licence` shrink it.

    arch: D15.14, D15.15
    """
    base = health.required_item_count("T1", public=False, tags=0)
    assert (
        health.required_item_count("T1", public=False, tags=0, agents=True) == base + 2
    )
    assert health.required_item_count("T0", public=False, tags=0, agents=True) == 2
    assert (
        health.required_item_count("T1", public=False, tags=0, licence=False)
        == base - 1
    )
    assert health.required_item_count("T3", public=True, tags=0, files="readme") == 1


def test_platform_findings_are_info_and_stay_out_of_the_plan(tmp_path: Path) -> None:
    """The three `platform:*` rows are `info` with category `security`.

    arch: D15.14, D15.15
    """
    _git_init(tmp_path)
    _write_config(tmp_path, "T0", public=True)
    findings = [
        finding
        for finding in health.health_findings(
            survey_mod.run(tmp_path), load_config(tmp_path)
        )
        if finding.rule in _PLATFORM_RULES
    ]
    assert len(findings) == 3
    assert {(f.severity, f.category) for f in findings} == {("info", "security")}


def test_tidy_public_t0_tree_has_plan_zero_and_exit_zero(
    tmp_path: Path, capsys
) -> None:
    """A tidy public T0 tree gives a plan of 0 rows and exit 0; platform rows are info.

    arch: D15.14, D15.15
    """
    from trueup import cli

    _git_init(tmp_path)
    _write_config(tmp_path, "T0", public=True, extra='docs = "readme"\n')
    (tmp_path / "README.md").write_text("# A tiny project\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc\n.scratch/\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
    assert cli.main(["check", "--root", str(tmp_path), "--json"]) == 0
    out = capsys.readouterr().out
    assert '"plan": []' in out or '"plan":[]' in out
