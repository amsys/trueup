"""Acceptance tests for the criteria S11 and S12 of the brief (docs/BRIEF.md).

Each test materialises its fixture tree and runs the lint commands of the
standard page as a child process (D4.3). It asserts the exit code and the
exact failure lines of the checker. The tests came from the meridian
repository, together with the standard page and the lint configurations.
A test skips, with the tool name, when a tool of a block is not on the
path (D15.38).
"""

from pathlib import Path

from conftest import materialise
from test_lint_fixtures import _checker_lines, _run_lint, skip_without_tools

LANGUAGES = ("python", "rust", "typescript", "shell", "sql")
CLEAN = ["ref_check: 0 failures, 0 references"]


def _lint_pairs(case: str, tmp_path: Path) -> dict[str, tuple[list, list]]:
    """Run the lint block of each language on the wrong tree and the corrected tree.

    Every pair is below `tmp_path`; `_run_lint` runs the TypeScript line
    from its tree (D4.3, R-3). The test skips before the first run when a
    tool of any block is absent.

    Args:
        case: The fixture tree that holds `<language>/wrong` and
            `<language>/corrected` for each language.
        tmp_path: The directory for the pairs.

    Returns:
        For each language, the results of the block on the wrong tree and
        on the corrected tree.
    """
    for language in LANGUAGES:
        skip_without_tools(language)
    results = {}
    for language in LANGUAGES:
        wrong = materialise(f"{case}/{language}/wrong", tmp_path / language / "wrong")
        corrected = materialise(
            f"{case}/{language}/corrected", tmp_path / language / "corrected"
        )
        results[language] = (
            _run_lint(language, wrong),
            _run_lint(language, corrected),
        )
    return results


def _assert_corrected_pass(results: dict[str, tuple[list, list]]) -> None:
    """Assert that each corrected tree gives exit 0 and, for the checker, the summary alone."""
    for language, (_, corrected) in results.items():
        codes = [result.returncode for result in corrected]
        assert codes == [0] * len(corrected), (language, corrected)
        if language in ("python", "shell", "sql"):
            assert _checker_lines(corrected) == CLEAN, language


def test_s11_comment_standard(tmp_path):
    """A fixture that breaks the comment standard fails its lint command (brief S11).

    arch: D1.5, D1.6, D2.11, D2.9
    """
    results = _lint_pairs("s11-comment-standard", tmp_path)

    (ruff, checker), _ = results["python"]
    assert ruff.returncode == 1
    assert "D100" in ruff.stdout
    assert "D103" in ruff.stdout
    assert checker.returncode == 0
    assert _checker_lines([ruff, checker]) == CLEAN

    ((clippy,), _) = results["rust"]
    assert clippy.returncode != 0
    assert "missing documentation for the crate" in clippy.stderr
    assert "missing documentation for a function" in clippy.stderr

    ((eslint,), _) = results["typescript"]
    assert eslint.returncode == 1
    assert "jsdoc/require-jsdoc" in eslint.stdout

    (shellcheck, checker), _ = results["shell"]
    assert shellcheck.returncode == 0, shellcheck.stdout
    assert checker.returncode == 1
    assert _checker_lines([shellcheck, checker]) == [
        "fixture.sh:1: [no-header] file has no header comment",
        "ref_check: 1 failures, 0 references",
    ]

    (sqlfluff, checker), _ = results["sql"]
    assert sqlfluff.returncode == 0, sqlfluff.stdout
    assert checker.returncode == 1
    assert _checker_lines([sqlfluff, checker]) == [
        "fixture.sql:1: [no-header] file has no header comment",
        "ref_check: 1 failures, 0 references",
    ]

    _assert_corrected_pass(results)


def test_s12_suppression_reason(tmp_path):
    """A suppression with no reason fails. The same suppression with a reason passes (brief S12).

    arch: D1.5, D1.6, D2.11, D2.9
    """
    results = _lint_pairs("s12-suppression-reason", tmp_path)

    (ruff, checker), _ = results["python"]
    assert ruff.returncode == 0, ruff.stdout
    assert checker.returncode == 1
    assert _checker_lines([ruff, checker]) == [
        "fixture.py:4: [no-reason] hidden: suppression has no reason: noqa: D103",
        "ref_check: 1 failures, 0 references",
    ]

    ((clippy,), _) = results["rust"]
    assert clippy.returncode != 0
    assert "allow_attributes_without_reason" in clippy.stderr

    ((eslint,), _) = results["typescript"]
    assert eslint.returncode == 1
    assert "eslint-comments/require-description" in eslint.stdout

    (shellcheck, checker), _ = results["shell"]
    assert shellcheck.returncode == 0, shellcheck.stdout
    assert checker.returncode == 1
    assert _checker_lines([shellcheck, checker]) == [
        "fixture.sh:3: [no-reason] -: suppression has no reason: shellcheck disable=SC2086",
        "ref_check: 1 failures, 0 references",
    ]

    (sqlfluff, checker), _ = results["sql"]
    assert sqlfluff.returncode == 0, sqlfluff.stdout
    assert checker.returncode == 1
    assert _checker_lines([sqlfluff, checker]) == [
        "fixture.sql:3: [no-reason] -: suppression has no reason: noqa: CP01",
        "ref_check: 1 failures, 0 references",
    ]

    _assert_corrected_pass(results)
