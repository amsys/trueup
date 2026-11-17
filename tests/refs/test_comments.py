"""Unit tests for the design ids about comments: the registry and check f."""

from trueup.ref_check import format_failure, run


def test_comment_r1_and_r2_rules(tmp_path):
    """A table of comments gives the R1 result, the R2 result, or no marker (D2.2).

    arch: D2.2
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "## D1.2 — a design id\n\n## Verification\n\nD1.2\n",
        encoding="utf-8",
    )
    source = tmp_path / "sample.py"
    source.write_text(
        "# FIXME: an R1 tag, held in TODO's spot\n"
        "# refs: arch/D1.2\n"
        "# wobble: arch/D1.2\n"
        "x = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    ids = {edge.id for edge in report.edges}
    kinds = {failure.kind for failure in report.failures}
    assert "D1.2" in ids
    assert "unregistered" in kinds


def test_suppression_reason_and_file_header(tmp_path):
    """A table of suppressions, with and without a reason, and of headers (D2.9).

    arch: D2.9
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text(
        "x = 1  # noqa: F401  # reason: kept for the side effect\n",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.py"
    bad.write_text("y = 1  # noqa\n", encoding="utf-8")
    headed = tmp_path / "headed.sh"
    headed.write_text("#!/bin/sh\n# a header\necho hi\n", encoding="utf-8")
    headless = tmp_path / "headless.sh"
    headless.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    kinds_and_paths = {(failure.kind, failure.path) for failure in report.failures}
    assert ("no-reason", "bad.py") in kinds_and_paths
    assert ("no-header", "headless.sh") in kinds_and_paths
    assert ("no-reason", "good.py") not in kinds_and_paths
    assert ("no-header", "headed.sh") not in kinds_and_paths


def test_suppression_shell_and_sql_forms(tmp_path):
    """The shellcheck form and the SQL noqa form, each with and without a reason (D2.9).

    arch: D2.9
    """
    good_sh = tmp_path / "good.sh"
    good_sh.write_text(
        "#!/bin/sh\n# header\necho hi  # shellcheck disable=SC2086  # the word split is wanted\n",
        encoding="utf-8",
    )
    bad_sh = tmp_path / "bad.sh"
    bad_sh.write_text(
        "#!/bin/sh\n# header\necho hi  # shellcheck disable=SC2086\n",
        encoding="utf-8",
    )
    good_sql = tmp_path / "good.sql"
    good_sql.write_text(
        "-- header\nSELECT 1;  /* the vendor fixes this layout */ -- noqa: LT01\n",
        encoding="utf-8",
    )
    bad_sql = tmp_path / "bad.sql"
    bad_sql.write_text("-- header\nSELECT 1;  -- noqa\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    kinds_and_paths = {(failure.kind, failure.path) for failure in report.failures}
    assert ("no-reason", "bad.sh") in kinds_and_paths
    assert ("no-reason", "good.sh") not in kinds_and_paths
    assert ("no-reason", "bad.sql") in kinds_and_paths
    assert ("no-reason", "good.sql") not in kinds_and_paths


def test_sql_reason_is_a_block_comment(tmp_path):
    """The SQL reason is a block comment before the bare noqa; the old two-leader form fails (D2.9).

    arch: D2.9
    """
    block = tmp_path / "block.sql"
    block.write_text(
        "-- header\nSELECT a,b FROM t;  /* the vendor fixes this layout */ -- noqa: LT01\n",
        encoding="utf-8",
    )
    dashes = tmp_path / "dashes.sql"
    dashes.write_text(
        "-- header\nSELECT a,b FROM t;  /* the -- is in the reason */ -- noqa: LT01\n",
        encoding="utf-8",
    )
    old = tmp_path / "old.sql"
    old.write_text(
        "-- header\nSELECT a,b FROM t;  -- noqa: LT01  -- the vendor fixes this layout\n",
        encoding="utf-8",
    )
    empty = tmp_path / "empty.sql"
    empty.write_text(
        "-- header\nSELECT a,b FROM t;  /*  */ -- noqa: LT01\n", encoding="utf-8"
    )
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    lines = {format_failure(failure) for failure in report.failures}
    paths = {failure.path for failure in report.failures if failure.kind == "no-reason"}
    assert "block.sql" not in paths
    assert "dashes.sql" not in paths
    assert (
        "old.sql:2: [no-reason] -: suppression has no reason: noqa: LT01  -- the vendor fixes this layout"
        in lines
    )
    assert "empty.sql:2: [no-reason] -: suppression has no reason: noqa: LT01" in lines


def test_suppression_header_edge_cases(tmp_path):
    """A file with no shebang, a comment-first file, and a blank line before the header (D2.9).

    arch: D2.9
    """
    no_shebang = tmp_path / "no_shebang.sh"
    no_shebang.write_text("echo hi\n", encoding="utf-8")
    comment_first = tmp_path / "comment_first.sh"
    comment_first.write_text("# a header\necho hi\n", encoding="utf-8")
    blank_then_comment = tmp_path / "blank_then_comment.sh"
    blank_then_comment.write_text("#!/bin/sh\n\n# header\necho hi\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    kinds_and_paths = {(failure.kind, failure.path) for failure in report.failures}
    assert ("no-header", "no_shebang.sh") in kinds_and_paths
    assert ("no-header", "comment_first.sh") not in kinds_and_paths
    assert ("no-header", "blank_then_comment.sh") not in kinds_and_paths


def test_a_hash_in_a_python_string_is_not_a_suppression(tmp_path):
    """Check f reads a Python suppression from a comment token only (D2.9).

    arch: D2.9
    """
    from trueup.ref_check import Failure

    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    source = '"""Module."""\n\nX = "#noqa"\nY = "#a"  # noqa: F401\n'
    (tmp_path / "sample.py").write_text(source, encoding="utf-8")
    report = run(tmp_path)
    assert report.failures == [
        Failure(
            "sample.py", 4, "no-reason", "module: suppression has no reason: noqa: F401"
        )
    ]


def test_suppression_reason_python_coding_declaration(tmp_path):
    """A `.py` file with a PEP 263 coding declaration decodes by its own codec before check f reads it (R-12).

    arch: D2.9
    """
    src = tmp_path / "src"
    src.mkdir()
    latin1_source = "# coding: latin-1\n# café note\nx = 1  # noqa\n"
    (src / "a.py").write_bytes(latin1_source.encode("latin-1"))
    utf8_source = "# a note\n# café note\nx = 1  # noqa\n"
    (src / "b.py").write_text(utf8_source, encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\ncomments = true\n", encoding="utf-8"
    )
    report = run(tmp_path)
    by_path = {
        failure.path: (failure.line, failure.kind, failure.detail)
        for failure in report.failures
        if failure.kind == "no-reason"
    }
    assert by_path["src/a.py"] == by_path["src/b.py"]


def test_check_f_reads_no_suppression_in_a_heredoc(tmp_path):
    """A `shellcheck disable` line inside a heredoc body is text, not a suppression.

    arch: D15.18
    """
    from trueup.ref_check import _check_f

    script = tmp_path / "gen.sh"
    script.write_text(
        "#!/bin/sh\n# Write a file.\ncat > x.sh <<'EOF'\n# shellcheck disable=SC2086\nEOF\n"
        "# shellcheck disable=SC2034\n",
        encoding="utf-8",
    )
    failures = _check_f(tmp_path, [(script, "shell")])
    assert [format_failure(failure) for failure in failures] == [
        "gen.sh:6: [no-reason] -: suppression has no reason: shellcheck disable=SC2034"
    ]
