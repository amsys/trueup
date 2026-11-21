"""The legacy-adoption baseline: keys, the file, the gate, the ratchets (arch: D6.6-D6.8).

`trueup baseline` (the `write` function, wired from `trueup.cli`) runs a
full `collect`, then writes `.trueup-baseline.json`: the plan's finding
counts by `key` and the clean-mode ratchet values of `ratchet_values`. It
is the only code path that writes this file (I-16). `trueup check
--baseline` never writes; it loads the file with `load` and calls
`compare`, whose `Gate` says whether a new finding, a ratchet drop or a
missing report should fail the run. A score rise alone does not (D15.21).
"""

from __future__ import annotations

import ast
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree

from trueup import docrules, fsread
from trueup.config import Config, ConfigError
from trueup.findings import Finding
from trueup.score import compute as score_compute
from trueup.survey import Survey

if TYPE_CHECKING:
    # A `CheckRun` is only a type hint here (`from __future__ import
    # annotations` keeps it unevaluated at import time), so this module
    # never imports `trueup.report` at run time; `report.py` imports this
    # module instead, and `write` below reaches back into `report` with a
    # local import, the same lazy pattern `trueup.cli`'s own handlers use.
    from trueup.report import CheckRun

BASELINE_FILENAME = ".trueup-baseline.json"
"""The one file `trueup baseline` writes, at the target root (D6.6, I-16)."""

_REPORT_READ_CAP = 64 * 1024 * 1024
"""The longest report or baseline file, in bytes, that a run reads (D16.10)."""

_RATCHET_DROP_TOLERANCE = 0.1
"""D6.8: a ratchet value counts as dropped only below `before - 0.1`, so a
rounding difference of one tenth never fails the gate on its own."""


def key(finding: Finding) -> str:
    """Give the baseline key of one finding: the id with its line part dropped (D6.6, D15.8).

    A key stays readable and is never a hash (D5.4). Every finding rule but
    the three below keeps its id as its key untouched.

    Args:
        finding: The finding to key.

    Returns:
        A `secret-content` or `changelog` id, `<rule>:<path>:<fp>[:<n>]`,
        becomes `<rule>:<path>`, by the rule name: the fingerprint can be
        all digits, so the shape of the last segment decides nothing
        (D15.8). `refcheck:<path>:<line>:<kind>[:<tail>][:<n>]`
        becomes `refcheck:<path>:<kind>`. `docrules._refcheck_ids` adds
        `:<tail>` and `:<n>` only while two failures share
        `path:line:kind`, so the key drops them: the count in the baseline
        file holds the number of such failures. Every other id is its own
        key.
    """
    if finding.rule == "refcheck":
        return _refcheck_key(finding.id)
    if finding.rule in ("secret-content", "changelog"):
        return f"{finding.rule}:{finding.path}"
    return finding.id


def _refcheck_key(finding_id: str) -> str:
    """Drop the line number and each disambiguator from one `refcheck` id.

    Args:
        finding_id: A `refcheck` finding's id.

    Returns:
        `finding_id` unchanged when it holds no `path:line:kind` (the bare
        `refcheck:` id of a run that produced no parseable failure line);
        else `refcheck:<path>:<kind>`.
    """
    parts = finding_id.split(":")
    if len(parts) <= 2:
        return finding_id
    prefix, path, _line, kind, *_rest = parts
    return ":".join([prefix, path, kind])


