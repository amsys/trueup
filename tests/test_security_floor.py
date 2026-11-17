"""Tests for the security floor section of the trueup reference page (D7.10)."""

import re
from pathlib import Path

from trueup import managed
from trueup.hygiene import _LOCK_PAIRS

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "reference" / "trueup.md"

HEADING = "## Security floor"
"""The level two heading of the section that D7.10 adds."""

TABLE_HEADER = "| Row | What it checks | OSPS Baseline Level 1 control |"
"""The header row of the one control table that D7.10 names."""

ROW_NAMES = (
    "`lockfile`",
    "`secret-file`",
    "`secret-content`",
    "`secret-history`",
    "CI action pins",
    "`osv-scanner` step",
    "SAST rule sets",
    "`health-security`",
    "install guard",
    "`platform:branch-protection`",
    "`platform:mfa`",
    "`platform:least-privilege`",
)
"""The first cell of each control table row, in the order of D7.10."""

BASELINE_VERSION = "v2026.08.28"
"""The OSPS Baseline version that the section cites."""

LEVEL_1_IDS = frozenset(
    {
        "OSPS-AC-01.01",
        "OSPS-AC-02.01",
        "OSPS-AC-03.01",
        "OSPS-AC-03.02",
        "OSPS-BR-01.01",
        "OSPS-BR-01.03",
        "OSPS-BR-03.01",
        "OSPS-BR-03.02",
        "OSPS-BR-07.01",
        "OSPS-DO-01.01",
        "OSPS-DO-02.01",
        "OSPS-GV-02.01",
        "OSPS-GV-03.01",
        "OSPS-LE-02.01",
        "OSPS-LE-02.02",
        "OSPS-LE-03.01",
        "OSPS-LE-03.02",
        "OSPS-QA-01.01",
        "OSPS-QA-01.02",
        "OSPS-QA-02.01",
        "OSPS-QA-04.01",
        "OSPS-QA-05.01",
        "OSPS-QA-05.02",
        "OSPS-VM-02.01",
    }
)
"""The Level 1 control ids of OSPS Baseline v2026.08.28, read from
https://baseline.openssf.org/versions/2026-08-28 on 2026-10-04."""

_CONTROL_ID = re.compile(r"OSPS-[A-Z]{2}-\d{2}\.\d{2}")

_PIN = re.compile(r"^\s*- uses: [\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40} # \S+$")
"""The I-32 form of one `uses:` line: owner, repo, optional path, SHA, tag comment."""


def _sections(text: str) -> list[tuple[str, str]]:
    """Split the page into its level two sections, in page order.

    Args:
        text: The whole text of the page.

    Returns:
        A list of `(heading line, body)` pairs. A fenced code block does
        not start a section.
    """
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading = line.rstrip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    return sections


def _section(heading: str) -> str:
    """Give the body of the one level two section with this heading.

    Args:
        heading: The heading line, with its `## ` prefix.

    Returns:
        The body text of the section.
    """
    matches = [
        body
        for head, body in _sections(PAGE.read_text(encoding="utf-8"))
        if head == heading
    ]
    assert len(matches) == 1, f"{heading!r} occurs {len(matches)} times"
    return matches[0]


