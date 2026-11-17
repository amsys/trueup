"""The `check` driver: survey, findings, score, then a Markdown or JSON report (D5.11, D5.7).

`collect` is the one place the finding rows meet: it loads `trueup.toml`,
surveys the target, runs the hygiene, health, document, layout and setup
rows, marks protected findings manual, and builds the plan. `check` (what
`trueup.cli._run_check` calls) renders that result and `trueup.apply`
validates its ids against it. `check` refuses an `--out` that points inside
`root` unless an `ignore` glob covers it, so I-18 holds without the caller's
help (LOW-1). Its return value is the process exit code.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from trueup import baseline as baseline_mod
from trueup import changes as changes_mod
from trueup import config as config_mod
from trueup import (
    docrules,
    drift,
    health,
    hygiene,
    layout,
    managed,
    secrets,
    survey as survey_mod,
)
from trueup.baseline import Gate
from trueup.config import Config
from trueup.findings import (
    Finding,
    build_plan,
    keep_match,
    protect_findings,
    sorted_findings,
    stale_keeps,
)
from trueup.score import Score, compute

_SEVERITY_LABEL: dict[str, str] = {"error": "ERROR", "warn": "WARN", "info": "INFO"}

REPORT_NAMES: tuple[str, str] = ("trueup-report.md", "trueup-report.json")
"""The two file names that `check --out` writes: Markdown, then JSON."""

JSON_SCHEMA = 1
"""The value of the `schema` key of every `check --json` report (D15.3)."""

_NOT_ADOPTED_PROFILE_LINE = (
    "profile minimal (no trueup.toml; pass --profile house for the house standard)"
)
"""The profile header line of a target that is not adopted (D15.3, D15.6)."""

_PROSE_HINT_WORD_FLOOR = 10
"""D6.9: at or above this many distinct banned words in one `prose`
finding, the file more likely quotes the list than misuses it."""

_PROSE_EVIDENCE_HIT = re.compile(r" \(line \d+\)")
"""One `docrules._prose_findings` evidence entry ends this way,
`'word' (line N)`; counting these counts the distinct words without caring
whether `repr` quoted a word with `'` or `"`."""

_PROSE_KEEP_HINT = (
    "hint: this file may quote the list on purpose; add a [[keep]] entry with a reason"
)
"""The D6.9 hint line adds under a policy-sized `prose` finding."""


def check(
    root: Path,
    as_json: bool,
    out: Path | None,
    baseline: bool = False,
    sarif: Path | None = None,
) -> int:
    """Run `check` against one target repository.

    Args:
        root: The target repository root.
        as_json: Print the JSON report on standard output instead of
            Markdown.
        out: A directory to also write `trueup-report.md` and
            `trueup-report.json` into.
        baseline: Compare the plan against `.trueup-baseline.json` (D6.7).
            `check` still writes nothing of its own (I-18, I-16): it only
            reads the baseline file through `trueup.baseline.load`. The
            secret scan then reads the git history, the same mode as
            `trueup baseline` (D7.3 rule 6).
        sarif: A file to also write the SARIF 2.1.0 report to (arch: D12.4).
            It follows the same refusal rule as `out`.

    Returns:
        With `baseline=False`: 0 when the plan is empty, 1 when it holds at
        least one finding, 2 when `out` is inside `root` and no `ignore`
        glob covers it (LOW-1). With `baseline=True`: 2 when no baseline
        file exists, else 0 or 1 from `trueup.baseline.failed` (D6.7); the
        plan being non-empty no longer decides the exit code on its own.

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid.
    """
    # D12.1: read the tree identity before the rows read the files, so a
    # file that changes during the run makes the saved plan stale.
    # D15.1: load the config first, so an unreadable `trueup.toml` is named
    # as such and not as a git failure.
    config_mod.load(root)
    tree = changes_mod.tree_identity(root)
    run = collect(root, history=baseline)
    if out is not None and _out_refused(root, out, run.cfg):
        print(
            f"trueup: --out {out} is inside root and no ignore glob covers it",
            file=sys.stderr,
        )
        return 2
    if sarif is not None and _sarif_refused(root, sarif, run.cfg):
        return 2
    score = compute(run.plan, run.survey, run.cfg)

    gate: Gate | None = None
    if baseline:
        base = baseline_mod.load(root)
        if base is None:
            print("no baseline: run trueup baseline", file=sys.stderr)
            return 2
        ratchet_now = baseline_mod.ratchet_values(run.survey, run.cfg)
        gate = baseline_mod.compare(base, run, ratchet_now)

    kept = kept_findings(run)
    moves = tuple(run.moves)
    profile = profile_block(root)
    markdown = render_markdown(
        run.survey,
        run.findings,
        run.plan,
        score,
        kept,
        gate,
        moves,
        secret_engine=run.secret_engine,
        secret_note=run.secret_note,
        repins=tuple(run.repins),
        tree=tree,
        profile=profile,
    )
    data = render_json(
        run.survey,
        run.findings,
        run.plan,
        score,
        kept,
        gate,
        moves,
        secret_engine=run.secret_engine,
        secret_note=run.secret_note,
        tree=tree,
        repins=tuple(run.repins),
        profile=profile,
    )

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / REPORT_NAMES[0]).write_text(
            markdown,
            encoding="utf-8",
            errors="surrogateescape",  # arch: D12.10
        )
        (out / REPORT_NAMES[1]).write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            errors="surrogateescape",  # arch: D12.10
        )

    if sarif is not None:
        _write_sarif(sarif, run, kept)

    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(markdown, end="")

    if gate is not None:
        return 1 if baseline_mod.failed(gate) else 0
    return 0 if not run.plan else 1


def profile_block(root: Path) -> dict[str, str]:
    """Give the profile of a run: its name, its file and its layer (arch: D14.3, D14.18, D15.6).

    The profile resolves on every target, so a target that is not adopted
    gets the built-in default `minimal`. The config layers are cached, so
    this call reads no file again after `collect` loaded them.

    Args:
        root: The target repository root.

    Returns:
        `{"name": <name>, "path": <file>, "source": <layer>}`. The source
        is one of `config.PROFILE_SOURCES` (arch: D15.3).

    Raises:
        trueup.config.ConfigError: A config file is invalid, or the profile
            name resolves to no file.
    """
    layers = config_mod.load_layers(root)
    return {
        "name": layers.profile,
        "path": str(layers.profile_path),
        "source": layers.profile_source,
    }


def check_changed(root: Path, as_json: bool, sarif: Path | None = None) -> int:
    """Run `trueup check --changed`, the D6.17 scoped view of this session's own edits.

    The scope is `changes.working_set(root)`: the working tree against
    `HEAD`, plus untracked files. `refcheck` does not run, and a repo-wide
    finding (`health`, `setup`, `root-budget`) never shows: see `collect`'s
    `only` argument.

    Args:
        root: The target repository root.
        as_json: Print the JSON report instead of Markdown.
        sarif: A file to also write the SARIF report to (arch: D12.4).

    Returns:
        1 when the scoped plan holds a finding, else 0 (arch: D6.17). 2
        when `sarif` is refused (arch: D12.4).

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid, or
            `root` is not inside a git repository.
    """
    only = changes_mod.working_set(root)
    # D12.1, D15.3: the tree identity comes before the rows read the files.
    tree = changes_mod.tree_identity(root)
    run = collect(root, only=only)
    kept = kept_findings(run)
    if sarif is not None:
        if _sarif_refused(root, sarif, run.cfg):
            return 2
        _write_sarif(sarif, run, kept)
    if as_json:
        data = render_changed_json(
            run, kept=kept, tree=tree, profile=profile_block(root)
        )
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(render_changed_markdown(run), end="")
    return 0 if not run.plan else 1


def _out_refused(
    root: Path,
    out: Path,
    cfg: Config | None,
    names: tuple[str, ...] = REPORT_NAMES,
) -> bool:
    """Say whether `check` must refuse `--out` before writing anything (LOW-1).

    Args:
        root: The target repository root.
        out: The `--out` directory the caller gave.
        cfg: The loaded config, for its `ignore` globs.
        names: The file names written into `out`. The default is the two
            report files; `--sarif` passes its own file name (arch: D12.4).

    Returns:
        True when `out` resolves under `root` and the `ignore` globs of
        `cfg` do not match every file path. The survey filters
        file paths, not directories, so this tests the two file paths
        (I-18: an unmatched report file is surveyed on the next `check`).
    """
    try:
        relative = out.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    ignore = cfg.ignore if cfg is not None else ()
    return not all(
        survey_mod.matches_ignore((relative / name).as_posix(), ignore)
        for name in names
    )


def _sarif_refused(root: Path, sarif: Path, cfg: Config | None) -> bool:
    """Say whether `--sarif` must be refused, and print the reason (arch: D12.4).

    Args:
        root: The target repository root.
        sarif: The SARIF file the caller gave.
        cfg: The loaded config, for its `ignore` globs.

    Returns:
        True when the file is inside `root` and no `ignore` glob covers it.
    """
    if not _out_refused(root, sarif.resolve().parent, cfg, (sarif.name,)):
        return False
    print(
        f"trueup: --sarif {sarif} is inside root and no ignore glob covers it",
        file=sys.stderr,
    )
    return True


def _write_sarif(sarif: Path, run: CheckRun, kept: list[tuple[Finding, str]]) -> None:
    """Write the SARIF report of one run to a file (arch: D12.4).

    Args:
        sarif: The file to write. Its parent directory is created.
        run: The check result.
        kept: The kept findings, from `kept_findings`.
    """
    document = render_sarif(run.findings, {finding.id for finding, _ in kept})
    sarif.parent.mkdir(parents=True, exist_ok=True)
    sarif.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


_SARIF_LEVELS: dict[str, str] = {"error": "error", "warn": "warning", "info": "note"}
"""SARIF level for each finding severity (arch: D12.4)."""

_SARIF_RANK: dict[str, int] = {"note": 0, "warning": 1, "error": 2}
"""Order of the SARIF levels, so a rule gets its worst level (arch: D12.4)."""


def render_sarif(findings: list[Finding], kept_ids: set[str]) -> dict[str, object]:
    """Render findings as one SARIF 2.1.0 run (arch: D12.4).

    Args:
        findings: Every finding of the run, in finding order.
        kept_ids: Ids of the findings a `[[keep]]` entry holds out. They
            give no result.

    Returns:
        The SARIF document. One rule per distinct rule name, at the worst
        level of its results. A finding with an empty path has no
        `locations`.
    """
    results: list[dict[str, object]] = []
    rule_levels: dict[str, str] = {}
    for finding in findings:
        if finding.id in kept_ids:
            continue
        level = _SARIF_LEVELS.get(finding.severity, "note")
        current = rule_levels.get(finding.rule)
        if current is None or _SARIF_RANK[level] > _SARIF_RANK[current]:
            rule_levels[finding.rule] = level
        result: dict[str, object] = {
            "ruleId": finding.rule,
            "level": level,
            "message": {"text": f"{finding.evidence} \u2014 {finding.action}"},
            "partialFingerprints": {"trueupId/v1": finding.id},
        }
        if finding.path:
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": finding.path},
                        "region": {"startLine": _sarif_line(finding)},
                    }
                }
            ]
        results.append(result)
    rules = [
        {"id": rule, "defaultConfiguration": {"level": level}}
        for rule, level in rule_levels.items()
    ]
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {"tool": {"driver": {"name": "trueup", "rules": rules}}, "results": results}
        ],
    }


def _sarif_line(finding: Finding) -> int:
    """Give the line of a finding: `finding.line`, else the line of a `refcheck:` id, else 1 (D15.8).

    Args:
        finding: The finding.

    Returns:
        The 1-based line number.
    """
    if finding.line > 0:
        return finding.line
    prefix = f"refcheck:{finding.path}:"
    if finding.id.startswith(prefix):
        match = re.match(r"\d+", finding.id[len(prefix) :])
        if match:
            return max(int(match.group()), 1)
    return 1


@dataclass(frozen=True)
class CheckRun:
    """The result of one pass over a target, before it is rendered.

    Attributes:
        survey: The survey of the target.
        cfg: The loaded `trueup.toml`, or `None` when it is absent.
        findings: Every finding of the rows, sorted (I-21).
        plan: The plan: `error` and `warn` findings not kept (D5.4).
        moves: The move plan `layout.locate` proposed (D10.6). Empty under
            a scoped run (D10.6, D10.12). A move is not a finding: it is
            not in `plan`, and the score does not read it.
        secret_engine: The secret engine that gave the secret-content
            findings: `"gitleaks"` or `"built-in"` (D7.3).
        secret_note: An empty string, or why gitleaks did not run to the
            end (D7.3 rule 3).
        repins: The re-pin entries, sorted by id (arch: D12.6). Empty under
            a scoped run, since `refcheck` does not run there. A repin is
            not a finding: it is not in `plan`.
    """

    survey: survey_mod.Survey
    cfg: Config | None
    findings: list[Finding]
    plan: list[Finding]
    moves: list[layout.Move] = field(default_factory=list)
    secret_engine: str = "built-in"  # noqa: S105  # reason: an engine name ("gitleaks" or "built-in"), not a credential
    secret_note: str = ""
    repins: list[docrules.Repin] = field(default_factory=list)


def collect(
    root: Path, only: frozenset[str] | None = None, history: bool = False
) -> CheckRun:
    """Run every finding row over one target and build the plan (D5.4).

    The rows are hygiene, health, document rules, setup and drift (D6.5).
    The document and drift rows get a copy of the survey with each
    `secret-file` path taken out, so their file reads never open a secret
    file (I-23).

    Args:
        root: The target repository root.
        only: Repo-relative POSIX paths to scope the run to (arch: D6.17).
            `None` runs every row, `refcheck` included, matching v1's own
            rows byte for byte (I-21) with the D6.5 drift rows added on top,
            since drift is a v2 row with no v1 shape to hold to. A value
            skips the `health` and `setup` rows, narrows the `scratch`,
            `artifact` and `duplicate` rows to `only` (D14.14), narrows
            the files the document rows read to the paths `only` holds (and skips
            `refcheck`), gives the drift rows their full-run findings for
            those paths (`drift.drift_findings`), then keeps only the
            findings whose own `path` is in `only`; a
            repo-wide finding (an empty `path`) is always dropped, since it
            names no single changed file.
        history: Scan the git history for secrets, not the working tree
            (D7.3 rule 5a). `trueup baseline` and `check --baseline` give
            `True`; every other caller keeps the default.

    Returns:
        The survey, the config, the sorted findings and the plan, plus the
        secret engine and its note. In scoped
        mode both lists hold only the findings `only` keeps. A full run
        adds one `keep-stale` info row for each `[[keep]]` id that matches
        no finding (D15.8).

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid, or
            the survey holds no file (arch: D15.2).
    """
    cfg = config_mod.load(root)
    # D6.6: the baseline file is data, so no row and no score term sees it;
    # `trueup baseline` measures the repo before the file exists. The
    # `trueup survey` command drops it too, so both commands give the same
    # `files`.
    survey = hygiene.drop_managed_data_files(survey_mod.run(root))
    if not survey.files:
        raise config_mod.ConfigError(
            f"{root}: no tracked file to check (after [scan] ignore)"
        )
    # D7.3 rule 5a: one secret scan per run. `None` (no gitleaks) and a
    # failed run both keep the built-in `secret-content` row. A scoped run
    # scans only the changed tracked files (D14.14).
    engine_run = secrets.scan(root, survey, history, only=None if history else only)
    gitleaks_ran = engine_run is not None and engine_run.engine == "gitleaks"
    findings = hygiene.hygiene_findings(
        survey, engine_run.findings if gitleaks_ran else None, only=only
    )
    if engine_run is not None and engine_run.engine != "gitleaks" and engine_run.note:
        # D15.20: a gitleaks failure is a visible row, not a quiet fallback.
        findings.append(secrets.engine_failure_finding(engine_run.note))
    secret_paths = {
        finding.path for finding in findings if finding.rule == "secret-file"
    }
    readable = replace(
        survey, files=tuple(path for path in survey.files if path not in secret_paths)
    )
    if only is None:
        findings.extend(health.health_findings(survey, cfg))
        findings.extend(docrules.docrules_findings(readable, cfg))
        # D15.6: the setup rows describe what adoption writes, so a target
        # that is not adopted gives them no config.
        adopted = config_mod.load_layers(root).adopted
        findings.extend(managed.setup_findings(survey, cfg if adopted else None))
    else:
        findings.extend(docrules.docrules_findings(readable, cfg, only=only))
    # D10.2, D10.6: the locator needs the scratch set (`hygiene_findings`)
    # and the refcheck `broken-link` findings (`docrules_findings`), both
    # already in `findings` at this point; it runs before `protect_findings`
    # since its own findings are already `auto=False` (D10.2) and need no
    # protect pass of their own.
    layout_result = layout.locate(root, readable, cfg, findings, only=only)
    findings.extend(layout_result.findings)
    findings = _apply_evidence_notes(findings, layout_result.evidence_notes)
    findings.extend(
        drift.drift_findings(
            readable, only, _ignored_paths(root, drift.missing_command_paths(readable))
        )
    )
    findings = protect_findings(findings, cfg.protect if cfg is not None else ())
    keep = dict(cfg.keep) if cfg is not None else {}
    plan = build_plan(findings, keep)
    if only is None:
        # D15.8: only a full run sees every finding, so only a full run can
        # tell that a keep matches nothing.
        findings.extend(stale_keeps(findings, keep))
    all_findings = sorted_findings(findings)
    if only is not None:
        all_findings = [finding for finding in all_findings if _in_scope(finding, only)]
        plan = [finding for finding in plan if _in_scope(finding, only)]
    return CheckRun(
        survey=survey,
        cfg=cfg,
        findings=all_findings,
        plan=plan,
        moves=layout_result.moves,
        secret_engine=engine_run.engine if engine_run is not None else "built-in",
        secret_note=engine_run.note if engine_run is not None else "",
        repins=list(docrules.repins(root, all_findings)) if only is None else [],
    )


def _ignored_paths(root: Path, tokens: list[str]) -> frozenset[str]:
    """Give the tokens that git ignores, by one `git check-ignore` (arch: D15.17).

    Args:
        root: The repository root.
        tokens: Missing command-path tokens from `drift.missing_command_paths`.

    Returns:
        The tokens git ignores; empty when `tokens` is empty or git fails
        (a failed call must not hide a drift row).
    """
    if not tokens:
        return frozenset()
    relative = {
        token: (token[2:] if token.startswith("./") else token) for token in tokens
    }
    stdin = "\0".join(relative.values()) + "\0"
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=root,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if result.returncode not in (0, 1):
        return frozenset()
    hit = {part for part in result.stdout.split("\0") if part}
    return frozenset(token for token, path in relative.items() if path in hit)


def _apply_evidence_notes(
    findings: list[Finding], notes: dict[str, str]
) -> list[Finding]:
    """Append a `layout.locate` broken-link hint to its own refcheck finding's evidence (D10.6, I-39).

    Args:
        findings: The merged findings so far.
        notes: Finding id to hint text, from
            `layout.LayoutResult.evidence_notes`.

    Returns:
        A new list in the same order. A finding named in `notes` keeps its
        id and gets the hint appended to its evidence with
        `dataclasses.replace`; every other finding is returned unchanged.
    """
    if not notes:
        return findings
    return [
        replace(finding, evidence=f"{finding.evidence}; {notes[finding.id]}")
        if finding.id in notes
        else finding
        for finding in findings
    ]


def _in_scope(finding: Finding, only: frozenset[str]) -> bool:
    """Say whether a scoped `collect` run keeps one finding (arch: D6.17).

    A scoped run never calls the `health` or `setup` rows, so neither
    category reaches this function; the one repo-wide row it still runs,
    `root-budget` (`hygiene._root_budget`), carries an empty `path` and is
    dropped here on that ground, the same as any other repo-wide finding.

    Args:
        finding: The finding to test.
        only: The paths the scoped run is limited to.

    Returns:
        `True` for the `secret-engine` row (D15.20); `False` for another
        repo-wide finding (an empty `path`), else whether `finding.path`
        is in `only`.
    """
    if finding.rule == "secret-engine":
        return True  # D15.20: a failed secret scan matters to a scoped run too
    if not finding.path:
        return False
    return finding.path in only


def kept_findings(run: CheckRun) -> list[tuple[Finding, str]]:
    """List the `error` and `warn` findings a `[[keep]]` entry holds out of the plan.

    A keep id matches as `findings.keep_match` says: exact first, else the
    longest segment prefix (D15.8).

    Args:
        run: The check result.

    Returns:
        Each kept finding with the reason of the keep that matched it, in
        finding order (I-21).
    """
    keep = run.cfg.keep if run.cfg is not None else {}
    kept: list[tuple[Finding, str]] = []
    for finding in run.findings:
        if finding.severity not in ("error", "warn"):
            continue
        matched = keep_match(finding.id, keep)
        if matched is not None:
            kept.append((finding, keep[matched]))
    return kept


def render_markdown(
    survey: survey_mod.Survey,
    findings: list[Finding],
    plan: list[Finding],
    score: Score,
    kept: list[tuple[Finding, str]],
    gate: Gate | None = None,
    moves: tuple[layout.Move, ...] = (),
    *,
    secret_engine: str,
    secret_note: str,
    repins: tuple[docrules.Repin, ...] = (),
    tree: dict[str, str] | None = None,
    profile: dict[str, str] | None = None,
) -> str:
    """Render the Markdown report of one check run (D5.11).

    Every finding appears in one of three sections: the plan, `Kept` (an
    `error` or `warn` finding a `[[keep]]` entry names, with its reason) or
    `Info`, so the text lists the same findings as the JSON report. A move
    is not a finding, so it is not in any of the three.

    A line with an id that `apply --ids` accepts starts with an empty box
    `- [ ] <id>`: an automatic plan finding, the setup opt-in row, a move
    and a re-pin entry (arch: D12.3). These are the keys of
    `trueup.apply.approvable`. `apply --from-report` reads the ticked boxes.

    Args:
        survey: The survey the report is about.
        findings: Every finding, sorted (I-21).
        plan: The plan: the findings the person is asked to act on.
        score: The slop score of this run.
        kept: The kept findings with their reasons, from `kept_findings`.
        gate: The `check --baseline` result, or `None` for a plain `check`
            (D6.7). When given, a `## Baseline` section is appended.
        moves: The move plan (D10.6). A `## Move plan (n)` section follows
            `## Plan` when it is not empty; empty by default, and always
            empty under a scoped run (D10.12).
        secret_engine: The secret engine of the run, printed on the line
            after `counter` (D7.3 rule 6).
        secret_note: The engine note; when not empty it follows the engine
            in brackets.
        repins: The re-pin entries (arch: D12.6). A `## Re-pin plan (n)`
            section follows the move plan when it is not empty; each entry
            is one box line `- [ ] <id> → pin:<new> (<target>)` (D12.3).
        tree: The tree identity of the run, from `changes.tree_identity`
            (arch: D12.3). When given, line 2 is the comment
            `<!-- trueup tree head=<head> status=<status> -->`, which
            `apply --from-report` compares with the tree it runs on.
        profile: The profile of the run, from `profile_block` (arch:
            D14.3). When given, the header line before `tier` is
            `_profile_line` of it. `None` gives no line.

    Returns:
        The Markdown text, ending in a newline.
    """
    lines = ["# trueup check"]
    if tree is not None:
        lines.append(tree_comment(tree))
    lines.append("")
    if profile is not None:
        lines.append(_profile_line(profile))
    lines += [
        f"tier {_tier_text(survey)}",
        f"counter {survey.counter}",
        f"secrets {secret_engine}" + (f" ({secret_note})" if secret_note else ""),
        f"score {score.total} (tier {score.tier})",
    ]
    for category in sorted(score.categories):
        raw = score.raw.get(category, "")
        lines.append(f"- {category} {score.categories[category]:.1f} ({raw})")
    lines.append("")
    if not plan:
        lines.append("The plan is empty. Nothing to do.")
    else:
        lines.append(f"## Plan ({len(plan)})")
        lines.append("")
        for finding in plan:
            lines.append(_markdown_line(finding, boxed=finding.auto))
            hint = _prose_keep_hint(finding)
            if hint is not None:
                lines.append(hint)
    if moves:
        lines.append("")
        lines.append(f"## Move plan ({len(moves)})")
        lines.append("")
        for move in moves:
            lines.append(_move_markdown_line(move))
    if repins:
        lines.append("")
        lines.append(f"## Re-pin plan ({len(repins)})")
        lines.append("")
        for entry in repins:
            lines.append(f"- [ ] {entry.id} → pin:{entry.new_pin} ({entry.target})")
    if kept:
        lines.append("")
        lines.append(f"## Kept ({len(kept)})")
        lines.append("")
        for finding, reason in kept:
            label = _SEVERITY_LABEL[finding.severity]
            lines.append(
                f"- [{label}] {finding.id} — {finding.evidence} — kept: {reason}"
            )
    info_findings = [finding for finding in findings if finding.severity == "info"]
    if info_findings:
        lines.append("")
        lines.append(f"## Info ({len(info_findings)})")
        lines.append("")
        for finding in info_findings:
            lines.append(
                _markdown_line(
                    finding, boxed=finding.auto and finding.id == managed.SETUP_ID
                )
            )
    if gate is not None:
        lines.append("")
        lines.extend(_baseline_section_lines(gate))
    return "\n".join(lines) + "\n"


def _profile_line(profile: dict[str, str]) -> str:
    """Give the profile header line of the Markdown report (D15.3).

    Args:
        profile: The profile block, from `profile_block`.

    Returns:
        `profile <name> (<path>)`. The built-in default `minimal` is the
        profile of a target that is not adopted (D15.6), so that case gives
        `_NOT_ADOPTED_PROFILE_LINE`, which names the house flag.
    """
    if profile.get("source") == "built-in default" and profile["name"] == "minimal":
        return _NOT_ADOPTED_PROFILE_LINE
    return f"profile {profile['name']} ({profile['path']})"


def _baseline_section_lines(gate: Gate) -> list[str]:
    """Render the `## Baseline` section lines of a `check --baseline` report (D6.7).

    Args:
        gate: The `Gate` of the comparison.

    Returns:
        The section's lines, with no leading or trailing blank line.
    """
    lines = ["## Baseline", "", f"score {gate.score_before} -> {gate.score_now}"]
    if gate.new:
        lines.append(f"new ({len(gate.new)}):")
        lines.extend(f"- {finding_id}" for finding_id in gate.new)
    else:
        lines.append("new: none")
    if gate.ratchet_drops:
        lines.append(f"ratchet drops ({len(gate.ratchet_drops)}):")
        lines.extend(f"- {drop}" for drop in gate.ratchet_drops)
    else:
        lines.append("ratchet drops: none")
    if gate.missing_reports:
        lines.append(f"missing reports ({len(gate.missing_reports)}):")
        lines.extend(f"- {report}" for report in gate.missing_reports)
    else:
        lines.append("missing reports: none")
    if gate.tighten:
        lines.append(f"tighten ({len(gate.tighten)}):")
        lines.extend(f"- {finding_key}" for finding_key in gate.tighten)
    else:
        lines.append("tighten: none")
    return lines


def _tier_text(survey: survey_mod.Survey) -> str:
    """Give the tier text of the report: the reason alone when it names the tier.

    Args:
        survey: The survey the report is about.

    Returns:
        `survey.tier_reason` when it starts with `survey.tier` (the form
        `trueup.survey` writes, for example `T2 (default: ...)`), else
        `"<tier> (<reason>)"`.
    """
    if survey.tier_reason.startswith(survey.tier):
        return survey.tier_reason
    return f"{survey.tier} ({survey.tier_reason})"


def _prose_keep_hint(finding: Finding) -> str | None:
    """Give the `[[keep]]` hint for a `prose` finding that names many words (D6.9).

    A `docrules` `prose` finding whose evidence names at least
    `_PROSE_HINT_WORD_FLOOR` distinct banned words more likely comes from a
    file that quotes the banned-word list on purpose (a policy document)
    than from real prose slop.

    Args:
        finding: The finding to check.

    Returns:
        The hint line when `finding` is such a `prose` finding, else `None`.
    """
    if finding.rule != "prose":
        return None
    if len(_PROSE_EVIDENCE_HIT.findall(finding.evidence)) < _PROSE_HINT_WORD_FLOOR:
        return None
    return _PROSE_KEEP_HINT


def tree_comment(tree: dict[str, str]) -> str:
    """Give the tree comment of line 2 of the Markdown report (arch: D12.3).

    Args:
        tree: The tree identity, from `changes.tree_identity`.

    Returns:
        `<!-- trueup tree head=<head> status=<status> -->`.
    """
    return f"<!-- trueup tree head={tree['head']} status={tree['status']} -->"


def _markdown_line(finding: Finding, boxed: bool = False) -> str:
    """Render one finding as a Markdown list line.

    Args:
        finding: The finding to render.
        boxed: The id is one that `apply --ids` accepts (arch: D12.3). The
            line then starts with an empty box and puts the label after the
            id, so the text up to the first ` — ` after the box is the id.

    Returns:
        A `"- [LABEL] id — evidence — action"` line, or with `boxed` a
        `"- [ ] id — [LABEL] evidence — action"` line.
    """
    label = _SEVERITY_LABEL[finding.severity]
    if boxed:
        return f"- [ ] {finding.id} — [{label}] {finding.evidence} — {finding.action}"
    return f"- [{label}] {finding.id} — {finding.evidence} — {finding.action}"


def _move_markdown_line(move: layout.Move) -> str:
    """Render one move as a Markdown list line of the `## Move plan` section (D10.6).

    Args:
        move: The move to render.

    Returns:
        A `"- [ ] move:<source> → <target> (<basis>: <evidence>)"` line,
        with the box of an approval id (arch: D12.3).
    """
    return f"- [ ] {move.id} → {move.target} ({move.basis}: {move.evidence})"


def render_json(
    survey: survey_mod.Survey,
    findings: list[Finding],
    plan: list[Finding],
    score: Score,
    kept: list[tuple[Finding, str]],
    gate: Gate | None = None,
    moves: tuple[layout.Move, ...] = (),
    *,
    secret_engine: str,
    secret_note: str = "",
    tree: dict[str, str] | None = None,
    repins: tuple[docrules.Repin, ...] = (),
    profile: dict[str, str] | None = None,
) -> dict[str, object]:
    """Render the JSON report of one check run (D5.11, D15.3).

    Args:
        survey: The survey the report is about.
        findings: Every finding, sorted (I-21).
        plan: The plan: the findings the person is asked to act on.
        score: The slop score of this run.
        kept: The kept findings with their reasons, from `kept_findings`.
        gate: The `check --baseline` result, or `None` for a plain `check`
            (D6.7). When given, a `"baseline"` key is added.
        moves: The move plan (D10.6, D10.12). Its `"moves"` key holds
            `dataclasses.asdict` of each move, sorted by id; empty by
            default, and always empty under a scoped run.
        secret_engine: The secret engine of the run, the value of the
            `"secret_engine"` key (D7.3 rule 6).
        secret_note: The engine note, the value of the `"secret_note"`
            key; `""` when gitleaks ran to the end or did not run (D15.3).
        tree: The tree identity of the run, from `changes.tree_identity`,
            the value of the `"tree"` key; `None` gives JSON `null`
            (arch: D12.1). `apply --plan` refuses a file whose `tree`
            differs from the tree it runs on.
        repins: The re-pin entries (arch: D12.6). The `"repins"` key holds
            `dataclasses.asdict` of each entry, sorted by id.
        profile: The profile of the run, from `profile_block`: the value of
            the `"profile"` key, `{"name", "path", "source"}` (arch: D14.3,
            D15.3). `None` gives JSON `null`; `check` always gives a block.

    Returns:
        A JSON-ready mapping: `"schema": 1`, the survey, the profile, the
        score, the plan, every finding (each with its `line`), `kept`, the
        id and reason of each kept finding, the move plan, the secret
        engine and its note, the tree identity and the re-pin entries.
    """
    data: dict[str, object] = {
        "schema": JSON_SCHEMA,
        "survey": survey_mod.as_dict(survey),
        "profile": profile,
        "score": {
            "total": score.total,
            "tier": score.tier,
            "categories": score.categories,
            "raw": score.raw,
        },
        "plan": [_finding_dict(finding) for finding in plan],
        "findings": [_finding_dict(finding) for finding in findings],
        "kept": [{"id": finding.id, "reason": reason} for finding, reason in kept],
        "moves": [asdict(move) for move in sorted(moves, key=lambda move: move.id)],
        "secret_engine": secret_engine,
        "secret_note": secret_note,
        "tree": tree,
        "repins": [
            asdict(entry) for entry in sorted(repins, key=lambda entry: entry.id)
        ],
    }
    if gate is not None:
        data["baseline"] = {
            "new": list(gate.new),
            "score_before": gate.score_before,
            "score_now": gate.score_now,
            "ratchet_drops": list(gate.ratchet_drops),
            "missing_reports": list(gate.missing_reports),
            "tighten": list(gate.tighten),
        }
    return data


def _finding_dict(finding: Finding) -> dict[str, object]:
    """Turn one `Finding` into a JSON-ready mapping.

    Args:
        finding: The finding to convert.

    Returns:
        A mapping of the finding's own fields; `line` is 0 when the finding
        points at no single line (D15.8).
    """
    return {
        "id": finding.id,
        "rule": finding.rule,
        "category": finding.category,
        "severity": finding.severity,
        "path": finding.path,
        "evidence": finding.evidence,
        "action": finding.action,
        "auto": finding.auto,
        "line": finding.line,
    }


def render_changed_markdown(run: CheckRun) -> str:
    """Render the Markdown report of a `check --changed` run (arch: D6.17).

    Args:
        run: The scoped result of `collect(root, only=...)`.

    Returns:
        The Markdown text, ending in a newline. It carries no score line: a
        score is for the whole repository, not a scoped run.
    """
    lines = ["# trueup check --changed", ""]
    if not run.plan:
        lines.append("The scoped plan is empty. Nothing to do.")
    else:
        lines.append(f"## Plan ({len(run.plan)})")
        lines.append("")
        for finding in run.plan:
            lines.append(_markdown_line(finding))
    info_findings = [finding for finding in run.findings if finding.severity == "info"]
    if info_findings:
        lines.append("")
        lines.append(f"## Info ({len(info_findings)})")
        lines.append("")
        for finding in info_findings:
            lines.append(_markdown_line(finding))
    return "\n".join(lines) + "\n"


def render_changed_json(
    run: CheckRun,
    *,
    kept: list[tuple[Finding, str]] | None = None,
    tree: dict[str, str] | None = None,
    profile: dict[str, str] | None = None,
) -> dict[str, object]:
    """Render the JSON report of a `check --changed` run (arch: D6.17, D15.3).

    Args:
        run: The scoped result of `collect(root, only=...)`.
        kept: The kept findings inside the scope, from `kept_findings`.
            `None` gives an empty list.
        tree: The tree identity of the run, from `changes.tree_identity`;
            `None` gives JSON `null`.
        profile: The profile of the run, from `profile_block`; `None` gives
            JSON `null`.

    Returns:
        A JSON-ready mapping: `"schema": 1`, `"scope": "changed"`,
        `"score": None` (a score is for the whole repository), the
        profile, the secret engine and its note, the survey, the scoped
        plan and findings, `kept` and the tree identity.
    """
    return {
        "schema": JSON_SCHEMA,
        "scope": "changed",
        "score": None,
        "profile": profile,
        "secret_engine": run.secret_engine,
        "secret_note": run.secret_note,
        "survey": survey_mod.as_dict(run.survey),
        "plan": [_finding_dict(finding) for finding in run.plan],
        "findings": [_finding_dict(finding) for finding in run.findings],
        "kept": [
            {"id": finding.id, "reason": reason} for finding, reason in kept or []
        ],
        "tree": tree,
    }
