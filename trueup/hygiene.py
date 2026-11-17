"""The nine slop rows: findings that run over every surveyed file (D5.4, D7.2).

Each function below is one row of the D5.4 table: `_scratch`, `_artifact`,
`_duplicate`, `_generated`, `_secret_file`, `_secret_content`, `_lockfile`,
`_binary` and `_root_budget`. `_lockfile` is the D7.2 row, joined after
`_secret_content`. `hygiene_findings` runs all nine and returns one
combined, unsorted list; `report.py` sorts and plans it together with
`health.py`'s findings.

`_secret_file` never opens the file it flags (I-23): the rule matches on
the file's name alone. `_scratch`, `_duplicate`, `_generated` and
`_binary` each read other files' bytes for their own purpose, so each one
skips a file `_is_secret_basename` names, rather than opening it (I-23).
`_secret_content` does read other text files, but its evidence names only
the pattern and the line number, never the matched text (I-23). `_duplicate`
gives no finding for a group that sits entirely under a fixture, test-data
or snapshot directory (D6.12).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import posixpath
import re
import subprocess
import tomllib
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from trueup import config as config_mod
from trueup import fsread
from trueup import layout as layout_mod
from trueup.rulesets import ESLINT_PACKAGE_TARGET
from trueup.findings import Finding, line_fingerprint, number_repeats
from trueup.survey import MANIFEST_NAMES, Survey, matches_ignore

ROOT_BUDGET: dict[str, int] = {"T0": 8, "T1": 15, "T2": 25, "T3": 35}
"""The root-entry budget per tier, before `[root] allow` is added (D5.4)."""

_SCRATCH_WORD = re.compile(r"(tmp|temp|scratch|notes|untitled)(\d+|[-_ ].*)?")
"""A scratch stem: one of the five words alone, or followed by digits, or by
`-`, `_` or a space and more text (D5.4). `template`, `temperature`,
`scratchpad` and `notes_service` stems do not match on their own; see
`_SCRATCH_WORD_SUFFIXES` for the extension rule."""

_SCRATCH_WORD_SUFFIXES: frozenset[str] = frozenset(
    {"", ".txt", ".md", ".log", ".tmp", ".out", ".old"}
)
"""The last extensions a scratch-word name may carry: none, or a text or
log kind. A source extension (`.py`, `.rs`, `.sql` and the rest) never
makes a scratch-word name scratch, so `temp_table.sql` and `notes.py` pass."""

_SCRATCH_WHOLE_STEM = re.compile(r"(notes|tmp|temp|scratch|draft|untitled)\d*")
"""A stem that is exactly one scratch word, with optional digits (D15.9).
Only such a name, or a backup suffix, is proven scratch by its name
(`scratch_proven`). `draft` joins the candidate set only as a whole stem,
so `draft-rfc.md` stays clean."""

_SCRATCH_PROVEN_GLOBS: tuple[str, ...] = ("*.bak", "*.orig", "*.rej", "*~")
"""Basename globs that prove a scratch file by name alone (D15.9)."""

_VENDOR_SEGMENTS: frozenset[str] = frozenset({"vendor", "third_party", "node_modules"})
"""A path segment at any depth that marks copied third-party code. A scratch
name there is never automatic (D15.9). Same names as
`layout._EXEMPT_SEGMENTS` less the test-data ones."""

_KEEP_BASENAMES: frozenset[str] = frozenset({".keep", ".gitkeep"})
"""Placeholder files that keep a directory in git; never scratch (D15.9)."""

_SCRATCH_GLOBS: tuple[str, ...] = (
    "*.bak",
    "*.orig",
    "*.rej",
    "*.swp",
    "*~",
    "* copy.*",
    "Copy of *",
)
"""Basename globs that look like a scratch file whatever the stem (D5.4)."""

_SCRATCH_PREFIX_ANY = re.compile(r"(scratch|untitled)(\d+|[-_ ].*)")
"""A stem starting with `scratch` or `untitled`, then a digit or a `-`,
`_` or space separator, is scratch at any extension (D10.3). `tmp`, `temp`
and `notes` stay limited to the document extensions of
`_SCRATCH_WORD_SUFFIXES`, so `tmp_file.rs` stays clean."""

_BACKUP_EXTENSIONS: frozenset[str] = frozenset({".old", ".bak", ".orig", ".backup"})
"""A backup word anywhere in a name's extension chain is scratch, whatever
the final extension (D10.3): `README.old.md`, `x.bak.py`."""

_COPY_SUFFIX_EXTENSIONS: frozenset[str] = _SCRATCH_WORD_SUFFIXES | {".rst"}
"""The document extensions the copy-suffix rule allows (D10.3). A source
extension never matches, so `v0_v1.rs` stays clean."""

_COPY_SUFFIX_STEM = re.compile(
    r"(?:[_-](?:v\d+|draft|copy|old|backup)| copy(?: \d+)?)$"
)
"""A stem ending in a version, draft, copy or backup marker, for the
copy-suffix rule (D10.3): `_v2`, `-draft`, `_copy`, ` copy`, ` copy 2`."""

_VERSION_SUFFIX_STEM = re.compile(r"[_-]v\d+$")
"""The `v<n>` alternative of `_COPY_SUFFIX_STEM` alone. Under the docs
directory it does not make a name scratch (D14.12 C2)."""

SCRATCH_DIR = ".scratch"
"""The directory the guard sends scratch files to; nothing under it is scratch (D5.8)."""

_SCRATCH_DIR_NAMES: frozenset[str] = frozenset({"tmp", "temp", "scratch"})
"""Top-level directory names `looks_scratch_path` treats as scratch,
whatever they hold (D10.3). The guard hook keeps `looks_scratch` alone and
never takes this directory rule (I-guard)."""

_ARTIFACT_DIR_GLOBS: tuple[str, ...] = (
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "*.egg-info",
)
"""Path-segment globs that mark a build or cache directory (D5.4)."""

_ARTIFACT_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".class", ".o")
"""File suffixes that are always build output (D5.4)."""

_LOCK_PAIRS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cargo.toml", ("Cargo.lock",)),
    ("pyproject.toml", ("uv.lock", "poetry.lock", "pdm.lock", "pylock.toml")),
    ("Pipfile", ("Pipfile.lock",)),
    (
        "package.json",
        (
            "package-lock.json",
            "npm-shrinkwrap.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "bun.lock",
            "bun.lockb",
        ),
    ),
    ("go.mod", ("go.sum",)),
    ("composer.json", ("composer.lock",)),
)
"""Manifest basename to the lockfile basenames its ecosystem uses (D7.2)."""

_LOCKFILE_NAMES: frozenset[str] = frozenset(
    name for _, names in _LOCK_PAIRS for name in names
)
"""Every lockfile name `_LOCK_PAIRS` lists, derived so the `generated` row
below still spares a lockfile it never flagged (D5.4) and the `lockfile`
row below reads one table of ecosystems (D7.2)."""

_PYLOCK_RE = re.compile(r"^pylock\.[^.]+\.toml$")
"""A PEP 751 lockfile variant for `pyproject.toml`: `pylock.<name>.toml`
counts as a Python lockfile beside the fixed names above (D7.2 rule 1)."""

_LOCK_ACTIONS: dict[str, str] = {
    "Cargo.toml": "run cargo generate-lockfile and commit the lockfile",
    "pyproject.toml": "run uv lock (or poetry lock, pdm lock) and commit the lockfile",
    "Pipfile": "run pipenv lock and commit the lockfile",
    "package.json": "run npm install (or yarn install, pnpm install) and commit the lockfile",
    "go.mod": "run go mod tidy and commit the lockfile",
    "composer.json": "run composer update and commit the lockfile",
}
"""The one-line lock command `_lockfile`'s finding names, per ecosystem (D7.2 rule 5)."""

_GENERATED_MARKER = re.compile(r"Code generated .* DO NOT EDIT", re.IGNORECASE)
"""The generated-file marker regex of D5.4, checked line by line."""

