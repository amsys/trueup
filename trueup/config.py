"""Read and write `trueup.toml`, the config file trueup keeps at a target root.

`load` parses the file with the standard library `tomllib` and returns a
frozen `Config`. `render` turns a `Config` back into text, in one fixed key
order, so two renders of an equal `Config` give the same bytes (arch:
D5.3).

`_parse` validates one file of one layer (D14.3): the target `trueup.toml`,
a profile file or the user default file. Only the target layer records the
keys that the file set, in `Config.explicit`.

`load_layers` reads the five layers of D14.1, low to high: the code
defaults, a profile (built-in under `data/profiles/` or a user file under
`$XDG_CONFIG_HOME/trueup/profiles/`), the user default file (only when the
target has no `trueup.toml`), the target file, and `TRUEUP_PROFILE`. It
merges them into one effective `Config` and keeps the target layer apart,
for `apply` and `render`. A module cache keyed on the stats of the files
makes each further load cost one set of stats.

The profile resolves on every target (D15.6). A target is adopted when it
holds `trueup.toml` or the user default file exists. When no layer names a
profile, an adopted target gets `house` and a target that is not adopted
gets `minimal`. `profile_flag` sets the `--profile` value for one run.
"""

from __future__ import annotations

import datetime
import os
import re
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

#: The eight languages trueup knows, in the fixed order every rendered list
#: and table follows.
LANGUAGES: tuple[str, ...] = (
    "python",
    "rust",
    "typescript",
    "vue",
    "shell",
    "sql",
    "go",
    "php",
)

_TIERS: tuple[str, ...] = ("auto", "T0", "T1", "T2", "T3")
_DOCS_MODES: tuple[str, ...] = ("auto", "full", "readme")
"""The `docs` values (D12.9): `auto` resolves by tier, `full` and `readme` are fixed."""
_HEALTH_FILES: tuple[str, ...] = ("tier", "readme")
"""The values of `[health] files` (D15.14)."""

_FULL_DOCS_TIERS: frozenset[str] = frozenset({"T2", "T3"})
"""The tiers at which `docs = "auto"` resolves to `full` (D12.9)."""
_LANGUAGE_MODES: tuple[str, ...] = ("strict", "clean", "off")
_REFS_MODES: tuple[str, ...] = ("global", "copy")
"""The checker modes of D9.1: `global` runs `trueup refs` from the path; `copy` keeps a checker copy in the target."""

PROFILE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
"""The shape of a profile name (D14.1): lower-case letters, digits and hyphens."""

BUILTIN_PROFILES: tuple[str, ...] = ("house", "minimal")
"""The built-in profile names (D14.1). A user file cannot take one of them (I-46)."""

_PROFILE_DIR = Path(__file__).resolve().parent / "data" / "profiles"
"""The directory of the built-in profile files (D14.1)."""

_DEFAULT_PROFILE = "house"
"""The profile in force on an adopted target when no layer names one (D14.1, D15.6)."""

_DEFAULT_PROFILE_NOT_ADOPTED = "minimal"
"""The profile in force on a target that is not adopted, when no layer names one (D15.6)."""

PROFILE_SOURCES: tuple[str, ...] = (
    "--profile",
    "TRUEUP_PROFILE",
    "target",
    "user default",
    "built-in default",
)
"""The values of `Layers.profile_source`, first hit first (D15.3, D15.6)."""

_FLAG_PROFILE: str | None = None
"""The `--profile` value of the current run, or `None`; `profile_flag` sets it (D15.6)."""

_PROFILE_ENV = "TRUEUP_PROFILE"
"""The environment variable that names the profile; `--profile` sets it (D14.1)."""

_LAYERS: tuple[str, ...] = ("target", "profile", "user")
"""The config files that `_parse` reads (D14.3): the target `trueup.toml`,
a profile file and the user default file."""

_TARGET_ONLY_KEYS: tuple[str, ...] = ("version", "run_date", "keep")
"""The top-level keys that only the target `trueup.toml` can set (D14.1)."""

_DOCS_DIR = re.compile(r"[A-Za-z0-9_.-]+")
"""The shape of `[layout] docs_dir` (D14.2): one path segment, with no `/`."""

_LAYOUT_SWITCHES: tuple[str, ...] = ("front_matter", "types", "index")
"""The `[layout]` switches that the older `[refs] layout` key sets together (D14.2)."""

_PROSE_LISTS: tuple[str, ...] = ("builtin", "off")
"""The `[prose] banned` values that are not a path (D14.2)."""

_DEFAULT_ESLINT_SUPPRESSIONS = "lint/typescript/eslint-suppressions.json"
"""The repo path of the eslint suppressions file, before `[eslint] suppressions` names another one (D14.2)."""

_DEFAULT_PYDOCLINT_BASELINE = "lint/python/pydoclint-baseline.txt"
"""The repo path of the pydoclint baseline, before `[python] pydoclint_baseline` names another one (D14.2)."""

_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "run_date",
        "profile",
        "tier",
        "public",
        "docs",
        "stale_days",
        "ignore",
        "protect",
        "root",
        "scratch",
        "guard",
        "layout",
        "prose",
        "health",
        "python",
        "binary",
        "refs",
        "languages",
        "eslint",
        "keep",
    }
)

_DEFAULT_REFS_PATH = "ref_check.py"

_REFS_PATH_NEEDS_COPY = (
    'trueup.toml: refs.path needs refs.mode = "copy"; in global mode the '
    "target holds no checker copy"
)
"""The error of a `refs.path` without copy mode, in one file or merged (D15.29)."""

_ROOT_BASE_CODE = "code"
"""The `[root] base` value that sets the code list again (D15.29)."""
"""The reference checker module's path at a target's root, before `[refs] path` names another one (D5.3)."""

_LOCAL_TAG = re.compile(r"[A-Z]+")
"""The shape of one `[refs] local_tags` prefix (D8.7). It equals
`trueup.ref_check._LOCAL_TAG`, which checks the same value once `apply` has
rendered it into `ref_check.toml`; a test keeps the two patterns equal,
since this module must not import the checker."""

_ID_FORM_HOLE = re.compile(r"<[a-z]+>")
"""One placeholder of a `[refs] id_forms` entry. It means digits (D16.2)."""

_ID_FORM_GLUED = re.compile(r"<[a-z]+>(?:<[a-z]+>|\d)")
"""A placeholder that a digit or a placeholder follows (D16.2). The digits
of the first placeholder would have no end."""

_ID_FORM_BANNED = re.compile(r"[\s,]")
"""The characters that a `[refs] id_forms` entry cannot hold (D16.2)."""

_ID_FORM_MAX_LENGTH = 24
"""The longest `[refs] id_forms` entry, in characters (D16.2)."""

_ID_FORMS_MAX = 16
"""The largest number of `[refs] id_forms` entries (D16.2)."""

_ESLINT_RULE = re.compile(r"[@A-Za-z0-9_.-]+(?:/[@A-Za-z0-9_.-]+)*")
"""The shape of one `[[eslint.off]]` rule name (D13.5): a core rule such as
`no-console`, or a plugin rule such as `security/detect-object-injection` or
`@typescript-eslint/no-explicit-any`. No space and no quote, so the name
goes into the rendered eslint config as a plain string."""

_LINE_BREAKS: frozenset[str] = frozenset({"\u2028", "\u2029"})
"""The characters beyond the C0 controls that end a JavaScript `//` comment.
An `[[eslint.off]]` reason holds none of them, so it stays on its line (D13.5)."""


class ConfigError(Exception):
    """`trueup.toml` holds an unknown key, or a value that fails validation."""


