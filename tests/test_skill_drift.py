"""Tests that `skills/trueup/SKILL.md` names only commands, flags, keys, templates and anchors that exist."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from trueup import cli, config, managed, ref_check
from trueup.rulesets import RULESETS

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILL = _REPO_ROOT / "skills" / "trueup" / "SKILL.md"
_REFERENCE = _REPO_ROOT / "docs" / "reference" / "trueup.md"

_FENCE = re.compile(r"^ *(```|~~~)")
_SPAN = re.compile(r"`([^`]+)`")
_LONG_FLAG = re.compile(r"^--[a-z][a-z0-9-]*")
_ARRAY_TABLE = re.compile(r"\[\[([a-z_][a-z0-9_.]*)\]\]")
_TABLE_KEY = re.compile(r"(?<!\[)\[([a-z_][a-z0-9_]*)\] ([a-z_][a-z0-9_]*)\b")
_BARE_KEY = re.compile(r"^([a-z_][a-z0-9_.]*) = ")
_TABLE_LINE = re.compile(r"^\[\[?([a-z_][a-z0-9_.]*)\]\]?$")
_REFERENCE_ANCHOR = re.compile(r"trueup\.md#([A-Za-z0-9_-]+)")
_LOCAL_ANCHOR = re.compile(r"\]\(#([A-Za-z0-9_-]+)\)")

_LAUNCHERS = ("trueup", "PLUGIN/trueup")
"""The words that start a trueup command: the console script, and the
launcher path of the skill once its quotes are stripped."""

_FOREIGN_FLAGS = frozenset(
    {
        "--suppress-all",
        "--suppressions-location",
        "--prune-suppressions",
        "--pass-on-unpruned-suppressions",
        "--all-files",
    }
)
"""Flags of other tools that the skill names in a code span of their own:
the four eslint bulk suppression options and `pre-commit run --all-files`."""

REQUIRED_KEYS: tuple[str, ...] = (
    "health.agents",
    "layout.docs_dir",
    "layout.front_matter",
    "layout.index",
    "layout.types",
    "prose.banned",
    "prose.extra",
    "refs.comments",
    "refs.links",
    "refs.registry",
    "root.base",
    "scratch.gitignore",
    "stale_days",
    "guard.registry",
    "health.files",
    "refs.declared",
    "refs.id_forms",
    "refs.accepted_reader_changes",
)
"""Keys that the skill must name (D15.36). The audit of 2026-11-02 found
fifteen keys that the skill did not name. These are the ones a person sets;
`version` and `run_date` are left out because trueup writes them. The list
adds `guard.registry` and `health.files` of round 15, and the three checker
reader keys of round 16."""


def _skill_text() -> str:
    """Read the skill file.

    Returns:
        The text of `skills/trueup/SKILL.md`.
    """
    return _SKILL.read_text(encoding="utf-8")


def _split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Separate the prose of a Markdown file from its fenced code lines.

    A line that ends in a backslash joins the next line, as in a shell.

    Args:
        text: The Markdown text.

    Returns:
        The prose with each fenced block removed, and one
        `(info string, logical line)` pair per line inside a fence.
    """
    prose: list[str] = []
    fenced: list[tuple[str, str]] = []
    info: str | None = None
    pending = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match:
            info = None if info is not None else line.strip()[3:].strip()
            continue
        if info is None:
            prose.append(line)
            continue
        stripped = line.strip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        fenced.append((info, pending + stripped))
        pending = ""
    return "\n".join(prose), fenced


def _spans(prose: str) -> list[str]:
    """Give each inline code span of the prose, with its white space folded.

    Args:
        prose: Markdown text with no fenced block.

    Returns:
        The text of each code span; a span that crosses a line break is one
        span.
    """
    return [" ".join(span.split()) for span in _SPAN.findall(prose)]


def _subparsers() -> dict:
    """Give the subcommand parsers of the trueup command line.

    Returns:
        A map from each subcommand name to its `argparse` parser.
    """
    parser = cli._build_parser()
    actions = [
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    ]
    return dict(actions[0].choices)


def _flags_of(sub: str) -> set[str]:
    """Give the flags that one subcommand accepts.

    Args:
        sub: A subcommand name of `_subparsers()`.

    Returns:
        Its option strings; for `refs`, the flags of `ref_check.REFS_FLAGS`,
        because `refs` hands its arguments to the checker unparsed.
    """
    if sub == "refs":
        return set(ref_check.REFS_FLAGS)
    return {
        opt for action in _subparsers()[sub]._actions for opt in action.option_strings
    }


def _positional_choices(sub: str) -> tuple[str, ...] | None:
    """Give the allowed words of the one positional argument of a subcommand.

    Args:
        sub: A subcommand name.

    Returns:
        `managed.TEMPLATE_NAMES` for `template`, the `choices` of the
        positional argument (the hook events for `hook`), or `None` when
        the subcommand takes free words.
    """
    if sub == "template":
        return managed.TEMPLATE_NAMES
    for action in _subparsers()[sub]._actions:
        if not action.option_strings and action.choices:
            return tuple(action.choices)
    return None


