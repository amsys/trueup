"""Tests for `trueup.layout`: the `doc-misplaced` row and the move locator (arch: D10.2, D10.6)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from trueup import layout, survey as survey_mod
from trueup.config import Config
from trueup.findings import Finding


def _git(root: Path, *args: str) -> None:
    """Run one git command in a test repository, with a fixed signer.

    Args:
        root: The repository.
        *args: The git arguments after `git`.
    """
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _init(root: Path) -> None:
    """Turn `root` into a git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    _git(root, "init", "-q")


def _write(root: Path, rel: str, content: str = "content\n") -> None:
    """Write one text file, creating its parent directories.

    Args:
        root: The repository root.
        rel: The repo-relative POSIX path to write.
        content: The text to write.
    """
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _move(root: Path, source: str, target: str) -> None:
    """Run `git mv`, first making the target's parent directory.

    Args:
        root: The repository root.
        source: The repo-relative source path.
        target: The repo-relative target path. This git version refuses
            a move whose target directory does not exist yet.
    """
    (root / target).parent.mkdir(parents=True, exist_ok=True)
    _git(root, "mv", source, target)


def _commit(root: Path, message: str) -> None:
    """Stage every change and commit it.

    Args:
        root: The repository root.
        message: The commit message.
    """
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _survey(root: Path) -> survey_mod.Survey:
    """Survey a test repository.

    Args:
        root: The repository root.

    Returns:
        The survey.
    """
    return survey_mod.run(root)


def _broken_link(path: str, line: int, target: str) -> Finding:
    """Build one `refcheck` finding that carries a `broken-link` failure line.

    Args:
        path: The repo-relative path of the file holding the link.
        line: The line of the link.
        target: The link's written destination, as `ref_check.py` would
            print it (may hold a fragment).

    Returns:
        A `refcheck` finding whose evidence is the one failure line
        `docrules._refcheck_findings` would have given it.
    """
    evidence = f"{path}:{line}: [broken-link] link does not resolve: {target}"
    return Finding(
        id=f"refcheck:{path}:{line}:broken-link:{target}",
        rule="refcheck",
        category="docs",
        severity="error",
        path=path,
        evidence=evidence,
        action="fix the reference ref_check.py names, then re-run it",
        auto=False,
    )


def _scratch_finding(path: str) -> Finding:
    """Build one `scratch` finding for a path, the shape `hygiene._scratch` gives.

    Args:
        path: The repo-relative path the scratch row flagged.

    Returns:
        A minimal `scratch` finding naming `path`.
    """
    return Finding(
        id=f"scratch:{path}",
        rule="scratch",
        category="files",
        severity="error",
        path=path,
        evidence="looks like a scratch file",
        action=f"git rm {path}",
        auto=True,
    )


# ---------------------------------------------------------------------------
# The candidate filter (D10.2)
# ---------------------------------------------------------------------------


def test_candidate_filter_accepts_a_plain_misplaced_page() -> None:
    """A Markdown page outside `docs/` with no exemption is a candidate (arch: D10.2)."""
    assert layout._is_candidate("misc/page.md", frozenset()) is True
    assert layout._is_candidate("misc/page.markdown", frozenset()) is True


def test_candidate_filter_rejects_a_non_markdown_file() -> None:
    """A file whose name does not end in `.md` or `.markdown` is never a candidate (arch: D10.2)."""
    assert layout._is_candidate("misc/notes.txt", frozenset()) is False


def test_candidate_filter_rejects_any_docs_segment() -> None:
    """A `docs/` segment at any depth takes a page out of the candidate set (arch: D10.2)."""
    assert layout._is_candidate("docs/page.md", frozenset()) is False
    assert layout._is_candidate("crates/core/docs/page.md", frozenset()) is False


def test_candidate_filter_rejects_a_standard_root_page_case_insensitively() -> None:
    """A standard root page is exempt at depth 0, matched exactly and without case (arch: D10.2)."""
    assert layout._is_candidate("LICENSE.md", frozenset()) is False
    assert layout._is_candidate("license.md", frozenset()) is False
    assert layout._is_candidate("AGENTS.md", frozenset()) is False
    # README.old.md is not an exact match, so the root-page exemption does not reach it;
    # it stays a candidate unless the scratch row has already flagged it.
    assert layout._is_candidate("README.old.md", frozenset()) is True


def test_candidate_filter_rejects_a_standard_root_page_only_at_depth_zero() -> None:
    """The standard root page exemption does not reach a nested path (arch: D10.2)."""
    assert layout._is_candidate("crates/core/LICENSE.md", frozenset()) is True


def test_candidate_filter_rejects_a_github_community_health_file_at_the_root() -> None:
    """A community health page that GitHub reads at the root is not a candidate (arch: D10.2).

    GitHub reads `SUPPORT.md`, `ACCESSIBILITY.md` and a pull request
    template at the root (docs/reference/trueup.md, the GitHub table).
    `GOVERNANCE.md` is not a file that GitHub reads, so it stays a
    candidate, and so does a health name below the root.
    """
    for path in (
        "SUPPORT.md",
        "support.md",
        "ACCESSIBILITY.md",
        "pull_request_template.md",
        "PULL_REQUEST_TEMPLATE.md",
        "PULL_REQUEST_TEMPLATE/feature.md",
    ):
        assert layout._is_candidate(path, frozenset()) is False, path
    assert layout._is_candidate("GOVERNANCE.md", frozenset()) is True
    assert layout._is_candidate("pkg/SUPPORT.md", frozenset()) is True
    assert layout._is_candidate("misc/PULL_REQUEST_TEMPLATE/x.md", frozenset()) is True


def test_locate_gives_a_root_support_page_no_finding_and_no_move(
    tmp_path: Path,
) -> None:
    """A root `SUPPORT.md` gets no `doc-misplaced` finding and no `move:` id (arch: D10.2, D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "README.md")
    _write(root, "SUPPORT.md", "# Support\n")
    result = layout.locate(root, _survey(root), None, [])
    assert result.findings == []
    assert result.moves == []


def test_candidate_filter_rejects_readme_changelog_and_skill_anywhere() -> None:
    """`README.md`, `CHANGELOG.md` and `SKILL.md` are exempt at any depth, exact case (arch: D10.2)."""
    assert layout._is_candidate("crates/core/README.md", frozenset()) is False
    assert layout._is_candidate("crates/core/CHANGELOG.md", frozenset()) is False
    assert layout._is_candidate("skills/trueup/SKILL.md", frozenset()) is False
    assert layout._is_candidate("crates/core/readme.md", frozenset()) is True


def test_candidate_filter_rejects_hidden_and_fixture_segments() -> None:
    """A dot-directory or a fixture-set segment takes a page out (arch: D10.2)."""
    assert layout._is_candidate(".github/page.md", frozenset()) is False
    assert layout._is_candidate("tests/fixtures/page.md", frozenset()) is False
    assert layout._is_candidate("vendor/lib/page.md", frozenset()) is False


def test_candidate_filter_rejects_a_scratch_flagged_path() -> None:
    """The `scratch` row's flagged paths are not candidates, giving one remedy each (arch: D10.2)."""
    assert (
        layout._is_candidate("misc/draft_v2.md", frozenset({"misc/draft_v2.md"}))
        is False
    )


# ---------------------------------------------------------------------------
# locate(): history, link and standard evidence (D10.6)
# ---------------------------------------------------------------------------


