"""Inventory a target repository: files, languages, tools, tier (arch: D5.4).

`run` is the one entry point. It lists the files `git` tracks or would add,
counts lines per language with `tokei` when it is on the path or a small
built-in counter otherwise, checks which rule-set tools are on the path, and
picks a tier from the file count, the manifests, the workspace markers and
the contributor count. `hygiene.py`, `health.py`, `score.py` and `report.py`
all read the `Survey` this module builds; none of them reads the file
system a second time for the same facts.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from trueup import config as config_mod
from trueup import fsread
from trueup.config import ConfigError
from trueup.rulesets import RULESETS

_TEXT_READ_CAP = 1024 * 1024
"""The largest file, in bytes, that the line counter reads (D15.22)."""

TOKEI_TIMEOUT_S = 60
"""The time limit of one tokei run, in seconds (D16.10).

tokei opens `.gitignore` during its walk, so a `.gitignore` symlink to a
FIFO stops it. On expiry the survey uses the built-in counter."""

LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "rust": (".rs",),
    "typescript": (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"),
    "vue": (".vue",),
    "shell": (".sh", ".bash"),
    "sql": (".sql",),
    "go": (".go",),
    "php": (".php",),
}
"""The file extensions that count towards each of the eight languages (D5.4)."""

_COMMENT_LEADERS: dict[str, tuple[str, ...]] = {
    "python": ("#",),
    "rust": ("//", "/*", "*"),
    "typescript": ("//", "/*", "*"),
    "vue": ("<!--",),
    "shell": ("#",),
    "sql": ("--",),
    "go": ("//", "/*", "*"),
    "php": ("#", "//", "/*", "*"),
}
"""The comment leaders the built-in counter skips, per language (D5.4)."""

_TOKEI_NAMES: dict[str, tuple[str, ...]] = {
    "python": ("Python",),
    "rust": ("Rust",),
    "typescript": ("TypeScript", "JavaScript"),
    "vue": ("Vue",),
    "shell": ("Shell", "Bash"),
    "sql": ("SQL",),
    "go": ("Go",),
    "php": ("PHP",),
}
"""tokei's own language names, mapped onto the eight trueup languages.

