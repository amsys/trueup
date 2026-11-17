"""Run the linters of the effective config on a target (arch: D14.6, D14.7, D14.20, D15.4, D15.5).

`trueup lint` reads the config layers, surveys the target, and selects the
files to lint: the paths on the command line, the working-tree change set
(`--changed`), or every surveyed file. It renders each tool config of the
enabled rule sets into a temporary directory, `cfgdir`, and runs each hook
of `managed.lint_hooks` with its config flag. The eslint packages and the
eslint run config live in the eslint package directory under the trueup
cache (D14.7). Nothing is written under the target root (I-47).

A tool that is not installed makes the run exit 2, unless `--skip-missing`
asks for the skip (D15.4). jscpd and sqlfluff run from the tools directory
under the trueup cache (D15.5).

`trueup lint --install` writes the eslint package.json into the eslint
package directory and runs `npm install` there. It also installs jscpd and
sqlfluff into the tools directory. It is the only path of this module that
opens the network (I-28).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from trueup import changes, docrules, managed, rulesets
from trueup import config as config_mod
from trueup import survey as survey_mod
from trueup.config import Config, ConfigError
from trueup.rulesets import Hook

_PREFIX = "trueup lint"
"""The start of each line that this module prints to standard error."""

_SOURCE_EXTENSIONS: tuple[str, ...] = tuple(
    extension
    for extensions in survey_mod.LANGUAGE_EXTENSIONS.values()
    for extension in extensions
)
"""The extensions of the eight languages (D5.4)."""

_MARKDOWN_EXTENSIONS: tuple[str, ...] = (".md", ".markdown")
"""The extensions of a Markdown page."""

_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": survey_mod.LANGUAGE_EXTENSIONS["python"],
    "pyi": (".pyi",),
    "rust": survey_mod.LANGUAGE_EXTENSIONS["rust"],
    "ts": (".ts", ".mts", ".cts"),
    "tsx": (".tsx",),
    "javascript": (".js", ".mjs", ".cjs"),
    "jsx": (".jsx",),
    "shell": survey_mod.LANGUAGE_EXTENSIONS["shell"],
    "sql": survey_mod.LANGUAGE_EXTENSIONS["sql"],
    "go": survey_mod.LANGUAGE_EXTENSIONS["go"],
    "php": survey_mod.LANGUAGE_EXTENSIONS["php"],
    "markdown": _MARKDOWN_EXTENSIONS,
}
"""The `pre-commit` type names that `Hook.types_or` uses, each to its file extensions (D14.6)."""

_ESLINT_FIELD = "{eslint}"
"""The entry field of a hook that needs the eslint package directory (D14.7)."""

_BANNED_STYLE = "styles/Trueup/Banned.yml"
"""The end of the Vale path whose tokens come from the banned list in force (I-25)."""

_TOKENS_LINE = "tokens:"
"""The line of the Banned.yml template after which the tokens follow."""

_PROSE_PREFIX = "prose:"
"""The start of a `prose` finding id; a `[[keep]]` entry with it spares one page from Vale (D5.6)."""

_RUFF_CACHE = "ruff-cache"
"""The directory under `cfgdir` that ruff uses as its cache (I-47)."""


def run(
    root: Path,
    paths: Sequence[str],
    *,
    changed: bool,
    install: bool,
    skip_missing: bool = False,
) -> int:
    """Lint the selected files with the rule sets of the effective config (D14.6).

    Args:
        root: The target root.
        paths: Repo paths to lint, relative to `root` or absolute. A
            directory selects the surveyed files under it. Empty selects
            every surveyed file, or the change set with `changed`.
        changed: Lint the working-tree change set (`changes.working_set`).
        install: Install the eslint packages in the eslint package
            directory, and jscpd and sqlfluff in the tools directory, and
            lint nothing (D14.7, D15.5).
        skip_missing: Skip a tool that is not installed, with one line,
            and take the exit code from the tools that ran (D15.4).

    Returns:
        0 when each tool that ran exited 0, 1 when one did not, 2 on a
        config error, a bad command line or a missing tool (a failed tool
        and a missing tool in one run give 2). With `install`, the first
        non-zero exit code of the install commands, or 0.
    """
    try:
        return _run(
            root.resolve(),
            paths,
            changed=changed,
            install=install,
            skip_missing=skip_missing,
        )
    except ConfigError as exc:
        print(f"{_PREFIX}: {exc}", file=sys.stderr)
        return 2


def _run(
    root: Path,
    paths: Sequence[str],
    *,
    changed: bool,
    install: bool,
    skip_missing: bool,
) -> int:
    """Do the work of `run`; a `ConfigError` goes up to `run`.

    Args:
        root: The resolved target root.
        paths: As `run` takes them.
        changed: As `run` takes it.
        install: As `run` takes it.
        skip_missing: As `run` takes it.

    Returns:
        The exit code that `run` returns.
    """
    if paths and changed:
        print(f"{_PREFIX}: give PATH or --changed, not both", file=sys.stderr)
        return 2
    layers = config_mod.load_layers(root)
    # D15.6: a target that is not adopted names no language, so lint stops.
    if not layers.adopted:
        print(
            f"{_PREFIX}: no trueup.toml and no user default file; run trueup check",
            file=sys.stderr,
        )
        return 2
    survey = survey_mod.run(root)
    if not survey.files:
        raise config_mod.ConfigError(
            f"{root}: no tracked file to check (after [scan] ignore)"
        )
    cfg = managed.effective_config(layers.effective, survey)
    if install:
        return _install(cfg)
    full = not paths and not changed
    selection = _select(root, survey, cfg, paths, changed)
    docs = config_mod.resolve_docs(cfg, survey.tier)
    vale = docs == "full"
    with tempfile.TemporaryDirectory(prefix="trueup-lint-") as scratch:
        cfgdir = Path(scratch)
        _render_configs(cfgdir, cfg, survey, vale)
        failed, missing = _run_hooks(root, cfgdir, cfg, selection, full=full, vale=vale)
        if (full or any(_is_text_or_source(path) for path in selection)) and not (
            _run_checker(root, cfgdir, cfg)
        ):
            failed = True
    if missing and not skip_missing:
        print(
            f"{_PREFIX}: {len(missing)} tool(s) missing: {', '.join(missing)}; "
            "install them, or pass --skip-missing",
            file=sys.stderr,
        )
        return 2
    return 1 if failed else 0


def _select(
    root: Path,
    survey: survey_mod.Survey,
    cfg: Config,
    paths: Sequence[str],
    changed: bool,
) -> list[str]:
    """Select the files to lint (D14.6 step 2).

    Args:
        root: The resolved target root.
        survey: The survey of the target.
        cfg: The effective config, whose `ignore` globs drop a path.
        paths: As `run` takes them.
        changed: As `run` takes it.

    Returns:
        Surveyed repo paths that exist as files, in survey order.
    """
    surveyed = [path for path in survey.files if os.path.isfile(root / path)]
    if changed:
        wanted = changes.working_set(root)
        chosen = [path for path in surveyed if path in wanted]
    elif paths:
        chosen = []
        for given in paths:
            relative = _relative(root, given)
            if relative is None:
                print(
                    f"{_PREFIX}: {given} is not under the root; skipped",
                    file=sys.stderr,
                )
                continue
            if relative == "":
                hits = surveyed
            else:
                hits = [
                    path
                    for path in surveyed
                    if path == relative or path.startswith(relative + "/")
                ]
            if not hits:
                if survey_mod.matches_ignore(relative, cfg.ignore):
                    continue
                print(
                    f"{_PREFIX}: {given} is not a surveyed file; skipped",
                    file=sys.stderr,
                )
            chosen.extend(path for path in hits if path not in chosen)
    else:
        chosen = surveyed
    return [path for path in chosen if not survey_mod.matches_ignore(path, cfg.ignore)]


def _relative(root: Path, given: str) -> str | None:
    """Give one command-line path as a POSIX path relative to the root.

    Args:
        root: The resolved target root.
        given: A path relative to `root`, or absolute.

    Returns:
        The relative path, `""` for the root itself, or `None` when the
        path is outside the root.
    """
    path = Path(given)
    absolute = path if path.is_absolute() else root / path
    try:
        relative = Path(os.path.normpath(absolute)).relative_to(root)
    except ValueError:
        return None
    text = relative.as_posix()
    return "" if text == "." else text


def _render_configs(
    cfgdir: Path, cfg: Config, survey: survey_mod.Survey, vale: bool
) -> None:
    """Render the tool configs of the enabled rule sets into `cfgdir` (D14.6 step 3).

    The eslint config and package.json are not written here: they belong
    in the eslint package directory (D14.7). The checker config goes in
    `cfgdir/ref_check.toml` in global mode only; a copy-mode copy reads
    the target's own file.

    Args:
        cfgdir: The temporary directory of this run.
        cfg: The effective config.
        survey: The survey of the target.
        vale: Whether the Vale style is on (`docs` resolves to `full`).
    """
    root = str(survey.root.resolve())
    enabled = managed.enabled_rulesets(cfg)
    for rule_set in enabled:
        for key, template in rule_set.files.items():
            if key in rulesets.SHARED_TARGETS:
                continue
            text = rulesets.template_path(template).read_text(encoding="utf-8")
            _write(cfgdir / key, text.replace(rulesets.ROOT_TOKEN, root))
    strict = [rule_set.language for rule_set in enabled if rule_set.mode == "strict"]
    if strict:
        _write(cfgdir / rulesets.JSCPD_FILE, rulesets.render_jscpd(strict))
    if vale:
        words = docrules.banned_words(cfg)
        for old_path, template in rulesets.VALE_FILES.items():
            text = rulesets.template_path(template).read_text(encoding="utf-8")
            if old_path.endswith(_BANNED_STYLE):
                if not words:
                    continue
                text = _render_banned_style(text, words)
            _write(cfgdir / old_path.removeprefix("lint/"), text)
    if cfg.refs_mode == "global":
        _write(cfgdir / managed.REF_CHECK_CONFIG_PATH, _ref_check_text(cfg, survey))


def _write(path: Path, text: str) -> None:
    """Write one rendered file, with its parent directories.

    Args:
        path: The file under `cfgdir`.
        text: The file text.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _render_banned_style(template: str, words: Sequence[str]) -> str:
    """Render the Vale `Banned.yml` from the banned list in force (I-25, D14.4).

    The template lines up to `tokens:` stay. One token follows per entry:
    the regex of a `word => <regex>` entry, or the bare word. With the
    built-in list, the text equals the template.

    Args:
        template: The text of the Banned.yml template.
        words: The entries of `docrules.banned_words`, not empty.

    Returns:
        The style text.
    """
    head = template.split(f"\n{_TOKENS_LINE}\n", 1)[0]
    lines = [head, _TOKENS_LINE]
    for entry in words:
        _, separator, pattern = entry.partition(" => ")
        token = pattern.strip() if separator else entry
        lines.append(f"  - {json.dumps(token, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def _ref_check_text(cfg: Config, survey: survey_mod.Survey) -> str:
    """Give the checker config of a lint run: the `check` text plus the `[keep]` table (D14.5).

    Args:
        cfg: The effective config.
        survey: The survey of the target.

    Returns:
        `managed.render_ref_check_config` with `docs` resolved and
        `keep=True` when `managed.refcheck_switches_on` is true, else an
        empty text, as `check` gives it (D14.5).
    """
    if not managed.refcheck_switches_on(cfg, survey):
        return ""
    resolved = replace(cfg, docs=config_mod.resolve_docs(cfg, survey.tier))
    return managed.render_ref_check_config(resolved, survey, keep=True)


def _hook_owners(cfg: Config, vale: bool) -> dict[Hook, list[tuple[str, str]]]:
    """Map each hook of the run to the languages and modes that add it.

    Args:
        cfg: The effective config.
        vale: Whether the Vale hook runs.

    Returns:
        Hook to `(language, mode)` pairs. The jscpd hook maps to each
        strict language; the Vale hook maps to `("docs", "full")`.
    """
    owners: dict[Hook, list[tuple[str, str]]] = {}
    for rule_set in managed.enabled_rulesets(cfg):
        pair = (rule_set.language, rule_set.mode)
        for hook in rule_set.hooks:
            owners.setdefault(hook, []).append(pair)
        if rule_set.mode == "strict":
            owners.setdefault(rulesets.JSCPD_HOOK, []).append(pair)
    if vale:
        owners[rulesets.VALE_HOOK] = [("docs", "full")]
    return owners


def _hook_files(hook: Hook, selection: Sequence[str], cfg: Config) -> list[str]:
    """Give the selected files that one hook sees, as `pre-commit` would (D14.6 step 4).

    Args:
        hook: The hook.
        selection: The selected repo paths.
        cfg: The effective config, which gives the paths of `_spared_paths`.

    Returns:
        The paths that match `hook.files` and `hook.types_or`, minus the
        paths that match `hook.exclude` and the paths of `_spared_paths`.
    """
    files = re.compile(hook.files) if hook.files else None
    exclude = re.compile(hook.exclude) if hook.exclude else None
    extensions = tuple(
        extension
        for type_name in hook.types_or
        for extension in _TYPE_EXTENSIONS.get(type_name, ())
    )
    spared = _spared_paths(hook, cfg)
    return [
        path
        for path in selection
        if (files is None or files.search(path))
        and (not hook.types_or or path.endswith(extensions))
        and (exclude is None or not exclude.search(path))
        and path not in spared
    ]


def _spared_paths(hook: Hook, cfg: Config) -> frozenset[str]:
    """Give the repo paths that one hook does not see, beyond its own `exclude` (D14.6).

    The Vale hook does not see a page whose `prose:<path>` finding is in
    `[[keep]]`, so `lint` and `check` decline the same pages (D5.6). In
    copy mode, the ruff format hook does not see the checker copy at
    `cfg.refs_path`: it is a byte copy of the bundled file (I-26).

    Args:
        hook: The hook.
        cfg: The effective config.

    Returns:
        The exact repo paths to leave out.
    """
    if hook.id == rulesets.VALE_HOOK.id:
        return frozenset(
            finding_id.removeprefix(_PROSE_PREFIX)
            for finding_id in cfg.keep
            if finding_id.startswith(_PROSE_PREFIX)
        )
    if hook.id == "ruff-format" and cfg.refs_mode == "copy":
        return frozenset((cfg.refs_path,))
    return frozenset()


def _is_text_or_source(path: str) -> bool:
    """Say whether a path is a Markdown page or a source file of the eight languages.

    Args:
        path: A repo path.

    Returns:
        True for a `.md` or `.markdown` page or a `LANGUAGE_EXTENSIONS` file.
    """
    return path.endswith(_MARKDOWN_EXTENSIONS + _SOURCE_EXTENSIONS)


def _language_files(pairs: Sequence[tuple[str, str]], selection: Sequence[str]) -> bool:
    """Say whether the selection holds a file of one of the given languages.

    Args:
        pairs: `(language, mode)` pairs; `docs` counts Markdown pages.
        selection: The selected repo paths.

    Returns:
        True when one selected path has an extension of one language.
    """
    extensions: tuple[str, ...] = ()
    for language, _ in pairs:
        extensions += survey_mod.LANGUAGE_EXTENSIONS.get(language, _MARKDOWN_EXTENSIONS)
    return any(path.endswith(extensions) for path in selection)


def _tool_name(argv: Sequence[str]) -> str:
    """Give the executable of a command line: the first token after `env` and its assignments.

    Args:
        argv: The command line.

    Returns:
        The executable token, or the empty string when there is none.
    """
    tokens = list(argv)
    if tokens and tokens[0] == "env":
        tokens = tokens[1:]
        while tokens and "=" in tokens[0]:
            tokens = tokens[1:]
    return tokens[0] if tokens else ""


def tools_dir() -> Path:
    """Give the tools directory of jscpd and sqlfluff (D15.5).

    The directory is `config.cache_home() / "tools" / <hash>`, where the
    hash is the first 16 hex digits of the SHA-256 of
    `rulesets.render_tools_manifest()`. A new tool version gets a new
    directory. Nothing goes under the target root (I-47).

    Returns:
        The directory. It does not have to exist.
    """
    manifest = rulesets.render_tools_manifest()
    digest = hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:16]
    return config_mod.cache_home() / "tools" / digest