@dataclass(frozen=True)
class Config:
    """The parsed contents of `trueup.toml`.

    Attributes:
        version: The config schema version. Always 1.
        run_date: The date of the last apply that changed a file, as
            `YYYY-MM-DD`, or `None` before the first such apply.
        tier: One of `"auto"`, `"T0"`, `"T1"`, `"T2"`, `"T3"`.
        public: Whether the target repository is public.
        docs: `"auto"` (the default), `"full"` or `"readme"`. Readers
            call `resolve_docs` to get the mode in force (D12.9).
        stale_days: Days after which a `status: current` page counts as
            stale (P8).
        ignore: Glob patterns left out of the survey and every finding.
        protect: Glob patterns that `apply` never changes or removes.
        root_allow: Extra root entries the guard hook allows, beyond the
            base list.
        scratch_allow: Globs, matched against a repo path or a basename,
            that the scratch rule of `check` and the guard hook lets
            through whatever the name looks like.
        layout_code_dirs: Directory names that hold Markdown-as-code, added
            to `layout.CODE_SEGMENTS`. A Markdown file under one is not a
            `doc-misplaced` candidate (D13.1).
        binary_allow: Globs, matched against a repo path or a basename,
            that the `binary` row lets through (D13.2).
        refs_mode: `"global"` (the default: the target holds no checker
            copy and the `ref-check` hook runs `trueup refs`) or `"copy"`
            (D9.1).
        refs_path: The repo-relative path of the reference checker module,
            a `.py` file with no `..` part, in copy mode only. `apply`
            writes the bundled checker there, the `ref-check` pre-commit
            hook runs it, and the Python rule set's `ruff-format` hook
            excludes it. Default `"ref_check.py"`.
        refs_local_tags: The project's own comment-tag prefixes, uppercase
            letters each, that the checker's rule R1 does not report as an
            unregistered marker. `apply` renders them into the managed
            `ref_check.toml` as `[registry] local_tags` (D8.7). Empty by
            default.
        refs_law_archive: The law archive directory, relative to the root
            or absolute, or `None`. `render_ref_check_config` writes it as
            `[targets.law] archive` (D16.13). `None` by default: no `law`
            reference resolves.
        refs_declared: The pages or globs, relative to the root, that declare
            the design ids (D16.2). `render_ref_check_config` writes them as
            `[targets.arch] sources`. Empty by default.
        refs_id_forms: The forms of a design id, for example `D<n>.<m>`
            (D16.2). `render_ref_check_config` writes them as
            `[targets.arch] forms`. Empty by default.
        refs_accepted_reader_changes: The names of the reader changes that
            fail now, not warn (D16.3). `render_ref_check_config` writes them
            as `[targets.arch] accepted`. Empty by default.
        refs_layout: Whether check h of the checker runs (D9.4). `False`
            renders `[checks] layout = false`. Default `True`.
        languages: Language name to mode (`"strict"`, `"clean"` or
            `"off"`), one entry per language present in the file.
        eslint_off: eslint rule name to the reason it is off, from the
            `[[eslint.off]]` entries. `apply` renders them into the managed
            eslint config as a last config object (D13.5). Empty by default.
        keep: Finding id to the reason a person declined it.
        profile: The profile name as the file set it, or `None` for the
            built-in `house` profile (D14.1).
        layout_docs_dir: The directory that holds the documentation pages,
            one path segment. Default `"docs"` (D14.2).
        layout_front_matter: Whether a page needs front matter. Default
            `True`.
        layout_types: Whether the pages sit in the Diataxis type
            directories. Default `True`.
        layout_index: Whether each page needs a link from an index.
            Default `True`.
        prose_banned: `"builtin"`, `"off"`, or the path of a banned-word
            file. The target layer holds the text as written; the config
            that `load` returns holds the absolute path (D14.2).
        prose_extra: Banned-word entries in the `banned.txt` form, added
            after the entries of the file. Empty by default.
        refs_registry: Whether the checker runs its registry check.
            Default `True`.
        refs_comments: Whether the checker runs its comment check. Default
            `True`.
        refs_links: Whether the checker runs its link check. Default
            `True`.
        root_base: Globs that replace the base root list of the guard
            hook, or `None` to keep the list in the code.
        health_agents: Whether the health rows for the agent rules file
            run. Default `True`.
        health_files: `"tier"` (the default) asks for the health files
            of the tier; `"readme"` asks for the README only (D15.14).
        scratch_gitignore: Whether the `.gitignore` row asks for the
            `.scratch/` line. Default `True`.
        eslint_suppressions: The repo path of the eslint suppressions file.
        python_pydoclint_baseline: The repo path of the pydoclint baseline.
        explicit: The dotted keys that the target file set, for example
            `"tier"`, `"root.allow"` or `"languages.python"`. `None` for a
            profile file, for the user default file and for the config that
            `load` returns (D14.3).
    """

    version: int = 1
    run_date: str | None = None
    tier: str = "auto"
    public: bool = False
    docs: str = "auto"
    stale_days: int = 180
    ignore: tuple[str, ...] = ()
    protect: tuple[str, ...] = ()
    root_allow: tuple[str, ...] = ()
    scratch_allow: tuple[str, ...] = ()
    layout_code_dirs: tuple[str, ...] = ()
    binary_allow: tuple[str, ...] = ()
    refs_mode: str = "global"
    refs_path: str = _DEFAULT_REFS_PATH
    refs_local_tags: tuple[str, ...] = ()
    refs_law_archive: str | None = None
    refs_layout: bool = True
    languages: dict[str, str] = field(default_factory=dict)
    eslint_off: dict[str, str] = field(default_factory=dict)
    keep: dict[str, str] = field(default_factory=dict)
    profile: str | None = None
    layout_docs_dir: str = "docs"
    layout_front_matter: bool = True
    layout_types: bool = True
    layout_index: bool = True
    prose_banned: str = "builtin"
    prose_extra: tuple[str, ...] = ()
    refs_registry: bool = True
    refs_comments: bool = True
    refs_links: bool = True
    refs_declared: tuple[str, ...] = ()
    refs_id_forms: tuple[str, ...] = ()
    refs_accepted_reader_changes: tuple[str, ...] = ()
    root_base: tuple[str, ...] | None = None
    health_agents: bool = True
    health_files: str = "tier"
    scratch_gitignore: bool = True
    guard_registry: bool = False
    guard_private_packages: tuple[str, ...] = ()
    eslint_suppressions: str = _DEFAULT_ESLINT_SUPPRESSIONS
    python_pydoclint_baseline: str = _DEFAULT_PYDOCLINT_BASELINE
    explicit: frozenset[str] | None = None


@dataclass(frozen=True)
class Layers:
    """The config layers of one target, read and merged (D14.1, D14.3).

    Attributes:
        effective: The code defaults, the profile, the user default file
            (only without a target file) and the target file, merged.
            Every reader takes this config. `explicit` is `None`.
        target: The target `trueup.toml` alone, with `explicit`, or `None`
            when the target has no file. `apply` and `render` take this
            layer.
        profile: The resolved profile name.
        profile_path: The file the profile came from.
        user_default: The user default file, when it was read.
        adopted: True when the target holds `trueup.toml` or the user
            default file exists (D15.6).
        profile_source: The layer that named the profile, one of
            `PROFILE_SOURCES` (D15.3, D15.6).
    """

    effective: Config
    target: Config | None
    profile: str
    profile_path: Path
    user_default: Path | None
    adopted: bool
    profile_source: str


_Stat = tuple[str, int | None, int | None]
"""One file probe of the cache key: the path, `st_mtime_ns` and `st_size`,
or `None` twice when the file does not exist."""

_CACHE: dict[
    tuple[str, str | None, str | None, str], tuple[tuple[_Stat, ...], Layers]
] = {}
"""The loaded layers per `(root, --profile, TRUEUP_PROFILE, config_home())`,
with the stats of each file that the load read or probed (D14.3, D15.6)."""

_MERGE_FIELDS: dict[str, tuple[str, ...]] = {
    "version": ("version",),
    "run_date": ("run_date",),
    "tier": ("tier",),
    "public": ("public",),
    "docs": ("docs",),
    "stale_days": ("stale_days",),
    "ignore": ("ignore",),
    "protect": ("protect",),
    "root.allow": ("root_allow",),
    "root.base": ("root_base",),
    "scratch.allow": ("scratch_allow",),
    "scratch.gitignore": ("scratch_gitignore",),
    "guard.registry": ("guard_registry",),
    "guard.private_packages": ("guard_private_packages",),
    "layout.code_dirs": ("layout_code_dirs",),
    "layout.docs_dir": ("layout_docs_dir",),
    "layout.front_matter": ("layout_front_matter",),
    "layout.types": ("layout_types",),
    "layout.index": ("layout_index",),
    "binary.allow": ("binary_allow",),
    "prose.banned": ("prose_banned",),
    "prose.extra": ("prose_extra",),
    "refs.mode": ("refs_mode",),
    "refs.path": ("refs_path",),
    "refs.local_tags": ("refs_local_tags",),
    "refs.law_archive": ("refs_law_archive",),
    "refs.declared": ("refs_declared",),
    "refs.id_forms": ("refs_id_forms",),
    "refs.accepted_reader_changes": ("refs_accepted_reader_changes",),
    # The older key sets the three [layout] switches together (D14.2).
    "refs.layout": (
        "refs_layout",
        "layout_front_matter",
        "layout_types",
        "layout_index",
    ),
    "refs.registry": ("refs_registry",),
    "refs.comments": ("refs_comments",),
    "refs.links": ("refs_links",),
    "health.agents": ("health_agents",),
    "health.files": ("health_files",),
    "python.pydoclint_baseline": ("python_pydoclint_baseline",),
    "eslint.suppressions": ("eslint_suppressions",),
    # D15.29: a layer that sets `[[eslint.off]]`, or `off = []`, replaces
    # the lower list.
    "eslint.off": ("eslint_off",),
    "keep": ("keep",),
}
"""Per dotted key of a config file, the `Config` fields that a higher layer
replaces when it sets the key (D14.3, D15.29). `[languages]` merges per
entry in `_overlay`; `profile` is resolved in `_read_layers`."""