_SECRET_FILE_SUFFIXES: tuple[str, ...] = (".pem", ".key", ".p12", ".pfx")
_SECRET_KEY_NAMES: frozenset[str] = frozenset(
    {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
)
_ENV_ALLOWED_SUFFIXES: tuple[str, ...] = (".example", ".sample", ".template", ".dist")

_SECRET_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("an AWS access key id", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("a GitHub token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36}")),
    ("a Slack token", re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}")),
)
"""The secret-content patterns of D5.4, each with the name its evidence uses.
The private-key pattern is not here: it is a block rule (D6.10), checked
separately in `_secret_content` because it needs the lines after the
banner, not just the banner line itself."""

_PRIVATE_KEY_BANNER = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")
"""The private-key banner line of D6.10. A banner alone is not proof: a
placeholder such as `<paste private key here>` also follows it, so the
banner counts only when `_BASE64_BODY_LINE` also matches one of the next
`_PRIVATE_KEY_BODY_LOOKAHEAD` lines (D6.10, FP-5)."""

_BASE64_BODY_LINE = re.compile(rb"^[A-Za-z0-9+/=]{40,}$")
"""A PEM body line: base64 characters only, stripped, 40 or more of them
(D6.10). A placeholder line such as `<paste ... >` or a `#` comment never
matches this, so it never turns a banner into a finding."""

_PRIVATE_KEY_BODY_LOOKAHEAD = 3
"""How many lines after a private-key banner `_secret_content` checks for a
base64 body line (D6.10)."""

_TEXT_READ_CAP = 1024 * 1024
_BINARY_MAX_SIZE = 1024 * 1024
_BINARY_SNIFF_SIZE = 8192
_BINARY_SNIFF_MIN_SIZE = 100 * 1024
_BINARY_SNIFF_TIER = "T3"
"""Below this tier the NUL-byte sniff does not run, so only a file over
`_BINARY_MAX_SIZE` gets a `binary` finding (D13.2)."""
_DUPLICATE_MIN_SIZE = 256

_TEST_DATA_DIRS: frozenset[str] = frozenset({"fixtures", "testdata", "__snapshots__"})
"""Directory names that mark intended test data (D6.12). A `duplicate`
group whose every path has one of these as a path component is not
flagged: repeated fixture trees are a normal test pattern, not slop."""

_MANAGED_DATA_BASENAMES: frozenset[str] = frozenset({".trueup-baseline.json"})
"""Basenames of trueup's own data files (D6.6): `trueup baseline`'s output.
This name must equal `trueup.baseline.BASELINE_FILENAME`; a test checks
that the two stay equal, rather than one module importing the other,
since `trueup.baseline` already imports `trueup.score`, which imports
this module (`ROOT_BUDGET`), and an import the other way would cycle.
Such a file records finding counts, not source text, so the content-
reading rows below (`_duplicate`, `_generated`, `_secret_content`,
`_binary`) must never read or flag it, the same way `report.collect`
keeps a secret file's path out of the document rows (I-23). `_root_budget`
does not count it as a root entry: else the first `trueup baseline` run
in a repo at its budget makes the next `check --baseline` fail."""


def hygiene_findings(
    survey: Survey,
    secret_findings: tuple[Finding, ...] | None = None,
    only: frozenset[str] | None = None,
) -> list[Finding]:
    """Run the nine rows (D5.4, plus the D7.2 lockfile row) over one survey.

    Args:
        survey: The survey to check. `survey.files` is already filtered by
            `trueup.toml`'s `ignore` globs (D5.3), so every row below runs
            only on files the person chose not to ignore.
        secret_findings: `None` runs the built-in `secret-content` row.
            A tuple is the gitleaks result of `trueup.secrets.scan`: it
            takes the place of that row, and the row does not run. The
            `secret-file` row runs in both cases (D7.3 rules 5 and 5a).
        only: The changed set of a scoped run, or `None` for a full run
            (D14.14). A set narrows the `scratch`, `artifact` and
            `duplicate` rows to the paths in `only` and to their content
            twins (`_scope`). The other rows still run in full. A finding
            whose path is in `only` is equal to the full run's finding for
            that path (D6.17); a finding for another path can differ, and
            `report.collect` drops it.

    Returns:
        The findings of every row, unsorted; `report.py` sorts them (I-21).
    """
    attributes = _read_gitattributes(survey.root)
    content_survey = drop_managed_data_files(survey)
    findings: list[Finding] = []
    scope = None if only is None else _scope(survey, only)
    artifact_findings = _artifact(survey, scope)
    artifact_paths = frozenset(finding.path for finding in artifact_findings)
    scratch_findings = _scratch(survey, artifact_paths, scope)
    flagged = frozenset(finding.path for finding in scratch_findings) | artifact_paths
    findings.extend(scratch_findings)
    findings.extend(artifact_findings)
    if scope is None:
        findings.extend(_duplicate(content_survey, flagged))
    elif _holds_duplicate_size(survey.root, scope & only):
        findings.extend(
            _duplicate(
                _narrowed(content_survey, scope),
                flagged,
                reference_files=content_survey.files,
            )
        )
    findings.extend(_generated(content_survey, attributes))
    if secret_findings is None:
        content_findings: tuple[Finding, ...] = tuple(_secret_content(content_survey))
    else:
        content_findings = tuple(secret_findings)
    secret_paths = frozenset(
        finding.path for finding in content_findings if finding.rule == "secret-content"
    )
    findings.extend(_secret_file(survey, secret_paths))
    findings.extend(content_findings)
    findings.extend(_lockfile(survey))
    findings.extend(_binary(content_survey, attributes))
    findings.extend(_root_budget(content_survey))
    return findings


def _scope(survey: Survey, only: frozenset[str]) -> frozenset[str]:
    """Give the paths the `scratch`, `artifact` and `duplicate` rows check in a scoped run (D14.14).

    A finding for a path in `only` can depend on a file outside `only`
    with the same content: the `duplicate` row picks its kept original
    from the whole group, and the `scratch` row writes "copy of" evidence
    and the I-35 last-copy rule from the whole group. So the scope holds
    each full content group that has a path in `only` (D6.17).

    The hash pass runs only when `only` holds a scratch-looking path or a
    file of `_DUPLICATE_MIN_SIZE` bytes or more. Else no group can change
    a finding for a path in `only`, and the scope is `only` itself.

    Args:
        survey: The survey of the run.
        only: The changed set of the scoped run.

    Returns:
        The surveyed paths in `only`, plus every other member of a content
        group that holds one of them.
    """
    changed = frozenset(path for path in survey.files if path in only)
    cfg = config_mod.load(survey.root)
    if not any(scratch_looking(path, cfg) for path in changed) and not (
        _holds_duplicate_size(survey.root, changed)
    ):
        return changed
    scope = set(changed)
    for members in _content_groups(survey, min_size=0).values():
        if any(member in changed for member in members):
            scope.update(members)
    return frozenset(scope)


def _holds_duplicate_size(root: Path, paths: frozenset[str]) -> bool:
    """Say whether one of `paths` is large enough to join a `duplicate` group (D14.14).

    Args:
        root: The repository root.
        paths: Repo-relative paths. A path that is not a readable file
            counts as too small.

    Returns:
        True when one file of `paths` has `_DUPLICATE_MIN_SIZE` bytes or more.
    """
    for path in paths:
        try:
            if (root / path).stat().st_size >= _DUPLICATE_MIN_SIZE:
                return True
        except OSError:
            continue
    return False


def _narrowed(survey: Survey, scope: frozenset[str]) -> Survey:
    """Give a copy of `survey` whose `files` hold only the paths in `scope` (D14.14).

    Args:
        survey: The survey to narrow.
        scope: The paths to keep, from `_scope`.

    Returns:
        `survey` with `files` narrowed; every other field is unchanged.
    """
    return replace(survey, files=tuple(path for path in survey.files if path in scope))


