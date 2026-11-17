"""Tests of `trueup lint`: selection, rendered configs, commands, the eslint package directory and `--install`."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from trueup import cli, config, lint, managed, rulesets
from trueup.config import Config

_REPO_ESLINT_PACKAGES = (
    Path(__file__).resolve().parent.parent / "lint" / "ts" / "node_modules"
)
"""The eslint packages of this repository's own D1.5 config, used by the real eslint test."""


class _Recorder:
    """Stand in for `lint._execute`: record each command and give a fixed exit code."""

    def __init__(
        self,
        code: Callable[[list[str]], int] | None = None,
        look: Callable[[list[str]], object] | None = None,
    ) -> None:
        """Make a recorder.

        Args:
            code: Gives the exit code of one command; `None` gives 0.
            look: Called with each command while it "runs"; its result is
                kept in `seen`.
        """
        self.calls: list[list[str]] = []
        self.cwds: list[Path] = []
        self.cfgdirs: list[Path | None] = []
        self.seen: list[object] = []
        self._code = code
        self._look = look

    def __call__(
        self, argv: Sequence[str], cwd: Path, *, cfgdir: Path | None = None
    ) -> int:
        """Record one command.

        Args:
            argv: The command line.
            cwd: The working directory.
            cfgdir: The directory of the rendered configs, as `lint._execute`
                takes it.

        Returns:
            The exit code that `code` gives, or 0.
        """
        command = list(argv)
        self.calls.append(command)
        self.cwds.append(Path(cwd))
        self.cfgdirs.append(cfgdir)
        if self._look is not None:
            self.seen.append(self._look(command))
        return 0 if self._code is None else self._code(command)

    def first(self, tool: str, *rest: str) -> list[str]:
        """Give the first recorded command that starts with the given tokens.

        Args:
            tool: The first token.
            *rest: The tokens after it.

        Returns:
            The command line.
        """
        start = [tool, *rest]
        for command in self.calls:
            if command[: len(start)] == start:
                return command
        raise AssertionError(f"no command starts with {start}: {self.calls}")

    def has(self, tool: str, *rest: str) -> bool:
        """Say whether a recorded command starts with the given tokens.

        Args:
            tool: The first token.
            *rest: The tokens after it.

        Returns:
            True when one command starts with them.
        """
        start = [tool, *rest]
        return any(command[: len(start)] == start for command in self.calls)


def _git(root: Path, *args: str) -> None:
    """Run one git command in `root`, with signing off.

    Args:
        root: The repository.
        *args: The git arguments.
    """
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repo(root: Path, files: dict[str, str], toml: str | None) -> Path:
    """Make a git repository with the given files, untracked.

    Args:
        root: The directory to make.
        files: Repo path to text.
        toml: The text of `trueup.toml`, or `None` for no file.

    Returns:
        The resolved root.
    """
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    for path, text in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
    if toml is not None:
        (root / "trueup.toml").write_text(toml, encoding="utf-8")
    return root.resolve()


def _toml(languages: dict[str, str], extra: str = "") -> str:
    """Give a `trueup.toml` text with a `[languages]` table.

    Args:
        languages: Language to mode.
        extra: More TOML text, put before the table.

    Returns:
        The file text.
    """
    lines = ["version = 1", extra, "[languages]"]
    lines += [f'{language} = "{mode}"' for language, mode in languages.items()]
    return "\n".join(lines) + "\n"


def _snapshot(root: Path) -> dict[str, bytes]:
    """Read every file under `root` except `.git`.

    Args:
        root: The tree.

    Returns:
        Repo path to bytes.
    """
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


