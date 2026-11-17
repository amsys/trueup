"""Tests for `trueup.cli`: argument parsing, root resolution and error handling."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import trueup
from trueup import cli
from trueup.config import ConfigError

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`--help` prints usage and exits 0, with no subcommand required.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "trueup" in capsys.readouterr().out


def test_version_prints_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--version` prints `trueup <version>` and exits 0.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == f"trueup {trueup.__version__}\n"


def test_the_three_version_fields_agree() -> None:
    """`pyproject.toml`, `trueup.__version__` and `plugin.json` name one version.

    The package uses the Python form (`0.1.0a1`) and the plugin manifest
    the semver form (`0.1.0-alpha.1`).

    arch: D5.10
    """
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == trueup.__version__
    manifest = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    semver = re.sub(r"a(\d+)$", r"-alpha.\1", trueup.__version__)
    assert manifest["version"] == semver


def test_entry_point_help_runs_as_a_script() -> None:
    """`python3 trueup --help` runs the package as a directory (arch: D5.10)."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "trueup"), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "trueup" in result.stdout


def test_no_command_exits_two() -> None:
    """No subcommand at all is a usage error: exit 2.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_unknown_command_exits_two() -> None:
    """An unrecognised subcommand is a usage error: exit 2.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["frobnicate"])
    assert excinfo.value.code == 2


def test_apply_requires_ids_or_all_auto() -> None:
    """`apply` with neither `--ids` nor `--all-auto` is a usage error: exit 2.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["apply"])
    assert excinfo.value.code == 2


def test_apply_rejects_ids_and_all_auto_together() -> None:
    """`--ids` and `--all-auto` are mutually exclusive.

    arch: D5.11
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["apply", "--ids", "scratch:a.tmp", "--all-auto"])
    assert excinfo.value.code == 2