KEYS: tuple[str, ...] = tuple(
    sorted({*_MERGE_FIELDS, "profile", "languages", "eslint.off"})
)
"""Every dotted key a config file can set, sorted (D15.36). It is the
`_MERGE_FIELDS` keys, `profile`, `languages` and `eslint.off`, which
includes `guard.registry` and `guard.private_packages`. The skill drift
test checks the keys the skill names against it."""


def config_home() -> Path:
    """Give the directory of the user config files of trueup (D14.1).

    Returns:
        `$XDG_CONFIG_HOME/trueup`, or `~/.config/trueup` when the variable
        is empty or unset.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "trueup"


def cache_home() -> Path:
    """Give the directory of the cache of trueup (D14.1, D14.7).

    Returns:
        `$XDG_CACHE_HOME/trueup`, or `~/.cache/trueup` when the variable is
        empty or unset.
    """
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "trueup"


def clear_cache() -> None:
    """Forget every loaded set of layers, so the next load reads the files again (D14.3)."""
    _CACHE.clear()


@contextmanager
def profile_flag(name: str | None) -> Iterator[None]:
    """Set the `--profile` value for the body of the block (D15.6).

    The block sets `TRUEUP_PROFILE` and the module value that `load_layers`
    reads first. On exit, also on an error, both get their old values
    back, so the flag never leaks past one run.

    Args:
        name: The `--profile` value, or `None`, which changes nothing.

    Yields:
        Nothing.
    """
    global _FLAG_PROFILE
    if name is None:
        yield
        return
    saved_flag = _FLAG_PROFILE
    saved_env = os.environ.get(_PROFILE_ENV)
    _FLAG_PROFILE = name
    os.environ[_PROFILE_ENV] = name
    try:
        yield
    finally:
        _FLAG_PROFILE = saved_flag
        if saved_env is None:
            os.environ.pop(_PROFILE_ENV, None)
        else:
            os.environ[_PROFILE_ENV] = saved_env


def load_layers(root: Path) -> Layers:
    """Read and merge the config layers of one target (D14.1, D14.3, D15.6).

    A target that holds `trueup.toml` never reads the user default file
    (I-44). The profile name comes from `--profile` (`profile_flag`), then
    `TRUEUP_PROFILE`, then the target's `profile` key, then the user
    default file's `profile` key. When no layer names a profile, an
    adopted target gets `house` and a target that is not adopted gets
    `minimal`. A second call with no changed file gives the cached result.

    Args:
        root: The repository root that may hold `trueup.toml`.

    Returns:
        The layers. `adopted` is False when neither `<root>/trueup.toml`
        nor the user default file exists.

    Raises:
        ConfigError: A file is not valid TOML or fails validation, a user
            profile file has a built-in name, or the profile name is not
            valid or resolves to no file, on every target. The message
            starts with `--profile:` or `TRUEUP_PROFILE:` when the flag or
            the variable named the profile.
    """
    env_profile = os.environ.get(_PROFILE_ENV) or None
    key = (str(root.absolute()), _FLAG_PROFILE, env_profile, str(config_home()))
    cached = _CACHE.get(key)
    if cached is not None:
        stats, layers = cached
        if all(_stat(Path(path)) == (path, mtime, size) for path, mtime, size in stats):
            return layers
    probed: list[_Stat] = []
    layers = _read_layers(root, env_profile, probed)
    _CACHE[key] = (tuple(probed), layers)
    return layers


def public_is_false(cfg: Config, root: Path) -> bool:
    """Say whether the target file sets `public = false` itself (D15.14).

    An unset `public` is not false here: it keeps today's behaviour.

    Args:
        cfg: A config. When its `explicit` is set, that decides. The
            effective config has `explicit` at `None`, so the target layer
            of `root` decides then.
        root: The repository root.

    Returns:
        True when `public` is among the keys the target file sets and its
        value is false.
    """
    if cfg.explicit is not None:
        return "public" in cfg.explicit and not cfg.public
    target = load_layers(root).target
    return (
        target is not None and "public" in (target.explicit or ()) and not target.public
    )


def load(root: Path) -> Config:
    """Give the effective config of a target: every layer merged (D14.3, D15.6).

    `explicit` is `None`, and a `[prose] banned` path is the absolute path
    of the file. A target that is not adopted also gets a config: the
    resolved profile over the code defaults. A reader that needs to know
    whether the target is adopted reads `load_layers(root).adopted`.

    Args:
        root: The repository root that may hold `trueup.toml`.

    Returns:
        `load_layers(root).effective`.

    Raises:
        ConfigError: As `load_layers` raises it.
    """
    return load_layers(root).effective


def load_target(root: Path) -> Config | None:
    """Give the target layer: `<root>/trueup.toml` alone, as the file holds it (D14.3).

    `apply` merges into this config and `render` writes it back, so a key
    that the file set stays in the file also when it holds the default
    value. `explicit` lists the dotted keys of the file, and a
    `[prose] banned` path stays as written.

    Args:
        root: The repository root that may hold `trueup.toml`.

    Returns:
        `load_layers(root).target`, or `None` when the file does not exist.

    Raises:
        ConfigError: As `load_layers` raises it.
    """
    return load_layers(root).target


def _stat(path: Path) -> _Stat:
    """Give one cache probe of a file (D14.3).

    Args:
        path: The file.

    Returns:
        The path, `st_mtime_ns` and `st_size`, or `None` twice when the
        file does not exist.
    """
    try:
        info = path.stat()
    except OSError:
        return (str(path), None, None)
    return (str(path), info.st_mtime_ns, info.st_size)


def _read_layers(root: Path, env_profile: str | None, probed: list[_Stat]) -> Layers:
    """Read each layer file and merge the layers, for `load_layers` (D14.1, D14.3, D15.6).

    Each file is probed before it is read, so the recorded stats are never
    newer than the content.

    Args:
        root: The repository root that may hold `trueup.toml`.
        env_profile: The value of `TRUEUP_PROFILE`, or `None` when it is
            empty or unset.
        probed: The list that collects the stats of each file probed.

    Returns:
        The layers, also for a target that is not adopted.

    Raises:
        ConfigError: As `load_layers` raises it.
    """
    target_path = root / "trueup.toml"
    user_path = config_home() / "trueup.toml"
    target = target_raw = None
    user = user_raw = None
    probed.append(_stat(target_path))
    if probed[-1][1] is not None:
        target_raw = _read_toml(target_path, str(target_path))
        target = _parse(target_raw, source=target_path, layer="target")
    else:
        probed.append(_stat(user_path))
        if probed[-1][1] is not None:
            user_raw = _read_toml(user_path, str(user_path))
            user = _parse(user_raw, source=user_path, layer="user")
    adopted = target is not None or user is not None

    # D15.6: the profile resolves on every target, adopted or not.
    name = _DEFAULT_PROFILE if adopted else _DEFAULT_PROFILE_NOT_ADOPTED
    named_by: str | None = None
    source = "built-in default"
    if _FLAG_PROFILE is not None:
        name, named_by, source = _FLAG_PROFILE, "--profile", "--profile"
    elif env_profile is not None:
        name, named_by, source = env_profile, _PROFILE_ENV, _PROFILE_ENV
    elif target is not None and target.profile is not None:
        name, named_by, source = target.profile, str(target_path), "target"
    elif user is not None and user.profile is not None:
        name, named_by, source = user.profile, str(user_path), "user default"
    if not PROFILE_NAME.fullmatch(name):
        raise ConfigError(
            f"{named_by}: profile name must be lower-case letters, digits and "
            f"hyphens, got {name!r}"
        )
    profile_path = _profile_path(name, named_by, probed)
    profile_raw = _read_toml(profile_path, str(profile_path))
    profile = _parse(profile_raw, source=profile_path, layer="profile")

    effective = _overlay(Config(), profile, profile_raw)
    if user is not None and user_raw is not None:
        effective = _overlay(effective, user, user_raw)
    resolved_target = None
    if target is not None and target_raw is not None:
        resolved_target = replace(
            target, prose_banned=_resolve_banned(target.prose_banned, target_path)
        )
        effective = _overlay(effective, resolved_target, target_raw)
    effective = replace(
        effective, profile=None if named_by is None else name, explicit=None
    )
    _check_merged(
        effective,
        [
            (profile_path, profile_raw),
            (user_path, user_raw),
            (target_path, target_raw),
        ],
    )
    # D14.3: a banned-word file that a layer names is also a probe, so a
    # removed or changed list file makes the next load read the files again.
    for layer_cfg in (profile, user, resolved_target):
        if layer_cfg is not None and layer_cfg.prose_banned not in _PROSE_LISTS:
            probed.append(_stat(Path(layer_cfg.prose_banned)))
    return Layers(
        effective=effective,
        target=target,
        profile=name,
        profile_path=profile_path,
        user_default=user_path if user is not None else None,
        adopted=adopted,
        profile_source=source,
    )


def _check_merged(
    effective: Config, layers: list[tuple[Path, dict[str, Any] | None]]
) -> None:
    """Check the rules that span two layers on the merged config (D15.29).

    Args:
        effective: The merged config.
        layers: Each layer file with its parsed mapping, lowest first, or
            `None` for a layer that was not read.

    Raises:
        ConfigError: A layer sets `refs.path` and the merged `refs.mode` is
            not `copy`. The message starts with the path of the highest
            layer that sets `refs.path` or `refs.mode`.
    """
    setters = [
        path
        for path, raw in layers
        if raw is not None and {"refs.path", "refs.mode"} & _explicit_keys(raw)
    ]
    sets_path = any(
        raw is not None and "refs.path" in _explicit_keys(raw) for _, raw in layers
    )
    if sets_path and effective.refs_mode != "copy":
        message = _REFS_PATH_NEEDS_COPY.removeprefix("trueup.toml: ")
        raise ConfigError(f"{setters[-1]}: {message}")


def profile_path(name: str, named_by: str | None = None) -> Path:
    """Find the file of one profile name, as a load finds it (D14.1, D15.6).

    `apply --set profile=NAME` calls this before it writes the name, so
    the target file never names a profile that resolves to no file. The
    CLI calls it for `--profile` before the handler runs.

    Args:
        name: The profile name.
        named_by: The flag or file that named the profile, the prefix of
            each error message, or `None` for no prefix.

    Returns:
        The built-in file for a built-in name, else the user profile file.

    Raises:
        ConfigError: The name is not valid, a user profile file has a
            built-in name, or the name resolves to no file. The message
            names both search paths.
    """
    if not PROFILE_NAME.fullmatch(name):
        prefix = f"{named_by}: " if named_by is not None else ""
        raise ConfigError(
            f"{prefix}profile name must be lower-case letters, digits and "
            f"hyphens, got {name!r}"
        )
    return _profile_path(name, named_by, [])


def _profile_path(name: str, named_by: str | None, probed: list[_Stat]) -> Path:
    """Find the file of one profile name (D14.1).

    A user profile file with a built-in name is an error for every load,
    so `profile = "house"` means the same rules on every machine (I-46).

    Args:
        name: A valid profile name.
        named_by: The flag, variable or file that named the profile, or
            `None` for the built-in default.
        probed: The list that collects the stats of each file probed.

    Returns:
        The built-in file for a built-in name, else the user profile file.

    Raises:
        ConfigError: A user profile file has a built-in name, or the name
            resolves to no file. The message names both search paths.
    """
    user_dir = config_home() / "profiles"
    for builtin in BUILTIN_PROFILES:
        shadow = user_dir / f"{builtin}.toml"
        probed.append(_stat(shadow))
        if probed[-1][1] is not None:
            raise ConfigError(
                f"{shadow}: profiles/{builtin}.toml shadows the built-in profile "
                f"{builtin}; rename it"
            )
    path = (
        _PROFILE_DIR / f"{name}.toml"
        if name in BUILTIN_PROFILES
        else user_dir / f"{name}.toml"
    )
    probed.append(_stat(path))
    if probed[-1][1] is None:
        source = f"{named_by}: " if named_by is not None else ""
        raise ConfigError(
            f"{source}profile {name!r} is not found: it is not a built-in profile "
            f"in {_PROFILE_DIR} and {path} does not exist"
        )
    return path


def _read_toml(path: Path, label: str) -> dict[str, Any]:
    """Read and parse one TOML config file.

    Args:
        path: The file.
        label: The name of the file in an error message.

    Returns:
        The mapping that `tomllib` returned.

    Raises:
        ConfigError: The file cannot be read or is not UTF-8 (D15.1), or it
            is not valid TOML.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
        raise ConfigError(f"{label}: cannot read: {reason}") from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{label} is not valid TOML: {exc}") from exc


