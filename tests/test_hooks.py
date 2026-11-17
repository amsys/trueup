"""Tests for `trueup.hooks`: the session, guard, stop and interface hooks."""

from __future__ import annotations

import contextlib
import fnmatch
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trueup import changes, hooks, registry
from trueup.config import Config, render


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _write_config(root: Path, cfg: Config = Config()) -> None:
    """Write `cfg` to `root/trueup.toml`.

    Args:
        root: The repository root.
        cfg: The config to render. Defaults to `Config()`.
    """
    (root / "trueup.toml").write_text(render(cfg), encoding="utf-8")


def _run(event: str, payload: dict) -> tuple[int, str]:
    """Run `hooks.run` with `payload` as its JSON stdin.

    Args:
        event: `"session"` or `"guard"`.
        payload: The dict to send as the hook's JSON input.

    Returns:
        The exit code and everything printed to stdout.
    """
    return _run_raw(event, json.dumps(payload))


def _run_raw(event: str, raw_stdin: str) -> tuple[int, str]:
    """Run `hooks.run` with `raw_stdin` given exactly as its stdin text.

    Args:
        event: `"session"` or `"guard"`.
        raw_stdin: The literal text to feed as stdin, valid JSON or not.

    Returns:
        The exit code and everything printed to stdout.
    """
    stdout = io.StringIO()
    stdin = io.StringIO(raw_stdin)
    with contextlib.redirect_stdout(stdout):
        code = hooks.run(event, stdin=stdin)
    return code, stdout.getvalue()


def test_no_trueup_toml_is_silent(tmp_path: Path) -> None:
    """A root with no `trueup.toml` gives exit 0 and no output.

    The `tool_input` here names a real scratch-looking write outside
    `.scratch/` (`src/tmp_notes.txt`), the exact shape that a config would
    deny. An empty `tool_input` would pass this test even if the D5.8
    activation check were deleted, because `_check_write` would return
    `None` before ever touching the (missing) config; a real target is
    needed to prove the guard stays inactive rather than merely idle.

    arch: D5.8, I-22
    """
    _git_init(tmp_path)
    target = tmp_path / "src" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_bad_json_is_silent(tmp_path: Path) -> None:
    """Invalid JSON on stdin gives exit 0 and no output.

    arch: I-22
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    code, out = _run_raw("guard", "{not valid json")
    assert code == 0
    assert out == ""


def test_non_object_json_is_silent(tmp_path: Path) -> None:
    """A JSON value that is not an object gives exit 0 and no output.

    arch: I-22
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    code, out = _run_raw("guard", "[1, 2, 3]")
    assert code == 0
    assert out == ""


