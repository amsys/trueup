"""Document rules: README length, changelog shape, page status and banned words (D5.4).

`docrules_findings` always runs the README-length check, the banned-word
floor and, in a full check, one run of `ref_check.py` (D12.9). When the
docs mode in force (`config.resolve_docs`) is `"full"` it also runs the
changelog shape check and the `superseded`/`stale` front-matter checks. `trueup.health` already covers the community-file
table (contributing guide, the public-only files, the agent-file check), so
this module does not repeat it. `banned_words` gives the one banned-word
list in force (I-25): the built-in `trueup/data/banned.txt`, or the file
and entries that `[prose]` names. `trueup.config` and `trueup.survey` do
not read the list. `repins` turns each stale pin with one
clear fix into a re-pin entry that `apply` can carry out (D12.6).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from trueup import config as config_mod, fsread, managed, ref_check
from trueup.config import Config
from trueup.findings import Finding, line_fingerprint, number_repeats
from trueup.survey import LANGUAGE_EXTENSIONS, Survey

_BANNED_WORDS_PATH = Path(__file__).resolve().parent / "data" / "banned.txt"
"""The built-in banned-word list, the list of `[prose] banned = "builtin"`
(I-25, D14.4)."""

_DEFAULT_DOCS_DIR = Config().layout_docs_dir
"""The docs directory when no config is given: the default of `[layout]
docs_dir` (D14.4)."""

_BUNDLED_REF_CHECK = Path(__file__).resolve().parent / "ref_check.py"
"""The checker that ships inside `trueup/` (D5.10's plugin layout); `check`
runs this copy only, never the target's own copy, wherever `[refs] path`
names it there (I-18)."""

_TEXT_READ_CAP = 1024 * 1024
"""The longest file, in bytes, that a document rule reads (D16.10, I-50)."""

_README_MAX_LINES = 200
"""The R10 line budget for `README.md`, above which it is a `warn`."""

_INLINE_CODE = re.compile(r"`[^`]*`")
"""One inline code span on a Markdown line, dropped before a word scan."""

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
"""Per-language comment leaders. A line counts as a comment when its
stripped text starts with one of these, the same line-based reading
`trueup.survey` uses for its own line counter; a block comment whose body
line carries no leader of its own is not read as prose (D5.4)."""

_CHANGELOG_TYPE_HEADINGS: tuple[str, ...] = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)
"""The only `### <type>` headings a CHANGELOG.md entry may use (D5.4)."""

_CHANGELOG_UNRELEASED = "## [Unreleased]"
_CHANGELOG_VERSION = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}$")
_CHANGELOG_TYPE_HEADING = re.compile(r"^### (.+)$")

_REFCHECK_FAILURE_LINE = re.compile(
    r"^(?P<path>.+):(?P<line>\d+): \[(?P<kind>[a-z-]+)\] (?P<detail>.*)$"
)
"""One failure line of `ref_check.py`'s report: `<path>:<line>: [<kind>] <detail>`."""

_REFCHECK_WARNING_LINE = re.compile(
    r"^ref_check: (?P<count>\d+) warnings from reader change (?P<name>[^\s;,]+);"
)
"""The line of `ref_check.py` that counts the warnings of one reader change (D16.3)."""


def docrules_findings(
    survey: Survey, cfg: Config | None, only: frozenset[str] | None = None
) -> list[Finding]:
    """Run the document rules of D5.4 over one survey.

    Args:
        survey: The survey to check.
        cfg: The loaded `trueup.toml`, or `None` when it is absent, in which
            case `docs` is `auto` and `stale_days` takes `Config`'s own
            default. `config.resolve_docs` gives the docs mode by tier.
        only: Repo-relative POSIX paths to scope the run to (arch: D6.17).
            `None` runs every row over the full survey, `refcheck` included
            (the v1 shape, byte for byte). A value narrows `survey.files` to
            the paths it holds before the README, prose and changelog rows
            read it, and skips `refcheck` (too slow to run on every scoped
            check). The page row still emits findings for pages in `only`
            only, but reads every page's `id` field from the full,
            unscoped survey, so a `superseded_by` link to a page outside
            `only` is not misread as broken (D6.17).

    Returns:
        The findings of every rule this module owns, unsorted, in the same
        shape `hygiene.hygiene_findings` and `health.health_findings`
        return theirs: `trueup.findings.sorted_findings` gives the I-21
        order once a caller merges the lists.
    """
    docs_mode = config_mod.resolve_docs(cfg, survey.tier)
    stale_days = cfg.stale_days if cfg is not None else Config().stale_days
    docs_dir = cfg.layout_docs_dir if cfg is not None else _DEFAULT_DOCS_DIR
    known_ids_survey: Survey | None = None
    if only is not None:
        known_ids_survey = survey
        survey = replace(
            survey, files=tuple(path for path in survey.files if path in only)
        )

    findings: list[Finding] = []
    readme_finding = _readme_length_finding(survey, docs_dir)
    if readme_finding is not None:
        findings.append(readme_finding)
    findings.extend(_prose_findings(survey, banned_words(cfg)))
    if docs_mode == "full":
        findings.extend(_changelog_findings(survey))
        findings.extend(_page_findings(survey, stale_days, known_ids_survey, docs_dir))
    if only is None:
        findings.extend(
            _refcheck_findings(survey.root, _refcheck_config_text(cfg, survey))
        )
    return findings


def _refcheck_config_text(cfg: Config | None, survey: Survey) -> str:
    """Give the `ref_check.toml` text that the `ref-check` hook has after `apply` (D8.1, D12.9).

    Args:
        cfg: The loaded `trueup.toml`, or `None` when it is absent.
        survey: The survey of the target; its tier decides the managed set
            and the docs mode.

    Returns:
        `managed.render_ref_check_config` of the effective config with no
        `[keep]` table, when `managed.refcheck_switches_on` is true
        (D14.5); the renderer resolves `docs` for the survey tier. Else an
        empty text: the checker then acts as with no `ref_check.toml`,
        every switch off and checks a-d on.
    """
    effective = managed.effective_config(cfg, survey)
    if not managed.refcheck_switches_on(effective, survey):
        return ""
    return managed.render_ref_check_config(effective, survey, keep=False)


def _universal_newlines(text: str) -> str:
    """Give text the line ends that `Path.read_text` gives.

    `fsread` returns the bytes of a file as they are, so a CRLF page
    would otherwise differ from what `ref_check` reads and pins.

    Args:
        text: The decoded text.

    Returns:
        The text with CRLF and CR changed to LF.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_text(path: Path) -> str | None:
    """Read a file as text, tolerating an unreadable or non-UTF-8 file.

    The read is bounded (D16.10, I-50): a path that does not resolve, a
    device, a FIFO, a socket and a file over `_TEXT_READ_CAP` give `None`.
    The root test for a file of the target is in `_surveyed_text`.

    Args:
        path: The file to read.

    Returns:
        The decoded text, or `None` when the file cannot be read.
    """
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    text = fsread.read_text_capped(resolved.parent, resolved.name, _TEXT_READ_CAP)
    return None if text is None else _universal_newlines(text)


def _surveyed_text(survey: Survey, rel: str) -> str | None:
    """Read one surveyed file, and refuse a symlink out of the root (D16.10, I-50).

    Args:
        survey: The survey that lists the file.
        rel: The repo-relative path.

    Returns:
        The text, or `None` when the path resolves outside the root or
        `_read_text` gives `None`.
    """
    full = survey.root / rel
    try:
        inside = full.resolve().is_relative_to(survey.root.resolve())
    except (OSError, RuntimeError):
        return None
    return _read_text(full) if inside else None


def read_repo_text(root: Path, rel: str, encoding: str = "utf-8") -> str | None:
    """Read one tracked file with a strict decode, as `Path.read_text` does.

    A caller that writes the text back needs the strict decode: a file with
    bad bytes must stay as it is.

    Args:
        root: The repository root.
        rel: The repo-relative path.
        encoding: The codec, `utf-8` or `utf-8-sig`.

    Returns:
        The text with universal newlines, or `None` for an `fsread` refusal
        (D16.10, I-50) or for bytes that do not decode.
    """
    data = fsread.read_capped(root, rel, _TEXT_READ_CAP)
    if data is None:
        return None
    try:
        return _universal_newlines(data.decode(encoding))
    except UnicodeDecodeError:
        return None


def _readme_length_finding(
    survey: Survey, docs_dir: str = _DEFAULT_DOCS_DIR
) -> Finding | None:
    """R10: `README.md` over `_README_MAX_LINES` lines is a `warn` (D5.4).

    A missing `README.md` is `trueup.health`'s finding, not this one.

    Args:
        survey: The survey to check.
        docs_dir: The `[layout] docs_dir` name that the action names
            (D14.4).

    Returns:
        One `warn` finding when the README is present and too long, else
        `None`.
    """
    path = "README.md"
    if path not in survey.files:
        return None
    text = _surveyed_text(survey, path)
    if text is None:
        return None
    line_count = len(text.splitlines())
    if line_count <= _README_MAX_LINES:
        return None
    return Finding(
        id=f"readme-length:{path}",
        rule="readme-length",
        category="docs",
        severity="warn",
        path=path,
        evidence=f"{path} is {line_count} lines, over {_README_MAX_LINES}",
        action=f"split the README into {docs_dir}/ pages, and link them from it",
        auto=False,
    )


def _load_banned_words() -> tuple[str, ...]:
    """Read the banned-word list, one entry per non-blank line (I-25).

    Returns:
        The list's entries, in file order, with surrounding white space
        stripped; empty when `_BANNED_WORDS_PATH` cannot be read.
    """
    return _read_entries(_BANNED_WORDS_PATH)


def _read_entries(path: Path) -> tuple[str, ...]:
    """Read one file in the `banned.txt` form, one entry per non-blank line.

    Args:
        path: The file to read.

    Returns:
        The entries, in file order, with surrounding white space stripped;
        empty when the file cannot be read.
    """
    text = _read_text(path)
    if text is None:
        return ()
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def banned_words(cfg: Config | None) -> tuple[str, ...]:
    """Give the one banned-word list in force for a run (I-25, D14.4).

    `[prose] banned` picks the base list: `"builtin"` reads
    `trueup/data/banned.txt`, `"off"` gives no entries, and any other
    value is the path of a file in the `banned.txt` form. `config.load`
    resolves that path to an absolute path and refuses a missing file.
    The `[prose] extra` entries come after the base entries, in order.
    The prose row and the Vale style that `trueup lint` renders read
    this list.

    Args:
        cfg: The effective config, or `None` for the defaults.

    Returns:
        The entries in force, `word` or `word => <regex>` each. An empty
        tuple turns the prose pass off.
    """
    effective = cfg if cfg is not None else Config()
    if effective.prose_banned == "builtin":
        base = _load_banned_words()
    elif effective.prose_banned == "off":
        base = ()
    else:
        base = _read_entries(Path(effective.prose_banned))
    extra = tuple(entry.strip() for entry in effective.prose_extra if entry.strip())
    return base + extra


_ENTRY_SEPARATOR = " => "
"""Splits a `data/banned.txt` form line into its word and its regex (D6.9)."""


def _split_entry(entry: str) -> tuple[str, str]:
    """Split one banned-word entry into the word it names and the regex it bans.

    A bare-word entry (no `_ENTRY_SEPARATOR`) is its own regex, escaped so it
    matches only itself (D6.9).

    Args:
        entry: One line of `data/banned.txt`: `word` or `word => <regex>`.

    Returns:
        The word RULES rule 7 names, and the regex source that bans it.
    """
    if _ENTRY_SEPARATOR in entry:
        word, pattern = entry.split(_ENTRY_SEPARATOR, 1)
        return word.strip(), pattern.strip()
    return entry, re.escape(entry)


def _entry_pattern(entry: str) -> re.Pattern[str]:
    r"""Compile one banned-word entry into a whole-word, case-free pattern (D6.9).

    Args:
        entry: One line of `data/banned.txt`: `word` or `word => <regex>`.

    Returns:
        A pattern that matches the entry's regex, wrapped as
        `\b(?:<regex>)\b`, ignoring case.
    """
    _, pattern = _split_entry(entry)
    return re.compile(r"\b(?:" + pattern + r")\b", re.IGNORECASE)


_QUOTE_CUE = re.compile(
    r"\b(?:banned|never use|do not use|don't use|forbidden|prohibited|not allowed)\b",
    re.IGNORECASE,
)
"""A cue that a Markdown block states a vocabulary rule, so its banned words
are quoted, not used (D8.4). The Vale template's `BlockIgnores` holds the
same alternation, so `check` and the Vale hook agree."""

_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
"""The start of a Markdown list item: a bullet or a number, then a space."""

_QUOTE_CUE_LINES = 3
"""How many lines of a block, from its first, may hold the cue (D8.4). The
Vale `BlockIgnores` regexes read the same window; an unbounded window is
quadratic on Vale's backtracking engine and took minutes on a long page."""


def _drop_quoted_blocks(lines: list[str]) -> list[str]:
    """Blank each Markdown block that quotes the banned list (D8.4).

    A block is a list item or a paragraph. A list item starts at a bullet or
    a number and continues over each indented line (a nested item too) and
    over a blank line that an indented line follows (a loose item). It ends
    at a line with no indent: a new item starts a new block, any other line
    starts a paragraph. A paragraph starts at a line with no indent that is
    not an item, and continues over every line up to a blank line, bullets
    and numbers included, so a lead-in sentence keeps the list it
    introduces. A heading, a block quote and a table row (`#`, `>`, `|`
    first) are neutral: they end a block and belong to none. A block whose
    first `_QUOTE_CUE_LINES` lines hold a `_QUOTE_CUE` cue states a rule,
    so each of its lines becomes `""` and the word scan does not read it.
    The two `BlockIgnores` regexes of the Vale template read the same
    shapes and the same window.

    Args:
        lines: The prose lines of `_markdown_prose_lines`, one per source
            line.

    Returns:
        The same list, with each quoting block blanked.
    """
    result = list(lines)
    start: int | None = None
    item = False

    def close(end: int) -> None:
        window = (
            lines[start : min(end, start + _QUOTE_CUE_LINES)]
            if start is not None
            else []
        )
        if start is not None and _QUOTE_CUE.search(" ".join(window)):
            for index in range(start, end):
                result[index] = ""

    for index, line in enumerate(lines):
        stripped = line.strip()
        indented = bool(line) and line[0] in " \t"
        if not stripped:
            after = lines[index + 1] if index + 1 < len(lines) else ""
            if item and after.strip() and after[0] in " \t":
                continue  # a loose item spans the blank line
            close(index)
            start = None
        elif not indented and stripped[0] in "#>|":
            close(index)  # a heading, quote or table row is neutral
            start = None
        elif start is None:
            start = index
            item = bool(_LIST_ITEM.match(line))
        elif indented:
            continue  # a continuation line of an item or a paragraph
        elif item:
            close(index)  # a line with no indent ends an item ...
            start = index
            item = bool(_LIST_ITEM.match(line))  # ... as a new item or a paragraph
    close(len(lines))
    return result


def _markdown_prose_lines(text: str) -> list[str]:
    """Give the prose text of a Markdown file, one entry per line.

    A fenced code block (` ``` ` or `~~~`) is blanked out, and an inline
    code span on a line still outside a fence is removed from that line, so
    the word scan below never reads code (D5.4). Line numbers of the
    returned list stay one-to-one with the source file.

    Args:
        text: The Markdown file's content.

    Returns:
        One entry per source line: the line's prose text, or `""` for a
        line inside a fenced code block.
    """
    lines: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            lines.append("")
            continue
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            lines.append("")
            continue
        lines.append(_INLINE_CODE.sub(" ", line))
    return lines


def _language_for_path(path: str) -> str | None:
    """Give the language a surveyed path belongs to, by its extension.

    Args:
        path: A repo-relative POSIX path.

    Returns:
        The language name, or `None` when no `LANGUAGE_EXTENSIONS` entry
        matches.
    """
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        if path.endswith(extensions):
            return language
    return None


def _comment_lines(text: str, language: str) -> list[str]:
    """Give the comment text of a source file, one entry per line.

    Args:
        text: The source file's content.
        language: One of `_COMMENT_LEADERS`' keys.

    Returns:
        One entry per source line: the line itself when it is a comment
        line by `_COMMENT_LEADERS`, else `""`. Line numbers stay one-to-one
        with the source file.
    """
    leaders = _COMMENT_LEADERS[language]
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lines.append(line if stripped.startswith(leaders) else "")
    return lines


_BACKREFERENCE = re.compile(r"\\[1-9]|\(\?P=")
"""A numbered or named back reference in an entry's regex. The union of
`_prefilter` would shift or clash its group, so such a list gets no
pre-filter."""


@lru_cache(maxsize=8)
def _prefilter(words: tuple[str, ...]) -> re.Pattern[str] | None:
    r"""Compile one alternation of every banned-word entry (D14.14).

    A line that one entry's pattern matches also matches the alternation,
    because `search` tries each alternative at each position. So the
    per-entry loop of `_first_hits` can skip each line the alternation
    misses, and the findings stay the same. A line the alternation hits
    still goes through each entry's own pattern.

    Args:
        words: The banned-word entries, in list order.

    Returns:
        The pattern `\b(?:<regex 1>)\b|\b(?:<regex 2>)\b|...`, ignoring
        case; `None` when the list is empty, an entry holds a back
        reference, or the union does not compile. `None` means "scan every
        line".
    """
    sources = [_split_entry(entry)[1] for entry in words]
    if not sources or any(_BACKREFERENCE.search(source) for source in sources):
        return None
    union = "|".join(r"\b(?:" + source + r")\b" for source in sources)
    try:
        return re.compile(union, re.IGNORECASE)
    except re.error:
        return None


def _first_hits(lines: list[str], words: tuple[str, ...]) -> list[tuple[str, int]]:
    """Find the first line of each banned word that appears in `lines`.

    Args:
        lines: The text to scan, one entry per source line (blank entries
            are the lines the caller already excluded).
        words: The banned-word entries to look for, in list order.

    Returns:
        `(word, line_number)` pairs, one per matching word, sorted by line
        number then word for a deterministic evidence line (I-21).
    """
    prefilter = _prefilter(words)
    candidates = [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if line and (prefilter is None or prefilter.search(line))
    ]
    hits: list[tuple[str, int]] = []
    if not candidates:
        return hits
    for entry in words:
        word, _ = _split_entry(entry)
        pattern = _entry_pattern(entry)
        for number, line in candidates:
            if pattern.search(line):
                hits.append((word, number))
                break
    return sorted(hits, key=lambda hit: (hit[1], hit[0]))


def _prose_findings(survey: Survey, words: tuple[str, ...]) -> list[Finding]:
    """The banned-word floor: one `prose:<path>` finding per file that holds one (D5.4).

    Runs over every surveyed Markdown file's prose (fenced and inline code
    left out, and each block that quotes the list blanked, D8.4) and every
    surveyed source file's comments, in the eight languages of
    `LANGUAGE_EXTENSIONS`.

    Args:
        survey: The survey to check.
        words: The banned-word list in force, from `banned_words` (I-25).
            An empty list skips the pass (D14.4).

    Returns:
        One `error` finding per file that holds at least one banned word or
        phrase; its evidence names each word and the first line it appears
        on.
    """
    if not words:
        return []
    findings: list[Finding] = []
    for path in survey.files:
        is_markdown = path.endswith(".md")
        language = None if is_markdown else _language_for_path(path)
        if not is_markdown and language is None:
            continue
        text = _surveyed_text(survey, path)
        if text is None:
            continue
        if language is None:
            lines = _drop_quoted_blocks(_markdown_prose_lines(text))
        else:
            lines = _comment_lines(text, language)
        hits = _first_hits(lines, words)
        if not hits:
            continue
        evidence = ", ".join(f"{word!r} (line {number})" for word, number in hits)
        findings.append(
            Finding(
                id=f"prose:{path}",
                rule="prose",
                category="docs",
                severity="error",
                path=path,
                evidence=evidence,
                action="remove or rephrase the banned word(s)",
                auto=False,
            )
        )
    return findings


def _changelog_defect(path: str, line: int, text: str, detail: str) -> Finding:
    """Build one `changelog` finding for one shape defect (D5.4, D15.8).

    Args:
        path: The CHANGELOG.md path, repo-relative.
        line: The line the defect sits on, or 1 when it names no single line.
        text: The text of that line (`""` when the file has no such line).
        detail: The one-line description of the defect.

    Returns:
        An `error` finding, id `changelog:<path>:<fp>`, `fp` the
        `findings.line_fingerprint` of the line, so a line added above the
        defect keeps the id. `line` holds the line number.
        `_changelog_findings` adds `:2`, `:3` to equal ids.
    """
    return Finding(
        id=f"changelog:{path}:{line_fingerprint(path, text)}",
        rule="changelog",
        category="docs",
        severity="error",
        path=path,
        evidence=detail,
        action="follow the Keep a Changelog headings: an '## [Unreleased]' section, "
        "'## [x.y.z] - YYYY-MM-DD' versions in descending order, and "
        f"'### <type>' sections from {', '.join(_CHANGELOG_TYPE_HEADINGS)}",
        auto=False,
        line=line,
    )


def _changelog_findings(survey: Survey) -> list[Finding]:
    """C6: check CHANGELOG.md's shape, when it is present (D5.4).

    A missing CHANGELOG.md is `trueup.health`'s finding, not this one.

    Args:
        survey: The survey to check.

    Returns:
        One `error` finding per shape defect: a missing `## [Unreleased]`
        heading, a `### <type>` heading outside `_CHANGELOG_TYPE_HEADINGS`,
        or a version heading not below the one before it. They come in
        line order; equal ids get `:2`, `:3` (D15.8).
    """
    path = "CHANGELOG.md"
    if path not in survey.files:
        return []
    text = _surveyed_text(survey, path)
    if text is None:
        return []
    lines = text.splitlines()
    findings: list[Finding] = []
    first = lines[0] if lines else ""
    if not any(line.rstrip() == _CHANGELOG_UNRELEASED for line in lines):
        findings.append(
            _changelog_defect(
                path,
                1,
                first,
                f"CHANGELOG.md has no '{_CHANGELOG_UNRELEASED}' heading",
            )
        )

    versions: list[tuple[int, tuple[int, int, int]]] = []
    in_entry = False
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        version_match = _CHANGELOG_VERSION.match(line)
        if version_match:
            versions.append(
                (number, tuple(int(part) for part in version_match.groups()))
            )
            in_entry = True
            continue
        if line == _CHANGELOG_UNRELEASED:
            in_entry = True
            continue
        type_match = _CHANGELOG_TYPE_HEADING.match(line)
        if type_match and in_entry:
            heading = type_match.group(1).strip()
            if heading not in _CHANGELOG_TYPE_HEADINGS:
                findings.append(
                    _changelog_defect(
                        path,
                        number,
                        line,
                        f"'### {heading}' is not one of {', '.join(_CHANGELOG_TYPE_HEADINGS)}",
                    )
                )

    for (_, previous), (line, current) in zip(versions, versions[1:]):
        if current >= previous:
            findings.append(
                _changelog_defect(
                    path,
                    line,
                    lines[line - 1],
                    f"version {'.'.join(map(str, current))} is not below the version before it",
                )
            )
    # D15.8: two defects on equal lines would share one id.
    findings.sort(key=lambda finding: finding.line)
    ids = number_repeats([finding.id for finding in findings])
    return [
        replace(finding, id=finding_id)
        for finding, finding_id in zip(findings, ids, strict=True)
    ]


@dataclass(frozen=True)
class _Page:
    """One Markdown page under `docs/`, with the front matter fields it read.

    Attributes:
        path: The page's repo-relative POSIX path.
        fields: Front-matter key to `(line, value)`, as
            `ref_check._front_matter` reads it (D15.30).
    """

    path: str
    fields: dict[str, tuple[int, str]]


def _docs_pages(survey: Survey, docs_dir: str = _DEFAULT_DOCS_DIR) -> list[str]:
    """Give each `<docs_dir>/**/*.md` path in `survey.files`, in `survey.files` order (D5.4, D14.4).

    Reading from `survey.files` rather than walking the docs directory on disk keeps
    `trueup.toml`'s `ignore` globs and git-ignored files out (D2.2), the
    same floor `_readme_length_finding` and `_changelog_findings` hold.
    The page rule is the checker's `ref_check.is_doc_page`, so a path
    below a directory whose name starts with a dot or is in
    `ref_check.SKIP_DIRS` is left out (D15.30).

    Args:
        survey: The survey to check.
        docs_dir: The `[layout] docs_dir` name, one path segment at the
            root.

    Returns:
        The repo-relative POSIX paths of the matching pages.
    """
    return [path for path in survey.files if ref_check.is_doc_page(path, docs_dir)]


def _load_pages(survey: Survey, docs_dir: str = _DEFAULT_DOCS_DIR) -> list[_Page]:
    """Read the front matter of every surveyed page under the docs directory that has a valid block.

    A page with no front matter, or a malformed one, is left out: ref_check's
    own check h already reports that defect, so P7 and P8 read only the
    pages whose fields they can trust.

    Args:
        survey: The survey to check.
        docs_dir: The `[layout] docs_dir` name.

    Returns:
        One `_Page` per page with a valid front matter block.
    """
    pages: list[_Page] = []
    for path in _docs_pages(survey, docs_dir):
        text = _surveyed_text(survey, path)
        if text is None:
            continue
        fields = ref_check._front_matter(text)
        if fields is None:
            continue
        pages.append(_Page(path=path, fields=fields))
    return pages


def _page_findings(
    survey: Survey,
    stale_days: int,
    known_ids_survey: Survey | None = None,
    docs_dir: str = _DEFAULT_DOCS_DIR,
) -> list[Finding]:
    """P7 and P8: a broken `superseded_by` link, and a stale `current` page (D5.4).

    Args:
        survey: The survey whose pages get findings. Under `check
            --changed` this is the scoped survey, so only a changed page
            can produce a `superseded` or `stale` finding.
        stale_days: `trueup.toml`'s `stale_days`.
        known_ids_survey: The survey to read every docs page's `id` field
            from, for the P7 broken-link check (arch: D6.17). `None` reads
            it from `survey` itself, the v1 (unscoped) shape. Passing the
            full, unscoped survey under `check --changed` keeps a
            `superseded_by` link to a page outside the changed set from
            being misread as broken.
        docs_dir: The `[layout] docs_dir` name that holds the pages
            (D14.4).

    Returns:
        One `error` finding, id `superseded:<path>`, per `status:
        superseded` page with no `superseded_by` field or one that names an
        id no page declares; one `error` finding, id `stale:<path>`, per
        `status: current` page whose `last_reviewed` is older than
        `stale_days`.
    """
    pages = _load_pages(survey, docs_dir)
    known_id_pages = (
        pages if known_ids_survey is None else _load_pages(known_ids_survey, docs_dir)
    )
    known_ids = {page.fields["id"][1] for page in known_id_pages if "id" in page.fields}
    today = date.today()
    findings: list[Finding] = []
    for page in pages:
        status = page.fields.get("status")
        if status is None:
            continue
        if status[1] == "superseded":
            superseded_by = page.fields.get("superseded_by")
            if superseded_by is None or superseded_by[1] not in known_ids:
                findings.append(
                    Finding(
                        id=f"superseded:{page.path}",
                        rule="superseded",
                        category="docs",
                        severity="error",
                        path=page.path,
                        evidence="status: superseded with no working superseded_by",
                        action="add 'superseded_by: <id>' naming the page that replaces this one",
                        auto=False,
                    )
                )
        elif status[1] == "current":
            last_reviewed = page.fields.get("last_reviewed")
            if last_reviewed is None:
                continue
            try:
                reviewed_date = date.fromisoformat(last_reviewed[1])
            except ValueError:
                continue  # ref_check's own check h already flags a malformed date
            age_days = (today - reviewed_date).days
            if age_days > stale_days:
                findings.append(
                    Finding(
                        id=f"stale:{page.path}",
                        rule="stale",
                        category="docs",
                        severity="error",
                        path=page.path,
                        evidence=f"last_reviewed {last_reviewed[1]} is {age_days} days old, over {stale_days}",
                        action="review the page, then update last_reviewed, or mark it superseded",
                        auto=False,
                    )
                )
    return findings


_REFCHECK_TIMEOUT = 120
"""Seconds that the bundled `ref_check.py` may run before `check` stops it (D15.23)."""


def _refcheck_findings(root: Path, config_text: str) -> list[Finding]:
    """Fold in one run of the bundled `ref_check.py` against the target (D5.4, I-18).

    `check` runs no code from the target: the checker is always the copy
    that ships beside `trueup/`, never the target's own `ref_check.py`, and
    it runs with the target root as its working directory. A target copy
    that differs from the bundled one is `managed.py`'s `file-managed`
    finding; a byte-equal one would run the same code. Neither copy is ever
    changed.

    The checker reads `config_text`, the `ref_check.toml` that `apply` would
    write less its `[keep]` table, from a temporary file outside the root
    (`--config`, D8.1, D9.2). So the row before the first `apply` equals
    the row after it, a stale or absent `ref_check.toml` in the target
    changes nothing, and `check` still sees the kept findings. The root
    gets no file.

    Args:
        root: The repository root to check.
        config_text: The text of `managed.render_ref_check_config` for the
            config in force, with `keep=False`.

    Returns:
        One `error` finding per parsed failure line, id from
        `_refcheck_ids`; when the process exits non-zero with no line that
        parses, one `error` finding, id `refcheck:`, whose evidence is its
        standard error; when it exits 2, one `error` finding, id
        `refcheck-run:`, whose evidence is the last line of its standard
        error (arch: D15.1); an empty list when the bundled copy is missing, or
        the run exits 0.
    """
    if not _BUNDLED_REF_CHECK.is_file():
        return []
    root = root.resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="trueup-refcheck-") as scratch:
            config_path = Path(scratch) / "ref_check.toml"
            config_path.write_text(config_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(_BUNDLED_REF_CHECK),
                    "--root",
                    str(root),
                    "--config",
                    str(config_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=root,
                timeout=_REFCHECK_TIMEOUT,
            )
    except subprocess.TimeoutExpired:
        return [
            Finding(
                id="refcheck-run:",
                rule="refcheck-run",
                category="docs",
                severity="error",
                path="",
                evidence=f"ref_check.py timed out after {_REFCHECK_TIMEOUT} s",
                action="run ref_check.py by hand and fix what it reports",
                auto=False,
            )
        ]
    except OSError as error:
        return [
            Finding(
                id="refcheck:",
                rule="refcheck",
                category="docs",
                severity="error",
                path="",
                evidence=f"ref_check.py could not be run: {error}",
                action="run ref_check.py by hand and fix what it reports",
                auto=False,
            )
        ]
    changes = _refcheck_change_findings(result.stdout)
    if result.returncode == 0:
        return changes
    if result.returncode == 2:
        # D15.1: exit 2 is the checker's own error, not a failure of the target.
        stderr_lines = result.stderr.strip().splitlines()
        return [
            Finding(
                id="refcheck-run:",
                rule="refcheck-run",
                category="docs",
                severity="error",
                path="",
                evidence=stderr_lines[-1] if stderr_lines else "ref_check.py exited 2",
                action="run ref_check.py by hand and fix what it reports",
                auto=False,
            )
        ]
    matches = [
        match
        for line in result.stdout.splitlines()
        if not line.startswith("warning: ")
        and (match := _REFCHECK_FAILURE_LINE.match(line)) is not None
    ]
    findings = [
        Finding(
            id=finding_id,
            rule="refcheck",
            category="docs",
            severity="error",
            path=match.group("path"),
            evidence=match.group(0),
            action=_refcheck_action(match.group("kind")),
            auto=False,
            line=int(match.group("line")),
        )
        for finding_id, match in zip(_refcheck_ids(matches), matches, strict=True)
    ]
    findings.extend(changes)
    if not matches:
        findings.append(
            Finding(
                id="refcheck:",
                rule="refcheck",
                category="docs",
                severity="error",
                path="",
                evidence=result.stderr.strip()
                or f"ref_check.py exited {result.returncode} with no parseable failure line",
                action="run ref_check.py by hand and fix what it reports",
                auto=False,
            )
        )
    return findings


def _refcheck_change_findings(stdout: str) -> list[Finding]:
    """Give one info finding for each reader change that the checker warned about.

    Args:
        stdout: The standard output of `ref_check.py`.

    Returns:
        One `refs-reader-change:<name>` info finding for each warning count
        line, in output order (arch: D16.3).
    """
    findings: list[Finding] = []
    for line in stdout.splitlines():
        match = _REFCHECK_WARNING_LINE.match(line)
        if match is None:
            continue
        name = match.group("name")
        findings.append(
            Finding(
                id=f"refs-reader-change:{name}",
                rule="refs-reader-change",
                category="docs",
                severity="info",
                path="",
                evidence=f"{match.group('count')} warnings from reader change {name}",
                action=(
                    f"fix the markers, or add {name} to [refs] "
                    "accepted_reader_changes in trueup.toml to fail on them"
                ),
                auto=False,
            )
        )
    return findings


def _refcheck_action(kind: str) -> str:
    """Give the action text of one `refcheck` finding, by the failure kind.

    Args:
        kind: The `[<kind>]` of the failure line.

    Returns:
        For `unregistered`, an action that names `[refs] local_tags` of
        `trueup.toml`, the key for a project's own tag convention (D8.7);
        for every other kind, the plain action.
    """
    if kind == "unregistered":
        return (
            "use a registry marker, or, when this is the project's own tag, "
            "add its prefix to [refs] local_tags in trueup.toml"
        )
    return "fix the reference ref_check.py names, then re-run it"


def _refcheck_ids(matches: list[re.Match[str]]) -> list[str]:
    """Give each parsed `ref_check.py` failure line its own finding id (D9.2).

    The id is `refcheck:` plus the checker's own failure id, from
    `ref_check.failure_ids` on a `Failure` record per line, so a `[[keep]]`
    id and the `[keep] failures` entry `apply` renders from it name the
    same line.

    Args:
        matches: The `_REFCHECK_FAILURE_LINE` matches, in output order.

    Returns:
        One id per match, in the same order.
    """
    failures = [
        ref_check.Failure(
            match.group("path"),
            int(match.group("line")),
            match.group("kind"),
            match.group("detail"),
        )
        for match in matches
    ]
    return [f"refcheck:{item}" for item in ref_check.failure_ids(failures)]


_STALE_PIN_DETAIL = "pinned section changed: "
"""The start of the `stale-pin` failure detail that a re-pin can fix (D12.6)."""

_PIN_SHAPE = re.compile(r"[0-9a-f]{8}")
"""The shape of a pin: eight lower-case hex digits (D2.10)."""


@dataclass(frozen=True)
class Repin:
    """One pinned link whose pin `apply` can write again (arch: D12.6).

    Attributes:
        id: `repin:<path>:<line>`, the id that `apply --ids` accepts.
        path: The repo path of the page that holds the link.
        line: The line of the link, from 1.
        target: The link target with its fragment, as the failure detail
            gives it.
        old_pin: The pin that the link holds now.
        new_pin: The pin of the target section now.
    """

    id: str
    path: str
    line: int
    target: str
    old_pin: str
    new_pin: str


def repins(root: Path, findings: list[Finding]) -> tuple[Repin, ...]:
    """Give one re-pin entry for each stale pin that has one clear fix (arch: D12.6).

    A `refcheck` finding qualifies when its failure detail is
    `pinned section changed: <target>`. The function reads line `line` of
    the page with the `ref_check` link parser (`_md_links`, `_link_pin`).
    Exactly one link on that line must have that target and a pin, and
    `ref_check.section_pin` must give a pin for the target section. Else
    the finding gets no entry and stays manual. The function only reads
    files (I-18); `ref_check.py` does not change (I-8).

    Args:
        root: The repository root.
        findings: The findings of the run.

    Returns:
        The entries, sorted by id.
    """
    found: dict[str, Repin] = {}
    for finding in findings:
        if finding.rule != "refcheck":
            continue
        match = _REFCHECK_FAILURE_LINE.match(finding.evidence)
        if match is None or match.group("kind") != "stale-pin":
            continue
        detail = match.group("detail")
        if not detail.startswith(_STALE_PIN_DETAIL):
            continue
        entry = _repin_entry(
            root,
            match.group("path"),
            int(match.group("line")),
            detail[len(_STALE_PIN_DETAIL) :],
        )
        if entry is not None:
            found[entry.id] = entry
    return tuple(found[key] for key in sorted(found))


def pinned_links(text: str, line: int, target: str) -> list[str]:
    """Give the pin of each link on one line that has the target and a pin (arch: D12.6).

    The links come from `ref_check._md_links` over the whole text, so the
    fence and code span rules are those of the checker.

    Args:
        text: The page text, decoded as `ref_check` decodes it.
        line: The line, from 1.
        target: The link target with its fragment.

    Returns:
        The pins, in the order of the links.
    """
    pins: list[str] = []
    for number, written, link_target, _path, _fragment in ref_check._md_links(text):
        if number != line or link_target != target:
            continue
        pin = ref_check._link_pin(written)
        if pin is not None:
            pins.append(pin)
    return pins


def _repin_entry(root: Path, path: str, line: int, target: str) -> Repin | None:
    """Give the re-pin entry of one stale pin, or `None` when it has no clear fix (D12.6).

    Args:
        root: The repository root.
        path: The repo path of the page.
        line: The line of the link, from 1.
        target: The link target with its fragment.

    Returns:
        The entry, or `None` when a page cannot be read, the line does not
        hold exactly one pinned link with the target, or the target section
        gives no pin.
    """
    page = root / path
    text = _read_page(root, page)
    if text is None:
        return None
    pins = pinned_links(text, line, target)
    if len(pins) != 1:
        return None
    raw_path, _, fragment = (unquote(part) for part in target.partition("#"))
    if not fragment:
        return None
    target_text = _read_page(root, page.parent / raw_path) if raw_path else text
    if target_text is None:
        return None
    new_pin = ref_check.section_pin(target_text, fragment)
    if new_pin is None or _PIN_SHAPE.fullmatch(new_pin) is None or new_pin == pins[0]:
        return None
    return Repin(
        id=f"repin:{path}:{line}",
        path=path,
        line=line,
        target=target,
        old_pin=pins[0],
        new_pin=new_pin,
    )


def _read_page(root: Path, path: Path) -> str | None:
    """Read one Markdown page as `ref_check` reads it, with `utf-8-sig` (D12.6).

    A link can name the path, so the path resolves first and must stay
    below the root (D16.10, I-50).

    Args:
        root: The repository root.
        path: The file.

    Returns:
        The text, or `None` when the path is outside the root or the file
        cannot be read or decoded.
    """
    base = root.resolve()
    try:
        rel = path.resolve().relative_to(base).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return read_repo_text(base, rel, "utf-8-sig")
