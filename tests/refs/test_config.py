"""Unit tests for the design id about the configuration file."""

from pathlib import Path

import pytest

from trueup.ref_check import CONFIG_SCHEMA, Config, ConfigError, load_config, main, run

BAD = Path(__file__).resolve().parent / "fixtures" / "config_bad"
"""The directory of the configuration files that are not valid (I-3)."""


def _install(case: str, root: Path) -> Path:
    """Copy the configuration of one fixture case to the root.

    Each fixture file ends in `.txt`, and the copy drops that suffix (D1.6,
    I-3). This helper copies the one file, because `materialise` copies a
    whole tree and this fixture is a single file.

    Args:
        case: The directory name under `tests/fixtures/config_bad/`.
        root: The directory that gets the copy.

    Returns:
        The path of the copy.
    """
    source = BAD / case / "ref_check.toml.txt"
    target = root / source.name.removesuffix(".txt")
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_configuration_file_valid_absent_and_unknown_key(tmp_path):
    """A valid file, an absent file, and an unknown key, each give the right result (D2.5).

    arch: D2.5
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")

    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\ncomments = false\nlinks = false\n",
        encoding="utf-8",
    )
    report = run(tmp_path)
    assert report.failures == [] or all(
        failure.kind != "malformed" for failure in report.failures
    )

    absent_root = tmp_path / "absent"
    (absent_root / "docs").mkdir(parents=True)
    (absent_root / "docs" / "ARCHITECTURE.md").write_text(
        "## Verification\n\n", encoding="utf-8"
    )
    run(absent_root)

    bad_root = tmp_path / "bad"
    (bad_root / "docs").mkdir(parents=True)
    (bad_root / "docs" / "ARCHITECTURE.md").write_text(
        "## Verification\n\n", encoding="utf-8"
    )
    (bad_root / "ref_check.toml").write_text(
        "[checks]\nwobble = true\n", encoding="utf-8"
    )
    assert main(["--root", str(bad_root)]) == 2


def test_the_schema_reads_the_switches_and_the_law_archive(tmp_path):
    """The loader reads the full schema of D2.5 and makes the archive absolute.

    arch: D2.5, I-2
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\n"
        "registry = true\n"
        "comments = true\n"
        "links = true\n"
        "\n"
        "[targets.law]\n"
        'archive = "../laws/archive"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert (config.registry, config.comments, config.links) == (True, True, True)
    assert config.archive == (tmp_path / ".." / "laws" / "archive").resolve()
    assert config.archive.is_absolute()


def test_the_schema_reads_the_scan_ignore_globs(tmp_path):
    """`[scan] ignore` is read as a tuple of globs; an absent key gives none (D2.5, I-2).

    arch: D2.5, I-2
    """
    (tmp_path / "ref_check.toml").write_text(
        '[scan]\nignore = ["docs/features/**", "gen/*.py"]\n', encoding="utf-8"
    )
    assert load_config(tmp_path).ignore == ("docs/features/**", "gen/*.py")
    assert Config().ignore == ()


def test_an_absent_file_and_an_absent_switch_are_both_off(tmp_path):
    """No file gives the empty configuration, and an absent switch is false (D2.5).

    arch: D2.5, I-2
    """
    assert not (tmp_path / "ref_check.toml").exists()
    assert load_config(tmp_path) == Config()
    assert load_config(tmp_path).archive is None

    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "ref_check.toml").write_text(
        "[checks]\nregistry = true\n", encoding="utf-8"
    )
    config = load_config(partial)
    assert config.registry is True
    assert (config.comments, config.links, config.archive) == (False, False, None)