def test_locate_with_no_candidate_runs_no_history_scan(tmp_path: Path) -> None:
    """With no candidate, `locate` gives an empty result and never shells out to git (arch: D10.2, D10.6)."""
    root = tmp_path
    _git(root, "init", "-q")  # a survey needs a git work tree (D15.2)
    _write(root, "README.md")
    _git(root, "add", "README.md")
    survey = _survey(root)
    result = layout.locate(root, survey, None, [])
    assert result == layout.LayoutResult(findings=[], moves=[], evidence_notes={})


def test_locate_history_evidence_resolves_a_renamed_page(tmp_path: Path) -> None:
    """A page `git mv`-ed out of `docs/` moves back to its old path, by history (arch: D10.2, D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "docs/running.md", "# Running\n")
    _commit(root, "add the page")
    _move(root, "docs/running.md", "HOWTO-run.md")
    _commit(root, "scramble")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:HOWTO-run.md"]
    move = result.moves[0]
    assert move.source == "HOWTO-run.md"
    assert move.target == "docs/running.md"
    assert move.kind == "file"
    assert move.basis == "history"
    assert "renamed from docs/running.md in" in move.evidence
    assert [finding.id for finding in result.findings] == ["doc-misplaced:HOWTO-run.md"]
    assert "move:HOWTO-run.md to docs/running.md" in result.findings[0].evidence


def test_locate_history_target_rejected_when_the_old_path_exists_now(
    tmp_path: Path,
) -> None:
    """A history target that something now occupies is rejected, and the next source runs (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "docs/design/a.md", "# A\n")
    _commit(root, "add the page")
    _move(root, "docs/design/a.md", "misc/a.md")
    _commit(root, "scramble")
    # Something else now occupies the old path, so moving back there would collide.
    _write(root, "docs/design/a.md", "# A, again\n")
    _commit(root, "re-add at the old path")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:misc/a.md"]
    move = result.moves[0]
    assert move.basis == "standard"
    assert move.target == "docs/a.md"