Nothing in this environment can run `tokei` to confirm these names against a
real report (it is not on the path here, run-wide fact 2), so this mapping
is a best-effort reading of tokei's public language list, not a checked
one. The built-in counter below is exercised by the tests instead; a wrong
name here only costs the accuracy of `tokei`'s counts, never the identity of
the surveyed files, which always comes from `git`.
"""

_OTHER_LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "scala": (".scala",),
    "groovy": (".groovy",),
    "c": (".c", ".h"),
    "cpp": (".cc", ".cpp", ".cxx", ".hpp", ".hh"),
    "csharp": (".cs",),
    "fsharp": (".fs",),
    "ruby": (".rb",),
    "swift": (".swift",),
    "objective-c": (".m", ".mm"),
    "dart": (".dart",),
    "elixir": (".ex", ".exs"),
    "erlang": (".erl",),
    "haskell": (".hs",),
    "ocaml": (".ml", ".mli"),
    "clojure": (".clj", ".cljs"),
    "lua": (".lua",),
    "perl": (".pl", ".pm"),
    "r": (".r",),
    "julia": (".jl",),
    "zig": (".zig",),
    "nim": (".nim",),
    "nix": (".nix",),
    "emacs-lisp": (".el",),
}
"""The languages outside the eight, by family, with their extensions (D15.26).
They count for the tier and show in `Survey.other_languages`; no rule set
covers them."""

_EXTRA_TIER_EXTENSIONS = [
    ext for extensions in _OTHER_LANGUAGE_EXTENSIONS.values() for ext in extensions
]

_TIER_MANIFEST_SKIP_DIRS: frozenset[str] = frozenset(
    {"tests", "test", "fixtures", "testdata", "__snapshots__", "examples"}
)
"""A manifest under one of these directories does not count for the tier (D15.26)."""

OTHER_LANGUAGE_NOTE = "present, no rule set"
"""The survey text for each entry of `Survey.other_languages` (D15.26)."""

TIER_EXTENSIONS: frozenset[str] = frozenset(
    ext for extensions in LANGUAGE_EXTENSIONS.values() for ext in extensions
) | frozenset(_EXTRA_TIER_EXTENSIONS)
"""The extensions that count towards the tier pick (D14.13). It holds the
eight languages and more. `LANGUAGE_EXTENSIONS` does not change (I-13)."""

MANIFEST_NAMES: tuple[str, ...] = (
    "Cargo.toml",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "Gemfile",
    "CMakeLists.txt",
    "meson.build",
    "Package.swift",
    "mix.exs",
    "pubspec.yaml",
    "build.sbt",
    "setup.py",
    "deno.json",
    "Makefile.PL",
    "cabal.project",
    "stack.yaml",
    "flake.nix",
)
"""File names that count as a manifest, at any depth (D5.4, D14.13).
`requirements*.txt` is left out on purpose. The tier counts fewer of them
(`_tier_manifest`, D15.26)."""

CI_PATHS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    "Jenkinsfile",
    ".travis.yml",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    ".woodpecker.yml",
    ".woodpecker/*.yml",
    ".drone.yml",
    ".forgejo/workflows/*",
    ".gitea/workflows/*",
    ".buildkite/pipeline.yml",
)
"""The path patterns of a CI file; `fnmatch` rules (D14.13)."""

MANAGED_CODE_FILES: tuple[str, ...] = ("ref_check.py",)
"""Root code files that trueup itself writes into a target (D5.6). They never
count towards a language or the tier, so a language the person never
chose does not turn on because `apply` copied the checker in."""

TRUEUP_OWN_PATHS: frozenset[str] = frozenset(
    {
        "trueup.toml",
        "ref_check.toml",
        ".trueup-baseline.json",
        "ref_check.py",
    }
)
"""The files trueup itself writes into a target (D12.9, D15.37). They do
not count towards the tier pick or the root budget (I-43). The paths an
earlier trueup managed (`lint/`, `.editorconfig` and the others of
`managed.LEGACY_PATHS`) are the person's files now, so they count.
`.trueup-baseline.json` is `baseline.BASELINE_FILENAME`; this module does
not import `baseline`, which imports `report` and so this module."""


def is_trueup_path(path: str) -> bool:
    """Say whether a repo path is one that trueup itself writes (D12.9, D15.37).

    Args:
        path: A repo-relative POSIX path.

    Returns:
        True for a path in `TRUEUP_OWN_PATHS`.
    """
    return path in TRUEUP_OWN_PATHS


def _language_extension(path: str) -> bool:
    """Say whether a path has the extension of one of the eight languages.

    Args:
        path: A repo-relative POSIX path.

    Returns:
        True when the suffix is in `LANGUAGE_EXTENSIONS`.
    """
    suffix = Path(path).suffix
    return any(suffix in extensions for extensions in LANGUAGE_EXTENSIONS.values())


_PRESENT_MIN_FILES = 1
_PRESENT_MIN_LINES = 50


@dataclass(frozen=True)
class LangStat:
    """The size of one language in a survey.

    Attributes:
        files: The number of surveyed files of this language.
        code_lines: The number of non-comment, non-blank lines counted
            across those files.
        present: Whether this language counts as present: `files >= 1` and
            `code_lines >= 50` (D5.4).
    """

    files: int
    code_lines: int
    present: bool


@dataclass(frozen=True)
class Survey:
    """The inventory of one target repository (D5.4).

    Attributes:
        root: The repository root that was surveyed.
        files: The tracked and untracked, non-ignored files `git` gives,
            minus the `ignore` globs of `trueup.toml`, sorted.
        languages: Language name to `LangStat`, one entry per language in
            `LANGUAGE_EXTENSIONS`.
        tools: Executable name to whether it is on the path, one entry per
            tool that any rule set of `trueup.rulesets.RULESETS` names.
        root_entries: The first path segment of each file in `files`,
            unique and sorted. A file that trueup writes (`is_trueup_path`
            or `MANAGED_CODE_FILES`) gives no entry (D12.9, I-43).
        manifests: The paths in `files` whose name is in `MANIFEST_NAMES`,
            at any depth. The tier counts only the ones `_tier_manifest`
            accepts (D15.26).
        workspace: Whether the target declares a Cargo, pnpm, npm or Go
            workspace at its root.
        contributors: The count of distinct author emails in `git log
            --since=12.months`.
        has_ci: Whether `.github/workflows/` holds a workflow file that is
            not trueup's own (D12.9).
        tags: The count of `git tag` entries.
        tier: The picked tier: `T0`, `T1`, `T2` or `T3`.
        tier_reason: One line explaining the pick.
        counter: Which line counter produced `languages`: `"tokei"` or
            `"built-in"` (D5.4). `report.py` prints this so the reader
            knows which counter the code counts came from.
        other_languages: The families of `_OTHER_LANGUAGE_EXTENSIONS` with
            one file or more in `files`, sorted. No rule set covers them
            (D15.26).
        tracked: The paths `git ls-files` gives (D15.27). The empty set
            means "all", so a `Survey` built by hand treats every file as
            tracked.
    """

    root: Path
    files: tuple[str, ...]
    languages: dict[str, LangStat]
    tools: dict[str, bool]
    root_entries: tuple[str, ...]
    manifests: tuple[str, ...]
    workspace: bool
    contributors: int
    has_ci: bool
    tags: int
    tier: str
    tier_reason: str
    counter: str
    other_languages: tuple[str, ...] = ()
    tracked: frozenset[str] = frozenset()


def run(root: Path) -> Survey:
    """Survey a target repository.

    Args:
        root: The repository root to survey.

    Returns:
        The `Survey` of `root`. `trueup.toml`'s `ignore` globs are applied
        when the file is present; a `tier` override in it wins over the
        picked tier.

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid.
    """
    cfg = config_mod.load(root)
    ignore = cfg.ignore if cfg is not None else ()
    files = _list_files(root, ignore)
    languages, counter = _language_stats(root, files)
    tools = {tool: shutil.which(tool) is not None for tool in _tool_names()}
    # The root budget counts no entry that holds only trueup's files, so
    # the setup opt-in never adds a `root-budget` warning (D12.9, I-43).
    root_entries = tuple(
        sorted(
            {
                path.split("/", 1)[0]
                for path in files
                if not is_trueup_path(path) and path not in MANAGED_CODE_FILES
            }
        )
    )
    manifests = tuple(
        sorted(path for path in files if Path(path).name in MANIFEST_NAMES)
    )
    workspace = _has_workspace(root)
    contributors = _count_contributors(root)
    # The tier pick counts no file that trueup writes, so `apply` never
    # changes the tier (D12.9, I-43). `Survey.files` keeps every path.
    tier_files = tuple(path for path in files if not is_trueup_path(path))
    has_ci = any(
        fnmatch.fnmatchcase(path, pattern)
        for path in tier_files
        for pattern in CI_PATHS
    )
    tags = _count_tags(root)
    own_lang_files = sum(
        1
        for path in files
        if is_trueup_path(path)
        and path not in MANAGED_CODE_FILES
        and _language_extension(path)
    )
    extra_tier_files = sum(
        1
        for path in tier_files
        if Path(path).suffix in TIER_EXTENSIONS and not _language_extension(path)
    )
    total_lang_files = max(
        0,
        sum(stat.files for stat in languages.values())
        - own_lang_files
        + extra_tier_files,
    )
    tier, tier_reason = _pick_tier(
        override=cfg.tier if cfg is not None else "auto",
        total_lang_files=total_lang_files,
        file_count=len(tier_files),
        manifests=tuple(
            path
            for path in manifests
            if not is_trueup_path(path) and _tier_manifest(path)
        ),
        workspace=workspace,
        contributors=contributors,
        has_ci=has_ci,
        tags=tags,
    )
    return Survey(
        root=root,
        files=files,
        languages=languages,
        tools=tools,
        root_entries=root_entries,
        manifests=manifests,
        workspace=workspace,
        contributors=contributors,
        has_ci=has_ci,
        tags=tags,
        tier=tier,
        tier_reason=tier_reason,
        counter=counter,
        other_languages=_other_languages(tier_files),
        tracked=_tracked_files(root),
    )


def _tier_manifest(path: str) -> bool:
    """Say whether one manifest counts for the tier (D15.26).

    Args:
        path: The repo-relative POSIX path of the manifest.

    Returns:
        True when the path has two parts at most (the root or one level
        down) and no directory part is in `_TIER_MANIFEST_SKIP_DIRS`.
    """
    parts = Path(path).parts
    return len(parts) <= 2 and not _TIER_MANIFEST_SKIP_DIRS.intersection(parts[:-1])


def _other_languages(files: tuple[str, ...]) -> tuple[str, ...]:
    """Give the families outside the eight languages that have a file (D15.26).

    Args:
        files: The repo-relative paths to read.

    Returns:
        The family names of `_OTHER_LANGUAGE_EXTENSIONS` with one file or
        more, sorted.
    """
    suffixes = {Path(path).suffix for path in files}
    return tuple(
        sorted(
            name
            for name, extensions in _OTHER_LANGUAGE_EXTENSIONS.items()
            if suffixes.intersection(extensions)
        )
    )


def _tracked_files(root: Path) -> frozenset[str]:
    """List the paths git tracks, for `Survey.tracked` (D15.27).

    Args:
        root: The repository root.

    Returns:
        The paths `git ls-files -z` gives, relative to `root`.

    Raises:
        trueup.config.ConfigError: `git ls-files` fails (arch: D15.2).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="surrogateescape",  # arch: D12.10
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _git_failure(root, "ls-files", exc) from exc
    return frozenset(path for path in result.stdout.split("\0") if path)