@pytest.mark.parametrize(
    "case",
    [
        "unknown_key",
        "unknown_table",
        "exclude_key",
        "skip_paths",
        "law_skip_key",
        "scan_other_key",
        "scan_ignore_not_a_list",
        "switch_not_boolean",
        "not_toml",
    ],
)
def test_a_file_outside_the_schema_gives_exit_two(case, tmp_path):
    """Each file of the bad fixture stops the run with exit 2 (D2.5, I-2, I-4).

    Four of them try to skip a path with a key other than `[scan] ignore`.
    The schema has no such key, so each one is an unknown key, and none can
    turn a check off without a report. An `ignore` value that is not a list
    of globs also stops the run.

    arch: D2.5, I-2
    """
    root = tmp_path / case
    root.mkdir()
    assert _install(case, root).name == "ref_check.toml"
    with pytest.raises(ConfigError):
        load_config(root)
    assert main(["--root", str(root)]) == 2


def test_the_checker_reports_a_valid_file_and_not_the_configuration(tmp_path):
    """A valid file gives exit 0 or 1, and never the exit code of a bad file (D2.5).

    arch: D2.5, I-2
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 0
    assert main(["--wobble"]) == 2
    assert run(tmp_path).failures == []


def test_the_registry_table_reads_the_local_tags(tmp_path):
    """The loader reads `[registry] local_tags`, and an absent key gives no tag (D2.5).

    arch: D2.5
    """
    (tmp_path / "ref_check.toml").write_text(
        '[checks]\nregistry = true\n\n[registry]\nlocal_tags = ["D", "O"]\n',
        encoding="utf-8",
    )
    assert load_config(tmp_path).local_tags == frozenset({"D", "O"})
    assert Config().local_tags == frozenset()


@pytest.mark.parametrize(
    "value",
    ['"D"', '["d"]', '["D1"]', "[1]", '[""]'],
)
def test_local_tags_that_are_not_uppercase_prefixes_give_exit_two(tmp_path, value):
    """A `local_tags` value that is not a list of uppercase prefixes stops the run (D2.5, I-4).

    arch: D2.5, I-4
    """
    (tmp_path / "ref_check.toml").write_text(
        f"[registry]\nlocal_tags = {value}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_config(tmp_path)
    assert main(["--root", str(tmp_path)]) == 2


def test_the_keep_table_reads_the_failure_ids(tmp_path):
    """`[keep] failures` is a list of failure ids; an absent table keeps nothing (D2.5, D9.2).

    arch: D2.5, D9.2
    """
    (tmp_path / "ref_check.toml").write_text(
        '[keep]\nfailures = ["docs/a.md:1:no-front-matter", "README.md:1:no-section:Install"]\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.keep == frozenset(
        {"docs/a.md:1:no-front-matter", "README.md:1:no-section:Install"}
    )
    assert Config().keep == frozenset()


def test_a_keep_prefix_keeps_every_failure_of_a_page_and_no_other_page(tmp_path):
    """A `[keep] failures` entry keeps its own id and each id below it at a `:` boundary (D15.8).

    `docs/a.md` keeps the failures of `docs/a.md`, not of `docs/abc.md`.

    arch: D15.3, D15.8
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "docs" / "abc.md").write_text("# ABC\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        '[checks]\nlayout = true\n\n[keep]\nfailures = ["docs/a.md"]\n',
        encoding="utf-8",
    )
    report = run(tmp_path)
    assert [item.path for item in report.kept] == ["docs/a.md"]
    assert [item.path for item in report.failures] == ["docs/abc.md"]


