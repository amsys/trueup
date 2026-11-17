"""Tests for the config layers: profiles, the user default file, the merge and the cache (arch: D14.1, D14.3, D14.15)."""

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import fields, replace
from datetime import date
from pathlib import Path

import pytest

from conftest import materialise
from trueup import apply as apply_mod
from trueup import cli, config, report

PROFILE_DIR = Path(config.__file__).resolve().parent / "data" / "profiles"


def _user_dir() -> Path:
    """Give the trueup user config directory that the autouse fixture set.

    Returns:
        `$XDG_CONFIG_HOME/trueup`.
    """
    return Path(os.environ["XDG_CONFIG_HOME"]) / "trueup"


def _write(path: Path, text: str) -> Path:
    """Write a text file and make its parent directories.

    Args:
        path: The file.
        text: The content.

    Returns:
        The file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _user_profile(name: str, text: str) -> Path:
    """Write a user profile file.

    Args:
        name: The profile name.
        text: The TOML text.

    Returns:
        The file.
    """
    return _write(_user_dir() / "profiles" / f"{name}.toml", text)


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
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_fixture_moves_the_user_directories_under_tmp_path(tmp_path: Path) -> None:
    """The autouse fixture isolates every test from the real user files.

    arch: D14.1, D14.3, D14.15
    """
    assert Path(os.environ["XDG_CONFIG_HOME"]).is_relative_to(tmp_path)
    assert Path(os.environ["XDG_CACHE_HOME"]).is_relative_to(tmp_path)
    assert "TRUEUP_PROFILE" not in os.environ
    assert config.config_home() == tmp_path / "xdg-config" / "trueup"
    assert config.cache_home() == tmp_path / "xdg-cache" / "trueup"


@pytest.mark.parametrize("value", [None, ""])
def test_empty_or_unset_xdg_falls_back_to_the_home_directory(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """An empty or unset XDG variable means the directory under the home directory.

    arch: D14.1, D14.3, D14.15
    """
    for name in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)
    assert config.config_home() == Path.home() / ".config" / "trueup"
    assert config.cache_home() == Path.home() / ".cache" / "trueup"


def test_builtin_names_and_files() -> None:
    """The built-in profiles are `house` and `minimal`, each a package file (I-46).

    arch: D14.1, D14.3, D14.15
    """
    assert config.BUILTIN_PROFILES == ("house", "minimal")
    for name in config.BUILTIN_PROFILES:
        assert (PROFILE_DIR / f"{name}.toml").is_file()


def test_house_profile_writes_every_key_at_its_default() -> None:
    """`house.toml` holds each key a profile can set, at its default value.

    The keys that the file cannot hold are the target-only keys, `profile`,
    `[root] base` (absent by default), `[refs] path` (copy mode only),
    `[refs] layout` (it cannot stand beside the `[layout]` switches) and
    `[[eslint.off]]` (no entry by default).

    arch: D14.1, D14.3, D14.15
    """
    path = PROFILE_DIR / "house.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    parsed = config._parse(raw, source=path, layer="profile")
    assert parsed == config.Config()
    left_out = {
        "version",
        "run_date",
        "keep",
        "profile",
        "root.base",
        "refs.path",
        "refs.layout",
        "refs.declared",
        "refs.id_forms",
        "refs.accepted_reader_changes",
        "eslint.off",
    }
    wanted = (set(config._MERGE_FIELDS) | {"languages"}) - left_out
    assert wanted <= config._explicit_keys(raw)


def test_minimal_profile_holds_the_minimal_column() -> None:
    """`minimal.toml` sets the `minimal` values of the D14.2 table.

    arch: D14.1, D14.2, D14.3, D14.15, D15.14
    """
    path = PROFILE_DIR / "minimal.toml"
    parsed = config._parse(
        tomllib.loads(path.read_text(encoding="utf-8")), source=path, layer="profile"
    )
    assert parsed == replace(
        config.Config(),
        docs="readme",
        layout_front_matter=False,
        layout_types=False,
        layout_index=False,
        prose_banned="off",
        refs_registry=False,
        refs_comments=False,
        health_agents=False,
        health_files="readme",
        scratch_gitignore=False,
    )


def test_no_target_and_no_user_default_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With neither file the target is not adopted, also with `TRUEUP_PROFILE` set.

    The profile still resolves (D15.6): `load` gives the effective config
    of the named profile, and `load_target` gives `None`.

    arch: D14.1, D14.3, D14.15, D15.6
    """
    monkeypatch.setenv("TRUEUP_PROFILE", "minimal")
    layers = config.load_layers(tmp_path)
    assert layers.adopted is False
    assert (layers.profile, layers.profile_source) == ("minimal", "TRUEUP_PROFILE")
    assert config.load(tmp_path).docs == "readme"
    assert config.load_target(tmp_path) is None


