"""Acceptance tests S23 (convergence) and S24 (metamorphic) of round 3 (arch: D10.10).

A tidy tree from `tests/fixtures/converge/` becomes a one-commit git
repository. For S23 and S24 it gets a committed `trueup.toml` with
`profile = "house"`, and its plan is empty (D15.38). `SCRAMBLE_OPS` makes the same kind of mess as
`.state/target-rust-scramble.sh` does: pages leave `docs/`, then copies and junk
files come in, in the order `SCRAMBLE_OPS` lists. Each copy and junk file
is junk by its content or by a whole-stem scratch name, so its row is
automatic (D15.9, D15.10). S23 runs the four steps of D10.7 on the
scrambled tree and expects the tidy source back (I-37). S24 runs one
operation at a time and expects a longer plan and a higher score than the
tidy run (I-36); `NEUTRAL_OPS` change neither (D15.21).
"""

from __future__ import annotations

import base64
import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import materialise

from trueup import apply as apply_mod
from trueup import baseline as baseline_mod
from trueup import findings as findings_mod
from trueup import report
from trueup.score import compute

HOUSE_CONFIG = (
    'profile = "house"\n\n[languages]\nrust = "clean"\ntypescript = "clean"\n'
)
"""The committed `trueup.toml` of the S23 and S24 runs (D15.38).

`_tidy` writes it, not the fixture, because `test_saved_plan.py` and
`test_from_report.py` build the same fixture and test the `setup` row of
a target with no `trueup.toml`."""

LAYOUT_OFF_CONFIG = "\n[refs]\nlayout = false\n"
"""The lines that the `layout = false` runs add to the committed `trueup.toml` (D9.4)."""

TRUEUP_WRITES: tuple[str, ...] = (
    "trueup.toml",
    "ref_check.toml",
    ".pre-commit-config.yaml",
    ".gitignore",
    ".editorconfig",
)
"""The root files that `apply` writes, which the S23 comparison leaves out."""

TRUEUP_WRITE_DIRS: tuple[str, ...] = ("lint/", ".github/workflows/")
"""The directories that `apply` writes, which the S23 comparison leaves out."""


def _git(root: Path, *args: str) -> str:
    """Run one git command in a test repository, with a fixed signer.

    Args:
        root: The repository.
        *args: The git arguments after `git`.

    Returns:
        The standard output of the command.
    """
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _commit(root: Path, message: str) -> None:
    """Stage every change in the working tree and commit it.

    Args:
        root: The repository.
        message: The commit message.
    """
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _tidy(tmp_path: Path, layout: bool = True, house: bool = False) -> Path:
    """Build the tidy repository from the `converge` fixture and commit it.

    Args:
        tmp_path: The directory to build the repository in.
        layout: False adds `[refs] layout = false` to the committed
            `trueup.toml`.
        house: True commits `HOUSE_CONFIG` as `trueup.toml`.

    Returns:
        The repository root.
    """
    root = materialise("converge", tmp_path)
    if house:
        (root / "trueup.toml").write_text(HOUSE_CONFIG, encoding="utf-8")
    if not layout:
        with (root / "trueup.toml").open("a", encoding="utf-8") as handle:
            handle.write(LAYOUT_OFF_CONFIG)
    _git(root, "init", "-q")
    _commit(root, "tidy")
    return root


def _write(root: Path, rel: str, data: bytes) -> None:
    """Write one file, and make its parent directories.

    Args:
        root: The repository root.
        rel: The repo-relative POSIX path.
        data: The bytes to write.
    """
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _copy(root: Path, source: str, target: str, force: bool = False) -> None:
    """Copy one tracked file to a new path and commit the copy.

    Args:
        root: The repository root.
        source: The repo-relative path to copy.
        target: The repo-relative path of the copy.
        force: Add the copy with `git add -f`, past a `.gitignore` line.
    """
    _write(root, target, (root / source).read_bytes())
    if force:
        _git(root, "add", "-f", target)
    _commit(root, f"copy {source} to {target}")


def _move(root: Path, pairs: list[tuple[str, str]]) -> None:
    """Move tracked paths with `git mv` and commit the moves as one commit.

    Args:
        root: The repository root.
        pairs: The source and target of each move, repo-relative.
    """
    for source, target in pairs:
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        _git(root, "mv", source, target)
    _commit(root, "move " + ", ".join(source for source, _ in pairs))


