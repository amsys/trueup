"""Shared pytest helpers for the lint fixture tests, and the user directory and git isolation of every test."""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from trueup import config

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_user_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Keep each test away from the real user config and cache (D14.15).

    The fixture points `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` at
    directories under `tmp_path`, removes `TRUEUP_PROFILE`, and clears the
    config cache before and after the test. So no test reads a profile or
    a user default file of the person who runs the suite. The fixture does
    not make the two directories.

    `uvx` also reads `XDG_CACHE_HOME`. When `UV_CACHE_DIR` is not set, the
    fixture sets it to the real uv cache, so the offline rule-set tests
    keep their cached tools (D14.23 item 2). The cache of trueup itself
    stays under `tmp_path`.

    Args:
        tmp_path: The pytest temporary directory of the test.
        monkeypatch: The pytest fixture that restores the environment.

    Yields:
        Nothing. The test runs at the yield.
    """
    if not os.environ.get("UV_CACHE_DIR"):
        real_cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        monkeypatch.setenv("UV_CACHE_DIR", str(Path(real_cache) / "uv"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.delenv("TRUEUP_PROFILE", raising=False)
    config.clear_cache()
    yield
    config.clear_cache()


_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "trueup tests",
    "GIT_AUTHOR_EMAIL": "tests@trueup.invalid",
    "GIT_COMMITTER_NAME": "trueup tests",
    "GIT_COMMITTER_EMAIL": "tests@trueup.invalid",
}
"""The identity of each commit that a test makes."""


@pytest.fixture(autouse=True)
def _git_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each test a git identity, and stop git's background maintenance.

    A CI runner has no `user.name`, so a `git commit` of a test would
    fail there. `maintenance.auto` and `gc.auto` are off because a commit
    can start a detached maintenance run: its `maintenance.lock` appears
    and goes while a test compares the files under `.git/objects`. A
    variable that the environment already sets stays as it is.

    Args:
        monkeypatch: The pytest fixture that restores the environment.
    """
    for name, value in _GIT_IDENTITY.items():
        if not os.environ.get(name):
            monkeypatch.setenv(name, value)
    if not os.environ.get("GIT_CONFIG_COUNT"):
        monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "maintenance.auto")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
        monkeypatch.setenv("GIT_CONFIG_KEY_1", "gc.auto")
        monkeypatch.setenv("GIT_CONFIG_VALUE_1", "0")


def materialise(case: str, dest: Path) -> Path:
    """Copy a fixture tree to a temporary directory, ready to run the checker on.

    The tree lives at `tests/fixtures/<case>/`. Each file there ends in
    `.txt`. This helper copies the tree to `dest` and drops that suffix from
    every copied file, so the result is a small repository the checker can
    read (D1.6).

    Args:
        case: The name of the directory under `tests/fixtures/`.
        dest: The directory to copy the tree into.

    Returns:
        The path to the materialised tree, which is `dest`.
    """
    source = FIXTURES_ROOT / case
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if path.is_dir():
            (dest / relative).mkdir(parents=True, exist_ok=True)
            continue
        target_name = relative.name
        if target_name.endswith(".txt"):
            target_name = target_name[: -len(".txt")]
        target = dest / relative.parent / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return dest


def quoted_list_shapes() -> list[tuple[str, str, set[int]]]:
    """Give the Markdown block shapes of D8.4, filled with real banned words.

    Each entry is a name, a page text, and the set of line numbers that
    must give a banned-word hit. `tests/test_docrules.py` runs them through
    `check`'s `prose` row and `tests/test_rulesets.py` through a real `vale`
    run, so the two engines are proven on one table (D8.4). The words come
    from `trueup/data/banned.txt` at run time, so this file holds none.

    Returns:
        The shapes, in table order.
    """
    from trueup import docrules

    words = docrules._load_banned_words()
    quoted, quoted_two, real = words[0], words[1], words[2]
    table: list[tuple[str, str, set[int]]] = [
        ("nested sub-items", "- Never use these words:\n  - {q}\n  - {q2}\n", set()),
        ("cue on a continuation line", "- These words are\n  banned: {q}\n", set()),
        (
            "cue on paragraph line 2",
            "Write {q} never. These words are\nbanned here.\n",
            set(),
        ),
        ("heading, blank, paragraph", "## Forbidden zone\n\nWe {r} the cache\n", {3}),
        ("heading then paragraph", "## Forbidden zone\nWe {r} the cache\n", {2}),
        (
            "loose numbered item",
            "7. Banned vocabulary. Never use these:\n\n   {q}, {q2}\n\n   Say the plain thing: not {q}.\n",
            set(),
        ),
        (
            "lead-in paragraph and bullets",
            "Never use these words:\n- {q}\n- {q2}\n",
            set(),
        ),
        (
            "real item after a cue item",
            "- Never use: {q}\n- This design is {r}.\n",
            {2},
        ),
        (
            "cue paragraph, blank, real paragraph",
            "Never use {q}.\n\nThis is {r} prose.\n",
            {3},
        ),
        ("emphasis start", "**Note.** Never use {q} here.\n", set()),
        ("table row", "| banned | {q} |\n|---|---|\n", {1}),
        ("block quote", "> Never use {q}\n", {1}),
        ("lazy line after a cue item", "- Never use: {q}\nthis is {r} prose\n", {2}),
        ("digit-start continuation", "These words are banned:\n2026 {q}\n", set()),
        ("real use before a cue line", "This is {r} prose.\nNever use {q}.\n", set()),
        ("nested real use under a plain item", "- Intro\n  - This is {r}\n", {2}),
        ("cue item, blank, real paragraph", "- Never use: {q}\n\nThis is {r}.\n", {3}),
        (
            "indented line after a cue paragraph",
            "Never use these words:\n  {q} and {q2}\n",
            set(),
        ),
        (
            "numbered list after a cue paragraph",
            "Never use these words:\n1. {q}\n2. {q2}\n",
            set(),
        ),
        (
            "cue beyond the third line",
            "A {q} line.\nTwo.\nThree.\nNever use it.\n",
            {1},
        ),
        (
            "cue on the third line of an item",
            "- First\n  second\n  banned: {q}\n",
            set(),
        ),
    ]
    return [
        (name, text.format(q=quoted, q2=quoted_two, r=real), fires)
        for name, text, fires in table
    ]
