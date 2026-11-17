"""Integration tests for the command line and one full checker run (D2.3, D4.1)."""

import subprocess
import sys

from pathlib import Path

from tests.refs.conftest import _excuse_tree, _readme_files, materialise

from trueup import ref_check
from trueup.ref_check import main, run

CHECKER = Path(__file__).resolve().parents[2] / "trueup" / "ref_check.py"
"""The checker, as an absolute path, so the child process needs no `cwd`."""


def test_command_line_flags_summary_and_exit_codes(tmp_path):
    """The flags, the summary line, and the three exit codes (D2.3).

    arch: D2.3
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("## Verification\n\n", encoding="utf-8")
    edges = tmp_path / "edges.json"

    assert main(["--root", str(tmp_path), "--edges", str(edges)]) == 0
    assert edges.read_text(encoding="utf-8") == '{\n  "schema": 1,\n  "edges": []\n}\n'

    (tmp_path / "ref_check.toml").write_text("[checks\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 2

    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("ref_check: ref_check.toml does not parse: ")
    assert result.stderr.count("\n") == 1


def test_one_checker_run_end_to_end(tmp_path):
    """One run finds the root, walks it, checks each reference, and reports (D4.1).

    arch: D4.1
    """
    tree = materialise("cli-one-run", tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--root",
            str(tree),
            "--edges",
            str(tree / "edges.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "ref_check: 0 failures, 1 references\n"
    assert (tree / "edges.json").exists()


def test_a_root_that_is_not_a_directory_gives_exit_two(tmp_path, capsys):
    """A `--root` that is absent or is a file stops the run with exit 2 (D2.3).

    arch: D2.3, I-4
    """
    absent = tmp_path / "absent"
    a_file = tmp_path / "file.txt"
    a_file.write_text("x\n", encoding="utf-8")

    for root in (absent, a_file):
        assert main(["--root", str(root)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == f"ref_check: root is not a directory: {root}\n"


def test_help_prints_the_usage_and_exits_zero(capsys):
    """`--help` and `-h` print the usage text on standard output and give exit 0 (D2.3).

    arch: D2.3
    """
    outputs = []
    for flag in ("--help", "-h"):
        assert main([flag]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        outputs.append(captured.out)
    assert outputs[0] == outputs[1]
    assert (
        outputs[0].splitlines()[0]
        == "usage: python3 ref_check.py [--root DIR] [--edges FILE] [--config FILE]"
    )


def test_root_takes_the_equals_form(tmp_path, capsys):
    """`--root=DIR` is the same as `--root DIR`; an empty value gives exit 2 (D2.3).

    arch: D2.3
    """
    assert main([f"--root={tmp_path}"]) == 0
    assert capsys.readouterr().out == "ref_check: 0 failures, 0 references\n"
    assert main(["--root="]) == 2
    assert capsys.readouterr().err == "ref_check: argument is not valid: --root=\n"


def _write_switches(root, **switches):
    """Write `ref_check.toml` at the root with these switches in `[checks]`."""
    lines = ["[checks]"] + [
        f"{key} = {str(value).lower()}" for key, value in switches.items()
    ]
    (root / "ref_check.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_no_configuration_gives_the_notice_of_all_checks_off(tmp_path, capsys):
    """With no `ref_check.toml`, standard error names checks e, f and g as off.

    arch: D2.3, D2.5
    """
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 0 references\n"
    assert captured.err == "ref_check: checks off: e, f, g, h, i\n"


def test_one_switch_on_gives_the_notice_of_the_other_two(tmp_path, capsys):
    """With only `comments = true`, standard error names checks e and g as off.

    arch: D2.3, D2.5
    """
    _write_switches(tmp_path, comments=True)
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 0 references\n"
    assert captured.err == "ref_check: checks off: e, g, h, i\n"


def test_all_switches_on_give_no_notice(tmp_path, capsys):
    """With all switches on, standard error is empty.

    arch: D2.3, D2.5
    """
    _readme_files(tmp_path)
    _write_switches(
        tmp_path, registry=True, comments=True, links=True, layout=True, readme=True
    )
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 0 references\n"
    assert captured.err == ""


def test_the_notice_does_not_change_the_exit_code_of_a_failure(tmp_path, capsys):
    """A run with a failure and checks off keeps exit 1 and its standard output.

    arch: D2.3, D2.5
    """
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_bad.py").write_text(
        'def test_bad():\n    """Bad.\n\n    arch: D9.9\n    """\n', encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == "ref_check: 1 failures, 1 references"
    assert captured.err == "ref_check: checks off: e, f, g, h, i\n"


def test_exit_two_and_help_give_no_notice(tmp_path, capsys):
    """A run that stops with exit 2, and `--help`, print no notice.

    arch: D2.3, D2.5
    """
    (tmp_path / "ref_check.toml").write_text(
        "[checks]\nregistry = 1\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "checks off" not in captured.err
    assert captured.err.count("\n") == 1

    (tmp_path / "ref_check.toml").unlink()
    assert (
        main(["--root", str(tmp_path), "--edges", str(tmp_path / "absent" / "e.json")])
        == 2
    )
    captured = capsys.readouterr()
    assert "checks off" not in captured.err
    assert captured.err.startswith("ref_check: edge file cannot be written: ")

    assert main(["--help"]) == 0
    assert capsys.readouterr().err == ""


def test_an_excused_claim_gives_the_notice_after_the_checks_off_notice(tmp_path):
    """The R-10 tree gives the excused notice on standard error, after the checks off notice.

    arch: D2.3, D2.8
    """
    _excuse_tree(tmp_path, cite=False)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "ref_check: 0 failures, 0 references\n"
    assert result.stderr == (
        "ref_check: checks off: e, f, g, h, i\nref_check: excused by an open plan row: D1.1\n"
    )


def test_the_excused_notice_stands_alone_when_the_checks_are_on(tmp_path, capsys):
    """With all switches on, the excused notice is the only line on standard error.

    arch: D2.3, D2.8
    """
    _excuse_tree(tmp_path, cite=False)
    _write_switches(
        tmp_path, registry=True, comments=True, links=True, layout=True, readme=True
    )
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 0 references\n"
    assert captured.err == "ref_check: excused by an open plan row: D1.1\n"


def test_run_makes_a_relative_root_absolute_before_any_read(tmp_path, monkeypatch):
    """A relative root and its absolute form give the same clean report (D4.1).

    arch: D4.1
    """
    tree = tmp_path / "tree"
    docs = tree / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text(
        "# Index\n\nRead [the guide](guide.md).\n", encoding="utf-8"
    )
    (docs / "guide.md").write_text("# Guide\n\nGuidance.\n", encoding="utf-8")
    (tree / "ref_check.toml").write_text("[checks]\nlinks = true\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    relative_report = run(Path("tree"))
    absolute_report = run(tree.resolve())

    assert relative_report.failures == []
    assert relative_report.failures == absolute_report.failures


def test_main_reads_the_configuration_one_time(tmp_path, monkeypatch):
    """`main` reads `ref_check.toml` one time for the whole run, through `run` (D4.1).

    arch: D4.1
    """
    calls = []
    original = ref_check.load_config

    def counting(root, path=None):
        calls.append(root)
        return original(root, path)

    monkeypatch.setattr(ref_check, "load_config", counting)
    assert main(["--root", str(tmp_path)]) == 0
    assert len(calls) == 1


def test_a_cited_claim_with_an_open_row_gives_no_excused_notice(tmp_path, capsys):
    """An id that a test cites and an open row names is proved, so no notice names it.

    arch: D2.3, D2.8
    """
    _excuse_tree(tmp_path, cite=True)
    _write_switches(
        tmp_path, registry=True, comments=True, links=True, layout=True, readme=True
    )
    assert main(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ref_check: 0 failures, 1 references\n"
    assert captured.err == ""


def test_config_flag_reads_the_configuration_from_another_file(tmp_path, capsys):
    """`--config FILE` reads `FILE` in place of `ROOT/ref_check.toml`; an absent `FILE` gives exit 2 (D8.1).

    The root holds no `ref_check.toml`, so a plain run has every switch off
    and reports nothing. The same run with a configuration elsewhere that
    turns check e on reports the unregistered marker, and the notice line
    follows the file that was read.

    arch: D8.1
    """
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)
    (root / "src" / "x.py").write_text("# X1: a local tag\n", encoding="utf-8")
    config = tmp_path / "elsewhere" / "checks.toml"
    config.parent.mkdir()
    config.write_text("[checks]\nregistry = true\n", encoding="utf-8")
    assert main(["--root", str(root)]) == 0
    assert "checks off: e, f, g, h, i" in capsys.readouterr().err
    assert main(["--root", str(root), "--config", str(config)]) == 1
    captured = capsys.readouterr()
    assert "[unregistered]" in captured.out
    assert "checks off: f, g, h, i" in captured.err
    assert main(["--root", str(root), f"--config={config}"]) == 1
    capsys.readouterr()
    assert main(["--root", str(root), "--config", str(tmp_path / "none.toml")]) == 2
    assert "none.toml" in capsys.readouterr().err
    assert main(["--help"]) == 0
    assert "[--config FILE]" in capsys.readouterr().out.splitlines()[0]


def test_a_kept_failure_is_not_printed_not_counted_and_gives_exit_zero(
    tmp_path, capsys
):
    """A failure named in `[keep] failures` leaves the output and the exit code, and gives the kept notice (D2.3, D9.2).

    arch: D2.3, D9.2
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "page.md").write_text("# A page\n", encoding="utf-8")
    (tmp_path / "ref_check.toml").write_text(
        '[checks]\nlayout = true\n\n[keep]\nfailures = ["docs/page.md:1:no-front-matter"]\n',
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path)]) == 0
    out, err = capsys.readouterr()
    assert "no-front-matter" not in out
    assert out.splitlines()[-1] == "ref_check: 0 failures, 0 references"
    assert err.splitlines() == [
        "ref_check: checks off: e, f, g, i",
        "ref_check: kept: 1",
    ]
    report = run(tmp_path)
    assert report.failures == []
    assert [(item.path, item.kind) for item in report.kept] == [
        ("docs/page.md", "no-front-matter")
    ]
    (tmp_path / "docs" / "other.md").write_text("# Other\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "docs/other.md:1: [no-front-matter] file has no front matter",
        "ref_check: 1 failures, 0 references",
    ]
    assert "ref_check: kept: 1" in err.splitlines()