def test_no_git_root_is_silent(tmp_path: Path) -> None:
    """A `cwd` with no `.git` ancestor gives exit 0 and no output.

    `tool_input` names a real scratch-looking write, not an empty dict, so
    the assertion actually depends on `_find_root` returning `None` rather
    than on `_check_write` having nothing to look at.

    arch: D5.8, I-22
    """
    target = tmp_path / "src" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_keys_on_session_cwd_not_the_writes_own_target(tmp_path: Path) -> None:
    """A scratch-looking `Write` into a repository other than the session `cwd` is not checked (LOW-8).

    `_find_root` reads only `cwd`, so a target the trueup skill names
    elsewhere gets no protection from this session. The test pins this
    known, not fixed, behavior. The warning in the skill's "Hooks" section
    is still to be written.

    arch: D6.15
    """
    session_repo = tmp_path / "session"
    session_repo.mkdir()
    _git_init(session_repo)
    _write_config(session_repo)

    other_repo = tmp_path / "other"
    other_repo.mkdir()
    _git_init(other_repo)
    _write_config(other_repo)
    target = other_repo / "tmp_notes.txt"

    code, out = _run(
        "guard",
        {
            "cwd": str(session_repo),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_exception_in_config_load_is_silent(tmp_path: Path) -> None:
    """Any exception while handling a hook gives exit 0 and no output.

    `config.load` raising `ConfigError` on a malformed `trueup.toml` is one
    such exception; the guard must fail open on it exactly as it does on a
    missing file. `tool_input` names a real scratch-looking write, not an
    empty dict, so the assertion depends on the exception actually being
    swallowed rather than on `_check_write` having nothing to look at.

    arch: I-22
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text("not = [valid", encoding="utf-8")
    target = tmp_path / "src" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_empty_stdin_is_silent() -> None:
    """Empty stdin (no JSON at all) gives exit 0 and no output.

    arch: I-22
    """
    code, out = _run_raw("guard", "")
    assert code == 0
    assert out == ""


def test_guard_asks_on_new_root_file(tmp_path: Path) -> None:
    """A new file whose parent is the root, and whose name is not allowed, gets `ask`.

    D14.11 changes this answer from `deny` to `ask`.

    arch: D5.8, D14.11
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "randomfile.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "[root] allow" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_guard_allows_root_file_named_in_config(tmp_path: Path) -> None:
    """A new root file whose name is in `[root] allow` is not denied.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(root_allow=("randomfile.txt",)))
    target = tmp_path / "randomfile.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_allows_base_list_name(tmp_path: Path) -> None:
    """A new root file matching the base allow list (e.g. README*) is not denied.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "README.md"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


@pytest.mark.parametrize("name", [".claude", ".github"])
def test_guard_allows_the_agent_and_platform_directories(
    tmp_path: Path, name: str
) -> None:
    """A new `.claude` or `.github` root entry is on the base list (D5.8).

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / name)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_allows_write_to_existing_root_file(tmp_path: Path) -> None:
    """Rewriting a root file that already exists is never denied by the root rule.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "extra.txt"
    target.write_text("already here\n", encoding="utf-8")
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_allows_write_inside_a_subdirectory(tmp_path: Path) -> None:
    """A write whose parent is not the root is never denied by the root rule.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "docs" / "new.md"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_asks_on_a_new_scratch_write_outside_scratch_dir(tmp_path: Path) -> None:
    """A new scratch-looking write path outside `.scratch/` gets `ask`, naming `.scratch/`.

    arch: D5.8, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "src" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert ".scratch/" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_guard_allows_scratch_write_under_scratch_dir(tmp_path: Path) -> None:
    """A scratch-looking write path under `.scratch/` is not denied.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / ".scratch" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_asks_on_git_add_of_scratch_path(tmp_path: Path) -> None:
    """A `Bash` `git add` of a scratch-looking path gets `ask`, naming `.scratch/` (D15.31).

    arch: D5.8, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git add tmp_notes.txt"},
        },
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert "tmp_notes.txt" in reason
    assert ".scratch/" in reason


def test_guard_lets_dash_c_stage_and_add_all_pass(tmp_path: Path) -> None:
    """`git -C . add`, `git stage` and `git add -A` are not denied (LOW-3).

    The review calls this "consistent with the contract" of checking the
    tokens after a literal `git add`, and asks only for a reference-page
    note, which is outside this task's file scope. Pinned as documented,
    not changed, behavior.

    arch: D6.15
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for command in (
        "git -C . add tmp_notes.txt",
        "git stage tmp_notes.txt",
        "git add -A",
    ):
        code, out = _run(
            "guard",
            {
                "cwd": str(tmp_path),
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        assert code == 0
        assert out == ""


def test_guard_silent_on_scratch_write_with_no_config(tmp_path: Path) -> None:
    """A scratch write in a subdirectory is not denied when `trueup.toml` is absent.

    This is the D5.8 activation check in isolation: `_check_write` denies a
    subdirectory scratch write on its scratch-name branch alone, without
    reading `cfg` at all, so this case does not fail open by accident (an
    exception from a `None` config being caught) the way a root-level file
    would. Only the explicit `if cfg is None: return 0` guard keeps it
    silent, so this is the regression test for that line.

    arch: D5.8, I-22
    """
    _git_init(tmp_path)
    target = tmp_path / "src" / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_allows_git_add_of_a_normal_path(tmp_path: Path) -> None:
    """A `Bash` `git add` of an ordinary path is not denied.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git add README.md"},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_ignores_other_tools(tmp_path: Path) -> None:
    """A tool other than `Write` or `Bash` is never acted on.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    target = tmp_path / "tmp_notes.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    assert out == ""


def test_guard_finds_root_from_a_nested_cwd(tmp_path: Path) -> None:
    """The root walk finds `.git` above a nested working directory.

    The guard answers `ask` for the new root file (D14.11).

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    target = tmp_path / "randomfile.txt"
    code, out = _run(
        "guard",
        {
            "cwd": str(nested),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        },
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_session_prints_tier_and_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStart prints the tier, and the root, scratch and managed-file rules.

    D14.10 replaces the closing line "Run the trueup skill" with "Run
    trueup check".

    arch: D5.8, D14.10
    """
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/bin/trueup")
    _git_init(tmp_path)
    _write_config(tmp_path, Config(tier="T2", languages={"python": "clean"}))
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert "tier T2" in out
    assert "python=clean" in out
    assert ".scratch/" in out
    assert "[root] allow" in out
    assert "Run trueup check before you finish" in out
    assert len(out.splitlines()) <= 15


def test_session_silent_with_no_config(tmp_path: Path) -> None:
    """SessionStart prints nothing when there is no `trueup.toml`.

    arch: D5.8, I-22
    """
    _git_init(tmp_path)
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert out == ""


def _guard_write(root: Path, relative: str) -> str:
    """Run the guard on one `Write` to a path under `root`.

    Args:
        root: The repository root, also the hook's `cwd`.
        relative: The written path, relative to `root`.

    Returns:
        What the guard printed: empty when it allows the write.
    """
    code, out = _run(
        "guard",
        {
            "cwd": str(root),
            "tool_name": "Write",
            "tool_input": {"file_path": str(root / relative)},
        },
    )
    assert code == 0
    return out


def test_guard_allows_ordinary_source_names(tmp_path: Path) -> None:
    """Source names that start with a scratch word are not scratch, so the guard lets them through.

    arch: D5.4, D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for name in (
        "src/template.py",
        "src/templates.py",
        "src/temperature.rs",
        "db/temp_table.sql",
        "src/tempo.go",
        "src/notes.py",
        "src/notes_service.py",
        "src/notesController.php",
        "src/scratchpad.rs",
    ):
        assert _guard_write(tmp_path, name) == "", name


def test_guard_asks_on_the_widened_scratch_name_patterns(tmp_path: Path) -> None:
    """The guard asks on the D10.3 backup-chain, copy-suffix and prefix-any-extension names.

    arch: D10.3, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for name in (
        "src/README.old.md",
        "src/x.bak.py",
        "docs/ARCHITECTURE_v2_draft.md",
        "src/scratch_fold.rs",
    ):
        assert _decision(_guard_write(tmp_path, name)) == "ask", name


def test_guard_ignores_the_scratch_directory_rule(tmp_path: Path) -> None:
    """The guard denies on name alone: a clean name under `tmp/` is let through (D10.3).

    `check` flags `tmp/report.py` through `looks_scratch_path`'s directory
    rule, but the guard hook keeps `looks_scratch` alone and never takes
    that rule, so this clean-named write is not denied.

    arch: D10.3
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    assert _guard_write(tmp_path, "tmp/report.py") == ""


def test_guard_honours_ignore_and_scratch_allow(tmp_path: Path) -> None:
    """A scratch-looking path under `ignore` or `[scratch] allow` is let through; others still get `ask`.

    arch: D5.3, D5.8, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    assert _decision(_guard_write(tmp_path, "docs/notes.md")) == "ask"
    assert "[scratch] allow" in _guard_write(tmp_path, "docs/notes.md")
    _write_config(
        tmp_path,
        Config(
            ignore=("tests/fixtures/**",),
            scratch_allow=("docs/notes.md", "tmp-keep.txt"),
        ),
    )
    assert _guard_write(tmp_path, "docs/notes.md") == ""
    assert _guard_write(tmp_path, "tests/fixtures/messy/tmp-draft.md") == ""
    assert _guard_write(tmp_path, "src/deep/tmp-keep.txt") == ""
    assert _decision(_guard_write(tmp_path, "src/notes.md")) == "ask"


def test_guard_honours_root_allow_for_a_scratch_name(tmp_path: Path) -> None:
    """A root entry named in `[root] allow` passes both the root rule and the scratch rule.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(root_allow=("notes.md",)))
    assert _guard_write(tmp_path, "notes.md") == ""


def test_guard_git_add_honours_scratch_allow(tmp_path: Path) -> None:
    """A `git add` of a path `[scratch] allow` names is not denied.

    arch: D5.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(scratch_allow=("docs/notes.md",)))
    code, out = _run(
        "guard",
        {
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git add ./docs/notes.md"},
        },
    )
    assert code == 0
    assert out == ""


def test_importing_hooks_does_not_pull_in_survey_or_rulesets() -> None:
    """`import trueup.hooks` alone never loads `trueup.survey` or `trueup.rulesets` (LOW-7).

    A fresh interpreter is needed: inside the pytest process, another test
    module may already have imported these, which would hide a regression.

    arch: D6.15
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, trueup.hooks\n"
            "assert not any(\n"
            "    m in sys.modules for m in ('trueup.survey', 'trueup.rulesets')\n"
            ")\n",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _decision(out: str) -> str | None:
    """Give the permission decision that one guard output holds.

    Args:
        out: What the guard printed.

    Returns:
        The `permissionDecision` value, or `None` when the guard printed
        nothing.
    """
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize("event", ["session", "guard", "stop", "interface"])
def test_user_default_file_never_turns_a_hook_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: str
) -> None:
    """A user default file without a target `trueup.toml` leaves every hook silent (I-22).

    The user default file makes `config.load` give a config, so only the
    gate on the target file keeps the hooks off.

    arch: D14.11, I-22
    """
    root = _session_repo(tmp_path, monkeypatch, config=False)
    user_file = tmp_path / "xdg-config" / "trueup" / "trueup.toml"
    user_file.parent.mkdir(parents=True)
    user_file.write_text('docs = "readme"\n', encoding="utf-8")
    (root / "src" / "app.txt").write_text("changed\n", encoding="utf-8")
    payload = {
        "cwd": str(root),
        "session_id": "s1",
        "source": "startup",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "randomfile.txt"),
            "content": "import argparse\nparser.add_argument('--x')\n",
        },
    }
    code, out = _run(event, payload)
    assert code == 0
    assert out == ""