def drop_managed_data_files(survey: Survey) -> Survey:
    """Give a copy of `survey` with trueup's own data files taken out (D6.6).

    Args:
        survey: The survey to filter.

    Returns:
        `survey` with `files` narrowed to drop any path whose basename is
        in `_MANAGED_DATA_BASENAMES`, and `root_entries` narrowed to drop
        an entry with such a name; every other field is unchanged.
    """
    return replace(
        survey,
        files=tuple(
            path
            for path in survey.files
            if Path(path).name not in _MANAGED_DATA_BASENAMES
        ),
        root_entries=tuple(
            entry
            for entry in survey.root_entries
            if entry not in _MANAGED_DATA_BASENAMES
        ),
    )


def looks_scratch(basename: str) -> bool:
    """Say whether a basename looks like a scratch file (D5.4, D10.3).

    Args:
        basename: The file's basename.

    Returns:
        True when the basename matches a backup or copy glob of
        `_SCRATCH_GLOBS`; holds a backup word anywhere in its extension
        chain (`_BACKUP_EXTENSIONS`); has a stem (the text before the
        first `.`) that matches `_SCRATCH_WORD` with its last extension in
        `_SCRATCH_WORD_SUFFIXES`; starts with `scratch` or `untitled` then
        a digit or a separator (`_SCRATCH_PREFIX_ANY`), at any extension;
        or is a document (`_COPY_SUFFIX_EXTENSIONS`) whose stem ends in a
        version, draft, copy or backup marker (`_COPY_SUFFIX_STEM`).
        Case-sensitive.
    """
    if any(fnmatch.fnmatchcase(basename, pattern) for pattern in _SCRATCH_GLOBS):
        return True
    if any(suffix in _BACKUP_EXTENSIONS for suffix in Path(basename).suffixes):
        return True
    stem, dot, rest = basename.partition(".")
    suffix = "." + rest.rsplit(".", 1)[-1] if dot else ""
    if _SCRATCH_WORD.fullmatch(stem) is not None and suffix in _SCRATCH_WORD_SUFFIXES:
        return True
    if _SCRATCH_PREFIX_ANY.fullmatch(stem) is not None:
        return True
    if (
        _SCRATCH_WHOLE_STEM.fullmatch(stem) is not None
        and suffix in _SCRATCH_WORD_SUFFIXES
    ):
        return True
    return (
        suffix in _COPY_SUFFIX_EXTENSIONS and _COPY_SUFFIX_STEM.search(stem) is not None
    )


def looks_scratch_path(path: str, docs_dir: str = "docs") -> bool:
    """Say whether a repo path looks like scratch, by name or by directory (D10.3).

    `check`'s `scratch` row uses this; the guard hook keeps `looks_scratch`
    alone and never takes the directory rule below (I-guard), since a
    git-ignored local `tmp/` is a common habit and `check` already finds a
    tracked one.

    Under the docs directory, a `-v<n>` or `_v<n>` suffix on a document
    name is a versioned page, not a copy (D14.12 C2). The other copy
    markers still count there.

    Args:
        path: The repo-relative POSIX path.
        docs_dir: The docs directory name (`cfg.layout_docs_dir`).

    Returns:
        True when `looks_scratch` of the basename is True (less the `v<n>`
        marker under `docs_dir`), or the path's first segment is exactly
        `tmp`, `temp` or `scratch` (`_SCRATCH_DIR_NAMES`).
    """
    name = Path(path).name
    parts = Path(path).parts
    if name in _KEEP_BASENAMES:
        return False
    if looks_scratch(name) and not (
        under_docs_dir(path, docs_dir) and versioned_document(name)
    ):
        return True
    return bool(parts) and parts[0] in _SCRATCH_DIR_NAMES


def under_docs_dir(path: str, docs_dir: str) -> bool:
    """Say whether a path sits under a docs directory at any depth (D15.9).

    `check` and the guard hook share this answer for the `-v<n>` exemption.

    Args:
        path: The repo-relative POSIX path.
        docs_dir: The docs directory name (`cfg.layout_docs_dir`).

    Returns:
        True when `docs_dir` is one of the directory segments of `path`.
    """
    return docs_dir in Path(path).parts[:-1]


def scratch_proven(path: str) -> bool:
    """Say whether the name alone proves a path is scratch (D15.9).

    Args:
        path: The repo-relative POSIX path.

    Returns:
        True for a basename that matches `*.bak`, `*.orig`, `*.rej` or
        `*~`, or whose stem before the last suffix is exactly `notes`,
        `tmp`, `temp`, `scratch`, `draft` or `untitled` with optional
        digits, and whose suffix is in `_SCRATCH_WORD_SUFFIXES`.
    """
    name = Path(path).name
    if name in _KEEP_BASENAMES:
        return False
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in _SCRATCH_PROVEN_GLOBS):
        return True
    stem, suffix = posixpath.splitext(name)
    return (
        _SCRATCH_WHOLE_STEM.fullmatch(stem) is not None
        and suffix in _SCRATCH_WORD_SUFFIXES
    )


def versioned_document(name: str) -> bool:
    """Say whether only the `v<n>` copy marker makes a basename scratch (D14.12 C2).

    Args:
        name: The file's basename.

    Returns:
        True when the name is scratch by the copy-suffix rule alone, with a
        `v<n>` marker, and by no other scratch rule.
    """
    stem, dot, rest = name.partition(".")
    suffix = "." + rest.rsplit(".", 1)[-1] if dot else ""
    if suffix not in _COPY_SUFFIX_EXTENSIONS:
        return False
    if _VERSION_SUFFIX_STEM.search(stem) is None:
        return False
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in _SCRATCH_GLOBS):
        return False
    if any(part in _BACKUP_EXTENSIONS for part in Path(name).suffixes):
        return False
    if _SCRATCH_WORD.fullmatch(stem) is not None and suffix in _SCRATCH_WORD_SUFFIXES:
        return False
    return _SCRATCH_PREFIX_ANY.fullmatch(stem) is None


def scratch_exempt(path: str, cfg: config_mod.Config | None) -> bool:
    """Say whether a repo path is exempt from the scratch rule, whatever its name.

    `check` and the guard hook both ask this, so a path one of them lets
    through the other lets through as well.

    Args:
        path: The repo-relative POSIX path.
        cfg: The loaded `trueup.toml`, or `None`.

    Returns:
        True when the path sits under `.scratch/`; has a secret-file name
        (the `secret-file` row owns it, and `apply` must untrack it rather
        than remove it); matches an `ignore` glob; is a root entry that a
        `[root] allow` glob names; or matches a `[scratch] allow` glob by
        its path or by its basename.
    """
    name = Path(path).name
    if Path(path).parts[:1] == (SCRATCH_DIR,) or _is_secret_basename(name):
        return True
    if cfg is None:
        return False
    if matches_ignore(path, cfg.ignore):
        return True
    if "/" not in path and any(
        fnmatch.fnmatchcase(path, pattern) for pattern in cfg.root_allow
    ):
        return True
    allow = cfg.scratch_allow
    return matches_ignore(path, allow) or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in allow
    )


def scratch_looking(path: str, cfg: config_mod.Config | None) -> bool:
    """Say whether a repo path counts as scratch for `check` (D12.11).

    The `scratch` row, the `artifact` row and `layout.locate` all ask this,
    so one answer holds for the three of them.

    Args:
        path: The repo-relative POSIX path.
        cfg: The loaded `trueup.toml`, or `None`.

    Returns:
        True when `looks_scratch_path` holds and `scratch_exempt` does not.
    """
    docs_dir = cfg.layout_docs_dir if cfg is not None else "docs"
    return looks_scratch_path(path, docs_dir) and not scratch_exempt(path, cfg)


