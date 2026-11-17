"""Shared pytest fixtures for the checker tests."""

import shutil
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def materialise(case: str, dest: Path) -> Path:
    """Copy a fixture tree to a temporary directory, ready to run the checker on.

    The tree lives at `tests/fixtures/<case>/`. Each file there ends in
    `.txt`. This helper copies the tree to `dest` and drops that suffix from
    every copied file, so the result is a small repository the checker can
    read (D1.6).

    Args:
        case: The name of the directory under `tests/fixtures/`.
        dest: The directory to copy the tree into.

    Returns:
        The path to the materialised tree, which is `dest`.
    """
    source = FIXTURES_ROOT / case
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if path.is_dir():
            (dest / relative).mkdir(parents=True, exist_ok=True)
            continue
        target_name = relative.name
        if target_name.endswith(".txt"):
            target_name = target_name[: -len(".txt")]
        target = dest / relative.parent / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return dest


def _front_matter(page_id: str) -> str:
    """Return the front matter of D2.13 with the five fields for a reference page."""
    return (
        f"---\nid: {page_id}\ntype: reference\naudience: [maintainer]\n"
        "status: current\nlast_reviewed: 2026-09-22\n---\n\n"
    )


def _readme_files(root: Path) -> None:
    """Write a root `README.md` that obeys D2.14, a `LICENSE`, and the index it links to."""
    index = root / "docs" / "README.md"
    if not index.exists():
        index.parent.mkdir(exist_ok=True)
        index.write_text(_front_matter("docs-index"), encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo\n\nDemo is a tree. Read the [index](docs/README.md).\n\n"
        "## Install\n\nCopy it.\n\n## Usage\n\nRun it.\n\n## License\n\nMIT.\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")


def _excuse_tree(root: Path, cite: bool) -> Path:
    """Give the tree of the R-10 command: a claim of D1.1 and an open plan row for it.

    Args:
        root: The directory to write the tree into.
        cite: When true, the page declares D1.1 and a test cites it, so the
            claim is proved.

    Returns:
        `root`, with the design page, the plan, the README files, and the
        test, if any.
    """
    docs = root / "docs"
    docs.mkdir(parents=True)
    heading = "## D1.1 — a gate\n\n" if cite else ""
    (docs / "ARCHITECTURE.md").write_text(
        _front_matter("architecture") + heading + "## Verification\n\n- D1.1\n",
        encoding="utf-8",
    )
    (docs / "README.md").write_text(
        _front_matter("docs-index") + "[architecture](ARCHITECTURE.md)\n",
        encoding="utf-8",
    )
    (root / "PLAN.md").write_text("| T1 | D1.1 | open |\n", encoding="utf-8")
    _readme_files(root)
    if cite:
        tests = root / "tests"
        tests.mkdir()
        body = (
            "def test_gate():\n    " + '"""Gate.\n\n    ' + "arch" + ': D1.1\n    """\n'
        )
        (tests / "test_gate.py").write_text(body, encoding="utf-8")
    return root
