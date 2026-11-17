"""Tests for `trueup.drift`, the D6.5 docs drift rows.

Method note: these tests reuse `tests/conftest.materialise` for the
good/bad tree pairs, the same shape `test_docrules.py` and
`test_lint_fixtures.py` already use for one rule per fixture directory;
that fits here too, since each drift rule needs its own small repository
tree, not a single shared one.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import materialise
from trueup import drift, report, survey as survey_mod


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _findings(root: Path, only: frozenset[str] | None = None) -> list:
    """Survey `root` and give every `drift_findings` result.

    Args:
        root: The repository root to survey and check.
        only: The scope to pass to `drift.drift_findings`.

    Returns:
        The findings `drift.drift_findings` produced.
    """
    survey = survey_mod.run(root)
    return drift.drift_findings(survey, only)


def _by_rule(root: Path, rule: str, only: frozenset[str] | None = None) -> list:
    """Survey `root` and give the `drift_findings` of one rule.

    Args:
        root: The repository root to survey and check.
        rule: The rule name to filter on.
        only: The scope to pass to `drift.drift_findings`.

    Returns:
        The findings whose `rule` equals `rule`.
    """
    return [finding for finding in _findings(root, only) if finding.rule == rule]


# -- drift-flag -----------------------------------------------------------


def test_drift_flag_fires_on_the_bad_fixture(tmp_path: Path) -> None:
    """A doc line that uses a flag outside the command's static set is a `warn` (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/flag-bad", tmp_path)
    _git_init(tree)
    findings = _by_rule(tree, "drift-flag")
    assert [finding.id for finding in findings] == ["drift-flag:README.md:--bogus"]
    assert findings[0].severity == "warn"
    assert findings[0].auto is False