def as_dict(survey: Survey) -> dict[str, object]:
    """Turn a `Survey` into a JSON-ready mapping.

    Args:
        survey: The survey to convert.

    Returns:
        A mapping of plain `dict`, `list`, `str`, `int` and `bool` values,
        suitable for `json.dumps`.
    """
    return {
        "root": str(survey.root),
        "files": list(survey.files),
        "languages": {
            name: {
                "files": stat.files,
                "code_lines": stat.code_lines,
                "present": stat.present,
            }
            for name, stat in survey.languages.items()
        },
        "tools": dict(survey.tools),
        "root_entries": list(survey.root_entries),
        "manifests": list(survey.manifests),
        "workspace": survey.workspace,
        "contributors": survey.contributors,
        "has_ci": survey.has_ci,
        "tags": survey.tags,
        "tier": survey.tier,
        "tier_reason": survey.tier_reason,
        "counter": survey.counter,
        "other_languages": dict.fromkeys(survey.other_languages, OTHER_LANGUAGE_NOTE),
    }


def matches_ignore(path: str, patterns: tuple[str, ...]) -> bool:
    """Say whether a repo-relative path matches any of the given glob patterns.

    `*` matches within one path segment, `**` matches across segments, and
    `?` matches one character; this is the gitignore-like subset that
    `trueup.toml`'s `ignore` and `protect` globs (D5.3) need, not full glob
    syntax.

    Args:
        path: A repo-relative POSIX path.
        patterns: The glob patterns to check.

    Returns:
        True when `path` matches at least one pattern.
    """
    return any(_glob_to_regex(pattern).match(path) for pattern in patterns)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile one glob pattern into a regular expression.

    Args:
        pattern: A glob pattern using `*`, `**` and `?`.

    Returns:
        The compiled, fully-anchored regular expression.
    """
    tokens: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern[index : index + 2] == "**":
            tokens.append(".*")
            index += 2
        elif pattern[index] == "*":
            tokens.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            tokens.append("[^/]")
            index += 1
        else:
            tokens.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(tokens) + "$")


def in_work_tree(root: Path) -> bool:
    """Say whether `root` is inside a git work tree (arch: D15.2).

    Args:
        root: The directory to test.

    Returns:
        True when `git rev-parse --is-inside-work-tree` prints `true` in
        `root`. False when git cannot run there or prints anything else.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return result.stdout.strip() == "true"


