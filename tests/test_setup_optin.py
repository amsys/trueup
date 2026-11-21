"""Tests for the setup opt-in: one `setup:trueup.toml` row below T2 (arch: D12.9, S26).

A tree at T0 or T1 with no `trueup.toml` gets one `info` row in place of
the `config` and `tool-missing` rows (D14.8). `apply --ids
setup:trueup.toml` writes the folded file in one pass. `--all-auto`
never takes the row.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from conftest import materialise
from trueup import apply as apply_mod
from trueup import cli, config, managed, report
from trueup import survey as survey_mod
from trueup.findings import Finding

DAY = date(2026, 10, 10)

SETUP_ID = "setup:trueup.toml"

T1_SETUP_FILES = ("trueup.toml",)
"""The tier set that the 9-file T1 fixture lacks: `trueup.toml` only (D14.8)."""

OLD_T1_FILES = (
    ".editorconfig",
    ".pre-commit-config.yaml",
    "lint/typescript/eslint.config.mjs",
    "lint/typescript/package.json",
)
"""The files an earlier trueup wrote at T1 for this fixture; legacy paths now (D14.8)."""

ABOVE_T1 = (
    managed.CI_PATH,
    managed.GITLEAKS_CONFIG_PATH,
    managed.REF_CHECK_CONFIG_PATH,
    managed.AGENT_RULES_PATH,
    ".vale.ini",
)
"""Paths whose minimum tier is above T1 for a tree with no `docs/` page."""


def _git(root: Path, *args: str) -> None:
    """Run one git command in a test repository.

    Args:
        root: The repository.
        *args: The git arguments.
    """
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _commit(root: Path) -> Path:
    """Make `root` a git repository with one commit of every file.

    The tree is committed, so a dirty-tree rule never acts on it (D12.2).

    Args:
        root: The tree.

    Returns:
        The same root.
    """
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _t1(tmp_path: Path) -> Path:
    """Materialise the 9-file T1 fixture as a committed repository.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    return _commit(materialise("setup_t1", tmp_path / "repo"))


def _t1_48(tmp_path: Path) -> Path:
    """Materialise the T1 fixture, add 39 small modules (48 files), and commit.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    root = materialise("setup_t1", tmp_path / "repo48")
    for number in range(39):
        (root / "src" / f"part{number:02d}.js").write_text(
            f"// Part {number} of the tool.\n\nmodule.exports = {{ part: {number} }};\n",
            encoding="utf-8",
        )
    return _commit(root)


def _t0(tmp_path: Path) -> Path:
    """Write a 2-file T0 tree (a README and one short script) and commit it.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    root = tmp_path / "repo0"
    root.mkdir()
    (root / "README.md").write_text("# Notes\n\nOne script.\n", encoding="utf-8")
    (root / "hello.py").write_text(
        '"""Say hello."""\n\nprint("hello")\n', encoding="utf-8"
    )
    return _commit(root)


def _ids(root: Path) -> dict[str, Finding]:
    """Collect one check run and map each finding id to its finding.

    Args:
        root: The target root.

    Returns:
        Finding id to finding.
    """
    return {finding.id: finding for finding in report.collect(root).findings}


def _files(root: Path) -> set[str]:
    """List every file under `root` outside `.git`.

    Args:
        root: The directory.

    Returns:
        The repo-relative POSIX paths.
    """
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _apply(root: Path, *, ids: list[str] | None = None, all_auto: bool = False) -> int:
    """Run `apply` with a fixed date.

    Args:
        root: The target root.
        ids: The ids for `--ids`.
        all_auto: Pass `--all-auto`.

    Returns:
        The exit code.
    """
    return apply_mod.run(
        root, ids=ids, all_auto=all_auto, mode_args=[], set_args=[], today=DAY
    )