def _scratch(
    survey: Survey,
    artifact_paths: frozenset[str] = frozenset(),
    scope: frozenset[str] | None = None,
) -> list[Finding]:
    """The `scratch` row: a scratch-looking path that no other text file references.

    A secret file's content is never opened (I-23), so it is never searched
    for a scratch basename either. A tracked file is an automatic finding,
    which `apply` removes with `git rm`; an untracked one is manual, since
    git holds no copy to restore and `apply` never deletes a file git does
    not track.

    Args:
        survey: The survey to check.
        artifact_paths: The paths (or, for a directory, its path ending in
            `/`) the `artifact` row already flags. A path these cover gets
            no `scratch` finding of its own (D10.2): the `artifact` remedy
            already covers it, so only one remedy remains per path. The
            same set also feeds the I-35 last-copy rule below: a copy that
            row removes is not a safe kept original either.
        scope: `None` checks every surveyed path. A set, from `_scope`,
            checks only the candidates in it (D14.14). The other surveyed
            files stay the same as in a full run: a scratch candidate
            outside `scope` is still not a referencing file, so a finding
            for a path in `scope` equals the full run's finding (D6.17).
            In this case `artifact_paths` covers only `scope`, so the
            candidate set comes from `_is_artifact_path`, which gives the
            same answer path by path.

    Returns:
        One `error` finding per scratch-looking path (`looks_scratch_path`),
        not exempt by `scratch_exempt` and not already flagged by
        `artifact_paths`, that no other surveyed text file `_referenced`s.
        The I-35 last-copy rule and the R4 copy evidence of
        `_apply_copy_evidence` are applied before this returns.
    """
    findings: list[Finding] = []
    cfg = config_mod.load(survey.root)
    if scope is None:
        candidates = [
            path
            for path in survey.files
            if scratch_looking(path, cfg) and not _flags_path(path, artifact_paths)
        ]
        excluded = frozenset(candidates)
    else:
        markers = _artifact_markers(survey.root)
        excluded = frozenset(
            path
            for path in survey.files
            if scratch_looking(path, cfg) and not _is_artifact_path(path, *markers)
        )
        candidates = [
            path for path in survey.files if path in excluded and path in scope
        ]
    if not candidates:
        return findings
    others = [
        path
        for path in survey.files
        if path not in excluded and not _is_secret_basename(Path(path).name)
    ]
    index = _reference_index(survey.root, others)
    tracked = _tracked_paths(survey.root)
    for path in candidates:
        basename = Path(path).name
        if _referenced(path, index):
            continue
        is_tracked = path in tracked
        auto = is_tracked and scratch_proven(path) and not _vendored(path)
        if auto:
            action = f"git rm {path}"
        elif is_tracked:
            action = (
                f"check the file; if it is scratch, `git rm {path}`; "
                "else rename it or add a [scratch] allow glob"
            )
        else:
            action = f"delete {path} by hand, or move it under {SCRATCH_DIR}/"
        findings.append(
            Finding(
                id=f"scratch:{path}",
                rule="scratch",
                category="files",
                severity="error",
                path=path,
                evidence=f"{basename!r} looks like a scratch file"
                + ("" if is_tracked else "; git does not track it"),
                action=action,
                auto=auto,
            )
        )
    group_survey = survey if scope is None else _narrowed(survey, scope)
    return _apply_copy_evidence(group_survey, findings, tracked, artifact_paths)


def _vendored(path: str) -> bool:
    """Say whether a path sits under a vendored-code directory at any depth (D15.9).

    Args:
        path: The repo-relative POSIX path.

    Returns:
        True when a directory segment is in `_VENDOR_SEGMENTS`.
    """
    return bool(_VENDOR_SEGMENTS.intersection(Path(path).parts[:-1]))