def ratchet_values(survey: Survey, cfg: Config | None) -> dict[str, dict[str, float]]:
    """Measure the D6.8 clean-mode ratchet values, from file reads only (I-18).

    Args:
        survey: The survey of the target.
        cfg: The loaded `trueup.toml`, or `None` when it is absent (no
            language is then in `clean` mode, so this gives `{}`).

    Returns:
        Language name to `{"docstring": ..., "test": ...}`, one entry per
        language that is both present (`survey.languages[name].present`)
        and set to `"clean"` in `trueup.toml`. A metric with no source to
        read (no coverage report, or a python target with no `.py` file
        outside `tests/`) is left out of that language's mapping, and a
        language with no metric measured is left out entirely.
    """
    languages = cfg.languages if cfg is not None else {}
    values: dict[str, dict[str, float]] = {}
    if _is_clean_and_present(languages, survey, "python"):
        metrics: dict[str, float] = {}
        docstring = _python_docstring_percent(survey)
        if docstring is not None:
            metrics["docstring"] = docstring
        test = _cobertura_percent(survey.root / "coverage.xml")
        if test is not None:
            metrics["test"] = test
        if metrics:
            values["python"] = metrics
    if _is_clean_and_present(languages, survey, "go"):
        test = _go_coverprofile_percent(survey.root / "coverage.out")
        if test is not None:
            values["go"] = {"test": test}
    if _is_clean_and_present(languages, survey, "typescript"):
        test = _lcov_percent(survey.root / "coverage" / "lcov.info")
        if test is not None:
            values["typescript"] = {"test": test}
    if _is_clean_and_present(languages, survey, "rust"):
        test = _lcov_percent(survey.root / "lcov.info")
        if test is not None:
            values["rust"] = {"test": test}
    return values


def _is_clean_and_present(languages: dict[str, str], survey: Survey, name: str) -> bool:
    """Say whether one language is set to `clean` and present in the survey.

    Args:
        languages: `Config.languages`.
        survey: The survey of the target.
        name: The language name.

    Returns:
        True when `languages[name] == "clean"` and `survey.languages[name].present`.
    """
    stat = survey.languages.get(name)
    return languages.get(name) == "clean" and stat is not None and stat.present


def _read(path: Path) -> str | None:
    """Read a report or the baseline file as text, with a bounded read (D16.10).

    The file is an output at a fixed name, not a surveyed file. The cap is
    `_REPORT_READ_CAP`: a large coverage report must not read as absent,
    because the gate fails on a missing report (D6.7).

    Args:
        path: The file to read.

    Returns:
        The decoded text, or `None` when `fsread` refuses the path: an
        absent path, a device, a FIFO, a symlink out of the directory of
        the path, or a file over the cap.
    """
    return fsread.read_text_capped(path.parent, path.name, _REPORT_READ_CAP)


def _python_docstring_percent(survey: Survey) -> float | None:
    """Give the D6.8 python `docstring` ratchet value.

    Args:
        survey: The survey of the target.

    Returns:
        The percent, to 1 decimal, of public modules, classes and
        functions (name not starting `_`) across the surveyed `.py` files
        outside `tests/` that carry a docstring, or `None` when that count
        is zero.
    """
    total = 0
    documented = 0
    for path in survey.files:
        if not path.endswith(".py"):
            continue
        if path == "tests" or path.startswith("tests/") or "/tests/" in path:
            continue
        text = fsread.read_text_capped(survey.root, path, docrules._TEXT_READ_CAP)
        if text is None:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                warnings.simplefilter("ignore", DeprecationWarning)
                tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        module_name = Path(path).stem
        if not module_name.startswith("_"):
            total += 1
            if ast.get_docstring(tree) is not None:
                documented += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                total += 1
                if ast.get_docstring(node) is not None:
                    documented += 1
    if total == 0:
        return None
    return round(documented * 100 / total, 1)


def _cobertura_percent(path: Path) -> float | None:
    """Give the `test` ratchet value from a Cobertura `coverage.xml` (D6.8).

    Args:
        path: The `coverage.xml` path.

    Returns:
        `line-rate` times 100, to 1 decimal, or `None` when the file is
        absent, is not valid XML, or has no `line-rate` attribute.
    """
    text = _read(path)
    if text is None:
        return None
    try:
        root = ElementTree.fromstring(text)  # noqa: S314  # reason: stdlib XML; the coverage report is written by this project's own tool, not untrusted input
    except ElementTree.ParseError:
        return None
    line_rate = root.get("line-rate")
    if line_rate is None:
        return None
    try:
        return round(float(line_rate) * 100, 1)
    except ValueError:
        return None


def _go_coverprofile_percent(path: Path) -> float | None:
    """Give the `test` ratchet value from a Go `coverage.out` coverprofile (D6.8).

    Args:
        path: The `coverage.out` path.

    Returns:
        Covered statements over total statements, times 100, to 1 decimal,
        or `None` when the file is absent or holds no statement line.
    """
    text = _read(path)
    if text is None:
        return None
    total = 0
    covered = 0
    for line in text.splitlines()[1:]:  # the first line is the "mode: ..." header
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            statements = int(fields[1])
            count = int(fields[2])
        except ValueError:
            continue
        total += statements
        if count > 0:
            covered += statements
    if total == 0:
        return None
    return round(covered * 100 / total, 1)