def _architecture(root: Path) -> str:
    """Give the current path of the architecture page.

    Args:
        root: The repository root.

    Returns:
        `ARCHITECTURE.md` when an earlier operation moved it to the root,
        else `docs/ARCHITECTURE.md`.
    """
    return (
        "ARCHITECTURE.md"
        if (root / "ARCHITECTURE.md").exists()
        else "docs/ARCHITECTURE.md"
    )


def op_pages_to_root(root: Path) -> None:
    """Move three pages from `docs/` to the root, one with a new name."""
    _move(
        root,
        [
            ("docs/ARCHITECTURE.md", "ARCHITECTURE.md"),
            ("docs/running.md", "HOWTO-run.md"),
            ("docs/IDEAS.md", "IDEAS.md"),
        ],
    )


def op_design_to_misc(root: Path) -> None:
    """Move `docs/design` to `misc/design`, and `docs/glossary.md` beside it.

    `misc/glossary.md` sits next to `misc/design/`, not under it. `a.md`
    links it as `../glossary.md`, a link that still resolves right after
    this move (the file is still there, one level up), to the wrong
    place: the canonical-form rule of D10.7 must still rewrite it, once
    here and once more when `docs/glossary.md` moves back.
    """
    _move(
        root, [("docs/design", "misc/design"), ("docs/glossary.md", "misc/glossary.md")]
    )


def op_traceability_to_out(root: Path) -> None:
    """Move `docs/traceability.md` to `out/traceability.md`."""
    _move(root, [("docs/traceability.md", "out/traceability.md")])


def op_readme_backup(root: Path) -> None:
    """Add `README.md~`, an editor backup copy of `README.md`."""
    _copy(root, "README.md", "README.md~")


def op_architecture_orig(root: Path) -> None:
    """Add `ARCHITECTURE.md.orig`, a merge leftover copy of the architecture page."""
    _copy(root, _architecture(root), "ARCHITECTURE.md.orig")


def op_source_backup(root: Path) -> None:
    """Add `src/fold.rs.bak`, a backup copy of `src/fold.rs`."""
    _copy(root, "src/fold.rs", "src/fold.rs.bak")


def op_dist_bundle(root: Path) -> None:
    """Add `dist/app.bundle.js`, a copy of `ui/app.js`."""
    _copy(root, "ui/app.js", "dist/app.bundle.js", force=True)


def op_notes_junk(root: Path) -> None:
    """Add `notes.txt`; the tidy `src/notes.rs` holds only its bare basename."""
    _write(root, "notes.txt", b"todo: check the fold\n")
    _commit(root, "add notes.txt")


def op_target_junk(root: Path) -> None:
    """Add `target/debug/old`, a binary build output beside `Cargo.toml`."""
    _write(root, "target/debug/old", bytes(range(256)) * 8)
    _git(root, "add", "-f", "target/debug/old")
    _commit(root, "add target/debug/old")


def _private_key_block() -> bytes:
    """Build a private-key block with a base64 body.

    The body is a hash, built at run time, so no key-shaped block is in the
    repository. It is the same in each run, so two scrambled trees hold the
    same bytes.

    Returns:
        The PEM text of the block.
    """
    body = base64.b64encode(hashlib.sha512(b"converge").digest()).decode("ascii")
    banner = "RSA " + "PRIVATE KEY"
    return f"-----BEGIN {banner}-----\n{body}\n-----END {banner}-----\n".encode()


def op_env_file(root: Path) -> None:
    """Add `.env` that holds a private-key block, a secret file by its content."""
    _write(root, ".env", _private_key_block())
    _git(root, "add", "-f", ".env")
    _commit(root, "add .env")


def op_committed_cache(root: Path) -> None:
    """Add 40 `.pyc` files under `src/app/__pycache__/`, past `.gitignore`."""
    for index in range(40):
        rel = f"src/app/__pycache__/mod{index}.cpython-312.pyc"
        _write(root, rel, b"\xcb\x0d\x0d\x0a" + index.to_bytes(4, "little"))
        _git(root, "add", "-f", rel)
    _commit(root, "add src/app/__pycache__")