def _overlay(lower: Config, layer: Config, raw: dict[str, Any]) -> Config:
    """Put one higher layer over the merged lower layers (D14.3).

    A scalar or a list that the layer set replaces the lower value; so does
    `[[eslint.off]]` (D15.29). A table merges key by key, `[languages]` per
    language, where the higher layer wins.

    Args:
        lower: The lower layers, merged.
        layer: The parsed higher layer.
        raw: The mapping that `tomllib` returned for the higher layer.

    Returns:
        The merged config.
    """
    changes: dict[str, Any] = {}
    for key in _explicit_keys(raw):
        for name in _MERGE_FIELDS.get(key, ()):
            changes[name] = getattr(layer, name)
    if layer.languages:
        changes["languages"] = {**lower.languages, **layer.languages}
    return replace(lower, **changes)


def _parse(raw: dict[str, Any], *, source: Path | None, layer: str) -> Config:
    """Validate one parsed config file and build a `Config` from it (D14.3).

    A profile file and the user default file cannot set the target-only
    keys `version`, `run_date` and `[[keep]]`; a profile file cannot set
    `profile` (D14.1). An error message starts with the full path of the
    file, the target file too (D15.29); with no `source`, a target error
    starts with `trueup.toml: `.
    For the target layer, `explicit` holds the dotted keys of `raw`: each
    top-level key, and `<table>.<key>` for each key of a table.

    Args:
        raw: The mapping that `tomllib` returned for the file.
        source: The path of the file. A relative `[prose] banned` path is
            relative to its directory; `None` means the current directory.
        layer: `"target"`, `"profile"` or `"user"`.

    Returns:
        The validated `Config`. A `[prose] banned` path stays as written
        for the target layer and is absolute for the other layers.

    Raises:
        ConfigError: An unknown key or an invalid value was found.
        ValueError: `layer` is not one of the three layers.
    """
    if layer not in _LAYERS:
        raise ValueError(f"unknown config layer {layer!r}")
    try:
        cfg = _parse_values(raw, source, layer)
    except ConfigError as exc:
        if source is None and layer == "target":
            raise
        label = str(source) if source is not None else f"the {layer} file"
        message = str(exc).removeprefix("trueup.toml: ")
        raise ConfigError(f"{label}: {message}") from exc
    if layer != "target":
        return cfg
    return replace(cfg, explicit=_explicit_keys(raw))


def _explicit_keys(raw: dict[str, Any]) -> frozenset[str]:
    """Give the dotted keys that a parsed config file set (D14.3).

    Args:
        raw: The mapping that `tomllib` returned for the file.

    Returns:
        Each top-level key, and `<table>.<key>` for each key of a table,
        for example `"root"`, `"root.allow"` and `"keep"`.
    """
    keys: set[str] = set()
    for key, value in raw.items():
        keys.add(key)
        if isinstance(value, dict):
            keys.update(f"{key}.{name}" for name in value)
    return frozenset(keys)