def test_check_rejects_changed_and_baseline_together(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`check --changed --baseline` is a usage error: exit 2 (arch: D6.17).

    arch: D6.17
    """
    exit_code = cli.main(["check", "--changed", "--baseline"])
    assert exit_code == 2
    assert "--changed" in capsys.readouterr().err


def test_check_rejects_changed_and_out_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check --changed --out DIR` is a usage error: exit 2, and nothing is written.

    arch: D6.17
    """
    out_dir = tmp_path / "out"
    exit_code = cli.main(["check", "--changed", "--out", str(out_dir)])
    assert exit_code == 2
    assert "--out" in capsys.readouterr().err
    assert not out_dir.exists()


def test_hook_rejects_unknown_event() -> None:
    """`hook` accepts only `session`, `guard`, `stop` or `interface`; argparse exits 2 on another name.

    arch: D5.11, D6.3, D6.15
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["hook", "bogus"])
    assert excinfo.value.code == 2


def test_main_turns_config_error_into_exit_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `ConfigError` raised by a handler becomes exit 2, not a traceback.

    arch: D5.11
    """

    def _boom(args: object) -> int:
        raise ConfigError("bad config")

    monkeypatch.setattr(cli, "_run_survey", _boom)
    exit_code = cli.main(["survey"])
    assert exit_code == 2
    assert "bad config" in capsys.readouterr().err


def test_resolve_root_with_explicit_root(tmp_path: Path) -> None:
    """An explicit `--root` resolves to an absolute path, unchanged otherwise.

    arch: D5.11
    """
    resolved = cli._resolve_root(tmp_path)
    assert resolved == tmp_path.resolve()


def test_resolve_root_defaults_to_git_top_level(tmp_path: Path) -> None:
    """With no `--root`, the git top level of the working directory is used.

    arch: D5.11
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch_cwd = Path.cwd()
    try:
        import os

        os.chdir(nested)
        resolved = cli._resolve_root(None)
    finally:
        import os

        os.chdir(monkeypatch_cwd)
    assert resolved == tmp_path.resolve()


def test_resolve_root_without_git_or_root_raises_config_error(tmp_path: Path) -> None:
    """Outside a git repository, with no `--root`, `_resolve_root` fails cleanly.

    arch: D5.11
    """
    import os

    outside = Path.cwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(ConfigError):
            cli._resolve_root(None)
    finally:
        os.chdir(outside)


def test_baseline_writes_the_file_and_prints_a_summary_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup baseline` writes `.trueup-baseline.json` and prints its key count and score (D6.6).

    arch: D6.6
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    exit_code = cli.main(["baseline", "--root", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / ".trueup-baseline.json").is_file()
    out = capsys.readouterr().out
    assert out.startswith("baseline: ")
    assert "keys" in out and "score" in out


def test_check_baseline_and_out_together_is_allowed(tmp_path: Path) -> None:
    """`--baseline` is only rejected together with `--changed`, not with `--out` (D6.17, D6.7).

    arch: D6.17, D6.7
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    cli.main(["baseline", "--root", str(tmp_path)])
    out_dir = tmp_path / ".." / "out"
    exit_code = cli.main(
        ["check", "--root", str(tmp_path), "--baseline", "--out", str(out_dir)]
    )
    assert exit_code == 0


def test_hook_choices_are_the_four_events() -> None:
    """The `hook` subcommand's choices are `session`, `guard`, `stop` and `interface` (LOW-5).

    arch: D6.2, D6.3, D6.4
    """
    parser = cli._build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    hook_parser = subparsers.choices["hook"]
    event = next(action for action in hook_parser._actions if action.dest == "event")
    assert list(event.choices) == ["session", "guard", "stop", "interface"]
    assert cli.HOOK_EVENTS == ("session", "guard", "stop", "interface")


def test_refs_is_a_listed_subcommand() -> None:
    """`refs` is one of the parser's subcommand choices, so `--help` lists it.

    arch: D5.11
    """
    parser = cli._build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert "refs" in subparsers.choices


def test_refs_forwards_its_tokens_to_ref_check_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`refs` passes every token after the subcommand to `ref_check.main`, unparsed.

    arch: D5.11
    """
    captured: list[list[str]] = []

    def _fake_main(argv: list[str]) -> int:
        captured.append(list(argv))
        return 0

    monkeypatch.setattr("trueup.ref_check.main", _fake_main)
    exit_code = cli.main(["refs", "--root", "/tmp/x", "--edges", "e.json"])
    assert exit_code == 0
    assert captured == [["--root", "/tmp/x", "--edges", "e.json"]]


def test_refs_adds_the_resolved_root_when_none_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `--root`, `-h` or `--help` token, `refs` adds the git top level.

    arch: D5.11
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    captured: list[list[str]] = []

    def _fake_main(argv: list[str]) -> int:
        captured.append(list(argv))
        return 0

    monkeypatch.setattr("trueup.ref_check.main", _fake_main)
    import os

    outside = Path.cwd()
    os.chdir(tmp_path)
    try:
        exit_code = cli.main(["refs"])
    finally:
        os.chdir(outside)
    assert exit_code == 0
    assert captured == [["--root", str(tmp_path.resolve())]]


@pytest.mark.parametrize("token", ["--root", "--root=/x", "-h", "--help"])
def test_refs_leaves_a_root_or_help_token_alone(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--root`, `--root=...`, `-h` or `--help` token stops `refs` from adding one.

    arch: D5.11
    """
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "trueup.ref_check.main", lambda argv: captured.append(list(argv)) or 0
    )
    cli.main(["refs", token])
    assert captured == [[token]]


