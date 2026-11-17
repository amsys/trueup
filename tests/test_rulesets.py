"""Tests for `trueup.rulesets`: the sixteen rule sets and their template files.

Every template a `RuleSet.files` mapping names is checked for existence and
for a header comment in the syntax of its own format. Where the tool a
hook calls is on the path (`ruff`, `cargo` for clippy, `shellcheck`,
`uv` for the local sqlfluff), the test also runs that hook's command, built the same
way `trueup lint` builds it (D14.6), against a tiny good sample (must pass)
and a tiny bad sample (must fail). The samples sit in a root directory
and the config files in a separate config directory, so no config file
is under the root (I-47). The eslint configs run on the eslint that
`lint/ts/node_modules` already holds, linked into a separate eslint
package directory (D14.7). A tool that is not on the path is skipped by
name, not treated as a failure.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from conftest import FIXTURES_ROOT, quoted_list_shapes
from trueup import lint
from trueup import rulesets as rulesets_module
from trueup import survey as survey_mod
from trueup.config import LANGUAGES, Config
from trueup.rulesets import (
    ESLINT_CONFIG_FILE,
    ESLINT_PACKAGE_FILE,
    ESLINT_RUN_CONFIG,
    JSCPD_FILE,
    JSCPD_HOOK,
    JSCPD_TEMPLATE,
    MANAGED_HEADER,
    ROOT_TOKEN,
    RULESETS,
    SHARED_TARGETS,
    TEMPLATES_DIR,
    VALE_FILES,
    VALE_HOOK,
    Hook,
    RuleSet,
    owned_file_args,
    render_eslint_config,
    render_eslint_package,
    render_jscpd,
)

REPO = Path(__file__).resolve().parent.parent
VALE_DIR = TEMPLATES_DIR / "vale"
CI_TEMPLATE = TEMPLATES_DIR / "ci" / "trueup.yml"

#: RULES.md rule 7's banned word and phrase list, transcribed here once so
#: this test does not depend on reading a file outside the repository. It
#: is the value `trueup/data/banned.txt` must hold, line for line (I-25).
CANONICAL_BANNED: tuple[str, ...] = (
    "idempotent",
    "upsert",
    "delve",
    "seamless",
    "robust",
    "comprehensive",
    "elevate",
    "unlock",
    "empower",
    "meticulous",
    "testament",
    "tapestry",
    "landscape",
    "realm",
    "embark",
    "journey",
    "crucial",
    "pivotal",
    "vital",
    "underscore",
    "foster",
    "facilitate",
    "navigate",
    "streamline",
    "cutting-edge",
    "game-changer",
    "holistic",
    "synergy",
    "paradigm",
    "notably",
    "moreover",
    "furthermore",
    "it's worth noting",
    "in today's world",
    "footgun",
    "battle-tested",
    "production-ready",
    "rock-solid",
    "bulletproof",
    "blazingly fast",
    "world-class",
    "best-in-class",
    "state-of-the-art",
    "next-level",
    "deep dive",
    "dive into",
    "unpack",
    "supercharge",
    "low-hanging fruit",
    "no-brainer",
    "silver bullet",
    "utilize",
    "plethora",
    "myriad",
    "aforementioned",
    "elegant",
    "elegantly",
    "simply put",
    "great question",
    "leverage",
)


def _header_ok(path: Path) -> bool:
    """Say whether a template file starts with the managed-file header of D4.4.

    The first line must be the header text behind the comment leader of the
    format: `#` for TOML/YAML/INI-family files and files with no
    extension, `//` for `.mjs`, `<!-- -->` for `.xml`. A `.json` file allows
    no comment, so its top-level `"//"` key must start with the header text.

    Args:
        path: The template file to check.

    Returns:
        True when the file opens with a manager header in its format.
    """
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("//", "")).startswith(MANAGED_HEADER)
    first = path.read_text(encoding="utf-8").split("\n", 1)[0]
    if path.suffix == ".mjs":
        return first == f"// {MANAGED_HEADER}"
    if path.suffix == ".xml":
        return first == f"<!-- {MANAGED_HEADER} -->"
    return first == f"# {MANAGED_HEADER}"


def test_sixteen_entries() -> None:
    """`RULESETS` holds exactly one entry per language and per mode.

    arch: D5.5
    """
    assert len(RULESETS) == 16
    assert set(RULESETS) == {
        (language, mode) for language in LANGUAGES for mode in ("strict", "clean")
    }
    for (language, mode), rule_set in RULESETS.items():
        assert isinstance(rule_set, RuleSet)
        assert rule_set.language == language
        assert rule_set.mode == mode
        assert rule_set.hooks, f"{language} {mode} has no hooks"
        assert all(isinstance(hook, Hook) for hook in rule_set.hooks)


def test_every_template_file_exists_and_has_a_header() -> None:
    """Every template a `RuleSet.files` mapping names exists and starts with a header.

    arch: D5.5
    """
    seen = 0
    for (language, mode), rule_set in RULESETS.items():
        for target, template in rule_set.files.items():
            path = TEMPLATES_DIR / template
            assert path.is_file(), (
                f"{language} {mode}: template {template!r} (for {target}) is missing"
            )
            assert _header_ok(path), (
                f"{language} {mode}: template {template!r} has no header"
            )
            seen += 1
    assert seen > 0


def test_jscpd_template_exists_and_has_a_header() -> None:
    """The shared duplication config exists, is valid JSON, and carries the header.

    arch: D5.5, D15.5
    """
    path = TEMPLATES_DIR / JSCPD_TEMPLATE
    assert path.is_file()
    assert _header_ok(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["threshold"] == 3
    assert data["minTokens"] == 100
    assert (
        JSCPD_HOOK.entry
        == "{tools}/node_modules/.bin/jscpd --config {cfg}/jscpd.json ."
    )
    assert "path" not in data
    assert data["gitignore"] is True
    assert JSCPD_FILE == "jscpd.json"


def test_ci_template_exists_and_has_no_header() -> None:
    """`templates/ci/trueup.yml` exists, has no managed header, and runs `trueup check` and `trueup lint`.

    D14.9: the person owns the workflow that `trueup template ci` prints,
    so the template has no header line and no pre-commit step.

    arch: D5.5, D14.9
    """
    assert CI_TEMPLATE.is_file()
    assert not _header_ok(CI_TEMPLATE)
    text = CI_TEMPLATE.read_text(encoding="utf-8")
    assert MANAGED_HEADER not in text
    assert "pre-commit" not in text
    assert "- run: trueup check --root .\n" in text
    assert "- run: trueup lint --root .\n" in text


def test_vale_style_files_exist_and_have_headers() -> None:
    """The Vale entry point and every Trueup style rule exist and have a header.

    arch: D5.5
    """
    ini = VALE_DIR / ".vale.ini"
    assert ini.is_file()
    assert _header_ok(ini)
    style_dir = VALE_DIR / "styles" / "Trueup"
    expected = {
        "Banned.yml",
        "SentenceLength.yml",
        "Contractions.yml",
        "Latin.yml",
        "We.yml",
        "FirstPerson.yml",
        "Will.yml",
    }
    names = {path.name for path in style_dir.glob("*.yml")}
    assert expected <= names
    for name in expected:
        assert _header_ok(style_dir / name), f"{name} has no header"
    vocab = VALE_DIR / "styles" / "config" / "vocabularies" / "Trueup" / "accept.txt"
    assert vocab.is_file()
    assert "trueup" in vocab.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def vale_dir(tmp_path: Path) -> Path:
    """Render the Vale style into `tmp_path` as `trueup lint` renders it (D14.6 step 3).

    The render function of the lint module writes the templates of
    `VALE_FILES` and the `Banned.yml` of `docrules.banned_words(Config())`
    into a config directory. The root is an empty directory beside it, so
    no config file is under the root (I-47).

    Args:
        tmp_path: The test's temporary directory.

    Returns:
        The rendered Vale directory, `{cfg}/vale`, which holds `.vale.ini`.
    """
    root = tmp_path / "vale-root"
    cfgdir = tmp_path / "vale-cfg"
    root.mkdir()
    cfgdir.mkdir()
    # D15.2: the survey reads tracked files, so the root is a repository
    # with one file.
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "README.md").write_text("# vale\n", encoding="utf-8")
    lint._render_configs(cfgdir, Config(), survey_mod.run(root), vale=True)
    return cfgdir / "vale"


_TOKEN_LINE = re.compile(r'^\s*-\s*"((?:[^"\\]|\\.)*)"\s*$')


def _banned_yml_tokens(vale_dir: Path) -> list[str]:
    r"""Extract the `tokens:` list of one `styles/Trueup/Banned.yml` copy.

    A tiny line-based reader is enough here: every token in the file this
    module ships is a double-quoted YAML scalar, one per line, which is
    exactly what the generator that built the file writes.

    Args:
        vale_dir: The Vale root directory to read from (`VALE_DIR` for the
            template copy, the `vale_dir` fixture for the copy that
            `trueup lint` renders).

    Returns:
        The tokens, in file order, with `\\"` unescaped back to `"`.
    """
    lines = (
        (vale_dir / "styles" / "Trueup" / "Banned.yml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    in_tokens = False
    tokens: list[str] = []
    for line in lines:
        if line.strip() == "tokens:":
            in_tokens = True
            continue
        if not in_tokens:
            continue
        match = _TOKEN_LINE.match(line)
        if match is None:
            break
        tokens.append(match.group(1).replace('\\"', '"'))
    return tokens


def test_i8_one_banned_list(vale_dir: Path) -> None:
    """`data/banned.txt`, the Vale `Banned.yml` tokens, and RULES rule 7 are one list.

    A `word => <regex>` form line (D6.9) names its word to the left of
    `=> `; that word is what RULES rule 7 lists, and the whole line (word or
    form) is the pattern both `Banned.yml` copies must carry, in order: the
    template and the copy that `trueup lint` renders from the list in force.

    arch: D5.5, D6.9, I-25, D14.6, D14.8
    """
    banned_txt = [
        line
        for line in (REPO / "trueup" / "data" / "banned.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    words = [line.split(" => ", 1)[0] for line in banned_txt]
    patterns = [
        line.split(" => ", 1)[1] if " => " in line else line for line in banned_txt
    ]
    assert words == list(CANONICAL_BANNED)
    assert _banned_yml_tokens(VALE_DIR) == patterns
    assert _banned_yml_tokens(vale_dir) == patterns


#: The D6.9 and D8.5 form fixtures (`tests/fixtures/docrules/forms/`): file
#: name, and whether its sentence must fire (the verb use) or stay silent
#: (the noun use, the plural noun `underscores` included).
_FORM_FIXTURES: tuple[tuple[str, bool], ...] = (
    ("noun-harness.py", False),
    ("verb-harness.py", False),
    ("noun-unlock.py", False),
    ("verb-unlock.py", True),
    ("noun-underscore.py", False),
    ("verb-underscore.py", True),
    ("plural-underscore.py", False),
    ("noun-underscore-leading.py", False),
    ("verb-underscore-passive.py", True),
    ("noun-underscore-that.py", False),
    ("verb-underscore-object.py", True),
    ("noun-leverage.py", False),
    ("verb-leverage.py", True),
    ("verb-leverage-subject.py", True),
)


@pytest.mark.parametrize("name,should_fire", _FORM_FIXTURES)
def test_vale_banned_forms_match_the_python_matcher(
    tmp_path: Path, vale_dir: Path, name: str, should_fire: bool
) -> None:
    """The real `vale` run agrees with the Python matcher on each D6.9 form fixture.

    Runs the `.vale.ini` that `trueup lint` renders against the same fixture files
    `tests/test_docrules.py`'s Python-matcher test reads, so both matchers
    are proven against one set of sentences (D6.9). Checks for the
    `Trueup.Banned` rule name in the output, not only the exit code, so a
    finding from an unrelated Vale style cannot make this test pass or fail
    for the wrong reason.

    arch: D6.9, D14.6, D14.8
    """
    if shutil.which("vale") is None:
        pytest.skip("tool not installed: vale")
    source = FIXTURES_ROOT / "docrules" / "forms" / f"{name}.txt"
    target = tmp_path / name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["vale", "--config", str(vale_dir / ".vale.ini"), str(target)],
        capture_output=True,
        text=True,
    )
    if should_fire:
        assert result.returncode != 0, result.stdout
        assert "Trueup.Banned" in result.stdout, result.stdout
    else:
        assert result.returncode == 0, result.stdout
        assert "Trueup.Banned" not in result.stdout, result.stdout


#: A word no dictionary or vocabulary file knows, used only in the two
#: sentences below so `Vale.Spelling` always has something to flag.
_UNKNOWN_WORD = "flurbotron"


def test_vale_markdown_spelling_is_a_warning_not_an_error(
    tmp_path: Path, vale_dir: Path
) -> None:
    """The `[*.md]` section of the rendered `.vale.ini` runs for real (D6.13, LOW-10).

    Every other Vale test in this module writes its fixture with a
    `.py` name, so it runs under the source-comment section
    (`Vale.Spelling = NO`) and never touches `[*.md]`, where LOW-10's
    fix (`Vale.Spelling = warning`) lives. This test writes `.md` files
    instead.

    A clean sentence with only the unknown word stays silent: the
    config's `MinAlertLevel = error` filters the warning-level spelling
    alert out of both the exit code and the report. Dropping the
    `Vale.Spelling = warning` line raises `vale`'s exit code on that
    same sentence; lowering `MinAlertLevel` below `error` puts
    `Vale.Spelling` back into the report even though the exit code
    stays 0. Either change fails this test. A banned word in the same
    file still fails on `Trueup.Banned`, proving the banned-word rule
    reaches `.md` files too, on the `BasedOnStyles = Vale, Trueup` path
    the `.py` fixtures never run.

    arch: D6.13, D6.15, D14.6, D14.8
    """
    if shutil.which("vale") is None:
        pytest.skip("tool not installed: vale")
    config = vale_dir / ".vale.ini"
    clean = tmp_path / "clean.md"
    clean.write_text(
        f"# Sample\n\nThe plan explains the {_UNKNOWN_WORD} adapter.\n",
        encoding="utf-8",
    )
    banned = tmp_path / "banned.md"
    banned.write_text(
        f"# Sample\n\nThe plan will utilize the {_UNKNOWN_WORD} adapter.\n",
        encoding="utf-8",
    )
    clean_result = subprocess.run(
        ["vale", "--config", str(config), str(clean)],
        capture_output=True,
        text=True,
    )
    assert clean_result.returncode == 0, clean_result.stdout
    assert "Vale.Spelling" not in clean_result.stdout, clean_result.stdout
    banned_result = subprocess.run(
        ["vale", "--config", str(config), str(banned)],
        capture_output=True,
        text=True,
    )
    assert banned_result.returncode != 0, banned_result.stdout
    assert "Trueup.Banned" in banned_result.stdout, banned_result.stdout


def _skip_if_missing(*tools: str) -> None:
    """Skip the current test, naming the first tool of `tools` that is not on the path.

    Args:
        tools: Executable names to check with `shutil.which`.
    """
    for tool in tools:
        if shutil.which(tool) is None:
            pytest.skip(f"tool not installed: {tool}")


def _write_tree(root: Path, files: dict[str, str]) -> None:
    """Write a small tree of text files under `root`.

    Args:
        root: The directory to write into. Created if absent.
        files: Relative path to file content, for each file to write.
    """
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Make a root directory and a separate config directory under `tmp_path`.

    Args:
        tmp_path: The test's temporary directory.

    Returns:
        The root, where the samples go and the hook runs, and `cfgdir`,
        where the config files go (D14.6). Neither holds the other.
    """
    root = tmp_path / "root"
    cfgdir = tmp_path / "cfg"
    root.mkdir(parents=True, exist_ok=True)
    cfgdir.mkdir(parents=True, exist_ok=True)
    return root, cfgdir


