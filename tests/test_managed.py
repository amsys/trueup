"""Tests for `trueup.managed`: the rendered files and the setup findings (arch: D5.6)."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from trueup import config, docrules, lint, managed, ref_check
from trueup.config import LANGUAGES, Config
from trueup.findings import Finding
from trueup.rulesets import JSCPD_HOOK, MANAGED_HEADER, VALE_FILES, VALE_HOOK
from trueup.survey import LangStat, Survey, matches_ignore

REPO = Path(__file__).resolve().parent.parent


def _survey(
    root: Path,
    tier: str = "T1",
    present: dict[str, int] | None = None,
    tools: dict[str, bool] | None = None,
) -> Survey:
    """Build a `Survey` by hand, so one test controls each field it reads.

    Args:
        root: The target root.
        tier: The tier to report.
        present: Language to code-line count; a count of 50 or more marks
            the language present. Languages not named have no files.
        tools: Tool name to whether it is on the path.

    Returns:
        The survey.
    """
    counts = present or {}
    languages = {
        language: LangStat(
            files=1 if language in counts else 0,
            code_lines=counts.get(language, 0),
            present=counts.get(language, 0) >= 50,
        )
        for language in LANGUAGES
    }
    return Survey(
        root=root,
        files=(),
        languages=languages,
        tools=tools or {},
        root_entries=(),
        manifests=(),
        workspace=False,
        contributors=1,
        has_ci=False,
        tags=0,
        tier=tier,
        tier_reason=f"{tier} (test)",
        counter="built-in",
    )


def _python_cfg(**changes: object) -> Config:
    """Give a config with Python in clean mode, plus any field changes.

    Args:
        **changes: `Config` fields to replace.

    Returns:
        The config.
    """
    return replace(Config(languages={"python": "clean"}), **changes)


def _write_all(root: Path, files: dict[str, str]) -> None:
    """Write every rendered file under `root`.

    Args:
        root: The target root.
        files: Repo path to text.
    """
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content.encode("utf-8"))


def test_render_lists_the_managed_files_of_a_python_clean_t2_repo(
    tmp_path: Path,
) -> None:
    """`render` gives `trueup.toml` and, in copy mode, the checker pair; nothing else.

    arch: D5.6, D14.8
    """
    survey = _survey(tmp_path, tier="T2")
    files = managed.render(_python_cfg(refs_mode="copy"), survey)
    assert set(files) == {"trueup.toml", "ref_check.py", "ref_check.toml"}
    assert list(files) == sorted(files)
    assert set(managed.render(_python_cfg(), survey)) == {"trueup.toml"}


def test_render_leaves_out_editorconfig_at_t0(tmp_path: Path) -> None:
    """`.editorconfig` is not in the set at T0, and not at T2 either (D14.8).

    arch: D5.6, D14.8
    """
    assert ".editorconfig" not in managed.render(
        _python_cfg(), _survey(tmp_path, tier="T0")
    )
    assert ".editorconfig" not in managed.render(
        _python_cfg(), _survey(tmp_path, tier="T2")
    )


def test_render_readme_docs_drops_vale_and_two_ref_check_switches(
    tmp_path: Path,
) -> None:
    """`docs = "readme"` renders no Vale file, no Vale hook, and turns layout and readme off.

    arch: D5.6, D14.8, D14.6
    """
    # D14.8: ref_check.toml is in the set in copy mode only.
    cfg = _python_cfg(docs="readme", refs_mode="copy")
    files = managed.render(cfg, _survey(tmp_path, tier="T2"))
    assert not set(VALE_FILES) & set(files)
    # D14.9: the Vale hook is a lint hook now; the target has no hook file.
    assert VALE_HOOK not in managed.lint_hooks(cfg)
    assert files["ref_check.toml"].splitlines()[1:] == [
        "[checks]",
        "registry = true",
        "comments = true",
        "links = true",
        "layout = false",
        "readme = false",
    ]
    full_cfg = _python_cfg(refs_mode="copy")
    full = managed.render(full_cfg, _survey(tmp_path, tier="T2"))  # D12.9
    assert "layout = true" in full["ref_check.toml"]
    assert "readme = true" in full["ref_check.toml"]
    assert VALE_HOOK in managed.lint_hooks(replace(full_cfg, docs="full"))


def test_render_skips_a_language_that_is_off(tmp_path: Path) -> None:
    """A language in `off` mode renders no rule-set file and no hook.

    arch: D5.6, D14.8, D14.6
    """
    cfg = _python_cfg(languages={"python": "off"})
    files = managed.render(cfg, _survey(tmp_path))
    assert "lint/python/ruff.toml" not in files
    assert not [hook for hook in managed.lint_hooks(cfg) if "ruff" in hook.entry]


def test_every_rendered_file_starts_with_the_header(tmp_path: Path) -> None:
    """Each rendered file but trueup.toml and the no-comment formats opens with the header, the checker copy included (D9.3).

    arch: D5.6, D9.3
    """
    every_language = {language: "strict" for language in LANGUAGES}
    files = managed.render(
        Config(languages=every_language, refs_mode="copy"), _survey(tmp_path)
    )
    assert "ref_check.py" in files
    for path, content in files.items():
        if path == "trueup.toml":
            continue
        header = managed.header_line(path)
        if header is None:
            assert path.startswith("lint/"), path
            assert path.endswith((".json", ".txt")), path
            continue
        assert MANAGED_HEADER in header
        assert content.split("\n", 1)[0] == header, path


def test_ref_check_is_the_bundled_copy_byte_for_byte(tmp_path: Path) -> None:
    """The rendered `ref_check.py` is the exact bytes of the copy inside `trueup/`.

    arch: D5.6, I-26
    """
    files = managed.render(_python_cfg(refs_mode="copy"), _survey(tmp_path))
    assert (
        files["ref_check.py"].encode("utf-8")
        == (REPO / "trueup" / "ref_check.py").read_bytes()
    )


def test_render_writes_the_checker_at_a_custom_refs_path(tmp_path: Path) -> None:
    """`[refs] path` moves the rendered checker's key; the default key drops out.

    arch: D5.3
    """
    cfg = _python_cfg(refs_mode="copy", refs_path="tools/checker.py")
    files = managed.render(cfg, _survey(tmp_path))
    assert "ref_check.py" not in files
    assert (
        files["tools/checker.py"].encode("utf-8")
        == (REPO / "trueup" / "ref_check.py").read_bytes()
    )


def test_file_finding_byte_equality_follows_refs_path(tmp_path: Path) -> None:
    """A custom `refs_path` module that differs from the bundled copy is a manual `warn`.

    arch: D5.3
    """
    cfg = _python_cfg(refs_mode="copy", refs_path="tools/checker.py")
    survey = _survey(tmp_path, present={"python": 80})
    _write_all(tmp_path, managed.render(cfg, survey))
    (tmp_path / "tools" / "checker.py").write_text("print('mine')\n", encoding="utf-8")
    finding = _ids(managed.setup_findings(survey, cfg))["file-managed:tools/checker.py"]
    assert (finding.severity, finding.auto) == ("warn", False)
    assert "ref_check.py" not in _ids(managed.setup_findings(survey, cfg))


def test_lint_hook_order_is_fixed_and_shared_hooks_appear_once(tmp_path: Path) -> None:
    """The hooks are in LANGUAGES order, then jscpd, then vale; eslint appears once.

    D14.9: the `ref-check` hook and the managed header went with the
    target's pre-commit file. D14.6: `lint_hooks` keeps the order and has
    no gitleaks hook, because `check` runs gitleaks for `secret-content`.

    arch: D5.6, I-21, D7.3, D14.9, D14.6
    """
    # D12.9: the renderer takes a resolved docs mode; full gives the Vale hook.
    cfg = Config(
        docs="full",
        languages={"python": "strict", "typescript": "clean", "vue": "clean"},
    )
    ids = [hook.id for hook in managed.lint_hooks(cfg)]
    assert ids == [
        "ruff-check",
        "ruff-format",
        "vulture",
        "interrogate",
        "complexipy",
        "pydoclint",
        "eslint",
        "vue-tsc",
        "jscpd",
        "vale",
    ]
    assert managed.lint_hooks(cfg) == managed.lint_hooks(cfg)


def test_lint_hooks_have_no_jscpd_without_a_strict_language(tmp_path: Path) -> None:
    """The duplication hook exists only when a language is strict; `render` never holds `lint/jscpd.json` (D14.8).

    arch: D5.5, D5.6, D14.8, D14.6
    """
    clean_cfg = _python_cfg()
    strict_cfg = _python_cfg(languages={"python": "strict"})
    assert JSCPD_HOOK not in managed.lint_hooks(clean_cfg)
    assert JSCPD_HOOK in managed.lint_hooks(strict_cfg)
    for cfg in (clean_cfg, strict_cfg):
        assert managed.JSCPD_PATH not in managed.render(cfg, _survey(tmp_path))


_PIN = re.compile(r"^\s*- uses: [\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40} # \S+$")
"""The I-32 form of one `uses:` line: owner, repo, optional path, SHA, tag comment."""

_FALLBACKS: tuple[str, ...] = (
    "pip-audit",
    "cargo audit",
    "npm audit --audit-level=high",
    "govulncheck ./...",
    "composer audit",
)
"""The five fallback audit commands that every CI render keeps as comments (D7.4 rule 5)."""

_LOCK_FILES: tuple[str, ...] = ("lint/ts/package-lock.json", "trueup/cli.py")
"""Survey files with one tracked lockfile, as this repository has."""

_CI_TEMPLATE = REPO / "trueup" / "templates" / "ci" / "trueup.yml"
"""The CI template; `render_ci` gives its text as it is (D14.9)."""


def test_ci_pins_every_action_to_a_commit_sha(tmp_path: Path) -> None:
    """Every `uses:` line of the CI text and the template ends in `@<40 hex> # <tag>`.

    D14.9: `render_ci` takes no argument and gives the template as it is.

    arch: D7.3, D7.4, I-32, D14.9
    """
    text = managed.render_ci()
    assert text == _CI_TEMPLATE.read_text(encoding="utf-8")
    uses = [line for line in text.splitlines() if "uses:" in line]
    assert len(uses) == 3
    for line in uses:
        assert _PIN.match(line), line
    assert "permissions:\n  contents: read\n" in text


def test_ci_has_the_osv_step_and_tells_when_to_remove_it(tmp_path: Path) -> None:
    """The CI text has one pinned osv-scanner step, after `trueup lint`, and a comment that says when to remove it.

    D14.9: the text reads no survey, so the person removes the step when
    the repository tracks no lockfile.

    arch: D7.3, D7.4, D14.9
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    text = managed.render_ci()
    steps = yaml.safe_load(text)["jobs"]["check"]["steps"]
    osv = [step for step in steps if "osv-scanner" in step.get("uses", "")]
    assert len(osv) == 1
    assert osv[0]["with"]["scan-args"].split() == ["--recursive", "./"]
    assert steps.index(osv[0]) == len(steps) - 1
    assert "Remove this step when the repository tracks no lockfile." in text