def test_t1_check_shows_one_setup_row_and_the_real_findings(tmp_path: Path) -> None:
    """A T1 tree with no `trueup.toml` gets one `info` setup row, the refcheck row and the gitignore row.

    arch: D12.9, D14.22, D14.4, D14.8
    """
    root = _t1(tmp_path)
    found = _ids(root)
    assert report.collect(root).survey.tier == "T1"
    setup = found[SETUP_ID]
    assert setup.rule == "setup"
    assert setup.category == "setup"
    assert setup.severity == "info"
    assert setup.path == "trueup.toml"
    assert setup.auto is True
    assert setup.evidence == f"1 setup files: {', '.join(T1_SETUP_FILES)}"
    assert setup.action == "run trueup apply --ids setup:trueup.toml to write them"
    assert "gitignore:.gitignore" in found
    assert any(identifier.startswith("refcheck:main.js:") for identifier in found), (
        sorted(found)
    )
    for identifier in found:
        assert not identifier.startswith(
            ("file-managed:", "config:", "tool-missing:")
        ), identifier


def test_setup_row_is_not_in_the_plan(tmp_path: Path) -> None:
    """The setup row is `info`, so the plan never holds it (D5.4).

    arch: D12.9
    """
    root = _t1(tmp_path)
    assert SETUP_ID not in {finding.id for finding in report.collect(root).plan}