def op_clean_deletion(root: Path) -> None:
    """Remove four clean files that no page links, with `git rm`."""
    _git(
        root,
        "rm",
        "-q",
        "src/notes.rs",
        "docs/traceability.md",
        "docs/design/fig.png",
        "ui/app.js",
    )
    _commit(root, "remove four clean files")


def op_architecture_draft(root: Path) -> None:
    """Add `ARCHITECTURE_v2_draft.md`, a copy with a compound-stem scratch name."""
    _copy(root, _architecture(root), "ARCHITECTURE_v2_draft.md")


def op_scratch_source(root: Path) -> None:
    """Add `tmp/scratch_fold.rs`, a copy with a compound-stem scratch name."""
    _copy(root, "src/fold.rs", "tmp/scratch_fold.rs")


def op_readme_old(root: Path) -> None:
    """Add `README.old.md`, a copy whose stem is not one scratch word."""
    _copy(root, "README.md", "README.old.md")


def op_env_placeholder(root: Path) -> None:
    """Add `.env` that holds no secret, a secret file by its name only."""
    _write(root, ".env", b"APP_MODE=dev\n")
    _git(root, "add", "-f", ".env")
    _commit(root, "add .env")


SCRAMBLE_OPS: list[Callable[[Path], None]] = [
    op_pages_to_root,
    op_design_to_misc,
    op_traceability_to_out,
    op_readme_backup,
    op_architecture_orig,
    op_source_backup,
    op_dist_bundle,
    op_notes_junk,
    op_target_junk,
    op_env_file,
]
"""The scramble operations, applied in this order: the pages move out of
`docs/`, then the four copies, then the three junk files. Each one
commits. The content or a whole-stem scratch name proves each copy and
junk file, so its row is automatic (D15.9, D15.10)."""

LATE_OPS: list[Callable[[Path], None]] = [op_committed_cache]
"""The scramble operations that S23 and S24 apply after `SCRAMBLE_OPS`.

They stay out of `SCRAMBLE_OPS`: 40 more files lift the scrambled tree
to T2, where the `setup` row does not fold, and `test_saved_plan.py` and
`test_from_report.py` build their messy tree from `SCRAMBLE_OPS` and test
that row."""

NEUTRAL_OPS: list[Callable[[Path], None]] = [op_clean_deletion]
"""The operations that add no finding: the plan, the score and the
baseline gate stay as in the tidy run (D15.21)."""

MANUAL_SHAPES: dict[str, Callable[[Path], None]] = {
    "scratch:ARCHITECTURE_v2_draft.md": op_architecture_draft,
    "scratch:tmp/scratch_fold.rs": op_scratch_source,
    "scratch:README.old.md": op_readme_old,
    "secret-file:.env": op_env_placeholder,
}
"""The realistic shapes that only a name proves, each with the id of its
row: a compound stem, a stem that is not one scratch word, and a
placeholder `.env`. Each row is manual (D15.9, D15.10)."""

SCRAMBLED_PAGES: list[str] = [
    "ARCHITECTURE.md",
    "HOWTO-run.md",
    "IDEAS.md",
    "misc/design/a.md",
    "misc/design/b.md",
    "misc/glossary.md",
    "out/traceability.md",
]
"""The pages that `SCRAMBLE_OPS` moves out of `docs/`, sorted."""


def _all_auto(root: Path) -> None:
    """Run `apply --all-auto` with no `--mode` and no `--set`, and expect exit 0.

    Args:
        root: The target root.
    """
    assert apply_mod.run(root, None, True, [], []) == 0


def _excluded(path: str) -> bool:
    """Say whether the S23 comparison leaves a path out, as a file trueup writes.

    Args:
        path: A repo-relative POSIX path.

    Returns:
        True for the files and directories that `apply` writes, and for the
        side files of `findings.APPLY_SIDE_FILES`.
    """
    side_files = {
        name for names in findings_mod.APPLY_SIDE_FILES.values() for name in names
    }
    return (
        path in TRUEUP_WRITES
        or path in side_files
        or path.startswith(TRUEUP_WRITE_DIRS)
    )


def _tracked_tree(root: Path) -> list[str]:
    """Give `git ls-files -s` of a tree, with each tracked file at its current content.

    `git add -u` first stages the content that `apply` wrote to tracked
    files, for example a rewritten link. It adds no new path.

    Args:
        root: The repository root.

    Returns:
        The lines of `git ls-files -s`: mode, blob hash, stage and path,
        without the paths that `_excluded` names.
    """
    _git(root, "add", "-u")
    lines = _git(root, "ls-files", "-s").splitlines()
    return [line for line in lines if not _excluded(line.split("\t", 1)[1])]