def _tool_found(root: Path, tool: str) -> bool:
    """Say whether a tool can run: on the path, or a file under the root for `vendor/bin/...`.

    Args:
        root: The target root, the working directory of the run.
        tool: The executable token.

    Returns:
        True when the tool can run.
    """
    if "/" in tool:
        candidate = root / tool
        return candidate.is_file() and os.access(candidate, os.X_OK)
    return shutil.which(tool) is not None


def _run_hooks(
    root: Path,
    cfgdir: Path,
    cfg: Config,
    selection: Sequence[str],
    *,
    full: bool,
    vale: bool,
) -> tuple[bool, list[str]]:
    """Run each hook of `managed.lint_hooks` on its files (D14.6 steps 4 and 5).

    A missing tool, or eslint without its packages, prints one line, goes
    on the list of missing tools, and the run goes on (D15.4). The eslint
    run config is written into the eslint package directory before the
    first eslint hook and removed at the end (D14.7).

    Args:
        root: The target root.
        cfgdir: The directory of the rendered configs.
        cfg: The effective config.
        selection: The selected repo paths.
        full: Whether the selection is the full survey.
        vale: Whether the Vale hook runs.

    Returns:
        `(failed, missing)`: whether a hook exited with a code other than
        0, and the missing tools in the order found, each once. The eslint
        packages count as the tool `eslint packages`.
    """
    owners = _hook_owners(cfg, vale)
    tools = tools_dir()
    packages = managed.eslint_dir(cfg)
    run_config = None if packages is None else packages / rulesets.ESLINT_RUN_CONFIG
    told: set[str] = set()
    missing: list[str] = []
    failed = False
    try:
        for hook in managed.lint_hooks(cfg, vale=vale):
            pairs = owners.get(hook, [])
            files = _hook_files(hook, selection, cfg)
            if hook.pass_filenames and not files:
                continue
            if (
                not hook.pass_filenames
                and not full
                and not _language_files(pairs, selection)
            ):
                continue
            tokens = shlex.split(hook.entry)
            tool = _tool_name(tokens).format(tools=tools)
            label = ", ".join(f"{language} {mode}" for language, mode in pairs)
            if not _tool_found(root, tool):
                _tell(told, f"{_PREFIX}: {tool} is not installed; {label} did not run")
                _note(missing, tool)
                continue
            needs_packages = any(_ESLINT_FIELD in token for token in tokens)
            if needs_packages and (
                packages is None or not (packages / "node_modules").is_dir()
            ):
                _tell(
                    told,
                    f"{_PREFIX}: eslint packages are not installed; run trueup lint --install",
                )
                _note(missing, "eslint packages")
                continue
            if run_config is not None and any(
                rulesets.ESLINT_RUN_CONFIG in token for token in tokens
            ):
                run_config.write_text(
                    rulesets.render_eslint_config(
                        cfg.languages.get("typescript", "off"),
                        cfg.languages.get("vue", "off"),
                        cfg.eslint_off,
                    ),
                    encoding="utf-8",
                )
            argv = [
                token.format(cfg=cfgdir, eslint=packages, tools=tools, root=root)
                for token in tokens
            ]
            argv += rulesets.owned_file_args(hook, root, cfg)
            if hook.pass_filenames:
                argv += files
            code = _execute(argv, root, cfgdir=cfgdir)
            if code != 0:
                print(f"{_PREFIX}: {hook.name} failed (exit {code})", file=sys.stderr)
                failed = True
    finally:
        if run_config is not None:
            run_config.unlink(missing_ok=True)
    return failed, missing


