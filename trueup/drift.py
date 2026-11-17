"""Docs drift rows: compare what the docs say against what the code has (D6.5).

`drift_findings` is the only entry point `report.collect` calls. Every rule
reads files it already has in memory or on disk; none spawns a process and
none calls `shutil.which` (I-18, I-21). "Docs" means `README.md` and
each `docs/**/*.md` path; this module reads them from the survey's own
`files`, the same stand-in `docrules._docs_pages` uses for "tracked", since
`Survey` does not keep the tracked/untracked split and a second `git` call
here would break the no-subprocess rule.

Four rules:

- `drift-flag`: a doc line invokes a known project command with a `--flag`
  the command's own argument parser does not define.
- `drift-undocumented`: a flag the code defines appears in no doc.
- `drift-package`: the README's install section runs an install command for
  another package, never this project's own.
- `drift-command`: a doc's shell block runs a path this repository does not
  have, an `npm run` script `package.json` does not define, or a `make`
  target the `Makefile` does not define.
"""

from __future__ import annotations

import ast
import json
import re
import fnmatch
import tomllib
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trueup import fsread
from trueup.findings import Finding
from trueup.survey import Survey

_TESTS_PREFIX = "tests/"

_TEXT_READ_CAP = 1024 * 1024
"""The largest file, in bytes, that drift reads as text (D15.22)."""

_FENCE_INFO = frozenset({"sh", "bash", "shell", "console", "fish", ""})
"""The fenced-block info strings D6.5 reads; only the info string's first
word counts, so `sh lint:python` still reads as `sh`."""

_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_FLAG_TOKEN = re.compile(r"(?<![\w-])(--[A-Za-z][\w-]*)")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")
_SHELL_SEPARATOR = re.compile(r"&&|\|\||;|\|")

_NPM_RUN = re.compile(r"^npm run (\S+)")
_MAKE_RUN = re.compile(r"^make (\S+)")
_INTERPRETERS = frozenset({"python3", "python", "sh", "bash", "node", "php", "ruby"})
_SCRIPT_EXTENSIONS = (".py", ".sh", ".js", ".ts", ".rb", ".php", ".pl")
_PLACEHOLDER_CHARS = frozenset("<>$(){}*")

_INSTALL_HEADING = re.compile(r"^#{1,6}\s+.*install.*$", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+")
_INSTALL_LINE = re.compile(
    r"^(?:pip install\b|uv tool install\b|uv add\b|pipx install\b|"
    r"npm (?:i|install)\b|cargo install\b|go install\b.*@|"
    r"go install \.(?:/\.\.\.)?(?:\s|$)|go get\b|composer require\b)"
)

_GO_MODULE = re.compile(r"^module\s+\"?([^\s\"]+)\"?\s*$", re.MULTILINE)
"""The `module` line of `go.mod`: the module path, quoted or not."""

_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)")

_GO_FLAG = re.compile(r"\.(?:Persistent)?Flags\(\)\.\w+\([^,]+,\s*\"([^\"]+)\"")
_GO_STD_TYPES = r"(?:Bool|String|Int|Int64|Uint|Uint64|Float64|Duration)"
_GO_STD_FLAG = re.compile(r"\bflag\." + _GO_STD_TYPES + r"\(\s*\"([^\"]+)\"")
_GO_STD_FLAG_VAR = re.compile(
    r"\bflag\." + _GO_STD_TYPES + r"Var\(\s*[^,()]+,\s*\"([^\"]+)\""
)
_RUST_ARG_LONG = re.compile(r'#\[arg\([^)]*\blong\s*=\s*"([^"]+)"')
_RUST_LONG_METHOD = re.compile(r'\.long\("([^"]+)"\)')


@dataclass(frozen=True)
class _Command:
    """One project command a doc line can invoke.

    Attributes:
        name: The literal text a doc line must hold, for example
            `"python3 trueup"`.
        source: The repo-relative path whose static scan gave `flags`, used
            in the `drift-undocumented` id.
        flags: The command's static flag set.
    """

    name: str
    source: str
    flags: frozenset[str]


