"""Acceptance test S25 and the refusals of `apply --plan`, the saved plan (arch: D12.1).

The messy tree is the S23 scramble of `tests/fixtures/converge/`, built
with the helpers of `tests/test_convergence.py`, so S25 runs on the same
tree as S23. Each plan file is written outside the repository root, as the
reference page tells the person to do.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from test_convergence import (
    SCRAMBLE_OPS,
    TWIN_SCRATCH,
    _git,
    _scratch_rows,
    _tidy,
    _twin_scratch_tree,
)

from trueup import apply as apply_mod
from trueup import changes, cli, layout, report
from trueup import secrets as secrets_mod
from trueup.config import ConfigError
from trueup.findings import Finding

TODAY = date(2026, 10, 10)
"""The run date of every `apply` call here, so two runs write the same `trueup.toml`."""

CHANGED_LINE = (
    "trueup: the tree changed since the plan was saved; run trueup check again"
)
"""The one refusal line for a tree that differs from the saved identity (D12.1)."""


def _scrambled(base: Path) -> Path:
    """Build the messy tree: the tidy `converge` fixture with every scramble operation.

    Args:
        base: The directory to build the repository in.

    Returns:
        The repository root. Every operation commits, so the tree is clean.
    """
    root = _tidy(base)
    for operation in SCRAMBLE_OPS:
        operation(root)
    return root


def _save_plan(
    root: Path, plan_file: Path, capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    """Run `check --json` and save what it prints to `plan_file`, as `> plan.json` does.

    Args:
        root: The target root.
        plan_file: The file to write, outside `root`.
        capsys: The pytest output capture.

    Returns:
        The parsed JSON report.
    """
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json"])
    printed = capsys.readouterr().out
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text(printed, encoding="utf-8")
    return json.loads(printed)


def _state(root: Path) -> tuple[dict[str, bytes], str, str]:
    """Give every file below `root` with its bytes, plus the git index and status.

    Args:
        root: The repository root.

    Returns:
        Relative path to bytes for each file outside `.git`, then the
        output of `git ls-files -s`, then `git status --porcelain`.
    """
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }
    return files, _git(root, "ls-files", "-s"), _git(root, "status", "--porcelain")


def test_s25_saved_plan_all_auto_gives_the_same_files_as_a_live_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S25: `apply --plan F --all-auto` gives the same files as `apply --all-auto` on a fresh copy.

    arch: D12.1, S25, I-40
    """
    saved_root = _scrambled(tmp_path / "saved")
    live_root = _scrambled(tmp_path / "live")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(saved_root, plan_file, capsys)
    assert data["tree"] == changes.tree_identity(saved_root)
    assert any(finding["auto"] for finding in data["plan"])

    assert apply_mod.run(live_root, None, True, [], [], today=TODAY) == 0
    assert (
        apply_mod.run(saved_root, None, True, [], [], today=TODAY, plan=plan_file) == 0
    )
    assert _state(saved_root) == _state(live_root)


def test_s25_saved_plan_applies_its_move_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S25: the move ids of the saved file apply with `--plan --ids`, the same as a live `--ids` run.

    arch: D12.1, S25, I-40
    """
    saved_root = _scrambled(tmp_path / "saved")
    live_root = _scrambled(tmp_path / "live")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(saved_root, plan_file, capsys)
    move_ids = [move["id"] for move in data["moves"]]
    assert move_ids, "the messy tree must plan at least one move"

    assert apply_mod.run(live_root, move_ids, False, [], [], today=TODAY) == 0
    assert (
        apply_mod.run(saved_root, move_ids, False, [], [], today=TODAY, plan=plan_file)
        == 0
    )
    assert _state(saved_root) == _state(live_root)
    assert not (saved_root / "ARCHITECTURE.md").exists()


def test_s25_second_edit_of_a_modified_file_refuses_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S25: a tracked file that is already modified and edited again after `check` gives exit 2 and no write.

    arch: D12.1, S25, I-40
    """
    root = _scrambled(tmp_path / "repo")
    (root / "README.md").write_text("# edit one\n", encoding="utf-8")
    plan_file = tmp_path / "outside" / "plan.json"
    _save_plan(root, plan_file, capsys)
    (root / "README.md").write_text("# edit two\n", encoding="utf-8")
    before = _state(root)

    assert apply_mod.run(root, None, True, [], [], today=TODAY, plan=plan_file) == 2
    captured = capsys.readouterr()
    assert captured.err.strip().splitlines() == [CHANGED_LINE]
    assert _state(root) == before


def test_saved_plan_run_never_collects_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`apply --plan` acts on the saved plan only: it calls `report.collect` not once.

    arch: D12.1, I-40
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(root, plan_file, capsys)
    move_ids = [move["id"] for move in data["moves"]]

    def _no_collect(*args: object, **kwargs: object) -> report.CheckRun:
        raise AssertionError("apply --plan called report.collect")

    monkeypatch.setattr(report, "collect", _no_collect)
    assert apply_mod.run(root, None, True, [], [], today=TODAY, plan=plan_file) == 0
    # The tree changed, so a second run with the same file refuses before any work.
    assert apply_mod.run(root, move_ids, False, [], [], plan=plan_file) == 2