def _clean(token: str) -> str:
    """Strip quotes, brackets and trailing punctuation from one word.

    Args:
        token: A word of a code span or a code line.

    Returns:
        The word without the characters `'"[]()` and a trailing `,` or `;`.
    """
    return token.strip("'\"[]()").rstrip(",;")


def _is_placeholder(word: str) -> bool:
    """Tell whether a word stands for a value, not a literal name.

    Args:
        word: A cleaned word.

    Returns:
        True for `<name>`, `...` and an upper-case word such as `PATH`.
    """
    return word.startswith("<") or word == "..." or word.isupper()


def command_problems(chunk: str) -> tuple[list[str], int]:
    """Find each trueup command in one chunk of code, and each wrong name in it.

    A command starts at `trueup <sub>`, at `PLUGIN/trueup <sub>`, at
    `ref_check.py`, or at a subcommand word that starts the chunk. Its flags
    run up to the next command or the end of a shell segment. A word after
    `PLUGIN/trueup` that is not a subcommand or a placeholder is a problem.
    After a bare `trueup` it is a problem only when the chunk starts with
    `trueup`, so prose in a span (`trueup writes this file`) and an output
    line (`trueup lint: ...`) give none. A chunk that starts with a long
    flag names flags of any subcommand.

    Args:
        chunk: The text of one code span or one logical code line.

    Returns:
        The problems found, and the number of commands found.
    """
    tokens = [_clean(t) for t in chunk.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return [], 0
    subs = _subparsers()
    problems: list[str] = []
    if _LONG_FLAG.match(tokens[0]):
        known = set().union(*(_flags_of(s) for s in subs)) | _FOREIGN_FLAGS
        for token in tokens:
            flag = _LONG_FLAG.match(token)
            if flag and flag.group(0) not in known:
                problems.append(f"flag {flag.group(0)} in `{chunk}`")
        return problems, 0
    found = 0
    i = 0
    while i < len(tokens):
        word = tokens[i]
        sub: str | None = None
        start = i + 1
        if word in _LAUNCHERS and i + 1 < len(tokens):
            name = tokens[i + 1]
            if name in subs:
                sub, start = name, i + 2
            elif (word == "PLUGIN/trueup" or i == 0) and not (
                name.endswith(":") or _is_placeholder(name)
            ):
                problems.append(f"command {name} in `{chunk}`")
        elif word == "ref_check.py":
            sub = "refs"
        elif i == 0 and word in subs:
            sub = word
        if sub is None:
            i += 1
            continue
        found += 1
        flags = _flags_of(sub)
        choices = _positional_choices(sub)
        positional_seen = False
        j = start
        while j < len(tokens):
            token = tokens[j]
            if (
                token in _LAUNCHERS
                or token in ("|", "&&", ">", ";")
                or token.endswith(";")
            ):
                break
            flag = _LONG_FLAG.match(token)
            if flag:
                if flag.group(0) not in flags:
                    problems.append(f"flag {flag.group(0)} of {sub} in `{chunk}`")
            elif choices is not None and not positional_seen:
                positional_seen = True
                if not _is_placeholder(token) and token not in choices:
                    problems.append(f"{sub} name {token} in `{chunk}`")
            j += 1
        i = j
    return problems, found


def _key_names(text: str) -> list[str]:
    """Give each config key that the text names in a `[table] key` or `key =` form.

    Args:
        text: Markdown text.

    Returns:
        The dotted keys, in order. `[[x]]` gives `x`. A key under a table
        line of a fenced `toml` block gives `<table>.<key>`; a key under an
        `[[x]]` line is a field of the entry and gives nothing.
    """
    prose, fenced = _split(text)
    keys: list[str] = []
    for span in _spans(prose):
        keys += _ARRAY_TABLE.findall(span)
        keys += [f"{t}.{k}" for t, k in _TABLE_KEY.findall(span)]
        bare = _BARE_KEY.match(span)
        if bare:
            keys.append(bare.group(1))
    table: str | None = None
    array = False
    for info, line in fenced:
        if info != "toml":
            continue
        code = line.split("#", 1)[0].strip()
        header = _TABLE_LINE.match(code)
        if header:
            table, array = header.group(1), code.startswith("[[")
            if array:
                keys.append(table)
            continue
        bare = _BARE_KEY.match(code)
        if bare and not array:
            keys.append(f"{table}.{bare.group(1)}" if table else bare.group(1))
    return keys


def _checker_keys() -> set[str]:
    """Give the dotted keys of the checker config `ref_check.toml`.

    Returns:
        `<table>.<key>` for each key of `ref_check.CONFIG_SCHEMA`, for
        example `scan.ignore`, `checks.layout` and `keep.failures`.
    """
    return {f"{t}.{k}" for t, ks in ref_check.CONFIG_SCHEMA.items() if t for k in ks}


def _all_commands(text: str) -> tuple[list[str], int]:
    """Run `command_problems` on each code span and each fenced code line.

    Args:
        text: Markdown text.

    Returns:
        The problems of every chunk, and the number of commands found.
    """
    prose, fenced = _split(text)
    problems: list[str] = []
    found = 0
    for chunk in _spans(prose) + [line for _, line in fenced]:
        chunk_problems, count = command_problems(chunk)
        problems += chunk_problems
        found += count
    return problems, found


def test_skill_names_only_real_commands_and_flags() -> None:
    """Each trueup command, flag, hook event and template the skill names exists.

    The flags come from a walk of `cli._build_parser()`, and for `refs` from
    `ref_check.REFS_FLAGS`. The template names come from
    `managed.TEMPLATE_NAMES`.

    arch: D15.36
    """
    problems, found = _all_commands(_skill_text())
    assert found > 40, f"the scan found only {found} commands"
    assert problems == []


def test_skill_names_check_sarif() -> None:
    """The skill names `check --sarif`, a flag the audit found missing.

    arch: D15.36
    """
    prose, _ = _split(_skill_text())
    assert any(
        span.startswith("check ") and "--sarif" in span for span in _spans(prose)
    )


def test_skill_names_only_real_config_keys() -> None:
    """Each config key the skill names is in `config.KEYS` or is a checker key.

    arch: D15.36
    """
    keys = _key_names(_skill_text())
    assert len(keys) > 30, f"the scan found only {len(keys)} keys"
    unknown = sorted(
        {k for k in keys if k not in config.KEYS and k not in _checker_keys()}
    )
    assert unknown == []


def test_skill_names_the_required_keys() -> None:
    """The skill names each key of `REQUIRED_KEYS`, and each one is a real key.

    arch: D15.36
    """
    assert set(REQUIRED_KEYS) <= set(config.KEYS)
    named = set(_key_names(_skill_text()))
    assert sorted(set(REQUIRED_KEYS) - named) == []


def test_skill_anchors_resolve() -> None:
    """Each `trueup.md#anchor` resolves in the reference page, and each `#anchor` in the skill.

    arch: D15.36
    """
    text = _skill_text()
    reference_slugs = ref_check._heading_slugs(_REFERENCE.read_text(encoding="utf-8"))
    anchors = _REFERENCE_ANCHOR.findall(text)
    assert len(anchors) > 20, f"the scan found only {len(anchors)} anchors"
    assert sorted({a for a in anchors if a not in reference_slugs}) == []
    own_slugs = ref_check._heading_slugs(text)
    assert sorted({a for a in _LOCAL_ANCHOR.findall(text) if a not in own_slugs}) == []


def test_skill_names_the_cpy_ignore_of_the_strict_ruff_config() -> None:
    """The skill names `CPY`, and the strict ruff config ignores it with a reason.

    The config is the file of the strict Python rule set, as `trueup lint`
    renders it. The reason is a comment line that starts with `# CPY:`.

    arch: D15.36, D16.7
    """
    rule_set = RULESETS[("python", "strict")]
    text = managed.template_path(rule_set.files["python/ruff.toml"]).read_text(
        encoding="utf-8"
    )
    assert "CPY" in tomllib.loads(text)["lint"]["ignore"]
    reasons = [line for line in text.splitlines() if line.startswith("# CPY: ")]
    assert len(reasons) == 1
    assert len(reasons[0]) > len("# CPY: ")
    prose, _ = _split(_skill_text())
    assert "CPY" in _spans(prose)


def test_the_scan_finds_planted_drift() -> None:
    """A wrong command, flag, template, hook event and key in a sample are each found.

    arch: D15.36
    """
    sample = "\n".join(
        [
            "Run `trueup chek --root ROOT` and `check --root ROOT --sarifs x`.",
            'Run `python3 "PLUGIN/trueup" template pre-comit` and `hook start`.',
            "Run `refs --root . --fix` and `--all-autos`.",
            "Set `[layout] front_mater = false` and `publik = true`.",
            "```toml",
            "[guard]",
            "registri = true",
            "[[keep]]",
            'id = "x"',
            "```",
            "Output `trueup: x: not a git repository; trueup reads tracked files`.",
        ]
    )
    problems, _ = _all_commands(sample)
    assert problems == [
        "command chek in `trueup chek --root ROOT`",
        "flag --sarifs of check in `check --root ROOT --sarifs x`",
        'template name pre-comit in `python3 "PLUGIN/trueup" template pre-comit`',
        "hook name start in `hook start`",
        "flag --fix of refs in `refs --root . --fix`",
        "flag --all-autos in `--all-autos`",
    ]
    keys = _key_names(sample)
    assert [k for k in keys if k not in config.KEYS] == [
        "layout.front_mater",
        "publik",
        "guard.registri",
    ]
    assert "keep" in keys