def test_markdown_report_lists_the_setup_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Markdown report prints the setup row in its `Info` section.

    arch: D12.9
    """
    root = _t1(tmp_path)
    cli.main(["check", "--root", str(root)])
    out = capsys.readouterr().out
    assert SETUP_ID in out.split("## Info", 1)[1]


def test_apply_setup_id_writes_the_tier_set_only(tmp_path: Path) -> None:
    """`apply --ids setup:trueup.toml` writes the T1 set in one run and no file above T1.

    arch: D12.9
    """
    root = _t1(tmp_path)
    before = _files(root)
    gitignore = (root / ".gitignore").read_bytes()
    assert _apply(root, ids=[SETUP_ID]) == 0
    written = _files(root) - before
    assert written == set(T1_SETUP_FILES)
    for path in ABOVE_T1:
        assert not (root / path).exists(), path
    assert (root / ".gitignore").read_bytes() == gitignore
    cfg = config.load(root)
    assert cfg is not None
    assert cfg.languages.get("typescript") == "clean"
    after = report.collect(root)
    assert after.survey.tier == "T1"
    ids = {finding.id for finding in after.findings}
    assert SETUP_ID not in ids
    assert not any(identifier.startswith("file-managed:") for identifier in ids)
    assert not any(identifier.startswith("config:") for identifier in ids)
    assert "gitignore:.gitignore" in ids


def test_apply_setup_id_prints_one_line_for_trueup_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`apply --ids setup:trueup.toml` prints `wrote trueup.toml` one time.

    The run writes the file and then stamps `run_date` into it. The stamp is
    a second write of the same path, and it gets no second line.

    arch: D12.9, D5.11
    """
    root = _t1(tmp_path)
    capsys.readouterr()
    assert _apply(root, ids=[SETUP_ID]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines.count("wrote trueup.toml") == 1


def test_all_auto_never_takes_the_setup_row(tmp_path: Path) -> None:
    """`--all-auto` fixes the gitignore row and writes no setup file.

    arch: D12.9
    """
    root = _t1(tmp_path)
    assert _apply(root, all_auto=True) == 0
    for path in T1_SETUP_FILES:
        assert not (root / path).exists(), path
    assert ".scratch/" in (root / ".gitignore").read_text(encoding="utf-8")
    assert SETUP_ID in _ids(root)


def test_48_file_t1_tree_stays_t1_after_the_opt_in(tmp_path: Path) -> None:
    """The setup file does not move a 48-file T1 tree to T2; the old managed files do.

    The opt-in writes `trueup.toml` only (D14.8), and that file does not
    count (I-43). An adopter of an earlier trueup also holds the old
    managed files. Decision D15.37 drops them from `TRUEUP_OWN_PATHS`, so
    they count as the person's files and the tree moves to T2. The test
    name is from before that decision.

    arch: D12.9, I-43, D14.22, D14.4, D14.8, D15.37
    """
    root = _t1_48(tmp_path)
    assert len(survey_mod.run(root).files) == 48
    assert report.collect(root).survey.tier == "T1"
    assert _apply(root, ids=[SETUP_ID]) == 0
    assert len(survey_mod.run(root).files) == 49
    for path in OLD_T1_FILES:
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("old managed file\n", encoding="utf-8")
    assert len(survey_mod.run(root).files) > 50
    after = report.collect(root)
    assert after.survey.tier == "T2"
    assert SETUP_ID not in {finding.id for finding in after.findings}


def test_t0_tree_gets_no_setup_row_and_no_write(tmp_path: Path) -> None:
    """A 2-file T0 tree gets no setup row; the setup id is unknown and nothing is written.

    arch: D12.9
    """
    root = _t0(tmp_path)
    run = report.collect(root)
    assert run.survey.tier == "T0"
    ids = {finding.id for finding in run.findings}
    assert SETUP_ID not in ids
    assert not any(
        identifier.startswith(("file-managed:", "config:", "tool-missing:"))
        for identifier in ids
    )
    before = _files(root)
    assert _apply(root, ids=[SETUP_ID]) == 2
    assert _apply(root, all_auto=True) in (0, 1)
    assert not (root / "trueup.toml").exists()
    assert {path for path in _files(root) - before} <= {".gitignore"}


def test_setup_findings_without_offer_gives_the_per_file_rows(tmp_path: Path) -> None:
    """`offer=False` gives the per-file rows that the setup row folds: `config` rows, no `file-managed` row (D14.8).

    arch: D12.9, D14.22, D14.4, D14.8
    """
    root = _t1(tmp_path)
    survey = survey_mod.run(root)
    folded = {finding.id for finding in managed.setup_findings(survey, None)}
    per_file = {
        finding.id for finding in managed.setup_findings(survey, None, offer=False)
    }
    assert SETUP_ID in folded
    assert SETUP_ID not in per_file
    assert "config:trueup.toml" in per_file
    assert "config:languages.typescript" in per_file
    assert not [
        identifier for identifier in per_file if identifier.startswith("file-managed:")
    ]
    assert "gitignore:.gitignore" in folded
    assert "gitignore:.gitignore" in per_file


def test_setup_findings_with_a_config_gives_the_per_file_rows(tmp_path: Path) -> None:
    """With a `trueup.toml`, the per-file rows show at T1 and no setup row: the copy-mode checker in copy mode, none in global mode (D14.8).

    arch: D12.9, D14.22, D14.4, D14.8
    """
    root = _t1(tmp_path)
    survey = survey_mod.run(root)
    ids = {finding.id for finding in managed.setup_findings(survey, config.Config())}
    assert SETUP_ID not in ids
    assert not [
        identifier for identifier in ids if identifier.startswith("file-managed:")
    ]
    copy = {
        finding.id
        for finding in managed.setup_findings(survey, config.Config(refs_mode="copy"))
    }
    assert SETUP_ID not in copy
    assert "file-managed:ref_check.py" in copy


def test_setup_id_with_a_config_present_is_unknown(tmp_path: Path) -> None:
    """Once `trueup.toml` exists, the setup id is unknown and `apply` exits 2.

    arch: D12.9
    """
    root = _t1(tmp_path)
    assert _apply(root, ids=[SETUP_ID]) == 0
    assert _apply(root, ids=[SETUP_ID]) == 2


def test_check_json_holds_the_setup_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --json` lists the setup row with `auto` true.

    arch: D12.9
    """
    root = _t1(tmp_path)
    cli.main(["check", "--root", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)
    rows = {row["id"]: row for row in data["findings"]}
    assert rows[SETUP_ID]["severity"] == "info"
    assert rows[SETUP_ID]["auto"] is True


def test_setup_row_folds_config_and_tool_missing_only(tmp_path: Path) -> None:
    """The fold takes the `config` and `tool-missing` rows; a `managed-legacy` row stays beside the setup row (D14.8).

    arch: D12.9, D14.22, D14.4, D14.8
    """
    root = _t1(tmp_path)
    (root / ".editorconfig").write_text(
        "# Managed by trueup. Edit trueup.toml, then run the trueup skill.\nroot = true\n",
        encoding="utf-8",
    )
    survey = survey_mod.run(root)
    rules = {finding.rule for finding in managed.setup_findings(survey, None)}
    assert "setup" in rules
    assert "managed-legacy" in rules
    assert not rules & {"config", "tool-missing", "file-managed"}
    assert managed._FOLDED_RULES == frozenset({"config", "tool-missing"})
