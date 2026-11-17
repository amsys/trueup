"""Integration tests for the scanner, the targets, and the one exclusion key (D1.2, D1.3, D4.3, I-2)."""

import subprocess
import sys
from pathlib import Path

from tests.refs.conftest import materialise

from trueup.ref_check import main, run

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the child process needs no `cwd`."""


def test_five_language_tree_gives_expected_references(tmp_path):
    """A tree with the five languages gives the expected references (D1.2, D1.3).

    arch: D1.2, D1.3
    """
    tree = materialise("scan-five-languages", tmp_path)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tree)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "ref_check: 0 failures, 5 references\n"


def test_fixture_pair_wrong_then_corrected(tmp_path):
    """A wrong fixture fails, and the corrected fixture gives exit 0 (D4.3).

    arch: D4.3
    """
    wrong = materialise("scan-wrong", tmp_path / "wrong")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(wrong)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert (
        result.stdout
        == "module.py:1: [unknown-id] module cites D9.9\nref_check: 1 failures, 1 references\n"
    )

    corrected = materialise("scan-corrected", tmp_path / "corrected")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(corrected)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "ref_check: 0 failures, 1 references\n"


_SWITCHES = "[checks]\nregistry = true\ncomments = true\nlinks = true\nlayout = true\n"
"""Every switch on but check i, for the trees of the `[scan] ignore` tests."""


def _ignore_tree(root: Path) -> Path:
    """Write a tree with one failure in each place that `[scan] ignore` can skip.

    `gen/a.py` cites an absent design id (check a). `docs/features/x.md`
    is not below `docs/reference/`, has no index link and has a broken link
    (checks g and h). `docs/features/y.md` has no front matter (check h).
    `src/b.py` cites an absent design id too, and no glob names it.

    Args:
        root: The directory that gets the tree.

    Returns:
        The root.
    """
    (root / "docs" / "features").mkdir(parents=True)
    (root / "gen").mkdir()
    (root / "src").mkdir()
    (root / "docs" / "ARCHITECTURE.md").write_text(
        "## D1.1 — One\n\n## Verification\n\n", encoding="utf-8"
    )
    (root / "docs" / "features" / "x.md").write_text(
        "---\nid: x\ntype: reference\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-10-16\n---\n\n"
        "# X\n\nSee [gone](missing.md).\n",
        encoding="utf-8",
    )
    (root / "docs" / "features" / "y.md").write_text("# Y\n", encoding="utf-8")
    (root / "gen" / "a.py").write_text(
        '"""Gen."""\n# ref: arch/D9.9\n', encoding="utf-8"
    )
    (root / "src" / "b.py").write_text('"""B."""\n# ref: arch/D9.8\n', encoding="utf-8")
    return root


def test_no_other_config_key_or_env_var_can_skip_a_path(tmp_path, monkeypatch):
    """Only `[scan] ignore` skips a path: another key gives exit 2, and no env var skips one (I-2).

    arch: I-2
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    for text in ('[checks]\nskip = ["vendor"]\n', '[scan]\nskip = ["vendor"]\n'):
        (tmp_path / "ref_check.toml").write_text(text, encoding="utf-8")
        assert main(["--root", str(tmp_path)]) == 2

    root = _ignore_tree(tmp_path / "env")
    (root / "ref_check.toml").write_text(_SWITCHES, encoding="utf-8")
    for name in ("REF_CHECK_IGNORE", "REF_CHECK_SKIP", "TRUEUP_IGNORE", "SKIP"):
        monkeypatch.setenv(name, "gen/**")
    paths = {failure.path for failure in run(root).failures}
    assert {"gen/a.py", "docs/features/x.md", "docs/features/y.md"} <= paths


def test_scan_ignore_skips_a_path_in_every_check(tmp_path):
    """`[scan] ignore` takes a path out of the walk of checks a to i, and no other path (I-2).

    arch: I-2, D2.5
    """
    plain = _ignore_tree(tmp_path / "plain")
    (plain / "ref_check.toml").write_text(_SWITCHES, encoding="utf-8")
    before = run(plain)
    kinds = {(f.path, f.kind) for f in before.failures}
    assert ("gen/a.py", "unknown-id") in kinds
    for kind in ("misplaced", "unindexed", "broken-link"):
        assert ("docs/features/x.md", kind) in kinds
    assert ("docs/features/y.md", "no-front-matter") in kinds

    ignored = _ignore_tree(tmp_path / "ignored")
    (ignored / "ref_check.toml").write_text(
        _SWITCHES + '\n[scan]\nignore = ["docs/features/**", "gen/**"]\n',
        encoding="utf-8",
    )
    after = run(ignored)
    paths = {failure.path for failure in after.failures}
    assert not any(p.startswith(("gen/", "docs/features/")) for p in paths)
    assert not any(edge.source.startswith("gen/") for edge in after.edges)
    assert ("src/b.py", "unknown-id") in {(f.path, f.kind) for f in after.failures}