def drift_findings(
    survey: Survey,
    only: frozenset[str] | None,
    ignored: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Run the D6.5 docs drift rows over one survey.

    Args:
        survey: The survey to check.
        only: Repo-relative POSIX paths to scope the run to (D6.17).
            `None` gives every finding. A value gives the findings of the
            full run whose `path` is in `only`, and no other finding. The
            manifests, the flag sources and the path set are facts about
            the whole repository, so every rule reads them from the full
            `survey.files`, also in a scoped run. Only the docs that
            `drift-flag`, `drift-package` and `drift-command` read are
            narrowed to `only`, since each of their findings has its doc as
            its `path`. In a scoped run, `drift-undocumented` parses only
            the `.py` files in `only`, and `drift-flag` parses only the
            `.py` files that a doc in `only` runs (D14.14).
        ignored: Command-path tokens that git ignores (D15.17).
            `report.collect` computes them with one `git check-ignore`;
            this module spawns no process. A `drift-command` token in this
            set gives an `info` finding, not a `warn`.

    Returns:
        The findings of every rule in this module, unsorted, in the same
        shape `hygiene.hygiene_findings` and `docrules.docrules_findings`
        return theirs.
    """
    files = survey.files
    all_docs = _doc_paths(files)
    docs = [doc for doc in all_docs if only is None or doc in only]
    if only is not None and not docs and not any(_may_be_source(path) for path in only):
        return []
    tracked = frozenset(files)
    wanted = None if only is None else _python_scope(survey.root, docs, only)
    commands = (
        _python_commands(survey.root, files, wanted)
        + _go_commands(survey.root, files)
        + _rust_commands(survey.root, files)
    )
    findings: list[Finding] = _manifest_findings(survey.root, files)
    findings.extend(_flag_findings(survey.root, docs, commands))
    findings.extend(_undocumented_findings(survey.root, all_docs, commands))
    findings.extend(_package_findings(survey.root, docs, files))
    findings.extend(_command_findings(survey.root, docs, files, tracked, ignored))
    if only is not None:
        findings = [finding for finding in findings if finding.path in only]
    return findings


def _may_be_source(path: str) -> bool:
    """Say whether a `drift-undocumented` finding can have `path` as its `path`.

    Args:
        path: One repo-relative POSIX path of a scoped run's `only`.

    Returns:
        True for a `.py` file, `go.mod` and `Cargo.toml`: the `source` of
        each `_Command` that `_python_commands`, `_go_commands` and
        `_rust_commands` give.
    """
    return path.endswith(".py") or path in ("go.mod", "Cargo.toml")


def _python_scope(
    root: Path, docs: list[str], only: frozenset[str]
) -> Callable[[str, frozenset[str]], bool]:
    """Give the test that selects the `.py` files a scoped run parses (D14.14).

    A scoped run keeps only the findings whose `path` is in `only` (D6.17).
    A `drift-undocumented` finding of a Python command has the `.py` file
    as its `path`, so only the files in `only` can give one that stays. A
    `drift-flag` finding has a doc in `only` as its `path`, and it reads
    only the commands that the doc runs. Thus a file that is not in `only`
    and that no doc in `only` runs can give no finding that stays.

    Args:
        root: The repository root.
        docs: The docs of the scoped run, all in `only`.
        only: The repo-relative POSIX paths of the scoped run.

    Returns:
        A test that takes a `.py` path and its command names. It is true
        when the path is in `only`, or when some text that `_flag_findings`
        reads in `docs` runs one of the names.
    """
    candidates: list[str] = []
    for doc in docs:
        text = _read_text(root, doc)
        if text is not None:
            candidates.extend(_doc_candidates(text))
    joined = "\n".join(candidates)
    named: dict[str, bool] = {}

    def runs(name: str) -> bool:
        if name not in named:
            named[name] = name in joined and any(
                _command_args(candidate, name) for candidate in candidates
            )
        return named[name]

    def wanted(path: str, names: frozenset[str]) -> bool:
        return path in only or any(runs(name) for name in sorted(names))

    return wanted


def _read_text(root: Path, rel: str) -> str | None:
    """Read a tracked file as text through `fsread`, 1 MiB at most (D15.22).

    Args:
        root: The repository root.
        rel: The repo-relative path.

    Returns:
        The decoded text, or `None` when the file cannot be read, is a
        device, a symlink out of the root, or is longer than 1 MiB.
    """
    return fsread.read_text_capped(root, rel, _TEXT_READ_CAP)


def _load_json(root: Path, rel: str) -> object | None:
    """Read and parse one JSON file.

    Args:
        root: The repository root.
        rel: The repo-relative path of the file.

    Returns:
        The parsed value, or `None` when the file is missing or not valid
        JSON.
    """
    text = _read_text(root, rel)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _load_toml(root: Path, rel: str) -> dict | None:
    """Read and parse one TOML file.

    Args:
        root: The repository root.
        rel: The repo-relative path of the file.

    Returns:
        The parsed table, or `None` when the file is missing or not valid
        TOML.
    """
    text = _read_text(root, rel)
    if text is None:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def _table(value: object) -> dict:
    """Give a manifest value as a table (arch: D15.1).

    Args:
        value: A value from a parsed manifest.

    Returns:
        `value` when it is a `dict`, else an empty `dict`, so a reader never
        calls `.get` on a string or a list.
    """
    return value if isinstance(value, dict) else {}


_TABLE_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pyproject.toml", ("project",)),
    ("pyproject.toml", ("project", "scripts")),
    ("Cargo.toml", ("package",)),
)
"""The manifest keys that the readers expect to be tables (arch: D15.1)."""


def _manifest_findings(root: Path, files: tuple[str, ...]) -> list[Finding]:
    """Give one `drift-manifest` info row for each manifest key that is not a table (arch: D15.1).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        At most one `info` row for each manifest. The readers skip the key.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    for name, keys in _TABLE_KEYS:
        if name not in files or name in seen:
            continue
        value: object = _load_toml(root, name)
        for position, key in enumerate(keys):
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
            if not isinstance(value, dict):
                seen.add(name)
                dotted = ".".join(keys[: position + 1])
                findings.append(
                    Finding(
                        id=f"drift-manifest:{name}",
                        rule="drift-manifest",
                        category="docs",
                        severity="info",
                        path=name,
                        evidence=f"manifest not readable: {dotted} is not a table",
                        action="fix the manifest so the drift rows can read it",
                        auto=False,
                    )
                )
                break
    return findings


def _doc_paths(files: tuple[str, ...]) -> list[str]:
    """Give the doc paths D6.5 reads, in `files` order.

    Args:
        files: The full surveyed files.

    Returns:
        `README.md` when it is in `files`, then each `docs/**/*.md` path in
        `files`.
    """
    return [
        path
        for path in files
        if path == "README.md" or (path.startswith("docs/") and path.endswith(".md"))
    ]


# -- Static flag sets, one per language -----------------------------------


def _callee_name(func: ast.expr) -> str | None:
    """Give the dotted text of a call's callee, for example `"parser.add_argument"`.

    Args:
        func: The `Call.func` node.

    Returns:
        The unparsed text, or `None` when it cannot be unparsed.
    """
    try:
        return ast.unparse(func)
    except (ValueError, TypeError):
        return None


def _string_flags(args: list[ast.expr]) -> set[str]:
    """Give each string constant argument that starts with `--`.

    Args:
        args: The positional arguments of one call.

    Returns:
        The matching argument values.
    """
    return {
        arg.value
        for arg in args
        if isinstance(arg, ast.Constant)
        and isinstance(arg.value, str)
        and arg.value.startswith("--")
    }


def _python_flags(path: Path) -> frozenset[str]:
    """Give the static flag set of one Python source file (D6.5).

    Args:
        path: The file to scan. `fsread` reads it with the parent
            directory as the root, so a symlink to another directory is
            refused (D15.22).

    Returns:
        Every string constant passed to `.add_argument(` that starts with
        `--`, and every `click.option("--x")` flag; empty when the file
        cannot be read or parsed, or defines no such call. A parse error
        is a `SyntaxError`, a `ValueError`, a `RecursionError` (D14.12
        C1) or a `MemoryError` (D15.1): one bad file must not stop the run.
    """
    text = _read_text(path.parent, path.name)
    if text is None:
        return frozenset()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            tree = ast.parse(text, filename=str(path))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return frozenset()
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _callee_name(node.func)
        if callee is None:
            continue
        if callee.endswith(".add_argument") or callee == "click.option":
            flags.update(_string_flags(node.args))
    return frozenset(flags)


def _project_scripts(root: Path, files: tuple[str, ...]) -> dict[str, str]:
    """Give each `[project.scripts]` name mapped to the `.py` file it runs.

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        Script name to repo-relative POSIX path; a name whose module does
        not resolve to a file in `files` is left out.
    """
    if "pyproject.toml" not in files:
        return {}
    data = _load_toml(root, "pyproject.toml")
    if not isinstance(data, dict):
        return {}
    scripts = _table(data.get("project")).get("scripts")
    if not isinstance(scripts, dict):
        return {}
    result: dict[str, str] = {}
    for name, target in scripts.items():
        if not isinstance(target, str):
            continue
        module = target.split(":", 1)[0].strip()
        candidate = module.replace(".", "/") + ".py"
        if candidate in files:
            result[name] = candidate
    return result


def _python_commands(
    root: Path,
    files: tuple[str, ...],
    wanted: Callable[[str, frozenset[str]], bool] | None = None,
) -> list[_Command]:
    """Give each Python command D6.5 can check, by static scan (D6.5).

    A file with an empty flag set gives no command at all, so it can never
    yield a `drift-flag` or `drift-undocumented` row (never guess).

    Args:
        root: The repository root.
        files: The full surveyed files.
        wanted: A test that takes a `.py` path and its command names and
            says whether to parse the file. `None` parses every file. A
            scoped run gives the test of `_python_scope` (D14.14).

    Returns:
        One `_Command` per alias (`python3 <path>`, `python3 <pkgdir>`, or a
        `[project.scripts]` name) of each `.py` file outside `tests/` with a
        non-empty flag set.
    """
    scripts = _project_scripts(root, files)
    commands: list[_Command] = []
    for path in sorted(
        p for p in files if p.endswith(".py") and not p.startswith(_TESTS_PREFIX)
    ):
        names = {f"python3 {path}"}
        segment = path.split("/", 1)[0]
        if path == f"{segment}/__main__.py" and f"{segment}/__init__.py" in files:
            names.add(f"python3 {segment}")
        names.update(name for name, target in scripts.items() if target == path)
        if wanted is not None and not wanted(path, frozenset(names)):
            continue
        flags = _python_flags(root / path)
        if not flags:
            continue
        for name in sorted(names):
            commands.append(_Command(name=name, source=path, flags=flags))
    return commands


def _go_commands(root: Path, files: tuple[str, ...]) -> list[_Command]:
    """Give the one Go command D6.5 can check, from the root `go.mod` (D6.5).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        A single `_Command` named after `go.mod`'s module's last segment,
        or an empty list when `go.mod` is not surveyed, missing, has no
        module line, or no `.go` file declares a flag.
    """
    if "go.mod" not in files:
        return []
    text = _read_text(root, "go.mod")
    if text is None:
        return []
    module = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("module "):
            module = line[len("module ") :].strip()
            break
    if not module:
        return []
    flags: set[str] = set()
    for path in files:
        if not path.endswith(".go"):
            continue
        source = _read_text(root, path)
        if source is None:
            continue
        flags.update(_GO_FLAG.findall(source))
        flags.update(_GO_STD_FLAG.findall(source))
        flags.update(_GO_STD_FLAG_VAR.findall(source))
    if not flags:
        return []
    command_name = module.rsplit("/", 1)[-1]
    return [
        _Command(
            name=command_name,
            source="go.mod",
            flags=frozenset(f"--{flag}" for flag in flags),
        )
    ]


def _rust_flags(root: Path, files: tuple[str, ...], prefix: str) -> frozenset[str]:
    """Give the `long` flags of every `.rs` file under `prefix` (D6.5, D15.17).

    Args:
        root: The repository root.
        files: The full surveyed files.
        prefix: A directory with a trailing `/`, or `""` for the whole tree.

    Returns:
        Each flag name with a leading `--`.
    """
    flags: set[str] = set()
    for path in files:
        if not path.endswith(".rs") or not path.startswith(prefix):
            continue
        source = _read_text(root, path)
        if source is None:
            continue
        flags.update(_RUST_ARG_LONG.findall(source))
        flags.update(_RUST_LONG_METHOD.findall(source))
    return frozenset(f"--{flag}" for flag in flags)


def _workspace_members(root_data: dict, files: tuple[str, ...]) -> list[str]:
    """Give the member directories of a Cargo `[workspace]` root (D15.17).

    Args:
        root_data: The parsed root `Cargo.toml`.
        files: The full surveyed files.

    Returns:
        Each directory whose `Cargo.toml` is surveyed and whose path
        matches a `members` pattern (`fnmatch`), sorted.
    """
    members = _table(root_data.get("workspace")).get("members")
    if not isinstance(members, list):
        return []
    patterns = [m.rstrip("/") for m in members if isinstance(m, str)]
    found: set[str] = set()
    for path in files:
        if not path.endswith("/Cargo.toml"):
            continue
        directory = path[: -len("/Cargo.toml")]
        if any(fnmatch.fnmatchcase(directory, pattern) for pattern in patterns):
            found.add(directory)
    return sorted(found)


def _rust_commands(root: Path, files: tuple[str, ...]) -> list[_Command]:
    """Give the Rust commands D6.5 can check, from `Cargo.toml` (D6.5, D15.17).

    A root `[package]` gives one command that reads every `.rs` file. A
    root `[workspace]` gives one command for each member that has
    `src/main.rs` or a `[[bin]]` table, with the flags of that member's
    `.rs` files only.

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        The commands; empty when `Cargo.toml` is not surveyed or missing,
        or no command has a `long` flag.
    """
    if "Cargo.toml" not in files:
        return []
    data = _load_toml(root, "Cargo.toml")
    if not isinstance(data, dict):
        return []
    commands: list[_Command] = []
    name = _table(data.get("package")).get("name")
    if isinstance(name, str) and name:
        flags = _rust_flags(root, files, "")
        if flags:
            commands.append(_Command(name=name, source="Cargo.toml", flags=flags))
    for directory in _workspace_members(data, files):
        manifest = f"{directory}/Cargo.toml"
        member = _load_toml(root, manifest)
        if not isinstance(member, dict):
            continue
        member_name = _table(member.get("package")).get("name")
        if not isinstance(member_name, str) or not member_name:
            continue
        if f"{directory}/src/main.rs" not in files and not member.get("bin"):
            continue
        flags = _rust_flags(root, files, directory + "/")
        if flags:
            commands.append(_Command(name=member_name, source=manifest, flags=flags))
    return commands


# -- Doc parsing, shared by drift-flag, drift-package and drift-command ---


def _strip_shell_prefix(line: str) -> str:
    """Drop a leading `$ `, `sudo` and env assignments from one shell line (D6.5).

    Args:
        line: One line already known to sit inside a recognised fenced
            block.

    Returns:
        The line with the prompt and the leading noise removed.
    """
    text = line.strip()
    if text.startswith("$ "):
        text = text[2:].strip()
    changed = True
    while changed:
        changed = False
        if text.startswith("sudo "):
            text = text[len("sudo ") :].strip()
            changed = True
            continue
        match = _ENV_ASSIGNMENT.match(text)
        if match:
            text = text[match.end() :].strip()
            changed = True
    return text


def _fenced_lines(text: str) -> list[tuple[int, str]]:
    """Give every line inside a fenced block with a recognised info string (D6.5).

    A closing fence is a line holding only the opening fence's character,
    three or more times; any other content on that line keeps the block
    open, so a fence tagged `sh lint:python` (`comment-standard.md`) still
    reads as `sh`.

    Args:
        text: One doc's content.

    Returns:
        `(line number, cleaned line)` pairs, one per non-blank source line
        inside such a block, cleaned by `_strip_shell_prefix`.
    """
    lines: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_ok = False
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if in_fence:
            if stripped and set(stripped) == {fence_char} and len(stripped) >= 3:
                in_fence = False
                continue
            if fence_ok and stripped:
                lines.append((number, _strip_shell_prefix(raw)))
            continue
        match = _FENCE_OPEN.match(stripped)
        if match:
            in_fence = True
            fence_char = match.group(1)[0]
            info = (
                match.group(2).strip().split()[0].lower()
                if match.group(2).strip()
                else ""
            )
            fence_ok = info in _FENCE_INFO
    return lines


def _inline_spans(text: str) -> list[str]:
    """Give the inner text of every inline code span (D6.5).

    `drift-flag` reads these in addition to fenced lines; the other rules
    do not.

    Args:
        text: One doc's content.

    Returns:
        Each span's inner text, in document order.
    """
    return [match.group(1) for match in _INLINE_CODE.finditer(text)]


def _doc_candidates(text: str) -> list[str]:
    """Give the texts of one doc that `drift-flag` reads (D6.5).

    Args:
        text: One doc's content.

    Returns:
        The cleaned lines of each recognised fenced block, then the inner
        text of each inline code span.
    """
    return [line for _, line in _fenced_lines(text)] + _inline_spans(text)


def _command_args(text: str, name: str) -> list[str]:
    """Give the argument text of each place where `text` runs the command `name` (D6.5).

    A shell line can hold more than one command, split by `&&`, `||`, `;`
    or `|`. A segment runs `name` only when `name` is its first word, after
    `_strip_shell_prefix`. A path before the last word is allowed, so
    `./build/tool` runs `tool`. The name must end at a space or at the end
    of the segment. Thus `docker compose run --rm tool` does not run
    `tool`, and `tool-rotate` is not `tool`.

    Args:
        text: One candidate line or inline-code span.
        name: The command's literal text, for example `"python3 trueup"`.

    Returns:
        The text after `name` in each segment that runs it. The list is
        empty when no segment runs `name`.
    """
    pattern = re.compile(r"^(?:\S*/)?" + re.escape(name) + r"(?=\s|$)")
    args: list[str] = []
    for segment in _SHELL_SEPARATOR.split(text):
        segment = _strip_shell_prefix(segment)
        match = pattern.match(segment)
        if match:
            args.append(segment[match.end() :])
    return args


def _mentions_flag(text: str, flag: str) -> bool:
    """Say whether `text` names one flag, as its own token.

    Args:
        text: The text to search.
        flag: The flag, for example `"--changed"`.

    Returns:
        True when `flag` appears in `text` with no letter, digit, `_` or
        `-` touching either side.
    """
    pattern = re.compile(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])")
    return pattern.search(text) is not None


