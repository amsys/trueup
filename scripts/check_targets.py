"""Run `trueup check --json` on the local target repositories and compare the plan counts.

The script runs the working copy of trueup, read-only, on each root that
`.state/targets/roots.txt` lists, one on each line (or on the roots given
as arguments). It counts the plan items
for each rule, writes the counts to `.state/targets/<date>.json` and
compares them to the last stored run. It prints each rule whose count
grew. Run it after every round: a new false-positive class on a real
target shows as a growth (purpose-and-state P1).

Usage: python3 scripts/check_targets.py [ROOT ...]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_STORE = _REPO / ".state" / "targets"

_ROOTS_FILE = _STORE / "roots.txt"
"""The local target list: one repository root on each line. The file is
not tracked, because the targets are repositories of this machine."""


def listed_roots() -> list[str]:
    """Read the target roots of `_ROOTS_FILE`.

    Returns:
        The lines that are not empty and do not start with `#`, in file
        order. An absent file gives an empty list.
    """
    if not _ROOTS_FILE.is_file():
        return []
    lines = _ROOTS_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def run_check(root: Path) -> dict[str, object]:
    """Run `check --json` on one root and count its plan items by rule.

    Args:
        root: The target repository root.

    Returns:
        A mapping with `rules` (rule name to plan item count), `moves`
        (the move plan length), `seconds` and, when `check` fails,
        `error` with the last line of its standard error, or, when the
        run used another secret engine than the configured one, the
        engine and its note (D15.20).
    """
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(_REPO / "trueup"), "check", "--root", str(root), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = round(time.perf_counter() - start, 2)
    if result.returncode not in (0, 1):
        lines = result.stderr.strip().splitlines() or ["no output"]
        return {"rules": {}, "moves": 0, "seconds": seconds, "error": lines[-1]}
    data = json.loads(result.stdout)
    # D15.20: a run that used another engine than the configured one is an
    # error, so a gitleaks timeout does not pass as a good run.
    configured = "gitleaks" if shutil.which("gitleaks") else "built-in"
    engine = data.get("secret_engine", "built-in")
    if engine != configured:
        note = data.get("secret_note", "")
        return {
            "rules": {},
            "moves": 0,
            "seconds": seconds,
            "error": f"secret engine {engine}: {note}",
        }
    rules = Counter(item["rule"] for item in data["plan"])
    return {
        "rules": dict(sorted(rules.items())),
        "moves": len(data.get("moves", [])),
        "seconds": seconds,
    }


def last_run() -> dict[str, dict[str, object]]:
    """Read the most recent stored run.

    Returns:
        The stored mapping of root to counts, or an empty mapping when no
        run is stored.
    """
    runs = sorted(_STORE.glob("*.json"))
    if not runs:
        return {}
    return json.loads(runs[-1].read_text(encoding="utf-8"))


def growths(
    before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]
) -> list[str]:
    """Give one line for each rule count that changed between two runs.

    Args:
        before: The stored run.
        after: This run.

    Returns:
        Lines of the form `root rule old -> new`, growths first. A root
        that is not in `before` gives no line. A root whose counts carry
        `error` in either run gives no line either: a failed check has no
        rules, so every rule would show as a change.
    """
    grew: list[str] = []
    fell: list[str] = []
    for root, counts in after.items():
        if root not in before:
            continue
        if "error" in before[root] or "error" in counts:
            continue
        old = before[root]["rules"]
        new = counts["rules"]
        for rule in sorted(set(old) | set(new)):
            a, b = old.get(rule, 0), new.get(rule, 0)
            if b > a:
                grew.append(f"GREW {root} {rule} {a} -> {b}")
            elif b < a:
                fell.append(f"fell {root} {rule} {a} -> {b}")
    return grew + fell


def main(argv: list[str]) -> int:
    """Run every target, store the counts and print the changes.

    For a root whose check failed, the stored file keeps the counts of the
    last run instead of the empty ones, when the last run has good counts
    for it. The printed lines and the exit code use the counts of this run.

    Args:
        argv: Target roots. Empty means the roots of `_ROOTS_FILE`.

    Returns:
        1 when a rule count grew or a check failed, else 0. 2 when no
        root is given and `_ROOTS_FILE` gives none.
    """
    names = argv or listed_roots()
    if not names:
        print(
            f"no target: give a root, or list the roots in {_ROOTS_FILE.relative_to(_REPO)}",
            file=sys.stderr,
        )
        return 2
    roots = [Path(arg).expanduser() for arg in names]
    present = [root for root in roots if (root / ".git").exists()]
    for root in roots:
        if root not in present:
            print(f"skip {root}: not a git repository")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(zip(map(str, present), pool.map(run_check, present)))
    for root, counts in results.items():
        line = ", ".join(f"{rule} {n}" for rule, n in counts["rules"].items())
        status = counts.get("error") or line or "plan empty"
        print(f"{root} ({counts['seconds']} s, {counts['moves']} moves): {status}")
    before = last_run()
    changes = growths(before, results)
    print("\n".join(changes) if changes else "no rule count changed")
    stored = dict(results)
    for root, counts in results.items():
        previous = before.get(root)
        if "error" in counts and previous is not None and "error" not in previous:
            stored[root] = previous
    _STORE.mkdir(parents=True, exist_ok=True)
    out = _STORE / f"{date.today().isoformat()}.json"
    out.write_text(
        json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"stored {out.relative_to(_REPO)}")
    failed = any("error" in counts for counts in results.values())
    return 1 if failed or any(c.startswith("GREW") for c in changes) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
