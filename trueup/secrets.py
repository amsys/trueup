"""The secret engine: run gitleaks when it is on the path and map its report to findings (D7.3).

`scan` is the one entry point. `report.collect` calls it once per run and
gives the result to `hygiene.hygiene_findings`. When gitleaks is absent,
`scan` returns `None` and the built-in `secret-content` row runs. When
gitleaks fails, `scan` returns an `EngineRun` with the engine `built-in`
and a note, and the built-in row runs too.

trueup reads only the `File`, `StartLine`, `RuleID`, `Commit` and
`Fingerprint` fields of the gitleaks report. It never reads the matched
text, and every gitleaks call has `--redact` (I-23, I-30). For a
working-tree entry it reads the tracked line itself, to give the same
line-fingerprint id as the built-in row (D15.8). The report goes
to a temporary directory outside the target, so the run writes nothing
into the target (I-18). The gitleaks config goes to the same directory:
`scan` renders `managed.render_gitleaks_config` of the effective config
there and passes `--config` (D14.22 item 2). A `lint/gitleaks/gitleaks.toml`
in the target is not read.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trueup import config as config_mod
from trueup import fsread
from trueup import managed
from trueup.config import Config
from trueup.findings import Finding, line_fingerprint, number_repeats
from trueup.survey import Survey

_CONFIG_NAME = "gitleaks.toml"
"""The gitleaks config file name inside the temporary directory (D14.22 item 2)."""

GITLEAKS_TIMEOUT_S = 120
"""The time limit of one gitleaks run, in seconds (D7.3)."""

_REPORT_NAME = "r.json"
"""The report file name inside the temporary directory (D7.3 rule 2)."""

_IGNORE_NAME = ".gitleaksignore"
"""The ignore file gitleaks reads from its working directory (D14.14)."""

_CONTENT_ACTION = "remove the secret, rotate it, and add the file to .gitignore"
"""The action of a working-tree finding: the same text as the built-in row."""

_ENGINE_ACTION = (
    "rerun the check, or fix the gitleaks run; the built-in engine ran instead"
)
"""The action of the `secret-engine` row (D15.20)."""

_LINE_READ_CAP = 16 * 1024 * 1024
"""The largest file, in bytes, that `_content_findings` reads for a line id (D15.22)."""

_HISTORY_ACTION = "rotate the secret; a history rewrite is the owner's decision"
"""The action of a history finding (D7.3 rule 4)."""


@dataclass(frozen=True)
class EngineRun:
    """The result of one secret scan (D7.3).

    Attributes:
        engine: `"gitleaks"` when gitleaks ran and its report was read, else
            `"built-in"`.
        note: An empty string, or one line that tells why gitleaks did not
            give the findings.
        findings: The mapped findings. Empty when `engine` is `"built-in"`.
    """

    engine: str
    note: str
    findings: tuple[Finding, ...]


def scan(
    root: Path,
    survey: Survey,
    history: bool,
    only: frozenset[str] | None = None,
) -> EngineRun | None:
    """Run gitleaks over one target and map its report (D7.3).

    Args:
        root: The target repository root. gitleaks runs with this as its
            working directory. Its effective config (`config.load`, or the
            code defaults when the root has no config) gives the `ignore`
            globs of the rendered gitleaks config.
        survey: The survey of the target. In working-tree mode a report
            entry whose file is not in `survey.files` (ignored or not
            tracked) gives no finding.
        history: `True` scans the git history (`gitleaks git`), for
            `trueup baseline` and `check --baseline`. `False` scans the
            working tree (`gitleaks dir`).
        only: Repo-relative POSIX paths of a scoped run (arch: D14.14).
            When it is not `None` and `history` is `False`, gitleaks scans
            a copy that holds only the paths of `only` that are in
            `survey.files` and are a regular file or a symlink under
            `root`. With no such path, gitleaks does not start and the
            result has the engine `"gitleaks"` and no findings. `history`
            `True` ignores `only`. With `only` `None` and `history`
            `False`, gitleaks scans such a copy of every path of
            `survey.files` (D15.20). A symlink whose resolved target is
            outside `root` is never copied (D15.22).

    Returns:
        `None` when `gitleaks` is not on the path. An `EngineRun` with the
        engine `"built-in"` and a note when gitleaks fails, times out or
        writes a report that is not a JSON list of entries. Else an
        `EngineRun` with the engine `"gitleaks"` and the mapped findings.
    """
    executable = shutil.which("gitleaks")
    if executable is None:
        return None
    cfg = config_mod.load(root) or Config()
    scan_paths: list[str] | None = None
    if not history:
        # D15.20: both shapes scan a copy of the tracked files, so an
        # untracked build tree never costs scan time.
        scope = frozenset(survey.files) if only is None else only
        scan_paths = _scan_paths(root, survey, scope)
        if not scan_paths:
            return EngineRun(engine="gitleaks", note="", findings=())
    with tempfile.TemporaryDirectory(prefix="trueup-gitleaks-") as tmp:
        report_path = Path(tmp) / _REPORT_NAME
        config_path = Path(tmp) / _CONFIG_NAME
        config_path.write_text(managed.render_gitleaks_config(cfg), encoding="utf-8")
        args = _gitleaks_args(executable, config_path, report_path, history)
        run_dir = root
        if scan_paths is not None:
            run_dir = Path(tmp) / "tree"
            try:
                _copy_paths(root, run_dir, scan_paths)
                # gitleaks reads `.gitleaksignore` from its cwd, so a scoped
                # run needs the file to suppress the same findings as a full run.
                ignore = root / _IGNORE_NAME
                if ignore.is_file() and not ignore.is_symlink():
                    shutil.copy2(ignore, run_dir / _IGNORE_NAME)
            except OSError as error:
                return _failed(
                    f"could not copy the changed files: {error.strerror or error}"
                )
        try:
            completed = subprocess.run(
                args,
                cwd=run_dir,
                capture_output=True,
                timeout=GITLEAKS_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failed(f"timeout after {GITLEAKS_TIMEOUT_S} s")
        except OSError as error:
            return _failed(f"could not start: {error.strerror or error}")
        if completed.returncode != 0:
            return _failed(f"exit {completed.returncode}")
        try:
            entries = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _failed("the report is not a JSON list")
    if not isinstance(entries, list):
        return _failed("the report is not a JSON list")
    findings: list[Finding] = []
    tracked = frozenset(survey.files)
    # D15.8: path to line to the rule ids that gitleaks found on that line.
    content: dict[str, dict[int, list[str]]] = {}
    for entry in entries:
        try:
            path, line, rule_id = _entry_fields(entry)
        except ValueError:
            return _failed("a report entry has no File or StartLine")
        if history:
            findings.append(_history_finding(entry, path, line, rule_id))
        elif path in tracked:
            rules = content.setdefault(path, {}).setdefault(line, [])
            if rule_id not in rules:
                rules.append(rule_id)
    findings.extend(_content_findings(root, content))
    findings.sort(key=lambda finding: finding.id)
    return EngineRun(engine="gitleaks", note="", findings=tuple(findings))


def _scan_paths(root: Path, survey: Survey, only: frozenset[str]) -> list[str]:
    """List the changed tracked paths that gitleaks must read (D14.14).

    Args:
        root: The target repository root.
        survey: The survey of the target.
        only: The paths of the scoped run.

    Returns:
        The sorted paths of `only` that are in `survey.files` and that
        `os.lstat` shows as a regular file or a symlink. A symlink whose
        resolved target is outside `root` is left out (D15.22).
    """
    root_resolved = root.resolve()
    tracked = frozenset(survey.files)
    paths: list[str] = []
    for path in sorted(only):
        if path not in tracked:
            continue
        try:
            mode = os.lstat(root / path).st_mode
        except OSError:
            continue
        if stat.S_ISLNK(mode):
            try:
                inside = (root / path).resolve().is_relative_to(root_resolved)
            except (OSError, RuntimeError):
                inside = False
            if inside:
                paths.append(path)
        elif stat.S_ISREG(mode):
            paths.append(path)
    return paths


def _copy_paths(root: Path, dest: Path, paths: list[str]) -> None:
    """Copy files and symlinks from `root` to `dest`, keeping the relative paths (D14.14).

    Args:
        root: The source repository root.
        dest: The directory to fill. It is made when absent.
        paths: Repo-relative POSIX paths; each is a file or a symlink.

    Raises:
        OSError: A copy failed.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for path in paths:
        src = root / path
        dst = dest / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)