def _parse_values(raw: dict[str, Any], source: Path | None, layer: str) -> Config:
    """Check the keys and values of one config file and build its `Config`.

    Args:
        raw: The mapping that `tomllib` returned for the file.
        source: The path of the file, or `None`.
        layer: `"target"`, `"profile"` or `"user"`.

    Returns:
        The validated `Config`, with `explicit` at `None`.

    Raises:
        ConfigError: An unknown key or an invalid value was found. The
            message starts with `trueup.toml: `.
    """
    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(f"trueup.toml: unknown key(s) {sorted(unknown)}")
    if layer != "target":
        target_only = [key for key in _TARGET_ONLY_KEYS if key in raw]
        if target_only:
            raise ConfigError(
                f"trueup.toml: only the target trueup.toml can set {target_only}; "
                "a profile or user default file cannot"
            )
    if layer == "profile" and "profile" in raw:
        raise ConfigError("trueup.toml: a profile file cannot set profile")

    profile = raw.get("profile")
    if profile is not None and (
        not isinstance(profile, str) or not PROFILE_NAME.fullmatch(profile)
    ):
        raise ConfigError(
            "trueup.toml: profile name must be lower-case letters, digits and "
            f"hyphens, got {profile!r}"
        )

    version = raw.get("version", 1)
    if version != 1:
        raise ConfigError(f"trueup.toml: version must be 1, got {version!r}")

    run_date = raw.get("run_date")
    if run_date is not None and not isinstance(run_date, str):
        raise ConfigError("trueup.toml: run_date must be a string")
    if run_date == "":
        # `render` writes an empty string, never an absent key, for "no
        # apply yet". Reading it back as `None` keeps render/load a
        # round trip for the default Config.
        run_date = None
    elif run_date is not None:
        try:
            datetime.date.fromisoformat(run_date)
        except ValueError as exc:
            raise ConfigError(
                f"trueup.toml: run_date must be a date as YYYY-MM-DD, got {run_date!r}"
            ) from exc

    tier = raw.get("tier", "auto")
    if tier not in _TIERS:
        raise ConfigError(f"trueup.toml: tier must be one of {_TIERS}, got {tier!r}")

    public = raw.get("public", False)
    if not isinstance(public, bool):
        raise ConfigError("trueup.toml: public must be true or false")

    docs = raw.get("docs", "auto")
    if docs not in _DOCS_MODES:
        raise ConfigError(
            f"trueup.toml: docs must be one of {_DOCS_MODES}, got {docs!r}"
        )

    stale_days = raw.get("stale_days", 180)
    if (
        not isinstance(stale_days, int)
        or isinstance(stale_days, bool)
        or stale_days <= 0
    ):
        raise ConfigError("trueup.toml: stale_days must be a positive integer")

    ignore = _string_list(raw, "ignore")
    protect = _string_list(raw, "protect")
    prose_banned, prose_extra = _parse_prose(raw.get("prose", {}), source, layer)

    health_table = _table(raw.get("health", {}), "health", ("agents", "files"))
    health_agents = _switch(health_table, "agents", "health.agents")
    health_files = health_table.get("files", "tier")
    if health_files not in _HEALTH_FILES:
        raise ConfigError(
            f"trueup.toml: health.files must be one of {_HEALTH_FILES}, "
            f"got {health_files!r}"
        )

    python_table = _table(raw.get("python", {}), "python", ("pydoclint_baseline",))
    python_pydoclint_baseline = _repo_path(
        python_table,
        "pydoclint_baseline",
        _DEFAULT_PYDOCLINT_BASELINE,
        "python.pydoclint_baseline",
    )

    root_table = _table(raw.get("root", {}), "root", ("allow", "base"))
    root_allow = _string_list(root_table, "allow", context="root.allow")
    # D15.29: `base = "code"` sets the code list again over a lower layer.
    root_base = (
        _string_list(root_table, "base", context="root.base")
        if "base" in root_table and root_table["base"] != _ROOT_BASE_CODE
        else None
    )

    scratch_table = _table(raw.get("scratch", {}), "scratch", ("allow", "gitignore"))
    scratch_allow = _string_list(scratch_table, "allow", context="scratch.allow")
    scratch_gitignore = _switch(scratch_table, "gitignore", "scratch.gitignore")

    guard_table = _table(
        raw.get("guard", {}), "guard", ("registry", "private_packages")
    )
    guard_registry = _switch(guard_table, "registry", "guard.registry", default=False)
    guard_private_packages = _string_list(
        guard_table, "private_packages", context="guard.private_packages"
    )

    layout_table = _table(
        raw.get("layout", {}), "layout", ("code_dirs", "docs_dir", *_LAYOUT_SWITCHES)
    )
    layout_code_dirs = _string_list(
        layout_table, "code_dirs", context="layout.code_dirs"
    )
    if any(not name or "/" in name for name in layout_code_dirs):
        raise ConfigError(
            "trueup.toml: layout.code_dirs must be directory names with no '/'"
        )
    layout_docs_dir = layout_table.get("docs_dir", "docs")
    if (
        not isinstance(layout_docs_dir, str)
        or not _DOCS_DIR.fullmatch(layout_docs_dir)
        or layout_docs_dir in {".", ".."}
    ):
        raise ConfigError(
            "trueup.toml: layout.docs_dir must be one directory name of letters, "
            f"digits, '_', '.' and '-', got {layout_docs_dir!r}"
        )
    layout_switches = {
        name: _switch(layout_table, name, f"layout.{name}") for name in _LAYOUT_SWITCHES
    }

    binary_table = _table(raw.get("binary", {}), "binary", ("allow",))
    binary_allow = _string_list(binary_table, "allow", context="binary.allow")

    refs_table = _table(
        raw.get("refs", {}),
        "refs",
        (
            "mode",
            "path",
            "local_tags",
            "law_archive",
            "layout",
            "registry",
            "comments",
            "links",
            "declared",
            "id_forms",
            "accepted_reader_changes",
        ),
    )
    refs_mode = refs_table.get("mode", "global")
    if refs_mode not in _REFS_MODES:
        raise ConfigError(
            f"trueup.toml: refs.mode must be one of {_REFS_MODES}, got {refs_mode!r}"
        )
    # D15.29: with both keys in this table the file decides; else the
    # merged config decides, in `_check_merged`.
    if "path" in refs_table and "mode" in refs_table and refs_mode != "copy":
        raise ConfigError(_REFS_PATH_NEEDS_COPY)
    refs_layout = refs_table.get("layout", True)
    if not isinstance(refs_layout, bool):
        raise ConfigError("trueup.toml: refs.layout must be true or false")
    if "layout" in refs_table:
        # The older key sets the three [layout] switches together (D14.2).
        beside = [f"layout.{name}" for name in _LAYOUT_SWITCHES if name in layout_table]
        if beside:
            raise ConfigError(
                f"trueup.toml: refs.layout cannot stand beside {', '.join(beside)}; "
                "set the [layout] keys and remove refs.layout"
            )
        layout_switches = dict.fromkeys(_LAYOUT_SWITCHES, refs_layout)
    refs_registry = _switch(refs_table, "registry", "refs.registry")
    refs_comments = _switch(refs_table, "comments", "refs.comments")
    refs_links = _switch(refs_table, "links", "refs.links")
    refs_path = refs_table.get("path", _DEFAULT_REFS_PATH)
    if not isinstance(refs_path, str):
        raise ConfigError("trueup.toml: refs.path must be a string")
    _validate_refs_path(refs_path)
    refs_local_tags = _string_list(refs_table, "local_tags", context="refs.local_tags")
    if not all(_LOCAL_TAG.fullmatch(tag) for tag in refs_local_tags):
        raise ConfigError(
            "trueup.toml: refs.local_tags must be a list of uppercase prefixes, "
            'for example ["X", "G"]'
        )
    refs_law_archive = refs_table.get("law_archive")
    if refs_law_archive is not None and (
        not isinstance(refs_law_archive, str) or not refs_law_archive.strip()
    ):
        raise ConfigError(
            "trueup.toml: refs.law_archive must be a non-empty string, the path "
            "of the law archive relative to the root or absolute (D16.13)"
        )
    refs_declared = _string_list(refs_table, "declared", context="refs.declared")
    if not all(entry and not os.path.isabs(entry) for entry in refs_declared):
        raise ConfigError(
            "trueup.toml: refs.declared must be a list of paths or globs relative "
            "to the root; an absolute path is an error"
        )
    refs_id_forms = _string_list(refs_table, "id_forms", context="refs.id_forms")
    if len(refs_id_forms) > _ID_FORMS_MAX or not all(
        _id_form_is_valid(form) for form in refs_id_forms
    ):
        raise ConfigError(
            f"trueup.toml: refs.id_forms must be a list of at most {_ID_FORMS_MAX} "
            f'id forms of at most {_ID_FORM_MAX_LENGTH} characters, such as "D<n>.<m>"'
        )
    refs_accepted = _string_list(
        refs_table, "accepted_reader_changes", context="refs.accepted_reader_changes"
    )
    if not all(
        entry and _CHANGE_BANNED.search(entry) is None for entry in refs_accepted
    ):
        raise ConfigError(
            "trueup.toml: refs.accepted_reader_changes must be a list of change "
            "names with no white space and no comma"
        )

    languages = _parse_languages(raw.get("languages", {}))
    eslint_off = _parse_eslint(raw.get("eslint", {}))
    keep = _parse_keep(raw.get("keep", []))
    eslint_suppressions = _repo_path(
        raw.get("eslint", {}),
        "suppressions",
        _DEFAULT_ESLINT_SUPPRESSIONS,
        "eslint.suppressions",
    )

    return Config(
        version=version,
        run_date=run_date,
        tier=tier,
        public=public,
        docs=docs,
        stale_days=stale_days,
        ignore=ignore,
        protect=protect,
        root_allow=root_allow,
        scratch_allow=scratch_allow,
        layout_code_dirs=layout_code_dirs,
        binary_allow=binary_allow,
        refs_mode=refs_mode,
        refs_path=refs_path,
        refs_local_tags=refs_local_tags,
        refs_law_archive=refs_law_archive,
        refs_declared=refs_declared,
        refs_id_forms=refs_id_forms,
        refs_accepted_reader_changes=refs_accepted,
        refs_layout=refs_layout,
        languages=languages,
        eslint_off=eslint_off,
        keep=keep,
        profile=profile,
        layout_docs_dir=layout_docs_dir,
        layout_front_matter=layout_switches["front_matter"],
        layout_types=layout_switches["types"],
        layout_index=layout_switches["index"],
        prose_banned=prose_banned,
        prose_extra=prose_extra,
        refs_registry=refs_registry,
        refs_comments=refs_comments,
        refs_links=refs_links,
        root_base=root_base,
        health_agents=health_agents,
        health_files=health_files,
        scratch_gitignore=scratch_gitignore,
        guard_registry=guard_registry,
        guard_private_packages=guard_private_packages,
        eslint_suppressions=eslint_suppressions,
        python_pydoclint_baseline=python_pydoclint_baseline,
    )


