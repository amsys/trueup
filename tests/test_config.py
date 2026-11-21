"""Tests for `trueup.config`: load, render and their validation errors."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from trueup import config as config_mod
from trueup.config import (
    Config,
    ConfigError,
    load,
    load_target,
    public_is_false,
    render,
    resolve_docs,
)


def test_load_returns_none_when_absent(tmp_path: Path) -> None:
    """For a root with no `trueup.toml`, `load` gives the `minimal` config and `load_target` gives `None`.

    Decision 2 inverts the old `None` of `load` (D15.6). The test name is
    from before that decision.

    arch: D5.3, D15.6
    """
    cfg = load(tmp_path)
    assert cfg.docs == "readme"
    assert cfg.refs_registry is False
    assert config_mod.load_target(tmp_path) is None
    assert config_mod.load_layers(tmp_path).adopted is False


def test_render_key_order_and_round_trip(tmp_path: Path) -> None:
    """`render` writes the fixed key order, and `load` reads it back equal.

    `public`, `stale_days` and `protect` hold their default values, so the
    config lists them in `explicit`: `render` writes a default value only
    for a key the file set (D14.3).

    arch: D5.3, D14.3
    """
    cfg = Config(
        run_date="2026-09-25",
        tier="T2",
        public=False,
        docs="full",
        stale_days=180,
        ignore=("tests/fixtures/**",),
        protect=(),
        root_allow=(".claude-plugin", "trueup"),
        scratch_allow=("docs/notes.md",),
        languages={"python": "clean", "rust": "strict"},
        keep={"prose:docs/explanation/x.md": "source document, text as received"},
        explicit=frozenset({"public", "stale_days", "protect"}),
    )
    text = render(cfg)
    lines = [line for line in text.splitlines() if line]
    key_order = [
        "version",
        "run_date",
        "tier",
        "public",
        "docs",
        "stale_days",
        "ignore",
        "protect",
        "[root]",
        "allow",
        "[scratch]",
        "[languages]",
    ]
    positions = []
    for key in key_order:
        needle = key if key.startswith("[") else f"{key} ="
        matches = [i for i, line in enumerate(lines) if line.startswith(needle)]
        assert matches, f"{key!r} missing from rendered trueup.toml"
        positions.append(matches[0])
    assert positions == sorted(positions), (
        "trueup.toml keys are out of the fixed D5.3 order"
    )
    # languages render in the fixed LANGUAGES order, not insertion order.
    assert text.index('python = "clean"') < text.index('rust = "strict"')

    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded == replace(cfg, explicit=None)


def test_render_is_deterministic() -> None:
    """Two equal `Config`s with `languages` and `keep` in a different order render the same bytes (I-21).

    Building both dicts in reverse order of each other, rather than calling
    `render` twice on the same object, is what makes this test fail if
    `render` ever iterates `languages` or `keep` in insertion order instead
    of the fixed D5.3 order.

    arch: D5.3
    """
    cfg_a = Config(
        languages={"go": "off", "python": "strict"}, keep={"b:x": "r1", "a:y": "r2"}
    )
    cfg_b = Config(
        languages={"python": "strict", "go": "off"}, keep={"a:y": "r2", "b:x": "r1"}
    )
    assert cfg_a == cfg_b
    assert render(cfg_a) == render(cfg_b)


def test_render_escapes_quotes_and_backslashes(tmp_path: Path) -> None:
    """A glob, id or reason holding a quote or backslash still round-trips (arch: D5.3).

    `render` must escape both characters, or the written `trueup.toml` is
    not valid TOML and `load` raises `ConfigError` on the very file
    `render` just wrote.
    """
    cfg = Config(
        ignore=("C:\\build\\**",),
        keep={"prose:x.md": 'False positive: matches "helper.py".'},
    )
    text = render(cfg)
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg


def test_load_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    """An unknown top-level key raises `ConfigError`.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nbogus = "x"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_bad_tier(tmp_path: Path) -> None:
    """A `tier` value outside T0-T3/auto raises `ConfigError`.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\ntier = "T9"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_unknown_language(tmp_path: Path) -> None:
    """A `[languages]` key that is not one of the eight languages fails.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[languages]\ncobol = "clean"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_bad_language_mode(tmp_path: Path) -> None:
    """A language mode outside strict/clean/off fails.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[languages]\npython = "loose"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_malformed_toml(tmp_path: Path) -> None:
    """Text that `tomllib` cannot parse raises `ConfigError`, not a bare TOMLDecodeError.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text("this is not = [valid toml", encoding="utf-8")
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_keep_entry_missing_reason(tmp_path: Path) -> None:
    """A `[[keep]]` entry without both `id` and `reason` fails.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[[keep]]\nid = "prose:x.md"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_render_escapes_control_and_delete_characters(tmp_path: Path) -> None:
    """A value holding a control character or DEL (U+007F) still round-trips.

    TOML forbids U+0000-U+001F (other than tab) and U+007F raw inside a
    basic string, so `render` must escape all of them, or `load` raises
    `ConfigError` on the very file `render` just wrote.

    arch: D5.3
    """
    cfg = Config(keep={"prose:a\x7fb.md": "bell \x07 and delete \x7f"})
    (tmp_path / "trueup.toml").write_text(render(cfg), encoding="utf-8")
    assert load(tmp_path) == cfg


def test_load_rejects_an_unknown_scratch_key(tmp_path: Path) -> None:
    """`[scratch]` takes only `allow`, a list of strings.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[scratch]\ndeny = []\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[scratch]\nallow = 3\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_refs_path_defaults_to_ref_check_py() -> None:
    """With no `[refs]` table, `refs_path` is `"ref_check.py"`.

    arch: D5.3
    """
    assert Config().refs_path == "ref_check.py"


def test_load_reads_a_custom_refs_path(tmp_path: Path) -> None:
    """`[refs] path` overrides the default checker module path, in copy mode (D9.1).

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[refs]\nmode = "copy"\npath = "tools/checker.py"\n',
        encoding="utf-8",
    )
    cfg = load(tmp_path)
    assert cfg.refs_path == "tools/checker.py"


def test_load_rejects_an_unknown_refs_key(tmp_path: Path) -> None:
    """`[refs]` takes only `path`.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[refs]\nother = 1\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/absolute.py",
        "ref_check",
        "ref_check.txt",
        "a/../ref_check.py",
        "..",
        "a\\b.py",
        "./x.py",
        "a/./b.py",
    ],
)
def test_load_rejects_a_bad_refs_path(tmp_path: Path, bad_path: str) -> None:
    """`[refs] path` must be a relative path, with no `.` or `..` part, ending in `.py`.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\npath = '{bad_path}'\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_load_rejects_a_non_string_refs_path(tmp_path: Path) -> None:
    """`[refs] path` must be a string.

    arch: D5.3
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[refs]\npath = 3\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_render_omits_the_refs_table_at_the_default(tmp_path: Path) -> None:
    """`render` writes no `[refs]` table when `refs_path` is the default (W5).

    arch: D5.3
    """
    text = render(Config())
    assert "[refs]" not in text


