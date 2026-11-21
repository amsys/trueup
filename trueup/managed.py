"""Render the files trueup manages, and compare the target with them (arch: D5.6, D14.8).

`render` maps each managed repo path to the text trueup would write there,
from the config and the survey. The set is `trueup.toml` and, in copy
mode, the checker pair `ref_check.py` and `ref_check.toml` (D14.8).
`setup_findings` compares that map with the files on disk and returns the
`setup` findings of D5.4: a missing or changed managed file, a config gap,
a missing `.gitignore` line, a file of the old managed lint tree
(`managed-legacy`, info), and a tool that an enabled rule set or the Vale
style needs but the path does not hold. `template_text` gives the text
that `trueup template` prints: the one-hook pre-commit snippet, the CI
workflow, `.editorconfig` and the health pages, with no trueup header
line (D14.9). The gitleaks config renderer stays here for `check` and
`trueup lint` (D14.6, D14.22).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
from dataclasses import replace
from pathlib import Path

from trueup import config as config_mod
from trueup import fsread
from trueup.config import LANGUAGES, Config
from trueup.findings import Finding
from trueup.rulesets import (
    ESLINT_CONFIG_TARGET,
    ESLINT_PACKAGE_TARGET,
    JSCPD_HOOK,
    MANAGED_HEADER,
    RULESETS,
    VALE_FILES,
    VALE_HOOK,
    Hook,
    RuleSet,
    render_eslint_package,
    template_path,
)
from trueup.survey import Survey, _glob_to_regex

_TEXT_READ_CAP = 1024 * 1024
"""The longest managed file, in bytes, that a check reads (D16.10, I-50).
`docrules` imports this module, so the cap cannot come from there."""

BUNDLED_REF_CHECK: Path = Path(__file__).resolve().parent / "ref_check.py"
"""The checker that ships inside `trueup/` (D5.10); copied byte for byte in copy mode (I-26, D9.1)."""

PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent
"""The plugin root, the directory `uv tool install --editable` takes to put `trueup` on the path (D9.1)."""

STALE_COPY_PATH = "ref_check.py"
"""Where an earlier trueup left the checker copy; in global mode a file there is the `refs-copy` info finding (D9.1)."""

CONFIG_PATH = "trueup.toml"
REF_CHECK_CONFIG_PATH = "ref_check.toml"
PRE_COMMIT_PATH = ".pre-commit-config.yaml"
CI_PATH = ".github/workflows/trueup.yml"
EDITORCONFIG_PATH = ".editorconfig"
JSCPD_PATH = "lint/jscpd.json"
GITLEAKS_CONFIG_PATH = "lint/gitleaks/gitleaks.toml"
AGENT_RULES_PATH = ".claude/rules/trueup.md"
"""The agent rules file of D12.7; its minimum tier is in `_min_tier` (D12.9)."""
ESLINT_PACKAGES_DIR = "lint/typescript/node_modules"
"""Where an earlier trueup told the person to install the eslint packages (D8.3).
A `managed.LEGACY_PATHS` entry now: `trueup lint --install` installs them
in `eslint_dir`, outside the target (D14.7)."""

GITIGNORE_LINES: tuple[str, ...] = (".scratch/",)
"""The lines trueup needs in the target's `.gitignore` (D5.6): the scratch directory."""

LEGACY_PATHS: tuple[str, ...] = (
    PRE_COMMIT_PATH,
    CI_PATH,
    EDITORCONFIG_PATH,
    JSCPD_PATH,
    GITLEAKS_CONFIG_PATH,
    AGENT_RULES_PATH,
    ESLINT_CONFIG_TARGET,
    ESLINT_PACKAGE_TARGET,
    ESLINT_PACKAGES_DIR,
    *VALE_FILES,
)
"""The paths an earlier trueup managed and this one does not (D14.8).

Only the `managed-legacy` info row reads them. The names of the
constants stay importable: `hygiene` reads `rulesets.ESLINT_PACKAGE_TARGET`
for the D8.3 lockfile exemption (D14.22 item 10)."""

_LEGACY_DIR = "lint/"
"""The directory of the old managed lint tree; a trueup file under it is legacy (D14.8)."""

_LEGACY_ACTION = (
    "trueup no longer manages this file; remove it when you have moved to "
    "trueup lint (see the reference page)"
)
"""The action text of the `managed-legacy` row (D14.8)."""

_JSON_MANAGED_KEY = "_managed"
_JSON_MANAGED_VALUE = "trueup"
"""LOW-2: the key and value a header-less managed JSON file carries, so
`_is_managed_json` can tell trueup's own file from one the target already
had. For one version, a file without the key is also managed when it has
the old form that `_OLD_FORM_FREE_KEYS` describes (D6.15)."""

_OLD_FORM_FREE_KEYS: dict[str, frozenset[str]] = {
    JSCPD_PATH: frozenset({"format"}),
    ESLINT_PACKAGE_TARGET: frozenset({"devDependencies"}),
}
"""LOW-2, one version only: the keys of a managed JSON file whose value can
differ between the old form that trueup wrote before the marker and the
form `render` builds today. The strict languages set the jscpd `format`
list, and a trueup release can change the eslint `devDependencies`. An
old-form file has the same keys as today's form, and the same value for
each key not in this set."""

_PRE_COMMIT_SNIPPET = """repos:
  - repo: local
    hooks:
      - id: trueup-lint
        name: trueup lint
        entry: trueup lint
        language: system
        pass_filenames: true
        require_serial: true
"""
"""The `.pre-commit-config.yaml` text of `trueup template pre-commit`: one hook that runs `trueup lint` (D14.9)."""

_HEALTH_TEMPLATES: dict[str, str] = {
    "contributing": "health/CONTRIBUTING.md",
    "security": "health/SECURITY.md",
    "code-of-conduct": "health/CODE_OF_CONDUCT.md",
    "changelog": "health/CHANGELOG.md",
    "issue-template": "health/ISSUE_TEMPLATE.md",
    "pr-template": "health/PULL_REQUEST_TEMPLATE.md",
}
"""The health page names of `trueup template`, each to its template path (D14.9)."""

