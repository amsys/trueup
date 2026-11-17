"""`trueup apply`: carry out the approved automatic findings of the current plan (arch: D5.6).

`run` checks every requested id against the plan that `report.collect`
builds, and exits 2 before any write when one is unknown, not in the plan,
or not automatic (I-19). It then writes `trueup.toml` first (the `config`
findings, merged with `--mode` and `--set`), and carries out the other ids
in plan order, one handler per rule. With `--all-auto` it runs that pass
again on the new plan, up to `_MAX_PASSES` times, until a pass changes
nothing (I-20). A finding that touches a `protect` glob is manual in the
plan, and the write helpers skip a protected path as well (I-24).

A `move:` id is not a finding: `_validate` checks it against
`run.moves`, the move plan `trueup.layout.locate` built for this run, not
against the plan. `--all-auto` never reads `moves`, so I-34 holds by
structure. An approved move runs `git mv`, then rewrites the relative
Markdown links the move changed (D10.7).

Git runs as `rm`, `rm --cached`, `mv` and read-only commands (`ls-files`,
`grep`, `check-ignore`): never `commit`, `push` or `clean` (D10.1, I-23).
`run_date` in `trueup.toml` changes only when the run changed a file.

With `--plan FILE`, `run` acts on the plan that `check --json` saved in
FILE (D12.1): it compares the saved tree identity with the tree now,
validates the ids against the file, and makes one pass with no
`report.collect` at all (I-40).

A `repin:` id is not a finding either: `_validate` checks it
against `run.repins`, the entries `docrules.repins` built. An approved
repin reads its line again and writes the new pin only when exactly one
link with the target and the old pin is there (arch: D12.6).

Every write stays below the root (I-51): `_safe_target` refuses a path
whose parent resolves outside the root or whose last component is a
symlink, and a write opens with `os.O_NOFOLLOW`. A saved plan row must pass
`findings.auto_row_holds` on the tree now, or it is an unknown id
(D15.27).

`approvable` is the one list of the ids `--ids` accepts: the automatic
plan findings, the `move:` ids, the `repin:` ids and the setup opt-in
(arch: D12.3). With `--from-report FILE`, `run` reads the ticked boxes of
a Markdown report that `check` wrote, compares its tree comment with the
tree now, makes one `report.collect` and one pass (I-40).
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

from trueup import changes
from trueup import config as config_mod
from trueup import docrules, hygiene, layout, managed, ref_check, report
from trueup import survey as survey_mod
from trueup.config import LANGUAGES, Config, ConfigError
from trueup.findings import (
    AutoFacts,
    Finding,
    auto_row_holds,
    sorted_findings,
    touched_paths,
)
from trueup.survey import matches_ignore

_MODES: tuple[str, ...] = ("strict", "clean", "off")
_SET_CHOICES: dict[str, tuple[str, ...] | re.Pattern[str]] = {
    "tier": ("auto", "T0", "T1", "T2", "T3"),
    "docs": ("auto", "full", "readme"),
    "public": ("true", "false"),
    "profile": config_mod.PROFILE_NAME,
}
"""The values `--set` accepts per key: a tuple of the values, or the
pattern a value must match (a profile name, D14.1). They are the values
that `config.load` accepts."""

_CONFIG_FILE_ID = f"config:{managed.CONFIG_PATH}"
"""The id of the `config` row for an absent `trueup.toml` (D14.3)."""

_MAX_PASSES = 5
"""The most passes `--all-auto` makes. A written file can give work to
another row in the next collect, so it runs again until a pass changes
nothing. A pass never moves the tier (I-43)."""

_FORBIDDEN_GIT: frozenset[str] = frozenset({"commit", "push", "clean"})
"""Git subcommands `apply` never runs (I-23)."""

_GITIGNORE_SPECIAL = "\\*?["
"""Characters that a `.gitignore` pattern treats as special, escaped with a backslash."""


class UsageError(Exception):
    """A `--mode` or `--set` value that `apply` cannot use."""


class WriteRefused(RuntimeError):
    """A write to a path that resolves outside the root, or through a symlink (I-51)."""


@dataclass
class _Context:
    """The state one `apply` run shares between its handlers.

    Attributes:
        root: The target root.
        protect: The `protect` globs of the config in force.
        rendered: Managed repo path to rendered text, from the config in force.
        changed: The repo paths this run changed, in order.
    """

    root: Path
    protect: tuple[str, ...]
    rendered: dict[str, str]
    changed: list[str] = field(default_factory=list)


_TREE_CHANGED = "the tree changed since the plan was saved; run trueup check again"
"""The refusal text for a saved plan whose tree differs from the tree now (D12.1)."""

_NO_TREE = (
    "the report has no tree comment; save a full check of a git root "
    "with trueup check --out, then tick its boxes"
)
"""The refusal text for a report that `check --changed` or a non-git root wrote (D12.3)."""

_INSIDE_ROOT = (
    "{path} is inside the root and git does not ignore it, so it changes "
    "the tree; keep it outside the root, or under .scratch/ once "
    "gitignore:.gitignore is applied"
)
"""The refusal text for a plan or report file that itself changes the tree (D12.1)."""

_TREE_COMMENT = re.compile(r"<!-- trueup tree head=(\S*) status=(\S+) -->")
"""The tree comment on line 2 of the Markdown report (arch: D12.3)."""

_TICKED_PREFIXES: tuple[str, ...] = ("- [x] ", "- [X] ")
"""The starts of a ticked box line in a Markdown report (arch: D12.3)."""

_ID_SEPARATORS: tuple[str, ...] = (" — ", " → ")
"""The id of a box line is the text up to the first of these (arch: D12.3)."""

_FINDING_FIELDS: dict[str, type] = {
    "id": str,
    "rule": str,
    "category": str,
    "severity": str,
    "path": str,
    "evidence": str,
    "action": str,
    "auto": bool,
}
"""The keys of one finding in the JSON report, with their types (D12.1)."""

_MOVE_FIELDS: tuple[str, ...] = ("id", "source", "target", "kind", "basis", "evidence")
"""The text keys of one move in the JSON report; `pages` is a list of text (D12.1)."""


@dataclass(frozen=True)
class SavedRun:
    """The parts of a saved `check --json` file that `apply --plan` acts on (arch: D12.1).

    Attributes:
        tree: The tree identity at check time, from `changes.tree_identity`.
        plan: The plan findings, in the saved order.
        findings: Every finding of the saved run.
        moves: The move plan, as `layout.Move` values.
        repins: The re-pin entries, as `docrules.Repin` values (arch: D12.6).
            A file with no `repins` key gives an empty tuple.
    """

    tree: dict[str, str]
    plan: tuple[Finding, ...]
    findings: tuple[Finding, ...]
    moves: tuple[layout.Move, ...]
    repins: tuple[docrules.Repin, ...] = ()


def load_saved_run(path: Path) -> SavedRun:
    """Read one file that `check --json` wrote, for `apply --plan` (arch: D12.1).

    Args:
        path: The plan file.

    Returns:
        The tree identity, the plan, the findings, the moves and the
        re-pin entries of the file.

    Raises:
        trueup.config.ConfigError: The file cannot be read, is not JSON,
            has no `tree` or a `null` one, or holds a bad `plan`,
            `findings`, `moves` or `repins` entry.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as error:
        raise ConfigError(f"cannot read the plan file {path}: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ConfigError(f"the plan file {path} is not JSON") from error
    if not isinstance(data, dict):
        raise ConfigError(f"the plan file {path} is not a trueup check --json file")
    tree = data.get("tree")
    if (
        not isinstance(tree, dict)
        or set(tree) != {"head", "status"}
        or not all(isinstance(value, str) for value in tree.values())
    ):
        raise ConfigError(
            f"the plan file {path} has no tree; run trueup check --json in a git work tree"
        )
    return SavedRun(
        tree=dict(tree),
        plan=tuple(_saved_findings(path, data, "plan")),
        findings=tuple(_saved_findings(path, data, "findings")),
        moves=tuple(_saved_moves(path, data)),
        repins=tuple(_saved_repins(path, data)),
    )


def _saved_findings(path: Path, data: dict[str, object], key: str) -> list[Finding]:
    """Turn the `plan` or `findings` list of a plan file into `Finding` values (D12.1).

    Args:
        path: The plan file, for the error text.
        data: The parsed file.
        key: `"plan"` or `"findings"`.

    Returns:
        One `Finding` per entry, in the saved order.

    Raises:
        trueup.config.ConfigError: The value is not a list, or an entry
            lacks a key or has a value of the wrong type.
    """
    entries = data.get(key)
    if not isinstance(entries, list):
        raise ConfigError(f"the plan file {path} has a bad {key} list")
    found: list[Finding] = []
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(name), kind) for name, kind in _FINDING_FIELDS.items()
        ):
            raise ConfigError(f"the plan file {path} has a bad {key} entry")
        found.append(Finding(**{name: entry[name] for name in _FINDING_FIELDS}))
    return found


