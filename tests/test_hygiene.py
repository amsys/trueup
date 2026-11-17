"""Tests for `trueup.hygiene`: the eight D5.4 slop rows."""

from __future__ import annotations

import base64
import dataclasses
import os
import subprocess
import types
from pathlib import Path

import pytest

from trueup import config, hygiene, survey as survey_mod


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _findings_by_rule(root: Path, rule: str) -> list:
    """Survey `root` and give the `hygiene_findings` of one rule.

    Args:
        root: The repository root to survey and check.
        rule: The rule name to filter on.

    Returns:
        The findings whose `rule` equals `rule`.
    """
    survey = survey_mod.run(root)
    return [
        finding for finding in hygiene.hygiene_findings(survey) if finding.rule == rule
    ]


def _commit_all(root: Path) -> None:
    """Commit every file under `root`, with signing off (this machine signs commits by default).

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


def test_scratch_flags_an_unreferenced_scratch_name(tmp_path: Path) -> None:
    """A tracked `tmp_*` file that no other file mentions is an auto `error`; untracked, it is manual (D5.4).

    arch: D5.4, D5.6
    """
    _git_init(tmp_path)
    (tmp_path / "tmp.txt").write_text("draft\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("the project\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "scratch")
    assert [finding.id for finding in findings] == ["scratch:tmp.txt"]
    assert findings[0].severity == "error"
    assert findings[0].auto is False
    assert "by hand" in findings[0].action
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "scratch")
    assert findings[0].auto is True
    assert findings[0].action == "git rm tmp.txt"


@pytest.mark.parametrize(
    "name",
    [
        "template.py",
        "templates.py",
        "temperature.rs",
        "temp_table.sql",
        "tempo.go",
        "notes.py",
        "notesController.php",
        "notes_service.py",
        "scratchpad.rs",
        "tmpl.go",
        "tmp.py",
    ],
)
def test_scratch_word_with_a_source_extension_is_not_scratch(name: str) -> None:
    """A source file whose stem starts with a scratch word is not scratch (D5.4).

    arch: D5.4
    """
    assert hygiene.looks_scratch(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "tmp",
        "tmp1",
        "tmp-draft.md",
        "tmp_notes.txt",
        "notes.md",
        "notes-tmp.md",
        "scratch.txt",
        "temp 2.log",
        "untitled3",
        "report.bak",
        "main.py.orig",
        "fix.rej",
        ".main.py.swp",
        "config~",
        "report copy.docx",
        "Copy of plan.txt",
    ],
)
def test_scratch_names_still_match(name: str) -> None:
    """The scratch words with a text suffix, and the backup and copy globs, stay scratch (D5.4).

    arch: D5.4
    """
    assert hygiene.looks_scratch(name) is True


def test_scratch_skips_the_scratch_dir_and_secret_names(tmp_path: Path) -> None:
    """Nothing under `.scratch/` is scratch, even before `.gitignore` names it, nor is a secret-file name (D5.4).

    arch: D5.4, D5.8
    """
    _git_init(tmp_path)
    (tmp_path / ".scratch").mkdir()
    (tmp_path / ".scratch" / "tmp-notes.md").write_text("draft\n", encoding="utf-8")
    (tmp_path / ".env.bak").write_text("KEY=1\n", encoding="utf-8")
    assert hygiene.looks_scratch(".env.bak") is True
    assert _findings_by_rule(tmp_path, "scratch") == []
    assert [finding.id for finding in _findings_by_rule(tmp_path, "secret-file")] == [
        "secret-file:.env.bak"
    ]


def test_scratch_allow_exempts_a_path_or_a_name(tmp_path: Path) -> None:
    """`[scratch] allow` exempts a path glob or a basename glob from the scratch row (D5.3, D5.4).

    arch: D5.3, D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("page\n", encoding="utf-8")
    (tmp_path / "tmp-keep.txt").write_text("kept\n", encoding="utf-8")
    (tmp_path / "tmp-drop.txt").write_text("drop\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[scratch]\nallow = ["docs/*.md", "tmp-k*"]\n', encoding="utf-8"
    )
    assert [finding.id for finding in _findings_by_rule(tmp_path, "scratch")] == [
        "scratch:tmp-drop.txt"
    ]


def test_scratch_spares_a_name_mentioned_elsewhere(tmp_path: Path) -> None:
    """A scratch-looking name is not flagged when another file mentions its basename.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "tmp_notes.txt").write_text("draft\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("clean:\n\trm tmp_notes.txt\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "scratch")
    assert findings == []


@pytest.mark.parametrize(
    "name",
    [
        "README.old.md",
        "x.bak.py",
        "data.orig.csv",
        "config.backup.json",
    ],
)
def test_scratch_backup_word_in_the_extension_chain_is_scratch(name: str) -> None:
    """A backup word anywhere after the first `.` is scratch, whatever the final extension (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "ARCHITECTURE_v2_draft.md",
        "plan-copy.txt",
        "notes-old.rst",
        "spec_backup.log",
    ],
)
def test_scratch_copy_suffix_in_a_document_name_is_scratch(name: str) -> None:
    """A document stem ending in a version, draft, copy or backup marker is scratch (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch(name) is True


@pytest.mark.parametrize("name", ["v0_v1.rs", "service_v2.py", "parser-copy.go"])
def test_scratch_copy_suffix_never_matches_a_source_extension(name: str) -> None:
    """The copy-suffix rule never fires on a source extension, so `v0_v1.rs` stays clean (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch(name) is False


@pytest.mark.parametrize(
    "name", ["scratch_fold.rs", "untitled-draft.go", "scratch2.py"]
)
def test_scratch_prefix_matches_any_extension(name: str) -> None:
    """`scratch` or `untitled`, then a digit or a separator, is scratch at any extension (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch(name) is True


@pytest.mark.parametrize("name", ["template.py", "notes_service.py", "v0_v1.rs"])
def test_scratch_i_fp_names_stay_clean(name: str) -> None:
    """The three I-fp names stay clean under the widened patterns (D10.3, D10.9 I-fp).

    arch: D10.3
    """
    assert hygiene.looks_scratch(name) is False


@pytest.mark.parametrize(
    "path",
    ["tmp/report.py", "temp/plan.md", "scratch/build.sh"],
)
def test_looks_scratch_path_flags_a_clean_name_under_a_scratch_directory(
    path: str,
) -> None:
    """A clean basename under `tmp/`, `temp/` or `scratch/` is scratch by the path rule (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch_path(path) is True


@pytest.mark.parametrize(
    "path",
    ["tmpfoo/report.py", "notes/plan.py", "src/report.py"],
)
def test_looks_scratch_path_needs_an_exact_directory_segment(path: str) -> None:
    """A directory that only starts with, or is not, a scratch word is not caught (D10.3).

    arch: D10.3
    """
    assert hygiene.looks_scratch_path(path) is False


def test_scratch_row_flags_a_clean_name_under_a_scratch_directory(
    tmp_path: Path,
) -> None:
    """The `scratch` row flags a plain-named tracked file sitting under `tmp/` (D10.3).

    arch: D10.3
    """
    _git_init(tmp_path)
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / "report.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("the project\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "scratch")
    assert [finding.id for finding in findings] == ["scratch:tmp/report.py"]


def test_scratch_exemption_needs_a_relative_or_slashed_mention(tmp_path: Path) -> None:
    """A bare basename mentioned from another directory no longer exempts a file (D10.12).

    A mention of the candidate's path relative to the mentioning file's own
    directory, or of the full repo path with a `/`, still exempts it.

    arch: D10.3, D10.12
    """
    _git_init(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "sub" / "tmp_notes.txt").write_text("draft\n", encoding="utf-8")
    # A bare basename mentioned from a different directory: no longer exempt.
    (tmp_path / "other" / "readme.md").write_text(
        "see tmp_notes.txt for the plan\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "scratch")
    assert [finding.id for finding in findings] == ["scratch:sub/tmp_notes.txt"]

    # The same basename, mentioned from the candidate's own directory: exempt.
    (tmp_path / "sub" / "readme.md").write_text(
        "see tmp_notes.txt for the plan\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "scratch")
    assert findings == []

    # The full repo path, with a `/`, mentioned from any directory: exempt.
    (tmp_path / "sub" / "readme.md").unlink()
    (tmp_path / "other" / "readme.md").write_text(
        "see sub/tmp_notes.txt for the plan\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "scratch")
    assert findings == []


def test_scratch_last_copy_keeps_one_removal_manual(tmp_path: Path) -> None:
    """When every copy of a content is scratch, the first sorted copy stays manual (I-35).

    An automatic id never removes every tracked copy of a content, so
    `tmp1.txt` (sorted first) becomes a manual finding and `tmp2.txt`
    stays automatic.

    arch: D10.3, I-35
    """
    _git_init(tmp_path)
    content = ("same scratch content, padded past the minimum size\n" * 2).encode()
    assert len(content) >= 64
    (tmp_path / "tmp1.txt").write_bytes(content)
    (tmp_path / "tmp2.txt").write_bytes(content)
    _commit_all(tmp_path)
    findings = {
        finding.path: finding for finding in _findings_by_rule(tmp_path, "scratch")
    }
    assert set(findings) == {"tmp1.txt", "tmp2.txt"}
    assert findings["tmp1.txt"].auto is False
    assert findings["tmp1.txt"].evidence == "the last copy of this content"
    assert findings["tmp2.txt"].auto is True


def test_scratch_last_copy_rule_also_counts_an_artifact_copy(tmp_path: Path) -> None:
    """A copy the `artifact` row auto-removes is not a safe "kept" original (I-35).

    `output.pyc` is build output, so the `artifact` row removes it with
    its own automatic id. It is not a kept copy of this content: the one
    `scratch` copy, `tmp1.txt`, must itself stay manual, or an
    `--all-auto` run removes every tracked copy of this content.

    arch: D10.3
    """
    _git_init(tmp_path)
    content = ("same content, one side scratch, one side build output\n" * 2).encode()
    assert len(content) >= 64
    (tmp_path / "tmp1.txt").write_bytes(content)
    (tmp_path / "output.pyc").write_bytes(content)
    _commit_all(tmp_path)
    findings = {
        finding.path: finding for finding in _findings_by_rule(tmp_path, "scratch")
    }
    assert set(findings) == {"tmp1.txt"}
    assert findings["tmp1.txt"].auto is False
    assert findings["tmp1.txt"].evidence == "the last copy of this content"


def test_scratch_last_copy_rule_skips_an_untracked_copy(tmp_path: Path) -> None:
    """An untracked scratch copy does not hold the manual slot of the last copy (I-35).

    `tmp1.txt` sorts first but git does not track it, so its finding is
    manual already. The one tracked copy, `tmp2.txt`, must stay manual
    too, or an automatic id removes every tracked copy of this content.

    arch: D10.3
    """
    _git_init(tmp_path)
    content = ("same scratch content, one copy tracked, one copy not\n" * 2).encode()
    assert len(content) >= 64
    (tmp_path / "tmp2.txt").write_bytes(content)
    _commit_all(tmp_path)
    (tmp_path / "tmp1.txt").write_bytes(content)
    findings = {
        finding.path: finding for finding in _findings_by_rule(tmp_path, "scratch")
    }
    assert set(findings) == {"tmp1.txt", "tmp2.txt"}
    assert findings["tmp1.txt"].auto is False
    assert findings["tmp2.txt"].auto is False
    assert findings["tmp2.txt"].evidence == "the last copy of this content"


def test_scratch_last_copy_rule_needs_a_tracked_kept_original(tmp_path: Path) -> None:
    """An untracked clean copy is not a tracked copy that stays (I-35).

    `README.md` is clean but git does not track it. Removing the tracked
    `draft.md` by an automatic id removes every tracked copy of
    this content, so that finding stays manual.

    arch: D10.3
    """
    _git_init(tmp_path)
    content = ("same content, the tracked side is a draft name\n" * 2).encode()
    assert len(content) >= 64
    (tmp_path / "draft.md").write_bytes(content)
    _commit_all(tmp_path)
    (tmp_path / "README.md").write_bytes(content)
    findings = {
        finding.path: finding for finding in _findings_by_rule(tmp_path, "scratch")
    }
    assert set(findings) == {"draft.md"}
    assert findings["draft.md"].auto is False
    assert findings["draft.md"].evidence == "the last copy of this content"


def test_scratch_last_copy_rule_holds_for_a_small_content(tmp_path: Path) -> None:
    """The last-copy rule also holds below the `duplicate` minimum size (I-35).

    arch: D10.3
    """
    _git_init(tmp_path)
    content = b"short draft\n"
    assert len(content) < 64
    (tmp_path / "tmp1.txt").write_bytes(content)
    (tmp_path / "tmp2.txt").write_bytes(content)
    _commit_all(tmp_path)
    findings = {
        finding.path: finding for finding in _findings_by_rule(tmp_path, "scratch")
    }
    assert set(findings) == {"tmp1.txt", "tmp2.txt"}
    assert findings["tmp1.txt"].auto is False
    assert findings["tmp1.txt"].evidence == "the last copy of this content"
    assert findings["tmp2.txt"].auto is True


def test_scratch_copy_evidence_names_the_kept_original(tmp_path: Path) -> None:
    """A scratch copy of a kept file's content gets "copy of <original>" evidence (D10.3 R4).

    arch: D10.3
    """
    _git_init(tmp_path)
    content = ("same content, kept by one file and scratch in another\n" * 8).encode()
    assert len(content) >= 256
    (tmp_path / "README.md").write_bytes(content)
    (tmp_path / "README_draft.md").write_bytes(content)
    findings = _findings_by_rule(tmp_path, "scratch")
    assert [finding.id for finding in findings] == ["scratch:README_draft.md"]
    assert "copy of README.md" in findings[0].evidence


def test_duplicate_drops_a_path_the_scratch_row_already_flags(tmp_path: Path) -> None:
    """`duplicate` gives no finding for a pair the `scratch` row already covers (D10.3 R4).

    arch: D10.3
    """
    _git_init(tmp_path)
    content = ("same content, kept by one file and scratch in another\n" * 8).encode()
    assert len(content) >= 256
    (tmp_path / "README.md").write_bytes(content)
    (tmp_path / "README_draft.md").write_bytes(content)
    assert _findings_by_rule(tmp_path, "duplicate") == []


def test_artifact_flags_a_tracked_pycache_file(tmp_path: Path) -> None:
    """A `__pycache__` directory is one auto `error` for the directory (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-311.pyc").write_bytes(b"\x00\x01")
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:__pycache__/"]
    assert findings[0].severity == "error"
    assert findings[0].auto is True


def test_artifact_is_one_finding_per_top_most_directory(tmp_path: Path) -> None:
    """Thirty files under `node_modules/` give one finding for the top-most directory (D5.4).

    A nested cache directory inside it adds no finding of its own.

    arch: D5.4
    """
    _git_init(tmp_path)
    modules = tmp_path / "web" / "node_modules"
    for index in range(30):
        package = modules / f"pkg{index}"
        package.mkdir(parents=True)
        (package / "index.js").write_text(
            f"module.exports = {index};\n", encoding="utf-8"
        )
    (modules / "pkg0" / "__pycache__").mkdir()
    (modules / "pkg0" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:web/node_modules/"]
    assert findings[0].path == "web/node_modules/"


def test_artifact_flags_a_pyc_suffix_anywhere(tmp_path: Path) -> None:
    """A `.pyc` file outside a cache directory is still flagged by its suffix.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "stray.pyc").write_bytes(b"\x00\x01")
    findings = _findings_by_rule(tmp_path, "artifact")
    assert len(findings) == 1


def test_duplicate_flags_the_later_of_two_equal_files(tmp_path: Path) -> None:
    """Two files with the same content over 64 bytes give one `warn` finding, on the later path.

    arch: D5.4
    """
    _git_init(tmp_path)
    content = ("same content, padded to be over the minimum size\n" * 6).encode()
    assert len(content) >= 256
    (tmp_path / "a.bin").write_bytes(content)
    (tmp_path / "b.bin").write_bytes(content)
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert len(findings) == 1
    assert findings[0].path == "b.bin"
    assert findings[0].severity == "warn"
    assert findings[0].auto is False


def test_duplicate_ignores_tiny_files(tmp_path: Path) -> None:
    """Two identical files under 64 bytes are not flagged as duplicates.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hi\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert findings == []


def test_duplicate_skips_a_group_entirely_under_a_fixtures_directory(
    tmp_path: Path,
) -> None:
    """A duplicate group under `fixtures/` gives no finding: it is test data (D6.12).

    arch: D6.12
    """
    _git_init(tmp_path)
    content = ("same content, padded to be over the minimum size\n" * 6).encode()
    assert len(content) >= 256
    (tmp_path / "fixtures" / "a").mkdir(parents=True)
    (tmp_path / "fixtures" / "b").mkdir(parents=True)
    (tmp_path / "fixtures" / "a" / "same.txt").write_bytes(content)
    (tmp_path / "fixtures" / "b" / "same.txt").write_bytes(content)
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert findings == []


def test_duplicate_still_flags_a_group_only_partly_under_testdata(
    tmp_path: Path,
) -> None:
    """A duplicate group flags as usual when only one path is test data (D6.12).

    arch: D6.12
    """
    _git_init(tmp_path)
    content = ("same content, padded to be over the minimum size\n" * 6).encode()
    assert len(content) >= 256
    (tmp_path / "testdata").mkdir()
    (tmp_path / "testdata" / "same.txt").write_bytes(content)
    (tmp_path / "same.txt").write_bytes(content)
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert len(findings) == 1


def test_generated_flags_a_do_not_edit_marker(tmp_path: Path) -> None:
    """A `Code generated ... DO NOT EDIT` header gives an auto `warn` (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "gen.go").write_text(
        "// Code generated by protoc-gen. DO NOT EDIT.\npackage main\n",
        encoding="utf-8",
    )
    findings = _findings_by_rule(tmp_path, "generated")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].auto is True


def test_generated_spares_a_lockfile(tmp_path: Path) -> None:
    """A lockfile is never flagged as generated, even with the marker text.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "Cargo.lock").write_text(
        "# This file is automatically @generated by Cargo.\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "generated")
    assert findings == []


def test_generated_spares_a_file_marked_in_gitattributes(tmp_path: Path) -> None:
    """A file `.gitattributes` marks `linguist-generated=true` is not flagged again.

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "gen.go").write_text(
        "// Code generated by protoc-gen. DO NOT EDIT.\npackage main\n",
        encoding="utf-8",
    )
    (tmp_path / ".gitattributes").write_text(
        "gen.go linguist-generated=true\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "generated")
    assert findings == []


def test_secret_file_flags_a_dotenv_by_name_and_proves_it_by_content(
    tmp_path: Path,
) -> None:
    """A `.env` file is flagged by its name; a matching secret makes it automatic (I-49).

    arch: D5.4, I-49, D15.10
    """
    _git_init(tmp_path)
    secret_value = "AKIA" + "Q" * 16  # built at run time, never a literal secret
    (tmp_path / ".env").write_text(f"API_KEY={secret_value}\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "secret-file")
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].auto is True
    assert secret_value not in findings[0].evidence
    assert secret_value not in findings[0].action


def test_secret_file_spares_the_example_suffix(tmp_path: Path) -> None:
    """`.env.example` is not a secret file (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / ".env.example").write_text("API_KEY=changeme\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "secret-file")
    assert findings == []


def test_secret_content_flags_an_aws_key_by_pattern_only(tmp_path: Path) -> None:
    """An AWS-shaped key inside an ordinary file is flagged, with no matched text in the evidence (I-23).

    arch: D5.4, I-23
    """
    _git_init(tmp_path)
    fake_key = (
        "AKIA" + "Q" * 16
    )  # built at run time, never a literal secret in the tree
    (tmp_path / "notes.txt").write_text(f"key: {fake_key}\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "secret-content")
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].auto is False
    assert fake_key not in findings[0].evidence
    assert fake_key not in findings[0].action
    assert "notes.txt:1" in findings[0].evidence


def test_secret_content_skips_a_secret_file_itself(tmp_path: Path) -> None:
    """A file the `secret-file` row already flags is not also scanned for content (I-23).

    arch: D5.4, I-23
    """
    _git_init(tmp_path)
    fake_key = "AKIA" + "Q" * 16
    (tmp_path / "server.key").write_text(f"KEY={fake_key}\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "secret-content")
    assert findings == []


def test_secret_content_spares_a_private_key_placeholder(tmp_path: Path) -> None:
    """A banner with a placeholder or comment line after it stays silent (D6.10, FP-5).

    Both target-go shapes are here: a paste instruction, and a `#` comment
    line, neither one a base64 body.

    arch: D6.10
    """
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text(
        "-----BEGIN "
        "PRIVATE KEY-----\n"
        "<paste private.pem contents, or omit on write-only nodes>\n"
        "-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    (tmp_path / "config.example.yaml").write_text(
        "    #     #   -----BEGIN "
        "PRIVATE KEY-----\n"
        "    #     #   <paste private key here>\n"
        "    #     #   -----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    findings = _findings_by_rule(tmp_path, "secret-content")
    assert findings == []


def test_secret_content_flags_a_private_key_with_a_base64_body(tmp_path: Path) -> None:
    """A banner followed by a base64 body line fires, with no matched text in evidence (D6.10, I-23).

    The body is built at test time from `os.urandom`, so no key-shaped
    block is committed to the repo.

    arch: D6.10, I-23
    """
    _git_init(tmp_path)
    body = base64.b64encode(os.urandom(48)).decode("ascii")  # built at run time
    (tmp_path / "notes.txt").write_text(
        f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    findings = _findings_by_rule(tmp_path, "secret-content")
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].auto is False
    assert body not in findings[0].evidence
    assert body not in findings[0].action
    assert "notes.txt:1" in findings[0].evidence


def test_binary_flags_an_oversized_file(tmp_path: Path) -> None:
    """A file over 1 MiB is a `warn`, manual finding (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "big.bin").write_bytes(b"\x00" + b"0" * (1024 * 1024))
    findings = _findings_by_rule(tmp_path, "binary")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].auto is False


def test_binary_spares_a_file_marked_lfs(tmp_path: Path) -> None:
    """A `.gitattributes` `filter=lfs` line spares an oversized file (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    (tmp_path / "big.bin").write_bytes(b"0" * (1024 * 1024 + 1))
    (tmp_path / ".gitattributes").write_text("big.bin filter=lfs\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "binary")
    assert findings == []


def test_binary_sniff_closes_the_file_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The NUL-byte sniff closes the file handle it opens (D5.4).

    Before this fix, the sniff called `Path.open("rb").read(...)` with no
    `with` block, leaving the returned handle open once `read` finished.

    arch: D5.4, D13.2
    """
    _git_init(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T3"\n', encoding="utf-8"
    )
    (tmp_path / "mid.bin").write_bytes(b"0" * (150 * 1024))
    opened: list[object] = []
    real_open = Path.open

    def _tracking_open(self: Path, *args: object, **kwargs: object) -> object:
        handle = real_open(self, *args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(Path, "open", _tracking_open)
    findings = _findings_by_rule(tmp_path, "binary")
    assert findings == []
    assert opened
    assert all(handle.closed for handle in opened)


def test_binary_sniff_runs_only_at_t3(tmp_path: Path) -> None:
    """Below T3 a 150 KiB file with a NUL byte gets no finding; at T3 it gets one.

    arch: D13.2
    """
    _git_init(tmp_path)
    (tmp_path / "mid.bin").write_bytes(b"\x00" * (150 * 1024))
    assert _findings_by_rule(tmp_path, "binary") == []
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T3"\n', encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "binary")
    assert [finding.path for finding in findings] == ["mid.bin"]


def test_binary_spares_a_file_that_a_page_links_to(tmp_path: Path) -> None:
    """A file that a Markdown page links to by relative path is evidence, not residue.

    arch: D13.2
    """
    _git_init(tmp_path)
    (tmp_path / "shots").mkdir()
    for name in ("linked.png", "loose.png"):
        (tmp_path / "shots" / name).write_bytes(b"\x00" + b"0" * (1024 * 1024))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "review.md").write_text(
        "# Review\n\n![the ledger](../shots/linked.png)\n", encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "binary")
    assert [finding.path for finding in findings] == ["shots/loose.png"]


def test_binary_allow_glob_spares_a_file(tmp_path: Path) -> None:
    """A `[binary] allow` glob names a file by path or by basename.

    arch: D13.2
    """
    _git_init(tmp_path)
    (tmp_path / "shots").mkdir()
    for name in ("a.png", "b.gif", "c.bin"):
        (tmp_path / "shots" / name).write_bytes(b"\x00" + b"0" * (1024 * 1024))
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[binary]\nallow = ["shots/*.png", "*.gif"]\n', encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "binary")
    assert [finding.path for finding in findings] == ["shots/c.bin"]


def test_root_budget_flags_over_budget_at_t0(tmp_path: Path) -> None:
    """More root entries than the T0 budget (8) gives one repo-wide `warn` (D5.4).

    arch: D5.4
    """
    _git_init(tmp_path)
    for i in range(12):
        (tmp_path / f"file{i}.txt").write_text("x\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "root-budget")
    assert len(findings) == 1
    assert findings[0].id == "root-budget:"
    assert findings[0].path == ""
    assert findings[0].severity == "warn"


def test_no_row_opens_a_secret_files_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No row reads the bytes or text of a secret file, not just `secret-file` and `secret-content` (I-23).

    `duplicate`, `generated`, `scratch` and `binary` each read other files'
    content for their own purpose; every one of them must skip a file
    `secret-file` would flag, rather than opening it.

    arch: D5.4, I-23, D14.12
    """
    _git_init(tmp_path)
    same_content = ("shared content, padded to be over the minimum size\n" * 2).encode()
    (tmp_path / "id_rsa").write_bytes(same_content)  # a secret key file
    (tmp_path / "a.bin").write_bytes(same_content)  # would be its duplicate, if opened
    (tmp_path / "big.pem").write_bytes(
        b"0" * (1024 * 1024 + 1)
    )  # a secret, and oversized
    (tmp_path / "medium.key").write_bytes(
        b"0" * (150 * 1024)
    )  # a secret, over the sniff floor
    (tmp_path / "tmp_scratch_name").write_bytes(
        same_content
    )  # scratch, mentions id_rsa nowhere

    opened: list[str] = []
    head_sizes: list[int] = []
    real_os_read = os.read
    real_os_open = os.open
    fd_names: dict[int, str] = {}

    def _tracking_os_open(path: object, *args: object, **kwargs: object) -> int:
        descriptor = real_os_open(path, *args, **kwargs)
        fd_names[descriptor] = Path(os.fsdecode(path)).name
        opened.append(fd_names[descriptor])
        return descriptor

    def _tracking_os_read(descriptor: int, count: int) -> bytes:
        if fd_names.get(descriptor) in {"big.pem", "id_rsa", "medium.key"}:
            head_sizes.append(count)
        return real_os_read(descriptor, count)

    real_os_close = os.close

    def _tracking_os_close(descriptor: int) -> None:
        fd_names.pop(descriptor, None)
        real_os_close(descriptor)

    monkeypatch.setattr(os, "close", _tracking_os_close)
    monkeypatch.setattr(os, "open", _tracking_os_open)
    monkeypatch.setattr(os, "read", _tracking_os_read)
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text
    real_open = Path.open

    def _tracking_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        opened.append(self.name)
        return real_read_bytes(self, *args, **kwargs)

    def _tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        opened.append(self.name)
        return real_read_text(self, *args, **kwargs)

    def _tracking_open(self: Path, *args: object, **kwargs: object) -> object:
        opened.append(self.name)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", _tracking_read_bytes)
    monkeypatch.setattr(Path, "read_text", _tracking_read_text)
    monkeypatch.setattr(Path, "open", _tracking_open)
    survey = survey_mod.run(tmp_path)
    findings = hygiene.hygiene_findings(survey)

    # I-49: the `secret-file` row reads at most 64 bytes of a key-named file,
    # once; the oversized one gets no `binary` or `large-text` row.
    assert opened.count("big.pem") == 1
    assert head_sizes and max(head_sizes) <= 64
    assert opened.count("id_rsa") == 1
    assert opened.count("medium.key") == 1
    assert _findings_by_rule(tmp_path, "binary") == []
    assert _findings_by_rule(tmp_path, "large-text") == []
    secret_paths = {
        finding.path for finding in findings if finding.rule == "secret-file"
    }
    assert secret_paths == {"big.pem", "id_rsa", "medium.key"}


def test_artifact_flags_dist_beside_a_go_manifest(tmp_path: Path) -> None:
    """`dist/` counts as build output beside `go.mod`, not only beside a Python or Node manifest.

    arch: D10.4
    """
    _git_init(tmp_path)
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "x.bin").write_bytes(b"\x00\x01")
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:dist/"]


def test_artifact_directory_holding_a_tracked_page_is_manual(tmp_path: Path) -> None:
    """An artifact directory that holds a tracked `*.md` file is a manual finding (D10.4 R5).

    arch: D10.4
    """
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "out.js").write_text("console.log(1);\n", encoding="utf-8")
    (build / "NOTES.md").write_text("# notes\n", encoding="utf-8")
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:build/"]
    assert findings[0].auto is False
    assert "holds build/NOTES.md" in findings[0].evidence


def test_root_budget_widened_by_root_allow(tmp_path: Path) -> None:
    """`[root] allow` raises the budget by the number of entries it lists.

    arch: D5.4
    """
    _git_init(tmp_path)
    for i in range(12):
        (tmp_path / f"file{i}.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[root]\nallow = ["a", "b", "c", "d", "e"]\n', encoding="utf-8"
    )
    findings = _findings_by_rule(tmp_path, "root-budget")
    assert findings == []


def test_root_budget_counts_no_entry_that_trueup_writes(tmp_path: Path) -> None:
    """A repo at its T0 budget stays inside it after trueup writes its files (D5.4, I-43).

    The files are the four of `survey.TRUEUP_OWN_PATHS`. An old managed
    file such as `.editorconfig` is the person's file after decision
    D15.37, so it counts and takes the repo past its budget.

    arch: D5.4, D12.9, I-43, D15.37
    """
    _git_init(tmp_path)
    for i in range(hygiene.ROOT_BUDGET["T0"]):
        (tmp_path / f"file{i}.txt").write_text("x\n", encoding="utf-8")
    for path in (
        "trueup.toml",
        "ref_check.toml",
        ".trueup-baseline.json",
        "ref_check.py",
    ):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("version = 1\n", encoding="utf-8")
    assert survey_mod.run(tmp_path).tier == "T0"
    assert _findings_by_rule(tmp_path, "root-budget") == []
    (tmp_path / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    assert len(_findings_by_rule(tmp_path, "root-budget")) == 1


def test_artifact_node_modules_readme_does_not_make_the_directory_manual(
    tmp_path: Path,
) -> None:
    """A `node_modules/` package `README.md` does not count as a held page (D10.4).

    `README.md` is not a `doc-misplaced` candidate: `node_modules` is an
    exempt segment and `README.md` is an exempt basename
    (`layout._is_candidate`, D10.2). So it is not a page the directory
    holds, and the directory stays an automatic finding.

    arch: D10.4
    """
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    modules = tmp_path / "node_modules" / "pkg"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (modules / "README.md").write_text("# pkg\n", encoding="utf-8")
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:node_modules/"]
    assert findings[0].auto is True


def test_scratch_gives_no_finding_for_a_path_the_artifact_row_flags(
    tmp_path: Path,
) -> None:
    """A path the `artifact` row flags gets no `scratch` finding; `artifact` wins (D10.3, D10.2).

    `tmp/out.pyc` looks like scratch (its directory is `tmp/`) and is also
    build output by suffix, so the `artifact` row flags it. Only the
    `artifact` remedy survives; the `scratch` row gives no finding for the
    same path.

    arch: D10.3
    """
    _git_init(tmp_path)
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / "out.pyc").write_bytes(b"\x00\x01")
    _commit_all(tmp_path)
    survey = survey_mod.run(tmp_path)
    findings = hygiene.hygiene_findings(survey)
    ids = [finding.id for finding in findings]
    assert "artifact:tmp/out.pyc" in ids
    assert "scratch:tmp/out.pyc" not in ids


def test_tracked_paths_splits_on_nul_for_a_non_ascii_path(tmp_path: Path) -> None:
    """`_tracked_paths` reads `git ls-files -z` output, so a non-ASCII path survives whole (D10.7).

    Without `-z`, git quotes a non-ASCII byte in octal and wraps the name
    in double quotes, so the returned path would not match the survey's
    path. With `-z`, the raw bytes come back unquoted, NUL-separated.

    arch: D10.7
    """
    _git_init(tmp_path)
    name = "café.txt"
    (tmp_path / name).write_text("x\n", encoding="utf-8")
    _commit_all(tmp_path)
    tracked = hygiene._tracked_paths(tmp_path)
    assert name in tracked


def test_artifact_directory_holding_a_markdown_suffix_page_is_manual(
    tmp_path: Path,
) -> None:
    """A tracked `*.markdown` page makes an artifact directory manual, as `*.md` does.

    arch: D12.11
    """
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "out.js").write_text("console.log(1);\n", encoding="utf-8")
    (build / "guide.markdown").write_text("# guide\n", encoding="utf-8")
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:build/"]
    assert findings[0].auto is False
    assert "holds build/guide.markdown" in findings[0].evidence


def test_artifact_ignores_a_scratch_looking_page_in_the_directory(
    tmp_path: Path,
) -> None:
    """A scratch-looking page does not make an artifact directory manual.

    arch: D12.11
    """
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "out.js").write_text("console.log(1);\n", encoding="utf-8")
    (build / "scratch_1.md").write_text("# scratch\n", encoding="utf-8")
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:build/"]
    assert findings[0].auto is True


def _scope_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the XDG directories at `tmp_path` and give a new target root.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        tmp_path: The test's temporary directory.

    Returns:
        An empty git repository under `tmp_path`.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    root = tmp_path / "target"
    root.mkdir()
    _git_init(root)
    return root


def test_scratch_reference_index_never_matches_across_two_files(
    tmp_path: Path,
) -> None:
    """A mention split over the end of one file and the start of the next does not count.

    The reference index joins the texts of one directory. Its separator
    must stop a match that starts in one file and ends in another.

    arch: D14.14, D14.21, D14.15
    """
    _git_init(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "tmp_notes.txt").write_text("draft\n", encoding="utf-8")
    (tmp_path / "sub" / "a.md").write_text("see tmp_no", encoding="utf-8")
    (tmp_path / "sub" / "b.md").write_text("tes.txt here\n", encoding="utf-8")
    findings = _findings_by_rule(tmp_path, "scratch")
    assert [finding.id for finding in findings] == ["scratch:sub/tmp_notes.txt"]


def test_scoped_hygiene_equals_the_full_run_for_each_changed_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A scoped run gives the full run's `scratch`, `artifact` and `duplicate` findings for its paths.

    The fixture holds the cases where a finding for a changed path depends
    on a file outside the changed set: a scratch copy that sorts before
    its kept twin, a scratch copy of a kept page, a reference from another
    scratch file, and a reference from a scratch-looking file under a
    build directory.

    arch: D14.14, D14.21, D14.15
    """
    root = _scope_env(monkeypatch, tmp_path)
    twin = ("a twin text, padded past the duplicate minimum size\n" * 2).encode()
    page = ("a kept page with a scratch copy beside it, padded\n" * 2).encode()
    (root / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "README.md").write_text("the project\n", encoding="utf-8")
    (root / "scratch_1.txt").write_bytes(twin)
    (root / "z").mkdir()
    (root / "z" / "keep.txt").write_bytes(twin)
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_bytes(page)
    (root / "tmp_a.txt").write_bytes(page)
    (root / "tmp_x.txt").write_text("see tmp_y.txt\n", encoding="utf-8")
    (root / "tmp_y.txt").write_text("draft\n", encoding="utf-8")
    (root / "tmp_z.txt").write_text("draft z\n", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "out.js").write_text("console.log(1);\n", encoding="utf-8")
    (root / "build" / "notes_1.txt").write_text("see ../tmp_z.txt\n", encoding="utf-8")
    _commit_all(root)
    survey = survey_mod.run(root)
    rules = {"scratch", "artifact", "duplicate"}
    full = [
        finding
        for finding in hygiene.hygiene_findings(survey, ())
        if finding.rule in rules
    ]
    full_ids = {finding.id for finding in full}
    assert "scratch:scratch_1.txt" in full_ids
    assert "duplicate:z/keep.txt" not in full_ids
    assert "scratch:tmp_y.txt" in full_ids
    assert "scratch:tmp_z.txt" not in full_ids
    scopes = [frozenset({path}) for path in survey.files]
    scopes.append(frozenset(survey.files))
    scopes.append(frozenset({"z/keep.txt", "tmp_a.txt"}))
    for only in scopes:
        scoped = hygiene.hygiene_findings(survey, (), only=only)
        expected = sorted(
            (finding for finding in full if finding.path in only), key=repr
        )
        got = sorted(
            (
                finding
                for finding in scoped
                if finding.rule in rules and finding.path in only
            ),
            key=repr,
        )
        assert got == expected, sorted(only)


def test_scoped_hygiene_builds_no_scratch_index_when_nothing_changed_looks_like_scratch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A Stop hook run on a small changed file reads no reference text and hashes nothing.

    A scratch file outside the changed set gets no index, and a changed
    set with no file of 64 bytes or more skips the `duplicate` hash pass.

    arch: D14.14, D14.21, D14.15
    """
    root = _scope_env(monkeypatch, tmp_path)
    (root / "README.md").write_text("the project\n", encoding="utf-8")
    (root / "tmp_a.txt").write_text("draft\n", encoding="utf-8")
    _commit_all(root)
    survey = survey_mod.run(root)
    assert [
        finding.id
        for finding in hygiene.hygiene_findings(survey, ())
        if finding.rule == "scratch"
    ] == ["scratch:tmp_a.txt"]

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a scoped run on README.md must not call this")

    monkeypatch.setattr(hygiene, "_reference_index", _refuse)
    monkeypatch.setattr(hygiene, "_content_groups", _refuse)
    scoped = hygiene.hygiene_findings(survey, (), only=frozenset({"README.md"}))
    assert [finding for finding in scoped if finding.path == "README.md"] == []


def test_report_collect_passes_only_to_hygiene(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`report.collect` gives its changed set to `hygiene_findings`, so the Stop hook builds no scratch index.

    arch: D14.14, D14.21, D14.15
    """
    from trueup import report

    root = _scope_env(monkeypatch, tmp_path)
    (root / "README.md").write_text("the project\n", encoding="utf-8")
    (root / "tmp_a.txt").write_text("draft\n", encoding="utf-8")
    _commit_all(root)
    seen: list[frozenset[str] | None] = []
    original = hygiene.hygiene_findings

    def _spy(*args: object, **kwargs: object) -> list:
        seen.append(kwargs.get("only"))  # type: ignore[arg-type]  # reason: the spy records what collect passed
        return original(*args, **kwargs)  # type: ignore[arg-type]  # reason: the spy forwards the same arguments

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a scoped collect on README.md must not build the index")

    monkeypatch.setattr(hygiene, "hygiene_findings", _spy)
    monkeypatch.setattr(hygiene, "_reference_index", _refuse)
    only = frozenset({"README.md"})
    run = report.collect(root, only=only)
    assert seen == [only]
    assert [finding for finding in run.findings if finding.rule == "scratch"] == []


def test_build_beside_build_gradle_is_build_output(tmp_path: Path) -> None:
    """A root build.gradle makes build/ count as build output.

    arch: D14.13, D14.22
    """
    _git_init(tmp_path)
    (tmp_path / "build.gradle").write_text("// g\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "out.bin").write_text("x\n", encoding="utf-8")
    _commit_all(tmp_path)
    findings = _findings_by_rule(tmp_path, "artifact")
    assert [finding.id for finding in findings] == ["artifact:build/"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/how-to/guide_v2.md", False),
        ("docs/guide-v10.md", False),
        ("docs/how-to/guide_draft.md", True),
        ("docs/guide_copy.md", True),
        ("docs/notes_v2.md", True),
        ("notes/guide_v2.md", True),
        ("guide_v2.md", True),
    ],
)
def test_looks_scratch_path_keeps_versioned_pages_under_docs(
    path: str, expected: bool
) -> None:
    """A `v<n>` suffix under the docs directory is not scratch; other markers are.

    arch: D14.12
    """
    assert hygiene.looks_scratch_path(path, "docs") is expected


def test_looks_scratch_path_uses_the_given_docs_dir() -> None:
    """The docs directory name comes from the caller.

    arch: D14.12
    """
    assert hygiene.looks_scratch_path("manual/guide_v2.md", "manual") is False
    assert hygiene.looks_scratch_path("docs/guide_v2.md", "manual") is True


def test_scratch_looking_passes_the_config_docs_dir(tmp_path: Path) -> None:
    """`scratch_looking` reads `layout_docs_dir` from the config.

    arch: D14.12
    """
    cfg = dataclasses.replace(config.Config(), layout_docs_dir="manual")
    assert hygiene.scratch_looking("manual/guide_v2.md", cfg) is False
    assert hygiene.scratch_looking("docs/guide_v2.md", cfg) is True


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"-----BEGIN CERTIFICATE-----\nMIIB\n", None),
        (b"-----BEGIN PUBLIC KEY-----\nMIIB\n", None),
        (b"-----BEGIN X509 CRL-----\n", None),
        (b"-----BEGIN CERTIFICATE REQUEST-----\n", None),
        (b"-----BEGIN " + b"PRIVATE KEY-----\nMIIB\n", "auto"),
        (b"", "manual"),
        (b"garbage\n-----BEGIN CERTIFICATE-----\n", "manual"),
    ],
)
def test_secret_file_kind_reads_the_pem_first_line(
    tmp_path: Path, content: bytes, expected: str | None
) -> None:
    """A public `.pem` banner gives no row; a private banner is automatic; the rest is manual.

    arch: D14.12, D15.10
    """
    (tmp_path / "cert.pem").write_bytes(content)
    assert hygiene._secret_file_kind(tmp_path, "cert.pem", frozenset()) == expected


def test_secret_file_kind_is_manual_on_a_read_error(tmp_path: Path) -> None:
    """A key-named path that cannot be read gives a manual row.

    arch: D14.12, D15.10
    """
    assert hygiene._secret_file_kind(tmp_path, "missing.pem", frozenset()) == "manual"
    (tmp_path / "dir.pem").mkdir()
    assert hygiene._secret_file_kind(tmp_path, "dir.pem", frozenset()) == "manual"
    assert hygiene._secret_file_kind(tmp_path, "absent.key", frozenset()) == "manual"


def test_secret_file_skips_a_public_pem_and_holds_no_bytes(tmp_path: Path) -> None:
    """The row flags a private `.pem` only, and its evidence holds no file bytes.

    arch: D14.12
    """
    (tmp_path / "public.pem").write_bytes(b"-----BEGIN CERTIFICATE-----\nAAAA\n")
    (tmp_path / "private.pem").write_bytes(
        b"-----BEGIN RSA PRIVATE KEY-----\nSECRETBODY\n"
    )
    findings = hygiene._secret_file(
        types.SimpleNamespace(root=tmp_path, files=["public.pem", "private.pem"])
    )
    assert [f.path for f in findings] == ["private.pem"]
    text = f"{findings[0].evidence} {findings[0].action} {findings[0].id}"
    assert "BEGIN" not in text and "SECRETBODY" not in text


def _content_id(root: Path, path: str, line_number: int) -> str:
    """Give the `secret-content` id of one line: path and line fingerprint (D15.8).

    Args:
        root: The repository root.
        path: The repo-relative path.
        line_number: The 1-based line.

    Returns:
        `secret-content:<path>:<fp>`.
    """
    from trueup.findings import line_fingerprint

    line = (root / path).read_bytes().splitlines()[line_number - 1]
    return f"secret-content:{path}:{line_fingerprint(path, line)}"


def test_secret_content_id_holds_no_line_number_and_survives_a_line_shift(
    tmp_path: Path,
) -> None:
    """Two secrets on one line give one finding; a line above does not change its id.

    The id is `secret-content:<path>:<fp>`, the fingerprint of the path
    and the stripped line. `line` holds the line number, and the evidence
    names each pattern.

    arch: D15.3, D15.8
    """
    _git_init(tmp_path)
    aws = "AKIA" + "Q" * 16
    slack = "xox" + "b-" + "1234567890abc"
    (tmp_path / "m3.py").write_text(f"x = 1\nK = '{aws} {slack}'\n", encoding="utf-8")
    (first,) = _findings_by_rule(tmp_path, "secret-content")
    assert first.id == _content_id(tmp_path, "m3.py", 2)
    assert first.line == 2
    assert first.evidence == "m3.py:2 matches an AWS access key id, a Slack token"
    assert aws not in first.evidence and slack not in first.evidence

    (tmp_path / "m3.py").write_text(
        f"# head\nx = 1\nK = '{aws} {slack}'\n", encoding="utf-8"
    )
    (moved,) = _findings_by_rule(tmp_path, "secret-content")
    assert moved.id == first.id
    assert moved.line == 3


def test_secret_content_numbers_equal_lines_in_file_order(tmp_path: Path) -> None:
    """Two equal secret lines in one file get the ids `<fp>` and `<fp>:2`.

    arch: D15.3, D15.8
    """
    _git_init(tmp_path)
    aws = "AKIA" + "Q" * 16
    (tmp_path / "notes.txt").write_text(f"{aws}\nok\n  {aws}\n", encoding="utf-8")
    found = _findings_by_rule(tmp_path, "secret-content")
    base = _content_id(tmp_path, "notes.txt", 1)
    assert [(finding.id, finding.line) for finding in found] == [
        (base, 1),
        (f"{base}:2", 3),
    ]


_D15_ARCH = "arch: D15.9, D15.10, D15.11, D15.12, D15.22"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("notes.md", True),
        ("docs/notes.md", True),
        ("tmp2.txt", True),
        ("draft.md", True),
        ("draft3.md", True),
        ("untitled.txt", True),
        ("a.bak", True),
        ("lib/x.c.orig", True),
        ("patch.rej", True),
        ("file.txt~", True),
        ("notes-2024.md", False),
        ("temp-sensors.md", False),
        ("scratch_buffer.rs", False),
        ("CHANGELOG-v2.md", False),
        ("README.old.md", False),
        ("report copy.md", False),
        ("a.swp", False),
        ("notes.py", False),
    ],
)
def test_scratch_proven_needs_a_whole_stem_name(path: str, expected: bool) -> None:
    """Only a whole-stem scratch word or a backup suffix proves scratch by name.

    arch: D15.9, I-53
    """
    assert hygiene.scratch_proven(path) is expected


def test_scratch_row_is_automatic_only_for_a_proven_tracked_name(
    tmp_path: Path,
) -> None:
    """A tracked whole-stem name is automatic; compound names and vendor copies are manual.

    arch: D15.9, I-53
    """
    _git_init(tmp_path)
    names = {
        "notes.md": True,
        "notes-2024.md": False,
        "temp-sensors.md": False,
        "vendor/zlib/inflate.c.orig": False,
        "third_party/x/patch.rej": False,
        "tmp/.keep": None,
        "packages/a/docs/install-v2.md": None,
    }
    for index, name in enumerate(names):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"distinct content {index}\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("tmp/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A", "-f"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@e.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "t",
        ],
        cwd=tmp_path,
        check=True,
    )
    found = {f.path: f for f in _findings_by_rule(tmp_path, "scratch")}
    for name, auto in names.items():
        if auto is None:
            assert name not in found, name
        else:
            assert found[name].auto is auto, name
    assert "if it is scratch" in found["notes-2024.md"].action


def test_looks_scratch_path_keeps_a_versioned_page_under_a_nested_docs_dir() -> None:
    """A `-v<n>` page under a docs directory at any depth is not scratch.

    arch: D15.9
    """
    assert hygiene.looks_scratch_path("packages/a/docs/install-v2.md", "docs") is False
    assert hygiene.under_docs_dir("packages/a/docs/x.md", "docs") is True
    assert hygiene.under_docs_dir("docs", "docs") is False
    assert hygiene.looks_scratch_path("packages/a/docs/x_draft.md", "docs") is True


def test_scratch_never_flags_keep_files(tmp_path: Path) -> None:
    """`.keep` and `.gitkeep` are never scratch, even under a scratch directory.

    arch: D15.9
    """
    assert hygiene.looks_scratch_path("tmp/.keep") is False
    assert hygiene.looks_scratch_path("temp/sub/.gitkeep") is False


def _key_bytes(label: bytes = b"PRIVATE KEY") -> bytes:
    """Give PEM-shaped key bytes built at run time.

    Args:
        label: The text between `BEGIN ` and `-----`.

    Returns:
        A banner line and a body line.
    """
    return b"-----BEGIN " + label + b"-----\n" + b"A" * 60 + b"\n"


def test_secret_file_kind_reads_the_head_of_a_key_name(tmp_path: Path) -> None:
    """A private PEM banner or a PKCS#12 head is automatic; other key-named files are manual.

    arch: D15.10
    """
    pkcs12 = bytes([0x30, 0x82, 0x06, 0x97, 2, 1, 3, 0x30, 0x82, 6, 0x45]) + bytes(
        [0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x07, 0x01]
    )
    cases = {
        "server.pem": (_key_bytes(), "auto"),
        "rsa.key": (_key_bytes(b"RSA PRIVATE KEY"), "auto"),
        "cert.p12": (pkcs12, "auto"),
        "talk.key": (b"PK\x03\x04keynote", "manual"),
        "label.pem": (
            b"# a long label line before the banner\n-----BEGIN CERTIFICATE-----\n",
            "manual",
        ),
        "public.pem": (b"-----BEGIN CERTIFICATE-----\nAAAA\n", None),
        "empty.pem": (b"", "manual"),
        "der.key": (
            bytes(
                [
                    0x30,
                    0x82,
                    2,
                    0x77,
                    2,
                    1,
                    0,
                    0x30,
                    0x0D,
                    6,
                    9,
                    0x2A,
                    0x86,
                    0x48,
                    0x86,
                    0xF7,
                ]
            ),
            "manual",
        ),
    }
    for name, (content, _kind) in cases.items():
        (tmp_path / name).write_bytes(content)
    for name, (_content, kind) in cases.items():
        assert hygiene._secret_file_kind(tmp_path, name, frozenset()) == kind, name


def test_secret_file_kind_for_dotenv_follows_secret_paths(tmp_path: Path) -> None:
    """A `.env` is automatic only when this run's secret-content paths hold it.

    arch: D15.10
    """
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    assert hygiene._secret_file_kind(tmp_path, ".env", frozenset()) == "manual"
    assert hygiene._secret_file_kind(tmp_path, ".env", frozenset({".env"})) == "auto"
    assert hygiene._secret_file_kind(tmp_path, "README.md", frozenset()) is None


def test_secret_file_row_dotenv_auto_only_with_a_matching_secret(
    tmp_path: Path,
) -> None:
    """A `.env` with a token-shaped value is automatic; a placeholder `.env` is manual.

    The built-in scan now reads `.env` files, so the row sees the match.

    arch: D15.10, I-53
    """
    _git_init(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    token = "AKIA" + "Q" * 16
    (tmp_path / "a" / ".env").write_text(f"KEY={token}\n", encoding="utf-8")
    (tmp_path / "b" / ".env").write_text("PLACEHOLDER_ONLY=1\n", encoding="utf-8")
    found = {f.path: f for f in _findings_by_rule(tmp_path, "secret-file")}
    assert found["a/.env"].auto is True
    assert "rotate" in found["a/.env"].action
    assert found["b/.env"].auto is False
    assert "rotate" not in found["b/.env"].action
    assert "[[keep]]" in found["b/.env"].action
    content = _findings_by_rule(tmp_path, "secret-content")
    assert [f.path for f in content] == ["a/.env"]
    assert token not in content[0].evidence


def test_secret_file_manual_key_action_says_check_first(tmp_path: Path) -> None:
    """A manual key row asks the owner to check; the word rotate is for the automatic row.

    arch: D15.10
    """
    _git_init(tmp_path)
    (tmp_path / "talk.key").write_bytes(b"PK\x03\x04keynote")
    (tmp_path / "id_rsa").write_bytes(_key_bytes())
    found = {f.path: f for f in _findings_by_rule(tmp_path, "secret-file")}
    assert found["talk.key"].auto is False
    assert found["talk.key"].action.startswith(
        "check whether the file holds a private key"
    )
    assert found["id_rsa"].auto is True
    assert "rotate" in found["id_rsa"].action


def test_binary_over_a_mebibyte_is_decided_by_a_nul_byte(tmp_path: Path) -> None:
    """A big file with a NUL byte is `binary`; a big text file is `large-text` (info, manual).

    arch: D15.11, I-53
    """
    _git_init(tmp_path)
    size = 1024 * 1024 + 1
    (tmp_path / "blob.bin").write_bytes(b"\x00" + b"0" * size)
    (tmp_path / "main.pot").write_bytes(b"msgid x\n" * (size // 8 + 1))
    (tmp_path / "big.pem").write_bytes(b"0" * size)
    binary = _findings_by_rule(tmp_path, "binary")
    large = _findings_by_rule(tmp_path, "large-text")
    assert [f.path for f in binary] == ["blob.bin"]
    assert [f.path for f in large] == ["main.pot"]
    assert large[0].severity == "info"
    assert large[0].category == "files"
    assert large[0].auto is False
    assert large[0].evidence == f"main.pot is {(size // 8 + 1) * 8} bytes of text"
    assert large[0].action == "none needed; add a [binary] allow glob to silence it"


def test_large_text_is_spared_by_an_allow_glob_and_a_page_link(tmp_path: Path) -> None:
    """A `[binary] allow` glob and a linked page spare `large-text` too.

    arch: D15.11
    """
    _git_init(tmp_path)
    text = b"line\n" * (1024 * 1024 // 5 + 2)
    for name in ("a.pot", "b.pot", "c.pot"):
        (tmp_path / name).write_bytes(text)
    (tmp_path / "README.md").write_text("[b](b.pot)\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[binary]\nallow = ["a.pot"]\n', encoding="utf-8"
    )
    assert [f.path for f in _findings_by_rule(tmp_path, "large-text")] == ["c.pot"]


def test_duplicate_floor_is_256_bytes(tmp_path: Path) -> None:
    """Equal files under 256 bytes give no duplicate row; 256 bytes or more do.

    arch: D15.12
    """
    _git_init(tmp_path)
    (tmp_path / "s1.txt").write_bytes(b"a" * 255)
    (tmp_path / "s2.txt").write_bytes(b"a" * 255)
    (tmp_path / "l1.txt").write_bytes(b"b" * 256)
    (tmp_path / "l2.txt").write_bytes(b"b" * 256)
    assert [f.path for f in _findings_by_rule(tmp_path, "duplicate")] == ["l2.txt"]


def test_duplicate_group_whose_members_are_all_referenced_is_dropped(
    tmp_path: Path,
) -> None:
    """A group is dropped when every remaining member is named by tracked text.

    arch: D15.12
    """
    _git_init(tmp_path)
    for name in ("x1.txt", "x2.txt", "y1.txt", "y2.txt", "y3.txt"):
        content = b"x" * 300 if name.startswith("x") else b"y" * 300
        (tmp_path / name).write_bytes(content)
    (tmp_path / "README.md").write_text(
        "see x1.txt and x2.txt and y1.txt and y2.txt\n", encoding="utf-8"
    )
    paths = [f.path for f in _findings_by_rule(tmp_path, "duplicate")]
    assert paths == ["y2.txt", "y3.txt"]


def test_duplicate_labels_paths_that_differ_in_one_directory_segment(
    tmp_path: Path,
) -> None:
    """Same basename, same depth, one differing directory: the text says so.

    arch: D16.6
    """
    _git_init(tmp_path)
    content = ("variant content, padded to be over the minimum size\n" * 6).encode()
    for rel in ("one/x/page.bin", "one/y/page.bin"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(content)
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert len(findings) == 1
    assert "the paths differ in one directory segment" in findings[0].evidence
    assert "[[keep]]" in findings[0].action
    assert findings[0].auto is False


def test_duplicate_keeps_the_plain_text_for_other_paths(tmp_path: Path) -> None:
    """Paths that differ in two segments keep the plain evidence text.

    arch: D16.6
    """
    _git_init(tmp_path)
    content = ("variant content, padded to be over the minimum size\n" * 6).encode()
    for rel in ("a/x/page.bin", "b/y/page.bin"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(content)
    findings = _findings_by_rule(tmp_path, "duplicate")
    assert len(findings) == 1
    assert findings[0].evidence == "same content as a/x/page.bin"
    assert findings[0].action.startswith("keep one of")
