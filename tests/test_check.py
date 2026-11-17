"""Tests for the `check` driver: `trueup.report.check`, wired through `trueup.cli` (D5.11)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import materialise
from trueup import cli, report
from trueup.findings import CATEGORY_ORDER, line_fingerprint

REPO_ROOT = Path(__file__).resolve().parent.parent


_MESSY_CHANGELOG_ID = (
    f"changelog:CHANGELOG.md:{line_fingerprint('CHANGELOG.md', '### Misc')}"
)
"""The id of the messy fixture's `### Misc` defect on line 5 (D15.8: a fingerprint, not the line)."""


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Read the content of every file under `root`, keyed by relative path.

    Args:
        root: The directory to snapshot. `.git` is excluded, since `git`
            itself may touch its own internal state on a read command.

    Returns:
        Relative path (as a string) to the file's bytes.
    """
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


def _clean_t0_repo(root: Path) -> None:
    """Set up a T0 repository with every T0 health item present.

    Args:
        root: The directory to populate. Must already be a git repository.
    """
    (root / "README.md").write_text("# A tiny project\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.pyc\n", encoding="utf-8")


def _applied_t0_repo(root: Path) -> None:
    """Set up a T0 repository, then let `apply --all-auto` write its managed files.

    `tier = "T0"` and `docs = "readme"` keep the health and document rules
    to what a two-file project can meet; the setup rows then have nothing
    left once apply has run.

    Args:
        root: The directory to populate. Must already be a git repository.
    """
    _clean_t0_repo(root)
    exit_code = cli.main(
        [
            "apply",
            "--root",
            str(root),
            "--all-auto",
            # D12.2: the fixture tree is not committed, so apply needs this flag.
            "--allow-dirty",
            "--set",
            "tier=T0",
            "--set",
            "docs=readme",
        ]
    )
    assert exit_code == 0


def test_check_exits_zero_for_a_clean_repo(tmp_path: Path) -> None:
    """`check` exits 0 when the plan is empty (D5.11).

    arch: D5.4
    """
    _git_init(tmp_path)
    _applied_t0_repo(tmp_path)
    exit_code = cli.main(["check", "--root", str(tmp_path)])
    assert exit_code == 0


def test_check_without_trueup_toml_plans_the_setup(tmp_path: Path) -> None:
    """A repository with no trueup.toml has a plan: the config and the managed files (D5.6).

    arch: D5.4, D5.6
    """
    _git_init(tmp_path)
    _clean_t0_repo(tmp_path)
    exit_code = cli.main(["check", "--root", str(tmp_path)])
    assert exit_code == 1


def test_check_exits_one_for_the_messy_fixture(tmp_path: Path) -> None:
    """`check` exits 1 on the messy fixture, which carries several plan findings.

    arch: D5.4
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    exit_code = cli.main(["check", "--root", str(tree)])
    assert exit_code == 1


def test_check_as_a_script_on_the_messy_fixture(tmp_path: Path) -> None:
    """`python3 trueup check --root DIR` runs as a script and reports the same verdict (D5.10, D5.11).

    arch: D5.4
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "trueup"), "check", "--root", str(tree)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 1
    assert "trueup check" in result.stdout


def test_check_writes_nothing_under_root(tmp_path: Path) -> None:
    """`check` leaves every file under the root byte-identical, with or without `--out` (I-18).

    Extended for `--changed` (D6.17): the scoped run also leaves the tree
    untouched, `git status --porcelain` unchanged, and `.git/index`'s mtime
    unchanged, since its one git call passes `--no-optional-locks` (I-14).
    Extended again for `--baseline` (D6.6, D6.7, I-16): with no baseline
    file it exits 2 and writes nothing, and with one present it still
    writes nothing, the baseline file itself included.

    arch: I-18, I-14, I-16, D6.7
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    before = _snapshot(tree)
    cli.main(["check", "--root", str(tree)])
    assert _snapshot(tree) == before

    out_dir = tmp_path / "out"
    cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    assert _snapshot(tree) == before

    # `git add` gives the repository a real `.git/index` file to watch; a
    # fresh `git init` with no staged file has none yet.
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    status_before = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(tree), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    index_mtime_before = (tree / ".git" / "index").stat().st_mtime_ns
    cli.main(["check", "--root", str(tree), "--changed"])
    assert _snapshot(tree) == before
    status_after = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(tree), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status_after == status_before
    assert (tree / ".git" / "index").stat().st_mtime_ns == index_mtime_before

    assert cli.main(["check", "--root", str(tree), "--baseline"]) == 2
    assert _snapshot(tree) == before

    cli.main(["baseline", "--root", str(tree)])
    with_baseline = _snapshot(tree)
    cli.main(["check", "--root", str(tree), "--baseline"])
    assert _snapshot(tree) == with_baseline
    cli.main(["check", "--root", str(tree), "--baseline", "--json"])
    assert _snapshot(tree) == with_baseline


def test_check_out_writes_the_markdown_and_json_reports(tmp_path: Path) -> None:
    """`--out DIR` writes `trueup-report.md` and `trueup-report.json` there (D5.11).

    arch: D5.4
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    out_dir = tmp_path / "out"
    exit_code = cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    assert exit_code == 1
    markdown = (out_dir / "trueup-report.md").read_text(encoding="utf-8")
    assert markdown.startswith("# trueup check")
    data = json.loads((out_dir / "trueup-report.json").read_text(encoding="utf-8"))
    assert data["plan"]
    assert data["score"]["total"] >= 0


def test_check_report_carries_raw_counts_next_to_each_category(
    tmp_path: Path,
) -> None:
    """The Markdown and JSON reports print the raw count behind each score category (D10.8).

    arch: D10.8
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    out_dir = tmp_path / "out"
    cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    markdown = (out_dir / "trueup-report.md").read_text(encoding="utf-8")
    import re

    for category in ("security", "files", "docs", "root", "health"):
        assert re.search(rf"- {category} [\d.]+ \(.+\)", markdown), (
            f"missing raw-count line for {category}"
        )
    data = json.loads((out_dir / "trueup-report.json").read_text(encoding="utf-8"))
    raw = data["score"]["raw"]
    assert raw["docs"].endswith(" paths")
    assert raw["files"].endswith(" files")
    assert raw["setup"].endswith(" findings")


def test_check_refuses_out_inside_root(tmp_path: Path) -> None:
    """`--out` inside `root` with no matching `ignore` glob exits 2 and writes nothing (LOW-1).

    arch: D6.15
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    before = _snapshot(tree)
    out_dir = tree / "out"
    exit_code = cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    assert exit_code == 2
    assert not out_dir.exists()
    assert _snapshot(tree) == before


def test_check_allows_out_inside_root_when_ignored(tmp_path: Path) -> None:
    """`--out` inside `root` is written when an `ignore` glob covers both report files (LOW-1).

    The next `check` does not survey the two report files (I-18).

    arch: D6.15
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    (tree / "trueup.toml").write_text(
        'version = 1\nignore = ["out/**"]\n', encoding="utf-8"
    )
    out_dir = tree / "out"
    exit_code = cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    assert exit_code == 1
    assert (out_dir / "trueup-report.md").exists()
    assert (out_dir / "trueup-report.json").exists()
    files = report.collect(tree).survey.files
    assert not [path for path in files if path.startswith("out/")]