def test_ci_keeps_the_five_fallback_comments(tmp_path: Path) -> None:
    """The CI text keeps one comment line per ecosystem audit command.

    arch: D7.3, D7.4, D14.9
    """
    lines = managed.render_ci().splitlines()
    for command in _FALLBACKS:
        hits = [line for line in lines if command in line]
        assert len(hits) == 1, command
        assert hits[0].lstrip().startswith("# "), hits[0]


def test_ci_installs_gitleaks_by_checksum_before_check(tmp_path: Path) -> None:
    """The check job checks out every commit and installs gitleaks by checksum before `trueup check` runs.

    D14.9: `trueup check` runs gitleaks itself for `secret-content`, so the
    workflow has no gitleaks scan step of its own.

    arch: D7.3, D7.4, D14.9
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    steps = yaml.safe_load(managed.render_ci())["jobs"]["check"]["steps"]
    assert steps[0]["uses"].startswith("actions/checkout@")
    assert steps[0]["with"] == {"fetch-depth": 0}
    runs = [step["run"] for step in steps if "run" in step]
    install = next(run for run in runs if "gitleaks.tar.gz" in run)
    assert re.search(
        r'echo "[0-9a-f]{64}  gitleaks\.tar\.gz" \| sha256sum -c -', install
    )
    assert "github.com/gitleaks/gitleaks/releases/download/" in install
    assert "-C /usr/local/bin gitleaks" in install
    assert runs.index(install) < runs.index("trueup check --root .")
    assert not [run for run in runs if run.startswith("gitleaks ")]


def test_lint_hooks_start_with_the_language_hooks_and_hold_no_gitleaks(
    tmp_path: Path,
) -> None:
    """The first lint hook is a language hook; no lint hook runs gitleaks.

    D14.6: `check` runs gitleaks for the `secret-content` row, so
    `lint_hooks` drops the shared gitleaks hook. With every language off
    and no Vale style, the list is empty.

    arch: D7.3, D7.4, D14.9, D14.22, D14.6
    """
    hooks = managed.lint_hooks(_python_cfg())
    assert hooks[0].id == "ruff-check"
    assert "gitleaks" not in [hook.id for hook in hooks]
    assert (
        managed.lint_hooks(_python_cfg(languages={"python": "off"}, docs="readme"))
        == []
    )


def test_gitleaks_config_lists_the_ignore_globs_as_anchored_regexes(
    tmp_path: Path,
) -> None:
    """The gitleaks config extends the default rules and allowlists each ignore glob.

    arch: D7.3, D7.4, D14.8, D16.5
    """
    # D14.8: the gitleaks config left the managed set; its renderer stays.
    bare = managed.render_gitleaks_config(_python_cfg())
    assert bare.split("\n", 1)[0] == f"# {MANAGED_HEADER}"
    # D16.5: the one rules override drops the published test values.
    assert tomllib.loads(bare) == {
        "extend": {"useDefault": True},
        "rules": [
            {
                "id": "generic-api-key",
                "allowlists": [
                    {
                        "description": "values that a public standard prints",
                        "regexTarget": "secret",
                        "regexes": [
                            "^" + re.escape(value) + "$"
                            for value in managed.PUBLISHED_TEST_VALUES
                        ],
                    }
                ],
            }
        ],
    }
    globs = ("tests/fixtures/**", "docs/*.md", "a b/c-?.txt")
    text = managed.render_gitleaks_config(_python_cfg(ignore=globs))
    data = tomllib.loads(text)
    assert data["extend"] == {"useDefault": True}
    (allowlist,) = data["allowlists"]
    assert len(allowlist["paths"]) == len(globs)
    samples = (
        "tests/fixtures/x/y.py",
        "docs/a.md",
        "docs/a/b.md",
        "a b/c-1.txt",
        "xdocs/a.md",
    )
    for glob, regex in zip(globs, allowlist["paths"], strict=True):
        assert regex.startswith("^") and regex.endswith("$"), regex
        for sample in samples:
            assert bool(re.match(regex, sample)) == matches_ignore(sample, (glob,))


def test_render_does_not_read_the_tools_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every rendered text has the same bytes whether `shutil.which` finds a tool or not.

    arch: D7.3, D7.4, I-33, D14.8
    """
    every_language = {language: "strict" for language in LANGUAGES}
    cfg = Config(languages=every_language, ignore=("tests/fixtures/**",))
    survey = replace(_survey(tmp_path, tier="T2"), files=_LOCK_FILES)
    renders = []
    for answer in ("/usr/bin/tool", None):
        monkeypatch.setattr(shutil, "which", lambda name, answer=answer: answer)
        texts = dict(managed.render(replace(cfg, refs_mode="copy"), survey))
        texts["pre-commit"] = managed.render_pre_commit()
        texts["ci"] = managed.render_ci()
        texts["gitleaks"] = managed.render_gitleaks_config(cfg)
        renders.append({key: text.encode("utf-8") for key, text in texts.items()})
    assert renders[0] == renders[1]
    assert managed.CONFIG_PATH in renders[0]


def test_effective_config_defaults_present_languages_to_clean(tmp_path: Path) -> None:
    """A present language with no mode gets `clean`; a small one and a named one are left alone.

    arch: D5.6
    """
    survey = _survey(tmp_path, present={"python": 80, "go": 60, "shell": 10})
    cfg = managed.effective_config(Config(languages={"go": "off"}), survey)
    assert cfg.languages == {"go": "off", "python": "clean"}
    assert managed.effective_config(None, survey).languages == {
        "go": "clean",
        "python": "clean",
    }


def _ids(findings: list[Finding]) -> dict[str, Finding]:
    """Map each finding id to its finding.

    Args:
        findings: The findings.

    Returns:
        Id to finding.
    """
    return {finding.id: finding for finding in findings}


def test_absent_managed_file_is_an_auto_error(tmp_path: Path) -> None:
    """A managed path that is absent is an auto `error` `file-managed:<path>` in category setup.

    arch: D5.4, D5.6, D14.8
    """
    survey = _survey(tmp_path, tier="T2", present={"python": 80})
    found = _ids(managed.setup_findings(survey, _python_cfg(refs_mode="copy")))
    for path in ("ref_check.py", "ref_check.toml"):
        finding = found[f"file-managed:{path}"]
        assert (finding.severity, finding.auto, finding.category) == (
            "error",
            True,
            "setup",
        )


def test_matching_files_give_no_finding_even_with_edited_comments(
    tmp_path: Path,
) -> None:
    """A managed file equal to its render, blank and comment lines aside, gives no finding.

    arch: D5.6, D14.8
    """
    cfg = _python_cfg(refs_mode="copy")
    survey = _survey(tmp_path, tier="T2", present={"python": 80})
    files = managed.render(cfg, survey)
    _write_all(tmp_path, files)
    (tmp_path / ".gitignore").write_text(".scratch/\n", encoding="utf-8")
    checker_config = tmp_path / "ref_check.toml"
    checker_config.write_text(
        checker_config.read_text(encoding="utf-8") + "\n# a note the person added\n\n",
        encoding="utf-8",
    )
    findings = managed.setup_findings(survey, cfg)
    assert [finding.id for finding in findings if finding.rule == "file-managed"] == []


