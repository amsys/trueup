"""Tests for `trueup.baseline`: keys, the file, the gate, the ratchets.

arch: D6.6, D6.7, D6.8
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from trueup import baseline, docrules, hygiene, report, survey as survey_mod
from trueup.config import ConfigError
from trueup.findings import Finding


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _write_config(root: Path, **overrides: str) -> None:
    """Write a small `trueup.toml`, `docs = "full"` by default.

    Args:
        root: The repository root.
        overrides: Extra top-level `key = value` lines, verbatim.
    """
    lines = ['docs = "full"'] + [f"{key} = {value}" for key, value in overrides.items()]
    (root / "trueup.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- key: line numbers drop out -------------------------------------------


def test_key_drops_the_line_from_secret_content(tmp_path: Path) -> None:
    """`secret-content:<path>:<line>` keys as `secret-content:<path>` (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    early = Finding(
        id="secret-content:app.py:3",
        rule="secret-content",
        category="security",
        severity="error",
        path="app.py",
        evidence="app.py:3 matches an AWS access key id",
        action="remove the secret",
        auto=False,
    )
    later = replace(early, id="secret-content:app.py:9")
    assert baseline.key(early) == baseline.key(later) == "secret-content:app.py"


def test_key_drops_the_line_from_changelog(tmp_path: Path) -> None:
    """`changelog:<path>:<line>` keys as `changelog:<path>` (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    early = Finding(
        id="changelog:CHANGELOG.md:4",
        rule="changelog",
        category="docs",
        severity="error",
        path="CHANGELOG.md",
        evidence="a bad heading",
        action="fix the heading",
        auto=False,
    )
    later = replace(early, id="changelog:CHANGELOG.md:11")
    assert baseline.key(early) == baseline.key(later) == "changelog:CHANGELOG.md"


@pytest.mark.parametrize(
    ("rule", "finding_id"),
    [
        ("secret-content", "secret-content:app.py:0f3a9c2b11de"),
        ("secret-content", "secret-content:app.py:123456789012"),
        ("secret-content", "secret-content:app.py:0f3a9c2b11de:2"),
        ("secret-content", "secret-content:app.py:aws-access-token:9"),
        ("changelog", "changelog:app.py:e5d4c3b2a190"),
        ("changelog", "changelog:app.py:e5d4c3b2a190:3"),
    ],
)
def test_key_of_a_fingerprint_id_is_the_rule_and_the_path(
    rule: str, finding_id: str
) -> None:
    """A fingerprint id keys as `<rule>:<path>`, by rule name, whatever its last segments hold.

    An all-digit fingerprint and a `:2` repeat count drop out the same as
    any other fingerprint (D15.8).

    arch: D15.3, D15.8
    """
    finding = Finding(
        id=finding_id,
        rule=rule,
        category="security",
        severity="error",
        path="app.py",
        evidence="x",
        action="x",
        auto=False,
    )
    assert baseline.key(finding) == f"{rule}:app.py"


@pytest.mark.parametrize(
    ("finding_id", "expected"),
    [
        (
            "refcheck:docs/ARCHITECTURE.md:3:unknown-id",
            "refcheck:docs/ARCHITECTURE.md:unknown-id",
        ),
        ("refcheck:README.md:1:no-section:Install", "refcheck:README.md:no-section"),
        (
            "refcheck:README.md:1:broken-link:no-such-file:1",
            "refcheck:README.md:broken-link",
        ),
        (
            "refcheck:README.md:9:broken-link:no-such-file:2",
            "refcheck:README.md:broken-link",
        ),
        ("refcheck:cwd.txt:1:cwd", "refcheck:cwd.txt:cwd"),
        ("refcheck:", "refcheck:"),
    ],
)
def test_key_drops_the_line_from_refcheck(finding_id: str, expected: str) -> None:
    """Every `refcheck` id shape `docrules._refcheck_ids` builds keys the same across a line shift (D6.6).

    The shapes here are the ones `test_refcheck_ids_are_unique_and_the_run_sits_in_the_target`
    (`tests/test_docrules.py`) proves `_refcheck_ids` actually produces.

    arch: D6.6, D6.7, D6.8
    """
    finding = Finding(
        id=finding_id,
        rule="refcheck",
        category="docs",
        severity="error",
        path="",
        evidence="x",
        action="x",
        auto=False,
    )
    assert baseline.key(finding) == expected


def test_refcheck_key_is_the_same_with_and_without_a_same_line_collision() -> None:
    """A `refcheck` failure keys the same when a second failure on its line comes or goes (D6.6).

    `docrules._refcheck_ids` adds `:<tail>` only while two failures share
    `path:line:kind`. When the owner fixes one of two such failures, the
    other must keep its key, or `check --baseline` reads it as new.

    arch: D6.6, D6.7
    """
    lines = [
        "README.md:1: [no-section] missing section: Install",
        "README.md:1: [no-section] missing section: Usage",
    ]
    both = docrules._refcheck_ids(
        [docrules._REFCHECK_FAILURE_LINE.match(line) for line in lines]
    )
    alone = docrules._refcheck_ids([docrules._REFCHECK_FAILURE_LINE.match(lines[0])])
    assert both[0] != alone[0]

    def _key(finding_id: str) -> str:
        return baseline.key(
            Finding(
                id=finding_id,
                rule="refcheck",
                category="docs",
                severity="error",
                path="README.md",
                evidence="x",
                action="x",
                auto=False,
            )
        )

    assert {_key(finding_id) for finding_id in both} == {_key(alone[0])}


def test_key_keeps_every_other_id_unchanged() -> None:
    """A finding whose rule is none of the three key-shortening ones keys as its own id (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    finding = Finding(
        id="scratch:notes.tmp",
        rule="scratch",
        category="files",
        severity="error",
        path="notes.tmp",
        evidence="x",
        action="x",
        auto=True,
    )
    assert baseline.key(finding) == "scratch:notes.tmp"


def test_a_line_inserted_above_a_changelog_failure_gives_no_new_key(
    tmp_path: Path,
) -> None:
    """Shifting a changelog defect's line number does not read as a new baseline key (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    _git_init(tmp_path)
    _write_config(tmp_path)
    bad_changelog = "# Changelog\n\n## [Unreleased]\n\n### Nonsense\n\n- x\n"
    (tmp_path / "CHANGELOG.md").write_text(bad_changelog, encoding="utf-8")
    num_keys, score = baseline.write(tmp_path)
    assert num_keys > 0
    base = baseline.load(tmp_path)
    assert base is not None

    # Insert a blank line above the bad heading: every later line number
    # shifts by one, the key must not.
    shifted = "# Changelog\n\n## [Unreleased]\n\n\n### Nonsense\n\n- x\n"
    (tmp_path / "CHANGELOG.md").write_text(shifted, encoding="utf-8")
    run = report.collect(tmp_path)
    changelog_before = [
        f for f in run.plan if f.rule == "changelog" and f.path == "CHANGELOG.md"
    ]
    assert changelog_before, "the shifted file must still fail the same way"
    gate = baseline.compare(base, run, ratchet_now={})
    assert gate.new == ()
    assert gate.tighten == ()
    assert gate.score_now == score


_REFCHECK_STAND_IN = textwrap.dedent(
    """\
    import sys

    def main() -> int:
        root = sys.argv[sys.argv.index("--root") + 1]
        print(f"README.md:{line}: [no-description] no paragraph after the title")
        return 1

    raise SystemExit(main())
    """
)


def _bundled_refcheck(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, line: int
) -> None:
    """Point `docrules._BUNDLED_REF_CHECK` at a stand-in reporting one failure at `line`.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        tmp_path: A directory outside the target to hold the script.
        line: The line number the stand-in reports its one failure at.
    """
    script = tmp_path / "bundled" / "ref_check.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_REFCHECK_STAND_IN.replace("{line}", str(line)), encoding="utf-8")
    monkeypatch.setattr(docrules, "_BUNDLED_REF_CHECK", script)


def test_a_line_inserted_above_a_refcheck_failure_gives_no_new_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shifting a `refcheck` failure's line number does not read as a new baseline key (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _write_config(root)
    _bundled_refcheck(monkeypatch, tmp_path, line=5)
    num_keys, score = baseline.write(root)
    assert num_keys > 0
    base = baseline.load(root)
    assert base is not None

    _bundled_refcheck(monkeypatch, tmp_path, line=6)
    run = report.collect(root)
    gate = baseline.compare(base, run, ratchet_now={})
    assert gate.new == ()
    assert gate.score_now == score


# -- the baseline file -----------------------------------------------------


def test_write_is_the_only_write_and_writes_only_the_baseline_file(
    tmp_path: Path,
) -> None:
    """`trueup baseline` writes `.trueup-baseline.json` and no other file (I-16).

    arch: D6.6, D6.7, D6.8
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    before = {
        str(path.relative_to(tmp_path))
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    baseline.write(tmp_path)
    after = {
        str(path.relative_to(tmp_path))
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after - before == {baseline.BASELINE_FILENAME}


def test_render_is_sorted_indented_and_ends_in_one_newline() -> None:
    """`render` gives sorted keys, 2-space indent, one trailing newline (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    data = {"version": 1, "score": 3, "findings": {"b:x": 1, "a:y": 2}, "ratchet": {}}
    text = baseline.render(data)
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert json.loads(text) == data
    lines = text.splitlines()
    # Indent 2: the top-level keys sit two spaces in, and sort_keys orders
    # them "findings", "ratchet", "score", "version".
    top_level_keys = [line.strip() for line in lines if line.startswith('  "')]
    assert [key.split(":")[0] for key in top_level_keys] == [
        '"findings"',
        '"ratchet"',
        '"score"',
        '"version"',
    ]


def test_load_gives_none_when_the_file_is_absent(tmp_path: Path) -> None:
    """`load` gives `None` with no `.trueup-baseline.json` on disk (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    assert baseline.load(tmp_path) is None


def test_load_gives_none_for_unparsable_json(tmp_path: Path) -> None:
    """A hand-broken baseline file raises a `ConfigError`; D15.1 inverts the old `None`.

    The test name is from before that decision. An absent file still gives
    `None`.

    arch: D6.6, D6.7, D6.8, D15.1
    """
    assert baseline.load(tmp_path) is None
    (tmp_path / baseline.BASELINE_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a trueup baseline"):
        baseline.load(tmp_path)


def test_baseline_file_is_never_flagged_by_the_slop_rows(tmp_path: Path) -> None:
    """`.trueup-baseline.json` is data, not a managed file, and the hygiene rows ignore it (D6.6).

    arch: D6.6, D6.7, D6.8
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    baseline.write(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    run = report.collect(tmp_path)
    assert all(finding.path != baseline.BASELINE_FILENAME for finding in run.findings)


def test_baseline_file_does_not_push_the_root_over_budget(tmp_path: Path) -> None:
    """At the T0 root budget, `trueup baseline` then `check --baseline` exits 0 (D6.6, D6.7).

    The baseline file is data: the `root-budget` row and the score do not
    count it as a root entry.

    arch: D6.6, D6.7, D6.8
    """
    _git_init(tmp_path)
    for index in range(hygiene.ROOT_BUDGET["T0"]):
        (tmp_path / f"f{index}.txt").write_text("x\n", encoding="utf-8")
    before = report.collect(tmp_path)
    baseline.write(tmp_path)
    after = report.collect(tmp_path)
    assert after.survey.root_entries == before.survey.root_entries
    assert [f.id for f in after.plan] == [f.id for f in before.plan]
    assert report.check(tmp_path, as_json=True, out=None, baseline=True) == 0


def test_deleting_clean_files_passes_the_baseline_gate(tmp_path: Path) -> None:
    """`git rm` of four clean files leaves `check --baseline` at exit 0 (D15.21).

    arch: D15.21
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# a project\n", encoding="utf-8")
    for index in range(4):
        (tmp_path / f"c{index}.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    baseline.write(tmp_path)
    for index in range(4):
        (tmp_path / f"c{index}.txt").unlink()
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert report.check(tmp_path, as_json=True, out=None, baseline=True) == 0


# -- compare / Gate ---------------------------------------------------------


def _fake_run(cfg=None, plan=None, survey=None):
    """Build a minimal `report.CheckRun` for `compare`/`build` tests.

    Args:
        cfg: The `Config` to carry, or `None`.
        plan: The plan findings, or `None` for an empty plan.
        survey: A `Survey`, or `None` for a bare one from a fresh `tmp_path`-free stand-in.

    Returns:
        A `CheckRun` whose `findings` equal `plan`.
    """
    from trueup.survey import LangStat, Survey

    survey = survey or Survey(
        root=Path("."),
        files=(),
        languages={"python": LangStat(files=0, code_lines=0, present=False)},
        tools={},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T0",
        tier_reason="T0 (test)",
        counter="built-in",
    )
    plan = plan or []
    return report.CheckRun(survey=survey, cfg=cfg, findings=plan, plan=plan)


def test_compare_on_an_unchanged_repo_gives_no_failure(tmp_path: Path) -> None:
    """A `compare` against the same plan the baseline recorded fails nothing (D6.7).

    arch: D6.6, D6.7, D6.8
    """
    finding = Finding(
        id="scratch:notes.tmp",
        rule="scratch",
        category="files",
        severity="error",
        path="notes.tmp",
        evidence="x",
        action="x",
        auto=True,
    )
    run = _fake_run(plan=[finding])
    data = baseline.build(run, ratchet={})
    gate = baseline.compare(data, run, ratchet_now={})
    assert not baseline.failed(gate)
    assert gate.new == ()
    assert gate.tighten == ()


def _scored_scratch_run():
    """Build a fake run with one `scratch` finding and a score above 0.

    Returns:
        The run, and the score that `baseline.build` records for it.
    """
    finding = Finding(
        id="scratch:notes.tmp",
        rule="scratch",
        category="files",
        severity="error",
        path="notes.tmp",
        evidence="x",
        action="x",
        auto=True,
    )
    run = _fake_run(plan=[finding])
    score = baseline.build(run, ratchet={})["score"]
    assert score > 0
    return run, score


def test_compare_passes_a_score_rise_with_no_new_key() -> None:
    """A score rise alone does not fail the gate: it reads keys only (D15.21).

    arch: D15.21
    """
    run, score = _scored_scratch_run()
    base_data = {
        "version": 1,
        "score": score - 1,
        "findings": {"scratch:notes.tmp": 1},
        "ratchet": {},
    }
    gate = baseline.compare(base_data, run, ratchet_now={})
    assert gate.score_now == score > gate.score_before
    assert not baseline.failed(gate)


def test_compare_passes_the_same_score_with_no_new_key() -> None:
    """The same score, with the same keys and no ratchet change, passes the gate (D6.7).

    arch: D6.6, D6.7, D6.8
    """
    run, score = _scored_scratch_run()
    base_data = {
        "version": 1,
        "score": score,
        "findings": {"scratch:notes.tmp": 1},
        "ratchet": {},
    }
    gate = baseline.compare(base_data, run, ratchet_now={})
    assert gate.score_now == gate.score_before == score
    assert not baseline.failed(gate)


def test_compare_flags_a_new_finding_id(tmp_path: Path) -> None:
    """A finding whose key's count rose is `new`, and the gate fails (D6.7).

    The baseline records the run's own score, so only the new-key rule can
    fail this gate.

    arch: D6.6, D6.7, D6.8
    """
    now_run, score = _scored_scratch_run()
    data = {"version": 1, "score": score, "findings": {}, "ratchet": {}}
    gate = baseline.compare(data, now_run, ratchet_now={})
    assert gate.new == ("scratch:notes.tmp",)
    assert gate.score_now == gate.score_before
    assert baseline.failed(gate)


def test_compare_tightens_when_a_key_drops(tmp_path: Path) -> None:
    """A key whose count fell is `tighten`, info only, never a failure (D6.7).

    arch: D6.6, D6.7, D6.8
    """
    finding = Finding(
        id="scratch:notes.tmp",
        rule="scratch",
        category="files",
        severity="error",
        path="notes.tmp",
        evidence="x",
        action="x",
        auto=True,
    )
    base_data = baseline.build(_fake_run(plan=[finding]), ratchet={})
    now_run = _fake_run(plan=[])
    gate = baseline.compare(base_data, now_run, ratchet_now={})
    assert gate.tighten == ("scratch:notes.tmp",)
    assert not baseline.failed(gate)


def test_compare_flags_a_ratchet_drop(tmp_path: Path) -> None:
    """A ratchet value under `before - 0.1` is a drop, and fails the gate (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    base_data = {
        "version": 1,
        "score": 0,
        "findings": {},
        "ratchet": {"python": {"docstring": 90.0}},
    }
    run = _fake_run(plan=[])
    gate = baseline.compare(base_data, run, ratchet_now={"python": {"docstring": 88.0}})
    assert gate.ratchet_drops == ("python:docstring 90.0 -> 88.0",)
    assert baseline.failed(gate)


def test_compare_tolerates_a_tenth_of_a_point(tmp_path: Path) -> None:
    """A drop of exactly the tolerance does not fail the gate (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    base_data = {
        "version": 1,
        "score": 0,
        "findings": {},
        "ratchet": {"python": {"docstring": 90.0}},
    }
    run = _fake_run(plan=[])
    gate = baseline.compare(base_data, run, ratchet_now={"python": {"docstring": 89.9}})
    assert gate.ratchet_drops == ()
    assert not baseline.failed(gate)


def test_compare_flags_a_missing_report(tmp_path: Path) -> None:
    """A ratchet value the baseline recorded, with no report now, fails the gate (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    base_data = {
        "version": 1,
        "score": 0,
        "findings": {},
        "ratchet": {"go": {"test": 70.0}},
    }
    run = _fake_run(plan=[])
    gate = baseline.compare(base_data, run, ratchet_now={})
    assert gate.missing_reports == ("go:test",)
    assert baseline.failed(gate)


# -- ratchet_values ----------------------------------------------------------


def test_ratchet_values_skips_a_language_not_set_to_clean(tmp_path: Path) -> None:
    """A language present but not `clean` gets no ratchet entry (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    from trueup.config import Config
    from trueup.survey import LangStat, Survey

    survey = Survey(
        root=tmp_path,
        files=(),
        languages={"python": LangStat(files=5, code_lines=200, present=True)},
        tools={},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    cfg = Config(languages={"python": "strict"})
    assert baseline.ratchet_values(survey, cfg) == {}


def test_ratchet_values_reads_python_docstring_percent(tmp_path: Path) -> None:
    """The python `docstring` ratchet counts public modules, classes and functions (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    from trueup.config import Config
    from trueup.survey import LangStat, Survey

    (tmp_path / "a.py").write_text(
        '"""A module."""\n\n\ndef public() -> None:\n    """Doc."""\n\n\ndef _private() -> None:\n    pass\n\n\ndef undocumented() -> None:\n    pass\n',
        encoding="utf-8",
    )
    survey = Survey(
        root=tmp_path,
        files=("a.py",),
        languages={"python": LangStat(files=1, code_lines=60, present=True)},
        tools={},
        root_entries=("a.py",),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    cfg = Config(languages={"python": "clean"})
    values = baseline.ratchet_values(survey, cfg)
    # module + public() documented, undocumented() not, _private() excluded: 2/3.
    assert values["python"]["docstring"] == pytest.approx(66.7, abs=0.05)


def test_ratchet_values_reads_go_coverprofile(tmp_path: Path) -> None:
    """The go `test` ratchet reads `coverage.out` (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    from trueup.config import Config
    from trueup.survey import LangStat, Survey

    (tmp_path / "coverage.out").write_text(
        "mode: set\nfoo/bar.go:1.1,2.2 10 1\nfoo/bar.go:3.1,4.2 10 0\n",
        encoding="utf-8",
    )
    survey = Survey(
        root=tmp_path,
        files=(),
        languages={"go": LangStat(files=1, code_lines=60, present=True)},
        tools={},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    cfg = Config(languages={"go": "clean"})
    values = baseline.ratchet_values(survey, cfg)
    assert values["go"]["test"] == 50.0


def test_ratchet_values_reads_lcov_for_typescript_and_rust(tmp_path: Path) -> None:
    """The typescript and rust `test` ratchets read `lcov.info` (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    from trueup.config import Config
    from trueup.survey import LangStat, Survey

    (tmp_path / "coverage").mkdir()
    (tmp_path / "coverage" / "lcov.info").write_text("LF:10\nLH:7\n", encoding="utf-8")
    (tmp_path / "lcov.info").write_text("LF:4\nLH:4\n", encoding="utf-8")
    survey = Survey(
        root=tmp_path,
        files=(),
        languages={
            "typescript": LangStat(files=1, code_lines=60, present=True),
            "rust": LangStat(files=1, code_lines=60, present=True),
        },
        tools={},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    cfg = Config(languages={"typescript": "clean", "rust": "clean"})
    values = baseline.ratchet_values(survey, cfg)
    assert values["typescript"]["test"] == 70.0
    assert values["rust"]["test"] == 100.0


def test_ratchet_values_gives_no_test_metric_with_no_report(tmp_path: Path) -> None:
    """A present, clean language with no coverage report gets no `test` value (D6.8).

    arch: D6.6, D6.7, D6.8
    """
    from trueup.config import Config
    from trueup.survey import LangStat, Survey

    survey = Survey(
        root=tmp_path,
        files=(),
        languages={"go": LangStat(files=1, code_lines=60, present=True)},
        tools={},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    cfg = Config(languages={"go": "clean"})
    assert baseline.ratchet_values(survey, cfg) == {}


def test_hygiene_and_baseline_agree_on_the_filename() -> None:
    """`hygiene`'s exemption name and `baseline.BASELINE_FILENAME` are the same string (D6.6).

    The two are not linked by an import (`trueup.baseline` already imports
    `trueup.score`, which imports `trueup.hygiene`, so the reverse import
    would cycle); this test is what keeps them equal instead.

    arch: D6.6, D6.7, D6.8
    """
    from trueup import hygiene

    assert baseline.BASELINE_FILENAME in hygiene._MANAGED_DATA_BASENAMES


def test_docstring_percent_skips_a_file_ast_cannot_parse(tmp_path: Path) -> None:
    """A NUL byte makes ast.parse raise ValueError; the file is skipped, not fatal.

    arch: D14.12
    """
    from trueup.survey import LangStat, Survey

    (tmp_path / "ok.py").write_text('"""A module."""\n', encoding="utf-8")
    (tmp_path / "bad.py").write_bytes(b"x = 1\x00\n")
    survey = Survey(
        root=tmp_path,
        files=("ok.py", "bad.py"),
        languages={"python": LangStat(files=2, code_lines=60, present=True)},
        tools={},
        root_entries=("ok.py", "bad.py"),
        manifests=(),
        workspace=False,
        contributors=0,
        has_ci=False,
        tags=0,
        tier="T1",
        tier_reason="T1 (test)",
        counter="built-in",
    )
    assert baseline._python_docstring_percent(survey) == 100.0


def test_a_memory_error_in_the_parser_skips_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ast.parse` can raise `MemoryError`; the docstring ratchet skips that file.

    arch: D15.1
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")

    real_parse = baseline.ast.parse

    def _raise(source: str, *args: object, **kwargs: object) -> object:
        if '"""A."""' in str(source):  # only the file under test
            raise MemoryError("Parser stack overflowed")
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(baseline.ast, "parse", _raise)
    assert baseline._python_docstring_percent(survey_mod.run(tmp_path)) is None


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"findings": {"x": "two"}}',
        '{"findings": []}',
        '{"score": "high"}',
        '{"ratchet": {"python": 3}}',
        '{"ratchet": {"python": {"docstring": "x"}}}',
    ],
)
def test_load_raises_for_a_file_that_is_not_a_baseline(
    tmp_path: Path, text: str
) -> None:
    """Bad JSON or a bad shape raises a `ConfigError` that names the file.

    arch: D15.1
    """
    (tmp_path / baseline.BASELINE_FILENAME).write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="not a trueup baseline"):
        baseline.load(tmp_path)


def test_load_accepts_a_baseline_of_the_right_shape(tmp_path: Path) -> None:
    """A well-formed baseline loads unchanged.

    arch: D15.1
    """
    data = {"score": 90, "findings": {"scratch": 2}, "ratchet": {"python": {"x": 1.5}}}
    (tmp_path / baseline.BASELINE_FILENAME).write_text(
        json.dumps(data), encoding="utf-8"
    )
    assert baseline.load(tmp_path) == data


def test_the_docstring_ratchet_ignores_a_syntax_warning(tmp_path: Path) -> None:
    """A file with an invalid escape raises no `SyntaxWarning` and still counts.

    arch: D15.16, D15.17
    """
    import warnings

    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\nX = "\\d"\n', encoding="utf-8")
    survey = survey_mod.run(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert baseline._python_docstring_percent(survey) == 100.0