def test_render_writes_the_refs_table_when_not_default(tmp_path: Path) -> None:
    """`render` writes `[refs] path` when it differs from the default, in copy mode, and `load` reads it back.

    arch: D5.3
    """
    cfg = Config(refs_mode="copy", refs_path="trueup/ref_check.py")
    text = render(cfg)
    assert "[refs]" in text
    assert 'mode = "copy"' in text
    assert 'path = "trueup/ref_check.py"' in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path).refs_path == "trueup/ref_check.py"


def test_load_reads_refs_local_tags(tmp_path: Path) -> None:
    """`[refs] local_tags` lists the project's own tag prefixes; absent, it is empty (D8.7).

    arch: D8.7
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[refs]\nlocal_tags = ["X", "G"]\n', encoding="utf-8"
    )
    cfg = load(tmp_path)
    assert cfg is not None
    assert cfg.refs_local_tags == ("X", "G")
    assert cfg.refs_path == "ref_check.py"
    assert Config().refs_local_tags == ()


@pytest.mark.parametrize("value", ['"X"', '["x"]', '["X1"]', "[1]", '[""]'])
def test_load_rejects_bad_refs_local_tags(tmp_path: Path, value: str) -> None:
    """A `local_tags` value that is not a list of uppercase prefixes is a config error (D8.7).

    The shape is the one `ref_check.py` checks for `[registry] local_tags`,
    so a bad value fails here, before `apply` renders it into
    `ref_check.toml` and every checker run exits 2.

    arch: D8.7
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\nlocal_tags = {value}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="local_tags"):
        load(tmp_path)


def test_render_writes_refs_local_tags_and_round_trips(tmp_path: Path) -> None:
    """`render` writes the `[refs]` table for `local_tags` alone, and `load` reads it back (D8.7).

    arch: D8.7
    """
    cfg = Config(refs_local_tags=("X", "G"))
    text = render(cfg)
    assert "[refs]" in text
    assert 'local_tags = ["X", "G"]' in text
    assert "path =" not in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg
    assert "[refs]" not in render(Config())


def test_refs_local_tag_shape_equals_the_checkers() -> None:
    """`config._LOCAL_TAG` and `ref_check._LOCAL_TAG` are the same pattern (D8.7).

    `config.py` validates `[refs] local_tags` before `apply` renders it;
    the checker validates the rendered `[registry] local_tags`. The two
    must agree, and `config.py` does not import the checker, so this test
    holds them together.

    arch: D8.7
    """
    from trueup import config as config_mod
    from trueup import ref_check

    assert config_mod._LOCAL_TAG.pattern == ref_check._LOCAL_TAG.pattern
    assert config_mod._LOCAL_TAG.flags == ref_check._LOCAL_TAG.flags


def test_refs_law_archive_parses_merges_and_round_trips(tmp_path: Path) -> None:
    """`[refs] law_archive` loads, merges over a profile, and `render` writes it only when set.

    arch: D16.13
    """
    assert Config().refs_law_archive is None
    assert "refs.law_archive" in config_mod.KEYS
    assert "law_archive" not in render(Config())
    cfg = Config(refs_law_archive="../laws/archive")
    text = render(cfg)
    assert '[refs]\nlaw_archive = "../laws/archive"' in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg
    absolute = Config(refs_law_archive=str(tmp_path / "archive"))
    (tmp_path / "trueup.toml").write_text(render(absolute), encoding="utf-8")
    assert load(tmp_path) == absolute
    # The profile gives the key; the target file sets it again and wins.
    profiles = config_mod.config_home() / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "mine.toml").write_text(
        '[refs]\nlaw_archive = "../profile/archive"\n', encoding="utf-8"
    )
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nprofile = "mine"\n', encoding="utf-8"
    )
    assert load(tmp_path).refs_law_archive == "../profile/archive"
    target = load_target(tmp_path)
    assert target is not None
    assert target.refs_law_archive is None
    assert "law_archive" not in render(target)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nprofile = "mine"\n[refs]\nlaw_archive = "../laws/archive"\n',
        encoding="utf-8",
    )
    assert load(tmp_path).refs_law_archive == "../laws/archive"