def test_changed_file_with_header_is_auto_and_without_header_is_manual(
    tmp_path: Path,
) -> None:
    """A changed file that keeps the header is auto; one with no header is manual and never overwritten.

    A `.editorconfig` is no longer in the set, so the person's own file
    gives no row at all (D14.8).

    arch: D5.6, I-24, D6.15, D14.8
    """
    cfg = _python_cfg(refs_mode="copy")
    survey = _survey(tmp_path, tier="T2", present={"python": 80})
    _write_all(tmp_path, managed.render(cfg, survey))
    checker_config = tmp_path / "ref_check.toml"
    rendered = checker_config.read_text(encoding="utf-8")
    checker_config.write_text(rendered + "[extra]\nx = 1\n", encoding="utf-8")
    (tmp_path / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    found = _ids(managed.setup_findings(survey, cfg))
    assert found["file-managed:ref_check.toml"].auto is True
    assert "file-managed:.editorconfig" not in found
    assert "managed-legacy:.editorconfig" not in found
    checker_config.write_text(
        rendered.split("\n", 1)[1] + "[extra]\nx = 1\n", encoding="utf-8"
    )
    unmanaged = _ids(managed.setup_findings(survey, cfg))["file-managed:ref_check.toml"]
    assert (unmanaged.severity, unmanaged.auto) == ("error", False)
    assert "never overwrites" in unmanaged.action


def test_preexisting_editorconfig_is_a_manual_warning_not_an_error(
    tmp_path: Path,
) -> None:
    """A `.editorconfig` from before trueup gives no finding: trueup no longer manages it (D14.8).

    arch: D6.15, D14.22, D14.4, D14.8
    """
    cfg = _python_cfg()
    survey = _survey(tmp_path, present={"python": 80})
    (tmp_path / ".editorconfig").write_text(
        "root = true\nindent_style = tab\n", encoding="utf-8"
    )
    found = _ids(managed.setup_findings(survey, cfg))
    assert not [finding_id for finding_id in found if "editorconfig" in finding_id]


def test_persons_own_json_under_lint_is_manual_not_auto(tmp_path: Path) -> None:
    """A JSON file under lint/ that the target authored, not trueup, gives no row (LOW-2, D14.8).

    It has no `"_managed"` marker, so it is not a file of the old managed
    lint tree, and no `managed-legacy` row asks about it (I-42).

    arch: D6.15, I-24, D14.22, D14.4, D14.8
    """
    cfg = _python_cfg(languages={"python": "strict"})
    jscpd = tmp_path / "lint/jscpd.json"
    jscpd.parent.mkdir(parents=True)
    jscpd.write_text('{"threshold": 50}\n', encoding="utf-8")
    survey = replace(
        _survey(tmp_path, present={"python": 80}), files=("lint/jscpd.json",)
    )
    found = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:lint/jscpd.json" not in found
    assert "managed-legacy:lint/jscpd.json" not in found


def test_rendered_json_carries_the_managed_marker(tmp_path: Path) -> None:
    """`_mark_json` puts `"_managed": "trueup"` first in the jscpd and eslint package JSON (LOW-2).

    arch: D6.15
    """
    from trueup.rulesets import render_eslint_package, render_jscpd

    for text in (render_jscpd(["python"]), render_eslint_package("clean", "off")):
        marked = json.loads(managed._mark_json(text))
        assert next(iter(marked)) == "_managed"
        assert marked["_managed"] == "trueup"


def test_marked_json_with_new_content_is_still_auto(tmp_path: Path) -> None:
    """A marked `jscpd.json` a person edited is an `info` `managed-legacy` row (LOW-2, D14.8).

    arch: D6.15, D14.22, D14.4, D14.8
    """
    cfg = _python_cfg(languages={"python": "strict"})
    jscpd = tmp_path / "lint/jscpd.json"
    jscpd.parent.mkdir(parents=True)
    jscpd.write_text('{"_managed": "trueup", "threshold": 50}\n', encoding="utf-8")
    survey = _survey(tmp_path, present={"python": 80})
    found = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:lint/jscpd.json" not in found
    row = found["managed-legacy:lint/jscpd.json"]
    assert (row.severity, row.auto) == ("info", False)


def test_old_form_json_with_no_marker_is_still_auto(tmp_path: Path) -> None:
    """A `jscpd.json` in the old form, with no marker, gives no row (D14.8).

    D14.8 knows a legacy JSON file by its marker only. The old form of
    D6.15 needs today's rendered text to compare with, and `render` no
    longer builds that file.

    arch: D6.15, D14.22, D14.4, D14.8
    """
    from trueup.rulesets import render_jscpd

    cfg = _python_cfg(languages={"python": "strict"})
    jscpd = tmp_path / "lint/jscpd.json"
    jscpd.parent.mkdir(parents=True)
    jscpd.write_text(render_jscpd(["python"]), encoding="utf-8")
    survey = _survey(tmp_path, present={"python": 80})
    found = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:lint/jscpd.json" not in found
    assert "managed-legacy:lint/jscpd.json" not in found


def _unmarked(path: Path) -> dict:
    """Read one rendered JSON file and drop its `"_managed"` marker."""
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["_managed"]
    return data


def test_stale_old_form_json_with_no_marker_is_still_auto(tmp_path: Path) -> None:
    """A marked eslint `package.json` with old pins is a `managed-legacy` row (LOW-2, D14.8).

    The row reads the marker, not the pinned values, so a file from an
    older trueup is still known as trueup's.

    arch: D6.15, I-24, D14.22, D14.4, D14.8
    """
    from trueup.rulesets import render_eslint_package

    cfg = _python_cfg(languages={"python": "strict", "typescript": "strict"})
    package_path = tmp_path / "lint/typescript/package.json"
    package_path.parent.mkdir(parents=True)
    package = json.loads(managed._mark_json(render_eslint_package("strict", "off")))
    package["devDependencies"]["eslint-plugin-sonarjs"] = "^3.0.0"
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    survey = _survey(tmp_path, present={"python": 80, "typescript": 80})
    found = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:lint/typescript/package.json" not in found
    row = found["managed-legacy:lint/typescript/package.json"]
    assert (row.severity, row.auto) == ("info", False)


def test_persons_own_package_json_under_lint_is_manual(tmp_path: Path) -> None:
    """A `lint/typescript/package.json` with no marker is the person's own and gives no row (LOW-2, D14.8).

    arch: D6.15, I-24, D14.22, D14.4, D14.8
    """
    cfg = _python_cfg(languages={"python": "clean", "typescript": "strict"})
    package_path = tmp_path / "lint/typescript/package.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text('{"name": "my-own-lint"}\n', encoding="utf-8")
    survey = _survey(tmp_path, present={"python": 80, "typescript": 80})
    found = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:lint/typescript/package.json" not in found
    assert "managed-legacy:lint/typescript/package.json" not in found


def test_ref_check_that_differs_is_a_manual_warning(tmp_path: Path) -> None:
    """A `ref_check.py` that is not byte-equal to the bundled copy and has no header is a manual `warn`.

    arch: D5.6, I-26
    """
    cfg = _python_cfg(refs_mode="copy")
    survey = _survey(tmp_path, present={"python": 80})
    _write_all(tmp_path, managed.render(cfg, survey))
    (tmp_path / "ref_check.py").write_text("print('mine')\n", encoding="utf-8")
    finding = _ids(managed.setup_findings(survey, cfg))["file-managed:ref_check.py"]
    assert (finding.severity, finding.auto) == ("warn", False)


def test_config_findings(tmp_path: Path) -> None:
    """No trueup.toml and a present language with no mode are auto errors; a small language is info.

    arch: D5.4, D5.6, D12.9
    """
    survey = _survey(tmp_path, present={"python": 80, "shell": 10})
    # D12.9: at T1 with no trueup.toml the rows fold into the setup opt-in
    # row; `offer=False` gives the per-file rows that the opt-in writes.
    found = _ids(managed.setup_findings(survey, None, offer=False))
    assert (found["config:trueup.toml"].severity, found["config:trueup.toml"].auto) == (
        "error",
        True,
    )
    python = found["config:languages.python"]
    assert (python.severity, python.auto) == ("error", True)
    shell = found["config:languages.shell"]
    assert (shell.severity, shell.auto) == ("info", False)
    named = _ids(
        managed.setup_findings(
            survey, Config(languages={"python": "off", "shell": "off"})
        )
    )
    assert not [finding_id for finding_id in named if finding_id.startswith("config:")]


def test_no_config_row_under_the_user_default_file(tmp_path: Path) -> None:
    """Under the user default file the target has no trueup.toml, but no `config:trueup.toml` row and no setup row come.

    `config.load` gives the effective config of the user default file, so
    the setup checks see an adopted target. Without the user default file
    the same tree is not adopted: the caller passes `None`, as
    `report.collect` does, and the tree gets the setup opt-in row (D15.6).

    arch: D14.3, D14.19, D15.6
    """
    root = tmp_path / "repo"
    root.mkdir()
    survey = _survey(root, present={"python": 80})
    assert config.load_layers(root).adopted is False
    bare = _ids(managed.setup_findings(survey, None))
    assert managed.SETUP_ID in bare

    user_default = config.config_home() / "trueup.toml"
    user_default.parent.mkdir(parents=True)
    user_default.write_text('docs = "readme"\n', encoding="utf-8")
    cfg = config.load(root)
    assert config.load_layers(root).adopted and config.load_target(root) is None
    found = _ids(managed.setup_findings(survey, cfg))
    assert "config:trueup.toml" not in found
    assert managed.SETUP_ID not in found
    assert "config:trueup.toml" not in _ids(
        managed.setup_findings(survey, cfg, offer=False)
    )


def test_language_row_is_info_under_the_user_default_file(tmp_path: Path) -> None:
    """With `cfg` set and no target `trueup.toml`, a present language row is `info`, not auto.

    The same row is an auto `error` once the target holds `trueup.toml`,
    because `apply` can then write the mode there.

    arch: D14.3, D14.8
    """
    survey = _survey(tmp_path, present={"python": 80, "shell": 10})
    found = _ids(managed.setup_findings(survey, Config()))
    python = found["config:languages.python"]
    assert (python.severity, python.auto) == ("info", False)
    assert "user default file" in python.action
    shell = found["config:languages.shell"]
    assert (shell.severity, shell.auto) == ("info", False)

    (tmp_path / "trueup.toml").write_text("", encoding="utf-8")
    python = _ids(managed.setup_findings(survey, Config()))["config:languages.python"]
    assert (python.severity, python.auto) == ("error", True)


def test_gitignore_finding_names_the_missing_scratch_line(tmp_path: Path) -> None:
    """`.gitignore` without `.scratch/` gives an auto `gitignore:.gitignore`; with it, none.

    arch: D5.6
    """
    survey = _survey(tmp_path)
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    assert (
        _ids(managed.setup_findings(survey, Config()))["gitignore:.gitignore"].auto
        is True
    )
    (tmp_path / ".gitignore").write_text("*.pyc\n.scratch/\n", encoding="utf-8")
    assert "gitignore:.gitignore" not in _ids(managed.setup_findings(survey, Config()))


def test_tool_missing_is_info_per_enabled_language_tool(tmp_path: Path) -> None:
    """A tool an enabled rule set needs and the path lacks is an `info` `tool-missing:<lang>/<tool>`.

    arch: D5.5, D5.6
    """
    survey = _survey(tmp_path, present={"python": 80}, tools={"ruff": False})
    found = _ids(managed.setup_findings(survey, _python_cfg()))
    assert found["tool-missing:python/ruff"].severity == "info"
    with_ruff = _survey(tmp_path, present={"python": 80}, tools={"ruff": True})
    assert "tool-missing:python/ruff" not in _ids(
        managed.setup_findings(with_ruff, _python_cfg())
    )


def test_editorconfig_template_is_what_render_writes(tmp_path: Path) -> None:
    """`render` no longer writes `.editorconfig`; a copy that carries the header is a `managed-legacy` row (D14.8).

    arch: D5.6, D14.22, D14.4, D14.8
    """
    survey = _survey(tmp_path, tier="T2")
    assert managed.EDITORCONFIG_PATH not in managed.render(_python_cfg(), survey)
    (tmp_path / ".editorconfig").write_text(
        f"# {MANAGED_HEADER}\nroot = true\n", encoding="utf-8"
    )
    found = _ids(managed.setup_findings(survey, _python_cfg()))
    assert found["managed-legacy:.editorconfig"].severity == "info"


def test_tool_findings_name_the_absent_eslint_packages(tmp_path: Path) -> None:
    """With TypeScript or Vue on and no `node_modules` in the eslint package directory, one `info` finding names `trueup lint --install`.

    The directory is `managed.eslint_dir` under the trueup cache, not the
    target (D14.7). A plain `check` never runs `npm install`: it uses the
    network. The finding is absent when the directory holds
    `node_modules`, and when neither language is on. A `node_modules` in
    the old target path does not count.

    arch: D8.3, D14.7
    """
    cfg = Config(languages={"typescript": "clean"})
    survey = _survey(tmp_path, present={"typescript": 100}, tools={"npx": True})
    findings = {finding.id: finding for finding in managed._tool_findings(cfg, survey)}
    finding = findings["tool-missing:typescript/node_modules"]
    assert finding.severity == "info"
    assert finding.auto is False
    assert finding.action == "run trueup lint --install"
    (tmp_path / "lint" / "typescript" / "node_modules").mkdir(parents=True)
    assert "tool-missing:typescript/node_modules" in {
        finding.id for finding in managed._tool_findings(cfg, survey)
    }
    packages = managed.eslint_dir(cfg)
    assert packages is not None
    assert packages.is_relative_to(tmp_path / "xdg-cache" / "trueup" / "eslint")
    (packages / "node_modules").mkdir(parents=True)
    assert "tool-missing:typescript/node_modules" not in {
        finding.id for finding in managed._tool_findings(cfg, survey)
    }
    python_only = Config(languages={"python": "clean"})
    assert "tool-missing:typescript/node_modules" not in {
        finding.id for finding in managed._tool_findings(python_only, survey)
    }


def test_render_ref_check_config_carries_the_local_tags(tmp_path: Path) -> None:
    """`ref_check.toml` gets a `[registry] local_tags` table from `[refs] local_tags`, and none without (D8.7).

    arch: D8.7, D14.8
    """
    # D14.8: ref_check.toml is in the set in copy mode.
    t2 = _survey(tmp_path, tier="T2")
    files = managed.render(
        _python_cfg(refs_mode="copy", refs_local_tags=("X", "G")), t2
    )
    assert files["ref_check.toml"].endswith('\n[registry]\nlocal_tags = ["X", "G"]\n')
    plain = managed.render(_python_cfg(refs_mode="copy"), t2)
    assert "[registry]" not in plain["ref_check.toml"]


def test_render_ref_check_config_carries_the_declared_sources(tmp_path: Path) -> None:
    """`ref_check.toml` gets `[targets.arch]` only when `declared` or `id_forms` is set (D16.2).

    arch: D16.2, I-54
    """
    t2 = _survey(tmp_path, tier="T2")
    plain = managed.render_ref_check_config(_python_cfg(), t2)
    assert "[targets" not in plain
    both = managed.render_ref_check_config(
        _python_cfg(refs_declared=("docs/*.md",), refs_id_forms=("D-<n>",)), t2
    )
    assert tomllib.loads(both)["targets"]["arch"] == {
        "sources": ["docs/*.md"],
        "forms": ["D-<n>"],
    }
    declared_only = managed.render_ref_check_config(
        _python_cfg(refs_declared=("docs/*.md",)), t2
    )
    assert tomllib.loads(declared_only)["targets"]["arch"] == {"sources": ["docs/*.md"]}
    forms_only = managed.render_ref_check_config(
        _python_cfg(refs_id_forms=("D-<n>",)), t2
    )
    assert tomllib.loads(forms_only)["targets"]["arch"] == {"forms": ["D-<n>"]}


def test_render_ref_check_config_carries_the_accepted_reader_changes(
    tmp_path: Path,
) -> None:
    """`ref_check.toml` gets `[targets.arch] accepted` only when the key is set (D16.3).

    arch: D16.3, I-54
    """
    t2 = _survey(tmp_path, tier="T2")
    assert "accepted" not in managed.render_ref_check_config(_python_cfg(), t2)
    text = managed.render_ref_check_config(
        _python_cfg(refs_accepted_reader_changes=("rust-doc-position",)), t2
    )
    assert tomllib.loads(text)["targets"]["arch"] == {"accepted": ["rust-doc-position"]}


def test_render_ref_check_config_carries_the_law_archive(tmp_path: Path) -> None:
    """`ref_check.toml` gets `[targets.law] archive` from `[refs] law_archive`, and no table without it.

    The table sits after `[targets.arch]` and before `[keep]`, and the
    text with no key is the text of before. The checker reads the
    rendered table with its own loader.

    arch: D16.13
    """
    t2 = _survey(tmp_path, tier="T2")
    plain_cfg = _python_cfg(
        refs_declared=("docs/*.md",),
        keep={"refcheck:docs/a.md:1:no-front-matter": "a reason"},
        ignore=("build/**",),
    )
    plain = managed.render_ref_check_config(plain_cfg, t2, keep=True)
    assert "[targets.law]" not in plain
    keyed = managed.render_ref_check_config(
        replace(plain_cfg, refs_law_archive="../laws/archive"), t2, keep=True
    )
    table = '\n[targets.law]\narchive = "../laws/archive"\n'
    assert keyed.count(table) == 1
    assert keyed.replace(table, "", 1) == plain
    assert keyed.index("[targets.arch]") < keyed.index("[targets.law]")
    assert keyed.index("[targets.law]") < keyed.index("[keep]")
    assert tomllib.loads(keyed)["targets"]["law"] == {"archive": "../laws/archive"}
    (tmp_path / "ref_check.toml").write_text(keyed, encoding="utf-8")
    loaded = ref_check.load_config(tmp_path)
    assert loaded.archive == (tmp_path / ".." / "laws" / "archive").resolve()
    # A quote, a backslash and a letter outside ASCII round-trip.
    odd = 'C:\\laws "x"/ärchive'
    text = managed.render_ref_check_config(_python_cfg(refs_law_archive=odd), t2)
    assert tomllib.loads(text)["targets"]["law"] == {"archive": odd}


def test_a_law_archive_is_rendered_below_the_tier_gate(tmp_path: Path) -> None:
    """Below the gate a set `law_archive` keeps its table, each switch stays off, and copy mode keeps the file at T0.

    arch: D16.13
    """
    other = ("src/a.py",)
    plain = Config()
    cfg = Config(refs_law_archive="/srv/laws/archive")
    for survey in (
        _survey(tmp_path, tier="T0"),
        _with_files(_survey(tmp_path, tier="T1"), other),
    ):
        assert not managed.refcheck_switches_on(plain, survey)
        assert managed.refcheck_switches_on(cfg, survey)
        for text in (
            managed.render_ref_check_config(cfg, survey),
            docrules._refcheck_config_text(cfg, survey),
            lint._ref_check_text(cfg, survey),
        ):
            assert not any(_switches(text).values())
            assert tomllib.loads(text)["targets"] == {
                "law": {"archive": "/srv/laws/archive"}
            }
    t0 = _survey(tmp_path, tier="T0")
    copy = Config(refs_mode="copy")
    assert managed.REF_CHECK_CONFIG_PATH not in managed.render(copy, t0)
    keyed = replace(copy, refs_law_archive="../laws/archive")
    assert managed.REF_CHECK_CONFIG_PATH in managed.render(keyed, t0)


@pytest.mark.parametrize(
    "keys",
    [
        {"refs_declared": ("design/*.md",)},
        {"refs_id_forms": ("D-<n>",)},
    ],
)
def test_a_reader_key_is_rendered_below_the_tier_gate(
    tmp_path: Path, keys: dict[str, tuple[str, ...]]
) -> None:
    """Below the gate a set key keeps its table, and each switch stays off.

    arch: D16.2
    """
    other = ("src/a.py",)
    for survey in (
        _survey(tmp_path, tier="T0"),
        _with_files(_survey(tmp_path, tier="T1"), other),
    ):
        plain = Config()
        cfg = replace(plain, **keys)
        assert not managed.refcheck_switches_on(plain, survey)
        assert docrules._refcheck_config_text(plain, survey) == ""
        assert lint._ref_check_text(plain, survey) == ""
        assert managed.refcheck_switches_on(cfg, survey)
        for text in (
            managed.render_ref_check_config(cfg, survey),
            docrules._refcheck_config_text(cfg, survey),
            lint._ref_check_text(cfg, survey),
        ):
            assert not any(_switches(text).values())
            assert tomllib.loads(text)["targets"]["arch"]


def test_an_accepted_only_target_is_rendered_below_the_tier_gate(
    tmp_path: Path,
) -> None:
    """Below the gate `accepted_reader_changes` alone keeps its table (I-58).

    arch: D16.3, I-58
    """
    other = ("src/a.py",)
    cfg = Config(refs_accepted_reader_changes=("rust-doc-position",))
    for survey in (
        _survey(tmp_path, tier="T0"),
        _with_files(_survey(tmp_path, tier="T1"), other),
    ):
        assert managed.refcheck_switches_on(cfg, survey)
        for text in (
            managed.render_ref_check_config(cfg, survey),
            docrules._refcheck_config_text(cfg, survey),
            lint._ref_check_text(cfg, survey),
        ):
            assert not any(_switches(text).values())
            assert tomllib.loads(text)["targets"]["arch"]["accepted"] == [
                "rust-doc-position"
            ]


def test_a_reader_key_keeps_the_copy_mode_config_at_t0(tmp_path: Path) -> None:
    """In copy mode at T0 the config comes with the checker when a key is set.

    arch: D16.2
    """
    t0 = _survey(tmp_path, tier="T0")
    plain = Config(refs_mode="copy")
    assert managed.REF_CHECK_CONFIG_PATH not in managed.render(plain, t0)
    keyed = replace(plain, refs_id_forms=("D-<n>",))
    assert managed.REF_CHECK_CONFIG_PATH in managed.render(keyed, t0)


def test_a_hand_edit_of_the_managed_ref_check_toml_is_drift(tmp_path: Path) -> None:
    """A `[registry]` table added by hand to the managed `ref_check.toml` is an auto `file-managed` error (D8.7).

    This is the reason `local_tags` lives in `trueup.toml`: the next
    `apply` rewrites the managed file from the config and drops a hand
    edit.

    arch: D8.7, D14.8
    """
    cfg = _python_cfg(refs_mode="copy")  # D14.8: ref_check.toml is copy mode only
    survey = _survey(tmp_path, tier="T2")
    _write_all(tmp_path, managed.render(cfg, survey))
    assert not [
        finding
        for finding in managed.setup_findings(survey, cfg)
        if finding.path == "ref_check.toml"
    ]
    with (tmp_path / "ref_check.toml").open("a", encoding="utf-8") as handle:
        handle.write('\n[registry]\nlocal_tags = ["X"]\n')
    (drift,) = [
        finding
        for finding in managed.setup_findings(survey, cfg)
        if finding.path == "ref_check.toml"
    ]
    assert drift.id == "file-managed:ref_check.toml"
    assert drift.severity == "error"
    assert drift.auto is True


def test_global_mode_renders_no_checker_copy_and_the_refs_hook(tmp_path: Path) -> None:
    """In global mode, the default, `render` has no checker pair, and the pre-commit snippet runs `trueup lint` only (D9.1, D14.9).

    arch: D9.1, D14.8, D14.9
    """
    files = managed.render(_python_cfg(), _survey(tmp_path, tier="T2"))
    assert "ref_check.py" not in files
    assert "ref_check.toml" not in files
    text = managed.render_pre_commit()
    assert "entry: trueup lint" in text
    assert "ref_check" not in text


def test_copy_mode_renders_the_copy_with_the_header_and_the_python_hook(
    tmp_path: Path,
) -> None:
    """In copy mode `render` writes the bundled checker, whose first line is the managed header (D9.1, D9.3).

    D14.9: `trueup lint` runs the copy; the target has no `ref-check` hook.

    arch: D9.1, D9.3, D14.8, D14.9
    """
    cfg = _python_cfg(refs_mode="copy")
    files = managed.render(cfg, _survey(tmp_path))
    copy = files["ref_check.py"]
    assert copy.encode("utf-8") == (REPO / "trueup" / "ref_check.py").read_bytes()
    assert copy.split("\n", 1)[0] == managed.header_line("ref_check.py")


def test_an_older_trueup_copy_with_the_header_is_an_automatic_error(
    tmp_path: Path,
) -> None:
    """A copy that differs from the shipped checker and still carries the header is rewritten by `apply`; one with no header stays manual (D9.3).

    arch: D9.3
    """
    cfg = _python_cfg(refs_mode="copy")
    survey = _survey(tmp_path, present={"python": 80})
    _write_all(tmp_path, managed.render(cfg, survey))
    copy = tmp_path / "ref_check.py"
    shipped = copy.read_text(encoding="utf-8")
    copy.write_text(shipped + "\n# an earlier version ended here\n", encoding="utf-8")
    finding = _ids(managed.setup_findings(survey, cfg))["file-managed:ref_check.py"]
    assert (finding.severity, finding.auto) == ("error", True)
    copy.write_text(shipped.split("\n", 1)[1], encoding="utf-8")
    finding = _ids(managed.setup_findings(survey, cfg))["file-managed:ref_check.py"]
    assert (finding.severity, finding.auto) == ("warn", False)
    assert "git rm ref_check.py" in finding.action
    copy.unlink()
    finding = _ids(managed.setup_findings(survey, cfg))["file-managed:ref_check.py"]
    assert (finding.severity, finding.auto) == ("error", True)


def test_global_mode_reports_an_old_copy_as_info(tmp_path: Path) -> None:
    """In global mode a file at `ref_check.py` is an `info` finding that names `git rm`, never a `file-managed` finding (D9.1).

    arch: D9.1
    """
    cfg = _python_cfg()
    survey = _survey(tmp_path, present={"python": 80})
    (tmp_path / "ref_check.py").write_text("print('old copy')\n", encoding="utf-8")
    findings = _ids(managed.setup_findings(survey, cfg))
    assert "file-managed:ref_check.py" not in findings
    finding = findings["refs-copy:ref_check.py"]
    assert (finding.severity, finding.auto, finding.category, finding.path) == (
        "info",
        False,
        "setup",
        "ref_check.py",
    )
    assert "git rm ref_check.py" in finding.action
    (tmp_path / "ref_check.py").unlink()
    assert "refs-copy:ref_check.py" not in _ids(managed.setup_findings(survey, cfg))
    assert "refs-copy:ref_check.py" not in _ids(
        managed.setup_findings(survey, _python_cfg(refs_mode="copy"))
    )


def test_global_mode_names_trueup_when_it_is_not_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tool-missing:refs/trueup` names the one-time install in global mode only, and only while `trueup` is absent (D9.1).

    arch: D9.1
    """
    survey = _survey(tmp_path, present={"python": 80}, tools={"ruff": True})
    monkeypatch.setattr(managed.shutil, "which", lambda name: None)
    finding = _ids(managed.setup_findings(survey, _python_cfg()))[
        "tool-missing:refs/trueup"
    ]
    assert finding.severity == "info"
    assert "uv tool install --editable" in finding.action
    assert "trueup refs" in finding.action
    assert "tool-missing:refs/trueup" not in _ids(
        managed.setup_findings(survey, _python_cfg(refs_mode="copy"))
    )
    monkeypatch.setattr(managed.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert "tool-missing:refs/trueup" not in _ids(
        managed.setup_findings(survey, _python_cfg())
    )


def test_render_ref_check_config_carries_the_kept_failures(tmp_path: Path) -> None:
    """The managed `ref_check.toml` lists the kept `refcheck:` ids, prefix removed and sorted; `keep=False` leaves the table out (D9.2).

    arch: D9.2, D14.8
    """
    # D12.9: docs full and T2 give the same ref_check.toml as the direct render.
    cfg = Config(
        docs="full",
        keep={
            "refcheck:docs/b.md:1:no-front-matter": "fixed path",
            "refcheck:docs/a.md:1:no-front-matter": "fixed path",
            "prose:docs/c.md": "source document",
        },
    )
    # D14.22 item 3: the renderer takes the survey.
    t2 = _survey(tmp_path, tier="T2")
    with_keep = managed.render_ref_check_config(cfg, t2)
    assert with_keep.endswith(
        '\n[keep]\nfailures = ["docs/a.md:1:no-front-matter", "docs/b.md:1:no-front-matter"]\n'
    )
    assert "[keep]" not in managed.render_ref_check_config(cfg, t2, keep=False)
    assert "[keep]" not in managed.render_ref_check_config(
        Config(keep={"prose:docs/c.md": "source document"}), t2
    )
    copy_cfg = replace(cfg, refs_mode="copy")  # D14.8: copy mode holds the file
    assert managed.render(copy_cfg, t2)["ref_check.toml"] == with_keep


def test_render_ref_check_config_carries_a_page_prefix_keep(tmp_path: Path) -> None:
    """A `refcheck:<page>` prefix keep renders as the checker prefix `<page>` (D15.8).

    The checker then keeps every failure of the page, as `check` does.

    arch: D15.3, D15.8
    """
    cfg = Config(docs="full", keep={"refcheck:docs/a.md": "fixed page"})
    t2 = _survey(tmp_path, tier="T2")
    assert managed.kept_failure_ids(cfg) == ("docs/a.md",)
    assert managed.render_ref_check_config(cfg, t2).endswith(
        '\n[keep]\nfailures = ["docs/a.md"]\n'
    )


def test_render_ref_check_config_turns_layout_off(tmp_path: Path) -> None:
    """`[refs] layout = false` renders `[checks] layout = false` and leaves the other switches on (D9.4).

    The off config comes from a parse, since `refs.layout` sets the three
    `[layout]` switches and the switches decide (D15.29).

    arch: D9.4, D15.29
    """
    # D14.22 item 3: the renderer takes the survey and resolves docs itself.
    t2 = _survey(tmp_path, tier="T2")
    on = managed.render_ref_check_config(Config(docs="full"), t2)
    off_cfg = config._parse(
        {"docs": "full", "refs": {"layout": False}}, source=None, layer="target"
    )
    off = managed.render_ref_check_config(off_cfg, t2)
    assert "layout = true" in on
    assert "layout = false" in off
    assert "readme = true" in off
    assert "layout = false" in managed.render_ref_check_config(
        Config(docs="readme"), t2
    )


def test_render_ref_check_config_carries_the_ignore_globs(tmp_path: Path) -> None:
    """The managed `ref_check.toml` carries the `ignore` globs as `[scan] ignore`, with and without `[keep]` (I-2).

    `check` renders with `keep=False`, so the globs must be in that text
    too, or `check` and the hook would scan different paths.

    arch: I-2
    """
    cfg = Config(docs="full", ignore=("docs/features/**", ".state/**"))
    t2 = _survey(tmp_path, tier="T2")  # D14.22 item 3: the renderer takes the survey
    for keep in (True, False):
        text = managed.render_ref_check_config(cfg, t2, keep=keep)
        assert text.endswith('\n[scan]\nignore = ["docs/features/**", ".state/**"]\n')
    assert "[scan]" not in managed.render_ref_check_config(Config(docs="full"), t2)
    assert managed.render(replace(cfg, refs_mode="copy"), t2)[
        "ref_check.toml"
    ] == managed.render_ref_check_config(cfg, t2)


def test_ci_names_the_trueup_install_in_one_placeholder_comment(tmp_path: Path) -> None:
    """The CI text carries one placeholder comment for the trueup install, in every mode (D9.1, D14.9).

    D14.9: the text reads no config, so global and copy mode get the same
    line; `trueup lint` runs the checker in both modes.

    arch: D9.1, D14.9
    """
    text = managed.render_ci()
    lines = [line for line in text.splitlines() if "install trueup" in line]
    assert [line.strip() for line in lines] == [
        "# install trueup here, for example: pip install <path or URL of trueup>"
    ]
    assert "pre-commit" not in text
    assert "trueup refs" not in text


# -- D12.9: the managed set per tier (I-42) --------------------------------

_T2_ONLY: tuple[str, ...] = (
    managed.CI_PATH,
    managed.GITLEAKS_CONFIG_PATH,
    managed.REF_CHECK_CONFIG_PATH,
)


def _with_files(survey: Survey, files: tuple[str, ...]) -> Survey:
    """Give a copy of a survey with another file list.

    Args:
        survey: The survey to copy.
        files: The repo paths the copy holds.

    Returns:
        The copy.
    """
    return replace(survey, files=files)


def test_render_t1_holds_the_t1_files_only(tmp_path: Path) -> None:
    """At T1 in global mode the set is `trueup.toml` only (D14.8, I-42).

    arch: D12.9, D14.8
    """
    files = managed.render(
        managed.effective_config(None, _survey(tmp_path, present={"python": 60})),
        _survey(tmp_path, present={"python": 60}),
    )
    assert set(files) == {managed.CONFIG_PATH}


def test_render_t1_with_a_docs_page_holds_ref_check_toml(tmp_path: Path) -> None:
    """In copy mode, a T1 survey with a Markdown page under `docs/` adds `ref_check.toml`; global mode never holds it (D12.9, D14.8).

    arch: D12.9, D14.22, D14.4, D14.8
    """
    survey = _with_files(_survey(tmp_path), ("README.md", "docs/guide.md"))
    files = managed.render(Config(refs_mode="copy"), survey)
    assert managed.REF_CHECK_CONFIG_PATH in files
    assert managed.CI_PATH not in files
    assert managed.GITLEAKS_CONFIG_PATH not in files
    assert "readme = false" in files[managed.REF_CHECK_CONFIG_PATH]
    assert managed.REF_CHECK_CONFIG_PATH not in managed.render(Config(), survey)
    bare = managed.render(Config(refs_mode="copy"), _survey(tmp_path))
    assert managed.REF_CHECK_CONFIG_PATH not in bare


def test_render_t1_with_a_markdown_extension_page_holds_ref_check_toml(
    tmp_path: Path,
) -> None:
    """A `.markdown` page under `docs/` counts as a page, as a `.md` page does (D12.9, D12.11).

    arch: D12.9, D12.11, D14.8
    """
    survey = _with_files(_survey(tmp_path), ("README.md", "docs/guide.markdown"))
    files = managed.render(Config(refs_mode="copy"), survey)
    assert managed.REF_CHECK_CONFIG_PATH in files
    assert managed.AGENT_RULES_PATH not in files
    assert managed.refcheck_switches_on(Config(), survey)


def test_render_t2_holds_ci_gitleaks_ref_check_and_vale(tmp_path: Path) -> None:
    """At T2 with `docs = "auto"` the set holds no CI, gitleaks, Vale or agent rules file (D14.8).

    arch: D12.9, D14.8
    """
    for cfg in (Config(), Config(refs_mode="copy")):
        files = managed.render(cfg, _survey(tmp_path, tier="T2"))
        assert not set(managed.LEGACY_PATHS) & set(files)
    copy = managed.render(Config(refs_mode="copy"), _survey(tmp_path, tier="T2"))
    assert "readme = true" in copy[managed.REF_CHECK_CONFIG_PATH]


def test_render_vale_needs_t2_even_with_docs_full(tmp_path: Path) -> None:
    """An explicit `docs = "full"` at T1 renders no Vale file, and `readme` at T2 renders none (D12.9).

    arch: D12.9
    """
    t1_full = managed.render(Config(docs="full"), _survey(tmp_path))
    t2_readme = managed.render(Config(docs="readme"), _survey(tmp_path, tier="T2"))
    assert not set(VALE_FILES) & set(t1_full)
    assert not set(VALE_FILES) & set(t2_readme)


def test_render_t0_holds_nothing_until_trueup_toml_exists(tmp_path: Path) -> None:
    """At T0 the set is empty; a `trueup.toml` on disk keeps that path in the set (D12.9).

    arch: D12.9
    """
    survey = _survey(tmp_path, tier="T0")
    assert managed.render(Config(), survey) == {}
    (tmp_path / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    assert set(managed.render(Config(), survey)) == {managed.CONFIG_PATH}


def test_render_copy_mode_checker_is_in_the_set_at_any_tier(tmp_path: Path) -> None:
    """The copy-mode checker stays in the set at T0 (D12.9).

    arch: D12.9
    """
    files = managed.render(Config(refs_mode="copy"), _survey(tmp_path, tier="T0"))
    assert "ref_check.py" in files


def test_render_keeps_a_managed_file_on_disk_below_its_tier(tmp_path: Path) -> None:
    """A copy-mode `ref_check.toml` with the header stays in the T1 set; one without the header does not (I-42).

    A CI workflow with the header is no longer in the set at any tier: it
    is a `managed-legacy` row (D14.8).

    arch: D12.9, D14.8
    """
    survey = _survey(tmp_path)
    cfg = Config(refs_mode="copy")
    full = managed.render(cfg, _survey(tmp_path, tier="T2"))
    checker_config = tmp_path / managed.REF_CHECK_CONFIG_PATH
    checker_config.write_text(full[managed.REF_CHECK_CONFIG_PATH], encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / managed.CI_PATH).write_text(
        f"# {MANAGED_HEADER}\non: push\n", encoding="utf-8"
    )
    files = managed.render(cfg, survey)
    assert managed.REF_CHECK_CONFIG_PATH in files
    assert managed.CI_PATH not in files
    checker_config.write_text("[checks]\nlinks = true\n", encoding="utf-8")
    assert managed.REF_CHECK_CONFIG_PATH not in managed.render(cfg, survey)


def test_setup_findings_never_ask_for_a_path_above_the_tier(tmp_path: Path) -> None:
    """At T1 no finding asks to add a T2 path, and an unmanaged file there gives no finding (I-42).

    arch: D12.9, I-42
    """
    (tmp_path / "lint" / "gitleaks").mkdir(parents=True)
    (tmp_path / managed.GITLEAKS_CONFIG_PATH).write_text(
        "# the person's own gitleaks config\n", encoding="utf-8"
    )
    ids = _ids(managed.setup_findings(_survey(tmp_path), None))
    for path in (*_T2_ONLY, *VALE_FILES):
        assert f"file-managed:{path}" not in ids
    assert "tool-missing:docs/vale" not in ids


def test_no_lint_hook_names_gitleaks_or_its_config(tmp_path: Path) -> None:
    """No lint hook names gitleaks or `lint/gitleaks/gitleaks.toml`, in any mode (D14.6).

    The D12.9 switch between the tool default and `--config` left the hook
    list with the gitleaks hook; `check` owns the gitleaks run now.

    arch: D12.9, D14.8, D14.22, D14.6
    """
    configs = (
        Config(),
        Config(docs="full", languages={"python": "strict", "typescript": "strict"}),
    )
    for cfg in configs:
        entries = [hook.entry for hook in managed.lint_hooks(cfg)]
        assert not [entry for entry in entries if "gitleaks" in entry]


def test_render_keeps_docs_auto_in_trueup_toml(tmp_path: Path) -> None:
    """The rendered `trueup.toml` keeps `docs = "auto"`; only the other files use the resolved mode (D12.9).

    `render` writes the default `docs` value only when the file set it
    (D14.3); the resolved `full` never reaches `trueup.toml`.

    arch: D12.9, D14.3
    """
    files = managed.render(Config(), _survey(tmp_path, tier="T2"))
    assert "docs =" not in files[managed.CONFIG_PATH]
    files = managed.render(
        Config(explicit=frozenset({"docs"})), _survey(tmp_path, tier="T2")
    )
    assert 'docs = "auto"' in files[managed.CONFIG_PATH]


# -- D12.7: the agent rules file, now a legacy path (D14.8) -------------------

_OLD_RULES_FILE = (
    '---\npaths:\n  - "docs/**"\n---\n'
    f"<!-- {MANAGED_HEADER} -->\n"
    "Write docs in Simplified Technical English.\n"
)
"""The agent rules file as an earlier trueup wrote it: front matter, then the header on line 5."""


def test_agent_rules_file_is_in_the_t2_set_with_front_matter_and_header(
    tmp_path: Path,
) -> None:
    """At T2 the set holds no `.claude/rules/trueup.md`; an old one with the header after its front matter is a `managed-legacy` row (D14.8, D14.10).

    arch: D12.7, D14.22, D14.4, D14.8
    """
    survey = _survey(tmp_path, tier="T2")
    assert managed.AGENT_RULES_PATH not in managed.render(Config(), survey)
    full = tmp_path / managed.AGENT_RULES_PATH
    full.parent.mkdir(parents=True)
    full.write_text(_OLD_RULES_FILE, encoding="utf-8")
    row = _ids(managed.setup_findings(survey, Config()))[
        f"managed-legacy:{managed.AGENT_RULES_PATH}"
    ]
    assert (row.severity, row.auto, row.category) == ("info", False, "setup")


def test_agent_rules_file_needs_t2_without_a_docs_page(tmp_path: Path) -> None:
    """A T1 tree has no rules file in the set, with or without a page under `docs/` (D14.8).

    arch: D12.7, D14.8
    """
    bare = managed.render(Config(), _survey(tmp_path))
    paged = managed.render(
        Config(), _with_files(_survey(tmp_path), ("README.md", "docs/guide.md"))
    )
    assert managed.AGENT_RULES_PATH not in bare
    assert managed.AGENT_RULES_PATH not in paged


def test_agent_rules_file_header_is_the_first_line_after_front_matter(
    tmp_path: Path,
) -> None:
    """`_is_managed_on_disk` reads line 5 of the rules file, so a file with another line 5 is not trueup's.

    arch: D12.7, D14.8
    """
    content = _OLD_RULES_FILE
    path = managed.AGENT_RULES_PATH
    assert managed._is_managed_on_disk(path, content, content)
    own = '---\npaths:\n  - "docs/**"\n---\n<!-- my own rule -->\n'
    assert not managed._is_managed_on_disk(path, own, content)
    assert not managed._is_managed_on_disk(path, f"# Rules\n{content}", content)
    assert not managed._is_managed_on_disk(path, "---\n", content)


def test_agent_rules_file_that_is_not_trueups_stays_out_of_the_set(
    tmp_path: Path,
) -> None:
    """A rules file the person wrote gets no `file-managed` row and no `managed-legacy` row (D12.9, D12.7, D14.8).

    arch: D12.7, D14.8
    """
    full = tmp_path / managed.AGENT_RULES_PATH
    full.parent.mkdir(parents=True)
    full.write_text("# my own rules\n", encoding="utf-8")
    ids = _ids(managed.setup_findings(_survey(tmp_path), None))
    assert f"file-managed:{managed.AGENT_RULES_PATH}" not in ids
    assert f"managed-legacy:{managed.AGENT_RULES_PATH}" not in ids


# -- D14.8: the managed set cut, LEGACY_PATHS and the managed-legacy row -----


def test_legacy_paths_hold_the_old_managed_files_and_the_names_stay() -> None:
    """`LEGACY_PATHS` holds every path trueup no longer manages; the constant names stay importable.

    The expected paths are literals, not the constants under test, so a
    changed constant fails here (D15.38).

    arch: D14.22, D14.4, D14.8
    arch: D15.38
    """
    from trueup import rulesets

    vale_styles = ("Banned", "Contractions", "FirstPerson", "Latin")
    vale_styles += ("SentenceLength", "We", "Will")
    expected = {
        ".pre-commit-config.yaml",
        ".github/workflows/trueup.yml",
        ".editorconfig",
        "lint/jscpd.json",
        "lint/gitleaks/gitleaks.toml",
        ".claude/rules/trueup.md",
        "lint/typescript/node_modules",
        "lint/typescript/eslint.config.mjs",
        "lint/typescript/package.json",
        "lint/vale/.vale.ini",
        "lint/vale/styles/config/vocabularies/Trueup/accept.txt",
        *(f"lint/vale/styles/Trueup/{name}.yml" for name in vale_styles),
    }
    assert set(managed.LEGACY_PATHS) == expected
    assert len(managed.LEGACY_PATHS) == len(expected)
    assert (
        managed.PRE_COMMIT_PATH,
        managed.CI_PATH,
        managed.EDITORCONFIG_PATH,
        managed.JSCPD_PATH,
        managed.GITLEAKS_CONFIG_PATH,
        managed.AGENT_RULES_PATH,
        managed.ESLINT_PACKAGES_DIR,
        rulesets.ESLINT_CONFIG_TARGET,
        rulesets.ESLINT_PACKAGE_TARGET,
    ) == (
        ".pre-commit-config.yaml",
        ".github/workflows/trueup.yml",
        ".editorconfig",
        "lint/jscpd.json",
        "lint/gitleaks/gitleaks.toml",
        ".claude/rules/trueup.md",
        "lint/typescript/node_modules",
        "lint/typescript/eslint.config.mjs",
        "lint/typescript/package.json",
    )
    assert set(VALE_FILES) <= expected
    assert (
        managed.CONFIG_PATH,
        managed.REF_CHECK_CONFIG_PATH,
        managed.STALE_COPY_PATH,
    ) == ("trueup.toml", "ref_check.toml", "ref_check.py")
    assert not {"trueup.toml", "ref_check.toml", "ref_check.py"} & set(
        managed.LEGACY_PATHS
    )


def test_render_holds_trueup_toml_and_the_copy_pair_only(tmp_path: Path) -> None:
    """At every tier and in both modes, `render` holds no path but `trueup.toml` and the copy-mode pair.

    arch: D14.22, D14.4, D14.8
    """
    every_language = {language: "strict" for language in LANGUAGES}
    for mode in ("global", "copy"):
        cfg = Config(languages=every_language, docs="full", refs_mode=mode)
        allowed = {managed.CONFIG_PATH}
        if mode == "copy":
            allowed |= {cfg.refs_path, managed.REF_CHECK_CONFIG_PATH}
        for tier in ("T0", "T1", "T2", "T3"):
            files = managed.render(cfg, _survey(tmp_path, tier=tier))
            assert set(files) <= allowed, (mode, tier, sorted(files))


def _legacy_tree(root: Path) -> tuple[str, ...]:
    """Write one file of the old managed lint tree per kind under `root`.

    Args:
        root: The target root.

    Returns:
        The repo paths of the files under `lint/`, for the survey.
    """
    texts = {
        managed.PRE_COMMIT_PATH: f"# {MANAGED_HEADER}\nrepos: []\n",
        managed.CI_PATH: f"# {MANAGED_HEADER}\non: push\n",
        managed.GITLEAKS_CONFIG_PATH: f"# {MANAGED_HEADER}\n[extend]\n",
        "lint/python/ruff.toml": f"# {MANAGED_HEADER}\nline-length = 88\n",
        managed.JSCPD_PATH: '{"_managed": "trueup", "threshold": 0}\n',
        "lint/vale/styles/config/vocabularies/Trueup/accept.txt": "trueup\n",
    }
    for path, text in texts.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
    (root / managed.ESLINT_PACKAGES_DIR).mkdir(parents=True)
    return tuple(sorted(path for path in texts if path.startswith("lint/")))


def test_managed_legacy_is_info_for_each_file_an_earlier_trueup_wrote(
    tmp_path: Path,
) -> None:
    """Each file of the old managed lint tree gives one `info` `managed-legacy` row that never joins the plan.

    The row informs: it is not automatic, it is not in the plan, and it
    changes no exit code (I-42 amended).

    arch: D14.22, D14.4, D14.8, I-42
    """
    from trueup.findings import build_plan

    lint_files = _legacy_tree(tmp_path)
    survey = _with_files(_survey(tmp_path, tier="T2"), lint_files)
    findings = managed.setup_findings(survey, _python_cfg())
    rows = {
        finding.path: finding
        for finding in findings
        if finding.rule == "managed-legacy"
    }
    assert set(rows) == {
        managed.PRE_COMMIT_PATH,
        managed.CI_PATH,
        managed.GITLEAKS_CONFIG_PATH,
        managed.JSCPD_PATH,
        managed.ESLINT_PACKAGES_DIR,
        "lint/python/ruff.toml",
        "lint/vale/styles/config/vocabularies/Trueup/accept.txt",
    }
    for path, row in rows.items():
        assert row.id == f"managed-legacy:{path}"
        assert (row.category, row.severity, row.auto) == ("setup", "info", False)
        assert row.action == (
            "trueup no longer manages this file; remove it when you have "
            "moved to trueup lint (see the reference page)"
        )
    assert not [finding for finding in findings if finding.rule == "file-managed"]
    plan = build_plan(findings, {})
    assert not [finding for finding in plan if finding.rule == "managed-legacy"]


def test_managed_legacy_skips_a_file_the_person_owns(tmp_path: Path) -> None:
    """A file at a legacy path with no trueup mark gives no finding at all: the fastapi case (D14.8, I-42).

    arch: D14.22, D14.4, D14.8
    """
    own = {
        managed.PRE_COMMIT_PATH: "repos:\n  - repo: local\n    hooks: []\n",
        managed.CI_PATH: "on: push\njobs: {}\n",
        "lint/ruff.toml": "line-length = 100\n",
        "lint/ts/package.json": '{"name": "own"}\n',
    }
    for path, text in own.items():
        full = tmp_path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
    survey = _with_files(
        _survey(tmp_path, tier="T2"), ("lint/ruff.toml", "lint/ts/package.json")
    )
    ids = _ids(managed.setup_findings(survey, _python_cfg()))
    for path in own:
        assert f"managed-legacy:{path}" not in ids, path
        assert f"file-managed:{path}" not in ids, path


def test_setup_findings_ask_for_no_legacy_path(tmp_path: Path) -> None:
    """No `file-managed` row names a legacy path, absent or present, at any tier (D14.8).

    arch: D14.22, D14.4, D14.8
    """
    for tier in ("T1", "T2", "T3"):
        survey = _survey(tmp_path, tier=tier, present={"python": 80})
        for cfg in (_python_cfg(), _python_cfg(refs_mode="copy")):
            ids = _ids(managed.setup_findings(survey, cfg))
            for path in managed.LEGACY_PATHS:
                assert f"file-managed:{path}" not in ids, (tier, path)


def test_refcheck_switches_on_follows_the_tier_and_the_docs_pages(
    tmp_path: Path,
) -> None:
    """`refcheck_switches_on` is true at T2 and T3, and at T1 with a page under the docs directory.

    arch: D14.22, D14.4, D14.8
    """
    cfg = Config()
    for tier, expected in (("T0", False), ("T1", False), ("T2", True), ("T3", True)):
        survey = _survey(tmp_path, tier=tier)
        assert managed.refcheck_switches_on(cfg, survey) is expected, tier
    paged = ("README.md", "docs/how-to/guide.md")
    assert managed.refcheck_switches_on(cfg, _with_files(_survey(tmp_path), paged))
    t0 = _with_files(_survey(tmp_path, tier="T0"), paged)
    assert not managed.refcheck_switches_on(cfg, t0)
    other = ("docs/notes.txt", "documentation/guide.md", "src/docs/a.md")
    assert not managed.refcheck_switches_on(cfg, _with_files(_survey(tmp_path), other))
    custom = Config(layout_docs_dir="documentation")
    assert managed.refcheck_switches_on(custom, _with_files(_survey(tmp_path), other))
    assert not managed.refcheck_switches_on(
        custom, _with_files(_survey(tmp_path), paged)
    )


def test_gitignore_row_follows_scratch_gitignore(tmp_path: Path) -> None:
    """The `gitignore:.gitignore` row comes only when `scratch_gitignore` is true.

    arch: D14.22, D14.4, D14.8
    """
    survey = _survey(tmp_path)
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    assert "gitignore:.gitignore" in _ids(managed.setup_findings(survey, Config()))
    assert "gitignore:.gitignore" not in _ids(
        managed.setup_findings(survey, Config(scratch_gitignore=False))
    )


def test_vale_tool_row_follows_the_resolved_docs_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tool-missing:docs/vale` stays when the resolved docs mode is `full`, though the Vale files left the set.

    arch: D14.22, D14.4, D14.8
    """
    monkeypatch.setattr(managed.shutil, "which", lambda name: None)
    t2 = _ids(managed.setup_findings(_survey(tmp_path, tier="T2"), Config()))
    assert t2["tool-missing:docs/vale"].severity == "info"
    t1 = _ids(managed.setup_findings(_survey(tmp_path), Config()))
    assert "tool-missing:docs/vale" not in t1
    readme = _ids(
        managed.setup_findings(_survey(tmp_path, tier="T2"), Config(docs="readme"))
    )
    assert "tool-missing:docs/vale" not in readme


def test_trueup_own_paths_keep_their_entries() -> None:
    """`TRUEUP_OWN_PATHS` keeps the paths trueup still writes and drops the old managed paths.

    Decision D15.37 inverts the old expectation: an old managed path is
    the person's file after D14.8, so it counts towards the tier and the
    root budget. The test name is from before that decision.

    arch: D14.22, D14.4, D14.8, D15.37
    """
    from trueup import survey

    for path in (
        managed.CONFIG_PATH,
        managed.REF_CHECK_CONFIG_PATH,
        ".trueup-baseline.json",
    ):
        assert path in survey.TRUEUP_OWN_PATHS, path
        assert survey.is_trueup_path(path), path
    for path in (
        managed.PRE_COMMIT_PATH,
        managed.EDITORCONFIG_PATH,
        managed.CI_PATH,
        managed.AGENT_RULES_PATH,
        *managed.LEGACY_PATHS,
    ):
        assert path not in survey.TRUEUP_OWN_PATHS, path
        assert not survey.is_trueup_path(path), path


def _switches(text: str) -> dict[str, bool]:
    """Read the `[checks]` switches of one rendered `ref_check.toml`.

    Args:
        text: The rendered text.

    Returns:
        Switch name to value.
    """
    return tomllib.loads(text)["checks"]


def test_render_ref_check_config_reads_the_refs_switches_of_the_effective_config(
    tmp_path: Path,
) -> None:
    """`registry`, `comments` and `links` follow `[refs]`; `layout` needs one `[layout]` rule on.

    arch: D14.22, D14.4, D14.5
    """
    t2 = _survey(tmp_path, tier="T2")
    every = _switches(managed.render_ref_check_config(Config(), t2))
    assert every == dict.fromkeys(
        ("registry", "comments", "links", "layout", "readme"), True
    )
    for field, switch in (
        ("refs_registry", "registry"),
        ("refs_comments", "comments"),
        ("refs_links", "links"),
    ):
        switches = _switches(
            managed.render_ref_check_config(replace(Config(), **{field: False}), t2)
        )
        assert switches == {**every, switch: False}, field
    no_rules = Config(layout_front_matter=False, layout_types=False, layout_index=False)
    switches = _switches(managed.render_ref_check_config(no_rules, t2))
    assert switches == {**every, "layout": False}
    one_rule = replace(no_rules, layout_types=True)
    assert _switches(managed.render_ref_check_config(one_rule, t2))["layout"] is True


def test_render_ref_check_config_turns_every_switch_off_below_its_tier(
    tmp_path: Path,
) -> None:
    """Every switch is off when `refcheck_switches_on` is false; `readme` mode keeps `layout` and `readme` off.

    arch: D14.22, D14.4, D14.5
    """
    for tier in ("T0", "T1"):
        text = managed.render_ref_check_config(
            Config(docs="full"), _survey(tmp_path, tier=tier)
        )
        assert not any(_switches(text).values()), tier
    paged = _with_files(_survey(tmp_path, tier="T1"), ("docs/guide.md",))
    switches = _switches(managed.render_ref_check_config(Config(), paged))
    assert switches == {
        "registry": True,
        "comments": True,
        "links": True,
        "layout": False,
        "readme": False,
    }
    full = _switches(managed.render_ref_check_config(Config(docs="full"), paged))
    assert all(full.values())


def test_render_ref_check_config_writes_the_layout_table_only_off_its_defaults(
    tmp_path: Path,
) -> None:
    """The `[layout]` table holds all four keys when one is not its default, and the checker reads it.

    arch: D14.5, D14.22, D14.4
    """
    t2 = _survey(tmp_path, tier="T2")
    assert "[layout]" not in managed.render_ref_check_config(Config(), t2)
    for changed in (
        {"layout_docs_dir": "documentation"},
        {"layout_front_matter": False},
        {"layout_types": False},
        {"layout_index": False},
    ):
        cfg = replace(Config(), **changed)
        text = managed.render_ref_check_config(cfg, t2)
        table = tomllib.loads(text)["layout"]
        assert table == {
            "docs_dir": cfg.layout_docs_dir,
            "front_matter": cfg.layout_front_matter,
            "types": cfg.layout_types,
            "index": cfg.layout_index,
        }, changed
        (tmp_path / "ref_check.toml").write_text(text, encoding="utf-8")
        loaded = ref_check.load_config(tmp_path, tmp_path / "ref_check.toml")
        assert (
            loaded.docs_dir,
            loaded.front_matter,
            loaded.types,
            loaded.index,
        ) == (
            cfg.layout_docs_dir,
            cfg.layout_front_matter,
            cfg.layout_types,
            cfg.layout_index,
        ), changed


def test_refs_layout_false_keeps_the_readme_check_on(tmp_path: Path) -> None:
    """`[refs] layout = false` turns check h and the index rules off, and keeps the README check on.

    D14.2 gives `[layout] index` the index rules of check h and check i
    only, so the `[layout]` table carries it, and the `readme` switch stays
    on. An adopter with `layout = false` keeps its README rows.

    arch: D14.22, D14.4, D14.5
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ndocs = "full"\n\n[refs]\nlayout = false\n', encoding="utf-8"
    )
    cfg = config.load(tmp_path)
    assert cfg is not None
    text = managed.render_ref_check_config(cfg, _survey(tmp_path, tier="T2"))
    switches = _switches(text)
    assert switches["layout"] is False
    assert switches["readme"] is True
    assert tomllib.loads(text)["layout"]["index"] is False


