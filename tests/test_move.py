"""Tests for `trueup.apply`'s `move:` id handler: `git mv` and the link rewrite (arch: D10.7)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from trueup import apply as apply_mod
from trueup import layout
from trueup.findings import Finding


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one git command in a test repository, with a fixed signer.

    Args:
        root: The repository.
        *args: The git arguments after `git`.

    Returns:
        The completed process.
    """
    return subprocess.run(
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
        text=True,
    )


def _write(root: Path, rel: str, content: str) -> None:
    """Write one text file, creating its parent directories.

    Args:
        root: The repository root.
        rel: The repo-relative POSIX path to write.
        content: The text to write.
    """
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a one-commit git repository from a path-to-content map.

    Args:
        tmp_path: The pytest temporary directory.
        files: Repo-relative path to content.

    Returns:
        The repository root.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    for rel, content in files.items():
        _write(root, rel, content)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _apply(root: Path, *ids: str, all_auto: bool = False) -> int:
    """Run `apply` on a root with no `--mode`/`--set`.

    Args:
        root: The target root.
        *ids: The ids to pass to `--ids`, or none with `all_auto`.
        all_auto: Run `--all-auto` instead of `--ids`.

    Returns:
        The exit code.
    """
    return apply_mod.run(
        root,
        ids=list(ids) or None,
        all_auto=all_auto,
        mode_args=[],
        set_args=[],
    )


def test_move_rewrites_an_inbound_link_from_outside_the_move(tmp_path: Path) -> None:
    """A link from a file that does not move is rewritten to the new target.

    arch: D10.7, I-34
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n\nSee [notes](NOTES.md) for more.\n",
            "NOTES.md": "# Notes\n\ncontent\n",
            "LICENSE.md": "licence text\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    assert not (root / "NOTES.md").exists()
    assert (root / "docs" / "NOTES.md").is_file()
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "[notes](docs/NOTES.md)" in readme


def test_move_rewrites_an_outbound_link_from_the_moved_file(tmp_path: Path) -> None:
    """A link the moved file holds to a file outside the move is rewritten.

    arch: D10.7, I-34
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "NOTES.md": "# Notes\n\nSee [licence](LICENSE.md).\n",
            "LICENSE.md": "licence text\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    notes = (root / "docs" / "NOTES.md").read_text(encoding="utf-8")
    assert "[licence](../LICENSE.md)" in notes


def test_directory_move_keeps_its_inner_links_and_carries_a_non_markdown_file(
    tmp_path: Path,
) -> None:
    """A directory move's inner links still resolve, and its other file moves with it.

    arch: D10.7, D10.6

    The tree is committed at `docs/`, then renamed to `misc/` with one more
    commit, the way the D10.10 scramble operations build a misplaced
    fixture. History then gives `misc/data.json` (not a page) its own
    evidence to move back to `docs/data.json` with the directory, with no
    extra rule of its own (D10.6, units).
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "docs/a.md": "# A\n\nSee [b](b.md).\n",
            "docs/b.md": "# B\n\ncontent\n",
            "docs/data.json": '{"k": "v"}\n',
        },
    )
    _git(root, "mv", "docs", "misc")
    _git(root, "commit", "-q", "-m", "rename docs to misc")
    assert _apply(root, "move:misc/") == 0
    assert not (root / "misc").exists()
    assert (root / "docs" / "data.json").is_file()
    a_text = (root / "docs" / "a.md").read_text(encoding="utf-8")
    assert "[b](b.md)" in a_text


def test_a_protected_file_is_left_broken_and_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `protect`-matched file's link is never rewritten, and the move prints it as left broken.

    arch: D10.7, I-38
    """
    root = _repo(
        tmp_path,
        {
            "trueup.toml": 'version = 1\nprotect = ["LOCKED.md"]\n',
            "LOCKED.md": "# Locked\n\nSee [notes](NOTES.md).\n",
            "NOTES.md": "# Notes\n\ncontent\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    locked = (root / "LOCKED.md").read_text(encoding="utf-8")
    assert "[notes](NOTES.md)" in locked
    assert (root / "docs" / "NOTES.md").is_file()
    assert "left broken: LOCKED.md:3" in capsys.readouterr().out


def test_an_unknown_move_id_exits_two_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `move:` id not in the current move plan stops the run at exit 2 before any write.

    The id is checked against `run.moves`, so the message names the move
    plan, not the finding plan `_validate` checks other ids against.

    arch: D10.7
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "NOTES.md": "# Notes\n\ncontent\n",
        },
    )
    before = (root / "NOTES.md").read_bytes()
    out = _git(root, "status", "--porcelain").stdout
    assert _apply(root, "move:DOES-NOT-EXIST.md") == 2
    assert (root / "NOTES.md").read_bytes() == before
    assert not (root / "docs").exists()
    assert _git(root, "status", "--porcelain").stdout == out
    assert (
        "move:DOES-NOT-EXIST.md is not in the current move plan"
        in capsys.readouterr().out
    )