def test_session_text_for_the_house_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStart prints the D14.10 lines for the built-in `house` profile.

    The docs mode is the mode in force (`auto` at T2 is `full`), not the raw key.

    arch: D14.10, D15.34
    """
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/bin/trueup")
    _git_init(tmp_path)
    _write_config(tmp_path, Config(tier="T2", languages={"python": "clean"}))
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert out.splitlines() == [
        "trueup: profile house, tier T2, docs full.",
        "Languages: python=clean.",
        "Write docs in Simplified Technical English: short sentences, active "
        "voice, one topic a page.",
        "Put a page under docs/ in one type: tutorial, how-to, reference or "
        "explanation.",
        "Start a comment marker with a registry word: ref, arch, law, SAFETY or TODO.",
        "Cite a design id only in a form that docs/ARCHITECTURE.md declares.",
        "Root rule: a new file at the repository root must be on the base list "
        "or in [root] allow in trueup.toml.",
        "Scratch rule: a tmp/temp/scratch/notes/*.bak/*.orig/*~-style name goes "
        "under .scratch/, never tracked elsewhere.",
        "Managed-file rule: apply rewrites trueup.toml; edit it by hand or with "
        "apply --set.",
        "Run trueup check before you finish. Fix each finding or report it.",
    ]


def test_session_text_follows_the_profile_and_the_docs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `minimal` profile drops the type, marker, registry and STE lines; `docs_dir` names the directory.

    arch: D14.10, D15.34
    """
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/bin/trueup")
    _git_init(tmp_path)
    _write_config(tmp_path, Config(profile="minimal"))
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert out.splitlines()[0] == "trueup: profile minimal, tier T0, docs readme."
    assert "Put a page under" not in out
    assert "comment marker" not in out
    assert "ARCHITECTURE.md" not in out
    assert "Simplified Technical English" not in out
    assert "Run trueup check before you finish" in out
    _write_config(
        tmp_path,
        Config(layout_docs_dir="pages", refs_comments=False),
    )
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert "Simplified Technical English" in out
    assert "Put a page under pages/ in one type" in out
    assert "a form that pages/ARCHITECTURE.md declares" in out
    assert "comment marker" not in out


def test_session_text_names_the_declared_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `[refs] declared` set, the SessionStart line names those pages, not the default page (D16.2).

    arch: D16.2
    """
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/bin/trueup")
    _git_init(tmp_path)
    _write_config(tmp_path, Config(refs_declared=("design/*.md",)))
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert "the pages named by [refs] declared" in out
    assert "ARCHITECTURE.md" not in out
    _write_config(tmp_path, Config(refs_id_forms=("D-<n>",)))
    code, out = _run("session", {"cwd": str(tmp_path)})
    assert code == 0
    assert "a form that docs/ARCHITECTURE.md declares" in out


def test_the_agent_rules_template_is_gone() -> None:
    """The SessionStart text replaces the agent rules template file.

    arch: D14.10
    """
    template = _REPO_ROOT / "trueup" / "templates" / "claude" / "trueup-rules.md"
    assert not template.exists()


def test_base_root_allow_code_list_and_root_base() -> None:
    """The code list holds the manifests, the lockfiles and the tool files; `[root] base` replaces it.

    arch: D14.11
    """
    from trueup import hygiene, layout, survey

    base = hooks.base_root_allow(Config())
    for name in (
        "README*",
        "trueup.toml",
        "CODEOWNERS",
        "Dockerfile",
        "Containerfile",
        "tsconfig.*.json",
        "requirements*.txt",
        ".woodpecker.yml",
        *survey.MANIFEST_NAMES,
        *hygiene._LOCKFILE_NAMES,
    ):
        assert name in base, name
    assert len(base) == len(set(base))
    for name in layout._STANDARD_ROOT_NAMES:
        assert any(fnmatch.fnmatchcase(name, glob) for glob in base), name
        assert any(fnmatch.fnmatchcase(name.upper(), glob) for glob in base), name
    assert hooks.base_root_allow(Config(root_base=("x",))) == ("x",)
    assert hooks.base_root_allow(Config(root_base=())) == ()


@pytest.mark.parametrize(
    "name",
    [
        "pom.xml",
        "build.gradle.kts",
        "CMakeLists.txt",
        "Dockerfile",
        "CODEOWNERS",
        "tsconfig.app.json",
        "requirements-dev.txt",
        "uv.lock",
        "SECURITY.md",
        "Security.md",
        "code_of_conduct.md",
    ],
)
def test_guard_allows_the_widened_base_list(tmp_path: Path, name: str) -> None:
    """A new root file on the D14.11 code list gets no decision.

    arch: D14.11
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    assert _guard_write(tmp_path, name) == ""


def test_guard_root_base_replaces_the_list_and_root_allow_extends_it(
    tmp_path: Path,
) -> None:
    """With `[root] base` set, a code-list name gets `ask`; `[root] allow` still adds names.

    arch: D14.11
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(root_base=("*.mk",), root_allow=("extra.txt",)))
    assert _decision(_guard_write(tmp_path, "pom.xml")) == "ask"
    assert _guard_write(tmp_path, "rules.mk") == ""
    assert _guard_write(tmp_path, "extra.txt") == ""


def test_guard_scratch_name_at_root_gets_one_scratch_ask(tmp_path: Path) -> None:
    """A new root file with a scratch-looking name gets one `ask` with the scratch reason.

    arch: D14.11, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for name in ("notes.md", "report_v2.md", "x.bak"):
        out = _guard_write(tmp_path, name)
        assert _decision(out) == "ask", name
        assert ".scratch/" in out, name
        assert "repository root" not in out, name