def _git_failure(root: Path, command: str, exc: Exception) -> ConfigError:
    """Word one failed git call as a `ConfigError` (arch: D15.2).

    Args:
        root: The repository root.
        command: The git subcommand that failed.
        exc: The `OSError` or `CalledProcessError` it raised.

    Returns:
        The error to raise, with the first stderr line of git when it has one.
    """
    stderr = getattr(exc, "stderr", None) or ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    reason = stderr.strip().splitlines()[0] if stderr.strip() else str(exc)
    return ConfigError(f"git {command} failed in {root}: {reason}")


def _list_files(root: Path, ignore: tuple[str, ...]) -> tuple[str, ...]:
    """List the tracked and untracked files `git` gives, minus the ignore globs.

    Args:
        root: The repository root.
        ignore: The glob patterns to drop.

    Returns:
        The surviving paths, sorted.

    Raises:
        trueup.config.ConfigError: `root` is not a git work tree, or
            `git ls-files` fails (arch: D15.2).
    """
    if not in_work_tree(root):
        raise ConfigError(f"{root}: not a git repository; trueup reads tracked files")
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="surrogateescape",  # arch: D12.10
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _git_failure(root, "ls-files", exc) from exc
    paths = [path for path in result.stdout.split("\0") if path]
    if ignore:
        paths = [path for path in paths if not matches_ignore(path, ignore)]
    return tuple(sorted(paths))


