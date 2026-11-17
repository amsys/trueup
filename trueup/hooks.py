"""Session, guard, stop and interface hooks for the trueup Claude Code plugin (arch: D5.8).

`run` is the one entry point `cli.py`'s `hook` subcommand calls. It reads
one JSON object from stdin and dispatches `"session"` to `_session`,
`"guard"` to `_guard`, `"stop"` to `_stop` (D6.3) and `"interface"` to
`_interface` (D6.4). All four fail open: a missing `trueup.toml` at the
discovered root, invalid JSON on stdin, or any other exception each leave
stdout empty and give exit 0 (I-22). The gate is the target's own
`trueup.toml`: a user default file never turns a hook on (D14.11). Every helper below builds its full
output before the one `print` call that can follow it, so a failure never
leaves a partial line on stdout. The only files a hook writes are the
session snapshot and the timing log below `$CLAUDE_PLUGIN_DATA` (I-14,
D6.2, D13.4).

The guard reuses `hygiene.looks_scratch` and `hygiene.scratch_exempt` for
its scratch-name check (D5.4), so a name the `check` command calls scratch
is the same name the guard blocks, from one pattern list, and a path that
`ignore`, `[scratch] allow` or `.scratch/` exempts is let through by both.
Under the docs directory, the guard also drops the `v<n>` copy marker, as
`check` does (D14.11, D14.12 C2). `hygiene` imports `survey`, which
imports `rulesets`, so `_scratch_denied` and `base_root_allow` import them
inside the function body rather than at module level: importing this
module alone never pulls in `survey` or `rulesets` (LOW-7).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import IO

from trueup import changes
from trueup import config as config_mod

_CODE_ROOT_ALLOW: tuple[str, ...] = (
    "README*",
    "LICENSE*",
    "COPYING*",
    "CHANGELOG*",
    "CITATION.cff",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "Makefile",
    "justfile",
    ".env.example",
    "AGENTS.md",
    "CLAUDE.md",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "go.sum",
    "composer.json",
    "composer.lock",
    "trueup.toml",
    "ref_check.py",
    "ref_check.toml",
    ".pre-commit-config.yaml",
    ".scratch",
    ".claude",
    ".github",
    "CODEOWNERS",
    "Dockerfile",
    "Containerfile",
    ".dockerignore",
    ".python-version",
    ".nvmrc",
    ".tool-versions",
    ".gitmodules",
    "tsconfig.json",
    "tsconfig.*.json",
    "requirements*.txt",
    "setup.py",
    "setup.cfg",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".travis.yml",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    ".circleci",
    ".woodpecker.yml",
    ".drone.yml",
)
"""The fixed part of the code base list of root entries (D5.8, D14.11).
`base_root_allow` adds the standard root pages, the manifests and the
lockfiles to it."""

_SHELL_BREAKS: frozenset[str] = frozenset({"&&", "||", ";", "|", ">", ">>", "<"})
"""Tokens that end a `git add` file list in one Bash command line."""

_STOP_LIST_LIMIT = 10
"""The Stop guard lists at most this many findings (D6.3)."""

_REPLACE_SOURCES: frozenset[str] = frozenset({"startup", "clear"})
"""SessionStart sources that replace a snapshot file that exists (D6.2)."""

_PROJECT_NAME_LINE = re.compile(r"^\s*name\s*=")
"""A `name = ...` line, as the `[project]` table of `pyproject.toml` has."""

_TOML_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$")
"""A TOML table header line, `[table]` or `[[table]]`; group 1 is the name."""


def base_root_allow(cfg: config_mod.Config) -> tuple[str, ...]:
    """Give the base list of root-entry globs that the guard allows (D14.11).

    `[root] allow` and the entries on disk extend this list; they are not
    part of it.

    Args:
        cfg: The effective config.

    Returns:
        `cfg.root_base` when the config sets it. Otherwise the code list:
        `_CODE_ROOT_ALLOW`, each standard root page name of
        `layout._STANDARD_ROOT_NAMES` as a glob that ignores case,
        `survey.MANIFEST_NAMES` and `hygiene._LOCKFILE_NAMES`, in that
        order, with no duplicates.
    """
    if cfg.root_base is not None:
        return cfg.root_base
    from trueup import hygiene, layout, survey

    globs = (
        *_CODE_ROOT_ALLOW,
        *(_any_case(name) for name in sorted(layout._STANDARD_ROOT_NAMES)),
        *survey.MANIFEST_NAMES,
        *sorted(hygiene._LOCKFILE_NAMES),
    )
    return tuple(dict.fromkeys(globs))


def _any_case(name: str) -> str:
    """Give an `fnmatch` glob that matches `name` in any letter case (D14.11).

    Args:
        name: A plain file name with no glob characters.

    Returns:
        The name with each letter `c` written as `[cC]`.
    """
    return "".join(
        f"[{char.lower()}{char.upper()}]" if char.isalpha() else char for char in name
    )


def run(event: str, stdin: IO[str]) -> int:
    """Run one hook event and print what it decides.

    Args:
        event: `"session"`, `"guard"`, `"stop"` or `"interface"`, from the
            CLI's `hook` subcommand.
        stdin: The stream to read the hook's JSON payload from.

    Returns:
        0 always: each hook fails open on any problem (D5.8, I-22).
    """
    start = time.perf_counter()
    gated = False
    try:
        gated = _dispatch(event, stdin)
    except Exception:
        return 0
    finally:
        if gated:
            _record_time(event, time.perf_counter() - start)
    return 0


def _dispatch(event: str, stdin: IO[str]) -> bool:
    """Read the payload and run one hook event.

    The target's own `trueup.toml` is the gate (D14.11, I-22): without it,
    the hook does nothing, also when a user default file exists. With it,
    each hook gets the effective config of every layer.

    Args:
        event: The hook event name, as `run` takes it.
        stdin: The stream to read the hook's JSON payload from.

    Returns:
        `True` when the gate passed, that is, the root holds a
        `trueup.toml`; `run` writes a timing line only then (D15.24). A file
        that is not valid prints one notice on `session`, stays silent on
        the other events, and counts as passed (D15.7).
    """
    raw = stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        return False
    root = _find_root(payload)
    if root is None:
        return False
    try:
        target = config_mod.load_target(root)
    except config_mod.ConfigError as error:
        if event == "session":
            print(
                f"trueup: trueup.toml is not valid: {error}; "
                "the trueup hooks are off until it is fixed"
            )
        return True
    if target is None:
        return False
    cfg = config_mod.load(root)
    if cfg is None:
        return True
    if event == "session":
        _session(root, cfg, payload)
    elif event == "guard":
        _guard(root, cfg, payload)
    elif event == "stop":
        _stop(root, payload)
    elif event == "interface":
        _interface(root, payload)
    return True


def _record_time(event: str, seconds: float) -> None:
    """Add one line to `$CLAUDE_PLUGIN_DATA/hook-times.jsonl` (D13.4).

    The line is `{"date": ..., "event": ..., "seconds": ...}`. The time
    starts after the interpreter and the imports are ready, so it is less
    than the wall time Claude Code waits. Nothing is written when
    `$CLAUDE_PLUGIN_DATA` is not set. A write error is ignored (I-22).

    Args:
        event: The hook event name.
        seconds: The time `run` took to dispatch the event.
    """
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return
    line = json.dumps(
        {
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            "seconds": round(seconds, 4),
        }
    )
    try:
        Path(data).mkdir(parents=True, exist_ok=True)
        with (Path(data) / "hook-times.jsonl").open("a", encoding="utf-8") as log:
            log.write(line + "\n")
        _cap_log(Path(data) / "hook-times.jsonl")
    except OSError:
        return


_LOG_LIMIT = 1024 * 1024
_LOG_KEEP = 10_000


def _cap_log(log: Path) -> None:
    """Cut the hook log to its last 10,000 lines when it is over 1 MiB (D15.24).

    The cut writes a temp file in the same directory and replaces the log.
    A line lost to a race between two hooks is acceptable.

    Args:
        log: The `hook-times.jsonl` file.
    """
    if log.stat().st_size <= _LOG_LIMIT:
        return
    lines = log.read_text(encoding="utf-8").splitlines(keepends=True)
    temp = log.with_name(log.name + ".tmp")
    temp.write_text("".join(lines[-_LOG_KEEP:]), encoding="utf-8")
    os.replace(temp, log)


def _find_root(payload: dict) -> Path | None:
    """Find the target repository root for one hook payload (D5.8).

    This reads only the session's own `cwd`, never `tool_input`. When the
    trueup skill names a target directory other than the session's `cwd`
    ("the directory the person names"), the guard still keys on `cwd`; it
    then checks the wrong repository, or none, for that target.

    Args:
        payload: The parsed hook JSON. Its `cwd` key, when present and a
            non-empty string, is where the walk starts; otherwise the
            process's own working directory is used.

    Returns:
        The first of that directory and its parents that holds a `.git`
        entry, or `None` when none does.
    """
    start = payload.get("cwd")
    cwd = Path(start) if isinstance(start, str) and start else Path.cwd()
    cwd = cwd.resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _session(root: Path, cfg: config_mod.Config, payload: dict) -> None:
    """Write the session snapshot, then print the SessionStart notice (D5.8, D6.2, D14.10).

    The notice holds the agent rules that the effective config turns on,
    in place of a rules file in the target (D14.10). A failure to write
    the snapshot does not stop the notice: the Stop guard then falls back
    to `working_set(root)`.

    Args:
        root: The repository root `_find_root` found.
        cfg: The effective config.
        payload: The parsed hook JSON, holding `session_id` and `source`.
    """
    try:
        _write_snapshot(root, payload)
    except Exception:  # noqa: S110  # reason: a failed snapshot write must not stop the SessionStart notice (fail open, D6.2)
        pass
    layers = config_mod.load_layers(root)
    profile = layers.profile if layers is not None else "house"
    docs_dir = cfg.layout_docs_dir
    tier = cfg.tier
    if tier == "auto":
        from trueup import survey

        tier = survey.run(root).tier
    docs = config_mod.resolve_docs(cfg, tier)
    lines = [f"trueup: profile {profile}, tier {tier}, docs {docs}."]
    if cfg.languages:
        modes = ", ".join(
            f"{name}={cfg.languages[name]}" for name in sorted(cfg.languages)
        )
        lines.append(f"Languages: {modes}.")
    if profile == "house":
        lines.append(
            "Write docs in Simplified Technical English: short sentences, "
            "active voice, one topic a page."
        )
    if cfg.layout_types:
        lines.append(
            f"Put a page under {docs_dir}/ in one type: tutorial, how-to, "
            "reference or explanation."
        )
    if cfg.refs_comments:
        lines.append(
            "Start a comment marker with a registry word: ref, arch, law, "
            "SAFETY or TODO."
        )
    if cfg.refs_registry:
        where = (
            "the pages named by [refs] declared declare"
            if cfg.refs_declared
            else f"{docs_dir}/ARCHITECTURE.md declares"
        )
        lines.append(f"Cite a design id only in a form that {where}.")
    lines.append(
        "Root rule: a new file at the repository root must be on the base "
        "list or in [root] allow in trueup.toml."
    )
    lines.append(
        "Scratch rule: a tmp/temp/scratch/notes/*.bak/*.orig/*~-style name "
        "goes under .scratch/, never tracked elsewhere."
    )
    lines.append(
        "Managed-file rule: apply rewrites trueup.toml; edit it by hand or "
        "with apply --set."
    )
    lines.append(
        f"Run {_command_hint()} check before you finish. Fix each finding or report it."
    )
    print("\n".join(lines))


def _command_hint() -> str:
    """Give the command that runs trueup from this machine (D15.34).

    Returns:
        `trueup` when it is on `PATH`, else `python3 <launcher>`, where the
        launcher is the directory that holds this module.
    """
    if shutil.which("trueup"):
        return "trueup"
    return f"python3 {Path(__file__).resolve().parent}"


def _write_snapshot(root: Path, payload: dict) -> None:
    """Write the D6.2 snapshot for the session in `payload`, when the source allows it.

    The source `startup` or `clear` replaces the file. Any other source
    writes the file only when none exists, so the first snapshot stays.

    Args:
        root: The repository root.
        payload: The parsed SessionStart JSON.
    """
    session_id = payload.get("session_id")
    path = changes.snapshot_path(session_id)
    if path is None:
        return
    if payload.get("source") in _REPLACE_SOURCES or not os.path.exists(path):
        changes.write_snapshot(root, session_id)


def _stop(root: Path, payload: dict) -> None:
    """The Stop guard: block one time on findings in the session's files (D6.3, D15.33).

    `hooks.json` has no `SubagentStop` entry, so this runs for the main
    session only and a read-only subagent never gets the block.

    When `stop_hook_active` is true, the agent already got the list one
    time, so the hook prints nothing (I-15).

    Args:
        root: The repository root `_find_root` found.
        payload: The parsed hook JSON, holding `session_id` and
            `stop_hook_active`.
    """
    if payload.get("stop_hook_active"):
        return
    paths = changes.session_set(root, payload.get("session_id"))
    if not paths:
        return
    from trueup import report

    plan = report.collect(root, only=paths).plan
    if not plan:
        return
    lines = [
        f"trueup: {len(plan)} finding(s) in files changed this session. Fix them, "
        "or add a [[keep]] entry with a reason in trueup.toml, then finish."
    ]
    lines.extend(
        f"- {finding.id}: {finding.evidence}" for finding in plan[:_STOP_LIST_LIMIT]
    )
    if len(plan) > _STOP_LIST_LIMIT:
        launcher = Path(__file__).resolve().parent
        lines.append(
            f"- ... {len(plan) - _STOP_LIST_LIMIT} more: run python3 {launcher} check --changed"
        )
    print(json.dumps({"decision": "block", "reason": "\n".join(lines)}))


def _interface(root: Path, payload: dict) -> None:
    """The PostToolUse reminder: name a public interface change once per path (D6.4).

    The hook records each path it names in the snapshot's `reminded` list.
    When the session has no snapshot path (`$CLAUDE_PLUGIN_DATA` is not
    set, or the id is not safe), it cannot record the path, so it prints
    nothing.

    Args:
        root: The repository root `_find_root` found.
        payload: The parsed hook JSON, holding `session_id`, `tool_name`
            and `tool_input`.
    """
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return
    signal = _interface_signal(
        relative, _tool_text(payload.get("tool_name"), tool_input)
    )
    if signal is None:
        return
    session_id = payload.get("session_id")
    snapshot = changes.read_snapshot(session_id)
    if snapshot is not None and relative in snapshot.reminded:
        return
    changed = changes.session_set(root, session_id)
    if any(
        item == "README.md" or item.startswith("docs/reference/") for item in changed
    ):
        return
    if not changes.mark_reminded(root, session_id, relative):
        return
    context = (
        f"trueup: {relative} changes a public interface ({signal}). README.md and "
        "docs/reference/ have no change this session. Update them if the "
        "interface changed."
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


def _tool_text(tool_name: object, tool_input: dict) -> str:
    """Give the text that one `Write`, `Edit` or `MultiEdit` call puts in a file (D6.4).

    Args:
        tool_name: The payload's `tool_name`.
        tool_input: The tool's input.

    Returns:
        `content` for `Write`, `old_string` and `new_string` for `Edit`,
        the old and new strings of every edit for `MultiEdit`, and `""` for
        another tool.
    """
    parts: list[object] = []
    if tool_name == "Write":
        parts = [tool_input.get("content")]
    elif tool_name == "Edit":
        parts = [tool_input.get("old_string"), tool_input.get("new_string")]
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        for edit in edits if isinstance(edits, list) else []:
            if isinstance(edit, dict):
                parts.extend([edit.get("old_string"), edit.get("new_string")])
    return "\n".join(part for part in parts if isinstance(part, str))


def _interface_signal(path: str, text: str) -> str | None:
    """Name the D6.4 signal that makes `path` an interface file, from static text only.

    Args:
        path: The repo-relative POSIX path of the changed file.
        text: The text of the tool call, from `_tool_text`.

    Returns:
        The signal name of the first row of the D6.4 table that matches, or
        `None` when no row matches.
    """
    name = Path(path).name
    suffix = Path(path).suffix
    if suffix == ".py" and any(
        token in text for token in ("add_argument(", "add_parser(", "@click.")
    ):
        return "Python CLI"
    if name == "__init__.py" and "__all__" in text:
        return "Python exports"
    if name == "pyproject.toml" and (
        "[project.scripts]" in text or _names_project(text)
    ):
        return "Python scripts"
    if name == "package.json" and any(
        token in text for token in ('"bin"', '"exports"', '"name"')
    ):
        return "Node"
    if suffix == ".rs" and ("#[arg(" in text or "#[command(" in text):
        return "Rust CLI"
    if suffix == ".go" and ("cobra.Command{" in text or ".Flags()." in text):
        return "Go CLI"
    return None


def _guard(root: Path, cfg: config_mod.Config, payload: dict) -> None:
    """The PreToolUse guard: ask on a new root file or a new scratch file or `git add` (D5.8, D14.11, D15.31).

    The scratch rule asks and never denies (D15.31). For `Bash`, the
    install guard (D7.7, D15.32) runs after `_check_bash` and gets its
    ask, so an install deny wins over the scratch ask. The guard gives
    `deny`, `ask` or no decision, never a permission grant (I-29).

    Args:
        root: The repository root `_find_root` found.
        cfg: The effective config, for the root lists and the scratch
            exemptions.
        payload: The parsed hook JSON, holding `tool_name` and `tool_input`.
    """
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    if tool_name == "Write":
        decision = _check_write(root, cfg, tool_input)
        if decision is not None:
            _decide(*decision)
        return
    if tool_name == "Bash":
        decision = _check_bash(cfg, tool_input)
        command = tool_input.get("command")
        if isinstance(command, str) and command:
            decision = _check_install(command, cfg, root, decision)
        if decision is not None:
            _decide(*decision)


def _check_write(
    root: Path, cfg: config_mod.Config, tool_input: dict
) -> tuple[str, str] | None:
    """Check one `Write` call's `file_path` against the scratch and root rules (D5.8, D14.11, D15.31).

    A new file with a scratch-looking name gets `ask`. A file that exists
    is never scratch here: a `Write` to it is an edit. A new root file
    that no list allows gets `ask` too: a list of root names is never
    complete, so the person decides (D14.11). The scratch rule runs first,
    so a new root file with a scratch-looking name gets the one scratch
    question. Bash writes (`touch`, `>`, a heredoc, `mv`) are not seen.

    Args:
        root: The repository root.
        cfg: The effective config, for the root lists and the scratch
            exemptions.
        tool_input: The `Write` tool's input, holding `file_path`.

    Returns:
        `("ask", reason)`, or `None` when the write is allowed. A path outside `root` is never this guard's business, so
        it is left alone.
    """
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if not os.path.exists(path) and _scratch_denied(relative.as_posix(), cfg):
        return (
            "ask",
            f"{path.name} looks like a scratch file; write it under .scratch/ instead, "
            "or add it to [scratch] allow in trueup.toml",
        )
    if (
        path.parent == root
        and not os.path.exists(path)
        and not _root_allowed(path.name, root, cfg)
    ):
        return (
            "ask",
            f"{path.name} is a new file at the repository root, and neither the "
            "base list nor [root] allow in trueup.toml names it; allow it only "
            "when it belongs at the root, and add it to [root] allow to stop "
            "this question",
        )
    return None


def _scratch_denied(path: str, cfg: config_mod.Config) -> bool:
    """Say whether the scratch rule denies one repo path (D5.8, D14.11).

    The guard reads the name only. It takes the `v<n>` exemption under
    `cfg.layout_docs_dir`, at any depth (D15.9), that `hygiene.looks_scratch_path` applies, but
    not that function's `tmp`/`temp`/`scratch` directory rule (D14.22
    item 6, the narrow reading). So the guard and `check` agree on each
    name.

    Imports `trueup.hygiene` on first use, not at module load (LOW-7): a
    caller that never reaches the guard's scratch check pays nothing for
    the `hygiene` -> `survey` -> `rulesets` chain.

    Args:
        path: The repo-relative POSIX path.
        cfg: The effective config, for the docs directory and the
            exemptions of `hygiene.scratch_exempt`.

    Returns:
        True when the basename looks like scratch and the path is not exempt.
    """
    from trueup.hygiene import (
        looks_scratch,
        scratch_exempt,
        under_docs_dir,
        versioned_document,
    )

    name = Path(path).name
    under_docs = under_docs_dir(path, cfg.layout_docs_dir)
    scratch = looks_scratch(name) and not (under_docs and versioned_document(name))
    return scratch and not scratch_exempt(path, cfg)


def _root_allowed(name: str, root: Path, cfg: config_mod.Config) -> bool:
    """Say whether `name` may exist at the repository root (D5.8, D14.11).

    Args:
        name: The candidate root-level basename.
        root: The repository root, whose current entries also count.
        cfg: The effective config, for `base_root_allow` and `root_allow`.

    Returns:
        True when `name` matches `base_root_allow(cfg)`, `cfg.root_allow`,
        or an entry already on disk at `root`.
    """
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in base_root_allow(cfg)):
        return True
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in cfg.root_allow):
        return True
    return (root / name).exists()


def _names_project(text: str) -> bool:
    """Say whether `text` holds the `name` line of the `[project]` table (D6.4).

    A `name = ...` line counts when the last table header above it in
    `text` is `[project]`. It also counts when no header is above it,
    because an `Edit` text is often a part of the file with no header.

    Args:
        text: The text of the tool call, from `_tool_text`.

    Returns:
        True when such a line is in `text`.
    """
    table: str | None = None
    for line in text.splitlines():
        header = _TOML_HEADER.match(line)
        if header:
            table = header.group(1)
        elif table in (None, "project") and _PROJECT_NAME_LINE.match(line):
            return True
    return False


def _check_bash(cfg: config_mod.Config, tool_input: dict) -> tuple[str, str] | None:
    """Check one `Bash` call's `command` for a `git add` of a scratch-looking path (D5.8, D15.31, D15.35).

    Each `git add` token is read as a path relative to the repository
    root, the same exemptions as `_scratch_denied` apply.

    The check reads only the tokens after a `git add` that starts a shell
    segment. Thus `git -C <dir> add`, `git stage` and `git add -A` or
    `--all` pass through unseen.

    Args:
        cfg: The loaded config, for the exemptions.
        tool_input: The `Bash` tool's input, holding `command`.

    Returns:
        `("ask", reason)`, or `None` when no `git add` target looks like a
        scratch file.
    """
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    for path in _git_add_paths(command):
        if _scratch_denied(path.removeprefix("./"), cfg):
            return (
                "ask",
                f"{path} looks like a scratch file; keep it under .scratch/ instead of tracking it",
            )
    return None


def _git_add_paths(command: str) -> list[str]:
    """List the path tokens of each `git add` shell segment in one Bash command line (D5.8, D15.35).

    Args:
        command: The `Bash` tool's `command` string.

    Returns:
        Every non-flag token of each shell segment that starts with `git
        add`, after the leading `sudo`, `env` and `NAME=value` words. A
        word of another segment, such as the arguments of `echo git add x`,
        is not a path. `git -C <dir> add`, `git stage` and a `-A`/`--all`
        token are not recognised (LOW-3, D6.15: documented, not changed).
        An unparsable command gives an empty list.
    """
    return [
        token
        for segment in _shell_segments(command)
        if segment[:2] == ["git", "add"]
        for token in segment[2:]
        if not token.startswith("-")
    ]


_INSTALL_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pypi", ("pip", "install")),
    ("pypi", ("pip3", "install")),
    ("pypi", ("python", "-m", "pip", "install")),
    ("pypi", ("python3", "-m", "pip", "install")),
    ("pypi", ("uv", "pip", "install")),
    ("pypi", ("uv", "add")),
    ("pypi", ("poetry", "add")),
    ("pypi", ("pdm", "add")),
    ("npm", ("npm", "install")),
    ("npm", ("npm", "i")),
    ("npm", ("npm", "add")),
    ("npm", ("pnpm", "add")),
    ("npm", ("yarn", "add")),
    ("npm", ("bun", "add")),
    ("crates", ("cargo", "add")),
    ("go", ("go", "get")),
    ("go", ("go", "install")),
    ("packagist", ("composer", "require")),
)
"""The D7.7 table: the leading tokens of an install segment, per ecosystem."""

_SKIP_NEXT: frozenset[str] = frozenset(
    {
        "-r",
        "--requirement",
        "-c",
        "--constraint",
        "-e",
        "--editable",
        "-i",
        "--index-url",
        "--extra-index-url",
        "--registry",
        "--features",
        "-F",
    }
)
"""Install options whose next token is a value, not a package name (D7.7)."""

_SHELL_PUNCTUATION = "();<>|&"
"""The shell operator characters that `shlex` splits on with `punctuation_chars`."""

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
"""A leading `NAME=value` token of a shell command."""

_PYPI_CUT = re.compile(r"[\[=<>!~;@ ]")
"""The first character that ends a pypi name in a requirement token."""

_REGISTRY_NAMES: dict[str, str] = {
    "pypi": "PyPI",
    "npm": "npm",
    "crates": "crates.io",
    "go": "the Go module proxy",
    "packagist": "Packagist",
}
"""The registry name that a D7.7 message gives for each ecosystem."""

_YOUNG_DAYS = 30
"""A package that first appeared fewer days ago than this gives `ask` (D7.7)."""


def _check_install(
    command: str,
    cfg: config_mod.Config,
    root: Path,
    pending: tuple[str, str] | None = None,
) -> tuple[str, str] | None:
    """Check one Bash command line for a package install, against the registries (D7.7, D15.32).

    The check is off unless `[guard] registry` is true (D15.32). A package
    is not looked up when its segment holds `--index-url`,
    `--extra-index-url`, `-i` or `--registry`; when it is an npm scoped
    name and `<root>/.npmrc` has `@scope:registry=`; when it is an npm
    name and `<root>/.npmrc` has `registry=`; or when its name matches a
    `[guard] private_packages` glob.

    `trueup.registry` is imported here, and only when a segment is an
    install, so a hook call with no install opens no network connection
    and pays no import cost (I-17).

    A name that the registry does not have gives `deny`. A name that first
    appeared less than `_YOUNG_DAYS` days ago gives `ask`. A deny wins over
    an ask, and also over `pending`. When a registry did not answer and
    there is no decision, this function prints a `systemMessage` itself.
    When there is a decision, the note goes at the end of its reason,
    because a hook prints one JSON object only. The function never gives a
    permission grant (I-29).

    Args:
        command: The `Bash` tool's `command` string.
        cfg: The effective config, for `[guard]`.
        root: The repository root, for `.npmrc`.
        pending: An `ask` that the scratch check already made. It stays
            the answer when the install guard finds nothing worse, and its
            reason comes first when this function also asks.

    Returns:
        `("deny", reason)`, `("ask", reason)`, or `pending` (`None` for no
        decision).
    """
    if not cfg.guard_registry:
        return pending
    installs = [
        (ecosystem, name)
        for ecosystem, name, private in _installs(command)
        if not private and not _is_private_package(ecosystem, name, cfg, root)
    ]
    if not installs:
        return pending
    from datetime import datetime, timedelta, timezone

    from trueup import registry

    deadline = time.monotonic() + registry.RUN_BUDGET_S
    now = datetime.now(timezone.utc)
    denies: list[str] = []
    asks: list[str] = [pending[1]] if pending else []
    notes: list[str] = []
    for ecosystem, name in installs:
        where = _REGISTRY_NAMES[ecosystem]
        answer = registry.first_release(ecosystem, name, deadline=deadline)
        if isinstance(answer, registry.Unknown):
            denies.append(
                f"{name} is not on {where}. Check the spelling. Do not install "
                "a package that you cannot find on the registry."
            )
        elif isinstance(answer, registry.Unreachable):
            notes.append(
                f"{where} did not answer; the install guard did not check {name}."
            )
        elif now - answer < timedelta(days=_YOUNG_DAYS):
            asks.append(
                f"{name} first appeared on {where} on {answer.date().isoformat()} "
                f"({(now - answer).days} days ago). Check the publisher, the source "
                "repository and the download count before you install it."
            )
    if denies or asks:
        decision = "deny" if denies else "ask"
        return decision, " ".join((denies or asks) + notes)
    if notes:
        message = " ".join(f"trueup: {note}" for note in notes)
        print(json.dumps({"systemMessage": message}))
    return None


_PRIVATE_INDEX_FLAGS: tuple[str, ...] = (
    "--index-url",
    "--extra-index-url",
    "-i",
    "--registry",
)
"""The install options that name a package source other than the public registry (D15.32)."""


def _is_private_package(
    ecosystem: str, name: str, cfg: config_mod.Config, root: Path
) -> bool:
    """Say whether the install guard leaves one package alone (D15.32).

    Args:
        ecosystem: The ecosystem of the install segment.
        name: The package name.
        cfg: The effective config, for `[guard] private_packages`.
        root: The repository root, for `.npmrc`.

    Returns:
        True when the name matches a `private_packages` glob, or when it is
        an npm name and `<root>/.npmrc` names a registry for its scope or
        sets `registry=`.
    """
    if any(fnmatch.fnmatchcase(name, glob) for glob in cfg.guard_private_packages):
        return True
    if ecosystem != "npm":
        return False
    try:
        npmrc = (root / ".npmrc").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    lines = [line.strip() for line in npmrc.splitlines()]
    if any(re.match(r"registry\s*=", line) for line in lines):
        return True
    if name.startswith("@") and "/" in name:
        scope = name.split("/", 1)[0]
        return any(
            re.match(re.escape(scope) + r":registry\s*=", line) for line in lines
        )
    return False


def _shell_segments(command: str) -> list[list[str]]:
    """Cut one Bash command line into shell segments (D7.7, D15.35).

    The command is split as `shlex.split` does, but with
    `punctuation_chars`, so an operator with no space around it
    (`pip install foo;ls`) is a token too. The tokens are then cut into
    segments at each `_SHELL_BREAKS` token and at each other token made
    only of shell operator characters, for example `(`, `)` or `>&`. A
    redirect operator also removes the digit token in front of it, because
    `punctuation_chars` splits `2>&1` into `2`, `>&` and `1`, and the `2`
    is a file descriptor, not a package name. Each segment loses its
    leading `sudo`, `env` and `NAME=value` tokens.

    Args:
        command: The `Bash` tool's `command` string.

    Returns:
        The non-empty segments in command order. An unparsable command
        gives an empty list.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SHELL_BREAKS or not token.strip(_SHELL_PUNCTUATION):
            if (
                ("<" in token or ">" in token)
                and segments[-1]
                and segments[-1][-1].isdigit()
            ):
                segments[-1].pop()
            segments.append([])
        else:
            segments[-1].append(token)
    cleaned: list[list[str]] = []
    for segment in segments:
        while segment and (
            segment[0] in ("sudo", "env") or _ENV_ASSIGN.match(segment[0])
        ):
            segment = segment[1:]
        if segment:
            cleaned.append(segment)
    return cleaned


