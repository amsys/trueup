"""Unit tests for the design ids about marker recognition."""

import pytest

from trueup.ref_check import (
    REGISTRY,
    marker_candidate,
    parse_legacy_marker,
    parse_marker,
    run,
)


def test_marker_text_outside_a_marker_position_gives_no_reference(tmp_path):
    """Marker text in a string, in Markdown, or in an unlisted file, is not read (I-1).

    arch: I-1
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## D1.2 — a design id\n\n"
        "Prose that quotes a marker in a code span: `ref: arch/D1.2`.\n\n"
        "## Verification\n\nD1.2\n",
        encoding="utf-8",
    )
    source = tmp_path / "sample.py"
    source.write_text('literal = "ref: arch/D1.2"\n', encoding="utf-8")
    unlisted = tmp_path / "notes.rst"
    unlisted.write_text("ref: arch/D1.2\n", encoding="utf-8")
    report = run(tmp_path)
    ids = {edge.id for edge in report.edges}
    assert "D1.2" not in ids


@pytest.mark.parametrize(
    "text",
    [
        "use `ref:` here for a design id",
        "The word law: in the middle of a sentence",
        "  and arch: D1.2 after other text",
        "plain prose with no keyword",
    ],
)
def test_a_keyword_inside_a_sentence_is_not_a_marker(text):
    """The anchored rule reads the first text of the line only (I-1).

    arch: I-1
    """
    assert parse_marker(text) is None


@pytest.mark.parametrize(
    ("text", "keyword", "refs"),
    [
        ("ref: arch/D1.2", "ref", (("arch", "D1.2"),)),
        ("# ref: arch/D1.2, arch/I-1", "ref", (("arch", "D1.2"), ("arch", "I-1"))),
        (
            "ref: law/acts/Income_Tax_Act/v13/s.111",
            "ref",
            (("law", "acts/Income_Tax_Act/v13/s.111"),),
        ),
        (
            "// arch: D1.2, I-1 - the gate closes",
            "arch",
            (("arch", "D1.2"), ("arch", "I-1")),
        ),
        ("-- arch: I-1", "arch", (("arch", "I-1"),)),
        (
            "law: acts/Income_Tax_Act/v13 s.111",
            "law",
            (("law", "acts/Income_Tax_Act/v13/s.111"),),
        ),
        (
            "/// law: acts/Value_Added_Tax_Act/base s.22A - the rate",
            "law",
            (("law", "acts/Value_Added_Tax_Act/base/s.22A"),),
        ),
        ("ref: arch/D1.2, arch/D1.2", "ref", (("arch", "D1.2"),)),
        ("arch: D1.2, I-1, D1.2", "arch", (("arch", "D1.2"), ("arch", "I-1"))),
    ],
)
def test_the_anchored_rule_gives_the_canonical_pairs(text, keyword, refs):
    """Each marker form of the grammar gives the same canonical pairs (D2.1).

    arch: D2.1
    """
    marker = parse_marker(text)
    assert marker is not None
    assert (marker.keyword, marker.refs, marker.malformed) == (keyword, refs, False)


@pytest.mark.parametrize(
    "text",
    [
        "ref: not-a-body",
        "ref: arch/D1",
        "ref: law/acts/Income_Tax_Act/v13",
        "ref:arch/D1.2",
        "arch: none of these ids",
        "law: acts/Income_Tax_Act/v13",
        "law: acts/Income_Tax_Act/v13 s.one",
    ],
)
def test_a_recognised_keyword_with_a_bad_body_is_malformed(text):
    """A body that does not parse gives the `malformed` result (D2.1).

    arch: D2.1
    """
    marker = parse_marker(text)
    assert marker is not None
    assert marker.malformed
    assert marker.refs == ()


def test_the_arch_body_none_gives_no_id_and_marks_the_unit():
    """An `arch` body of `none` excuses the unit and cites no id (D2.1).

    arch: D2.1
    """
    marker = parse_marker("# arch: none - this file checks the markers")
    assert marker is not None
    assert (marker.opt_out, marker.refs, marker.malformed) == (True, (), False)


@pytest.mark.parametrize(
    ("text", "refs", "opt_out", "malformed"),
    [
        (
            "Reads the gate. arch: D1.2, I-1",
            (("arch", "D1.2"), ("arch", "I-1")),
            False,
            False,
        ),
        ("ARCH: D2.1 with no case", (("arch", "D2.1"),), False, False),
        ("arch: D1.2, D1.2", (("arch", "D1.2"),), False, False),
        ("arch: none - this file checks the markers", (), True, False),
        ("arch: a body with no id", (), False, True),
    ],
)
def test_the_legacy_rule_reads_a_test_docstring_line(text, refs, opt_out, malformed):
    """The legacy rule keeps the regex of the existing checker (D2.1).

    arch: D2.1
    """
    marker = parse_legacy_marker(text)
    assert marker is not None
    assert (marker.refs, marker.opt_out, marker.malformed) == (refs, opt_out, malformed)


def test_marker_forms_and_the_malformed_result(tmp_path):
    """A table of marker texts gives the reference, or `malformed`, per D2.1.

    arch: D2.1
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## D1.2 — a design id\n\n## Verification\n\nD1.2\n",
        encoding="utf-8",
    )
    source = tmp_path / "sample.py"
    source.write_text(
        '"""Module.\n\n'
        "# ref: arch/D1.2\n"
        '"""\n\n'
        "def helper():\n"
        '    """A comment style marker.\n\n'
        "    # arch: D1.2 - the gate closes\n"
        '    """\n\n'
        "def bad():\n"
        '    """A recognised keyword with no id.\n\n'
        "    # ref: not-a-body\n"
        '    """\n',
        encoding="utf-8",
    )
    report = run(tmp_path)
    ids = {edge.id for edge in report.edges}
    kinds = {failure.kind for failure in report.failures}
    assert "D1.2" in ids
    assert "malformed" in kinds