def test_refs_without_root_outside_git_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside a git repository, `refs` with no `--root` is the usual `ConfigError`, exit 2.

    arch: D5.11
    """
    import os

    outside = Path.cwd()
    os.chdir(tmp_path)
    try:
        exit_code = cli.main(["refs"])
    finally:
        os.chdir(outside)
    assert exit_code == 2
    assert "trueup:" in capsys.readouterr().err


def _capture_refs_main(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[str], str | None]]:
    """Put a stand-in for `ref_check.main` that records its argv and the `--config` text.

    Args:
        monkeypatch: The pytest fixture that restores `ref_check.main`.

    Returns:
        The list the stand-in fills: one `(argv, config text or None)` per
        call. The text is `None` when no `--config` token names a file.
    """
    captured: list[tuple[list[str], str | None]] = []

    def _fake_main(argv: list[str]) -> int:
        text = None
        if "--config" in argv:
            config_path = Path(argv[argv.index("--config") + 1])
            if config_path.is_file():
                text = config_path.read_text(encoding="utf-8")
        captured.append((list(argv), text))
        return 0

    monkeypatch.setattr("trueup.ref_check.main", _fake_main)
    return captured


def test_refs_renders_the_checker_config_into_a_temporary_directory_in_global_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In global mode `refs` renders the effective checker config outside the root and passes `--config`.

    arch: D14.22, D14.4, D14.5, D15.2
    """
    from trueup import config, managed, survey

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # D15.2
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T2"\ndocs = "full"\nignore = ["vendor/**"]\n\n'
        "[[keep]]\n"
        'id = "refcheck:docs/page.md:1:no-front-matter"\nreason = "fixed path"\n',
        encoding="utf-8",
    )
    captured = _capture_refs_main(monkeypatch)
    assert cli.main(["refs", "--root", str(tmp_path)]) == 0
    ((argv, text),) = captured
    assert argv[:2] == ["--root", str(tmp_path)]
    assert argv[2] == "--config"
    config_path = Path(argv[3])
    assert not config_path.is_relative_to(tmp_path)
    assert config_path.parent.name.startswith("trueup-refs-")
    assert not config_path.exists()  # the temporary directory is gone
    cfg = config.load(tmp_path)
    assert cfg is not None
    expected = managed.render_ref_check_config(cfg, survey.run(tmp_path), keep=True)
    assert text == expected
    assert '[keep]\nfailures = ["docs/page.md:1:no-front-matter"]' in text
    assert '[scan]\nignore = ["vendor/**"]' in text
    assert not (tmp_path / "ref_check.toml").exists()


def test_refs_passes_an_empty_config_when_the_switches_are_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At T1 with no docs page `refs` passes an empty config, the text `check` gives the checker.

    arch: D14.22, D14.4, D14.5, D15.2
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # D15.2
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\n', encoding="utf-8"
    )
    captured = _capture_refs_main(monkeypatch)
    assert cli.main(["refs", f"--root={tmp_path}"]) == 0
    ((argv, text),) = captured
    assert argv[:2] == [f"--root={tmp_path}", "--config"]
    assert text == ""


@pytest.mark.parametrize(
    ("trueup_toml", "extra"),
    [
        ('version = 1\n\n[refs]\nmode = "copy"\n', []),
        ("version = 1\n", ["--config", "mine.toml"]),
        ("version = 1\n", ["--config=mine.toml"]),
        (None, []),
    ],
    ids=["copy-mode", "config-token", "config-equals", "no-config"],
)
def test_refs_adds_no_config_in_copy_mode_or_when_one_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trueup_toml: str | None,
    extra: list[str],
) -> None:
    """Copy mode, a `--config` token or a root with no config keeps the tokens as given.

    arch: D14.22, D14.4, D14.5
    """
    if trueup_toml is not None:
        (tmp_path / "trueup.toml").write_text(trueup_toml, encoding="utf-8")
    captured = _capture_refs_main(monkeypatch)
    cli.main(["refs", "--root", str(tmp_path), *extra])
    assert [argv for argv, _ in captured] == [["--root", str(tmp_path), *extra]]


def test_apply_plan_needs_ids_or_all_auto(tmp_path: Path) -> None:
    """`apply --plan F` with neither `--ids` nor `--all-auto` is a usage error: exit 2.

    arch: D12.1
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["apply", "--plan", str(tmp_path / "plan.json")])
    assert excinfo.value.code == 2


def test_apply_plan_passes_the_file_to_apply_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`apply --plan F --ids X` gives `apply.run` the plan path and the ids.

    arch: D12.1
    """
    from trueup import apply as apply_mod

    seen: dict[str, object] = {}

    def _fake_run(root: Path, **kwargs: object) -> int:
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(apply_mod, "run", _fake_run)
    plan_file = tmp_path / "plan.json"
    code = cli.main(
        ["apply", "--root", str(tmp_path), "--plan", str(plan_file), "--ids", "a,b"]
    )
    assert code == 0
    assert seen["plan"] == plan_file
    assert seen["ids"] == ["a", "b"]


@pytest.fixture
def profile_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the teardown remove the `TRUEUP_PROFILE` value that `main` sets.

    `main` writes `os.environ` itself. A `setenv` and then a `delenv`
    records the variable as unset, so `monkeypatch` deletes it again after
    the test.

    Args:
        monkeypatch: The pytest fixture that restores the environment.
    """
    monkeypatch.setenv(cli.PROFILE_ENV, "placeholder")
    monkeypatch.delenv(cli.PROFILE_ENV)


@pytest.mark.parametrize(
    ("command", "handler", "extra"),
    [
        ("survey", "_run_survey", []),
        ("check", "_run_check", []),
        ("baseline", "_run_baseline", []),
        ("apply", "_run_apply", ["--all-auto"]),
    ],
)
@pytest.mark.usefixtures("profile_env")
def test_profile_option_sets_trueup_profile_before_the_handler_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    handler: str,
    extra: list[str],
) -> None:
    """`--profile NAME` sets `TRUEUP_PROFILE` before the handler loads a config (L4).

    arch: D14.1, D14.3, D14.18
    """
    import os

    seen: list[str | None] = []

    def _fake(args: object) -> int:
        seen.append(os.environ.get("TRUEUP_PROFILE"))
        return 0

    monkeypatch.setattr(cli, handler, _fake)
    argv = [command, "--root", str(tmp_path), "--profile", "minimal", *extra]
    assert cli.main(argv) == 0
    assert seen == ["minimal"]


@pytest.mark.usefixtures("profile_env")
def test_no_profile_option_keeps_the_environment_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without `--profile`, `main` keeps `TRUEUP_PROFILE` as the environment gave it.

    arch: D14.1, D14.3, D14.18
    """
    import os

    seen: list[str | None] = []

    def _fake(args: object) -> int:
        seen.append(os.environ.get("TRUEUP_PROFILE"))
        return 0

    monkeypatch.setattr(cli, "_run_check", _fake)
    assert cli.main(["check", "--root", str(tmp_path)]) == 0
    monkeypatch.setenv("TRUEUP_PROFILE", "mine")
    assert cli.main(["check", "--root", str(tmp_path)]) == 0
    assert seen == [None, "mine"]


@pytest.mark.parametrize("name", ["", "House", "a/b", "x_y"])
@pytest.mark.usefixtures("profile_env")
def test_a_bad_profile_name_exits_two_and_sets_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    """A `--profile` value that is not a profile name exits 2; the handler does not run.

    arch: D14.1, D14.3, D14.18
    """
    import os

    called: list[object] = []
    monkeypatch.setattr(cli, "_run_check", called.append)
    assert cli.main(["check", "--root", str(tmp_path), "--profile", name]) == 2
    assert called == []
    assert "TRUEUP_PROFILE" not in os.environ
    assert "profile name must be lower-case" in capsys.readouterr().err


def test_hook_has_no_profile_option() -> None:
    """`hook` takes no `--profile`: argparse exits 2 (D14.22 item 5).

    arch: D14.1, D14.3, D14.18
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["hook", "stop", "--profile", "minimal"])
    assert excinfo.value.code == 2


# -- D15.1 loud failures, D15.2 git is required ---------------------------


def _raise_runtime_error(args: object) -> int:
    """Raise the error that stands for any bug in a handler.

    Args:
        args: The parsed arguments, unused.

    Raises:
        RuntimeError: Always.
    """
    raise RuntimeError("boom")


def test_main_turns_an_unexpected_exception_into_one_line_and_exit_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An exception that is not a `ConfigError` gives one stderr line and exit 2.

    arch: D15.1, D15.2, I-52
    """
    monkeypatch.delenv("TRUEUP_DEBUG", raising=False)
    monkeypatch.setattr(cli, "_run_survey", _raise_runtime_error)
    assert cli.main(["survey"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith("trueup: internal error: RuntimeError: boom")
    assert "TRUEUP_DEBUG=1" in err
    assert "Traceback" not in err


def test_main_prints_the_traceback_under_trueup_debug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`TRUEUP_DEBUG=1` adds the traceback before the one-line message.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("TRUEUP_DEBUG", "1")
    monkeypatch.setattr(cli, "_run_survey", _raise_runtime_error)
    assert cli.main(["survey"]) == 2
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "trueup: internal error: RuntimeError: boom" in err


def test_a_hook_stays_silent_on_an_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `hook` command returns 0 and prints nothing when its handler fails (I-22).

    arch: D15.1, D15.2
    """
    monkeypatch.setattr(cli, "_run_hook", _raise_runtime_error)
    assert cli.main(["hook", "session"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_a_root_that_is_not_a_directory_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--root` naming a missing path or a file gives exit 2 and one line.

    arch: D15.1, D15.2
    """
    a_file = tmp_path / "file.txt"
    a_file.write_text("x\n", encoding="utf-8")
    for bad in (tmp_path / "missing", a_file):
        assert cli.main(["check", "--root", str(bad)]) == 2
        err = capsys.readouterr().err
        assert err.count("\n") == 1
        assert "not a directory" in err


def test_check_outside_git_exits_two_with_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A root with no git repository gives exit 2 and one line, not a T0 report.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.err.count("\n") == 1
    assert "not a git repository" in captured.err
    assert captured.out == ""


def test_an_unreadable_config_is_a_config_error_not_a_git_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `trueup.toml` that is not UTF-8 gives a message that names the file.

    arch: D15.1, D15.2
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_bytes(b"version = 1\n# caf\xe9\n")
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "trueup.toml" in err
    assert "cannot read" in err
    assert "--changed" not in err


def test_refs_on_a_directory_with_no_git_repository_runs_the_checker_as_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`refs` stays git-free: with no work tree it adds no `--config` and reads no survey.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T2"\n', encoding="utf-8"
    )
    captured = _capture_refs_main(monkeypatch)
    assert cli.main(["refs", "--root", str(tmp_path)]) == 0
    ((argv, text),) = captured
    assert "--config" not in argv
    assert text is None


def test_lint_of_a_repository_with_no_tracked_file_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`lint` on an adopted git repository with no tracked file exits 2 with one line.

    arch: D15.1, D15.2, I-52
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "trueup.toml").write_text(
        'profile = "house"\nignore = ["trueup.toml"]\n', encoding="utf-8"
    )
    assert cli.main(["lint", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "no tracked file to check" in err


def test_a_saved_plan_run_of_an_empty_survey_is_a_config_error(tmp_path: Path) -> None:
    """The saved-plan path of `apply` refuses a survey that holds no file.

    arch: D15.1, D15.2, I-52
    """
    from trueup import apply as apply_mod  # reason: only this test needs it

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    saved = apply_mod.SavedRun(tree={}, plan=(), findings=(), moves=(), repins=())
    with pytest.raises(ConfigError, match="no tracked file to check"):
        apply_mod._saved_check_run(tmp_path, saved)