def _gitleaks_args(
    executable: str, config_path: Path, report_path: Path, history: bool
) -> list[str]:
    """Build the gitleaks argument list of one run (D7.3 rule 2, D14.22 item 2).

    Args:
        executable: The gitleaks path that `shutil.which` gave.
        config_path: The rendered gitleaks config in the temporary
            directory.
        report_path: The report file in the temporary directory.
        history: `True` for `gitleaks git`, `False` for `gitleaks dir`.

    Returns:
        The argument list. It always holds `--redact` (I-30) and
        `--config <config_path>`.
    """
    args = [
        executable,
        "git" if history else "dir",
        ".",
        "--redact",
        "--no-banner",
        "--exit-code",
        "0",
        "--report-format",
        "json",
        "--report-path",
        str(report_path),
        "--config",
        str(config_path),
    ]
    return args


def _failed(reason: str) -> EngineRun:
    """Give the `EngineRun` of a gitleaks run that gave no usable report (D7.3 rule 3).

    Args:
        reason: Why the run failed, one short phrase.

    Returns:
        An `EngineRun` with the engine `"built-in"`, the note
        `"gitleaks failed: <reason>"` and no findings.
    """
    return EngineRun(engine="built-in", note=f"gitleaks failed: {reason}", findings=())


def _entry_fields(entry: object) -> tuple[str, int, str]:
    """Read the path, the line and the rule of one gitleaks report entry (D7.3 rule 4).

    The function reads only `File`, `StartLine` and `RuleID`. It never
    reads the matched text (I-23).

    Args:
        entry: One parsed entry of the report.

    Returns:
        The POSIX path, the `StartLine` and the rule id
        (`unknown-rule` when the entry names none).

    Raises:
        ValueError: The entry is not a mapping, or has no string `File` or
            no integer `StartLine`.
    """
    if not isinstance(entry, dict):
        raise ValueError("a report entry is not a mapping")
    file_name = entry.get("File")
    line = entry.get("StartLine")
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("a report entry has no File")
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValueError("a report entry has no StartLine")
    path = PurePosixPath(file_name.replace("\\", "/")).as_posix()
    rule_id = str(entry.get("RuleID", "") or "unknown-rule")
    return path, line, rule_id