@pytest.fixture
def tools_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every tool count as present, so the tests do not depend on the host."""
    monkeypatch.setattr(lint, "_tool_found", lambda root, tool: True)


def test_run_takes_the_root_the_paths_and_the_two_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """`paths` selects the files, `install` runs no hook, and the switches are keyword only.

    The body asserts what the arguments do, not the signature (D15.38).

    arch: D14.6, D14.7, D14.20, D14.22, D15.4, D15.38
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "b.py": "y = 2\n"},
        _toml({"python": "clean"}),
    )
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, ["b.py"], changed=False, install=False) == 0
    assert recorder.first("ruff", "check")[4:] == ["b.py"]
    recorder.calls.clear()
    assert lint.run(root, [], changed=False, install=True) == 0
    assert recorder.calls == []
    with pytest.raises(TypeError):
        lint.run(root, [], False, False)  # type: ignore[misc]  # reason: the switches are keyword only


def test_no_config_and_no_user_default_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target with no `trueup.toml` and no user default file exits 2 with the D14.6 message.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, None)
    assert lint.run(root, [], changed=False, install=False) == 2
    assert (
        "trueup lint: no trueup.toml and no user default file; run trueup check"
        in capsys.readouterr().err
    )


def test_path_and_changed_together_exit_2(tmp_path: Path) -> None:
    """`PATH` and `--changed` together are a usage error, through `run` and through the CLI.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "clean"}))
    assert lint.run(root, ["a.py"], changed=True, install=False) == 2
    assert cli.main(["lint", "--root", str(root), "--changed", "a.py"]) == 2


def test_a_config_error_exits_2(tmp_path: Path) -> None:
    """A `trueup.toml` that fails validation exits 2, not a traceback.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, 'version = 1\ntier = "T9"\n')
    assert lint.run(root, [], changed=False, install=False) == 2


def test_cli_passes_the_arguments_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`trueup lint` gives `run` the resolved root, the paths and both switches; `--profile` sets the variable.

    The variable holds the flag value during the run only; `main`
    restores it after the run (D15.6).

    arch: D14.6, D14.7, D14.20, D14.22, D15.6, D15.4
    """
    got: list[tuple[Path, list[str], bool, bool]] = []
    seen: list[str | None] = []

    skips: list[bool] = []

    def fake_run(
        root: Path,
        paths: Sequence[str],
        *,
        changed: bool,
        install: bool,
        skip_missing: bool = False,
    ) -> int:
        got.append((root, list(paths), changed, install))
        skips.append(skip_missing)
        seen.append(os.environ.get("TRUEUP_PROFILE"))
        return 7

    monkeypatch.setattr(lint, "run", fake_run)
    root = tmp_path / "repo"
    root.mkdir()
    code = cli.main(
        ["lint", "--root", str(root), "--profile", "minimal", "a.py", "pkg"]
    )
    assert code == 7
    assert got == [(root.resolve(), ["a.py", "pkg"], False, False)]
    assert seen == ["minimal"]
    assert "TRUEUP_PROFILE" not in os.environ
    assert cli.main(["lint", "--root", str(root), "--install"]) == 7
    assert got[-1] == (root.resolve(), [], False, True)
    assert seen[-1] is None
    assert skips == [False, False]
    assert cli.main(["lint", "--root", str(root), "--skip-missing"]) == 7
    assert skips[-1] is True


def test_lint_writes_nothing_under_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """A full run with several rule sets, Vale and eslint leaves the target tree byte for byte as it was (I-47).

    The rendered configs live in a temporary directory that is gone after
    the run, and the eslint run config is removed from the package
    directory.

    arch: D14.6, D14.7, D14.20, D14.22, I-47
    """
    root = _repo(
        tmp_path / "repo",
        {
            "a.py": "x = 1\n",
            "web/a.ts": "export const y = 1;\n",
            "src/a.php": "<?php\n",
            "run.sh": "echo hi\n",
            "README.md": "# Repo\n",
        },
        _toml(
            {
                "python": "strict",
                "typescript": "clean",
                "php": "clean",
                "shell": "strict",
            },
            'docs = "full"',
        ),
    )
    packages = managed.eslint_dir(config.load(root) or Config())
    assert packages is not None
    (packages / "node_modules").mkdir(parents=True)
    before = _snapshot(root)
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    assert _snapshot(root) == before
    cfgdir = Path(recorder.first("ruff", "check")[3]).parent.parent
    assert cfgdir.name.startswith("trueup-lint-")
    assert not cfgdir.exists()
    assert not cfgdir.is_relative_to(root)
    assert not (packages / rulesets.ESLINT_RUN_CONFIG).exists()
    assert set(recorder.cwds) == {root}


def test_paths_select_files_and_directories_and_drop_ignored_ones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tools_found: None,
) -> None:
    """A file path selects that file, a directory the surveyed files under it, and an ignored path nothing, in silence.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {
            "a.py": "x = 1\n",
            "pkg/b.py": "x = 1\n",
            "pkg/c.py": "x = 1\n",
            "gen/d.py": "x = 1\n",
            "other.py": "x = 1\n",
        },
        _toml({"python": "clean"}, 'ignore = ["gen/**"]'),
    )
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    code = lint.run(
        root,
        ["pkg", str(root / "a.py"), "gen/d.py", "missing.py"],
        changed=False,
        install=False,
    )
    assert code == 0
    command = recorder.first("ruff", "check")
    assert command[4:] == ["pkg/b.py", "pkg/c.py", "a.py"]
    err = capsys.readouterr().err
    assert "gen/d.py" not in err
    assert "trueup lint: missing.py is not a surveyed file; skipped" in err


