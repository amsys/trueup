"""Tests for `trueup template <name>`: the texts of the files trueup no longer manages (arch: D14.9, D14.22)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from trueup import cli, managed
from trueup.rulesets import MANAGED_HEADER, template_path

_HEALTH_FILES: dict[str, str] = {
    "contributing": "CONTRIBUTING.md",
    "security": "SECURITY.md",
    "code-of-conduct": "CODE_OF_CONDUCT.md",
    "changelog": "CHANGELOG.md",
    "issue-template": "ISSUE_TEMPLATE.md",
    "pr-template": "PULL_REQUEST_TEMPLATE.md",
}
"""Each health name of D14.9 to its file under `templates/health/`."""

_PIN = re.compile(r"^\s*- uses: [\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40} # \S+$")
"""The I-32 form of one `uses:` line: owner, repo, optional path, SHA, tag comment."""

_INSTALL_PLACEHOLDER = (
    "# install trueup here, for example: pip install <path or URL of trueup>"
)
"""The placeholder comment of the CI install step (D14.9)."""


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run the CLI and capture its output.

    Args:
        argv: The arguments after `trueup`.
        capsys: The pytest capture fixture.

    Returns:
        The exit code, stdout and stderr.
    """
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_template_names_are_the_d14_9_names() -> None:
    """`TEMPLATE_NAMES` holds pre-commit, editorconfig, ci and the six health pages, in that order.

    arch: D14.22, D14.9
    """
    assert managed.TEMPLATE_NAMES == (
        "pre-commit",
        "editorconfig",
        "ci",
        *_HEALTH_FILES,
    )


def test_every_template_prints_with_exit_zero_and_no_trueup_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each name prints its text to stdout with exit 0, outside a git repository, with no trueup header line.

    The command reads no target, so a working directory with no git
    repository and no `trueup.toml` does not matter.

    arch: D14.22, D14.9
    """
    monkeypatch.chdir(tmp_path)
    for name in managed.TEMPLATE_NAMES:
        code, out, err = _run(["template", name], capsys)
        assert code == 0, name
        assert err == "", name
        assert out == managed.template_text(name), name
        assert out.strip(), name
        assert out.endswith("\n"), name
        assert MANAGED_HEADER not in out, name
        assert "trueup health skeleton" not in out, name


def test_unknown_or_missing_template_name_lists_the_names_and_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown name and no name both exit 2 and list every name on stderr; stdout stays empty.

    arch: D14.22, D14.9
    """
    for argv in (["template", "nope"], ["template"]):
        code, out, err = _run(argv, capsys)
        assert code == 2, argv
        assert out == "", argv
        for name in managed.TEMPLATE_NAMES:
            assert name in err, (argv, name)
    with pytest.raises(ValueError, match="pre-commit"):
        managed.template_text("nope")


def test_template_takes_no_root_option(capsys: pytest.CaptureFixture[str]) -> None:
    """`template` has no `--root`: argparse rejects it with exit 2.

    arch: D14.22, D14.9
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["template", "ci", "--root", "."])
    assert excinfo.value.code == 2
    capsys.readouterr()


def test_pre_commit_snippet_is_one_local_trueup_lint_hook() -> None:
    """The pre-commit snippet has one `repo: local` hook with the D14.9 keys, and reads no config.

    arch: D14.22, D14.9
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    text = managed.render_pre_commit()
    assert yaml.safe_load(text) == {
        "repos": [
            {
                "repo": "local",
                "hooks": [
                    {
                        "id": "trueup-lint",
                        "name": "trueup lint",
                        "entry": "trueup lint",
                        "language": "system",
                        "pass_filenames": True,
                        "require_serial": True,
                    }
                ],
            }
        ]
    }
    assert managed.template_text("pre-commit") == text


@pytest.mark.skipif(
    shutil.which("pre-commit") is None, reason="pre-commit is not installed"
)
def test_pre_commit_snippet_validates_with_pre_commit(tmp_path: Path) -> None:
    """`pre-commit validate-config` accepts the snippet as a whole file.

    arch: D14.22, D14.9
    """
    path = tmp_path / ".pre-commit-config.yaml"
    path.write_text(managed.render_pre_commit(), encoding="utf-8")
    result = subprocess.run(
        ["pre-commit", "validate-config", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_text_pins_actions_and_runs_check_then_lint() -> None:
    """The CI text pins every action (I-32), has the install placeholder, then `trueup check` and `trueup lint`.

    The template file is the text as it is: no trueup header line, no
    pre-commit step, no line that `render_ci` must fill.

    arch: D14.22, D14.9
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    text = managed.render_ci()
    assert text == template_path("ci/trueup.yml").read_text(encoding="utf-8")
    assert MANAGED_HEADER not in text
    assert "Managed by trueup" not in text
    assert "pre-commit" not in text
    uses = [line for line in text.splitlines() if "uses:" in line]
    assert len(uses) == 3
    for line in uses:
        assert _PIN.match(line), line
    assert "permissions:\n  contents: read\n" in text
    lines = [line.strip() for line in text.splitlines()]
    placeholder = lines.index(_INSTALL_PLACEHOLDER)
    check = lines.index("- run: trueup check --root .")
    lint = lines.index("- run: trueup lint --root .")
    assert placeholder < check < lint
    steps = yaml.safe_load(text)["jobs"]["check"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]
    assert runs[-2:] == ["trueup check --root .", "trueup lint --root ."]


def test_ci_text_installs_ruff_and_vale_pinned_and_names_the_opt_out() -> None:
    """The CI text installs `ruff` and `vale` at exact versions before the check, and names `--skip-missing`; the text reads no config.

    arch: D15.4, D14.9
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    text = managed.render_ci()
    steps = yaml.safe_load(text)["jobs"]["check"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]
    install = [run for run in runs if run.startswith("pip install")]
    assert len(install) == 1
    assert re.search(r"\bruff==\d+\.\d+\.\d+\b", install[0])
    assert re.search(r"\bvale==\d+(\.\d+)+\b", install[0])
    assert runs.index(install[0]) < runs.index("trueup lint --root .")
    assert "trueup lint --skip-missing" in text


@pytest.mark.parametrize("name", ["editorconfig", *_HEALTH_FILES])
def test_file_templates_are_the_template_without_its_header_line(name: str) -> None:
    """`editorconfig` and each health page print their template file minus its trueup header line.

    arch: D14.22, D14.9
    """
    relative = (
        "editorconfig" if name == "editorconfig" else f"health/{_HEALTH_FILES[name]}"
    )
    source = template_path(relative).read_text(encoding="utf-8")
    first, _, rest = source.partition("\n")
    assert MANAGED_HEADER in first or "trueup health skeleton" in first
    assert managed.template_text(name) == rest.lstrip("\n")
