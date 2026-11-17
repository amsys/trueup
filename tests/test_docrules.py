"""Tests for `trueup.docrules`.

Covers README length, changelog shape, page status, banned words and the
`ref_check.py` fold-in (D5.4).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import FIXTURES_ROOT, materialise, quoted_list_shapes
from trueup import docrules, survey as survey_mod
from trueup.config import load as load_config
from trueup.config import profile_flag

_REPO_ROOT = Path(__file__).resolve().parent.parent
"""The trueup checkout, the working directory a child process imports `trueup` from."""


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _write_config(root: Path, **fields: str) -> None:
    """Write a small `trueup.toml`, one `key = "value"` line per field.

    Args:
        root: The repository root.
        **fields: Each `trueup.toml` top-level string or literal value to
            write, already formatted as valid TOML on the right of `=`.
    """
    lines = [f"{key} = {value}" for key, value in fields.items()]
    (root / "trueup.toml").write_text(
        "version = 1\n" + "\n".join(lines) + "\n", encoding="utf-8"
    )


def _findings(root: Path) -> list:
    """Survey `root` and give every `docrules_findings` result, under the house profile.

    A fixture with no `trueup.toml` runs `minimal` since D15.6. These tests
    were written for the house rules, so the run names `house` as
    `--profile house` does (D15.0 rule 3).

    Args:
        root: The repository root to survey and check.

    Returns:
        The findings `trueup.docrules.docrules_findings` produced.
    """
    with profile_flag("house"):
        survey = survey_mod.run(root)
        cfg = load_config(root)
        return docrules.docrules_findings(survey, cfg)


def _banned_word(index: int) -> str:
    """Give one entry of `trueup/data/banned.txt`, so no test line holds a banned word itself.

    Args:
        index: The entry's position in the list.

    Returns:
        The entry, as `docrules` reads it.
    """
    return docrules._load_banned_words()[index]


def _findings_by_rule(root: Path, rule: str) -> list:
    """Survey `root` and give the `docrules_findings` of one rule.

    Args:
        root: The repository root to survey and check.
        rule: The rule name to filter on.

    Returns:
        The findings whose `rule` equals `rule`.
    """
    return [finding for finding in _findings(root) if finding.rule == rule]


# -- R10: README length -------------------------------------------------


def test_readme_under_the_budget_gives_no_finding(tmp_path: Path) -> None:
    """A README at or under 200 lines gives no `readme-length` finding (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("line\n" * 200, encoding="utf-8")
    assert _findings_by_rule(tmp_path, "readme-length") == []


def test_readme_over_the_budget_is_a_warn(tmp_path: Path) -> None:
    """A README over 200 lines is a `warn`, not automatic (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("line\n" * 201, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "readme-length")
    assert len(findings) == 1
    assert findings[0].id == "readme-length:README.md"
    assert findings[0].severity == "warn"
    assert findings[0].auto is False


def test_missing_readme_gives_no_finding_here(tmp_path: Path) -> None:
    """A missing README is `trueup.health`'s finding, not this module's (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    assert _findings_by_rule(tmp_path, "readme-length") == []


# -- Banned words, across Markdown and the eight languages --------------


def _banned_expectations() -> list[list[str]]:
    """Read `tests/fixtures/docrules/banned-expected.txt`, one list of fields per check.

    Returns:
        The TAB-split fields of each line that is not blank and not a `#`
        comment.
    """
    text = (FIXTURES_ROOT / "docrules" / "banned-expected.txt").read_text(
        encoding="utf-8"
    )
    return [
        line.split("\t")
        for line in text.splitlines()
        if line and not line.startswith("#")
    ]


def test_banned_word_fixture_tree(tmp_path: Path) -> None:
    """The banned-word floor flags prose in Markdown and comments in every language.

    It also skips fenced and inline code. The words the fixture tree holds,
    and where, are listed in `banned-expected.txt` so the banned words stay
    in fixture files (D5.4, I-25).

    arch: D5.4
    """
    materialise("docrules/banned", tmp_path)
    _git_init(tmp_path)
    findings = _findings_by_rule(tmp_path, "prose")
    by_path = {finding.path: finding for finding in findings}

    expectations = _banned_expectations()
    present_paths = {fields[0] for fields in expectations if fields[1] == "present"}
    assert len(present_paths) == 9, "README.md plus one source file per language"
    for fields in expectations:
        path, expect, word = fields[0], fields[1], fields[2]
        if expect == "present":
            assert path in by_path, f"{path} should have a prose finding"
            assert f"{word!r} (line {fields[3]})" in by_path[path].evidence
            assert by_path[path].severity == "error"
            assert by_path[path].auto is False
        elif word == "*":
            assert path not in by_path, f"{path} should have no prose finding"
        else:
            assert word not in by_path[path].evidence


def test_banned_word_in_a_python_string_is_not_flagged(tmp_path: Path) -> None:
    """A banned word inside code (not a comment) is left alone (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "mod.py").write_text(
        f'GREETING = "{_banned_word(0)} in a string"\n', encoding="utf-8"
    )
    assert _findings_by_rule(tmp_path, "prose") == []


def test_banned_word_finding_is_one_per_file(tmp_path: Path) -> None:
    """Two banned words in one file still give one `prose` finding, not two (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    first, second = _banned_word(0), _banned_word(1)
    (tmp_path / "notes.md").write_text(
        f"this holds {first} on one line\nand {second} on another\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "prose")
    assert len(findings) == 1
    assert f"{first!r} (line 1)" in findings[0].evidence
    assert f"{second!r} (line 2)" in findings[0].evidence


def test_banned_word_inside_a_longer_word_is_not_flagged(tmp_path: Path) -> None:
    r"""A banned word that is only part of a longer word gives no finding (D5.4).

    Guards the `\b` word boundaries `_entry_pattern` compiles in
    (docrules.py:204): with them dropped, this longer word would match too.

    arch: D5.4
    """
    _git_init(tmp_path)
    word = _banned_word(0)
    (tmp_path / "notes.md").write_text(
        f"this holds non{word}able as one word\n", encoding="utf-8"
    )
    assert _findings_by_rule(tmp_path, "prose") == []


_FORM_FIXTURES: tuple[tuple[str, str, bool], ...] = (
    ("noun-harness.py", "harness", False),
    # D15.16 (decision 11) took `harness` out of the built-in list: the verb
    # fixture stays and now expects silence.
    ("verb-harness.py", "harness", False),
    ("noun-unlock.py", "unlock", False),
    ("verb-unlock.py", "unlock", True),
    ("noun-underscore.py", "underscore", False),
    ("verb-underscore.py", "underscore", True),
    ("plural-underscore.py", "underscore", False),
    ("noun-underscore-leading.py", "underscore", False),
    ("verb-underscore-passive.py", "underscore", True),
    ("noun-underscore-that.py", "underscore", False),
    ("verb-underscore-object.py", "underscore", True),
    ("noun-leverage.py", "leverage", False),
    ("verb-leverage.py", "leverage", True),
    ("verb-leverage-subject.py", "leverage", True),
)
"""One row per D6.9 and D8.5 form fixture: its path, the word it is about,
and whether the noun (silent) or verb (fires) use is the one it holds."""


def test_banned_word_form_noun_use_is_silent_verb_use_fires(tmp_path: Path) -> None:
    """A D6.9 form entry's noun use gives no finding; its verb use does.

    Covers `harness`, `unlock` and `underscore`, the three field-trial
    false positives `trueup/data/banned.txt` banned by form, not by word.
    Since D15.16 the list holds no `harness` entry, so both of its
    fixtures are silent.

    arch: D6.9, D15.16
    """
    materialise("docrules/forms", tmp_path)
    _git_init(tmp_path)
    findings = _findings_by_rule(tmp_path, "prose")
    by_path = {finding.path: finding for finding in findings}
    for path, word, should_fire in _FORM_FIXTURES:
        if should_fire:
            assert path in by_path, f"{path} should have a prose finding"
            assert f"{word!r}" in by_path[path].evidence
        else:
            assert path not in by_path, f"{path} should have no prose finding"


def test_banned_word_form_plural_noun_underscores_is_silent(tmp_path: Path) -> None:
    """The plural noun "underscores" (the `_` character) gives no finding; the verb forms still do (D8.5).

    D6.9 accepted the plural noun as a residual risk. The first run on target-rust
    (2026-10-07) hit it ("Note the leading underscores"), so D8.5 reverses
    that choice: every form of the verb needs a following determiner or
    `by`, and the bare noun, singular or plural, is silent.

    arch: D8.5
    """
    materialise("docrules/forms", tmp_path)
    _git_init(tmp_path)
    findings = _findings_by_rule(tmp_path, "prose")
    by_path = {finding.path: finding for finding in findings}
    assert "plural-underscore.py" not in by_path
    assert "noun-underscore-leading.py" not in by_path
    assert "'underscore'" in by_path["verb-underscore.py"].evidence
    assert "'underscore'" in by_path["verb-underscore-passive.py"].evidence


def test_banned_word_form_leverage_noun_is_silent_verb_fires(tmp_path: Path) -> None:
    """`leverage` is banned as a verb only: the noun ("more leverage on the bolt") is silent (D8.5).

    arch: D8.5
    """
    materialise("docrules/forms", tmp_path)
    _git_init(tmp_path)
    findings = _findings_by_rule(tmp_path, "prose")
    by_path = {finding.path: finding for finding in findings}
    assert "noun-leverage.py" not in by_path
    assert "'leverage'" in by_path["verb-leverage.py"].evidence


def test_banned_word_matches_regardless_of_case(tmp_path: Path) -> None:
    """A capitalised banned word still matches: the scan ignores case (D5.4).

    Guards `re.IGNORECASE` in `_entry_pattern` (docrules.py:204): without it,
    this capitalised word would be missed.

    arch: D5.4
    """
    _git_init(tmp_path)
    word = _banned_word(0)
    (tmp_path / "notes.md").write_text(
        f"{word.capitalize()} starts this sentence\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "prose")
    assert len(findings) == 1
    assert f"{word!r} (line 1)" in findings[0].evidence


# -- C6: CHANGELOG.md shape, docs = "full" only --------------------------


_GOOD_CHANGELOG = textwrap.dedent(
    """\
    # Changelog

    ## [Unreleased]

    ### Added

    - nothing yet

    ## [1.1.0] - 2026-01-02

    ### Fixed

    - a bug

    ## [1.0.0] - 2026-01-01

    ### Added

    - first release
    """
)


def test_well_formed_changelog_gives_no_finding(tmp_path: Path) -> None:
    """A changelog that follows the Keep a Changelog shape gives no finding (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    (tmp_path / "CHANGELOG.md").write_text(_GOOD_CHANGELOG, encoding="utf-8")
    assert _findings_by_rule(tmp_path, "changelog") == []


def test_changelog_missing_unreleased_is_an_error(tmp_path: Path) -> None:
    """A changelog with no `## [Unreleased]` heading is a `changelog` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    text = _GOOD_CHANGELOG.replace(
        "## [Unreleased]\n\n### Added\n\n- nothing yet\n\n", ""
    )
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "changelog")
    assert any("Unreleased" in finding.evidence for finding in findings)
    assert all(
        finding.severity == "error" and finding.auto is False for finding in findings
    )


def test_changelog_bad_type_heading_is_an_error(tmp_path: Path) -> None:
    """A `### <type>` heading outside the closed list is a `changelog` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    text = _GOOD_CHANGELOG.replace("### Fixed", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "changelog")
    assert any("Tweaked" in finding.evidence for finding in findings)


def test_changelog_versions_out_of_order_is_an_error(tmp_path: Path) -> None:
    """A version heading not below the one before it is a `changelog` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    text = _GOOD_CHANGELOG.replace("## [1.0.0] - 2026-01-01", "## [1.2.0] - 2026-01-01")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "changelog")
    assert any("not below" in finding.evidence for finding in findings)


def test_changelog_id_holds_the_line_fingerprint_and_survives_a_line_shift(
    tmp_path: Path,
) -> None:
    """A `changelog` id is `changelog:<path>:<fp>`; a line above the defect keeps it (D15.8).

    `line` holds the line number. Equal defect lines get `<fp>`, `<fp>:2` and
    `<fp>:3` in file order.

    arch: D15.3, D15.8
    """
    from trueup.findings import line_fingerprint

    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    text = _GOOD_CHANGELOG.replace("### Fixed", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    (first,) = _findings_by_rule(tmp_path, "changelog")
    fp = line_fingerprint("CHANGELOG.md", "### Tweaked")
    assert first.id == f"changelog:CHANGELOG.md:{fp}"
    number = text.splitlines().index("### Tweaked") + 1
    assert first.line == number

    shifted = text.replace("## [Unreleased]", "Notes.\n\n## [Unreleased]", 1)
    (tmp_path / "CHANGELOG.md").write_text(shifted, encoding="utf-8")
    (moved,) = _findings_by_rule(tmp_path, "changelog")
    assert (moved.id, moved.line) == (first.id, number + 2)

    twice = text.replace("### Added", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(twice, encoding="utf-8")
    ids = [finding.id for finding in _findings_by_rule(tmp_path, "changelog")]
    assert sorted(ids) == sorted([first.id, f"{first.id}:2", f"{first.id}:3"])


def test_refcheck_findings_carry_the_line_of_the_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each `refcheck` finding holds the line of its failure line in `line` (D15.8).

    arch: D15.3, D15.8
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _bundled(monkeypatch, tmp_path, _FAKE_REF_CHECK)
    monkeypatch.chdir(tmp_path)
    findings = _findings_by_rule(root, "refcheck")
    assert findings
    assert all(finding.line == int(finding.id.split(":")[2]) for finding in findings)


def test_changelog_skipped_when_missing(tmp_path: Path) -> None:
    """No CHANGELOG.md gives no `changelog` finding: `trueup.health` covers that (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    assert _findings_by_rule(tmp_path, "changelog") == []


def test_changelog_not_checked_in_readme_docs_mode(tmp_path: Path) -> None:
    """`docs = "readme"` does not run the changelog shape check (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"readme"')
    text = _GOOD_CHANGELOG.replace("### Fixed", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    assert _findings_by_rule(tmp_path, "changelog") == []


def test_changelog_under_an_ignore_glob_gives_no_finding(tmp_path: Path) -> None:
    """A `CHANGELOG.md` matched by `ignore` gives no `changelog` finding (D5.4, D2.2).

    `_changelog_findings` gates on `path in survey.files`, the same check
    `_readme_length_finding` uses, so an ignored `CHANGELOG.md` is never
    read even though it sits on disk.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"', ignore='["CHANGELOG.md"]')
    text = _GOOD_CHANGELOG.replace("### Fixed", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    assert _findings_by_rule(tmp_path, "changelog") == []


# -- P7 / P8: page status, docs = "full" only ----------------------------


def _write_page(
    root: Path, relative: str, front_matter: str, body: str = "content\n"
) -> None:
    """Write one Markdown page under `docs/`, with a front-matter block.

    Args:
        root: The repository root.
        relative: The page's path, relative to `docs/`.
        front_matter: The lines between the `---` markers, already joined.
        body: The page's body, after the front matter.
    """
    path = root / "docs" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front_matter}\n---\n\n{body}", encoding="utf-8")


def test_superseded_with_a_working_link_gives_no_finding(tmp_path: Path) -> None:
    """`status: superseded` with a `superseded_by` id that exists gives no finding (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    _write_page(
        tmp_path,
        "new.md",
        "id: new\ntype: reference\nstatus: current\nlast_reviewed: 2026-01-01",
    )
    _write_page(
        tmp_path,
        "old.md",
        "id: old\ntype: reference\nstatus: superseded\nsuperseded_by: new",
    )
    assert _findings_by_rule(tmp_path, "superseded") == []


def test_superseded_with_no_link_is_an_error(tmp_path: Path) -> None:
    """`status: superseded` with no `superseded_by` field is a `superseded` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    _write_page(tmp_path, "old.md", "id: old\ntype: reference\nstatus: superseded")
    findings = _findings_by_rule(tmp_path, "superseded")
    assert len(findings) == 1
    assert findings[0].id == "superseded:docs/old.md"
    assert findings[0].severity == "error"


def test_superseded_pointing_at_an_unknown_id_is_an_error(tmp_path: Path) -> None:
    """A `superseded_by` id no page declares is a `superseded` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    _write_page(
        tmp_path,
        "old.md",
        "id: old\ntype: reference\nstatus: superseded\nsuperseded_by: ghost",
    )
    findings = _findings_by_rule(tmp_path, "superseded")
    assert len(findings) == 1


def test_stale_current_page_is_an_error(tmp_path: Path) -> None:
    """`status: current` with a `last_reviewed` older than `stale_days` is a `stale` error (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"', stale_days="30")
    _write_page(
        tmp_path,
        "page.md",
        "id: page\ntype: reference\nstatus: current\nlast_reviewed: 2020-01-01",
    )
    findings = _findings_by_rule(tmp_path, "stale")
    assert len(findings) == 1
    assert findings[0].id == "stale:docs/page.md"
    assert findings[0].severity == "error"


def test_fresh_current_page_gives_no_stale_finding(tmp_path: Path) -> None:
    """A `last_reviewed` within `stale_days` gives no `stale` finding (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"', stale_days="36500")
    _write_page(
        tmp_path,
        "page.md",
        "id: page\ntype: reference\nstatus: current\nlast_reviewed: 2020-01-01",
    )
    assert _findings_by_rule(tmp_path, "stale") == []


def test_stale_page_under_an_ignore_glob_gives_no_finding(tmp_path: Path) -> None:
    """A stale page whose path matches `ignore` gives no `stale` finding (D5.4, D2.2).

    `_docs_pages` reads its pages from `survey.files`, so a page an
    `ignore` glob drops from the survey never reaches P7/P8, the same
    floor `_readme_length_finding` and `_changelog_findings` hold.

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"', stale_days="30", ignore='["docs/old/**"]')
    _write_page(
        tmp_path,
        "old/page.md",
        "id: page\ntype: reference\nstatus: current\nlast_reviewed: 2020-01-01",
    )
    assert _findings_by_rule(tmp_path, "stale") == []


def test_page_checks_not_run_in_readme_docs_mode(tmp_path: Path) -> None:
    """`docs = "readme"` does not run the superseded/stale page checks (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"readme"', stale_days="1")
    _write_page(
        tmp_path,
        "page.md",
        "id: page\ntype: reference\nstatus: current\nlast_reviewed: 2020-01-01",
    )
    assert _findings_by_rule(tmp_path, "stale") == []


# -- ref_check fold-in ----------------------------------------------------


_FAKE_REF_CHECK = textwrap.dedent(
    """\
    import os
    import sys

    def main() -> int:
        root = sys.argv[sys.argv.index("--root") + 1]
        print(f"docs/ARCHITECTURE.md:3: [unknown-id] section cites D9.9: {root}")
        print(f"README.md:1: [no-description] no paragraph after the title")
        print(f"README.md:1: [no-section] section is absent: Install")
        print(f"README.md:1: [no-section] section is absent: Usage")
        print(f"README.md:1: [broken-link] no such file")
        print(f"README.md:1: [broken-link] no such file")
        print(f"cwd.txt:1: [cwd] {os.getcwd()}")
        print("ref_check: 7 failures, 0 references")
        return 1

    raise SystemExit(main())
    """
)

_HOSTILE_REF_CHECK = textwrap.dedent(
    """\
    import pathlib
    pathlib.Path("PWNED").write_text("x")
    print("README.md:1: [pwned] the target's own copy ran")
    raise SystemExit(1)
    """
)


def _bundled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> None:
    """Point `docrules._BUNDLED_REF_CHECK` at a stand-in script outside the target.

    The stand-in only has to honour `ref_check.py`'s own contract (accept
    `--root`, print `<path>:<line>: [<kind>] <detail>` failure lines, set
    the exit code): docrules only runs it as a separate process and reads
    its output, it never imports or edits it (I-26).

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        tmp_path: A directory outside the target to hold the script.
        text: The script's source.
    """
    script = tmp_path / "bundled" / "ref_check.py"
    script.parent.mkdir()
    script.write_text(text, encoding="utf-8")
    monkeypatch.setattr(docrules, "_BUNDLED_REF_CHECK", script)


def test_refcheck_never_runs_the_targets_own_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check` runs the bundled `ref_check.py`, never the target's, and writes nothing (I-18).

    The target's copy writes a file named `PWNED` into its working
    directory when run. Neither the target nor the caller's working
    directory may hold it afterwards, and no finding comes from it.

    arch: D5.4, I-18
    """
    root = tmp_path / "repo"
    caller = tmp_path / "caller"
    root.mkdir()
    caller.mkdir()
    _git_init(root)
    (root / "ref_check.py").write_text(_HOSTILE_REF_CHECK, encoding="utf-8")
    monkeypatch.chdir(caller)
    findings = _findings_by_rule(root, "refcheck")
    assert not (caller / "PWNED").exists()
    assert not (root / "PWNED").exists()
    assert all("pwned" not in finding.id for finding in findings)


def test_refcheck_ids_are_unique_and_the_run_sits_in_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each failure line is one `refcheck` error with its own id, and the checker runs in the root (D5.4).

    arch: D5.4
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _bundled(monkeypatch, tmp_path, _FAKE_REF_CHECK)
    monkeypatch.chdir(tmp_path)
    findings = _findings_by_rule(root, "refcheck")
    ids = [finding.id for finding in findings]
    assert sorted(ids) == sorted(
        [
            "refcheck:docs/ARCHITECTURE.md:3:unknown-id",
            "refcheck:README.md:1:no-description",
            "refcheck:README.md:1:no-section:Install",
            "refcheck:README.md:1:no-section:Usage",
            "refcheck:README.md:1:broken-link:no-such-file:1",
            "refcheck:README.md:1:broken-link:no-such-file:2",
            "refcheck:cwd.txt:1:cwd",
        ]
    )
    assert all(
        finding.severity == "error" and finding.auto is False for finding in findings
    )
    first = next(
        finding for finding in findings if finding.path == "docs/ARCHITECTURE.md"
    )
    assert first.evidence.endswith(str(root.resolve()))
    cwd = next(finding for finding in findings if finding.path == "cwd.txt")
    assert cwd.evidence == f"cwd.txt:1: [cwd] {root.resolve()}"


def test_refcheck_fold_in_runs_the_bundled_copy(tmp_path: Path) -> None:
    """The real bundled `ref_check.py` runs to completion on a small target (D5.4).

    The run uses every switch of the checker (D8.1), so the small repository
    holds what checks h and i ask for: a README with the standard sections
    and the index link, a licence file, and a `docs/README.md` with front
    matter. Then the real bundled copy has nothing to fail on, and this
    proves the run completes (exit 0, no finding), not any one failure
    line.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text(
        "---\nid: docs-index\ntype: reference\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-09-22\n---\n\n# Index\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Demo\n\nDemo is a tree. Read the [index](docs/README.md).\n\n"
        "## Install\n\nCopy it.\n\n## Usage\n\nRun it.\n\n## License\n\nMIT.\n",
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    assert docrules._BUNDLED_REF_CHECK.is_file()
    assert _findings_by_rule(tmp_path, "refcheck") == []


def test_refcheck_fold_in_reports_an_unparseable_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero exit with no parseable failure line gives one `refcheck:` finding (D5.4).

    The stand-in exits 1: exit 2 is the checker's own error and gives a
    `refcheck-run:` row (D15.1).

    arch: D5.4, D15.1
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _bundled(
        monkeypatch,
        tmp_path,
        "import sys\nprint('boom', file=sys.stderr)\nraise SystemExit(1)\n",
    )
    findings = _findings_by_rule(root, "refcheck")
    assert len(findings) == 1
    assert findings[0].id == "refcheck:"
    assert "boom" in findings[0].evidence


# -- docs mode gate on the module as a whole ------------------------------


def test_readme_and_banned_words_still_run_in_readme_docs_mode(tmp_path: Path) -> None:
    """`docs = "readme"` still runs R10 and the banned-word floor (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"readme"')
    (tmp_path / "README.md").write_text("line\n" * 201, encoding="utf-8")
    (tmp_path / "notes.md").write_text(
        f"this holds {_banned_word(0)}\n", encoding="utf-8"
    )
    assert _findings_by_rule(tmp_path, "readme-length") != []
    assert _findings_by_rule(tmp_path, "prose") != []


def test_no_config_resolves_docs_by_tier(tmp_path: Path) -> None:
    """`Config`'s own default `docs = "auto"` gives readme at T0 and the full docrules set at T2 (D5.4, D12.9).

    The owner changed the default from `full` to `auto` (D12.9): with no
    `trueup.toml` a T0 repository gets no changelog check, and a config
    that only sets the tier to T2 runs it.

    arch: D5.4, D12.9
    """
    _git_init(tmp_path)
    text = _GOOD_CHANGELOG.replace("### Fixed", "### Tweaked")
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    assert _findings_by_rule(tmp_path, "changelog") == []
    _write_config(tmp_path, tier='"T2"')
    assert _findings_by_rule(tmp_path, "changelog") != []


_CHILD_SCRIPT = textwrap.dedent(
    """\
    import dataclasses, json, sys
    from pathlib import Path
    from trueup import docrules, survey
    from trueup.config import load

    root = Path(sys.argv[1])
    found = docrules.docrules_findings(survey.run(root), load(root))
    print(json.dumps([dataclasses.asdict(finding) for finding in found]))
    """
)
"""Run `docrules_findings` on one root in a fresh interpreter and print it as JSON, in list order."""


def test_docrules_findings_is_deterministic(tmp_path: Path) -> None:
    """Fresh interpreters with different hash seeds give the same findings in the same order (I-21).

    Each run is a separate process with its own `PYTHONHASHSEED`, so a set
    or dict order that depends on the seed would show up as a different
    list or a different evidence line. The fixture tree puts several banned
    words on one line and spreads them over three files, so both the
    evidence order and the file order are exercised. The child runs the
    house profile, since the tree has no `trueup.toml` (D15.6).

    arch: D5.4, I-21, D15.6
    """
    materialise("docrules/order", tmp_path)
    _git_init(tmp_path)
    outputs = []
    for seed in ("0", "1", "2", "3", "4", "5"):
        # D15.6: the fixture has no trueup.toml; the test is about house rows.
        env = {**os.environ, "PYTHONHASHSEED": seed, "TRUEUP_PROFILE": "house"}
        result = subprocess.run(
            [sys.executable, "-c", _CHILD_SCRIPT, str(tmp_path)],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout)
    prose = [
        finding for finding in json.loads(outputs[0]) if finding["rule"] == "prose"
    ]
    assert len(prose) == 3, "one prose finding per fixture file"
    assert all(output == outputs[0] for output in outputs)


def test_first_hits_sorts_by_line_then_word() -> None:
    """`_first_hits` orders its pairs by line, then by word, not by list order (I-21).

    arch: D5.4, I-21
    """
    lines = ["zebra and apple", "", "mango"]
    hits = docrules._first_hits(lines, ("mango", "zebra", "apple"))
    assert hits == [("apple", 1), ("zebra", 1), ("mango", 3)]


def test_docrules_findings_sort_with_the_shared_helper(tmp_path: Path) -> None:
    """`docrules_findings` returns an unsorted list that `sorted_findings` can order (D5.4).

    `hygiene.hygiene_findings` and `health.health_findings` return theirs
    the same way, so a caller merges all three and sorts once. Ordering
    findings is `trueup.findings`' own contract (see `test_check.py`'s I-21
    coverage of the merged, sorted plan); this test only checks the shape
    `docrules_findings` hands that helper.

    arch: D5.4
    """
    from trueup.findings import sorted_findings

    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    (tmp_path / "README.md").write_text("line\n" * 201, encoding="utf-8")
    (tmp_path / "notes.md").write_text(
        f"this holds {_banned_word(0)}\n", encoding="utf-8"
    )
    findings = _findings(tmp_path)
    ordered = sorted_findings(findings)
    assert [finding.id for finding in ordered] == sorted(
        finding.id for finding in findings
    )


def test_refcheck_unregistered_action_names_local_tags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `unregistered` failure's action names `[refs] local_tags`; another kind keeps the plain action (D8.7).

    arch: D8.7
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _bundled(
        monkeypatch,
        tmp_path,
        textwrap.dedent(
            """\
            print("src/x.py:1: [unregistered] marker not in the registry: X1")
            print("README.md:1: [no-section] section is absent: Install")
            print("ref_check: 2 failures, 0 references")
            raise SystemExit(1)
            """
        ),
    )
    by_id = {finding.id: finding for finding in _findings_by_rule(root, "refcheck")}
    assert "local_tags" in by_id["refcheck:src/x.py:1:unregistered"].action
    assert "trueup.toml" in by_id["refcheck:src/x.py:1:unregistered"].action
    assert "local_tags" not in by_id["refcheck:README.md:1:no-section"].action


# -- D8.4: a block that quotes the banned list ----------------------------


def _quoted_list_doc(real_use: str = "") -> str:
    """Build a Markdown page whose list items and one paragraph quote the banned list.

    Args:
        real_use: Extra Markdown appended after the quoted blocks, for a
            real use that must still fire. Empty for none.

    Returns:
        The page text. The banned words come from `_banned_word`, so this
        test module holds none of them in a comment.
    """
    words = [_banned_word(index) for index in range(5)]
    return (
        textwrap.dedent(
            """\
            # Rules

            - Prose is plain English: short sentences, active voice.
            - Never use: {w0}, {w1}, {w2} or {w3} as verbs,
              and {w4}.
            - Tests use real files.

            Comments and docs: no banned vocabulary ({w0}, {w1}, {w2}). Say
            the plain thing.

            1. Banned words: {w0}, {w1},
               {w2} (say the plain thing).
            2. Another item.
            """
        ).format(w0=words[0], w1=words[1], w2=words[2], w3=words[3], w4=words[4])
        + real_use
    )


def test_a_markdown_block_that_quotes_the_list_gives_no_finding(tmp_path: Path) -> None:
    """A list item or paragraph with a cue (`banned`, `never use`, ...) states the rule; it gives no finding (D8.4).

    The cue and the words sit in one block: the item line with its indented
    continuation lines, or the paragraph. The target-rust run of 2026-10-07 hit
    four such blocks (FABLE.md, docs/BRIEF.md, two survey records).

    arch: D8.4
    """
    _git_init(tmp_path)
    (tmp_path / "RULES.md").write_text(_quoted_list_doc(), encoding="utf-8")
    assert _findings_by_rule(tmp_path, "prose") == []


def test_a_real_use_beside_a_quoted_list_still_fires(tmp_path: Path) -> None:
    """A block with no cue fires, also when the page quotes the list elsewhere (D8.4).

    The evidence names the real use's line, not the quoted list's line.

    arch: D8.4
    """
    _git_init(tmp_path)
    word = _banned_word(0)
    page = _quoted_list_doc(f"\n- This design is {word}, which is a real use.\n")
    (tmp_path / "RULES.md").write_text(page, encoding="utf-8")
    (findings,) = _findings_by_rule(tmp_path, "prose")
    line = page.splitlines().index(f"- This design is {word}, which is a real use.") + 1
    assert findings.evidence == f"{word!r} (line {line})"


def test_a_cue_in_a_source_comment_does_not_silence_the_word(tmp_path: Path) -> None:
    """The quoted-list rule is for Markdown only; a source comment keeps the plain rule (D8.4).

    Vale's `BlockIgnores` does not apply to a code format, so the two
    engines agree only when `check` keeps the plain rule in comments too.

    arch: D8.4
    """
    _git_init(tmp_path)
    word = _banned_word(0)
    (tmp_path / "rules.py").write_text(
        f"# Never use: {word}.\nX = 1\n", encoding="utf-8"
    )
    (finding,) = _findings_by_rule(tmp_path, "prose")
    assert finding.evidence == f"{word!r} (line 1)"


@pytest.mark.parametrize(
    "name,text,fires",
    quoted_list_shapes(),
    ids=lambda value: value if isinstance(value, str) and " " in value else None,
)
def test_quoted_list_shapes_fire_on_the_expected_lines(
    tmp_path: Path, name: str, text: str, fires: set[int]
) -> None:
    """Each block shape of D8.4 fires on the expected lines and on no other (D8.4).

    `tests/test_rulesets.py` runs the same table through a real `vale` run.

    arch: D8.4
    """
    _git_init(tmp_path)
    (tmp_path / "RULES.md").write_text(text, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "prose")
    fired = {
        int(number)
        for finding in findings
        for number in re.findall(r"\(line (\d+)\)", finding.evidence)
    }
    assert fired == fires, name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))


def test_refcheck_ids_come_from_the_checkers_failure_ids() -> None:
    """`docrules` builds a `refcheck:` id with `ref_check.failure_ids`, the one id function (D9.2).

    arch: D9.2
    """
    from trueup import ref_check

    lines = [
        "README.md:1: [no-section] section is absent: Install",
        "README.md:1: [no-section] section is absent: Usage",
        "a.py:3: [unregistered] -: marker not in the registry: X1",
    ]
    matches = [docrules._REFCHECK_FAILURE_LINE.match(line) for line in lines]
    assert all(match is not None for match in matches)
    failures = [
        ref_check.Failure(
            match.group("path"),
            int(match.group("line")),
            match.group("kind"),
            match.group("detail"),
        )
        for match in matches
    ]
    assert docrules._refcheck_ids(matches) == [
        "refcheck:" + item for item in ref_check.failure_ids(failures)
    ]
    assert not hasattr(docrules, "_ID_SEPARATORS")


# -- D12.9 step 6: the refcheck fold-in runs in both docs modes -------------

_CONFIG_SPY = textwrap.dedent(
    """\
    import sys
    from pathlib import Path
    args = sys.argv[1:]
    config = Path(args[args.index("--config") + 1]).read_text(encoding="utf-8")
    Path(__file__).with_name("seen.toml").write_text(config, encoding="utf-8")
    print("src/x.py:1: [unregistered] -: marker not in the registry: X1")
    raise SystemExit(1)
    """
)
"""A stand-in checker that saves the config text it gets beside itself and reports one failure."""


def _spy_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: Path
) -> tuple[list, str]:
    """Run the docrules over `root` with the config spy, and give the findings and the config text.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        tmp_path: A directory outside the target for the stand-in.
        root: The repository root.

    Returns:
        The `refcheck` findings and the config text the checker got.
    """
    _bundled(monkeypatch, tmp_path, _CONFIG_SPY)
    found = _findings_by_rule(root, "refcheck")
    seen = (tmp_path / "bundled" / "seen.toml").read_text(encoding="utf-8")
    return found, seen


def test_refcheck_runs_in_readme_mode_with_the_tier_set_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `docs = "readme"` at T2 the fold-in runs, with the `ref_check.toml` text of readme mode (D12.9).

    arch: D12.9
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _write_config(root, tier='"T2"', docs='"readme"')
    found, seen = _spy_config(monkeypatch, tmp_path, root)
    assert [finding.id for finding in found] == ["refcheck:src/x.py:1:unregistered"]
    assert "registry = true" in seen
    assert "readme = false" in seen
    assert "[keep]" not in seen


def test_refcheck_at_t1_without_a_docs_page_runs_with_no_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At T1 with no page under `docs/`, `ref_check.toml` is not in the set, so the checker gets the absent-file config (D12.9).

    arch: D12.9
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (root / "README.md").write_text("# X\n", encoding="utf-8")
    assert survey_mod.run(root).tier == "T1"
    found, seen = _spy_config(monkeypatch, tmp_path, root)
    assert [finding.id for finding in found] == ["refcheck:src/x.py:1:unregistered"]
    assert "true" not in seen


def test_refcheck_at_t1_with_a_docs_page_runs_with_the_readme_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At T1 a page under `docs/` puts `ref_check.toml` in the set; `docs = "auto"` gives the readme switches (D12.9).

    arch: D12.9
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    assert survey_mod.run(root).tier == "T1"
    _found, seen = _spy_config(monkeypatch, tmp_path, root)
    assert "registry = true" in seen
    assert "layout = false" in seen
    assert "readme = false" in seen


def test_prefilter_gives_the_same_hits_as_the_per_entry_loop() -> None:
    """The pre-filter changes no row of the banned-word scan.

    arch: D14.14, D14.15
    """
    words = docrules._load_banned_words()
    assert docrules._prefilter(words) is not None
    lines = [
        "",
        "We leverage the cache and harness every tool.",
        "The underscore character is fine; leverage is a noun here.",
        "A ROBUST plan that is Seamless.",
        "plain text with no banned word",
        "It underscores the point and will unlock new value.",
    ]
    expected: list[tuple[str, int]] = []
    for entry in words:
        word, _ = docrules._split_entry(entry)
        pattern = docrules._entry_pattern(entry)
        for number, line in enumerate(lines, start=1):
            if line and pattern.search(line):
                expected.append((word, number))
                break
    expected.sort(key=lambda hit: (hit[1], hit[0]))
    assert expected
    assert docrules._first_hits(lines, words) == expected


def test_prefilter_skips_a_list_with_a_back_reference() -> None:
    """A back reference in an entry turns the pre-filter off, not the scan.

    arch: D14.14, D14.15
    """
    words = ("again => (ab)\\1",)
    assert docrules._prefilter(words) is None
    assert docrules._first_hits(["x abab y"], words) == [("again", 1)]


def test_prose_pass_reads_no_file_of_another_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prose pass tests the path before it reads the file.

    arch: D14.14, D14.15
    """
    (tmp_path / "data.bin").write_text("robust\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("A robust note.\n", encoding="utf-8")
    read: list[str] = []
    real_read = docrules._read_text

    def spy(path: Path) -> str | None:
        read.append(path.name)
        return real_read(path)

    monkeypatch.setattr(docrules, "_read_text", spy)
    _git_init(tmp_path)
    surveyed = survey_mod.run(tmp_path)
    assert {"data.bin", "notes.md"} <= set(surveyed.files)
    findings = docrules._prose_findings(surveyed, docrules._load_banned_words())
    assert [finding.id for finding in findings] == ["prose:notes.md"]
    assert "data.bin" not in read


def test_banned_words_follows_the_prose_keys(tmp_path: Path) -> None:
    """`banned_words` gives the one list in force for each `[prose] banned` value.

    arch: D14.4
    """
    from trueup.config import Config

    builtin = docrules._load_banned_words()
    assert builtin
    assert docrules.banned_words(None) == builtin
    assert docrules.banned_words(Config()) == builtin
    assert docrules.banned_words(Config(prose_banned="off")) == ()
    assert docrules.banned_words(
        Config(prose_banned="off", prose_extra=("frobnicate",))
    ) == ("frobnicate",)
    assert docrules.banned_words(Config(prose_extra=("frobnicate",))) == (
        *builtin,
        "frobnicate",
    )
    own = tmp_path / "words.txt"
    own.write_text("zorble\n\n  quux => qu+x  \n", encoding="utf-8")
    assert docrules.banned_words(
        Config(prose_banned=str(own), prose_extra=("frobnicate",))
    ) == ("zorble", "quux => qu+x", "frobnicate")


def test_prose_off_skips_the_prose_pass(tmp_path: Path) -> None:
    """`[prose] banned = "off"` with no `extra` gives no `prose` finding.

    arch: D14.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[prose]\nbanned = "off"\n', encoding="utf-8"
    )
    (tmp_path / "notes.md").write_text(f"A {_banned_word(0)} note.\n", encoding="utf-8")
    assert _findings_by_rule(tmp_path, "prose") == []


def test_prose_extra_alone_is_the_list_when_banned_is_off(tmp_path: Path) -> None:
    """With `banned = "off"`, the `extra` entries are the whole list.

    arch: D14.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[prose]\nbanned = "off"\nextra = ["frobnicate"]\n',
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text(
        f"A {_banned_word(0)} note.\n\nWe frobnicate the cache.\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "prose")
    assert [finding.id for finding in findings] == ["prose:notes.md"]
    assert findings[0].evidence == "'frobnicate' (line 3)"


def test_prose_banned_path_replaces_the_builtin_list(tmp_path: Path) -> None:
    """A `[prose] banned` path is the base list; the built-in list is not read.

    arch: D14.4
    """
    _git_init(tmp_path)
    (tmp_path / "words.txt").write_text("zorble\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[prose]\nbanned = "words.txt"\n', encoding="utf-8"
    )
    (tmp_path / "notes.md").write_text(
        f"A {_banned_word(0)} note.\n\nThe zorble stays.\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "prose")
    assert [finding.evidence for finding in findings] == ["'zorble' (line 3)"]


def test_page_checks_read_the_docs_dir_in_force(tmp_path: Path) -> None:
    """`[layout] docs_dir` names the directory whose pages P7 and P8 read.

    arch: D14.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ndocs = "full"\nstale_days = 30\n\n[layout]\ndocs_dir = "manual"\n',
        encoding="utf-8",
    )
    front = "---\nid: {id}\ntype: reference\nstatus: current\nlast_reviewed: 2020-01-01\n---\n\nBody.\n"
    for directory in ("manual", "docs"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "page.md").write_text(
            front.format(id=directory), encoding="utf-8"
        )
    findings = _findings_by_rule(tmp_path, "stale")
    assert [finding.id for finding in findings] == ["stale:manual/page.md"]


def test_readme_action_names_the_docs_dir_in_force(tmp_path: Path) -> None:
    """The `readme-length` action names the `[layout] docs_dir` directory.

    arch: D14.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[layout]\ndocs_dir = "manual"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("line\n" * 300, encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "readme-length")
    assert len(findings) == 1
    assert (
        findings[0].action
        == "split the README into manual/ pages, and link them from it"
    )


def test_refcheck_exit_two_gives_one_run_error_with_the_last_stderr_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 2 of the checker gives one `refcheck-run:` error whose evidence is the last stderr line.

    arch: D15.1
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git_init(root)
    _bundled(
        monkeypatch,
        tmp_path,
        "import sys\nprint('first', file=sys.stderr)\n"
        "print('ref_check: internal error: boom', file=sys.stderr)\n"
        "raise SystemExit(2)\n",
    )
    findings = _findings_by_rule(root, "refcheck-run")
    assert [finding.id for finding in findings] == ["refcheck-run:"]
    assert findings[0].severity == "error"
    assert findings[0].evidence == "ref_check: internal error: boom"
    assert _findings_by_rule(root, "refcheck") == []


def _check_h_lines(case: str, tmp_path: Path) -> list[str]:
    """Run the bundled checker on one `tests/refs/fixtures` tree and give its failure lines.

    Args:
        case: The fixture tree under `tests/refs/fixtures/`.
        tmp_path: The directory to write the tree into.

    Returns:
        Each printed failure line, with no summary line.
    """
    from tests.refs.conftest import materialise as refs_materialise

    tree = refs_materialise(case, tmp_path / case)
    report = docrules.ref_check.run(tree)
    return [docrules.ref_check.format_failure(item) for item in report.failures]


def test_check_h_reads_a_block_list_and_a_quoted_scalar(tmp_path: Path) -> None:
    """A `key:` with `  - item` lines is a list, and one pair of matching quotes goes.

    arch: D15.18, D15.30
    """
    assert _check_h_lines("front-matter-block-list", tmp_path) == [
        "docs/reference/bad.md:4: [bad-field] value is not allowed: audience: [robot]"
    ]
    assert _check_h_lines("front-matter-quoted", tmp_path) == [
        "docs/reference/two.md:2: [bad-field] value is not allowed: id: \"two'"
    ]


def test_the_front_matter_parser_gives_lists_and_unquoted_scalars() -> None:
    """`ref_check._front_matter` gives a block list as `[a, b]` and drops one pair of quotes.

    arch: D15.18, D15.30
    """
    text = (
        "---\nid: 'page'\naudience:\n  - maintainer\n  - \"user\"\n"
        'title: "a \\"b\\" c"\nodd: "x\'\n---\n'
    )
    fields = docrules.ref_check._front_matter(text)
    assert fields == {
        "id": (2, "page"),
        "audience": (3, "[maintainer, user]"),
        "title": (6, 'a \\"b\\" c'),
        "odd": (7, "\"x'"),
    }
    assert docrules.ref_check._front_matter("---\nid: x\n  - stray\n---\n") is None


def test_docrules_pages_read_the_checkers_parser(tmp_path: Path) -> None:
    """A quoted `status: "superseded"` gives P7 its finding: docrules reads the checker's parser.

    arch: D15.30
    """
    _git_init(tmp_path)
    _write_config(tmp_path, docs='"full"')
    _write_page(tmp_path, "old.md", 'id: old\ntype: reference\nstatus: "superseded"')
    findings = _findings_by_rule(tmp_path, "superseded")
    assert [finding.id for finding in findings] == ["superseded:docs/old.md"]


def test_docrules_and_the_checker_give_the_same_pages(tmp_path: Path) -> None:
    """On a tree with no ignored page, docrules and the checker give one page set.

    arch: D15.30
    """
    _git_init(tmp_path)
    for rel in (
        "docs/README.md",
        "docs/guide.md",
        "docs/how-to/use.md",
        "docs/.hidden/skip.md",
        "docs/vendor/lib.md",
        "docs/notes.txt",
        "README.md",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Page\n", encoding="utf-8")
    survey = survey_mod.run(tmp_path)
    from_survey = sorted(docrules._docs_pages(survey, "docs"))
    from_disk = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in docrules.ref_check._docs_pages(tmp_path, (), "docs")
    )
    assert (
        from_survey
        == from_disk
        == [
            "docs/README.md",
            "docs/guide.md",
            "docs/how-to/use.md",
        ]
    )
    assert docrules.ref_check.is_doc_page("docs/how-to/use.md", "docs")
    assert not docrules.ref_check.is_doc_page("docs/vendor/lib.md", "docs")
    assert not docrules.ref_check.is_doc_page("docs/.hidden/skip.md", "docs")
    assert not docrules.ref_check.is_doc_page("docsx/page.md", "docs")
    assert not docrules.ref_check.is_doc_page("docs/notes.txt", "docs")


def test_refcheck_timeout_gives_one_refcheck_run_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checker run that passes 120 s gives one `refcheck-run:` error finding.

    arch: D15.23
    """

    def slow(*args: object, **kwargs: object) -> object:
        assert kwargs["timeout"] == 120
        raise subprocess.TimeoutExpired(cmd="ref_check.py", timeout=120)

    monkeypatch.setattr(docrules.subprocess, "run", slow)
    findings = docrules._refcheck_findings(tmp_path, "")
    assert [(f.id, f.severity) for f in findings] == [("refcheck-run:", "error")]
    assert findings[0].evidence == "ref_check.py timed out after 120 s"


_WARNING_REF_CHECK = textwrap.dedent(
    """\
    import sys

    def main() -> int:
        print("warning: src/lib.rs:1: [unknown-id] section cites D9.9")
        print("warning: src/lib.rs:4: [unknown-id] section cites D9.8")
        print("ref_check: 2 warnings from reader change rust-doc; add it to [refs] accepted_reader_changes to fail on them")
        print("ref_check: 0 failures, 2 references")
        return {code}

    sys.exit(main())
    """
)


@pytest.mark.parametrize("code", [0, 1])
def test_a_reader_change_gives_one_info_row_and_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """The warning lines of the checker give one info row with the count (D16.3, I-58).

    Exit 0 gives the row alone. Exit 1 gives the row and the real failures, and
    a `warning:` line is never read as a failure line.

    arch: D16.3, I-58
    """
    text = _WARNING_REF_CHECK.replace("{code}", str(code))
    if code:
        text = text.replace(
            'print("ref_check: 0',
            'print("README.md:1: [no-description] no paragraph")\n    print("ref_check: 1',
        )
    _bundled(monkeypatch, tmp_path, text)
    findings = docrules._refcheck_findings(tmp_path, "")
    rows = [f for f in findings if f.id == "refs-reader-change:rust-doc"]
    assert [(f.severity, f.rule, f.auto) for f in rows] == [
        ("info", "refs-reader-change", False)
    ]
    assert "2" in rows[0].evidence
    others = [f for f in findings if f is not rows[0]]
    assert [f.id for f in others] == (
        ["refcheck:README.md:1:no-description"] if code else []
    )