TEMPLATE_NAMES: tuple[str, ...] = (
    "pre-commit",
    "editorconfig",
    "ci",
    *_HEALTH_TEMPLATES,
)
"""The names that `trueup template <name>` accepts, in the order it lists them (D14.9)."""

_HEALTH_SKELETON_PREFIX = "<!-- trueup health skeleton:"
"""The start of the first line of each health template; `template_text` drops that line (D14.9)."""

_REF_CHECK_SWITCHES: tuple[str, ...] = (
    "registry",
    "comments",
    "links",
    "layout",
    "readme",
)
"""The `[checks]` keys of ref_check's own config schema, in the order it lists them."""

_DEFAULT_LAYOUT_TABLE: dict[str, str] = {
    "docs_dir": '"docs"',
    "front_matter": "true",
    "types": "true",
    "index": "true",
}
"""The `[layout]` values of the checker when its config has no `[layout]` table (D14.5)."""


_TIER_RANK: dict[str, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
"""The tiers in order, for the minimum-tier test of the managed set (D12.9)."""


def refcheck_switches_on(cfg: Config, survey: Survey) -> bool:
    """Say whether the checker gets its rendered config (D14.5, D16.2, D16.13).

    The callers `check`, `lint` and `refs` give an empty config when this
    is false. A set reader key needs the rendered `[targets.arch]` table
    at each tier, and a set `[refs] law_archive` needs the rendered
    `[targets.law]` table at each tier, so each makes this true. The
    `[checks]` switches follow `_tier_switches_on` only.

    Args:
        cfg: The config of the target.
        survey: The survey of the target.

    Returns:
        True when `[refs] declared`, `id_forms` or `law_archive` is set,
        or when `_tier_switches_on` is true. Else False.
    """
    return _target_is_configured(cfg) or _tier_switches_on(cfg, survey)


def _target_is_configured(cfg: Config) -> bool:
    """Say whether a key that the checker needs at each tier is set (D16.2, D16.13).

    Args:
        cfg: The config of the target.

    Returns:
        True when `_reader_is_configured` is true or `refs_law_archive`
        is set.
    """
    return _reader_is_configured(cfg) or cfg.refs_law_archive is not None


def _reader_is_configured(cfg: Config) -> bool:
    """Say whether a key of the configured reader is set (D16.2).

    Args:
        cfg: The config of the target.

    Returns:
        True when `refs_declared`, `refs_id_forms` or
        `refs_accepted_reader_changes` is not empty (D16.3).
    """
    return bool(
        cfg.refs_declared or cfg.refs_id_forms or cfg.refs_accepted_reader_changes
    )


def _tier_switches_on(cfg: Config, survey: Survey) -> bool:
    """Say whether the checker's switches are on for one target (D14.5, D14.22 item 12).

    Args:
        cfg: The config whose `layout_docs_dir` names the docs directory.
        survey: The survey of the target; its tier and files decide.

    Returns:
        True at T2 and T3. At T1, True when `survey.files` holds a
        Markdown page (`.md` or `.markdown`) at any depth under the docs
        directory. Else False.
    """
    if survey.tier in ("T2", "T3"):
        return True
    if survey.tier != "T1":
        return False
    prefix = f"{cfg.layout_docs_dir}/"
    return any(
        name.startswith(prefix) and name.endswith((".md", ".markdown"))
        for name in survey.files
    )


def _min_tier(path: str, cfg: Config, survey: Survey) -> str:
    """Give the lowest tier whose managed set holds `path` (D12.9, D14.8).

    Args:
        path: A repo path of the full rendered map.
        cfg: The config the map was rendered from.
        survey: The survey of the target.

    Returns:
        `"T0"` for the copy-mode checker; for `ref_check.toml`, `"T0"`
        when a reader key or the law archive is set, so the file comes
        with the checker (D16.2, D16.13), `"T1"` when `refcheck_switches_on` is true, else `"T2"`,
        so the file comes at the same tier as its switches; `"T1"` for
        `trueup.toml`.
    """
    if cfg.refs_mode == "copy" and path == cfg.refs_path:
        return "T0"
    if path == REF_CHECK_CONFIG_PATH and _target_is_configured(cfg):
        return "T0"
    if path == REF_CHECK_CONFIG_PATH and not refcheck_switches_on(cfg, survey):
        return "T2"
    return "T1"


def _on_disk_stays(root: Path, path: str, content: str) -> bool:
    """Say whether a path below its minimum tier stays in the set by its file on disk (D12.9).

    Args:
        root: The target root.
        path: The managed repo path.
        content: The text `render` builds for `path`.

    Returns:
        For `trueup.toml`, True when the file exists. For another path,
        True when the file exists and `_is_managed_on_disk` says it is
        trueup's. A file that is not trueup's gives False, so no finding
        asks to change or remove it (I-42).
    """
    full = root / path
    if path == CONFIG_PATH:
        return os.path.exists(full)
    if not os.path.isfile(full):
        return False
    raw = fsread.read_capped(root, path, _TEXT_READ_CAP)
    if raw is None:
        return False
    return _is_managed_on_disk(path, raw.decode("utf-8", errors="replace"), content)


def effective_config(cfg: Config | None, survey: Survey) -> Config:
    """Give the config that `apply` would write: the loaded one plus default modes.

    A language the survey marks present and the config does not name gets
    `clean`, the default the `config:languages.<lang>` finding applies.

    Args:
        cfg: The loaded `trueup.toml`, or `None` when it is absent.
        survey: The survey of the target.

    Returns:
        The config with a mode for every present language.
    """
    base = cfg if cfg is not None else Config()
    languages = dict(base.languages)
    for language in LANGUAGES:
        if survey.languages[language].present and language not in languages:
            languages[language] = "clean"
    return replace(base, languages=languages)


def enabled_rulesets(cfg: Config) -> list[RuleSet]:
    """List the rule sets that the config turns on, in `LANGUAGES` order.

    Args:
        cfg: The config whose `[languages]` table decides.

    Returns:
        One `RuleSet` per language whose mode is `strict` or `clean`.
    """
    return [
        RULESETS[(language, cfg.languages[language])]
        for language in LANGUAGES
        if cfg.languages.get(language, "off") != "off"
    ]


def _vale_enabled(cfg: Config) -> bool:
    """Say whether the Vale style is rendered: only when `docs` is `full` (D5.6).

    Args:
        cfg: The config to read.

    Returns:
        True when `cfg.docs` is `"full"`.
    """
    return cfg.docs == "full"


def render(cfg: Config, survey: Survey) -> dict[str, str]:
    """Render the managed set of one config and survey (D5.6, D12.9, D14.8).

    The set is `trueup.toml` and, in copy mode, the checker pair. A path
    is in it when `survey.tier` is at or above the path's minimum tier
    (`_min_tier`), or when its file on disk is trueup's (`_on_disk_stays`),
    so no finding asks to add a path above the tier or to remove a managed
    file (I-42). `ref_check.toml` comes from the config with `docs`
    resolved by `config.resolve_docs`; `trueup.toml` keeps the stored
    value.

    Args:
        cfg: The config to render from. Pass `effective_config(...)` to get
            the files that a first `apply` writes.
        survey: The survey of the target; its tier decides the set.

    Returns:
        Repo path to file text, sorted by path. `trueup.toml` is the text
        of `trueup.config.render(cfg)`. In copy mode (D9.1) `cfg.refs_path`
        (default `"ref_check.py"`) is the bundled copy's exact text, whose
        first line is the managed header (D9.3), and `ref_check.toml` is
        the text of `render_ref_check_config`.
    """
    resolved = replace(cfg, docs=config_mod.resolve_docs(cfg, survey.tier))
    full = {CONFIG_PATH: config_mod.render(cfg)}
    if cfg.refs_mode == "copy":
        full[cfg.refs_path] = BUNDLED_REF_CHECK.read_bytes().decode("utf-8")
        full[REF_CHECK_CONFIG_PATH] = render_ref_check_config(cfg, survey)
    rank = _TIER_RANK.get(survey.tier, 0)
    files = {
        path: text
        for path, text in full.items()
        if rank >= _TIER_RANK[_min_tier(path, resolved, survey)]
        or _on_disk_stays(survey.root, path, text)
    }
    return dict(sorted(files.items()))


def render_ref_check_config(cfg: Config, survey: Survey, keep: bool = True) -> str:
    """Render `ref_check.toml` from the effective config and the survey (D14.5, D14.22 item 3).

    `check` runs the bundled checker with this text, through a file outside
    the target, so its `refcheck` row equals the row after `apply` (D8.1).
    `trueup lint` and, in global mode, `trueup refs` run it with this text
    too (D14.5). Each `[checks]` switch is off when
    `_tier_switches_on(cfg, survey)` is false. `registry`, `comments`
    and `links` follow `[refs] registry`, `comments` and `links`. `layout`
    is on only for `docs = "full"`, `[refs] layout` true and one of the
    three `[layout]` rules on. `readme` is on only for `docs = "full"`.
    The `[layout] index` switch turns off the index rules of the checker
    (`unindexed`, `no-index-link`) through the `[layout]` table, not the
    whole README check (D14.2).

    Args:
        cfg: The effective config. Its `docs` value, resolved for the
            survey tier, its `refs_*` and `layout_*` values decide the
            switches and the `[layout]` table; its `refs_local_tags` fill
            the `[registry]` table (D8.7), its kept `refcheck:` ids fill
            the `[keep]` table (D9.2), and its `ignore` globs fill the
            `[scan]` table (I-2).
        survey: The survey of the target; its tier and files decide
            `_tier_switches_on` and the docs mode.
        keep: Whether to write the `[keep]` table. `render` writes it, so
            the hook honours the kept findings; `check` leaves it out and
            applies `[[keep]]` itself, so the report still lists them.
            The `[scan]` table does not follow `keep`: `check` and the hook
            skip the same paths.

    Returns:
        The file text, with the managed header, a `[checks]` table, a
        `licence = false` in `[checks]` when the target file sets
        `public = false` (D15.14), a
        `[layout]` table with all four keys when one of them is not its
        default, a `[registry]` table when `refs_local_tags` is not empty,
        a `[targets.arch]` table when `refs_declared`, `refs_id_forms` or
        `refs_accepted_reader_changes` is set (D16.2, D16.3),
        a `[targets.law]` table with `archive` when `refs_law_archive` is
        set (D16.13),
        a `[keep]` table when `keep` is true and a `refcheck:` id is kept,
        and a `[scan]` table when `ignore` is not empty.
    """
    on = _tier_switches_on(cfg, survey)
    full = on and config_mod.resolve_docs(cfg, survey.tier) == "full"
    layout_rules = cfg.layout_front_matter or cfg.layout_types or cfg.layout_index
    switches = {
        "registry": on and cfg.refs_registry,
        "comments": on and cfg.refs_comments,
        "links": on and cfg.refs_links,
        # D15.29: the `[layout]` switches decide; `refs.layout` set them.
        "layout": full and layout_rules,
        "readme": full,
    }
    lines = [f"# {MANAGED_HEADER}", "[checks]"]
    for switch in _REF_CHECK_SWITCHES:
        lines.append(f"{switch} = {_toml_bool(switches[switch])}")
    if config_mod.public_is_false(cfg, survey.root):
        # D15.14: `public = false` in the target file turns the licence rows off.
        lines.append("licence = false")
    layout = {
        "docs_dir": json.dumps(cfg.layout_docs_dir),
        "front_matter": _toml_bool(cfg.layout_front_matter),
        "types": _toml_bool(cfg.layout_types),
        "index": _toml_bool(cfg.layout_index),
    }
    if layout != _DEFAULT_LAYOUT_TABLE:
        lines.append("")
        lines.append("[layout]")
        lines.extend(f"{key} = {value}" for key, value in layout.items())
    if cfg.refs_local_tags:
        lines.append("")
        lines.append("[registry]")
        lines.append(f"local_tags = {config_mod.toml_list(cfg.refs_local_tags)}")
    if cfg.refs_declared or cfg.refs_id_forms or cfg.refs_accepted_reader_changes:
        lines.append("")
        lines.append("[targets.arch]")
        if cfg.refs_declared:
            lines.append(f"sources = {config_mod.toml_list(cfg.refs_declared)}")
        if cfg.refs_id_forms:
            lines.append(f"forms = {config_mod.toml_list(cfg.refs_id_forms)}")
        if cfg.refs_accepted_reader_changes:
            accepted = config_mod.toml_list(cfg.refs_accepted_reader_changes)
            lines.append(f"accepted = {accepted}")
    if cfg.refs_law_archive is not None:
        lines.append("")
        lines.append("[targets.law]")
        lines.append(f"archive = {config_mod.toml_string(cfg.refs_law_archive)}")
    if keep:
        kept = kept_failure_ids(cfg)
        if kept:
            lines.append("")
            lines.append("[keep]")
            lines.append(f"failures = {config_mod.toml_list(kept)}")
    if cfg.ignore:
        lines.append("")
        lines.append("[scan]")
        lines.append(f"ignore = {config_mod.toml_list(cfg.ignore)}")
    return "\n".join(lines) + "\n"


def _toml_bool(value: bool) -> str:
    """Give the TOML text of one boolean.

    Args:
        value: The value.

    Returns:
        `"true"` or `"false"`.
    """
    return "true" if value else "false"


def kept_failure_ids(cfg: Config) -> tuple[str, ...]:
    """Give the checker's own ids of the kept `refcheck:` findings, sorted (D9.2).

    A keep id can be a prefix such as `refcheck:docs/a.md`. It renders as
    `docs/a.md`, and `ref_check.keep_match` then keeps every failure of
    the page, as `findings.keep_match` does in `check` (D15.8).

    Args:
        cfg: The config whose `[[keep]]` entries are read.

    Returns:
        Each kept id that starts with `refcheck:` and names a failure, with
        that prefix removed, sorted; empty when none is kept.
    """
    prefix = "refcheck:"
    return tuple(
        sorted(
            finding_id.removeprefix(prefix)
            for finding_id in cfg.keep
            if finding_id.startswith(prefix) and finding_id != prefix
        )
    )


def lint_hooks(cfg: Config, *, vale: bool | None = None) -> list[Hook]:
    """List the hooks that `trueup lint` runs, in their fixed order (I-21, D14.6).

    The order is each enabled rule set's hooks in `LANGUAGES` order, then
    the jscpd hook when a language is strict, then the Vale hook when the
    Vale style is on. A hook that two rule sets share (the eslint and knip
    hooks of TypeScript and Vue) appears once, where it first appears. No
    hook runs gitleaks: `check` runs it for the `secret-content` row.

    Args:
        cfg: The config to read.
        vale: Whether the Vale hook comes last; `None` reads
            `_vale_enabled(cfg)`.

    Returns:
        The hooks, with no repeat.
    """
    rule_sets = enabled_rulesets(cfg)
    hooks: list[Hook] = []
    for rule_set in rule_sets:
        hooks.extend(rule_set.hooks)
    if any(rule_set.mode == "strict" for rule_set in rule_sets):
        hooks.append(JSCPD_HOOK)
    if _vale_enabled(cfg) if vale is None else vale:
        hooks.append(VALE_HOOK)
    unique: list[Hook] = []
    for hook in hooks:
        if hook not in unique:
            unique.append(hook)
    return unique


def render_pre_commit() -> str:
    """Give the pre-commit snippet of `trueup template pre-commit` (D14.9).

    The snippet has one `repo: local` hook that runs `trueup lint` on the
    staged files. It reads no config: `trueup lint` reads the effective
    config each time it runs (D14.6).

    Returns:
        The `.pre-commit-config.yaml` text, with no trueup header line.
    """
    return _PRE_COMMIT_SNIPPET


def render_ci() -> str:
    """Give the GitHub Actions workflow of `trueup template ci` (D14.9).

    The text is `templates/ci/trueup.yml` as it is: every action pinned to
    a commit SHA (I-32), a placeholder comment for the trueup install, then
    `trueup check` and `trueup lint`. It reads no config.

    Returns:
        The workflow text, with no trueup header line.
    """
    return template_path("ci/trueup.yml").read_text(encoding="utf-8")


def _without_header(text: str) -> str:
    """Remove the trueup header line from the top of a template text (D14.9).

    The header line is the managed header after a comment leader, or the
    health skeleton comment. The blank lines after it go too.

    Args:
        text: The template text.

    Returns:
        The text without its first line when that line is a trueup header,
        else the text as it is.
    """
    first, _, rest = text.partition("\n")
    if MANAGED_HEADER in first or first.startswith(_HEALTH_SKELETON_PREFIX):
        return rest.lstrip("\n")
    return text


def template_text(name: str) -> str:
    """Give the text that `trueup template <name>` prints (D14.9, D14.22).

    The person owns the file they write from the text, so no text has a
    trueup header line.

    Args:
        name: One of `TEMPLATE_NAMES`.

    Returns:
        The text of that template.

    Raises:
        ValueError: `name` is not in `TEMPLATE_NAMES`.
    """
    if name == "pre-commit":
        return render_pre_commit()
    if name == "ci":
        return render_ci()
    if name == "editorconfig":
        relative = "editorconfig"
    elif name in _HEALTH_TEMPLATES:
        relative = _HEALTH_TEMPLATES[name]
    else:
        raise ValueError(
            f"unknown template {name!r}; the names are: {', '.join(TEMPLATE_NAMES)}"
        )
    return _without_header(template_path(relative).read_text(encoding="utf-8"))


# arch: D16.5
# Values that a public standard prints. The code builds them, so the source
# holds no literal key. The first is the sample key of RFC 6455.
PUBLISHED_TEST_VALUES: tuple[str, ...] = (
    base64.b64encode(b"the sample nonce").decode("ascii"),
)


def _published_values_rule() -> str:
    """Render the `generic-api-key` override that drops the published test values (D16.5).

    The override holds one `[[rules.allowlists]]` table with one exact-match
    regex per value. The scope is that one rule, so another rule still
    reports the value. gitleaks compares; trueup never reads the match (I-30).

    Returns:
        The TOML text, starting with a blank line.
    """
    lines = [
        "",
        "[[rules]]",
        'id = "generic-api-key"',
        "",
        "[[rules.allowlists]]",
        'description = "values that a public standard prints"',
        'regexTarget = "secret"',
        "regexes = [",
    ]
    for value in PUBLISHED_TEST_VALUES:
        lines.append(f"  {json.dumps('^' + re.escape(value) + '$')},")
    lines.append("]")
    return "\n".join(lines) + "\n"


def render_gitleaks_config(cfg: Config) -> str:
    """Render `lint/gitleaks/gitleaks.toml` from `templates/gitleaks/gitleaks.toml` (D7.3).

    The template holds the managed header and the `[extend]` table. When
    `cfg.ignore` holds a glob, one `[[allowlists]]` table follows, with one
    anchored path regex per glob, in config order. The regex comes from the
    glob rules of the survey, so gitleaks skips the paths trueup skips.
    A `generic-api-key` override with the published test values always
    comes before it (D16.5).

    Args:
        cfg: The config whose `ignore` globs decide.

    Returns:
        The file text.
    """
    text = template_path("gitleaks/gitleaks.toml").read_text(encoding="utf-8")
    text += _published_values_rule()
    if not cfg.ignore:
        return text
    lines = [
        "",
        "[[allowlists]]",
        'description = "trueup.toml ignore globs"',
        "paths = [",
    ]
    for pattern in cfg.ignore:
        regex = _glob_to_regex(pattern).pattern
        lines.append(f"  {json.dumps(regex, ensure_ascii=False)},")
    lines.append("]")
    return text + "\n".join(lines) + "\n"


def _comment_leader(path: str) -> str | None:
    """Give the comment leader of a managed path, or `None` for a no-comment format.

    Args:
        path: A repo path from `render`.

    Returns:
        `"//"` for `.mjs`, `"<!--"` for `.xml` and for the `.md` agent
        rules file (D12.7), `None` for `.json` and a `.txt` word list, `"#"` for every other managed file (TOML, YAML,
        INI, `.editorconfig`, `shellcheckrc`, `.sqlfluff`, `.neon`).
    """
    suffix = Path(path).suffix
    if suffix == ".mjs":
        return "//"
    if suffix in (".xml", ".md"):
        return "<!--"
    if suffix in (".json", ".txt"):
        return None
    return "#"


def header_line(path: str) -> str | None:
    """Give the managed header line a file at `path` starts with.

    Args:
        path: A repo path from `render`.

    Returns:
        The header line, or `None` for a format that holds no comment.
    """
    leader = _comment_leader(path)
    if leader is None:
        return None
    if leader == "<!--":
        return f"<!-- {MANAGED_HEADER} -->"
    return f"{leader} {MANAGED_HEADER}"


def _significant_lines(text: str, leader: str | None) -> list[str]:
    """Drop blank lines and lines that start with the comment leader.

    Args:
        text: The file text.
        leader: The format's comment leader, or `None` to drop blank lines
            only.

    Returns:
        The other lines, right-stripped, in order.
    """
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or (leader is not None and stripped.startswith(leader)):
            continue
        kept.append(line.rstrip())
    return kept


def _is_managed_on_disk(path: str, text: str, content: str) -> bool:
    """Say whether an existing file is one trueup manages.

    Args:
        path: The repo path.
        text: The file's current text.
        content: The text `render` would write for `path` today; for a
            JSON path this carries the `"_managed"` marker.

    Returns:
        True when the first line is the managed header (for the agent
        rules file, line 5, after the front matter, D12.7); when the format
        holds no comment and `path` is a JSON file, True by
        `_is_managed_json` (LOW-2); or, for another no-comment format,
        when the path sits under `lint/`.
    """
    header = header_line(path)
    if header is None:
        if path.endswith(".json"):
            return _is_managed_json(path, text, content)
        return path.startswith("lint/")
    if path == AGENT_RULES_PATH:
        # arch: D12.7 - the header follows the front matter (lines 1-4).
        lines = text.split("\n")
        in_front = len(lines) > 4 and lines[0].rstrip() == "---"
        return in_front and lines[4].rstrip() == header
    first = text.split("\n", 1)[0].rstrip()
    return first == header


def _has_json_managed_marker(text: str) -> bool:
    """Say whether `text` is a JSON object carrying the LOW-2 managed marker.

    Args:
        text: The file's current text.

    Returns:
        True when `text` parses as a JSON object whose `"_managed"` key is
        `"trueup"`. Unparsable or non-object text gives False, never an
        exception.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get(_JSON_MANAGED_KEY) == _JSON_MANAGED_VALUE


def _is_managed_json(path: str, text: str, content: str) -> bool:
    """Say whether an on-disk JSON file is one trueup manages (LOW-2).

    A file the target already had, even one that happens to sit under
    `lint/`, is not managed just because of its path: the review's own
    example was a person's own `lint/jscpd.json` being auto-overwritten
    on that path test alone. This checks the JSON content instead.

    Args:
        path: The repo path of the JSON file.
        text: The file's current text.
        content: The text `render` would write for this path today,
            carrying the `"_managed"` marker.

    Returns:
        True when `text` carries the marker (`_has_json_managed_marker`).
        For one version, also True for the old form that trueup wrote
        before the marker: a JSON object with the same keys as `content`
        less the marker, and the same value for each key that is not in
        `_OLD_FORM_FREE_KEYS` for `path`. Any other content, unparsable
        or not, gives False, so it stays a manual, unmanaged finding (I-24).
    """
    if _has_json_managed_marker(text):
        return True
    try:
        on_disk = json.loads(text)
        rendered = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(on_disk, dict) or not isinstance(rendered, dict):
        return False
    rendered.pop(_JSON_MANAGED_KEY, None)
    if on_disk.keys() != rendered.keys():
        return False
    free = _OLD_FORM_FREE_KEYS.get(path, frozenset())
    return all(
        on_disk[key] == value for key, value in rendered.items() if key not in free
    )


def _mark_json(text: str) -> str:
    """Add the LOW-2 managed marker to one rendered JSON file's text.

    Args:
        text: The JSON text a rule-set renderer built, `indent=2` and one
            trailing newline.

    Returns:
        The same object, `"_managed": "trueup"` as its first key, rendered
        the same way (`indent=2`, one trailing newline), so
        `_is_managed_on_disk` can tell trueup's own file apart from one the
        target already had.
    """
    data = json.loads(text)
    marked = {_JSON_MANAGED_KEY: _JSON_MANAGED_VALUE, **data}
    return json.dumps(marked, indent=2) + "\n"


def _setup_finding(
    path: str, severity: str, evidence: str, action: str, auto: bool
) -> Finding:
    """Build one `file-managed` finding.

    Args:
        path: The managed repo path.
        severity: `"error"` or `"warn"`.
        evidence: The one-line evidence.
        action: The one-line action.
        auto: Whether `apply` may write the file.

    Returns:
        The finding, id `file-managed:<path>`, category `setup`.
    """
    return Finding(
        id=f"file-managed:{path}",
        rule="file-managed",
        category="setup",
        severity=severity,
        path=path,
        evidence=evidence,
        action=action,
        auto=auto,
    )


def _file_finding(
    root: Path, path: str, content: str, refs_path: str | None
) -> Finding | None:
    """Compare one managed path on disk with its rendered text (D5.6, I-24).

    Args:
        root: The target root.
        path: The managed repo path.
        content: The rendered text.
        refs_path: In copy mode, `cfg.refs_path` (or the effective
            config's), the path of the reference checker module, compared
            by bytes rather than by significant lines (D5.3); `None` in
            global mode, where no path is the checker.

    Returns:
        `None` when the file matches; else an auto `error` for an absent
        file or a changed file that still carries the header; a manual
        `error` for a changed file with no header, which trueup never
        overwrites (a manual `warn` for `.editorconfig`, since most
        repositories already have one and this is routine, not a defect,
        LOW-4); and for the reference checker module, an auto `error` when
        it differs from the bundled copy and still carries the header (an
        earlier trueup wrote it, D9.3), or a manual `warn` when it has no
        header (a person's own file, or a copy from before D9.3).
    """
    full = root / path
    if not os.path.exists(full):
        return _setup_finding(
            path, "error", f"{path} is absent", f"write {path}", auto=True
        )
    raw = fsread.read_capped(root, path, _TEXT_READ_CAP) or b""
    text = raw.decode("utf-8", errors="replace")
    if path == refs_path:
        if raw == content.encode("utf-8"):
            return None
        if text.split("\n", 1)[0].rstrip() == header_line(path):
            return _setup_finding(
                path,
                "error",
                f"{path} differs from the copy trueup ships",
                f"rewrite {path}",
                auto=True,
            )
        return _setup_finding(
            path,
            "warn",
            f"{path} is not byte-equal to the copy trueup ships and has no trueup header",
            (
                f"when it is an unedited copy from an earlier trueup, git rm {path} "
                "and apply the absent-copy finding that follows; else compare it "
                "with the bundled ref_check.py and merge by hand"
            ),
            auto=False,
        )
    leader = _comment_leader(path)
    if os.path.isfile(full) and _significant_lines(text, leader) == _significant_lines(
        content, leader
    ):
        return None
    if os.path.isfile(full) and _is_managed_on_disk(path, text, content):
        return _setup_finding(
            path,
            "error",
            f"{path} differs from the rendered content",
            f"rewrite {path}",
            auto=True,
        )
    return _setup_finding(
        path,
        "warn" if path == EDITORCONFIG_PATH else "error",
        f"{path} differs from the rendered content and has no trueup header",
        "merge by hand; trueup never overwrites an unmanaged file",
        auto=False,
    )


def _config_findings(cfg: Config | None, survey: Survey) -> list[Finding]:
    """The config gaps: no `trueup.toml`, or a language with no mode (D5.6).

    `cfg` is the effective config of `config.load`. The caller passes
    `None` when the target is not adopted: `config.load` gives a config on
    every target, so the caller reads `config.load_layers(root).adopted`
    (D15.6). Under the user default file the target has
    no `trueup.toml` but `cfg` is not `None`, so no `config:trueup.toml`
    row comes (D14.3): `apply` must not create a target file that stops
    the user default file (I-44).

    Under the user default file a present language with no mode is an
    `info` row, not an auto `error`: `apply` writes a language mode only
    through `config:trueup.toml` (I-44, I-45), so an auto row there is a
    plan item that `apply --all-auto` cannot clear. The effective config
    already lints the language as `clean`.

    Args:
        cfg: The effective config, or `None` when the target has no
            `trueup.toml` and no user default file exists.
        survey: The survey of the target.

    Returns:
        An auto `error` `config:trueup.toml` when `cfg` is `None`; an
        auto `error` `config:languages.<lang>` per present language with no
        mode, or an `info` of that id under the user default file; an
        `info` of the same id per language with files but below the
        present line count, for the skill to ask about.
    """
    findings: list[Finding] = []
    user_default = cfg is not None and not (survey.root / CONFIG_PATH).exists()
    if cfg is None:
        findings.append(
            Finding(
                id="config:trueup.toml",
                rule="config",
                category="setup",
                severity="error",
                path=CONFIG_PATH,
                evidence="trueup.toml is absent",
                action="write trueup.toml",
                auto=True,
            )
        )
    named = cfg.languages if cfg is not None else {}
    for language in LANGUAGES:
        stat = survey.languages[language]
        if language in named or stat.files == 0:
            continue
        if stat.present and user_default:
            findings.append(
                Finding(
                    id=f"config:languages.{language}",
                    rule="config",
                    category="setup",
                    severity="info",
                    path=CONFIG_PATH,
                    evidence=f"{language} is present ({stat.code_lines} code lines) and has no mode",
                    action=f"set [languages] {language} in the user default file, or write trueup.toml",
                    auto=False,
                )
            )
        elif stat.present:
            findings.append(
                Finding(
                    id=f"config:languages.{language}",
                    rule="config",
                    category="setup",
                    severity="error",
                    path=CONFIG_PATH,
                    evidence=f"{language} is present ({stat.code_lines} code lines) and has no mode",
                    action=f'set [languages] {language} = "clean" (--mode {language}=MODE overrides)',
                    auto=True,
                )
            )
        else:
            findings.append(
                Finding(
                    id=f"config:languages.{language}",
                    rule="config",
                    category="setup",
                    severity="info",
                    path=CONFIG_PATH,
                    evidence=f"{language} has {stat.code_lines} code lines, below the present count",
                    action=f"ask the person: strict, clean or off for {language}",
                    auto=False,
                )
            )
    return findings


def missing_gitignore_lines(root: Path) -> list[str]:
    """List the `GITIGNORE_LINES` that the target's `.gitignore` does not hold.

    Args:
        root: The target root.

    Returns:
        The missing lines, in `GITIGNORE_LINES` order; all of them when
        `.gitignore` is absent or `fsread` refuses it (D16.10). A write
        through a refused symlink then stops in `apply` (I-51).
    """
    path = root / ".gitignore"
    present: set[str] = set()
    if path.is_file():
        raw = fsread.read_capped(root, ".gitignore", _TEXT_READ_CAP)
        if raw is not None:
            present = {
                line.strip()
                for line in raw.decode("utf-8", errors="replace").splitlines()
            }
    return [line for line in GITIGNORE_LINES if line not in present]


def eslint_dir(cfg: Config) -> Path | None:
    """Give the eslint package directory of one config (D14.7).

    The directory is `config.cache_home() / "eslint" / <hash>`, where the
    hash is the first 16 hex digits of the SHA-256 of the package.json
    that `render_eslint_package` gives for the TypeScript and Vue modes.
    So each set of packages has its own directory, and `trueup lint
    --install` fills it once per set. Nothing goes under the target root
    (I-47).

    Args:
        cfg: The effective config, whose `[languages]` table gives the
            TypeScript and Vue modes.

    Returns:
        The directory, or `None` when TypeScript and Vue are both off. The
        directory does not have to exist.
    """
    typescript = cfg.languages.get("typescript", "off")
    vue = cfg.languages.get("vue", "off")
    if typescript == "off" and vue == "off":
        return None
    package = render_eslint_package(typescript, vue)
    digest = hashlib.sha256(package.encode("utf-8")).hexdigest()[:16]
    return config_mod.cache_home() / "eslint" / digest


def _tool_findings(
    cfg: Config, survey: Survey, vale: bool | None = None
) -> list[Finding]:
    """One `info` per tool an enabled rule set, or the Vale style, needs but the path lacks.

    Args:
        cfg: The effective config.
        survey: The survey, whose `tools` map says what is on the path.
        vale: Whether the Vale files are in the managed set (D12.9);
            `None` reads `_vale_enabled(cfg)`.

    Returns:
        `tool-missing:<lang>/<tool>` findings, `tool-missing:docs/vale`
        when the Vale style is rendered and `vale` is not on the path, and
        `tool-missing:typescript/node_modules` when TypeScript or Vue is on
        and `eslint_dir` holds no `node_modules` (D14.7).
    """
    missing: list[tuple[str, str]] = []
    for rule_set in enabled_rulesets(cfg):
        for tool in rule_set.tools:
            if (
                not survey.tools.get(tool, False)
                and (rule_set.language, tool) not in missing
            ):
                missing.append((rule_set.language, tool))
    if vale is None:
        vale = _vale_enabled(cfg)
    if vale and shutil.which("vale") is None:
        missing.append(("docs", "vale"))
    findings = [
        Finding(
            id=f"tool-missing:{owner}/{tool}",
            rule="tool-missing",
            category="setup",
            severity="info",
            path="",
            evidence=f"{tool} is not on the path; its hooks cannot be verified here",
            action=f"install {tool}",
            auto=False,
        )
        for owner, tool in missing
    ]
    if cfg.refs_mode == "global" and shutil.which("trueup") is None:
        findings.append(
            Finding(
                id="tool-missing:refs/trueup",
                rule="tool-missing",
                category="setup",
                severity="info",
                path="",
                evidence="trueup is not on the path, and the ref-check hook needs it",
                action=(
                    "install trueup once on this machine, so that the ref-check "
                    f"hook can run trueup refs: uv tool install --editable {PLUGIN_ROOT} "
                    f"(or pipx install {PLUGIN_ROOT})"
                ),
                auto=False,
            )
        )
    packages = eslint_dir(cfg)
    if packages is not None and not (packages / "node_modules").is_dir():
        # The evidence names no path: the cache directory differs per
        # machine, and a finding must not (I-44).
        findings.append(
            Finding(
                id="tool-missing:typescript/node_modules",
                rule="tool-missing",
                category="setup",
                severity="info",
                path="",
                evidence=(
                    "the eslint packages are not installed in the trueup cache; "
                    "trueup lint cannot run eslint until they are"
                ),
                action="run trueup lint --install",
                auto=False,
            )
        )
    return findings


SETUP_ID = "setup:trueup.toml"
"""The id of the setup opt-in row (D12.9); `apply --ids` takes it."""

_FOLDED_RULES: frozenset[str] = frozenset({"config", "tool-missing"})
"""The rules that the setup opt-in row folds into one row (D12.9 step 4, D14.8)."""


def setup_findings(
    survey: Survey, cfg: Config | None, *, offer: bool = True
) -> list[Finding]:
    """Run the setup checks of D5.6 over one target.

    Args:
        survey: The survey of the target.
        cfg: The effective config, or `None` when the target is not
            adopted (`config.load_layers(root).adopted` is False, D15.6).
        offer: Fold the setup rows into the one opt-in row when `cfg` is
            `None` and the tier is T0 or T1 (D12.9 step 4). `apply` gives
            `False` to get the rows that the opt-in writes.

    Returns:
        The config gaps, one `file-managed` finding per managed path that
        does not match its rendered text, a `gitignore:.gitignore` finding
        when a `GITIGNORE_LINES` line is missing and `scratch_gitignore`
        is true, in global mode the `refs-copy` info finding for an old
        checker copy (D9.1), one `managed-legacy` info finding per file of
        the old managed lint tree (D14.8), and the `tool-missing` info
        findings; unsorted. With the fold, the `config` and `tool-missing`
        findings are replaced by one `setup:trueup.toml` info finding, or
        by none when the tier set does not hold `trueup.toml`.
    """
    findings = _per_file_setup_findings(survey, cfg)
    if not offer or cfg is not None or survey.tier not in ("T0", "T1"):
        return findings
    folded = [finding for finding in findings if finding.rule in _FOLDED_RULES]
    kept = [finding for finding in findings if finding.rule not in _FOLDED_RULES]
    rendered = render(effective_config(cfg, survey), survey)
    paths = sorted(
        {
            finding.path
            for finding in folded
            if finding.path == CONFIG_PATH and CONFIG_PATH in rendered
        }
    )
    if not paths:
        return kept
    kept.append(
        Finding(
            id=SETUP_ID,
            rule="setup",
            category="setup",
            severity="info",
            path=CONFIG_PATH,
            evidence=f"{len(paths)} setup files: {', '.join(paths)}",
            action=f"run trueup apply --ids {SETUP_ID} to write them",
            auto=True,
        )
    )
    return kept


def _per_file_setup_findings(survey: Survey, cfg: Config | None) -> list[Finding]:
    """Give the setup findings of D5.6 with one row per file and per gap.

    Args:
        survey: The survey of the target.
        cfg: The loaded `trueup.toml`, or `None` when it is absent.

    Returns:
        The findings that `setup_findings` returns without the fold.
    """
    effective = effective_config(cfg, survey)
    findings = _config_findings(cfg, survey)
    refs_path = effective.refs_path if effective.refs_mode == "copy" else None
    rendered = render(effective, survey)
    for path, content in rendered.items():
        if path == CONFIG_PATH:
            continue  # trueup.toml is the `config` rule's file, above
        finding = _file_finding(survey.root, path, content, refs_path)
        if finding is not None:
            findings.append(finding)
    if effective.refs_mode == "global" and (survey.root / STALE_COPY_PATH).is_file():
        findings.append(
            Finding(
                id=f"refs-copy:{STALE_COPY_PATH}",
                rule="refs-copy",
                category="setup",
                severity="info",
                path=STALE_COPY_PATH,
                evidence=(
                    f"{STALE_COPY_PATH} exists; in global mode nothing runs it "
                    "(the ref-check hook runs trueup refs)"
                ),
                action=f"delete it when it is trueup's old copy: git rm {STALE_COPY_PATH}",
                auto=False,
            )
        )
    missing = missing_gitignore_lines(survey.root)
    if missing and effective.scratch_gitignore:
        findings.append(
            Finding(
                id="gitignore:.gitignore",
                rule="gitignore",
                category="setup",
                severity="error",
                path=".gitignore",
                evidence=f".gitignore lacks {', '.join(missing)}",
                action=f"append {', '.join(missing)} to .gitignore",
                auto=True,
            )
        )
    findings.extend(_legacy_findings(survey))
    vale = config_mod.resolve_docs(effective, survey.tier) == "full"
    findings.extend(_tool_findings(effective, survey, vale=vale))
    return findings


def _is_legacy_file(root: Path, path: str) -> bool:
    """Say whether one path holds a file of the old managed lint tree (D14.8).

    Args:
        root: The target root.
        path: A repo path in `LEGACY_PATHS` or under `lint/`.

    Returns:
        For `ESLINT_PACKAGES_DIR`, True when the directory exists. For a
        file, True when an earlier trueup wrote it: its first line is the
        managed header (for the agent rules file, line 5 after the front
        matter, D12.7), or its JSON object holds `"_managed": "trueup"`
        (LOW-2), or, for a `LEGACY_PATHS` path in a format with no
        comment and no JSON (the Vale word list), the path alone. A file
        with no such mark is the person's own and gives False (I-42).
    """
    full = root / path
    if path == ESLINT_PACKAGES_DIR:
        return os.path.isdir(full)
    if not os.path.isfile(full):
        return False
    raw = fsread.read_capped(root, path, _TEXT_READ_CAP)
    if raw is None:
        return False
    text = raw.decode("utf-8", errors="replace")
    if path in LEGACY_PATHS:
        return _is_managed_on_disk(path, text, "")
    header = header_line(path)
    if header is None:
        return path.endswith(".json") and _has_json_managed_marker(text)
    return text.split("\n", 1)[0].rstrip() == header


def _legacy_findings(survey: Survey) -> list[Finding]:
    """One `managed-legacy` info finding per file of the old managed lint tree (D14.8, I-42).

    The candidates are the `LEGACY_PATHS` and every surveyed file under
    `lint/`. Each row is `info` and not automatic: it never joins the
    plan (D5.4), so it changes no exit code. It informs; it never asks.

    Args:
        survey: The survey of the target.

    Returns:
        The findings, in `LEGACY_PATHS` order and then in survey order.
    """
    candidates = list(LEGACY_PATHS)
    candidates.extend(
        path
        for path in survey.files
        if path.startswith(_LEGACY_DIR) and path not in LEGACY_PATHS
    )
    return [
        Finding(
            id=f"managed-legacy:{path}",
            rule="managed-legacy",
            category="setup",
            severity="info",
            path=path,
            evidence=f"{path} is part of the managed lint tree of an earlier trueup",
            action=_LEGACY_ACTION,
            auto=False,
        )
        for path in candidates
        if _is_legacy_file(survey.root, path)
    ]
