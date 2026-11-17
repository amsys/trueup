"""Tests for `trueup.apply`: validation first, the handlers, re-runs and the safety rules (arch: D5.6)."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from datetime import date
from pathlib import Path

import pytest

from conftest import materialise
from trueup import apply as apply_mod
from trueup import cli, config, managed, report
from trueup.rulesets import RULESETS, render_eslint_config

DAY_ONE = date(2026, 9, 25)
DAY_TWO = date(2026, 10, 1)


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


def _messy(tmp_path: Path) -> Path:
    """Materialise the messy fixture as a git repository with no commits.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    tree = materialise("messy", tmp_path / "repo")
    _git(tree, "init", "-q")
    return tree


def _messy_t2(tmp_path: Path) -> Path:
    """Materialise the messy fixture at tier T2, with no `trueup.toml`.

    D12.9: below T2 the setup rows fold into the `setup:trueup.toml`
    opt-in row (T1) or go away (T0), so a test of the `config:trueup.toml`
    id needs a T2 tree. A CI workflow and a tag make the tier T2. Every
    file is committed.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        The repository root.
    """
    tree = _messy(tmp_path)
    (tree / ".github" / "workflows").mkdir(parents=True)
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        "on: push\njobs: {}\n", encoding="utf-8"
    )
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "fixture")
    _git(tree, "-c", "tag.gpgsign=false", "tag", "v1")
    assert report.collect(tree).survey.tier == "T2"
    return tree


def _snapshot(root: Path) -> dict[str, bytes]:
    """Read every file under `root` outside `.git`, plus the git index listing.

    Args:
        root: The directory.

    Returns:
        Relative path to bytes, and the key `"<index>"` for `git ls-files --stage`.
    """
    files = {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }
    files["<index>"] = subprocess.run(
        ["git", "ls-files", "--stage"], cwd=root, capture_output=True, check=True
    ).stdout
    return files


def _apply(root: Path, *args: str, today: date = DAY_ONE) -> int:
    """Run `apply` on a root with a fixed date.

    Args:
        root: The target root.
        *args: The `--ids`/`--all-auto`, `--mode` and `--set` arguments.
        today: The date for `run_date`.

    Returns:
        The exit code.
    """
    ids = None
    all_auto = False
    modes: list[str] = []
    sets: list[str] = []
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if flag == "--all-auto":
            all_auto = True
        elif flag == "--ids":
            ids = rest.pop(0).split(",")
        elif flag == "--mode":
            modes.append(rest.pop(0))
        elif flag == "--set":
            sets.append(rest.pop(0))
    # arch: D12.2 - the fixture has no commit, so every file is untracked and
    # dirty. These tests check the handlers, not the refusal, so they allow it.
    return apply_mod.run(
        root,
        ids=ids,
        all_auto=all_auto,
        mode_args=modes,
        set_args=sets,
        today=today,
        allow_dirty=True,
    )


@pytest.mark.parametrize(
    "ids",
    [
        "no-such:id",
        "health-license:",
        "duplicate:data2.csv",
        "scratch:tmp-draft.md",
        "gitignore:.gitignore,no-such:id",
        "gitignore:.gitignore,duplicate:data2.csv",
    ],
)
def test_bad_id_exits_two_and_changes_nothing(tmp_path: Path, ids: str) -> None:
    """An unknown id, an info id, or a manual id stops the run at exit 2 before any write, even beside a good id.

    `scratch:tmp-draft.md` is manual because git does not track the file.

    arch: D5.11, I-19
    """
    tree = _messy(tmp_path)
    before = _snapshot(tree)
    assert _apply(tree, "--ids", ids) == 2
    assert _snapshot(tree) == before


