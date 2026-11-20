"""Unit tests for the design id about document link rules."""

import hashlib
import re
from pathlib import Path

import pytest

from tests.refs.conftest import materialise
from trueup.ref_check import (
    _link_destination,
    _link_pin,
    _md_link_targets,
    format_failure,
    main,
    run,
    section_pin,
)


def _turn_on_links(root):
    """Write a `ref_check.toml` that switches check g on (D2.5)."""
    (root / "ref_check.toml").write_text("[checks]\nlinks = true\n", encoding="utf-8")


def test_document_link_rules(tmp_path):
    """Slugs, code spans, fenced blocks, schemes, and fragments, each resolve as stated (D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## Verification\n\n"
        "See [the guide](guide.md#a-heading).\n"
        "A broken link: [gone](guide.md#missing).\n"
        "An external link: [site](https://example.org/x).\n"
        "A link in a code span: `[gone](guide.md#missing)`.\n\n"
        "```\n[gone](guide.md#missing)\n```\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text("## A heading\n\nText.\n", encoding="utf-8")

    report = run(tmp_path)
    broken = [format_failure(f) for f in report.failures if f.kind == "broken-link"]
    assert broken == [
        "docs/ARCHITECTURE.md:4: [broken-link] link does not resolve: guide.md#missing"
    ]


def test_reference_definition_and_directory_target(tmp_path):
    """A `[label]: target` link, and a directory target, each resolve too (D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "features").mkdir()
    (docs / "features" / "one.md").write_text("Text.\n", encoding="utf-8")
    (docs / "page.md").write_text(
        "See [the label][gone].\n\n[gone]: features/missing.md\n[ok]: features\n",
        encoding="utf-8",
    )

    report = run(tmp_path)
    broken = [format_failure(f) for f in report.failures if f.kind == "broken-link"]
    assert broken == [
        "docs/page.md:3: [broken-link] link does not resolve: features/missing.md"
    ]


def test_fragment_on_the_same_file_and_repeated_heading(tmp_path):
    """An empty path part checks the fragment against the same file's own headings.

    A repeated heading text gives the second slug a `-1` suffix (D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text(
        "## Notes\n\n"
        "## Notes\n\n"
        "See [here](#notes) and [again](#notes-1) and [gone](#missing).\n",
        encoding="utf-8",
    )

    report = run(tmp_path)
    broken = [format_failure(f) for f in report.failures if f.kind == "broken-link"]
    assert broken == ["docs/page.md:5: [broken-link] link does not resolve: #missing"]


def test_target_outside_the_root_is_broken(tmp_path):
    """A path target that resolves outside the root fails, even when a file exists there (D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    outside = tmp_path.parent / "outside.md"
    outside.write_text("Text.\n", encoding="utf-8")
    (docs / "page.md").write_text(
        "See [it](../../outside.md).\n",
        encoding="utf-8",
    )

    report = run(tmp_path)
    broken = [format_failure(f) for f in report.failures if f.kind == "broken-link"]
    assert broken == [
        "docs/page.md:1: [broken-link] link does not resolve: ../../outside.md"
    ]


def test_links_switch_off_skips_the_check(tmp_path):
    """With no `links` switch on, a broken document link gives no failure (D2.5, D2.10).

    arch: D2.10
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text("See [gone](missing.md).\n", encoding="utf-8")

    report = run(tmp_path)
    broken = [failure for failure in report.failures if failure.kind == "broken-link"]
    assert broken == []


def test_titles_angle_brackets_and_percent_encoding(tmp_path):
    """A link title, a target in `<...>`, and percent-encoding resolve to the file (D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "my page.md").write_text("# My page\n", encoding="utf-8")
    (docs / "index.md").write_text(
        "# Index\n\n"
        '[a](my%20page.md "The title")\n'
        "[b](<my page.md>)\n"
        "[c](<my page.md#my-page> 'T')\n"
        "[d]: <my page.md>\n"
        '[e](gone.md "The title")\n',
        encoding="utf-8",
    )

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/index.md:7: [broken-link] link does not resolve: gone.md"
    ]