def _plan_and_score(root: Path) -> tuple[int, int]:
    """Give the plan length and the score total of one `check` run.

    Args:
        root: The target root.

    Returns:
        The number of plan findings and `score.total`.
    """
    run = report.collect(root)
    return len(run.plan), compute(run.plan, run.survey, run.cfg).total


@pytest.mark.parametrize("layout", [True, False], ids=["layout-on", "layout-off"])
def test_scrambled_fixture_converges_to_its_tidy_source(
    tmp_path: Path, layout: bool
) -> None:
    """S23: check, apply --all-auto, check and apply of each move id give the tidy source back.

    The tidy tree has an empty plan and no move, so it gets no `apply`.
    The scrambled tree gets every operation of `SCRAMBLE_OPS` and
    `LATE_OPS`. Its two
    `git ls-files -s` lists, with blob hashes, are equal to the tidy
    source apart from the files trueup writes. `--all-auto` moves no page,
    and each moved page has its own finding.

    arch: D10.1, D10.9, D10.10, I-37, I-34, I-36
    arch: D15.38
    """
    tidy = _tidy(tmp_path / "tidy", layout, house=True)
    tidy_run = report.collect(tidy)
    assert [finding.id for finding in tidy_run.plan] == []
    assert tidy_run.moves == []
    source = _tracked_tree(tidy)

    messy = _tidy(tmp_path / "messy", layout, house=True)
    for operation in SCRAMBLE_OPS + LATE_OPS:
        operation(messy)
    report.collect(messy)
    _all_auto(messy)
    # I-34: `--all-auto` removed the copies and the junk, but moved no page.
    assert set(SCRAMBLED_PAGES) <= set(_git(messy, "ls-files").splitlines())
    second = report.collect(messy)
    # I-36: one finding for each page, also for the pages of a directory move.
    misplaced = [f.path for f in second.findings if f.rule == "doc-misplaced"]
    assert sorted(misplaced) == SCRAMBLED_PAGES
    move_ids = [move.id for move in second.moves]
    assert "move:misc/design/" in move_ids

    # D10.7 (I-37): `a.md`'s link to the glossary page still resolves
    # right after `misc/design/` moves, but to the wrong place (the
    # glossary has not moved yet). Apply up to and including that one
    # move, then check the link before the rest of the moves run: with
    # the canonical-form rewrite in place, it already points at the
    # glossary's current path, so no `broken-link` finding names it. A
    # `_rewrite_links` that only left the link alone (an identity stub)
    # would leave it pointing at the old `docs/glossary.md`, which does
    # not exist yet at this point, and this check would fail.
    design_move = "move:misc/design/"
    first_wave = [mid for mid in move_ids if mid <= design_move]
    second_wave = [mid for mid in move_ids if mid > design_move]
    assert apply_mod.run(messy, first_wave, False, [], []) == 0
    between = report.collect(messy)
    assert not any(
        finding.rule == "refcheck"
        and "broken-link" in finding.id
        and finding.path == "docs/design/a.md"
        for finding in between.findings
    )
    # arch: D12.2 - the first wave left staged moves and rewritten pages
    # uncommitted, and the second wave rewrites some of them again.
    assert apply_mod.run(messy, second_wave, False, [], [], allow_dirty=True) == 0

    assert _tracked_tree(messy) == source
    assert report.collect(messy).moves == []


@pytest.mark.parametrize("layout", [True, False], ids=["layout-on", "layout-off"])
@pytest.mark.parametrize("finding_id", sorted(MANUAL_SHAPES))
def test_a_name_only_scramble_shape_gives_a_manual_row(
    tmp_path: Path, finding_id: str, layout: bool
) -> None:
    """A compound-stem copy, a `README.old.md` copy and a placeholder `.env` each give a manual row.

    Only the name proves these shapes, so `--all-auto` must leave them to
    the person (I-53).

    arch: D15.9, D15.10
    """
    root = _tidy(tmp_path, layout, house=True)
    MANUAL_SHAPES[finding_id](root)
    rows = {finding.id: finding for finding in report.collect(root).plan}
    assert finding_id in rows
    assert rows[finding_id].auto is False


