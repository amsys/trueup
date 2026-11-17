"""Tests for the checkbox report, `apply.approvable` and `apply --from-report` (arch: D12.3).

The messy tree is the S23 scramble of `tests/fixtures/converge/`, built
with the helpers of `tests/test_convergence.py`. Its plan holds automatic
and manual findings, a move plan and the setup opt-in row, and every
operation commits, so the tree is clean. Each report file is written
outside the repository root.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest
from test_convergence import SCRAMBLE_OPS, _tidy
from test_repin import REPIN_ID, _stale

from trueup import apply as apply_mod
from trueup import changes, cli, docrules, layout, managed, report
from trueup.findings import Finding

TODAY = date(2026, 10, 10)
"""The run date of every `apply` call here, so two runs write the same `trueup.toml`."""

CHANGED_LINE = (
    "trueup: the tree changed since the plan was saved; run trueup check again"
)
"""The one refusal line for a tree that differs from the saved identity (D12.1)."""

NO_TREE_LINE = (
    "trueup: the report has no tree comment; save a full check of a git root "
    "with trueup check --out, then tick its boxes"
)
"""The refusal line for a report that `check --changed` or a non-git root wrote (D12.3)."""


def _scrambled(base: Path) -> Path:
    """Build the messy tree: the tidy `converge` fixture with every scramble operation.

    Args:
        base: The directory to build the repository in.

    Returns:
        The repository root, with a clean tree.
    """
    root = _tidy(base)
    for operation in SCRAMBLE_OPS:
        operation(root)
    return root


def _markdown(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run `check` and give the Markdown report it prints.

    Args:
        root: The target root.
        capsys: The pytest output capture.

    Returns:
        The Markdown text.
    """
    capsys.readouterr()
    cli.main(["check", "--root", str(root)])
    return capsys.readouterr().out


def _save_ticked(
    root: Path, report_file: Path, ids: list[str], capsys: pytest.CaptureFixture[str]
) -> str:
    """Save the Markdown report to `report_file` with a ticked box on each id.

    Args:
        root: The target root.
        report_file: The file to write, outside `root`.
        ids: The ids whose box gets an `x`.
        capsys: The pytest output capture.

    Returns:
        The text written.
    """
    text = _markdown(root, capsys)
    for wanted in ids:
        box = f"- [ ] {wanted} "
        assert box in text, f"no box line for {wanted}"
        text = text.replace(box, f"- [x] {wanted} ", 1)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(text, encoding="utf-8")
    return text


def _box_id(line: str) -> str:
    """Give the id of one box line, by the reader rule of D12.3.

    Args:
        line: A line that starts with `- [ ] `.

    Returns:
        The text up to the first ` — ` or ` → `, stripped.
    """
    rest = line[len("- [ ] ") :]
    for separator in (" — ", " → "):
        rest = rest.split(separator, 1)[0]
    return rest.strip()


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
    return (
        files,
        _git_out(root, "ls-files", "-s"),
        _git_out(root, "status", "--porcelain"),
    )


def _git_out(root: Path, *args: str) -> str:
    """Run one read-only git command and give its output.

    Args:
        root: The repository root.
        *args: The git arguments.

    Returns:
        The standard output.
    """
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _commit_all(root: Path) -> None:
    """Commit every file of `root`, so the tree is clean.

    Args:
        root: The repository root.
    """
    for args in (("add", "-A"), ("commit", "-q", "-m", "fixture")):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )


def test_markdown_line_two_is_the_tree_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Line 2 of the Markdown report holds the tree identity as an HTML comment.

    arch: D12.3, D12.1
    """
    root = _scrambled(tmp_path / "repo")
    tree = changes.tree_identity(root)
    assert tree is not None
    lines = _markdown(root, capsys).splitlines()
    assert lines[0] == "# trueup check"
    assert (
        lines[1] == f"<!-- trueup tree head={tree['head']} status={tree['status']} -->"
    )
    assert lines[2] == ""


def test_check_outside_git_writes_no_report_so_no_tree_comment_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside a git work tree `check` exits 2 and prints no report, so no tree comment exists.

    arch: D12.3, D15.2
    """
    (tmp_path / "README.md").write_text("# R\n", encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a git repository" in captured.err


def test_boxes_sit_on_exactly_the_approvable_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The box lines name exactly the keys of `approvable`: auto findings, moves and the setup row.

    arch: D12.3
    """
    root = _scrambled(tmp_path / "repo")
    run = report.collect(root)
    approvable = apply_mod.approvable(run)
    markdown = _markdown(root, capsys)
    boxed = [
        _box_id(line) for line in markdown.splitlines() if line.startswith("- [ ] ")
    ]
    assert len(boxed) == len(set(boxed))
    assert set(boxed) == set(approvable)
    assert "scratch:notes.txt" in boxed
    assert "move:IDEAS.md" in boxed
    assert managed.SETUP_ID in boxed
    manual = [finding for finding in run.plan if not finding.auto]
    assert manual, "the messy tree must hold a manual plan finding"
    for finding in manual:
        assert finding.id not in approvable
        label = "ERROR" if finding.severity == "error" else "WARN"
        assert f"- [{label}] {finding.id} — {finding.evidence} — {finding.action}" in (
            markdown.splitlines()
        )


def test_box_line_forms_and_the_parity_parse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A box finding line keeps label, evidence and action; the parity parse gives its id.

    arch: D12.3, D5.11
    """
    root = _scrambled(tmp_path / "repo")
    run = report.collect(root)
    lines = _markdown(root, capsys).splitlines()
    finding = next(item for item in run.plan if item.id == "scratch:notes.txt")
    line = f"- [ ] {finding.id} — [ERROR] {finding.evidence} — {finding.action}"
    assert line in lines
    assert line.split("] ", 1)[1].split(" — ", 1)[0] == finding.id
    move = next(item for item in run.moves if item.id == "move:IDEAS.md")
    assert f"- [ ] {move.id} → {move.target} ({move.basis}: {move.evidence})" in lines


def test_approvable_maps_each_id_to_what_it_acts_on(tmp_path: Path) -> None:
    """`approvable` maps an auto finding id to its finding, a move id to its move, the setup id to its row.

    arch: D12.3
    """
    root = _scrambled(tmp_path / "repo")
    run = report.collect(root)
    approvable = apply_mod.approvable(run)
    auto_ids = {finding.id for finding in run.plan if finding.auto}
    move_ids = {move.id for move in run.moves}
    assert set(approvable) == auto_ids | move_ids | {managed.SETUP_ID}
    assert isinstance(approvable["scratch:notes.txt"], Finding)
    assert isinstance(approvable["move:IDEAS.md"], layout.Move)
    setup = approvable[managed.SETUP_ID]
    assert isinstance(setup, Finding) and setup.rule == "setup"


def test_approvable_holds_the_repin_ids(tmp_path: Path) -> None:
    """A re-pin entry is approvable; its stale-pin finding is not.

    arch: D12.3, D12.6
    """
    root = _stale(tmp_path / "repo")
    approvable = apply_mod.approvable(report.collect(root))
    assert isinstance(approvable[REPIN_ID], docrules.Repin)
    assert "refcheck:docs/a.md:3:stale-pin" not in approvable


def test_from_report_applies_the_ticked_ids_as_ids_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`apply --from-report` on ticked boxes gives the same files as `apply --ids` with those ids.

    arch: D12.3, I-40
    """
    report_root = _scrambled(tmp_path / "report")
    live_root = _scrambled(tmp_path / "live")
    ticked = ["scratch:notes.txt", "move:IDEAS.md"]
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(report_root, report_file, ticked, capsys)

    assert apply_mod.run(live_root, ticked, False, [], [], today=TODAY) == 0
    assert (
        apply_mod.run(
            report_root, None, False, [], [], today=TODAY, from_report=report_file
        )
        == 0
    )
    assert _state(report_root) == _state(live_root)
    assert not (report_root / "notes.txt").exists()
    assert (report_root / "docs" / "IDEAS.md").is_file()


def test_from_report_applies_the_setup_box(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ticked setup box writes the setup files, as `--ids setup:trueup.toml` does.

    arch: D12.3, D12.9
    """
    report_root = _scrambled(tmp_path / "report")
    live_root = _scrambled(tmp_path / "live")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(report_root, report_file, [managed.SETUP_ID], capsys)

    assert apply_mod.run(live_root, [managed.SETUP_ID], False, [], [], today=TODAY) == 0
    assert (
        apply_mod.run(
            report_root, None, False, [], [], today=TODAY, from_report=report_file
        )
        == 0
    )
    assert (report_root / "trueup.toml").is_file()
    assert _state(report_root) == _state(live_root)


def test_from_report_applies_a_ticked_repin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ticked re-pin box writes the new pin.

    arch: D12.3, D12.6
    """
    root = _stale(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, [REPIN_ID], capsys)
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 0
    )
    assert "pin:00000000" not in (root / "docs" / "a.md").read_text(encoding="utf-8")


def test_from_report_collects_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--from-report` makes one `report.collect` call, also after a pass that changed files.

    arch: D12.3, I-40
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, ["scratch:notes.txt", "move:IDEAS.md"], capsys)
    calls: list[Path] = []
    real_collect = report.collect

    def counting_collect(*args: object, **kwargs: object) -> report.CheckRun:
        calls.append(Path(str(args[0])))
        return real_collect(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(report, "collect", counting_collect)
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 0
    )
    assert not (root / "notes.txt").exists()
    assert calls == [root]


def test_from_report_refuses_a_report_with_no_tree_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report with no tree comment gives exit 2, its own refusal line and no write.

    arch: D12.3, I-40
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    text = _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    report_file.write_text(
        "\n".join(line for line in text.splitlines() if "<!-- trueup tree" not in line)
        + "\n",
        encoding="utf-8",
    )
    before = _state(root)
    capsys.readouterr()
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert NO_TREE_LINE in capsys.readouterr().err.splitlines()
    assert _state(root) == before


def test_from_report_refuses_a_report_inside_the_root_and_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report file that git does not ignore inside the root changes the tree; the refusal names the file.

    arch: D12.3, I-40
    """
    root = _scrambled(tmp_path / "repo")
    report_file = root / "report.md"
    _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    before = _state(root)
    capsys.readouterr()
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert capsys.readouterr().err.strip().splitlines() == [
        "trueup: report.md is inside the root and git does not ignore it, so it "
        "changes the tree; keep it outside the root, or under .scratch/ once "
        "gitignore:.gitignore is applied"
    ]
    assert _state(root) == before


def test_from_report_refuses_a_changed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An edit after the report was saved gives exit 2, the I-40 line and no write.

    arch: D12.3, I-40
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    with (root / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("\nOne more line.\n")
    before = _state(root)
    capsys.readouterr()
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert CHANGED_LINE in capsys.readouterr().err.splitlines()
    assert _state(root) == before


@pytest.mark.parametrize(
    "line",
    [
        "- [x] root-budget: — hand-typed tick on a manual finding",
        "- [X] nothing:here — an id the run does not know",
    ],
)
def test_from_report_refuses_a_ticked_id_that_is_not_approvable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    """A hand-typed tick on a manual or unknown id gives exit 2 and no write.

    arch: D12.3, I-19
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    text = _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    report_file.write_text(text + line + "\n", encoding="utf-8")
    before = _state(root)
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert _state(root) == before


def test_from_report_refuses_a_report_with_no_ticked_box(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report with no ticked box names no id: exit 2 and no write.

    arch: D12.3
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, [], capsys)
    before = _state(root)
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert _state(root) == before


def test_from_report_cuts_a_path_with_a_dash_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Break case: a path that holds ` — ` gives a cut id that fails validation; nothing is written.

    arch: D12.3
    """
    root = _scrambled(tmp_path / "repo")
    (root / "gen — x.py").write_text("# @generated\nX = 1\n", encoding="utf-8")
    _commit_all(root)
    finding_id = "generated:gen — x.py"
    assert finding_id in apply_mod.approvable(report.collect(root))
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, [finding_id], capsys)
    before = _state(root)
    capsys.readouterr()
    assert (
        apply_mod.run(root, None, False, [], [], today=TODAY, from_report=report_file)
        == 2
    )
    assert "generated:gen" in capsys.readouterr().out
    assert _state(root) == before


def test_cli_from_report_runs_the_ticked_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup apply --from-report FILE` reaches `apply.run` and applies the ticked ids.

    arch: D12.3
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    code = cli.main(["apply", "--root", str(root), "--from-report", str(report_file)])
    assert code == 0
    assert not (root / "notes.txt").exists()


def test_cli_from_report_excludes_ids_and_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--from-report` is one member of the group with `--ids` and `--all-auto`, and takes no `--plan`.

    arch: D12.3, D12.1
    """
    root = _scrambled(tmp_path / "repo")
    report_file = tmp_path / "outside" / "report.md"
    _save_ticked(root, report_file, ["scratch:notes.txt"], capsys)
    with pytest.raises(SystemExit) as raised:
        cli.main(
            [
                "apply",
                "--root",
                str(root),
                "--from-report",
                str(report_file),
                "--ids",
                "scratch:notes.txt",
            ]
        )
    assert raised.value.code == 2
    before = _state(root)
    code = cli.main(
        [
            "apply",
            "--root",
            str(root),
            "--from-report",
            str(report_file),
            "--plan",
            str(tmp_path / "outside" / "plan.json"),
        ]
    )
    assert code == 2
    assert _state(root) == before