def test_changed_lints_the_working_set_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """`--changed` lints the dirty tracked files and the untracked ones, nothing else.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "b.py": "x = 1\n"},
        _toml({"python": "clean"}),
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")
    (root / "b.py").write_text("x = 2\n", encoding="utf-8")
    (root / "c.py").write_text("x = 3\n", encoding="utf-8")
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=True, install=False) == 0
    assert recorder.first("ruff", "check")[4:] == ["b.py", "c.py"]


def test_commands_carry_the_config_rendered_into_the_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """Each hook entry gets `{cfg}` filled with the run's directory, which holds the rendered template while the tool runs.

    The ruff format hook keeps its `exclude`, so the root `ref_check.py`
    is not passed to it.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "ref_check.py": "x = 1\n"},
        _toml({"python": "clean"}),
    )

    def config_text(command: list[str]) -> str | None:
        if "--config" not in command:
            return None
        path = Path(command[command.index("--config") + 1])
        return path.read_text(encoding="utf-8") if path.is_file() else None

    recorder = _Recorder(look=config_text)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    check = recorder.first("ruff", "check")
    assert check[:3] == ["ruff", "check", "--config"]
    assert check[3].endswith("/python/ruff.toml")
    assert check[4:] == ["a.py", "ref_check.py"]
    template = rulesets.template_path("rules/python/ruff-clean.toml").read_text(
        encoding="utf-8"
    )
    assert recorder.seen[recorder.calls.index(check)] == template
    assert recorder.first("ruff", "format")[-1:] == ["a.py"]


