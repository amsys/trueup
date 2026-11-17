"""Integration tests that run the lint commands of the standard page on fixtures.

For each of the five languages, the wrong fixture fails the command that the
page names. The corrected fixture passes it. The corrected fixture holds a
suppression with a reason over a real defect, so a pass also shows that the
reason does not break the suppression. A test skips, with the tool name,
when a tool of its block is not on the path (D15.38).
"""

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import materialise

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "reference" / "comment-standard.md"

_BLOCK = re.compile(r"^```sh lint:(\w+)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_EXTENSIONS = {
    "python": ".py",
    "rust": ".rs",
    "typescript": ".ts",
    "shell": ".sh",
    "sql": ".sql",
}
_CLEAN_SUMMARY = ["ref_check: 0 failures, 0 references"]

_LINT_DIR = "lint/"
"""A block token that starts with this prefix names a file of this
repository's `lint/` tree; `_run_lint` makes it absolute."""

_TS_MODULES = REPO / "lint" / "ts" / "node_modules"
"""The eslint packages that the TypeScript block needs (`npm ci --prefix lint/ts`)."""

_PAGE_REF_CHECK_TOKEN = "refs"
"""The page runs the checker as `python3 trueup refs --root {root}` (D3.3).
The command line is already this repository's own, so a lint block runs it
unchanged; the token marks that line among a block's results in
`_checker_lines`."""


def _lint_block(language: str) -> list[str]:
    """Read the lint command lines of one language from the standard page.

    Args:
        language: The name in the info string `sh lint:<language>`.

    Returns:
        The command lines of the block, with the placeholders still in them.
    """
    blocks = {
        name: body for name, body in _BLOCK.findall(PAGE.read_text(encoding="utf-8"))
    }
    assert language in blocks, f"the page has no sh lint:{language} block"
    return [line for line in blocks[language].splitlines() if line.strip()]


def skip_without_tools(language: str) -> None:
    """Skip the test when a tool of one lint block is absent.

    The tool is the first token of each block line. The TypeScript block
    also needs `lint/ts/node_modules`.

    Args:
        language: The language whose block the test runs.
    """
    for line in _lint_block(language):
        tool = shlex.split(line)[0]
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is not on the path")
    if language == "typescript" and not _TS_MODULES.is_dir():
        pytest.skip("lint/ts/node_modules is absent; run npm ci --prefix lint/ts")


def _run_lint(language: str, tree: Path) -> list[subprocess.CompletedProcess[str]]:
    """Replace the placeholders of one lint block and run each line.

    A line runs from the repository, and a TypeScript line runs from
    `tree`, because eslint ignores a file outside its working directory
    (D4.3, R-3). A `lint/` token becomes an absolute path in this
    repository. The test skips when a tool of the block is absent.

    Args:
        language: The language whose block to run.
        tree: The materialised fixture tree. It is `{root}` and `{crate}`.

    Returns:
        The result of each command line, in the order of the block.
    """
    skip_without_tools(language)
    files = sorted(str(path) for path in tree.rglob(f"*{_EXTENSIONS[language]}"))
    assert files, f"the tree {tree} holds no {_EXTENSIONS[language]} file"
    cwd = tree if language == "typescript" else REPO
    results = []
    for line in _lint_block(language):
        argv: list[str] = []
        for token in shlex.split(line):
            if token == "{files}":
                argv.extend(files)
            elif token.startswith(_LINT_DIR):
                argv.append(str(REPO / token))
            else:
                argv.append(
                    token.replace("{root}", str(tree)).replace("{crate}", str(tree))
                )
        results.append(
            subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        )
    return results


def _checker_lines(results: list[subprocess.CompletedProcess[str]]) -> list[str]:
    """Give the standard output lines of the reference checker line of a block."""
    checker = [result for result in results if _PAGE_REF_CHECK_TOKEN in result.args]
    assert len(checker) == 1
    return checker[0].stdout.splitlines()


def _materialise_pair(case: str, tmp_path: Path) -> tuple[Path, Path]:
    """Materialise the wrong tree and the corrected tree of one fixture case."""
    wrong = materialise(f"{case}/wrong", tmp_path / "wrong")
    corrected = materialise(f"{case}/corrected", tmp_path / "corrected")
    return wrong, corrected


def test_python_wrong_fails_corrected_passes(tmp_path):
    """The Python pair: ruff and check f fail the wrong tree and pass the corrected one.

    arch: D1.5, D4.3, D2.11, D2.9, I-12
    """
    wrong, corrected = _materialise_pair("lint_python", tmp_path)
    ruff, checker = _run_lint("python", wrong)
    assert ruff.returncode == 1
    assert "D100" in ruff.stdout
    assert "D103" in ruff.stdout
    assert checker.returncode == 1
    assert _checker_lines([ruff, checker])[:-1] == [
        "fixture.py:5: [no-reason] hidden: suppression has no reason: noqa: D103"
    ]
    results = _run_lint("python", corrected)
    assert [result.returncode for result in results] == [0, 0], results
    assert _checker_lines(results) == _CLEAN_SUMMARY