@pytest.mark.parametrize("value", ['""', '"   "', "1", '["../laws/archive"]', "true"])
def test_refs_law_archive_rejects_a_bad_value(tmp_path: Path, value: str) -> None:
    """A `law_archive` that is not a non-empty string is a config error that names the key.

    arch: D16.13
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\nlaw_archive = {value}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match=r"refs\.law_archive"):
        load(tmp_path)


def test_a_bad_refs_law_archive_exits_2_and_names_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`trueup check` on a bad `law_archive` exits 2 with one line that names `refs.law_archive`.

    arch: D16.13
    """
    import subprocess

    from trueup import cli

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[refs]\nlaw_archive = ""\n', encoding="utf-8"
    )
    assert cli.main(["check", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "refs.law_archive" in err


def test_refs_declared_and_id_forms_parse_merge_and_round_trip(tmp_path: Path) -> None:
    """`[refs] declared` and `id_forms` load, render and read back; the default sets neither (D16.2).

    arch: D16.2
    """
    assert Config().refs_declared == ()
    assert Config().refs_id_forms == ()
    cfg = Config(
        refs_declared=("docs/ARCHITECTURE.md", "../.state/runs/*/03-design.md"),
        refs_id_forms=("D<n>.<m>", "D-<n>"),
    )
    text = render(cfg)
    assert (
        'declared = ["docs/ARCHITECTURE.md", "../.state/runs/*/03-design.md"]' in text
    )
    assert 'id_forms = ["D<n>.<m>", "D-<n>"]' in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg
    assert "declared =" not in render(Config())
    assert "id_forms =" not in render(Config())
    assert {"refs.declared", "refs.id_forms"} <= set(config_mod.KEYS)


@pytest.mark.parametrize(
    "body",
    [
        'declared = ["/abs/page.md"]',
        'declared = [""]',
        "declared = 1",
        "id_forms = 1",
        'id_forms = ["D-1"]',
        'id_forms = ["<n>"]',
        'id_forms = ["D <n>"]',
        'id_forms = ["D,<n>"]',
        'id_forms = ["D<n><m>"]',
        'id_forms = ["D<n>1"]',
        'id_forms = ["D<n>{}"]'.format("x" * 24),
        "id_forms = [{}]".format(", ".join(f'"D{i}<n>"' for i in range(17))),
    ],
)
def test_refs_declared_and_id_forms_reject_a_bad_value(
    tmp_path: Path, body: str
) -> None:
    """An absolute source and a form outside the shape are config errors (D16.2).

    arch: D16.2
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\n{body}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="refs"):
        load(tmp_path)


@pytest.mark.parametrize(
    "form",
    [
        "D<n>.<m>",
        "D<n>.<m>.<k>",
        "D-<n>",
        "I-<n>",
        "<n>.x",
        "1<n>",
        "D",
        "",
        "<n>",
        "D <n>",
        "D,<n>",
        "D<n><m>",
        "D<n>1",
        "D<N>",
        "D<n>" + "x" * 21,
        "D<n>" + "x" * 20,
    ],
)
def test_the_id_form_rule_equals_the_checkers(form: str) -> None:
    """`config._id_form_is_valid` and the checker's rule give the same answer (D16.2).

    `config.py` validates `[refs] id_forms` before `apply` renders it, and
    the checker validates the rendered `[targets.arch] forms`. The checker
    is one file with no import of the package, so this test holds the two
    copies together.

    arch: D16.2
    """
    from trueup import ref_check

    assert config_mod._id_form_is_valid(form) == ref_check._id_form_is_valid(form)
    assert config_mod._ID_FORM_HOLE.pattern == ref_check._ID_FORM_HOLE.pattern
    assert config_mod._ID_FORM_GLUED.pattern == ref_check._ID_FORM_GLUED.pattern
    assert config_mod._ID_FORM_BANNED.pattern == ref_check._ID_FORM_BANNED.pattern
    assert config_mod._ID_FORM_MAX_LENGTH == ref_check._ID_FORM_MAX_LENGTH
    assert config_mod._ID_FORMS_MAX == ref_check._ID_FORMS_MAX


def test_refs_mode_defaults_to_global_and_layout_to_on() -> None:
    """With no `[refs]` table, the checker mode is `global` and check h stays on (D9.1, D9.4).

    arch: D9.1, D9.4
    """
    cfg = Config()
    assert cfg.refs_mode == "global"
    assert cfg.refs_layout is True
    assert "[refs]" not in render(cfg)


def test_load_reads_refs_mode_path_and_layout(tmp_path: Path) -> None:
    """`[refs] mode = "copy"`, a `path` beside it, and `layout = false` read back (D9.1, D9.4).

    arch: D9.1, D9.4
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[refs]\nmode = "copy"\npath = "tools/checker.py"\nlayout = false\n',
        encoding="utf-8",
    )
    cfg = load(tmp_path)
    assert cfg is not None
    assert (cfg.refs_mode, cfg.refs_path, cfg.refs_layout) == (
        "copy",
        "tools/checker.py",
        False,
    )


@pytest.mark.parametrize(
    "table",
    [
        '[refs]\nmode = "shared"\n',
        "[refs]\nmode = 1\n",
        '[refs]\nlayout = "no"\n',
        '[refs]\npath = "ref_check.py"\n',
        '[refs]\nmode = "global"\npath = "tools/checker.py"\n',
    ],
)
def test_load_rejects_a_bad_refs_mode_or_layout_or_a_path_without_copy_mode(
    tmp_path: Path, table: str
) -> None:
    """A mode outside `global`/`copy`, a non-bool `layout`, or a `path` in global mode is a config error (D9.1, D9.4).

    arch: D9.1, D9.4
    """
    (tmp_path / "trueup.toml").write_text(f"version = 1\n\n{table}", encoding="utf-8")
    with pytest.raises(ConfigError, match="refs"):
        load(tmp_path)


def test_render_writes_refs_mode_and_layout_and_round_trips(tmp_path: Path) -> None:
    """`render` writes `mode = "copy"` and `layout = false` in the `[refs]` table, and `load` reads them back equal (D9.1, D9.4).

    `layout = false` also turns off the three `[layout]` switches when it
    loads (D14.2), so the expected configs carry them off.

    arch: D9.1, D9.4, D14.2
    """
    cfg = Config(refs_mode="copy", refs_path="tools/checker.py", refs_layout=False)
    text = render(cfg)
    values = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    assert 'mode = "copy"' in values
    assert 'path = "tools/checker.py"' in values
    assert "layout = false" in values
    assert values.index('mode = "copy"') < values.index('path = "tools/checker.py"')
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    switches_off = {
        "layout_front_matter": False,
        "layout_types": False,
        "layout_index": False,
    }
    assert load(tmp_path) == replace(cfg, **switches_off)
    only_layout = render(Config(refs_layout=False))
    assert "[refs]" in only_layout and "mode =" not in only_layout
    (tmp_path / "trueup.toml").write_text(only_layout, encoding="utf-8")
    assert load(tmp_path) == Config(refs_layout=False, **switches_off)


# -- D12.9: docs = "auto" and resolve_docs ---------------------------------


def test_docs_default_is_auto_in_config_and_in_a_file_without_the_key(
    tmp_path: Path,
) -> None:
    """`Config` and a `trueup.toml` with no `docs` key give `docs = "auto"`; render writes the three modes.

    `docs = "auto"` is the default, so `render` writes it only when the
    file set it (D14.3).

    arch: D12.9, D14.3
    """
    assert Config().docs == "auto"
    (tmp_path / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded is not None and loaded.docs == "auto"
    assert "docs =" not in render(Config())
    text = render(Config(explicit=frozenset({"docs"})))
    assert 'docs = "auto"' in text
    assert "# auto | full | readme" in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == Config()


@pytest.mark.parametrize(
    ("docs", "tier", "expected"),
    [
        ("auto", "T0", "readme"),
        ("auto", "T1", "readme"),
        ("auto", "T2", "full"),
        ("auto", "T3", "full"),
        ("full", "T0", "full"),
        ("readme", "T3", "readme"),
        (None, "T1", "readme"),
        (None, "T2", "full"),
    ],
)
def test_resolve_docs_maps_auto_by_tier_and_keeps_an_explicit_mode(
    docs: str | None, tier: str, expected: str
) -> None:
    """`resolve_docs` gives `readme` below T2 and `full` from T2 for `auto` or no config; an explicit mode wins.

    arch: D12.9
    """
    cfg = None if docs is None else Config(docs=docs)
    assert resolve_docs(cfg, tier) == expected


_ESLINT_OFF_TOML = """version = 1

[languages]
typescript = "clean"

[[eslint.off]]
rule = "security/detect-object-injection"
reason = "numeric code indexes objects by computed keys; the rule flags each lookup"

[[eslint.off]]
rule = "no-console"
reason = "the CLI tools print to the console"
"""


def test_load_reads_eslint_off_entries(tmp_path: Path) -> None:
    """`[[eslint.off]]` entries load as rule name to reason; no entry gives an empty map.

    arch: D13.5
    """
    assert Config().eslint_off == {}
    (tmp_path / "trueup.toml").write_text(_ESLINT_OFF_TOML, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded is not None
    assert loaded.eslint_off == {
        "security/detect-object-injection": "numeric code indexes objects by computed keys; the rule flags each lookup",
        "no-console": "the CLI tools print to the console",
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "[eslint]\nrules = []\n",
            "[eslint] rules: unknown key; allowed: 'off', 'suppressions'",
        ),
        ("[eslint]\noff = 1\n", "eslint.off must be an array of tables"),
        ('[[eslint.off]]\nrule = "no-console"\n', "needs exactly 'rule' and 'reason'"),
        (
            '[[eslint.off]]\nrule = "no-console"\nreason = "r"\nwhy = "x"\n',
            "needs exactly 'rule' and 'reason'",
        ),
        ('[[eslint.off]]\nrule = ""\nreason = "r"\n', "must be an eslint rule name"),
        ('[[eslint.off]]\nrule = 3\nreason = "r"\n', "must be an eslint rule name"),
        (
            '[[eslint.off]]\nrule = "no console"\nreason = "r"\n',
            "must be an eslint rule name",
        ),
        (
            '[[eslint.off]]\nrule = "a\\"b"\nreason = "r"\n',
            "must be an eslint rule name",
        ),
        ('[[eslint.off]]\nrule = "no-console"\nreason = ""\n', "needs a reason"),
        ('[[eslint.off]]\nrule = "no-console"\nreason = "  "\n', "needs a reason"),
        ('[[eslint.off]]\nrule = "no-console"\nreason = 1\n', "needs a reason"),
        (
            '[[eslint.off]]\nrule = "no-console"\nreason = "a\\nb"\n',
            "must be one line",
        ),
        (
            '[[eslint.off]]\nrule = "no-console"\nreason = "a\\u2028b"\n',
            "must be one line",
        ),
        (
            '[[eslint.off]]\nrule = "no-console"\nreason = "r"\n\n'
            '[[eslint.off]]\nrule = "no-console"\nreason = "s"\n',
            "repeats rule 'no-console'",
        ),
    ],
)
def test_load_rejects_a_bad_eslint_off_entry(
    tmp_path: Path, body: str, message: str
) -> None:
    """A bad `[eslint]` table or `[[eslint.off]]` entry is a `ConfigError` that names the problem.

    The reason goes into the eslint config as a `//` comment, so a line
    break in it (U+2028 included) would end the comment. The message
    starts with the full path of the file and names a bad key (D15.29).

    arch: D13.5, D15.29
    """
    (tmp_path / "trueup.toml").write_text(f"version = 1\n{body}", encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load(tmp_path)
    assert message in str(caught.value)
    assert str(caught.value).startswith(f"{tmp_path / 'trueup.toml'}: ")


def test_render_writes_eslint_off_sorted_and_round_trips(tmp_path: Path) -> None:
    """`render` writes one `[[eslint.off]]` block per rule, sorted, after `[languages]`; `load` reads it back equal.

    A `Config` with no entry renders no `[[eslint.off]]` line, so a target
    that never sets the key keeps the same bytes.

    arch: D13.5, D5.3
    """
    assert "eslint" not in render(Config(languages={"typescript": "clean"}))
    (tmp_path / "trueup.toml").write_text(_ESLINT_OFF_TOML, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded is not None
    text = render(loaded)
    lines = text.splitlines()
    rules = [line for line in lines if line.startswith("rule = ")]
    assert rules == ['rule = "no-console"', 'rule = "security/detect-object-injection"']
    assert lines.index(
        "[languages]                  # one key per language: strict | clean | off"
    ) < min(i for i, line in enumerate(lines) if line.startswith("[[eslint.off]]"))
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == loaded
    assert render(loaded) == text


# -- D14.2, D14.3: the configurable standard and the layer parse -----------

_D14_TARGET = """version = 1
profile = "mine"

[layout]
docs_dir = "doc"
front_matter = false
types = false
index = false

[prose]
banned = "words.txt"
extra = ["widget", "gizmo => gizmos?"]

[refs]
registry = false
comments = false
links = false

[root]
allow = []
base = ["src", "*.md"]

[health]
agents = false

[scratch]
gitignore = false

[eslint]
suppressions = "web/eslint-suppressions.json"

[python]
pydoclint_baseline = "tools/pydoclint.txt"
"""


def _empty_mine_profile() -> None:
    """Write an empty user profile `mine`, so a target can name it (D14.23 item 3).

    The file goes under the `XDG_CONFIG_HOME` that the autouse fixture set.
    """
    profiles = config_mod.config_home() / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "mine.toml").write_text("", encoding="utf-8")


def test_the_new_keys_default_to_the_house_values(tmp_path: Path) -> None:
    """`Config()` and a file with no D14.2 key give the `house` column of D14.2.

    arch: D14.2, D14.3
    """
    house = {
        "profile": None,
        "layout_docs_dir": "docs",
        "layout_front_matter": True,
        "layout_types": True,
        "layout_index": True,
        "prose_banned": "builtin",
        "prose_extra": (),
        "refs_registry": True,
        "refs_comments": True,
        "refs_links": True,
        "root_base": None,
        "health_agents": True,
        "scratch_gitignore": True,
        "eslint_suppressions": "lint/typescript/eslint-suppressions.json",
        "python_pydoclint_baseline": "lint/python/pydoclint-baseline.txt",
        "explicit": None,
    }
    (tmp_path / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded is not None
    for name, value in house.items():
        assert getattr(Config(), name) == value, name
        assert getattr(loaded, name) == value, name


def test_load_reads_every_d14_2_key(tmp_path: Path) -> None:
    """Each D14.2 key loads into its field; the banned path is absolute in the loaded config.

    arch: D14.2, D14.3
    """
    _empty_mine_profile()
    (tmp_path / "words.txt").write_text("widget\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(_D14_TARGET, encoding="utf-8")
    cfg = load(tmp_path)
    assert cfg is not None
    assert cfg.profile == "mine"
    assert cfg.layout_docs_dir == "doc"
    assert (cfg.layout_front_matter, cfg.layout_types, cfg.layout_index) == (
        False,
        False,
        False,
    )
    assert cfg.prose_banned == str((tmp_path / "words.txt").resolve())
    assert cfg.prose_extra == ("widget", "gizmo => gizmos?")
    assert (cfg.refs_registry, cfg.refs_comments, cfg.refs_links) == (
        False,
        False,
        False,
    )
    assert cfg.root_allow == ()
    assert cfg.root_base == ("src", "*.md")
    assert cfg.health_agents is False
    assert cfg.scratch_gitignore is False
    assert cfg.eslint_suppressions == "web/eslint-suppressions.json"
    assert cfg.python_pydoclint_baseline == "tools/pydoclint.txt"
    assert cfg.explicit is None


def test_an_empty_root_base_replaces_the_list_and_differs_from_absent(
    tmp_path: Path,
) -> None:
    """`[root] base = []` loads as an empty tuple; an absent key stays `None` (keep the code list).

    arch: D14.2, D14.3
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[root]\nbase = []\n", encoding="utf-8"
    )
    cfg = load(tmp_path)
    assert cfg is not None and cfg.root_base == ()
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[root]\nallow = []\n", encoding="utf-8"
    )
    cfg = load(tmp_path)
    assert cfg is not None and cfg.root_base is None


@pytest.mark.parametrize("value", ["builtin", "off"])
def test_prose_banned_builtin_and_off_stay_words(tmp_path: Path, value: str) -> None:
    """`builtin` and `off` are not paths: they load unchanged, with no file read.

    arch: D14.2, D14.3
    """
    (tmp_path / "trueup.toml").write_text(
        f'version = 1\n[prose]\nbanned = "{value}"\nextra = ["widget"]\n',
        encoding="utf-8",
    )
    cfg = load(tmp_path)
    assert cfg is not None
    assert cfg.prose_banned == value
    assert cfg.prose_extra == ("widget",)


def test_parse_keeps_a_target_banned_path_as_written_and_makes_a_profile_one_absolute(
    tmp_path: Path,
) -> None:
    """A relative banned path is relative to the file that set it: the target layer keeps the text, a profile holds the absolute path.

    arch: D14.2, D14.3
    """
    (tmp_path / "words.txt").write_text("widget\n", encoding="utf-8")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "words.txt").write_text("gizmo\n", encoding="utf-8")
    raw = {"prose": {"banned": "words.txt"}}
    target = config_mod._parse(raw, source=tmp_path / "trueup.toml", layer="target")
    assert target.prose_banned == "words.txt"
    profile = config_mod._parse(raw, source=profiles / "mine.toml", layer="profile")
    assert profile.prose_banned == str((profiles / "words.txt").resolve())


def test_load_rejects_a_banned_path_that_names_no_file(tmp_path: Path) -> None:
    """A `[prose] banned` path with no file behind it is a `ConfigError` at load.

    arch: D14.2, D14.3
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[prose]\nbanned = "missing.txt"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="prose.banned names 'missing.txt'"):
        load(tmp_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('profile = "House"\n', "profile name must be lower-case"),
        ('profile = "-x"\n', "profile name must be lower-case"),
        ('profile = "a_b"\n', "profile name must be lower-case"),
        ("profile = 3\n", "profile name must be lower-case"),
        ('[layout]\ndocs_dir = "a/b"\n', "layout.docs_dir"),
        ('[layout]\ndocs_dir = ".."\n', "layout.docs_dir"),
        ('[layout]\ndocs_dir = ""\n', "layout.docs_dir"),
        ("[layout]\ndocs_dir = 3\n", "layout.docs_dir"),
        ('[layout]\nfront_matter = "no"\n', "layout.front_matter"),
        ("[layout]\ntypes = 1\n", "layout.types"),
        ('[layout]\nindex = "x"\n', "layout.index"),
        ("[layout]\nother = 1\n", "[layout] other: unknown key; allowed: "),
        ("[prose]\nbanned = 3\n", "prose.banned"),
        ("[prose]\nother = 1\n", "[prose] other: unknown key; allowed: "),
        ('[prose]\nextra = "widget"\n', "prose.extra"),
        ('[prose]\nextra = [""]\n', "must be one line"),
        ('[prose]\nextra = ["a\\nb"]\n', "must be one line"),
        ('[prose]\nextra = ["gizmo => ("]\n', "bad regex"),
        ('[prose]\nextra = [" => x"]\n', "needs a word and a regex"),
        ('[refs]\nregistry = "no"\n', "refs.registry"),
        ("[refs]\ncomments = 0\n", "refs.comments"),
        ('[refs]\nlinks = "yes"\n', "refs.links"),
        ('[root]\nbase = "src"\n', "root.base"),
        ("[root]\nother = []\n", "[root] other: unknown key; allowed: "),
        ("[health]\nagents = 1\n", "health.agents"),
        ("[health]\nother = true\n", "[health] other: unknown key; allowed: "),
        ('[scratch]\ngitignore = "yes"\n', "scratch.gitignore"),
        ('[eslint]\nsuppressions = "/abs.json"\n', "eslint.suppressions"),
        ('[eslint]\nsuppressions = "a/../b.json"\n', "eslint.suppressions"),
        ('[eslint]\nsuppressions = "a\\\\b.json"\n', "eslint.suppressions"),
        ('[eslint]\nsuppressions = ""\n', "eslint.suppressions"),
        ("[eslint]\nsuppressions = 3\n", "eslint.suppressions"),
        ('[python]\npydoclint_baseline = "../x.txt"\n', "python.pydoclint_baseline"),
        ("[python]\nother = 1\n", "[python] other: unknown key; allowed: "),
    ],
)
def test_load_rejects_a_bad_d14_2_value(
    tmp_path: Path, body: str, message: str
) -> None:
    """A bad value or an unknown key in a D14.2 table is a `ConfigError` that names the key.

    The message starts with the full path of the file (D15.29).

    arch: D14.2, D14.3, D15.29
    """
    (tmp_path / "trueup.toml").write_text(f"version = 1\n{body}", encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load(tmp_path)
    assert message in str(caught.value)
    assert str(caught.value).startswith(f"{tmp_path / 'trueup.toml'}: ")


@pytest.mark.parametrize("value", [True, False])
def test_refs_layout_sets_the_three_layout_switches(
    tmp_path: Path, value: bool
) -> None:
    """`[refs] layout` stays loadable and sets `front_matter`, `types` and `index` to its value.

    arch: D14.2, D14.3
    """
    text = "true" if value else "false"
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\nlayout = {text}\n", encoding="utf-8"
    )
    cfg = load(tmp_path)
    assert cfg is not None
    assert cfg.refs_layout is value
    assert (cfg.layout_front_matter, cfg.layout_types, cfg.layout_index) == (
        value,
        value,
        value,
    )


@pytest.mark.parametrize("switch", ["front_matter", "types", "index"])
def test_refs_layout_beside_a_layout_switch_is_an_error(
    tmp_path: Path, switch: str
) -> None:
    """A file that sets `[refs] layout` and one of the three `[layout]` switches is a `ConfigError`.

    arch: D14.2, D14.3
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[layout]\n{switch} = true\n[refs]\nlayout = false\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError, match=f"refs.layout cannot stand beside layout.{switch}"
    ):
        load(tmp_path)


_EXPLICIT_TARGET = """version = 1
run_date = ""
tier = "auto"

[root]
allow = []

[refs]
layout = false

[languages]
python = "clean"

[[eslint.off]]
rule = "no-console"
reason = "the CLI prints"

[[keep]]
id = "prose:x.md"
reason = "quoted text"
"""


def test_parse_records_the_explicit_keys_of_the_target_layer_only(
    tmp_path: Path,
) -> None:
    """The target layer lists each key the file set, as a dotted name; other layers and `load` give `None`.

    A key set at its default value still counts: `tier = "auto"` is in
    the set, an absent `docs` is not.

    arch: D14.2, D14.3
    """
    raw = tomllib.loads(_EXPLICIT_TARGET)
    target = config_mod._parse(raw, source=tmp_path / "trueup.toml", layer="target")
    assert target.explicit == frozenset(
        {
            "version",
            "run_date",
            "tier",
            "root",
            "root.allow",
            "refs",
            "refs.layout",
            "languages",
            "languages.python",
            "eslint",
            "eslint.off",
            "keep",
        }
    )
    profile_raw = {"tier": "T2", "languages": {"python": "strict"}}
    for layer in ("profile", "user"):
        cfg = config_mod._parse(profile_raw, source=tmp_path / "p.toml", layer=layer)
        assert cfg.explicit is None
        assert cfg.tier == "T2"
    (tmp_path / "trueup.toml").write_text(_EXPLICIT_TARGET, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded is not None and loaded.explicit is None
    assert replace(target, explicit=None) == loaded


@pytest.mark.parametrize("layer", ["profile", "user"])
@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ({"version": 1}, "version"),
        ({"run_date": "2026-10-16"}, "run_date"),
        ({"keep": [{"id": "prose:x.md", "reason": "r"}]}, "keep"),
    ],
)
def test_a_profile_or_user_file_cannot_set_a_target_only_key(
    tmp_path: Path, layer: str, raw: dict[str, object], key: str
) -> None:
    """`version`, `run_date` and `[[keep]]` belong to the target file; the error names the file.

    arch: D14.2, D14.3
    """
    source = tmp_path / "profiles" / "mine.toml"
    with pytest.raises(ConfigError) as caught:
        config_mod._parse(raw, source=source, layer=layer)
    assert str(caught.value).startswith(f"{source}: ")
    assert key in str(caught.value)


def test_only_a_profile_file_cannot_name_a_profile(tmp_path: Path) -> None:
    """A profile file that sets `profile` is an error (no chaining); the user default file and the target may set it.

    arch: D14.2, D14.3
    """
    raw = {"profile": "minimal"}
    source = tmp_path / "profiles" / "mine.toml"
    with pytest.raises(
        ConfigError, match="a profile file cannot set profile"
    ) as caught:
        config_mod._parse(raw, source=source, layer="profile")
    assert str(caught.value).startswith(f"{source}: ")
    user = config_mod._parse(raw, source=tmp_path / "trueup.toml", layer="user")
    assert user.profile == "minimal"
    target = config_mod._parse(raw, source=tmp_path / "trueup.toml", layer="target")
    assert target.profile == "minimal"


def test_an_error_in_a_profile_file_names_the_file(tmp_path: Path) -> None:
    """A bad value in a profile file gives a message that starts with the file path, not `trueup.toml`.

    arch: D14.2, D14.3
    """
    source = tmp_path / "profiles" / "mine.toml"
    with pytest.raises(ConfigError) as caught:
        config_mod._parse({"tier": "T9"}, source=source, layer="profile")
    assert str(caught.value).startswith(f"{source}: tier must be one of")


def test_parse_rejects_an_unknown_layer() -> None:
    """`_parse` takes only the three layers of D14.3.

    arch: D14.2, D14.3
    """
    with pytest.raises(ValueError, match="unknown config layer"):
        config_mod._parse({}, source=None, layer="global")


# -- D14.3, D14.19: render writes the explicit or non-default keys ----------

_HEADER = (
    "# trueup configuration. The trueup skill writes this file. A person can edit it.\n"
    "# comments do not survive a config write; trueup writes this file\n"
)
"""The two header lines of a rendered file; decision 13 added the second (D15.27)."""

_ALL_WRITTEN = (
    _HEADER
    + """version = 1
run_date = "2026-10-16"
tier = "auto"                # auto | T0 | T1 | T2 | T3
public = false                # true adds C1, C2 and the public health files
docs = "auto"                # auto | full | readme
stale_days = 180                # P8
ignore = []   # globs left out of the survey and all findings
protect = []                 # globs that apply never changes or removes

[root]
allow = []                   # root entries allowed beyond the base list (D5.8)

[scratch]
allow = []                   # paths or names the scratch rule lets through (D5.8)

[languages]                  # one key per language: strict | clean | off

[[keep]]                     # a finding the person declined, with the reason
id = "health-license:"
reason = "private repository"
"""
)
"""A file in the form that `render` wrote before D14.3: every key at its default value, written."""


def test_render_of_the_default_config_is_the_header_and_version() -> None:
    """`render(Config())` writes the two header comment lines and `version = 1`, and no other key.

    arch: D14.3, D14.19, D15.27
    """
    assert render(Config()) == _HEADER + "version = 1\n"


def test_load_target_keeps_the_explicit_keys_and_load_drops_them(
    tmp_path: Path,
) -> None:
    """`load_target` gives the target layer with `explicit`; `load` gives the same values with `explicit` at `None`.

    arch: D14.3, D14.19
    """
    assert config_mod.load_target(tmp_path) is None
    (tmp_path / "trueup.toml").write_text(_ALL_WRITTEN, encoding="utf-8")
    target = config_mod.load_target(tmp_path)
    assert target is not None
    assert target.explicit is not None
    assert {"tier", "public", "root.allow", "languages", "keep"} <= target.explicit
    assert load(tmp_path) == replace(target, explicit=None)


def test_a_file_whose_keys_are_explicit_renders_to_the_same_bytes(
    tmp_path: Path,
) -> None:
    """A file that holds each key at its default value renders back byte for byte: the keys the file set stay.

    arch: D14.3, D14.19, D15.27
    """
    (tmp_path / "trueup.toml").write_text(_ALL_WRITTEN, encoding="utf-8")
    target = config_mod.load_target(tmp_path)
    assert target is not None
    assert render(target) == _ALL_WRITTEN
    effective = load(tmp_path)
    assert effective is not None
    assert render(effective) == (
        _HEADER
        + 'version = 1\nrun_date = "2026-10-16"\n\n'
        + "[[keep]]                     # a finding the person declined, with the reason\n"
        + 'id = "health-license:"\nreason = "private repository"\n'
    )


def test_render_writes_a_value_that_differs_from_the_default_with_no_explicit_set() -> (
    None
):
    """A non-default value is written although `explicit` is `None`; a default value is not.

    arch: D14.3, D14.19
    """
    cfg = Config(tier="T2", scratch_gitignore=False, layout_docs_dir="doc")
    values = [
        line.split("#", 1)[0].strip()
        for line in render(cfg).splitlines()
        if line.split("#", 1)[0].strip()
    ]
    assert values == [
        "version = 1",
        'tier = "T2"',
        "[scratch]",
        "gitignore = false",
        "[layout]",
        'docs_dir = "doc"',
    ]


def test_a_profile_line_stays_one_line(tmp_path: Path) -> None:
    """A hand-written file `profile = "minimal"` renders to that key and `version` only.

    arch: D14.3, D14.19
    """
    (tmp_path / "trueup.toml").write_text('profile = "minimal"\n', encoding="utf-8")
    target = config_mod.load_target(tmp_path)
    assert target is not None
    values = [
        line.split("#", 1)[0].strip()
        for line in render(target).splitlines()
        if line.split("#", 1)[0].strip()
    ]
    assert values == ["version = 1", 'profile = "minimal"']


def test_the_d14_2_keys_round_trip_through_the_target_layer(tmp_path: Path) -> None:
    """Every D14.2 key renders, and the rendered text loads back to the same target layer.

    The banned-word path stays as the file wrote it: `render` writes the
    target layer, not the absolute path of the effective config (I-33).

    arch: D14.3, D14.19
    """
    _empty_mine_profile()
    (tmp_path / "words.txt").write_text("widget\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(_D14_TARGET, encoding="utf-8")
    target = config_mod.load_target(tmp_path)
    assert target is not None
    text = render(target)
    assert 'banned = "words.txt"' in text
    assert str(tmp_path) not in text
    for key in (
        'profile = "mine"',
        'base = ["src", "*.md"]',
        "allow = []",
        "gitignore = false",
        'docs_dir = "doc"',
        "front_matter = false",
        "types = false",
        "index = false",
        'extra = ["widget", "gizmo => gizmos?"]',
        "registry = false",
        "comments = false",
        "links = false",
        "agents = false",
        'suppressions = "web/eslint-suppressions.json"',
        'pydoclint_baseline = "tools/pydoclint.txt"',
    ):
        assert key in text, key
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert config_mod.load_target(tmp_path) == target
    assert render(config_mod.load_target(tmp_path)) == text


def test_refs_layout_false_renders_alone_without_the_three_switches(
    tmp_path: Path,
) -> None:
    """`[refs] layout = false` renders as written; the three `[layout]` switches it sets are not written.

    A file that held both would be a `ConfigError` (D14.2).

    arch: D14.3, D14.19
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n\n[refs]\nlayout = false\n", encoding="utf-8"
    )
    target = config_mod.load_target(tmp_path)
    assert target is not None and not target.layout_types
    text = render(target)
    assert "layout = false" in text
    assert "[layout]" not in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert config_mod.load_target(tmp_path) == target


def test_eslint_suppressions_and_eslint_off_render_together(tmp_path: Path) -> None:
    """The `[eslint]` table and the `[[eslint.off]]` entries render after `[languages]` and load back.

    A file with `[[eslint.off]]` alone gets no empty `[eslint]` header.

    arch: D14.3, D14.19
    """
    cfg = Config(
        languages={"typescript": "clean"},
        eslint_suppressions="web/s.json",
        eslint_off={"no-console": "the CLI prints"},
    )
    text = render(cfg)
    lines = text.splitlines()
    assert lines.index(
        "[languages]                  # one key per language: strict | clean | off"
    ) < (lines.index("[eslint]"))
    assert lines.index("[eslint]") < min(
        i for i, line in enumerate(lines) if line.startswith("[[eslint.off]]")
    )
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg
    assert "[eslint]" not in render(
        replace(cfg, eslint_suppressions=Config().eslint_suppressions)
    )


def test_profile_path_finds_a_builtin_and_a_user_profile(tmp_path: Path) -> None:
    """`profile_path` gives the built-in file for a built-in name and the user file for another name.

    arch: D14.1, D14.3
    """
    builtin = config_mod.profile_path("minimal")
    assert builtin.name == "minimal.toml" and builtin.is_file()
    profiles = config_mod.config_home() / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "mine.toml").write_text("stale_days = 30\n", encoding="utf-8")
    assert config_mod.profile_path("mine") == profiles / "mine.toml"


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("nope", "profile 'nope' is not found"),
        ("No_Pe", "profile name must be lower-case"),
        ("../house", "profile name must be lower-case"),
    ],
)
def test_profile_path_refuses_a_name_that_resolves_to_no_file(
    name: str, message: str
) -> None:
    """An unknown name is a `ConfigError` that names both search paths; a bad name fails before a path is made.

    arch: D14.1, D14.3
    """
    with pytest.raises(ConfigError, match=message) as error:
        config_mod.profile_path(name)
    if name == "nope":
        text = str(error.value)
        assert str(config_mod._PROFILE_DIR) in text
        assert str(config_mod.config_home() / "profiles" / "nope.toml") in text