@pytest.mark.parametrize(
    "text",
    [
        '[keep]\nfailures = "docs/a.md:1:no-front-matter"\n',
        "[keep]\nfailures = [1]\n",
        "[keep]\nids = []\n",
        "keep = 1\n",
    ],
)
def test_a_keep_table_outside_the_schema_gives_exit_two(tmp_path, text):
    """A `[keep]` value that is not a list of strings, or a key beside `failures`, gives exit 2 (D2.5, D9.2, I-4).

    arch: D2.5, D9.2, I-4
    """
    (tmp_path / "ref_check.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)
    assert main(["--root", str(tmp_path)]) == 2


def test_the_layout_table_reads_the_docs_dir_and_the_three_rule_switches(tmp_path):
    """`[layout]` gives `docs_dir` and three rule switches; an absent table gives `docs` and all on (D14.5).

    arch: D14.5
    """
    assert CONFIG_SCHEMA["layout"] == ("docs_dir", "front_matter", "types", "index")
    assert "layout" in CONFIG_SCHEMA[""]
    default = Config()
    assert (default.docs_dir, default.front_matter, default.types, default.index) == (
        "docs",
        True,
        True,
        True,
    )
    assert load_config(tmp_path) == default
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlayout = true\n", encoding="utf-8"
    )
    assert load_config(tmp_path) == Config(layout=True)
    (tmp_path / "ref_check.toml").write_text(
        '[layout]\ndocs_dir = "handbook"\nfront_matter = false\n'
        "types = false\nindex = false\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert (config.docs_dir, config.front_matter, config.types, config.index) == (
        "handbook",
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    "text",
    [
        '[layout]\ndocs_dir = "docs/sub"\n',
        '[layout]\ndocs_dir = ""\n',
        '[layout]\ndocs_dir = ".."\n',
        '[layout]\ndocs_dir = "my docs"\n',
        "[layout]\ndocs_dir = 1\n",
        "[layout]\nfront_matter = 1\n",
        '[layout]\ntypes = "no"\n',
        "[layout]\nindex = []\n",
        "[layout]\nwobble = true\n",
        "layout = true\n",
    ],
)
def test_a_layout_table_outside_the_schema_gives_exit_two(tmp_path, text):
    """A `docs_dir` that is not one directory name, a switch that is not a boolean, or an unknown key gives exit 2 (D14.5, I-4).

    arch: D14.5, I-4
    """
    (tmp_path / "ref_check.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)
    assert main(["--root", str(tmp_path)]) == 2


def test_checks_licence_defaults_on_and_must_be_a_bool(tmp_path):
    """`[checks] licence` is on when absent and takes only true or false.

    arch: D15.14, D15.15
    """
    assert "licence" in CONFIG_SCHEMA["checks"]
    assert load_config(tmp_path, None).licence is True
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlicence = false\n", encoding="utf-8"
    )
    assert load_config(tmp_path, None).licence is False
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlicence = 1\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="licence"):
        load_config(tmp_path, None)


def test_the_arch_target_table_reads_sources_and_forms(tmp_path):
    """The loader reads `[targets.arch]`; an absent key gives an empty value (D16.2).

    arch: D16.2
    """
    (tmp_path / "ref_check.toml").write_text(
        '[targets.arch]\nsources = ["docs/a.md", "../x/*.md"]\nforms = ["D-<n>"]\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.declared == ("docs/a.md", "../x/*.md")
    assert config.id_forms == ("D-<n>",)
    assert Config().declared == ()
    assert Config().id_forms == ()
    assert CONFIG_SCHEMA["targets"] == ("law", "arch")


@pytest.mark.parametrize(
    "body",
    [
        'sources = ["/abs/page.md"]\n',
        'sources = [""]\n',
        "sources = 1\n",
        "forms = 1\n",
        'forms = ["D-1"]\n',
        'forms = ["<n>"]\n',
        'forms = ["D <n>"]\n',
        'forms = ["D,<n>"]\n',
        'forms = ["D<n><m>"]\n',
        'forms = ["D<n>1"]\n',
        f'forms = ["D<n>{"x" * 24}"]\n',
        "forms = [{}]\n".format(", ".join(f'"D{i}<n>"' for i in range(17))),
        'other = "x"\n',
    ],
)
def test_a_bad_arch_target_table_gives_exit_two(tmp_path, body):
    """An absolute source, a bad form or an unknown key stops the run (D16.2).

    arch: D16.2
    """
    (tmp_path / "ref_check.toml").write_text(
        f"[targets.arch]\n{body}", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="targets.arch"):
        load_config(tmp_path)
