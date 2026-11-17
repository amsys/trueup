"""Tests for the profile that resolves on every target, and the scope of `--profile` (arch: D15.6)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from trueup import cli, config, report

PROFILE_DIR = Path(config.__file__).resolve().parent / "data" / "profiles"


def _git(root: Path, *args: str) -> None:
    """Run one git command in a test repository, with signing off.

    Args:
        root: The repository.
        *args: The git arguments.
    """
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=test",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repo(root: Path) -> Path:
    """Make an empty git repository with one README.

    Args:
        root: The directory to make.

    Returns:
        The root.
    """
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_text("# Demo\n\nA demo.\n", encoding="utf-8")
    return root


def test_a_target_that_is_not_adopted_resolves_the_minimal_profile(
    tmp_path: Path,
) -> None:
    """With no target file and no user default file, the layers resolve `minimal`.

    arch: D15.6
    """
    layers = config.load_layers(tmp_path)
    assert layers.adopted is False
    assert layers.profile == "minimal"
    assert layers.profile_path == PROFILE_DIR / "minimal.toml"
    assert layers.profile_source == "built-in default"
    assert layers.target is None
    cfg = config.load(tmp_path)
    assert cfg.docs == "readme"
    assert cfg.refs_registry is False
    assert config.load_target(tmp_path) is None


def test_an_adopted_target_with_no_profile_key_resolves_house(tmp_path: Path) -> None:
    """A target file that names no profile gives `house`, from the built-in default.

    arch: D15.6
    """
    (tmp_path / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    layers = config.load_layers(tmp_path)
    assert layers.adopted is True
    assert layers.profile == "house"
    assert layers.profile_source == "built-in default"


def test_the_user_default_file_adopts_the_target(tmp_path: Path) -> None:
    """The user default file alone adopts a target; its `profile` key has the source `user default`.

    arch: D15.6
    """
    user = config.config_home() / "trueup.toml"
    user.parent.mkdir(parents=True)
    user.write_text('profile = "minimal"\n', encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    layers = config.load_layers(root)
    assert layers.adopted is True
    assert (layers.profile, layers.profile_source) == ("minimal", "user default")


@pytest.mark.parametrize("adopted", [False, True])
def test_the_variable_and_the_target_key_name_their_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, adopted: bool
) -> None:
    """`TRUEUP_PROFILE` wins on every target; the target key has the source `target`.

    arch: D15.6
    """
    if adopted:
        (tmp_path / "trueup.toml").write_text(
            'version = 1\nprofile = "minimal"\n', encoding="utf-8"
        )
        layers = config.load_layers(tmp_path)
        assert (layers.profile, layers.profile_source) == ("minimal", "target")
    monkeypatch.setenv("TRUEUP_PROFILE", "house")
    layers = config.load_layers(tmp_path)
    assert layers.adopted is adopted
    assert (layers.profile, layers.profile_source) == ("house", "TRUEUP_PROFILE")


def test_the_profile_flag_wins_and_restores_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profile_flag` names the source `--profile`, and restores the variable on exit and on error.

    arch: D15.6
    """
    monkeypatch.setenv("TRUEUP_PROFILE", "house")
    with config.profile_flag("minimal"):
        assert os.environ["TRUEUP_PROFILE"] == "minimal"
        layers = config.load_layers(tmp_path)
        assert (layers.profile, layers.profile_source) == ("minimal", "--profile")
    assert os.environ["TRUEUP_PROFILE"] == "house"
    assert config.load_layers(tmp_path).profile_source == "TRUEUP_PROFILE"

    monkeypatch.delenv("TRUEUP_PROFILE")
    with pytest.raises(RuntimeError), config.profile_flag("minimal"):
        raise RuntimeError("stop")
    assert "TRUEUP_PROFILE" not in os.environ
    assert config.load_layers(tmp_path).profile_source == "built-in default"


def test_main_leaves_the_environment_as_it_found_it(tmp_path: Path) -> None:
    """`--profile` sets the variable for the run only; `main` restores it after the run.

    arch: D15.6
    """
    root = _repo(tmp_path / "repo")
    assert cli.main(["survey", "--root", str(root), "--profile", "minimal"]) == 0
    assert "TRUEUP_PROFILE" not in os.environ


@pytest.mark.parametrize("toml", [None, "version = 1\n"])
def test_an_unknown_profile_flag_is_exit_2_on_every_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], toml: str | None
) -> None:
    """An unknown `--profile` name stops the run at exit 2, adopted or not; the message names the flag.

    arch: D15.6, I-44
    """
    root = _repo(tmp_path / "repo")
    if toml is not None:
        (root / "trueup.toml").write_text(toml, encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["survey", "--root", str(root), "--profile", "nosuch"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("trueup: --profile: profile 'nosuch' is not found")
    assert "TRUEUP_PROFILE" not in os.environ


def test_an_unknown_variable_is_an_error_on_a_target_that_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown or bad `TRUEUP_PROFILE` value is a `ConfigError` that names the variable.

    arch: D15.6
    """
    monkeypatch.setenv("TRUEUP_PROFILE", "nosuch")
    with pytest.raises(config.ConfigError, match=r"^TRUEUP_PROFILE: profile 'nosuch'"):
        config.load_layers(tmp_path)
    monkeypatch.setenv("TRUEUP_PROFILE", "BAD")
    with pytest.raises(config.ConfigError, match=r"^TRUEUP_PROFILE: profile name must"):
        config.load(tmp_path)


def _t2_tree(root: Path) -> Path:
    """Write a T2-shaped git repository whose comments carry `NOTE:`, `A1:` and `H3:` labels (row B6).

    Two manifests and one tag make the tree T2 without a `tier` key.

    Args:
        root: The directory to make.

    Returns:
        The root.
    """
    _repo(root)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text(
        '# NOTE: keep this\ndef f():\n    """F."""\n    # H3: header\n',
        encoding="utf-8",
    )
    (root / "src" / "m.rs").write_text("// A1: first\nfn m() {}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (root / "Cargo.toml").write_text('[package]\nname = "demo"\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    _git(root, "tag", "v1")
    return root


def _refcheck_rules(root: Path) -> set[str]:
    """Give the `refcheck` finding ids of one `report.collect` run.

    Args:
        root: The target root.

    Returns:
        The ids of the `refcheck` findings.
    """
    run = report.collect(root)
    assert run.survey.tier == "T2"
    return {finding.id for finding in run.findings if finding.rule == "refcheck"}


def test_labels_give_no_refcheck_row_on_a_target_that_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row B6: under `minimal`, `NOTE:`, `A1:` and `H3:` give no row; `profile = "house"` gives `unregistered`.

    arch: D15.6
    """
    monkeypatch.setattr(report.secrets, "scan", lambda *_args, **_kw: None)
    root = _t2_tree(tmp_path / "repo")
    assert _refcheck_rules(root) == set()
    (root / "trueup.toml").write_text(
        'version = 1\nprofile = "house"\n', encoding="utf-8"
    )
    unregistered = {
        rule for rule in _refcheck_rules(root) if rule.endswith(":unregistered")
    }
    assert {rule.split(":")[1] for rule in unregistered} == {"src/a.py", "src/m.rs"}