def _table(value: Any, name: str, allowed: tuple[str, ...]) -> dict[str, Any]:
    """Check that one config table holds only its own keys (D14.2, D15.29).

    Args:
        value: The value read for the table key.
        name: The table name, for example `"refs"`.
        allowed: The keys the table can hold, in the order of the message.

    Returns:
        The table.

    Raises:
        ConfigError: The value is not a table, or a key is not in
            `allowed`. The message names the first such key in sort order.
    """
    if not isinstance(value, dict):
        raise ConfigError(f"trueup.toml: [{name}] must be a table")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        listed = ", ".join(repr(key) for key in allowed)
        raise ConfigError(
            f"trueup.toml: [{name}] {unknown[0]}: unknown key; allowed: {listed}"
        )
    return value


def _switch(table: dict[str, Any], key: str, name: str, default: bool = True) -> bool:
    """Read an on-off key that is on when absent, unless `default` says otherwise (D14.2, D15.32).

    Args:
        table: The mapping that may hold `key`.
        key: The key to read.
        name: The dotted name to use in an error message.
        default: The value when `key` is absent.

    Returns:
        The value, or `default` when `key` is absent.

    Raises:
        ConfigError: The value is present and is not a bool.
    """
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"trueup.toml: {name} must be true or false")
    return value


def _repo_path(table: dict[str, Any], key: str, default: str, name: str) -> str:
    """Read a repo-relative file path, such as `[eslint] suppressions` (D14.2).

    Args:
        table: The mapping that may hold `key`.
        key: The key to read.
        default: The value when `key` is absent.
        name: The dotted name to use in an error message.

    Returns:
        The path as written, or `default`.

    Raises:
        ConfigError: The value is not a string, is empty, starts with `/`,
            holds a backslash, or has an empty, `.` or `..` segment.
    """
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"trueup.toml: {name} must be a string")
    segments = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ConfigError(
            f"trueup.toml: {name} must be a relative path with no empty, '.' or "
            f"'..' part and no backslash, got {value!r}"
        )
    return value


def _parse_prose(
    raw: Any, source: Path | None, layer: str
) -> tuple[str, tuple[str, ...]]:
    """Validate the `[prose]` table (D14.2).

    Args:
        raw: The value read for the `prose` key.
        source: The path of the file that holds the table, or `None`.
        layer: `"target"`, `"profile"` or `"user"`.

    Returns:
        The `banned` value and the `extra` entries. A `banned` path stays
        as written for the target layer and is absolute for the others.

    Raises:
        ConfigError: The table holds another key, `banned` is not a string
            or names no file, or an `extra` entry is not in the
            `banned.txt` form.
    """
    raw = _table(raw, "prose", ("banned", "extra"))
    banned = raw.get("banned", "builtin")
    if not isinstance(banned, str):
        raise ConfigError(
            'trueup.toml: prose.banned must be "builtin", "off" or a path'
        )
    resolved = _resolve_banned(banned, source)
    extra = _string_list(raw, "extra", context="prose.extra")
    for entry in extra:
        _check_banned_entry(entry)
    return (banned if layer == "target" else resolved), extra


def _resolve_banned(value: str, source: Path | None) -> str:
    """Give the `[prose] banned` value with a path made absolute (D14.2).

    Args:
        value: `"builtin"`, `"off"` or a path.
        source: The config file that set the value. A relative path is
            relative to its directory; `None` means the current directory.

    Returns:
        `"builtin"` and `"off"` unchanged, or the absolute path of the file.

    Raises:
        ConfigError: The path names no file.
    """
    if value in _PROSE_LISTS:
        return value
    base = source.parent if source is not None else Path.cwd()
    path = (base / value).resolve()
    if not path.is_file():
        raise ConfigError(
            f"trueup.toml: prose.banned names {value!r}, but {path} is not a file"
        )
    return str(path)


def _check_banned_entry(entry: str) -> None:
    """Check one `[prose] extra` entry against the `banned.txt` form (D14.2, I-25).

    The form is one line: `word`, or `word => <regex>`.

    Args:
        entry: The entry as written.

    Raises:
        ConfigError: The entry is empty, holds a control character or a
            line break, has an empty word or regex, or its regex does not
            compile.
    """
    if not entry.strip() or any(
        ord(char) < 0x20 or char == "\x7f" or char in _LINE_BREAKS for char in entry
    ):
        raise ConfigError(
            f"trueup.toml: prose.extra entry {entry!r} must be one line that is not empty"
        )
    if " => " not in entry:
        return
    word, pattern = (part.strip() for part in entry.split(" => ", 1))
    if not word or not pattern:
        raise ConfigError(
            f"trueup.toml: prose.extra entry {entry!r} needs a word and a regex around ' => '"
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ConfigError(
            f"trueup.toml: prose.extra entry {entry!r} has a bad regex: {exc}"
        ) from exc


def resolve_docs(cfg: Config | None, tier: str) -> str:
    """Give the docs mode in force for one config and tier (D12.9).

    Args:
        cfg: The loaded config, or `None` when `trueup.toml` is absent.
        tier: The survey tier: `T0`, `T1`, `T2` or `T3`.

    Returns:
        An explicit `"full"` or `"readme"` unchanged. For `"auto"`, or no
        config, `"readme"` at T0 and T1 and `"full"` at T2 and T3.
    """
    docs = cfg.docs if cfg is not None else "auto"
    if docs != "auto":
        return docs
    return "full" if tier in _FULL_DOCS_TIERS else "readme"


def _validate_refs_path(path: str) -> None:
    """Validate a `[refs] path` value: a relative POSIX path ending in `.py` (D5.3).

    Args:
        path: The candidate value, read from `trueup.toml` or given as the
            default.

    Raises:
        ConfigError: `path` is empty, starts with `/`, does not end in
            `.py`, holds a backslash, or a `/`-separated segment of it is
            `.` or `..`.
    """
    if not path or path.startswith("/") or not path.endswith(".py"):
        raise ConfigError(
            f"trueup.toml: refs.path must be a relative path ending in .py, got {path!r}"
        )
    if "\\" in path:
        raise ConfigError(
            f"trueup.toml: refs.path must not hold a backslash, got {path!r}"
        )
    segments = path.split("/")
    if ".." in segments or "." in segments:
        raise ConfigError(
            f"trueup.toml: refs.path must not hold a '.' or '..' part, got {path!r}"
        )


_CHANGE_BANNED = re.compile(r"[\s,]")
"""The characters that a `[refs] accepted_reader_changes` name cannot hold (D16.3).

`trueup.ref_check` holds a copy of this rule. A test keeps the two equal.
"""


def _id_form_is_valid(form: str) -> bool:
    """Tell if one `[refs] id_forms` entry has the shape of D16.2.

    `trueup.ref_check` holds a copy of this rule, because this module does
    not import the checker. A test keeps the two copies equal.

    Args:
        form: The entry, for example `D<n>.<m>`.

    Returns:
        True when the form is at most 24 characters, holds no white space
        and no comma, holds one placeholder and one literal character or
        more, and no placeholder comes just before a digit or a placeholder.
    """
    return (
        len(form) <= _ID_FORM_MAX_LENGTH
        and _ID_FORM_BANNED.search(form) is None
        and _ID_FORM_HOLE.search(form) is not None
        and _ID_FORM_HOLE.sub("", form) != ""
        and _ID_FORM_GLUED.search(form) is None
    )


def _string_list(
    table: dict[str, Any], key: str, context: str | None = None
) -> tuple[str, ...]:
    """Read a list-of-strings value, defaulting to empty.

    Args:
        table: The mapping that may hold `key`.
        key: The key to read.
        context: The dotted name to use in an error message; `key` itself
            when not given.

    Returns:
        The value as a tuple of strings.

    Raises:
        ConfigError: The value is present and is not a list of strings.
    """
    value = table.get(key, [])
    name = context or key
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"trueup.toml: {name} must be a list of strings")
    return tuple(value)


def _parse_languages(raw: Any) -> dict[str, str]:
    """Validate the `[languages]` table.

    Args:
        raw: The value read for the `languages` key.

    Returns:
        Language name to mode, for the languages present in the file.

    Raises:
        ConfigError: A key is not a known language, or a value is not a
            known mode.
    """
    if not isinstance(raw, dict):
        raise ConfigError("trueup.toml: [languages] must be a table")
    languages: dict[str, str] = {}
    for name, mode in raw.items():
        if name not in LANGUAGES:
            raise ConfigError(
                f"trueup.toml: [languages] has an unknown language {name!r}"
            )
        if mode not in _LANGUAGE_MODES:
            raise ConfigError(
                f"trueup.toml: [languages].{name} must be one of {_LANGUAGE_MODES}, got {mode!r}"
            )
        languages[name] = mode
    return languages