def _cells(line: str) -> list[str]:
    """Split one Markdown table row into its stripped cells.

    Args:
        line: A row that starts and ends with `|`.

    Returns:
        The cell texts. A pipe with a backslash before it stays inside
        its cell.
    """
    inner = line.strip()[1:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", inner)]


def _table_after(body: str, header: str) -> list[list[str]]:
    """Read the data rows of the table that starts with this header row.

    Args:
        body: The text of one section.
        header: The exact header row.

    Returns:
        The cells of each data row, with the header and separator dropped.
    """
    lines = body.splitlines()
    start = lines.index(header)
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(_cells(line))
    return rows


def test_security_floor_section_follows_the_health_section() -> None:
    """The page has one `## Security floor` section, after the section that holds the health table.

    arch: D7.10
    """
    headings = [head for head, _ in _sections(PAGE.read_text(encoding="utf-8"))]
    assert headings.count(HEADING) == 1
    health = next(
        index
        for index, (_, body) in enumerate(_sections(PAGE.read_text(encoding="utf-8")))
        if "### Tier and health" in body
    )
    assert headings.index(HEADING) == health + 1


def test_security_floor_table_has_one_row_per_d7_10_row() -> None:
    """The control table has one row per row name of D7.10, in order, and each row cites a control.

    A control cell starts with a Level 1 control id of the cited Baseline
    version, or with `none at Level 1`. Every control id in the table has
    the OSPS shape.

    arch: D7.10
    """
    body = _section(HEADING)
    rows = _table_after(body, TABLE_HEADER)
    assert tuple(row[0] for row in rows) == ROW_NAMES
    for row in rows:
        assert len(row) == 3, row
        control = row[2]
        if control.startswith("none at Level 1"):
            continue
        first = _CONTROL_ID.match(control)
        assert first is not None, row
        assert first.group(0) in LEVEL_1_IDS, row


def test_security_floor_names_the_baseline_version_and_the_gaps() -> None:
    """The section names the Baseline version and date, and each security tool this machine did not verify.

    arch: D7.10
    """
    body = _section(HEADING)
    assert BASELINE_VERSION in body
    assert "https://baseline.openssf.org" in body
    gaps = body.split("### Gaps", 1)
    assert len(gaps) == 2, "no ### Gaps subsection"
    for tool in ("gitleaks", "osv-scanner", "gosec", "semgrep"):
        assert tool in gaps[1], tool


def test_security_floor_lockfile_table_matches_lock_pairs() -> None:
    """The lockfile pair table of the page holds the same pairs as `_LOCK_PAIRS`.

    arch: D7.10
    """
    body = _section(HEADING)
    rows = _table_after(body, "| Manifest | Lockfile names |")
    page_pairs = {
        row[0].strip("`"): tuple(re.findall(r"`([^`]+)`", row[1])) for row in rows
    }
    code_pairs = {manifest: names for manifest, names in _LOCK_PAIRS}
    code_pairs["pyproject.toml"] = (*code_pairs["pyproject.toml"], "pylock.<name>.toml")
    assert page_pairs == code_pairs


def test_security_floor_states_the_secret_engine_line_and_the_managed_files() -> None:
    """The page states the `secrets <engine>` report line, the gitleaks managed file and its hook.

    arch: D7.10
    """
    body = _section(HEADING)
    assert "secrets built-in" in body
    assert "secrets gitleaks" in body
    assert "lint/gitleaks/gitleaks.toml" in body
    assert "`gitleaks` pre-commit hook" in body


def test_reference_page_states_the_other_wave_b_facts() -> None:
    """The findings tables, the health table and the Hooks section carry the wave B facts.

    The slop table has the `lockfile` and `secret-history` rows, the health
    table says "when `public`" for `SECURITY.md` in all four tier columns
    (D7.6), and the Hooks section describes the install guard.

    arch: D7.10
    """
    findings = _section("## Findings")
    rule_cells = {
        _cells(line)[0] for line in findings.splitlines() if line.startswith("| `")
    }
    assert {"`lockfile`", "`secret-history`"} <= rule_cells
    security_row = next(
        _cells(line)
        for line in findings.splitlines()
        if line.startswith("| `SECURITY.md`")
    )
    assert security_row[1:] == ["when `public`"] * 4
    hooks = _section("## Hooks")
    assert "install guard" in hooks
    assert "permissionDecision" in hooks


def test_security_floor_ci_rows_hold_in_the_ci_template() -> None:
    """The workflow that `trueup template ci` prints meets the two CI rows of the control table.

    Each `uses:` line ends in `@<40 hex> # <tag>` (I-32), the workflow
    reads the repository only (`permissions: contents: read`), and it holds
    one pinned osv-scanner step.

    arch: D7.10, D14.22, D14.9
    """
    rows = {row[0] for row in _table_after(_section(HEADING), TABLE_HEADER)}
    assert {"CI action pins", "`osv-scanner` step"} <= rows
    text = managed.template_text("ci")
    uses = [line for line in text.splitlines() if "uses:" in line]
    assert uses
    for line in uses:
        assert _PIN.match(line), line
    assert "permissions:\n  contents: read\n" in text
    assert len([line for line in uses if "osv-scanner-action" in line]) == 1