def test_move_rewrites_a_link_with_a_fragment_without_doubling_it(
    tmp_path: Path,
) -> None:
    """A link's fragment is kept once, not repeated, when its path is rewritten.

    arch: D10.7

    `_md_links` gives the written target (`NOTES.md#section`) and its
    decoded fragment apart. The rewrite must replace the whole target,
    path and fragment together, or the old fragment is left behind next
    to the one the rewrite writes back.
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n\nSee [notes](NOTES.md#section) for more.\n",
            "NOTES.md": "# Notes\n\n## Section\n\ncontent\n",
            "LICENSE.md": "licence text\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "[notes](docs/NOTES.md#section)" in readme
    assert "#section#section" not in readme


def test_move_rewrites_a_percent_encoded_link_target(tmp_path: Path) -> None:
    """A link target with a percent-escaped character still resolves and is rewritten.

    arch: D10.7

    D10.7 step 2 says the rewrite follows `ref_check._md_links`'s parsing
    rules, which decode the path part from percent escapes before it is
    resolved against a file on disk. A link to `MY%20NOTES.md` must
    resolve to the file `MY NOTES.md` the same way `ref_check` does, so
    the move does not leave it pointing at the old, now-moved, location.
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n\nSee [my notes](MY%20NOTES.md) for more.\n",
            "MY NOTES.md": "# My Notes\n\ncontent\n",
            "LICENSE.md": "licence text\n",
        },
    )
    assert _apply(root, "move:MY NOTES.md") == 0
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "[my notes](docs/MY%20NOTES.md)" in readme