def test_the_registry_is_closed_to_the_table_of_the_design():
    """`REGISTRY` holds exactly the marker words of the D2.2 table (D2.2).

    arch: D2.2
    """
    assert set(REGISTRY) == {"ref", "arch", "law", "SAFETY", "TODO"}


@pytest.mark.parametrize(
    "text",
    [
        "REFS: arch/D1.2",
        "# NB: arch/D1.2",
        "-- HACK: this is odd",
    ],
)
def test_a_tag_or_reference_shape_word_not_in_the_registry_is_a_registry_candidate(
    text,
):
    """Rule R1 or R2 finds a candidate word that `REGISTRY` does not list (D2.2).

    arch: D2.2
    """
    candidate = marker_candidate(text, docstring=False)
    assert candidate is not None
    assert candidate not in REGISTRY


def test_an_unregistered_reference_shape_word_fails_the_registry_check(tmp_path):
    """A candidate word absent from `REGISTRY` gives the `unregistered` failure (D2.2).

    arch: D2.2
    """
    source = tmp_path / "sample.py"
    source.write_text("x = 1  # refs: arch/D1.2\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    kinds = {failure.kind for failure in report.failures}
    assert "unregistered" in kinds


@pytest.mark.parametrize("local_tags", ['local_tags = ["D"]\n', ""])
def test_a_local_tag_passes_the_registry_check_only_with_the_key(tmp_path, local_tags):
    """A `# D1:` comment passes with `local_tags = ["D"]` and fails without it (D2.2, D2.5).

    arch: D2.2, D2.5
    """
    (tmp_path / "sample.py").write_text(
        "x = 1  # D1: the first decision\n", encoding="utf-8"
    )
    (tmp_path / "ref_check.toml").write_text(
        f"[checks]\nregistry = true\n\n[registry]\n{local_tags}", encoding="utf-8"
    )
    unregistered = [f for f in run(tmp_path).failures if f.kind == "unregistered"]
    if local_tags:
        assert unregistered == []
    else:
        assert [(f.path, f.line) for f in unregistered] == [("sample.py", 1)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# D: a note", None),
        ("# D1: a note", None),
        ("# D12(owner): a note", None),
        ("# DONE: a note", "DONE"),
        ("# D1X: a note", "D1X"),
        ("# FIXME: a note", "FIXME"),
    ],
)
def test_a_local_tag_is_a_prefix_alone_or_a_prefix_and_digits(text, expected):
    """Rule R1 drops a word that is a local prefix, or a local prefix and digits (D2.2).

    arch: D2.2
    """
    assert (
        marker_candidate(text, docstring=False, local_tags=frozenset({"D"})) == expected
    )


def test_a_marker_reads_the_configured_id_patterns() -> None:
    """Each marker parser takes the compiled patterns, and defaults to today's (D16.2).

    arch: D16.2
    """
    from trueup.ref_check import _id_grammar

    grammar = _id_grammar(("D<n>.<m>.<k>", "D-<n>"))
    assert parse_marker("# arch: D1.2.3", grammar.whole).refs == (("arch", "D1.2.3"),)
    assert parse_marker("# ref: arch/D-9", grammar.whole).refs == (("arch", "D-9"),)
    assert parse_marker("# arch: D1.2", grammar.whole).malformed
    assert parse_marker("# arch: D1.2.3").malformed
    assert parse_legacy_marker("arch: D1.2.3, D-9", grammar.anywhere).refs == (
        ("arch", "D1.2.3"),
        ("arch", "D-9"),
    )
    assert marker_candidate("# refs: arch/D-9", False, frozenset(), grammar.whole) == (
        "refs"
    )
    assert marker_candidate("# refs: arch/D-9", False) is None