def test_query_string_is_not_part_of_the_path(tmp_path):
    """The path part of a local target ends at the first `?`, and the fragment is still checked (D2.10).

    arch: D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "sim.html").write_text("<p>sim</p>\n", encoding="utf-8")
    (docs / "guide.md").write_text("## Install\n", encoding="utf-8")
    (docs / "index.md").write_text(
        "# Index\n\n"
        '[a](../public/sim.html?preset=coast&set=house.case:H100 "Open")\n'
        "[b](../public/gone.html?preset=coast)\n"
        "[c](guide.md?v=1#install)\n"
        "[d](guide.md?v=1#missing)\n",
        encoding="utf-8",
    )

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/index.md:4: [broken-link] link does not resolve: "
        "../public/gone.html?preset=coast",
        "docs/index.md:6: [broken-link] link does not resolve: guide.md?v=1#missing",
    ]


def test_slugs_keep_other_letters_and_drop_inline_markup(tmp_path):
    """A slug keeps non-ASCII letters and takes the text of inline links (D2.10).

    arch: D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        "## [Foo](x.md) bar\n\n"
        "## Café résumé\n\n"
        "## Use `ref:` <em>here</em>\n\n"
        "[a](#foo-bar) [b](#café-résumé) [c](#use-ref-here) [d](#foo-x-bar)\n",
        encoding="utf-8",
    )
    (docs / "x.md").write_text("# X\n", encoding="utf-8")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/index.md:7: [broken-link] link does not resolve: #foo-x-bar"
    ]


def _broken_fragments(root):
    """Give the fragment of each broken-link failure of a run, in order."""
    return [
        format_failure(f).rsplit("#", 1)[-1]
        for f in run(root).failures
        if f.kind == "broken-link"
    ]


def test_html_id_and_name_attributes_are_anchors(tmp_path):
    """An `id` or `name` attribute of an HTML tag outside fenced code is an anchor (D14.12).

    arch: D14.12
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text(
        '<a id="top"></a>\n'
        "<a name='old-anchor'></a>\n"
        '<div class="note"\n     id="split-tag">Text.</div>\n'
        '<span data-id="not-an-anchor"></span>\n\n'
        '```\n<a id="fenced"></a>\n```\n\n'
        "[a](#top) [b](#old-anchor) [c](#split-tag) [d](#not-an-anchor) [e](#fenced)\n",
        encoding="utf-8",
    )
    (docs / "other.md").write_text(
        "See [it](page.md#top) and [gone](page.md#fenced).\n", encoding="utf-8"
    )

    assert sorted(_broken_fragments(tmp_path)) == ["fenced", "fenced", "not-an-anchor"]


def test_attribute_list_id_gives_the_id_and_the_plain_slug(tmp_path):
    """A `{#x}` at the end of a heading gives `x` and the slug of the text without it (D14.12).

    The GitHub slug of the full text still resolves, so the set only grows.

    arch: D14.12
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text(
        "## Install the tool {#install}\n\n"
        "## Setup {: #setup .note }\n\n"
        "## Plain {.note}\n\n"
        "[a](#install) [b](#install-the-tool) [c](#install-the-tool-install)\n"
        "[d](#setup) [e](#setup--setup-note-) [f](#plain-note) [g](#note)\n",
        encoding="utf-8",
    )

    assert _broken_fragments(tmp_path) == ["note"]