@pytest.mark.parametrize(
    "args",
    [
        ("--all-auto", "--mode", "python=loose"),
        ("--all-auto", "--mode", "cobol=clean"),
        ("--all-auto", "--set", "tier=T9"),
        ("--all-auto", "--set", "stale_days=0"),
        ("--all-auto", "--set", "colour=red"),
    ],
)
def test_bad_mode_or_set_exits_two_and_changes_nothing(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    """A `--mode` or `--set` value that apply cannot use is exit 2 with no file changed.

    arch: D5.11, I-19
    """
    tree = _messy(tmp_path)
    before = _snapshot(tree)
    assert _apply(tree, *args) == 2
    assert _snapshot(tree) == before


def test_set_values_are_ones_config_load_accepts(tmp_path: Path) -> None:
    """Every enumerated `--set` value that apply accepts round-trips through `config.load`.

    `profile` takes a name that matches a pattern, not a list of values;
    the test takes the two built-in names for it (D14.1, D14.3).

    arch: D5.3, D14.3
    """
    for key, choices in apply_mod._SET_CHOICES.items():
        values = choices
        if isinstance(choices, re.Pattern):
            values = ("house", "minimal")
            assert all(choices.fullmatch(value) for value in values)
        for value in values:
            literal = value if key == "public" else f'"{value}"'
            (tmp_path / "trueup.toml").write_text(
                f"version = 1\n{key} = {literal}\n", encoding="utf-8"
            )
            assert config.load(tmp_path) is not None


def test_all_auto_twice_is_safe_to_re_run(tmp_path: Path) -> None:
    """After `apply --all-auto`, check has no auto finding, and a second run changes no byte.

    arch: I-20
    """
    tree = _messy(tmp_path)
    assert _apply(tree, "--all-auto") == 0
    after_first = report.collect(tree)
    assert [finding.id for finding in after_first.findings if finding.auto] == []
    snapshot = _snapshot(tree)
    assert _apply(tree, "--all-auto", today=DAY_TWO) == 0
    assert _snapshot(tree) == snapshot


def test_run_date_changes_only_when_a_file_changed(tmp_path: Path) -> None:
    """`run_date` is the date of the apply that changed a file; a no-op apply keeps it.

    arch: D5.3, D5.6, D12.9
    """
    tree = _messy(tmp_path)
    # D12.9: the messy fixture is T0, where `--all-auto` writes no
    # trueup.toml, so the test starts from a written one.
    (tree / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    _apply(tree, "--all-auto", today=DAY_ONE)
    assert config.load(tree).run_date == DAY_ONE.isoformat()
    _apply(tree, "--all-auto", today=DAY_TWO)
    assert config.load(tree).run_date == DAY_ONE.isoformat()


def test_ids_config_only_writes_trueup_toml(tmp_path: Path) -> None:
    """`--ids config:trueup.toml` writes trueup.toml and no other file.

    arch: D5.6, D12.9
    """
    tree = _messy_t2(tmp_path)  # D12.9: the config id shows at T2 only
    before = _snapshot(tree)
    assert _apply(tree, "--ids", "config:trueup.toml") == 0
    after = _snapshot(tree)
    changed = {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    }
    assert changed == {"trueup.toml"}


def test_mode_writes_the_config_and_the_strict_rule_set(tmp_path: Path) -> None:
    """`--mode python=strict` lands in trueup.toml; `apply` writes no ruff config (D14.8).

    The strict rule set names the strict ruff template; `trueup lint`
    renders it at run time, never under the root.

    arch: D5.3, D5.6, D14.22, D14.4, D14.8
    """
    tree = _messy(tmp_path)
    assert (
        _apply(tree, "--all-auto", "--mode", "python=strict", "--set", "tier=T1") == 0
    )
    assert config.load(tree).languages["python"] == "strict"
    assert not (tree / "lint").exists()
    templates = RULESETS[("python", "strict")].files.values()
    assert "rules/python/ruff-strict.toml" in templates


def test_scratch_untracked_is_never_deleted_and_tracked_is_git_removed(
    tmp_path: Path,
) -> None:
    """`scratch` runs `git rm` on a tracked file; an untracked one is manual and stays on disk.

    The handler itself also skips an untracked path, so a finding whose file
    lost its tracked state after `check` still deletes nothing.

    arch: D5.6
    """
    tree = _messy(tmp_path)
    (tree / "scratch.txt").write_text("a tracked scratch file\n", encoding="utf-8")
    _git(tree, "add", "scratch.txt")
    _git(tree, "commit", "-q", "-m", "test")
    plan = {finding.id: finding for finding in report.collect(tree).plan}
    assert plan["scratch:tmp-draft.md"].auto is False
    assert plan["scratch:scratch.txt"].auto is True
    assert _apply(tree, "--ids", "scratch:tmp-draft.md") == 2
    assert _apply(tree, "--ids", "scratch:scratch.txt") == 0
    assert (tree / "tmp-draft.md").exists()
    assert not (tree / "scratch.txt").exists()
    listed = subprocess.run(
        ["git", "ls-files"], cwd=tree, capture_output=True, text=True, check=True
    )
    assert "scratch.txt" not in listed.stdout.split()
    ctx = apply_mod._Context(root=tree, protect=(), rendered={})
    apply_mod._handle_scratch(ctx, plan["scratch:tmp-draft.md"])
    assert (tree / "tmp-draft.md").exists()
    assert ctx.changed == []


def test_artifact_is_untracked_kept_on_disk_and_ignored(tmp_path: Path) -> None:
    """`artifact` runs `git rm --cached -r` on the directory, keeps the working copy, and adds one .gitignore line.

    arch: D5.6
    """
    tree = _messy(tmp_path)
    cache = tree / "pkg/__pycache__"
    cache.mkdir(parents=True)
    for index in range(30):
        (cache / f"mod{index}.cpython-312.pyc").write_bytes(b"\x00compiled")
    _git(tree, "add", "pkg/__pycache__")
    assert _apply(tree, "--ids", "artifact:pkg/__pycache__/") == 0
    assert (cache / "mod0.cpython-312.pyc").read_bytes() == b"\x00compiled"
    listed = subprocess.run(
        ["git", "ls-files"], cwd=tree, capture_output=True, text=True, check=True
    )
    assert "__pycache__" not in listed.stdout
    lines = (tree / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if "pycache" in line] == ["/pkg/__pycache__/"]
    assert not [f for f in report.collect(tree).findings if f.rule == "artifact"]


def test_artifact_directory_holding_a_protected_file_is_skipped(tmp_path: Path) -> None:
    """A directory `artifact` is left tracked when a file inside it matches a `protect` glob (I-24).

    arch: I-24
    """
    tree = _messy(tmp_path)
    cache = tree / "node_modules/pkg"
    cache.mkdir(parents=True)
    (cache / "keep.js").write_text("module.exports = 1;\n", encoding="utf-8")
    _git(tree, "add", "node_modules")
    (tree / "trueup.toml").write_text(
        'version = 1\nprotect = ["node_modules/pkg/keep.js"]\n', encoding="utf-8"
    )
    assert _apply(tree, "--ids", "artifact:node_modules/") == 0
    listed = subprocess.run(
        ["git", "ls-files"], cwd=tree, capture_output=True, text=True, check=True
    )
    assert "node_modules/pkg/keep.js" in listed.stdout.split()


def test_artifact_gitignore_line_is_not_repeated_when_already_covered(
    tmp_path: Path,
) -> None:
    """`artifact` adds no `.gitignore` line when a pattern already covers the path.

    arch: D10.5
    """
    tree = _messy(tmp_path)
    (tree / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    (tree / ".gitignore").write_text("target/\n", encoding="utf-8")
    build = tree / "target"
    build.mkdir()
    (build / "out.bin").write_bytes(b"\x00built")
    _git(tree, "add", "-f", "Cargo.toml", "target", ".gitignore")
    assert _apply(tree, "--ids", "artifact:target/") == 0
    listed = subprocess.run(
        ["git", "ls-files"], cwd=tree, capture_output=True, text=True, check=True
    )
    assert "target" not in listed.stdout
    lines = (tree / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines == ["target/"]


def test_secret_that_looks_like_scratch_is_untracked_not_deleted(
    tmp_path: Path,
) -> None:
    """A tracked `.env.bak` is untracked and kept on disk, never removed as scratch (D5.6).

    arch: D5.4, D5.6
    """
    tree = _messy(tmp_path)
    (tree / ".env.bak").write_text("KEY=1\n", encoding="utf-8")
    _git(tree, "add", ".env.bak")
    _git(tree, "commit", "-q", "-m", "test")
    ids = {finding.id for finding in report.collect(tree).plan}
    assert "secret-file:.env.bak" in ids
    assert "scratch:.env.bak" not in ids
    assert _apply(tree, "--all-auto") == 0
    assert (tree / ".env.bak").read_text(encoding="utf-8") == "KEY=1\n"


def test_bundled_ref_check_does_not_turn_python_on(tmp_path: Path) -> None:
    """`apply --all-auto` on a Go-only repository in copy mode writes `ref_check.py` but adds no Python mode (D5.4, D5.6).

    arch: D5.4, D5.6
    """
    tree = tmp_path / "repo"
    tree.mkdir()
    _git(tree, "init", "-q")
    (tree / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    (tree / "README.md").write_text("# go\n", encoding="utf-8")
    # D14.8: tier T1 keeps the test as it was; the pre-commit file left the set.
    (tree / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\n\n[refs]\nmode = "copy"\n', encoding="utf-8"
    )
    assert _apply(tree, "--all-auto") == 0
    assert (tree / "ref_check.py").is_file()
    assert "python" not in config.load(tree).languages
    assert not [
        f.id for f in report.collect(tree).findings if f.id == "config:languages.python"
    ]
    assert not (tree / ".pre-commit-config.yaml").exists()
    # D14.9: the ruff hooks are lint hooks now; no hook file holds them.
    assert not [
        hook for hook in managed.lint_hooks(config.load(tree)) if "ruff" in hook.entry
    ]


def test_secret_file_is_untracked_and_its_bytes_stay_out_of_every_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An automatic `.env` is untracked; no finding or output line holds its content.

    arch: D5.6, I-49, D15.10
    """
    tree = _messy(tmp_path)
    secret_value = "AKIA" + "QY7TM2PL" + "ZK4XW6RB"  # built at run time
    (tree / ".env").write_text(f"KEY={secret_value}\n", encoding="utf-8")
    secret = (tree / ".env").resolve()
    for finding in report.collect(tree).findings:
        assert secret_value not in f"{finding.evidence} {finding.action}"
    assert _apply(tree, "--ids", "secret-file:.env") == 0
    captured = capsys.readouterr()
    assert secret_value not in captured.out + captured.err
    assert "/.env" in (tree / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert secret.exists()


def test_generated_and_gitignore_handlers_append_their_lines(tmp_path: Path) -> None:
    """`generated` adds a .gitattributes line; `gitignore` adds `.scratch/`; both findings then clear.

    arch: D5.6
    """
    tree = _messy(tmp_path)
    assert _apply(tree, "--ids", "generated:vendor_bundle.js,gitignore:.gitignore") == 0
    attributes = (tree / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "vendor_bundle.js linguist-generated=true" in attributes
    assert ".scratch/" in (tree / ".gitignore").read_text(encoding="utf-8").splitlines()
    ids = {finding.id for finding in report.collect(tree).findings}
    assert "generated:vendor_bundle.js" not in ids
    assert "gitignore:.gitignore" not in ids


def test_apply_never_runs_git_commit_push_or_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every git call apply makes is `rm` or `ls-files`, never `commit`, `push` or `clean`.

    arch: I-23
    """
    tree = _messy(tmp_path)
    (tree / "scratch.txt").write_text("a tracked scratch file\n", encoding="utf-8")
    _git(tree, "add", "scratch.txt")
    _git(tree, "commit", "-q", "-m", "test")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def _recording_run(command: list[str], *args: object, **kwargs: object) -> object:
        calls.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(apply_mod.subprocess, "run", _recording_run)
    assert _apply(tree, "--all-auto") == 0
    git_subcommands = {
        call[2] for call in calls if call[:2] == ["git", "--literal-pathspecs"]
    }
    assert git_subcommands
    assert git_subcommands <= {"rm", "ls-files"}
    with pytest.raises(RuntimeError):
        apply_mod._git(
            apply_mod._Context(root=tree, protect=(), rendered={}),
            ["commit", "-m", "x"],
        )


def test_unmanaged_file_is_never_overwritten(tmp_path: Path) -> None:
    """A managed path holding a file with no trueup header is manual: apply refuses its id and leaves it.

    arch: I-24
    """
    tree = _messy(tmp_path)
    own = "repos: []\n"
    (tree / ".pre-commit-config.yaml").write_text(own, encoding="utf-8")
    assert _apply(tree, "--ids", "file-managed:.pre-commit-config.yaml") == 2
    assert _apply(tree, "--all-auto") == 0
    assert (tree / ".pre-commit-config.yaml").read_text(encoding="utf-8") == own


def test_protect_glob_keeps_a_path_and_its_side_file(tmp_path: Path) -> None:
    """A `protect` glob makes the finding manual and apply leaves the path, and a protected .gitignore, alone.

    arch: I-24
    """
    tree = _messy(tmp_path)
    (tree / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    _git(
        tree, "add", "tmp-draft.md"
    )  # tracked, so only the protect glob makes it manual
    # A glob, not the file name: the scratch row drops a name that another
    # file (here trueup.toml) mentions.
    (tree / "trueup.toml").write_text(
        'version = 1\nprotect = ["tmp*.md", ".gitignore"]\n', encoding="utf-8"
    )
    plan = {finding.id: finding for finding in report.collect(tree).plan}
    assert plan["scratch:tmp-draft.md"].auto is False
    assert plan["secret-file:.env"].auto is False
    assert _apply(tree, "--ids", "scratch:tmp-draft.md") == 2
    assert _apply(tree, "--all-auto") == 0
    assert (tree / "tmp-draft.md").exists()
    assert (tree / ".gitignore").read_text(encoding="utf-8") == "*.pyc\n"


def test_cli_apply_prints_one_line_per_action(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup apply` through the CLI exits 0 and prints a line per write or removal.

    arch: D5.11, D12.9
    """
    # D12.9: the config id shows at T2 only; `_messy_t2` commits
    # tmp-draft.md as the test did before.
    tree = _messy_t2(tmp_path)
    # D15.9: a compound scratch name is manual; use a whole-stem name.
    _git(tree, "mv", "tmp-draft.md", "tmp.md")
    _git(tree, "commit", "-q", "-m", "rename")
    assert (
        cli.main(
            [
                "apply",
                "--root",
                str(tree),
                "--ids",
                "scratch:tmp.md,config:trueup.toml",
            ]
        )
        == 0
    )
    lines = capsys.readouterr().out.splitlines()
    assert "wrote trueup.toml" in lines
    assert "removed tmp.md" in lines


def test_protected_trueup_toml_keeps_its_run_date(tmp_path: Path) -> None:
    """With `trueup.toml` under a `protect` glob, an apply that changes files leaves it byte-identical.

    arch: I-24
    """
    tree = _messy(tmp_path)
    text = 'version = 1\nprotect = ["trueup.toml"]\n\n[languages]\ntypescript = "off"\n'
    (tree / "trueup.toml").write_text(text, encoding="utf-8")
    assert _apply(tree, "--ids", "gitignore:.gitignore") == 0
    assert (tree / ".gitignore").is_file()
    assert (tree / "trueup.toml").read_text(encoding="utf-8") == text


def test_ids_with_no_config_id_ignores_set_and_writes_no_trueup_toml(
    tmp_path: Path,
) -> None:
    """`--ids` naming no `config` id drops a `--set` value: no `trueup.toml` write (LOW-9).

    A person who reads only the report and approves `gitignore:.gitignore`
    never approved a `trueup.toml` change, so `--set docs=full` beside it
    must not write the file.

    arch: D6.15
    """
    tree = _messy(tmp_path)
    assert _apply(tree, "--ids", "gitignore:.gitignore", "--set", "docs=full") == 0
    assert (tree / ".gitignore").is_file()
    assert not (tree / "trueup.toml").exists()


def test_apply_in_global_mode_writes_no_copy_and_leaves_an_old_one_in_place(
    tmp_path: Path,
) -> None:
    """In global mode, the default, `apply` writes no checker copy, changes no file it did not write, and the old copy is an `info` finding (D9.1).

    arch: D9.1
    """
    tree = tmp_path / "repo"
    tree.mkdir()
    _git(tree, "init", "-q")
    (tree / "README.md").write_text("# demo\n", encoding="utf-8")
    (tree / "ref_check.py").write_text("print('an old copy')\n", encoding="utf-8")
    # D14.8: tier T1 keeps the test as it was; the pre-commit file left the set.
    assert _apply(tree, "--all-auto", "--set", "tier=T1") == 0
    assert (tree / "ref_check.py").read_text(
        encoding="utf-8"
    ) == "print('an old copy')\n"
    assert config.load(tree).refs_mode == "global"
    assert not (tree / ".pre-commit-config.yaml").exists()
    # D14.9: the pre-commit snippet runs `trueup lint` in every mode.
    text = managed.render_pre_commit()
    assert "entry: trueup lint" in text
    assert "python3 ref_check.py" not in text
    findings = {finding.id: finding for finding in report.collect(tree).findings}
    assert "file-managed:ref_check.py" not in findings
    assert findings["refs-copy:ref_check.py"].severity == "info"


_ESLINT_OFF_CONFIG = """version = 1
tier = "T1"

[languages]
python = "clean"
typescript = "clean"

[[eslint.off]]
rule = "security/detect-object-injection"
reason = "numeric code indexes objects by computed keys"
"""


def test_apply_keeps_eslint_off_and_renders_it_into_the_eslint_config(
    tmp_path: Path,
) -> None:
    """`apply` keeps `[[eslint.off]]` when it writes trueup.toml again, and renders the rule into the eslint config.

    Then `check` holds no finding on the eslint pair or on a tracked
    `lint/typescript/eslint-suppressions.json`: trueup does not manage
    that file, and no scratch, root, artifact or lockfile row names it.
    D14.8: `apply` writes no eslint config; `render_eslint_config` renders
    the rule from the loaded config, as `trueup lint` does (D14.7). A
    changed reason changes that text and gives no `file-managed` row.

    arch: D13.5, D13.6, D5.6, D8.3, D14.22, D14.4, D14.8
    """
    tree = _messy(tmp_path)
    (tree / "trueup.toml").write_text(_ESLINT_OFF_CONFIG, encoding="utf-8")
    assert _apply(tree, "--all-auto", "--mode", "python=strict") == 0
    cfg = config.load(tree)
    assert cfg.languages["python"] == "strict"
    assert cfg.eslint_off == {
        "security/detect-object-injection": "numeric code indexes objects by computed keys"
    }
    assert "[[eslint.off]]" in (tree / "trueup.toml").read_text(encoding="utf-8")
    assert not (tree / "lint/typescript/eslint.config.mjs").exists()
    eslint_config = render_eslint_config("clean", "off", cfg.eslint_off)
    assert (
        '    "security/detect-object-injection": "off", // numeric code indexes objects by computed keys\n'
        in eslint_config
    )
    assert eslint_config.endswith(
        "export default tseslint.config(tsBlock, offBlock);\n"
    )

    suppressions = tree / "lint/typescript/eslint-suppressions.json"
    suppressions.parent.mkdir(parents=True)
    suppressions.write_text(
        '{\n  "src/a.ts": {\n    "jsdoc/require-jsdoc": {\n      "count": 2\n    }\n  }\n}',
        encoding="utf-8",
    )
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "applied")
    run = report.collect(tree)
    named = [
        finding.id
        for finding in run.findings
        if "eslint-suppressions" in finding.id
        or "eslint-suppressions" in finding.path
        or "lint/typescript/eslint.config.mjs" in finding.id
        or "lint/typescript/package.json" in finding.id
    ]
    assert named == []

    text = (tree / "trueup.toml").read_text(encoding="utf-8")
    (tree / "trueup.toml").write_text(
        text.replace("by computed keys", "by computed keys, each a lookup"),
        encoding="utf-8",
    )
    plan = {finding.id: finding for finding in report.collect(tree).plan}
    assert "file-managed:lint/typescript/eslint.config.mjs" not in plan
    changed = render_eslint_config("clean", "off", config.load(tree).eslint_off)
    assert changed != eslint_config
    assert "by computed keys, each a lookup" in changed


def test_merge_marks_the_set_keys_and_languages_explicit() -> None:
    """`_merge` adds each `--set` key and `languages` to `explicit`, so a default value is written.

    arch: D14.3, D14.19
    """
    merged = apply_mod._merge(None, {"python": "clean"}, {"tier": "auto"})
    assert merged.explicit == frozenset({"languages", "tier"})
    text = config.render(merged)
    assert 'tier = "auto"' in text
    assert 'python = "clean"' in text
    empty = apply_mod._merge(None, {}, {})
    assert "[languages]" in config.render(empty)
    kept = apply_mod._merge(
        config.Config(explicit=frozenset({"public"})), {}, {"docs": "auto"}
    )
    assert kept.explicit == frozenset({"public", "languages", "docs"})


_ALL_DEFAULTS = """# trueup configuration. The trueup skill writes this file. A person can edit it.
version = 1
run_date = "2026-09-01"
tier = "auto"                # auto | T0 | T1 | T2 | T3
public = false                # true adds C1, C2 and the public health files
docs = "auto"                # auto | full | readme
stale_days = 180                # P8
ignore = []   # globs left out of the survey and all findings
protect = []                 # globs that apply never changes or removes

[root]
allow = []                   # root entries allowed beyond the base list (D5.8)

[scratch]
allow = []                   # paths or names the scratch rule lets through (D5.8)

[languages]                  # one key per language: strict | clean | off
"""


def test_apply_keeps_the_keys_the_file_set_and_writes_set_tier_auto(
    tmp_path: Path,
) -> None:
    """`apply --set tier=auto` writes the key at its default value; the keys the file set stay.

    The file holds every key at its default value. After the write, only
    the run date and the languages differ.

    arch: D14.3, D14.19
    """
    tree = _messy(tmp_path)
    (tree / "trueup.toml").write_text(_ALL_DEFAULTS, encoding="utf-8")
    assert _apply(tree, "--all-auto", "--set", "tier=auto") == 0
    text = (tree / "trueup.toml").read_text(encoding="utf-8")
    before = [line for line in _ALL_DEFAULTS.splitlines() if "run_date" not in line]
    after = text.splitlines()
    assert [line for line in before if line not in after] == []
    assert f'run_date = "{DAY_ONE.isoformat()}"' in after

    (tree / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    assert _apply(tree, "--all-auto", "--set", "tier=auto") == 0
    assert 'tier = "auto"' in (tree / "trueup.toml").read_text(encoding="utf-8")


def test_set_profile_is_written_and_a_bad_name_is_refused(tmp_path: Path) -> None:
    """`--set profile=<name>` writes the key; a name outside the D14.1 shape is exit 2 with no file changed.

    arch: D14.3, D14.19
    """
    tree = _messy(tmp_path)
    (tree / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    before = _snapshot(tree)
    assert _apply(tree, "--all-auto", "--set", "profile=Bad_Name") == 2
    assert _snapshot(tree) == before
    assert _apply(tree, "--all-auto", "--set", "profile=minimal") == 0
    target = config.load_target(tree)
    assert target is not None and target.profile == "minimal"


def test_stamp_run_date_renders_the_target_layer(tmp_path: Path) -> None:
    """With no `run_date` line, the stamp renders the target layer: a default key the file set stays, and a banned path stays as written.

    arch: D14.3, D14.19
    """
    (tmp_path / "words.txt").write_text("widget\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "auto"\n\n[prose]\nbanned = "words.txt"\n',
        encoding="utf-8",
    )
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    text = (tmp_path / "trueup.toml").read_text(encoding="utf-8")
    assert f'run_date = "{DAY_ONE.isoformat()}"' in text
    assert 'tier = "auto"' in text
    assert 'banned = "words.txt"' in text
    assert str(tmp_path) not in text


def _python_files(root: Path) -> None:
    """Add Python files enough to make Python a present language (60 code lines).

    Args:
        root: The target root.
    """
    (root / "pkg.py").write_text(
        "".join(f"value_{index} = {index}\n" for index in range(60)), encoding="utf-8"
    )


def test_stamp_run_date_writes_nothing_without_a_target_file(tmp_path: Path) -> None:
    """With no `trueup.toml`, the run-date stamp creates no file, also under the user default file.

    arch: D14.3, D14.19
    """
    user_default = config.config_home() / "trueup.toml"
    user_default.parent.mkdir(parents=True)
    user_default.write_text('docs = "readme"\n', encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    assert config.load(root) is not None
    ctx = apply_mod._Context(root=root, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    assert not (root / "trueup.toml").exists()
    assert ctx.changed == []


def test_apply_under_the_user_default_file_creates_no_target_file(
    tmp_path: Path,
) -> None:
    """Under the user default file, `apply --all-auto` writes the other fixes but no `trueup.toml`.

    The check has no `config:trueup.toml` row. The `config:languages.python`
    row is info and not in the plan, so it does not create the target file:
    that file would stop the user default file (I-44).

    arch: D14.3, D14.8, D14.19
    """
    user_default = config.config_home() / "trueup.toml"
    user_default.parent.mkdir(parents=True)
    user_default.write_text('docs = "readme"\n', encoding="utf-8")
    tree = _messy(tmp_path)
    _python_files(tree)
    run = report.collect(tree)
    ids = {finding.id for finding in run.findings}
    assert "config:trueup.toml" not in ids
    rows = [f for f in run.findings if f.id == "config:languages.python"]
    assert [(f.severity, f.auto) for f in rows] == [("info", False)]
    assert "config:languages.python" not in {finding.id for finding in run.plan}
    assert _apply(tree, "--all-auto") == 0
    assert not (tree / "trueup.toml").exists()
    assert ".scratch/" in (tree / ".gitignore").read_text(encoding="utf-8")
    assert config.load(tree).docs == "readme"


_MINE_PROFILE = """stale_days = 30
docs = "readme"

[prose]
extra = ["gizmo"]

[layout]
front_matter = false
"""


def test_apply_refuses_a_set_profile_that_resolves_to_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`apply --set profile=nope` exits 2 before a write and names both search paths; a later `check` still loads.

    arch: D14.1, D14.3
    """
    tree = _messy(tmp_path)
    _python_files(tree)
    (tree / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    before = _snapshot(tree)
    capsys.readouterr()
    assert _apply(tree, "--all-auto", "--set", "profile=nope") == 2
    out = capsys.readouterr().out
    assert "--set profile: profile 'nope' is not found" in out
    assert str(config.config_home() / "profiles" / "nope.toml") in out
    assert str(config._PROFILE_DIR) in out
    assert _snapshot(tree) == before
    assert config.load(tree) is not None


def test_apply_leaves_no_profile_key_in_the_target_file(tmp_path: Path) -> None:
    """Scenario (a), apply half: with `profile = "mine"` and `mine.toml` present, `apply --all-auto` writes no key of `mine.toml` into the target file.

    The effective config still takes the profile values (I-45).

    arch: D14.3, D14.19, D14.15, I-45
    """
    profiles = config.config_home() / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "mine.toml").write_text(_MINE_PROFILE, encoding="utf-8")
    tree = _messy(tmp_path)
    _python_files(tree)
    (tree / "trueup.toml").write_text(
        'version = 1\nprofile = "mine"\n', encoding="utf-8"
    )
    assert _apply(tree, "--all-auto") == 0
    text = (tree / "trueup.toml").read_text(encoding="utf-8")
    for key in ("stale_days", "docs", "gizmo", "front_matter", "[prose]", "[layout]"):
        assert key not in text, key
    assert 'profile = "mine"' in text
    assert 'python = "clean"' in text
    assert f'run_date = "{DAY_ONE.isoformat()}"' in text
    effective = config.load(tree)
    assert (effective.stale_days, effective.docs) == (30, "readme")
    assert effective.prose_extra == ("gizmo",)
    assert effective.layout_front_matter is False


# -- D15.27: the stamp edits text, writes stay in the root -----------------


def test_stamp_keeps_comments_and_uncommitted_text_and_inserts_before_the_first_table(
    tmp_path: Path,
) -> None:
    """With no `run_date` line, the stamp inserts one line before the first table; every other byte stays.

    arch: D15.27
    """
    before = (
        "# my comment about the profile\n"
        "version = 1\n"
        'profile = "minimal"   # the rules\n'
        "ignore = [\n"
        '  "a/**",\n'
        "]\n"
        "\n"
        "# the prose table\n"
        "[prose]\n"
        'banned = "builtin"\n'
        "# UNCOMMITTED note\n"
    )
    (tmp_path / "trueup.toml").write_text(before, encoding="utf-8")
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    after = (tmp_path / "trueup.toml").read_text(encoding="utf-8")
    assert after == before.replace(
        "]\n\n# the prose table\n",
        f']\nrun_date = "{DAY_ONE.isoformat()}"\n\n# the prose table\n',
    )
    assert config.load_target(tmp_path).run_date == DAY_ONE.isoformat()


def test_stamp_replaces_only_the_top_level_run_date_line(tmp_path: Path) -> None:
    """A top-level `run_date` line changes in place; a file with no table gets the line appended.

    arch: D15.27
    """
    before = 'version = 1\nrun_date = "2020-01-01"   # last change\n# note\n'
    (tmp_path / "trueup.toml").write_text(before, encoding="utf-8")
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    assert (tmp_path / "trueup.toml").read_text(encoding="utf-8") == (
        f'version = 1\nrun_date = "{DAY_ONE.isoformat()}"   # last change\n# note\n'
    )
    (tmp_path / "trueup.toml").write_text("version = 1\n# note", encoding="utf-8")
    apply_mod._stamp_run_date(ctx, DAY_TWO)
    assert (tmp_path / "trueup.toml").read_text(encoding="utf-8") == (
        f'version = 1\n# note\nrun_date = "{DAY_TWO.isoformat()}"\n'
    )


@pytest.mark.parametrize(
    "line",
    [
        '  run_date = "2020-01-01"',
        '"run_date" = "2020-01-01"',
        "'run_date' = '2020-01-01'  # last change",
        '\trun_date="2020-01-01"',
    ],
)
def test_stamp_changes_an_indented_or_quoted_run_date_key_in_place(
    tmp_path: Path, line: str
) -> None:
    """An indented or quoted top-level `run_date` key changes in place; the file keeps one `run_date` and stays valid TOML.

    arch: D15.27
    """
    before = f'version = 1\n{line}\n\n[prose]\nbanned = "builtin"\n'
    (tmp_path / "trueup.toml").write_text(before, encoding="utf-8")
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    after = (tmp_path / "trueup.toml").read_text(encoding="utf-8")
    assert after.count("run_date") == 1
    assert after.replace(DAY_ONE.isoformat(), "2020-01-01").replace(
        "'2020-01-01'", '"2020-01-01"'
    ) == before.replace("'2020-01-01'", '"2020-01-01"')
    assert tomllib.loads(after)["run_date"] == DAY_ONE.isoformat()


def test_stamp_renders_the_file_when_the_line_edit_would_break_it(
    tmp_path: Path,
) -> None:
    """A `run_date` value that the line edit cannot replace (a multi-line string) makes the stamp render the target layer, so the file stays valid.

    arch: D15.27
    """
    before = 'version = 1\nrun_date = """\n2020-01-01"""\ntier = "auto"\n'
    (tmp_path / "trueup.toml").write_text(before, encoding="utf-8")
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    after = (tmp_path / "trueup.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(after)
    assert parsed["run_date"] == DAY_ONE.isoformat()
    assert parsed["tier"] == "auto"
    assert config.load_target(tmp_path).run_date == DAY_ONE.isoformat()


def test_stamp_keeps_crlf_line_endings(tmp_path: Path) -> None:
    """A CRLF `trueup.toml` keeps CRLF on every line, for an in-place stamp and for an inserted line.

    arch: D15.27
    """
    path = tmp_path / "trueup.toml"
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    path.write_bytes(b'version = 1\r\nrun_date = "2020-01-01"\r\n# note\r\n')
    apply_mod._stamp_run_date(ctx, DAY_ONE)
    assert path.read_bytes() == (
        f'version = 1\r\nrun_date = "{DAY_ONE.isoformat()}"\r\n# note\r\n'.encode()
    )
    path.write_bytes(b'version = 1\r\n\r\n[prose]\r\nbanned = "builtin"\r\n')
    apply_mod._stamp_run_date(ctx, DAY_TWO)
    assert (
        path.read_bytes()
        == (
            f'version = 1\r\nrun_date = "{DAY_TWO.isoformat()}"\r\n\r\n[prose]\r\n'
            'banned = "builtin"\r\n'
        ).encode()
    )


def test_write_through_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """A last component or a parent that resolves outside the root is refused; the outside file stays.

    arch: D15.27, I-51
    """
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "shared"
    outside.mkdir()
    (outside / "x").write_text("outside\n", encoding="utf-8")
    (root / ".gitignore").symlink_to(outside / "x")
    (root / "docs").symlink_to(outside)
    ctx = apply_mod._Context(root=root, protect=(), rendered={})
    for rel in (".gitignore", "docs/page.md", "../escape/x.md"):
        with pytest.raises(
            apply_mod.WriteRefused,
            match=re.escape(f"refused: {rel} resolves outside the repository"),
        ):
            apply_mod._write_file(ctx, rel, "new\n")
    with pytest.raises(apply_mod.WriteRefused):
        apply_mod._append_lines(ctx, ".gitignore", [".scratch/"])
    assert (outside / "x").read_text(encoding="utf-8") == "outside\n"
    assert not (outside / "page.md").exists()
    assert not (tmp_path / "escape").exists()
    assert ctx.changed == []


def test_symlink_inside_the_root_is_refused_as_a_last_component(tmp_path: Path) -> None:
    """A last component that is a symlink is refused, also when it points inside the root.

    arch: D15.27, I-51
    """
    (tmp_path / "real.txt").write_text("real\n", encoding="utf-8")
    (tmp_path / ".gitattributes").symlink_to(tmp_path / "real.txt")
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    with pytest.raises(apply_mod.WriteRefused):
        apply_mod._write_file(ctx, ".gitattributes", "x\n")
    apply_mod._write_file(ctx, "sub/new.txt", "new\n")
    assert (tmp_path / "sub" / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "real.txt").read_text(encoding="utf-8") == "real\n"


def test_apply_gitignore_through_a_symlink_fails_and_writes_nothing_outside(
    tmp_path: Path,
) -> None:
    """`apply --ids gitignore:.gitignore` on a tracked symlink out of the root exits 1 and leaves the outside file.

    arch: D15.27
    """
    root = tmp_path / "repo"
    root.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "x").write_text("keep\n", encoding="utf-8")
    _git(root, "init", "-q")
    (root / ".gitignore").symlink_to("../shared/x")
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    run = report.collect(root)
    assert "gitignore:.gitignore" in {f.id for f in run.plan if f.auto}
    assert _apply(root, "--ids", "gitignore:.gitignore") == 1
    assert (shared / "x").read_text(encoding="utf-8") == "keep\n"


def test_render_says_comments_do_not_survive_a_config_write() -> None:
    """The rendered `trueup.toml` says that a config write drops comments.

    arch: D15.27
    """
    text = config.render(config.Config())
    assert "# comments do not survive a config write; trueup writes this file\n" in text


def test_apply_write_clears_the_config_cache(tmp_path: Path) -> None:
    """After an apply write of the same size and time stamp, the next load reads the new file.

    arch: D15.29
    """
    path = tmp_path / "trueup.toml"
    path.write_text('version = 1\ntier = "T1"\n', encoding="utf-8")
    assert config.load(tmp_path).tier == "T1"
    stamp = path.stat()
    ctx = apply_mod._Context(root=tmp_path, protect=(), rendered={})
    apply_mod._write_file(ctx, "trueup.toml", 'version = 1\ntier = "T2"\n')
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert config.load(tmp_path).tier == "T2"
