"""Integration test that the fixture trees stay inert on disk."""

from pathlib import Path

import pytest

from tests.refs.conftest import materialise

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "refs" / "fixtures"


def test_every_fixture_file_ends_in_txt():
    """Each file under `tests/refs/fixtures/` has a name that ends in `.txt` (D1.6, I-3).

    arch: D1.6, I-3
    """
    if not FIXTURES.is_dir():
        pytest.fail("T5: tests/refs/fixtures/ does not exist yet")
    files = [path for path in FIXTURES.rglob("*") if path.is_file()]
    if not files:
        pytest.fail("T5: tests/refs/fixtures/ holds no file yet")
    for path in files:
        assert path.suffix == ".txt", path


def test_materialise_strips_txt_suffix_and_leaves_source_untouched(tmp_path):
    """`materialise` copies a fixture tree and drops the `.txt` suffix (D1.6, I-3).

    The copy holds no `.txt` file, so a checker reading it selects the files
    by their real extension. The source tree under `tests/refs/fixtures/` is
    not changed by the copy.

    arch: D1.6, I-3
    """
    case = "design_target/check_c"
    source = FIXTURES / case
    before = sorted(p.relative_to(source) for p in source.rglob("*") if p.is_file())

    dest = materialise(case, tmp_path / "materialised")

    copied = [p for p in dest.rglob("*") if p.is_file()]
    assert copied, "materialise copied no file"
    for path in copied:
        assert not path.name.endswith(".txt"), path

    after = sorted(p.relative_to(source) for p in source.rglob("*") if p.is_file())
    assert before == after, "materialise changed the source fixture tree"