def test_a_whole_tree_hook_runs_only_with_a_file_of_its_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """A `pass_filenames=False` hook runs on the full survey, or when the selection holds a file of its language.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "notes.txt": "hi\n"},
        _toml({"python": "strict"}),
    )
    for paths, expected in ((["notes.txt"], False), (["a.py"], True), ([], True)):
        recorder = _Recorder()
        monkeypatch.setattr(lint, "_execute", recorder)
        assert lint.run(root, paths, changed=False, install=False) == 0
        assert recorder.has("vulture") is expected, paths
        if expected:
            assert recorder.first("vulture") == [
                "vulture",
                "--min-confidence",
                "80",
                ".",
            ]


def test_a_missing_tool_exits_2_and_skip_missing_restores_the_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tool that is not installed prints one line and the summary, and the run exits 2; `--skip-missing` gives 0.

    The other tools still run in both cases.

    arch: D15.4, D14.6
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "run.sh": "echo hi\n"},
        _toml({"python": "clean", "shell": "clean"}),
    )
    monkeypatch.setattr(lint, "_tool_found", lambda root, tool: tool != "ruff")
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 2
    err = capsys.readouterr().err
    line = "trueup lint: ruff is not installed; python clean did not run"
    assert err.count(line) == 1
    assert (
        "trueup lint: 1 tool(s) missing: ruff; install them, or pass --skip-missing"
        in err
    )
    assert not recorder.has("ruff")
    assert recorder.first("shellcheck") == ["shellcheck", "run.sh"]

    assert lint.run(root, [], changed=False, install=False, skip_missing=True) == 0
    err = capsys.readouterr().err
    assert line in err
    assert "tool(s) missing" not in err
    assert cli.main(["lint", "--root", str(root), "--skip-missing"]) == 0


def test_a_missing_tool_and_a_failed_tool_give_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When one tool is missing and another fails, 2 wins; with `--skip-missing` the failure gives 1.

    arch: D15.4
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "run.sh": "echo hi\n"},
        _toml({"python": "clean", "shell": "clean"}),
    )
    monkeypatch.setattr(lint, "_tool_found", lambda root, tool: tool != "ruff")
    monkeypatch.setattr(
        lint,
        "_execute",
        _Recorder(code=lambda command: 1 if command[0] == "shellcheck" else 0),
    )
    assert lint.run(root, [], changed=False, install=False) == 2
    assert lint.run(root, [], changed=False, install=False, skip_missing=True) == 1


def test_a_failing_tool_gives_exit_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tools_found: None,
) -> None:
    """One tool that exits non-zero makes the run exit 1; the other tools still run.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "run.sh": "echo hi\n"},
        _toml({"python": "clean", "shell": "clean"}),
    )
    recorder = _Recorder(
        code=lambda command: 1 if command[:2] == ["ruff", "check"] else 0
    )
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 1
    assert recorder.has("shellcheck")
    assert "trueup lint: ruff check failed (exit 1)" in capsys.readouterr().err


def test_eslint_without_its_packages_is_a_missing_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tools_found: None,
) -> None:
    """With no `node_modules` in the eslint package directory, the run exits 2 with the install line; `--skip-missing` gives 0.

    arch: D14.6, D14.7, D14.20, D14.22, D15.4
    """
    root = _repo(
        tmp_path / "repo",
        {"a.ts": "export const y = 1;\n"},
        _toml({"typescript": "clean"}),
    )
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 2
    err = capsys.readouterr().err
    assert (
        "trueup lint: eslint packages are not installed; run trueup lint --install"
        in err
    )
    assert "1 tool(s) missing: eslint packages;" in err
    assert not recorder.has("npx")
    assert lint.run(root, [], changed=False, install=False, skip_missing=True) == 0