# -- drift-flag and drift-undocumented ------------------------------------


def _flag_findings(
    root: Path, docs: list[str], commands: list[_Command]
) -> list[Finding]:
    """R `drift-flag`: a doc invokes a command with a flag it does not have (D6.5).

    Args:
        root: The repository root.
        docs: The doc paths to read.
        commands: The commands `_python_commands`, `_go_commands` and
            `_rust_commands` found.

    Returns:
        One `warn` finding per `(doc, flag)` pair where some candidate text
        of that doc invokes a known command with a `--flag` outside its
        static flag set.
    """
    if not commands:
        return []
    findings: list[Finding] = []
    for doc in docs:
        text = _read_text(root, doc)
        if text is None:
            continue
        candidates = _doc_candidates(text)
        bad: dict[str, None] = {}
        for candidate in candidates:
            for command in commands:
                for args in _command_args(candidate, command.name):
                    for flag in _FLAG_TOKEN.findall(args):
                        if flag not in command.flags:
                            bad.setdefault(flag, None)
        for flag in sorted(bad):
            findings.append(
                Finding(
                    id=f"drift-flag:{doc}:{flag}",
                    rule="drift-flag",
                    category="docs",
                    severity="warn",
                    path=doc,
                    evidence=f"{doc} uses {flag}, which the command's own parser does not define",
                    action="fix the doc, or add the flag to the argument parser",
                    auto=False,
                )
            )
    return findings