def test_check_refuses_out_when_ignore_matches_only_the_directory(
    tmp_path: Path,
) -> None:
    """An `ignore` glob that matches the `--out` directory but not its files is refused (LOW-1).

    The survey filters file paths, so `ignore = ["out"]` does not stop the
    survey of `out/trueup-report.md` (I-18).

    arch: D6.15
    """
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    (tree / "trueup.toml").write_text(
        'version = 1\nignore = ["out"]\n', encoding="utf-8"
    )
    before = _snapshot(tree)
    out_dir = tree / "out"
    exit_code = cli.main(["check", "--root", str(tree), "--out", str(out_dir)])
    assert exit_code == 2
    assert not out_dir.exists()
    assert _snapshot(tree) == before


def test_check_reports_name_the_counter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Markdown and JSON reports name the real counter that ran (arch: D6.14, D6.13).

    The name is `"tokei"` when the tool is on the path and reads the tree,
    else `"built-in"` (D5.4). Both branches run the real `shutil.which`
    check, so this test tracks whichever tool the machine actually has,
    rather than assuming one is absent.

    arch: D6.14, D6.13
    """
    _git_init(tmp_path)
    _clean_t0_repo(tmp_path)
    expected = "tokei" if shutil.which("tokei") is not None else "built-in"

    cli.main(["check", "--root", str(tmp_path)])
    markdown = capsys.readouterr().out
    assert f"counter {expected}" in markdown

    cli.main(["check", "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["survey"]["counter"] == expected


def test_check_json_flag_prints_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` prints the JSON report on standard output, in place of Markdown (D5.11).

    arch: D5.4
    """
    _git_init(tmp_path)
    _applied_t0_repo(tmp_path)
    capsys.readouterr()
    cli.main(["check", "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["plan"] == []
    assert data["survey"]["tier"] == "T0"


def test_check_json_plan_is_sorted_by_category_then_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `--json` plan is sorted by category order, then by id (D5.4, I-21).

    arch: I-21
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    cli.main(["check", "--root", str(tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    seen_indexes = [
        CATEGORY_ORDER.index(finding["category"]) for finding in data["plan"]
    ]
    assert seen_indexes == sorted(seen_indexes)
    assert len(data["plan"]) >= 2  # the messy fixture holds more than one plan finding


def test_check_output_is_deterministic_across_runs(tmp_path: Path) -> None:
    """Two `check` runs on the same unchanged tree give byte-identical output (I-21).

    arch: I-21
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    first = subprocess.run(
        [sys.executable, str(REPO_ROOT / "trueup"), "check", "--root", str(tree)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    second = subprocess.run(
        [sys.executable, str(REPO_ROOT / "trueup"), "check", "--root", str(tree)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert first.stdout == second.stdout


def test_check_raises_config_error_as_exit_two(tmp_path: Path) -> None:
    """An invalid `trueup.toml` turns into exit 2, through `cli.main`'s `ConfigError` handling (D5.11).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T9"\n', encoding="utf-8"
    )
    exit_code = cli.main(["check", "--root", str(tmp_path)])
    assert exit_code == 2


def test_check_changed_scopes_findings_to_the_change_set(tmp_path: Path) -> None:
    """`--changed` reports a finding only when its own file is in the change set (D6.17).

    A committed file that carries a banned word stays out of the scoped
    plan until it is itself touched again; touching an unrelated file does
    not pull it in. Both pages live under `docs/` so the `doc-misplaced`
    row (D10.2) never fires on either one, which would otherwise be a
    second, unrelated reason for the scoped plan to hold a finding. The
    tree has no `trueup.toml`, so each run names `--profile house` for the
    banned-word row (D15.6).

    arch: D6.17, D15.6
    """
    from trueup import docrules

    word = docrules._load_banned_words()[0]
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bad.md").write_text(
        f"this line names {word}\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "good.md").write_text(
        "nothing to see here\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add"],
        cwd=tmp_path,
        check=True,
    )

    house = ("--profile", "house")
    assert cli.main(["check", "--root", str(tmp_path), "--changed", *house]) == 0

    (tmp_path / "docs" / "good.md").write_text(
        "nothing to see here still\n", encoding="utf-8"
    )
    assert cli.main(["check", "--root", str(tmp_path), "--changed", *house]) == 0

    (tmp_path / "docs" / "bad.md").write_text(
        f"this line still names {word}\n", encoding="utf-8"
    )
    assert cli.main(["check", "--root", str(tmp_path), "--changed", *house]) == 1


def test_check_changed_json_scope_score_and_no_repo_wide_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--changed --json` names its scope, gives a null score, and carries no repo-wide or refcheck row (D6.17).

    arch: D6.17
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    capsys.readouterr()
    cli.main(["check", "--root", str(tree), "--changed", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["scope"] == "changed"
    assert data["score"] is None
    assert all(
        finding["category"] not in ("health", "setup") for finding in data["findings"]
    )
    assert all(finding["rule"] != "refcheck" for finding in data["findings"])
    assert all(finding["path"] for finding in data["findings"])


def test_check_changed_drops_hygiene_rows_outside_the_change_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scoped run drops a per-file hygiene finding on an unchanged file and the repo-wide `root-budget` finding (D6.17).

    The hygiene rows run on the full survey in scoped mode too, so only
    the post-row path filter in `report.collect` keeps these two findings
    out: the committed scratch file is not in the change set, and the
    `root-budget` finding names no single file. The touched page sits at
    the root with no `docs` segment, so it is itself a `doc-misplaced`
    candidate (D10.2); the scoped plan keeps that one finding, which the
    change set's own file earns on its own account.

    arch: D6.17, D10.2
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T0"\n', encoding="utf-8"
    )
    (tmp_path / "tmp-draft.md").write_text("draft\n", encoding="utf-8")
    for index in range(10):
        (tmp_path / f"page{index}.md").write_text("plain text\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "page0.md").write_text("plain text, touched\n", encoding="utf-8")

    full_ids = {finding.id for finding in report.collect(tmp_path).plan}
    assert {"scratch:tmp-draft.md", "root-budget:"} <= full_ids

    from trueup import changes

    only = changes.working_set(tmp_path)
    assert only == frozenset({"page0.md"})
    scoped = report.collect(tmp_path, only=only)
    assert [finding.id for finding in scoped.findings] == ["doc-misplaced:page0.md"]
    assert [finding.id for finding in scoped.plan] == ["doc-misplaced:page0.md"]

    capsys.readouterr()
    assert cli.main(["check", "--root", str(tmp_path), "--changed", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert [finding["id"] for finding in data["plan"]] == ["doc-misplaced:page0.md"]


def test_check_changed_superseded_link_to_an_unchanged_page_stays_clean(
    tmp_path: Path,
) -> None:
    """A `superseded_by` link to a page outside the change set is not a false `superseded` finding (D6.17).

    `docrules._page_findings` reads every page's `id` from the full,
    unscoped survey, not just the scoped one, so editing only the
    superseded page does not turn its still-working link into a broken
    one under `--changed`, even though the page it points to is untouched
    and so falls outside the change set: the full (unscoped) run holds no
    `superseded` finding for either page, and the scoped run must agree.

    arch: D6.17
    """
    from trueup import changes

    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "new.md").write_text(
        "---\nid: new\ntype: reference\nstatus: current\n"
        "last_reviewed: 2026-01-01\n---\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "old.md").write_text(
        "---\nid: old\ntype: reference\nstatus: superseded\n"
        "superseded_by: new\n---\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ndocs = "full"\nstale_days = 99999\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add"],
        cwd=tmp_path,
        check=True,
    )
    full_before = report.collect(tmp_path)
    assert not any(finding.rule == "superseded" for finding in full_before.findings)

    (tmp_path / "docs" / "old.md").write_text(
        "---\nid: old\ntype: reference\nstatus: superseded\n"
        "superseded_by: new\n---\nbody, touched\n",
        encoding="utf-8",
    )
    full_after = report.collect(tmp_path)
    assert not any(finding.rule == "superseded" for finding in full_after.findings)

    only = changes.working_set(tmp_path)
    assert only == frozenset({"docs/old.md"})
    scoped = report.collect(tmp_path, only=only)
    assert not any(finding.rule == "superseded" for finding in scoped.findings)


def test_check_baseline_with_no_file_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --baseline` with no `.trueup-baseline.json` exits 2 and says so (D6.7).

    arch: D6.7
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    exit_code = cli.main(["check", "--root", str(tmp_path), "--baseline"])
    assert exit_code == 2
    assert "no baseline" in capsys.readouterr().err


def test_check_baseline_on_an_unchanged_repo_exits_zero(tmp_path: Path) -> None:
    """`check --baseline` on the repository the baseline was taken from exits 0 (D6.7).

    The plan is not empty (the messy fixture has no `trueup.toml`), so a
    plain `check` would exit 1; the baseline gate exits 0 anyway, since
    nothing about the plan changed since `trueup baseline` ran (D6.7).

    arch: D6.7
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    assert cli.main(["check", "--root", str(tree)]) == 1
    assert cli.main(["baseline", "--root", str(tree)]) == 0
    assert cli.main(["check", "--root", str(tree), "--baseline"]) == 0


def test_check_baseline_fails_on_a_new_finding(tmp_path: Path) -> None:
    """A finding with no recorded key fails `check --baseline` (D6.6, D6.7).

    arch: D6.6, D6.7
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    assert cli.main(["baseline", "--root", str(tmp_path)]) == 0
    (tmp_path / "notes.tmp").write_text("scratch\n", encoding="utf-8")
    assert cli.main(["check", "--root", str(tmp_path), "--baseline"]) == 1


def test_check_baseline_json_reports_the_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --baseline --json` adds a `"baseline"` key with the `Gate` fields (D6.7).

    arch: D6.7
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    cli.main(["baseline", "--root", str(tmp_path)])
    capsys.readouterr()
    (tmp_path / "notes.tmp").write_text("scratch\n", encoding="utf-8")
    exit_code = cli.main(["check", "--root", str(tmp_path), "--baseline", "--json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert any(
        finding_id.startswith("scratch:") for finding_id in data["baseline"]["new"]
    )
    assert isinstance(data["baseline"]["score_before"], int)
    assert isinstance(data["baseline"]["score_now"], int)
    assert data["baseline"]["ratchet_drops"] == []
    assert data["baseline"]["missing_reports"] == []


def test_check_baseline_markdown_has_a_baseline_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --baseline` (Markdown) adds a `## Baseline` section (D6.7).

    arch: D6.7
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    cli.main(["baseline", "--root", str(tmp_path)])
    capsys.readouterr()
    exit_code = cli.main(["check", "--root", str(tmp_path), "--baseline"])
    assert exit_code == 0
    markdown = capsys.readouterr().out
    assert "## Baseline" in markdown
    assert "new: none" in markdown


def test_check_category_order_constant_matches_the_sort(tmp_path: Path) -> None:
    """The plan's categories never appear out of `CATEGORY_ORDER` (D5.4, I-21).

    arch: I-21
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    from trueup.config import load as load_config
    from trueup.findings import build_plan

    cfg = load_config(tree)
    findings = report.collect(tree).findings
    plan = build_plan(findings, dict(cfg.keep) if cfg else {})
    seen_indexes = [CATEGORY_ORDER.index(finding.category) for finding in plan]
    assert seen_indexes == sorted(seen_indexes)


def test_check_reports_docrules_and_setup_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One check run holds a document-rule finding and a setup finding beside the hygiene ones.

    The messy fixture's CHANGELOG.md uses a `### Misc` heading (a docrules
    finding) and its `.gitignore` lacks `.scratch/` (a setup finding). The
    fixture is T0, so `docs = "auto"` resolves to readme and the changelog
    row waits for a config that sets T2 (D12.9). At T0 with no trueup.toml
    the tier set is empty, so no `config` row and no setup opt-in row show
    (D12.9); at T2 the `config:trueup.toml` row shows.

    arch: D5.4, D5.6, D12.9, D15.8
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    cli.main(["check", "--root", str(tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    plan_ids = {finding["id"] for finding in data["plan"]}
    # D12.9: readme mode at T0 runs no changelog row.
    assert _MESSY_CHANGELOG_ID not in plan_ids
    # D12.9: setup is an opt-in; at T0 the set is empty, so no config row.
    assert "config:trueup.toml" not in plan_ids
    assert "setup:trueup.toml" not in {finding["id"] for finding in data["findings"]}
    assert "scratch:tmp-draft.md" in plan_ids
    setup = [finding for finding in data["plan"] if finding["category"] == "setup"]
    assert setup and all(
        finding["rule"] in ("config", "file-managed", "gitignore") for finding in setup
    )

    cli.main(["check", "--root", str(tree)])
    markdown = capsys.readouterr().out
    assert "gitignore:.gitignore" in markdown

    # D12.9: at T2 the config row shows in both reports.
    (tree / ".github" / "workflows").mkdir(parents=True)
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        "on: push\njobs: {}\n", encoding="utf-8"
    )
    for args in (["add", "-A"], ["commit", "-q", "-m", "fixture"], ["tag", "v1"]):
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "user.name=test",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "tag.gpgsign=false",
                *args,
            ],
            cwd=tree,
            check=True,
            capture_output=True,
        )
    cli.main(["check", "--root", str(tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["survey"]["tier"] == "T2"
    assert "config:trueup.toml" in {finding["id"] for finding in data["plan"]}
    cli.main(["check", "--root", str(tree)])
    assert "config:trueup.toml" in capsys.readouterr().out

    # D12.9: at T2 docs resolves to full and the changelog row runs.
    (tree / "trueup.toml").write_text('version = 1\ntier = "T2"\n', encoding="utf-8")
    cli.main(["check", "--root", str(tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert _MESSY_CHANGELOG_ID in {finding["id"] for finding in data["plan"]}
    cli.main(["check", "--root", str(tree)])
    assert _MESSY_CHANGELOG_ID in capsys.readouterr().out


def test_check_prints_the_keep_hint_for_a_word_heavy_prose_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `prose` finding naming 10+ distinct banned words gets the D6.9 hint line.

    A policy file that quotes most of the banned-word list, the way
    `domain/RULES.md` does in the field trial, should not read as a plain
    violation: the report tells the reader it may want `[[keep]]` instead.
    The tree has no `trueup.toml`, so the run names `--profile house` for
    the banned-word row (D15.6).

    arch: D6.9, D15.6
    """
    from trueup import docrules

    _git_init(tmp_path)
    words = [word for word in docrules._load_banned_words() if "=>" not in word][:10]
    assert len(words) == 10
    (tmp_path / "notes.md").write_text(
        "\n".join(f"this line names {word}" for word in words) + "\n",
        encoding="utf-8",
    )
    cli.main(["check", "--root", str(tmp_path), "--profile", "house"])
    markdown = capsys.readouterr().out
    lines = markdown.splitlines()
    finding_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("- [ERROR] prose:notes.md")
    )
    assert "hint: this file may quote the list on purpose" in lines[finding_index + 1]


def test_check_no_hint_for_a_prose_finding_under_the_word_floor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `prose` finding naming fewer than 10 distinct words gets no D6.9 hint.

    arch: D6.9
    """
    from trueup import docrules

    _git_init(tmp_path)
    word = docrules._load_banned_words()[0]
    (tmp_path / "notes.md").write_text(f"this line names {word}\n", encoding="utf-8")
    cli.main(["check", "--root", str(tmp_path)])
    markdown = capsys.readouterr().out
    assert "hint: this file may quote the list on purpose" not in markdown


def test_report_names_the_tier_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tier line prints the tier reason as it is, not the tier wrapped around it.

    arch: D5.4
    """
    _git_init(tmp_path)
    _clean_t0_repo(tmp_path)
    cli.main(["check", "--root", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    tier_line = next(line for line in lines if line.startswith("tier "))
    assert tier_line == "tier T0 (5 or fewer language files, no manifest, no CI)"


def test_text_and_json_reports_list_the_same_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A kept `error` finding shows in the text report's Kept section, so text and JSON list the same ids (D5.11).

    arch: D5.11, D5.4, D15.8
    """
    tree = materialise("messy", tmp_path)
    _git_init(tree)
    # D12.9: tier T2 resolves docs to full, so the changelog row runs.
    (tree / "trueup.toml").write_text(
        f'version = 1\ntier = "T2"\n\n[[keep]]\nid = "{_MESSY_CHANGELOG_ID}"\nreason = "house style"\n',
        encoding="utf-8",
    )
    cli.main(["check", "--root", str(tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["kept"] == [{"id": _MESSY_CHANGELOG_ID, "reason": "house style"}]
    json_ids = sorted(finding["id"] for finding in data["findings"])
    cli.main(["check", "--root", str(tree)])
    markdown = capsys.readouterr().out
    text_ids = sorted(
        line.split("] ", 1)[1].split(" — ", 1)[0]
        for line in markdown.splitlines()
        if line.startswith("- [")
    )
    assert text_ids == json_ids
    assert "## Kept (1)" in markdown
    assert "kept: house style" in markdown


def _v1_collect(root: Path) -> report.CheckRun:
    """Run the v1 (`f09d0f4`) body of `report.collect`, with no scope code in it.

    The rows it calls are today's rows; only the join is the v1 join, so a
    change to a row does not break the test, but a change to the unscoped
    join does.

    Args:
        root: The target repository root.

    Returns:
        The `CheckRun` the v1 join builds.
    """
    from dataclasses import replace

    from trueup import config as config_mod
    from trueup import docrules, health, hygiene, managed
    from trueup import survey as survey_mod
    from trueup.findings import build_plan, protect_findings, sorted_findings

    cfg = config_mod.load(root)
    survey = survey_mod.run(root)
    findings = hygiene.hygiene_findings(survey)
    secret_paths = {
        finding.path for finding in findings if finding.rule == "secret-file"
    }
    readable = replace(
        survey, files=tuple(path for path in survey.files if path not in secret_paths)
    )
    findings.extend(health.health_findings(survey, cfg))
    findings.extend(docrules.docrules_findings(readable, cfg))
    # D15.6: `load` gives a config on every target; the v1 `cfg` was
    # `None` for a target that is not adopted, so the setup rows get `None`.
    adopted = config_mod.load_layers(root).adopted
    findings.extend(managed.setup_findings(survey, cfg if adopted else None))
    findings = protect_findings(findings, cfg.protect if cfg is not None else ())
    keep = dict(cfg.keep) if cfg is not None else {}
    return report.CheckRun(
        survey=survey,
        cfg=cfg,
        findings=sorted_findings(findings),
        plan=build_plan(findings, keep),
    )


def test_unscoped_check_json_is_byte_equal_to_the_v1_join(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check --json` with no `--changed` prints the v1 join's JSON, byte for byte (I-21).

    The `only` argument of `collect` must not change the unscoped path.

    The secret scan is pinned to the built-in path, so the host's gitleaks
    does not change the result.

    arch: D14.15
    arch: D6.17, I-21, D15.6
    """
    from trueup import changes
    from trueup.score import compute

    monkeypatch.setattr(report.secrets, "scan", lambda *_args, **_kw: None)
    tree = materialise("messy", tmp_path / "repo")
    _git_init(tree)
    capsys.readouterr()
    cli.main(["check", "--root", str(tree), "--json"])
    printed = capsys.readouterr().out

    run = _v1_collect(tree)
    assert run == report.collect(tree)
    score = compute(run.plan, run.survey, run.cfg)
    # The `tree` key is new in D12.1; the rest of the join stays byte equal.
    data = report.render_json(
        run.survey,
        run.findings,
        run.plan,
        score,
        report.kept_findings(run),
        secret_engine="built-in",
        tree=changes.tree_identity(tree),
        # D15.6: the profile resolves on every target, so the key is set.
        profile=report.profile_block(tree),
    )
    assert printed == json.dumps(data, indent=2, sort_keys=True) + "\n"


def test_check_changed_never_runs_refcheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scoped run does not call the `refcheck` row, even in `docs = "full"` mode (D6.17).

    arch: D6.17
    """
    from trueup import docrules

    calls: list[Path] = []
    monkeypatch.setattr(
        docrules,
        "_refcheck_findings",
        lambda root, config_text: calls.append(root) or [],
    )
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ndocs = "full"\n', encoding="utf-8"
    )
    report.collect(tmp_path)
    assert len(calls) == 1
    cli.main(["check", "--root", str(tmp_path), "--changed"])
    assert len(calls) == 1


def test_check_changed_with_a_subdirectory_root(tmp_path: Path) -> None:
    """`--changed` on a root below the repository top still scopes to that root's files (D6.17).

    arch: D6.17
    """
    from trueup import docrules

    word = docrules._load_banned_words()[0]
    _git_init(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "bad.md").write_text(f"this line names {word}\n", encoding="utf-8")
    assert cli.main(["check", "--root", str(sub), "--changed"]) == 1


def test_check_changed_outside_a_git_repository_exits_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--changed` on a directory with no git repository is an error: exit 2 (D6.17).

    D15.1 words the git failure without `--changed`.

    arch: D6.17, D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert cli.main(["check", "--root", str(tmp_path), "--changed"]) == 2
    err = capsys.readouterr().err
    assert "failed in" in err
    assert "--changed" not in err


def _write_refcheck_repo(root: Path) -> None:
    """Write a repository with two things for the checker to report, and a config that sets T2 only.

    `docs/page.md` has no front matter (check h) and `src/lib.py` holds a
    tag that is not in the registry (check e). Both checks are off until a
    `ref_check.toml` turns them on. The repository is T0 by size; the
    `trueup.toml` sets T2, so `ref_check.toml` is in the managed set and
    `docs = "auto"` resolves to full (D12.9).

    Args:
        root: The directory to populate. Must already be a git repository.
    """
    (root / "README.md").write_text(
        "# A project\n\nIt does one thing.\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "page.md").write_text("# A page\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "lib.py").write_text(
        "# X1: the project's own tag\n", encoding="utf-8"
    )
    (root / "trueup.toml").write_text('version = 1\ntier = "T2"\n', encoding="utf-8")


def _refcheck_ids(root: Path) -> set[str]:
    """Collect the `refcheck` finding ids of one full `check` run.

    Args:
        root: The repository root.

    Returns:
        The ids, as a set.
    """
    return {
        finding.id
        for finding in report.collect(root).findings
        if finding.rule == "refcheck"
    }


def test_first_check_reports_the_refcheck_findings_that_apply_leaves(
    tmp_path: Path,
) -> None:
    """The `refcheck` row before the first `apply` equals the row after it (D8.1).

    `check` runs the bundled checker with the `ref_check.toml` that `apply`
    would write for the config in force, through a file outside the root,
    so the plan the person approves is the plan `apply` leaves behind. The
    root gets no file from `check`.

    arch: D8.1
    """
    _git_init(tmp_path)
    _write_refcheck_repo(tmp_path)
    before = _refcheck_ids(tmp_path)
    assert not (tmp_path / "ref_check.toml").exists()
    assert "refcheck:src/lib.py:1:unregistered" in before
    assert "refcheck:docs/page.md:1:no-front-matter" in before
    # D12.2: the fixture tree is not committed, so apply needs this flag.
    assert (
        cli.main(["apply", "--root", str(tmp_path), "--all-auto", "--allow-dirty"]) == 0
    )
    # arch: D14.5, D14.8
    # global mode keeps no ref_check.toml in the target.
    assert not (tmp_path / "ref_check.toml").exists()
    assert _refcheck_ids(tmp_path) == before


def test_refs_local_tags_silence_the_projects_own_tags(tmp_path: Path) -> None:
    """`[refs] local_tags` in `trueup.toml` reaches the checker on the first `check` and after `apply` (D8.7).

    arch: D8.7
    """
    _git_init(tmp_path)
    _write_refcheck_repo(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T2"  # D12.9: the full set and docs mode\n[refs]\nlocal_tags = ["X"]\n',
        encoding="utf-8",
    )
    before = _refcheck_ids(tmp_path)
    assert "refcheck:src/lib.py:1:unregistered" not in before
    assert "refcheck:docs/page.md:1:no-front-matter" in before
    # D12.2: the fixture tree is not committed, so apply needs this flag.
    assert (
        cli.main(["apply", "--root", str(tmp_path), "--all-auto", "--allow-dirty"]) == 0
    )
    # arch: D14.5, D14.8
    # global mode keeps no ref_check.toml in the target.
    assert not (tmp_path / "ref_check.toml").exists()
    assert 'local_tags = ["X"]' in (tmp_path / "trueup.toml").read_text(
        encoding="utf-8"
    )
    assert _refcheck_ids(tmp_path) == before


def _write_conforming_repo(root: Path) -> None:
    """Write a T1 repository the checker and the health rows accept, plus one page with no front matter.

    `docs/page.md` is the one thing check h reports; a `[[keep]]` entry for
    it is what the tests below add.

    Args:
        root: The directory to populate. Must already be a git repository.
    """
    (root / "docs").mkdir()
    (root / "docs" / "README.md").write_text(
        "---\nid: docs-index\ntype: reference\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-09-22\n---\n\n# Index\n",
        encoding="utf-8",
    )
    (root / "docs" / "page.md").write_text("# A page\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo\n\nDemo is a tree. Read the [index](docs/README.md).\n\n"
        "## Install\n\nCopy it.\n\n## Usage\n\nRun it.\n\n## License\n\nMIT.\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / ".gitignore").write_text(".scratch/\n", encoding="utf-8")


@pytest.mark.parametrize("mode", ["copy", "global"])
def test_a_kept_refcheck_finding_fails_neither_check_nor_the_hook(
    tmp_path: Path, mode: str
) -> None:
    """A kept `refcheck` finding fails neither `check` nor the command the hook runs, and a new one fails both (D9.1, D9.2).

    In copy mode the hook runs the target's copy with python3; in global
    mode it runs `trueup refs`. Both read the `[keep]` table that `apply`
    renders into `ref_check.toml`, so they agree with `check`, which still
    lists the kept finding.

    arch: D9.1, D9.2
    """
    _git_init(tmp_path)
    _write_conforming_repo(tmp_path)
    refs_table = '[refs]\nmode = "copy"\n\n' if mode == "copy" else ""
    # D12.9: docs full keeps check h on at T1, where "auto" gives readme.
    (tmp_path / "trueup.toml").write_text(
        f'version = 1\ntier = "T1"\ndocs = "full"\n\n{refs_table}[[keep]]\n'
        'id = "refcheck:docs/page.md:1:no-front-matter"\nreason = "fixed path"\n',
        encoding="utf-8",
    )
    # D12.2: the fixture tree is not committed, so apply needs this flag.
    assert (
        cli.main(["apply", "--root", str(tmp_path), "--all-auto", "--allow-dirty"]) == 0
    )
    assert (tmp_path / "ref_check.py").is_file() == (mode == "copy")

    def hook() -> int:
        if mode == "copy":
            return subprocess.run(
                [sys.executable, "ref_check.py", "--root", "."],
                cwd=tmp_path,
                capture_output=True,
                check=False,
            ).returncode
        return cli.main(["refs", "--root", str(tmp_path)])

    run = report.collect(tmp_path)
    assert [finding.id for finding in run.plan] == []
    kept = [finding.id for finding, _ in report.kept_findings(run)]
    assert kept == ["refcheck:docs/page.md:1:no-front-matter"]
    assert cli.main(["check", "--root", str(tmp_path)]) == 0
    assert hook() == 0

    (tmp_path / "docs" / "other.md").write_text("# Other\n", encoding="utf-8")
    assert cli.main(["check", "--root", str(tmp_path)]) == 1
    assert [finding.id for finding in report.collect(tmp_path).plan] == [
        "refcheck:docs/other.md:1:no-front-matter"
    ]
    assert hook() == 1


@pytest.mark.parametrize("mode", ["copy", "global"])
def test_an_ignored_path_fails_neither_check_nor_the_hook(
    tmp_path: Path, mode: str
) -> None:
    """A page under an `ignore` glob gives no `refcheck` finding in `check` and no failure in the hook (I-2).

    `check` reads the rendered `[scan] ignore` from the first run, and
    `apply` writes it into `ref_check.toml`, so the hook skips the same
    paths. A page outside the globs still fails both.

    arch: I-2
    """
    _git_init(tmp_path)
    _write_conforming_repo(tmp_path)
    (tmp_path / "docs" / "features").mkdir()
    (tmp_path / "docs" / "features" / "x.md").write_text("# X\n", encoding="utf-8")
    refs_table = '[refs]\nmode = "copy"\n\n' if mode == "copy" else ""
    # D12.9: docs full keeps check h on at T1, where "auto" gives readme.
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\ndocs = "full"\n'
        'ignore = ["docs/page.md", "docs/features/**"]\n\n'
        f"{refs_table}",
        encoding="utf-8",
    )
    assert [
        finding.id
        for finding in report.collect(tmp_path).findings
        if finding.rule == "refcheck"
    ] == []
    # D12.2: the fixture tree is not committed, so apply needs this flag.
    assert (
        cli.main(["apply", "--root", str(tmp_path), "--all-auto", "--allow-dirty"]) == 0
    )
    if mode == "copy":
        assert '[scan]\nignore = ["docs/page.md", "docs/features/**"]\n' in (
            tmp_path / "ref_check.toml"
        ).read_text(encoding="utf-8")
    else:
        # arch: D14.5, D14.8
        # global mode keeps no ref_check.toml in the target.
        assert not (tmp_path / "ref_check.toml").exists()

    def hook() -> int:
        if mode == "copy":
            return subprocess.run(
                [sys.executable, "ref_check.py", "--root", "."],
                cwd=tmp_path,
                capture_output=True,
                check=False,
            ).returncode
        return cli.main(["refs", "--root", str(tmp_path)])

    assert cli.main(["check", "--root", str(tmp_path)]) == 0
    assert hook() == 0

    (tmp_path / "docs" / "other.md").write_text("# Other\n", encoding="utf-8")
    assert [finding.id for finding in report.collect(tmp_path).plan] == [
        "refcheck:docs/other.md:1:no-front-matter"
    ]
    assert hook() == 1


def test_collect_wires_layout_into_the_move_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`collect` folds `layout.locate`'s finding and move into `CheckRun`, and both reports print it (arch: D10.2, D10.6).

    `GUIDE.md` sits at the root with no front matter, so the locator's only
    source is the standard: `docs/GUIDE.md`.
    """
    _git_init(tmp_path)
    (tmp_path / "GUIDE.md").write_text("# A guide\n", encoding="utf-8")
    run = report.collect(tmp_path)
    assert [
        finding.id for finding in run.findings if finding.rule == "doc-misplaced"
    ] == ["doc-misplaced:GUIDE.md"]
    assert len(run.moves) == 1
    move = run.moves[0]
    assert move.id == "move:GUIDE.md"
    assert move.source == "GUIDE.md"
    assert move.target == "docs/GUIDE.md"
    assert move.kind == "file"
    assert move.basis == "standard"
    assert move.pages == ("GUIDE.md",)

    cli.main(["check", "--root", str(tmp_path)])
    markdown = capsys.readouterr().out
    assert "\n## Move plan (1)\n" in markdown
    assert markdown.index("## Move plan") > markdown.index("## Plan")
    # A move id is an approval id, so its line starts with a box.
    # arch: D12.3
    assert (
        f"- [ ] {move.id} → {move.target} ({move.basis}: {move.evidence})" in markdown
    )

    cli.main(["check", "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["moves"] == [
        {
            "id": "move:GUIDE.md",
            "source": "GUIDE.md",
            "target": "docs/GUIDE.md",
            "kind": "file",
            "basis": "standard",
            "evidence": move.evidence,
            "pages": ["GUIDE.md"],
        }
    ]


def test_collect_applies_the_broken_link_note_without_changing_the_refcheck_id(
    tmp_path: Path,
) -> None:
    """`collect` adds the D10.6 hint to a `broken-link` finding's evidence, by its own id (arch: D10.2, D10.6).

    `README.md` links to `docs/guide.md`, which does not exist; `guide.md`
    sits misplaced at the root and is the only file this basename
    matches, so the locator's link step places it there (I-39: the
    finding id and its original evidence line do not change).
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text(
        "# Demo\n\nSee the [guide](docs/guide.md).\n", encoding="utf-8"
    )
    (tmp_path / "guide.md").write_text("# A guide\n", encoding="utf-8")
    # D12.9: T2 puts ref_check.toml in the set, so the links check runs.
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T2"\n', encoding="utf-8"
    )
    run = report.collect(tmp_path)

    assert [move.id for move in run.moves] == ["move:guide.md"]
    assert run.moves[0].basis == "link"

    refcheck = next(
        finding
        for finding in run.findings
        if finding.rule == "refcheck" and "broken-link" in finding.id
    )
    assert refcheck.id == "refcheck:README.md:3:broken-link"
    assert refcheck.evidence.startswith(
        "README.md:3: [broken-link] link does not resolve: docs/guide.md"
    )
    assert refcheck.evidence.endswith(
        "; the target is now at guide.md; approve move:guide.md"
    )


def test_collect_scoped_run_has_no_moves_and_scopes_the_doc_misplaced_row(
    tmp_path: Path,
) -> None:
    """A scoped `collect` call keeps `moves` empty and reports only the scoped page (arch: D10.2, D10.6).

    D10.6's scoped mode makes `layout.locate` itself give an empty move
    plan under `only`; this proves `collect` forwards its own `only`
    argument through, rather than always calling the locator unscoped.
    """
    _git_init(tmp_path)
    (tmp_path / "GUIDE.md").write_text("# A guide\n", encoding="utf-8")
    (tmp_path / "OTHER.md").write_text("# Another guide\n", encoding="utf-8")
    run = report.collect(tmp_path, only=frozenset({"GUIDE.md"}))
    assert run.moves == []
    assert [
        finding.id for finding in run.findings if finding.rule == "doc-misplaced"
    ] == ["doc-misplaced:GUIDE.md"]


def test_check_json_holds_the_tree_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --json` carries the key `tree`, the value of `changes.tree_identity(root)`.

    arch: D12.1, I-40
    """
    from trueup import changes

    _git_init(tmp_path)
    _clean_t0_repo(tmp_path)
    capsys.readouterr()
    cli.main(["check", "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["tree"] == changes.tree_identity(tmp_path)
    assert set(data["tree"]) == {"head", "status"}


def test_check_json_tree_is_null_outside_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a git work tree `check --json` exits 2 and prints no report; D15.2 inverts the `null` tree.

    The test name is from before that decision.

    arch: D12.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    _clean_t0_repo(tmp_path)
    capsys.readouterr()
    assert cli.main(["check", "--root", str(tmp_path), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a git repository" in captured.err


@pytest.fixture
def profile_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the secret scan and make the teardown remove `TRUEUP_PROFILE`.

    `cli.main` writes `os.environ` itself for `--profile`. A `setenv` and
    then a `delenv` records the variable as unset, so `monkeypatch` deletes
    it again after the test. The built-in secret engine keeps the host's
    gitleaks out of the result.

    Args:
        monkeypatch: The pytest fixture that restores the environment.
    """
    monkeypatch.setenv("TRUEUP_PROFILE", "placeholder")
    monkeypatch.delenv("TRUEUP_PROFILE")
    monkeypatch.setattr(report.secrets, "scan", lambda *_args, **_kw: None)


def _profile_repo(root: Path, toml: str | None) -> Path:
    """Write a git repository with the conforming T1 tree and an optional `trueup.toml`.

    Args:
        root: The directory to make. It must not be the `tmp_path` that
            holds `XDG_CONFIG_HOME`, so the user files stay outside the
            tree.
        toml: The text of `trueup.toml`, or `None` for no file.

    Returns:
        The root.
    """
    root.mkdir()
    _git_init(root)
    _write_conforming_repo(root)
    if toml is not None:
        (root / "trueup.toml").write_text(toml, encoding="utf-8")
    return root


def _check_json(root: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> str:
    """Run `trueup check --json` and give its standard output.

    Args:
        root: The target root.
        capsys: The pytest capture fixture.
        *extra: More command-line tokens.

    Returns:
        The printed JSON text.
    """
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json", *extra])
    return capsys.readouterr().out


_BUILTIN_PROFILES = REPO_ROOT / "trueup" / "data" / "profiles"


@pytest.mark.usefixtures("profile_env")
def test_check_json_and_markdown_name_the_profile_and_its_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The JSON report carries `profile` beside `survey`; the Markdown header prints it (D14.18).

    The default is `house`; `--profile` wins over the target key; a user
    profile comes from `XDG_CONFIG_HOME/trueup/profiles/`. Each block names
    its source layer, and `--profile` holds for one run only (D15.6).

    arch: D14.1, D14.3, D14.18, D15.6
    """
    from trueup import config

    root = _profile_repo(tmp_path / "repo", 'version = 1\ntier = "T1"\n')
    data = json.loads(_check_json(root, capsys))
    house = str(_BUILTIN_PROFILES / "house.toml")
    assert data["profile"] == {
        "name": "house",
        "path": house,
        "source": "built-in default",
    }

    minimal = str(_BUILTIN_PROFILES / "minimal.toml")
    data = json.loads(_check_json(root, capsys, "--profile", "minimal"))
    assert data["profile"] == {
        "name": "minimal",
        "path": minimal,
        "source": "--profile",
    }
    assert "TRUEUP_PROFILE" not in os.environ
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--profile", "minimal"])
    lines = capsys.readouterr().out.splitlines()
    assert f"profile minimal ({minimal})" in lines
    assert lines.index(f"profile minimal ({minimal})") + 1 == next(
        index for index, line in enumerate(lines) if line.startswith("tier ")
    )

    mine = config.config_home() / "profiles" / "mine.toml"
    mine.parent.mkdir(parents=True)
    mine.write_text('docs = "auto"\n', encoding="utf-8")
    (root / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\nprofile = "mine"\n', encoding="utf-8"
    )
    assert "TRUEUP_PROFILE" not in os.environ
    data = json.loads(_check_json(root, capsys))
    assert data["profile"] == {"name": "mine", "path": str(mine), "source": "target"}


@pytest.mark.usefixtures("profile_env")
def test_check_of_a_target_that_is_not_adopted_has_a_null_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no `trueup.toml` and no user default file the profile is `minimal`, from the built-in default.

    Decision 2 inverts the old JSON `null` and the missing header line
    (D15.6). The test name is from before that decision.

    arch: D14.1, D14.3, D14.18, D15.6
    """
    root = _profile_repo(tmp_path / "repo", None)
    data = json.loads(_check_json(root, capsys))
    minimal = str(_BUILTIN_PROFILES / "minimal.toml")
    assert data["profile"] == {
        "name": "minimal",
        "path": minimal,
        "source": "built-in default",
    }
    cli.main(["check", "--root", str(root)])
    assert [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("profile minimal (")
    ]


@pytest.mark.usefixtures("profile_env")
def test_a_user_default_file_does_not_change_check_json_of_a_target_with_trueup_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target that holds `trueup.toml` never reads the user default file (I-44).

    The control run proves the user file has an effect where it is read:
    on the same tree with no `trueup.toml`, its `docs = "readme"` turns
    check h off.

    arch: D14.1, D14.3, D14.18
    """
    from trueup import config

    root = _profile_repo(tmp_path / "repo", 'version = 1\ntier = "T1"\ndocs = "full"\n')
    without = _check_json(root, capsys)
    user_file = config.config_home() / "trueup.toml"
    user_file.parent.mkdir(parents=True)
    user_file.write_text('tier = "T1"\ndocs = "readme"\n', encoding="utf-8")
    with_user = _check_json(root, capsys)
    assert with_user == without
    page_row = "refcheck:docs/page.md:1:no-front-matter"
    assert page_row in {row["id"] for row in json.loads(without)["findings"]}

    (root / "trueup.toml").unlink()
    control = json.loads(_check_json(root, capsys))
    assert page_row not in {row["id"] for row in control["findings"]}
    assert control["profile"]["name"] == "house"


@pytest.mark.parametrize("extra", [[], ["--profile", "minimal"]])
@pytest.mark.usefixtures("profile_env")
def test_a_user_profile_with_a_built_in_name_makes_check_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    """`profiles/house.toml` under `XDG_CONFIG_HOME` is exit 2 for every profile name (I-46).

    arch: D14.1, D14.3, D14.18
    """
    from trueup import config

    root = _profile_repo(tmp_path / "repo", 'version = 1\ntier = "T1"\n')
    shadow = config.config_home() / "profiles" / "house.toml"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("", encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["check", "--root", str(root), "--json", *extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "shadows the built-in profile house" in captured.err


def test_check_of_a_repository_with_no_file_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A git repository with no file to check exits 2 and says so.

    arch: D15.1, D15.2
    """
    _git_init(tmp_path)
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "no tracked file to check" in err


def test_check_loads_the_config_before_it_reads_the_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unreadable `trueup.toml` is reported as such, not as a git failure.

    arch: D15.1, D15.2
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    config = tmp_path / "trueup.toml"
    config.write_text("version = 1\n", encoding="utf-8")
    config.chmod(0)
    try:
        if os.access(config, os.R_OK):
            pytest.skip("the user can read a mode 000 file")
        assert cli.main(["check", "--root", str(tmp_path)]) == 2
        err = capsys.readouterr().err
    finally:
        config.chmod(0o644)
    assert "cannot read" in err
    assert "hash-object" not in err


_FULL_JSON_KEYS = {
    "schema",
    "profile",
    "secret_engine",
    "secret_note",
    "survey",
    "findings",
    "plan",
    "kept",
    "moves",
    "repins",
    "score",
    "tree",
}
"""The keys of `check --json` with no `--baseline` (D15.3)."""


@pytest.mark.usefixtures("profile_env")
def test_check_json_is_schema_1_with_a_secret_note_and_a_line_per_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check --json` has exactly the schema 1 keys; each finding has an int `line` (D15.3).

    A gitleaks run that failed gives its note in `secret_note`; no note is `""`.

    arch: D15.3, D15.8
    """
    root = _profile_repo(tmp_path / "repo", 'version = 1\ntier = "T1"\n')
    data = json.loads(_check_json(root, capsys))
    assert set(data) == _FULL_JSON_KEYS
    assert data["schema"] == 1
    assert data["secret_note"] == ""
    assert set(data["profile"]) == {"name", "path", "source"}
    assert data["findings"]
    assert all(isinstance(finding["line"], int) for finding in data["findings"])

    note = "gitleaks failed: exit 2"
    monkeypatch.setattr(
        report.secrets,
        "scan",
        lambda *_args, **_kw: report.secrets.EngineRun(
            engine="built-in", note=note, findings=()
        ),
    )
    data = json.loads(_check_json(root, capsys))
    assert (data["secret_engine"], data["secret_note"]) == ("built-in", note)


@pytest.mark.usefixtures("profile_env")
def test_check_changed_json_has_the_schema_1_scoped_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--changed --json` has the schema 1 scoped keys; `kept` holds kept findings in scope (D15.3).

    The keep is the rule prefix `prose`, so it also proves a prefix keep
    under `--changed` (D15.8).

    arch: D15.3, D15.8
    """
    from trueup import docrules

    root = _profile_repo(
        tmp_path / "repo",
        'version = 1\ntier = "T1"\n\n[[keep]]\nid = "prose"\nreason = "r"\n',
    )
    word = docrules._load_banned_words()[0]
    (root / "docs" / "bad.md").write_text(f"this line names {word}\n", encoding="utf-8")
    data = json.loads(_check_json(root, capsys, "--changed"))
    assert set(data) == {
        "schema",
        "scope",
        "profile",
        "secret_engine",
        "secret_note",
        "survey",
        "findings",
        "plan",
        "kept",
        "tree",
        "score",
    }
    assert (data["schema"], data["scope"], data["score"]) == (1, "changed", None)
    assert data["kept"] == [{"id": "prose:docs/bad.md", "reason": "r"}]
    assert data["plan"] == []
    assert set(data["tree"]) == {"head", "status"}
    assert data["profile"]["source"] == "built-in default"


@pytest.mark.usefixtures("profile_env")
def test_the_text_header_of_a_target_that_is_not_adopted_names_the_house_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no `trueup.toml`, the profile line says how to get the house standard (D15.3).

    arch: D15.3
    """
    root = _profile_repo(tmp_path / "repo", None)
    capsys.readouterr()
    cli.main(["check", "--root", str(root)])
    lines = capsys.readouterr().out.splitlines()
    assert (
        "profile minimal (no trueup.toml; pass --profile house for the house standard)"
        in lines
    )
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--profile", "house"])
    house = str(_BUILTIN_PROFILES / "house.toml")
    assert f"profile house ({house})" in capsys.readouterr().out.splitlines()


@pytest.mark.usefixtures("profile_env")
def test_a_keep_that_matches_nothing_gives_a_keep_stale_row_on_a_full_run_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each `[[keep]]` id that matches no finding gives one `keep-stale` info row (D15.8).

    `--changed` gives none: every keep outside its scope would look stale.

    arch: D15.3, D15.8
    """
    root = _profile_repo(
        tmp_path / "repo",
        'version = 1\ntier = "T1"\n\n[[keep]]\nid = "prose:gone.md"\nreason = "r"\n',
    )
    data = json.loads(_check_json(root, capsys))
    stale = [finding for finding in data["findings"] if finding["rule"] == "keep-stale"]
    assert stale == [
        {
            "id": "keep-stale:prose:gone.md",
            "rule": "keep-stale",
            "category": "setup",
            "severity": "info",
            "path": "trueup.toml",
            "evidence": "keeps nothing",
            "action": "remove the [[keep]] entry or fix its id",
            "auto": False,
            "line": 0,
        }
    ]
    assert "keep-stale:prose:gone.md" not in {finding["id"] for finding in data["plan"]}
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    changed = json.loads(_check_json(root, capsys, "--changed"))
    assert all(finding["rule"] != "keep-stale" for finding in changed["findings"])


@pytest.mark.parametrize("mode", ["copy", "global"])
def test_a_page_prefix_refcheck_keep_holds_in_check_and_in_the_hook(
    tmp_path: Path, mode: str
) -> None:
    """`refcheck:<page>` keeps every checker row of the page in `check` and in the hook command (D15.8).

    arch: D15.3, D15.8
    """
    _git_init(tmp_path)
    _write_conforming_repo(tmp_path)
    refs_table = '[refs]\nmode = "copy"\n\n' if mode == "copy" else ""
    (tmp_path / "trueup.toml").write_text(
        f'version = 1\ntier = "T1"\ndocs = "full"\n\n{refs_table}[[keep]]\n'
        'id = "refcheck:docs/page.md"\nreason = "fixed page"\n',
        encoding="utf-8",
    )
    assert (
        cli.main(["apply", "--root", str(tmp_path), "--all-auto", "--allow-dirty"]) == 0
    )

    def hook() -> int:
        if mode == "copy":
            return subprocess.run(
                [sys.executable, "ref_check.py", "--root", "."],
                cwd=tmp_path,
                capture_output=True,
                check=False,
            ).returncode
        return cli.main(["refs", "--root", str(tmp_path)])

    run = report.collect(tmp_path)
    assert run.plan == []
    assert [(finding.id, reason) for finding, reason in report.kept_findings(run)] == [
        ("refcheck:docs/page.md:1:no-front-matter", "fixed page")
    ]
    assert all(finding.rule != "keep-stale" for finding in run.findings)
    assert cli.main(["check", "--root", str(tmp_path)]) == 0
    assert hook() == 0


def test_a_kept_secret_line_stays_kept_after_a_line_is_added_above_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The A8 case: a kept `secret-content` id still keeps its line after the line moves (D15.8).

    arch: D15.3, D15.8
    """
    from trueup.findings import line_fingerprint

    monkeypatch.setattr(report.secrets, "scan", lambda *_args, **_kw: None)
    _git_init(tmp_path)
    _clean_t0_repo(tmp_path)
    aws = "AKIA" + "Q" * 16  # built at run time, never a literal secret in the tree
    secret_line = f"K = '{aws}'"
    (tmp_path / "m3.py").write_text(f"x = 1\n{secret_line}\n", encoding="utf-8")
    finding_id = f"secret-content:m3.py:{line_fingerprint('m3.py', secret_line)}"
    (tmp_path / "trueup.toml").write_text(
        f'version = 1\n\n[[keep]]\nid = "{finding_id}"\nreason = "test key"\n',
        encoding="utf-8",
    )
    capsys.readouterr()
    cli.main(["check", "--root", str(tmp_path), "--json"])
    before = json.loads(capsys.readouterr().out)
    assert [entry["id"] for entry in before["kept"]] == [finding_id]

    (tmp_path / "m3.py").write_text(f"# head\nx = 1\n{secret_line}\n", encoding="utf-8")
    cli.main(["check", "--root", str(tmp_path), "--json"])
    after = json.loads(capsys.readouterr().out)
    assert [entry["id"] for entry in after["kept"]] == [finding_id]
    assert finding_id not in {finding["id"] for finding in after["plan"]}
    (moved,) = [f for f in after["findings"] if f["rule"] == "secret-content"]
    assert moved["line"] == 3


def test_a_doc_command_under_a_git_ignored_path_gives_info(tmp_path: Path) -> None:
    """`collect` asks git which missing command paths are ignored; those give `info`.

    arch: D15.16, D15.17
    """
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# App\n\n```sh\n./build/tool --go\n./gone/tool --go\n```\n", encoding="utf-8"
    )
    run = report.collect(tmp_path)
    severity = {f.id: f.severity for f in run.findings if f.rule == "drift-command"}
    assert severity == {
        "drift-command:README.md:./build/tool": "info",
        "drift-command:README.md:./gone/tool": "warn",
    }