def _history_finding(entry: dict, path: str, line: int, rule_id: str) -> Finding:
    """Map one history entry to a `secret-history` finding (D7.3 rule 4).

    The function reads only `Commit` and `Fingerprint` beyond the fields
    of `_entry_fields`. It never reads the matched text (I-23).

    Args:
        entry: One parsed entry of a `gitleaks git` report.
        path: The path from `_entry_fields`.
        line: The `StartLine`.
        rule_id: The rule id.

    Returns:
        The finding, id `secret-history:<Fingerprint>`.
    """
    commit = str(entry.get("Commit", "") or "")
    fingerprint = str(
        entry.get("Fingerprint", "") or f"{commit}:{path}:{rule_id}:{line}"
    )
    return Finding(
        id=f"secret-history:{fingerprint}",
        rule="secret-history",
        category="security",
        severity="error",
        path=path,
        evidence=f"{path}:{line} matches {rule_id} in commit {commit[:12]}",
        action=_HISTORY_ACTION,
        auto=False,
        line=line,
    )


def _content_findings(
    root: Path, content: dict[str, dict[int, list[str]]]
) -> list[Finding]:
    """Give one `secret-content` finding per tracked line that gitleaks matched (D15.8).

    The id is `secret-content:<path>:<fp>`, the same
    `findings.line_fingerprint` of the line that the built-in row gives, so
    one line has one id under both engines. A line that cannot be read (a
    read error, a symlink, a line past the end) uses `<rule>:<StartLine>` in
    place of `fp`. Equal ids in one file add `:2`, `:3` in line order.

    Args:
        root: The target repository root.
        content: Path to line to the rule ids found on that line, in
            report order.

    Returns:
        The findings, path by path, in line order. The evidence names the
        line and every rule id, never the matched text (I-23).
    """
    findings: list[Finding] = []
    for path in sorted(content):
        by_line = content[path]
        full = root / path
        lines: list[bytes] | None = None
        if not os.path.islink(full):
            data = fsread.read_capped(root, path, _LINE_READ_CAP)
            lines = None if data is None else data.splitlines()
        numbers = sorted(by_line)
        segments = [
            line_fingerprint(path, lines[number - 1])
            if lines is not None and 1 <= number <= len(lines)
            else f"{by_line[number][0]}:{number}"
            for number in numbers
        ]
        ids = number_repeats(
            [f"secret-content:{path}:{segment}" for segment in segments]
        )
        findings.extend(
            Finding(
                id=finding_id,
                rule="secret-content",
                category="security",
                severity="error",
                path=path,
                evidence=f"{path}:{number} matches {', '.join(by_line[number])}",
                action=_CONTENT_ACTION,
                auto=False,
                line=number,
            )
            for finding_id, number in zip(ids, numbers, strict=True)
        )
    return findings


def engine_failure_finding(note: str) -> Finding:
    """Give the one `secret-engine` finding of a failed gitleaks run (D15.20).

    The built-in `secret-content` row still runs in that case, so the
    finding makes the failure visible and does not hide a secret.

    Args:
        note: The `EngineRun.note` of the failed run.

    Returns:
        An `error` finding with the id `secret-engine:` and an empty path.
    """
    return Finding(
        id="secret-engine:",
        rule="secret-engine",
        category="security",
        severity="error",
        path="",
        evidence=note,
        action=_ENGINE_ACTION,
        auto=False,
    )
