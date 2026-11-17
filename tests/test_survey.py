"""Tests for `trueup.survey`: the inventory, the built-in line counter and the tier pick."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from trueup import survey as survey_mod
from trueup.config import ConfigError


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    `git ls-files --others --exclude-standard` (survey.py) works with no
    commit at all, which keeps the fixtures in this file small.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def test_run_lists_files_and_applies_ignore(tmp_path: Path) -> None:
    """`run` lists tracked and untracked files, minus the `ignore` globs, sorted.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text('"""A."""\n', encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nignore = ["src/**"]\n', encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.files == ("README.md", "trueup.toml")


def test_run_without_git_surveys_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root with no `.git` directory raises; decision D15.2 inverts the old empty survey.

    The test name is from before that decision. A git repository with no
    file still surveys as empty.

    arch: D5.4, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(ConfigError, match="not a git repository"):
        survey_mod.run(tmp_path)
    _git_init(tmp_path)
    assert survey_mod.run(tmp_path).files == ()


def test_matches_ignore_star_star_crosses_segments() -> None:
    """`**` matches across path segments, `*` stays inside one segment.

    arch: D5.4
    """
    assert survey_mod.matches_ignore("tests/fixtures/a/b.py", ("tests/fixtures/**",))
    assert not survey_mod.matches_ignore("tests/other/a.py", ("tests/fixtures/**",))
    assert survey_mod.matches_ignore("a.py", ("*.py",))
    assert not survey_mod.matches_ignore("src/a.py", ("*.py",))


_COMMENTED_PY = '''"""Module header."""


# a comment, not counted
def f(a: int) -> int:
    """Return a."""
    return a
'''


def test_builtin_counter_skips_comments_and_blanks(tmp_path: Path) -> None:
    """The built-in counter drops blank lines and lines that start with the language's comment leader.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text(_COMMENTED_PY, encoding="utf-8")
    result = survey_mod.run(tmp_path)
    stat = result.languages["python"]
    assert stat.files == 1
    # 3 non-blank, non-comment lines: the docstring line, "def f(...):",
    # the nested docstring line and "return a" -- the comment line and the
    # two blank lines are dropped.
    assert stat.code_lines == 4
    assert stat.present is False  # fewer than 50 code lines


def test_language_present_needs_a_file_and_fifty_lines(tmp_path: Path) -> None:
    """`present` is true only once a language has at least one file and 50 code lines.

    arch: D5.4
    """
    _git_init(tmp_path)
    lines = "\n".join(f"x{i} = {i}" for i in range(60))
    (tmp_path / "big.py").write_text(lines + "\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    stat = result.languages["python"]
    assert stat.code_lines == 60
    assert stat.present is True


def test_language_stats_use_tokei_when_it_is_on_the_path(tmp_path: Path) -> None:
    """`_language_stats` reads `tokei --output json` instead of the built-in counter, when `tokei` is on the path.

    `tokei` is not installed in this environment (run-wide fact 2), so this
    test can only skip, naming it; the built-in counter's own line-counting
    rules are checked directly by `test_builtin_counter_skips_comments_and_blanks`.

    arch: D5.4
    """
    if shutil.which("tokei") is None:
        pytest.skip("tool not installed: tokei")
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n\nx = 1\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.languages["python"].files == 1
    assert result.counter == "tokei"


def test_survey_counter_is_built_in_without_tokei(tmp_path: Path) -> None:
    """`Survey.counter` names `"built-in"` when `tokei` is not on the path.

    `tokei` is not installed in this environment (run-wide fact 2), so this
    is the counter every other test in this file exercises.

    arch: D5.4
    """
    if shutil.which("tokei") is not None:
        pytest.skip("tool installed: tokei")
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.counter == "built-in"


def test_tokei_scope_matches_builtin_for_ignored_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Language presence does not depend on which counter ran (arch: D6.14, I-13).

    `vendor/ignored.go` sits under an `ignore` glob, so `survey.run` never
    lists it in `files`. tokei still scans the whole tree by itself, so
    `_tokei_counts` must post-filter its report to `files` -- else tokei
    would count the ignored file and disagree with the built-in counter,
    which only ever sees `files`. This test forces the built-in branch with
    `monkeypatch` and compares it against whichever counter this machine's
    `shutil.which` actually finds, so it exercises the real tokei run when
    the tool is on the `PATH` and the built-in path when it is not.

    arch: D6.14, I-13
    """
    _git_init(tmp_path)
    (tmp_path / "keep.py").write_text(
        "\n".join(f"x{i} = {i}" for i in range(60)) + "\n", encoding="utf-8"
    )
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "ignored.go").write_text(
        "package v\n\n" + "\n".join(f"var x{i} = {i}" for i in range(60)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nignore = ["vendor/**"]\n', encoding="utf-8"
    )

    real = survey_mod.run(tmp_path)
    monkeypatch.setattr(survey_mod.shutil, "which", lambda name: None)
    builtin = survey_mod.run(tmp_path)

    real_present = {lang: stat.present for lang, stat in real.languages.items()}
    builtin_present = {lang: stat.present for lang, stat in builtin.languages.items()}
    assert real_present == builtin_present
    # The ignored file would make "go" present if either counter scoped to
    # the whole tree instead of the surveyed `files`.
    assert real_present["go"] is False
    assert real_present["python"] is True


def test_tools_reflects_shutil_which(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tools` holds one entry per executable any rule set names, found by `shutil.which`.

    The fake `which` finds only `ruff`, so the expected values do not come
    from the call that the code makes (D15.38).

    arch: D5.4, D15.38
    """
    _git_init(tmp_path)
    monkeypatch.setattr(
        survey_mod.shutil,
        "which",
        lambda name, *_args, **_kwargs: "/opt/bin/ruff" if name == "ruff" else None,
    )
    result = survey_mod.run(tmp_path)
    assert len(result.tools) > 1
    assert [name for name, found in result.tools.items() if found] == ["ruff"]


def test_root_entries_are_first_segments(tmp_path: Path) -> None:
    """`root_entries` holds the unique, sorted first path segment of every file.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text('"""A."""\n', encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text('"""B."""\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.root_entries == ("README.md", "src")


def test_root_entries_leave_out_an_entry_that_holds_only_trueup_files(
    tmp_path: Path,
) -> None:
    """A root entry counts only when it holds a file that trueup does not write (D12.9, I-43).

    The four files trueup still writes (`trueup.toml`, `ref_check.toml`,
    `.trueup-baseline.json`, `ref_check.py`) are not root entries. The old
    managed paths (`.editorconfig`, `.pre-commit-config.yaml`, `lint/`,
    `.claude/rules/trueup.md`, `.github/workflows/trueup.yml`) are the
    person's files after D14.8, so decision D15.37 counts them.

    arch: D12.9, I-43, D15.37
    """
    _git_init(tmp_path)
    own = (
        "trueup.toml",
        "ref_check.toml",
        "ref_check.py",
        ".trueup-baseline.json",
    )
    for path in (*own, "README.md"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("version = 1\n", encoding="utf-8")
    assert survey_mod.run(tmp_path).root_entries == ("README.md",)

    old = (
        ".editorconfig",
        ".pre-commit-config.yaml",
        "lint/python/ruff.toml",
        ".claude/rules/trueup.md",
        ".github/workflows/trueup.yml",
    )
    for path in old:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("version = 1\n", encoding="utf-8")
    assert survey_mod.run(tmp_path).root_entries == (
        ".claude",
        ".editorconfig",
        ".github",
        ".pre-commit-config.yaml",
        "README.md",
        "lint",
    )


def test_manifests_found_at_any_depth(tmp_path: Path) -> None:
    """`manifests` lists every `MANIFEST_NAMES` file `git` sees, at any depth.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "package.json").write_text("{}\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.manifests == ("pyproject.toml", "sub/package.json")


def test_tier_t0_for_a_tiny_repo(tmp_path: Path) -> None:
    """A handful of files, no manifest, no CI, gives T0.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.tier == "T0"


def test_tier_t1_for_a_small_repo_with_a_manifest(tmp_path: Path) -> None:
    """A repo with a manifest and 50 or fewer files, few contributors, no tag, gives T1.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    for i in range(10):
        (tmp_path / f"m{i}.py").write_text('"""M."""\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.tier == "T1"


def test_tier_t3_for_a_workspace(tmp_path: Path) -> None:
    """A Cargo `[workspace]` at the root gives T3, whatever the file count.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        "[workspace]\nmembers = []\n", encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.tier == "T3"


def test_tier_override_from_config(tmp_path: Path) -> None:
    """A `tier` value in `trueup.toml` other than `auto` wins over the picked tier.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        "[workspace]\nmembers = []\n", encoding="utf-8"
    )
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T1"\n', encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.tier == "T1"
    assert "trueup.toml" in result.tier_reason


def test_has_ci_true_for_a_github_workflow(tmp_path: Path) -> None:
    """A file under `.github/workflows/` with a YAML suffix sets `has_ci`.

    arch: D5.4
    """
    _git_init(tmp_path)
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("on: push\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.has_ci is True


def test_run_raises_config_error_for_invalid_trueup_toml(tmp_path: Path) -> None:
    """A `trueup.toml` that `config.load` rejects stops `run` with `ConfigError`.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T9"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        survey_mod.run(tmp_path)


def test_as_dict_is_json_ready(tmp_path: Path) -> None:
    """`as_dict` gives a mapping `json.dumps` can serialise, matching the survey's own fields.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    data = survey_mod.as_dict(result)
    text = json.dumps(data, sort_keys=True)
    reloaded = json.loads(text)
    assert reloaded["tier"] == result.tier
    assert reloaded["files"] == list(result.files)
    assert reloaded["languages"]["python"]["files"] == result.languages["python"].files


def test_pick_tier_reason_names_the_matched_condition() -> None:
    """`_pick_tier`'s reason names the condition it matched, for the report to show.

    arch: D5.4
    """
    tier, reason = survey_mod._pick_tier(
        override="auto",
        total_lang_files=0,
        file_count=0,
        manifests=(),
        workspace=True,
        contributors=0,
        has_ci=False,
        tags=0,
    )
    assert tier == "T3"
    assert "workspace" in reason


def test_managed_ref_check_counts_towards_no_language(tmp_path: Path) -> None:
    """The root `ref_check.py` that apply copies in leaves Python absent and the file count unchanged (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "ref_check.py").write_text("x = 1\n" * 200, encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ref_check.py").write_text("x = 1\n" * 60, encoding="utf-8")
    survey = survey_mod.run(tmp_path)
    assert survey.languages["python"].files == 1
    assert survey.languages["python"].code_lines == 60


def test_manifests_under_an_ignore_glob_do_not_count_for_the_tier(
    tmp_path: Path,
) -> None:
    """A manifest under an `ignore` glob leaves the survey, so it does not pick the tier (D8.8).

    A superrepository that keeps snapshot copies of its submodule's
    sources (run records under `.state/`, `pre/` trees) gets T3 from the
    copied manifests. The skill proposes `ignore` globs for such copies;
    this is the fact behind that advice.

    The three copies sit one level down, where a manifest still counts
    for the tier (D15.26).

    arch: D8.8, D15.26
    """
    _git_init(tmp_path)
    for name in ("a", "b", "c"):
        copy = tmp_path / f"copy-{name}" / "Cargo.toml"
        copy.parent.mkdir(parents=True)
        copy.write_text('[package]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("# A superrepository\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.tier == "T3"
    assert "3 manifests" in result.tier_reason
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nignore = ["copy-*/**"]\n', encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.manifests == ()
    assert result.tier != "T3"


# -- D12.9 step 7, I-43: trueup's own files never change the tier ----------

_TRUEUP_OWN_FILES: tuple[str, ...] = (
    "trueup.toml",
    "ref_check.toml",
    ".trueup-baseline.json",
    "ref_check.py",
)
"""The paths trueup still writes into a target (D15.37)."""


def _write_own_files(root: Path) -> None:
    """Write every path that trueup itself puts into a target, with small text.

    Args:
        root: The repository root.
    """
    for path in _TRUEUP_OWN_FILES:
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        text = "version = 1\n" if path == "trueup.toml" else "x = 1\n"
        full.write_text(text, encoding="utf-8")


def test_tier_t0_stays_t0_after_trueup_writes_its_files(tmp_path: Path) -> None:
    """A T0 repository stays T0 when trueup writes its own files (I-43).

    The files do not count towards the tier, but `Survey.files` still
    lists every path.

    arch: D12.9
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    assert survey_mod.run(tmp_path).tier == "T0"
    _write_own_files(tmp_path)
    after = survey_mod.run(tmp_path)
    assert after.tier == "T0"
    assert not after.has_ci
    assert set(_TRUEUP_OWN_FILES) <= set(after.files)


def test_tier_t1_stays_t1_when_trueup_files_pass_the_file_count(
    tmp_path: Path,
) -> None:
    """A 50-file T1 repository stays T1 when trueup's four files take it to 54 files (I-43).

    `ref_check.py` is not a tier file (D15.37), so the count stays 50.

    arch: D12.9, D15.37
    """
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    for i in range(49):
        (tmp_path / f"m{i}.py").write_text('"""M."""\n', encoding="utf-8")
    before = survey_mod.run(tmp_path)
    assert len(before.files) == 50 and before.tier == "T1"
    _write_own_files(tmp_path)
    after = survey_mod.run(tmp_path)
    assert len(after.files) > 50
    assert after.tier == "T1"


def test_a_workflow_of_the_target_still_counts_as_ci(tmp_path: Path) -> None:
    """A workflow of the target keeps `has_ci` true (D12.9).

    arch: D12.9
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "on: push\n", encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.has_ci
    assert result.tier != "T0"


def test_maven_tree_moves_from_t0_to_t1(tmp_path: Path) -> None:
    """Java files and a pom.xml give T1, not T0.

    arch: D14.13, D14.22
    """
    _git_init(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    for i in range(8):
        (tmp_path / f"A{i}.java").write_text("class A {}\n", encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert result.tier == "T1"
    assert "java" not in result.languages


def test_tier_extensions_keep_the_eight_languages_apart(tmp_path: Path) -> None:
    """TIER_EXTENSIONS is wider; LANGUAGE_EXTENSIONS keeps eight entries.

    arch: D14.13, D14.22
    """
    assert len(survey_mod.LANGUAGE_EXTENSIONS) == 8
    assert ".java" in survey_mod.TIER_EXTENSIONS
    assert ".py" in survey_mod.TIER_EXTENSIONS
    assert "requirements.txt" not in survey_mod.MANIFEST_NAMES


def test_has_ci_reads_the_wider_ci_paths(tmp_path: Path) -> None:
    """A GitLab file gives has_ci; a `.github/workflows/trueup.yml` gives it too.

    Decision D15.37 inverts the second half: trueup no longer writes that
    workflow (D14.8), so a file at that path is the person's CI.

    arch: D14.13, D14.22, D15.37
    """
    _git_init(tmp_path)
    (tmp_path / ".gitlab-ci.yml").write_text("a: 1\n", encoding="utf-8")
    assert survey_mod.run(tmp_path).has_ci is True
    other = tmp_path / "o"
    other.mkdir()
    _git_init(other)
    (other / ".github/workflows").mkdir(parents=True)
    (other / ".github/workflows/trueup.yml").write_text("a: 1\n", encoding="utf-8")
    assert survey_mod.run(other).has_ci is True


def test_own_paths_are_the_four_files_trueup_still_writes() -> None:
    """`TRUEUP_OWN_PATHS` holds four paths and `lint/` is not a trueup path.

    arch: D15.37
    """
    assert survey_mod.TRUEUP_OWN_PATHS == frozenset(
        {"trueup.toml", "ref_check.toml", ".trueup-baseline.json", "ref_check.py"}
    )
    assert survey_mod.is_trueup_path("ref_check.py")
    assert not survey_mod.is_trueup_path("lint/python/ruff.toml")
    assert not survey_mod.is_trueup_path(".editorconfig")


# -- D15.2 git is required ------------------------------------------------


def test_run_outside_git_raises_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root that is not in a git work tree raises, naming the root.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(ConfigError, match="not a git repository; trueup reads tracked"):
        survey_mod.run(tmp_path)


def test_in_work_tree_tells_a_repository_from_a_plain_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`in_work_tree` is true after `git init` and false before.

    arch: D15.1, D15.2
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert survey_mod.in_work_tree(tmp_path) is False
    _git_init(tmp_path)
    assert survey_mod.in_work_tree(tmp_path) is True


def test_a_branch_with_no_commit_has_zero_contributors(tmp_path: Path) -> None:
    """`git log` exits 128 on an unborn branch; the count is 0, not an error.

    arch: D15.1, D15.2
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    assert survey_mod._count_contributors(tmp_path) == 0
    assert survey_mod._count_tags(tmp_path) == 0
    assert survey_mod.run(tmp_path).files == ("README.md",)


def test_a_failed_git_tag_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A git failure in the tag count raises with the first stderr line.

    arch: D15.1, D15.2
    """

    def fail(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(
            128, "git", stderr="fatal: bad object\nsecond line"
        )

    monkeypatch.setattr(survey_mod.subprocess, "run", fail)
    with pytest.raises(ConfigError) as excinfo:
        survey_mod._count_tags(tmp_path)
    assert f"git tag failed in {tmp_path}: fatal: bad object" in str(excinfo.value)
    assert "second line" not in str(excinfo.value)


def test_a_package_json_that_is_not_utf8_counts_as_absent(tmp_path: Path) -> None:
    """A UTF-16 root `package.json` gives no workspace and no crash.

    arch: D15.1, D15.2
    """
    (tmp_path / "package.json").write_bytes('{"workspaces": []}'.encode("utf-16"))
    assert survey_mod._has_workspace(tmp_path) is False


# -- D15.26: tier manifests and other languages -----------------------------


def test_manifests_deep_or_under_a_test_directory_do_not_count_for_the_tier(
    tmp_path: Path,
) -> None:
    """Only a manifest at the root or one level down, outside test and fixture directories, counts.

    `manifests` keeps every path; only the tier count is narrower.

    arch: D15.26
    """
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    for rel in (
        "tests/fixtures/a/pyproject.toml",
        "tests/fixtures/b/pyproject.toml",
        "examples/pyproject.toml",
        "pkg/deep/pyproject.toml",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text('[project]\nname = "y"\n', encoding="utf-8")
    result = survey_mod.run(tmp_path)
    assert len(result.manifests) == 5
    assert result.tier != "T3"
    assert "manifests" not in result.tier_reason


def test_other_languages_are_listed_as_present_with_no_rule_set(
    tmp_path: Path,
) -> None:
    """A Java tree lists `java` as present with no rule set; `languages` keeps the eight.

    arch: D15.26
    """
    _git_init(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    source = tmp_path / "src" / "main" / "java"
    source.mkdir(parents=True)
    (source / "App.java").write_text("class App {}\n", encoding="utf-8")
    (tmp_path / "native.c").write_text(
        "int main(void) { return 0; }\n", encoding="utf-8"
    )
    result = survey_mod.run(tmp_path)
    assert result.other_languages == ("c", "java")
    assert len(result.languages) == 8
    data = survey_mod.as_dict(result)
    assert data["other_languages"] == {
        "c": "present, no rule set",
        "java": "present, no rule set",
    }
    json.dumps(data)


def test_survey_lists_the_tracked_files(tmp_path: Path) -> None:
    """`tracked` holds the paths of `git ls-files`; an untracked file is not in it.

    arch: D15.27
    """
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    result = survey_mod.run(tmp_path)
    assert result.files == ("a.py", "b.py")
    assert result.tracked == frozenset({"a.py"})