def test_eslint_runs_from_the_package_directory_with_its_run_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """The eslint hook runs through `npx --prefix <eslint_dir>` with the run config written beside `node_modules`, then removed.

    The suppressions file goes on the command line only when the target
    has it (D13.6, I-47).

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.ts": "export const y = 1;\n"},
        _toml(
            {"typescript": "clean"},
            '[[eslint.off]]\nrule = "no-console"\nreason = "a CLI"\n',
        ),
    )
    cfg = config.load(root)
    assert cfg is not None
    packages = managed.eslint_dir(cfg)
    assert packages is not None
    (packages / "node_modules").mkdir(parents=True)
    run_config = packages / rulesets.ESLINT_RUN_CONFIG

    def run_config_text(command: list[str]) -> str | None:
        return run_config.read_text(encoding="utf-8") if run_config.is_file() else None

    recorder = _Recorder(look=run_config_text)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    command = recorder.first("npx")
    assert command == [
        "npx",
        "--prefix",
        str(packages),
        "eslint",
        "--config",
        str(run_config),
        "--max-warnings",
        "0",
        "a.ts",
    ]
    text = recorder.seen[recorder.calls.index(command)]
    assert text == rulesets.render_eslint_config(
        "clean", "off", {"no-console": "a CLI"}
    )
    assert not run_config.exists()

    suppressions = root / cfg.eslint_suppressions
    suppressions.parent.mkdir(parents=True)
    suppressions.write_text("{}\n", encoding="utf-8")
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, ["a.ts"], changed=False, install=False) == 0
    assert recorder.first("npx")[-3:] == [
        "--suppressions-location",
        cfg.eslint_suppressions,
        "a.ts",
    ]


def test_eslint_dir_is_under_the_cache_and_keyed_by_the_packages(
    tmp_path: Path,
) -> None:
    """The package directory is `cache_home()/eslint/<sha256 of package.json, 16 digits>`; none when TypeScript and Vue are off.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    clean = Config(languages={"typescript": "clean"})
    package = rulesets.render_eslint_package("clean", "off")
    expected = (
        config.cache_home()
        / "eslint"
        / hashlib.sha256(package.encode("utf-8")).hexdigest()[:16]
    )
    assert managed.eslint_dir(clean) == expected
    assert expected.is_relative_to(tmp_path / "xdg-cache" / "trueup")
    vue = managed.eslint_dir(Config(languages={"typescript": "clean", "vue": "clean"}))
    assert vue is not None and vue != expected
    assert managed.eslint_dir(Config(languages={"python": "strict"})) is None


def test_install_writes_the_package_json_and_runs_npm_in_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--install` writes package.json into the eslint package directory, installs jscpd for a strict language, and exits with npm's code; the target is untouched.

    `npm install` is the one network path of `trueup lint` (I-28). The test
    replaces the command runner, so no network is opened. Each install
    runs, and the first non-zero code is the exit code.

    arch: D14.6, D14.7, D14.20, D14.22, D15.5
    """
    root = _repo(
        tmp_path / "repo",
        {"a.ts": "export const y = 1;\n", "b.vue": "<template/>\n"},
        _toml({"typescript": "strict", "vue": "clean"}),
    )
    before = _snapshot(root)
    recorder = _Recorder(code=lambda command: 3)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=True) == 3
    packages = managed.eslint_dir(
        Config(languages={"typescript": "strict", "vue": "clean"})
    )
    assert packages is not None
    assert recorder.calls == [
        ["npm", "install", "--prefix", str(packages), "--no-audit", "--no-fund"],
        [
            "npm",
            "install",
            "--prefix",
            str(lint.tools_dir()),
            "--no-audit",
            "--no-fund",
            "jscpd@4.3.0",
        ],
    ]
    assert (packages / "package.json").read_text(
        encoding="utf-8"
    ) == rulesets.render_eslint_package("strict", "clean")
    assert _snapshot(root) == before


def test_install_with_typescript_and_vue_off_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--install` with no TypeScript or Vue mode on runs no command and exits 0.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "clean"}))
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=True) == 0
    assert recorder.calls == []


def test_vale_banned_style_follows_the_list_in_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """The rendered `Banned.yml` equals the template for the built-in list, and is absent when the list is empty (I-25).

    arch: D14.6, D14.7, D14.20, D14.22
    """
    from trueup import docrules

    template = rulesets.template_path("vale/styles/Trueup/Banned.yml").read_text(
        encoding="utf-8"
    )
    assert (
        lint._render_banned_style(template, docrules._load_banned_words()) == template
    )
    extra = lint._render_banned_style(template, ("synergy", "foo => fo+"))
    assert extra.endswith('tokens:\n  - "synergy"\n  - "fo+"\n')

    root = _repo(
        tmp_path / "repo",
        {"README.md": "# Repo\n"},
        _toml({}, 'docs = "full"\n[prose]\nbanned = "off"'),
    )

    def styles(command: list[str]) -> list[str]:
        directory = Path(command[2]).parent / "styles" / "Trueup"
        return sorted(path.name for path in directory.iterdir())

    recorder = _Recorder(
        look=lambda command: styles(command) if command[0] == "vale" else None
    )
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    command = recorder.first("vale")
    assert command[1] == "--config"
    assert command[-1] == "README.md"
    seen = recorder.seen[recorder.calls.index(command)]
    assert isinstance(seen, list)
    assert "Banned.yml" not in seen
    assert "Latin.yml" in seen


