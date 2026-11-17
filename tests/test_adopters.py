"""Round trip of the four adopter `trueup.toml` copies through `render`."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from trueup.config import _parse, load_target, render

_ROOT = Path(__file__).parent / "fixtures" / "adopters"
_NAMES = sorted(p.name for p in _ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize("name", _NAMES)
def test_adopter_file_survives_one_render(name: str) -> None:
    """A render keeps every value of the adopter file, and a second render is the same.

    The hand-written file keeps its own comments and key order, so the test
    compares parsed values, not bytes. `explicit` is part of the compare.

    arch: D14.15, D14.22
    arch: D14.23
    """
    directory = _ROOT / name
    cfg = load_target(directory)
    assert cfg is not None
    text = render(cfg)
    cfg2 = _parse(tomllib.loads(text), source=directory / "trueup.toml", layer="target")
    assert cfg2 == cfg
    assert render(cfg2) == text
