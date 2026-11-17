"""Tests for the plugin manifests: `plugin.json`, `marketplace.json` and `hooks/hooks.json`."""

from __future__ import annotations

import json
import shlex
import subprocess
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_JSON = _REPO_ROOT / ".claude-plugin" / "plugin.json"
_MARKETPLACE_JSON = _REPO_ROOT / ".claude-plugin" / "marketplace.json"
_HOOKS_JSON = _REPO_ROOT / "hooks" / "hooks.json"


def _load(path: Path) -> dict:
    """Parse one manifest file as JSON.

    Args:
        path: The manifest file to read.

    Returns:
        The parsed JSON object.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_json_has_the_d5_1_fields() -> None:
    """`plugin.json` names trueup, version 0.1.0-alpha.1, and an MIT license.

    arch: D5.10
    """
    manifest = _load(_PLUGIN_JSON)
    assert manifest["name"] == "trueup"
    assert manifest["version"] == "0.1.0-alpha.1"
    assert manifest["license"] == "MIT"
    assert isinstance(manifest["description"], str) and manifest["description"]


def test_marketplace_json_lists_the_one_plugin_from_this_directory() -> None:
    """`marketplace.json` names trueup, owned by Martin, sourced from `./`.

    arch: D5.10
    """
    marketplace = _load(_MARKETPLACE_JSON)
    assert marketplace["name"] == "trueup"
    assert marketplace["owner"]["name"] == "Martin"
    assert marketplace["plugins"] == [
        {
            "name": "trueup",
            "source": "./",
            "description": _load(_PLUGIN_JSON)["description"],
            "version": "0.1.0-alpha.1",
        }
    ]


def test_marketplace_and_plugin_versions_match() -> None:
    """The marketplace entry's version never drifts from `plugin.json`'s.

    arch: D5.10
    """
    plugin = _load(_PLUGIN_JSON)
    marketplace = _load(_MARKETPLACE_JSON)
    assert marketplace["plugins"][0]["version"] == plugin["version"]


def test_hooks_json_wires_session_start_and_pre_tool_use() -> None:
    """`hooks/hooks.json` runs `trueup hook session` and `trueup hook guard`.

    arch: D5.10, D5.8
    """
    manifest = _load(_HOOKS_JSON)
    hooks = manifest["hooks"]

    session_commands = [
        entry["command"] for group in hooks["SessionStart"] for entry in group["hooks"]
    ]
    assert any(
        "${CLAUDE_PLUGIN_ROOT}" in cmd and "hook session" in cmd
        for cmd in session_commands
    )

    pre_tool_use = hooks["PreToolUse"]
    assert any(group.get("matcher") == "Write|Bash" for group in pre_tool_use)
    guard_commands = [
        entry["command"]
        for group in pre_tool_use
        if group.get("matcher") == "Write|Bash"
        for entry in group["hooks"]
    ]
    assert any(
        "${CLAUDE_PLUGIN_ROOT}" in cmd and "hook guard" in cmd for cmd in guard_commands
    )


def _run_manifest_command(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one `hooks.json` command line, with `${CLAUDE_PLUGIN_ROOT}` filled in.

    Args:
        command: The command string from `hooks/hooks.json`, e.g.
            `python3 "${CLAUDE_PLUGIN_ROOT}/trueup" hook guard`.
        cwd: The directory to run it from, standing in for the hook's `cwd`.

    Returns:
        The finished process, with empty stdin, as a hook gets when Claude
        Code sends no tool call payload.
    """
    filled = command.replace("${CLAUDE_PLUGIN_ROOT}", str(_REPO_ROOT))
    return subprocess.run(
        shlex.split(filled),
        cwd=cwd,
        input="",
        capture_output=True,
        text=True,
        check=False,
    )


def test_guard_command_from_the_manifest_fails_open_on_a_plain_git_repo(
    tmp_path: Path,
) -> None:
    """The exact `hooks.json` guard command exits 0 with no output when `trueup.toml` is absent.

    This runs the real command line the manifest wires up, not `trueup.hooks`
    directly, so it also proves `CLAUDE_PLUGIN_ROOT` substitution and the CLI
    wiring of D5.11's `hook` subcommand end to end.

    arch: D5.8, I-22
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    manifest = _load(_HOOKS_JSON)
    guard_group = next(
        group
        for group in manifest["hooks"]["PreToolUse"]
        if group.get("matcher") == "Write|Bash"
    )
    command = guard_group["hooks"][0]["command"]
    result = _run_manifest_command(command, cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def _commands(event: str, matcher: str | None = None) -> list[str]:
    """List the command lines that `hooks/hooks.json` wires to one event.

    Args:
        event: The hook event name, for example `"Stop"`.
        matcher: When given, only the groups with this `matcher` count.

    Returns:
        Each `command` string of the matching groups.
    """
    groups = _load(_HOOKS_JSON)["hooks"][event]
    return [
        entry["command"]
        for group in groups
        if matcher is None or group.get("matcher") == matcher
        for entry in group["hooks"]
    ]


def test_hooks_json_wires_stop_and_post_tool_use() -> None:
    """`Stop` runs `hook stop`, and there is no `SubagentStop` entry; `PostToolUse` `Write|Edit|MultiEdit` runs `hook interface`.

    Each command has the launcher shape of the v1 `session` entry, with
    only the event name changed. A subagent never gets the Stop block
    (D15.33).

    arch: D6.2, D6.3, D6.4, D15.33
    """
    session = _commands("SessionStart")[0]
    assert session.endswith(" hook session")
    launcher = session.removesuffix(" session")
    assert _commands("Stop") == [f"{launcher} stop"]
    assert "SubagentStop" not in _load(_HOOKS_JSON)["hooks"]
    assert _commands("PostToolUse", "Write|Edit|MultiEdit") == [f"{launcher} interface"]


def test_stop_and_interface_commands_fail_open_on_a_plain_git_repo(
    tmp_path: Path,
) -> None:
    """The exact `hooks.json` stop and interface commands exit 0 with no output when `trueup.toml` is absent.

    arch: D6.2, D6.3, D6.4, I-22
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tmp_notes.txt").write_text("x\n", encoding="utf-8")
    for command in (_commands("Stop")[0], _commands("PostToolUse")[0]):
        result = _run_manifest_command(command, cwd=tmp_path)
        assert result.returncode == 0, command
        assert result.stdout == "", command


def test_stop_hook_has_a_30_second_timeout() -> None:
    """The `Stop` entry sets `"timeout": 30`; a kill is fail-open.

    arch: D15.7, D15.24
    """
    stop = _load(_HOOKS_JSON)["hooks"]["Stop"][0]["hooks"][0]
    assert stop["timeout"] == 30


def test_the_wheel_package_data_holds_the_builtin_profiles() -> None:
    """The package data of `pyproject.toml` takes in each built-in profile file.

    The D14.16 pattern `data/**/*` reaches `trueup/data/profiles/`. A
    pattern `data/*` does not, and a wheel without the profiles cannot run.

    arch: D14.16
    """
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    patterns = tomllib.loads(text)["tool"]["setuptools"]["package-data"]["trueup"]
    package = _REPO_ROOT / "trueup"
    matched = {path for pattern in patterns for path in package.glob(pattern)}
    for name in ("house", "minimal"):
        assert package / "data" / "profiles" / f"{name}.toml" in matched