def test_vale_hook_leaves_out_the_kept_prose_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """The Vale hook does not see a page whose `prose:<path>` id is kept in `[[keep]]`; other keep ids change nothing.

    So `lint` and `check` decline the same pages (D5.6). A selection of
    kept pages only gives no Vale run.

    arch: D14.6, D14.17
    """
    keep = "".join(
        f'[[keep]]\nid = "{finding_id}"\nreason = "a source document"\n'
        for finding_id in (
            "prose:docs/a.md",
            "prose:docs/b-notes.md",
            "secret-file:.env",
        )
    )
    root = _repo(
        tmp_path / "repo",
        {
            "README.md": "# Repo\n",
            "docs/a.md": "# A\n",
            "docs/b-notes.md": "# B\n",
            "docs/c.md": "# C\n",
        },
        _toml({}, f'docs = "full"\n{keep}'),
    )
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    assert recorder.first("vale")[3:] == ["README.md", "docs/c.md"]

    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, ["docs/a.md"], changed=False, install=False) == 0
    assert not recorder.has("vale")


def test_copy_mode_ruff_format_leaves_out_a_custom_checker_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """In copy mode the ruff format hook does not see the checker copy at `[refs] path`; ruff check still sees it (I-26).

    arch: D14.6, D14.17
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "tools/checker.py": "x = 1\n"},
        _toml({"python": "clean"}, '[refs]\nmode = "copy"\npath = "tools/checker.py"'),
    )
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    assert recorder.first("ruff", "format")[5:] == ["a.py"]
    assert recorder.first("ruff", "check")[4:] == ["a.py", "tools/checker.py"]


def test_hooks_get_the_ruff_cache_in_the_temporary_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    tools_found: None,
) -> None:
    """Each hook command gets the run's `cfgdir`, and `_execute` sets `RUFF_CACHE_DIR` under it (I-47).

    A cache that a tool writes by itself is the tool's own; trueup moves
    the ruff cache out of the root.

    arch: D14.6, D14.17
    """
    execute = lint._execute
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "clean"}))
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    check = recorder.first("ruff", "check")
    cfgdir = recorder.cfgdirs[recorder.calls.index(check)]
    assert cfgdir is not None
    assert Path(check[3]).parent.parent == cfgdir

    target = tmp_path / "cfg"
    probe = [sys.executable, "-c", "import os; print(os.environ['RUFF_CACHE_DIR'])"]
    capfd.readouterr()
    assert execute(probe, tmp_path, cfgdir=target) == 0
    assert capfd.readouterr().out.strip() == str(target / "ruff-cache")


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not on the path")
def test_real_ruff_writes_no_cache_under_the_root(tmp_path: Path) -> None:
    """A real lint run with ruff leaves no `.ruff_cache` under the root (I-47).

    arch: D14.6, D14.17, I-47
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "clean"}))
    lint.run(root, [], changed=False, install=False)
    assert not (root / ".ruff_cache").exists()