def _tool_names() -> frozenset[str]:
    """Give every executable name any rule set of `RULESETS` calls for.

    Returns:
        The set of tool names to probe with `shutil.which`.
    """
    return frozenset(tool for rule_set in RULESETS.values() for tool in rule_set.tools)


def _language_stats(
    root: Path, files: tuple[str, ...]
) -> tuple[dict[str, LangStat], str]:
    """Count files and code lines per language.

    Uses `tokei --output json` when `tokei` is on the path and its output
    parses, else the built-in counter (D5.4). This function returns which
    one ran, since `shutil.which("tokei")` alone would say the wrong thing
    when `tokei` is on the path but `_tokei_counts` falls back (a run
    failure or output that does not parse).

    Args:
        root: The repository root.
        files: The surveyed files, repo-relative. `MANAGED_CODE_FILES`
            are left out of both counters.

    Returns:
        Language name to `LangStat`, one entry per `LANGUAGE_EXTENSIONS`
        key, paired with `"tokei"` or `"built-in"` naming the counter used.
    """
    if shutil.which("tokei") is not None:
        counts = _tokei_counts(root, files)
        if counts is not None:
            return counts, "tokei"
    counted = tuple(path for path in files if path not in MANAGED_CODE_FILES)
    return _builtin_counts(root, counted), "built-in"


def _tokei_counts(root: Path, files: tuple[str, ...]) -> dict[str, LangStat] | None:
    """Count files and code lines with `tokei --output json`, scoped to `files`.

    tokei scans `root` itself, so its raw report includes paths the survey
    already dropped (an ignore glob, `.gitignore`, a file outside git). This
    function post-filters tokei's per-file `reports` entries to `files` (the
    surveyed set) before summing, so a counted file is a surveyed file no
    matter which counter ran (arch: D6.14, I-13).

    Args:
        root: The repository root.
        files: The surveyed files, repo-relative. `MANAGED_CODE_FILES` are
            left out, matching `_builtin_counts`.

    Returns:
        The per-language counts, or `None` when `tokei` could not be run,
        did not end within `TOKEI_TIMEOUT_S`, or its output could not be
        parsed, so the caller falls back to the built-in counter. On
        expiry one line on standard error names tokei and the limit
        (D16.10).
    """
    try:
        result = subprocess.run(
            ["tokei", "--output", "json", str(root)],
            capture_output=True,
            text=True,
            check=True,
            timeout=TOKEI_TIMEOUT_S,
        )
        report = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print(
            f"trueup: tokei did not end in {TOKEI_TIMEOUT_S} s;"
            " the survey uses the built-in line counter",
            file=sys.stderr,
        )
        return None
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    allowed = {
        (root / path).resolve() for path in files if path not in MANAGED_CODE_FILES
    }
    stats: dict[str, LangStat] = {}
    for language, tokei_names in _TOKEI_NAMES.items():
        file_count = 0
        code_lines = 0
        for name in tokei_names:
            entry = report.get(name)
            if not isinstance(entry, dict):
                continue
            for item in entry.get("reports", []):
                # tokei's per-file entry: {"name": <path>, "stats": {"code": n, ...}}.
                if not isinstance(item, dict):
                    continue
                if (root / str(item.get("name", ""))).resolve() not in allowed:
                    continue
                file_count += 1
                code_lines += int(item.get("stats", {}).get("code", 0))
        stats[language] = LangStat(
            files=file_count,
            code_lines=code_lines,
            present=file_count >= _PRESENT_MIN_FILES
            and code_lines >= _PRESENT_MIN_LINES,
        )
    return stats


def _builtin_counts(root: Path, files: tuple[str, ...]) -> dict[str, LangStat]:
    """Count files and non-comment, non-blank lines per language, in pure Python.

    Args:
        root: The repository root.
        files: The surveyed files, repo-relative.

    Returns:
        Language name to `LangStat`, one entry per `LANGUAGE_EXTENSIONS` key.
    """
    stats: dict[str, LangStat] = {}
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        leaders = _COMMENT_LEADERS[language]
        matched = [path for path in files if path.endswith(extensions)]
        code_lines = 0
        for path in matched:
            text = _read_text(root, path)
            if text is None:
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith(leaders):
                    code_lines += 1
        stats[language] = LangStat(
            files=len(matched),
            code_lines=code_lines,
            present=len(matched) >= _PRESENT_MIN_FILES
            and code_lines >= _PRESENT_MIN_LINES,
        )
    return stats