def _undocumented_findings(
    root: Path, docs: list[str], commands: list[_Command]
) -> list[Finding]:
    """R `drift-undocumented`: a static flag that no doc names (D6.5).

    Args:
        root: The repository root.
        docs: The doc paths to read.
        commands: The commands to check.

    Returns:
        One `info` finding per `(source file, flag)` pair where `flag` is
        not a substring, as its own token, of any doc's raw text.
    """
    if not commands:
        return []
    doc_text = "\n".join(
        text for text in (_read_text(root, doc) for doc in docs) if text
    )
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for command in commands:
        for flag in sorted(command.flags):
            key = (command.source, flag)
            if key in seen or _mentions_flag(doc_text, flag):
                continue
            seen.add(key)
            findings.append(
                Finding(
                    id=f"drift-undocumented:{command.source}:{flag}",
                    rule="drift-undocumented",
                    category="docs",
                    severity="info",
                    path=command.source,
                    evidence=f"{command.source} defines {flag}. No doc names it",
                    action="document the flag, or remove it if it is dead",
                    auto=False,
                )
            )
    return findings


# -- drift-package ----------------------------------------------------------


def _install_section(text: str) -> list[str] | None:
    """Give the fenced-block lines of README's install section (D6.5).

    Args:
        text: `README.md`'s content.

    Returns:
        The cleaned lines `_fenced_lines` gives for the span between the
        first heading matching `/install/i` and the next heading at the
        same level or shallower, or `None` when no such heading exists.
    """
    lines = text.splitlines()
    start = None
    level = 0
    for number, line in enumerate(lines):
        if _INSTALL_HEADING.match(line.strip()):
            start = number
            level = len(line) - len(line.lstrip("#"))
            break
    if start is None:
        return None
    end = len(lines)
    for number in range(start + 1, len(lines)):
        heading = _HEADING.match(lines[number].strip())
        if heading and len(heading.group(1)) <= level:
            end = number
            break
    return [line for _, line in _fenced_lines("\n".join(lines[start:end]))]


