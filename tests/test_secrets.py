"""Tests for `trueup.secrets`, the gitleaks secret engine, and its wiring into `check` (D7.3).

gitleaks may be absent. The tests put a fake `gitleaks` script first on
`PATH`; the fake writes a canned JSON report and records its arguments.
The one test that runs the real gitleaks skips when it is absent. Every
secret is assembled at run time; no file under `tests/` holds one (D7.3
rule 9).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from trueup import cli, hygiene, managed, report, secrets, survey as survey_mod
from trueup import config as config_mod
from trueup.config import Config
from trueup.findings import line_fingerprint

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "secrets"

_PLACEHOLDER = "__ACCESS_KEY_ID__"
"""The placeholder in `fixtures/secrets/fires/config.py` that a test fills."""

_KEY_LINE = 8
"""The line of `fires/config.py` that holds the placeholder."""


def _assembled_key() -> str:
    """Assemble an access key id that both secret engines match (D7.3 rule 9).

    Returns:
        A 20-character AWS-shaped access key id, built from parts so no
        source file holds it whole.
    """
    return "AKIA" + "QY7TM2PL" + "ZK4XW6RB"


def _git_init(root: Path) -> None:
    """Turn `root` into a small git repository with no commits.

    Args:
        root: The directory to initialise.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _tree(tmp_path: Path, case: str, with_key: bool) -> Path:
    """Copy one fixture tree into a fresh git repository under `tmp_path`.

    Args:
        tmp_path: The test's temporary directory.
        case: `"fires"` or `"silent"`.
        with_key: Put the assembled key in place of the placeholder.

    Returns:
        The repository root.
    """
    root = tmp_path / "repo"
    shutil.copytree(_FIXTURES_ROOT / case, root)
    if with_key:
        config = root / "config.py"
        text = config.read_text(encoding="utf-8")
        config.write_text(
            text.replace(_PLACEHOLDER, _assembled_key()), encoding="utf-8"
        )
    _git_init(root)
    return root


def _fake_gitleaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    report_data: object = (),
    exit_code: int = 0,
    raw: str | None = None,
    sleep_s: float = 0.0,
) -> Path:
    """Put a fake `gitleaks` first on `PATH`.

    The fake writes `report_data` as JSON (or `raw` as text) to the path
    after `--report-path`, appends its arguments, its working directory and
    the text of the file after `--config` (or `None`) and the files under
    its working directory to `calls.jsonl`
    beside it, and exits with `exit_code`.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: The pytest fixture that restores `PATH`.
        report_data: The report entries to write.
        exit_code: The exit code of the fake.
        raw: Text to write as the report instead of `report_data`.
        sleep_s: Seconds the fake waits before it writes the report.

    Returns:
        The path of `calls.jsonl`.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = bin_dir / "calls.jsonl"
    text = raw if raw is not None else json.dumps(list(report_data))
    script = bin_dir / "gitleaks"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        f"time.sleep({sleep_s!r})\n"
        "config = None\n"
        "if '--config' in sys.argv:\n"
        "    with open(sys.argv[sys.argv.index('--config') + 1]) as handle:\n"
        "        config = handle.read()\n"
        "files = sorted(os.path.relpath(os.path.join(d, f)) for d, _, fs in os.walk('.') for f in fs)\n"
        f"with open({str(calls)!r}, 'a') as handle:\n"
        "    handle.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'config': config, 'files': files}) + '\\n')\n"
        "path = sys.argv[sys.argv.index('--report-path') + 1]\n"
        "with open(path, 'w') as handle:\n"
        f"    handle.write({text!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return calls


def _calls(calls: Path) -> list[dict]:
    """Read the calls the fake gitleaks recorded.

    Args:
        calls: The `calls.jsonl` path of `_fake_gitleaks`.

    Returns:
        One mapping per call, in call order: `argv`, `cwd`, `config` and `files`.
    """
    if not calls.exists():
        return []
    return [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]


def _entry(file_name: str, line: int, **extra: object) -> dict[str, object]:
    """Build one gitleaks report entry that carries the matched text.

    Args:
        file_name: The `File` field.
        line: The `StartLine` field.
        **extra: More fields, for example `Commit` and `Fingerprint`.

    Returns:
        The entry. Its `Secret` and `Match` fields hold the assembled key,
        so a test can prove that trueup copies neither (I-30).
    """
    entry: dict[str, object] = {
        "File": file_name,
        "StartLine": line,
        "RuleID": "aws-access-token",
        "Secret": _assembled_key(),
        "Match": f'ACCESS_KEY_ID = "{_assembled_key()}"',
    }
    entry.update(extra)
    return entry


def _content_id(root: Path, path: str, line_number: int) -> str:
    """Give the `secret-content` id of one tracked line (D15.8).

    Args:
        root: The repository root.
        path: The repo-relative path.
        line_number: The 1-based line.

    Returns:
        `secret-content:<path>:<fp>`, `fp` from `findings.line_fingerprint`.
    """
    line = (root / path).read_bytes().splitlines()[line_number - 1]
    return f"secret-content:{path}:{line_fingerprint(path, line)}"


def test_scan_gives_none_when_gitleaks_is_not_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `gitleaks` on the path, `scan` returns `None` (D7.3 rule 1).

    arch: D7.3
    """
    root = _tree(tmp_path, "silent", with_key=False)
    survey = survey_mod.run(root)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert secrets.scan(root, survey, history=False) is None