def test_failure_ids_add_the_tail_and_the_count_where_ids_repeat():
    """`failure_ids` gives `<path>:<line>:<kind>`, the tail where the base repeats, and `:<n>` where ids still repeat (D9.2).

    arch: D9.2
    """
    failures = [
        ref_check.Failure("README.md", 1, "no-section", "section is absent: Install"),
        ref_check.Failure("README.md", 1, "no-section", "section is absent: Usage"),
        ref_check.Failure(
            "a.py", 3, "unregistered", "-: marker not in the registry: X1"
        ),
        ref_check.Failure("b.md", 2, "broken-link", "first: no such file"),
        ref_check.Failure("b.md", 2, "broken-link", "second: no such file"),
    ]
    assert ref_check.failure_ids(failures) == [
        "README.md:1:no-section:Install",
        "README.md:1:no-section:Usage",
        "a.py:3:unregistered",
        "b.md:2:broken-link:no-such-file:1",
        "b.md:2:broken-link:no-such-file:2",
    ]
    assert ref_check.failure_ids([]) == []


def test_main_turns_an_unexpected_exception_into_one_line_and_exit_two(
    tmp_path, monkeypatch, capsys
):
    """A bug in a check gives `ref_check: internal error: ...` and exit 2 (D15.1).

    arch: D15.1, I-52
    """

    def boom(root, config_path=None):
        raise RuntimeError("boom")

    monkeypatch.delenv("TRUEUP_DEBUG", raising=False)
    monkeypatch.setattr(ref_check, "run", boom)
    assert main(["--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith("ref_check: internal error: RuntimeError: boom")


def test_a_deep_python_file_is_unreadable_not_a_crash(tmp_path, monkeypatch):
    """`RecursionError` and `MemoryError` in a reader give an `unreadable` failure (D15.1).

    arch: D15.1
    """
    (tmp_path / "a.py").write_text('"""A."""\n', encoding="utf-8")
    for error in (RecursionError, MemoryError):

        def boom(path, error=error):
            raise error("too deep")

        monkeypatch.setitem(ref_check.READERS, "python", boom)
        report = run(tmp_path)
        assert [f.kind for f in report.failures] == ["unreadable"]


def test_a_deep_test_file_gives_no_test_functions(tmp_path, monkeypatch):
    """`_python_test_functions` returns `[]` for a file that overflows the parser (D15.1).

    arch: D15.1
    """
    path = tmp_path / "test_a.py"
    path.write_text("def test_a():\n    pass\n", encoding="utf-8")
    for error in (RecursionError, MemoryError):

        def boom(source, *args, error=error, **kwargs):
            raise error("too deep")

        monkeypatch.setattr(ref_check, "_decode_python", boom)
        assert ref_check._python_test_functions(path) == []
