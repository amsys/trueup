"""The sixteen rule sets: one per language, in `strict` and `clean` mode.

A rule set names the config files it needs (a path under the lint config
directory mapped to a template path under `trueup/templates/`), the lint
hooks it adds and the executables those hooks call. `managed.lint_hooks` reads `RULESETS`
for the languages that the effective config turns on, and `trueup lint`
runs those hooks (arch: D5.5, D14.6).

Every template path in a rule set's `files` mapping is relative to
`trueup/templates/` (so `"rules/python/ruff-clean.toml"` resolves under
`TEMPLATES_DIR`). The key on the other side of that mapping is relative
to the lint config directory, `cfgdir`: a temporary directory that
`trueup lint` makes for one run. Nothing goes under the target root
(I-47). In a template, the token `ROOT_TOKEN` stands for the absolute
target root; `trueup lint` replaces it when it writes the file.

A hook entry is a command line with four `str.format` fields: `{cfg}` is
`cfgdir`, `{eslint}` is the eslint package directory (D14.7), `{tools}` is
the tools directory of jscpd and sqlfluff (D15.5) and `{root}` is the
target root. No entry runs a shell. A file that the target owns
(the eslint suppressions file, the pydoclint baseline) goes on the command
line only when it exists; `owned_file_args` gives those arguments.

Most config files come from one template, copied as it is. The TypeScript
and Vue rule sets are the exception: both name the two `SHARED_TARGETS`,
and their templates are fragments. `render_eslint_config` and
`render_eslint_package` join the fragments of the enabled modes into one
file each. `render_jscpd` gives the duplication config for the strict
languages.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from trueup.config import LANGUAGES, Config

TEMPLATES_DIR: Path = Path(__file__).resolve().parent / "templates"
"""The directory that every template path in a `RuleSet.files` mapping is relative to."""

ROOT_TOKEN: str = "__TRUEUP_ROOT__"  # noqa: S105  # reason: a template placeholder, not a secret
"""The token in a template that `trueup lint` replaces with the absolute target root (D14.6).