def test_saved_plan_with_a_plan_file_inside_the_root_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A plan file that is untracked and not ignored inside the root changes the tree, so `apply` refuses and names the file.

    arch: D12.1, I-40
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = root / "plan.json"
    plan_file.write_text("", encoding="utf-8")  # the shell makes the file first
    _save_plan(root, plan_file, capsys)
    before = _state(root)
    assert apply_mod.run(root, None, True, [], [], plan=plan_file) == 2
    assert capsys.readouterr().err.strip().splitlines() == [
        "trueup: plan.json is inside the root and git does not ignore it, so it "
        "changes the tree; keep it outside the root, or under .scratch/ once "
        "gitignore:.gitignore is applied"
    ]
    assert _state(root) == before


@pytest.mark.parametrize(
    ("mode_args", "set_args"),
    [(["python=strict"], []), ([], ["tier=T2"])],
    ids=["mode", "set"],
)
def test_saved_plan_refuses_mode_and_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode_args: list[str],
    set_args: list[str],
) -> None:
    """`--mode` or `--set` with `--plan` gives exit 2 and one line: they need a new `check`.

    arch: D12.1
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    _save_plan(root, plan_file, capsys)
    before = _state(root)
    assert apply_mod.run(root, None, True, mode_args, set_args, plan=plan_file) == 2
    lines = capsys.readouterr().err.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("trueup: ")
    assert _state(root) == before


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("not json {", "JSON"),
        ('{"plan": [], "findings": [], "moves": []}', "tree"),
        ('{"tree": null, "plan": [], "findings": [], "moves": []}', "tree"),
        (
            '{"tree": {"head": "x", "status": "y"}, "plan": {}, "findings": [], "moves": []}',
            "bad plan",
        ),
    ],
    ids=["not-json", "no-tree", "null-tree", "bad-plan"],
)
def test_saved_plan_refuses_a_bad_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, word: str
) -> None:
    """A file that does not parse, or has no tree, or a null tree, gives exit 2, one line, no write.

    arch: D12.1
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    plan_file.parent.mkdir()
    plan_file.write_text(text, encoding="utf-8")
    before = _state(root)
    assert apply_mod.run(root, None, True, [], [], plan=plan_file) == 2
    lines = capsys.readouterr().err.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("trueup: ")
    assert word in lines[0]
    assert _state(root) == before


def test_saved_plan_refuses_an_id_the_file_does_not_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An id that is not in the saved plan or its move plan gives exit 2 and no write.

    arch: D12.1, I-19
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    _save_plan(root, plan_file, capsys)
    before = _state(root)
    assert apply_mod.run(root, ["move:no-such.md"], False, [], [], plan=plan_file) == 2
    assert "move:no-such.md" in capsys.readouterr().out
    assert _state(root) == before


def test_load_saved_run_reads_plan_findings_and_moves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`load_saved_run` gives `Finding` and `layout.Move` values, `pages` as a tuple, and empty repins.

    arch: D12.1
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(root, plan_file, capsys)
    saved = apply_mod.load_saved_run(plan_file)
    assert saved.tree == data["tree"]
    assert [finding.id for finding in saved.plan] == [
        finding["id"] for finding in data["plan"]
    ]
    assert all(isinstance(finding, Finding) for finding in saved.findings)
    assert len(saved.findings) == len(data["findings"])
    assert saved.moves
    assert all(isinstance(move, layout.Move) for move in saved.moves)
    assert all(isinstance(move.pages, tuple) for move in saved.moves)
    assert saved.moves == tuple(report.collect(root).moves)
    assert saved.repins == ()


def test_load_saved_run_raises_config_error_on_a_missing_file(tmp_path: Path) -> None:
    """A plan file that cannot be read gives `ConfigError`, which the CLI maps to exit 2.

    arch: D12.1
    """
    with pytest.raises(ConfigError):
        apply_mod.load_saved_run(tmp_path / "absent.json")


