"""Tests for the re-pin entries and the `repin:` approval ids (arch: D12.6).

Each test builds a small git repository with a `trueup.toml` at tier T2
and `docs = "full"`, so the bundled `ref_check.py` runs its link check and
reports a stale pin. The tests then read `docrules.repins`, the report
keys and sections, and `apply --ids repin:<path>:<line>`.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from trueup import apply as apply_mod
from trueup import cli, docrules, ref_check, report
from trueup import config as config_mod

TODAY = date(2026, 10, 10)
"""The run date of every `apply` call here."""

OLD_PIN = "00000000"
"""The stale pin that the fixture page holds."""

REPIN_ID = "repin:docs/a.md:3"
"""The id of the one re-pin entry of the fixture."""

TARGET_PAGE = "# B\n\n## Sec\n\nText.\n"
"""The target page of the fixture link."""


def _git(root: Path, *args: str) -> None:
    """Run one git command in the fixture repository.

    Args:
        root: The repository root.
        *args: The git arguments.
    """
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repo(root: Path, page_a: str) -> Path:
    """Build and commit the fixture repository.

    Args:
        root: The directory to build in.
        page_a: The text of `docs/a.md`.

    Returns:
        The repository root, with a clean tree.
    """
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text(page_a, encoding="utf-8")
    (root / "docs" / "b.md").write_text(TARGET_PAGE, encoding="utf-8")
    (root / "trueup.toml").write_text(
        config_mod.render(config_mod.Config(tier="T2", docs="full")), encoding="utf-8"
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _stale(root: Path) -> Path:
    """Build the fixture with one pinned link whose section changed.

    Args:
        root: The directory to build in.

    Returns:
        The repository root.
    """
    return _repo(root, f'# A\n\nSee [b](b.md#sec "pin:{OLD_PIN}").\n')


def _new_pin() -> str:
    """Give the pin of the fixture target section now.

    Returns:
        Eight lower-case hex digits.
    """
    pin = ref_check.section_pin(TARGET_PAGE, "sec")
    assert pin is not None
    return pin


def test_repins_gives_one_entry_per_stale_pin(tmp_path: Path) -> None:
    """A `pinned section changed` finding with one pinned link gives one `Repin`.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    run = report.collect(root)
    assert "refcheck:docs/a.md:3:stale-pin" in {finding.id for finding in run.findings}
    entries = docrules.repins(root, run.findings)
    assert entries == (
        docrules.Repin(
            id=REPIN_ID,
            path="docs/a.md",
            line=3,
            target="b.md#sec",
            old_pin=OLD_PIN,
            new_pin=_new_pin(),
        ),
    )
    assert run.repins == list(entries)


def test_repins_skips_a_line_with_two_matching_links(tmp_path: Path) -> None:
    """Two pinned links with the same target on one line give no entry; the finding stays manual.

    arch: D12.6
    """
    line = f'[b](b.md#sec "pin:{OLD_PIN}") and [c](b.md#sec "pin:{OLD_PIN}")'
    root = _repo(tmp_path / "repo", f"# A\n\n{line}\n")
    run = report.collect(root)
    stale = [finding for finding in run.findings if finding.id.endswith(":stale-pin")]
    assert stale
    assert not any(finding.auto for finding in stale)
    assert docrules.repins(root, run.findings) == ()


def test_repins_skips_a_pin_that_does_not_apply(tmp_path: Path) -> None:
    """A `pin does not apply` failure is no re-pin entry: no section gives a pin.

    arch: D12.6
    """
    root = _repo(tmp_path / "repo", f'# A\n\nSee [b](b.md "pin:{OLD_PIN}").\n')
    run = report.collect(root)
    assert any(finding.id.endswith(":stale-pin") for finding in run.findings)
    assert docrules.repins(root, run.findings) == ()


def test_check_json_and_markdown_carry_the_repins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The JSON key `repins` and the section `## Re-pin plan (n)` list each entry.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["repins"] == [
        {
            "id": REPIN_ID,
            "path": "docs/a.md",
            "line": 3,
            "target": "b.md#sec",
            "old_pin": OLD_PIN,
            "new_pin": _new_pin(),
        }
    ]
    cli.main(["check", "--root", str(root)])
    markdown = capsys.readouterr().out
    assert "## Re-pin plan (1)" in markdown.splitlines()
    assert f"- [ ] {REPIN_ID} → pin:{_new_pin()} (b.md#sec)" in markdown.splitlines()