The php templates use it for `paths`, `excludePaths` and `includes`:
phpstan resolves a relative path from the directory of its config file,
and that directory is `cfgdir`, not the root (D14.22 item 13)."""


def template_path(relative: str) -> Path:
    """Resolve a template path from a `RuleSet.files` mapping to a file on disk.

    Args:
        relative: A value of a `RuleSet.files` mapping, for example
            `"rules/python/ruff-clean.toml"`.

    Returns:
        The absolute path of the template file, under `TEMPLATES_DIR`.
    """
    return TEMPLATES_DIR / relative


@dataclass(frozen=True)
class Hook:
    """One lint hook that a rule set adds (D5.5, D14.6).

    Attributes:
        id: The hook id, unique within one `managed.lint_hooks` list.
        name: The human-readable name of the hook.
        entry: The command line the hook runs, with no file list appended.
            It holds the fields `{cfg}`, `{eslint}`, `{tools}` and `{root}` (see this
            module's docstring); `trueup lint` fills them with
            `str.format`, then splits the line with `shlex.split`.
        types_or: File types that select this hook, in `pre-commit`'s own
            names (for example `("markdown",)`), or empty to select by
            `files` instead.
        pass_filenames: Whether `trueup lint` appends the selected files to
            `entry`. `False` for a hook that always scans the whole tree.
        files: A regular expression narrowing which paths this hook sees,
            or the empty string for `pre-commit`'s default.
        exclude: A regular expression for paths this hook never sees, or
            the empty string for none.
    """

    id: str
    name: str
    entry: str
    types_or: tuple[str, ...] = ()
    pass_filenames: bool = True
    files: str = ""
    exclude: str = ""


@dataclass(frozen=True)
class RuleSet:
    """One language, in one mode, and everything it takes to lint it.

    Attributes:
        language: One of `trueup.config.LANGUAGES`.
        mode: `"strict"` or `"clean"`.
        files: Path under the lint config directory (`cfgdir`, D14.6) to
            template path (under `TEMPLATES_DIR`, see this module's
            docstring). Empty when the mode needs no config file beyond
            the linter's own defaults.
        hooks: The lint hooks this rule set adds, in run order.
        tools: The executables `hooks` call. A target repository missing
            one gives an `info` finding (D5.4) rather than a hard failure.
    """

    language: str
    mode: str
    files: dict[str, str]
    hooks: tuple[Hook, ...]
    tools: tuple[str, ...]


_PYTHON_HOOKS_BASE: tuple[Hook, ...] = (
    Hook(
        id="ruff-check",
        name="ruff check",
        entry="ruff check --config {cfg}/python/ruff.toml",
        types_or=("python", "pyi"),
    ),
    Hook(
        id="ruff-format",
        name="ruff format check",
        entry="ruff format --check --config {cfg}/python/ruff.toml",
        types_or=("python", "pyi"),
        # This default spares the root ref_check.py, the copy that
        # `[refs] mode = "copy"` writes byte for byte (I-26).
        exclude=r"^ref_check\.py$",
    ),
)

_RUST_CLEAN_CLIPPY = (
    "cargo clippy --all-targets --keep-going -- -D warnings -D missing_docs "
    "-D clippy::missing_safety_doc -D clippy::undocumented_unsafe_blocks "
    "-D clippy::allow_attributes_without_reason"
)

_RUST_STRICT_CLIPPY = (
    "env CLIPPY_CONF_DIR={cfg}/rust cargo clippy --all-targets --keep-going -- -D warnings "
    "-D missing_docs -D clippy::pedantic -D clippy::cognitive_complexity "
    "-D clippy::excessive_nesting -D clippy::missing_docs_in_private_items "
    "-D clippy::allow_attributes_without_reason -D clippy::allow_attributes "
    "-D clippy::undocumented_unsafe_blocks -D clippy::missing_errors_doc "
    "-D clippy::missing_panics_doc"
)

JSCPD_VERSION: str = "4.3.0"
"""The exact jscpd version that `trueup lint --install` installs (D15.5)."""

SQLFLUFF_VERSION: str = "4.3.0"
"""The exact sqlfluff version that `trueup lint --install` installs (D15.5)."""

JSCPD_BIN: str = "{tools}/node_modules/.bin/jscpd"
"""The jscpd executable in the tools directory (D15.5)."""

SQLFLUFF_BIN: str = "{tools}/sqlfluff/bin/sqlfluff"
"""The sqlfluff executable in the tools directory (D15.5)."""

SQLFLUFF_ENTRY: str = f"{SQLFLUFF_BIN} lint --config {{cfg}}/sql/.sqlfluff"
"""The sqlfluff hook entry of both SQL modes (D15.5)."""


def render_tools_manifest() -> str:
    """Give the text that names the tools of the tools directory (D15.5).

    The first 16 hex digits of its SHA-256 name the tools directory, so a
    new tool version gets a new directory.

    Returns:
        A JSON text with the exact versions of jscpd and sqlfluff.
    """
    return (
        json.dumps(
            {"jscpd": JSCPD_VERSION, "sqlfluff": SQLFLUFF_VERSION},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


ESLINT_RUN_CONFIG: str = f"run-{os.getpid()}.mjs"
"""The name of the eslint config that `trueup lint` writes into the eslint package directory (D14.7).

eslint 10 resolves a plugin from the directory of its config file, so the
config sits beside `node_modules`. The process id keeps two runs apart;
`trueup lint` removes the file when the run ends."""

# D13.6, D14.6: eslint 10 exits 2 and lints nothing when
# --suppressions-location names an absent file. The entry has no shell
# wrapper; `owned_file_args` adds the flag only when the file exists. A
# suppression that no longer occurs fails the hook (exit 2); the fix is
# --prune-suppressions, which the eslint message names.
_ESLINT_HOOK = Hook(
    id="eslint",
    name="eslint",
    entry=f"npx --prefix {{eslint}} eslint --config {{eslint}}/{ESLINT_RUN_CONFIG} --max-warnings 0",
    files=r"\.(ts|tsx|mts|cts|js|jsx|mjs|cjs|vue)$",
)

_VUE_TSC_HOOK = Hook(
    id="vue-tsc",
    name="vue-tsc",
    entry="npx --prefix {eslint} vue-tsc --noEmit",
    pass_filenames=False,
)

_KNIP_HOOK = Hook(
    id="knip",
    name="knip dead code",
    entry="npx --prefix {eslint} knip",
    pass_filenames=False,
)

ESLINT_CONFIG_TARGET = "lint/typescript/eslint.config.mjs"
"""Where an earlier trueup wrote the shared eslint config; a `managed.LEGACY_PATHS` entry now (D14.8)."""

ESLINT_PACKAGE_TARGET = "lint/typescript/package.json"
"""Where an earlier trueup wrote the shared package.json; a `managed.LEGACY_PATHS` entry now (D14.8, D14.22 item 10)."""

ESLINT_CONFIG_FILE = "typescript/eslint.config.mjs"
"""The `files` key of the eslint config fragments that the TypeScript and Vue rule sets share.

`trueup lint` writes the joined config as `ESLINT_RUN_CONFIG` into the
eslint package directory, not into `cfgdir` (D14.7)."""

ESLINT_PACKAGE_FILE = "typescript/package.json"
"""The `files` key of the package.json fragments that the TypeScript and Vue rule sets share.

`trueup lint --install` writes the joined file into the eslint package
directory (D14.7)."""

SHARED_TARGETS: frozenset[str] = frozenset({ESLINT_CONFIG_FILE, ESLINT_PACKAGE_FILE})
"""`files` keys whose templates are fragments: render them with `render_eslint_config` and `render_eslint_package`."""


def _eslint_files(language: str, mode: str) -> dict[str, str]:
    """Give the `files` mapping of one TypeScript or Vue rule set.

    Args:
        language: `"typescript"` or `"vue"`.
        mode: `"strict"` or `"clean"`.

    Returns:
        The two shared keys, mapped to this language's fragments.
    """
    return {
        ESLINT_CONFIG_FILE: f"rules/{language}/eslint-{mode}.block.mjs",
        ESLINT_PACKAGE_FILE: f"rules/{language}/package-{mode}.json",
    }


# D12.8, D14.6: pydoclint checks against the baseline only when the target
# has one; `owned_file_args` adds `--baseline`. trueup never writes the
# baseline (I-47): the person makes it with `--generate-baseline`.
_PYDOCLINT_ENTRY = (
    "pydoclint --style=google --arg-type-hints-in-docstring=False "
    "--check-return-types=False ."
)

_OWNED_FILE_FLAGS: dict[str, tuple[str, str]] = {
    "eslint": ("--suppressions-location", "eslint_suppressions"),
    "pydoclint": ("--baseline", "python_pydoclint_baseline"),
}
"""Hook id to the flag that names a target-owned file and the `Config` field that holds its repo path (D14.6)."""


def owned_file_args(hook: Hook, root: Path, cfg: Config) -> tuple[str, ...]:
    """Give the arguments that pass a target-owned file to a hook, when the file exists (I-47).

    The eslint hook takes the suppressions file (`cfg.eslint_suppressions`,
    D13.6) and the pydoclint hook takes the baseline
    (`cfg.python_pydoclint_baseline`, D12.8). Without the file the hook
    runs with no such flag: eslint 10 lints nothing when the suppressions
    file is absent, and trueup never writes either file.

    Args:
        hook: The hook to run.
        root: The target root; the run's working directory.
        cfg: The effective config, which names the file.

    Returns:
        The flag and the repo path of the file, or empty when the hook
        takes no such file or the file is not under the root.
    """
    flag_and_field = _OWNED_FILE_FLAGS.get(hook.id)
    if flag_and_field is None:
        return ()
    flag, field = flag_and_field
    path = getattr(cfg, field)
    if not os.path.isfile(root / path):
        return ()
    return (flag, path)


RULESETS: dict[tuple[str, str], RuleSet] = {
    ("python", "clean"): RuleSet(
        language="python",
        mode="clean",
        files={"python/ruff.toml": "rules/python/ruff-clean.toml"},
        hooks=_PYTHON_HOOKS_BASE,
        tools=("ruff",),
    ),
    ("python", "strict"): RuleSet(
        language="python",
        mode="strict",
        files={"python/ruff.toml": "rules/python/ruff-strict.toml"},
        hooks=_PYTHON_HOOKS_BASE
        + (
            Hook(
                id="vulture",
                name="vulture dead code",
                entry="vulture --min-confidence 80 .",
                pass_filenames=False,
            ),
            Hook(
                id="interrogate",
                name="interrogate docstring coverage",
                entry="interrogate --fail-under 100 --ignore-private --ignore-init-module .",
                pass_filenames=False,
            ),
            Hook(
                id="complexipy",
                name="complexipy cognitive complexity",
                entry="complexipy --max-complexity-allowed 15 .",
                pass_filenames=False,
            ),
            Hook(
                id="pydoclint",
                name="pydoclint docstring match",
                entry=_PYDOCLINT_ENTRY,
                pass_filenames=False,
            ),
        ),
        tools=("ruff", "vulture", "interrogate", "complexipy", "pydoclint"),
    ),
    ("rust", "clean"): RuleSet(
        language="rust",
        mode="clean",
        files={},
        hooks=(
            Hook(
                id="clippy",
                name="cargo clippy",
                entry=_RUST_CLEAN_CLIPPY,
                pass_filenames=False,
            ),
            Hook(
                id="fmt",
                name="cargo fmt check",
                entry="cargo fmt --all -- --check",
                pass_filenames=False,
            ),
        ),
        tools=("cargo",),
    ),
    ("rust", "strict"): RuleSet(
        language="rust",
        mode="strict",
        files={"rust/clippy.toml": "rules/rust/clippy-strict.toml"},
        hooks=(
            Hook(
                id="clippy",
                name="cargo clippy",
                entry=_RUST_STRICT_CLIPPY,
                pass_filenames=False,
            ),
            Hook(
                id="machete",
                name="cargo machete dead code",
                entry="cargo machete",
                pass_filenames=False,
            ),
            Hook(
                id="fmt",
                name="cargo fmt check",
                entry="cargo fmt --all -- --check",
                pass_filenames=False,
            ),
        ),
        tools=("cargo", "cargo-machete"),
    ),
    ("typescript", "clean"): RuleSet(
        language="typescript",
        mode="clean",
        files=_eslint_files("typescript", "clean"),
        hooks=(_ESLINT_HOOK,),
        tools=("npx",),
    ),
    ("typescript", "strict"): RuleSet(
        language="typescript",
        mode="strict",
        files=_eslint_files("typescript", "strict"),
        hooks=(_ESLINT_HOOK, _KNIP_HOOK),
        tools=("npx",),
    ),
    ("vue", "clean"): RuleSet(
        language="vue",
        mode="clean",
        files=_eslint_files("vue", "clean"),
        hooks=(_ESLINT_HOOK, _VUE_TSC_HOOK),
        tools=("npx",),
    ),
    ("vue", "strict"): RuleSet(
        language="vue",
        mode="strict",
        files=_eslint_files("vue", "strict"),
        hooks=(_ESLINT_HOOK, _VUE_TSC_HOOK, _KNIP_HOOK),
        tools=("npx",),
    ),
    ("shell", "clean"): RuleSet(
        language="shell",
        mode="clean",
        files={},
        hooks=(
            Hook(
                id="shellcheck",
                name="shellcheck",
                entry="shellcheck",
                types_or=("shell",),
            ),
        ),
        tools=("shellcheck",),
    ),
    ("shell", "strict"): RuleSet(
        language="shell",
        mode="strict",
        files={"shell/shellcheckrc": "rules/shell/shellcheckrc-strict"},
        hooks=(
            Hook(
                id="shellcheck",
                name="shellcheck",
                entry="shellcheck --rcfile {cfg}/shell/shellcheckrc --severity style",
                types_or=("shell",),
            ),
            Hook(
                id="shfmt",
                name="shfmt check",
                entry="shfmt -d -i 2 -ci -bn",
                types_or=("shell",),
            ),
        ),
        tools=("shellcheck", "shfmt"),
    ),
    ("sql", "clean"): RuleSet(
        language="sql",
        mode="clean",
        files={"sql/.sqlfluff": "rules/sql/sqlfluff-clean.cfg"},
        hooks=(
            Hook(
                id="sqlfluff",
                name="sqlfluff lint",
                entry=SQLFLUFF_ENTRY,
                types_or=("sql",),
            ),
        ),
        tools=("uvx",),
    ),
    ("sql", "strict"): RuleSet(
        language="sql",
        mode="strict",
        files={"sql/.sqlfluff": "rules/sql/sqlfluff-strict.cfg"},
        hooks=(
            Hook(
                id="sqlfluff",
                name="sqlfluff lint",
                entry=SQLFLUFF_ENTRY,
                types_or=("sql",),
            ),
        ),
        tools=("uvx",),
    ),
    ("go", "clean"): RuleSet(
        language="go",
        mode="clean",
        files={"go/golangci.yml": "rules/go/golangci-clean.yml"},
        hooks=(
            Hook(
                id="golangci-lint",
                name="golangci-lint",
                entry="golangci-lint run -c {cfg}/go/golangci.yml ./...",
                pass_filenames=False,
            ),
        ),
        tools=("golangci-lint",),
    ),
    ("go", "strict"): RuleSet(
        language="go",
        mode="strict",
        files={"go/golangci.yml": "rules/go/golangci-strict.yml"},
        hooks=(
            Hook(
                id="golangci-lint",
                name="golangci-lint",
                entry="golangci-lint run -c {cfg}/go/golangci.yml ./...",
                pass_filenames=False,
            ),
        ),
        tools=("golangci-lint",),
    ),
    ("php", "clean"): RuleSet(
        language="php",
        mode="clean",
        files={
            "php/phpstan.neon": "rules/php/phpstan-clean.neon",
            "php/phpcs.xml": "rules/php/phpcs-clean.xml",
            "php/phpmd.xml": "rules/php/phpmd-clean.xml",
        },
        hooks=(
            Hook(
                id="phpstan",
                name="phpstan analyse",
                entry="vendor/bin/phpstan analyse -c {cfg}/php/phpstan.neon",
                pass_filenames=False,
            ),
            Hook(
                id="phpcs",
                name="phpcs",
                entry="vendor/bin/phpcs --standard={cfg}/php/phpcs.xml",
                types_or=("php",),
            ),
            Hook(
                id="phpmd",
                name="phpmd",
                entry="vendor/bin/phpmd . text {cfg}/php/phpmd.xml --exclude vendor/,node_modules/",
                pass_filenames=False,
            ),
        ),
        tools=("php", "composer"),
    ),
    ("php", "strict"): RuleSet(
        language="php",
        mode="strict",
        files={
            "php/phpstan.neon": "rules/php/phpstan-strict.neon",
            "php/phpcs.xml": "rules/php/phpcs-strict.xml",
            "php/phpmd.xml": "rules/php/phpmd-strict.xml",
        },
        hooks=(
            Hook(
                id="phpstan",
                name="phpstan analyse",
                entry="vendor/bin/phpstan analyse -c {cfg}/php/phpstan.neon",
                pass_filenames=False,
            ),
            Hook(
                id="phpcs",
                name="phpcs",
                entry="vendor/bin/phpcs --standard={cfg}/php/phpcs.xml",
                types_or=("php",),
            ),
            Hook(
                id="phpmd",
                name="phpmd",
                entry="vendor/bin/phpmd . text {cfg}/php/phpmd.xml --exclude vendor/,node_modules/",
                pass_filenames=False,
            ),
        ),
        tools=("php", "composer"),
    ),
}
"""The sixteen rule sets: `trueup.config.LANGUAGES` (8) times `strict`/`clean` (arch: D5.5)."""

if set(RULESETS) != {
    (lang, mode) for lang in LANGUAGES for mode in ("strict", "clean")
}:
    raise RuntimeError("RULESETS must hold exactly one entry per language and mode")

JSCPD_TEMPLATE: str = "rules/jscpd.json"
"""The template path of the shared duplication config (under `TEMPLATES_DIR`)."""

JSCPD_FILE: str = "jscpd.json"
"""The path of the duplication config under `cfgdir`, the text of `render_jscpd` (D14.6)."""

JSCPD_HOOK: Hook = Hook(
    id="jscpd",
    name="jscpd duplication check",
    entry=f"{JSCPD_BIN} --config {{cfg}}/{JSCPD_FILE} .",
    pass_filenames=False,
)
"""The one duplication hook, run once when any enabled language is `strict` (D5.5).

`check` runs gitleaks for the `secret-content` row, so no lint hook runs
it (D14.6)."""

MANAGED_HEADER = "Managed by trueup. Edit trueup.toml, then run the trueup skill."
"""The header text every rendered file carries after its comment leader (D5.6)."""

_JSCPD_FORMATS: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "rust": ("rust",),
    "typescript": ("typescript", "javascript", "tsx", "jsx"),
    "vue": ("vue",),
    "shell": ("bash",),
    "sql": ("sql",),
    "go": ("go",),
    "php": ("php",),
}
"""The jscpd format names that cover each trueup language."""


def _fragment_body(relative: str) -> str:
    """Read an eslint fragment and drop its leading `//` comment lines.

    Args:
        relative: The fragment's template path, under `TEMPLATES_DIR`.

    Returns:
        The fragment text after its header comment, with no blank line at
        either end.
    """
    lines = template_path(relative).read_text(encoding="utf-8").splitlines()
    while lines and lines[0].startswith("//"):
        lines.pop(0)
    return "\n".join(lines).strip()


def _block_modes(typescript: str, vue: str) -> tuple[str, str | None]:
    """Choose the mode of the TypeScript block and of the Vue block.

    The TypeScript block is always present, because a Vue project's script
    code needs it. When TypeScript is `off`, the block takes Vue's mode.

    Args:
        typescript: The TypeScript mode: `strict`, `clean` or `off`.
        vue: The Vue mode: `strict`, `clean` or `off`.

    Returns:
        The TypeScript block mode, and the Vue block mode or None.

    Raises:
        ValueError: When both modes are `off`, or a mode is unknown.
    """
    for mode in (typescript, vue):
        if mode not in ("strict", "clean", "off"):
            raise ValueError(f"unknown mode: {mode!r}")
    if typescript == "off" and vue == "off":
        raise ValueError("the eslint files need TypeScript or Vue to be on")
    ts_mode = vue if typescript == "off" else typescript
    return ts_mode, (None if vue == "off" else vue)


def render_eslint_config(
    typescript: str, vue: str, off: Mapping[str, str] | None = None
) -> str:
    """Join the eslint fragments of the enabled modes into one flat config.

    When `off` holds rules, a last config object `offBlock` sets each of
    them to `"off"`, sorted by rule, with its reason as a comment on its
    line (D13.5). The object has no `files` key, so it applies to each
    file that an earlier block matches, and it comes last, so it wins.

    Args:
        typescript: The TypeScript mode: `strict`, `clean` or `off`.
        vue: The Vue mode: `strict`, `clean` or `off`.
        off: eslint rule name to the reason it is off, from the
            `[[eslint.off]]` entries of `trueup.toml`. None or empty adds
            no block.

    Returns:
        The text of the eslint config, `ESLINT_RUN_CONFIG` (D14.7).

    Raises:
        ValueError: When both modes are `off`, or a mode is unknown.
    """
    ts_mode, vue_mode = _block_modes(typescript, vue)
    vue_note = f" and the Vue block ({vue_mode} mode)" if vue_mode else ""
    parts = [
        f"// {MANAGED_HEADER}\n// eslint flat configuration: the TypeScript block ({ts_mode} mode){vue_note}.",
        _fragment_body(RULESETS[("typescript", ts_mode)].files[ESLINT_CONFIG_FILE]),
    ]
    blocks = "tsBlock"
    if vue_mode is not None:
        parts.append(
            _fragment_body(RULESETS[("vue", vue_mode)].files[ESLINT_CONFIG_FILE])
        )
        blocks = "tsBlock, ...vueBlocks"
    if off:
        parts.append(_off_block(off))
        blocks += ", offBlock"
    parts.append(f"export default tseslint.config({blocks});")
    return "\n\n".join(parts) + "\n"


def _off_block(off: Mapping[str, str]) -> str:
    """Give the `offBlock` config object for the `[[eslint.off]]` rules (D13.5).

    Args:
        off: eslint rule name to the reason it is off. Not empty. The
            config loader has checked each name and that each reason is
            one line.

    Returns:
        The JavaScript text of the `offBlock` constant.
    """
    lines = [
        "/** The rules that trueup.toml turns off ([[eslint.off]]), each with its reason. */",
        "const offBlock = {",
        "  rules: {",
    ]
    for rule in sorted(off):
        lines.append(f'    {json.dumps(rule)}: "off", // {off[rule]}')
    lines.extend(["  },", "};"])
    return "\n".join(lines)


def render_eslint_package(typescript: str, vue: str) -> str:
    """Join the package fragments of the enabled modes into one package.json.

    Args:
        typescript: The TypeScript mode: `strict`, `clean` or `off`.
        vue: The Vue mode: `strict`, `clean` or `off`.

    Returns:
        The text of the eslint package.json (D14.7), with sorted
        devDependencies and no header key (D5.6: a JSON file has none).

    Raises:
        ValueError: When both modes are `off`, or a mode is unknown.
    """
    ts_mode, vue_mode = _block_modes(typescript, vue)
    fragments = [RULESETS[("typescript", ts_mode)].files[ESLINT_PACKAGE_FILE]]
    if vue_mode is not None:
        fragments.append(RULESETS[("vue", vue_mode)].files[ESLINT_PACKAGE_FILE])
    dependencies: dict[str, str] = {}
    for fragment in fragments:
        dependencies.update(
            json.loads(template_path(fragment).read_text(encoding="utf-8"))[
                "devDependencies"
            ]
        )
    package = {
        "name": "trueup-lint-typescript",
        "private": True,
        "type": "module",
        "devDependencies": dict(sorted(dependencies.items())),
    }
    return json.dumps(package, indent=2) + "\n"


def render_jscpd(strict_languages: Iterable[str]) -> str:
    """Give `JSCPD_FILE` for the languages whose mode is `strict`.

    Args:
        strict_languages: The languages in `strict` mode. At least one.

    Returns:
        The jscpd config text: the shared thresholds, the formats of the
        strict languages, and the usual vendored and build paths ignored.

    Raises:
        ValueError: When `strict_languages` is empty or holds an unknown language.
    """
    languages = sorted(set(strict_languages))
    if not languages:
        raise ValueError("jscpd needs at least one strict language")
    unknown = [language for language in languages if language not in _JSCPD_FORMATS]
    if unknown:
        raise ValueError(f"unknown language: {unknown[0]!r}")
    config = json.loads(template_path(JSCPD_TEMPLATE).read_text(encoding="utf-8"))
    config.pop("//", None)
    config["format"] = sorted(
        {name for language in languages for name in _JSCPD_FORMATS[language]}
    )
    return json.dumps(config, indent=2) + "\n"


VALE_FILES: dict[str, str] = {
    "lint/vale/.vale.ini": "vale/.vale.ini",
    **{
        f"lint/vale/styles/Trueup/{name}.yml": f"vale/styles/Trueup/{name}.yml"
        for name in (
            "Banned",
            "Contractions",
            "FirstPerson",
            "Latin",
            "SentenceLength",
            "We",
            "Will",
        )
    },
    "lint/vale/styles/config/vocabularies/Trueup/accept.txt": "vale/styles/config/vocabularies/Trueup/accept.txt",
}
"""Old target path to template path for the Vale style (D5.6, D14.6, D14.8).

The keys are the paths where an earlier trueup wrote the style, so
`managed.LEGACY_PATHS` holds them. `trueup lint` writes each file to its
key without the `lint/` prefix under `cfgdir`, which gives
`{cfg}/vale/.vale.ini` for `VALE_HOOK`."""

VALE_HOOK: Hook = Hook(
    id="vale",
    name="vale prose check",
    entry="vale --config {cfg}/vale/.vale.ini",
    types_or=(
        "markdown",
        "python",
        "rust",
        "ts",
        "tsx",
        "javascript",
        "jsx",
        "go",
        "php",
    ),
)
"""The Vale hook: Markdown prose plus the comments of the source types Vale
lexes as code (D5.6, D8.6). Shell, SQL and Vue files are left to the `prose`
row of `check`: Vale reads them as plain text."""