def test_guard_never_answers_allow(tmp_path: Path) -> None:
    """Every guard decision on a mix of writes is `deny`, `ask` or none (I-29).

    arch: D14.11, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for relative in (
        "randomfile.txt",
        "README.md",
        "notes.md",
        "src/tmp_notes.txt",
        "docs/how-to/guide_v2.md",
        "src/app.py",
    ):
        assert _decision(_guard_write(tmp_path, relative)) in (None, "deny", "ask")


def test_guard_scratch_rule_agrees_with_check_under_the_docs_dir(
    tmp_path: Path,
) -> None:
    """The guard drops the `v<n>` marker under `docs_dir`, as `check` does, and takes no directory rule.

    arch: D14.11
    """
    from trueup import hygiene

    _git_init(tmp_path)
    _write_config(tmp_path)
    assert _guard_write(tmp_path, "docs/how-to/guide_v2.md") == ""
    assert _decision(_guard_write(tmp_path, "docs/how-to/guide_draft.md")) == "ask"
    assert _decision(_guard_write(tmp_path, "notes/guide_v2.md")) == "ask"
    assert _guard_write(tmp_path, "tmp/report.py") == ""
    _write_config(tmp_path, Config(layout_docs_dir="pages"))
    assert _guard_write(tmp_path, "pages/guide_v2.md") == ""
    assert _decision(_guard_write(tmp_path, "docs/guide_v2.md")) == "ask"
    cfg = Config(layout_docs_dir="pages")
    for path in (
        "pages/guide_v2.md",
        "pages/a/b-v3.rst",
        "pages/guide_draft.md",
        "docs/guide_v2.md",
        "src/notes.md",
        "README.old.md",
        "src/app.py",
    ):
        assert hooks._scratch_denied(path, cfg) == hygiene.looks_scratch_path(
            path, "pages"
        ), path


def test_guard_keeps_a_versioned_page_under_a_nested_docs_dir(tmp_path: Path) -> None:
    """The guard and `check` agree on a `-v<n>` page under a docs directory at any depth.

    arch: D15.9
    """
    from trueup import hygiene

    _git_init(tmp_path)
    _write_config(tmp_path)
    assert _guard_write(tmp_path, "packages/a/docs/install-v2.md") == ""
    assert (
        _decision(_guard_write(tmp_path, "packages/a/docs/install_draft.md")) == "ask"
    )
    cfg = Config()
    for path in (
        "packages/a/docs/install-v2.md",
        "packages/a/docs/install_draft.md",
        "packages/a/install-v2.md",
        "draft.md",
    ):
        assert hooks._scratch_denied(path, cfg) == hygiene.looks_scratch_path(
            path, "docs"
        ), path


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _session_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: bool = True
) -> Path:
    """Make a repository with one commit, and point `CLAUDE_PLUGIN_DATA` outside it.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: The fixture that sets the environment variable.
        config: When True, the commit holds a `trueup.toml`.

    Returns:
        The repository root, `tmp_path / "repo"`.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    (root / "src").mkdir()
    (root / "src" / "app.txt").write_text("app\n", encoding="utf-8")
    if config:
        _write_config(root)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "start"],
        cwd=root,
        check=True,
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    return root


def _start(root: Path, session_id: str = "s1", source: str = "startup") -> str:
    """Run the SessionStart hook for one session.

    Args:
        root: The repository root, also the hook's `cwd`.
        session_id: The session id to send.
        source: The SessionStart source to send.

    Returns:
        What the hook printed.
    """
    code, out = _run(
        "session", {"cwd": str(root), "session_id": session_id, "source": source}
    )
    assert code == 0
    return out


def _stop(root: Path, session_id: str = "s1", active: bool = False) -> str:
    """Run the Stop hook for one session.

    Args:
        root: The repository root, also the hook's `cwd`.
        session_id: The session id to send.
        active: The `stop_hook_active` value to send.

    Returns:
        What the hook printed.
    """
    code, out = _run(
        "stop",
        {"cwd": str(root), "session_id": session_id, "stop_hook_active": active},
    )
    assert code == 0
    return out


def _edit_payload(root: Path, relative: str, new: str, session_id: str = "s1") -> dict:
    """Build one PostToolUse payload for an `Edit` of a path under `root`.

    Args:
        root: The repository root, also the hook's `cwd`.
        relative: The edited path, relative to `root`.
        new: The `new_string` of the edit.
        session_id: The session id to send.

    Returns:
        The payload dict.
    """
    return {
        "cwd": str(root),
        "session_id": session_id,
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(root / relative),
            "old_string": "",
            "new_string": new,
        },
    }


def _interface(payload: dict) -> str:
    """Run the PostToolUse interface hook on one payload.

    Args:
        payload: The payload dict.

    Returns:
        What the hook printed.
    """
    code, out = _run("interface", payload)
    assert code == 0
    return out


def test_session_writes_the_snapshot_and_resume_keeps_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStart writes the snapshot; `resume` keeps the file, `startup` replaces it.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    assert "tier" in _start(root)
    path = tmp_path / "data" / "sessions" / "s1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["dirty"] == {}
    (root / "src" / "late.txt").write_text("late\n", encoding="utf-8")
    _start(root, source="resume")
    assert json.loads(path.read_text(encoding="utf-8"))["dirty"] == {}
    _start(root, source="startup")
    assert list(json.loads(path.read_text(encoding="utf-8"))["dirty"]) == [
        "src/late.txt"
    ]


def test_stop_blocks_on_a_new_scratch_file_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop without the flag gives one `block` decision that names the new scratch file.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    _start(root)
    (root / "src" / "tmp_notes.txt").write_text("x\n", encoding="utf-8")
    out = _stop(root)
    decision = json.loads(out)
    assert decision["decision"] == "block"
    first, *rest = decision["reason"].splitlines()
    assert first.startswith("trueup: 1 finding(s) in files changed this session.")
    assert "[[keep]]" in first
    assert rest == [
        "- scratch:src/tmp_notes.txt: 'tmp_notes.txt' looks like a scratch file; "
        "git does not track it"
    ]


def test_stop_is_silent_when_stop_hook_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `stop_hook_active` true and a dirty scratch file, Stop prints nothing (I-15).

    arch: D6.2, D6.3, D6.4, I-15
    """
    root = _session_repo(tmp_path, monkeypatch)
    _start(root)
    (root / "src" / "tmp_notes.txt").write_text("x\n", encoding="utf-8")
    assert _stop(root, active=True) == ""
    assert _stop(root) != ""


def test_stop_is_silent_without_trueup_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository with no `trueup.toml` gets no Stop output, even with a new scratch file.

    arch: D6.2, D6.3, D6.4, I-22
    """
    root = _session_repo(tmp_path, monkeypatch, config=False)
    _start(root)
    (root / "src" / "tmp_notes.txt").write_text("x\n", encoding="utf-8")
    assert _stop(root) == ""


def test_stop_ignores_unchanged_pre_session_dirt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scratch file from before the session, not changed since, does not block.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    (root / "src" / "tmp_old.txt").write_text("old\n", encoding="utf-8")
    _start(root)
    assert _stop(root) == ""
    (root / "src" / "tmp_old.txt").write_text("changed in session\n", encoding="utf-8")
    assert "scratch:src/tmp_old.txt" in _stop(root)