def test_all_auto_never_moves_a_page(tmp_path: Path) -> None:
    """`--all-auto` never reads the move plan, so a misplaced page stays where it is.

    arch: D10.7, I-34
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "NOTES.md": "# Notes\n\ncontent\n",
        },
    )
    _apply(root, all_auto=True)
    assert (root / "NOTES.md").is_file()
    assert not (root / "docs" / "NOTES.md").exists()


def _readme_after_notes_move(tmp_path: Path, readme: str) -> str:
    """Move the root `NOTES.md` to `docs/NOTES.md` and give the new `README.md` text.

    Args:
        tmp_path: The pytest temporary directory.
        readme: The `README.md` content before the move.

    Returns:
        The `README.md` content after `apply --ids move:NOTES.md`.
    """
    root = _repo(
        tmp_path,
        {
            "README.md": readme,
            "NOTES.md": "# Notes\n\ncontent\n",
            "LICENSE.md": "licence text\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    return (root / "README.md").read_text(encoding="utf-8")


def test_move_rewrites_a_link_whose_text_equals_its_target(tmp_path: Path) -> None:
    """The rewrite changes the link destination, not the same words in the link text.

    arch: D10.7
    """
    readme = _readme_after_notes_move(
        tmp_path, "# Readme\n\nSee [NOTES.md](NOTES.md).\n"
    )
    assert "See [NOTES.md](docs/NOTES.md).\n" in readme


def test_move_rewrites_a_reference_definition_whose_label_equals_its_target(
    tmp_path: Path,
) -> None:
    """A reference definition gets its destination rewritten, and its label stays.

    arch: D10.7
    """
    readme = _readme_after_notes_move(
        tmp_path, "# Readme\n\nSee [NOTES.md].\n\n[NOTES.md]: NOTES.md\n"
    )
    assert "\n[NOTES.md]: docs/NOTES.md\n" in readme


def test_move_never_changes_a_broken_link_on_the_same_line(tmp_path: Path) -> None:
    """A link that was already broken stays as it is, also when its text holds the moved path.

    arch: D10.7
    """
    readme = _readme_after_notes_move(
        tmp_path, "# Readme\n\nSee [old](OLD-NOTES.md) and [notes](NOTES.md).\n"
    )
    assert "See [old](OLD-NOTES.md) and [notes](docs/NOTES.md).\n" in readme


def test_move_rewrites_two_equal_links_on_one_line_once_each(tmp_path: Path) -> None:
    """Two links with the same destination on one line are each rewritten one time.

    arch: D10.7
    """
    readme = _readme_after_notes_move(
        tmp_path, "# Readme\n\nSee [a](NOTES.md) and [b](NOTES.md).\n"
    )
    assert "See [a](docs/NOTES.md) and [b](docs/NOTES.md).\n" in readme


def test_move_never_changes_a_code_span_before_the_link(tmp_path: Path) -> None:
    """A code span that holds the moved path is not a link, so the rewrite leaves it.

    arch: D10.7
    """
    readme = _readme_after_notes_move(
        tmp_path, "# Readme\n\nThe file `NOTES.md` is [here](NOTES.md).\n"
    )
    assert "The file `NOTES.md` is [here](docs/NOTES.md).\n" in readme


def test_directory_move_keeps_link_forms_that_need_no_change(tmp_path: Path) -> None:
    """An inner `./` link stays as written, and a directory link keeps its trailing `/`.

    arch: D10.7, D10.6
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n\nSee [the docs](docs/).\n",
            "docs/a.md": "# A\n\nSee [b](./b.md).\n",
            "docs/b.md": "# B\n\ncontent\n",
        },
    )
    _git(root, "mv", "docs", "misc")
    _git(root, "commit", "-q", "-m", "rename docs to misc")
    _write(root, "README.md", "# Readme\n\nSee [the docs](misc/).\n")
    _git(root, "commit", "-q", "-am", "follow the rename")
    assert _apply(root, "move:misc/") == 0
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "See [the docs](docs/).\n" in readme
    a_text = (root / "docs" / "a.md").read_text(encoding="utf-8")
    assert "See [b](./b.md).\n" in a_text


# ---------------------------------------------------------------------------
# Unquoted git paths, `.markdown` readers, canonical links, code mentions
# ---------------------------------------------------------------------------


def _quoting_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a one-commit repository that quotes non-ASCII paths in git output.

    Args:
        tmp_path: The pytest temporary directory.
        files: Repo-relative path to content.

    Returns:
        The repository root, with `core.quotePath` set to true.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "core.quotePath", "true")
    for rel, content in files.items():
        _write(root, rel, content)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_move_rewrites_a_link_in_a_non_ascii_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-ASCII page that links the moved file is read and rewritten.

    arch: D10.7, D10.6

    `git ls-files` and `git grep` quote a non-ASCII path when
    `core.quotePath` is true. The quoted name does not end in `.md`, so
    the page is not read, and `git grep` prints it as a code mention.
    """
    root = _quoting_repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "Übersicht.md": "# Übersicht\n\nSee [notes](NOTES.md).\n",
            "NOTES.md": "# Notes\n\ncontent\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    page = (root / "Übersicht.md").read_text(encoding="utf-8")
    assert "See [notes](docs/NOTES.md).\n" in page
    assert "code mentions" not in capsys.readouterr().out


def test_untrack_keeps_a_directory_with_a_protected_non_ascii_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An artifact directory that holds a protected non-ASCII file is skipped.

    arch: D10.7, D10.6, I-24

    The protect check lists the directory with `git ls-files`. A quoted
    name does not match the `protect` glob, so the directory was untracked.
    """
    root = _quoting_repo(
        tmp_path,
        {
            "dist/app.js": "console.log(1);\n",
            "dist/Änderung.lock": "keep\n",
        },
    )
    ctx = apply_mod._Context(root=root, protect=("dist/Änderung.lock",), rendered={})
    finding = Finding(
        id="artifact:dist/",
        rule="artifact",
        category="hygiene",
        severity="warn",
        path="dist/",
        evidence="a build directory",
        action="untrack it",
        auto=True,
    )
    apply_mod._handle_untrack(ctx, finding)
    assert "skip dist/: holds a protected file" in capsys.readouterr().out
    assert _git(root, "ls-files", "--", "dist/app.js").stdout.strip() == "dist/app.js"