def test_rust_wrong_fails_corrected_passes(tmp_path):
    """The Rust pair: clippy fails the wrong crate and passes the corrected one.

    The corrected crate uses `#[expect]` with a reason over two real lints.

    arch: D1.5, D4.3, D2.11, D2.9, I-12
    """
    wrong, corrected = _materialise_pair("lint_rust", tmp_path)
    (clippy,) = _run_lint("rust", wrong)
    assert clippy.returncode != 0
    assert "allow_attributes_without_reason" in clippy.stderr
    assert "missing documentation for a function" in clippy.stderr
    (clippy,) = _run_lint("rust", corrected)
    assert clippy.returncode == 0, clippy.stderr
    assert "unfulfilled" not in clippy.stderr


def test_typescript_wrong_fails_corrected_passes(tmp_path):
    """The TypeScript pair: eslint fails the wrong file and passes the corrected one.

    The pair is below `tmp_path`; `_run_lint` runs eslint from the tree,
    with the `lint/ts` paths absolute, so no directory of this repository
    holds a fixture run.

    arch: D1.5, D4.3, D2.11, D2.9, I-12
    arch: D15.38
    """
    wrong, corrected = _materialise_pair("lint_ts", tmp_path)
    (eslint,) = _run_lint("typescript", wrong)
    assert eslint.returncode == 1, eslint.stdout
    assert "jsdoc/require-jsdoc" in eslint.stdout
    assert "@typescript-eslint/ban-ts-comment" in eslint.stdout
    assert "eslint-comments/require-description" in eslint.stdout
    (eslint,) = _run_lint("typescript", corrected)
    assert eslint.returncode == 0, eslint.stdout
    assert "warning" not in eslint.stdout


def test_shell_wrong_fails_corrected_passes(tmp_path):
    """The shell pair: shellcheck and check f fail the wrong file and pass the corrected one.

    arch: D1.5, D4.3, D2.11, D2.9, I-12
    """
    wrong, corrected = _materialise_pair("lint_shell", tmp_path)
    results = _run_lint("shell", wrong)
    shellcheck, checker = results
    assert shellcheck.returncode == 1
    assert "SC2086" in shellcheck.stdout
    assert checker.returncode == 1
    assert _checker_lines(results)[:-1] == [
        "fixture.sh:1: [no-header] file has no header comment",
        "fixture.sh:3: [no-reason] -: suppression has no reason: shellcheck disable=SC2086",
    ]
    results = _run_lint("shell", corrected)
    assert [result.returncode for result in results] == [0, 0], results
    assert _checker_lines(results) == _CLEAN_SUMMARY


def test_sql_wrong_fails_corrected_passes(tmp_path):
    """The SQL pair: sqlfluff and check f fail the wrong file and pass the corrected one.

    The corrected file carries the reason in a block comment before a bare
    noqa, the form of R-1.

    arch: D1.5, D4.3, D2.11, D2.9, I-12
    """
    wrong, corrected = _materialise_pair("lint_sql", tmp_path)
    results = _run_lint("sql", wrong)
    sqlfluff, checker = results
    assert sqlfluff.returncode == 1
    assert "CP01" in sqlfluff.stdout
    assert checker.returncode == 1
    assert _checker_lines(results)[:-1] == [
        "fixture.sql:1: [no-header] file has no header comment",
        "fixture.sql:4: [no-reason] -: suppression has no reason: noqa: CP01",
    ]
    results = _run_lint("sql", corrected)
    assert [result.returncode for result in results] == [0, 0], results
    assert _checker_lines(results) == _CLEAN_SUMMARY


def test_a_missing_lint_tool_skips_with_its_name(monkeypatch, tmp_path):
    """A block tool that is not on the path, or no eslint packages, skips the test with the name.

    arch: D15.38
    """
    monkeypatch.setattr(
        shutil, "which", lambda name: None if name == "shellcheck" else name
    )
    with pytest.raises(pytest.skip.Exception, match="shellcheck is not on the path"):
        skip_without_tools("shell")
    monkeypatch.setattr(shutil, "which", lambda name: name)
    skip_without_tools("shell")
    monkeypatch.setitem(globals(), "_TS_MODULES", tmp_path / "absent")
    with pytest.raises(pytest.skip.Exception, match="lint/ts/node_modules is absent"):
        skip_without_tools("typescript")