def _manifest_names(root: Path, files: tuple[str, ...]) -> frozenset[str]:
    """Give this project's own package name, per ecosystem manifest (D6.5).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        The `name` field of each root manifest in `files` that has one, and
        the module path of a root `go.mod`.
    """
    names: set[str] = set()
    if "pyproject.toml" in files:
        data = _load_toml(root, "pyproject.toml")
        if isinstance(data, dict):
            name = _table(data.get("project")).get("name")
            if isinstance(name, str):
                names.add(name)
    if "package.json" in files:
        data = _load_json(root, "package.json")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            names.add(data["name"])
    if "Cargo.toml" in files:
        data = _load_toml(root, "Cargo.toml")
        if isinstance(data, dict):
            name = _table(data.get("package")).get("name")
            if isinstance(name, str):
                names.add(name)
    if "composer.json" in files:
        data = _load_json(root, "composer.json")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            names.add(data["name"])
    if "go.mod" in files:
        text = _read_text(root, "go.mod")
        found = _GO_MODULE.search(text) if text is not None else None
        if found is not None:
            names.add(found.group(1))
    return frozenset(names)


def _names_manifest(line: str, manifests: frozenset[str]) -> bool:
    """Say whether one install line names this project's own manifest (D6.5).

    Args:
        line: One cleaned install line.
        manifests: `_manifest_names`' result.

    Returns:
        True when a token of `line` is `.`, `-e` or `-r` (D6.5's "manifest"
        tokens), or equals one of `manifests`. In a `go install` or
        `go get` line, `./...` also counts, and so does a module path with
        its `@<version>` removed that equals a manifest name or is a path
        below it (`<module>/cmd/<name>`). A URL token counts when its last
        path segment, with `@<ref>`, `#<fragment>` and `.git` removed,
        equals a manifest name (`git+https://host/owner/<name>@v1`).
    """
    go = line.startswith(("go install", "go get"))
    for token in line.split():
        token = token.strip(",")
        if token in (".", "-e", "-r") or token in manifests:
            return True
        if "://" in token:
            last = token.partition("#")[0].rstrip("/").rpartition("/")[2]
            if last.partition("@")[0].removesuffix(".git") in manifests:
                return True
        if not go:
            continue
        path = token.partition("@")[0]
        if token == "./..." or any(  # noqa: S105  # reason: token is an argv string, not a credential
            path == name or path.startswith(name + "/") for name in manifests
        ):
            return True
    return False