def _parse_eslint(raw: Any) -> dict[str, str]:
    """Validate the `[eslint]` table and its `[[eslint.off]]` entries (D13.5).

    Args:
        raw: The value read for the `eslint` key.

    Returns:
        eslint rule name to the reason it is off.

    Raises:
        ConfigError: `[eslint]` holds a key other than `off` and
            `suppressions` (D14.2), an entry does
            not hold exactly `rule` and `reason`, the rule is not a rule
            name, the reason is empty or holds a line break or a control
            character, or a rule repeats.
    """
    raw = _table(raw, "eslint", ("off", "suppressions"))
    entries = raw.get("off", [])
    if not isinstance(entries, list):
        raise ConfigError("trueup.toml: eslint.off must be an array of tables")
    off: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"rule", "reason"}:
            raise ConfigError(
                "trueup.toml: each [[eslint.off]] entry needs exactly 'rule' and 'reason'"
            )
        rule, reason = entry["rule"], entry["reason"]
        if not isinstance(rule, str) or not _ESLINT_RULE.fullmatch(rule):
            raise ConfigError(
                "trueup.toml: [[eslint.off]] rule must be an eslint rule name, "
                f'for example "security/detect-object-injection", got {rule!r}'
            )
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(
                f"trueup.toml: [[eslint.off]] rule {rule!r} needs a reason that is not empty"
            )
        if any(
            ord(char) < 0x20 or char == "\x7f" or char in _LINE_BREAKS
            for char in reason
        ):
            raise ConfigError(
                f"trueup.toml: the reason of [[eslint.off]] rule {rule!r} must be one line"
            )
        if rule in off:
            raise ConfigError(f"trueup.toml: [[eslint.off]] repeats rule {rule!r}")
        off[rule] = reason
    return off


def _parse_keep(raw: Any) -> dict[str, str]:
    """Validate the `[[keep]]` array of tables.

    Args:
        raw: The value read for the `keep` key.

    Returns:
        Finding id to the reason a person declined it.

    Raises:
        ConfigError: An entry is missing `id` or `reason`, holds an extra
            key, or repeats an id already seen.
    """
    if not isinstance(raw, list):
        raise ConfigError("trueup.toml: keep must be an array of tables")
    keep: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"id", "reason"}:
            raise ConfigError(
                "trueup.toml: each [[keep]] entry needs exactly 'id' and 'reason'"
            )
        finding_id, reason = entry["id"], entry["reason"]
        if not isinstance(finding_id, str) or not isinstance(reason, str):
            raise ConfigError("trueup.toml: [[keep]] id and reason must be strings")
        if finding_id in keep:
            raise ConfigError(f"trueup.toml: [[keep]] repeats id {finding_id!r}")
        keep[finding_id] = reason
    return keep


def render(cfg: Config) -> str:
    """Render a `Config` to the text of `trueup.toml`.

    The text is the header comment, `version`, and then each key whose
    dotted name is in `cfg.explicit` or whose value differs from
    `Config()` (D14.3). There is no set of keys that is always written:
    `render(Config())` is the header and `version = 1`. A file that `load_target`
    read renders to the same keys it held, also a key at its default
    value. `render` reads no file, so it writes only the layer it gets
    (I-33). `apply` gives it the target layer.

    The key order is fixed and language and keep entries are sorted, so two
    renders of an equal `Config` give the same bytes (arch: D5.3, I-21).
    Every string value goes through `_toml_string`, so a glob, id or reason
    that holds a quote or backslash still round-trips through `tomllib`.
    A table header is written only when one of its keys is written. The
    `[languages]` header is also written when the file set the table, so
    a written file shows the table that `apply` fills. With
    `[refs] layout = false`, the three `[layout]` switches are not written,
    since `layout = false` sets them (D14.2). The `[[eslint.off]]` entries
    come after `[languages]`, sorted by rule (D13.5).

    Args:
        cfg: The configuration to render.

    Returns:
        The full text of `trueup.toml`, ending in a newline.
    """
    default = Config()
    lines: list[str] = [
        "# trueup configuration. The trueup skill writes this file. A person can edit it.",
        "# comments do not survive a config write; trueup writes this file",
        f"version = {cfg.version}",
    ]
    lines.extend(
        _wanted_lines(
            cfg,
            [
                (
                    "run_date",
                    cfg.run_date is not None,
                    f"run_date = {_toml_string(cfg.run_date or '')}",
                ),
                (
                    "profile",
                    cfg.profile is not None,
                    None
                    if cfg.profile is None
                    else f"profile = {_toml_string(cfg.profile)}                # house | minimal | a user profile (D14.1)",
                ),
                (
                    "tier",
                    cfg.tier != default.tier,
                    f"tier = {_toml_string(cfg.tier)}                # auto | T0 | T1 | T2 | T3",
                ),
                (
                    "public",
                    cfg.public != default.public,
                    f"public = {_toml_bool(cfg.public)}                # true adds C1, C2 and the public health files",
                ),
                (
                    "docs",
                    cfg.docs != default.docs,
                    f"docs = {_toml_string(cfg.docs)}                # auto | full | readme",
                ),
                (
                    "stale_days",
                    cfg.stale_days != default.stale_days,
                    f"stale_days = {cfg.stale_days}                # P8",
                ),
                (
                    "ignore",
                    bool(cfg.ignore),
                    f"ignore = {_toml_list(cfg.ignore)}   # globs left out of the survey and all findings",
                ),
                (
                    "protect",
                    bool(cfg.protect),
                    f"protect = {_toml_list(cfg.protect)}                 # globs that apply never changes or removes",
                ),
            ],
        )
    )
    _add_table(
        lines,
        "[root]",
        _wanted_lines(
            cfg,
            [
                (
                    "root.allow",
                    bool(cfg.root_allow),
                    f"allow = {_toml_list(cfg.root_allow)}                   # root entries allowed beyond the base list (D5.8)",
                ),
                (
                    "root.base",
                    cfg.root_base is not None,
                    f'base = "{_ROOT_BASE_CODE}"                   # the code list of the guard hook (D15.29)'
                    if cfg.root_base is None
                    else f"base = {_toml_list(cfg.root_base)}                   # replaces the base list of the guard hook (D14.2)",
                ),
            ],
        ),
    )
    _add_table(
        lines,
        "[scratch]",
        _wanted_lines(
            cfg,
            [
                (
                    "scratch.allow",
                    bool(cfg.scratch_allow),
                    f"allow = {_toml_list(cfg.scratch_allow)}                   # paths or names the scratch rule lets through (D5.8)",
                ),
                (
                    "scratch.gitignore",
                    cfg.scratch_gitignore != default.scratch_gitignore,
                    f"gitignore = {_toml_bool(cfg.scratch_gitignore)}                   # true: the .gitignore row asks for the .scratch/ line (D14.2)",
                ),
            ],
        ),
    )
    _add_table(
        lines,
        "[guard]",
        _wanted_lines(
            cfg,
            [
                (
                    "guard.registry",
                    cfg.guard_registry != default.guard_registry,
                    f"registry = {_toml_bool(cfg.guard_registry)}                   # true: the install guard looks up each package name on the public registry (D15.32)",
                ),
                (
                    "guard.private_packages",
                    bool(cfg.guard_private_packages),
                    f"private_packages = {_toml_list(cfg.guard_private_packages)}                   # package-name globs the install guard never looks up (D15.32)",
                ),
            ],
        ),
    )
    _add_table(lines, "[layout]", _layout_lines(cfg, default))
    _add_table(
        lines,
        "[binary]",
        _wanted_lines(
            cfg,
            [
                (
                    "binary.allow",
                    bool(cfg.binary_allow),
                    f"allow = {_toml_list(cfg.binary_allow)}                   # binary files kept on purpose (D13.2)",
                ),
            ],
        ),
    )
    _add_table(
        lines,
        "[prose]",
        _wanted_lines(
            cfg,
            [
                (
                    "prose.banned",
                    cfg.prose_banned != default.prose_banned,
                    f"banned = {_toml_string(cfg.prose_banned)}                   # builtin | off | a banned-word file (D14.2)",
                ),
                (
                    "prose.extra",
                    bool(cfg.prose_extra),
                    f"extra = {_toml_list(cfg.prose_extra)}                   # banned-word entries added to the list (D14.2)",
                ),
            ],
        ),
    )
    _add_table(lines, "[refs]", _refs_lines(cfg, default))
    _add_table(
        lines,
        "[health]",
        _wanted_lines(
            cfg,
            [
                (
                    "health.agents",
                    cfg.health_agents != default.health_agents,
                    f"agents = {_toml_bool(cfg.health_agents)}                   # true: the agent rules file rows run (D14.2)",
                ),
                (
                    "health.files",
                    cfg.health_files != default.health_files,
                    f'files = "{cfg.health_files}"                  # tier | readme: which health files are required (D15.14)',
                ),
            ],
        ),
    )
    _add_table(
        lines,
        "[python]",
        _wanted_lines(
            cfg,
            [
                (
                    "python.pydoclint_baseline",
                    cfg.python_pydoclint_baseline != default.python_pydoclint_baseline,
                    f"pydoclint_baseline = {_toml_string(cfg.python_pydoclint_baseline)}                   # the pydoclint baseline file (D14.2)",
                ),
            ],
        ),
    )
    if cfg.languages or "languages" in (cfg.explicit or ()):
        lines.append("")
        lines.append(
            "[languages]                  # one key per language: strict | clean | off"
        )
        for name in LANGUAGES:
            if name in cfg.languages:
                lines.append(f"{name} = {_toml_string(cfg.languages[name])}")
    _add_table(
        lines,
        "[eslint]",
        _wanted_lines(
            cfg,
            [
                (
                    "eslint.suppressions",
                    cfg.eslint_suppressions != default.eslint_suppressions,
                    f"suppressions = {_toml_string(cfg.eslint_suppressions)}                   # the eslint suppressions file (D14.2)",
                ),
            ],
        ),
    )
    for rule in sorted(cfg.eslint_off):
        lines.append("")
        lines.append(
            "[[eslint.off]]               # an eslint rule turned off, with the reason (D13.5)"
        )
        lines.append(f"rule = {_toml_string(rule)}")
        lines.append(f"reason = {_toml_string(cfg.eslint_off[rule])}")
    for finding_id in sorted(cfg.keep):
        lines.append("")
        lines.append(
            "[[keep]]                     # a finding the person declined, with the reason"
        )
        lines.append(f"id = {_toml_string(finding_id)}")
        lines.append(f"reason = {_toml_string(cfg.keep[finding_id])}")
    return "\n".join(lines) + "\n"