def _saved_moves(path: Path, data: dict[str, object]) -> list[layout.Move]:
    """Turn the `moves` list of a plan file into `layout.Move` values (D12.1).

    Args:
        path: The plan file, for the error text.
        data: The parsed file.

    Returns:
        One `Move` per entry, in the saved order, with `pages` as a tuple.

    Raises:
        trueup.config.ConfigError: The value is not a list, or an entry
            lacks a key or has a value of the wrong type.
    """
    entries = data.get("moves")
    if not isinstance(entries, list):
        raise ConfigError(f"the plan file {path} has a bad moves list")
    moves: list[layout.Move] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not all(isinstance(entry.get(name), str) for name in _MOVE_FIELDS)
            or not isinstance(entry.get("pages"), list)
            or not all(isinstance(page, str) for page in entry["pages"])
        ):
            raise ConfigError(f"the plan file {path} has a bad moves entry")
        moves.append(
            layout.Move(
                **{name: entry[name] for name in _MOVE_FIELDS},
                pages=tuple(entry["pages"]),
            )
        )
    return moves


_REPIN_FIELDS: dict[str, type] = {
    "id": str,
    "path": str,
    "line": int,
    "target": str,
    "old_pin": str,
    "new_pin": str,
}
"""The keys of one re-pin entry in the JSON report, with their types (D12.6)."""


def _saved_repins(path: Path, data: dict[str, object]) -> list[docrules.Repin]:
    """Turn the `repins` list of a plan file into `docrules.Repin` values (arch: D12.6).

    Args:
        path: The plan file, for the error text.
        data: The parsed file.

    Returns:
        One `Repin` per entry, in the saved order. An absent key gives an
        empty list.

    Raises:
        trueup.config.ConfigError: The value is not a list, or an entry
            lacks a key or has a value of the wrong type.
    """
    entries = data.get("repins", [])
    if not isinstance(entries, list):
        raise ConfigError(f"the plan file {path} has a bad repins list")
    found: list[docrules.Repin] = []
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(name), kind) and not isinstance(entry.get(name), bool)
            for name, kind in _REPIN_FIELDS.items()
        ):
            raise ConfigError(f"the plan file {path} has a bad repins entry")
        found.append(docrules.Repin(**{name: entry[name] for name in _REPIN_FIELDS}))
    return found


def _saved_check_run(root: Path, saved: SavedRun) -> report.CheckRun:
    """Give a check result made of the saved plan, with no `report.collect` call (D12.1).

    The survey and the config are read again, since the setup opt-in and
    the managed text need them. The tree is equal to the saved one, so
    they are the ones the saved run used.

    Args:
        root: The target root.
        saved: The loaded plan file.

    Returns:
        A `report.CheckRun` whose findings, plan and moves come from the
        file.

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid, or
            the survey holds no file (arch: D15.2).
    """
    cfg = config_mod.load(root)
    survey = hygiene.drop_managed_data_files(survey_mod.run(root))
    if not survey.files:
        raise config_mod.ConfigError(
            f"{root}: no tracked file to check (after [scan] ignore)"
        )
    return report.CheckRun(
        survey=survey,
        cfg=cfg,
        findings=list(saved.findings),
        plan=list(saved.plan),
        moves=list(saved.moves),
        repins=list(saved.repins),
    )


def _setup_cfg(root: Path, cfg: Config | None) -> Config | None:
    """Give the config that the setup rows and the managed render read (arch: D15.6).

    `config.load` gives a config on every target, but the setup rows and
    the `trueup.toml` that `apply` writes describe the adopted target. So
    a target that is not adopted gives them `None`, as `report.collect`
    does.

    Args:
        root: The target root.
        cfg: The effective config of the run.

    Returns:
        `cfg`, or `None` when the target is not adopted.
    """
    return cfg if config_mod.load_layers(root).adopted else None


def _refuse(text: str) -> int:
    """Print one refusal line of `apply --plan` on standard error (D12.1).

    Args:
        text: The reason, without the `trueup: ` prefix.

    Returns:
        2, the exit code of a refusal.
    """
    print(f"trueup: {text}", file=sys.stderr)
    return 2


def _open_saved_run(
    root: Path, plan: Path, mode_args: list[str], set_args: list[str]
) -> report.CheckRun | int:
    """Load a plan file and check it against the tree now, before any write (D12.1).

    Args:
        root: The target root.
        plan: The plan file.
        mode_args: The `--mode` values; any value refuses the run.
        set_args: The `--set` values; any value refuses the run.

    Returns:
        The check result of the saved plan, or 2 after one refusal line.

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid.
    """
    if mode_args or set_args:
        return _refuse(
            "--plan takes no --mode or --set; they change the managed set, "
            "so run trueup check again"
        )
    try:
        saved = load_saved_run(plan)
    except ConfigError as error:
        return _refuse(str(error))
    if saved.tree != changes.tree_identity(root):
        return _refuse(_tree_changed(root, plan))
    opened = _saved_check_run(root, saved)
    failing = _failing_saved_rows(root, opened)
    if failing:
        for finding_id in failing:
            _refuse(
                f"unknown id {finding_id}: the saved row does not hold on the tree now"
            )
        return _refuse("nothing written")
    return opened


def _failing_saved_rows(root: Path, run: report.CheckRun) -> list[str]:
    """Give the id of each saved `auto` plan row that does not hold now (D15.27).

    The check reads the tree with the static predicates of
    `findings.AUTO_RULES`; it collects nothing (I-40). The secret paths are
    the paths of the saved run's `secret-content` findings.

    Args:
        root: The target root.
        run: The check result of the saved plan.

    Returns:
        The failing ids, in plan order.
    """
    rendered = managed.render(
        managed.effective_config(_setup_cfg(root, run.cfg), run.survey), run.survey
    )
    facts = AutoFacts(
        secret_paths=frozenset(
            finding.path for finding in run.findings if finding.rule == "secret-content"
        ),
        rendered=frozenset(rendered),
    )
    return [
        finding.id
        for finding in run.plan
        if finding.auto
        and (finding.rule not in _RULES or not auto_row_holds(root, finding, facts))
    ]