def _installs(command: str) -> list[tuple[str, str, bool]]:
    """List the `(ecosystem, name, private)` triples that one Bash command line installs (D7.7, D15.32).

    A segment is an install when its leading tokens match one row of
    `_INSTALL_COMMANDS`. `private` is true when the segment holds one of
    `_PRIVATE_INDEX_FLAGS`, also in the `--flag=value` form.

    Args:
        command: The `Bash` tool's `command` string.

    Returns:
        The triples in command order, with no duplicate pair. An
        unparsable command, or one with no install segment, gives an empty
        list.
    """
    found: list[tuple[str, str, bool]] = []
    seen: set[tuple[str, str]] = set()
    for segment in _shell_segments(command):
        for ecosystem, lead in _INSTALL_COMMANDS:
            if tuple(segment[: len(lead)]) == lead:
                args = segment[len(lead) :]
                private = any(
                    arg in _PRIVATE_INDEX_FLAGS
                    or arg.startswith(
                        ("--index-url=", "--extra-index-url=", "--registry=")
                    )
                    for arg in args
                )
                for name in _package_names(ecosystem, args):
                    if (ecosystem, name) not in seen:
                        seen.add((ecosystem, name))
                        found.append((ecosystem, name, private))
                break
    return found


def _install_names(command: str) -> list[tuple[str, str]]:
    """List the `(ecosystem, name)` pairs that one Bash command line installs (D7.7).

    Args:
        command: The `Bash` tool's `command` string.

    Returns:
        The pairs in command order, with no duplicates. An unparsable
        command, or one with no install segment, gives an empty list.
    """
    return [(ecosystem, name) for ecosystem, name, _ in _installs(command)]


