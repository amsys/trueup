# Managed by trueup. Edit trueup.toml, then run the trueup skill.
"""Check that each reference in the source matches its target.

This file holds the scan, the checks, the report, the edge file and the
entry points.

The `trueup refs` subcommand runs this module as the check command. The
`[refs] path` config key names where a target keeps its copy of this file,
and `trueup apply` writes that copy. The checker has three entry points
and one worker, `run`. The command line prints a report and sets the exit
code. Ten pytest functions assert that the report holds no failure of
their kinds. A direct run with no argument repeats the command line.

The checker uses the standard library only, and it stays one file. A copy
with a different name, in a different directory, operates in the same way.
"""

import ast
import bisect
import collections
import functools
import glob
import hashlib
import html
import json
import os
import re
import stat
import sys
import tokenize
import tomllib
import traceback
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve()
"""The checker file itself, as an absolute path."""

ROOT = next(
    (
        parent
        for parent in HERE.parents
        if os.path.exists(parent / "ref_check.toml")
        or os.path.exists(parent / "docs" / "ARCHITECTURE.md")
    ),
    HERE.parents[1],
)
"""The default root: the first parent that holds a configuration or a design."""

SKIP_DIRS = {
    "node_modules",
    "vendor",
    "graphify-out",
    "site-packages",
    "target",
    "venv",
}
"""Directory names that the walk does not enter, at each depth (D1.2).

They hold code from other parties or build output that is not a copy of the
source. `build` and `dist` are not in the set: they hold copies of the source,
and a stale copy gives a failure that the user can see. Nothing can add to
this set (I-2).
"""

REGISTRY: dict[str, tuple[str, str]] = {
    "ref": ("a reference to a target", "checks a, d"),
    "arch": ("a test proves these design ids", "checks a, b, c"),
    "law": ("code implements this section of law", "checks a, d"),
    "SAFETY": ("why an `unsafe` block is sound (Rust)", "clippy"),
    "TODO": ("work that is owed, with a link", "ruff `TD` rules in Python"),
}
"""The closed registry of marker words. Each value is (meaning, checked by)."""


@dataclass(frozen=True, order=True)
class Failure:
    """One failure of one check, at one place in one file.

    The print order of a report is the sort order of these fields.

    Attributes:
        path: The file, relative to the root, with `/` as the separator.
        line: The line, which starts at 1.
        kind: The kind of the failure, for example `unknown-id`.
        detail: The text that follows the kind on the printed line.
    """

    path: str
    line: int
    kind: str
    detail: str


KINDS: tuple[str, ...] = (
    "unknown-id",
    "no-target",
    "malformed",
    "unmarked",
    "unproved",
    "drift",
    "unregistered",
    "no-reason",
    "no-header",
    "broken-link",
    "unreadable",
    "no-front-matter",
    "bad-field",
    "misplaced",
    "unindexed",
    "duplicate-id",
    "stale-pin",
    "no-readme",
    "no-title",
    "no-description",
    "no-section",
    "misordered",
    "no-licence-file",
    "badges-scattered",
    "no-index-link",
)
"""The closed set of failure kinds, in the order of the table of D2.4."""


def format_failure(failure: Failure) -> str:
    """Give the printed line of one failure.

    The format is `<path>:<line>: [<kind>] <detail>`. When the failure has
    an id, the detail ends with that id, so the id is the last text of the
    line.

    Args:
        failure: The failure to print.

    Returns:
        One line, with no line end.
    """
    return f"{failure.path}:{failure.line}: [{failure.kind}] {failure.detail}"


_ID_SEPARATORS = re.compile(r"[\s,]+")
"""The runs of white space or commas that a failure id's tail writes as `-` (D9.2)."""


def failure_ids(failures: Sequence[Failure]) -> list[str]:
    """Give each failure its id: the key of `[keep] failures` and of a trueup `refcheck:` finding (D9.2).

    Args:
        failures: The failures, in the order of the report.

    Returns:
        One id per failure, in the same order: `<path>:<line>:<kind>`;
        where two failures share that text, each gets `:<tail>` added, the
        text after the last `": "` of its detail (the whole detail when it
        holds none) with each run of white space or commas written as `-`;
        where ids still repeat, each gets `:<n>`, counting from 1 in the
        given order.
    """
    bases = [f"{item.path}:{item.line}:{item.kind}" for item in failures]
    base_counts = collections.Counter(bases)
    ids: list[str] = []
    for base, item in zip(bases, failures, strict=True):
        if base_counts[base] > 1:
            tail = item.detail.rsplit(": ", 1)[-1].strip()
            base = f"{base}:{_ID_SEPARATORS.sub('-', tail)}"
        ids.append(base)
    id_counts = collections.Counter(ids)
    counts: dict[str, int] = {}
    unique: list[str] = []
    for failure_id in ids:
        if id_counts[failure_id] > 1:
            counts[failure_id] = counts.get(failure_id, 0) + 1
            unique.append(f"{failure_id}:{counts[failure_id]}")
        else:
            unique.append(failure_id)
    return unique


def keep_match(failure_id: str, keep: Iterable[str]) -> str | None:
    """Give the `[keep] failures` entry that keeps one failure id, or `None` (D15.8).

    This is a copy of `trueup.findings.keep_match`, since this file runs
    alone. A test pins the two equal. The match is segment-bounded: an
    entry `k` keeps `k` and each id that starts with `k + ":"`.

    Args:
        failure_id: The failure id, from `failure_ids`.
        keep: The `[keep] failures` entries.

    Returns:
        The exact entry, else the longest entry that is a segment prefix of
        `failure_id`, else `None`.
    """
    if failure_id in keep:
        return failure_id
    prefixes = [k for k in keep if failure_id.startswith(k + ":")]
    return max(prefixes, key=len) if prefixes else None


def _detail(kind: str, unit: str, tail: str) -> str:
    """Join a unit and the tail of a resolution into the detail of D2.4.

    Args:
        kind: The kind of the failure.
        unit: The unit that holds the marker.
        tail: The text of the line that follows the unit.

    Returns:
        The detail text. The kind `unknown-id` takes no colon after the
        unit, because the legacy selftest greps `<unit> cites <id>`.
    """
    return f"{unit} cites {tail}" if kind == "unknown-id" else f"{unit}: {tail}"


@dataclass(frozen=True)
class Edge:
    """One reference, as one record of the edge file.

    The field order is the key order of the JSON record. The records of the
    edge file are sorted by `source`, `line`, `target` and `id`.

    Attributes:
        source: The file that holds the marker, relative to the root.
        line: The line of the marker, which starts at 1.
        unit: The module, class or function that holds the marker. The regex
            languages give `-`.
        marker: The keyword as written.
        target: The name of the target, `arch` or `law`.
        id: The canonical id inside that target.
        status: `ok`, or the kind of the failure of check a or check d.
    """

    source: str
    line: int
    unit: str
    marker: str
    target: str
    id: str
    status: str


@dataclass
class Report:
    """The result of one checker run.

    Attributes:
        failures: The failures, sorted, less the kept ones.
        edges: One record for each reference, sorted.
        excused: The ids that an open plan row excuses in check c, sorted as
            text (D2.8).
        config: The configuration that this run read (D4.1).
        kept: The failures that `[keep] failures` names, sorted (D9.2).
            They are not printed and not counted.
        warnings: One pair (change name, failure) for each failure that a
            registered reader change turned into a warning, sorted (D16.3).
            They do not change the exit code.
    """

    failures: list[Failure]
    edges: list[Edge]
    excused: list[str]
    config: "Config"
    kept: list[Failure] = field(default_factory=list)
    warnings: list[tuple[str, Failure]] = field(default_factory=list)


Resolution = tuple[str, str] | None
"""The result for one reference.

`None` when the reference resolves. Otherwise a pair (kind, tail). The kind
is one of `KINDS`. The tail is the text of the failure line that follows the
unit name, because a target function does not know the unit. `_detail` joins
the unit and the tail into the detail of D2.4.
"""

Resolver = Callable[[Path, Path, str], Resolution]
"""The shape of a target function. Each target takes the same three arguments."""


_DESIGN_HEADING = re.compile(r"^## (D\d+\.\d+) ", re.M)
_DESIGN_INVARIANT = re.compile(r"^- \*\*(I-\d+)\b", re.M)
_ANY_ID = re.compile(r"D\d+\.\d+|I-\d+")
_VERIFICATION = re.compile(r"^## Verification\s*$", re.M)
_NEXT_HEADING = re.compile(r"^## ", re.M)
_OPEN_ROW = re.compile(r"\|\s*open\s*\|")


def _decode_python(path: Path) -> str:
    """Decode one Python source file by its own encoding declaration (D1.2).

    A byte order mark, or else a PEP 263 `coding:` comment on line 1 or 2,
    picks the codec. This is the one decoder for every `.py` read (R-12).

    Args:
        path: The `.py` file to read.

    Returns:
        The text of the file, decoded by its own rule.

    Raises:
        OSError: The file cannot be read, or `_read_bytes` refuses it.
        SyntaxError: The file names a codec that Python does not know.
        UnicodeDecodeError: The file does not decode as its declared codec.
    """
    data = _read_bytes(path)
    encoding, _ = tokenize.detect_encoding(BytesIO(data).readline)
    return _universal_newlines(data.decode(encoding))


_READ_CAP = 16 * 1024 * 1024
"""The longest file, in bytes, that the checker reads (D16.10, I-50)."""

_CONFIG_READ_CAP = _READ_CAP
"""The longest configuration file, in bytes, that `load_config` reads
(D16.10, I-50). The value is fixed at import. The configuration is not a
target file, so a change of `_READ_CAP` for the target files does not
apply to it."""

_run_root: Path | None = None
"""The resolved root of the current `run`, for the symlink test of
`_read_bytes` (D16.10). `run` sets it, as it clears the read caches."""


def _read_bytes(path: Path, cap: int | None = None) -> bytes:
    """Read one file with the limits of I-50 (D16.10).

    The checker ships as one file, so it cannot import `trueup.fsread`.
    The open does not block on a FIFO, and the test of the file type comes
    after the open, so the file cannot change between the two.

    Args:
        path: The file to read.
        cap: The longest file, in bytes. `None` gives `_READ_CAP`.

    Returns:
        The bytes of the file.

    Raises:
        OSError: The file cannot be opened, is not a regular file, is
            larger than `_READ_CAP`, or is a symlink out of the root of
            the run.
    """
    if (
        _run_root is not None
        and os.path.islink(path)
        and not Path(os.path.realpath(path)).is_relative_to(_run_root)
    ):
        raise OSError(f"symlink out of the root: {path}")
    return _read_capped(path, cap)


def _read_capped(path: Path, cap: int | None = None) -> bytes:
    """Read one regular file up to `_READ_CAP`, and follow a symlink (I-50).

    Args:
        path: The file to read.
        cap: The longest file, in bytes. `None` gives `_READ_CAP`.

    Returns:
        The bytes of the file.

    Raises:
        OSError: The file cannot be opened, is not a regular file, or is
            larger than `_READ_CAP`.
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        handle = os.fdopen(descriptor, "rb")
    except OSError:
        os.close(descriptor)
        raise
    with handle:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"not a regular file: {path}")
        limit = _READ_CAP if cap is None else cap
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise OSError(f"file over the read cap: {path}")
    return data


def _universal_newlines(text: str) -> str:
    """Give text the line ends that a text-mode read gives (D16.10).

    Args:
        text: The decoded text.

    Returns:
        The text with each CRLF and CR changed to LF.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_utf8(path: Path, cap: int | None = None) -> str:
    """Read one file as UTF-8 with a bounded read and universal newlines.

    Args:
        path: The file to read.
        cap: The longest file, in bytes. `None` gives `_READ_CAP`.

    Returns:
        The text of the file.

    Raises:
        OSError: `_read_bytes` refuses the file.
        UnicodeDecodeError: The file is not UTF-8.
    """
    return _universal_newlines(_read_bytes(path, cap).decode("utf-8-sig"))


@functools.cache
def _read_text(path: Path) -> str:
    """Read one target file, one time for each run (D4.1).

    `run` clears this cache first, so a later run reads the file again. An
    error is not cached. A `.py` path decodes by `_decode_python` (R-12);
    every other path decodes as UTF-8.

    Args:
        path: The file to read.

    Returns:
        The text of the file.

    Raises:
        OSError: The file cannot be read.
        SyntaxError: A `.py` file names a codec that Python does not know.
        UnicodeDecodeError: The file is not the codec it declares or UTF-8.
    """
    if path.suffix == ".py":
        return _decode_python(path)
    return _read_utf8(path)


@functools.cache
def _design_ids(design: Path) -> frozenset[str]:
    """List the design ids that `docs/ARCHITECTURE.md` declares.

    Args:
        design: The design file, which exists.

    Returns:
        The declared ids. The two regexes are those of the existing checker.

    Raises:
        OSError: The file cannot be read.
        UnicodeDecodeError: The file is not UTF-8.
    """
    text = _read_text(design)
    return frozenset(_DESIGN_HEADING.findall(text)) | frozenset(
        _DESIGN_INVARIANT.findall(text)
    )


def _verification_claims(design: Path) -> list[tuple[str, int]]:
    """List the ids that the section `## Verification` of the design claims.

    Args:
        design: The design file.

    Returns:
        One pair (id, line) for each claimed id, in order. The list is empty
        when the file is absent or holds no such section.
    """
    try:
        text = _read_text(design)
    except (OSError, UnicodeDecodeError):
        return []
    return _claims_in_text(text, _ANY_ID)


def _claims_in_text(text: str, any_id: re.Pattern[str]) -> list[tuple[str, int]]:
    """List the ids that the section `## Verification` of one text claims.

    Args:
        text: The text of one design page.
        any_id: The pattern that finds an id in a line.

    Returns:
        One pair (id, line) for each claimed id, in order. The line is the
        first line under the section that names the id. The list is empty
        when the text holds no such section.
    """
    head = _VERIFICATION.search(text)
    if head is None:
        return []
    tail = _NEXT_HEADING.search(text, head.end())
    body = text[head.end() : tail.start() if tail else len(text)]
    first = text.count("\n", 0, head.end()) + 1
    seen: dict[str, int] = {}
    for offset, line in enumerate(body.splitlines(), start=first):
        for ident in any_id.findall(line):
            seen.setdefault(ident, offset)
    return sorted(seen.items(), key=lambda item: (item[1], item[0]))


def _open_plan_ids(plan: Path, any_id: re.Pattern[str] = _ANY_ID) -> set[str]:
    """List the ids that an open row of `PLAN.md` still owns.

    Args:
        plan: The plan file. An absent file gives no open row.
        any_id: The pattern that finds an id in a row.

    Returns:
        The ids of every table row whose state cell is `open`.
    """
    try:
        text = _read_utf8(plan)
    except (OSError, UnicodeDecodeError):
        return set()
    rows = [
        line
        for line in text.splitlines()
        if line.startswith("|") and _OPEN_ROW.search(line)
    ]
    return set(any_id.findall(" ".join(rows)))


_TEST_STEMS = ("_test", ".test", ".spec")


def _is_test_file(relative: Path, language: str) -> bool:
    """Tell whether one source file is a test file, by the rule of D1.2.

    Args:
        relative: The path of the file, relative to the root.
        language: The language that the extension table gives.

    Returns:
        True for a test file.
    """
    if language == "python":
        return relative.name.startswith("test_")
    return "tests" in relative.parts or relative.stem.endswith(_TEST_STEMS)