def _apply_copy_evidence(
    survey: Survey,
    findings: list[Finding],
    tracked: frozenset[str],
    artifact_paths: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Resolve the I-35 last-copy rule and the R4 copy evidence over one scratch content group (D10.3).

    Args:
        survey: The survey `_scratch` ran over.
        findings: The scratch findings `_scratch` built, one per flagged
            candidate, before this adjustment.
        tracked: The paths git tracks. Only a tracked copy that no
            automatic id removes keeps a content safe (I-35).
        artifact_paths: The paths (or directory paths ending in `/`) the
            `artifact` row already flags. A member one of these covers is
            not a safe kept original: that row removes it with its own
            automatic id, the same as a scratch finding does (I-35).

    Returns:
        `findings`, content group by content group (`_content_groups`,
        at any size): when a kept path (not covered by `scratch` or
        `artifact`) shares a group's content, each scratch finding in the
        group gets "; copy of <original>" appended to its evidence. When
        no kept path of the group is tracked, the first sorted automatic
        scratch finding is replaced by a manual one (`auto=False`), with
        the evidence "the last copy of this content", so an automatic id
        never removes every tracked copy of a content (I-35).
    """
    if not findings:
        return findings
    flagged_paths = {finding.path for finding in findings}
    by_path = {finding.path: finding for finding in findings}
    for members in _content_groups(survey, min_size=0).values():
        in_scratch = sorted(member for member in members if member in flagged_paths)
        if not in_scratch:
            continue
        kept = [
            member
            for member in members
            if member not in flagged_paths and not _flags_path(member, artifact_paths)
        ]
        if kept:
            original = kept[0]
            for path in in_scratch:
                current = by_path[path]
                by_path[path] = replace(
                    current, evidence=f"{current.evidence}; copy of {original}"
                )
        if any(member in tracked for member in kept):
            continue
        removed = [path for path in in_scratch if by_path[path].auto]
        if removed:
            by_path[removed[0]] = replace(
                by_path[removed[0]],
                evidence="the last copy of this content",
                auto=False,
            )
    return [by_path[finding.path] for finding in findings]


def _tracked_paths(root: Path) -> frozenset[str]:
    """List the paths git tracks in the target.

    Args:
        root: The repository root.

    Returns:
        The repo-relative paths `git ls-files -z` gives, split on the `NUL`
        separator so a non-ASCII path comes back whole rather than
        octal-quoted (D10.7).

    Raises:
        trueup.config.ConfigError: git cannot be run there or fails
            (arch: D15.2).
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
        stderr = getattr(exc, "stderr", None) or ""
        lines = stderr.strip().splitlines()
        raise config_mod.ConfigError(
            f"git ls-files failed in {root}: {lines[0] if lines else exc}"
        ) from exc
    return frozenset(line for line in result.stdout.split("\0") if line)


def _reference_index(root: Path, others: list[str]) -> tuple[dict[str, str], str]:
    """Read the referencing files once for every scratch candidate (D14.14).

    Each text is read once, with the `_TEXT_READ_CAP` cap. The texts of one
    directory are joined with a `NUL` character. A repo path holds no
    `NUL`, so a search for a path never matches across two files.

    Args:
        root: The repository root.
        others: The surveyed paths that can reference a candidate.

    Returns:
        The joined text per directory (`posixpath.dirname` of the path,
        `""` for the root), and one corpus that joins all of them with a
        `NUL` character.
    """
    texts: dict[str, list[str]] = defaultdict(list)
    for other in others:
        text = fsread.read_text_capped(root, other, _TEXT_READ_CAP)
        if text is not None:
            texts[posixpath.dirname(other)].append(text)
    by_directory = {directory: "\0".join(parts) for directory, parts in texts.items()}
    return by_directory, "\0".join(by_directory.values())


def _referenced(path: str, index: tuple[dict[str, str], str]) -> bool:
    """Say whether another surveyed text file references `path` (D10.3, D10.12).

    A bare basename mentioned from a different directory no longer
    exempts a file (D10.12): only a mention of `path`'s own path relative
    to the mentioning file F's directory (`relpath(path, dir(F))`, which
    covers a Markdown link and a root `Makefile` line for a root file), or
    a mention of `path`'s full repository path when that path has a `/`
    in it, counts. All files of one directory share the relative form, so
    one search per directory gives the same answer (D14.14).

    Args:
        path: The scratch candidate's repo-relative POSIX path.
        index: The texts of the other surveyed files, from
            `_reference_index`.

    Returns:
        True when one other file's text holds the needed form.
    """
    by_directory, corpus = index
    for directory, text in by_directory.items():
        if posixpath.relpath(path, directory) in text:
            return True
    return "/" in path and path in corpus


def _artifact_markers(root: Path) -> tuple[bool, bool]:
    """Say which root files turn on the `target/`, `dist/` and `build/` rules (D5.4, D10.4).

    Args:
        root: The repository root.

    Returns:
        Whether `Cargo.toml` is at the root, and whether a root file's name
        is in `survey.MANIFEST_NAMES`.
    """
    has_cargo = (root / "Cargo.toml").is_file()
    has_manifest = any((root / name).is_file() for name in MANIFEST_NAMES)
    return has_cargo, has_manifest


def _is_artifact_path(path: str, has_cargo: bool, has_manifest: bool) -> bool:
    """Say whether a full `artifact` run covers one surveyed path (D14.14).

    The answer depends only on the path and the two root markers. So a
    scoped run can find it for a path outside its scope.

    Args:
        path: A surveyed repo-relative POSIX path.
        has_cargo: Whether `Cargo.toml` is at the root.
        has_manifest: Whether a root manifest is present.

    Returns:
        True when the path sits under a build or cache directory, has a
        build-output suffix or is `.DS_Store`.
    """
    if _artifact_directory(Path(path).parts, has_cargo, has_manifest) is not None:
        return True
    return path.endswith(_ARTIFACT_SUFFIXES) or Path(path).name == ".DS_Store"


def _artifact(survey: Survey, scope: frozenset[str] | None = None) -> list[Finding]:
    """The `artifact` row: a tracked build or cache path (D5.4).

    A build or cache directory is one finding for the top-most matching
    directory, whatever it holds, so a committed `node_modules/` gives one
    finding, one `git rm --cached -r` and one `.gitignore` line.

    A tracked `*.md` or `*.markdown` file only counts as a page the
    directory holds when `layout._is_candidate` also accepts it (D10.2,
    D10.4, D12.11): a package `README.md`, `CHANGELOG.md` or `SKILL.md`,
    one under a fixture segment such as `node_modules`, or a scratch-looking
    page does not keep the directory manual.

    Args:
        survey: The survey to check.
        scope: `None` checks every surveyed path. A set, from `_scope`,
            checks only the paths in it (D14.14). A directory finding then
            comes only from a path in `scope`, but its evidence still reads
            every tracked page under it, as in a full run.

    Returns:
        One `error` finding per top-most build or cache directory (id and
        path end in `/`), and one per other file that has a build-output
        suffix or is `.DS_Store`.
    """
    has_cargo, has_manifest = _artifact_markers(survey.root)
    directories: dict[str, str] = {}
    files: dict[str, str] = {}
    for path in survey.files:
        if scope is not None and path not in scope:
            continue
        directory = _artifact_directory(Path(path).parts, has_cargo, has_manifest)
        if directory is not None:
            directories.setdefault(directory[0], directory[1])
        elif path.endswith(_ARTIFACT_SUFFIXES):
            files[path] = f"{path} is build output"
        elif Path(path).name == ".DS_Store":
            files[path] = f"{path} is a macOS Finder file"
    if not directories and not files:
        return []
    tracked = _tracked_paths(survey.root)
    cfg = config_mod.load(survey.root)
    scratch_paths = frozenset(
        path for path in survey.files if scratch_looking(path, cfg)
    )
    pages_held: dict[str, str] = {}
    for path in survey.files:
        if path not in tracked:
            continue
        if not layout_mod._is_candidate(
            path, scratch_paths, code_dirs=layout_mod.code_dirs(cfg)
        ):
            continue
        for directory in directories:
            if path.startswith(directory):
                pages_held.setdefault(directory, path)
                break
    findings: list[Finding] = []
    for directory, reason in directories.items():
        page = pages_held.get(directory)
        if page is not None:
            findings.append(
                Finding(
                    id=f"artifact:{directory}",
                    rule="artifact",
                    category="files",
                    severity="error",
                    path=directory,
                    evidence=f"{directory} {reason}; holds {page}",
                    action=f"git rm --cached -r -- {directory}; add /{directory} to .gitignore",
                    auto=False,
                )
            )
            continue
        findings.append(
            Finding(
                id=f"artifact:{directory}",
                rule="artifact",
                category="files",
                severity="error",
                path=directory,
                evidence=f"{directory} {reason}",
                action=f"git rm --cached -r -- {directory}; add /{directory} to .gitignore",
                auto=True,
            )
        )
    for path, evidence in files.items():
        findings.append(
            Finding(
                id=f"artifact:{path}",
                rule="artifact",
                category="files",
                severity="error",
                path=path,
                evidence=evidence,
                action=f"git rm --cached -- {path}; add it to .gitignore",
                auto=True,
            )
        )
    return findings


def _artifact_directory(
    parts: tuple[str, ...], has_cargo: bool, has_manifest: bool
) -> tuple[str, str] | None:
    """Find the top-most build or cache directory a file sits under.

    Args:
        parts: The file's repo-relative path segments.
        has_cargo: Whether `Cargo.toml` sits at the root.
        has_manifest: Whether a root file's name is in
            `survey.MANIFEST_NAMES` (D10.4).

    Returns:
        The directory as a repo path ending in `/`, with the reason, or
        `None` when the file sits under no such directory.
    """
    if len(parts) > 1 and has_cargo and parts[0] == "target":
        return "target/", "is build output beside Cargo.toml"
    if len(parts) > 1 and has_manifest and parts[0] in ("dist", "build"):
        return f"{parts[0]}/", "is build output beside a package manifest"
    for index, part in enumerate(parts[:-1]):
        if any(fnmatch.fnmatchcase(part, pattern) for pattern in _ARTIFACT_DIR_GLOBS):
            return "/".join(parts[: index + 1]) + "/", "is a build or cache directory"
    return None


def _is_test_data_path(path: str) -> bool:
    """Say whether `path` sits under a fixture, test-data or snapshot directory.

    Args:
        path: A repo-relative POSIX path.

    Returns:
        True when a directory component of `path` is `fixtures`, `testdata`
        or `__snapshots__` (D6.12).
    """
    return bool(_TEST_DATA_DIRS.intersection(Path(path).parts[:-1]))


def _content_groups(
    survey: Survey, min_size: int = _DUPLICATE_MIN_SIZE
) -> dict[str, list[str]]:
    """Group surveyed files by content hash, for the `duplicate` and `scratch` rows (D5.4, D10.3).

    A secret file's content is never opened (I-23), so it never joins a
    group; its `secret-file` finding already covers it. A file under
    `min_size` is skipped.

    Args:
        survey: The survey to hash.
        min_size: The smallest file size, in bytes, that joins a group.
            The `duplicate` row keeps `_DUPLICATE_MIN_SIZE`; the `scratch`
            last-copy rule uses 0, since I-35 holds at any size.

    Returns:
        Content digest to the sorted paths that share it, for groups of
        two or more only.
    """
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in survey.files:
        if _is_secret_basename(Path(path).name):
            continue
        full = survey.root / path
        try:
            size = full.stat().st_size
        except OSError:
            continue
        if size < min_size:
            continue
        digest = _sha256(survey.root, path)
        if digest is not None:
            by_hash[digest].append(path)
    return {
        digest: sorted(paths) for digest, paths in by_hash.items() if len(paths) >= 2
    }


def _flags_path(path: str, flagged: frozenset[str]) -> bool:
    """Say whether `flagged` already covers `path`, as a file or a directory (D10.3 R4).

    Args:
        path: The repo-relative path to test.
        flagged: Other findings' paths; a directory path ends in `/`.

    Returns:
        True when `path` equals an entry of `flagged`, or sits under a
        directory entry of `flagged`.
    """
    if path in flagged:
        return True
    return any(entry.endswith("/") and path.startswith(entry) for entry in flagged)


def _duplicate(
    survey: Survey,
    flagged: frozenset[str] = frozenset(),
    reference_files: list[str] | None = None,
) -> list[Finding]:
    """The `duplicate` row: files with the same content as another file (D5.4, D10.3 R4).

    A group whose every path is under a fixture, test-data or snapshot
    directory gives no finding: it is intended test data, not slop
    (D6.12). A path the `scratch` or `artifact` row already flags is
    dropped before the original is picked (R4): that row already removes
    the file with its own automatic id, so a `duplicate` finding for the
    same path would only repeat the work. A file under
    `_DUPLICATE_MIN_SIZE` bytes joins no group, and a group whose every
    remaining member is named by other tracked text gives no finding
    (D15.12).

    Args:
        survey: The survey to check.
        flagged: The paths the `scratch` and `artifact` rows already flag,
            from `hygiene_findings`.
        reference_files: The paths whose text can name a group member.
            `None` means `survey.files`. A scoped run passes the full
            list, so a finding equals the full run's (D6.17).

    Returns:
        One `warn` finding per path in a duplicate group, after the
        `flagged` paths are dropped, on every path but the first (sorted),
        which is the one kept with no finding.
    """
    findings: list[Finding] = []
    groups: list[list[str]] = []
    for paths in _content_groups(survey).values():
        if all(_is_test_data_path(path) for path in paths):
            continue
        remaining = [path for path in paths if not _flags_path(path, flagged)]
        if len(remaining) >= 2:
            groups.append(remaining)
    if not groups:
        return findings
    members = {path for remaining in groups for path in remaining}
    others = [
        path
        for path in (survey.files if reference_files is None else reference_files)
        if path not in members and not _is_secret_basename(Path(path).name)
    ]
    index = _reference_index(survey.root, others)
    for remaining in groups:
        if all(_referenced(path, index) for path in remaining):
            continue
        original = remaining[0]
        for path in remaining[1:]:
            evidence = f"same content as {original}"
            action = (
                f"keep one of {original} and {path}, or explain why both are needed"
            )
            if _differ_in_one_directory(original, path):
                evidence += "; the paths differ in one directory segment"
                action = (
                    "if these are variants on purpose, add a [[keep]] entry "
                    "with the reason; else keep one"
                )
            findings.append(
                Finding(
                    id=f"duplicate:{path}",
                    rule="duplicate",
                    category="files",
                    severity="warn",
                    path=path,
                    evidence=evidence,
                    action=action,
                    auto=False,
                )
            )
    return findings


def _differ_in_one_directory(first: str, second: str) -> bool:
    """Tell whether two paths differ in exactly one directory segment (D16.6)."""
    left, right = first.split("/"), second.split("/")
    if len(left) != len(right) or left[-1] != right[-1]:
        return False
    return sum(a != b for a, b in zip(left[:-1], right[:-1])) == 1


def _sha256(root: Path, rel: str) -> str | None:
    """Give the SHA-256 hex digest of a tracked file's content (D15.22).

    Args:
        root: The repository root.
        rel: The repo-relative path.

    Returns:
        The digest, or `None` when `fsread.read_capped` refuses the file:
        unreadable, a device, a symlink out of the root, or longer than
        `_BINARY_MAX_SIZE`. Such a file leaves the hash groups.
    """
    data = fsread.read_capped(root, rel, _BINARY_MAX_SIZE)
    return None if data is None else hashlib.sha256(data).hexdigest()


def _generated(survey: Survey, attributes: dict[str, str]) -> list[Finding]:
    """The `generated` row: a generated-file marker with no matching `.gitattributes` line (D5.4).

    Args:
        survey: The survey to check.
        attributes: Path pattern to `.gitattributes` value, from
            `_read_gitattributes`.

    Returns:
        One `warn` finding per generated file not already declared
        `linguist-generated` and not a lockfile.
    """
    findings: list[Finding] = []
    for path in survey.files:
        if Path(path).name in _LOCKFILE_NAMES:
            continue
        if _is_secret_basename(Path(path).name):
            continue  # I-23: a secret file's content is never opened
        if _gitattributes_value(attributes, path, "linguist-generated") == "true":
            continue
        text = fsread.read_text_capped(survey.root, path, _TEXT_READ_CAP)
        if text is None:
            continue
        head = "\n".join(text.splitlines()[:5])
        if _GENERATED_MARKER.search(head) or "@generated" in head:
            findings.append(
                Finding(
                    id=f"generated:{path}",
                    rule="generated",
                    category="files",
                    severity="warn",
                    path=path,
                    evidence=f"{path} carries a generated-file marker",
                    action=f"add '{path} linguist-generated=true' to .gitattributes",
                    auto=True,
                )
            )
    return findings


def _secret_file(
    survey: Survey, secret_paths: frozenset[str] = frozenset()
) -> list[Finding]:
    """The `secret-file` row: a key or environment file, decided by content (I-49).

    Args:
        survey: The survey to check.
        secret_paths: The paths of this run's `secret-content` findings,
            from either engine. An `.env` file in this set is proven.

    Returns:
        One `error` finding per path that `_secret_file_kind` rates
        `"auto"` or `"manual"`. The automatic one carries the untrack and
        rotate action; the manual one asks the owner to check first. Only
        the first 64 bytes of a key-named file are read; no finding holds
        file bytes.
    """
    findings: list[Finding] = []
    for path in survey.files:
        kind = _secret_file_kind(survey.root, path, secret_paths)
        if kind is None:
            continue
        name = Path(path).name
        if kind == "auto":
            action = "untrack the file and add it to .gitignore; rotate the secret, the history still holds it"
        elif _is_env_basename(name):
            action = "check whether the file holds a secret; if it does not, add a [[keep]] entry"
        else:
            action = (
                "check whether the file holds a private key; if it does, untrack "
                "it, add it to .gitignore and rotate the key"
            )
        findings.append(
            Finding(
                id=f"secret-file:{path}",
                rule="secret-file",
                category="security",
                severity="error",
                path=path,
                evidence=f"{name!r} looks like a secret or key file",
                action=action,
                auto=kind == "auto",
            )
        )
    return findings


_PUBLIC_PEM_BANNERS: tuple[bytes, ...] = (
    b"-----BEGIN CERTIFICATE-----",
    b"-----BEGIN X509 CRL-----",
    b"-----BEGIN PUBLIC KEY-----",
    b"-----BEGIN CERTIFICATE REQUEST-----",
)
"""First lines that mark a `.pem` file as public material (D14.12 C4)."""

_PEM_HEAD_BYTES = 64
"""How many bytes `_secret_file_kind` reads from a key-named file (D15.10)."""


_PKCS12_DATA_OID = bytes(
    [0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x07, 0x01]
)
"""The DER bytes of the PKCS#7 data OID that opens a PKCS#12 file (D15.10)."""


def _secret_file_kind(
    root: Path, path: str, secret_paths: frozenset[str]
) -> str | None:
    """Rate a repo file for the `secret-file` row (D15.10, I-49).

    A key-named file is read through `fsread.read_head`, 64 bytes at most.
    The result is `"auto"` when the head, after `lstrip()`, starts with
    `-----BEGIN ` and its first line holds `PRIVATE KEY-----`, or starts
    with byte 0x30 and holds the PKCS#12 data OID. It is `None` when the
    first line is a public PEM banner. Else it is `"manual"`: a
    certificate after a label line, a Keynote `.key`, a DER key, an
    unreadable file. An `.env` file is `"auto"` only when `secret_paths`
    holds it. No byte read here goes into a finding.

    Args:
        root: The repository root.
        path: The repo-relative POSIX path.
        secret_paths: The paths of this run's `secret-content` findings.

    Returns:
        `None` (no row), `"manual"` or `"auto"`.
    """
    name = Path(path).name
    if not _is_secret_basename(name):
        return None
    if _is_env_basename(name):
        return "auto" if path in secret_paths else "manual"
    head = fsread.read_head(root, path, _PEM_HEAD_BYTES)
    if head is None:
        return "manual"
    text = head.lstrip()
    first_line = text.splitlines()[0].strip() if text else b""
    if any(first_line.startswith(banner) for banner in _PUBLIC_PEM_BANNERS):
        return None
    if text.startswith(b"-----BEGIN ") and b"PRIVATE KEY-----" in first_line:
        return "auto"
    if head[:1] == b"\x30" and _PKCS12_DATA_OID in head:
        return "auto"
    return "manual"


def _is_env_basename(name: str) -> bool:
    """Say whether a basename is a secret `.env` file (D15.10).

    Args:
        name: The file's basename.

    Returns:
        True for `.env` or `.env.<x>` without a placeholder suffix.
    """
    return name == ".env" or (
        name.startswith(".env.") and not name.endswith(_ENV_ALLOWED_SUFFIXES)
    )


def _is_secret_basename(name: str) -> bool:
    """Say whether a basename looks like a secret or private-key file.

    Args:
        name: The file's basename.

    Returns:
        True for an `.env`-family name (excluding the allowed placeholder
        suffixes), a `.pem`/`.key`/`.p12`/`.pfx` file, or a private SSH key
        that is not the matching `.pub` file.
    """
    if name == ".env" or (
        name.startswith(".env.") and not name.endswith(_ENV_ALLOWED_SUFFIXES)
    ):
        return True
    if name.endswith(_SECRET_FILE_SUFFIXES):
        return True
    return name in _SECRET_KEY_NAMES


def _secret_content(survey: Survey) -> list[Finding]:
    """The `secret-content` row: a secret pattern inside another text file (D5.4, I-49).

    A key-named file is skipped (the `secret-file` row owns it). An `.env`
    file is scanned like any text file, so its path joins the
    `secret_paths` that rate a `secret-file` row `"auto"` (D15.10).

    The id is `secret-content:<path>:<fp>`, `fp` the
    `findings.line_fingerprint` of the line, so a line that moves keeps its
    id; equal lines in one file add `:2`, `:3` in file order (D15.8).

    Args:
        survey: The survey to check.

    Returns:
        One `error` finding per matching line, with `line` set. The
        evidence names the line number and each pattern that matched on
        it, never the matched text (I-23).
    """
    findings: list[Finding] = []
    for path in survey.files:
        name = Path(path).name
        if _is_secret_basename(name) and not _is_env_basename(name):
            continue
        data = fsread.read_capped(survey.root, path, _TEXT_READ_CAP - 1)
        if data is None:
            continue
        if b"\x00" in data[:_BINARY_SNIFF_SIZE]:
            continue
        findings.extend(_secret_content_lines(path, data.splitlines()))
    return findings


def _secret_content_lines(path: str, lines: list[bytes]) -> list[Finding]:
    """Give the `secret-content` findings of one file, one per line (D15.8).

    Args:
        path: The repo-relative path.
        lines: The lines of the file, as bytes.

    Returns:
        One finding per line that a pattern or a private key block matches,
        in file order.
    """
    names: dict[int, list[str]] = {}
    for name, pattern in _SECRET_CONTENT_PATTERNS:
        for line_number, line in enumerate(lines, start=1):
            if pattern.search(line):
                names.setdefault(line_number, []).append(name)
    for line_number, line in enumerate(lines, start=1):
        if not _PRIVATE_KEY_BANNER.search(line):
            continue
        body_lines = lines[line_number : line_number + _PRIVATE_KEY_BODY_LOOKAHEAD]
        if not any(_BASE64_BODY_LINE.match(body.strip()) for body in body_lines):
            continue
        names.setdefault(line_number, []).append("a private key block")
    numbers = sorted(names)
    ids = number_repeats(
        [
            f"secret-content:{path}:{line_fingerprint(path, lines[number - 1])}"
            for number in numbers
        ]
    )
    return [
        Finding(
            id=finding_id,
            rule="secret-content",
            category="security",
            severity="error",
            path=path,
            evidence=f"{path}:{number} matches {', '.join(names[number])}",
            action="remove the secret, rotate it, and add the file to .gitignore",
            auto=False,
            line=number,
        )
        for finding_id, number in zip(ids, numbers, strict=True)
    ]


def _lockfile(survey: Survey) -> list[Finding]:
    """The `lockfile` row: a manifest with dependencies and no lockfile (arch: D7.2).

    A scoped run (`report.collect`'s `only`) keeps a finding from this row
    only when its manifest is in `only`: the finding's `path` is the
    manifest, never empty, so the generic scope filter at the end of
    `report.collect` applies without help from this function (D6.17).

    Args:
        survey: The survey to check.

    Returns:
        One `error` finding per manifest whose basename is a key of
        `_LOCK_PAIRS`, declares at least one dependency, and has no
        matching lockfile name tracked by git in its own directory or an
        ancestor directory up to the root.
    """
    lock_map = dict(_LOCK_PAIRS)
    tracked_by_dir = _tracked_basenames_by_dir(survey.root)
    findings: list[Finding] = []
    for manifest in survey.files:
        name = Path(manifest).name
        if name not in lock_map:
            continue
        raw = fsread.read_capped(survey.root, manifest, _TEXT_READ_CAP)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                Finding(
                    id=f"manifest-unreadable:{manifest}",
                    rule="manifest-unreadable",
                    category="security",
                    severity="info",
                    path=manifest,
                    evidence=f"{manifest} is not UTF-8, so the lockfile row skips it",
                    action="save the manifest as UTF-8",
                    auto=False,
                )
            )
            continue
        if not _declares_dependencies(name, text):
            continue
        if manifest == ESLINT_PACKAGE_TARGET and _is_managed_manifest(text):
            continue  # D8.3: trueup's own tool manifest, no lockfile to ship
        if _has_lockfile(manifest, lock_map[name], tracked_by_dir):
            continue
        findings.append(
            Finding(
                id=f"lockfile:{manifest}",
                rule="lockfile",
                category="security",
                severity="error",
                path=manifest,
                evidence=f"{manifest} declares dependencies and has no lockfile",
                action=_LOCK_ACTIONS[name],
                auto=False,
            )
        )
    return findings