def _package_findings(
    root: Path, docs: list[str], files: tuple[str, ...]
) -> list[Finding]:
    """R `drift-package`: README installs another package, never this one (D6.5).

    Args:
        root: The repository root.
        docs: The doc paths to read; the rule reads only `README.md`.
        files: The full surveyed files, for the manifest read.

    Returns:
        A single `warn` finding when the install section holds at least
        one recognised install line and none of them names this project's
        manifest, else an empty list.
    """
    path = "README.md"
    if path not in docs:
        return []
    text = _read_text(root, path)
    if text is None:
        return []
    section = _install_section(text)
    if section is None:
        return []
    install_lines = [line for line in section if _INSTALL_LINE.match(line)]
    if not install_lines:
        return []
    manifests = _manifest_names(root, files)
    if any(_names_manifest(line, manifests) for line in install_lines):
        return []
    return [
        Finding(
            id=f"drift-package:{path}",
            rule="drift-package",
            category="docs",
            severity="warn",
            path=path,
            evidence=(
                f"{path}'s install section holds {len(install_lines)} install "
                "line(s); none names this project's own package"
            ),
            action="name the project's own package, or '.', in an install line",
            auto=False,
        )
    ]


# -- drift-command ------------------------------------------------------


def _npm_scripts(root: Path, files: tuple[str, ...]) -> frozenset[str] | None:
    """Give `package.json`'s `scripts` keys (D6.5).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        The script names, or `None` when `package.json` is not surveyed,
        missing or not an object (never guess).
    """
    if "package.json" not in files:
        return None
    data = _load_json(root, "package.json")
    if not isinstance(data, dict):
        return None
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return frozenset()
    return frozenset(scripts)


