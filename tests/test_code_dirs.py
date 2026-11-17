"""Tests for Markdown-as-code in the `doc-misplaced` row: code segments, agent front matter and `[layout] code_dirs`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from trueup import layout, survey as survey_mod
from trueup.config import Config, ConfigError, load, render


def _repo(root: Path, files: dict[str, str]) -> survey_mod.Survey:
    """Make a git repository that holds `files` and survey it.

    Args:
        root: The directory to use.
        files: Repo-relative path to text content.

    Returns:
        The survey of `root`.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return survey_mod.run(root)


def _flagged(root: Path, survey: survey_mod.Survey, cfg: Config | None) -> list[str]:
    """Give the paths of the `doc-misplaced` findings of one `locate` run.

    Args:
        root: The repository root.
        survey: The survey of `root`.
        cfg: The config to pass, or `None`.

    Returns:
        The finding paths, sorted.
    """
    result = layout.locate(root, survey, cfg, [])
    return sorted(finding.path for finding in result.findings)


def test_a_code_segment_takes_a_page_out_of_the_candidate_set() -> None:
    """A page under a Markdown-as-code directory is not a candidate; a file named like one is.

    arch: D13.1
    """
    for path in (
        "claude/agents/python-reviewer.md",
        "claude/skills/runner/build.md",
        "pi/prompts/design.md",
        "bench/rules/candidate.md",
        "core/skills/graphify/references/hooks.md",
        "repo/templates/page.md",
    ):
        assert layout._is_candidate(path, frozenset()) is False, path
    assert layout._is_candidate("misc/rules.md", frozenset()) is True
    assert layout._is_candidate("misc/page.md", frozenset()) is True


def test_extra_code_dirs_extend_the_default_list() -> None:
    """`code_dirs` adds segments to `CODE_SEGMENTS`; it does not replace them.

    arch: D13.1
    """
    dirs = layout.code_dirs(Config(layout_code_dirs=("blocks",)))
    assert layout._is_candidate("core/blocks/00.md", frozenset()) is True
    assert (
        layout._is_candidate("core/blocks/00.md", frozenset(), code_dirs=dirs) is False
    )
    assert (
        layout._is_candidate("claude/agents/x.md", frozenset(), code_dirs=dirs) is False
    )


def test_locate_skips_an_agent_definition_by_its_front_matter(tmp_path: Path) -> None:
    """A file whose front matter has `name` and `description` and no `type` is not a page.

    arch: D13.1
    """
    survey = _repo(
        tmp_path,
        {
            "bots/reviewer.md": "---\nname: reviewer\ndescription: Reviews code: all of it.\ntools:\n  - Read\n---\n\nBody.\n",
            "bots/typed.md": "---\nname: typed\ndescription: A page.\ntype: how-to\n---\n\nBody.\n",
            "bots/plain.md": "# Plain page\n",
        },
    )
    assert _flagged(tmp_path, survey, None) == ["bots/plain.md", "bots/typed.md"]


def test_locate_reads_layout_code_dirs_from_the_config(tmp_path: Path) -> None:
    """`locate` takes the extra segments from `cfg.layout_code_dirs`.

    arch: D13.1
    """
    survey = _repo(
        tmp_path, {"core/blocks/00.md": "# Block\n", "misc/page.md": "# Page\n"}
    )
    assert _flagged(tmp_path, survey, None) == ["core/blocks/00.md", "misc/page.md"]
    cfg = Config(layout_code_dirs=("blocks",))
    assert _flagged(tmp_path, survey, cfg) == ["misc/page.md"]


def test_layout_and_binary_tables_round_trip(tmp_path: Path) -> None:
    """`[layout] code_dirs` and `[binary] allow` load and render back to the same config.

    arch: D13.1, D13.2
    """
    cfg = Config(
        layout_code_dirs=("blocks", "_templates"), binary_allow=("shots/*.png",)
    )
    (tmp_path / "trueup.toml").write_text(render(cfg), encoding="utf-8")
    assert load(tmp_path) == cfg
    assert "[layout]" not in render(Config())
    assert "[binary]" not in render(Config())


@pytest.mark.parametrize(
    "text",
    [
        "version = 1\n[layout]\ndirs = []\n",
        'version = 1\n[layout]\ncode_dirs = ["a/b"]\n',
        "version = 1\n[binary]\ndeny = []\n",
        "version = 1\n[binary]\nallow = 3\n",
    ],
)
def test_layout_and_binary_tables_reject_bad_values(tmp_path: Path, text: str) -> None:
    """An unknown key, a path in `code_dirs` or a non-list `allow` fails to load.

    arch: D13.1, D13.2
    """
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load(tmp_path)