def _render_rule_files(rule_set: RuleSet, cfgdir: Path, root: Path) -> None:
    """Write the config files of one rule set under `cfgdir`, as `trueup lint` does (D14.6).

    The token `ROOT_TOKEN` in a template becomes the absolute root. The
    shared eslint fragments are left out: `render_eslint_config` joins them.

    Args:
        rule_set: The rule set whose `files` mapping is written.
        cfgdir: The config directory.
        root: The root that `ROOT_TOKEN` stands for.
    """
    _write_tree(
        cfgdir,
        {
            key: (TEMPLATES_DIR / template)
            .read_text(encoding="utf-8")
            .replace(ROOT_TOKEN, str(root))
            for key, template in rule_set.files.items()
            if key not in SHARED_TARGETS
        },
    )


def _argv(
    hook: Hook,
    cfgdir: Path,
    eslint_dir: Path | None = None,
    root: Path | None = None,
    tools_dir: Path | None = None,
) -> list[str]:
    """Give the argument list of a hook, with its fields filled as `trueup lint` fills them (D14.6).

    Args:
        hook: The hook to run.
        cfgdir: The value of the `{cfg}` field.
        eslint_dir: The value of the `{eslint}` field, or None for a hook
            that does not use it.
        root: The value of the `{root}` field, or None for a hook that
            does not use it.
        tools_dir: The value of the `{tools}` field, or None for a hook
            that does not use it.

    Returns:
        `shlex.split` of the filled entry, with no file appended.
    """
    return shlex.split(
        hook.entry.format(
            cfg=cfgdir,
            eslint=eslint_dir or "",
            root=root or "",
            tools=tools_dir or "",
        )
    )


def _eslint_dir(tmp_path: Path, typescript: str, vue: str) -> Path:
    """Make an eslint package directory outside the root, as D14.7 lays it out.

    The directory holds `package.json`, the run config `ESLINT_RUN_CONFIG`
    and a `node_modules` link to `lint/ts/node_modules`.

    Args:
        tmp_path: The test's temporary directory.
        typescript: The TypeScript mode.
        vue: The Vue mode.

    Returns:
        The eslint package directory.
    """
    eslint_dir = tmp_path / "eslint"
    _write_tree(
        eslint_dir,
        {
            ESLINT_RUN_CONFIG: render_eslint_config(typescript, vue),
            "package.json": render_eslint_package(typescript, vue),
        },
    )
    (eslint_dir / "node_modules").symlink_to(_LINT_TS_MODULES, target_is_directory=True)
    return eslint_dir


_GOOD_PY = '''"""Module header."""


def f(a: int) -> int:
    """Return a.

    Args:
        a: The value.

    Returns:
        The value.
    """
    return a
'''