def _make_targets(root: Path, files: tuple[str, ...]) -> frozenset[str] | None:
    """Give the `Makefile`'s own target names (D6.5).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        The target names, or `None` when `Makefile` is not surveyed or
        missing.
    """
    if "Makefile" not in files:
        return None
    text = _read_text(root, "Makefile")
    if text is None:
        return None
    targets: set[str] = set()
    for line in text.splitlines():
        if line.startswith("\t") or line.startswith("#"):
            continue
        match = _MAKE_TARGET.match(line)
        if match and "%" not in match.group(1):
            targets.add(match.group(1))
    return frozenset(targets)


def _bad_command_token(
    line: str,
    tracked: frozenset[str],
    npm_scripts: frozenset[str] | None,
    make_targets: frozenset[str] | None,
) -> str | None:
    """Give the id token of one `drift-command` defect on `line`, if any (D6.5).

    Args:
        line: One cleaned fenced-block line.
        tracked: The full surveyed file set (D6.5). A path candidate
            present here is never a defect.
        npm_scripts: `_npm_scripts`' result.
        make_targets: `_make_targets`' result.

    Returns:
        `"npm-run:<script>"`, `"make:<target>"` or the bad path itself,
        matching `line`'s form; `None` when `line` names no defect, or
        checking it would need a manifest (`package.json`, `Makefile`)
        that the survey does not have.
    """
    match = _NPM_RUN.match(line)
    if match:
        script = match.group(1)
        if npm_scripts is not None and script not in npm_scripts:
            return f"npm-run:{script}"
        return None
    match = _MAKE_RUN.match(line)
    if match:
        target = match.group(1)
        if make_targets is not None and target not in make_targets:
            return f"make:{target}"
        return None
    tokens = line.split()
    if not tokens:
        return None
    candidate: str | None = None
    if tokens[0] in _INTERPRETERS and len(tokens) > 1:
        candidate = tokens[1]
    elif tokens[0].startswith("./") or tokens[0].startswith("../"):
        candidate = tokens[0]
    if candidate is None:
        return None
    candidate = candidate.strip("'\"")
    if not candidate or candidate.startswith(("-", "/")) or "://" in candidate:
        return None
    if any(char in candidate for char in _PLACEHOLDER_CHARS):
        return None
    if not ("/" in candidate or candidate.endswith(_SCRIPT_EXTENSIONS)):
        return None
    relative = candidate[2:] if candidate.startswith("./") else candidate
    if relative in tracked:
        return None
    return candidate