def test_python_markdown_toc_slugs_resolve_beside_github_slugs(tmp_path):
    """The python-markdown `toc` slug of each heading is an anchor beside the GitHub one (D14.12).

    arch: D14.12
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text(
        "## Café résumé\n\n"
        "## A -- B: the end\n\n"
        "## Notes\n\n"
        "## Notes\n\n"
        "[a](#cafe-resume) [b](#café-résumé) [c](#a-b-the-end) [d](#a----b-the-end)\n"
        "[e](#notes) [f](#notes-1) [g](#notes_1) [h](#notes_2) [i](#caf-rsum)\n",
        encoding="utf-8",
    )

    assert sorted(_broken_fragments(tmp_path)) == ["caf-rsum", "notes_2"]


def test_check_g_does_not_follow_a_directory_symlink(tmp_path):
    """Check g walks `docs/` as the source walk does, so a symlink to a directory is not entered (D2.10).

    arch: D2.10
    """
    _turn_on_links(tmp_path)
    sub = tmp_path / "docs" / "sub"
    sub.mkdir(parents=True)
    (sub / "guide.md").write_text("# Guide\n\n[gone](gone.md)\n", encoding="utf-8")
    (tmp_path / "docs" / "alias").symlink_to(sub, target_is_directory=True)

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/sub/guide.md:3: [broken-link] link does not resolve: gone.md"
    ]


def test_a_nul_byte_in_a_link_target_is_a_broken_link_not_a_crash(tmp_path):
    """A link path that holds a NUL byte after decoding fails closed, not with a traceback (I-4, D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "p.md").write_text("[x](a%00b.md)\n", encoding="utf-8")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/p.md:1: [broken-link] link does not resolve: a%00b.md"
    ]
    assert main(["--root", str(tmp_path)]) == 1


def test_a_symlink_loop_in_a_link_target_is_a_broken_link_not_a_crash(tmp_path):
    """A link target through a symlink loop fails closed with broken-link, not a traceback (I-4, D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "loop.md").symlink_to(vendor / "loop.md")
    (docs / "page.md").write_text("[x](../vendor/loop.md)\n", encoding="utf-8")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/page.md:1: [broken-link] link does not resolve: ../vendor/loop.md"
    ]
    assert main(["--root", str(tmp_path)]) == 1


def test_a_target_with_a_long_file_name_is_a_broken_link_not_a_crash(tmp_path):
    """A link target whose file name exceeds the OS limit fails closed with broken-link (I-4, D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    long_name = "a" * 300 + ".md"
    (docs / "page.md").write_text(f"[x]({long_name})\n", encoding="utf-8")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        f"docs/page.md:1: [broken-link] link does not resolve: {long_name}"
    ]
    assert main(["--root", str(tmp_path)]) == 1


def test_a_page_that_does_not_decode_gives_unreadable_not_a_skip(tmp_path):
    """A docs page that does not decode fails closed with `unreadable`, not a silent skip (I-4, D2.10).

    arch: D2.4, D2.10
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "p.md").write_bytes(b"\xff")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/p.md:1: [unreadable] file cannot be read: UnicodeDecodeError"
    ]


def test_check_g_and_check_h_agree_on_one_unreadable_line(tmp_path):
    """With links and layout both on, an unreadable page gives its line once, not twice (U1, D2.4).

    arch: D2.4, D2.10
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nlinks = true\nlayout = true\n", encoding="utf-8"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "p.md").write_bytes(b"\xff")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "docs/p.md:1: [unreadable] file cannot be read: UnicodeDecodeError"
    ]


def _pin(section):
    """Give the first eight hex digits of the D2.7 step 4 hash of one text.

    arch: none - a helper, not a test.
    """
    normalised = re.sub(r"\s+", " ", section).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:8]


PIN_PAGE = (
    "# Page\n"
    "\n"
    "## A\n"
    "\n"
    "Text of A.\n"
    "\n"
    "### A sub\n"
    "\n"
    "```\n"
    "## not a heading\n"
    "```\n"
    "\n"
    "## B\n"
    "\n"
    "Text of B.\n"
    "\n"
    "## A\n"
    "\n"
    "Last.\n"
)


