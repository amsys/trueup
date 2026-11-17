"""Integration test for the comment standard page and the registry link."""

from pathlib import Path

from trueup.ref_check import REGISTRY

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "reference" / "comment-standard.md"

LANGUAGES = ("Python", "Rust", "TypeScript", "Shell", "SQL")
"""The five languages of the standard, in the order that the page uses."""

PARTS = (
    "Docstring format.",
    "File header.",
    "Content rule.",
    "Suppression form.",
    "Marker form.",
    "Lint command.",
)
"""The six parts that D1.4 demands of each language section."""

REGISTRY_HEADING = "The marker registry"
"""The heading of the section that holds the registry table."""


def _sections(text: str) -> dict[str, str]:
    """Split the page into its level two sections.

    Args:
        text: The whole text of the page.

    Returns:
        A map of the heading text to the body that follows it.
    """
    sections: dict[str, str] = {}
    heading = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections[heading] = "\n".join(body)
            heading = line[3:].strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections[heading] = "\n".join(body)
    return sections


def _table_rows(body: str) -> list[tuple[str, ...]]:
    """Read the data rows of the one table in a section body.

    The header row and the separator row are dropped. Each cell keeps its
    text, without the surrounding spaces and without a code fence character.

    Args:
        body: The text of one section.

    Returns:
        One tuple of cells for each data row, in the order of the page.
    """
    rows: list[tuple[str, ...]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = tuple(
            cell.strip().strip("`") for cell in stripped.strip("|").split("|")
        )
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue
        rows.append(cells)
    return rows[1:]


def test_page_has_one_section_for_each_language():
    """Each of the five languages has a section with the six parts of D1.4.

    arch: D1.4, I-9
    """
    sections = _sections(PAGE.read_text(encoding="utf-8"))
    missing = [name for name in LANGUAGES if name not in sections]
    assert missing == [], f"the page has no section for: {missing}"
    for name in LANGUAGES:
        absent = [part for part in PARTS if part not in sections[name]]
        assert absent == [], f"the {name} section has no: {absent}"


def test_each_language_section_names_a_lint_command():
    """Each language section holds a tagged block with the lint command.

    arch: D1.4, I-9
    """
    sections = _sections(PAGE.read_text(encoding="utf-8"))
    for name in LANGUAGES:
        tag = f"```sh lint:{name.lower()}"
        body = sections.get(name, "")
        assert tag in body, f"the {name} section has no {tag} block"
        block = body.split(tag, 1)[1].split("```", 1)[0].strip()
        assert block, f"the {tag} block of the {name} section is empty"


def test_registry_table_equals_the_checker_registry():
    """The registry table is equal to REGISTRY, row for row and in order.

    arch: D1.4, I-9
    """
    sections = _sections(PAGE.read_text(encoding="utf-8"))
    assert REGISTRY_HEADING in sections, "the page has no registry section"
    rows = _table_rows(sections[REGISTRY_HEADING])
    found = [(cells[0].rstrip(":"), cells[1], cells[2]) for cells in rows]
    expected = [(word, meaning, gate) for word, (meaning, gate) in REGISTRY.items()]
    assert found == expected, f"the table is {found}, the checker holds {expected}"