def test_cache_reads_the_files_again_when_the_banned_file_changes(
    tmp_path: Path,
) -> None:
    """The cache key probes the resolved `[prose] banned` file: a changed file reloads, a removed file is a `ConfigError`.

    arch: D14.1, D14.3
    """
    words = tmp_path / "words.txt"
    words.write_text("widget\n", encoding="utf-8")
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[prose]\nbanned = "words.txt"\n', encoding="utf-8"
    )
    first = config_mod.load_layers(tmp_path)
    assert first is not None
    assert config_mod.load_layers(tmp_path) is first
    words.write_text("widget\ngizmo\n", encoding="utf-8")
    second = config_mod.load_layers(tmp_path)
    assert second is not first and second == first
    words.unlink()
    with pytest.raises(ConfigError, match="prose.banned names 'words.txt'"):
        config_mod.load_layers(tmp_path)


def test_read_toml_names_the_file_when_it_is_not_utf8(tmp_path: Path) -> None:
    """A `trueup.toml` with a non-UTF-8 byte raises a `ConfigError` that names the file.

    arch: D15.1
    """
    path = tmp_path / "trueup.toml"
    path.write_bytes(b"version = 1\n# caf\xe9\n")
    with pytest.raises(ConfigError, match="trueup.toml: cannot read"):
        config_mod._read_toml(path, "trueup.toml")