def _python_test_functions(path: Path) -> list[tuple[int, str]]:
    """List the test functions of one Python file, by dotted name.

    Args:
        path: The file, which parses.

    Returns:
        One pair (line, dotted name) for each function or async function
        whose own name starts with `test_`, at every depth.
    """
    found: list[tuple[int, str]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                if not isinstance(child, ast.ClassDef) and child.name.startswith(
                    "test_"
                ):
                    found.append((child.lineno, name))
                walk(child, name)
            else:
                walk(child, prefix)

    try:
        walk(_parsed_python(path)[1], "")
    except (
        OSError,
        SyntaxError,
        UnicodeDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
    ):
        return []
    return found


def resolve_arch(
    root: Path, archive: Path | None, ident: str, docs_dir: str = "docs"
) -> Resolution:
    """Resolve one design id against `ARCHITECTURE.md` of the docs directory.

    Args:
        root: The repository to examine.
        archive: Not used by this target. It keeps the table uniform.
        ident: The design id, for example `D1.2` or `I-1`.
        docs_dir: The directory below the root that holds the design
            (`[layout] docs_dir`, D14.5).

    Returns:
        `None` when the id exists. A pair (kind, tail) when it does not. The
        kind `unreadable` means that the design cannot be read; check c gives
        its one failure line.
    """
    design = root / docs_dir / "ARCHITECTURE.md"
    if not os.path.exists(design):
        return ("no-target", f"target arch is not configured: {ident}")
    try:
        ids = _design_ids(design)
    except (OSError, UnicodeDecodeError) as error:
        return ("unreadable", f"file cannot be read: {type(error).__name__}")
    if ident in ids:
        return None
    return ("unknown-id", ident)


def resolve_law(root: Path, archive: Path, ident: str) -> Resolution:
    r"""Resolve one section key against a lawsmu archive (D2.7).

    The pinned file is `<archive>/<law-key>/document.md`, where `<law-key>`
    is the id with its trailing `s.<section>` removed. A section heading is
    a line that matches `^### <section>\\. `, the number compared as exact
    text (D2.7, steps 1-2). The order of versions and the section hash are
    not needed here: the id already names one pinned version. The drift
    check that compares versions is `_check_d` (D4.2).

    `_check_a` calls this only when the configuration names an archive; with
    no archive, it gives `no-target` itself and never calls this function.

    Args:
        root: The repository to examine.
        archive: The archive directory, already made absolute.
        ident: The canonical key, for example `acts/Income_Tax_Act/v13/s.111`.

    Returns:
        `None` when the section exists. A pair (kind, detail) when it does not.
    """
    law_key, sep, section = ident.rpartition("/")
    if not sep or not section.startswith("s."):
        return ("unknown-id", ident)
    pinned = archive / law_key / "document.md"
    if not os.path.isfile(pinned):
        return ("unknown-id", ident)
    try:
        pinned_hash = _file_section_hash(pinned, section[2:])
    except (OSError, UnicodeDecodeError) as error:
        return ("unreadable", f"file cannot be read: {type(error).__name__}")
    if pinned_hash is None:
        return ("unknown-id", ident)
    return None


_ID_FORM_HOLE = re.compile(r"<[a-z]+>")
"""One placeholder of an `id_forms` entry. It means digits (D16.2)."""

_ID_FORM_GLUED = re.compile(r"<[a-z]+>(?:<[a-z]+>|\d)")
"""A placeholder that a digit or a placeholder follows. The digits of the
first placeholder would have no end, so a match would need backtracking
(D16.2)."""

_ID_FORM_BANNED = re.compile(r"[\s,]")
"""The characters that an `id_forms` entry cannot hold (D16.2)."""

_ID_FORM_MAX_LENGTH = 24
"""The longest `id_forms` entry, in characters (D16.2)."""

_ID_FORMS_MAX = 16
"""The largest number of `id_forms` entries (D16.2)."""

_DEFAULT_ID_FORMS = ("D<n>.<m>", "I-<n>")
"""The forms of the configured reader when `[targets.arch] forms` is absent."""

_ID_END = r"(?!\w|\.\w)"
"""What cannot follow a configured id: more of a token (D16.2)."""


def _id_form_is_valid(form: str) -> bool:
    """Tell if one `id_forms` entry has the shape of D16.2.

    `config.py` holds a copy of this rule, because the checker is one file
    and the package cannot import it. A test keeps the two copies equal.

    Args:
        form: The entry, for example `D<n>.<m>`.

    Returns:
        True when the form is at most 24 characters, holds no white space
        and no comma, holds one placeholder and one literal character or
        more, and no placeholder comes just before a digit or a placeholder.
    """
    return (
        len(form) <= _ID_FORM_MAX_LENGTH
        and _ID_FORM_BANNED.search(form) is None
        and _ID_FORM_HOLE.search(form) is not None
        and _ID_FORM_HOLE.sub("", form) != ""
        and _ID_FORM_GLUED.search(form) is None
    )


@dataclass(frozen=True)
class IdGrammar:
    """The compiled patterns of one list of id forms (D16.2).

    Attributes:
        whole: Matches a text that is one id, with `match`. It has the role
            of `_ARCH_ID`.
        anywhere: Finds each id of a free text. It has the role of `_ANY_ID`.
        declaration: Matches one Markdown line that declares an id. Each
            alternative has one group, the id.
    """

    whole: re.Pattern[str]
    anywhere: re.Pattern[str]
    declaration: re.Pattern[str]


def _id_grammar(forms: Sequence[str]) -> IdGrammar:
    """Compile a list of forms that `load_config` accepted (D16.2).

    Each placeholder compiles to a possessive digit run, so a target cannot
    make the checker backtrack. A form compiles from its own text only.

    Args:
        forms: The forms, for example `("D<n>.<m>", "I-<n>")`.

    Returns:
        The patterns, with the longest form first.
    """
    ident = "(?:{})".format(
        "|".join(
            r"\d++".join(re.escape(part) for part in _ID_FORM_HOLE.split(form))
            for form in sorted(forms, key=lambda item: (-len(item), item))
        )
    )
    heading = rf" {{0,3}}#{{1,6}}[ \t]+({ident}){_ID_END}"
    table = rf"[ \t]*\|[ \t]*(?:\*\*)?({ident})(?:\*\*)?[ \t]*\|"
    bold = rf"[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?\*\*[ \t]*({ident}){_ID_END}"
    return IdGrammar(
        re.compile(rf"{ident}\Z"),
        re.compile(rf"(?<![\w.]){ident}{_ID_END}"),
        re.compile(f"{heading}|{table}|{bold}"),
    )


@dataclass(frozen=True)
class DeclaredSources:
    """The sources of the configured reader, after one read (D16.2).

    Attributes:
        grammar: The compiled id forms.
        texts: One pair (path as written, text) for each source that the
            reader read, in order.
        ids: Every id that a read source declares.
        missing: The entries that name no file, in order.
        unreadable: One `unreadable` failure for each source that is found
            and cannot be read.
    """

    grammar: IdGrammar
    texts: tuple[tuple[str, str], ...]
    ids: frozenset[str]
    missing: tuple[str, ...]
    unreadable: tuple[Failure, ...]


def _expand_entry(root: Path, entry: str) -> list[str]:
    """Give the files that one `declared` entry names.

    Args:
        root: The repository to examine.
        entry: A path or a glob, relative to the root. It may hold `..`.

    Returns:
        The paths as written, relative to the root, sorted. The list is
        empty when the entry names nothing.
    """
    if glob.has_magic(entry):
        return sorted(glob.glob(entry, root_dir=root, recursive=True))
    return [entry] if os.path.exists(root / entry) else []


def _declared_in_text(text: str, grammar: IdGrammar) -> set[str]:
    """List the ids that one page declares, by the shapes of D16.2.

    Args:
        text: The text of the page.
        grammar: The compiled id forms.

    Returns:
        The ids of each line outside a fenced block that declares one.
    """
    ids: set[str] = set()
    for line in _md_lines_outside_fences(text):
        found = grammar.declaration.match(line)
        if found is not None:
            ids.add(found.group(found.lastindex))
    return ids


def _read_declared_sources(root: Path, config: "Config") -> DeclaredSources | None:
    """Read the sources of the configured reader (D16.2).

    Args:
        root: The repository to examine.
        config: The configuration of the root.

    Returns:
        The sources, or `None` when neither `sources` nor `forms` is set, so
        that the checker keeps its one page and its constants (I-54).
    """
    if not config.declared and not config.id_forms:
        return None
    grammar = _id_grammar(config.id_forms or _DEFAULT_ID_FORMS)
    entries = config.declared or (f"{config.docs_dir}/ARCHITECTURE.md",)
    named: dict[str, None] = {}
    missing: list[str] = []
    for entry in entries:
        matched = _expand_entry(root, entry)
        if not matched:
            missing.append(entry)
        named.update(dict.fromkeys(matched))
    texts: list[tuple[str, str]] = []
    ids: set[str] = set()
    unreadable: list[Failure] = []
    for shown in named:
        try:
            text = _universal_newlines(_read_capped(root / shown).decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError) as error:
            detail = f"file cannot be read: {type(error).__name__}"
            unreadable.append(Failure(shown, 1, "unreadable", detail))
            continue
        texts.append((shown, text))
        ids |= _declared_in_text(text, grammar)
    return DeclaredSources(
        grammar, tuple(texts), frozenset(ids), tuple(missing), tuple(unreadable)
    )


def _resolve_declared(declared: DeclaredSources, ident: str) -> Resolution:
    """Resolve one design id against the read sources (D16.2).

    Args:
        declared: The sources of the configured reader.
        ident: The cited id.

    Returns:
        `None` when a read source declares the id. Otherwise `no-target`
        when a source is missing, `unreadable` when a source cannot be read,
        because then the reader cannot decide, else `unknown-id` (I-55).
    """
    if ident in declared.ids:
        return None
    if declared.missing:
        return ("no-target", "")
    if declared.unreadable:
        return ("unreadable", "")
    return ("unknown-id", ident)


TARGETS: dict[str, Resolver] = {"arch": resolve_arch, "law": resolve_law}
"""The closed table of targets. A new target is a change to the design."""


def _section_text(text: str, section: str) -> str | None:
    """Give the text of one section, or `None` when the section is absent.

    The section starts at its heading line and ends before the next line
    that matches `^#{1,3} `, or at the end of the file (D2.7, steps 2-3).

    Args:
        text: The document text to search.
        section: The section number, compared as exact text.

    Returns:
        The section text, or `None` when no heading matches.
    """
    heading = re.compile(rf"^### {re.escape(section)}\. ", re.M)
    match = heading.search(text)
    if match is None:
        return None
    end_heading = re.compile(r"^#{1,3} ", re.M)
    end_match = end_heading.search(text, match.end())
    end = end_match.start() if end_match else len(text)
    return text[match.start() : end]


def _normalised_hash(text: str) -> str:
    """Give the SHA-256 of one normalised text (D2.7, step 4).

    Normalisation replaces each run of white space with one space and
    removes white space at the two ends.

    Args:
        text: The text to hash.

    Returns:
        The hex digest.
    """
    normalised = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _section_hash(text: str, section: str) -> str | None:
    """Give the SHA-256 of one normalised section, or `None` when absent (D2.7, step 4).

    Args:
        text: The document text to search.
        section: The section number, compared as exact text.

    Returns:
        The hex digest, or `None` when the section is absent.
    """
    section_text = _section_text(text, section)
    if section_text is None:
        return None
    return _normalised_hash(section_text)


@functools.cache
def _file_section_hash(path: Path, section: str) -> str | None:
    """Give the section hash of one law document, one time for each run (D4.1).

    Args:
        path: The `document.md` file.
        section: The section number, compared as exact text.

    Returns:
        The hex digest, or `None` when the section is absent.

    Raises:
        OSError: The file cannot be read.
        UnicodeDecodeError: The file is not UTF-8.
    """
    return _section_hash(_read_text(path), section)


@functools.cache
def _newest_version(archive: Path, doc_type_slug: str) -> str | None:
    """Give the newest version directory that holds a `document.md` (D2.7, step 5).

    The order is `base` first, then `v<N>` by the integer `N`.

    Args:
        archive: The archive directory, already made absolute.
        doc_type_slug: The `<doc-type>/<slug>` path, relative to the archive.

    Returns:
        The version directory name, or `None` when none holds a `document.md`.
    """
    base_dir = archive / doc_type_slug
    if not os.path.isdir(base_dir):
        return None
    candidates: list[tuple[int, str]] = []
    for entry in base_dir.iterdir():
        if not os.path.isdir(entry) or not os.path.isfile(entry / "document.md"):
            continue
        if entry.name == "base":
            candidates.append((-1, entry.name))
            continue
        match = re.fullmatch(r"v(\d+)", entry.name)
        if match is not None:
            candidates.append((int(match.group(1)), entry.name))
    if not candidates:
        return None
    return max(candidates)[1]


def _check_d(archive: Path | None, edges: list[Edge]) -> list[Failure]:
    """Compare each resolved `law` reference with the newest version (D4.2).

    Args:
        archive: The law archive, already made absolute. `None` when the
            configuration sets no archive; no `law` reference resolves then.
        edges: The references that check a resolved, each with its status.

    Returns:
        One `unknown-id` failure for each pinned section absent from the
        newest version, and one `drift` failure for each section whose hash
        changed. One `unreadable` failure, at the reference, when a version
        listing or a document cannot be read (I-4). No failure when the pin
        is already the newest version, or when the section text is unchanged.
    """
    failures: list[Failure] = []
    if archive is None:
        return failures
    for edge in edges:
        if edge.target != "law" or edge.status != "ok":
            continue
        law_key, sep, section_part = edge.id.rpartition("/")
        if not sep:
            continue
        doc_type_slug, sep2, pinned_version = law_key.rpartition("/")
        if not sep2:
            continue
        section = section_part[2:]
        try:
            newest_version = _newest_version(archive, doc_type_slug)
            if newest_version is None:
                # Check a found the pinned file, so the listing lost it since then.
                raise FileNotFoundError(archive / law_key / "document.md")
            if newest_version == pinned_version:
                continue
            newest_hash = _file_section_hash(
                archive / doc_type_slug / newest_version / "document.md", section
            )
            pinned_hash = _file_section_hash(archive / law_key / "document.md", section)
        except (OSError, UnicodeDecodeError) as error:
            detail = f"file cannot be read: {type(error).__name__}"
            failures.append(Failure(edge.source, edge.line, "unreadable", detail))
            continue
        if newest_hash is None:
            tail = f"section absent in {newest_version}: {edge.id}"
            failures.append(
                Failure(edge.source, edge.line, "unknown-id", f"{edge.unit}: {tail}")
            )
            continue
        if pinned_hash != newest_hash:
            tail = f"section text changed in {newest_version}: {edge.id}"
            failures.append(
                Failure(
                    edge.source, edge.line, "drift", _detail("drift", edge.unit, tail)
                )
            )
    return failures


@dataclass(frozen=True)
class MarkerPosition:
    """One place where the position rule allows a marker.

    Attributes:
        line: The line, which starts at 1.
        unit: The module, class or function that holds the position. The
            regex languages give `-`.
        text: The line, with the comment leader and its leading white space
            removed. A docstring line keeps its own text unchanged.
        docstring: True for a line of a docstring, False for a comment. The
            legacy rule of D2.1 reads a docstring line only.
    """

    line: int
    unit: str
    text: str
    docstring: bool = False


READER_CHANGES: dict[str, Callable[[str, MarkerPosition], bool]] = {}
"""The reader changes of the last release that still warn (D16.3).

A name maps to a predicate on (language, position). A failure from a marker
at a position that a predicate matches is a warning, not a failure, until the
target lists the name in `[targets.arch] accepted`. The table is empty in this
release.
"""

_CHANGE_KINDS = frozenset(
    {"unknown-id", "no-target", "malformed", "unregistered", "drift"}
)
"""The failure kinds that warn at a matched position by their kind (D16.3).

Another check gives `malformed` or `no-target` only for a Markdown page or a
missing source, and neither has a marker position. `unreadable` is not here:
other checks give it too, so `run` matches it on the read of the marker.
"""

_CHANGE_NAME = re.compile(r"[^\s,]+")
"""The form of one name in `[targets.arch] accepted` (D16.3)."""


EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
}
"""The extension table of the scanner. An unlisted extension is never a source."""