def test_stop_lists_ten_findings_then_a_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With more than 10 findings, Stop lists 10 and then one line with the rest.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    _start(root)
    for number in range(12):
        (root / "src" / f"tmp_{number:02}.txt").write_text("x\n", encoding="utf-8")
    lines = json.loads(_stop(root))["reason"].splitlines()
    assert lines[0].startswith("trueup: 12 finding(s)")
    assert len(lines) == 12
    assert lines[-1].startswith("- ... 2 more: run python3 ")
    assert lines[-1].endswith("trueup check --changed")


def test_stop_is_silent_on_a_readme_edit_that_the_full_check_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session that edits only a correct `README.md` gets no Stop block from a drift row (D6.3, D6.5).

    `README.md` installs `foo`, the `[project]` name in `pyproject.toml`,
    which the session does not change. The scoped run must read
    `pyproject.toml` to see that, as the full run does.

    arch: D6.17, D6.3, D6.5
    """
    root = _session_repo(tmp_path, monkeypatch)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    readme = "# foo\n\nA tool.\n\n## Install\n\n```sh\npip install foo\n```\n"
    (root / "README.md").write_text(readme, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "foo"],
        cwd=root,
        check=True,
    )
    _start(root)
    (root / "README.md").write_text(readme + "\nMore text.\n", encoding="utf-8")
    assert changes.session_set(root, "s1") == frozenset({"README.md"})
    assert _stop(root) == ""


def test_stop_and_interface_fail_open_on_bad_json(tmp_path: Path) -> None:
    """Invalid JSON gives exit 0 and no output for `stop` and `interface`.

    arch: D6.2, D6.3, D6.4, I-22
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    for event in ("stop", "interface"):
        assert _run_raw(event, "{not valid json") == (0, "")
        assert _run_raw(event, "[1]") == (0, "")


def _tree_state(root: Path) -> dict[str, int]:
    """List every file below `root`, `.git` included, with its mtime.

    Args:
        root: The directory to walk.

    Returns:
        A map from each relative file path to its `st_mtime_ns`.
    """
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in root.rglob("*")
        if path.is_file()
    }


def _porcelain(root: Path) -> str:
    """Give `git status --porcelain` for `root`, with no optional locks.

    Args:
        root: The repository root.

    Returns:
        The status text.
    """
    return subprocess.run(
        ["git", "--no-optional-locks", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_each_hook_writes_only_below_plugin_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each hook leaves `git status`, `.git/index` and every file of the target tree unchanged (I-14).

    arch: D6.2, D6.3, D6.4, D13.4, I-14
    """
    root = _session_repo(tmp_path, monkeypatch)
    (root / "src" / "app.txt").write_text(
        "edited before the session\n", encoding="utf-8"
    )
    status_before = _porcelain(root)
    tree_before = _tree_state(root)
    assert "tier" in _start(root)
    assert _porcelain(root) == status_before
    assert _tree_state(root) == tree_before
    (root / "src" / "tmp_notes.txt").write_text("x\n", encoding="utf-8")
    status_before = _porcelain(root)
    tree_before = _tree_state(root)
    payloads = [
        (
            "guard",
            {
                "cwd": str(root),
                "session_id": "s1",
                "tool_name": "Write",
                "tool_input": {"file_path": str(root / "src" / "tmp_more.txt")},
            },
        ),
        ("interface", _edit_payload(root, "src/cli.py", "p.add_argument('--x')")),
        ("stop", {"cwd": str(root), "session_id": "s1"}),
    ]
    for event, payload in payloads:
        code, out = _run(event, payload)
        assert code == 0
        assert out, event
        assert _porcelain(root) == status_before, event
        assert _tree_state(root) == tree_before, event
    written = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "data").rglob("*")
        if path.is_file()
    )
    assert written == ["data/hook-times.jsonl", "data/sessions/s1.json"]
    lines = (tmp_path / "data" / "hook-times.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line)["event"] for line in lines.splitlines()]
    assert events == ["session", *(event for event, _payload in payloads)]


def test_interface_reminds_once_per_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI edit gets one reminder; the same path again, or a plain edit, gets none.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    _start(root)
    out = _interface(_edit_payload(root, "src/cli.py", "parser.add_argument('--x')"))
    context = json.loads(out)["hookSpecificOutput"]
    assert context["hookEventName"] == "PostToolUse"
    assert context["additionalContext"].startswith(
        "trueup: src/cli.py changes a public interface (Python CLI)."
    )
    assert _interface(_edit_payload(root, "src/cli.py", "p.add_parser('y')")) == ""
    assert _interface(_edit_payload(root, "src/other.py", "x = 1")) == ""
    assert "src/other_cli.py" in _interface(
        _edit_payload(root, "src/other_cli.py", "@click.command()")
    )


def test_interface_is_silent_when_readme_or_reference_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A change to `README.md` or a `docs/reference/**` file in the session stops the reminder.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    _start(root)
    (root / "README.md").write_text("# app\n", encoding="utf-8")
    assert _interface(_edit_payload(root, "src/cli.py", "p.add_argument(")) == ""
    (root / "README.md").unlink()
    (root / "docs" / "reference").mkdir(parents=True)
    (root / "docs" / "reference" / "cli.md").write_text("# cli\n", encoding="utf-8")
    assert _interface(_edit_payload(root, "src/cli.py", "p.add_argument(")) == ""
    (root / "docs" / "reference" / "cli.md").unlink()
    assert "src/cli.py" in _interface(
        _edit_payload(root, "src/cli.py", "p.add_argument(")
    )


def test_interface_is_silent_outside_root_and_without_plugin_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path outside the root, or a session with no `CLAUDE_PLUGIN_DATA`, gets no reminder.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    payload = _edit_payload(root, "src/cli.py", "p.add_argument(")
    payload["tool_input"]["file_path"] = str(tmp_path / "elsewhere" / "cli.py")
    assert _interface(payload) == ""
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA")
    assert _interface(_edit_payload(root, "src/cli.py", "p.add_argument(")) == ""


@pytest.mark.parametrize(
    ("tool_name", "relative", "tool_input", "signal"),
    [
        ("Write", "pkg/__init__.py", {"content": "__all__ = ['x']"}, "Python exports"),
        (
            "Write",
            "pyproject.toml",
            {"content": "[project.scripts]\nx = 'y'"},
            "Python scripts",
        ),
        (
            "Edit",
            "pyproject.toml",
            {"old_string": "", "new_string": 'name = "x"'},
            "Python scripts",
        ),
        (
            "Write",
            "pyproject.toml",
            {"content": '[tool.poetry]\nname = "x"\n'},
            None,
        ),
        (
            "Write",
            "pyproject.toml",
            {"content": '[tool.x]\nname = "y"\n\n[project]\nname = "z"\n'},
            "Python scripts",
        ),
        ("Write", "package.json", {"content": '{"bin": {}}'}, "Node"),
        ("Write", "src/main.rs", {"content": "#[command(version)]"}, "Rust CLI"),
        (
            "MultiEdit",
            "cmd/root.go",
            {"edits": [{"old_string": "a", "new_string": "cmd.Flags().String()"}]},
            "Go CLI",
        ),
        ("Write", "src/main.rs", {"content": "fn main() {}"}, None),
        ("Write", "package.json", {"content": "{}"}, None),
        ("Read", "src/cli.py", {"content": "add_argument("}, None),
    ],
)
def test_interface_signals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    relative: str,
    tool_input: dict,
    signal: str | None,
) -> None:
    """Each row of the D6.4 signal table fires from its static text, and plain text does not.

    arch: D6.2, D6.3, D6.4
    """
    root = _session_repo(tmp_path, monkeypatch)
    payload = {
        "cwd": str(root),
        "session_id": "s1",
        "tool_name": tool_name,
        "tool_input": {"file_path": str(root / relative), **tool_input},
    }
    out = _interface(payload)
    if signal is None:
        assert out == ""
    else:
        assert f"({signal})" in out


def test_stop_on_this_repo_records_its_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run of `python3 trueup hook stop` on a fixture repo, with one changed file, records its time (I-17).

    The bound itself is a field measurement, not a unit-suite assertion: a
    wall-clock bound here fails on a loaded machine (D13.4). The hook
    writes one `stop` line to `hook-times.jsonl`, and
    `scripts/hook_times.py` reads the log of real sessions.

    The repo has two commits, so `HEAD~1` exists on every checkout,
    also a shallow CI clone of this repository. The test writes a
    snapshot of the clean tree, moves its head to `HEAD~1`, and keeps
    the true sha of each path that the last commit changed, except one
    `.py` path. So `session_set` holds that one path.

    arch: D6.2, D6.3, D6.4, D13.4, I-17
    arch: D15.38
    """
    root = _session_repo(tmp_path, monkeypatch)
    (root / "src" / "app.py").write_text('"""The app."""\n', encoding="utf-8")
    (root / "src" / "app.txt").write_text("app, two\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second"],
        cwd=root,
        check=True,
    )
    changes.write_snapshot(root, "timing")
    snapshot = changes.read_snapshot("timing")
    assert snapshot is not None
    assert snapshot.dirty == {}
    parent = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    snapshot.head = parent
    changes._save(changes.snapshot_path("timing"), snapshot)  # type: ignore[arg-type]
    paths = sorted(changes.session_set(root, "timing"))
    assert paths == ["src/app.py", "src/app.txt"]
    snapshot.dirty = dict(zip(paths, changes._blob_shas(root, paths)))
    snapshot.dirty["src/app.py"] = "0" * 40
    changes._save(changes.snapshot_path("timing"), snapshot)  # type: ignore[arg-type]
    assert changes.session_set(root, "timing") == {"src/app.py"}
    payload = json.dumps({"cwd": str(root), "session_id": "timing"})
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "trueup"), "hook", "stop"],
        cwd=root,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    log = (tmp_path / "data" / "hook-times.jsonl").read_text(encoding="utf-8")
    entries = [json.loads(line) for line in log.splitlines()]
    assert [entry["event"] for entry in entries] == ["stop"]
    assert isinstance(entries[0]["seconds"], float)
    assert entries[0]["seconds"] >= 0