def test_house_effective_equals_the_target_file_alone(tmp_path: Path) -> None:
    """With no profile set, the effective config is the target file over the defaults (I-48).

    arch: D14.1, D14.3, D14.15, I-48
    """
    text = (
        'tier = "T2"\nignore = ["vendor/**"]\n\n[refs]\nmode = "copy"\n'
        'layout = false\n\n[languages]\npython = "strict"\n\n'
        '[[keep]]\nid = "a:b"\nreason = "kept"\n'
    )
    _write(tmp_path / "trueup.toml", text)
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.profile == "house"
    assert layers.profile_path == PROFILE_DIR / "house.toml"
    assert layers.user_default is None
    assert layers.target == config.load_target(tmp_path)
    assert layers.target is not None
    assert layers.effective == replace(layers.target, explicit=None)
    assert layers.effective.profile is None
    assert config.load(tmp_path) == layers.effective


def test_minimal_profile_under_a_target_file(tmp_path: Path) -> None:
    """A target key wins over the profile; the target layer holds only its own keys.

    arch: D14.1, D14.3, D14.15, D15.27
    """
    _write(
        tmp_path / "trueup.toml",
        'profile = "minimal"\n\n[layout]\nindex = true\n',
    )
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.profile == "minimal"
    assert layers.profile_path == PROFILE_DIR / "minimal.toml"
    cfg = layers.effective
    assert cfg.profile == "minimal"
    assert cfg.docs == "readme"
    assert cfg.layout_front_matter is False
    assert cfg.layout_index is True
    assert cfg.prose_banned == "off"
    assert cfg.explicit is None
    assert layers.target is not None
    assert layers.target.explicit == frozenset({"profile", "layout", "layout.index"})
    assert layers.target.docs == "auto"
    assert config.render(layers.target) == (
        "# trueup configuration. The trueup skill writes this file. A person can edit it.\n"
        "# comments do not survive a config write; trueup writes this file\n"
        "version = 1\n"
        'profile = "minimal"                # house | minimal | a user profile (D14.1)\n'
        "\n[layout]\n"
        "index = true                   # true: an index links each page (D14.2)\n"
    )