def test_cli_apply_plan_runs_the_saved_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup apply --plan F --all-auto` runs the saved plan; `--plan` alone is a usage error.

    arch: D12.1
    """
    root = _scrambled(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    _save_plan(root, plan_file, capsys)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["apply", "--root", str(root), "--plan", str(plan_file)])
    assert excinfo.value.code == 2
    code = cli.main(
        ["apply", "--root", str(root), "--plan", str(plan_file), "--all-auto"]
    )
    assert code == 0
    assert "wrote" in capsys.readouterr().out
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout
    assert status.strip()


# -- D15.27: a saved row must hold on the tree now ---------------------------


def _crafted_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], row: dict[str, object]
) -> tuple[Path, Path]:
    """Save the plan of a small clean repository, then add one crafted row to it.

    Args:
        tmp_path: The pytest temporary directory.
        capsys: The pytest output capture.
        row: The crafted plan row.

    Returns:
        The repository root and the plan file, outside the root.
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(root, plan_file, capsys)
    data["plan"].append(row)
    data["findings"].append(row)
    plan_file.write_text(json.dumps(data), encoding="utf-8")
    return root, plan_file


def _row(rule: str, path: str, finding_id: str | None = None) -> dict[str, object]:
    """Give one automatic plan row in the JSON shape of `check --json`.

    Args:
        rule: The rule name.
        path: The repo path.
        finding_id: The id; `<rule>:<path>` when `None`.

    Returns:
        The row.
    """
    return {
        "id": finding_id or f"{rule}:{path}",
        "rule": rule,
        "category": "files",
        "severity": "error",
        "path": path,
        "evidence": "crafted",
        "action": "crafted",
        "auto": True,
    }


def test_saved_plan_refuses_a_crafted_row_that_does_not_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A crafted `scratch` row on a source file is an unknown id: exit 2 and no write.

    arch: D15.27
    """
    root, plan_file = _crafted_plan(tmp_path, capsys, _row("scratch", "src/app.py"))
    capsys.readouterr()
    before = _state(root)
    assert (
        apply_mod.run(root, ["scratch:src/app.py"], False, [], [], plan=plan_file) == 2
    )
    assert "unknown id scratch:src/app.py" in capsys.readouterr().err
    assert apply_mod.run(root, None, True, [], [], plan=plan_file) == 2
    assert _state(root) == before


@pytest.mark.parametrize(
    "row",
    [
        _row("artifact", "src/app.py"),
        _row("generated", "src/app.py"),
        _row("secret-file", "src/app.py"),
        _row("gitignore", "src/app.py"),
        _row("file-managed", "src/app.py"),
        _row("scratch", "src/app.py", finding_id="scratch:README.md"),
        _row("config", "trueup.toml", finding_id="tier:trueup.toml"),
        _row("no-such-rule", "src/app.py"),
    ],
)
def test_saved_plan_refuses_each_rule_whose_predicate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], row: dict[str, object]
) -> None:
    """Each handled rule has a predicate; a row that fails it, or a bad id, writes nothing.

    arch: D15.27
    """
    root, plan_file = _crafted_plan(tmp_path, capsys, row)
    before = _state(root)
    assert apply_mod.run(root, [str(row["id"])], False, [], [], plan=plan_file) == 2
    assert _state(root) == before


def test_auto_rules_cover_every_rule_apply_handles() -> None:
    """`findings.AUTO_RULES` holds one predicate for each rule in `apply._RULES`.

    arch: D15.27
    """
    from trueup import findings as findings_mod

    assert set(findings_mod.AUTO_RULES) == set(apply_mod._RULES)


def test_saved_plan_secret_file_reads_the_saved_secret_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved `secret-file:.env` row holds when the saved run has a `secret-content` row on `.env`.

    The built-in scanner runs (no gitleaks), since it reads the `.env` file.

    arch: D15.27
    """
    monkeypatch.setattr(secrets_mod, "scan", lambda *args, **kwargs: None)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    key = "AKIA" + "Z3T7K2M9Q4W8R1Y6"
    (root / ".env").write_text(f"AWS_ACCESS_KEY_ID={key}\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    plan_file = tmp_path / "outside" / "plan.json"
    data = _save_plan(root, plan_file, capsys)
    auto_ids = {row["id"] for row in data["plan"] if row["auto"]}
    assert "secret-file:.env" in auto_ids
    assert apply_mod.run(root, ["secret-file:.env"], False, [], [], plan=plan_file) == 0
    assert ".env" not in _git(root, "ls-files")
    assert (root / ".env").is_file()


def test_saved_plan_removes_only_the_automatic_one_of_two_equal_scratch_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """I-35: `apply --plan` with `--all-auto` makes one pass, so the last copy stays.

    The contrast to `--all-auto` with no saved plan, which removes both
    copies across passes.

    arch: D16.9, I-35, I-40
    """
    root = _twin_scratch_tree(tmp_path / "twins")
    plan_file = tmp_path / "outside" / "plan.json"
    _save_plan(root, plan_file, capsys)
    rows = _scratch_rows(root)
    automatic = [path for path, auto in rows.items() if auto]
    manual = [path for path, auto in rows.items() if not auto]
    assert sorted(rows) == sorted(TWIN_SCRATCH)
    assert len(automatic) == 1
    assert len(manual) == 1

    assert apply_mod.run(root, None, True, [], [], today=TODAY, plan=plan_file) == 0

    tracked = set(_git(root, "ls-files").splitlines())
    assert automatic[0] not in tracked
    assert manual[0] in tracked