def _read_report(root: Path, path: Path) -> list[str] | int:
    """Read the ticked ids of a Markdown report, after its tree check (arch: D12.3).

    Args:
        root: The target root.
        path: The Markdown report that `check` wrote, with boxes ticked.

    Returns:
        The ticked ids, in file order, or 2 after one refusal line when the
        file cannot be read, or its tree comment is absent or differs from
        the tree now (I-40).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as error:
        return _refuse(f"cannot read the report {path}: {error}")
    lines = text.splitlines()
    match = next(
        (found for found in map(_TREE_COMMENT.fullmatch, lines) if found), None
    )
    if match is None:
        return _refuse(_NO_TREE)
    tree = changes.tree_identity(root)
    if tree != {"head": match.group(1), "status": match.group(2)}:
        return _refuse(_tree_changed(root, path))
    return [_box_id(line) for line in lines if line.startswith(_TICKED_PREFIXES)]


def _tree_changed(root: Path, path: Path) -> str:
    """Give the refusal text for a tree that differs from the saved one (D12.1).

    Args:
        root: The target root.
        path: The plan or report file that holds the saved tree.

    Returns:
        `_INSIDE_ROOT` with the file's repo path when the file is inside
        `root` and git does not ignore it, since the file itself then
        changes the tree; `_TREE_CHANGED` otherwise.
    """
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return _TREE_CHANGED
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        capture_output=True,
        check=False,
    )
    # Exit 1 means "not ignored"; 0 is ignored and 128 is an error.
    if ignored.returncode == 1:
        return _INSIDE_ROOT.format(path=relative)
    return _TREE_CHANGED


def _box_id(line: str) -> str:
    """Give the id of one ticked box line (arch: D12.3).

    A path that holds a separator cuts the id short. The cut id then fails
    validation, so the run refuses and writes nothing.

    Args:
        line: A line that starts with a ticked box.

    Returns:
        The text after the box up to the first ` — ` or ` → `, stripped.
    """
    rest = line[len(_TICKED_PREFIXES[0]) :]
    for separator in _ID_SEPARATORS:
        rest = rest.split(separator, 1)[0]
    return rest.strip()


def approvable(run: report.CheckRun) -> dict[str, object]:
    """Map each id that `--ids` accepts to what it acts on (arch: D12.3).

    The Markdown report puts a box on exactly these ids. `_validate` checks
    the ids of `--ids`, `--plan` and `--from-report` against this map.

    Args:
        run: The check result: from `report.collect`, or from a saved plan.

    Returns:
        Each automatic plan finding id to its `Finding`, each move id to
        its `layout.Move`, each re-pin id to its `docrules.Repin`, and the
        setup id to the setup row when the run holds one.
    """
    allowed: dict[str, object] = {
        finding.id: finding for finding in run.plan if finding.auto
    }
    allowed.update(
        (finding.id, finding)
        for finding in run.findings
        if finding.id == managed.SETUP_ID and finding.auto
    )
    allowed.update((move.id, move) for move in run.moves)
    allowed.update((entry.id, entry) for entry in run.repins)
    return allowed


def run(
    root: Path,
    ids: list[str] | None,
    all_auto: bool,
    mode_args: list[str],
    set_args: list[str],
    today: date | None = None,
    plan: Path | None = None,
    allow_dirty: bool = False,
    from_report: Path | None = None,
) -> int:
    """Validate the requested ids, then carry them out (D5.6).

    Args:
        root: The target root.
        ids: The finding ids to apply, or `None` with `all_auto`. A
            `move:` id is checked against `run.moves`, not the plan, and
            can be mixed with finding ids in one call (D10.7).
        all_auto: Apply every automatic finding of the plan, and repeat on
            the new plan until a pass changes nothing. Never reads
            `moves` (I-34) or `repins` (D12.6).
        mode_args: `--mode` values, each `LANG=MODE[,LANG=MODE...]`.
        set_args: `--set` values, each `KEY=VALUE`.
        today: The date written to `run_date`; the system date when `None`.
        plan: A file that `check --json` wrote (arch: D12.1). The ids are
            then checked against that file, `--all-auto` takes the `auto`
            findings of its plan, and the run makes one pass with no
            `report.collect` (I-40). `None` keeps the flow above.
        allow_dirty: Write also when a path the run touches has
            uncommitted changes (arch: D12.2).
        from_report: A Markdown report that `check` wrote, with boxes
            ticked (arch: D12.3). The ticked ids take the place of `ids`;
            the run makes one `report.collect` and one pass (I-40). It
            takes no `plan`, `ids` or `all_auto`.

    Returns:
        0 when every handler succeeded; 1 when a handler failed (the others
        still ran), also when an approved repin finds its line changed; 2 when an argument or an id failed validation, with no
        file changed. With `plan`, also 2 with no file changed when the
        file is bad, its tree differs from the tree now, or `--mode` or
        `--set` is given. Also 2 with no file changed when the dirty-tree
        refusal applies (arch: D12.2). With `from_report`, also 2 with no
        file changed when the report has no tree comment or its tree
        differs from the tree now (arch: D12.3).

    Raises:
        trueup.config.ConfigError: `trueup.toml` is present and invalid.
    """
    opened: report.CheckRun | int | None = None
    if from_report is not None:
        if plan is not None or ids is not None or all_auto:
            return _refuse("--from-report takes no --plan, --ids or --all-auto")
        ticked = _read_report(root, from_report)
        if isinstance(ticked, int):
            return ticked
        ids = ticked
    if plan is not None:
        opened = _open_saved_run(root, plan, mode_args, set_args)
        if isinstance(opened, int):
            return opened
    try:
        modes = _parse_modes(mode_args)
        settings = _parse_sets(set_args)
    except UsageError as error:
        print(f"trueup apply: {error}")
        return 2
    first = opened if opened is not None else report.collect(root)
    # I-40: a saved plan and a report make one pass and no second collect.
    saved = plan is not None or from_report is not None
    if all_auto:
        # I-34: `--all-auto` never reads `moves`; its selection comes only
        # from `plan`, so a move never runs unless its own id is named.
        selected = [finding for finding in first.plan if finding.auto]
        move_selected: list[layout.Move] = []
        repin_selected: list[docrules.Repin] = []
    else:
        selected, move_selected, repin_selected, errors = _validate(ids or [], first)
        if errors:
            for error in errors:
                print(f"trueup apply: {error}")
            print("trueup apply: nothing written")
            return 2

    unhandled = sorted(
        {finding.rule for finding in selected if finding.rule not in _RULES}
    )
    if unhandled:
        print(
            f"trueup apply: no handler for rule(s) {', '.join(unhandled)}; nothing written"
        )
        return 2

    ctx = _Context(
        root=root, protect=first.cfg.protect if first.cfg else (), rendered={}
    )
    if not allow_dirty:
        config_write = _has_config_id(selected, root) or (
            all_auto and bool(modes or settings)
        )
        touched = _touched(
            selected,
            move_selected,
            repin_selected,
            config_write,
            ctx,
        )
        rendered = managed.render(
            managed.effective_config(_setup_cfg(root, first.cfg), first.survey),
            first.survey,
        )
        conflicts = _dirty_conflicts(touched, changes.dirty_paths(root), rendered, root)
        if conflicts:
            for path in conflicts:
                _refuse(f"{path} has changes that are not committed")
            return _refuse("commit or stash them, or pass --allow-dirty")
    failed = False
    current = first
    for _ in range(_MAX_PASSES if all_auto and not saved else 1):
        changed_before = len(ctx.changed)
        failed = (
            _one_pass(ctx, current, selected, modes, settings, all_auto, saved)
            or failed
        )
        if len(ctx.changed) == changed_before:
            break
        if saved:
            # I-40: one pass on the saved plan or the report; only the
            # config is read again.
            current = replace(current, cfg=config_mod.load(root))
            break
        current = report.collect(root)
        selected = [
            finding
            for finding in current.plan
            if finding.auto and finding.rule in _RULES
        ]

    if repin_selected:
        # D12.6: a repin runs before the moves, while its page is still at
        # the path of the entry.
        ctx.protect = current.cfg.protect if current.cfg else ()
        failed = _apply_repins(ctx, repin_selected) or failed

    if move_selected:
        ctx.protect = current.cfg.protect if current.cfg else ()
        failed = _apply_moves(ctx, move_selected) or failed

    if ctx.changed:
        try:
            _stamp_run_date(ctx, today or date.today())
        except (OSError, WriteRefused, ConfigError) as error:
            print(f"failed run_date: {error}")
            failed = True
    return 1 if failed else 0


def _one_pass(
    ctx: _Context,
    start: report.CheckRun,
    selected: list[Finding],
    modes: dict[str, str],
    settings: dict[str, object],
    all_auto: bool,
    saved: bool = False,
) -> bool:
    """Carry out one pass: `trueup.toml` first, then every other selected finding.

    `trueup.toml` is written when a `config` id was approved, or, with
    `--all-auto`, when `--mode`/`--set` was given (LOW-9): with named
    `--ids` and no `config` id among them, `--mode`/`--set` values are
    dropped rather than writing a file the person never approved.

    Args:
        ctx: The run state.
        start: The check result the selection came from.
        selected: The findings to carry out, in plan order.
        modes: Language to mode, from `--mode`.
        settings: Field name to value, from `--set`.
        all_auto: Take the non-config findings from the plan as it stands
            after `trueup.toml` is written, in place of `selected`. Also
            lets `--mode`/`--set` write `trueup.toml` on their own (LOW-9):
            `--all-auto` already approves every automatic finding, so a
            mode or setting given beside it needs no separate `config` id.
        saved: The selection comes from a saved plan (arch: D12.1). The
            pass then calls no `report.collect`: after `trueup.toml` is
            written it reads only the config again, and it carries out
            `selected`, also with `all_auto` (I-40).

    Returns:
        True when a handler failed.
    """
    ctx.protect = start.cfg.protect if start.cfg else ()
    changed_before = len(ctx.changed)
    if _has_config_id(selected, ctx.root) or (all_auto and (modes or settings)):
        # D14.19: merge into the target layer, so a key the file set stays.
        target = config_mod.load_target(ctx.root)
        new_cfg = _merge(target, _default_modes(selected, modes), settings)
        try:
            _write_file(ctx, managed.CONFIG_PATH, config_mod.render(new_cfg))
        except WriteRefused as error:
            print(f"failed {managed.CONFIG_PATH}: {error}")
            return True
    if len(ctx.changed) == changed_before:
        current = start
    elif saved:
        current = replace(start, cfg=config_mod.load(ctx.root))
    else:
        current = report.collect(ctx.root)
    ctx.protect = current.cfg.protect if current.cfg else ()
    ctx.rendered = managed.render(
        managed.effective_config(_setup_cfg(ctx.root, current.cfg), current.survey),
        current.survey,
    )
    if all_auto and not saved:
        todo = [
            finding
            for finding in current.plan
            if finding.auto and finding.rule in _HANDLERS
        ]
    else:
        todo = [finding for finding in selected if finding.rule in _HANDLERS]
    failed = False
    for finding in todo:
        try:
            _HANDLERS[finding.rule](ctx, finding)
        except (OSError, RuntimeError) as error:
            print(f"failed {finding.id}: {error}")
            failed = True
    return failed


def _has_config_id(findings: list[Finding], root: Path) -> bool:
    """Say whether the selected findings approve a `trueup.toml` write.

    When the target has no `trueup.toml`, only the `config:trueup.toml` id
    approves the write (the setup opt-in adds that id). A
    `config:languages.<lang>` id alone writes nothing: under the user
    default file it would create a target file, and that file stops the
    user default file (D14.3, I-44).

    Args:
        findings: The selected findings.
        root: The target root.

    Returns:
        True when one has rule `config` and `trueup.toml` exists, or when
        one is `config:trueup.toml`.
    """
    if (root / managed.CONFIG_PATH).is_file():
        return any(finding.rule == "config" for finding in findings)
    return any(finding.id == _CONFIG_FILE_ID for finding in findings)


def _default_modes(selected: list[Finding], modes: dict[str, str]) -> dict[str, str]:
    """Add `clean` for each selected `config:languages.<lang>` that `--mode` does not set.

    Args:
        selected: The selected findings.
        modes: Language to mode, from `--mode`.

    Returns:
        `modes` plus the defaults.
    """
    merged = dict(modes)
    prefix = "config:languages."
    for finding in selected:
        if finding.id.startswith(prefix):
            merged.setdefault(finding.id[len(prefix) :], "clean")
    return merged


def _validate(
    ids: list[str], run: report.CheckRun
) -> tuple[list[Finding], list[layout.Move], list[docrules.Repin], list[str]]:
    """Check each requested id against `approvable(run)` (I-19, arch: D12.3).

    Args:
        ids: The requested ids, as given on `--ids` or read from the ticked
            boxes of a report. Blanks are dropped; each id is stripped.
        run: The check result of this `apply` run.

    Returns:
        The selected findings in plan order (with the setup files of the
        setup id), the selected moves in move-plan order, the selected
        re-pin entries in id order, and one error line per id that is not
        approvable, or one line when no id is named.
    """
    allowed = approvable(run)
    wanted = {requested.strip() for requested in ids if requested.strip()}
    errors = [
        _not_approvable(requested, run)
        for requested in sorted(wanted)
        if requested not in allowed
    ]
    if not wanted:
        errors.append("--ids names no id")
    selected = [
        finding
        for finding in run.plan
        if finding.id in wanted and finding.id in allowed
    ]
    if managed.SETUP_ID in wanted and managed.SETUP_ID in allowed:
        setup_selected, setup_errors = _select_setup(run)
        known = {finding.id for finding in selected}
        selected = sorted_findings(
            selected
            + [finding for finding in setup_selected if finding.id not in known]
        )
        errors += setup_errors
    moves = [move for move in run.moves if move.id in wanted]
    repins = [entry for entry in run.repins if entry.id in wanted]
    return selected, moves, repins, errors


def _not_approvable(requested: str, run: report.CheckRun) -> str:
    """Give the error line for one id that `approvable` does not hold (I-19).

    Args:
        requested: The stripped id.
        run: The check result of this `apply` run.

    Returns:
        Why the id is refused: not a move or re-pin of this run, unknown,
        not in the plan, or not automatic.
    """
    if requested.startswith("move:"):
        return f"{requested} is not in the current move plan"
    if requested.startswith("repin:"):
        return f"{requested} is not in the current re-pin plan"
    plan_by_id = {finding.id: finding for finding in run.plan}
    if requested not in plan_by_id:
        if requested in {finding.id for finding in run.findings} and (
            requested != managed.SETUP_ID
        ):
            return f"{requested} is not in the current plan"
        return f"unknown id {requested}"
    return f"{requested} is not automatic"


def _select_setup(run: report.CheckRun) -> tuple[list[Finding], list[str]]:
    """Give the findings that the setup opt-in `setup:trueup.toml` writes (D12.9 step 5).

    Args:
        run: The check result of this `apply` run.

    Returns:
        The automatic `config` and `file-managed` findings of
        `managed.setup_findings(..., offer=False)`, in plan order, and one
        error line when the check result holds no setup row (the tree has
        a `trueup.toml`, or its tier is not T0 or T1, or the tier set is
        empty).
    """
    if managed.SETUP_ID not in {finding.id for finding in run.findings}:
        return [], [f"unknown id {managed.SETUP_ID}"]
    per_file = managed.setup_findings(
        run.survey, _setup_cfg(run.survey.root, run.cfg), offer=False
    )
    selected = [
        finding
        for finding in per_file
        if finding.auto and finding.rule in ("config", "file-managed")
    ]
    return sorted_findings(selected), []


def _parse_modes(mode_args: list[str]) -> dict[str, str]:
    """Parse the `--mode` values.

    Args:
        mode_args: Each `LANG=MODE[,LANG=MODE...]`.

    Returns:
        Language to mode.

    Raises:
        UsageError: A pair is malformed, or names an unknown language or mode.
    """
    modes: dict[str, str] = {}
    for arg in mode_args:
        for pair in arg.split(","):
            language, sep, mode = pair.strip().partition("=")
            if not sep or language not in LANGUAGES or mode not in _MODES:
                raise UsageError(
                    f"--mode {pair!r}: want LANG=MODE, LANG in {LANGUAGES}, MODE in {_MODES}"
                )
            modes[language] = mode
    return modes


def _parse_sets(set_args: list[str]) -> dict[str, object]:
    """Parse the `--set` values: `tier`, `public`, `docs`, `stale_days`, `profile`.

    Args:
        set_args: Each `KEY=VALUE`.

    Returns:
        Config field name to the typed value.

    Raises:
        UsageError: An unknown key, a value that key does not accept, or
            a profile name that resolves to no file.
    """
    settings: dict[str, object] = {}
    for arg in set_args:
        key, sep, value = arg.partition("=")
        if not sep:
            raise UsageError(f"--set {arg!r}: want KEY=VALUE")
        choices = _SET_CHOICES.get(key)
        if isinstance(choices, re.Pattern):
            if not choices.fullmatch(value):
                raise UsageError(
                    f"--set {key}: want lower-case letters, digits and hyphens"
                )
            # D14.3: resolve the name before a write, so the file never
            # names a profile that every later load refuses (D14.1).
            try:
                config_mod.profile_path(value)
            except config_mod.ConfigError as error:
                raise UsageError(f"--set {key}: {error}") from error
            settings[key] = value
        elif choices is not None:
            if value not in choices:
                raise UsageError(f"--set {key}: want one of {choices}")
            settings[key] = (value == "true") if key == "public" else value
        elif key == "stale_days":
            if not value.isdigit() or int(value) <= 0:
                raise UsageError("--set stale_days: want a positive integer")
            settings[key] = int(value)
        else:
            raise UsageError(
                f"--set {key!r}: want tier, public, docs, stale_days or profile"
            )
    return settings


def _merge(
    cfg: Config | None, modes: dict[str, str], settings: dict[str, object]
) -> Config:
    """Merge modes and `--set` values into the target layer (D14.3, D14.19).

    Each `--set` key and `"languages"` join `explicit`, so `render` writes
    them also at the default value: `--set tier=auto` stays in the file,
    and the file always holds the `[languages]` table.

    Args:
        cfg: The target layer to start from, or `None` for the default
            `Config`.
        modes: Language to mode.
        settings: Field name to value, from `--set`. Each name is a
            top-level key, so it is also its dotted name.

    Returns:
        The merged config.
    """
    base = cfg if cfg is not None else Config()
    languages = {**base.languages, **modes}
    explicit = (base.explicit or frozenset()) | {"languages", *settings}
    return replace(base, languages=languages, explicit=explicit, **settings)


def _protected(ctx: _Context, path: str) -> bool:
    """Say whether a path matches a `protect` glob, and say so on standard output.

    Args:
        ctx: The run state.
        path: The repo path.

    Returns:
        True when the path is protected (I-24).
    """
    if matches_ignore(path, ctx.protect):
        print(f"skip {path}: protected")
        return True
    return False


def _safe_target(ctx: _Context, rel: str) -> Path:
    """Give the path of one write, after the checks of I-51 (D15.27).

    Args:
        ctx: The run state.
        rel: The repo path to write.

    Returns:
        `ctx.root / rel`.

    Raises:
        WriteRefused: `os.path.realpath` of the parent is not the root or
            below it, or the last component is a symlink. The message is
            `refused: <rel> resolves outside the repository`.
    """
    full = ctx.root / rel
    root = ctx.root.resolve()
    parent = Path(os.path.realpath(full.parent))
    if (parent != root and root not in parent.parents) or full.is_symlink():
        raise WriteRefused(f"refused: {rel} resolves outside the repository")
    return full


def _write_bytes(full: Path, data: bytes) -> None:
    """Write bytes to one file that opens with `os.O_NOFOLLOW` (I-51).

    Args:
        full: The file, from `_safe_target`.
        data: The bytes to write.

    Raises:
        OSError: The file cannot be opened, for example when it became a
            symlink after the check.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    descriptor = os.open(full, flags, 0o666)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _write_file(ctx: _Context, path: str, content: str) -> None:
    """Write one file when its bytes differ; never a protected path.

    The config cache is cleared after the write (D15.29).

    Args:
        ctx: The run state; `changed` gains the path when it is written.
        path: The repo path.
        content: The text to write, as UTF-8 with no newline translation.

    Raises:
        WriteRefused: The path resolves outside the root (I-51).
    """
    if _protected(ctx, path):
        return
    full = _safe_target(ctx, path)
    data = content.encode("utf-8")
    if full.is_file() and full.read_bytes() == data:
        return
    full.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(full, data)
    config_mod.clear_cache()
    ctx.changed.append(path)
    print(f"wrote {path}")


