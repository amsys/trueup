"""Tests for the launcher `trueup/__main__.py`: the gates that run before any import."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from trueup import __main__ as launcher
from trueup import hooks

_PACKAGE = Path(__file__).resolve().parent.parent / "trueup"


def _git_init(root: Path) -> None:
    """Turn `root` into an empty git repository.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _launch(args: list[str], stdin: str, cwd: Path, data: Path | None = None):
    """Run `python3 trueup <args>` as the plugin does.

    Args:
        args: The command-line words after the package path.
        stdin: The text to send on stdin.
        cwd: The working directory of the process.
        data: The `CLAUDE_PLUGIN_DATA` directory, when the test wants one.

    Returns:
        The finished process.
    """
    import os

    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}
    if data is not None:
        env["CLAUDE_PLUGIN_DATA"] = str(data)
    return subprocess.run(
        [sys.executable, str(_PACKAGE), *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_old_python_hook_exits_0_silently() -> None:
    """On Python older than 3.11 a `hook` call exits 0 with no output.

    arch: D15.7, D15.24
    """
    result = launcher.early_exit(["trueup", "hook", "guard"], (3, 10, 4), lambda: "")
    assert result == 0


def test_old_python_other_command_exits_2_with_a_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On Python older than 3.11 any other command prints the version need and exits 2.

    arch: D15.7, D15.24
    """
    result = launcher.early_exit(["trueup", "check"], (3, 10, 4), lambda: "")
    assert result == 2
    assert capsys.readouterr().err.strip() == (
        "trueup: needs Python 3.11 or later, this is 3.10.4"
    )


def test_hook_without_trueup_toml_exits_before_the_cli_import(tmp_path: Path) -> None:
    """A hook in a git repo with no `trueup.toml` exits 0 and never imports `trueup.cli`.

    The launcher reads stdin itself, so the child process never loads the
    CLI module.

    arch: D15.7, D15.24
    """
    _git_init(tmp_path)
    payload = json.dumps({"cwd": str(tmp_path)})
    assert (
        launcher.early_exit(["trueup", "hook", "session"], (3, 12, 0), lambda: payload)
        == 0
    )
    result = _launch(["hook", "session"], payload, tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_hook_with_bad_json_exits_0(tmp_path: Path) -> None:
    """A hook whose stdin is not JSON, or not an object, exits 0 with no output.

    arch: D15.7, D15.24
    """
    for text in ("{not json", "[1, 2]", "42"):
        assert (
            launcher.early_exit(
                ["trueup", "hook", "guard"], (3, 12, 0), lambda t=text: t
            )
            == 0
        )


def test_hook_with_trueup_toml_goes_on_to_the_cli(tmp_path: Path) -> None:
    """With `trueup.toml` at the root, the launcher gives no exit code and the session notice prints.

    arch: D15.7, D15.24
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    payload = json.dumps({"cwd": str(tmp_path), "session_id": "s1"})
    assert (
        launcher.early_exit(["trueup", "hook", "session"], (3, 12, 0), lambda: payload)
        is None
    )
    result = _launch(["hook", "session"], payload, tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("trueup")


def test_root_walk_equals_hooks_find_root(tmp_path: Path) -> None:
    """The launcher's root walk and `hooks._find_root` give the same root on three paths.

    arch: D15.7, D15.24
    """
    repo = tmp_path / "repo"
    (repo / "a" / "b").mkdir(parents=True)
    _git_init(repo)
    plain = tmp_path / "plain"
    plain.mkdir()
    for start in (repo, repo / "a" / "b", plain):
        expected = hooks._find_root({"cwd": str(start)})
        assert launcher.find_root(str(start)) == expected


def test_malformed_trueup_toml_prints_one_session_line(tmp_path: Path) -> None:
    """A broken `trueup.toml` gives one notice on `session` and silence on the other events.

    arch: D15.7, D15.24
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text("profile = [unclosed\n", encoding="utf-8")
    payload = json.dumps({"cwd": str(tmp_path), "session_id": "s1"})
    session = _launch(["hook", "session"], payload, tmp_path)
    assert session.returncode == 0
    lines = session.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("trueup: trueup.toml is not valid: ")
    assert lines[0].endswith("; the trueup hooks are off until it is fixed")
    for event in ("guard", "stop", "interface"):
        other = _launch(["hook", event], payload, tmp_path)
        assert (other.returncode, other.stdout) == (0, ""), event