def test_render_ref_check_config_turns_the_licence_off_for_public_false(
    tmp_path: Path,
) -> None:
    """`public = false` in the target file renders `[checks] licence = false`; an unset `public` writes no key.

    arch: D15.14, D15.15
    """
    survey = _survey(tmp_path, tier="T2")
    unset = managed.render_ref_check_config(Config(explicit=frozenset()), survey)
    assert "licence" not in _switches(unset)
    off = managed.render_ref_check_config(
        Config(explicit=frozenset({"public"}), public=False), survey
    )
    assert _switches(off)["licence"] is False
    public = managed.render_ref_check_config(
        Config(explicit=frozenset({"public"}), public=True), survey
    )
    assert "licence" not in _switches(public)


def test_ref_check_layout_switch_follows_the_layout_switches_not_refs_layout(
    tmp_path: Path,
) -> None:
    """A merged config with `refs_layout` off and one `[layout]` switch on turns check h on.

    A higher layer's `[layout]` switch wins over a lower `[refs] layout`.

    arch: D15.29
    """
    cfg = Config(
        docs="full",
        refs_layout=False,
        layout_front_matter=True,
        layout_types=False,
        layout_index=False,
    )
    text = managed.render_ref_check_config(cfg, _survey(tmp_path, tier="T2"))
    assert tomllib.loads(text)["checks"]["layout"] is True