def test_php_templates_get_the_absolute_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """The `__TRUEUP_ROOT__` token of a template is replaced with the absolute root (D14.22 item 13).

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(tmp_path / "repo", {"src/a.php": "<?php\n"}, _toml({"php": "clean"}))

    def neon(command: list[str]) -> str | None:
        if command[:2] != ["vendor/bin/phpstan", "analyse"]:
            return None
        return Path(command[3]).read_text(encoding="utf-8")

    recorder = _Recorder(look=neon)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    command = recorder.first("vendor/bin/phpstan", "analyse")
    text = recorder.seen[recorder.calls.index(command)]
    assert isinstance(text, str)
    assert rulesets.ROOT_TOKEN not in text
    assert str(root) in text


def test_checker_runs_with_the_rendered_config_in_global_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """In global mode the bundled checker runs with `--config <cfgdir>/ref_check.toml`; a selection of no text or source file skips it.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "data.bin": "x\n"},
        _toml({"python": "clean"}),
    )

    def config_exists(command: list[str]) -> bool:
        return (
            "--config" in command
            and Path(command[command.index("--config") + 1]).is_file()
        )

    recorder = _Recorder(look=config_exists)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    command = recorder.first(sys.executable)
    assert command[1] == str(managed.BUNDLED_REF_CHECK)
    assert command[2:4] == ["--root", str(root)]
    assert command[4] == "--config"
    assert command[5].endswith("/ref_check.toml")
    assert recorder.seen[recorder.calls.index(command)] is True

    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, ["data.bin"], changed=False, install=False) == 0
    assert not recorder.has(sys.executable)


@pytest.mark.skipif(
    not _REPO_ESLINT_PACKAGES.is_dir() or shutil.which("npx") is None,
    reason="the eslint packages of lint/ts are not installed, or npx is absent",
)
def test_real_eslint_fails_a_known_bad_file(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """The real eslint, with its config outside the root and `cwd` the root, fails a known-bad file and passes a good one (D14.22 item 11).

    The eslint package directory under the test cache links to this
    repository's own `lint/ts/node_modules`, so no network is opened.

    arch: D14.6, D14.7, D14.20, D14.22
    """
    root = _repo(
        tmp_path / "repo",
        {
            "bad.ts": "// @ts-ignore\nexport const x: number = 1;\n",
            "good.ts": "/** Good. */\nexport const y = 2;\n",
        },
        _toml({"typescript": "clean"}),
    )
    packages = managed.eslint_dir(Config(languages={"typescript": "clean"}))
    assert packages is not None
    packages.mkdir(parents=True)
    (packages / "node_modules").symlink_to(_REPO_ESLINT_PACKAGES)
    assert lint.run(root, ["bad.ts"], changed=False, install=False) == 1
    assert "ban-ts-comment" in capfd.readouterr().out
    assert lint.run(root, ["good.ts"], changed=False, install=False) == 0
    assert not (packages / rulesets.ESLINT_RUN_CONFIG).exists()


def test_tools_dir_is_under_the_cache_and_keyed_by_the_manifest(tmp_path: Path) -> None:
    """The tools directory is `cache_home()/tools/<sha256 of the manifest, 16 digits>`.

    arch: D15.5
    """
    manifest = rulesets.render_tools_manifest()
    expected = (
        config.cache_home()
        / "tools"
        / hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:16]
    )
    assert lint.tools_dir() == expected
    assert expected.is_relative_to(tmp_path / "xdg-cache" / "trueup")
    assert json.loads(manifest) == {"jscpd": "4.3.0", "sqlfluff": "4.3.0"}


