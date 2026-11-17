"""Tests for `scripts/check_targets.py`: the change lines, the stored runs and the main loop."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_targets.py"


def _load() -> ModuleType:
    """Load `scripts/check_targets.py` by path, since `scripts` is not a package.

    Returns:
        The loaded module.
    """
    spec = importlib.util.spec_from_file_location("check_targets", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load()


class _FixedDate(date):
    """A `date` whose `today` is always 2026-10-18."""

    @classmethod
    def today(cls) -> _FixedDate:
        """Give the pinned day.

        Returns:
            The date 2026-10-18.
        """
        return cls(2026, 10, 18)


def _counts(rules: dict[str, int], error: str | None = None) -> dict[str, object]:
    """Build the counts of one root, in the shape `run_check` gives.

    Args:
        rules: Rule name to plan item count.
        error: The error line of a failed check, or None.

    Returns:
        The counts mapping.
    """
    counts: dict[str, object] = {"rules": rules, "moves": 0, "seconds": 0.1}
    if error is not None:
        counts["error"] = error
    return counts


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module's repo and store at `tmp_path` and pin the date.

    Args:
        tmp_path: The pytest temporary directory of the test.
        monkeypatch: The pytest fixture that restores the module.

    Returns:
        The store directory. The fixture does not make it.
    """
    path = tmp_path / ".state" / "targets"
    monkeypatch.setattr(ct, "_REPO", tmp_path)
    monkeypatch.setattr(ct, "_STORE", path)
    monkeypatch.setattr(ct, "date", _FixedDate)
    return path


def _roots(tmp_path: Path, *names: str) -> list[Path]:
    """Make one git-like root per name under `tmp_path`.

    Args:
        tmp_path: The pytest temporary directory of the test.
        *names: The root directory names.

    Returns:
        The root paths, each with a `.git` directory.
    """
    paths = []
    for name in names:
        (tmp_path / name / ".git").mkdir(parents=True)
        paths.append(tmp_path / name)
    return paths


def _stub(
    monkeypatch: pytest.MonkeyPatch, results: dict[Path, dict[str, object]]
) -> list[Path]:
    """Replace `run_check` with a lookup in `results`.

    Args:
        monkeypatch: The pytest fixture that restores the module.
        results: Root to the counts the stub gives.

    Returns:
        The list the stub appends each run root to.
    """
    calls: list[Path] = []

    def fake(root: Path) -> dict[str, object]:
        calls.append(root)
        return results[root]

    monkeypatch.setattr(ct, "run_check", fake)
    return calls


def _write_run(store: Path, name: str, run: dict[str, dict[str, object]]) -> None:
    """Write one stored run to the store.

    Args:
        store: The store directory.
        name: The file stem, a date.
        run: Root to counts.
    """
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{name}.json").write_text(json.dumps(run), encoding="utf-8")


def _stored(store: Path) -> dict[str, dict[str, object]]:
    """Read the run `main` stored for the pinned date.

    Args:
        store: The store directory.

    Returns:
        The stored mapping of root to counts.
    """
    return json.loads((store / "2026-10-18.json").read_text(encoding="utf-8"))


def test_growths_growth_line() -> None:
    """A rule whose count rose gives a GREW line.

    arch: D15.20
    """
    lines = ct.growths({"r": _counts({"a": 1})}, {"r": _counts({"a": 3})})
    assert lines == ["GREW r a 1 -> 3"]


def test_growths_fall_line() -> None:
    """A rule whose count dropped gives a fell line.

    arch: D15.20
    """
    lines = ct.growths({"r": _counts({"a": 3})}, {"r": _counts({"a": 1})})
    assert lines == ["fell r a 3 -> 1"]


def test_growths_lists_growths_before_falls() -> None:
    """Growths come before falls, whatever the rule order.

    arch: D15.20
    """
    lines = ct.growths(
        {"r": _counts({"a": 5, "b": 1})}, {"r": _counts({"a": 2, "b": 4})}
    )
    assert lines == ["GREW r b 1 -> 4", "fell r a 5 -> 2"]


def test_growths_new_and_gone_rules() -> None:
    """A new rule grows from 0 and a gone rule falls to 0.

    arch: D15.20
    """
    lines = ct.growths({"r": _counts({"old": 2})}, {"r": _counts({"new": 1})})
    assert lines == ["GREW r new 0 -> 1", "fell r old 2 -> 0"]


def test_growths_root_not_in_before() -> None:
    """A root missing from the stored run gives no line.

    arch: D15.20
    """
    assert ct.growths({}, {"r": _counts({"a": 1})}) == []


def test_growths_no_change() -> None:
    """Equal counts give an empty list.

    arch: D15.20
    """
    assert ct.growths({"r": _counts({"a": 1})}, {"r": _counts({"a": 1})}) == []


def test_growths_skips_error_in_before() -> None:
    """A root that failed in the stored run gives no line.

    arch: D15.20
    """
    lines = ct.growths({"r": _counts({}, error="boom")}, {"r": _counts({"a": 2})})
    assert lines == []


def test_growths_skips_error_in_after() -> None:
    """A root that failed in this run gives no line.

    arch: D15.20
    """
    lines = ct.growths({"r": _counts({"a": 2})}, {"r": _counts({}, error="boom")})
    assert lines == []


def test_last_run_no_store(store: Path) -> None:
    """A missing store gives an empty mapping.

    arch: D15.20
    """
    assert ct.last_run() == {}