@pytest.fixture(scope="module")
def tidy_baseline(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[bool, tuple[int, int]]:
    """Give the plan length and the score total of the tidy tree, for each `layout` value.

    Args:
        tmp_path_factory: The pytest factory for module-scoped directories.

    Returns:
        `layout` value to the plan length and `score.total`.
    """
    baseline: dict[bool, tuple[int, int]] = {}
    for layout in (True, False):
        root = _tidy(tmp_path_factory.mktemp(f"tidy-{layout}"), layout, house=True)
        baseline[layout] = _plan_and_score(root)
    return baseline


@pytest.mark.parametrize("layout", [True, False], ids=["layout-on", "layout-off"])
@pytest.mark.parametrize(
    "operation", SCRAMBLE_OPS + LATE_OPS, ids=lambda op: op.__name__
)
def test_one_scramble_operation_gives_a_longer_plan_and_a_higher_score(
    tmp_path: Path,
    tidy_baseline: dict[bool, tuple[int, int]],
    operation: Callable[[Path], None],
    layout: bool,
) -> None:
    """S24: one scramble operation gives a longer plan and a higher score than the tidy run.

    arch: D10.1, D10.9, D10.10, I-36
    arch: D15.21
    """
    root = _tidy(tmp_path, layout, house=True)
    operation(root)
    plan_length, total = _plan_and_score(root)
    tidy_length, tidy_total = tidy_baseline[layout]
    assert plan_length > tidy_length
    assert total > tidy_total


@pytest.mark.parametrize("layout", [True, False], ids=["layout-on", "layout-off"])
@pytest.mark.parametrize("operation", NEUTRAL_OPS, ids=lambda op: op.__name__)
def test_one_neutral_operation_keeps_the_plan_the_score_and_the_gate(
    tmp_path: Path,
    tidy_baseline: dict[bool, tuple[int, int]],
    operation: Callable[[Path], None],
    layout: bool,
) -> None:
    """S24: a clean deletion keeps the plan and the score, and `check --baseline` exits 0.

    arch: D10.1, D10.9, D10.10, I-36
    arch: D15.21
    """
    root = _tidy(tmp_path, layout, house=True)
    baseline_mod.write(root)
    operation(root)
    assert _plan_and_score(root) == tidy_baseline[layout]
    assert report.check(root, as_json=True, out=None, baseline=True) == 0


TWIN_SCRATCH: tuple[str, str] = ("docs/old-a.bak", "docs/old-b.bak")
"""Two `.bak` paths, proven scratch by name (D15.9), that get equal bytes."""


def _twin_scratch_tree(base: Path) -> Path:
    """Build the tidy tree plus two tracked scratch files of equal content.

    The content is in no other tracked file, so the two copies are the
    only copies of it (I-35).

    Args:
        base: The directory to build the repository in.

    Returns:
        The repository root, clean.
    """
    root = _tidy(base, house=True)
    for rel in TWIN_SCRATCH:
        _write(root, rel, b"the only content of the twin scratch files\n")
    _commit(root, "add two equal scratch copies")
    return root


def _scratch_rows(root: Path) -> dict[str, bool]:
    """Give each `scratch` row of a fresh check, with its `auto` flag.

    Args:
        root: The target root.

    Returns:
        Path to the `auto` flag.
    """
    return {
        finding.path: finding.auto
        for finding in report.collect(root).findings
        if finding.rule == "scratch"
    }


def test_all_auto_removes_two_equal_scratch_copies_across_passes(
    tmp_path: Path,
) -> None:
    """I-35: the first plan holds one copy manual, and `--all-auto` still removes both across passes.

    Within one plan the last copy is manual. `--all-auto` collects a new
    plan for each pass, so the second pass sees the remaining copy as a
    scratch file with no copy. The test pins this known limit.

    arch: D16.9, I-35, D10.3
    """
    root = _twin_scratch_tree(tmp_path / "twins")
    first = _scratch_rows(root)
    assert sorted(first) == sorted(TWIN_SCRATCH)
    assert sorted(first.values()) == [False, True]
    assert first[min(TWIN_SCRATCH)] is False

    _all_auto(root)

    tracked = set(_git(root, "ls-files").splitlines())
    assert not tracked & set(TWIN_SCRATCH)