_OLD = datetime(2015, 1, 1, tzinfo=timezone.utc)
"""A first-release date far older than the D7.7 young window."""


def _fake_registry(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, object] | None = None
) -> list[tuple[str, str]]:
    """Patch `registry.first_release` with a fake that opens no network connection.

    Args:
        monkeypatch: The pytest fixture.
        answers: The answer for each package name. A name not in it gets
            `_OLD`.

    Returns:
        The list of `(ecosystem, name)` calls, filled as the hook runs.
    """
    calls: list[tuple[str, str]] = []
    table = answers or {}

    def fake(ecosystem: str, name: str, *, deadline: float) -> object:
        calls.append((ecosystem, name))
        return table.get(name, _OLD)

    monkeypatch.setattr(registry, "first_release", fake)
    return calls


def _guard_bash(root: Path, command: str) -> tuple[int, str]:
    """Run the guard on one `Bash` call in `root`.

    Args:
        root: The repository root, with a `trueup.toml`.
        command: The Bash command line.

    Returns:
        The exit code and everything printed to stdout.
    """
    return _run(
        "guard",
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": command}},
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pip install foo", ("pypi", "foo")),
        ("pip3 install foo", ("pypi", "foo")),
        ("python -m pip install foo", ("pypi", "foo")),
        ("python3 -m pip install foo", ("pypi", "foo")),
        ("uv pip install foo", ("pypi", "foo")),
        ("uv add foo", ("pypi", "foo")),
        ("poetry add foo", ("pypi", "foo")),
        ("pdm add foo", ("pypi", "foo")),
        ("npm install foo", ("npm", "foo")),
        ("npm i foo", ("npm", "foo")),
        ("npm add foo", ("npm", "foo")),
        ("pnpm add foo", ("npm", "foo")),
        ("yarn add foo", ("npm", "foo")),
        ("bun add foo", ("npm", "foo")),
        ("cargo add foo", ("crates", "foo")),
        ("go get example.com/foo@v1.2.3", ("go", "example.com/foo")),
        ("go install example.com/foo@latest", ("go", "example.com/foo")),
        ("composer require acme/foo", ("packagist", "acme/foo")),
    ],
)
def test_install_table_rows(command: str, expected: tuple[str, str]) -> None:
    """Each row of the D7.7 table makes its segment an install of its ecosystem.

    arch: D7.7
    """
    assert hooks._install_names(command) == [expected]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("sudo pip install foo", [("pypi", "foo")]),
        ("env pip install foo", [("pypi", "foo")]),
        ("PIP_NO_CACHE=1 FOO=bar pip install foo", [("pypi", "foo")]),
        ("sudo env A=1 npm i foo", [("npm", "foo")]),
        ("cd x && pip install foo; npm i bar | cat", [("pypi", "foo"), ("npm", "bar")]),
        ("pip install foo;npm i bar>log", [("pypi", "foo"), ("npm", "bar")]),
        ("(pip install foo) 2>&1", [("pypi", "foo")]),
        ("pip install foo 2>&1 | tail", [("pypi", "foo")]),
        ("pip install foo 2>/dev/null", [("pypi", "foo")]),
        ("npm install foo 2>&1", [("npm", "foo")]),
        ("npm install foo 1>log 0<in", [("npm", "foo")]),
        ("pip install foo2>&1", [("pypi", "foo2")]),
        ("pip install -U --quiet foo", [("pypi", "foo")]),
        ("pip install -r requirements.txt foo", [("pypi", "foo")]),
        ("pip install --requirement req.txt -c c.txt foo", [("pypi", "foo")]),
        ("pip install --constraint c.txt -e src foo", [("pypi", "foo")]),
        ("pip install --editable src -i idx foo", [("pypi", "foo")]),
        ("pip install --index-url idx --extra-index-url idx2 foo", [("pypi", "foo")]),
        ("npm install --registry reg foo", [("npm", "foo")]),
        ("cargo add foo --features derive -F extra", [("crates", "foo")]),
        ("pip install ./pkg /abs/pkg ~/pkg foo", [("pypi", "foo")]),
        ("pip install https://x.org/a.zip git+https://x/y foo", [("pypi", "foo")]),
        ("pip install a-1.0-py3-none-any.whl b.tar.gz c.tgz foo", [("pypi", "foo")]),
        (
            "pip install 'foo[extra]>=1' bar==2 'baz; python_version>\"3\"'",
            [
                ("pypi", "foo"),
                ("pypi", "bar"),
                ("pypi", "baz"),
            ],
        ),
        (
            "pip install qux~=1 zap!=2 'zip<3' zop@4",
            [
                ("pypi", "qux"),
                ("pypi", "zap"),
                ("pypi", "zip"),
                ("pypi", "zop"),
            ],
        ),
        (
            "npm i foo@1.2 @scope/bar@^2 @scope/baz",
            [
                ("npm", "foo"),
                ("npm", "@scope/bar"),
                ("npm", "@scope/baz"),
            ],
        ),
        ("cargo add foo@1.0", [("crates", "foo")]),
        ("composer require acme/foo:^1.0", [("packagist", "acme/foo")]),
        ("go get example.com/foo", []),
        ("go install mytool/cmd@latest", []),
        ("go install ./...", []),
        ("npm install", []),
        ("pip install -r requirements.txt", []),
        ("pip install foo foo==2", [("pypi", "foo")]),
        ("echo pip install foo", []),
        ("pip list", []),
        ("pip install 'unclosed", []),
    ],
)
def test_install_skip_rules(command: str, expected: list[tuple[str, str]]) -> None:
    """The D7.7 strip, skip and version rules give exactly the package names.

    arch: D7.7
    """
    assert hooks._install_names(command) == expected