def test_last_run_no_json(store: Path) -> None:
    """A store with no json file gives an empty mapping.

    arch: D15.20
    """
    store.mkdir(parents=True)
    (store / "notes.txt").write_text("x", encoding="utf-8")
    assert ct.last_run() == {}


def test_last_run_latest_by_name(store: Path) -> None:
    """The file with the last name wins.

    arch: D15.20
    """
    _write_run(store, "2026-01-02", {"r": _counts({"a": 2})})
    _write_run(store, "2026-01-10", {"r": _counts({"a": 10})})
    _write_run(store, "2025-12-31", {"r": _counts({"a": 1})})
    assert ct.last_run() == {"r": _counts({"a": 10})}


def test_main_no_change(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Equal counts print the no-change line and return 0.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _write_run(store, "2026-01-01", {str(root): _counts({"a": 1})})
    _stub(monkeypatch, {root: _counts({"a": 1})})
    assert ct.main([str(root)]) == 0
    assert "no rule count changed" in capsys.readouterr().out


def test_main_growth(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A growth prints a GREW line and returns 1.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _write_run(store, "2026-01-01", {str(root): _counts({"a": 1})})
    _stub(monkeypatch, {root: _counts({"a": 2})})
    assert ct.main([str(root)]) == 1
    assert f"GREW {root} a 1 -> 2" in capsys.readouterr().out


def test_main_fall_only(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fall alone prints a fell line and returns 0.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _write_run(store, "2026-01-01", {str(root): _counts({"a": 2})})
    _stub(monkeypatch, {root: _counts({"a": 1})})
    assert ct.main([str(root)]) == 0
    assert f"fell {root} a 2 -> 1" in capsys.readouterr().out


def test_main_skips_non_git_root(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A root with no `.git` prints a skip line and is not run.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    plain = tmp_path / "plain"
    plain.mkdir()
    calls = _stub(monkeypatch, {root: _counts({"a": 1})})
    assert ct.main([str(root), str(plain)]) == 0
    assert f"skip {plain}: not a git repository" in capsys.readouterr().out
    assert calls == [root]


def test_main_failed_check(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed check prints its error and returns 1.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _stub(monkeypatch, {root: _counts({}, error="boom")})
    assert ct.main([str(root)]) == 1
    assert f"{root} (0.1 s, 0 moves): boom" in capsys.readouterr().out


def test_main_stores_counts(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The run is written to the dated file in the store.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _stub(monkeypatch, {root: _counts({"a": 1})})
    ct.main([str(root)])
    assert _stored(store) == {str(root): _counts({"a": 1})}
    assert "stored .state/targets/2026-10-18.json" in capsys.readouterr().out


def test_main_failed_root_keeps_previous_counts(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed root stores its previous counts, gives no change line and returns 1.

    arch: D15.20
    """
    good, bad = _roots(tmp_path, "good", "bad")
    previous = {str(good): _counts({"a": 1}), str(bad): _counts({"b": 4})}
    _write_run(store, "2026-01-01", previous)
    _stub(monkeypatch, {good: _counts({"a": 1}), bad: _counts({}, error="boom")})
    assert ct.main([str(good), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "no rule count changed" in out
    assert f"{bad} (0.1 s, 0 moves): boom" in out
    assert _stored(store) == previous


def test_main_failed_root_without_previous_counts(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed root with no previous counts stores the error counts.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _stub(monkeypatch, {root: _counts({}, error="boom")})
    assert ct.main([str(root)]) == 1
    assert _stored(store) == {str(root): _counts({}, error="boom")}


def test_main_failed_root_with_failed_previous_counts(
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed root whose previous counts also failed stores the new error counts.

    arch: D15.20
    """
    (root,) = _roots(tmp_path, "one")
    _write_run(store, "2026-01-01", {str(root): _counts({}, error="old")})
    _stub(monkeypatch, {root: _counts({}, error="new")})
    assert ct.main([str(root)]) == 1
    assert _stored(store) == {str(root): _counts({}, error="new")}


def _completed(payload: dict[str, object], code: int = 1) -> object:
    """Build the `CompletedProcess` of a stubbed `check --json` run.

    Args:
        payload: The JSON the stub prints.
        code: The exit code.

    Returns:
        The completed process.
    """
    return subprocess.CompletedProcess([], code, stdout=json.dumps(payload), stderr="")


def test_run_check_flags_a_run_that_used_another_secret_engine(
    store: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A run whose engine differs from the configured one is an error (D15.20).

    arch: D15.20
    """
    payload = {
        "plan": [],
        "moves": [],
        "secret_engine": "built-in",
        "secret_note": "gitleaks failed: timeout after 120 s",
    }
    monkeypatch.setattr(ct.subprocess, "run", lambda *a, **k: _completed(payload))
    monkeypatch.setattr(ct.shutil, "which", lambda name: "/bin/gitleaks")
    counts = ct.run_check(tmp_path)
    assert (
        counts["error"]
        == "secret engine built-in: gitleaks failed: timeout after 120 s"
    )

    monkeypatch.setattr(ct.shutil, "which", lambda name: None)
    assert "error" not in ct.run_check(tmp_path)

    monkeypatch.setattr(ct.shutil, "which", lambda name: "/bin/gitleaks")
    payload["secret_engine"] = "gitleaks"
    assert "error" not in ct.run_check(tmp_path)