def test_drift_flag_is_silent_on_the_good_fixture(tmp_path: Path) -> None:
    """A doc line that uses only known flags gives no `drift-flag` row (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/flag-good", tmp_path)
    _git_init(tree)
    assert _by_rule(tree, "drift-flag") == []


def test_empty_flag_set_gives_no_drift_flag_row(tmp_path: Path) -> None:
    """A command file with no `--flag` argument yields no `drift-flag` row (D6.5).

    `cli.py` here calls `add_argument` with a positional name only, so its
    static flag set is empty; D6.5 never guesses a command's flags from a
    doc line alone.

    arch: D6.5
    """
    _git_init(tmp_path)
    (tmp_path / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        'parser.add_argument("event")\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Fixture\n\n```sh\npython3 cli.py --bogus\n```\n", encoding="utf-8"
    )
    assert _by_rule(tmp_path, "drift-flag") == []


def test_drift_flag_reads_only_the_flags_of_the_command_that_runs(
    tmp_path: Path,
) -> None:
    """A flag of another program on the same line gives no `drift-flag` row (D6.5).

    `docker compose run --rm tool` names `tool` as an argument, so `--rm`
    belongs to docker. `tool-rotate` is a different command. The flag
    after `./build/tool` and after `&& tool` is checked.

    arch: D6.5
    """
    _git_init(tmp_path)
    (tmp_path / "go.mod").write_text("module example.com/x/tool\n", encoding="utf-8")
    (tmp_path / "main.go").write_text(
        'package main\n\nfunc main() { cmd.Flags().StringVar(&c, "config", "", "") }\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Fixture\n\n```bash\n"
        "docker compose run --rm tool\n"
        "tool-rotate --dry-run\n"
        "./build/tool --config c.yaml\n"
        "make build && tool --bogus\n"
        "```\n",
        encoding="utf-8",
    )
    ids = [finding.id for finding in _by_rule(tmp_path, "drift-flag")]
    assert ids == ["drift-flag:README.md:--bogus"]


# -- drift-undocumented ----------------------------------------------------


def test_drift_undocumented_fires_on_the_bad_fixture(tmp_path: Path) -> None:
    """A static flag no doc names is an `info` finding (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/undocumented-bad", tmp_path)
    _git_init(tree)
    findings = _by_rule(tree, "drift-undocumented")
    assert [finding.id for finding in findings] == ["drift-undocumented:cli.py:--extra"]
    assert findings[0].severity == "info"


def test_drift_undocumented_is_silent_on_the_good_fixture(tmp_path: Path) -> None:
    """A static flag every doc names gives no `drift-undocumented` row (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/undocumented-good", tmp_path)
    _git_init(tree)
    assert _by_rule(tree, "drift-undocumented") == []


# -- drift-package ----------------------------------------------------------


def test_drift_package_fires_on_the_bad_fixture(tmp_path: Path) -> None:
    """An install section with no line naming this project's manifest is a `warn` (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/package-bad", tmp_path)
    _git_init(tree)
    findings = _by_rule(tree, "drift-package")
    assert [finding.id for finding in findings] == ["drift-package:README.md"]
    assert findings[0].severity == "warn"


def test_drift_package_is_silent_on_the_good_fixture(tmp_path: Path) -> None:
    """An install line that names `.` gives no `drift-package` row (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/package-good", tmp_path)
    _git_init(tree)
    assert _by_rule(tree, "drift-package") == []


def _python_repo(root: Path, install: str) -> None:
    """Write a Python project `foo` whose README install section holds one line.

    Args:
        root: The repository root. Must already be a git repository.
        install: The one line of the fenced block under `## Install`.
    """
    (root / "pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "1.0"\n', encoding="utf-8"
    )
    (root / "README.md").write_text(
        f"# Foo\n\nA tool.\n\n## Install\n\n```sh\n{install}\n```\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "install",
    [
        "pip install git+https://github.com/acme/foo",
        "uv tool install git+https://github.com/acme/foo.git@v1.0",
        "pipx install https://github.com/acme/foo/#egg=foo",
    ],
)
def test_drift_package_reads_a_url_that_ends_in_the_package_name(
    tmp_path: Path, install: str
) -> None:
    """An install line with a URL whose last path segment is the package name is the project's own (D6.5).

    arch: D6.5
    """
    _git_init(tmp_path)
    _python_repo(tmp_path, install)
    assert _by_rule(tmp_path, "drift-package") == []


def test_drift_package_fires_on_a_url_of_another_package(tmp_path: Path) -> None:
    """A URL whose last path segment only starts with the package name is another package (D6.5).

    arch: D6.5
    """
    _git_init(tmp_path)
    _python_repo(tmp_path, "pip install git+https://github.com/acme/foobar")
    assert [f.id for f in _by_rule(tmp_path, "drift-package")] == [
        "drift-package:README.md"
    ]


def _go_repo(root: Path, install: str) -> None:
    """Write a Go module whose README install section holds one line.

    Args:
        root: The repository root. Must already be a git repository.
        install: The one line of the fenced block under `## Install`.
    """
    (root / "go.mod").write_text(
        "module github.com/acme/tool\n\ngo 1.22\n", encoding="utf-8"
    )
    (root / "README.md").write_text(
        f"# Tool\n\nA tool.\n\n## Install\n\n```sh\n{install}\n```\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "install",
    [
        "go install github.com/acme/tool@latest",
        "go install github.com/acme/tool/cmd/tool@v1.2.0",
        "go install .",
        "go install ./...",
        "go get github.com/acme/tool@latest",
    ],
)
def test_drift_package_reads_the_go_module_path(tmp_path: Path, install: str) -> None:
    """A Go install line that names the `go.mod` module, a path below it, or `.` is the project's own (D6.5).

    arch: D6.5
    """
    _git_init(tmp_path)
    _go_repo(tmp_path, install)
    assert _by_rule(tmp_path, "drift-package") == []


@pytest.mark.parametrize(
    "install",
    [
        "go install github.com/other/tool@latest",
        "go install github.com/acme/toolkit@latest",
        "go get github.com/other/lib@v1.0.0",
    ],
)
def test_drift_package_fires_on_another_go_module(tmp_path: Path, install: str) -> None:
    """A Go install line for another module is a `drift-package` row (D6.5).

    `github.com/acme/toolkit` only starts with the module text; it is not a
    path below the module.

    arch: D6.5
    """
    _git_init(tmp_path)
    _go_repo(tmp_path, install)
    assert [f.id for f in _by_rule(tmp_path, "drift-package")] == [
        "drift-package:README.md"
    ]


# -- drift-command ----------------------------------------------------------


def test_drift_command_fires_on_the_bad_fixture(tmp_path: Path) -> None:
    """A shell block that runs an untracked path is a `warn` (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/command-bad", tmp_path)
    _git_init(tree)
    findings = _by_rule(tree, "drift-command")
    assert [finding.id for finding in findings] == [
        "drift-command:README.md:missing.py"
    ]
    assert findings[0].severity == "warn"


def test_drift_command_is_silent_on_the_good_fixture(tmp_path: Path) -> None:
    """A shell block that runs a tracked path gives no `drift-command` row (D6.5).

    arch: D6.5
    """
    tree = materialise("drift/command-good", tmp_path)
    _git_init(tree)
    assert _by_rule(tree, "drift-command") == []


def test_drift_command_checks_npm_run_and_make_targets(tmp_path: Path) -> None:
    """`npm run <s>` and `make <t>` are checked against their own manifest (D6.5).

    arch: D6.5
    """
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text(
        '{"name": "fixture", "scripts": {"build": "true"}}\n', encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text("test:\n\ttrue\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Fixture\n\n"
        "```sh\n"
        "npm run build\n"
        "npm run lint\n"
        "make test\n"
        "make release\n"
        "```\n",
        encoding="utf-8",
    )
    ids = {finding.id for finding in _by_rule(tmp_path, "drift-command")}
    assert ids == {
        "drift-command:README.md:npm-run:lint",
        "drift-command:README.md:make:release",
    }


# -- Scope and the no-subprocess invariants (I-18, I-21) ---------------------


def test_a_scoped_run_reads_the_flag_sources_outside_only(tmp_path: Path) -> None:
    """A scoped run reads a flag source outside `only` and flags a bad flag in a doc in `only` (D6.17, D6.5).

    `other.py` sits outside `only`. The scoped run must still read its
    static flag set, so `python3 other.py --bogus` in `README.md` gives the
    same `drift-flag` row as the full run, and `--outside` gives none.

    arch: D6.17, D6.5
    """
    _git_init(tmp_path)
    (tmp_path / "other.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        'parser.add_argument("--outside")\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Fixture\n\n```sh\npython3 other.py --outside\npython3 other.py --bogus\n```\n",
        encoding="utf-8",
    )
    scoped = [finding.id for finding in _findings(tmp_path, frozenset({"README.md"}))]
    full = [finding.id for finding in _findings(tmp_path)]
    assert scoped == ["drift-flag:README.md:--bogus"]
    assert scoped == [
        finding_id for finding_id in full if finding_id.startswith("drift-flag:")
    ]


def _scope_repo(root: Path) -> None:
    """Write the H-1 tree: a correct README for package `foo` and its `cli.py`.

    `README.md` installs `foo` and names both flags of `cli.py`, so the
    full run gives no `drift-package` and no `drift-undocumented` row.

    Args:
        root: The directory to fill; it becomes a git repository.
    """
    _git_init(root)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (root / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        'parser.add_argument("--json")\n'
        'parser.add_argument("--root")\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# foo\n\nA tool.\n\n## Install\n\n```sh\npip install foo\n```\n\n"
        "## Usage\n\n```sh\npython3 cli.py --json --root .\n```\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("changed", ["README.md", "cli.py", "pyproject.toml"])
def test_a_scoped_run_adds_no_drift_row_the_full_run_lacks(
    tmp_path: Path, changed: str
) -> None:
    """With `only` holding one file, `collect` gives no drift row that the full run does not give (D6.17, D6.5).

    `README.md` alone once gave `drift-package`, since the scoped run did
    not read `pyproject.toml`. `cli.py` alone once gave
    `drift-undocumented` for each flag, since the scoped run did not read
    `README.md`.

    arch: D6.17, D6.5
    """
    _scope_repo(tmp_path)
    full = {finding.id for finding in report.collect(tmp_path).findings}
    scoped = report.collect(tmp_path, only=frozenset({changed})).findings
    drift_ids = {finding.id for finding in scoped if finding.rule.startswith("drift-")}
    assert drift_ids <= full
    assert not any(finding_id.startswith("drift-") for finding_id in full)


def test_a_scoped_run_still_flags_a_path_missing_from_the_whole_survey(
    tmp_path: Path,
) -> None:
    """A path absent from the full survey still fires `drift-command` scoped (D6.17, D6.5).

    Unlike `other.py` in the test above, `missing.py` names no file
    anywhere in the tree, scoped or not, so the finding must survive
    scoping down to `only`.

    arch: D6.17, D6.5
    """
    _git_init(tmp_path)
    (tmp_path / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        'parser.add_argument("--allowed")\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Fixture\n\n```sh\npython3 cli.py --allowed\npython3 missing.py\n```\n",
        encoding="utf-8",
    )
    survey = survey_mod.run(tmp_path)
    only = frozenset({"README.md"})
    findings = drift.drift_findings(survey, only)
    assert [finding.id for finding in findings] == [
        "drift-command:README.md:missing.py"
    ]


def test_drift_findings_calls_no_subprocess_and_no_which(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`drift_findings` runs no process and probes no tool on the path (I-18, I-21).

    arch: I-18, I-21
    """
    tree = materialise("drift/flag-bad", tmp_path)
    _git_init(tree)
    survey = survey_mod.run(tree)

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("drift_findings must not call this")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(shutil, "which", _boom)
    drift.drift_findings(survey, None)


# -- Parse errors and the scoped parse (D14.12 C1, D14.14) -------------------


@pytest.mark.parametrize("error", [SyntaxError, ValueError, RecursionError])
def test_a_parse_error_gives_an_empty_flag_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    """Each parse error of `ast.parse` gives an empty flag set, not a crash (D14.12 C1).

    arch: D14.12, D14.14, D14.21
    """
    path = tmp_path / "bad.py"
    path.write_text('parser.add_argument("--x")\n', encoding="utf-8")

    def _raise(*args: object, **kwargs: object) -> object:
        raise error("bad source")

    monkeypatch.setattr(drift.ast, "parse", _raise)
    assert drift._python_flags(path) == frozenset()


def test_a_deeply_nested_file_does_not_stop_the_run(tmp_path: Path) -> None:
    """A file that overflows the parser stack is skipped, and the other files still count (D14.12 C1).

    `deep.py` holds one long chain of `+`, which gives a `RecursionError`
    in `ast.parse` on Python 3.13.

    arch: D14.12, D14.14, D14.21
    """
    _git_init(tmp_path)
    (tmp_path / "deep.py").write_text("x = " + "1+" * 100000 + "1\n", encoding="utf-8")
    (tmp_path / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        'parser.add_argument("--quiet")\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Fixture\n", encoding="utf-8")
    ids = [finding.id for finding in _findings(tmp_path)]
    assert ids == ["drift-undocumented:cli.py:--quiet"]


def _parse_repo(root: Path) -> None:
    """Write a tree with four flag sources and a README that runs two of them.

    `README.md` runs `run.py` and the `pkg` package. Only
    `pkg/__main__.py` has the `python3 pkg` alias (arch: D15.17). No doc runs
    `idle.py` or `pkg/extra.py`.

    Args:
        root: The directory to fill; it becomes a git repository.
    """
    _git_init(root)
    for path, flag in [
        ("run.py", "--fast"),
        ("idle.py", "--idle"),
        ("pkg/__init__.py", None),
        ("pkg/__main__.py", "--deep"),
        ("pkg/extra.py", "--extra"),
    ]:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        body = "import argparse\nparser = argparse.ArgumentParser()\n"
        if flag is not None:
            body += f'parser.add_argument("{flag}")\n'
        (root / path).write_text(body, encoding="utf-8")
    (root / "README.md").write_text(
        "# Fixture\n\n```sh\npython3 run.py --fast --bogus\npython3 pkg --deep\n```\n",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text(
        "# Notes\n\nNo command.\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("only", "parsed"),
    [
        (frozenset({"idle.py"}), ["idle.py"]),
        (
            frozenset({"README.md"}),
            ["pkg/__main__.py", "run.py"],
        ),
        (frozenset({"docs/notes.md"}), []),
        (frozenset({"docs/notes.md", "idle.py"}), ["idle.py"]),
        (
            frozenset({"README.md", "idle.py"}),
            ["idle.py", "pkg/__main__.py", "run.py"],
        ),
    ],
)
def test_a_scoped_run_parses_only_the_scoped_and_the_named_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    only: frozenset[str],
    parsed: list[str],
) -> None:
    """A scoped run parses the `.py` files in `only` and those a scoped doc runs, and keeps D6.17 (D14.14).

    The scoped findings equal the full-run findings whose `path` is in
    `only`, in the same order.

    arch: D14.12, D14.14, D14.21
    """
    _parse_repo(tmp_path)
    survey = survey_mod.run(tmp_path)
    full = drift.drift_findings(survey, None)
    seen: list[str] = []
    real = drift._python_flags

    def _record(path: Path) -> frozenset[str]:
        seen.append(path.relative_to(tmp_path).as_posix())
        return real(path)

    monkeypatch.setattr(drift, "_python_flags", _record)
    scoped = drift.drift_findings(survey, only)
    assert sorted(seen) == parsed
    assert scoped == [finding for finding in full if finding.path in only]


def test_a_full_run_still_parses_every_flag_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full run parses every `.py` file outside `tests/` (D14.14).

    arch: D14.12, D14.14, D14.21
    """
    _parse_repo(tmp_path)
    survey = survey_mod.run(tmp_path)
    seen: list[str] = []
    real = drift._python_flags

    def _record(path: Path) -> frozenset[str]:
        seen.append(path.relative_to(tmp_path).as_posix())
        return real(path)

    monkeypatch.setattr(drift, "_python_flags", _record)
    ids = sorted(finding.id for finding in drift.drift_findings(survey, None))
    assert sorted(seen) == [
        "idle.py",
        "pkg/__init__.py",
        "pkg/__main__.py",
        "pkg/extra.py",
        "run.py",
    ]
    assert ids == [
        "drift-flag:README.md:--bogus",
        "drift-undocumented:idle.py:--idle",
        "drift-undocumented:pkg/extra.py:--extra",
    ]


def test_a_memory_error_in_the_parser_gives_an_empty_flag_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ast.parse` can raise `MemoryError` on a deep file; the flag set is empty.

    arch: D15.1
    """
    path = tmp_path / "cli.py"
    path.write_text('parser.add_argument("--x")\n', encoding="utf-8")

    real_parse = drift.ast.parse

    def _raise(source: str, *args: object, **kwargs: object) -> object:
        if "add_argument" in str(source):  # only the file under test
            raise MemoryError("Parser stack overflowed")
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(drift.ast, "parse", _raise)
    assert drift._python_flags(path) == frozenset()


@pytest.mark.parametrize(
    ("name", "text", "key"),
    [
        ("pyproject.toml", 'project = "x"\n', "project"),
        ("pyproject.toml", "[project]\nscripts = 3\n", "project.scripts"),
        ("Cargo.toml", 'package = "x"\n', "package"),
    ],
)
def test_a_manifest_key_that_is_not_a_table_gives_one_info_row(
    tmp_path: Path, name: str, text: str, key: str
) -> None:
    """A manifest whose table key holds a scalar gives one `drift-manifest` info row and no crash.

    arch: D15.1
    """
    _git_init(tmp_path)
    (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    survey = survey_mod.run(tmp_path)
    rows = [f for f in drift.drift_findings(survey, None) if f.rule == "drift-manifest"]
    assert [row.id for row in rows] == [f"drift-manifest:{name}"]
    assert rows[0].severity == "info"
    assert rows[0].evidence == f"manifest not readable: {key} is not a table"


# -- D15.17: ignored paths, Go flags, Cargo workspaces -----------------------


def _commit_files(root: Path, files: dict[str, str]) -> None:
    """Write `files` under a new git repository at `root`."""
    _git_init(root)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


def test_an_ignored_command_path_gives_info(tmp_path: Path) -> None:
    """A token in `ignored` gives `info`; any other missing path stays `warn`.

    arch: D15.16, D15.17
    """
    _commit_files(
        tmp_path,
        {
            "README.md": "# x\n\n```sh\n./build/tool\n./gone/tool\n```\n",
            "a.py": "x=1\n",
        },
    )
    survey = survey_mod.run(tmp_path)
    assert drift.missing_command_paths(survey) == ["./build/tool", "./gone/tool"]
    found = drift.drift_findings(survey, None, frozenset({"./build/tool"}))
    assert {f.id: f.severity for f in found} == {
        "drift-command:README.md:./build/tool": "info",
        "drift-command:README.md:./gone/tool": "warn",
    }


def test_a_path_named_in_the_makefile_or_a_script_gives_info(tmp_path: Path) -> None:
    """A missing path that the Makefile or a `package.json` script names gives `info`.

    arch: D15.16, D15.17
    """
    _commit_files(
        tmp_path,
        {
            "README.md": "# x\n\n```sh\n./out/a\n./out/b\n./out/c\n```\n",
            "Makefile": "all:\n\tcc -o out/a main.c\n",
            "package.json": '{"scripts": {"build": "tsc -o out/b"}}',
        },
    )
    found = _findings(tmp_path)
    assert {f.id: f.severity for f in found if f.rule == "drift-command"} == {
        "drift-command:README.md:./out/a": "info",
        "drift-command:README.md:./out/b": "info",
        "drift-command:README.md:./out/c": "warn",
    }


def test_python3_package_reads_only_main_module_flags(tmp_path: Path) -> None:
    """`python3 pkg` names `pkg/__main__.py` only, so a flag of `pkg/cli.py` is not its flag.

    arch: D15.16, D15.17
    """
    parser = "import argparse\np = argparse.ArgumentParser()\np.add_argument('{}')\n"
    _commit_files(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/__main__.py": parser.format("--main"),
            "pkg/cli.py": parser.format("--other"),
            "README.md": "# x\n\n```sh\npython3 pkg --main --other\n```\n",
        },
    )
    ids = {f.id for f in _findings(tmp_path) if f.rule == "drift-flag"}
    assert ids == {"drift-flag:README.md:--other"}


@pytest.mark.parametrize(
    "line",
    [
        'flag.Bool("verbose", false, "x")',
        'flag.Duration("wait", 0, "x")',
        'flag.Int64Var(&n, "count", 0, "x")',
    ],
)
def test_go_standard_flags_are_read(tmp_path: Path, line: str) -> None:
    """The Go `flag` package's typed and `Var` calls define a flag.

    arch: D15.16, D15.17
    """
    _commit_files(
        tmp_path,
        {
            "go.mod": "module example.com/tool\n",
            "main.go": f"package main\nfunc main() {{ {line} }}\n",
            "README.md": "# x\n\n```sh\ntool --nothing\n```\n",
        },
    )
    commands = drift._go_commands(tmp_path, survey_mod.run(tmp_path).files)
    assert len(commands) == 1
    assert len(commands[0].flags) == 1


def test_a_cargo_workspace_gives_one_command_per_binary_member(tmp_path: Path) -> None:
    """Members with `src/main.rs` give a command with their own flags; a library gives none.

    arch: D15.16, D15.17
    """
    _commit_files(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n',
            "crates/a/Cargo.toml": '[package]\nname = "alpha"\n',
            "crates/a/src/main.rs": '#[arg(long = "fast")]\nfn main() {}\n',
            "crates/b/Cargo.toml": '[package]\nname = "beta"\n',
            "crates/b/src/main.rs": '.long("slow")\n',
            "crates/c/Cargo.toml": '[package]\nname = "gamma"\n',
            "crates/c/src/lib.rs": '.long("lib")\n',
        },
    )
    commands = drift._rust_commands(tmp_path, survey_mod.run(tmp_path).files)
    assert {(c.name, c.flags) for c in commands} == {
        ("alpha", frozenset({"--fast"})),
        ("beta", frozenset({"--slow"})),
    }


def test_a_syntax_warning_does_not_escape_the_flag_scan(tmp_path: Path) -> None:
    """A file with an invalid escape parses without a `SyntaxWarning`.

    arch: D15.16, D15.17
    """
    import warnings

    path = tmp_path / "cli.py"
    path.write_text('X = "\\d"\np.add_argument("--x")\n', encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert drift._python_flags(path) == frozenset({"--x"})