def test_locate_link_evidence_resolves_a_unique_basename_match(tmp_path: Path) -> None:
    """A broken link naming a missing path gives that candidate's target, by its basename (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/running.md", "# Running\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/running.md")
    result = layout.locate(root, survey, None, [broken_link])

    assert [move.id for move in result.moves] == ["move:misc/running.md"]
    move = result.moves[0]
    assert move.target == "docs/running.md"
    assert move.basis == "link"
    assert "README.md" in move.evidence


def test_locate_link_evidence_is_skipped_when_two_candidates_share_a_basename(
    tmp_path: Path,
) -> None:
    """A basename that matches more than one candidate gives no link target (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/running.md", "# Running one\n")
    _write(root, "other/running.md", "# Running two\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/running.md")
    result = layout.locate(root, survey, None, [broken_link])

    names = layout._basename_index(frozenset(survey.files))
    links = layout._broken_link_targets([broken_link])
    for page in ("misc/running.md", "other/running.md"):
        assert layout._link_target(page, names, links, frozenset(survey.files)) is None
    sources = {move.source for move in result.moves}
    assert "misc/running.md" not in sources
    assert "other/running.md" not in sources
    evidence = {finding.path: finding.evidence for finding in result.findings}
    for page in ("misc/running.md", "other/running.md"):
        assert (
            "target docs/running.md is claimed by more than one page" in evidence[page]
        )


def test_locate_standard_evidence_uses_front_matter_type(tmp_path: Path) -> None:
    """With no history or link evidence, the standard reads the page's own `type` (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "---\ntype: how-to\n---\n# Page\n")
    _commit(root, "add")

    survey = _survey(root)
    # D12.9: a small repository resolves docs = "auto" to readme; this test means full.
    result = layout.locate(root, survey, Config(docs="full"), [])

    move = result.moves[0]
    assert move.basis == "standard"
    assert move.target == "docs/how-to/page.md"


def test_locate_standard_evidence_falls_back_with_layout_off(tmp_path: Path) -> None:
    """`[refs] layout = false` turns off the type-folder standard, not the row itself (arch: D10.2, D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "---\ntype: how-to\n---\n# Page\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(refs_layout=False)
    result = layout.locate(root, survey, cfg, [])

    assert len(result.findings) == 1
    move = result.moves[0]
    assert move.target == "docs/page.md"


def test_locate_standard_evidence_falls_back_with_docs_readme(tmp_path: Path) -> None:
    """`docs = "readme"` also turns off the type-folder standard (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "---\ntype: how-to\n---\n# Page\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(docs="readme")
    result = layout.locate(root, survey, cfg, [])

    assert result.moves[0].target == "docs/page.md"


# ---------------------------------------------------------------------------
# Units: a directory move (D10.6)
# ---------------------------------------------------------------------------


def test_locate_groups_a_renamed_directory_into_one_move(tmp_path: Path) -> None:
    """A directory whose pages all move the same way becomes one `dir` move (arch: D10.2, D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "docs/design/a.md", "# A\n")
    _write(root, "docs/design/b.md", "# B\n")
    _write(root, "docs/design/notes.txt", "not markdown\n")
    _commit(root, "add the design docs")
    _move(root, "docs/design", "misc/design")
    # An unrelated page sits beside `misc/design/`, with a target that
    # does not fit the `misc/` -> `docs/` formula, so the ancestor `misc/`
    # does not also qualify as a unit; only the narrower `misc/design/`
    # does, matching the "largest such S" example of D10.6.
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _commit(root, "scramble")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    moves_by_id = {move.id: move for move in result.moves}
    assert "move:misc/design/" in moves_by_id
    move = moves_by_id["move:misc/design/"]
    assert move.kind == "dir"
    assert move.source == "misc/design/"
    assert move.target == "docs/design/"
    assert move.pages == ("misc/design/a.md", "misc/design/b.md")

    # One finding per page, even though the move unit is a directory (I-36).
    design_findings = [
        finding
        for finding in result.findings
        if finding.path.startswith("misc/design/")
    ]
    finding_paths = sorted(finding.path for finding in design_findings)
    assert finding_paths == ["misc/design/a.md", "misc/design/b.md"]
    for finding in design_findings:
        assert "move:misc/design/ to docs/design/" in finding.evidence


def test_locate_keeps_individual_moves_when_siblings_disagree(tmp_path: Path) -> None:
    """Two pages under one directory with different targets each get their own move (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/a.md", "---\ntype: how-to\n---\n# A\n")
    _write(root, "misc/b.md", "# B, untyped\n")
    _commit(root, "add")

    survey = _survey(root)
    # D12.9: a small repository resolves docs = "auto" to readme; this test means full.
    result = layout.locate(root, survey, Config(docs="full"), [])

    sources = sorted(move.source for move in result.moves)
    assert sources == ["misc/a.md", "misc/b.md"]
    assert all(move.kind == "file" for move in result.moves)


# ---------------------------------------------------------------------------
# Vetoes (D10.6, I-38)
# ---------------------------------------------------------------------------


def test_locate_protect_veto_on_the_target_blocks_the_move(tmp_path: Path) -> None:
    """A `protect` glob on the target stops the move, and the finding says `protected` (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/legal.md", "# Legal\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(protect=("docs/legal.md",))
    result = layout.locate(root, survey, cfg, [])

    assert result.moves == []
    assert len(result.findings) == 1
    assert result.findings[0].evidence.endswith("protected")
    assert result.findings[0].action == "add a [[keep]] entry"


def test_locate_protect_veto_on_the_source_blocks_the_move(tmp_path: Path) -> None:
    """A `protect` glob on the source stops the move too (arch: D10.6)."""
    # D12.11: `notes_page.md` looks like scratch and is no candidate now,
    # so the page has a name that does not.
    root = tmp_path
    _init(root)
    _write(root, "legacy/overview_page.md", "# Notes\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(protect=("legacy/**",))
    result = layout.locate(root, survey, cfg, [])

    assert result.moves == []
    assert result.findings[0].evidence.endswith("protected")


# ---------------------------------------------------------------------------
# Broken-link evidence notes (D10.6, I-39)
# ---------------------------------------------------------------------------


def test_locate_broken_link_evidence_note_names_the_new_location(
    tmp_path: Path,
) -> None:
    """A broken link that names a move's target gets a hint, with the finding id unchanged (arch: D10.6, I-39)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/running.md", "# Running\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/running.md")
    result = layout.locate(root, survey, None, [broken_link])

    assert set(result.evidence_notes) == {broken_link.id}
    note = result.evidence_notes[broken_link.id]
    assert note == "the target is now at misc/running.md; approve move:misc/running.md"


def test_locate_broken_link_hint_when_the_match_already_lives_under_docs(
    tmp_path: Path,
) -> None:
    """A broken link that matches an existing docs page by basename gets a fix hint, not a move (arch: D10.6, I-39)."""
    root = tmp_path
    _init(root)
    _write(root, "docs/existing/thing.md", "# Thing\n")
    _write(root, "README.md", "see [thing](docs/other/thing.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/other/thing.md")
    result = layout.locate(root, survey, None, [broken_link])

    assert result.moves == []
    note = result.evidence_notes[broken_link.id]
    assert note == "a file with this name is at docs/existing/thing.md; fix the link"


def test_locate_evidence_notes_never_rename_a_finding_id(tmp_path: Path) -> None:
    """D10.6 adds evidence only: the refcheck finding id stays exactly as given (arch: D10.6, I-39)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/running.md", "# Running\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/running.md")
    original_id = broken_link.id
    result = layout.locate(root, survey, None, [broken_link])

    assert original_id in result.evidence_notes
    assert broken_link.id == original_id


# ---------------------------------------------------------------------------
# The scratch set (T1 dependency)
# ---------------------------------------------------------------------------


def test_locate_excludes_a_path_the_scratch_row_already_flagged(tmp_path: Path) -> None:
    """A page the `scratch` row flagged gives no `doc-misplaced` finding, one remedy each (arch: D10.2)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/draft_v2.md", "# Draft\n")
    _commit(root, "add")

    survey = _survey(root)
    scratch = _scratch_finding("misc/draft_v2.md")
    result = layout.locate(root, survey, None, [scratch])

    assert result == layout.LayoutResult(findings=[], moves=[], evidence_notes={})


# ---------------------------------------------------------------------------
# A protected file inside a directory unit (D10.6, I-38)
# ---------------------------------------------------------------------------


def test_locate_protect_on_a_contained_file_blocks_the_directory_move(
    tmp_path: Path,
) -> None:
    """A protected page stops its directory from moving as one unit (arch: D10.2, D10.6).

    A `protect` glob on one page inside an otherwise qualifying directory
    stops the whole directory from moving as one unit: the protected page
    gets no move, and its unprotected sibling still gets its own move
    (arch: D10.2, D10.6). A directory move never carries a protected path
    along (I-38).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(protect=("misc/design/a.md",))
    result = layout.locate(root, survey, cfg, [])

    # No move ever carries a protected page, whether as a lone move or
    # bundled inside a directory move (I-38).
    assert all(move.kind != "dir" for move in result.moves)
    for move in result.moves:
        assert "misc/design/a.md" not in move.pages

    moves_by_source = {move.source: move for move in result.moves}
    assert "misc/design/a.md" not in moves_by_source
    assert moves_by_source["misc/design/b.md"].target == "docs/b.md"

    findings_by_path = {finding.path: finding for finding in result.findings}
    assert findings_by_path["misc/design/a.md"].evidence.endswith("protected")
    assert findings_by_path["misc/design/a.md"].action == "add a [[keep]] entry"
    assert "move:misc/design/b.md" in findings_by_path["misc/design/b.md"].evidence


# ---------------------------------------------------------------------------
# Link evidence, the directory case (D10.6, step 2)
# ---------------------------------------------------------------------------


def test_locate_link_evidence_resolves_a_directory_by_basename(tmp_path: Path) -> None:
    """Pages under a missing linked directory get one `dir` move (arch: D10.2, D10.6).

    A broken link naming a missing directory gives every page under the
    one surveyed directory that shares its basename a `link` target, and
    the pages bundle into one `dir` move (arch: D10.2, D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    # An unrelated page sits beside `misc/design/`, with a target that
    # does not fit the `misc/` -> `docs/` formula, so the ancestor `misc/`
    # does not also qualify as a unit; only the narrower `misc/design/`
    # does, the same disambiguation `test_locate_groups_a_renamed_directory_into_one_move`
    # (history evidence) already relies on.
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _write(root, "README.md", "see [design](docs/design/)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    # D12.9: a small repository resolves docs = "auto" to readme; this test means full.
    result = layout.locate(root, survey, Config(docs="full"), [broken_link])

    moves_by_id = {move.id: move for move in result.moves}
    assert "move:misc/design/" in moves_by_id
    move = moves_by_id["move:misc/design/"]
    assert move.kind == "dir"
    assert move.source == "misc/design/"
    assert move.target == "docs/design/"
    assert move.basis == "link"
    assert "README.md" in move.evidence
    assert move.pages == ("misc/design/a.md", "misc/design/b.md")


def test_locate_directory_link_evidence_is_skipped_when_two_directories_share_a_basename(
    tmp_path: Path,
) -> None:
    """A directory basename that matches more than one surveyed directory gives no link target (arch: D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A one\n")
    _write(root, "other/design/b.md", "# B two\n")
    _write(root, "README.md", "see [design](docs/design/)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    result = layout.locate(root, survey, None, [broken_link])

    moves_by_source = {move.source: move for move in result.moves}
    assert moves_by_source["misc/design/a.md"].basis == "standard"
    assert moves_by_source["other/design/b.md"].basis == "standard"


# ---------------------------------------------------------------------------
# Units: a non-Markdown file moves only on evidence (D10.6, units)
# ---------------------------------------------------------------------------


def test_locate_keeps_a_lone_page_a_file_move_when_its_sibling_has_no_evidence(
    tmp_path: Path,
) -> None:
    """A lone standard-placed page gets a file move and its sibling stays (arch: D10.2, D10.6).

    The standard places a page, not the files beside it. A lone
    standard-placed page with a non-Markdown sibling gets a file move, and
    the sibling stays where it is (arch: D10.2, D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/onlypage/doc.md", "---\ntype: how-to\n---\n# Doc\n")
    _write(root, "misc/onlypage/fig.png", "binary\n")
    _commit(root, "add")

    survey = _survey(root)
    # D12.9: a small repository resolves docs = "auto" to readme; this test means full.
    result = layout.locate(root, survey, Config(docs="full"), [])

    assert [move.id for move in result.moves] == ["move:misc/onlypage/doc.md"]
    move = result.moves[0]
    assert move.kind == "file"
    assert move.target == "docs/how-to/doc.md"
    assert move.pages == ("misc/onlypage/doc.md",)


def test_locate_never_moves_a_code_directory_for_one_page(tmp_path: Path) -> None:
    """A page in a code directory moves alone (arch: D10.2, D10.6).

    The directory and its code files never move into `docs/` on the standard.
    """
    root = tmp_path
    _init(root)
    _write(root, "src/NOTES.md", "# Notes\n")
    _write(root, "src/main.rs", "fn main() {}\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:src/NOTES.md"]
    move = result.moves[0]
    assert move.kind == "file"
    assert move.target == "docs/NOTES.md"
    assert [finding.id for finding in result.findings] == ["doc-misplaced:src/NOTES.md"]


def test_locate_never_moves_a_code_directory_on_page_history_only(
    tmp_path: Path,
) -> None:
    """History that places a page does not move the code file beside it (arch: D10.2, D10.6).

    The code file was never renamed out of `docs/`, so the page moves
    alone.
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/DESIGN.md", "# Design\n")
    _commit(root, "add the page")
    _move(root, "docs/DESIGN.md", "crates/foo/DESIGN.md")
    _write(root, "crates/foo/lib.rs", "pub fn f() {}\n")
    _commit(root, "scramble")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:crates/foo/DESIGN.md"]
    move = result.moves[0]
    assert move.kind == "file"
    assert move.basis == "history"
    assert move.target == "docs/DESIGN.md"


def test_locate_groups_a_lone_page_with_a_sibling_renamed_out_of_docs(
    tmp_path: Path,
) -> None:
    """A lone page moves with its directory when history renamed its sibling (arch: D10.2, D10.6).

    A lone page takes its directory as a unit when history also renamed
    its non-Markdown sibling from the same target directory (arch: D10.2,
    D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/how-to/doc.md", "# Doc\n")
    _write(root, "docs/how-to/fig.png", "binary\n")
    _commit(root, "add")
    _move(root, "docs/how-to", "misc/onlypage")
    _commit(root, "scramble")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:misc/onlypage/"]
    move = result.moves[0]
    assert move.kind == "dir"
    assert move.target == "docs/how-to/"
    assert move.basis == "history"
    assert move.pages == ("misc/onlypage/doc.md",)


def test_locate_directory_link_carries_a_non_markdown_file(tmp_path: Path) -> None:
    """A directory link move carries a non-Markdown file (arch: D10.2, D10.6).

    A broken link that names a missing directory places every file under
    the matched directory, so its non-Markdown file goes with the `dir`
    move (arch: D10.2, D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    _write(root, "misc/design/fig.png", "binary\n")
    # A sibling page with a type target keeps the ancestor `misc/` out of
    # the unit set, as in the other directory tests.
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _write(root, "README.md", "see [design](docs/design/)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    # D12.9: a small repository resolves docs = "auto" to readme; this test means full.
    result = layout.locate(root, survey, Config(docs="full"), [broken_link])

    assert [move.id for move in result.moves] == [
        "move:misc/design/",
        "move:misc/other.md",
    ]
    move = result.moves[0]
    assert move.target == "docs/design/"
    assert move.basis == "link"
    assert move.pages == ("misc/design/a.md", "misc/design/b.md")


def test_locate_units_skip_an_ancestor_whose_target_already_holds_other_content(
    tmp_path: Path,
) -> None:
    """A unit skips an ancestor whose target holds other content (arch: D10.6).

    A shallower ancestor that would structurally qualify as a unit is
    skipped when its computed target directory already holds a file this
    move does not account for; the narrower, unoccupied directory is
    taken instead (arch: D10.6). `misc/` -> `docs/` would collide with
    `docs/unrelated.md`, which the plan never touches.
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    _write(root, "docs/unrelated.md", "# Unrelated\n")
    _write(root, "README.md", "see [design](docs/design/)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    result = layout.locate(root, survey, None, [broken_link])

    moves_by_id = {move.id: move for move in result.moves}
    assert "move:misc/" not in moves_by_id
    assert "move:misc/design/" in moves_by_id
    move = moves_by_id["move:misc/design/"]
    assert move.target == "docs/design/"
    assert move.pages == ("misc/design/a.md", "misc/design/b.md")


def test_locate_keeps_a_lone_candidate_a_file_move_with_no_sibling(
    tmp_path: Path,
) -> None:
    """A lone candidate with no sibling keeps a file move (arch: D10.6).

    A lone candidate with no sibling file at all stays a plain file
    move: there is nothing for a directory move to carry along, so the
    simpler move is kept (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "# Page\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert len(result.moves) == 1
    assert result.moves[0].kind == "file"
    assert result.moves[0].source == "misc/page.md"


def test_locate_units_skip_a_target_that_another_move_fills(tmp_path: Path) -> None:
    """A directory move skips a target that another move fills (arch: D10.6).

    A directory move needs a target directory that no other move fills.
    `git mv misc/design docs` after `move:ARCHITECTURE.md` made `docs/`
    would nest the pages under `docs/design/`, so each page gets its own
    move (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "ARCHITECTURE.md", "# Architecture\n")
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    moves_by_id = {move.id: move for move in result.moves}
    assert sorted(moves_by_id) == [
        "move:ARCHITECTURE.md",
        "move:misc/design/a.md",
        "move:misc/design/b.md",
    ]
    assert all(move.kind == "file" for move in result.moves)
    assert moves_by_id["move:misc/design/a.md"].target == "docs/a.md"


# ---------------------------------------------------------------------------
# D10.6: target acceptance (inside the repository, unique basename over
# every surveyed path), scoped mode
# ---------------------------------------------------------------------------


def _inside_repository(target: str) -> bool:
    """Say whether a move target is relative and stays inside the repository.

    Args:
        target: A move target as `locate` gives it.

    Returns:
        True when the target has no leading `/` and no `..` segment.
    """
    return not target.startswith("/") and ".." not in target.rstrip("/").split("/")


def test_locate_refuses_a_file_link_target_outside_the_repository(
    tmp_path: Path,
) -> None:
    """A file link target outside the repository is refused (arch: D10.6).

    A link target that is absolute or climbs out of the repository is
    refused, and the standard gives the target instead (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "one/a.md", "# A\n")
    _write(root, "two/b.md", "# B\n")
    _write(root, "README.md", "see [a](/docs/a.md) and [b](../docs/b.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    links = [
        _broken_link("README.md", 1, "/docs/a.md"),
        _broken_link("README.md", 1, "../docs/b.md"),
    ]
    result = layout.locate(root, survey, None, links)

    moves_by_source = {move.source: move for move in result.moves}
    assert sorted(moves_by_source) == ["one/a.md", "two/b.md"]
    assert all(_inside_repository(move.target) for move in result.moves)
    assert moves_by_source["one/a.md"].target == "docs/a.md"
    assert moves_by_source["one/a.md"].basis == "standard"
    assert moves_by_source["two/b.md"].target == "docs/b.md"
    assert moves_by_source["two/b.md"].basis == "standard"


def test_locate_refuses_a_directory_link_target_outside_the_repository(
    tmp_path: Path,
) -> None:
    """A directory link target outside the repository is refused (arch: D10.6).

    A directory link target that is absolute or climbs out of the
    repository gives no link target to the pages under the matched
    directory (arch: D10.6).
    """
    for index, written in enumerate(("/docs/design/", "../docs/design/")):
        root = tmp_path / f"repo{index}"
        root.mkdir()
        _init(root)
        _write(root, "misc/design/a.md", "# A\n")
        _write(root, "misc/design/b.md", "# B\n")
        _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
        _commit(root, "add")

        survey = _survey(root)
        broken_link = _broken_link("README.md", 1, written)
        result = layout.locate(root, survey, None, [broken_link])

        assert result.moves, written
        assert all(_inside_repository(move.target) for move in result.moves), written
        assert all(move.basis == "standard" for move in result.moves), written


def test_locate_link_evidence_counts_every_surveyed_file_with_the_basename(
    tmp_path: Path,
) -> None:
    """Every surveyed file with the basename counts against link evidence (arch: D10.6).

    A docs page that shares the link target's basename means there is no
    link evidence, even though it is not a candidate (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/other/running.md", "# Running, the real page\n")
    _write(root, "misc/running.md", "# Running, a stray copy\n")
    _write(root, "README.md", "see [running](docs/guide/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/guide/running.md")
    result = layout.locate(root, survey, None, [broken_link])

    assert [move.id for move in result.moves] == ["move:misc/running.md"]
    move = result.moves[0]
    assert move.basis == "standard"
    assert move.target == "docs/running.md"
    assert broken_link.id not in result.evidence_notes


def test_locate_directory_link_evidence_counts_a_file_with_the_basename(
    tmp_path: Path,
) -> None:
    """A file named like the linked directory counts against link evidence (arch: D10.6).

    A surveyed file named like the linked directory also counts, so the
    directory match is not unique and gives no link evidence (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/design/a.md", "# A\n")
    _write(root, "misc/design/b.md", "# B\n")
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _write(root, "tools/design", "#!/bin/sh\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    result = layout.locate(root, survey, None, [broken_link])

    assert result.moves
    assert all(move.basis == "standard" for move in result.moves)


def test_locate_scoped_gives_findings_only_for_pages_in_only(
    tmp_path: Path, monkeypatch
) -> None:
    """A scoped locate gives findings only for pages in `only` (arch: D10.6).

    With `only` set, only candidates in `only` give a finding, there is
    no move and no note, and no git command runs (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/running.md", "# Running\n")
    _commit(root, "add the page")
    _move(root, "docs/running.md", "misc/running.md")
    _write(root, "other/page.md", "# Page\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "scramble")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/running.md")

    def _no_git(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"a scoped locate ran a command: {args}")

    monkeypatch.setattr(layout.subprocess, "run", _no_git)
    result = layout.locate(
        root, survey, None, [broken_link], only=frozenset({"misc/running.md"})
    )

    assert result.moves == []
    assert result.evidence_notes == {}
    assert [finding.id for finding in result.findings] == [
        "doc-misplaced:misc/running.md"
    ]
    finding = result.findings[0]
    assert finding.evidence.startswith("Markdown page outside docs/")
    assert "protected" not in finding.evidence


def test_locate_scoped_with_no_candidate_in_only_gives_no_note(
    tmp_path: Path,
) -> None:
    """A scoped locate with no candidate in `only` gives no note (arch: D10.6).

    With `only` set and no candidate in it, the result is empty: the
    fix-the-link hint of a full check is not given (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/existing/thing.md", "# Thing\n")
    _write(root, "misc/page.md", "# Page\n")
    _write(root, "README.md", "see [thing](docs/other/thing.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/other/thing.md")
    result = layout.locate(
        root, survey, None, [broken_link], only=frozenset({"README.md"})
    )

    assert result == layout.LayoutResult(findings=[], moves=[], evidence_notes={})


# ---------------------------------------------------------------------------
# One target, one move (D10.6)
# ---------------------------------------------------------------------------


def test_locate_drops_two_standard_moves_with_the_same_target(tmp_path: Path) -> None:
    """Two standard moves with the same target give no move (arch: D10.6).

    Two standard targets `docs/<basename>` with the same basename give no
    move, and each page says its target is claimed by more than one page
    (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/guide.md", "# Guide one\n")
    _write(root, "other/guide.md", "# Guide two\n")
    _write(root, "lib/x.md", "# X\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == ["move:lib/x.md"]
    by_path = {finding.path: finding for finding in result.findings}
    for page in ("misc/guide.md", "other/guide.md"):
        finding = by_path[page]
        assert finding.evidence == (
            "Markdown page outside docs/; "
            "target docs/guide.md is claimed by more than one page"
        )
        assert finding.action == "add a [[keep]] entry"
    assert "move:lib/x.md" in by_path["lib/x.md"].evidence


def test_locate_drops_a_history_move_and_a_link_move_with_the_same_target(
    tmp_path: Path,
) -> None:
    """A history move and a link move with the same target give no move (arch: D10.6).

    A history target and a directory-link page target that are the same
    path give no move for either page (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/design/a.md", "# A\n")
    _commit(root, "add the page")
    _move(root, "docs/design/a.md", "top/a.md")
    _commit(root, "scramble")
    _write(root, "misc/design/a.md", "# Another A\n")
    _write(root, "README.md", "see [design](docs/design/)\n")
    _commit(root, "add")

    survey = _survey(root)
    broken_link = _broken_link("README.md", 1, "docs/design/")
    result = layout.locate(root, survey, None, [broken_link])

    assert result.moves == []
    by_path = {finding.path: finding for finding in result.findings}
    for page in ("top/a.md", "misc/design/a.md"):
        assert by_path[page].evidence == (
            "Markdown page outside docs/; "
            "target docs/design/a.md is claimed by more than one page"
        )
    assert broken_link.id not in result.evidence_notes


def test_collisions_group_a_file_target_inside_a_directory_target() -> None:
    """A file target inside a directory target is in the same collision group (arch: D10.6).

    A file target inside a directory move's target is in the same group,
    and a group of one move is no collision (arch: D10.6).
    """
    dir_move = layout.Move(
        id="move:misc/design/",
        source="misc/design/",
        target="docs/design/",
        kind="dir",
        basis="link",
        evidence="named by a broken link in README.md",
        pages=("misc/design/a.md", "misc/design/b.md"),
    )
    inside = layout.Move(
        id="move:top/c.md",
        source="top/c.md",
        target="docs/design/c.md",
        kind="file",
        basis="history",
        evidence="renamed from docs/design/c.md in 1a2b3c4",
        pages=("top/c.md",),
    )
    alone = layout.Move(
        id="move:lib/x.md",
        source="lib/x.md",
        target="docs/x.md",
        kind="file",
        basis="standard",
        evidence="the standard target for an untyped page",
        pages=("lib/x.md",),
    )

    assert layout._collisions([dir_move, inside, alone]) == {
        "move:misc/design/": "docs/design/",
        "move:top/c.md": "docs/design/",
    }


def test_locate_gives_no_first_wins_target_to_two_history_pages(tmp_path: Path) -> None:
    """Two history pages with the same old path get no first-wins target (arch: D10.6).

    Two pages renamed from the same old path both claim it, so neither
    moves; the first page in sort order does not win (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/a.md", "# A\n")
    _commit(root, "add the page")
    _move(root, "docs/a.md", "x/a.md")
    _commit(root, "first scramble")
    _write(root, "docs/a.md", "# A, again\n")
    _commit(root, "re-add at the old path")
    _move(root, "docs/a.md", "y/b.md")
    _commit(root, "second scramble")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert result.moves == []
    by_path = {finding.path: finding for finding in result.findings}
    for page in ("x/a.md", "y/b.md"):
        assert by_path[page].evidence == (
            "Markdown page outside docs/; "
            "target docs/a.md is claimed by more than one page"
        )


# ---------------------------------------------------------------------------
# A kept page does not move (D10.2, D10.6)
# ---------------------------------------------------------------------------


def test_locate_gives_a_kept_page_its_finding_but_no_move(tmp_path: Path) -> None:
    """A `[[keep]]` entry on a `doc-misplaced` id keeps the finding and stops the move (arch: D10.2, D10.6)."""
    root = tmp_path
    _init(root)
    _write(root, "GUIDE.md", "# Guide\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(keep={"doc-misplaced:GUIDE.md": "the guide stays at the root"})
    result = layout.locate(root, survey, cfg, [])

    assert result.moves == []
    assert [finding.id for finding in result.findings] == ["doc-misplaced:GUIDE.md"]
    assert "move:" not in result.findings[0].evidence


def test_locate_keeps_every_page_under_a_rule_prefix_keep(tmp_path: Path) -> None:
    """A `[[keep]]` id `doc-misplaced` keeps every misplaced page in place by prefix.

    arch: D15.3, D15.8
    """
    root = tmp_path
    _init(root)
    _write(root, "GUIDE.md", "# Guide\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(keep={"doc-misplaced": "the pages stay where they are"})
    result = layout.locate(root, survey, cfg, [])

    assert result.moves == []
    assert [finding.id for finding in result.findings] == ["doc-misplaced:GUIDE.md"]


def test_locate_gives_a_broken_link_to_a_kept_page_no_note(tmp_path: Path) -> None:
    """A broken link whose target a kept page would fill gets no `approve move:` note (arch: D10.6, I-39)."""
    root = tmp_path
    _init(root)
    _write(root, "misc/running.md", "# Running\n")
    _write(root, "README.md", "see [running](docs/running.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(keep={"doc-misplaced:misc/running.md": "it stays in misc/"})
    broken_link = _broken_link("README.md", 1, "docs/running.md")
    result = layout.locate(root, survey, cfg, [broken_link])

    assert result.moves == []
    assert result.evidence_notes == {}


def test_locate_kept_page_stops_its_directory_unit(tmp_path: Path) -> None:
    """A kept page stops its directory from moving as one unit (arch: D10.2, D10.6).

    A directory that holds a kept page is never one directory move, like a
    `protect` match (I-38); its other page still gets a file move
    (arch: D10.2, D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/design/a.md", "# A\n")
    _write(root, "docs/design/b.md", "# B\n")
    _commit(root, "add the design docs")
    _move(root, "docs/design", "misc/design")
    _commit(root, "scramble")

    survey = _survey(root)
    cfg = Config(keep={"doc-misplaced:misc/design/a.md": "a stays"})
    result = layout.locate(root, survey, cfg, [])

    assert [move.id for move in result.moves] == ["move:misc/design/b.md"]
    assert result.moves[0].target == "docs/design/b.md"
    assert sorted(finding.path for finding in result.findings) == [
        "misc/design/a.md",
        "misc/design/b.md",
    ]


# ---------------------------------------------------------------------------
# `[root] allow` exempts a root page (D10.2)
# ---------------------------------------------------------------------------


def test_candidate_filter_honours_root_allow_at_depth_zero_only() -> None:
    """A `[root] allow` glob exempts a page at the root only (arch: D10.2).

    A root page that a `[root] allow` glob names is not a candidate; the
    same name one level down still is (arch: D10.2).
    """
    allow = ("HANDOFF.md", "PLAN*.md")
    assert layout._is_candidate("HANDOFF.md", frozenset(), root_allow=allow) is False
    assert layout._is_candidate("PLAN-2.md", frozenset(), root_allow=allow) is False
    assert layout._is_candidate("GUIDE.md", frozenset(), root_allow=allow) is True
    assert layout._is_candidate("sub/HANDOFF.md", frozenset(), root_allow=allow) is True
    assert layout._is_candidate("HANDOFF.md", frozenset()) is True


def test_locate_root_allow_exempts_a_root_page(tmp_path: Path) -> None:
    """`[root] allow` in `trueup.toml` takes its root pages out of `doc-misplaced` (arch: D10.2)."""
    from trueup import config as config_mod

    root = tmp_path
    _init(root)
    _write(root, "trueup.toml", '[root]\nallow = ["HANDOFF.md", "FABLE.md"]\n')
    for name in ("HANDOFF.md", "FABLE.md", "GUIDE.md"):
        _write(root, name, f"# {name}\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = config_mod.load(root)
    assert cfg is not None
    result = layout.locate(root, survey, cfg, [])

    assert [finding.id for finding in result.findings] == ["doc-misplaced:GUIDE.md"]


# ---------------------------------------------------------------------------
# A target that exists is refused (D10.6)
# ---------------------------------------------------------------------------


def test_locate_refuses_a_file_move_onto_an_existing_target(tmp_path: Path) -> None:
    """A file move onto an existing target is refused (arch: D10.6).

    A standard target that already exists gives no move, and the evidence
    names it (arch: D10.6).
    """
    root = tmp_path
    _init(root)
    _write(root, "lib/x.md", "# X\n")
    _write(root, "docs/x.md", "# Another X\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert "move:lib/x.md" not in [move.id for move in result.moves]
    by_path = {finding.path: finding for finding in result.findings}
    assert by_path["lib/x.md"].evidence.endswith(
        "; target docs/x.md exists, move it by hand"
    )


def test_locate_refuses_a_directory_move_onto_an_existing_directory(
    tmp_path: Path,
) -> None:
    """A directory move onto an existing directory falls back to file moves (arch: D10.6, D12.11).

    A directory target that exists on disk, even empty, gives no `dir`
    move: `git mv` would nest the source inside it. The pages fall back to
    file moves (arch: D10.6, D12.11). D12.11 changed this contract: the
    old result was a refusal for each page.
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/design/a.md", "# A\n")
    _write(root, "docs/design/b.md", "# B\n")
    _commit(root, "add the design docs")
    _move(root, "docs/design", "misc/design")
    # A typed sibling keeps the ancestor `misc/` from being the unit, as in
    # `test_locate_groups_a_renamed_directory_into_one_move`.
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _commit(root, "scramble")
    (root / "docs" / "design").mkdir(parents=True)

    survey = _survey(root)
    result = layout.locate(root, survey, None, [])

    assert [move.id for move in result.moves] == [
        "move:misc/design/a.md",
        "move:misc/design/b.md",
        "move:misc/other.md",
    ]
    assert all(move.kind == "file" for move in result.moves)


def test_locate_skips_a_directory_unit_whose_target_holds_an_ignored_file(
    tmp_path: Path,
) -> None:
    """A directory unit is skipped when its target holds an ignored file (arch: D12.11).

    A target directory that holds only an ignored file is absent from the
    survey, but it exists on disk. The directory unit is skipped and the
    pages get file moves (arch: D12.11).
    """
    root = tmp_path
    _init(root)
    _write(root, ".gitignore", "_build/\n")
    _write(root, "docs/design/a.md", "# A\n")
    _write(root, "docs/design/b.md", "# B\n")
    _commit(root, "add the design docs")
    _move(root, "docs/design", "misc/design")
    _write(root, "misc/other.md", "---\ntype: how-to\n---\n# Other\n")
    _commit(root, "scramble")
    _write(root, "docs/design/_build/index.html", "<html></html>\n")

    survey = _survey(root)
    assert "docs/design/_build/index.html" not in survey.files
    result = layout.locate(root, survey, None, [])

    assert "move:misc/design/" not in [move.id for move in result.moves]
    assert {"move:misc/design/a.md", "move:misc/design/b.md"} <= {
        move.id for move in result.moves
    }


def test_locate_excludes_a_scratch_looking_path_without_a_scratch_finding(
    tmp_path: Path,
) -> None:
    """A scratch-looking path is never a candidate (arch: D12.11).

    A scratch-looking page gives no `doc-misplaced` candidate, even when
    the caller passes no `scratch` finding for it (arch: D12.11).
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/scratch_1.md", "# Scratch\n")
    _commit(root, "add")

    result = layout.locate(root, _survey(root), None, [])

    assert result == layout.LayoutResult(findings=[], moves=[], evidence_notes={})


# ---------------------------------------------------------------------------
# Unquoted paths from the git history (D10.6, D10.7)
# ---------------------------------------------------------------------------


def test_history_renames_reads_a_committed_non_ascii_rename(tmp_path: Path) -> None:
    """A committed non-ASCII rename comes back unquoted (arch: D10.6, D10.7).

    A committed rename of a non-ASCII page comes back unquoted, even when
    the repository quotes paths (arch: D10.6, D10.7).
    """
    root = tmp_path
    _init(root)
    _git(root, "config", "core.quotePath", "true")
    _write(root, "docs/guide/Übersicht.md", "# Übersicht\n")
    _commit(root, "add the page")
    _move(root, "docs/guide/Übersicht.md", "misc/Übersicht.md")
    _commit(root, "scramble")

    renames = layout._history_renames(root)

    assert set(renames) == {"misc/Übersicht.md"}
    assert renames["misc/Übersicht.md"][0] == "docs/guide/Übersicht.md"


def test_history_renames_reads_a_staged_non_ascii_rename(tmp_path: Path) -> None:
    """A staged non-ASCII rename comes back unquoted (arch: D10.6, D10.7).

    A staged rename of a non-ASCII page comes back unquoted, even when
    the repository quotes paths (arch: D10.6, D10.7).
    """
    root = tmp_path
    _init(root)
    _git(root, "config", "core.quotePath", "true")
    _write(root, "docs/guide/Übersicht.md", "# Übersicht\n")
    _commit(root, "add the page")
    _move(root, "docs/guide/Übersicht.md", "misc/Übersicht.md")

    renames = layout._history_renames(root)

    assert renames == {
        "misc/Übersicht.md": ("docs/guide/Übersicht.md", "a staged change")
    }


def test_broken_link_note_names_the_one_file_with_the_basename() -> None:
    """The note uses the one-index lookup and skips same-named directories.

    arch: D14.14, D14.15
    """
    link = _broken_link("README.md", 1, "docs/running.md")
    links = layout._broken_link_targets([link])
    files = ("README.md", "misc/running.md", "dir/running.md/inner.txt")
    notes = layout._broken_link_evidence_notes(links, [], frozenset(), files)
    assert notes == {
        link.id: "a file with this name is at misc/running.md; fix the link"
    }
    two = files + ("other/running.md",)
    assert layout._broken_link_evidence_notes(links, [], frozenset(), two) == {}


def test_candidate_filter_reads_the_docs_dir_in_force() -> None:
    """`[layout] docs_dir` names the segment that takes a page out of the candidates.

    arch: D14.4
    """
    assert (
        layout._is_candidate("manual/page.md", frozenset(), docs_dir="manual") is False
    )
    assert (
        layout._is_candidate("pkg/manual/page.md", frozenset(), docs_dir="manual")
        is False
    )
    assert layout._is_candidate("docs/page.md", frozenset(), docs_dir="manual") is True


def test_acceptance_checks_read_the_docs_dir_in_force() -> None:
    """A history or link target is acceptable under the `docs_dir` in force only.

    arch: D14.4
    """
    files = frozenset({"README.md"})
    assert layout._acceptable("manual/a.md", files, "manual") is True
    assert layout._acceptable("docs/a.md", files, "manual") is False
    assert layout._acceptable("docs/a.md", files) is True
    assert layout._acceptable_directory("manual/guides", files, "manual") is True
    assert layout._acceptable_directory("docs/guides", files, "manual") is False
    assert layout._acceptable_directory("docs/guides", files) is True


def test_locate_standard_target_uses_the_docs_dir_in_force(tmp_path: Path) -> None:
    """The standard target and the evidence name `[layout] docs_dir`.

    A page under `docs_dir` is not a candidate; a page under `docs/` is
    one when `docs_dir` is another name.

    arch: D14.4
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "---\ntype: how-to\n---\n# Page\n")
    _write(root, "manual/kept.md", "# Kept\n")
    _write(root, "docs/old.md", "# Old\n")
    _commit(root, "add")

    survey = _survey(root)
    cfg = Config(docs="full", layout_docs_dir="manual")
    result = layout.locate(root, survey, cfg, [])

    targets = {move.source: move.target for move in result.moves}
    assert targets == {
        "docs/old.md": "manual/old.md",
        "misc/page.md": "manual/how-to/page.md",
    }
    for finding in result.findings:
        assert finding.evidence.startswith("Markdown page outside manual/; ")


def test_locate_standard_target_has_no_type_directory_with_types_off(
    tmp_path: Path,
) -> None:
    """`[layout] types = false` gives `<docs_dir>/<basename>` for a typed page.

    arch: D14.4
    """
    root = tmp_path
    _init(root)
    _write(root, "misc/page.md", "---\ntype: how-to\n---\n# Page\n")
    _commit(root, "add")

    survey = _survey(root)
    result = layout.locate(root, survey, Config(docs="full", layout_types=False), [])

    assert [move.target for move in result.moves] == ["docs/page.md"]


def test_locate_link_evidence_reads_the_docs_dir_in_force(tmp_path: Path) -> None:
    """A broken link into `docs_dir` gives the link target; one into `docs/` does not.

    arch: D14.4
    """
    root = tmp_path
    _init(root)
    _write(root, "one/running.md", "# Running\n")
    _write(root, "two/setup.md", "# Setup\n")
    _write(root, "README.md", "[a](manual/running.md) [b](docs/setup.md)\n")
    _commit(root, "add")

    survey = _survey(root)
    links = [
        _broken_link("README.md", 1, "manual/running.md"),
        _broken_link("README.md", 1, "docs/setup.md"),
    ]
    cfg = Config(layout_docs_dir="manual")
    result = layout.locate(root, survey, cfg, links)

    moves = {move.source: (move.target, move.basis) for move in result.moves}
    assert moves == {
        "one/running.md": ("manual/running.md", "link"),
        "two/setup.md": ("manual/setup.md", "standard"),
    }


def _tooling_tree(root: Path) -> None:
    """Make an empty repository with a root README for the D15.13 tests.

    Args:
        root: The repository root.
    """
    _init(root)
    _write(root, "README.md")


def test_locate_leaves_a_tooling_segment_page_alone(tmp_path: Path) -> None:
    """A page under `change_log`, `locale`, `content` or `_templates` gives no row (arch: D15.13)."""
    _tooling_tree(tmp_path)
    for seg in ("change_log", "changelog", "locale", "content", "_templates"):
        _write(tmp_path, f"pkg/{seg}/v1.md", "# v1\n")
    _write(tmp_path, "pkg/guide.md", "# guide\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    assert [f.path for f in result.findings] == ["pkg/guide.md"]


def test_locate_leaves_a_directory_that_code_names(tmp_path: Path) -> None:
    """A page whose directory a non-Markdown file names gets no row and no move (arch: D15.13)."""
    _tooling_tree(tmp_path)
    _write(tmp_path, "core/blocks/a.md", "# a\n")
    _write(tmp_path, "tools/run.sh", "cat core/blocks/a.md\n")
    _write(tmp_path, "pi/standards/ts/b.md", "# b\n")
    _write(tmp_path, "pi/ext.ts", "// see pi/standards/ for the rules\n")
    _write(tmp_path, "misc/c.md", "# c\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    assert [f.path for f in result.findings] == ["misc/c.md"]


def test_locate_ignores_a_directory_named_only_in_markdown(tmp_path: Path) -> None:
    """A Markdown mention of a directory does not exempt its pages (arch: D15.13)."""
    _tooling_tree(tmp_path)
    _write(tmp_path, "misc/c.md", "# c\n")
    _write(tmp_path, "other.md", "see misc/\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    assert "misc/c.md" in [f.path for f in result.findings]


def test_locate_gives_a_content_tree_one_info_row(tmp_path: Path) -> None:
    """More than 20 pages under one top directory give one `doc-tree` info row (arch: D15.13)."""
    _tooling_tree(tmp_path)
    for index in range(21):
        _write(tmp_path, f"site/p{index}/page.md", "# p\n")
    _write(tmp_path, "misc/c.md", "# c\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    rows = [f for f in result.findings if f.rule == "doc-tree"]
    assert [(f.id, f.severity) for f in rows] == [("doc-tree:site/", "info")]
    assert "holds 21 pages" in rows[0].evidence
    assert [f.path for f in result.findings if f.rule == "doc-misplaced"] == [
        "misc/c.md"
    ]
    assert all(not m.source.startswith("site/") for m in result.moves)


def test_locate_keeps_a_tree_of_20_pages_as_candidates(tmp_path: Path) -> None:
    """Exactly 20 pages stay candidates and give no `doc-tree` row (arch: D15.13)."""
    _tooling_tree(tmp_path)
    for index in range(20):
        _write(tmp_path, f"site/p{index}/page.md", "# p\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    assert not [f for f in result.findings if f.rule == "doc-tree"]
    assert len([f for f in result.findings if f.rule == "doc-misplaced"]) == 20


def test_locate_leaves_a_generated_page(tmp_path: Path) -> None:
    """A page that says it is generated in its first 5 lines gives no row (arch: D15.13)."""
    _tooling_tree(tmp_path)
    _write(tmp_path, "pkg/a.md", "# A\n\n> Auto-generated. Last sync: today\n")
    _write(tmp_path, "pkg/b.md", "# B\n\n\n\n\n\nGenerated by hand later\n")
    _write(tmp_path, "pkg/c.md", "<!-- DO NOT EDIT -->\n")
    result = layout.locate(tmp_path, _survey(tmp_path), None, [])
    assert [f.path for f in result.findings] == ["pkg/b.md"]


def test_is_candidate_stays_unchanged_for_tooling_segments() -> None:
    """`_is_candidate` still accepts a `locale` page, so the artifact row is unchanged (arch: D15.13)."""
    assert layout._is_candidate("pkg/locale/a.md", frozenset()) is True


def test_front_matter_type_reads_the_checkers_parser() -> None:
    """`_front_matter_type` drops one pair of quotes and reads a block list, as check h does.

    arch: D15.18, D15.30
    """
    assert layout._front_matter_type('---\ntype: "how-to"\n---\n# Page\n') == "how-to"
    text = "---\naudience:\n  - user\ntype: 'reference'\n---\n# Page\n"
    assert layout._front_matter_type(text) == "reference"
    assert layout._front_matter_type("---\ntype: how-to\n  - stray\n---\n") is None
    assert layout._front_matter_type("---\ntype: guide\n---\n") is None


def test_agent_definition_skips_folded_lines_with_the_checkers_parser(
    tmp_path: Path,
) -> None:
    """An agent file with a folded `description`, a block list and quotes is an agent definition.

    arch: D15.30
    """
    agent = tmp_path / "agent.md"
    agent.write_text(
        '---\nname: "reviewer"\ndescription: >\n  Reviews code,\n  all of it.\n'
        "tools:\n  - Read\n---\n\nBody.\n",
        encoding="utf-8",
    )
    typed = tmp_path / "typed.md"
    typed.write_text(
        "---\nname: typed\ndescription: A page.\ntype: how-to\n---\n", encoding="utf-8"
    )
    assert layout._is_agent_definition(agent)
    assert not layout._is_agent_definition(typed)


# ---------------------------------------------------------------------------
# D15.25: the history locator; D15.27: no move for an untracked page
# ---------------------------------------------------------------------------


def test_history_from_a_subdirectory_root_keeps_the_history_basis(
    tmp_path: Path,
) -> None:
    """With `--root` at a subdirectory, the renames lose the prefix and keep the history basis.

    arch: D15.25
    """
    root = tmp_path
    _init(root)
    _write(root, "sub/docs/design/guide.md", "# Guide\n")
    _commit(root, "add the page")
    _move(root, "sub/docs/design/guide.md", "sub/docs/guide.md")
    _commit(root, "flatten")
    _move(root, "sub/docs/guide.md", "sub/guide.md")
    _commit(root, "scramble")

    sub = root / "sub"
    result = layout.locate(sub, _survey(sub), None, [])

    assert [(m.id, m.target, m.basis) for m in result.moves] == [
        ("move:guide.md", "docs/guide.md", "history")
    ]


def test_history_follows_the_rename_chain_back_to_a_docs_path(tmp_path: Path) -> None:
    """A page renamed twice goes back to the newest old path that passes, not to the standard.

    arch: D15.25
    """
    root = tmp_path
    _init(root)
    _write(root, "docs/design/guide.md", "# Guide\n")
    _commit(root, "add the page")
    _move(root, "docs/design/guide.md", "misc/guide.md")
    _commit(root, "out of docs")
    _move(root, "misc/guide.md", "guide.md")
    _commit(root, "to the root")

    result = layout.locate(root, _survey(root), None, [])

    assert [(m.id, m.target, m.basis) for m in result.moves] == [
        ("move:guide.md", "docs/design/guide.md", "history")
    ]


def test_history_target_stops_at_a_cycle() -> None:
    """A rename cycle in the map ends the walk with no target.

    arch: D15.25
    """
    history = {"a.md": ("b.md", "c1"), "b.md": ("a.md", "c2")}
    assert layout._history_target("a.md", history, lambda path: False) is None
    assert layout._history_target("a.md", history, lambda path: path == "b.md") == (
        "b.md",
        "c1",
    )


def test_shallow_clone_says_history_is_unavailable(tmp_path: Path) -> None:
    """In a shallow clone, a standard-basis evidence says the history is not there.

    arch: D15.25
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _init(origin)
    _write(origin, "docs/design/guide.md", "# Guide\n")
    _commit(origin, "add the page")
    _move(origin, "docs/design/guide.md", "guide.md")
    _commit(origin, "to the root")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{origin}", str(clone))

    result = layout.locate(clone, _survey(clone), None, [])

    assert [(m.id, m.basis) for m in result.moves] == [("move:guide.md", "standard")]
    assert result.moves[0].evidence.endswith("; history unavailable (shallow clone)")


def test_untracked_page_gets_its_finding_but_no_move(tmp_path: Path) -> None:
    """A misplaced page that git does not track keeps its row and gets no `move:` id.

    arch: D15.27
    """
    root = tmp_path
    _init(root)
    _write(root, "README.md", "# Repo\n")
    _write(root, "HOWTO-run.md", "# Running\n")
    _write(root, "guide.md", "# Guide\n")
    _git(root, "add", "README.md", "guide.md")

    survey = _survey(root)
    assert "HOWTO-run.md" not in survey.tracked
    result = layout.locate(root, survey, None, [])

    assert [m.id for m in result.moves] == ["move:guide.md"]
    rows = {f.id: f for f in result.findings}
    assert "doc-misplaced:HOWTO-run.md" in rows
    assert "not tracked" in rows["doc-misplaced:HOWTO-run.md"].evidence
