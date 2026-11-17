"""The `house` profile gives the output of 720b5d2 on the messy fixture, except the allowed rows (arch: D16.9, I-48).

`tests/fixtures/messy-check-720b5d2.json` is the `check --json` output of
commit 720b5d2 on `tests/fixtures/messy`, with the volatile fields left
out (the root path, the tree identity, the tool table, the secret engine,
the counter and the contributors).
The commit has no profile. The test builds the same tree, commits a
`trueup.toml` with `profile = "house"`, and compares each part of the
output. `ALLOWED` lists every difference, and each one names the design id
that explains it. A difference that `ALLOWED` does not list fails the test.

The adopter trees cannot be rebuilt: the stored head of target-web is
gone. This one fixture is the whole of the I-48 evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FIXTURES_ROOT, materialise
from test_convergence import _commit, _git

from trueup import cli

BASELINE = FIXTURES_ROOT / "messy-check-720b5d2.json"
"""The stored output of 720b5d2."""

NEW_KEYS = {
    "profile": "D14.22 item 7 (the profile block)",
    "schema": "D15.3 (the JSON schema number)",
    "secret_engine": "D7.3 (the engine; the stored baseline leaves it out)",
    "secret_note": "D7.3 (why gitleaks stopped; D15.3 keeps the key)",
}
"""The top-level keys that the current output adds, each with its design id."""

ALLOWED_FIELD_CHANGES: dict[str, dict[str, str]] = {
    "scratch:tmp-draft.md": {
        "auto": "D15.9 (automatic needs a whole-stem name and house is proof-first)",
        "action": "D15.9 (the manual action text)",
    },
    "secret-file:.env": {
        "auto": "D15.10 (content decides the automatic flag)",
        "action": "D15.10 (the manual action text)",
    },
}
"""A finding that stays, with the fields that change and the design id of each."""

ALLOWED_LINE_ADDED = "D15.8 (every finding holds a `line` field)"
"""The one reason that a finding gains `line` (0 when there is none)."""

ALLOWED_REMOVED = {
    "duplicate:data2.csv": "D15.12 (a duplicate group needs 256 bytes)",
}
"""The finding ids that the current output drops, each with its design id."""

ALLOWED_ADDED = {
    "config:languages.typescript": "D15.6 (a target with a trueup.toml is adopted)",
}
"""The finding ids that the current output adds, each with its design id."""


def _run_house(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """Build the messy tree under `profile = "house"` and run `check --json`.

    Args:
        tmp_path: The directory to build the repository in.
        capsys: The pytest output capture.

    Returns:
        The parsed JSON report.
    """
    root = materialise("messy", tmp_path / "repo")
    (root / "trueup.toml").write_text('profile = "house"\n', encoding="utf-8")
    _git(root, "init", "-q")
    _commit(root, "messy under house")
    capsys.readouterr()
    cli.main(["check", "--root", str(root), "--json"])
    report = json.loads(capsys.readouterr().out)
    del report["tree"]  # the identity of the tree: the stored baseline has none
    for key in ("root", "tools", "counter", "contributors"):
        report["survey"].pop(key)  # volatile: the stored baseline has none
    return report


def _by_id(findings: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Index findings by id.

    Args:
        findings: The `findings` list of a report.

    Returns:
        Id to finding.
    """
    return {str(finding["id"]): finding for finding in findings}


def _assert_same_rows(
    old_rows: dict[str, dict[str, object]], new_rows: dict[str, dict[str, object]]
) -> None:
    """Check each shared row against the allow list.

    Args:
        old_rows: The stored rows by id.
        new_rows: The current rows by id.
    """
    for row_id in sorted(set(old_rows) & set(new_rows)):
        before, after = dict(old_rows[row_id]), dict(new_rows[row_id])
        assert after.pop("line") == 0, ALLOWED_LINE_ADDED
        changed = {
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        }
        assert changed == set(ALLOWED_FIELD_CHANGES.get(row_id, {})), row_id


def test_house_gives_the_output_of_720b5d2_except_the_allowed_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """I-48: under `house`, each difference to the 720b5d2 output is on the allow list.

    arch: D16.9, I-48
    """
    old = json.loads(BASELINE.read_text(encoding="utf-8"))
    new = _run_house(tmp_path, capsys)

    assert set(new) - set(old) == set(NEW_KEYS)
    assert set(old) <= set(new)

    old_rows, new_rows = _by_id(old["findings"]), _by_id(new["findings"])
    assert set(old_rows) - set(new_rows) == set(ALLOWED_REMOVED)
    assert set(new_rows) - set(old_rows) == set(ALLOWED_ADDED)
    _assert_same_rows(old_rows, new_rows)
    # The plan rows hold the same fields, and both plans keep the same id order.
    old_plan, new_plan = _by_id(old["plan"]), _by_id(new["plan"])
    assert set(old_plan) - set(new_plan) == set(ALLOWED_REMOVED)
    assert set(new_plan) - set(old_plan) == {
        i for i in ALLOWED_ADDED if new_rows[i]["severity"] in ("error", "warn")
    }
    _assert_same_rows(old_plan, new_plan)
    shared = set(old_plan) & set(new_plan)
    assert [i for i in old_plan if i in shared] == [i for i in new_plan if i in shared]
    assert [i for i in old_rows if i in set(new_rows)] == [
        i for i in new_rows if i in set(old_rows)
    ]
    assert new["kept"] == old["kept"]
    assert new["moves"] == old["moves"]
    assert new["repins"] == old["repins"]

    # D15.12 drops one file from the scored files and the config file adds one.
    assert new["score"]["categories"] == old["score"]["categories"]
    assert new["score"]["total"] == old["score"]["total"]
    assert new["score"]["tier"] == old["score"]["tier"]
    old_raw, new_raw = old["score"]["raw"], new["score"]["raw"]
    assert set(new_raw) == set(old_raw)
    assert {k for k in old_raw if old_raw[k] != new_raw[k]} == {"files"}
    assert new_raw["files"] == "2 of 7 files"

    # D15.26: the survey differs by the config file and the new `other_languages` key only.
    old_survey, new_survey = old["survey"], new["survey"]
    assert set(new_survey) - set(old_survey) == {"other_languages"}
    for key in old_survey:
        if key == "files":
            assert new_survey[key] == sorted([*old_survey[key], "trueup.toml"])
        else:
            assert new_survey[key] == old_survey[key], key
    assert new["profile"]["name"] == "house"
    assert new["profile"]["source"] == "target"