def _is_managed_manifest(text: str) -> bool:
    """Tell if a manifest is one trueup wrote: a JSON object with `"_managed": "trueup"` (D8.3).

    `managed._mark_json` adds that key to `lint/typescript/package.json`.
    Its packages are the tools of the eslint hook, installed under `lint/`
    with `npm install --prefix lint/typescript`, not dependencies of the
    project, and trueup cannot write their lockfile without the network.
    The key is read here by shape, so this module imports nothing from
    `trueup.managed`, which imports this module. The caller also tests the
    path, so the marker in a project's own manifest exempts nothing.

    Args:
        text: The manifest's text.

    Returns:
        True for a JSON object whose `_managed` key is `"trueup"`.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("_managed") == "trueup"


def _tracked_basenames_by_dir(root: Path) -> dict[str, frozenset[str]]:
    """Group the paths git tracks in `root` by their directory.

    Args:
        root: The repository root.

    Returns:
        Directory (POSIX, `"."` for the root) to the basenames git tracks
        directly in it. A lockfile git does not track is absent from every
        set, so `_has_lockfile` never counts it (D7.2 rule 4).
    """
    grouped: dict[str, set[str]] = defaultdict(set)
    for path in _tracked_paths(root):
        grouped[Path(path).parent.as_posix()].add(Path(path).name)
    return {directory: frozenset(names) for directory, names in grouped.items()}


def _has_lockfile(
    manifest: str,
    lock_names: tuple[str, ...],
    tracked_by_dir: dict[str, frozenset[str]],
) -> bool:
    """Say whether a manifest has a lockfile in its own or an ancestor directory (D7.2 rule 3).

    Args:
        manifest: The manifest's repo-relative path.
        lock_names: The lockfile basenames `_LOCK_PAIRS` gives for this
            manifest's ecosystem.
        tracked_by_dir: Directory to the basenames git tracks directly in
            it, from `_tracked_basenames_by_dir`.

    Returns:
        True when one of `lock_names`, or (for `pyproject.toml`) a name
        `_PYLOCK_RE` matches, sits in the manifest's own directory or an
        ancestor directory up to the root.
    """
    manifest_dir = Path(manifest).parent
    is_pyproject = Path(manifest).name == "pyproject.toml"
    for directory in (manifest_dir, *manifest_dir.parents):
        basenames = tracked_by_dir.get(directory.as_posix(), frozenset())
        if any(name in basenames for name in lock_names):
            return True
        if is_pyproject and any(_PYLOCK_RE.match(name) for name in basenames):
            return True
    return False


def _declares_dependencies(name: str, text: str) -> bool:
    """Say whether a manifest's text declares at least one dependency (D7.2 rule 2).

    A manifest that fails to parse declares dependencies: the row fails
    closed rather than staying silent on a manifest it cannot read.

    Args:
        name: The manifest's basename, a key of `_LOCK_PAIRS`.
        text: The manifest's decoded content.

    Returns:
        True when the manifest's own dependency table (per ecosystem,
        D7.2 rule 2) is non-empty, or the text does not parse.
    """
    if name in ("pyproject.toml", "Pipfile"):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return True
        if name == "Pipfile":
            return bool(data.get("packages")) or bool(data.get("dev-packages"))
        project = data.get("project")
        if isinstance(project, dict) and (
            project.get("dependencies") or project.get("optional-dependencies")
        ):
            return True
        if data.get("dependency-groups"):
            return True
        tool = data.get("tool")
        poetry = tool.get("poetry") if isinstance(tool, dict) else None
        poetry_deps = poetry.get("dependencies") if isinstance(poetry, dict) else None
        if isinstance(poetry_deps, dict) and any(
            key != "python" for key in poetry_deps
        ):
            return True
        return False
    if name == "Cargo.toml":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return True
        for key in ("dependencies", "dev-dependencies", "build-dependencies"):
            if data.get(key):
                return True
        workspace = data.get("workspace")
        return bool(isinstance(workspace, dict) and workspace.get("dependencies"))
    if name in ("package.json", "composer.json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return True
        if not isinstance(data, dict):
            return True
        if name == "package.json":
            keys = (
                "dependencies",
                "devDependencies",
                "optionalDependencies",
                "peerDependencies",
            )
            return any(data.get(key) for key in keys)
        for key in ("require", "require-dev"):
            deps = data.get(key)
            if isinstance(deps, dict) and any(
                k != "php" and not k.startswith("ext-") for k in deps
            ):
                return True
        return False
    # go.mod has no machine-readable table; a `require` directive is enough
    # (D7.2 rule 2). A broken go.mod has no syntax to fail on, so there is
    # no fail-closed case here.
    return bool(re.search(r"(?m)^\s*require\b", text))


def _binary(survey: Survey, attributes: dict[str, str]) -> list[Finding]:
    """The `binary` and `large-text` rows: a big or binary file with no LFS filter (D5.4, D13.2, D15.11).

    A file over 1 MiB, at every tier, has its first 8 KiB read: a NUL byte
    gives `binary`, none gives `large-text` (info, manual). The 100 KiB to
    1 MiB sniff stays at T3. A secret-named file gets neither row; its
    `secret-file` row covers the path and I-49 bars a longer read.

    Args:
        survey: The survey to check.
        attributes: Path pattern to `.gitattributes` value, from
            `_read_gitattributes`.

    Returns:
        One `warn` `binary` finding per file that holds a NUL byte in its
        first 8 KiB and is over 1 MiB (or, at T3, over 100 KiB), and one
        `info` `large-text` finding per file over 1 MiB with no NUL byte
        there. No finding for a file that `.gitattributes` marks
        `filter=lfs`, that a Markdown file of the survey links to by
        relative path, or that a `[binary] allow` glob names by path or
        basename.
    """
    cfg = config_mod.load(survey.root)
    allow = cfg.binary_allow if cfg is not None else ()
    sniff = survey.tier == _BINARY_SNIFF_TIER
    linked: frozenset[str] | None = None
    findings: list[Finding] = []
    for path in survey.files:
        if _gitattributes_value(attributes, path, "filter") == "lfs":
            continue
        if matches_ignore(path, allow) or any(
            fnmatch.fnmatchcase(Path(path).name, pattern) for pattern in allow
        ):
            continue
        if _is_secret_basename(Path(path).name):
            continue
        full = survey.root / path
        try:
            size = full.stat().st_size
        except OSError:
            continue
        oversized = size > _BINARY_MAX_SIZE
        if not oversized and not (sniff and size > _BINARY_SNIFF_MIN_SIZE):
            continue
        head = fsread.read_head(survey.root, path, _BINARY_SNIFF_SIZE)
        if head is None:
            continue
        looks_binary = b"\x00" in head
        if not (oversized or looks_binary):
            continue
        if linked is None:
            linked = _linked_paths(survey)
        if path in linked:
            continue
        if looks_binary:
            findings.append(
                Finding(
                    id=f"binary:{path}",
                    rule="binary",
                    category="files",
                    severity="warn",
                    path=path,
                    evidence=f"{path} is {size} bytes",
                    action="move the file to Git LFS, add it to .gitignore, link it from a page, or add a [binary] allow glob",
                    auto=False,
                )
            )
        else:
            findings.append(
                Finding(
                    id=f"large-text:{path}",
                    rule="large-text",
                    category="files",
                    severity="info",
                    path=path,
                    evidence=f"{path} is {size} bytes of text",
                    action="none needed; add a [binary] allow glob to silence it",
                    auto=False,
                )
            )
    return findings


def _linked_paths(survey: Survey) -> frozenset[str]:
    """Give each repo path that a Markdown file of the survey links to (D13.2).

    Args:
        survey: The survey to read.

    Returns:
        The normalized repo-relative paths of every relative link target
        in a `.md` or `.markdown` file of `survey.files`. A target that
        leaves the root is left out.
    """
    from trueup.ref_check import _md_links  # lazy: only a binary candidate needs it

    linked: set[str] = set()
    for page in survey.files:
        if not page.endswith((".md", ".markdown")):
            continue
        raw_page = fsread.read_capped(survey.root, page, _TEXT_READ_CAP)
        if raw_page is None:
            continue
        text = raw_page.decode("utf-8", errors="replace")
        base = posixpath.dirname(page)
        for _line, _written, _target, part, _fragment in _md_links(text):
            if not part or part.startswith("/"):
                continue
            target = posixpath.normpath(posixpath.join(base, part))
            if not target.startswith("../"):
                linked.add(target)
    return frozenset(linked)


def _root_budget(survey: Survey) -> list[Finding]:
    """The `root-budget` row: more root entries than the tier's budget allows (D5.4).

    Args:
        survey: The survey to check.

    Returns:
        A single, repo-wide `warn` finding when `root_entries` exceeds the
        tier's budget; an empty list otherwise. `[root] allow` widens the
        budget; `Survey` does not carry it, so this row reads
        `trueup.toml` again itself to get it.
    """
    cfg = config_mod.load(survey.root)
    allow = len(cfg.root_allow) if cfg is not None else 0
    budget = ROOT_BUDGET[survey.tier] + allow
    if len(survey.root_entries) <= budget:
        return []
    return [
        Finding(
            id="root-budget:",
            rule="root-budget",
            category="root",
            severity="warn",
            path="",
            evidence=(
                f"{len(survey.root_entries)} root entries, budget {budget} at {survey.tier}"
            ),
            action="relocation is out of scope; move by hand or add to [root] allow",
            auto=False,
        )
    ]


def _read_gitattributes(root: Path) -> dict[str, str]:
    """Read `.gitattributes` into a flat pattern-and-key to value mapping.

    Args:
        root: The repository root.

    Returns:
        `"<pattern> <key>"` to the attribute's value (`"true"` for a bare
        `key`, the text after `=` for `key=value`); empty when the file is
        absent.
    """
    text = fsread.read_text_capped(root, ".gitattributes", _TEXT_READ_CAP)
    if text is None:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        for attribute in parts[1:]:
            if "=" in attribute:
                key, _, value = attribute.partition("=")
            else:
                key, value = attribute, "true"
            values[f"{pattern} {key}"] = value
    return values


def _gitattributes_value(attributes: dict[str, str], path: str, key: str) -> str | None:
    """Look up one `.gitattributes` value for a path, by glob pattern.

    Args:
        attributes: The mapping `_read_gitattributes` built.
        path: The repo-relative path to check.
        key: The attribute name, for example `"linguist-generated"`.

    Returns:
        The value, or `None` when no pattern with this key matches `path`.
    """
    for entry, value in attributes.items():
        pattern, _, entry_key = entry.rpartition(" ")
        if entry_key == key and fnmatch.fnmatchcase(path, pattern):
            return value
    return None