def _note(missing: list[str], tool: str) -> None:
    """Add a missing tool to the list once.

    Args:
        missing: The missing tools so far; this function adds `tool`.
        tool: The tool name.
    """
    if tool not in missing:
        missing.append(tool)


def _tell(told: set[str], line: str) -> None:
    """Print one line to standard error, once per run.

    Args:
        told: The lines printed so far; this function adds `line`.
        line: The line.
    """
    if line not in told:
        told.add(line)
        print(line, file=sys.stderr)


def _run_checker(root: Path, cfgdir: Path, cfg: Config) -> bool:
    """Run the reference checker on the target (D14.6 step 4).

    Global mode runs the bundled checker with `cfgdir/ref_check.toml`.
    Copy mode runs the target's copy, which reads the target's own
    `ref_check.toml`.

    Args:
        root: The target root.
        cfgdir: The directory of the rendered configs.
        cfg: The effective config.

    Returns:
        True when the checker exited 0 or did not run, False when it failed.
    """
    if cfg.refs_mode == "copy":
        copy = root / cfg.refs_path
        if not copy.is_file():
            print(
                f"{_PREFIX}: {cfg.refs_path} is not there; run trueup apply; ref check skipped",
                file=sys.stderr,
            )
            return True
        argv = [sys.executable, str(copy), "--root", str(root)]
    else:
        argv = [
            sys.executable,
            str(managed.BUNDLED_REF_CHECK),
            "--root",
            str(root),
            "--config",
            str(cfgdir / managed.REF_CHECK_CONFIG_PATH),
        ]
    code = _execute(argv, root)
    if code != 0:
        print(f"{_PREFIX}: ref check failed (exit {code})", file=sys.stderr)
    return code == 0