def _package_names(ecosystem: str, args: list[str]) -> list[str]:
    """Give the package names in the arguments of one install segment (D7.7).

    Args:
        ecosystem: The ecosystem of the matched `_INSTALL_COMMANDS` row.
        args: The tokens after the leading install tokens.

    Returns:
        Each name with its version or extra removed. An option, the value
        of a `_SKIP_NEXT` option, a path, a URL and a local go package are
        not names.
    """
    names: list[str] = []
    skip = False
    for token in args:
        if skip:
            skip = False
            continue
        if token.startswith("-"):
            skip = token in _SKIP_NEXT
            continue
        if _is_path_or_url(token):
            continue
        name = _strip_version(ecosystem, token)
        if name:
            names.append(name)
    return names


def _is_path_or_url(token: str) -> bool:
    """Say whether an install argument is a path, a URL or an archive (D7.7).

    Args:
        token: One install argument.

    Returns:
        True when the token starts with `.`, `/` or `~`, holds `://`,
        starts with `git+`, or ends in `.whl`, `.tar.gz` or `.tgz`.
    """
    return (
        token.startswith((".", "/", "~", "git+"))
        or "://" in token
        or token.endswith((".whl", ".tar.gz", ".tgz"))
    )


def _strip_version(ecosystem: str, token: str) -> str | None:
    """Remove the version or extra from one install argument (D7.7).

    Args:
        ecosystem: The ecosystem of the install segment.
        token: One install argument that is not an option or a path.

    Returns:
        The package name, or `None` when no name is left or the token is a
        go argument with no `@` or a local go package.
    """
    if ecosystem == "pypi":
        match = _PYPI_CUT.search(token)
        name = token[: match.start()] if match else token
    elif ecosystem == "npm":
        at = token.rfind("@")
        name = token[:at] if at > 0 else token
    elif ecosystem == "go":
        if "@" not in token:
            return None
        name = token.split("@", 1)[0]
        if "." not in name.split("/", 1)[0]:
            return None
    elif ecosystem == "crates":
        name = token.split("@", 1)[0]
    else:
        name = token.split(":", 1)[0]
    name = name.strip()
    return name or None


def _decide(decision: str, reason: str) -> None:
    """Print one PreToolUse permission decision (D5.8, D7.7).

    Args:
        decision: `"deny"` or `"ask"`. No caller gives a permission grant
            (I-29).
        reason: The reason text, with no `trueup: ` prefix.
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"trueup: {reason}",
        }
    }
    print(json.dumps(output))