def _wanted_lines(
    cfg: Config, entries: list[tuple[str, bool, str | None]]
) -> list[str]:
    """Keep the lines of the keys that `render` writes (D14.3).

    Args:
        cfg: The configuration that `render` writes.
        entries: Per key, its dotted name, whether its value differs from
            the default, and its line. A line of `None` is a key with no
            value to write.

    Returns:
        The lines whose key is in `cfg.explicit` or differs from the
        default, in the order of `entries`.
    """
    explicit = cfg.explicit or frozenset()
    return [
        line
        for key, differs, line in entries
        if line is not None and (differs or key in explicit)
    ]


def _add_table(lines: list[str], header: str, body: list[str]) -> None:
    """Add a table to the rendered lines when it has a key to write.

    Args:
        lines: The rendered lines so far; the table goes at the end.
        header: The table header, for example `"[root]"`.
        body: The key lines of the table.
    """
    if body:
        lines.append("")
        lines.append(header)
        lines.extend(body)


def _layout_lines(cfg: Config, default: Config) -> list[str]:
    """Give the `[layout]` key lines that `render` writes (D13.1, D14.2).

    Args:
        cfg: The configuration that `render` writes.
        default: `Config()`, the values a key is compared with.

    Returns:
        The lines in their fixed order. The three switches are left out
        when `[refs] layout = false` sets them.
    """
    entries: list[tuple[str, bool, str | None]] = [
        (
            "layout.code_dirs",
            bool(cfg.layout_code_dirs),
            f"code_dirs = {_toml_list(cfg.layout_code_dirs)}                   # directories of Markdown-as-code, not pages (D13.1)",
        ),
        (
            "layout.docs_dir",
            cfg.layout_docs_dir != default.layout_docs_dir,
            f"docs_dir = {_toml_string(cfg.layout_docs_dir)}                   # the directory of the documentation pages (D14.2)",
        ),
    ]
    if cfg.refs_layout:
        entries += [
            (
                "layout.front_matter",
                cfg.layout_front_matter != default.layout_front_matter,
                f"front_matter = {_toml_bool(cfg.layout_front_matter)}                   # true: each page needs front matter (D14.2)",
            ),
            (
                "layout.types",
                cfg.layout_types != default.layout_types,
                f"types = {_toml_bool(cfg.layout_types)}                   # true: the pages sit in the Diataxis type directories (D14.2)",
            ),
            (
                "layout.index",
                cfg.layout_index != default.layout_index,
                f"index = {_toml_bool(cfg.layout_index)}                   # true: an index links each page (D14.2)",
            ),
        ]
    return _wanted_lines(cfg, entries)


def _refs_lines(cfg: Config, default: Config) -> list[str]:
    """Give the `[refs]` key lines that `render` writes (D8.7, D9.1, D9.4, D14.2, D16.13).

    Args:
        cfg: The configuration that `render` writes.
        default: `Config()`, the values a key is compared with.

    Returns:
        The lines in their fixed order.
    """
    layout_line = (
        "layout = true                   # check h on (D9.4)"
        if cfg.refs_layout
        else "layout = false                   # check h off: the pages keep their paths (D9.4)"
    )
    return _wanted_lines(
        cfg,
        [
            (
                "refs.mode",
                cfg.refs_mode != default.refs_mode,
                f"mode = {_toml_string(cfg.refs_mode)}                   # global: the hook runs trueup refs; copy: a checker copy at path (D9.1)",
            ),
            (
                "refs.path",
                cfg.refs_path != default.refs_path,
                f"path = {_toml_string(cfg.refs_path)}                   # the reference checker module, relative to the root",
            ),
            (
                "refs.local_tags",
                bool(cfg.refs_local_tags),
                f"local_tags = {_toml_list(cfg.refs_local_tags)}                   # the project's own tag prefixes (D8.7)",
            ),
            (
                "refs.law_archive",
                cfg.refs_law_archive is not None,
                None
                if cfg.refs_law_archive is None
                else f"law_archive = {_toml_string(cfg.refs_law_archive)}                   # the law archive, relative to the root or absolute (D16.13)",
            ),
            (
                "refs.declared",
                bool(cfg.refs_declared),
                f"declared = {_toml_list(cfg.refs_declared)}                   # the pages that declare the design ids (D16.2)",
            ),
            (
                "refs.id_forms",
                bool(cfg.refs_id_forms),
                f"id_forms = {_toml_list(cfg.refs_id_forms)}                   # the forms of a design id (D16.2)",
            ),
            (
                "refs.accepted_reader_changes",
                bool(cfg.refs_accepted_reader_changes),
                "accepted_reader_changes = "
                f"{_toml_list(cfg.refs_accepted_reader_changes)}                   # the reader changes that fail now, not warn (D16.3)",
            ),
            ("refs.layout", cfg.refs_layout != default.refs_layout, layout_line),
            (
                "refs.registry",
                cfg.refs_registry != default.refs_registry,
                f"registry = {_toml_bool(cfg.refs_registry)}                   # true: the checker runs its registry check (D14.2)",
            ),
            (
                "refs.comments",
                cfg.refs_comments != default.refs_comments,
                f"comments = {_toml_bool(cfg.refs_comments)}                   # true: the checker runs its comment check (D14.2)",
            ),
            (
                "refs.links",
                cfg.refs_links != default.refs_links,
                f"links = {_toml_bool(cfg.refs_links)}                   # true: the checker runs its link check (D14.2)",
            ),
        ],
    )


def _toml_bool(value: bool) -> str:
    """Render a Python bool as a TOML literal.

    Args:
        value: The bool to render.

    Returns:
        `"true"` or `"false"`.
    """
    return "true" if value else "false"


def toml_string(value: str) -> str:
    """Render a string as a TOML basic string, for another module's TOML file (D16.13).

    Args:
        value: The string.

    Returns:
        `_toml_string(value)`.
    """
    return _toml_string(value)


def toml_list(values: tuple[str, ...]) -> str:
    """Render a tuple of strings as a TOML array, for another module's TOML file (D8.7).

    Args:
        values: The strings.

    Returns:
        `_toml_list(values)`.
    """
    return _toml_list(values)


def _toml_list(values: tuple[str, ...]) -> str:
    """Render a tuple of strings as a single-line TOML array.

    Args:
        values: The strings to render, in order.

    Returns:
        A TOML array literal, e.g. `["a", "b"]` or `[]`.
    """
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


_TOML_ESCAPES: dict[str, str] = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _toml_string(value: str) -> str:
    r"""Render a Python string as a quoted TOML basic string.

    Escapes the backslash and double-quote characters, uses the short TOML
    escape for each common control character, and writes any other
    character below U+0020, and DEL (U+007F), as `\u00XX`, so a glob, id or reason that holds
    a quote or backslash still parses back with `tomllib` (arch: D5.3).

    Args:
        value: The raw string to render.

    Returns:
        The value wrapped in double quotes, with its contents escaped.
    """
    out: list[str] = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif ord(char) < 0x20 or char == "\x7f":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'