def test_section_pin_takes_the_section_limits_and_the_hash():
    """A section ends at a heading of the same or a higher level, and its pin is the D2.7 hash (D2.10).

    arch: D2.10
    """
    section_a = "## A\n\nText of A.\n\n### A sub\n\n```\n## not a heading\n```\n"
    assert section_pin(PIN_PAGE, "a") == _pin(section_a)
    assert section_pin(PIN_PAGE, "a-sub") == _pin(
        "### A sub\n\n```\n## not a heading\n```\n"
    )
    assert section_pin(PIN_PAGE, "b") == _pin("## B\n\nText of B.\n")
    assert section_pin(PIN_PAGE, "a-1") == _pin("## A\n\nLast.\n")
    assert section_pin(PIN_PAGE, "page") == _pin(PIN_PAGE)
    assert section_pin(PIN_PAGE, "not-a-heading") is None
    assert section_pin(PIN_PAGE.replace("Text of A.", "Text  of\nA."), "a") == _pin(
        section_a
    )
    assert section_pin(PIN_PAGE.replace("Text of A.", "Text of a."), "a") != _pin(
        section_a
    )


PIN_EXPECTED = {
    "pin-match": [],
    "pin-changed": [
        "README.md:3: [stale-pin] pinned section changed: docs/guide.md#the-rule",
    ],
    "pin-broken-fragment": [
        "README.md:3: [broken-link] link does not resolve: docs/guide.md#absent",
    ],
    "pin-orphan": [
        'README.md:6: [malformed] pin has no link on its line: "pin:c641c99d"',
    ],
    "pin-not-apply": [
        "README.md:3: [stale-pin] pin does not apply: LICENSE",
        "README.md:4: [stale-pin] pin does not apply: docs/guide.md",
        "README.md:5: [stale-pin] pin does not apply: docs/guide.md#the-rule",
        "README.md:8: [stale-pin] pin does not apply: LICENSE",
    ],
}


@pytest.mark.parametrize("case", sorted(PIN_EXPECTED))
def test_each_pin_tree_gives_its_failure_lines(case, tmp_path):
    """A pin that matches gives no line; a stale pin, a broken fragment, a pin that does not apply and an orphan pin title each give theirs (D2.10).

    arch: D2.10, D2.4
    """
    tree = materialise(case, tmp_path)
    assert [format_failure(f) for f in run(tree).failures] == PIN_EXPECTED[case]


def test_a_pin_needs_the_links_switch(tmp_path):
    """With `links` off, a stale pin gives no failure (D2.10, S18).

    arch: D2.10
    """
    tree = materialise("pin-changed", tmp_path)
    (tree / "ref_check.toml").unlink()
    assert run(tree).failures == []