def test_check_json_repins_is_empty_with_no_stale_pin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no stale pin the JSON key `repins` is an empty list and no section prints.

    arch: D12.6
    """
    root = _repo(tmp_path / "repo", "# A\n\nSee [b](b.md#sec).\n")
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json"])
    assert json.loads(capsys.readouterr().out)["repins"] == []
    cli.main(["check", "--root", str(root)])
    assert "## Re-pin plan" not in capsys.readouterr().out


def test_apply_repin_id_writes_the_new_pin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An approved `repin:` id writes the new pin in that line only; the stale pin is gone.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    assert apply_mod.run(root, [REPIN_ID], False, [], [], today=TODAY) == 0
    text = (root / "docs" / "a.md").read_text(encoding="utf-8")
    assert text == f'# A\n\nSee [b](b.md#sec "pin:{_new_pin()}").\n'
    run = report.collect(root)
    assert not any(finding.id.endswith(":stale-pin") for finding in run.findings)
    assert run.repins == []


def test_apply_all_auto_does_not_repin(tmp_path: Path) -> None:
    """`--all-auto` takes the `auto` plan findings only; a repin needs its own id.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    before = (root / "docs" / "a.md").read_bytes()
    apply_mod.run(root, None, True, [], [], today=TODAY)
    assert (root / "docs" / "a.md").read_bytes() == before


def test_apply_unknown_repin_id_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `repin:` id that is not in the re-pin plan gives exit 2 and no write.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    before = (root / "docs" / "a.md").read_bytes()
    assert apply_mod.run(root, ["repin:docs/a.md:9"], False, [], [], today=TODAY) == 2
    assert "repin:docs/a.md:9" in capsys.readouterr().out
    assert (root / "docs" / "a.md").read_bytes() == before


def test_apply_repin_refuses_a_line_that_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A line that no longer holds the link with the old pin fails that id with exit 1 and a reason.

    arch: D12.6
    """
    root = _stale(tmp_path / "repo")
    entry = docrules.repins(root, report.collect(root).findings)[0]
    changed = '# A\n\nSee [b](b.md#sec "pin:11111111").\n'
    (root / "docs" / "a.md").write_text(changed, encoding="utf-8")
    capsys.readouterr()
    ctx = apply_mod._Context(root=root, protect=(), rendered={})
    assert apply_mod._apply_repins(ctx, [entry]) is True
    out = capsys.readouterr().out
    assert f"failed {REPIN_ID}:" in out
    assert (root / "docs" / "a.md").read_text(encoding="utf-8") == changed
    assert ctx.changed == []


def test_apply_repin_refuses_a_dirty_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repin page with uncommitted changes refuses the run (exit 2) without `--allow-dirty`.

    arch: D12.6, D12.2
    """
    root = _stale(tmp_path / "repo")
    page = root / "docs" / "a.md"
    page.write_text(page.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")
    before = page.read_bytes()
    assert apply_mod.run(root, [REPIN_ID], False, [], [], today=TODAY) == 2
    assert "trueup: docs/a.md has changes that are not committed" in (
        capsys.readouterr().err
    )
    assert page.read_bytes() == before


def test_saved_plan_loads_and_applies_the_repins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`load_saved_run` gives the `repins` of the file; `apply --plan --ids repin:...` writes the pin.

    arch: D12.6, D12.1
    """
    root = _stale(tmp_path / "repo")
    plan_file = tmp_path / "outside" / "plan.json"
    plan_file.parent.mkdir()
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json"])
    plan_file.write_text(capsys.readouterr().out, encoding="utf-8")
    saved = apply_mod.load_saved_run(plan_file)
    assert saved.repins == docrules.repins(root, report.collect(root).findings)
    assert all(isinstance(entry, docrules.Repin) for entry in saved.repins)
    assert (
        apply_mod.run(root, [REPIN_ID], False, [], [], today=TODAY, plan=plan_file) == 0
    )
    assert f"pin:{_new_pin()}" in (root / "docs" / "a.md").read_text(encoding="utf-8")


def test_saved_plan_with_a_bad_repins_entry_is_refused(tmp_path: Path) -> None:
    """A `repins` entry with a missing key or a wrong type is a bad plan file.

    arch: D12.6, D12.1
    """
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "tree": {"head": "x", "status": "y"},
                "plan": [],
                "findings": [],
                "moves": [],
                "repins": [{"id": REPIN_ID, "line": "3"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(config_mod.ConfigError, match="repins"):
        apply_mod.load_saved_run(plan_file)


def test_repin_through_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """A re-pin entry whose page is a symlink out of the root writes nothing.

    arch: D15.27
    """
    outside = tmp_path / "outside.md"
    text = "See [b](b.md#part) pin:aaaa.\n"
    outside.write_text(text, encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.md").symlink_to(outside)
    entry = docrules.Repin(
        id="repin:a.md:1",
        path="a.md",
        line=1,
        target="b.md#part",
        old_pin="aaaa",
        new_pin="bbbb",
    )
    ctx = apply_mod._Context(root=root, protect=(), rendered={})
    with pytest.raises(apply_mod.WriteRefused):
        apply_mod._repin_one(ctx, entry)
    assert outside.read_text(encoding="utf-8") == text
    assert ctx.changed == []