def test_move_rewrites_a_link_in_a_markdown_suffix_page(tmp_path: Path) -> None:
    """A `.markdown` page that links the moved file is rewritten too.

    arch: D10.7
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "GUIDE.markdown": "# Guide\n\nSee [notes](NOTES.md).\n",
            "NOTES.md": "# Notes\n\ncontent\n",
        },
    )
    assert _apply(root, "move:NOTES.md") == 0
    guide = (root / "GUIDE.markdown").read_text(encoding="utf-8")
    assert "See [notes](docs/NOTES.md).\n" in guide


def _move(root: Path, source: str, target: str) -> layout.Move:
    """Carry out one move on a test repository with `_move_one`.

    Args:
        root: The repository root.
        source: The move's source; it ends in `/` for a directory.
        target: The move's target; it ends in `/` for a directory.

    Returns:
        The move that ran.
    """
    kind = "dir" if source.endswith("/") else "file"
    move = layout.Move(
        id=f"move:{source}",
        source=source,
        target=target,
        kind=kind,
        basis="history",
        evidence="a test move",
        pages=(),
    )
    ctx = apply_mod._Context(root=root, protect=(), rendered={})
    apply_mod._move_one(ctx, move)
    return move


def test_moved_file_links_take_the_canonical_form(tmp_path: Path) -> None:
    """Two moves that undo a scramble give back the tidy text byte for byte.

    arch: D10.7, I-37

    The first move rewrites the link in `misc/design/a.md` to
    `../../docs/ARCHITECTURE.md`. That form still resolves after the
    second move, but a moved file's link takes the one canonical form,
    `../ARCHITECTURE.md`. A `./b.md` link stays as written.
    """
    tidy = "# A\n\nSee [the design](../ARCHITECTURE.md) and [b](./b.md).\n"
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "misc/ARCHITECTURE.md": "# Architecture\n",
            "misc/design/a.md": tidy,
            "misc/design/b.md": "# B\n",
        },
    )
    _move(root, "misc/ARCHITECTURE.md", "docs/ARCHITECTURE.md")
    _move(root, "misc/design/", "docs/design/")
    assert (root / "docs" / "design" / "a.md").read_bytes() == tidy.encode("utf-8")


def test_unmoved_file_keeps_a_link_that_still_resolves(tmp_path: Path) -> None:
    """A file that does not move keeps a link form that still resolves.

    arch: D10.7, I-37
    """
    text = "# Readme\n\nSee [b](docs/sub/../b.md).\n"
    root = _repo(
        tmp_path,
        {
            "README.md": text,
            "docs/b.md": "# B\n",
            "docs/sub/c.md": "# C\n",
            "misc/x.md": "# X\n",
        },
    )
    _move(root, "misc/x.md", "docs/x.md")
    assert (root / "README.md").read_text(encoding="utf-8") == text


def test_directory_move_code_mentions_need_the_trailing_slash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory move greps `<source>/`, so the bare word in code is no mention.

    arch: D10.7
    """
    root = _repo(
        tmp_path,
        {
            "README.md": "# Readme\n",
            "misc/a.md": "# A\n",
            "tool.py": "misc = 1\nPATH = 'misc/a.md'\n",
        },
    )
    _move(root, "misc/", "docs/")
    out = capsys.readouterr().out
    assert "tool.py:1" not in out
    assert "code mentions misc/: tool.py:2" in out