def test_install_guard_does_not_check_a_redirect_file_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file descriptor before a redirect is not sent to the registry as a name.

    arch: D7.7
    """
    calls = _fake_registry(monkeypatch, {"2": registry.Unknown()})
    assert (
        hooks._check_install(
            "pip install requests 2>&1 | tail -5",
            Config(guard_registry=True),
            Path("."),
        )
        is None
    )
    assert calls == [("pypi", "requests")]


def test_install_guard_denies_unknown_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name the registry does not have gives `deny` with the D7.7 text.

    arch: D7.7, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    calls = _fake_registry(monkeypatch, {"reqeusts": registry.Unknown()})
    code, out = _guard_bash(tmp_path, "pip install reqeusts")
    assert code == 0
    assert calls == [("pypi", "reqeusts")]
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"] == (
        "trueup: reqeusts is not on PyPI. Check the spelling. Do not install "
        "a package that you cannot find on the registry."
    )
    assert '"allow"' not in out


def test_install_guard_asks_for_young_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name that first appeared less than 30 days ago gives `ask` with its date and age.

    arch: D7.7, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    first = datetime.now(timezone.utc) - timedelta(days=3, hours=1)
    _fake_registry(monkeypatch, {"fresh": first})
    code, out = _guard_bash(tmp_path, "npm i fresh")
    assert code == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert decision["permissionDecisionReason"] == (
        f"trueup: fresh first appeared on npm on {first.date().isoformat()} "
        "(3 days ago). Check the publisher, the source repository and the "
        "download count before you install it."
    )
    assert '"allow"' not in out


def test_install_guard_is_silent_for_an_old_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package older than 30 days gives no decision and no output.

    arch: D7.7, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    edge = datetime.now(timezone.utc) - timedelta(days=30, minutes=1)
    calls = _fake_registry(monkeypatch, {"edge": edge})
    code, out = _guard_bash(tmp_path, "cargo add serde edge")
    assert code == 0
    assert calls == [("crates", "serde"), ("crates", "edge")]
    assert out == ""


def test_install_guard_unreachable_gives_system_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreachable registry gives no decision and one `systemMessage`.

    arch: D7.7, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    _fake_registry(monkeypatch, {"acme/foo": registry.Unreachable("timeout")})
    code, out = _guard_bash(tmp_path, "composer require acme/foo")
    assert code == 0
    assert json.loads(out) == {
        "systemMessage": "trueup: Packagist did not answer; the install guard "
        "did not check acme/foo."
    }
    assert "permissionDecision" not in out
    assert '"allow"' not in out


def test_install_guard_deny_wins_and_keeps_the_unreachable_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown, young and unreachable names in one command give one `deny` line.

    The hook prints one JSON object, so the unreachable note goes at the
    end of the deny reason.

    arch: D7.7, I-29
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    _fake_registry(
        monkeypatch,
        {
            "young": datetime.now(timezone.utc) - timedelta(days=1),
            "ghost": registry.Unknown(),
            "far": registry.Unreachable("timeout"),
        },
    )
    code, out = _guard_bash(tmp_path, "pip install young ghost far")
    assert code == 0
    assert len(out.splitlines()) == 1
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "ghost is not on PyPI" in reason
    assert "young" not in reason
    assert reason.endswith("PyPI did not answer; the install guard did not check far.")
    assert '"allow"' not in out


def test_install_guard_deny_wins_over_the_scratch_git_add_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry deny wins over the scratch `git add` ask of `_check_bash` (D15.31).

    arch: D7.7, D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    calls = _fake_registry(monkeypatch, {"ghost": registry.Unknown()})
    code, out = _guard_bash(tmp_path, "git add tmp_notes.txt && pip install ghost")
    assert code == 0
    assert calls == [("pypi", "ghost")]
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "ghost is not on PyPI" in decision["permissionDecisionReason"]


def test_scratch_git_add_ask_stands_when_the_install_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scratch `git add` ask is the answer when the install guard finds nothing.

    arch: D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    _fake_registry(monkeypatch)
    _code, out = _guard_bash(tmp_path, "git add tmp_notes.txt && pip install fine")
    assert _decision(out) == "ask"
    assert "tmp_notes.txt" in out


def test_install_guard_inactive_without_trueup_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `trueup.toml`, an install gives no lookup and no output (I-22).

    arch: D7.7
    """
    _git_init(tmp_path)
    calls = _fake_registry(monkeypatch, {"ghost": registry.Unknown()})
    code, out = _guard_bash(tmp_path, "pip install ghost")
    assert (code, out, calls) == (0, "", [])


