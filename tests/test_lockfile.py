"""Tests for the D7.2 `lockfile` row of `trueup.hygiene`."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from trueup import hygiene, managed, survey as survey_mod
from trueup.rulesets import render_eslint_package

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "lockfile"


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _commit_all(root: Path) -> None:
    """Commit every file under `root`, so git tracks it.

    Args:
        root: The repository root.
    """
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "t",
        ],
        cwd=root,
        check=True,
    )


def _lockfile_findings(root: Path) -> list:
    """Survey `root` and give the `lockfile` row's findings.

    Args:
        root: The repository root to survey and check.

    Returns:
        The `hygiene_findings` whose `rule` equals `"lockfile"`.
    """
    survey = survey_mod.run(root)
    return [
        finding
        for finding in hygiene.hygiene_findings(survey)
        if finding.rule == "lockfile"
    ]


def test_fixture_fires_gives_one_lockfile_finding(tmp_path: Path) -> None:
    """A manifest with a dependency and no lockfile gives one finding.

    arch: D7.2
    """
    shutil.copytree(_FIXTURES_ROOT / "fires", tmp_path, dirs_exist_ok=True)
    _git_init(tmp_path)
    _commit_all(tmp_path)
    findings = _lockfile_findings(tmp_path)
    assert [finding.id for finding in findings] == ["lockfile:package.json"]
    assert findings[0].severity == "error"
    assert findings[0].auto is False
    assert findings[0].path == "package.json"
    assert "lockfile" in findings[0].evidence


def test_fixture_silent_gives_no_lockfile_finding(tmp_path: Path) -> None:
    """A manifest with its lockfile, and a manifest with no dependencies, give nothing.

    arch: D7.2
    """
    shutil.copytree(_FIXTURES_ROOT / "silent", tmp_path, dirs_exist_ok=True)
    _git_init(tmp_path)
    _commit_all(tmp_path)
    assert _lockfile_findings(tmp_path) == []


def test_workspace_member_with_lockfile_at_root_is_silent(tmp_path: Path) -> None:
    """A manifest below the root counts the root's lockfile as its own.

    arch: D7.2
    """
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    member = tmp_path / "packages" / "app"
    member.mkdir(parents=True)
    (member / "package.json").write_text(
        '{"name": "app", "dependencies": {"left-pad": "^1.0.0"}}\n',
        encoding="utf-8",
    )
    _git_init(tmp_path)
    _commit_all(tmp_path)
    assert _lockfile_findings(tmp_path) == []


def test_broken_manifest_fails_closed(tmp_path: Path) -> None:
    """A manifest that does not parse still gives a finding (fail closed).

    arch: D7.2
    """
    (tmp_path / "package.json").write_text("{ not valid json", encoding="utf-8")
    _git_init(tmp_path)
    findings = _lockfile_findings(tmp_path)
    assert [finding.id for finding in findings] == ["lockfile:package.json"]


def test_a_managed_manifest_gives_no_lockfile_finding(tmp_path: Path) -> None:
    """The managed `lint/typescript/package.json` gives no finding; the same file with no marker does (D8.3).

    The managed manifest carries `"_managed": "trueup"` and names the
    eslint packages that `npm install --prefix lint/typescript` fetches.
    They are tools of the lint step, not dependencies of the project, and
    trueup cannot ship a lockfile for them without the network.

    arch: D8.3
    """
    _git_init(tmp_path)
    manifest = tmp_path / "lint" / "typescript" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        managed._mark_json(render_eslint_package("clean", "off")), encoding="utf-8"
    )
    _commit_all(tmp_path)
    assert _lockfile_findings(tmp_path) == []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.pop("_managed")
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _commit_all(tmp_path)
    assert [finding.id for finding in _lockfile_findings(tmp_path)] == [
        "lockfile:lint/typescript/package.json"
    ]


def test_the_managed_marker_exempts_only_the_managed_path(tmp_path: Path) -> None:
    """The `_managed` marker in a project's own `package.json` exempts nothing (D8.3).

    arch: D8.3
    """
    _git_init(tmp_path)
    manifest = tmp_path / "package.json"
    manifest.write_text(
        managed._mark_json(render_eslint_package("clean", "off")), encoding="utf-8"
    )
    _commit_all(tmp_path)
    assert [finding.id for finding in _lockfile_findings(tmp_path)] == [
        "lockfile:package.json"
    ]


def test_a_manifest_that_is_not_utf8_gives_one_info_row(tmp_path: Path) -> None:
    """A UTF-16 `package.json` is skipped by the lockfile row and named in an info row.

    arch: D15.1, D15.2
    """
    _git_init(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "package.json").write_bytes(
        '{"dependencies": {"left-pad": "1"}}'.encode("utf-16")
    )
    survey = survey_mod.run(tmp_path)
    rows = [
        finding
        for finding in hygiene.hygiene_findings(survey)
        if finding.rule in ("lockfile", "manifest-unreadable")
    ]
    assert [row.id for row in rows] == ["manifest-unreadable:sub/package.json"]
    assert rows[0].severity == "info"
    assert "not UTF-8" in rows[0].evidence