def test_fake_gitleaks_maps_working_tree_entries_and_drops_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A working-tree report maps to `secret-content` ids; no secret text survives (D7.3 rules 2, 4).

    arch: D7.3, I-30, I-23, D15.3, D15.8, D15.20
    """
    root = _tree(tmp_path, "fires", with_key=False)
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "out.py").write_text("x = 1\n", encoding="utf-8")
    calls = _fake_gitleaks(
        tmp_path,
        monkeypatch,
        [_entry("config.py", _KEY_LINE), _entry("build/out.py", 3)],
    )
    run = secrets.scan(root, survey_mod.run(root), history=False)

    assert run is not None
    assert run.engine == "gitleaks"
    assert run.note == ""
    # D15.8: the id holds the line fingerprint; `line` holds the number.
    assert [finding.id for finding in run.findings] == [
        _content_id(root, "config.py", _KEY_LINE)
    ]
    finding = run.findings[0]
    assert finding.line == _KEY_LINE
    assert finding.rule == "secret-content"
    assert finding.path == "config.py"
    assert finding.evidence == f"config.py:{_KEY_LINE} matches aws-access-token"
    assert (finding.category, finding.severity, finding.auto) == (
        "security",
        "error",
        False,
    )
    assert _assembled_key() not in repr(run)

    (call,) = _calls(calls)
    argv = call["argv"]
    assert argv[:2] == ["dir", "."]
    assert "--redact" in argv
    # D14.22 item 2: every run passes the rendered config, from outside the root.
    config_path = Path(argv[argv.index("--config") + 1])
    assert root.resolve() not in config_path.resolve().parents
    # D15.20: gitleaks runs in a copy of the tracked files, never in the root.
    assert Path(call["cwd"]).resolve() != root.resolve()
    assert "build/out.py" not in call["files"]
    assert "config.py" in call["files"]
    report_path = Path(argv[argv.index("--report-path") + 1])
    assert root.resolve() not in report_path.resolve().parents


def test_fake_gitleaks_maps_history_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A history report maps to `secret-history` ids keyed by fingerprint (D7.3 rules 2, 4).

    arch: D7.3, I-30
    """
    root = _tree(tmp_path, "silent", with_key=False)
    commit = "0123456789abcdef0123456789abcdef01234567"
    fingerprint = f"{commit}:old/config.py:aws-access-token:4"
    calls = _fake_gitleaks(
        tmp_path,
        monkeypatch,
        [_entry("old/config.py", 4, Commit=commit, Fingerprint=fingerprint)],
    )
    run = secrets.scan(root, survey_mod.run(root), history=True)

    assert run is not None
    assert run.engine == "gitleaks"
    (finding,) = run.findings
    assert finding.id == f"secret-history:{fingerprint}"
    assert finding.rule == "secret-history"
    assert finding.path == "old/config.py"
    assert finding.evidence == (
        "old/config.py:4 matches aws-access-token in commit 0123456789ab"
    )
    assert (
        finding.action == "rotate the secret; a history rewrite is the owner's decision"
    )
    assert _assembled_key() not in repr(run)
    (call,) = _calls(calls)
    assert call["argv"][:2] == ["git", "."]
    assert "--redact" in call["argv"]