def _append_lines(ctx: _Context, path: str, lines: list[str]) -> None:
    """Append the lines a file does not already hold, creating it when absent.

    Args:
        ctx: The run state.
        path: The repo path, for example `.gitignore`.
        lines: The lines to add.

    Raises:
        WriteRefused: The path resolves outside the root (I-51).
    """
    full = _safe_target(ctx, path)
    text = full.read_text(encoding="utf-8", errors="replace") if full.is_file() else ""
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if line not in present]
    if not missing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    _write_file(ctx, path, text + "".join(line + "\n" for line in missing))


def _git(ctx: _Context, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one git command in the target, with literal pathspecs.

    Args:
        ctx: The run state.
        args: The git arguments, subcommand first.

    Returns:
        The completed process.

    Raises:
        RuntimeError: The subcommand is `commit`, `push` or `clean` (I-23).
    """
    if args[0] in _FORBIDDEN_GIT:
        raise RuntimeError(f"apply never runs git {args[0]}")
    return subprocess.run(
        ["git", "--literal-pathspecs", *args],
        cwd=ctx.root,
        capture_output=True,
        text=True,
        errors="surrogateescape",  # arch: D12.10
        check=False,
    )


def _tracked(ctx: _Context, path: str) -> bool:
    """Say whether git tracks a path.

    Args:
        ctx: The run state.
        path: The repo path.

    Returns:
        True when `git ls-files --error-unmatch` finds it.
    """
    return _git(ctx, ["ls-files", "--error-unmatch", "--", path]).returncode == 0


def _gitignore_pattern(path: str) -> str:
    """Give the `.gitignore` line that matches exactly one repo path.

    Args:
        path: The repo path.

    Returns:
        `/` and the path, each special glob character and a trailing space
        escaped with a backslash.
    """
    escaped = "".join(
        "\\" + char if char in _GITIGNORE_SPECIAL else char for char in path
    )
    if escaped.endswith(" "):
        escaped = escaped[:-1] + "\\ "
    return "/" + escaped


def _handle_file_managed(ctx: _Context, finding: Finding) -> None:
    """`file-managed`: write the rendered text of the path (D5.6).

    Args:
        ctx: The run state.
        finding: The finding.
    """
    if finding.path not in ctx.rendered:
        print(f"skip {finding.id}: not managed under the config in force")
        return
    _write_file(ctx, finding.path, ctx.rendered[finding.path])


def _handle_untrack(ctx: _Context, finding: Finding) -> None:
    """`artifact` and `secret-file`: untrack the path, keep the working copy, ignore it (D5.6).

    The file's content is never opened (I-23). A path that ends in `/` is a
    directory: it is untracked whole with `git rm --cached -r`, and its one
    `.gitignore` line ends in `/`; when a tracked file under it matches a
    `protect` glob, the directory is skipped (I-24). `git ls-files -z`
    lists those files, so a non-ASCII name is not quoted (D10.7). Before the
    `.gitignore` line is appended, `git check-ignore --no-index -q` checks
    whether a pattern already covers the path; a covered path gets no new
    line (arch: D10.5).

    Args:
        ctx: The run state.
        finding: The finding.

    Raises:
        RuntimeError: `git rm --cached` failed.
    """
    if _protected(ctx, finding.path) or _protected(ctx, ".gitignore"):
        return
    if finding.path.endswith("/") and ctx.protect:
        listed = _git(ctx, ["ls-files", "-z", "--", finding.path]).stdout
        inside = [path for path in listed.split("\0") if path]
        if any(matches_ignore(path, ctx.protect) for path in inside):
            print(f"skip {finding.path}: holds a protected file")
            return
    if _tracked(ctx, finding.path):
        result = _git(ctx, ["rm", "--cached", "-r", "-q", "--", finding.path])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        config_mod.clear_cache()
        ctx.changed.append(finding.path)
        print(f"untracked {finding.path}")
    covered = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", finding.path],
        cwd=ctx.root,
        capture_output=True,
        check=False,
    )
    if covered.returncode == 0:
        return
    _append_lines(ctx, ".gitignore", [_gitignore_pattern(finding.path)])


def _handle_scratch(ctx: _Context, finding: Finding) -> None:
    """`scratch`: remove a tracked file with `git rm` (D5.6).

    `apply` never deletes a file that git does not track, since nothing
    could restore it: such a path is skipped with a line that says so. The
    `scratch` row already makes that finding manual; this check covers a
    file whose tracked state changed after `check` ran.

    Args:
        ctx: The run state.
        finding: The finding.

    Raises:
        RuntimeError: `git rm` failed.
    """
    if _protected(ctx, finding.path):
        return
    if not _tracked(ctx, finding.path):
        print(f"skip {finding.path}: not tracked, delete it by hand")
        return
    result = _git(ctx, ["rm", "-q", "--", finding.path])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    config_mod.clear_cache()
    ctx.changed.append(finding.path)
    print(f"removed {finding.path}")


def _handle_generated(ctx: _Context, finding: Finding) -> None:
    """`generated`: add `<path> linguist-generated=true` to `.gitattributes` (D5.6).

    Args:
        ctx: The run state.
        finding: The finding.

    Raises:
        RuntimeError: The path holds whitespace, which a `.gitattributes`
            line cannot hold unquoted.
    """
    if any(char.isspace() for char in finding.path):
        raise RuntimeError(
            "a path with whitespace needs a hand-written .gitattributes line"
        )
    if _protected(ctx, ".gitattributes"):
        return
    _append_lines(ctx, ".gitattributes", [f"{finding.path} linguist-generated=true"])


def _handle_gitignore(ctx: _Context, finding: Finding) -> None:
    """`gitignore`: append the missing `managed.GITIGNORE_LINES` (D5.6).

    Args:
        ctx: The run state.
        finding: The finding.
    """
    del finding  # the lines to add come from the target, not the finding
    _append_lines(ctx, ".gitignore", managed.missing_gitignore_lines(ctx.root))


_HANDLERS: dict[str, Callable[[_Context, Finding], None]] = {
    "file-managed": _handle_file_managed,
    "artifact": _handle_untrack,
    "secret-file": _handle_untrack,
    "scratch": _handle_scratch,
    "generated": _handle_generated,
    "gitignore": _handle_gitignore,
}
"""Rule to handler. `config` is not here: `_one_pass` writes `trueup.toml` before any handler."""

_RULES: frozenset[str] = frozenset(_HANDLERS) | {"config"}
"""Every rule `apply` can carry out."""


def _move_mapper(move: layout.Move) -> Callable[[str], str]:
    """Give the function that maps an old repo path to its path after one move (D10.7).

    Args:
        move: The approved move.

    Returns:
        A function from a repo-relative POSIX path to the path it has
        after `move` runs: `move.target` for a file move's own source, a
        prefix replace of `move.source` by `move.target` for a directory
        move (covering the directory itself and every path under it), and
        identity for every other path.
    """
    if move.kind == "dir":
        source = move.source.rstrip("/")
        target = move.target.rstrip("/")
        prefix = f"{source}/"

        def mapper(path: str) -> str:
            if path == source:
                return target
            if path.startswith(prefix):
                return f"{target}/{path[len(prefix) :]}"
            return path

        return mapper

    def mapper(path: str) -> str:
        return move.target if path == move.source else path

    return mapper


def _link_destinations(text: str) -> list[tuple[int, int, int, str]]:
    """Give the place of each link destination in F's text, with `ref_check`'s rules (D10.7 step 2).

    The links are the ones `ref_check._md_links` gives, found with the same
    regular expressions, fence rule and code span rule. A code span is
    removed before the match, as `ref_check` does, but the raw position of
    each kept character is recorded. The rewrite can then replace the exact
    destination characters, and never the same words in the link text, a
    reference label, a code span or another link on the line.

    Args:
        text: F's content.

    Returns:
        One `(line index, start, end, destination)` tuple for each link.
        The line index starts at 0, in `text.splitlines()`. `start` and
        `end` are the raw column span of the destination on that line. A
        link with a code span inside its destination is not given.
    """
    places: list[tuple[int, int, int, str]] = []
    for index, line in enumerate(ref_check._md_lines_outside_fences(text)):
        kept: list[int] = []
        last = 0
        for span in ref_check._CODE_SPAN.finditer(line):
            kept.extend(range(last, span.start()))
            last = span.end()
        kept.extend(range(last, len(line)))
        clean = "".join(line[column] for column in kept)
        spans = [found.span(1) for found in ref_check._MD_LINK.finditer(clean)]
        reference = ref_check._MD_REFERENCE.match(clean)
        if reference is not None:
            spans.append(reference.span(1))
        for span_start, span_end in spans:
            target = clean[span_start:span_end]
            destination = ref_check._link_destination(target)
            if not destination:
                continue
            stripped = target.lstrip()
            offset = span_start + len(target) - len(stripped)
            if stripped.startswith("<") and ">" in stripped:
                offset += 1
            raw_start = kept[offset]
            raw_end = kept[offset + len(destination) - 1] + 1
            if raw_end - raw_start != len(destination):
                continue
            places.append((index, raw_start, raw_end, destination))
    return places


def _rewrite_links(
    root: Path,
    old_path: str,
    new_path: str,
    text: str,
    mapper: Callable[[str], str],
) -> tuple[str, list[int]]:
    """Give F's rewritten text for one move, read before `git mv` runs (D10.7 step 2).

    A relative link's destination is resolved against `old_path`'s own
    directory, with `ref_check._md_links`'s parsing rules: no scheme, no
    link that starts with `#` or `/`, and nothing inside a fenced block or
    a code span. Only the destination characters change. The link text, a
    title and the rest of the line stay as they are. When F does not move,
    a link that still resolves to the same file is not changed. When F
    moves, each link takes the canonical form, the relative path from F's
    new directory (I-37); a link that already has that form, with or
    without one leading `./`, is not changed, so `./b.md` stays. A
    trailing `/` and the fragment are kept.

    Args:
        root: The repository root, read before `git mv` runs.
        old_path: F's repo-relative path before the move.
        new_path: F's repo-relative path after the move (`mapper(old_path)`).
        text: F's content, read before the move.
        mapper: The move's path map, from `_move_mapper`.

    Returns:
        The text to write at `new_path` (`text` itself when nothing
        changes), and the 1-based line of each link the move breaks when F
        is not rewritten (I-38). A link whose target did not exist before
        the move is in neither: it was already broken, and a move back
        heals it with no rewrite.
    """
    old_dir = posixpath.dirname(old_path)
    new_dir = posixpath.dirname(new_path) or "."
    edits: dict[int, list[tuple[int, int, str]]] = {}
    for index, start, end, destination in _link_destinations(text):
        if ref_check._SCHEME.match(destination):
            continue
        raw_path, has_fragment, raw_fragment = destination.partition("#")
        path_part = unquote(raw_path)
        if not path_part or path_part.startswith("/"):
            continue
        resolved = posixpath.normpath(posixpath.join(old_dir, path_part))
        if not (root / resolved).exists():
            continue
        mapped = mapper(resolved)
        new_relative = posixpath.relpath(mapped, new_dir)
        if path_part.endswith("/") and not new_relative.endswith("/"):
            new_relative += "/"
        if new_path == old_path:
            if posixpath.normpath(posixpath.join(new_dir, path_part)) == mapped:
                continue
        elif new_relative in (path_part, path_part.removeprefix("./")):
            continue
        new_destination = quote(new_relative, safe="/~!$&'*+,;=@") + (
            f"#{raw_fragment}" if has_fragment else ""
        )
        edits.setdefault(index, []).append((start, end, new_destination))
    if not edits:
        return text, []
    lines = text.splitlines(keepends=True)
    for index, line_edits in edits.items():
        line = lines[index]
        for start, end, new_destination in sorted(line_edits, reverse=True):
            line = line[:start] + new_destination + line[end:]
        lines[index] = line
    return "".join(lines), sorted(index + 1 for index in edits)


def _print_code_mentions(ctx: _Context, source: str) -> None:
    """Print each non-Markdown tracked file that still holds the move's old path (D10.7 step 4).

    The file is not changed. A directory move's source ends in `/`, so a
    bare name such as `misc` in code is not a mention. `git grep` runs with
    `core.quotePath=false`, so a non-ASCII Markdown path is given as
    written and is skipped (D10.6).

    Args:
        ctx: The run state.
        source: The move's old path, as `Move.source` gives it: a
            directory ends in `/`.
    """
    # `_git` puts `--literal-pathspecs` first and takes no `-c` option;
    # `grep` is never a forbidden subcommand, so the guard is not needed.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "grep", "-n", "-F", "--", source],
        cwd=ctx.root,
        capture_output=True,
        text=True,
        errors="surrogateescape",  # arch: D12.10
        check=False,
    )
    if result.returncode not in (0, 1):
        return
    for line in result.stdout.splitlines():
        path, _, rest = line.partition(":")
        if path.endswith((".md", ".markdown")):
            continue
        number = rest.partition(":")[0]
        print(f"code mentions {source}: {path}:{number}")


def _move_rewrites(
    ctx: _Context, move: layout.Move, quiet: bool = False
) -> dict[str, str]:
    """Give the Markdown text that one move rewrites, read before `git mv` runs (D10.7).

    Every tracked `*.md` and `*.markdown` file is read. `git ls-files -z`
    lists them, so a non-ASCII name is not quoted (D10.6). The rewrite
    decision for each one sees the pre-move tree (which link target
    existed, and whether the file itself moved). A file that matches
    `protect` is never rewritten; the links the move would have changed are
    printed as left broken instead (I-38). `_touched` calls this function
    too, so the dirty-tree check and the rewrite agree (arch: D12.2).

    The read is bounded (D16.10, I-50). A page that the read refuses, or
    that does not decode, is skipped, unless `_refuse_hidden_page` stops
    the move.

    Args:
        ctx: The run state.
        move: The approved move.
        quiet: Print no `left broken` line, and raise no refusal.

    Returns:
        The new repo path of each rewritten file, and its new text.

    Raises:
        WriteRefused: A page can hold links that the read cannot see, and
            `quiet` is false.
    """
    mapper = _move_mapper(move)
    md_files = [
        path
        for path in _git(ctx, ["ls-files", "-z"]).stdout.split("\0")
        if path.endswith((".md", ".markdown"))
    ]
    new_text: dict[str, str] = {}
    for old_path in md_files:
        text = docrules.read_repo_text(ctx.root, old_path)
        if text is None:
            if not quiet:
                _refuse_hidden_page(ctx, old_path)
            continue
        new_path = mapper(old_path)
        rewritten, breaks = _rewrite_links(ctx.root, old_path, new_path, text, mapper)
        if matches_ignore(old_path, ctx.protect):
            for number in breaks:
                if not quiet:
                    print(f"left broken: {old_path}:{number}")
            continue
        if rewritten != text:
            new_text[new_path] = rewritten
    return new_text


def _refuse_hidden_page(ctx: _Context, rel: str) -> None:
    """Stop a move when an unread page can hold links to it (D16.10, I-50).

    A regular file out of the root, or over the read cap, can hold a link
    that the move changes. The run cannot prove that the move needs no
    rewrite, so it refuses and the tree stays as it is. A device and a FIFO
    hold no links. A page that does not decode stays as it is, as before.

    Args:
        ctx: The run state.
        rel: The repo path of a page that the read refused.

    Raises:
        WriteRefused: The page resolves outside the root, or it is over
            `docrules._TEXT_READ_CAP`.
    """
    full = ctx.root / rel
    if not full.is_file():
        return
    resolved = full.resolve()
    if not resolved.is_relative_to(ctx.root.resolve()):
        raise WriteRefused(f"refused: {rel} resolves outside the repository")
    if resolved.stat().st_size > docrules._TEXT_READ_CAP:
        raise WriteRefused(
            f"refused: {rel} is over the read cap, so the run cannot rewrite "
            "its links; move the file by hand"
        )


def _touched(
    selected: list[Finding],
    moves: list[layout.Move],
    repins: list[docrules.Repin],
    config_write: bool,
    ctx: _Context,
) -> set[str]:
    """Give every repo path that a run would write, move or remove (arch: D12.2).

    Args:
        selected: The findings to carry out.
        moves: The approved moves. A move gives its source, its target and
            every Markdown file whose links it would rewrite. A directory
            source or target ends in `/`.
        repins: The approved re-pin entries; each one gives its `path`.
        config_write: True when the run writes `trueup.toml` (a `config`
            finding, `--mode`, `--set` or the setup opt-in). The run-date
            stamp is no touch.
        ctx: The run state, for the root and the `protect` globs.

    Returns:
        The repo paths. A directory ends in `/`.
    """
    touched: set[str] = set()
    for finding in selected:
        touched.update(touched_paths(finding))
    for move in moves:
        touched.add(move.source)
        touched.add(move.target)
        touched.update(_move_rewrites(ctx, move, quiet=True))
    touched.update(entry.path for entry in repins)
    if config_write:
        touched.add(managed.CONFIG_PATH)
    return touched


def _dirty_conflicts(
    touched: set[str], dirty: frozenset[str], rendered: dict[str, str], root: Path
) -> list[str]:
    """Give the dirty paths that a run must not overwrite (arch: D12.2, I-41).

    A dirty path that `managed.render` also produces, and whose file on
    disk carries the managed header, is trueup's own earlier output. It does
    not count.

    Args:
        touched: The paths from `_touched`; a directory ends in `/`.
        dirty: The paths from `changes.dirty_paths`.
        rendered: Managed repo path to rendered text.
        root: The target root.

    Returns:
        The conflicting dirty paths, sorted.
    """
    conflicts: list[str] = []
    for path in sorted(dirty):
        hit = any(
            path == entry or (entry.endswith("/") and path.startswith(entry))
            for entry in touched
        )
        if not hit:
            continue
        if path in rendered:
            text = docrules.read_repo_text(root, path) or ""
            if managed._is_managed_on_disk(path, text, rendered[path]):
                continue
        conflicts.append(path)
    return conflicts


def _move_one(ctx: _Context, move: layout.Move) -> None:
    """Carry out one approved move: `git mv`, then its link rewrite (D10.7).

    Every tracked `*.md` and `*.markdown` file is read before the move.
    `git ls-files -z` lists them, so a non-ASCII name is not quoted
    (D10.6). The rewrite decision for each one sees the pre-move tree
    (which link target existed, and whether the file itself moved). A
    file that matches `protect` is never rewritten; the links the move
    would have changed are printed as left broken instead (I-38).

    The target must resolve below the root before any directory is made
    (I-51). `git mv -n` cannot check a target whose parent does not exist
    yet, so the parents are made first and removed again when `git mv`
    fails (D15.27). Each rewrite goes through `_safe_target`.

    Args:
        ctx: The run state.
        move: The approved move.

    Raises:
        RuntimeError: `git mv` failed.
        WriteRefused: The target or a rewritten file resolves outside the
            root (I-51).
    """
    source = move.source.rstrip("/")
    target = move.target.rstrip("/")
    new_text = _move_rewrites(ctx, move)
    # I-51: check each rewrite at its path before the move, so a refusal
    # comes before `git mv` changes the tree.
    before = _move_mapper(replace(move, source=move.target, target=move.source))
    for new_path in new_text:
        _safe_target(ctx, before(new_path))

    made = _make_parents(_safe_target(ctx, target).parent)
    result = _git(ctx, ["mv", source, target])
    if result.returncode != 0:
        for directory in reversed(made):
            directory.rmdir()
        raise RuntimeError(result.stderr.strip())
    config_mod.clear_cache()
    ctx.changed.append(target)
    print(f"moved {source} to {target}")

    for new_path, text in new_text.items():
        _write_bytes(_safe_target(ctx, new_path), text.encode("utf-8"))
        if new_path not in ctx.changed:
            ctx.changed.append(new_path)

    _print_code_mentions(ctx, move.source)


def _make_parents(directory: Path) -> list[Path]:
    """Make one directory and its missing parents (D15.27).

    Args:
        directory: The directory to make.

    Returns:
        The directories that this call made, top first.
    """
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    directory.mkdir(parents=True, exist_ok=True)
    return list(reversed(missing))


def _apply_moves(ctx: _Context, moves: list[layout.Move]) -> bool:
    """Carry out each approved `move:` id, in plan order (D10.7).

    Args:
        ctx: The run state.
        moves: The approved moves, already checked against `run.moves`.

    Returns:
        True when a move's `git mv` failed; the other moves still run.
    """
    failed = False
    for move in moves:
        try:
            _move_one(ctx, move)
        except (OSError, RuntimeError) as error:
            print(f"failed {move.id}: {error}")
            failed = True
    return failed


def _repin_one(ctx: _Context, entry: docrules.Repin) -> None:
    """Write the new pin of one approved re-pin entry (arch: D12.6).

    The line is read again. Exactly one link with the entry's target and
    `pin:<old_pin>` must be on it, and the text `pin:<old_pin>` must occur
    once on the line. Only that text changes; the other bytes of the file,
    a byte order mark included, stay as they are.

    Args:
        ctx: The run state.
        entry: The approved entry.

    Raises:
        RuntimeError: The line does not hold the link with the old pin, or
            the file cannot be read as UTF-8.
        WriteRefused: The page resolves outside the root (I-51).
    """
    if _protected(ctx, entry.path):
        return
    full = _safe_target(ctx, entry.path)
    data = full.read_bytes()
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    try:
        text = data[len(bom) :].decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"{entry.path} is not UTF-8") from error
    lines = text.splitlines(keepends=True)
    old = f"pin:{entry.old_pin}"
    if (
        docrules.pinned_links(text, entry.line, entry.target) != [entry.old_pin]
        or entry.line > len(lines)
        or lines[entry.line - 1].count(old) != 1
    ):
        raise RuntimeError(
            f"line {entry.line} no longer holds one link to {entry.target} with {old}"
        )
    lines[entry.line - 1] = lines[entry.line - 1].replace(old, f"pin:{entry.new_pin}")
    _write_bytes(full, bom + "".join(lines).encode("utf-8"))
    config_mod.clear_cache()
    ctx.changed.append(entry.path)
    print(f"re-pinned {entry.path}:{entry.line} to pin:{entry.new_pin}")


def _apply_repins(ctx: _Context, entries: list[docrules.Repin]) -> bool:
    """Carry out each approved `repin:` id, in id order (arch: D12.6).

    Args:
        ctx: The run state.
        entries: The approved entries, already checked against `run.repins`.

    Returns:
        True when an entry failed; the other entries still run.
    """
    failed = False
    for entry in entries:
        try:
            _repin_one(ctx, entry)
        except (OSError, RuntimeError) as error:
            print(f"failed {entry.id}: {error}")
            failed = True
    return failed


_RUN_DATE_LINE = re.compile(
    r"^([ \t]*([\"']?)run_date\2[ \t]*=[ \t]*)"
    r"(\"[^\"]*\"|'[^']*'|[^#\n]*?)([ \t]*(?:#.*)?)$"
)
"""The `run_date` line of `trueup.toml`: the key (indented or quoted too), the value, then a comment or nothing."""

_TABLE_HEADER = re.compile(r"^[ \t]*\[")
"""A line that starts a table: the end of the top-level keys (D15.27)."""


def _stamp_run_date(ctx: _Context, today: date) -> None:
    """Set `run_date` in `trueup.toml` to today, after a run that changed a file (D15.27).

    The stamp edits the text, so comments and text that is not committed
    stay (decision 13). Nothing happens when `trueup.toml` is absent, since
    this run did not approve writing it. A top-level `run_date` line
    changes in place. With no such line, the line `run_date = "<date>"`
    goes in before the first table header and the comment and blank lines
    just above it, or at the end of a file with no table. The line ending
    of the file stays. When a parse of the edited text differs from the
    file in more than `run_date`, the stamp renders the target layer
    instead, so the file stays valid TOML. The stamp is no touch for the
    dirty check (I-41).

    Args:
        ctx: The run state.
        today: The date to write.

    Raises:
        WriteRefused: `trueup.toml` resolves outside the root (I-51).
        trueup.config.ConfigError: The edit fails and the target layer
            does not load.
    """
    full = _safe_target(ctx, managed.CONFIG_PATH)
    if not full.is_file():
        return
    text = full.read_bytes().decode("utf-8")
    stamped = _stamped_text(text, today)
    if not _only_run_date_changed(text, stamped, today):
        cfg = config_mod.load_target(ctx.root)
        if cfg is None:
            return
        stamped = config_mod.render(replace(cfg, run_date=today.isoformat()))
    _write_file(ctx, managed.CONFIG_PATH, stamped)


def _stamped_text(text: str, today: date) -> str:
    """Return the text of `trueup.toml` with the `run_date` line set to today.

    Args:
        text: The file text, with its line endings.
        today: The date to write.

    Returns:
        The text with one `run_date` line changed or inserted.
    """
    lines = text.splitlines(keepends=True)
    ending = next(
        (line[len(line.rstrip("\r\n")) :] for line in lines if line.endswith("\n")),
        "\n",
    )
    header = next(
        (index for index, line in enumerate(lines) if _TABLE_HEADER.match(line)),
        len(lines),
    )
    value = f'"{today.isoformat()}"'
    for index in range(header):
        body = lines[index].rstrip("\r\n")
        found = _RUN_DATE_LINE.match(body)
        if found is not None:
            lines[index] = (
                f"{found.group(1)}{value}{found.group(4)}{lines[index][len(body) :]}"
            )
            return "".join(lines)
    new_line = f"run_date = {value}{ending}"
    if header == len(lines):
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += ending
        lines.append(new_line)
    else:
        at = header
        while at > 0 and (
            not lines[at - 1].strip() or lines[at - 1].lstrip().startswith("#")
        ):
            at -= 1
        lines.insert(at, new_line)
    return "".join(lines)


def _only_run_date_changed(text: str, stamped: str, today: date) -> bool:
    """Tell if the stamped text parses and differs from the file only in `run_date`.

    Args:
        text: The file text.
        stamped: The text after the line edit.
        today: The date the edit wrote.

    Returns:
        True when both texts parse, the stamped `run_date` is today and
        every other key is equal.
    """
    try:
        before = tomllib.loads(text)
        after = tomllib.loads(stamped)
    except tomllib.TOMLDecodeError:
        return False
    before.pop("run_date", None)
    return after.pop("run_date", None) == today.isoformat() and after == before