def test_read_toml_names_the_file_when_it_cannot_be_opened(tmp_path: Path) -> None:
    """A path that is a directory raises a `ConfigError` that says it cannot be read.

    arch: D15.1
    """
    directory = tmp_path / "trueup.toml"
    directory.mkdir()
    with pytest.raises(ConfigError, match="cannot read"):
        config_mod._read_toml(directory, "trueup.toml")


def test_health_files_reads_tier_or_readme_and_rejects_the_rest(tmp_path: Path) -> None:
    """`[health] files` takes `tier` or `readme`; the minimal profile sets `readme`.

    arch: D15.14, D15.15
    """
    assert Config().health_files == "tier"
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[health]\nfiles = "readme"\n', encoding="utf-8"
    )
    assert load(tmp_path).health_files == "readme"
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[health]\nfiles = "all"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="health.files"):
        load(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nprofile = "minimal"\n', encoding="utf-8"
    )
    assert load(tmp_path).health_files == "readme"
    assert public_is_false(load(tmp_path), tmp_path) is False
    (tmp_path / "trueup.toml").write_text(
        "version = 1\npublic = false\n", encoding="utf-8"
    )
    assert public_is_false(load(tmp_path), tmp_path) is True


# -- D15.29: run_date and error messages -------------------------------------