def test_rewrite_links_leaves_a_link_that_was_already_broken(tmp_path: Path) -> None:
    """A link whose target did not exist before the move is left as it is.

    arch: D10.7

    `_rewrite_links` reads the tree before `git mv` runs. The move here
    is a directory move whose mapper sends every path under `notes/` to
    a path under `stuff/`. If the early branch were missing, a link to
    `notes/MISSING.md` would be mapped and rewritten to
    `stuff/MISSING.md` even though that target never existed; the test
    would then fail. Because the target was never on disk, the function
    takes the early branch and gives back the text unchanged, with no
    broken-line number.
    """
    root = _repo(tmp_path, {"README.md": "# Readme\n", "notes/kept.md": "content\n"})
    text = "# Readme\n\nSee [missing](notes/MISSING.md) for more.\n"
    mapper = apply_mod._move_mapper(
        layout.Move(
            id="move:notes/",
            source="notes/",
            target="stuff/",
            kind="dir",
            basis="history",
            evidence="a test move",
            pages=(),
        )
    )
    rewritten, breaks = apply_mod._rewrite_links(
        root, "README.md", "README.md", text, mapper
    )
    assert rewritten == text
    assert breaks == []


def test_move_mapper_directory_prefix_does_not_match_a_sibling_file(
    tmp_path: Path,
) -> None:
    """A directory move's mapper matches the directory and its contents, not a sibling.

    arch: D10.7

    `misc/` and `miscellany.md` share the letters `misc`, but the mapper's
    prefix is `misc/`: `miscellany.md` does not start with it, so the
    mapper leaves that sibling path unchanged.
    """
    move = layout.Move(
        id="move:misc/",
        source="misc/",
        target="docs/",
        kind="dir",
        basis="history",
        evidence="a test move",
        pages=(),
    )
    mapper = apply_mod._move_mapper(move)
    assert mapper("misc/") == "docs/"
    assert mapper("misc/a.md") == "docs/a.md"
    assert mapper("miscellany.md") == "miscellany.md"


# -- D15.27: a move writes only below the root --------------------------------


def test_move_to_a_target_outside_the_root_is_refused_before_any_mkdir(
    tmp_path: Path,
) -> None:
    """A crafted target that leaves the root is refused, and no directory is made outside.

    arch: D15.27
    """
    root = _repo(tmp_path, {"README.md": "# Readme\n", "guide.md": "# Guide\n"})
    with pytest.raises(apply_mod.WriteRefused):
        _move(root, "guide.md", "../escape-dir/sub/guide.md")
    assert not (tmp_path / "escape-dir").exists()
    assert (root / "guide.md").is_file()


def test_failed_git_mv_leaves_no_new_directory(tmp_path: Path) -> None:
    """When `git mv` fails, the directories made for its target are removed again.

    arch: D15.27
    """
    root = _repo(tmp_path, {"README.md": "# Readme\n"})
    _write(root, "loose.md", "# Not tracked\n")
    with pytest.raises(RuntimeError):
        _move(root, "loose.md", "docs/new/loose.md")
    assert not (root / "docs").exists()
    assert (root / "loose.md").is_file()


def test_move_never_rewrites_a_link_through_a_symlink_out_of_the_root(
    tmp_path: Path,
) -> None:
    """A tracked Markdown symlink to a file outside the root is not written by the link rewrite.

    arch: D15.27
    """
    outside = tmp_path / "outside.md"
    outside.write_text("See [notes](NOTES.md).\n", encoding="utf-8")
    root = _repo(tmp_path, {"README.md": "# Readme\n", "NOTES.md": "# Notes\n"})
    (root / "pointer.md").symlink_to(outside)
    _git(root, "add", "pointer.md")
    _git(root, "commit", "-q", "-m", "pointer")
    with pytest.raises(apply_mod.WriteRefused):
        _move(root, "NOTES.md", "docs/NOTES.md")
    assert outside.read_text(encoding="utf-8") == "See [notes](NOTES.md).\n"
    assert (root / "NOTES.md").is_file()
    assert not (root / "docs").exists()