def _install(cfg: Config) -> int:
    """Install the tools that the effective config needs (D14.7, D15.5).

    This is the one network path of `trueup lint` (I-28). It installs, in
    this order: the eslint packages when TypeScript or Vue is on; jscpd
    into the tools directory when any language is `strict`; sqlfluff into
    a virtual environment in the tools directory when SQL is on. Each
    install runs, even after one failed.

    Args:
        cfg: The effective config.

    Returns:
        The first non-zero exit code of the install commands; 0 when all
        passed or when nothing needs an install; 1 when a command cannot
        start.
    """
    codes: list[int] = []
    packages = managed.eslint_dir(cfg)
    if packages is not None:
        packages.mkdir(parents=True, exist_ok=True)
        (packages / "package.json").write_text(
            rulesets.render_eslint_package(
                cfg.languages.get("typescript", "off"),
                cfg.languages.get("vue", "off"),
            ),
            encoding="utf-8",
        )
        codes.append(
            _execute(
                [
                    "npm",
                    "install",
                    "--prefix",
                    str(packages),
                    "--no-audit",
                    "--no-fund",
                ],
                packages,
            )
        )
    tools = tools_dir()
    if any(mode == "strict" for mode in cfg.languages.values()):
        tools.mkdir(parents=True, exist_ok=True)
        codes.append(
            _execute(
                [
                    "npm",
                    "install",
                    "--prefix",
                    str(tools),
                    "--no-audit",
                    "--no-fund",
                    f"jscpd@{rulesets.JSCPD_VERSION}",
                ],
                tools,
            )
        )
    if cfg.languages.get("sql", "off") != "off":
        tools.mkdir(parents=True, exist_ok=True)
        venv = tools / "sqlfluff"
        codes.append(_execute(["uv", "venv", str(venv)], tools))
        codes.append(
            _execute(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(venv),
                    f"sqlfluff=={rulesets.SQLFLUFF_VERSION}",
                ],
                tools,
            )
        )
    if not codes:
        print(
            f"{_PREFIX}: TypeScript, Vue, SQL and strict modes are off; nothing to install",
            file=sys.stderr,
        )
        return 0
    return next((code for code in codes if code != 0), 0)


def _execute(argv: Sequence[str], cwd: Path, *, cfgdir: Path | None = None) -> int:
    """Run one command; its output passes through.

    Args:
        argv: The command line. No shell runs it.
        cwd: The working directory.
        cfgdir: The directory of the rendered configs. When given, the
            command gets `RUFF_CACHE_DIR=<cfgdir>/ruff-cache`, so ruff
            writes no `.ruff_cache` under the root (I-47).

    Returns:
        The exit code, or 1 when the command cannot start.
    """
    env = None
    if cfgdir is not None:
        env = {**os.environ, "RUFF_CACHE_DIR": str(cfgdir / _RUFF_CACHE)}
    try:
        return subprocess.run(list(argv), cwd=cwd, env=env, check=False).returncode
    except OSError as exc:
        print(f"{_PREFIX}: {argv[0]} cannot run: {exc}", file=sys.stderr)
        return 1