@pytest.mark.parametrize("value", ["yesterday-ish", "2026-13-01", "2026/01/02"])
def test_run_date_must_be_an_iso_date(tmp_path: Path, value: str) -> None:
    """A `run_date` that is not empty and not an ISO date is a `ConfigError` that names the key.

    arch: D15.29
    """
    (tmp_path / "trueup.toml").write_text(
        f'version = 1\nrun_date = "{value}"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="run_date"):
        load(tmp_path)
    (tmp_path / "trueup.toml").write_text(
        'version = 1\nrun_date = "2026-11-03"\n', encoding="utf-8"
    )
    assert load(tmp_path).run_date == "2026-11-03"


def test_unknown_table_key_is_named_and_the_message_starts_with_the_path(
    tmp_path: Path,
) -> None:
    """`[refs] bogus` names the bad key and the allowed keys, after the full path of the file.

    arch: D15.29
    """
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n\n[refs]\nbogus = 1\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as caught:
        load(tmp_path)
    message = str(caught.value)
    assert message.startswith(
        f"{tmp_path / 'trueup.toml'}: [refs] bogus: unknown key; allowed: "
    )
    assert "'mode'" in message


def test_root_base_code_round_trips_through_render(tmp_path: Path) -> None:
    """A target `[root] base = "code"` stays in the file after a render.

    arch: D15.29
    """
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n\n[root]\nbase = "code"\n', encoding="utf-8"
    )
    target = load_target(tmp_path)
    assert target is not None and target.root_base is None
    assert 'base = "code"' in render(target)