def test_install_guard_imports_registry_only_for_an_install() -> None:
    """`trueup.registry` loads only when a Bash segment is an install.

    A fresh interpreter is needed, because this test module imports
    `registry` itself.

    arch: D7.7
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, trueup.hooks as h\n"
            "assert 'trueup.registry' not in sys.modules\n"
            "from pathlib import Path\n"
            "from trueup.config import Config\n"
            "cfg = Config(guard_registry=True)\n"
            "assert h._check_install('ls -la && git status', cfg, Path('.')) is None\n"
            "assert 'trueup.registry' not in sys.modules\n",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_hook_log_is_written_only_when_the_gate_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hook in a repo with no `trueup.toml` adds no line to `hook-times.jsonl`.

    arch: D15.7, D15.24
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    code, _out = _run("guard", {"cwd": str(repo)})
    assert code == 0
    assert not (data / "hook-times.jsonl").exists()
    _write_config(repo)
    _run("guard", {"cwd": str(repo)})
    assert (
        len((data / "hook-times.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    )


def test_hook_log_over_1_mib_keeps_its_last_10000_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log over 1 MiB is cut to its last 10,000 lines, and the new line is last.

    arch: D15.7, D15.24
    """
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    log = data / "hook-times.jsonl"
    log.write_text(
        "".join(f"{'x' * 90} {n}\n" for n in range(20_000)), encoding="utf-8"
    )
    assert log.stat().st_size > 1024 * 1024
    hooks._record_time("guard", 0.01)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10_000
    assert json.loads(lines[-1])["event"] == "guard"
    assert lines[0].endswith(" 10001")
    assert [p.name for p in data.iterdir()] == ["hook-times.jsonl"]


def test_guard_leaves_an_existing_scratch_named_file_alone(tmp_path: Path) -> None:
    """A `Write` to a scratch-named file that exists gives no decision; a new one gives `ask`.

    arch: D15.31
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("old\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("old\n", encoding="utf-8")
    assert _guard_write(tmp_path, "docs/notes.md") == ""
    assert _guard_write(tmp_path, "notes.md") == ""
    assert _decision(_guard_write(tmp_path, "docs/notes2.md")) == "ask"
    assert _decision(_guard_write(tmp_path, "docs/tmp_new.md")) == "ask"


@pytest.mark.parametrize(
    ("command", "decision"),
    [
        ("echo git add notes.md", None),
        ("printf 'git add notes.md'", None),
        ("cd d && git add notes.md", "ask"),
        ("cd d; git add notes.md", "ask"),
        ("ls | git add notes.md", "ask"),
        ("sudo git add notes.md", "ask"),
        ("env GIT_X=1 git add notes.md", "ask"),
        ("GIT_X=1 git add notes.md", "ask"),
        ("git add src/app.py && git add notes.md", "ask"),
        ("git add src/app.py", None),
    ],
)
def test_git_add_is_read_per_shell_segment(
    tmp_path: Path, command: str, decision: str | None
) -> None:
    """Only a segment that starts with `git add` counts (D15.35).

    arch: D15.35
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    _code, out = _guard_bash(tmp_path, command)
    assert _decision(out) == decision


def test_git_add_paths_cut_at_each_segment() -> None:
    """`_git_add_paths` lists the paths of each `git add` segment and no word of another segment.

    arch: D15.35
    """
    assert hooks._git_add_paths("echo git add a.txt") == []
    assert hooks._git_add_paths("cd d && git add a.txt -f b.txt") == ["a.txt", "b.txt"]
    assert hooks._git_add_paths("git add a.txt; git add c.txt") == ["a.txt", "c.txt"]
    assert hooks._git_add_paths("git add 'unclosed") == []


def test_install_guard_is_off_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `[guard] registry` unset, an install gives no lookup and no output (D15.32).

    arch: D15.32
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    calls = _fake_registry(monkeypatch, {"ghost": registry.Unknown()})
    assert _guard_bash(tmp_path, "pip install ghost") == (0, "")
    assert calls == []


@pytest.mark.parametrize(
    "command",
    [
        "pip install --index-url https://pypi.corp.example/simple ghost",
        "pip install --extra-index-url https://pypi.corp.example/simple ghost",
        "pip install -i https://pypi.corp.example/simple ghost",
        "npm install --registry https://npm.corp.example ghost",
    ],
)
def test_install_guard_skips_a_package_from_a_private_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """An index flag in the command means no public lookup (D15.32).

    arch: D15.32
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    calls = _fake_registry(monkeypatch, {"ghost": registry.Unknown()})
    assert _guard_bash(tmp_path, command) == (0, "")
    assert calls == []


def test_install_guard_reads_the_npmrc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scope with `@s:registry=` in `.npmrc` and any `registry=` line skip the lookup (D15.32).

    arch: D15.32
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(guard_registry=True))
    calls = _fake_registry(monkeypatch, {"ghost": registry.Unknown()})
    (tmp_path / ".npmrc").write_text(
        "@corp:registry=https://npm.corp.example\n", encoding="utf-8"
    )
    assert _guard_bash(tmp_path, "npm install @corp/ghost") == (0, "")
    assert calls == []
    _code, out = _guard_bash(tmp_path, "npm install ghost")
    assert _decision(out) == "deny"
    assert calls == [("npm", "ghost")]
    calls.clear()
    (tmp_path / ".npmrc").write_text(
        "registry=https://npm.corp.example\n", encoding="utf-8"
    )
    assert _guard_bash(tmp_path, "npm install ghost") == (0, "")
    assert calls == []


def test_install_guard_skips_a_private_package_glob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name that matches `[guard] private_packages` gets no lookup; other names still do (D15.32).

    arch: D15.32
    """
    _git_init(tmp_path)
    _write_config(
        tmp_path,
        Config(guard_registry=True, guard_private_packages=("corp-*", "@corp/*")),
    )
    calls = _fake_registry(monkeypatch, {"corp-tool": registry.Unknown()})
    assert _guard_bash(tmp_path, "pip install corp-tool") == (0, "")
    assert calls == []
    _fake_registry(monkeypatch, {"other": registry.Unknown()})
    _code, out = _guard_bash(tmp_path, "pip install corp-tool other")
    assert _decision(out) == "deny"
    assert "other is not on PyPI" in out
    assert "corp-tool" not in out


def test_session_hint_names_the_command_that_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The closing line says `trueup` when it is on `PATH`, else `python3 <launcher>` (D15.34).

    arch: D15.34
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/usr/bin/trueup")
    _code, out = _run("session", {"cwd": str(tmp_path)})
    assert out.splitlines()[-1].startswith("Run trueup check before you finish.")
    monkeypatch.setattr(hooks.shutil, "which", lambda name: None)
    _code, out = _run("session", {"cwd": str(tmp_path)})
    launcher = Path(hooks.__file__).resolve().parent
    assert out.splitlines()[-1].startswith(
        f"Run python3 {launcher} check before you finish."
    )


def test_session_tier_and_docs_are_the_ones_in_force(tmp_path: Path) -> None:
    """With `tier = "auto"` the notice names the survey tier and the docs mode that follows (D15.34).

    arch: D15.34
    """
    _git_init(tmp_path)
    _write_config(tmp_path, Config(profile="minimal", docs="full"))
    _code, out = _run("session", {"cwd": str(tmp_path)})
    assert out.splitlines()[0] == "trueup: profile minimal, tier T0, docs full."
    assert "auto" not in out.splitlines()[0]