def test_check_g_reads_the_markdown_files_at_the_root(tmp_path):
    """A root `*.md` file is read with no `docs/` directory; a name that starts with `.` is not (D2.10).

    arch: D2.10
    """
    _turn_on_links(tmp_path)
    (tmp_path / "README.md").write_text("# R\n\n[gone](gone.md)\n", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("[gone](gone.md)\n", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text(
        "A `[x](<t>)` span and <t> text.\n", encoding="utf-8"
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text("[gone](gone.md)\n", encoding="utf-8")

    report = run(tmp_path)
    assert [format_failure(f) for f in report.failures] == [
        "README.md:3: [broken-link] link does not resolve: gone.md"
    ]


ROOT = Path(__file__).resolve().parents[2]
"""The root of this repository."""

REPOSITORY_PINS = {"README.md": 2, "CONTRIBUTING.md": 1}
"""The count of pins that each root page of this repository holds."""


@pytest.mark.parametrize("name", sorted(REPOSITORY_PINS))
def test_check_g_reads_every_pin_of_this_repository(name):
    """Each pin of a root page is on the line of its link, and it matches its section (D2.10).

    The reader of check g works on one line, so a pin on a second line is
    not read. The test counts the pin titles in the text, and it counts the
    pins that the reader gives. The two counts are equal, and each pin is
    the pin of the section that its link cites.

    arch: D2.10, D2.4
    """
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    written = [
        target for _, target in _md_link_targets(text) if _link_pin(target) is not None
    ]

    assert len(written) == REPOSITORY_PINS[name]
    assert text.count('"pin' + ":") == REPOSITORY_PINS[name]
    for target in written:
        page, _, fragment = _link_destination(target).partition("#")
        cited = (path.parent / page).resolve()
        expected = section_pin(cited.read_text(encoding="utf-8"), fragment)
        assert _link_pin(target) == expected, target


MARKDOWN_CASES = {
    "links-gfm-tilde": [
        "docs/page.md:9: [broken-link] link does not resolve: missing-after-tilde.md",
        "docs/page.md:17: [broken-link] link does not resolve: missing-after-long.md",
    ],
    "links-gfm-indented": [
        "docs/page.md:8: [broken-link] link does not resolve: missing-after-code.md",
        "docs/page.md:9: [broken-link] link does not resolve: missing-continued.md",
        "docs/page.md:13: [broken-link] link does not resolve: missing-list.md",
    ],
    "links-double-backtick": [
        "docs/page.md:5: [broken-link] link does not resolve: missing-real.md",
    ],
    "links-setext": [
        "docs/page.md:10: [broken-link] link does not resolve: #list-item",
        "docs/page.md:10: [broken-link] link does not resolve: #missing-setext",
    ],
    "links-root-relative": [
        "docs/page.md:5: [broken-link] link does not resolve: /../outside.md",
        "docs/page.md:5: [broken-link] link does not resolve: /docs/missing-root.md",
    ],
    "links-parens": [
        "docs/page.md:5: [broken-link] link does not resolve: gone_(y).md",
    ],
    "links-footnote": [
        "docs/page.md:6: [broken-link] link does not resolve: missing-ref.md",
    ],
    "links-escaped": [
        "docs/page.md:5: [broken-link] link does not resolve: missing-real.md",
    ],
    "links-entity": [
        "docs/page.md:5: [broken-link] link does not resolve: #missing-entity",
    ],
}
"""The failure lines of each Markdown case tree. Each tree also holds the
false failures of the case, which must not show (D15.18)."""


@pytest.mark.parametrize("case", sorted(MARKDOWN_CASES))
def test_each_markdown_case_gives_only_its_real_broken_links(case, tmp_path):
    """Each Markdown case tree gives its real broken links and none of its false ones.

    The cases are a `~~~` fence and a longer fence, an indented code block
    outside a list, a double-backtick code span, setext headings, a target
    from the root, a target with parentheses, a footnote, an escaped
    bracket, and an HTML entity in a heading.

    arch: D15.18
    """
    tree = materialise(case, tmp_path)
    report = run(tree)
    assert [format_failure(failure) for failure in report.failures] == MARKDOWN_CASES[
        case
    ]


def test_a_target_with_parentheses_keeps_its_title_out_of_the_destination():
    """A target with one level of parentheses and a title gives the whole path as the destination.

    arch: D15.18
    """
    targets = _md_link_targets('See [x](a_(b).md "A title") and \\[y\\](z.md).\n')
    assert [_link_destination(target) for _, target in targets] == ["a_(b).md"]


def test_a_link_target_that_starts_with_a_placeholder_is_skipped(tmp_path):
    """A target that starts with `${NAME}` is not a broken link; three other forms still fail.

    arch: D16.4
    """
    _turn_on_links(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ok.tmpl.md").write_text(
        "[a](${ROOT}/missing.md)\n[b](${X}/gone.md#frag)\n\n[r]: ${ROOT}/also.md\n",
        encoding="utf-8",
    )
    (docs / "bad.tmpl.md").write_text(
        "[a](plain-missing.md)\n[b](docs/${X}/missing.md)\n[c](.$name.md)\n",
        encoding="utf-8",
    )

    report = run(tmp_path)
    got = [format_failure(f) for f in report.failures]
    assert got == [
        "docs/bad.tmpl.md:1: [broken-link] link does not resolve: plain-missing.md",
        "docs/bad.tmpl.md:2: [broken-link] link does not resolve: docs/${X}/missing.md",
        "docs/bad.tmpl.md:3: [broken-link] link does not resolve: .$name.md",
    ]