def test_jscpd_runs_from_the_tools_dir_on_the_root_with_no_npx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None
) -> None:
    """The duplication hook runs the local jscpd with the rendered config and `.`; no command is `npx jscpd` or `uvx`.

    arch: D15.4, D15.5
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "strict"}))
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    binary = str(lint.tools_dir() / "node_modules" / ".bin" / "jscpd")
    command = recorder.first(binary)
    assert command[1] == "--config"
    assert command[2].endswith("/jscpd.json")
    assert command[3:] == ["."]
    assert not recorder.has("npx", "jscpd")
    assert not recorder.has("uvx")
    assert not any(
        command[0] == "npx" and "jscpd" in command[1] for command in recorder.calls
    )


def test_a_missing_local_jscpd_is_a_missing_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no jscpd in the tools directory, a strict language gives exit 2 and names the path; `--skip-missing` gives 0.

    arch: D15.4, D15.5
    """
    root = _repo(tmp_path / "repo", {"a.py": "x = 1\n"}, _toml({"python": "strict"}))
    binary = str(lint.tools_dir() / "node_modules" / ".bin" / "jscpd")
    monkeypatch.setattr(lint, "_tool_found", lambda root, tool: tool != binary)
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 2
    err = capsys.readouterr().err
    assert f"trueup lint: {binary} is not installed; python strict did not run" in err
    assert f"1 tool(s) missing: {binary};" in err
    assert not recorder.has(binary)
    assert lint.run(root, [], changed=False, install=False, skip_missing=True) == 0


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_sqlfluff_runs_from_the_tools_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools_found: None, mode: str
) -> None:
    """The sqlfluff hook runs the local virtual environment, not `uvx`.

    arch: D15.5
    """
    root = _repo(tmp_path / "repo", {"q.sql": "SELECT 1;\n"}, _toml({"sql": mode}))
    recorder = _Recorder()
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=False) == 0
    command = recorder.first(str(lint.tools_dir() / "sqlfluff" / "bin" / "sqlfluff"))
    assert command[1] == "lint"
    assert command[-1] == "q.sql"
    assert not recorder.has("uvx")


def test_install_adds_jscpd_for_strict_and_sqlfluff_for_sql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--install` runs the npm install of jscpd for a strict language and the uv commands for SQL; the first failure sets the exit code.

    arch: D15.5
    """
    root = _repo(
        tmp_path / "repo",
        {"a.py": "x = 1\n", "q.sql": "SELECT 1;\n"},
        _toml({"python": "strict", "sql": "clean"}),
    )
    tools = lint.tools_dir()
    recorder = _Recorder(code=lambda command: 5 if command[0] == "uv" else 0)
    monkeypatch.setattr(lint, "_execute", recorder)
    assert lint.run(root, [], changed=False, install=True) == 5
    assert recorder.calls == [
        [
            "npm",
            "install",
            "--prefix",
            str(tools),
            "--no-audit",
            "--no-fund",
            "jscpd@4.3.0",
        ],
        ["uv", "venv", str(tools / "sqlfluff")],
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(tools / "sqlfluff"),
            "sqlfluff==4.3.0",
        ],
    ]


def _npm_online() -> bool:
    """Say whether the npm registry answers within 20 seconds.

    Returns:
        True when `npm ping` exits 0.
    """
    if shutil.which("npm") is None:
        return False
    try:
        return (
            subprocess.run(
                ["npm", "ping"], capture_output=True, timeout=20, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def test_real_jscpd_finds_two_identical_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two identical 300-line files under a strict language fail the duplication hook, with the jscpd that `lint --install` made.

    Only the jscpd hook runs for real; every other tool counts as found and
    exits 0. The test skips when the npm registry is not reachable.

    arch: D15.4, D15.5
    """
    if not _npm_online():
        pytest.skip("the npm registry is not reachable, so jscpd cannot be installed")
    body = "".join(
        f"def function_{number}(value):\n    return value + {number}\n\n\n"
        for number in range(100)
    )
    root = _repo(
        tmp_path / "repo",
        {"src/a.py": body, "src/b.py": body},
        _toml({"python": "strict"}),
    )
    real_execute = lint._execute
    assert lint.run(root, [], changed=False, install=True) == 0
    binary = str(lint.tools_dir() / "node_modules" / ".bin" / "jscpd")
    ran: list[int] = []

    def only_jscpd(
        argv: Sequence[str], cwd: Path, *, cfgdir: Path | None = None
    ) -> int:
        if argv[0] != binary:
            return 0
        code = real_execute(argv, cwd, cfgdir=cfgdir)
        ran.append(code)
        return code

    monkeypatch.setattr(lint, "_execute", only_jscpd)
    monkeypatch.setattr(
        lint, "_tool_found", lambda root, tool: tool != binary or Path(tool).is_file()
    )
    assert lint.run(root, [], changed=False, install=False) == 1
    assert ran == [1]