_BAD_PY = '''"""Module header."""


def f(a):
    return a
'''


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_python_ruff_config_passes_good_fails_bad(tmp_path: Path, mode: str) -> None:
    """The rendered `ruff.toml` of each Python mode passes a documented function and fails an undocumented one.

    arch: D5.5
    """
    _skip_if_missing("ruff")
    rule_set = RULESETS[("python", mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "ruff-check")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    (root / "good.py").write_text(_GOOD_PY, encoding="utf-8")
    (root / "bad.py").write_text(_BAD_PY, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir) + ["good.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir) + ["bad.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout


_SECURITY_BAD_PY = '''"""Module header."""


def f() -> object:
    """Return a value read from standard input, run as code.

    Returns:
        The value that `eval` returns.
    """
    return eval(input())
'''


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_python_ruff_config_flags_a_security_bad_file(
    tmp_path: Path, mode: str
) -> None:
    """The rendered `ruff.toml` of each Python mode flags `eval(input())` and still passes the documented good function.

    arch: D7.5
    """
    _skip_if_missing("ruff")
    rule_set = RULESETS[("python", mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "ruff-check")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    (root / "good.py").write_text(_GOOD_PY, encoding="utf-8")
    (root / "bad.py").write_text(_SECURITY_BAD_PY, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir) + ["good.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir) + ["--output-format", "json", "bad.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout
    codes = [row["code"] for row in json.loads(bad.stdout)]
    assert any((code or "").startswith("S") for code in codes), bad.stdout


_GOOD_NESTED_PY = '''"""Module header."""


def f(rows: list[list[int]]) -> int:
    """Count the positive values, nested four levels deep.

    Args:
        rows: The values.

    Returns:
        The count.
    """
    count = 0
    for row in rows:
        for value in row:
            if value > 0:
                if value % 2:
                    count += 1
                else:
                    count += 2
            else:
                count -= 1
    return count
'''

_BAD_NESTED_PY = '''"""Module header."""


def f(rows: list[list[int]]) -> int:
    """Count the positive values, nested five levels deep.

    Args:
        rows: The values.

    Returns:
        The count.
    """
    count = 0
    for row in rows:
        for value in row:
            if value > 0:
                if value % 2:
                    for _ in range(value):
                        count += 1
                else:
                    count += 2
            else:
                count -= 1
    return count
'''

_SIX_PARAMS_PY = '''"""Module header."""


def f(a: int, b: int, c: int, d: int, e: int, g: int) -> int:
    """Return the sum.

    Args:
        a: A value.
        b: A value.
        c: A value.
        d: A value.
        e: A value.
        g: A value.

    Returns:
        The sum.
    """
    return a + b + c + d + e + g
'''


def test_python_strict_selects_every_rule_and_clean_keeps_the_defaults(
    tmp_path: Path,
) -> None:
    """Strict mode is the research strict set (`select = ["ALL"]`, 5 parameters); clean mode is ruff's defaults plus the standard.

    A documented six-parameter function passes clean and fails strict.
    An unused import fails both, which proves clean extends ruff's
    default rules rather than replacing them.

    arch: D5.5
    """
    _skip_if_missing("ruff")
    results: dict[tuple[str, str], int] = {}
    for mode in ("clean", "strict"):
        rule_set = RULESETS[("python", mode)]
        hook = next(hook for hook in rule_set.hooks if hook.id == "ruff-check")
        root, cfgdir = _dirs(tmp_path / mode)
        _render_rule_files(rule_set, cfgdir, root)
        _write_tree(
            root,
            {
                "six.py": _SIX_PARAMS_PY,
                "unused.py": '"""Module header."""\n\nimport os\n',
            },
        )
        for sample in ("six.py", "unused.py"):
            results[mode, sample] = subprocess.run(
                _argv(hook, cfgdir) + [sample],
                cwd=root,
                capture_output=True,
                text=True,
            ).returncode
    assert results["clean", "six.py"] == 0
    assert results["strict", "six.py"] != 0
    assert results["clean", "unused.py"] != 0
    assert results["strict", "unused.py"] != 0


def test_python_strict_ruff_config_enforces_the_nesting_threshold(
    tmp_path: Path,
) -> None:
    """The rendered strict `ruff.toml` passes 4 levels of nesting and fails 5, the research threshold (D5.5).

    Ruff's own default for PLR1702 is 5 levels, one looser than the shared
    threshold. Without `max-nested-blocks = 4`, the five-level sample
    would pass. The samples use `else` branches so that no other rule of
    `select = ["ALL"]` (such as SIM102) fires.

    arch: D5.5
    """
    _skip_if_missing("ruff")
    rule_set = RULESETS[("python", "strict")]
    hook = next(hook for hook in rule_set.hooks if hook.id == "ruff-check")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    (root / "good.py").write_text(_GOOD_NESTED_PY, encoding="utf-8")
    (root / "bad.py").write_text(_BAD_NESTED_PY, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir) + ["good.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir) + ["bad.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout


_GOOD_RS = """//! Give the sum of two numbers, for the trueup rule-set sample.

/// Give the sum of `a` and `b`.
#[must_use]
pub fn total(a: u32, b: u32) -> u32 {
    a + b
}
"""

_BAD_RS = """pub fn total(a: u32, b: u32) -> u32 {
    a + b
}
"""

_CARGO_TOML = """[package]
name = "trueup_sample"
version = "0.1.0"
edition = "2021"
"""


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_rust_clippy_config_passes_good_fails_bad(tmp_path: Path, mode: str) -> None:
    """The rendered clippy flags of each Rust mode pass a documented crate and fail an undocumented one.

    arch: D5.5
    """
    _skip_if_missing("cargo")
    rule_set = RULESETS[("rust", mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "clippy")
    for name, content in (("good", _GOOD_RS), ("bad", _BAD_RS)):
        crate, cfgdir = _dirs(tmp_path / name)
        _render_rule_files(rule_set, cfgdir, crate)
        _write_tree(crate, {"Cargo.toml": _CARGO_TOML, "src/lib.rs": content})
        result = subprocess.run(
            _argv(hook, cfgdir), cwd=crate, capture_output=True, text=True
        )
        if name == "good":
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout + result.stderr


_GOOD_SH = """#!/bin/sh
# purpose: demo for the trueup rule-set sample
echo "$1"
"""

_BAD_SH = """#!/bin/sh
# purpose: demo for the trueup rule-set sample
echo $1
"""


_GOOD_SH_SHFMT = """#!/bin/sh
# purpose: demo for the trueup shfmt test
case "$1" in
  foo)
    echo "foo"
    ;;
  *)
    echo "other"
    ;;
esac
"""

_BAD_SH_SHFMT = """#!/bin/sh
# purpose: demo for the trueup shfmt test
case "$1" in
    foo)
        echo "foo"
        ;;
    *)
        echo "other"
        ;;
esac
"""


def test_shell_strict_shfmt_config_passes_good_fails_bad(tmp_path: Path) -> None:
    """The strict shell rule set's `shfmt` hook passes a 2-space `case` block and fails a 4-space one.

    `shfmt -d` prints a diff and exits 1 when a file is not already in its
    own canonical form, so the bad sample only changes indentation.

    arch: D6.13, D6.15
    """
    _skip_if_missing("shfmt")
    rule_set = RULESETS[("shell", "strict")]
    hook = next(hook for hook in rule_set.hooks if hook.id == "shfmt")
    root, cfgdir = _dirs(tmp_path)
    (root / "good.sh").write_text(_GOOD_SH_SHFMT, encoding="utf-8")
    (root / "bad.sh").write_text(_BAD_SH_SHFMT, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir) + ["good.sh"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir) + ["bad.sh"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout + bad.stderr


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_shell_shellcheck_config_passes_good_fails_bad(
    tmp_path: Path, mode: str
) -> None:
    """The rendered shellcheck flags of each shell mode pass a quoted script and fail an unquoted one.

    arch: D5.5
    """
    _skip_if_missing("shellcheck")
    rule_set = RULESETS[("shell", mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "shellcheck")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    (root / "good.sh").write_text(_GOOD_SH, encoding="utf-8")
    (root / "bad.sh").write_text(_BAD_SH, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir) + ["good.sh"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir) + ["bad.sh"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout


_GOOD_SQL = """SELECT
    a,
    b
FROM t;
"""

_BAD_SQL = """select a,b from t;
"""


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_sql_sqlfluff_config_passes_good_fails_bad(tmp_path: Path, mode: str) -> None:
    """The rendered `.sqlfluff` of each SQL mode passes a laid-out query and fails a cramped one.

    The test makes the local sqlfluff environment of the tools directory
    from the uv cache, offline. It skips by name when that is not possible.

    arch: D5.5, D15.5
    """
    _skip_if_missing("uv")
    tools = tmp_path / "tools"
    tools.mkdir()
    setup = subprocess.run(
        ["uv", "venv", "-q", str(tools / "sqlfluff")], capture_output=True, text=True
    )
    if setup.returncode == 0:
        setup = subprocess.run(
            ["uv", "pip", "install", "--offline", "sqlfluff==4.3.0"],
            capture_output=True,
            text=True,
            env={**os.environ, "VIRTUAL_ENV": str(tools / "sqlfluff")},
        )
    if setup.returncode != 0:
        pytest.skip("sqlfluff 4.3.0 is not in the uv cache and the test runs offline")
    rule_set = RULESETS[("sql", mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "sqlfluff")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    (root / "good.sql").write_text(_GOOD_SQL, encoding="utf-8")
    (root / "bad.sql").write_text(_BAD_SQL, encoding="utf-8")
    good = subprocess.run(
        _argv(hook, cfgdir, tools_dir=tools) + ["good.sql"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir, tools_dir=tools) + ["bad.sql"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout


_GOOD_GO = (
    "// Package sample gives a small function for the trueup golangci-lint test.\n"
    "package sample\n"
    "\n"
    "// Total gives the sum of a and b.\n"
    "func Total(a, b int) int {\n"
    "\treturn a + b\n"
    "}\n"
)

_BAD_GO = "package sample\n\nfunc Total(a, b int) int {\n\treturn a + b\n}\n"

_GO_MOD = "module trueup_sample\n\ngo 1.21\n"


@pytest.mark.parametrize(("language", "mode"), [("go", "clean"), ("go", "strict")])
def test_go_golangci_lint_config_passes_good_fails_bad(
    tmp_path: Path, language: str, mode: str
) -> None:
    """The rendered golangci-lint config verifies silently, then passes a documented package and fails an undocumented one.

    `config verify` catches a schema mistake before `run` ever loads a
    package, so it runs first and must print nothing. `run`'s stderr must
    carry no `deprecated` warning, which proves the strict template's
    disabled `wsl` and `gomodguard` linters (D6.13) took effect; both
    modes enable `revive`'s `package-comments` and `exported` rules, so
    the bad sample fails on its missing comments in either mode.

    arch: D6.13, D6.15
    """
    _skip_if_missing("golangci-lint")
    rule_set = RULESETS[(language, mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "golangci-lint")
    for name, content in (("good", _GOOD_GO), ("bad", _BAD_GO)):
        root, cfgdir = _dirs(tmp_path / name)
        _render_rule_files(rule_set, cfgdir, root)
        _write_tree(root, {"go.mod": _GO_MOD, "main.go": content})
        verify = subprocess.run(
            [
                "golangci-lint",
                "config",
                "verify",
                "-c",
                str(cfgdir / "go/golangci.yml"),
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert verify.returncode == 0, verify.stdout + verify.stderr
        assert verify.stdout == "", verify.stdout
        assert verify.stderr == "", verify.stderr
        result = subprocess.run(
            _argv(hook, cfgdir), cwd=root, capture_output=True, text=True
        )
        assert "deprecated" not in result.stderr, result.stderr
        if name == "good":
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout + result.stderr


_GOOD_GO_SECURITY = (
    "// Package sample gives a small function for the trueup gosec test.\n"
    "package sample\n"
    "\n"
    "import (\n"
    '\t"context"\n'
    '\t"fmt"\n'
    '\t"os/exec"\n'
    ")\n"
    "\n"
    "// Run runs a fixed command with no variable input.\n"
    "func Run() error {\n"
    '\tcmd := exec.CommandContext(context.Background(), "echo", "ok")\n'
    "\n"
    "\terr := cmd.Run()\n"
    "\tif err != nil {\n"
    '\t\treturn fmt.Errorf("run command: %w", err)\n'
    "\t}\n"
    "\n"
    "\treturn nil\n"
    "}\n"
)

_BAD_GO_SECURITY = (
    "// Package sample gives a small function for the trueup gosec test.\n"
    "package sample\n"
    "\n"
    "import (\n"
    '\t"context"\n'
    '\t"fmt"\n'
    '\t"os"\n'
    '\t"os/exec"\n'
    ")\n"
    "\n"
    "// Run runs the command named on the command line, which gosec flags (G204).\n"
    "func Run() error {\n"
    "\tcmd := exec.CommandContext(context.Background(), os.Args[1])\n"
    "\n"
    "\terr := cmd.Run()\n"
    "\tif err != nil {\n"
    '\t\treturn fmt.Errorf("run command: %w", err)\n'
    "\t}\n"
    "\n"
    "\treturn nil\n"
    "}\n"
)


@pytest.mark.parametrize(("language", "mode"), [("go", "clean"), ("go", "strict")])
def test_go_golangci_lint_config_flags_a_security_bad_file(
    tmp_path: Path, language: str, mode: str
) -> None:
    """The rendered golangci-lint config flags `exec.Command(os.Args[1])` (gosec G204) and still passes a fixed command.

    Clean mode enables `gosec` explicitly; strict mode's `default: all`
    already enables it, since nothing in its `disable` list names it.
    gosec's taint analysis only flags a command built from a recognized
    source such as `os.Args`, so the bad sample reads its argument from
    there rather than from an ordinary function parameter.

    arch: D7.5
    """
    _skip_if_missing("golangci-lint")
    rule_set = RULESETS[(language, mode)]
    hook = next(hook for hook in rule_set.hooks if hook.id == "golangci-lint")
    for name, content in (("good", _GOOD_GO_SECURITY), ("bad", _BAD_GO_SECURITY)):
        root, cfgdir = _dirs(tmp_path / name)
        _render_rule_files(rule_set, cfgdir, root)
        _write_tree(root, {"go.mod": _GO_MOD, "main.go": content})
        result = subprocess.run(
            _argv(hook, cfgdir), cwd=root, capture_output=True, text=True
        )
        if name == "good":
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout + result.stderr
            assert "gosec" in result.stdout, result.stdout


def _composer_global_vendor_dir() -> Path | None:
    """Give the composer global vendor directory, or None when it cannot be found.

    Returns:
        The absolute path `composer global config vendor-dir --absolute`
        prints, or None when `php` or `composer` is not on the path, or
        the command fails.
    """
    if shutil.which("php") is None or shutil.which("composer") is None:
        return None
    result = subprocess.run(
        ["composer", "global", "config", "vendor-dir", "--absolute"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


_PHP_TOOLS: tuple[str, ...] = ("phpstan", "phpcs", "phpmd")

_GOOD_PHP = """<?php
/**
 * Trueup sample file, used to test the rendered phpcs config.
 *
 * @package    TrueupSample
 * @subpackage Calculator
 * @author     Squiz Pty Ltd <products@squiz.net>
 * @copyright  2026 Squiz Pty Ltd (ABN 77 084 670 600)
 * @license    MIT
 * @link       https://example.com
 */

namespace TrueupSample;

/**
 * Give a small function for the trueup phpstan test.
 */
final class Calculator
{
    /**
     * Give the sum of a and b.
     *
     * @param integer $a The first value.
     * @param integer $b The second value.
     *
     * @return integer The sum.
     */
    public function total(int $a, int $b): int
    {
        return $a + $b;
    }//end total()
}//end class
"""

_BAD_PHP = """<?php

namespace TrueupSample;

class Calculator
{
    public function total($a, $b)
    {
        $unused = 42;
        return $a + $b;
    }
}
"""


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_php_tools_config_passes_good_fails_bad(tmp_path: Path, mode: str) -> None:
    """The rendered phpstan, phpcs and phpmd configs of each PHP mode pass a documented class and fail an undocumented one.

    `vendor` is a symlink to the composer global vendor directory
    (run-wide fact 6: the owner approved a global
    `phpstan/phpstan-strict-rules` install for this task), so
    `vendor/bin/<tool>` and, for strict phpstan,
    `vendor/phpstan/phpstan-strict-rules/rules.neon` resolve with no
    project-local `composer install`. The bad sample fails phpstan (no
    parameter or return types), phpcs (no doc comments) and phpmd (an
    unused local variable) in both modes.

    arch: D6.13, D6.15
    """
    vendor_dir = _composer_global_vendor_dir()
    if vendor_dir is None:
        pytest.skip("tool not installed: composer (global vendor dir)")
    for tool in _PHP_TOOLS:
        if not (vendor_dir / "bin" / tool).exists():
            pytest.skip(
                f"tool not installed: vendor/bin/{tool} (composer global vendor)"
            )
    rule_set = RULESETS[("php", mode)]
    for name, content in (("good", _GOOD_PHP), ("bad", _BAD_PHP)):
        root, cfgdir = _dirs(tmp_path / mode / name)
        _render_rule_files(rule_set, cfgdir, root)
        _write_tree(root, {"Calculator.php": content})
        (root / "vendor").symlink_to(vendor_dir, target_is_directory=True)
        for tool in _PHP_TOOLS:
            hook = next(hook for hook in rule_set.hooks if hook.id == tool)
            args = _argv(hook, cfgdir)
            if hook.pass_filenames:
                args.append("Calculator.php")
            result = subprocess.run(args, cwd=root, capture_output=True, text=True)
            if name == "good":
                assert result.returncode == 0, (
                    f"{mode} {tool}: {result.stdout}{result.stderr}"
                )
            else:
                assert result.returncode != 0, f"{mode} {tool}: expected a failure"


_GOOD_TS = """/**
 * Give the sum.
 * @param a - The first value.
 * @param b - The second value.
 * @returns The sum.
 */
export function total(a: number, b: number): number {
  return a + b;
}
"""

_BAD_TS = """export function total(a: any, b: number): number {
  // @ts-ignore
  return a + b;
}
"""

_LINT_TS_MODULES = REPO / "lint" / "ts" / "node_modules"


def test_typescript_clean_eslint_config_passes_good_fails_bad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rendered clean eslint config passes a documented function and fails an undocumented `any` one.

    `lint/ts/node_modules` holds eslint, typescript-eslint, jsdoc and
    eslint-comments: the whole clean dependency set. The test links it into
    an eslint package directory outside the root (D14.7), so the hook's own
    `npx --prefix` command finds eslint with no install, and the config
    outside the root still lints the files under it (D14.22 item 11).

    arch: D5.5, D14.6, D14.7, D14.22
    """
    _skip_if_missing("npx")
    if not (_LINT_TS_MODULES / "eslint").is_dir():
        pytest.skip("tool not installed: eslint (lint/ts/node_modules)")
    monkeypatch.setenv("npm_config_offline", "true")
    root, cfgdir = _dirs(tmp_path)
    eslint_dir = _eslint_dir(tmp_path, "clean", "off")
    _write_tree(root, {"good.ts": _GOOD_TS, "bad.ts": _BAD_TS})
    hook = next(
        hook for hook in RULESETS[("typescript", "clean")].hooks if hook.id == "eslint"
    )
    good = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["good.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["bad.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout + bad.stderr
    for rule in (
        "jsdoc/require-jsdoc",
        "@typescript-eslint/no-explicit-any",
        "@typescript-eslint/ban-ts-comment",
    ):
        assert rule in bad.stdout


_GOOD_TS_STRICT = """/**
 * @file Give the sum, for the trueup rule-set sample.
 */

/**
 * Give the sum.
 * @param a - The first value.
 * @param b - The second value.
 * @returns The sum.
 */
export function total(a: number, b: number): number {
  return a + b;
}
"""

_TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true
  },
  "include": ["*.ts"]
}
"""


def test_typescript_strict_eslint_config_passes_good_fails_bad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rendered strict eslint config passes a typed, documented function and fails an `any`-typed, undocumented one.

    A `tsconfig.json` gives `strictTypeChecked` the project it needs. The
    bad sample is the same `_BAD_TS` the clean test uses, so passing here
    proves the strict block still bans `any` and `@ts-ignore` and, being
    strict only, also demands a file overview comment
    (`jsdoc/require-file-overview`).

    arch: D6.13, D6.15
    """
    _skip_if_missing("npx")
    if not (_LINT_TS_MODULES / "eslint-plugin-sonarjs").is_dir():
        pytest.skip("tool not installed: eslint-plugin-sonarjs (lint/ts/node_modules)")
    monkeypatch.setenv("npm_config_offline", "true")
    root, cfgdir = _dirs(tmp_path)
    eslint_dir = _eslint_dir(tmp_path, "strict", "off")
    _write_tree(
        root,
        {"tsconfig.json": _TSCONFIG, "good.ts": _GOOD_TS_STRICT, "bad.ts": _BAD_TS},
    )
    hook = next(
        hook for hook in RULESETS[("typescript", "strict")].hooks if hook.id == "eslint"
    )
    good = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["good.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["bad.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout + bad.stderr


_SECURITY_BAD_TS = """/**
 * Evaluate the given code string, which a SAST check must flag.
 * @param code - The code to run.
 * @returns Whatever the expression gives.
 */
export function run(code: string): unknown {
  return eval(code);
}
"""

_SECURITY_BAD_TS_STRICT = (
    """/**
 * @file Evaluate code, for the trueup SAST test (D7.5).
 */

"""
    + _SECURITY_BAD_TS
)


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_typescript_eslint_config_flags_a_security_bad_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The rendered eslint config of each TypeScript mode flags `eval(x)` and still passes the documented good function.

    `eslint-plugin-security`'s recommended rules run at `warn` severity;
    the `eslint` hook's `--max-warnings 0` turns that warning into a
    failed run. The good sample is the one the comment-standard test
    above uses, so passing here proves the new plugin adds no false
    positive on ordinary code.

    arch: D7.5
    """
    _skip_if_missing("npx")
    if not (_LINT_TS_MODULES / "eslint-plugin-security").is_dir():
        pytest.skip("tool not installed: eslint-plugin-security (lint/ts/node_modules)")
    monkeypatch.setenv("npm_config_offline", "true")
    good = _GOOD_TS if mode == "clean" else _GOOD_TS_STRICT
    bad = _SECURITY_BAD_TS if mode == "clean" else _SECURITY_BAD_TS_STRICT
    root, cfgdir = _dirs(tmp_path)
    eslint_dir = _eslint_dir(tmp_path, mode, "off")
    files = {"good.ts": good, "bad.ts": bad}
    if mode == "strict":
        files["tsconfig.json"] = _TSCONFIG
    _write_tree(root, files)
    hook = next(
        hook for hook in RULESETS[("typescript", mode)].hooks if hook.id == "eslint"
    )
    good_result = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["good.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad_result = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["bad.ts"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good_result.returncode == 0, good_result.stdout + good_result.stderr
    assert bad_result.returncode != 0, bad_result.stdout + bad_result.stderr
    assert "security/detect-eval-with-expression" in bad_result.stdout, (
        bad_result.stdout
    )


_GOOD_VUE = """<template>
  <div>{{ msg }}</div>
</template>

<script lang="ts">
export default {
  props: {
    msg: { type: String, required: true },
  },
};
</script>
"""

_BAD_VUE_CLEAN = """<template>
  <div v-for="item in items">{{ item }}</div>
</template>

<script lang="ts">
export default {
  props: {
    items: { type: Array, required: true },
  },
};
</script>
"""

_BAD_VUE_STRICT = """<template>
  <div>{{ msg }}</div>
</template>

<script>
export default {
  props: {
    msg: { type: String, required: true },
  },
};
</script>
"""


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_vue_eslint_config_passes_good_fails_bad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The rendered Vue eslint config of each mode passes a compliant component and fails one with a mode-specific defect.

    Clean fails on a `v-for` with no `:key` (`flat/essential`); strict
    also requires a TypeScript `<script>` block (`vue/block-lang`), so the
    strict bad sample drops `lang="ts"` instead. Both files use a
    multi-word name so `vue/multi-word-component-names` does not fire on
    the good sample.

    arch: D6.13, D6.15
    """
    _skip_if_missing("npx")
    if not (_LINT_TS_MODULES / "eslint-plugin-vue").is_dir():
        pytest.skip("tool not installed: eslint-plugin-vue (lint/ts/node_modules)")
    monkeypatch.setenv("npm_config_offline", "true")
    bad_vue = _BAD_VUE_CLEAN if mode == "clean" else _BAD_VUE_STRICT
    root, cfgdir = _dirs(tmp_path)
    eslint_dir = _eslint_dir(tmp_path, "off", mode)
    _write_tree(root, {"good-sample.vue": _GOOD_VUE, "bad-sample.vue": bad_vue})
    hook = next(hook for hook in RULESETS[("vue", mode)].hooks if hook.id == "eslint")
    good = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["good-sample.vue"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        _argv(hook, cfgdir, eslint_dir) + ["bad-sample.vue"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert bad.returncode != 0, bad.stdout + bad.stderr


_MODES = ("strict", "clean", "off")


@pytest.mark.parametrize(
    ("typescript", "vue"),
    [(t, v) for t in _MODES for v in _MODES if (t, v) != ("off", "off")],
)
def test_every_eslint_combination_renders_valid_javascript(
    tmp_path: Path, typescript: str, vue: str
) -> None:
    """Each TypeScript and Vue mode pair renders one config that parses, with one header and the right blocks.

    The fragments share one file (D5.5), so a pair that declared a name
    twice would be a syntax error; `node --check` catches it.

    arch: D5.5
    """
    text = render_eslint_config(typescript, vue)
    lines = text.splitlines()
    assert lines[0] == f"// {MANAGED_HEADER}"
    assert text.count(MANAGED_HEADER) == 1
    ts_mode = vue if typescript == "off" else typescript
    assert ("strictTypeChecked" in text) == (ts_mode == "strict")
    assert ("pluginVue" in text) == (vue != "off")
    assert ('"flat/recommended"' in text) == (vue == "strict")
    assert lines[-1] == (
        "export default tseslint.config(tsBlock);"
        if vue == "off"
        else "export default tseslint.config(tsBlock, ...vueBlocks);"
    )
    assert "max-statements" not in text
    if ts_mode == "strict":
        assert '"max-lines": ["error", 1000]' in text
    _skip_if_missing("node")
    config = tmp_path / "eslint.config.mjs"
    config.write_text(text, encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(config)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_eslint_package_follows_the_blocks() -> None:
    """The rendered package.json holds sonarjs only for a strict block and the Vue packages only when Vue is on.

    arch: D5.5
    """
    clean = json.loads(render_eslint_package("clean", "off"))["devDependencies"]
    strict_vue = json.loads(render_eslint_package("strict", "strict"))[
        "devDependencies"
    ]
    assert "eslint-plugin-sonarjs" not in clean
    assert "eslint-plugin-vue" not in clean
    assert {"eslint", "typescript-eslint", "eslint-plugin-jsdoc"} <= set(clean)
    assert {
        "eslint-plugin-sonarjs",
        "eslint-plugin-vue",
        "vue-eslint-parser",
        "vue-tsc",
        "knip",
    } <= set(strict_vue)
    assert list(strict_vue) == sorted(strict_vue)
    assert "//" not in json.loads(render_eslint_package("clean", "clean"))
    with pytest.raises(ValueError, match="TypeScript or Vue"):
        render_eslint_package("off", "off")


def test_shared_targets_are_only_named_by_typescript_and_vue() -> None:
    """Only the TypeScript and Vue rule sets name a shared key, and every other key has one owner per mode.

    D14.6: a key is a relative path under `cfgdir`, with no `lint/` prefix.

    arch: D5.5, D14.6
    """
    owners: dict[tuple[str, str], str] = {}
    for (language, mode), rule_set in RULESETS.items():
        for target in rule_set.files:
            assert not target.startswith(("lint/", "/", "..")), (
                f"{language} {mode}: {target} is not a path under cfgdir (D14.6)"
            )
            if target in SHARED_TARGETS:
                assert language in ("typescript", "vue")
                continue
            assert owners.setdefault((target, mode), language) == language


def test_hooks_that_take_filenames_are_filtered() -> None:
    """A hook that receives file names also names the file types or pattern it lints.

    Without a filter, pre-commit passes every changed file, and a linter
    fails on a file of another language.

    arch: D5.5
    """
    for (language, mode), rule_set in RULESETS.items():
        for hook in rule_set.hooks:
            if hook.pass_filenames:
                assert hook.types_or or hook.files, (
                    f"{language} {mode}: hook {hook.id} has no filter"
                )
    assert VALE_HOOK.types_or[0] == "markdown"


def test_jscpd_renders_the_strict_formats() -> None:
    """`render_jscpd` keeps the shared thresholds, drops the header key, and lists the strict formats.

    arch: D5.5
    """
    data = json.loads(render_jscpd(["vue", "python", "python"]))
    assert data["threshold"] == 3
    assert data["minTokens"] == 100
    assert data["exitCode"] == 1
    assert data["format"] == ["python", "vue"]
    assert "//" not in data
    with pytest.raises(ValueError, match="at least one"):
        render_jscpd([])


def test_vale_files_all_exist() -> None:
    """Every Vale template that `VALE_FILES` maps exists, and its old target path is `lint/` plus the template path.

    So `trueup lint` writes each file to `{cfg}/vale/`, where `VALE_HOOK`
    reads `.vale.ini`.

    arch: D5.5, D14.6, D14.8
    """
    for target, template in VALE_FILES.items():
        assert template.startswith("vale/"), template
        assert target == f"lint/{template}", target
        assert (TEMPLATES_DIR / template).is_file(), template


def test_no_template_carries_a_design_id() -> None:
    """No template holds a design-id marker: the target's ref_check would look it up in the target's own design.

    arch: D5.5
    """
    for path in sorted(TEMPLATES_DIR.rglob("*")):
        if path.is_file():
            assert "arch" + ":" not in path.read_text(encoding="utf-8"), path


#: The extensions Vale lexes as code, so that only their comments are checked
#: (D8.6). Tested on 2026-10-07 with a comment and a string literal per
#: extension: mjs, cjs, mts, cts, sh, sql and vue were read as plain text,
#: and no `[formats]` or `Lang` setting changed that.
_VALE_CODE_EXTENSIONS = frozenset({"py", "rs", "ts", "tsx", "js", "jsx", "go", "php"})


def test_vale_source_section_lists_only_the_extensions_vale_lexes() -> None:
    """The template's source section names the eight extensions Vale lexes, and the hook's types agree (D8.6).

    arch: D8.6
    """
    text = (VALE_DIR / ".vale.ini").read_text(encoding="utf-8")
    sections = re.findall(r"^\[\*\.\{([^}]*)\}\]", text, re.MULTILINE)
    assert len(sections) == 1, "one source-comment section"
    assert set(sections[0].split(",")) == _VALE_CODE_EXTENSIONS
    assert set(VALE_HOOK.types_or) == {
        "markdown",
        "python",
        "rust",
        "ts",
        "tsx",
        "javascript",
        "jsx",
        "go",
        "php",
    }


@pytest.mark.parametrize(
    "name,text",
    [
        ("render.mjs", "await send('Page.{word}', {{ url }});\n"),
        ("run.sh", '#!/bin/sh\necho "a {word} literal"\n'),
        ("query.sql", "SELECT '{word}' AS word;\n"),
    ],
)
def test_vale_does_not_read_a_string_literal_of_an_unlexed_extension(
    tmp_path: Path, vale_dir: Path, name: str, text: str
) -> None:
    """A banned word in a string literal of an `.mjs`, `.sh` or `.sql` file gives no Vale alert (D8.6).

    Vale has no comment lexer for these extensions and read the whole file
    as prose (the target-rust run of 2026-10-07 failed on a DevTools method name). The
    template leaves them to the `prose` row of `check`. A `.js` comment
    with the same word still fires, as the control.

    arch: D8.6, D14.6, D14.8
    """
    if shutil.which("vale") is None:
        pytest.skip("tool not installed: vale")
    word = CANONICAL_BANNED[22]
    target = tmp_path / name
    target.write_text(text.format(word=word), encoding="utf-8")
    config = vale_dir / ".vale.ini"
    result = subprocess.run(
        ["vale", "--config", str(config), str(target)], capture_output=True, text=True
    )
    assert "Trueup.Banned" not in result.stdout, result.stdout
    control = tmp_path / "control.js"
    control.write_text(f"// {word} the tree\n", encoding="utf-8")
    result = subprocess.run(
        ["vale", "--config", str(config), str(control)], capture_output=True, text=True
    )
    assert "Trueup.Banned" in result.stdout, result.stdout


def test_vale_block_ignores_match_the_quoted_list_rule(
    tmp_path: Path, vale_dir: Path
) -> None:
    """A real `vale` run and the Python matcher agree on a page that quotes the list (D8.4).

    The page is the one `tests/test_docrules.py` builds: list items and a
    paragraph with a cue, then one real use. Vale's `BlockIgnores` of the
    `[*.md]` section holds the cue rule, so the quoted blocks give no
    alert and the real use gives one.

    arch: D8.4, D14.6, D14.8
    """
    if shutil.which("vale") is None:
        pytest.skip("tool not installed: vale")
    words = CANONICAL_BANNED[:5]
    page = (
        "# Rules\n\n"
        "- Prose is plain English: short sentences, active voice.\n"
        f"- Never use: {words[0]}, {words[1]}, {words[2]} or {words[3]} as verbs,\n"
        f"  and {words[4]}.\n"
        "- Tests use real files.\n\n"
        f"Comments and docs: no banned vocabulary ({words[0]}, {words[1]}, {words[2]}). Say\n"
        "the plain thing.\n\n"
        f"1. Banned words: {words[0]}, {words[1]},\n"
        f"   {words[2]} (say the plain thing).\n"
        "2. Another item.\n"
    )
    target = tmp_path / "RULES.md"
    target.write_text(page, encoding="utf-8")
    config = vale_dir / ".vale.ini"
    result = subprocess.run(
        ["vale", "--config", str(config), str(target)], capture_output=True, text=True
    )
    assert "Trueup.Banned" not in result.stdout, result.stdout
    target.write_text(
        page + f"\n- This design is {words[0]}, which is a real use.\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["vale", "--config", str(config), "--output=line", str(target)],
        capture_output=True,
        text=True,
    )
    alerts = [line for line in result.stdout.splitlines() if "Trueup.Banned" in line]
    assert len(alerts) == 1, result.stdout
    assert alerts[0].startswith(f"{target}:{page.count(chr(10)) + 2}:")


@pytest.mark.parametrize(
    "name,text,fires",
    quoted_list_shapes(),
    ids=lambda value: value if isinstance(value, str) and " " in value else None,
)
def test_vale_quoted_list_shapes_match_the_python_matcher(
    tmp_path: Path, vale_dir: Path, name: str, text: str, fires: set[int]
) -> None:
    """A real `vale` run fires on the same lines as `check` for each block shape of D8.4.

    arch: D8.4, D14.6, D14.8
    """
    if shutil.which("vale") is None:
        pytest.skip("tool not installed: vale")
    target = tmp_path / "RULES.md"
    target.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [
            "vale",
            "--config",
            str(vale_dir / ".vale.ini"),
            "--output=line",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    fired = {
        int(line.split(":")[1])
        for line in result.stdout.splitlines()
        if "Trueup.Banned" in line
    }
    assert fired == fires, (name, result.stdout)


_ESLINT_10_RANGES: dict[str, str] = {
    "eslint": "^10.0.0",
    "typescript-eslint": "^8.71.0",
    "eslint-plugin-jsdoc": "^65.2.0",
    "@eslint-community/eslint-plugin-eslint-comments": "^4.8.1",
    "eslint-plugin-security": "^4.2.0",
    "eslint-plugin-sonarjs": "^4.2.2",
    "eslint-plugin-vue": "^10.11.1",
    "vue-eslint-parser": "^10.4.1",
    "vue-tsc": "^3.3.0",
    "knip": "^6.40.0",
    "typescript": "^5.7.0 || ^6.0.0",
}
"""The ranges of D9.5: eslint 10 and the plugin versions whose peer range names it (registry, 2026-10-07)."""

_LINT_TS_PACKAGE = (
    Path(__file__).resolve().parent.parent / "lint" / "ts" / "package.json"
)


def test_eslint_packages_ask_for_eslint_10_and_the_matching_plugins() -> None:
    """Every package fragment holds the D9.5 ranges, and the TypeScript fragments ask for eslint major 10.

    arch: D9.5
    """
    rendered = json.loads(render_eslint_package("strict", "strict"))["devDependencies"]
    assert rendered == _ESLINT_10_RANGES
    for (language, mode), rule_set in RULESETS.items():
        if ESLINT_PACKAGE_FILE not in rule_set.files:
            continue
        deps = json.loads(
            (TEMPLATES_DIR / rule_set.files[ESLINT_PACKAGE_FILE]).read_text(
                encoding="utf-8"
            )
        )["devDependencies"]
        for name, version in deps.items():
            assert version == _ESLINT_10_RANGES[name], (language, mode, name)
        if language == "typescript":
            assert deps["eslint"].startswith("^10.")


def test_lint_ts_follows_the_template_ranges() -> None:
    """This repository's `lint/ts/package.json`, where the eslint tests run, holds the template's ranges (D9.5).

    arch: D9.5
    """
    own = json.loads(_LINT_TS_PACKAGE.read_text(encoding="utf-8"))["devDependencies"]
    for name, version in own.items():
        assert version == _ESLINT_10_RANGES[name], name
    assert own["eslint"] == "^10.0.0"


def test_clippy_entries_keep_going_and_keep_missing_docs() -> None:
    """Both clippy entries pass `--keep-going` to cargo and deny `missing_docs` (D9.6).

    arch: D9.6
    """
    for mode in ("clean", "strict"):
        hook = next(
            hook for hook in RULESETS[("rust", mode)].hooks if hook.id == "clippy"
        )
        cargo_part, _, rustc_part = hook.entry.partition(" -- ")
        assert "--keep-going" in cargo_part.split(), mode
        assert "-D missing_docs" in rustc_part, mode


_WORKSPACE_TOML = '[workspace]\nmembers = ["a", "b", "c"]\nresolver = "2"\n'


def _member_toml(name: str, dependency: str | None = None) -> str:
    """Give the `Cargo.toml` of one workspace member.

    Args:
        name: The crate name.
        dependency: A sibling crate to depend on by path, or `None`.

    Returns:
        The manifest text.
    """
    text = f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n'
    if dependency:
        text += f'\n[dependencies]\n{dependency} = {{ path = "../{dependency}" }}\n'
    return text


def test_rust_clippy_checks_every_crate_that_does_not_depend_on_a_failing_one(
    tmp_path: Path,
) -> None:
    """With `--keep-going`, a crate independent of a failing one is still checked, and cargo accepts the flag (D9.6).

    `a` fails `missing_docs`, `b` depends on `a` and cannot be checked, `c`
    is independent and is checked. The dependents stay hidden: that is the
    limit the skill names.

    arch: D9.6
    """
    _skip_if_missing("cargo")
    hook = next(
        hook for hook in RULESETS[("rust", "clean")].hooks if hook.id == "clippy"
    )
    _write_tree(
        tmp_path,
        {
            "Cargo.toml": _WORKSPACE_TOML,
            "a/Cargo.toml": _member_toml("a"),
            "a/src/lib.rs": "//! crate a\npub fn undocumented_a() {}\n",
            "b/Cargo.toml": _member_toml("b", "a"),
            "b/src/lib.rs": "//! crate b\npub fn undocumented_b() {\n    a::undocumented_a()\n}\n",
            "c/Cargo.toml": _member_toml("c"),
            "c/src/lib.rs": "//! crate c\npub fn undocumented_c() {}\n",
        },
    )
    result = subprocess.run(
        shlex.split(hook.entry), cwd=tmp_path, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "unexpected argument" not in output, output
    assert "undocumented_a" in output, output
    assert "undocumented_c" in output, output


def test_python_strict_has_the_pydoclint_hook_after_complexipy() -> None:
    """Strict Python adds a pydoclint hook right after complexipy; the hook never writes a baseline.

    D14.6 changed D12.8: the entry has no shell wrapper and no
    `--generate-baseline`, and names no baseline. `owned_file_args` adds
    the baseline only when the target has one (I-47).

    arch: D12.8, D14.6, D14.22
    """
    rs = RULESETS[("python", "strict")]
    ids = [h.id for h in rs.hooks]
    assert ids.index("pydoclint") == ids.index("complexipy") + 1
    hook = rs.hooks[ids.index("pydoclint")]
    assert hook.pass_filenames is False
    assert hook.entry == (
        "pydoclint --style=google --arg-type-hints-in-docstring=False "
        "--check-return-types=False ."
    )
    assert "baseline" not in hook.entry
    assert "pydoclint" in rs.tools
    assert "pydoclint" not in [h.id for h in RULESETS[("python", "clean")].hooks]


_OFF = {
    "security/detect-object-injection": "numeric code indexes objects by computed keys; the rule flags each lookup",
    "security/detect-non-literal-fs-filename": "Node tools read their own files",
}


@pytest.mark.parametrize(("typescript", "vue"), [("clean", "off"), ("strict", "clean")])
def test_eslint_config_ends_with_the_off_block_of_the_entries(
    tmp_path: Path, typescript: str, vue: str
) -> None:
    """With `[[eslint.off]]` entries the config ends with `offBlock`: one sorted line per rule, its reason as a comment.

    With no entry (None or empty) the text is the one of the plain render,
    so a target that never sets the key keeps the same bytes.

    arch: D13.5, D5.5
    """
    plain = render_eslint_config(typescript, vue)
    assert render_eslint_config(typescript, vue, {}) == plain
    assert render_eslint_config(typescript, vue, None) == plain
    assert "offBlock" not in plain
    text = render_eslint_config(typescript, vue, _OFF)
    assert text.startswith(plain.rsplit("export default", 1)[0])
    assert "\n".join(text.splitlines()[-9:]) == "\n".join(
        [
            "/** The rules that trueup.toml turns off ([[eslint.off]]), each with its reason. */",
            "const offBlock = {",
            "  rules: {",
            '    "security/detect-non-literal-fs-filename": "off", // Node tools read their own files',
            '    "security/detect-object-injection": "off", // numeric code indexes objects by computed keys; the rule flags each lookup',
            "  },",
            "};",
            "",
            "export default tseslint.config(tsBlock"
            + (", ...vueBlocks" if vue != "off" else "")
            + ", offBlock);",
        ]
    )
    _skip_if_missing("node")
    config = tmp_path / "eslint.config.mjs"
    config.write_text(text, encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(config)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_eslint_hook_runs_npx_from_the_eslint_dir_with_no_shell() -> None:
    """Each eslint hook runs eslint from the eslint package directory with the run config, and keeps `--max-warnings 0`.

    The `sh -c 'if test -f ...'` wrapper of D13.6 is gone (D14.6): the
    entry names no suppressions file, and `owned_file_args` adds it. The
    entry does not pass `--pass-on-unpruned-suppressions`: a suppression
    that no longer occurs fails the hook.

    arch: D14.22, D14.6
    """
    entries = {
        hook.entry
        for (language, _mode), rule_set in RULESETS.items()
        if language in ("typescript", "vue")
        for hook in rule_set.hooks
        if hook.id == "eslint"
    }
    assert len(entries) == 1
    (entry,) = entries
    assert entry == (
        f"npx --prefix {{eslint}} eslint --config {{eslint}}/{ESLINT_RUN_CONFIG} "
        "--max-warnings 0"
    )
    assert re.fullmatch(r"run-\d+\.mjs", ESLINT_RUN_CONFIG)
    assert "suppressions" not in entry
    assert "--pass-on-unpruned-suppressions" not in entry


def _every_hook() -> list[Hook]:
    """List every hook of every rule set, plus the jscpd and Vale hooks.

    Returns:
        The hooks, with repeats.
    """
    return [
        *(hook for rule_set in RULESETS.values() for hook in rule_set.hooks),
        JSCPD_HOOK,
        VALE_HOOK,
    ]


def test_every_entry_fills_only_the_three_fields_and_runs_no_shell() -> None:
    """Each hook entry uses only `{cfg}`, `{eslint}`, `{tools}` and `{root}`, names no `lint/` path, runs no shell, and calls no `npx <package>` or `uvx`.

    `trueup lint` fills the fields with `str.format` and splits the line
    with `shlex.split` (D14.6), so a stray brace or a shell wrapper would
    break the run.

    arch: D14.22, D14.6, D15.5
    """
    for hook in _every_hook():
        fields = {
            name for _, name, _, _ in string.Formatter().parse(hook.entry) if name
        }
        assert fields <= {"cfg", "eslint", "tools", "root"}, (hook.id, fields)
        argv = shlex.split(
            hook.entry.format(cfg="/c", eslint="/e", tools="/t", root="/r")
        )
        assert argv[0] not in ("sh", "bash", "uvx"), hook.id
        assert argv[:2] != ["npx", "jscpd"], hook.id
        assert "lint/" not in hook.entry, hook.id
        assert "gitleaks" not in hook.entry, hook.id
    assert VALE_HOOK.entry == "vale --config {cfg}/vale/.vale.ini"
    ruff = next(h for h in RULESETS[("python", "clean")].hooks if h.id == "ruff-check")
    assert _argv(ruff, Path("/tmp/c")) == [
        "ruff",
        "check",
        "--config",
        "/tmp/c/python/ruff.toml",
    ]


def test_rule_set_files_are_paths_under_cfgdir() -> None:
    """Every `RuleSet.files` key lost the `lint/` prefix of D5.5 (D14.6).

    arch: D14.22, D14.6
    """
    keys = {key for rule_set in RULESETS.values() for key in rule_set.files}
    assert keys == {
        "python/ruff.toml",
        "rust/clippy.toml",
        "shell/shellcheckrc",
        "sql/.sqlfluff",
        "go/golangci.yml",
        "php/phpstan.neon",
        "php/phpcs.xml",
        "php/phpmd.xml",
        ESLINT_CONFIG_FILE,
        ESLINT_PACKAGE_FILE,
    }
    assert SHARED_TARGETS == {ESLINT_CONFIG_FILE, ESLINT_PACKAGE_FILE}


@pytest.mark.parametrize("mode", ["clean", "strict"])
def test_phpstan_template_paths_start_with_the_root_token(
    tmp_path: Path, mode: str
) -> None:
    """Every path of the phpstan template starts with `ROOT_TOKEN`; the written file names the absolute root.

    phpstan resolves a relative path from the directory of its config
    file, which is `cfgdir` (D14.6). The token covers `paths`,
    `excludePaths` and `includes` (D14.22 item 13).

    arch: D14.22, D14.6
    """
    rule_set = RULESETS[("php", mode)]
    text = (TEMPLATES_DIR / rule_set.files["php/phpstan.neon"]).read_text(
        encoding="utf-8"
    )
    assert ROOT_TOKEN == "__TRUEUP_ROOT__"
    assert "../" not in text
    items = [
        line.strip()[2:] for line in text.splitlines() if line.strip().startswith("- ")
    ]
    assert items
    assert all(item.startswith(ROOT_TOKEN) for item in items), items
    assert any("rules.neon" in item for item in items) == (mode == "strict")
    root, cfgdir = _dirs(tmp_path)
    _render_rule_files(rule_set, cfgdir, root)
    written = (cfgdir / "php/phpstan.neon").read_text(encoding="utf-8")
    assert ROOT_TOKEN not in written
    assert f"        - {root}\n" in written


@pytest.mark.parametrize(
    ("hook_id", "language", "field", "flag"),
    [
        ("eslint", "typescript", "eslint_suppressions", "--suppressions-location"),
        ("pydoclint", "python", "python_pydoclint_baseline", "--baseline"),
    ],
)
def test_owned_file_args_pass_a_target_file_only_when_it_exists(
    tmp_path: Path, hook_id: str, language: str, field: str, flag: str
) -> None:
    """A file the target owns goes on the command line only when it exists under the root (I-47).

    The default path and a path that `trueup.toml` names both work; a
    hook with no owned file gets no argument, and nothing is written
    under the root.

    arch: D14.22, D14.6
    """
    hook = next(h for h in RULESETS[(language, "strict")].hooks if h.id == hook_id)
    root = tmp_path / "root"
    root.mkdir()
    default = Config()
    custom = Config(**{field: "tools/owned.txt"})
    assert owned_file_args(hook, root, default) == ()
    assert owned_file_args(hook, root, custom) == ()
    for cfg in (default, custom):
        path = getattr(cfg, field)
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("{}\n", encoding="utf-8")
        assert owned_file_args(hook, root, cfg) == (flag, path)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    other = next(h for h in RULESETS[("python", "strict")].hooks if h.id == "vulture")
    assert owned_file_args(other, root, default) == ()
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


_TWO_UNDOCUMENTED_TS = """export function one(): number {
  return 1;
}

export function two(): number {
  return 2;
}
"""

_ONE_UNDOCUMENTED_TS = """/**
 * Give one.
 * @returns One.
 */
export function one(): number {
  return 1;
}

export function two(): number {
  return 2;
}
"""

_LOOKUP_TS = """/**
 * Look up one value.
 * @param table - The values by name.
 * @param key - The name.
 * @returns The value.
 */
export function look(table: Record<string, number>, key: string): number {
  return table[key];
}
"""


def test_eslint_hook_runs_with_the_off_block_and_the_suppressions_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real eslint 10 run of the hook entry: the off block, then the suppressions file absent, present, and unused.

    The config sits in the eslint package directory outside the root
    (D14.7), and `owned_file_args` adds the suppressions file only when it
    exists (D14.6, I-47).

    - `security/detect-object-injection` warns on `table[key]` and fails
      the hook; with the rule in `[[eslint.off]]` the file passes.
    - With no suppressions file the hook lints and fails on the errors.
    - `--suppress-all` writes the file; the hook then passes.
    - After one of two errors is fixed, the suppression count is too high:
      the hook exits 2 and names `--prune-suppressions`.
    - `--prune-suppressions` lowers the count; the hook passes again.

    arch: D13.5, D13.6, D14.22, D14.6
    """
    _skip_if_missing("npx")
    if not (_LINT_TS_MODULES / "eslint-plugin-security").is_dir():
        pytest.skip("tool not installed: eslint-plugin-security (lint/ts/node_modules)")
    monkeypatch.setenv("npm_config_offline", "true")
    root, cfgdir = _dirs(tmp_path)
    eslint_dir = _eslint_dir(tmp_path, "clean", "off")
    _write_tree(root, {"lookup.ts": _LOOKUP_TS, "old.ts": _TWO_UNDOCUMENTED_TS})
    cfg = Config()
    hook = next(
        hook for hook in RULESETS[("typescript", "clean")].hooks if hook.id == "eslint"
    )

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                *_argv(hook, cfgdir, eslint_dir),
                *owned_file_args(hook, root, cfg),
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )

    def eslint(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "npx",
                "--prefix",
                str(eslint_dir),
                "eslint",
                "--config",
                str(eslint_dir / ESLINT_RUN_CONFIG),
                "--suppressions-location",
                cfg.eslint_suppressions,
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )

    lookup = run("lookup.ts")
    assert lookup.returncode == 1, lookup.stdout + lookup.stderr
    assert "security/detect-object-injection" in lookup.stdout
    (eslint_dir / ESLINT_RUN_CONFIG).write_text(
        render_eslint_config("clean", "off", _OFF), encoding="utf-8"
    )
    lookup = run("lookup.ts")
    assert lookup.returncode == 0, lookup.stdout + lookup.stderr

    absent = run("old.ts")
    assert absent.returncode == 1, absent.stdout + absent.stderr
    assert "jsdoc/require-jsdoc" in absent.stdout

    suppressions = root / cfg.eslint_suppressions
    suppressions.parent.mkdir(parents=True)
    assert eslint("--suppress-all", "old.ts").returncode == 0
    assert json.loads(suppressions.read_text(encoding="utf-8")) == {
        "old.ts": {"jsdoc/require-jsdoc": {"count": 2}}
    }
    present = run("old.ts", "lookup.ts")
    assert present.returncode == 0, present.stdout + present.stderr

    (root / "old.ts").write_text(_ONE_UNDOCUMENTED_TS, encoding="utf-8")
    unused = run("old.ts")
    assert unused.returncode == 2, unused.stdout + unused.stderr
    assert "--prune-suppressions" in unused.stdout + unused.stderr

    assert eslint("--prune-suppressions", "old.ts").returncode == 0
    assert json.loads(suppressions.read_text(encoding="utf-8")) == {
        "old.ts": {"jsdoc/require-jsdoc": {"count": 1}}
    }
    pruned = run("old.ts")
    assert pruned.returncode == 0, pruned.stdout + pruned.stderr


def test_rendered_jscpd_has_no_path_and_reads_gitignore() -> None:
    """The rendered duplication config names no `path` (the hook gives `.`) and skips git-ignored trees.

    arch: D15.5
    """
    data = json.loads(render_jscpd(["python"]))
    assert "path" not in data
    assert data["gitignore"] is True
    assert data["format"] == ["python"]


def test_typescript_strict_block_is_a_typed_and_an_untyped_object() -> None:
    """The strict TypeScript block is an array: typed rules for TypeScript files, untyped rules for JavaScript files (D15.28).

    A `.js` file outside a tsconfig would fail `projectService`, so the
    JavaScript object uses `strict` and `stylistic` without type checks.

    arch: D15.28
    """
    text = render_eslint_config("strict", "off")
    assert "const tsBlock = [" in text
    assert 'files: ["**/*.{ts,tsx,mts,cts}"]' in text
    assert 'files: ["**/*.{js,jsx,mjs,cjs}"]' in text
    typed, _, untyped = text.partition('files: ["**/*.{js,jsx,mjs,cjs}"]')
    assert "strictTypeChecked" in typed
    assert "projectService" in typed
    assert "tseslint.configs.strict," in untyped
    assert "tseslint.configs.stylistic," in untyped
    assert "TypeChecked" not in untyped
    assert "projectService" not in untyped
    assert "sonarjs.configs.recommended" in untyped
    assert "pluginSecurity.configs.recommended" in untyped
    assert "rules: sharedRules" in untyped
    assert '"complexity": ["error", 10]' in text
    assert (
        "export default tseslint.config(tsBlock, ...vueBlocks);"
        in render_eslint_config("strict", "strict")
    )


def test_vue_strict_block_has_the_shared_thresholds_and_its_own_sonarjs() -> None:
    """The strict Vue block sets the shared thresholds, imports sonarjs as `vueSonar` (D15.28).

    arch: D15.28
    """
    text = render_eslint_config("clean", "strict")
    vue_part = text[text.index("const vueBlocks") :]
    assert 'import vueSonar from "eslint-plugin-sonarjs";' in text
    for rule in (
        '"complexity": ["error", 10]',
        '"max-depth": ["error", 4]',
        '"max-params": ["error", 5]',
        '"max-lines-per-function": ["error", { max: 60',
        '"sonarjs/cognitive-complexity": ["error", 15]',
    ):
        assert rule in vue_part, rule
    both = render_eslint_config("strict", "strict")
    assert both.count("import sonarjs from") == 1


def test_phpmd_strict_reports_at_the_value_after_the_limit() -> None:
    """The strict phpmd file allows cyclomatic 10, method length 60 and 5 parameters, because phpmd reports at the minimum (D15.28).

    arch: D15.28
    """
    text = (TEMPLATES_DIR / "rules/php/phpmd-strict.xml").read_text(encoding="utf-8")
    assert re.search(r'name="reportLevel" value="11"', text)
    assert re.search(r'ExcessiveMethodLength.*?name="minimum" value="61"', text, re.S)
    assert re.search(r'ExcessiveParameterList.*?name="minimum" value="6"', text, re.S)


def test_rule_set_has_no_nightly_field() -> None:
    """A rule set carries no nightly commands: the field and its values are gone (D15.28).

    arch: D15.28
    """
    assert not hasattr(RULESETS[("python", "strict")], "nightly")
    assert "nightly" not in (Path(rulesets_module.__file__)).read_text(encoding="utf-8")