def _python_units(tree: ast.Module) -> list[tuple[int, int, str]]:
    """List the class and function spans of a module, by dotted name.

    Args:
        tree: The parsed module.

    Returns:
        A list of (first line, last line, dotted name), one entry for each
        class or function definition, at every depth.
    """
    units: list[tuple[int, int, str]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                units.append((child.lineno, child.end_lineno or child.lineno, name))
                walk(child, name)
            else:
                walk(child, prefix)

    walk(tree, "")
    return units


def unit_at(units: list[tuple[int, int, str]], line: int) -> str:
    """Give the innermost Python unit of D1.2 that holds a line.

    Args:
        units: The class and function spans of the file, as `_python_units` gives.
        line: The source line to place.

    Returns:
        The dotted name of the smallest span that holds the line, or
        `module` when no span does.
    """
    # `_python_units` lists the spans in source order, so the innermost span
    # that holds the line is the last one that starts at or before it and
    # has not ended (D15.23).
    index = bisect.bisect_right(units, line, key=lambda span: span[0])
    for start, end, name in reversed(units[:index]):
        if start <= line <= end:
            return name
    return "module"


_STRING_OPENING = re.compile(r"[rRuU]?(\"\"\"|'''|\"|')")
"""The prefix and the opening quotes of a string literal."""


@functools.lru_cache(maxsize=8)
def _source_lines(source: str) -> tuple[bytes, ...]:
    r"""Cut a source text into UTF-8 encoded lines, once for each text (D15.23).

    Args:
        source: The text of one file.

    Returns:
        The lines with their ends kept, split at `\n`, `\r\n` and `\r`
        only, as `ast.get_source_segment` splits them.
    """
    return tuple(line.encode() for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+", source))


def _source_segment(source: str, node: ast.expr) -> str | None:
    """Give the source text of a node from the cached line table (D15.23).

    The result equals `ast.get_source_segment(source, node)`; the table is
    built once for a file, so a file with many docstrings is read in linear time.

    Args:
        source: The text of the file.
        node: A node with end positions.

    Returns:
        The text from the node start to its end, or `None` with no end position.
    """
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    lines = _source_lines(source)
    first, last = node.lineno - 1, node.end_lineno - 1
    if last >= len(lines):
        return None
    if first == last:
        return lines[first][node.col_offset : node.end_col_offset].decode()
    parts = [lines[first][node.col_offset :]]
    parts.extend(lines[first + 1 : last])
    parts.append(lines[last][: node.end_col_offset])
    return b"".join(parts).decode()


def _docstring_line_numbers(source: str, node: ast.expr, doc: str) -> list[int]:
    """Give the source line of each line of one docstring.

    An escaped line end in the literal makes a new docstring line on the
    same source line. The line of a marker must be the source line (D2.4).
    The function evaluates the literal up to the end of each source line and
    counts the docstring text that each source line gives.

    Args:
        source: The text of the file.
        node: The string constant of the docstring.
        doc: The docstring value, not cleaned.

    Returns:
        One source line for each entry of `doc.splitlines()`. A literal that
        this method cannot cut, for example two joined strings, gives the
        count from the first line.
    """
    doc_lines = doc.splitlines(keepends=True)
    fallback = [node.lineno + offset for offset in range(len(doc_lines))]
    segment = _source_segment(source, node)
    opening = _STRING_OPENING.match(segment or "")
    if segment is None or opening is None:
        return fallback
    quote = opening.group(1)
    ends: list[int] = []
    cut = 0
    try:
        for raw in segment.split("\n")[:-1]:
            cut += len(raw) + 1
            ends.append(len(ast.literal_eval(segment[:cut] + quote)))
    except (SyntaxError, ValueError):
        return fallback
    numbers: list[int] = []
    start = 0
    for doc_line in doc_lines:
        first = start + len(doc_line) - len(doc_line.lstrip())
        numbers.append(node.lineno + sum(1 for end in ends if end <= first))
        start += len(doc_line)
    return numbers


@functools.cache
def _parsed_python(path: Path) -> tuple[str, ast.Module, list[tuple[int, int, str]]]:
    """Parse one Python file one time for each run (D15.23).

    `run` clears this cache first. An error is not cached.

    Args:
        path: The `.py` file.

    Returns:
        The decoded source, its tree and its unit spans.

    Raises:
        SyntaxError: The file does not parse.
        OSError: The file cannot be read.
    """
    source = _decode_python(path)
    tree = ast.parse(source, filename=str(path))
    return source, tree, _python_units(tree)


@functools.cache
def _comment_tokens(path: Path) -> tuple[tuple[int, str], ...]:
    """Tokenize one Python file one time for each run (D15.23).

    Args:
        path: The `.py` file.

    Returns:
        One pair (line, comment text with its `#`) for each comment token.

    Raises:
        tokenize.TokenError: The file does not tokenize.
        SyntaxError: The file does not tokenize.
    """
    source = _parsed_python(path)[0]
    return tuple(
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(StringIO(source).readline)
        if token.type == tokenize.COMMENT
    )


def _python_positions(path: Path) -> list[MarkerPosition]:
    """Read the marker positions of one Python file: docstring lines and comments.

    Args:
        path: The file to read.

    Returns:
        One entry for each physical line of a module, class or function
        docstring, and one entry for each comment token.

    Raises:
        SyntaxError: The file does not parse.
        OSError: The file cannot be read.
    """
    source, tree, units = _parsed_python(path)

    positions: list[MarkerPosition] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            continue
        doc_node = node.body[0].value
        start_line = doc_node.lineno
        doc_lines = doc.splitlines()
        numbers = _docstring_line_numbers(source, doc_node, doc)
        for offset, doc_line in enumerate(doc_lines):
            positions.append(
                MarkerPosition(
                    numbers[offset], unit_at(units, start_line), doc_line, True
                )
            )

    for line, text in _comment_tokens(path):
        positions.append(MarkerPosition(line, unit_at(units, line), text))

    return positions


_HEREDOC_OPEN = re.compile(r"(?<!<)<<(?!<)(-?)\s*['\"]?(\w+)['\"]?")
"""The operator that opens a shell heredoc. Group 1 is `-` for `<<-`, group 2
the closing word. A `<<<` here-string opens none (D15.18)."""


def _heredoc_lines(lines: list[str]) -> set[int]:
    """Give the index of each heredoc body line and closing line of a shell file.

    A line that holds `<<WORD` or `<<-WORD` opens a heredoc. A later line
    equal to `WORD` closes it; after `<<-`, tabs can come before `WORD`. An
    opening with no closing line opens no heredoc, so a shift such as
    `$((1 << 2))` hides no line. A whole-line comment opens no heredoc
    (D15.18).

    Args:
        lines: The lines of the file.

    Returns:
        The 0-based index of each line inside a heredoc, closing line
        included. The opening line is not inside.
    """
    inside: set[int] = set()
    number = 0
    while number < len(lines):
        line = lines[number]
        number += 1
        if line.lstrip().startswith("#"):
            continue
        for found in _HEREDOC_OPEN.finditer(line):
            tabs, word = found.group(1) == "-", found.group(2)
            for end in range(number, len(lines)):
                candidate = lines[end].lstrip("\t") if tabs else lines[end]
                if candidate == word:
                    inside.update(range(number, end + 1))
                    number = end + 1
                    break
    return inside


def _regex_positions(
    path: Path,
    leaders: Sequence[str],
    doc_leaders: frozenset[str] = frozenset(),
    heredocs: bool = False,
) -> list[MarkerPosition]:
    """Read the whole-line-comment positions of one regex-language file.

    Args:
        path: The file to read.
        leaders: The comment leaders of the language, longest first, for
            example `("///", "//!", "//")`. The first one that starts the
            line is removed.
        doc_leaders: The leaders of a doc comment. Their lines are
            docstring positions, so only rule R2 applies there (D15.19).
        heredocs: True for shell: a heredoc line is no position (D15.18).

    Returns:
        One entry for each line whose comment leader is the first text that
        is not white space, with the leader and its white space removed.

    Raises:
        OSError: The file cannot be read.
    """
    text = _read_utf8(path)
    lines = text.splitlines()
    skipped = _heredoc_lines(lines) if heredocs else set()
    positions: list[MarkerPosition] = []
    for index, line in enumerate(lines):
        if index in skipped:
            continue
        stripped = line.lstrip()
        leader = next((item for item in leaders if stripped.startswith(item)), None)
        if leader is None:
            continue
        # D15.19: `////` is a plain comment in Rust, not a doc comment.
        doc = leader in doc_leaders and not stripped[len(leader) :].startswith("/")
        if leader in doc_leaders and not doc:
            leader = leaders[-1]
        positions.append(
            MarkerPosition(index + 1, "-", stripped[len(leader) :].strip(), doc)
        )
    return positions


READERS: dict[str, Callable[[Path], list[MarkerPosition]]] = {
    "python": _python_positions,
    "rust": lambda path: _regex_positions(
        path, ("///", "//!", "//"), frozenset({"///", "//!"})
    ),
    "typescript": lambda path: _regex_positions(path, ("//",)),
    "shell": lambda path: _regex_positions(path, ("#",), heredocs=True),
    "sql": lambda path: _regex_positions(path, ("--",)),
}
"""The closed table of readers, one for each language of the extension table."""


@dataclass(frozen=True)
class Marker:
    """One recognised marker, parsed into canonical references.

    Attributes:
        keyword: The keyword as written, `ref`, `arch` or `law`.
        refs: The canonical pairs (target, id) of the body, distinct, in the
            order of first mention. A body that repeats a pair gives it one
            time (D2.1, D2.6).
        opt_out: True for an `arch` body of `none`. The body gives no id and
            it marks the unit as excused.
        malformed: True when the keyword is recognised and the body does not
            parse. The pairs are then empty.
        text: The marker as written, without the leader and the white space.
    """

    keyword: str
    refs: tuple[tuple[str, str], ...]
    opt_out: bool
    malformed: bool
    text: str


COMMENT_LEADERS = ("///", "//!", "//", "#", "--")
"""The leaders that a marker position may carry before the keyword."""

_ARCH_ID = re.compile(r"(?:D\d+\.\d+|I-\d+)\Z")
_LAW_KEY = re.compile(r"[a-z_]+/[A-Za-z0-9_]+/(?:base|v\d+)\Z")
_SECTION = re.compile(r"\d+[A-Z]*\Z")
_KEYWORD = re.compile(r"(ref|arch|law):")
_LEGACY = re.compile(r"arch:\s*([^\n]+)", re.I)


def _strip_leader(text: str) -> str:
    """Remove the leading white space and one comment leader of a line.

    Args:
        text: The text of a marker position, as the reader gives it.

    Returns:
        The text that follows the leader, with no leading white space.
    """
    stripped = text.lstrip()
    for leader in COMMENT_LEADERS:
        if stripped.startswith(leader):
            return stripped[len(leader) :].lstrip()
    return stripped


def _parse_law_section(key: str, section: str) -> str | None:
    """Join a law key and a section number into one canonical id.

    Args:
        key: The document key, for example `acts/Income_Tax_Act/v13`.
        section: The section number, for example `111` or `111A`.

    Returns:
        The canonical id, or `None` when one part does not parse.
    """
    if _LAW_KEY.match(key) is None or _SECTION.match(section) is None:
        return None
    return f"{key}/s.{section}"


def _parse_reference(text: str, arch_id: re.Pattern[str]) -> tuple[str, str] | None:
    """Parse one reference of a `ref` body into its canonical pair.

    Args:
        text: One reference, for example `arch/D1.2` or
            `law/acts/Income_Tax_Act/v13/s.111`.
        arch_id: The pattern of a whole design id.

    Returns:
        The pair (target, id), or `None` when the text does not parse.
    """
    target, separator, rest = text.partition("/")
    if not separator or target not in TARGETS:
        return None
    if target == "arch":
        return ("arch", rest) if arch_id.match(rest) else None
    key, mark, section = rest.rpartition("/s.")
    if not mark:
        return None
    ident = _parse_law_section(key, section)
    return ("law", ident) if ident else None


def _distinct(pairs: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Give the pairs one time each, in the order of first mention (D2.1, D2.6).

    Args:
        pairs: The canonical pairs of one body, as written.

    Returns:
        The pairs with each repeat removed.
    """
    return tuple(dict.fromkeys(pairs))


def _parse_ref_body(
    body: str, arch_id: re.Pattern[str]
) -> tuple[tuple[str, str], ...] | None:
    """Parse the body of a `ref` marker: one reference or more.

    Args:
        body: The body text, with the free text already removed.
        arch_id: The pattern of a whole design id.

    Returns:
        The distinct canonical pairs, or `None` when one part does not parse.
    """
    pairs = [_parse_reference(item.strip(), arch_id) for item in body.split(",")]
    if not body or any(pair is None for pair in pairs):
        return None
    return _distinct(pair for pair in pairs if pair is not None)


def _parse_arch_body(
    body: str, arch_id: re.Pattern[str]
) -> tuple[tuple[str, str], ...] | None:
    """Parse the body of an `arch` marker: one design id or more.

    Args:
        body: The body text, with the free text already removed.
        arch_id: The pattern of a whole design id.

    Returns:
        The distinct canonical pairs, or `None` when one part does not parse.
    """
    ids = [item.strip() for item in body.split(",")]
    if not body or any(arch_id.match(item) is None for item in ids):
        return None
    return _distinct(("arch", item) for item in ids)


def _parse_law_body(
    body: str, _arch_id: re.Pattern[str]
) -> tuple[tuple[str, str], ...] | None:
    """Parse the body of a `law` marker: one key and one section.

    Args:
        body: The body text, with the free text already removed.
        _arch_id: Not used. It keeps the table of body parsers uniform.

    Returns:
        The canonical pair, or `None` when the body does not parse.
    """
    key, separator, section = body.partition(" s.")
    if not separator:
        return None
    ident = _parse_law_section(key.strip(), section.strip())
    return (("law", ident),) if ident else None


_BODIES: dict[
    str, Callable[[str, re.Pattern[str]], tuple[tuple[str, str], ...] | None]
] = {
    "ref": _parse_ref_body,
    "arch": _parse_arch_body,
    "law": _parse_law_body,
}
"""One body parser for each keyword of the grammar."""


_LOCAL_TAG = re.compile(r"[A-Z]+")
"""The shape of one prefix of `[registry] local_tags` (D2.5)."""

_R1_TAG = re.compile(r"[A-Z][A-Z0-9_]+(?:\([^)]*\))?:")
_R2_WORD = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):")


def _reference_shape_marker(
    stripped: str, arch_id: re.Pattern[str] = _ARCH_ID
) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    """Give the word and the parsed pairs of one rule R2 candidate of D2.2.

    The remainder must parse as a `ref` body, an `arch` body with one id or
    more, or a `law` body. R2 is the rule that catches a misspelled keyword,
    which otherwise is a reference that no check reads (D2.2): the pairs are
    given here so that check a still resolves it, even though the word fails
    the registry check.

    Args:
        stripped: The text of a marker position, with the leader removed.
        arch_id: The pattern of a whole design id (D16.2).

    Returns:
        The candidate word and its parsed pairs, or `None` when the text is
        not a reference shape.
    """
    found = _R2_WORD.match(stripped)
    if found is None:
        return None
    word = found.group(1)
    rest = stripped[found.end() :]
    if not rest.startswith(" "):
        return None
    body = rest.strip().partition(" - ")[0].strip()
    for parser in _BODIES.values():
        pairs = parser(body, arch_id)
        if pairs is not None:
            return word, pairs
    return None


def _is_local_tag(word: str, local_tags: frozenset[str]) -> bool:
    """Tell if one R1 tag word is a local tag of the repository (D2.5).

    A word is a local tag when it is equal to a prefix of `local_tags`, or
    when it is a prefix followed only by digits.

    Args:
        word: The tag word that rule R1 found.
        local_tags: The prefixes from `[registry] local_tags`.

    Returns:
        True when the word is a local tag.
    """
    for prefix in local_tags:
        if word.startswith(prefix):
            rest = word[len(prefix) :]
            if rest == "" or rest.isdecimal():
                return True
    return False


def marker_candidate(
    text: str,
    docstring: bool,
    local_tags: frozenset[str] = frozenset(),
    arch_id: re.Pattern[str] = _ARCH_ID,
) -> str | None:
    """Give the marker word of one position, by rule R1 or R2 of D2.2.

    Rule R1 (tag) applies to a comment only. Rule R2 (reference shape)
    applies to a comment and to a docstring line. A comment whose R1 tag is
    a local tag gives no candidate (D2.5).

    Args:
        text: The text of one marker position.
        docstring: True for a docstring line, False for a comment.
        local_tags: The prefixes from `[registry] local_tags`.
        arch_id: The pattern of a whole design id (D16.2).

    Returns:
        The candidate word, or `None` when the line holds no candidate.
    """
    stripped = _strip_leader(text)
    if not docstring:
        tag = _R1_TAG.match(stripped)
        if tag is not None:
            word = stripped[: tag.end() - 1].partition("(")[0]
            if _is_local_tag(word, local_tags):
                return None
            return word
    found = _reference_shape_marker(stripped, arch_id)
    return found[0] if found else None


def parse_marker(text: str, arch_id: re.Pattern[str] = _ARCH_ID) -> Marker | None:
    """Parse one marker position by the anchored rule of D2.1.

    The keyword must be the first text of the line, after the leader and the
    white space. Keyword text inside a sentence gives no marker (I-1).

    Args:
        text: The text of one marker position.
        arch_id: The pattern of a whole design id (D16.2).

    Returns:
        A marker, or `None` when the line holds no marker.
    """
    stripped = _strip_leader(text)
    found = _KEYWORD.match(stripped)
    if found is None:
        return None
    keyword = found.group(1)
    written = stripped.strip()
    rest = stripped[found.end() :]
    if not rest.startswith(" "):
        return Marker(keyword, (), False, True, written)
    body = rest.strip().partition(" - ")[0].strip()
    if keyword == "arch" and body.lower() == "none":
        return Marker(keyword, (), True, False, written)
    pairs = _BODIES[keyword](body, arch_id)
    if pairs is None:
        return Marker(keyword, (), False, True, written)
    return Marker(keyword, pairs, False, False, written)


def parse_legacy_marker(text: str, any_id: re.Pattern[str] = _ANY_ID) -> Marker | None:
    """Parse one docstring line of a test file by the legacy rule of D2.1.

    The keyword is found with the regex of the existing checker, with no
    anchor and no case. The ids are every design id of the captured text. A
    captured text with no id, that does not start with `none`, does not
    parse.

    Args:
        text: The text of one docstring line of a `test_*.py` file.
        any_id: The pattern that finds a design id in a text (D16.2).

    Returns:
        A marker, or `None` when the line holds no keyword.
    """
    found = _LEGACY.search(text)
    if found is None:
        return None
    captured = found.group(1).strip()
    written = f"{found.group(0).strip()}"
    if captured.lower().startswith("none"):
        return Marker("arch", (), True, False, written)
    ids = any_id.findall(captured)
    if not ids:
        return Marker("arch", (), False, True, written)
    return Marker(
        "arch", _distinct(("arch", item) for item in ids), False, False, written
    )


def _marker_at(
    position: MarkerPosition,
    legacy: bool,
    arch_id: re.Pattern[str] = _ARCH_ID,
    any_id: re.Pattern[str] = _ANY_ID,
) -> Marker | None:
    """Give the marker of one position, by the rule that the position asks.

    Args:
        position: One marker position of one file.
        legacy: True for a docstring line of a Python test file.
        arch_id: The pattern of a whole design id (D16.2).
        any_id: The pattern that finds a design id in a text (D16.2).

    Returns:
        A marker, or `None` when the position holds no marker.
    """
    if legacy and position.docstring:
        found = parse_legacy_marker(position.text, any_id)
        if found is not None:
            return found
    return parse_marker(position.text, arch_id)


def matches_ignore(path: str, patterns: Sequence[str]) -> bool:
    """Tell if a path matches one glob of `[scan] ignore` (I-2).

    The rules are those of the `ignore` globs of `trueup.toml`: `*`
    matches within one path segment, `**` matches across segments, and `?`
    matches one character. The checker is one file with no import of the
    package, so it holds its own copy of these rules; a test keeps the two
    copies equal.

    Args:
        path: A path relative to the root, with `/` between the parts.
        patterns: The globs.

    Returns:
        True when the path matches at least one glob.
    """
    return any(_glob_to_regex(pattern).match(path) for pattern in patterns)


@functools.cache
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile one glob of `[scan] ignore` into an anchored regex.

    Args:
        pattern: A glob with `*`, `**` and `?`.

    Returns:
        The compiled regex, anchored at both ends.
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


def _iter_source_files(
    root: Path,
    failures: list[Failure] | None = None,
    ignore: Sequence[str] = (),
) -> list[tuple[Path, str]]:
    """Walk the root and list each file the extension table selects.

    The walk does not enter a directory whose name starts with `.`, or whose
    name is in `SKIP_DIRS`, or that holds its own `.git` entry (a nested
    repository, D8.2), at each depth. It reads `build/` and `dist/`. A
    directory that the walk cannot read gives an `unreadable` failure (I-4).
    A file or an unreadable directory whose path matches an `ignore` glob
    is left out (I-2).

    Args:
        root: The repository to examine.
        failures: The failure list that gets one `unreadable` failure for
            each directory that the walk cannot read. `None` drops them.
        ignore: The globs of `[scan] ignore`.

    Returns:
        A sorted list of (path, language) pairs.
    """

    def unreadable(error: OSError) -> None:
        if failures is None:
            return
        relative = Path(error.filename).relative_to(root).as_posix()
        if matches_ignore(relative, ignore):
            return
        detail = f"file cannot be read: {type(error).__name__}"
        failures.append(Failure(relative, 1, "unreadable", detail))

    # D15.23: a glob `<prefix>/**` with no wildcard in its prefix covers
    # every file below `<prefix>`, so the walk does not enter that directory.
    pruned = {
        pattern[: -len("/**")]
        for pattern in ignore
        if pattern.endswith("/**") and not set("*?") & set(pattern[: -len("/**")])
    }
    found: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=unreadable):
        here = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and name not in SKIP_DIRS
            and (f"{here}/{name}" if here != "." else name) not in pruned
            and not _is_nested_repository(Path(dirpath) / name)
        )
        for filename in sorted(filenames):
            language = EXTENSIONS.get(Path(filename).suffix)
            path = Path(dirpath) / filename
            if language is None:
                continue
            if ignore and matches_ignore(path.relative_to(root).as_posix(), ignore):
                continue
            found.append((path, language))
    return sorted(found)


def _is_nested_repository(directory: Path) -> bool:
    """Tell if a directory below the root is another repository (D8.2).

    A submodule holds a `.git` file, a plain clone a `.git` directory. Both
    hold the files of another repository, which has its own checker run,
    the same way `git ls-files` of the root does not list them.

    Args:
        directory: The directory to examine.

    Returns:
        True when `directory/.git` exists, as a file or a directory.
    """
    return os.path.exists(directory / ".git")


def _below_nested_repository(root: Path, path: Path) -> bool:
    """Tell if a path below the root sits inside a nested repository (D8.2).

    Args:
        root: The repository root.
        path: A path below the root.

    Returns:
        True when a directory strictly between the root and the path, or
        the path's own directory, is a nested repository.
    """
    for parent in path.relative_to(root).parents:
        if parent != Path(".") and _is_nested_repository(root / parent):
            return True
    return False


class ConfigError(Exception):
    """The configuration file is not valid. The command line gives exit 2."""


@dataclass(frozen=True)
class Config:
    """The values of `ref_check.toml`, after the schema check of D2.5.

    Attributes:
        registry: The switch of check e. False when the key is absent.
        comments: The switch of check f. False when the key is absent.
        links: The switch of check g. False when the key is absent.
        layout: The switch of check h. False when the key is absent.
        readme: The switch of check i. False when the key is absent.
        licence: The switch of the rule `no-licence-file` and of the
            `License` section that check i asks for. True when the key is
            absent (D15.14).
        archive: The law archive, as an absolute path. `None` when the file
            names no archive.
        local_tags: The prefixes of the local tags that rule R1 does not
            report. Empty when the key is absent.
        keep: The failure ids of `[keep] failures` (D9.2). A failure whose
            id is one of these, or starts with one of these and `:`, is
            kept, not reported (D15.8). Empty when the key is absent.
        ignore: The globs of `[scan] ignore` (I-2). A file whose path
            matches one is not read by any check. Empty when the key is
            absent.
        docs_dir: The documentation directory of `[layout] docs_dir`, one
            path segment below the root (D14.5). `docs` when the key is
            absent.
        front_matter: The switch of the rules `no-front-matter`,
            `bad-field` and `duplicate-id` of check h. True when the key is
            absent.
        types: The switch of the rule `misplaced` of check h. True when the
            key is absent.
        index: The switch of the rule `unindexed` of check h and of the
            rule `no-index-link` of check i. True when the key is absent.
        declared: The entries of `[targets.arch] sources` (D16.2): paths or
            globs of the design pages. Empty when the key is absent.
        id_forms: The entries of `[targets.arch] forms` (D16.2). Empty when
            the key is absent.
        accepted: The entries of `[targets.arch] accepted` (D16.3): the
            reader changes that fail now, not warn. Empty when the key is
            absent.
    """

    registry: bool = False
    comments: bool = False
    links: bool = False
    layout: bool = False
    readme: bool = False
    licence: bool = True
    archive: Path | None = None
    local_tags: frozenset[str] = frozenset()
    keep: frozenset[str] = frozenset()
    ignore: tuple[str, ...] = ()
    docs_dir: str = "docs"
    front_matter: bool = True
    types: bool = True
    index: bool = True
    declared: tuple[str, ...] = ()
    id_forms: tuple[str, ...] = ()
    accepted: frozenset[str] = frozenset()


CONFIG_SCHEMA: dict[str, tuple[str, ...]] = {
    "": ("checks", "registry", "targets", "keep", "scan", "layout"),
    "checks": ("registry", "comments", "links", "layout", "licence", "readme"),
    "registry": ("local_tags",),
    "targets": ("law", "arch"),
    "targets.law": ("archive",),
    "targets.arch": ("sources", "forms", "accepted"),
    "keep": ("failures",),
    "scan": ("ignore",),
    "layout": ("docs_dir", "front_matter", "types", "index"),
}
"""The full schema of D2.5. `[scan] ignore` is its one key that removes a
path (I-2). `apply` renders it from the `ignore` globs of `trueup.toml`. A
kept failure id names one failure line, and the file is still scanned (D9.2).
`[layout]` names the documentation directory and turns the rules of checks h
and i on or off one at a time (D14.5)."""

_DOCS_DIR = re.compile(r"[A-Za-z0-9_.-]+")
"""The form of `[layout] docs_dir`: one path segment (D14.2)."""

CONFIG_NAME = "ref_check.toml"
"""The name of the configuration file. It lives at the root."""


def _config_table(data: dict, name: str) -> dict:
    """Give one table of the configuration, and check that it is a table.

    Args:
        data: The table that holds the value.
        name: The name of the wanted table, in the words of the schema.

    Returns:
        The table, or an empty table when the key is absent.

    Raises:
        ConfigError: The value is not a table.
    """
    value = data.get(name.rsplit(".", 1)[-1], {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] is not a table")
    return value


def _check_config_keys(table: dict, name: str) -> None:
    """Reject each key of one table that the schema of D2.5 does not name.

    A key other than `[scan] ignore` that tries to skip a path is one of
    these, because the schema holds no other such key (I-2).

    Args:
        table: The table to examine.
        name: The name of the table, in the words of the schema.

    Raises:
        ConfigError: The table holds a key that the schema does not name.
    """
    place = f"[{name}]" if name else "the top level"
    for key in table:
        if key not in CONFIG_SCHEMA[name]:
            raise ConfigError(f"unknown key in {place}: {key}")


def load_config(root: Path, path: Path | None = None) -> Config:
    """Read the configuration file of one root, and check it against D2.5.

    The file is optional. An absent file gives every switch off and no law
    archive. Text that is not TOML, a table or a key outside the schema, or a
    value of the wrong type, each stop the run with exit 2 (I-4).

    Args:
        root: The repository to examine. A relative law archive resolves
            against it, whichever file holds the configuration.
        path: The configuration file to read in place of
            `root/ref_check.toml` (the `--config` flag, D8.1). A named file
            that is absent is an error: the caller asked for it.

    Returns:
        The configuration of the root.

    Raises:
        ConfigError: The file exists and is not valid, or `path` names a
            file that does not exist.
    """
    if path is None:
        path = root / CONFIG_NAME
        if not os.path.isfile(path):
            return Config()
    elif not os.path.isfile(path):
        raise ConfigError(f"configuration file is absent: {path}")
    try:
        data = tomllib.loads(_read_utf8(path, _CONFIG_READ_CAP))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        shown = CONFIG_NAME if path == root / CONFIG_NAME else str(path)
        raise ConfigError(f"{shown} does not parse: {error}") from error
    _check_config_keys(data, "")
    checks = _config_table(data, "checks")
    _check_config_keys(checks, "checks")
    switches: dict[str, bool] = {}
    for key in CONFIG_SCHEMA["checks"]:
        value = checks.get(key, key == "licence")
        if not isinstance(value, bool):
            raise ConfigError(f"[checks] {key} is not true or false")
        switches[key] = value
    targets = _config_table(data, "targets")
    _check_config_keys(targets, "targets")
    law = _config_table(targets, "targets.law")
    _check_config_keys(law, "targets.law")
    archive = law.get("archive")
    if archive is not None and not isinstance(archive, str):
        raise ConfigError("[targets.law] archive is not a path")
    arch = _config_table(targets, "targets.arch")
    _check_config_keys(arch, "targets.arch")
    sources = arch.get("sources", [])
    if not isinstance(sources, list) or not all(
        isinstance(item, str) and item and not os.path.isabs(item) for item in sources
    ):
        raise ConfigError("[targets.arch] sources is not a list of relative paths")
    forms = arch.get("forms", [])
    if (
        not isinstance(forms, list)
        or len(forms) > _ID_FORMS_MAX
        or not all(isinstance(item, str) and _id_form_is_valid(item) for item in forms)
    ):
        raise ConfigError("[targets.arch] forms is not a list of id forms")
    accepted = arch.get("accepted", [])
    if not isinstance(accepted, list) or not all(
        isinstance(item, str) and _CHANGE_NAME.fullmatch(item) for item in accepted
    ):
        raise ConfigError("[targets.arch] accepted is not a list of change names")
    registry = _config_table(data, "registry")
    _check_config_keys(registry, "registry")
    local_tags = registry.get("local_tags", [])
    if not isinstance(local_tags, list) or not all(
        isinstance(tag, str) and _LOCAL_TAG.fullmatch(tag) for tag in local_tags
    ):
        raise ConfigError("[registry] local_tags is not a list of uppercase prefixes")
    keep = _config_table(data, "keep")
    _check_config_keys(keep, "keep")
    kept = keep.get("failures", [])
    if not isinstance(kept, list) or not all(isinstance(item, str) for item in kept):
        raise ConfigError("[keep] failures is not a list of failure ids")
    scan = _config_table(data, "scan")
    _check_config_keys(scan, "scan")
    ignore = scan.get("ignore", [])
    if not isinstance(ignore, list) or not all(
        isinstance(item, str) and item for item in ignore
    ):
        raise ConfigError("[scan] ignore is not a list of globs")
    layout = _config_table(data, "layout")
    _check_config_keys(layout, "layout")
    docs_dir = layout.get("docs_dir", "docs")
    if (
        not isinstance(docs_dir, str)
        or _DOCS_DIR.fullmatch(docs_dir) is None
        or docs_dir in (".", "..")
    ):
        raise ConfigError("[layout] docs_dir is not one directory name")
    rules: dict[str, bool] = {}
    for key in ("front_matter", "types", "index"):
        value = layout.get(key, True)
        if not isinstance(value, bool):
            raise ConfigError(f"[layout] {key} is not true or false")
        rules[key] = value
    return Config(
        registry=switches["registry"],
        comments=switches["comments"],
        links=switches["links"],
        layout=switches["layout"],
        readme=switches["readme"],
        licence=switches["licence"],
        archive=None if archive is None else Path(root, archive).resolve(),
        local_tags=frozenset(local_tags),
        keep=frozenset(kept),
        ignore=tuple(ignore),
        docs_dir=docs_dir,
        front_matter=rules["front_matter"],
        types=rules["types"],
        index=rules["index"],
        declared=tuple(sources),
        id_forms=tuple(forms),
        accepted=frozenset(accepted),
    )


def run(root: Path, config_path: Path | None = None) -> Report:
    """Examine one repository and give its report.

    This is the one function that does the work. It walks the root, reads the
    markers, and runs the nine checks, a to i. It writes no file and it prints
    nothing. The entry points print the report and set the exit code.

    Args:
        root: The repository to examine.
        config_path: The configuration file to read in place of
            `root/ref_check.toml` (D8.1). `None` reads the root's own file.

    Returns:
        A report with the sorted failures and the sorted edges. An identical
        failure appears one time (D2.4). A failure whose id `keep_match`
        matches to a `[keep] failures` entry is in `kept`, not in
        `failures` (D9.2, D15.8).

    Raises:
        ConfigError: The configuration file of the root is not valid (D2.5).
    """
    global _run_root
    root = root.resolve()
    _run_root = root
    for cache in (
        _read_text,
        _design_ids,
        _file_section_hash,
        _newest_version,
        _parsed_python,
        _comment_tokens,
        _source_lines,
    ):
        cache.cache_clear()
    config = load_config(root, config_path)
    declared = _read_declared_sources(root, config)
    arch_id = declared.grammar.whole if declared else _ARCH_ID
    any_id = declared.grammar.anywhere if declared else _ANY_ID
    failures: list[Failure] = []
    edges: list[Edge] = []
    test_files: set[str] = set()
    changed: dict[tuple[str, int], str] = {}
    files = _iter_source_files(root, failures, config.ignore)
    for path, language in files:
        relative = path.relative_to(root)
        rel_path = relative.as_posix()
        try:
            positions = READERS[language](path)
        except SyntaxError as error:
            detail = "file cannot be read: SyntaxError"
            failures.append(Failure(rel_path, error.lineno or 1, "unreadable", detail))
            continue
        except (
            OSError,
            UnicodeDecodeError,
            ValueError,
            RecursionError,
            MemoryError,
        ) as error:
            detail = f"file cannot be read: {type(error).__name__}"
            failures.append(Failure(rel_path, 1, "unreadable", detail))
            continue
        if _is_test_file(relative, language):
            test_files.add(rel_path)
        legacy = language == "python" and relative.name.startswith("test_")
        marked_units: set[str] = set()
        for position in positions:
            for name in sorted(READER_CHANGES):
                if name not in config.accepted and READER_CHANGES[name](
                    language, position
                ):
                    changed.setdefault((rel_path, position.line), name)
                    break
            candidate = marker_candidate(
                position.text, position.docstring, config.local_tags, arch_id
            )
            if config.registry and candidate is not None and candidate not in REGISTRY:
                tail = f"marker not in the registry: {candidate}"
                detail = _detail("unregistered", position.unit, tail)
                failures.append(
                    Failure(rel_path, position.line, "unregistered", detail)
                )
            marker = _marker_at(position, legacy, arch_id, any_id)
            if marker is None:
                if candidate is not None and candidate not in REGISTRY:
                    shape = _reference_shape_marker(
                        _strip_leader(position.text), arch_id
                    )
                    if shape is not None:
                        _, pairs = shape
                        for target, ident in pairs:
                            edges.append(
                                Edge(
                                    rel_path,
                                    position.line,
                                    position.unit,
                                    candidate,
                                    target,
                                    ident,
                                    "ok",
                                )
                            )
                continue
            if position.docstring:
                marked_units.add(position.unit)
            if marker.malformed:
                tail = f"marker does not parse: {marker.text}"
                detail = _detail("malformed", position.unit, tail)
                failures.append(Failure(rel_path, position.line, "malformed", detail))
                continue
            for target, ident in marker.refs:
                edges.append(
                    Edge(
                        rel_path,
                        position.line,
                        position.unit,
                        marker.keyword,
                        target,
                        ident,
                        "ok",
                    )
                )
        if legacy:
            failures.extend(_check_b(rel_path, path, marked_units))
    edges = _check_a(root, edges, failures, config.archive, config.docs_dir, declared)
    unproved, excused = _check_c(root, edges, test_files, config.docs_dir, declared)
    failures.extend(unproved)
    law_failures = _check_d(config.archive, edges)
    failures.extend(law_failures)
    if config.comments:
        failures.extend(_check_f(root, files))
    failures.extend(_check_g(root, config))
    failures.extend(_check_h(root, config))
    failures.extend(_check_i(root, config))
    order = sorted(
        edges, key=lambda edge: (edge.source, edge.line, edge.target, edge.id)
    )
    distinct = sorted(set(failures))
    # A failure at a marker that a registered change reads is a warning (D16.3).
    marker_reads = {
        (edge.source, edge.line) for edge in edges if edge.status == "unreadable"
    } | {(item.path, item.line) for item in law_failures if item.kind == "unreadable"}
    warned = [
        (changed[(item.path, item.line)], item)
        for item in distinct
        if (item.path, item.line) in changed
        and (
            item.kind in _CHANGE_KINDS
            or (item.kind == "unreadable" and (item.path, item.line) in marker_reads)
        )
    ]
    warned_items = {item for _, item in warned}
    distinct = [item for item in distinct if item not in warned_items]
    ids = failure_ids(distinct)
    # D15.8: a keep entry also keeps each id below it, at a `:` boundary.
    held = [keep_match(key, config.keep) is not None for key in ids]
    reported = [
        item for item, is_kept in zip(distinct, held, strict=True) if not is_kept
    ]
    kept = [item for item, is_kept in zip(distinct, held, strict=True) if is_kept]
    return Report(reported, order, excused, config, kept, sorted(warned))


def _check_a(
    root: Path,
    edges: list[Edge],
    failures: list[Failure],
    archive: Path | None,
    docs_dir: str = "docs",
    declared: DeclaredSources | None = None,
) -> list[Edge]:
    """Resolve each reference against its target, and give the edges a status.

    The archive comes from `ref_check.toml` (D2.5). With no archive, each
    `law` reference fails with `no-target`, as D1.3 states.

    Args:
        root: The repository to examine.
        edges: The references that the markers gave.
        failures: The failure list, which this function extends.
        archive: The law archive, or `None` when the configuration names none.
        docs_dir: The directory below the root that holds the design (D14.5).
        declared: The sources of the configured reader, or `None` for the one
            page of today (D16.2). A missing source gives one row per entry
            and no `unknown-id` row, because the reader cannot decide (I-56).

    Returns:
        The edges, each with the status of its resolution.
    """
    resolved: list[Edge] = []
    unchecked = 0
    if declared is not None:
        failures.extend(declared.unreadable)
    for edge in edges:
        if edge.target == "law" and archive is None:
            tail = f"target law is not configured: {edge.id}"
            outcome: Resolution = ("no-target", tail)
        elif edge.target == "arch" and declared is not None:
            outcome = _resolve_declared(declared, edge.id)
        elif edge.target == "arch":
            outcome = resolve_arch(root, archive, edge.id, docs_dir)
        else:
            outcome = TARGETS[edge.target](root, archive, edge.id)
        if outcome is None:
            resolved.append(edge)
            continue
        kind, tail = outcome
        if declared is not None and edge.target == "arch" and kind == "no-target":
            unchecked += 1
        elif kind != "unreadable" or edge.target != "arch":
            detail = tail if kind == "unreadable" else _detail(kind, edge.unit, tail)
            failures.append(Failure(edge.source, edge.line, kind, detail))
        resolved.append(
            Edge(
                edge.source,
                edge.line,
                edge.unit,
                edge.marker,
                edge.target,
                edge.id,
                kind,
            )
        )
    if declared is not None:
        failures.extend(
            Failure(
                entry,
                1,
                "no-target",
                f"declared source not found: {entry}; {unchecked} citations not checked",
            )
            for entry in declared.missing
        )
    return resolved


def _check_b(rel_path: str, path: Path, marked_units: set[str]) -> list[Failure]:
    """Find each test function of a marked Python test file that has no marker.

    The rule is that of D2.8. A marker in the module docstring claims for
    every test of the file. Otherwise, once one test holds a marker, each
    test must hold one.

    Args:
        rel_path: The file, relative to the root.
        path: The file itself.
        marked_units: The units of the file whose docstring holds a marker.

    Returns:
        One `unmarked` failure for each test function that owes a marker.
    """
    if "module" in marked_units or not marked_units:
        return []
    functions = _python_test_functions(path)
    if not any(name in marked_units for _, name in functions):
        return []
    return [
        Failure(rel_path, line, "unmarked", name)
        for line, name in functions
        if name not in marked_units
    ]


def _check_c(
    root: Path,
    edges: list[Edge],
    test_files: set[str],
    docs_dir: str = "docs",
    declared: DeclaredSources | None = None,
) -> tuple[list[Failure], list[str]]:
    """Find each claim of `## Verification` that no test proves.

    Args:
        root: The repository to examine.
        edges: The references, after check a.
        test_files: The source files that the rule of D1.2 calls test files.
        docs_dir: The directory below the root that holds the design (D14.5).
        declared: The sources of the configured reader, or `None` for the one
            page of today (D16.2). The reader reads each section of its
            sources, and each failure names the source as written (I-57).

    Returns:
        A pair. First, one `unproved` failure for each owed id, one line for
        each id, or one `unreadable` failure alone when the design exists and
        cannot be read. Second, the excused ids of D2.8, sorted as text: the
        ids in `claims - cited` that an open plan row names.
    """
    if declared is None:
        shown = f"{docs_dir}/ARCHITECTURE.md"
        design = root / shown
        if os.path.exists(design):
            try:
                _read_text(design)
            except (OSError, UnicodeDecodeError) as error:
                detail = f"file cannot be read: {type(error).__name__}"
                return [Failure(shown, 1, "unreadable", detail)], []
        any_id = _ANY_ID
        pages = [(shown, _verification_claims(design))]
    else:
        any_id = declared.grammar.anywhere
        pages = [
            (shown, _claims_in_text(text, any_id)) for shown, text in declared.texts
        ]
    if not any(claims for _, claims in pages):
        return [], []
    cited = {
        edge.id for edge in edges if edge.target == "arch" and edge.source in test_files
    }
    open_ids = _open_plan_ids(root / "PLAN.md", any_id)
    failures: list[Failure] = []
    excused: set[str] = set()
    for shown, claims in pages:
        unproved = set(dict(claims)) - cited
        owed = unproved - open_ids
        failures.extend(
            Failure(
                shown,
                line,
                "unproved",
                f"claimed in ## Verification, proved by no test: {ident}",
            )
            for ident, line in claims
            if ident in owed
        )
        excused |= unproved & open_ids
    return failures, sorted(excused)


_SUPPRESSION_LEADERS: dict[str, str] = {"python": "#", "shell": "#", "sql": "--"}
"""The comment leader of each language that check f examines (D2.9)."""

_SUPPRESSION_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"noqa\b(?::\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?"),
    "shell": re.compile(r"shellcheck\s+disable=\S+"),
    "sql": re.compile(r"noqa\b(?::\s*[A-Za-z0-9_.,\s]+?)?"),
}
"""The suppression regex of D2.9, one for each language that owns no linter rule."""

_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/")
"""A `/* ... */` block comment on one line of SQL (D2.9, R-1)."""

_SQL_REASON = re.compile(r"/\*(.*?)\*/\s*$")
"""The block comment just before the `--` of a SQL suppression. Group 1 is the reason (D2.9)."""

_HEADER_LANGUAGES = {"shell", "sql"}
"""The languages whose files owe a header comment under D2.9. Python has a linter rule."""


def _has_file_header(lines: list[str], leader: str) -> bool:
    """Say whether a file's first line of content is a whole-line comment.

    An optional `#!` line is skipped first. A file with no content line at
    all owes nothing (D2.9).

    Args:
        lines: The file, split into lines, with no line terminator.
        leader: The comment leader of the language.

    Returns:
        True when the first non-empty line, after an optional `#!` line, is
        a whole-line comment.
    """
    start = 1 if lines and lines[0].startswith("#!") else 0
    for line in lines[start:]:
        if line.strip() == "":
            continue
        return line.lstrip().startswith(leader)
    return True


def _suppression_unit(
    language: str, units: list[tuple[int, int, str]], line: int
) -> str:
    """Find the unit of D1.2 that holds a suppression line.

    Args:
        language: The language of the file.
        units: The Python unit spans of the file, or an empty list.
        line: The line of the suppression.

    Returns:
        The innermost Python function or class that holds the line, or
        `module`. Shell and SQL give `-`.
    """
    if language != "python":
        return "-"
    return unit_at(units, line)


def _python_comments(path: Path) -> dict[int, str]:
    """Give the comment token of each line of one Python file.

    Args:
        path: The `.py` file; the tokens come from the per-run cache (D15.23).

    Returns:
        The text of each comment token after its `#`, by line. A file that
        does not tokenize gives no entry; `run` reports it as `unreadable`.
    """
    comments: dict[int, str] = {}
    try:
        for line, text in _comment_tokens(path):
            comments[line] = text[1:]
    except (tokenize.TokenError, SyntaxError, OSError, UnicodeDecodeError):
        return {}
    return comments


def _check_f(root: Path, files: list[tuple[Path, str]]) -> list[Failure]:
    """Check the suppression reason and the file header of D2.9.

    A Python or shell suppression with no second leader, or with no text
    after it, fails with `no-reason`. A SQL suppression fails with
    `no-reason` when no `/* ... */` block comment with text comes just before
    its `--` on the same line. A shell or SQL file whose first content line is
    not a whole-line comment fails with `no-header`.

    Args:
        root: The repository to examine.
        files: The (path, language) pairs that the walk of `run` selected.

    Returns:
        One failure for each suppression with no reason and each missing
        header. A file that cannot be read gives no failure here; `run`
        already reports it as `unreadable`.
    """
    failures: list[Failure] = []
    for path, language in files:
        if language not in _SUPPRESSION_LEADERS:
            continue
        try:
            text = _read_text(path)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        relative = path.relative_to(root).as_posix()
        leader = _SUPPRESSION_LEADERS[language]
        pattern = _SUPPRESSION_PATTERNS[language]
        lines = text.splitlines()
        # D15.18: a heredoc line of a shell file is no suppression position.
        heredoc = _heredoc_lines(lines) if language == "shell" else set()
        units: list[tuple[int, int, str]] = []
        python_comments: dict[int, str] = {}
        if language == "python":
            try:
                units = _parsed_python(path)[2]
            except (SyntaxError, ValueError):
                units = []  # `run` reports the parse error; the unit is `module`.
            python_comments = _python_comments(path)
        for number, line in enumerate(lines, start=1):
            if number - 1 in heredoc:
                continue
            start = -1
            if language == "python":
                # A `#` in a string literal is not a leader, so take the comment token.
                comment = python_comments.get(number)
            else:
                if language == "sql":
                    # Mask block comments, so that a `--` in the reason is not the leader.
                    masked = _SQL_BLOCK_COMMENT.sub(
                        lambda m: " " * len(m.group()), line
                    )
                    start = masked.find(leader)
                else:
                    start = line.find(leader)
                comment = line[start + len(leader) :] if start != -1 else None
            if comment is None:
                continue
            if not pattern.match(comment.strip()):
                continue
            if language == "sql":
                block = _SQL_REASON.search(line[:start])
                reason = block.group(1).strip() if block else ""
            else:
                second = comment.find(leader)
                reason = comment[second + len(leader) :].strip() if second != -1 else ""
            if not reason:
                unit = _suppression_unit(language, units, number)
                detail = _detail(
                    "no-reason", unit, "suppression has no reason: " + comment.strip()
                )
                failures.append(Failure(relative, number, "no-reason", detail))
        if language in _HEADER_LANGUAGES and not _has_file_header(lines, leader):
            failures.append(
                Failure(relative, 1, "no-header", "file has no header comment")
            )
    return failures


_FENCE_LINE = re.compile(r"^\s*(?:```|~~~)")
"""The line that opens or closes a fenced code block (D2.10, D15.18)."""

_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
"""The opening line of a fenced code block. Group 1 is the fence (D15.18)."""

_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
"""A line that can close a fenced code block. Group 1 is the fence (D15.18)."""

_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:\s|$)")
"""The first line of a Markdown list item (D15.18)."""

_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
"""An inline code span: a run of backticks, the text, and the same run.
Its content is not a link (D2.10, D15.18)."""

_MD_LINK = re.compile(
    r"(?<!\\)\[[^\]]*\]\((\s*(?:[^()\s]|\([^()\s]*\))+(?:\s+[^)]*)?)\)"
)
"""An inline Markdown link. Group 1 is the target. The target can hold one
level of balanced parentheses, and a `[` after a backslash opens no link
(D2.10, D15.18)."""

_MD_REFERENCE = re.compile(r"^\s*\[(?!\^)[^\]]+\]:\s*((?:<[^>]*>|\S+).*)")
"""A Markdown reference definition. Group 1 is the target, with its title.
A label that starts with `^` is a footnote, not a link (D2.10, D15.18)."""

_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)\s*$")
"""The line under a setext heading: `===` for level 1, `---` for level 2 (D15.18)."""

_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
"""A Markdown ATX heading. Group 1 is the heading text (D2.10)."""

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:")
"""A URL scheme prefix. A target that starts with one is not examined (D2.10)."""

_SLUG_STRIP = re.compile(r"[^\w -]")
"""Each character a heading slug drops, after the text is made lower case.

`\\w` holds the letters and digits of each script, and `_`.
"""

_INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
"""An inline link or image in a heading. Group 1 is the text that the slug keeps."""

_HTML_TAG = re.compile(r"<[^>]+>")
"""An inline HTML tag in a heading. The slug keeps no text of the tag."""

_ATTR_LIST = re.compile(r"\s*\{:?([^{}]*)\}$")
"""An attribute list at the end of a heading. Group 1 holds its tokens (D14.12)."""

_HTML_START_TAG = re.compile(r"<[A-Za-z][^<>]*>")
"""An HTML start tag. Its `id` and `name` attributes give anchors (D14.12)."""

_HTML_ANCHOR_ATTR = re.compile(
    r"""(?<![\w-])(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE
)
"""An `id` or `name` attribute, double or single quoted (D14.12)."""

_TOC_STRIP = re.compile(r"[^\w\s-]")
"""Each character the python-markdown `toc` slug drops (D14.12)."""

_TOC_SEPARATOR = re.compile(r"[-\s]+")
"""A run of `-` and white space. The `toc` slug folds each run into one `-`."""

_TOC_REPEAT = re.compile(r"^(.*)_([0-9]+)$")
"""A `toc` slug that ends in `_<n>`. A repeat increments the number."""


def _link_destination(target: str) -> str:
    """Give the destination of one link target, with no title (D2.10).

    Args:
        target: The text between the parentheses of a link, or after the
            colon of a reference definition.

    Returns:
        The text inside `<...>`, or else the text before the first white
        space. A title such as `"The title"` is not part of the destination.
    """
    target = target.strip()
    if target.startswith("<"):
        end = target.find(">")
        return target[1:end] if end != -1 else target
    return target.split(maxsplit=1)[0] if target else target


_PIN_VALUE = re.compile(r"[0-9a-f]{8}")
"""The shape of a pin: eight lower-case hex digits (D2.10)."""

_PIN_TITLE = re.compile(r"""(["'])pin:.*?\1""")
"""A pin title in quotes. One that no link on its line owns is a failure (D2.10)."""


def _link_pin(target: str) -> str | None:
    """Give the pin in the title of one link target, or `None` (D2.10).

    Args:
        target: The text between the parentheses of a link, or after the
            colon of a reference definition.

    Returns:
        The text after `pin:` when the title in quotes starts with `pin:`.
        `None` when the link has no title or the title is not a pin.
    """
    target = target.strip()
    if target.startswith("<"):
        end = target.find(">")
        rest = target[end + 1 :] if end != -1 else ""
    else:
        parts = target.split(maxsplit=1)
        rest = parts[1] if len(parts) > 1 else ""
    rest = rest.strip()
    if len(rest) < 2 or rest[0] not in "\"'" or rest[-1] != rest[0]:
        return None
    title = rest[1:-1]
    return title.removeprefix("pin:") if title.startswith("pin:") else None


def _indent(line: str) -> int:
    """Give the indent of one line, with a tab as 4 columns.

    Args:
        line: One physical line.

    Returns:
        The count of columns before the first character that is not white
        space.
    """
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _md_lines_outside_fences(text: str) -> list[str]:
    """Give the lines of a Markdown file, with each code block blanked out.

    A fence of 3 or more backticks or tildes opens a fenced block. Only a
    fence of the same character, at least as long, with no text after it,
    closes the block. A line with an indent of 4 columns or more after a
    blank line, outside a list, opens an indented code block. The block
    continues while each line is blank or has that indent (D2.10, D15.18).

    Args:
        text: The file content.

    Returns:
        One entry for each physical line. A line inside a code block, and
        each fence line, becomes the empty string, so neither a link nor a
        heading inside a code block is examined.
    """
    outside: list[str] = []
    fence = ""
    indented = False
    in_list = False
    after_blank = True
    for line in text.splitlines():
        if fence:
            closing = _FENCE_CLOSE.match(line)
            if (
                closing is not None
                and closing.group(1)[0] == fence[0]
                and len(closing.group(1)) >= len(fence)
            ):
                fence = ""
            outside.append("")
            continue
        blank = not line.strip()
        if indented:
            if blank or _indent(line) >= 4:
                outside.append("")
                continue
            indented = False
        opening = _FENCE_OPEN.match(line)
        if opening is not None:
            fence = opening.group(1)
            outside.append("")
            after_blank = False
            continue
        if not blank and _indent(line) >= 4 and after_blank and not in_list:
            indented = True
            outside.append("")
            continue
        if not blank:
            if _LIST_ITEM.match(line):
                in_list = True
            elif _MD_HEADING.match(line) or (after_blank and _indent(line) == 0):
                in_list = False
        after_blank = blank
        outside.append(line)
    return outside


def _slugify_heading(text: str, seen: dict[str, int]) -> str:
    """Give the GitHub slug of one heading, and record it against repeats.

    Args:
        text: The heading text, with no leading `#` markers.
        seen: A count of each slug already given, updated in place.

    Returns:
        The slug: each inline link or image replaced by its text, each HTML
        tag removed, lower case, with each character that is not a letter, a
        digit, a space, `-` or `_` removed, each space turned into `-`, and
        `-1`, `-2` appended for a slug that repeats (D2.10).
    """
    text = _HTML_TAG.sub("", _INLINE_LINK.sub(r"\1", text))
    base = _SLUG_STRIP.sub("", text.lower()).replace(" ", "-")
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def _toc_slug(text: str, used: set[str]) -> str:
    """Give the python-markdown `toc` slug of one heading, and record it.

    Args:
        text: The heading text, with no leading `#` markers.
        used: Each `toc` slug already given, updated in place.

    Returns:
        The slug: each inline link or image replaced by its text, each HTML
        tag removed, each letter decomposed and each non-ASCII character
        removed, each character that is not a letter, a digit, white space,
        `-` or `_` removed, lower case, and each run of `-` and white space
        turned into one `-`. A slug that repeats gets `_1`, `_2` as the
        `toc` extension gives it (D14.12).
    """
    text = _HTML_TAG.sub("", _INLINE_LINK.sub(r"\1", text))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _TOC_SEPARATOR.sub("-", _TOC_STRIP.sub("", text).strip().lower())
    while slug in used or not slug:
        repeat = _TOC_REPEAT.match(slug)
        if repeat is not None:
            slug = f"{repeat.group(1)}_{int(repeat.group(2)) + 1}"
        else:
            slug = f"{slug}_1"
    used.add(slug)
    return slug


def _split_attr_list(text: str) -> tuple[str, str | None]:
    """Split an attribute-list id from the end of one heading text.

    Args:
        text: The heading text, with no leading `#` markers.

    Returns:
        The text without the attribute list and the id, such as `x` for
        `{#x}` or `{: #x .note}`. The text as given and `None` when the
        heading ends in no attribute list with an id (D14.12).
    """
    found = _ATTR_LIST.search(text)
    if found is None:
        return text, None
    for token in found.group(1).split():
        if token.startswith("#") and len(token) > 1:
            return text[: found.start()].rstrip(), token[1:]
    return text, None


def _html_anchors(text: str) -> set[str]:
    """Give the value of each `id` or `name` attribute of each HTML tag.

    Args:
        text: The file content, with each fenced block blanked out.

    Returns:
        Each non-empty value. A tag can span lines (D14.12).
    """
    anchors: set[str] = set()
    for tag in _HTML_START_TAG.finditer(text):
        for attr in _HTML_ANCHOR_ATTR.finditer(tag.group(0)):
            value = attr.group(1) if attr.group(1) is not None else attr.group(2)
            if value:
                anchors.add(value)
    return anchors


def _heading_slugs(text: str) -> set[str]:
    """Give the set of every anchor of one Markdown file.

    A fragment that resolves on one renderer resolves here. The set only
    grows from D2.10, so each fragment that resolved before still resolves
    (D14.12).

    Args:
        text: The file content.

    Returns:
        For each ATX or setext heading outside a code block: the GitHub slug
        of its text (D2.10), the id of an attribute list `{#x}` at its end,
        the GitHub slug of its text without that list, and the
        python-markdown `toc` slug of its text without that list. Each
        slug is given for the text as written and for the text with its
        HTML entities decoded (D15.18). Also the value of each `id` or
        `name` attribute of an HTML tag outside a code block.
    """
    seen: dict[str, int] = {}
    seen_plain: dict[str, int] = {}
    seen_decoded: dict[str, int] = {}
    seen_decoded_plain: dict[str, int] = {}
    used_toc: set[str] = set()
    used_decoded_toc: set[str] = set()
    slugs: set[str] = set()
    lines = _md_lines_outside_fences(text)
    for heading in _heading_texts(lines):
        slugs.add(_slugify_heading(heading, seen))
        plain, attr_id = _split_attr_list(heading)
        if attr_id is not None:
            slugs.add(attr_id)
        slugs.add(_slugify_heading(plain, seen_plain))
        slugs.add(_toc_slug(plain, used_toc))
        decoded = html.unescape(heading)
        slugs.add(_slugify_heading(decoded, seen_decoded))
        slugs.add(_slugify_heading(html.unescape(plain), seen_decoded_plain))
        slugs.add(_toc_slug(html.unescape(plain), used_decoded_toc))
    slugs |= _html_anchors("\n".join(lines))
    return slugs


def _heading_texts(lines: list[str]) -> Iterator[str]:
    """Give the text of each ATX and setext heading, in the order they appear.

    A setext heading is a text line followed by a line of `=` or `-`. The
    text line is not blank, not a list item, not a table row, not an ATX
    heading, and it has an indent of 3 columns or less (D15.18).

    Args:
        lines: The lines of one file, with each code block blanked out.

    Yields:
        The heading text, with no `#` markers.
    """
    for number, line in enumerate(lines):
        found = _MD_HEADING.match(line)
        if found is not None:
            yield found.group(1)
            continue
        if (
            number + 1 < len(lines)
            and line.strip()
            and _SETEXT_UNDERLINE.match(lines[number + 1])
            and _indent(line) < 4
            and _LIST_ITEM.match(line) is None
            and not line.lstrip().startswith("|")
            and _SETEXT_UNDERLINE.match(line) is None
        ):
            yield line.strip()


def _heading_level(line: str) -> int:
    """Give the level of one ATX heading line, the count of its `#` markers.

    Args:
        line: A line that `_MD_HEADING` matches.

    Returns:
        The level, 1 to 6.
    """
    marks = line.lstrip()
    return len(marks) - len(marks.lstrip("#"))


def section_pin(text: str, fragment: str) -> str | None:
    """Give the pin of the section whose heading slug is the fragment (D2.10).

    The section starts at the heading line. It ends before the next heading
    line of the same or a higher level, or at the end of the text. A heading
    in a fenced code block does not end it. The pin is the first eight hex
    digits of the hash of D2.7 step 4. A person uses this function to write
    a new pin; the checker never writes one (I-8).

    Args:
        text: The content of one Markdown file.
        fragment: The heading slug, with no `#`.

    Returns:
        The pin, or `None` when no heading has that slug.
    """
    lines = text.splitlines()
    seen: dict[str, int] = {}
    start: int | None = None
    level = 0
    end = len(lines)
    for number, line in enumerate(_md_lines_outside_fences(text)):
        found = _MD_HEADING.match(line)
        if found is None:
            continue
        if start is None:
            if _slugify_heading(found.group(1), seen) == fragment:
                start, level = number, _heading_level(line)
        elif _heading_level(line) <= level:
            end = number
            break
    if start is None:
        return None
    return _normalised_hash("\n".join(lines[start:end]))[:8]


def _md_link_targets(text: str) -> list[tuple[int, str]]:
    """Give the line and target of each link and reference definition of one file.

    Fenced code blocks are excluded first. An inline code span on a
    remaining line is then blanked out, so a link written inside one is not
    found (D2.10).

    Args:
        text: The file content.

    Returns:
        One `(line, target)` pair for each link, in the order they appear.
        The line starts at 1. A reference definition takes the line of the
        definition (D2.4).
    """
    targets: list[tuple[int, str]] = []
    for number, line in enumerate(_md_lines_outside_fences(text), start=1):
        clean = _CODE_SPAN.sub("", line)
        targets.extend((number, target) for target in _MD_LINK.findall(clean))
        found = _MD_REFERENCE.match(clean)
        if found is not None:
            targets.append((number, found.group(1)))
    return targets


def _md_links(text: str) -> Iterator[tuple[int, str, str, str, str]]:
    """Give the parts of each link of one file that has no URL scheme (D2.10).

    A target with a URL scheme is not given. The path part ends at the
    first `?` or `#`, so a query string is not part of the path. The path
    part and the fragment are decoded from percent escapes. The helper
    does not resolve a path.

    Args:
        text: The file content.

    Yields:
        One `(line, written, target, path part, fragment)` tuple for each
        link, in the order they appear. `written` is the text as the file
        writes it, and `target` is its destination with no title.
    """
    for number, written in _md_link_targets(text):
        target = _link_destination(written)
        if _SCHEME.match(target):
            continue
        before_fragment, _, fragment = target.partition("#")
        path_part = unquote(before_fragment.partition("?")[0])
        yield number, written, target, path_part, unquote(fragment)


def _docs_pages(
    root: Path, ignore: Sequence[str] = (), docs_dir: str = "docs"
) -> list[Path]:
    """Give each `*.md` file under the docs directory of the root, sorted.

    A file below a directory whose name starts with a dot, or is in
    `SKIP_DIRS`, or that is a nested repository (D8.2), is not given. A
    file whose path matches an `ignore` glob is not given (I-2).

    Args:
        root: The repository to examine.
        ignore: The globs of `[scan] ignore`.
        docs_dir: The docs directory below the root (`[layout] docs_dir`,
            D14.5).

    Returns:
        The pages, or an empty list when the docs directory is not a
        directory.
    """
    directory = root / docs_dir
    if not os.path.isdir(directory):
        return []
    return [
        path
        for path in sorted(directory.rglob("*.md"))
        if is_doc_page(path.relative_to(root).as_posix(), docs_dir)
        and not _below_nested_repository(root, path)
        and not (ignore and matches_ignore(path.relative_to(root).as_posix(), ignore))
    ]


def _orphan_pin_titles(text: str) -> list[tuple[int, str]]:
    """Give the line and text of each pin title that no link on its line owns.

    A pinned link and its title stay on one line (D2.10). Check g reads one
    line at a time, so a title on the next line belongs to no link. The
    helper removes each link and each reference definition from the line,
    and reports each pin title that is left.

    Args:
        text: The file content.

    Returns:
        One `(line, title)` pair for each orphan pin title, in the order
        they appear. The line starts at 1. A title inside a fenced block or
        a code span is not examined.
    """
    orphans: list[tuple[int, str]] = []
    for number, line in enumerate(_md_lines_outside_fences(text), start=1):
        clean = _CODE_SPAN.sub("", line)
        rest = _MD_REFERENCE.sub("", _MD_LINK.sub("", clean))
        orphans.extend((number, found.group(0)) for found in _PIN_TITLE.finditer(rest))
    return orphans


_PLACEHOLDER_TARGET = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
"""A link target that starts with a `${NAME}` placeholder (D16.4)."""


def _check_g(root: Path, config: Config) -> list[Failure]:
    """Check the document link rules of D2.10.

    Each `*.md` file under the docs directory of the root (`docs_dir`,
    D14.5), and each `*.md` file at
    depth 0 of the root, is read for links, unless an `ignore` glob
    matches its path (I-2). A target with a URL scheme is
    not examined. A path target must resolve, inside the root, to a file or
    a directory. A fragment on a `.md` target must equal a heading slug of
    that target, or of the same file when the path part is empty. A link
    that resolves and has a pin in its title must match the hash of its
    section. A pinned link and its title stay on one line, so a pin title
    that no link on its line owns fails with `malformed`.

    Args:
        root: The repository to examine.
        config: The configuration. The check runs only when `links` is on.

    Returns:
        One `broken-link` failure for each target or fragment that does not
        resolve, one `stale-pin` failure for each pin that does not apply or
        does not match, on the line of the link, and one `malformed` failure
        for each orphan pin title, on the line of the title, with the
        details of D2.4.
    """
    if not config.links:
        return []
    pages = _docs_pages(root, config.ignore, config.docs_dir)
    pages += sorted(
        path
        for path in root.glob("*.md")
        if os.path.isfile(path)
        and not path.name.startswith(".")
        and not matches_ignore(path.name, config.ignore)
    )
    failures: list[Failure] = []
    slug_cache: dict[Path, set[str]] = {}

    def slugs_of(path: Path) -> set[str]:
        if path not in slug_cache:
            try:
                slug_cache[path] = _heading_slugs(_read_utf8(path))
            except (OSError, UnicodeDecodeError):
                slug_cache[path] = set()
        return slug_cache[path]

    for path in pages:
        relative = path.relative_to(root).as_posix()
        try:
            text = _read_utf8(path)
        except (OSError, UnicodeDecodeError) as error:
            detail = f"file cannot be read: {type(error).__name__}"
            failures.append(Failure(relative, 1, "unreadable", detail))
            continue
        for number, written, target, path_part, fragment in _md_links(text):
            if _PLACEHOLDER_TARGET.match(target):
                # D16.4: a template placeholder at the start is not a path.
                continue
            if path_part:
                # D15.18: a target that starts with `/` resolves from the root.
                base = root if path_part.startswith("/") else path.parent
                try:
                    resolved = (base / path_part.lstrip("/")).resolve()
                except (ValueError, RuntimeError, OSError):
                    resolved = None
            else:
                resolved = path
            if resolved is None:
                broken = True
            else:
                try:
                    resolved.relative_to(root)
                    broken = not os.path.exists(resolved)
                except (ValueError, RuntimeError, OSError):
                    broken = True
            if not broken and fragment:
                if (
                    resolved is not None
                    and os.path.isfile(resolved)
                    and resolved.suffix == ".md"
                ):
                    broken = fragment not in slugs_of(resolved)
            if broken:
                detail = "link does not resolve: " + target
                failures.append(Failure(relative, number, "broken-link", detail))
                continue
            pin = _link_pin(written)
            if pin is None:
                continue
            if resolved is None:
                continue
            if (
                not fragment
                or not os.path.isfile(resolved)
                or resolved.suffix != ".md"
                or _PIN_VALUE.fullmatch(pin) is None
            ):
                detail = "pin does not apply: " + target
                failures.append(Failure(relative, number, "stale-pin", detail))
            elif section_pin(_read_text(resolved), fragment) != pin:
                detail = "pinned section changed: " + target
                failures.append(Failure(relative, number, "stale-pin", detail))
        for number, title in _orphan_pin_titles(text):
            detail = "pin has no link on its line: " + title
            failures.append(Failure(relative, number, "malformed", detail))
    return failures


_FRONT_MATTER_LINE = re.compile(r"([A-Za-z0-9_-]+):(?:[ \t]+(.*))?")
"""One line of front matter, `<key>: <value>`. Group 2 is the value (D2.13)."""

_FRONT_MATTER_ITEM = re.compile(r"[ \t]*-[ \t]+(.*)")
"""One item line of a block list, `  - <item>`. Group 1 is the item (D15.18)."""

_PAGE_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
"""The shape of a page id (D2.13)."""

_PAGE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
"""The shape of the date in `last_reviewed` (D2.13)."""

_PAGE_TYPES = ("tutorial", "how-to", "reference", "explanation")
"""The values of the field `type`. Each one is also a directory below `docs/`."""

_PAGE_AUDIENCES = ("maintainer", "agent", "user")
"""The values that the list of the field `audience` can hold."""

_PAGE_STATUSES = ("draft", "current", "superseded")
"""The values of the field `status`."""

_PAGE_KEYS = ("id", "type", "audience", "status", "last_reviewed")
"""The fields that each page has, in the order that check h examines them."""


def _unquote(value: str) -> str:
    """Remove one pair of matching quotes around a front matter scalar (D15.18).

    Args:
        value: The value, with no white space at the ends.

    Returns:
        The text between the quotes, when the value starts and ends with
        the same `"` or `'`. Else the value as given.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _front_matter(
    text: str, *, skip_other: bool = False
) -> dict[str, tuple[int, str]] | None:
    """Read the front matter block of one page (D2.13 rule 1, D15.18, D15.30).

    This is the one front matter parser: `trueup.docrules` and
    `trueup.layout` call it too. A `key:` line with no value, followed by
    `  - <item>` lines, is a block list. Its value is `[<item>, <item>]`,
    the inline shape that check h reads. One pair of matching quotes
    around a scalar or an item is removed.

    Args:
        text: The file content.
        skip_other: True to skip a line that is not `<key>: <value>` and
            not a list item, such as the lines of a folded value. False to
            reject the block at such a line.

    Returns:
        Each key of the block, with its line and its value. The first line
        of a key that repeats is kept. `None` when line 1 is not `---`, when
        no later line `---` closes the block, or, with `skip_other` false,
        when a line between is not `<key>: <value>` or a list item.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    fields: dict[str, tuple[int, str]] = {}
    pending: tuple[str, int] | None = None
    items: list[str] = []

    def close_list() -> None:
        if pending is not None:
            value = f"[{', '.join(items)}]" if items else ""
            fields.setdefault(pending[0], (pending[1], value))

    for number, line in enumerate(lines[1:], start=2):
        stripped = line.rstrip()
        if stripped == "---":
            close_list()
            return fields
        if pending is not None:
            item = _FRONT_MATTER_ITEM.fullmatch(stripped)
            if item is not None:
                items.append(_unquote(item.group(1).strip()))
                continue
            close_list()
            pending, items = None, []
        found = _FRONT_MATTER_LINE.fullmatch(stripped)
        if found is None:
            if skip_other:
                continue
            return None
        value = (found.group(2) or "").strip()
        if value:
            fields.setdefault(found.group(1), (number, _unquote(value)))
        else:
            pending = (found.group(1), number)
    return None


def is_doc_page(rel: str, docs_dir: str) -> bool:
    """Say whether one path is a page of the docs directory (D15.30).

    The checker applies this rule to its walk of the disk, and
    `trueup.docrules` applies it to `survey.files`, so both read one page
    set.

    Args:
        rel: A path relative to the root, with `/` between the parts.
        docs_dir: The docs directory below the root (`[layout] docs_dir`).

    Returns:
        True for a `.md` path under `docs_dir` with no segment that starts
        with a dot and no segment in `SKIP_DIRS`.
    """
    return (
        rel.startswith(docs_dir.strip("/") + "/")
        and rel.endswith(".md")
        and not any(
            part.startswith(".") or part in SKIP_DIRS for part in rel.split("/")
        )
    )


def _field_allowed(key: str, value: str) -> bool:
    """Tell if one value of one field obeys the page rules (D2.13, rule 2).

    Args:
        key: One of `_PAGE_KEYS`.
        value: The value as written, with no white space at the ends.

    Returns:
        True when the value is allowed.
    """
    if key == "id":
        return _PAGE_ID.fullmatch(value) is not None
    if key == "type":
        return value in _PAGE_TYPES
    if key == "status":
        return value in _PAGE_STATUSES
    if key == "audience":
        if not (value.startswith("[") and value.endswith("]")):
            return False
        items = [item.strip() for item in value[1:-1].split(",")]
        return all(item in _PAGE_AUDIENCES for item in items)
    if _PAGE_DATE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_h(root: Path, config: Config) -> list[Failure]:
    """Check the page rules of the docs index, as D2.13 states them.

    Each `*.md` file under the docs directory of the root (`docs_dir`,
    D14.5) is a page. The index is `README.md` of that directory. The
    pipeline pages are `BRIEF.md` and `ARCHITECTURE.md` of that directory.
    Each rule runs only when its switch is on: `front_matter` for
    `no-front-matter`, `bad-field` and `duplicate-id`, `types` for
    `misplaced`, `index` for `unindexed`. When `front_matter` is on, a page
    with no valid front matter skips the rules 2 to 5. When it is off, such
    a page still gets the rule `unindexed`.

    Args:
        root: The repository to examine.
        config: The configuration. The check runs only when `layout` is on
            and one of the three rule switches is on.

    Returns:
        One failure of the kinds `no-front-matter`, `bad-field`, `misplaced`,
        `unindexed` or `duplicate-id` for each broken rule, with the detail
        and the line of D2.4.
    """
    if not config.layout or not (config.front_matter or config.types or config.index):
        return []
    docs_dir = root / config.docs_dir
    if not os.path.isdir(docs_dir):
        return []
    index = docs_dir / "README.md"
    exempt = {index, docs_dir / "BRIEF.md", docs_dir / "ARCHITECTURE.md"}
    failures: list[Failure] = []
    pages: list[tuple[Path, str]] = []
    for path in _docs_pages(root, config.ignore, config.docs_dir):
        relative = path.relative_to(root).as_posix()
        try:
            pages.append((path, _read_utf8(path)))
        except (OSError, UnicodeDecodeError) as error:
            detail = f"file cannot be read: {type(error).__name__}"
            failures.append(Failure(relative, 1, "unreadable", detail))
            continue
    indexed: set[Path] = set()
    for path, text in pages:
        if path != index:
            continue
        for _, _, _, path_part, _ in _md_links(text):
            if path_part:
                try:
                    indexed.add((index.parent / path_part).resolve())
                except (ValueError, RuntimeError, OSError):
                    pass
    owners: dict[str, str] = {}
    for path, text in pages:
        relative = path.relative_to(root).as_posix()
        fields = _front_matter(text)
        if fields is None:
            if config.front_matter:
                failures.append(
                    Failure(relative, 1, "no-front-matter", "file has no front matter")
                )
                continue
            fields = {}
        for key in _PAGE_KEYS if config.front_matter else ():
            if key not in fields:
                failures.append(
                    Failure(relative, 1, "bad-field", f"field is absent: {key}")
                )
                continue
            number, value = fields[key]
            if not _field_allowed(key, value):
                detail = f"value is not allowed: {key}: {value}"
                failures.append(Failure(relative, number, "bad-field", detail))
        kind = fields.get("type")
        if config.types and path not in exempt and kind is not None:
            below = path.relative_to(docs_dir).parts
            if len(below) < 2 or below[0] != kind[1]:
                detail = (
                    f"page of type {kind[1]} is not below {config.docs_dir}/{kind[1]}/"
                )
                failures.append(Failure(relative, kind[0], "misplaced", detail))
        if config.index and path != index and path.resolve() not in indexed:
            detail = f"{config.docs_dir}/README.md has no link to this page"
            failures.append(Failure(relative, 1, "unindexed", detail))
        ident = fields.get("id")
        if config.front_matter and ident is not None:
            number, value = ident
            if value in owners:
                detail = f"id is also on {owners[value]}: {value}"
                failures.append(Failure(relative, number, "duplicate-id", detail))
            else:
                owners[value] = relative
    return failures


_BADGE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
"""A badge: an image inside a link, `[![<alt>](<image>)](<target>)` (D2.14)."""

_README_SECTIONS = (
    (
        "Install",
        ("Install", "Installation", "Quick Start", "Quickstart", "Getting Started"),
    ),
    ("Usage", ("Usage",)),
)
"""The sections that the root README has, each with the heading texts it
accepts (D2.14, D15.18)."""

_LICENCE_STEMS = ("license", "licence", "copying")
"""The names of a licence file at the root, without case and without an
extension. One of them is enough (D2.14, D15.14)."""


def licence_present(root: Path) -> bool:
    """Say whether the root holds a licence file (D15.14).

    `trueup.health` imports this function, so the checker and the health
    rows use one candidate test.

    Args:
        root: The repository root.

    Returns:
        True when a file at the root is named `LICENSE`, `LICENCE` or
        `COPYING`, in any case and with any extension.
    """
    try:
        entries = list(root.iterdir())
    except OSError:
        return False
    return any(
        os.path.isfile(entry) and entry.name.split(".", 1)[0].lower() in _LICENCE_STEMS
        for entry in entries
    )


def _title_end(lines: list[str]) -> int | None:
    """Give the count of lines up to the end of the title of a README (D2.14, rule 1).

    Blank lines and HTML blocks can come before the title. An HTML block
    starts with a line whose first text is `<` and ends before the next
    blank line. A block that starts with `<!--` ends after the line that
    holds `-->`. An `<h1` in such a block is the title (D15.18).

    Args:
        lines: The lines of the file.

    Returns:
        The line of a Markdown heading of level 1. For an HTML `<h1`, the
        line of the first `</h1>` from there. `None` when other text comes
        before the title, the first heading is not of level 1, or an HTML
        title has no end tag.
    """
    block = ""  # "html" or "comment" while an HTML block is open.
    for start, line in enumerate(lines):
        stripped = line.strip()
        if block != "comment" and not stripped:
            block = ""
            continue
        in_comment = block == "comment" or (not block and stripped.startswith("<!--"))
        if (
            not in_comment
            and "<h1" in stripped.lower()
            and (block or stripped.startswith("<"))
        ):
            for number in range(start, len(lines)):
                if "</h1>" in lines[number].lower():
                    return number + 1
            return None
        if not block and stripped.startswith("<"):
            block = "comment" if stripped.startswith("<!--") else "html"
        if block == "comment" and "-->" in stripped:
            block = ""
            continue
        if block:
            continue
        if _FENCE_LINE.match(line) is None and _MD_HEADING.match(line) is not None:
            return start + 1 if _heading_level(line) == 1 else None
        return None
    return None


def _check_i(root: Path, config: Config) -> list[Failure]:
    """Check the README rules of D2.14 on the file `README.md` at the root.

    The name of the file is fixed. A line in a fenced code block is not a
    heading, a paragraph or a badge. A badge in an inline code span is not a
    badge.

    Args:
        root: The repository to examine.
        config: The configuration. The check runs only when `readme` is on
            and no `[scan] ignore` glob matches `README.md`. The rule
            `no-index-link` runs only when `index` is on and `README.md` of
            `docs_dir` exists, and it looks for a link to that file (D14.5,
            D15.18).

    Returns:
        One failure of the eight kinds of check i for each broken rule, or one
        `unreadable` failure when the file does not decode. The path of each
        is `README.md`, with the detail and the line of D2.4.
    """
    name = "README.md"
    if not config.readme or matches_ignore(name, config.ignore):
        return []
    path = root / name
    if not os.path.isfile(path):
        return [Failure(name, 1, "no-readme", "no README.md at the root")]
    try:
        text = _read_bytes(path).decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        return [
            Failure(
                name, 1, "unreadable", f"file cannot be read: {type(error).__name__}"
            )
        ]
    lines = text.splitlines()
    outside = _md_lines_outside_fences(text)
    failures: list[Failure] = []
    title_end = _title_end(lines)
    if title_end is None:
        failures.append(Failure(name, 1, "no-title", "line 1 is not a title"))
        title_end = 0
    block_end = title_end
    while block_end < len(lines) and (
        not lines[block_end].strip()
        or (
            _FENCE_LINE.match(lines[block_end]) is None
            and _BADGE.search(lines[block_end]) is not None
            and not _BADGE.sub("", lines[block_end]).strip()
        )
    ):
        block_end += 1
    if (
        block_end == len(lines)
        or _MD_HEADING.match(lines[block_end]) is not None
        or _FENCE_LINE.match(lines[block_end]) is not None
    ):
        failures.append(
            Failure(name, 1, "no-description", "no paragraph after the title")
        )
    headings: list[tuple[int, str]] = []
    for number, line in enumerate(outside, start=1):
        if not title_end < number <= block_end and _BADGE.search(
            _CODE_SPAN.sub("", line)
        ):
            detail = "badge is outside the block under the title"
            failures.append(Failure(name, number, "badges-scattered", detail))
        found = _MD_HEADING.match(line)
        if found is not None and _heading_level(line) == 2:
            headings.append((number, found.group(1)))
    texts = [heading for _, heading in headings]
    required = _README_SECTIONS
    if config.licence:
        required = (*required, ("License", ("License",)))
    for section, accepted in required:
        if not any(heading in accepted for heading in texts):
            detail = f"section is absent: {section}"
            failures.append(Failure(name, 1, "no-section", detail))
    if "License" in texts:
        position = texts.index("License")
        if position < len(texts) - 1:
            detail = "License is not the last section"
            failures.append(Failure(name, headings[position][0], "misordered", detail))
    if config.licence and not licence_present(root):
        detail = "no LICENSE, LICENCE or COPYING file at the root"
        failures.append(Failure(name, 1, "no-licence-file", detail))
    # D15.18: the rule applies only when the docs index exists.
    if config.index and os.path.isfile(root / config.docs_dir / "README.md"):
        try:
            index = (root / config.docs_dir / "README.md").resolve()
        except (RuntimeError, OSError):
            index = None
        for _, _, _, path_part, _ in _md_links(text):
            if not path_part or "\0" in path_part:
                continue
            try:
                resolved = (root / path_part).resolve()
            except (RuntimeError, OSError):
                continue
            if resolved == index:
                break
        else:
            detail = f"no link to {config.docs_dir}/README.md"
            failures.append(Failure(name, 1, "no-index-link", detail))
    return failures


def write_edges(path: Path, edges: Sequence[Edge]) -> None:
    """Write the edge file of one report (D2.6).

    The document holds `schema` and `edges`, in that key order. Each record
    holds the fields of `Edge`, in the field order. The file has two spaces
    of indent and a final newline, and it holds no time, no host name and no
    absolute path, so two runs on the same tree give the same bytes.

    Args:
        path: The file to write.
        edges: The records, already sorted by `run`.

    Raises:
        OSError: The file cannot be written.
    """
    document = {
        "schema": 1,
        "edges": [
            {
                "source": edge.source,
                "line": edge.line,
                "unit": edge.unit,
                "marker": edge.marker,
                "target": edge.target,
                "id": edge.id,
                "status": edge.status,
            }
            for edge in edges
        ],
    }
    text = json.dumps(document, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


USAGE = """\
usage: python3 ref_check.py [--root DIR] [--edges FILE] [--config FILE]

Check that each reference in the source matches its target.

  --root DIR, --root=DIR  the repository to examine
  --edges FILE            write the edge file of the references
  --config FILE           read FILE in place of ROOT/ref_check.toml
  -h, --help              print this text and stop

Exit 0: no failure. Exit 1: one failure or more.
Exit 2: the command line or the configuration file is not valid."""
"""The text that `--help` prints (D2.3)."""

REFS_FLAGS: tuple[str, ...] = ("--root", "--edges", "--config", "--help", "-h")
"""The flags that `main` accepts (D2.3, D15.36). The skill drift test reads them."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and give the exit code.

    The command line is `python3 ref_check.py [--root DIR] [--edges FILE]
    [--config FILE]`. `--root` names the repository to examine, and it
    defaults to `ROOT`. `--root=DIR` is the same flag. `--help` and `-h`
    print `USAGE`. `--edges` names the edge file to write. With no flag, no
    file is written. `--config` (or `--config=FILE`) names the configuration
    file to read in place of `ROOT/ref_check.toml` (D8.1).

    Standard output gets one line for each failure. Then it gets one
    `warning:` line for each failure that a registered reader change turned
    into a warning, and one line for each such change (D16.3). Then it gets
    one summary line. A warning does not change the exit code.
    After a run, standard error gets the notice `ref_check: checks off:
    <letters>` when one or more switches of checks e to i are off. Then
    it gets the notice `ref_check: excused by an open plan row: <ids>` when
    check c has one or more excused ids (D2.3, D2.8). Then it gets the
    notice `ref_check: kept: <n>` when `[keep] failures` names one or more
    failures of the run (D9.2); a kept failure is not printed and not
    counted.

    Args:
        argv: The arguments after the program name. `None` reads `sys.argv`.

    Returns:
        0 when the report holds no failure, or after `--help`. 1 when it
        holds one or more. 2
        when the command line or the configuration file is not valid, the
        edge file cannot be written, or a check raises an error that no
        narrow catch takes (D15.1).
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = ROOT
    edges: Path | None = None
    config_path: Path | None = None
    while arguments:
        flag = arguments.pop(0)
        if flag in ("--help", "-h"):
            print(USAGE)
            return 0
        if flag.startswith("--root=") and flag != "--root=":
            root = Path(flag.removeprefix("--root=")).resolve()
            continue
        if flag == "--root" and arguments:
            root = Path(arguments.pop(0)).resolve()
            continue
        if flag == "--edges" and arguments:
            edges = Path(arguments.pop(0))
            continue
        if flag.startswith("--config=") and flag != "--config=":
            config_path = Path(flag.removeprefix("--config=")).resolve()
            continue
        if flag == "--config" and arguments:
            config_path = Path(arguments.pop(0)).resolve()
            continue
        print(f"ref_check: argument is not valid: {flag}", file=sys.stderr)
        return 2
    if not os.path.isdir(root):
        print(f"ref_check: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        report = run(root, config_path)
    except ConfigError as error:
        print(f"ref_check: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # reason: D15.1 last-resort handler
        if os.environ.get("TRUEUP_DEBUG") == "1":
            traceback.print_exc()
        print(
            f"ref_check: internal error: {type(error).__name__}: {error} "
            "(set TRUEUP_DEBUG=1 for the traceback)",
            file=sys.stderr,
        )
        return 2
    for failure in report.failures:
        print(format_failure(failure))
    counts: dict[str, int] = {}
    for name, failure in report.warnings:
        print(f"warning: {format_failure(failure)}")
        counts[name] = counts.get(name, 0) + 1
    for name, count in counts.items():
        print(
            f"ref_check: {count} warnings from reader change {name}; "
            "add it to [refs] accepted_reader_changes to fail on them"
        )
    print(f"ref_check: {len(report.failures)} failures, {len(report.edges)} references")
    if edges is not None:
        try:
            write_edges(edges, report.edges)
        except OSError as error:
            print(f"ref_check: edge file cannot be written: {error}", file=sys.stderr)
            return 2
    config = report.config
    switches = (
        ("e", config.registry),
        ("f", config.comments),
        ("g", config.links),
        ("h", config.layout),
        ("i", config.readme),
    )
    off = [letter for letter, on in switches if not on]
    if off:
        print(f"ref_check: checks off: {', '.join(off)}", file=sys.stderr)
    if report.excused:
        print(
            f"ref_check: excused by an open plan row: {', '.join(report.excused)}",
            file=sys.stderr,
        )
    if report.kept:
        print(f"ref_check: kept: {len(report.kept)}", file=sys.stderr)
    return 1 if report.failures else 0


@functools.cache
def _default_report() -> Report:
    """Give the report of the default root, one time for each process.

    Returns:
        The report of `run(ROOT)`. The cache keeps the walk to one run for
        each process, because the ten entry points share this report.
    """
    return run(ROOT)


def _assert_no(*kinds: str) -> None:
    """Assert that the report of the default root holds no failure of these kinds.

    Args:
        *kinds: The failure kinds this entry point gates on.

    Raises:
        AssertionError: The report holds one such failure or more. The
            message holds the failure lines of D2.4, one for each line.
    """
    report = _default_report()
    lines = [format_failure(item) for item in report.failures if item.kind in kinds]
    if lines:
        raise AssertionError("\n".join(lines))


def test_cited_ids_exist_in_the_design() -> None:
    """Assert no `unknown-id`, `no-target` or `malformed` failure. This is check a."""
    _assert_no("unknown-id", "no-target", "malformed")


def test_every_test_in_a_marked_file_has_a_marker() -> None:
    """Assert no `unmarked` failure. This is check b."""
    _assert_no("unmarked")


def test_verification_claims_have_a_test() -> None:
    """Assert no `unproved` failure. This is check c."""
    _assert_no("unproved")


def test_pinned_law_sections_did_not_change() -> None:
    """Assert no `drift` failure. This is check d."""
    _assert_no("drift")


def test_markers_are_in_the_registry() -> None:
    """Assert no `unregistered` failure. This is check e."""
    _assert_no("unregistered")


def test_suppressions_and_files_have_their_comment() -> None:
    """Assert no `no-reason` and no `no-header` failure. This is check f."""
    _assert_no("no-reason", "no-header")


def test_document_links_resolve() -> None:
    """Assert no `broken-link` and no `stale-pin` failure. This is check g."""
    _assert_no("broken-link", "stale-pin")


def test_documents_follow_the_layout() -> None:
    """Assert no failure of the five kinds of check h (D2.13)."""
    _assert_no("no-front-matter", "bad-field", "misplaced", "unindexed", "duplicate-id")


def test_readme_follows_the_standard() -> None:
    """Assert no failure of the eight kinds of check i (D2.14)."""
    _assert_no(
        "no-readme",
        "no-title",
        "no-description",
        "no-section",
        "misordered",
        "no-licence-file",
        "badges-scattered",
        "no-index-link",
    )


def test_each_source_file_can_be_read() -> None:
    """Assert no `unreadable` failure. Every check gives this kind."""
    _assert_no("unreadable")


if __name__ == "__main__":
    raise SystemExit(main())