def _read_text(root: Path, rel: str) -> str | None:
    """Read a tracked file as text through `fsread`, 1 MiB at most (D15.22).

    Args:
        root: The repository root.
        rel: The repo-relative path.

    Returns:
        The decoded text, or `None` when the file cannot be read, is a
        device, a symlink out of the root, or is longer than 1 MiB. A
        file that gives `None` still counts as a file, with 0 lines.
    """
    return fsread.read_text_capped(root, rel, _TEXT_READ_CAP)


def _has_workspace(root: Path) -> bool:
    """Say whether the root declares a Cargo, pnpm, npm or Go workspace.

    Args:
        root: The repository root.

    Returns:
        True when `Cargo.toml` has a `[workspace]` table, `pnpm-workspace.yaml`
        exists, `package.json` has a `workspaces` key, or `go.work` exists.
    """
    if (root / "go.work").is_file() or (root / "pnpm-workspace.yaml").is_file():
        return True
    if "[workspace]" in (_read_text(root, "Cargo.toml") or ""):
        return True
    raw = fsread.read_capped(root, "package.json", _TEXT_READ_CAP)
    if raw is not None:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}  # D15.1: an unreadable manifest counts as absent
        if isinstance(data, dict) and "workspaces" in data:
            return True
    return False


def _count_contributors(root: Path) -> int:
    """Count the distinct author emails of the last twelve months.

    Args:
        root: The repository root.

    Returns:
        The count; 0 for a branch with no commit yet.

    Raises:
        trueup.config.ConfigError: `git log` fails on a branch that has a
            commit (arch: D15.2).
    """
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return 0  # unborn HEAD: `git log` exits 128 there
    except OSError as exc:
        raise _git_failure(root, "rev-parse", exc) from exc
    try:
        result = subprocess.run(
            ["git", "log", "--since=12.months", "--format=%ae"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _git_failure(root, "log", exc) from exc
    return len({line for line in result.stdout.splitlines() if line})


def _count_tags(root: Path) -> int:
    """Count the repository's git tags.

    Args:
        root: The repository root.

    Returns:
        The count.

    Raises:
        trueup.config.ConfigError: `git tag` fails (arch: D15.2).
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--list"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _git_failure(root, "tag", exc) from exc
    return len([line for line in result.stdout.splitlines() if line])


_TIER_ORDER: tuple[str, ...] = ("T0", "T1", "T2", "T3")


def _pick_tier(
    *,
    override: str,
    total_lang_files: int,
    file_count: int,
    manifests: tuple[str, ...],
    workspace: bool,
    contributors: int,
    has_ci: bool,
    tags: int,
) -> tuple[str, str]:
    """Pick a tier, first match wins, unless `trueup.toml` overrides it (D5.4).

    Args:
        override: The `tier` value from `trueup.toml`: `auto`, `T0`, `T1`,
            `T2` or `T3`.
        total_lang_files: The sum of `LangStat.files` across every language;
            this reading of D5.4's "five files or fewer in any one language"
            treats it as a total code-file count, since D5.4 also fixes T1's
            file count to `len(Survey.files)` (a repo total) rather than a
            per-language one.
        file_count: The number of surveyed files that trueup did not
            write (`is_trueup_path`, D12.9).
        manifests: The survey's `manifests` that `_tier_manifest`
            accepts, less any path that trueup writes (D12.9).
        workspace: The survey's `workspace` flag.
        contributors: The survey's `contributors` count.
        has_ci: The survey's `has_ci` flag.
        tags: The survey's `tags` count.

    Returns:
        The tier and a one-line reason.
    """
    if override != "auto" and override in _TIER_ORDER:
        return override, f"{override} (set in trueup.toml)"
    if workspace or len(manifests) >= 3 or contributors >= 10:
        reasons = []
        if workspace:
            reasons.append("a workspace")
        if len(manifests) >= 3:
            reasons.append(f"{len(manifests)} manifests")
        if contributors >= 10:
            reasons.append(f"{contributors} contributors")
        return "T3", "T3 (" + ", ".join(reasons) + ")"
    if total_lang_files <= 5 and not manifests and not has_ci:
        return "T0", "T0 (5 or fewer language files, no manifest, no CI)"
    if file_count <= 50 and contributors <= 2 and tags == 0:
        return "T1", "T1 (50 or fewer files, 2 or fewer contributors, not tagged)"
    return "T2", "T2 (default: none of T0, T1 or T3 applied)"