def missing_command_paths(survey: Survey) -> list[str]:
    """Give the path tokens `drift-command` would flag, for `git check-ignore` (D15.17).

    Args:
        survey: The survey to check.

    Returns:
        Each missing path token of every doc, once, in first-seen order.
        An `npm run` or `make` defect is not a path and is left out.
    """
    files = survey.files
    tracked = frozenset(files)
    npm_scripts = _npm_scripts(survey.root, files)
    make_targets = _make_targets(survey.root, files)
    tokens: dict[str, None] = {}
    for doc in _doc_paths(files):
        text = _read_text(survey.root, doc)
        if text is None:
            continue
        for _, line in _fenced_lines(text):
            token = _bad_command_token(line, tracked, npm_scripts, make_targets)
            if token is not None and not token.startswith(("npm-run:", "make:")):
                tokens.setdefault(token, None)
    return list(tokens)


def _named_in_build_files(root: Path, files: tuple[str, ...]) -> str:
    """Give the Makefile text and the `package.json` script values as one string (D15.17).

    Args:
        root: The repository root.
        files: The full surveyed files.

    Returns:
        The joined text; empty when neither file gives any.
    """
    parts: list[str] = []
    if "Makefile" in files:
        text = _read_text(root, "Makefile")
        if text:
            parts.append(text)
    if "package.json" in files:
        data = _load_json(root, "package.json")
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if isinstance(scripts, dict):
            parts.extend(v for v in scripts.values() if isinstance(v, str))
    return "\n".join(parts)


def _command_findings(
    root: Path,
    docs: list[str],
    files: tuple[str, ...],
    tracked: frozenset[str],
    ignored: frozenset[str] = frozenset(),
) -> list[Finding]:
    """R `drift-command`: a doc's shell block runs something this repository lacks (D6.5).

    Args:
        root: The repository root.
        docs: The doc paths to read (narrowed to `only` in a scoped run, D6.17).
        files: The full surveyed files, read for the
            `package.json`/`Makefile` manifests `npm_scripts` and
            `make_targets` come from.
        tracked: The full surveyed file set, for
            `_bad_command_token`'s path-existence check (D6.5).
        ignored: Path tokens that git ignores (D15.17). A token in it, or
            one that a Makefile or a `package.json` script names, gives
            `info`.

    Returns:
        One `warn` finding per `(doc, token)` pair `_bad_command_token`
        flags.
    """
    npm_scripts = _npm_scripts(root, files)
    make_targets = _make_targets(root, files)
    build_text = _named_in_build_files(root, files)
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for doc in docs:
        text = _read_text(root, doc)
        if text is None:
            continue
        for _, line in _fenced_lines(text):
            token = _bad_command_token(line, tracked, npm_scripts, make_targets)
            if token is None or (doc, token) in seen:
                continue
            seen.add((doc, token))
            is_path = not token.startswith(("npm-run:", "make:"))
            relative = token[2:] if token.startswith("./") else token
            quiet = is_path and (
                token in ignored or (bool(build_text) and relative in build_text)
            )
            findings.append(
                Finding(
                    id=f"drift-command:{doc}:{token}",
                    rule="drift-command",
                    category="docs",
                    severity="info" if quiet else "warn",
                    path=doc,
                    evidence=f"{doc} runs {token!r}, which this repository does not have",
                    action="fix the doc to name a real path, script or target",
                    auto=False,
                )
            )
    return findings
