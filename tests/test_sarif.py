"""Tests for `check --sarif FILE` and `report.render_sarif` (arch: D12.4)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import materialise
from trueup import cli, report
from trueup.findings import Finding


def _finding(
    rule: str,
    path: str,
    severity: str = "warn",
    finding_id: str | None = None,
) -> Finding:
    """Build one finding for a render test.

    Args:
        rule: The rule name.
        path: The repo-relative path, or the empty string.
        severity: `error`, `warn` or `info`.
        finding_id: The id, or `None` for `<rule>:<path>`.

    Returns:
        The finding.
    """
    return Finding(
        id=finding_id or f"{rule}:{path}",
        rule=rule,
        category="docs",
        severity=severity,
        path=path,
        evidence="the evidence",
        action="the action",
        auto=False,
    )


def test_render_sarif_shape_and_levels() -> None:
    """The run is SARIF 2.1.0 with one rule per rule name at its worst level.

    arch: D12.4
    """
    findings = [
        _finding("alpha", "a.md", "info"),
        _finding("alpha", "b.md", "error"),
        _finding("beta", "c.md", "warn"),
    ]
    doc = report.render_sarif(findings, set())
    assert doc["version"] == "2.1.0"
    (run,) = doc["runs"]
    driver = run["tool"]["driver"]
    assert driver["name"] == "trueup"
    assert driver["rules"] == [
        {"id": "alpha", "defaultConfiguration": {"level": "error"}},
        {"id": "beta", "defaultConfiguration": {"level": "warning"}},
    ]
    levels = [result["level"] for result in run["results"]]
    assert levels == ["note", "error", "warning"]
    first = run["results"][0]
    assert first["ruleId"] == "alpha"
    assert first["message"]["text"] == "the evidence — the action"
    assert first["partialFingerprints"] == {"trueupId/v1": "alpha:a.md"}


def test_render_sarif_skips_kept_findings() -> None:
    """A kept finding gives no result and no rule.

    arch: D12.4
    """
    findings = [_finding("alpha", "a.md"), _finding("beta", "b.md")]
    doc = report.render_sarif(findings, {"alpha:a.md"})
    (run,) = doc["runs"]
    assert [r["ruleId"] for r in run["results"]] == ["beta"]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["beta"]


def test_render_sarif_locations() -> None:
    """A refcheck id gives its line; other ids give line 1; an empty path gives none.

    arch: D12.4
    """
    findings = [
        _finding(
            "refcheck",
            "docs/A.md",
            finding_id="refcheck:docs/A.md:7:unknown-id",
        ),
        _finding("scratch", "x.tmp"),
        _finding("health", ""),
    ]
    results = report.render_sarif(findings, set())["runs"][0]["results"]
    loc = results[0]["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "docs/A.md"
    assert loc["region"]["startLine"] == 7
    assert results[1]["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    assert "locations" not in results[2]


def test_render_sarif_reads_the_line_field_first() -> None:
    """A finding's `line` gives the SARIF start line; 0 falls back to the refcheck id, then 1.

    arch: D15.3, D15.8
    """
    from dataclasses import replace

    findings = [
        replace(
            _finding(
                "secret-content", "a.py", "error", "secret-content:a.py:0f3a9c2b11de"
            ),
            line=12,
        ),
        replace(
            _finding("refcheck", "docs/A.md", finding_id="refcheck:docs/A.md:7:x"),
            line=9,
        ),
        _finding("refcheck", "docs/B.md", finding_id="refcheck:docs/B.md:5:x"),
        _finding(
            "changelog",
            "CHANGELOG.md",
            finding_id="changelog:CHANGELOG.md:e5d4c3b2a190",
        ),
    ]
    results = report.render_sarif(findings, set())["runs"][0]["results"]
    lines = [
        result["locations"][0]["physicalLocation"]["region"]["startLine"]
        for result in results
    ]
    assert lines == [12, 9, 5, 1]


def test_check_sarif_writes_file_and_keeps_exit_code(tmp_path: Path, capsys) -> None:
    """`--sarif FILE` writes valid JSON, and the exit code equals the run without it.

    arch: D12.4
    """
    tree = materialise("messy", tmp_path / "repo")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    plain = cli.main(["check", "--root", str(tree)])
    sarif = tmp_path / "out.sarif"
    code = cli.main(["check", "--root", str(tree), "--json", "--sarif", str(sarif)])
    assert code == plain == 1
    doc = json.loads(sarif.read_text(encoding="utf-8"))
    assert doc["runs"][0]["results"]
    stdout = capsys.readouterr().out
    assert '"plan"' in stdout


def test_check_sarif_refused_inside_root(tmp_path: Path) -> None:
    """A SARIF file inside root with no covering `ignore` glob exits 2 and writes nothing.

    arch: D12.4
    """
    tree = materialise("messy", tmp_path / "repo")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    sarif = tree / "trueup.sarif"
    assert cli.main(["check", "--root", str(tree), "--sarif", str(sarif)]) == 2
    assert not sarif.exists()


def test_check_sarif_allowed_inside_root_when_ignored(tmp_path: Path) -> None:
    """An `ignore` glob that covers the SARIF file lets it be written.

    arch: D12.4
    """
    tree = materialise("messy", tmp_path / "repo")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    (tree / "trueup.toml").write_text(
        'version = 1\nignore = ["trueup.sarif"]\n', encoding="utf-8"
    )
    sarif = tree / "trueup.sarif"
    assert cli.main(["check", "--root", str(tree), "--sarif", str(sarif)]) == 1
    assert sarif.exists()


def test_check_changed_sarif(tmp_path: Path) -> None:
    """`--sarif` combines with `--changed`.

    arch: D12.4
    """
    tree = materialise("messy", tmp_path / "repo")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    sarif = tmp_path / "c.sarif"
    code = cli.main(["check", "--root", str(tree), "--changed", "--sarif", str(sarif)])
    assert code == 1
    assert json.loads(sarif.read_text(encoding="utf-8"))["version"] == "2.1.0"


def test_render_sarif_escapes_a_surrogate_path() -> None:
    """A path with a lone surrogate serialises: ensure_ascii escapes it.

    arch: D12.4
    """
    path = "docs/bad\udcff.md"
    doc = report.render_sarif([_finding("alpha", path)], set())
    text = json.dumps(doc, indent=2, sort_keys=True)
    assert "\\udcff" in text
    text.encode("utf-8")