def test_scan_passes_the_rendered_config_from_a_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scan` renders the gitleaks config of the effective config outside the root and passes it; the target file is not read.

    D14.22 item 2 changes the D7.3 rule 2 expectation: the old managed
    `lint/gitleaks/gitleaks.toml` is a legacy path now (D14.8), so a file
    there does not reach gitleaks.

    arch: D14.22, D14.4, D14.5
    """
    root = _tree(tmp_path, "silent", with_key=False)
    legacy = root / "lint" / "gitleaks" / "gitleaks.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# the target's own text\n[extend]\n", encoding="utf-8")
    (root / "trueup.toml").write_text(
        'version = 1\nignore = ["vendor/**"]\n', encoding="utf-8"
    )
    calls = _fake_gitleaks(tmp_path, monkeypatch)
    secrets.scan(root, survey_mod.run(root), history=False)
    call = _calls(calls)[0]
    config_path = Path(call["argv"][call["argv"].index("--config") + 1])
    assert config_path.is_absolute()
    assert not config_path.is_relative_to(root)
    assert config_path.parent.name.startswith("trueup-gitleaks-")
    assert not config_path.exists()  # the temporary directory is gone
    loaded = config_mod.load(root)
    assert loaded is not None
    assert call["config"] == managed.render_gitleaks_config(loaded)
    assert "[[allowlists]]" in call["config"]
    assert "the target's own text" not in call["config"]
    assert "--redact" in call["argv"]


def test_scan_passes_the_default_config_when_the_root_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `trueup.toml`, `scan` passes the gitleaks config of the code defaults (D14.22 item 2).

    arch: D14.22, D14.4, D14.5
    """
    root = _tree(tmp_path, "silent", with_key=False)
    calls = _fake_gitleaks(tmp_path, monkeypatch)
    secrets.scan(root, survey_mod.run(root), history=True)
    call = _calls(calls)[0]
    assert call["config"] == managed.render_gitleaks_config(Config())
    assert "[[allowlists]]" not in call["config"]


@pytest.mark.parametrize(
    ("exit_code", "raw", "note"),
    [
        (1, None, "gitleaks failed: exit 1"),
        (0, '{"File": "x"}', "gitleaks failed: the report is not a JSON list"),
        (0, "not json", "gitleaks failed: the report is not a JSON list"),
        (
            0,
            '[{"RuleID": "x"}]',
            "gitleaks failed: a report entry has no File or StartLine",
        ),
    ],
)
def test_a_failing_gitleaks_gives_built_in_with_a_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    raw: str | None,
    note: str,
) -> None:
    """A non-zero exit or a bad report gives the `built-in` engine and a note (D7.3 rule 3).

    arch: D7.3
    """
    root = _tree(tmp_path, "silent", with_key=False)
    _fake_gitleaks(tmp_path, monkeypatch, exit_code=exit_code, raw=raw)
    run = secrets.scan(root, survey_mod.run(root), history=False)
    assert run == secrets.EngineRun(engine="built-in", note=note, findings=())


def test_a_gitleaks_timeout_gives_built_in_with_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gitleaks run past the time limit gives the `built-in` engine (D7.3 rule 3).

    arch: D7.3
    """
    root = _tree(tmp_path, "silent", with_key=False)
    _fake_gitleaks(tmp_path, monkeypatch, sleep_s=5.0)
    monkeypatch.setattr(secrets, "GITLEAKS_TIMEOUT_S", 1)
    run = secrets.scan(root, survey_mod.run(root), history=False)
    assert run == secrets.EngineRun(
        engine="built-in", note="gitleaks failed: timeout after 1 s", findings=()
    )


def test_collect_skips_the_built_in_row_when_gitleaks_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With gitleaks, the built-in `secret-content` row does not run; `secret-file` does (D7.3 rules 5, 5a).

    arch: D7.3
    """
    root = _tree(tmp_path, "fires", with_key=True)
    (root / ".env").write_text("NAME=value\n", encoding="utf-8")
    _fake_gitleaks(tmp_path, monkeypatch, [])
    run = report.collect(root)

    rules = {finding.rule for finding in run.findings}
    assert "secret-content" not in rules
    assert "secret-file:.env" in {finding.id for finding in run.findings}
    assert (run.secret_engine, run.secret_note) == ("gitleaks", "")


def test_collect_runs_the_built_in_row_when_gitleaks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed gitleaks run keeps the built-in `secret-content` row (D7.3 rules 3, 5a).

    arch: D7.3, D15.3, D15.8
    """
    root = _tree(tmp_path, "fires", with_key=True)
    _fake_gitleaks(tmp_path, monkeypatch, exit_code=2)
    run = report.collect(root)

    ids = {finding.id for finding in run.findings}
    assert _content_id(root, "config.py", _KEY_LINE) in ids
    assert (run.secret_engine, run.secret_note) == (
        "built-in",
        "gitleaks failed: exit 2",
    )


def test_the_report_names_the_engine_after_the_counter_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Markdown prints `secrets <engine>` after `counter`; JSON has `secret_engine` (D7.3 rule 6).

    arch: D7.3, I-30
    """
    root = _tree(tmp_path, "fires", with_key=True)
    _fake_gitleaks(tmp_path, monkeypatch, [_entry("config.py", _KEY_LINE)])
    capsys.readouterr()
    cli.main(["check", "--root", str(root)])
    markdown = capsys.readouterr().out
    lines = markdown.splitlines()
    counter_index = next(
        i for i, line in enumerate(lines) if line.startswith("counter ")
    )
    assert lines[counter_index + 1] == "secrets gitleaks"

    cli.main(["check", "--root", str(root), "--json"])
    printed = capsys.readouterr().out
    assert json.loads(printed)["secret_engine"] == "gitleaks"
    assert _assembled_key() not in markdown
    assert _assembled_key() not in printed


def test_the_report_prints_the_note_when_gitleaks_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed gitleaks run prints `secrets built-in (<note>)` (D7.3 rules 3, 6).

    arch: D7.3
    """
    root = _tree(tmp_path, "silent", with_key=False)
    _fake_gitleaks(tmp_path, monkeypatch, exit_code=1)
    capsys.readouterr()
    cli.main(["check", "--root", str(root)])
    assert "\nsecrets built-in (gitleaks failed: exit 1)\n" in capsys.readouterr().out


def test_baseline_and_check_baseline_scan_the_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`trueup baseline` and `check --baseline` use `gitleaks git`; the other runs use `dir` (D7.3 rule 6).

    arch: D7.3
    """
    root = _tree(tmp_path, "silent", with_key=False)
    calls = _fake_gitleaks(tmp_path, monkeypatch)
    assert cli.main(["baseline", "--root", str(root)]) == 0
    cli.main(["check", "--root", str(root), "--baseline"])
    cli.main(["check", "--root", str(root)])
    cli.main(["check", "--root", str(root), "--changed"])
    capsys.readouterr()
    assert [call["argv"][0] for call in _calls(calls)] == ["git", "git", "dir", "dir"]


def test_the_silent_fixture_gives_no_built_in_finding(tmp_path: Path) -> None:
    """The built-in row finds nothing in `fixtures/secrets/silent/` and the key in `fires/` (D7.3).

    arch: D7.3, D15.3, D15.8
    """
    silent = _tree(tmp_path / "a", "silent", with_key=False)
    fires = _tree(tmp_path / "b", "fires", with_key=True)
    silent_ids = [
        finding.id
        for finding in hygiene.hygiene_findings(survey_mod.run(silent))
        if finding.rule == "secret-content"
    ]
    fires_ids = [
        finding.id
        for finding in hygiene.hygiene_findings(survey_mod.run(fires))
        if finding.rule == "secret-content"
    ]
    assert silent_ids == []
    assert fires_ids == [_content_id(fires, "config.py", _KEY_LINE)]


def test_real_gitleaks_finds_the_assembled_key_and_hides_it(tmp_path: Path) -> None:
    """The real gitleaks gives one redacted finding in `fires/` and none in `silent/` (D7.3).

    arch: D7.3, I-30, D15.3, D15.8
    """
    if shutil.which("gitleaks") is None:
        pytest.skip("gitleaks is not on the path")
    fires = _tree(tmp_path / "a", "fires", with_key=True)
    silent = _tree(tmp_path / "b", "silent", with_key=False)

    fires_run = secrets.scan(fires, survey_mod.run(fires), history=False)
    silent_run = secrets.scan(silent, survey_mod.run(silent), history=False)

    assert fires_run is not None and fires_run.engine == "gitleaks"
    assert [finding.id for finding in fires_run.findings] == [
        _content_id(fires, "config.py", _KEY_LINE)
    ]
    assert _assembled_key() not in repr(fires_run)
    assert silent_run is not None and silent_run.findings == ()


def _scoped_repo(tmp_path: Path) -> Path:
    """Make a git repository of three tracked files and one untracked file (D14.14).

    Args:
        tmp_path: The test's temporary directory.

    Returns:
        The repository root. `a.py` and `b.py` are added to the index,
        `sub/c.py` too; `loose.py` is ignored.
    """
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    for name in ("a.py", "b.py", "sub/c.py", "loose.py"):
        (root / name).write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("loose.py\n", encoding="utf-8")
    _git_init(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    return root


def test_scoped_scan_runs_gitleaks_on_a_copy_of_the_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `only`, gitleaks runs in a directory that holds only the changed tracked files (D14.14).

    arch: D14.14, D15.3, D15.8
    """
    root = _scoped_repo(tmp_path)
    calls = _fake_gitleaks(
        tmp_path, monkeypatch, [_entry("sub/c.py", 1), _entry("b.py", 1)]
    )
    only = frozenset({"sub/c.py", "loose.py", "gone.py"})
    run = secrets.scan(root, survey_mod.run(root), history=False, only=only)

    recorded = _calls(calls)
    assert len(recorded) == 1
    assert recorded[0]["files"] == ["sub/c.py"]
    assert Path(recorded[0]["cwd"]) != root
    assert run is not None and run.engine == "gitleaks"
    assert [finding.id for finding in run.findings] == [
        _content_id(root, "b.py", 1),
        _content_id(root, "sub/c.py", 1),
    ]


def test_scoped_scan_with_no_changed_tracked_file_starts_no_gitleaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty scan set gives engine `gitleaks`, no findings and no process (D14.14).

    arch: D14.14
    """
    root = _scoped_repo(tmp_path)
    calls = _fake_gitleaks(tmp_path, monkeypatch, [_entry("a.py", 1)])
    survey = survey_mod.run(root)

    for only in (frozenset(), frozenset({"loose.py", "gone.py"})):
        run = secrets.scan(root, survey, history=False, only=only)
        assert run == secrets.EngineRun(engine="gitleaks", note="", findings=())
    assert _calls(calls) == []


def test_history_scan_ignores_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`history=True` with `only` still runs `gitleaks git` in `root` (D14.14).

    arch: D14.14
    """
    root = _scoped_repo(tmp_path)
    calls = _fake_gitleaks(tmp_path, monkeypatch, [])
    secrets.scan(root, survey_mod.run(root), history=True, only=frozenset())

    recorded = _calls(calls)
    assert len(recorded) == 1
    assert recorded[0]["argv"][0] == "git"
    assert Path(recorded[0]["cwd"]).resolve() == root.resolve()


def test_real_gitleaks_scoped_scan_matches_the_full_run_for_a_changed_file(
    tmp_path: Path,
) -> None:
    """A secret in a changed file gives the full run's finding; an unchanged file gives none (D14.14).

    arch: D14.14
    """
    if shutil.which("gitleaks") is None:
        pytest.skip("gitleaks is not on the path")
    root = tmp_path / "repo"
    root.mkdir()
    token = "ghp_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5"
    for name in ("a.py", "b.py"):
        (root / name).write_text(f'TOKEN = "{token}"\n', encoding="utf-8")
    _git_init(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    survey = survey_mod.run(root)

    full = secrets.scan(root, survey, history=False)
    scoped = secrets.scan(root, survey, history=False, only=frozenset({"a.py"}))

    assert full is not None and scoped is not None
    assert scoped.engine == "gitleaks"
    full_a = [f for f in full.findings if f.path == "a.py"]
    assert full_a, "the full run must find the token in a.py"
    assert list(scoped.findings) == full_a
    assert all(f.path != "b.py" for f in scoped.findings)


def test_real_gitleaks_scoped_scan_keeps_the_root_gitleaksignore(
    tmp_path: Path,
) -> None:
    """A scoped run applies the `.gitleaksignore` of the root, as a full run does (D14.14).

    arch: D14.14
    """
    if shutil.which("gitleaks") is None:
        pytest.skip("gitleaks is not on the path")
    root = tmp_path / "repo"
    root.mkdir()
    token = "ghp_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5"
    for name in ("a.py", "b.py"):
        (root / name).write_text(f'TOKEN = "{token}"\n', encoding="utf-8")
    _git_init(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    survey = survey_mod.run(root)
    full = secrets.scan(root, survey, history=False)
    assert full is not None
    assert any(f.path == "a.py" for f in full.findings)
    (root / ".gitleaksignore").write_text("a.py:github-pat:1\n", encoding="utf-8")

    full = secrets.scan(root, survey, history=False)
    scoped = secrets.scan(root, survey, history=False, only=frozenset({"a.py"}))

    assert full is not None and scoped is not None
    assert all(f.path != "a.py" for f in full.findings)
    assert list(scoped.findings) == []


def test_both_engines_give_the_same_id_for_one_secret_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gitleaks and the built-in row give one id for one line: the line fingerprint (D15.8).

    arch: D15.3, D15.8
    """
    root = _tree(tmp_path, "fires", with_key=True)
    built_in = [
        finding.id
        for finding in hygiene.hygiene_findings(survey_mod.run(root))
        if finding.rule == "secret-content"
    ]
    _fake_gitleaks(tmp_path, monkeypatch, [_entry("config.py", _KEY_LINE)])
    run = secrets.scan(root, survey_mod.run(root), history=False)
    assert run is not None
    assert [finding.id for finding in run.findings] == built_in


def test_two_gitleaks_entries_on_one_line_give_one_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two rules on one line give one finding whose evidence names both rules (D15.8).

    A `StartLine` past the end of the file cannot be read, so its id
    segment is `<rule>:<StartLine>`.

    arch: D15.3, D15.8
    """
    root = _tree(tmp_path, "fires", with_key=True)
    _fake_gitleaks(
        tmp_path,
        monkeypatch,
        [
            _entry("config.py", _KEY_LINE),
            _entry("config.py", _KEY_LINE, RuleID="generic-api-key"),
            _entry("config.py", 999),
        ],
    )
    run = secrets.scan(root, survey_mod.run(root), history=False)
    assert run is not None
    found = sorted(
        (finding.line, finding.id, finding.evidence) for finding in run.findings
    )
    assert found == [
        (
            _KEY_LINE,
            _content_id(root, "config.py", _KEY_LINE),
            f"config.py:{_KEY_LINE} matches aws-access-token, generic-api-key",
        ),
        (
            999,
            "secret-content:config.py:aws-access-token:999",
            "config.py:999 matches aws-access-token",
        ),
    ]


def test_full_scan_skips_a_symlink_that_leaves_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full-run copy leaves out a symlink to a file outside the root, and keeps one inside.

    arch: D15.20, D15.22
    """
    root = _tree(tmp_path, "silent", with_key=False)
    (tmp_path / "outside.txt").write_text("data\n", encoding="utf-8")
    (root / "out.txt").symlink_to(tmp_path / "outside.txt")
    (root / "zero.txt").symlink_to("/dev/zero")
    (root / "in.txt").symlink_to("config.py")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    calls = _fake_gitleaks(tmp_path, monkeypatch, [])
    run = secrets.scan(root, survey_mod.run(root), history=False)

    assert run is not None and run.engine == "gitleaks"
    (call,) = _calls(calls)
    assert "in.txt" in call["files"]
    assert "out.txt" not in call["files"]
    assert "zero.txt" not in call["files"]


def test_a_gitleaks_timeout_gives_a_secret_engine_row_and_the_built_in_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gitleaks timeout gives one `secret-engine` error finding; the built-in row still runs.

    arch: D15.20
    """
    root = _tree(tmp_path, "fires", with_key=True)
    _fake_gitleaks(tmp_path, monkeypatch, sleep_s=5.0)
    monkeypatch.setattr(secrets, "GITLEAKS_TIMEOUT_S", 1)
    run = report.collect(root)

    (row,) = [finding for finding in run.findings if finding.rule == "secret-engine"]
    assert row.id == "secret-engine:"
    assert (row.category, row.severity, row.path, row.auto) == (
        "security",
        "error",
        "",
        False,
    )
    assert row.evidence == "gitleaks failed: timeout after 1 s"
    assert row in run.plan
    assert run.secret_note == "gitleaks failed: timeout after 1 s"
    assert _content_id(root, "config.py", _KEY_LINE) in {
        finding.id for finding in run.findings
    }


def test_a_scoped_run_keeps_the_secret_engine_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scoped run keeps the repo-wide `secret-engine` row (D15.20).

    arch: D15.20
    """
    root = _tree(tmp_path, "silent", with_key=False)
    _fake_gitleaks(tmp_path, monkeypatch, exit_code=2)
    run = report.collect(root, only=frozenset({"config.py"}))

    assert [
        finding.id for finding in run.findings if finding.rule == "secret-engine"
    ] == ["secret-engine:"]


def test_a_working_gitleaks_gives_no_secret_engine_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run where gitleaks gives its report has no `secret-engine` row (D15.20).

    arch: D15.20
    """
    root = _tree(tmp_path, "silent", with_key=False)
    _fake_gitleaks(tmp_path, monkeypatch, [])
    run = report.collect(root)

    assert not [finding for finding in run.findings if finding.rule == "secret-engine"]


def _websocket_key_line(value: str) -> str:
    """Build one HTTP header line that holds `value` as a `Sec-WebSocket-Key`.

    Args:
        value: The header value.

    Returns:
        The line, with a line end.
    """
    return f"Sec-WebSocket-Key: {value}\n"


def test_real_gitleaks_drops_only_the_published_value(tmp_path: Path) -> None:
    """The allowlist drops the RFC 6455 sample key; another value of the same shape gives a row (I-59).

    arch: D16.5, I-59, I-30
    """
    if shutil.which("gitleaks") is None:
        pytest.skip("gitleaks is not on the path")
    root = tmp_path / "repo"
    root.mkdir()
    published = managed.PUBLISHED_TEST_VALUES[0]
    other = base64.b64encode(b"another nonce 16").decode("ascii")
    assert len(other) == len(published) and other != published
    (root / "published.txt").write_text(
        _websocket_key_line(published), encoding="utf-8"
    )
    (root / "other.txt").write_text(_websocket_key_line(other), encoding="utf-8")
    _git_init(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)

    run = secrets.scan(root, survey_mod.run(root), history=False)

    assert run is not None and run.engine == "gitleaks"
    assert [finding.id for finding in run.findings] == [
        _content_id(root, "other.txt", 1)
    ]
    assert published not in repr(run) and other not in repr(run)