def _lcov_percent(path: Path) -> float | None:
    """Give a `test` ratchet value from an `lcov.info` file (D6.8).

    Used for both typescript (`coverage/lcov.info`) and rust (`lcov.info`
    at the root).

    Args:
        path: The `lcov.info` path.

    Returns:
        The sum of `LH:` values over the sum of `LF:` values, times 100, to
        1 decimal, or `None` when the file is absent or its `LF:` sum is
        zero.
    """
    text = _read(path)
    if text is None:
        return None
    lines_found = 0
    lines_hit = 0
    for line in text.splitlines():
        if line.startswith("LF:"):
            lines_found += int(line[3:].strip() or 0)
        elif line.startswith("LH:"):
            lines_hit += int(line[3:].strip() or 0)
    if lines_found == 0:
        return None
    return round(lines_hit * 100 / lines_found, 1)


def build(run: "CheckRun", ratchet: dict[str, dict[str, float]]) -> dict:
    """Build the baseline data for one full `collect(root)` run (D6.6).

    Args:
        run: A full (`only=None`) `report.collect` result.
        ratchet: The ratchet values of `ratchet_values`.

    Returns:
        `{"version": 1, "score": <int>, "findings": {"<key>": <count>},
        "ratchet": ratchet}`. Only `run.plan` findings are counted: `error`
        and `warn`, not kept (D5.4).
    """
    score = score_compute(run.plan, run.survey, run.cfg)
    counts: dict[str, int] = {}
    for finding in run.plan:
        finding_key = key(finding)
        counts[finding_key] = counts.get(finding_key, 0) + 1
    return {
        "version": 1,
        "score": score.total,
        "findings": counts,
        "ratchet": ratchet,
    }


def render(data: dict) -> str:
    """Render baseline data to the text `.trueup-baseline.json` holds (D6.6).

    Args:
        data: A mapping from `build`.

    Returns:
        The JSON text, keys sorted, indented by 2, ending in one newline
        (D5.4: readable; I-21: the same data always renders the same bytes).
    """
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def load(root: Path) -> dict | None:
    """Load `.trueup-baseline.json` from a target root (D6.6).

    Args:
        root: The target repository root.

    Returns:
        The parsed mapping, or `None` when the file is absent.

    Raises:
        trueup.config.ConfigError: The file is not valid JSON, or has a
            shape that `compare` cannot read (arch: D15.1).
    """
    path = root / BASELINE_FILENAME
    text = _read(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"{BASELINE_FILENAME}: not a trueup baseline: not valid JSON ({exc.msg})"
        ) from exc
    problem = _shape_problem(data)
    if problem is not None:
        raise ConfigError(f"{BASELINE_FILENAME}: not a trueup baseline: {problem}")
    return data