def test_trueup_profile_wins_over_the_target_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TRUEUP_PROFILE` names the profile also when the target file names another.

    arch: D14.1, D14.3, D14.15
    """
    _write(tmp_path / "trueup.toml", 'profile = "minimal"\n')
    monkeypatch.setenv("TRUEUP_PROFILE", "house")
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.profile == "house"
    assert layers.effective.docs == "auto"
    assert layers.effective.profile == "house"


def test_user_profile_resolves_and_merges(tmp_path: Path) -> None:
    """A user profile is read; lists replace, `[[eslint.off]]` too, tables merge per key, languages per entry.

    arch: D14.1, D14.3, D14.15, D15.29
    """
    path = _user_profile(
        "mine",
        'ignore = ["a/**"]\nstale_days = 30\n\n[layout]\ntypes = false\n\n'
        '[languages]\npython = "off"\n\n'
        '[[eslint.off]]\nrule = "no-console"\nreason = "profile"\n\n'
        '[[eslint.off]]\nrule = "eqeqeq"\nreason = "profile"\n',
    )
    _write(
        tmp_path / "trueup.toml",
        'profile = "mine"\nignore = ["b/**"]\n\n[refs]\nlayout = true\n\n'
        '[languages]\ntypescript = "clean"\n\n'
        '[[eslint.off]]\nrule = "no-console"\nreason = "target"\n',
    )
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.profile == "mine"
    assert layers.profile_path == path
    cfg = layers.effective
    assert cfg.ignore == ("b/**",)
    assert cfg.stale_days == 30
    assert cfg.layout_types is True
    assert cfg.languages == {"python": "off", "typescript": "clean"}
    # D15.29: a layer that sets [[eslint.off]] replaces the lower list.
    assert cfg.eslint_off == {"no-console": "target"}


def test_unresolved_profile_names_both_search_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A name that resolves nowhere is exit 2 with both paths, never `house` (I-44).

    arch: D14.1, D14.3, D14.15
    """
    _write(tmp_path / "trueup.toml", 'profile = "mine"\n')
    with pytest.raises(config.ConfigError) as caught:
        config.load(tmp_path)
    message = str(caught.value)
    assert str(PROFILE_DIR) in message
    assert str(_user_dir() / "profiles" / "mine.toml") in message
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert str(PROFILE_DIR) in err
    assert str(_user_dir() / "profiles" / "mine.toml") in err


def test_apply_leaves_no_profile_key_in_the_target_file(tmp_path: Path) -> None:
    """`apply --all-auto` under a user profile writes none of its keys (I-45).

    arch: D14.1, D14.3, D14.15, D14.19
    """
    _user_profile(
        "mine",
        'docs = "readme"\nstale_days = 30\nignore = ["x/**"]\n\n'
        "[health]\nagents = false\n\n[layout]\ntypes = false\n",
    )
    root = materialise("messy", tmp_path / "repo")
    _git(root, "init", "-q")
    _write(root / "trueup.toml", 'profile = "mine"\n')
    code = apply_mod.run(
        root,
        ids=None,
        all_auto=True,
        mode_args=[],
        set_args=[],
        today=date(2026, 10, 16),
        allow_dirty=True,
    )
    assert code == 0
    raw = tomllib.loads((root / "trueup.toml").read_text(encoding="utf-8"))
    assert raw["profile"] == "mine"
    assert raw["run_date"] == "2026-10-16"
    for key in ("docs", "stale_days", "ignore", "health", "layout"):
        assert key not in raw


@pytest.mark.parametrize("name", ["house", "minimal"])
def test_user_file_with_a_builtin_name_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    """A user file cannot shadow a built-in profile (I-46).

    arch: D14.1, D14.3, D14.15, I-46
    """
    shadow = _user_profile(name, "")
    _write(tmp_path / "trueup.toml", "")
    with pytest.raises(config.ConfigError, match="shadows the built-in profile"):
        config.load(tmp_path)
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    assert str(shadow) in capsys.readouterr().err


@pytest.mark.parametrize("value", ["Mine", "-x", "a_b", "../x"])
def test_bad_profile_name_is_an_error(
    tmp_path: Path, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad name from the target file or from `TRUEUP_PROFILE` is a `ConfigError`.

    arch: D14.1, D14.3, D14.15
    """
    _write(tmp_path / "trueup.toml", f"profile = {value!r}\n".replace("'", '"'))
    with pytest.raises(config.ConfigError, match="lower-case letters"):
        config.load(tmp_path)
    _write(tmp_path / "trueup.toml", "")
    monkeypatch.setenv("TRUEUP_PROFILE", value)
    with pytest.raises(config.ConfigError, match="lower-case letters"):
        config.load(tmp_path)


def test_user_default_applies_only_without_a_target_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user default file adopts a target with no file; a target file shuts it out (I-44).

    arch: D14.1, D14.3, D14.15, I-44
    """
    user = _write(_user_dir() / "trueup.toml", 'profile = "minimal"\nstale_days = 9\n')
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.target is None
    assert layers.user_default == user
    assert layers.profile == "minimal"
    assert layers.effective.stale_days == 9
    assert layers.effective.docs == "readme"
    assert config.load_target(tmp_path) is None
    monkeypatch.setenv("TRUEUP_PROFILE", "house")
    assert config.load(tmp_path).docs == "auto"  # type: ignore[union-attr]
    monkeypatch.delenv("TRUEUP_PROFILE")

    _write(tmp_path / "trueup.toml", "")
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.user_default is None
    assert layers.profile == "house"
    assert layers.effective == replace(config.Config(), explicit=None)


def test_user_default_does_not_change_check_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target with `trueup.toml` gives the same `check --json` with and without a user default file (I-44).

    arch: D14.1, D14.3, D14.15
    """
    root = materialise("messy", tmp_path / "repo")
    _write(root / "trueup.toml", 'tier = "T1"\n')
    cli.main(["check", "--root", str(root), "--json"])
    without = capsys.readouterr().out
    _write(_user_dir() / "trueup.toml", 'docs = "readme"\n')
    config.clear_cache()
    cli.main(["check", "--root", str(root), "--json"])
    assert capsys.readouterr().out == without


@pytest.mark.parametrize(
    ("layer_file", "text", "match"),
    [
        ("user", 'run_date = "2026-10-16"\n', "only the target"),
        ("user", "version = 1\n", "only the target"),
        ("user", '[[keep]]\nid = "a"\nreason = "b"\n', "only the target"),
        ("profile", 'run_date = "2026-10-16"\n', "only the target"),
        ("profile", 'profile = "minimal"\n', "cannot set profile"),
        ("profile", "tier = 3\n", "tier must be one of"),
        ("profile", "tier = \n", "not valid TOML"),
    ],
)
def test_layer_rules_name_the_file(
    tmp_path: Path, layer_file: str, text: str, match: str
) -> None:
    """A profile or user default file that breaks a layer rule is an error that names the file.

    arch: D14.1, D14.3, D14.15
    """
    if layer_file == "user":
        path = _write(_user_dir() / "trueup.toml", text)
    else:
        path = _user_profile("mine", text)
        _write(tmp_path / "trueup.toml", 'profile = "mine"\n')
    with pytest.raises(config.ConfigError, match=match) as caught:
        config.load(tmp_path)
    assert str(path) in str(caught.value)


def test_banned_paths_resolve_per_layer(tmp_path: Path) -> None:
    """A `[prose] banned` path is relative to the file that set it; the target layer keeps it as written.

    arch: D14.1, D14.2, D14.3, D14.15
    """
    words = _write(_user_dir() / "profiles" / "words.txt", "foo\n")
    _user_profile("mine", '[prose]\nbanned = "words.txt"\n')
    _write(tmp_path / "trueup.toml", 'profile = "mine"\n')
    assert config.load(tmp_path).prose_banned == str(words.resolve())  # type: ignore[union-attr]

    own = _write(tmp_path / "lint" / "own.txt", "bar\n")
    _write(
        tmp_path / "trueup.toml",
        'profile = "mine"\n\n[prose]\nbanned = "lint/own.txt"\n',
    )
    layers = config.load_layers(tmp_path)
    assert layers is not None
    assert layers.effective.prose_banned == str(own.resolve())
    assert layers.target is not None
    assert layers.target.prose_banned == "lint/own.txt"


def test_merge_covers_every_config_field() -> None:
    """Each `Config` field that a file sets is in the merge, so a new key cannot drop out of `load`.

    arch: D14.3, D14.15
    """
    merged = {name for group in config._MERGE_FIELDS.values() for name in group}
    merged |= {"languages", "eslint_off", "profile", "explicit"}
    assert {item.name for item in fields(config.Config)} == merged


def test_cache_returns_the_same_layers_until_a_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second load is a cache hit; a changed, new or removed layer file is read again (D14.3).

    With the target file removed, the target is not adopted and the
    cached layers resolve `minimal` (D15.6).

    arch: D14.1, D14.3, D14.15, D15.6
    """
    target = _write(tmp_path / "trueup.toml", 'tier = "T1"\n')
    first = config.load_layers(tmp_path)
    assert config.load_layers(tmp_path) is first

    target.write_text('tier = "T2"\n', encoding="utf-8")
    assert config.load(tmp_path).tier == "T2"  # type: ignore[union-attr]

    target.write_text('profile = "mine"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)
    profile = _user_profile("mine", "stale_days = 5\n")
    assert config.load(tmp_path).stale_days == 5  # type: ignore[union-attr]
    profile.write_text("stale_days = 6\n", encoding="utf-8")
    assert config.load(tmp_path).stale_days == 6  # type: ignore[union-attr]

    monkeypatch.setenv("TRUEUP_PROFILE", "minimal")
    assert config.load(tmp_path).docs == "readme"  # type: ignore[union-attr]
    monkeypatch.delenv("TRUEUP_PROFILE")

    target.unlink()
    assert config.load(tmp_path).docs == "readme"
    hit = config.load_layers(tmp_path)
    assert hit is config.load_layers(tmp_path)
    assert hit.adopted is False and hit.profile == "minimal"
    config.clear_cache()
    assert config.load_layers(tmp_path) == hit


def test_user_default_language_row_is_info_and_check_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Under the user default file a present language with no mode is an `info` row, so `check` exits 0.

    `apply` writes a language mode only through `config:trueup.toml`
    (I-44, I-45). An auto `error` row here is a plan item that
    `apply --all-auto` cannot clear, so the target stays at exit 1.

    arch: D14.3, D14.8
    """
    _write(_user_dir() / "trueup.toml", 'profile = "minimal"\n')
    root = tmp_path / "repo"
    _write(
        root / "pkg.py",
        '"""Values."""\n\n' + "".join(f"VALUE_{n} = {n}\n" for n in range(60)),
    )
    _write(root / "README.md", "# Repo\n\nA test repository.\n")
    _write(root / ".gitignore", "*.pyc\n")
    _git(root, "init", "-q")
    run = report.collect(root)
    assert run.survey.languages["python"].present
    found = {finding.id: finding for finding in run.findings}
    python = found["config:languages.python"]
    assert (python.severity, python.auto) == ("info", False)
    assert python.action == (
        "set [languages] python in the user default file, or write trueup.toml"
    )
    assert run.plan == []
    assert cli.main(["check", "--root", str(root)]) == 0
    capsys.readouterr()
    assert not (root / "trueup.toml").exists()


# -- D15.29: config layers -------------------------------------------------


def test_refs_path_needs_copy_mode_after_the_merge(tmp_path: Path) -> None:
    """`refs.path` in the target is valid when a profile sets copy mode, and not when the target sets global.

    arch: D15.29
    """
    _user_profile("p1", '[refs]\nmode = "copy"\n')
    _write(
        tmp_path / "trueup.toml",
        'profile = "p1"\n\n[refs]\npath = "tools/rc.py"\n',
    )
    cfg = config.load(tmp_path)
    assert (cfg.refs_mode, cfg.refs_path) == ("copy", "tools/rc.py")

    _user_profile("p2", '[refs]\nmode = "copy"\npath = "tools/rc.py"\n')
    other = tmp_path / "other"
    _write(other / "trueup.toml", 'profile = "p2"\n\n[refs]\nmode = "global"\n')
    with pytest.raises(config.ConfigError) as caught:
        config.load(other)
    assert 'refs.path needs refs.mode = "copy"' in str(caught.value)
    assert str(caught.value).startswith(f"{other / 'trueup.toml'}: ")


def test_a_higher_layer_resets_eslint_off_and_root_base(tmp_path: Path) -> None:
    """`[eslint] off = []` and `[root] base = "code"` in the target reset the lists of the profile.

    arch: D15.29
    """
    _user_profile(
        "p1",
        '[root]\nbase = ["src"]\n\n'
        '[[eslint.off]]\nrule = "no-console"\nreason = "profile"\n',
    )
    _write(
        tmp_path / "trueup.toml",
        'profile = "p1"\n\n[root]\nbase = "code"\n\n[eslint]\noff = []\n',
    )
    cfg = config.load(tmp_path)
    assert cfg.eslint_off == {}
    assert cfg.root_base is None
    assert config.load_target(tmp_path).root_base is None


def test_a_higher_layout_switch_wins_over_a_lower_refs_layout(tmp_path: Path) -> None:
    """A target `[layout]` switch wins over a profile `[refs] layout = false`, and the readers obey the switch.

    arch: D15.29
    """
    _user_profile("p1", "[refs]\nlayout = false\n")
    _write(
        tmp_path / "trueup.toml",
        'profile = "p1"\n\n[layout]\ntypes = true\n',
    )
    cfg = config.load(tmp_path)
    assert (cfg.refs_layout, cfg.layout_types, cfg.layout_front_matter) == (
        False,
        True,
        False,
    )
    from trueup import layout

    page = "---\ntype: how-to\n---\n# Run\n"
    target = layout._standard_target("run.md", page, replace(cfg, docs="full"))
    assert target[0] == "docs/how-to/run.md"


def test_house_profile_documents_eslint_off_and_drops_the_old_default_text() -> None:
    """`house.toml` shows `[[eslint.off]]` as a commented example and no longer says it applies by default.

    arch: D15.29
    """
    text = (PROFILE_DIR / "house.toml").read_text(encoding="utf-8")
    assert "# [[eslint.off]]" in text
    assert "applies when no layer names a profile" not in text