def test_a_directory_the_walk_cannot_read_gives_unreadable(tmp_path):
    """A directory with no read permission gives one `unreadable` failure (D1.2, I-4).

    arch: D1.2, I-4
    """
    from trueup.ref_check import Failure, run

    locked = tmp_path / "src" / "locked"
    locked.mkdir(parents=True)
    (locked / "hidden.py").write_text('"""Hidden."""\n', encoding="utf-8")
    locked.chmod(0)
    try:
        report = run(tmp_path)
    finally:
        locked.chmod(0o755)
    assert report.failures == [
        Failure("src/locked", 1, "unreadable", "file cannot be read: PermissionError")
    ]


def test_a_large_tree_runs_in_under_two_seconds(tmp_path):
    """20 files of 200 references each, against a 200 KB design, run in under 2 s (D4.1).

    D4.1 reads each target file one time for each run. The tree is made here.

    arch: D4.1
    """
    import time

    from trueup.ref_check import run

    docs = tmp_path / "docs"
    docs.mkdir()
    filler = "The gate reads one reference and gives one verdict. " * 19
    sections = [f"## D1.{n} — Part {n}\n\n{filler}\n" for n in range(1, 201)]
    design = "".join(sections)
    assert len(design.encode("utf-8")) >= 200_000
    (docs / "ARCHITECTURE.md").write_text(design, encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    for index in range(20):
        lines = [f'"""Module {index}."""\n']
        lines += [f"# ref: arch/D1.{n}\n" for n in range(1, 201)]
        (src / f"part_{index}.py").write_text("".join(lines), encoding="utf-8")

    start = time.perf_counter()
    report = run(tmp_path)
    elapsed = time.perf_counter() - start
    assert report.failures == []
    assert len(report.edges) == 4000
    assert elapsed < 2.0, f"run took {elapsed:.2f} s"


JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")


def test_a_javascript_file_is_read_as_typescript(tmp_path):
    """A whole-line `//` marker in each JavaScript extension gives one reference (D1.2).

    arch: D1.2
    """
    from trueup.ref_check import EXTENSIONS

    for suffix in JS_EXTENSIONS:
        assert EXTENSIONS[suffix] == "typescript"
        root = tmp_path / suffix.lstrip(".")
        root.mkdir()
        (root / f"app{suffix}").write_text("// ref: arch/D9.9\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout.endswith("ref_check: 1 failures, 1 references\n")


def test_a_marker_in_an_unlisted_extension_is_not_read(tmp_path):
    """The same marker line in `app.go` gives no reference (D1.2, I-1).

    arch: D1.2, I-1
    """
    (tmp_path / "app.go").write_text("// ref: arch/D9.9\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "ref_check: 0 failures, 0 references\n"


def test_the_test_file_rule_holds_for_a_javascript_file(tmp_path):
    """A `.test.js`, `.spec.js` or `tests/` JavaScript file proves a claim; `app.js` does not (D1.2).

    arch: D1.2
    """
    from trueup.ref_check import run

    for name in ("app.test.js", "app.spec.js", "tests/app.js", "app.js"):
        root = tmp_path / name.replace("/", "-")
        (root / "docs").mkdir(parents=True)
        (root / "docs" / "ARCHITECTURE.md").write_text(
            "## D1.1 — Gate\n\n## Verification\n\n- D1.1\n", encoding="utf-8"
        )
        source = root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("// ref: arch/D1.1\n", encoding="utf-8")
        unproved = [f for f in run(root).failures if f.kind == "unproved"]
        assert (unproved == []) is (name != "app.js"), name


def test_check_f_treats_a_javascript_file_as_typescript(tmp_path):
    """Check f gives a `.js` file the same result as the same `.ts` file (D1.2, D2.9).

    arch: D1.2, D2.9
    """
    from trueup.ref_check import run

    body = "const a = 1;\n// eslint-disable-next-line no-console\nconsole.log(a);\n"
    reports = []
    for suffix in (".ts", ".js"):
        root = tmp_path / suffix.lstrip(".")
        root.mkdir()
        (root / "ref_check.toml").write_text(
            "[checks]\ncomments = true\n", encoding="utf-8"
        )
        (root / f"app{suffix}").write_text(body, encoding="utf-8")
        reports.append(run(root).failures)
    assert reports[0] == reports[1] == []


def _count_references(root):
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    return int(result.stdout.rsplit(", ", 1)[1].split()[0])


def test_a_marker_in_target_or_venv_gives_no_reference(tmp_path):
    """A marker under `target/` or `venv/` gives no reference, at each depth (D1.2).

    arch: D1.2
    """
    for relative in (
        "target/gen.py",
        "venv/bin/tool.py",
        "pkg/target/gen.py",
        "pkg/venv/bin/tool.py",
    ):
        root = tmp_path / relative.replace("/", "_")
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text("# ref: arch/D9.9\n", encoding="utf-8")
        assert _count_references(root) == 0, relative


def test_a_marker_in_build_or_dist_still_gives_a_reference(tmp_path):
    """A marker under `build/` or `dist/` gives one reference each (D1.2).

    arch: D1.2
    """
    from trueup.ref_check import SKIP_DIRS

    assert {"target", "venv"} <= SKIP_DIRS
    assert not {"build", "dist", ".github"} & SKIP_DIRS
    for relative in ("build/gen.py", "dist/gen.py"):
        root = tmp_path / relative.replace("/", "_")
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text("# ref: arch/D9.9\n", encoding="utf-8")
        assert _count_references(root) == 1, relative


def test_a_null_byte_source_gives_unreadable_not_a_traceback(tmp_path, monkeypatch):
    """A `.py` file whose source holds a NUL byte gives `unreadable`, not a crash (D2.4).

    Python 3.11's `ast.parse` raises `ValueError` for a NUL byte; 3.12 and
    later raise `SyntaxError`, which `run` already reports. This monkeypatches
    `ast.parse` to reproduce the 3.11 behaviour on any Python version, only
    for the source of the one file under test, so pytest's own use of
    `ast.parse` (to format a traceback) is undisturbed.

    arch: D2.4
    """
    import ast

    from trueup import ref_check

    original_parse = ast.parse
    source = '"""Module."""\n'

    def parse_or_raise(text, *args, **kwargs):
        if text == source:
            raise ValueError("source code string cannot contain null bytes")
        return original_parse(text, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", parse_or_raise)
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    report = ref_check.run(tmp_path)
    assert report.failures == [
        ref_check.Failure("app.py", 1, "unreadable", "file cannot be read: ValueError")
    ]


def test_a_marker_in_a_nested_repository_gives_no_reference(tmp_path):
    """A directory below the root with its own `.git` is another repository; the walk does not enter it (D8.2).

    A submodule holds a `.git` file, a plain clone a `.git` directory. The
    same marker in a directory with no `.git` gives one reference.

    arch: D8.2
    """
    for name, git in (("gitfile", "file"), ("gitdir", "dir"), ("plain", None)):
        root = tmp_path / name
        source = root / "pkg" / "gen.py"
        source.parent.mkdir(parents=True)
        source.write_text("# ref: arch/D9.9\n", encoding="utf-8")
        if git == "file":
            (root / "pkg" / ".git").write_text(
                "gitdir: ../.git/modules/pkg\n", encoding="utf-8"
            )
        elif git == "dir":
            (root / "pkg" / ".git").mkdir()
        expected = 1 if git is None else 0
        assert _count_references(root) == expected, name


def test_a_page_in_a_nested_repository_is_not_a_page_of_the_root(tmp_path):
    """Check h reads no page below a nested repository under `docs/` (D8.2).

    arch: D8.2
    """
    for name, nested in (("nested", True), ("plain", False)):
        root = tmp_path / name
        page = root / "docs" / "sub" / "page.md"
        page.parent.mkdir(parents=True)
        page.write_text("# No front matter\n", encoding="utf-8")
        (root / "ref_check.toml").write_text(
            "[checks]\nlayout = true\n", encoding="utf-8"
        )
        if nested:
            (root / "docs" / "sub" / ".git").write_text(
                "gitdir: ../../.git/modules/sub\n", encoding="utf-8"
            )
        assert main(["--root", str(root)]) == (0 if nested else 1), name


def test_scan_ignore_globs_match_as_the_survey_globs_do():
    """The checker reads an `ignore` glob as the survey of `trueup check` does (I-2).

    The checker is one file with no import of the package, so it holds its
    own copy of the glob rules. This test keeps the two copies equal.

    arch: I-2
    """
    from trueup import ref_check, survey

    patterns = ("docs/features/**", "*.md", "gen/?.py", "a/**/b.py", "x[1].md")
    paths = (
        "docs/features/a.md",
        "docs/features/sub/b.md",
        "docs/featuresx.md",
        "README.md",
        "docs/README.md",
        "gen/a.py",
        "gen/ab.py",
        "a/b.py",
        "a/c/b.py",
        "x[1].md",
        "x1.md",
    )
    for pattern in patterns:
        for path in paths:
            assert ref_check.matches_ignore(path, (pattern,)) == survey.matches_ignore(
                path, (pattern,)
            ), (pattern, path)