def _is_number(value: object) -> bool:
    """Say whether a JSON value is an int or a float and not a bool.

    Args:
        value: The value.

    Returns:
        True for a number.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _shape_problem(data: object) -> str | None:
    """Name the first way a loaded baseline has the wrong shape (arch: D15.1).

    Args:
        data: The parsed JSON.

    Returns:
        `None` when `findings` is `dict[str, int]`, `score` is an int and
        `ratchet` is `dict[str, dict[str, number]]` (each key may be absent).
        Else one phrase that names the key.
    """
    if not isinstance(data, dict):
        return "the top level is not an object"
    findings = data.get("findings", {})
    if not isinstance(findings, dict) or not all(
        isinstance(count, int) and not isinstance(count, bool)
        for count in findings.values()
    ):
        return "findings is not an object of counts"
    score = data.get("score", 0)
    if not isinstance(score, int) or isinstance(score, bool):
        return "score is not an integer"
    ratchet = data.get("ratchet", {})
    if not isinstance(ratchet, dict) or not all(
        isinstance(metrics, dict) and all(_is_number(v) for v in metrics.values())
        for metrics in ratchet.values()
    ):
        return "ratchet is not an object of objects of numbers"
    return None


def write(root: Path) -> tuple[int, int]:
    """Run `collect(root)` in full and write `.trueup-baseline.json` (D6.6, I-16).

    The secret scan reads the git history (D7.3 rule 6), the same mode as
    `check --baseline`, so the file and the gate count the same keys.

    This is the one function that writes the baseline file; `trueup.cli`'s
    `baseline` subcommand calls it and nothing else. The import of
    `trueup.report` is local to this function: `report.py` imports this
    module at its own top level (for the `check --baseline` gate), so a
    top-level import here the other way would cycle.

    Args:
        root: The target repository root.

    Returns:
        The number of keys written, and the score, for the caller's own
        `baseline: <n> keys, score <s>` line.

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid.
    """
    from trueup import report as report_mod

    run = report_mod.collect(root, history=True)
    ratchet = ratchet_values(run.survey, run.cfg)
    data = build(run, ratchet)
    (root / BASELINE_FILENAME).write_text(render(data), encoding="utf-8")
    return len(data["findings"]), data["score"]


@dataclass(frozen=True)
class Gate:
    """The result of comparing one `collect` run against a baseline (D6.7).

    Attributes:
        new: Finding ids whose key's count rose above the recorded count,
            in id order; a key with no recorded count starts from 0.
        score_before: The `score` field of the loaded baseline.
        score_now: The total score of the current run.
        ratchet_drops: `"<lang>:<metric> <before> -> <now>"` for a ratchet
            value that dropped by more than `_RATCHET_DROP_TOLERANCE`.
        missing_reports: `"<lang>:<metric>"` for a ratchet value the
            baseline recorded that this run could not measure (its report
            is now absent).
        tighten: Keys whose count fell, or that no longer appear at all;
            info only, never a gate failure.
    """

    new: tuple[str, ...]
    score_before: int
    score_now: int
    ratchet_drops: tuple[str, ...]
    missing_reports: tuple[str, ...]
    tighten: tuple[str, ...]


def failed(gate: Gate) -> bool:
    """Say whether a `Gate` fails `check --baseline` (D6.7).

    Args:
        gate: The gate to check.

    Returns:
        True when `gate.new`, `gate.ratchet_drops` or `gate.missing_reports`
        is not empty. The score is information only (D15.21).
    """
    return bool(gate.new or gate.ratchet_drops or gate.missing_reports)


def compare(
    base: dict, run: "CheckRun", ratchet_now: dict[str, dict[str, float]]
) -> Gate:
    """Compare a loaded baseline against one full `collect` run (D6.7).

    Args:
        base: A mapping `load` returned.
        run: A full (`only=None`) `report.collect` result.
        ratchet_now: The current ratchet values, from `ratchet_values`.

    Returns:
        The `Gate` of this comparison.
    """
    score_now = score_compute(run.plan, run.survey, run.cfg).total
    score_before = int(base.get("score", 0))
    recorded: dict[str, int] = base.get("findings", {})

    now_ids_by_key: dict[str, list[str]] = {}
    for finding in run.plan:
        now_ids_by_key.setdefault(key(finding), []).append(finding.id)

    new_ids: list[str] = []
    tighten: list[str] = []
    for finding_key in sorted(set(now_ids_by_key) | set(recorded)):
        ids = sorted(now_ids_by_key.get(finding_key, []))
        before_count = recorded.get(finding_key, 0)
        if len(ids) > before_count:
            new_ids.extend(ids[before_count:])
        elif len(ids) < before_count:
            tighten.append(finding_key)

    ratchet_before: dict[str, dict[str, float]] = base.get("ratchet", {})
    drops: list[str] = []
    missing: list[str] = []
    for lang, metrics in ratchet_before.items():
        now_metrics = ratchet_now.get(lang, {})
        for metric, before_value in metrics.items():
            now_value = now_metrics.get(metric)
            if now_value is None:
                missing.append(f"{lang}:{metric}")
            elif now_value < before_value - _RATCHET_DROP_TOLERANCE:
                drops.append(f"{lang}:{metric} {before_value} -> {now_value}")

    return Gate(
        new=tuple(new_ids),
        score_before=score_before,
        score_now=score_now,
        ratchet_drops=tuple(sorted(drops)),
        missing_reports=tuple(sorted(missing)),
        tighten=tuple(sorted(tighten)),
    )