def test_guard_defaults_and_round_trip(tmp_path: Path) -> None:
    """`[guard]` defaults to registry off and no private packages, and renders back to the same layer.

    arch: D15.32
    """
    assert Config().guard_registry is False
    assert Config().guard_private_packages == ()
    assert "[guard]" not in render(Config(guard_registry=False))
    (tmp_path / "trueup.toml").write_text(
        'version = 1\n[guard]\nregistry = true\nprivate_packages = ["corp-*", "@corp/*"]\n',
        encoding="utf-8",
    )
    cfg = load(tmp_path)
    assert cfg.guard_registry is True
    assert cfg.guard_private_packages == ("corp-*", "@corp/*")
    target = load_target(tmp_path)
    assert target is not None
    text = render(target)
    assert "[guard]" in text
    assert "registry = true" in text
    assert 'private_packages = ["corp-*", "@corp/*"]' in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load_target(tmp_path) == target


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[guard]\nregistry = "yes"\n', "guard.registry"),
        ("[guard]\nprivate_packages = 3\n", "guard.private_packages"),
        ("[guard]\nother = true\n", "[guard] other: unknown key; allowed: "),
    ],
)
def test_load_rejects_a_bad_guard_value(
    tmp_path: Path, body: str, message: str
) -> None:
    """A bad `[guard]` value or key is a `ConfigError` that names the key.

    arch: D15.32
    """
    (tmp_path / "trueup.toml").write_text(f"version = 1\n{body}", encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load(tmp_path)
    assert message in str(caught.value)


def test_a_higher_layer_replaces_the_guard_keys(tmp_path: Path) -> None:
    """A target file that sets `[guard] registry` wins over the profile; one that does not keeps it.

    arch: D15.32
    """
    (tmp_path / "trueup.toml").write_text("version = 1\n", encoding="utf-8")
    assert load(tmp_path).guard_registry is False
    (tmp_path / "trueup.toml").write_text(
        "version = 1\n[guard]\nregistry = true\n", encoding="utf-8"
    )
    assert load(tmp_path).guard_registry is True


def test_keys_lists_every_dotted_key() -> None:
    """`config.KEYS` is the sorted merge keys plus `profile`, `languages` and `guard.*`.

    arch: D15.32, D15.36
    """
    keys = config_mod.KEYS
    assert isinstance(keys, tuple)
    assert list(keys) == sorted(set(keys))
    assert set(config_mod._MERGE_FIELDS) <= set(keys)
    assert {
        "profile",
        "languages",
        "eslint.off",
        "guard.registry",
        "guard.private_packages",
    } <= set(keys)
    assert "scan.ignore" not in keys


def test_refs_flags_are_the_flags_the_checker_parses() -> None:
    """`ref_check.REFS_FLAGS` names each flag that `main` accepts and `USAGE` documents.

    arch: D15.36
    """
    from trueup import ref_check

    assert set(ref_check.REFS_FLAGS) == {
        "--root",
        "--edges",
        "--config",
        "--help",
        "-h",
    }
    for flag in ref_check.REFS_FLAGS:
        assert flag in ref_check.USAGE


def test_refs_accepted_reader_changes_parse_merge_and_round_trip(
    tmp_path: Path,
) -> None:
    """`[refs] accepted_reader_changes` loads, renders and reads back; the default is empty (D16.3).

    arch: D16.3
    """
    assert Config().refs_accepted_reader_changes == ()
    cfg = Config(refs_accepted_reader_changes=("rust-doc-position", "other"))
    text = render(cfg)
    assert 'accepted_reader_changes = ["rust-doc-position", "other"]' in text
    (tmp_path / "trueup.toml").write_text(text, encoding="utf-8")
    assert load(tmp_path) == cfg
    assert "accepted_reader_changes" not in render(Config())
    assert "refs.accepted_reader_changes" in config_mod.KEYS


@pytest.mark.parametrize(
    "body",
    [
        "accepted_reader_changes = 1",
        'accepted_reader_changes = [""]',
        'accepted_reader_changes = ["a b"]',
        'accepted_reader_changes = ["a,b"]',
    ],
)
def test_refs_accepted_reader_changes_reject_a_bad_value(
    tmp_path: Path, body: str
) -> None:
    """A name with white space or a comma, or an empty name, is a config error (D16.3).

    arch: D16.3
    """
    (tmp_path / "trueup.toml").write_text(
        f"version = 1\n[refs]\n{body}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="refs"):
        load(tmp_path)


def test_a_change_name_has_the_same_shape_in_both_modules() -> None:
    """`config._CHANGE_BANNED` and `ref_check._CHANGE_NAME` accept the same names (D16.3).

    `config.py` does not import the checker, so this test holds the two
    copies together.

    arch: D16.3
    """
    from trueup import ref_check

    for name in ("a", "rust-doc-position", "a.b_c", "", "a b", "a,b", "a\tb"):
        in_config = bool(name) and config_mod._CHANGE_BANNED.search(name) is None
        assert in_config == bool(ref_check._CHANGE_NAME.fullmatch(name))
