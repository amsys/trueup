"""The trueup package: a stdlib-only checker and fixer for repository hygiene.

Every submodule decides and writes only what has one right answer (survey,
findings, rule sets, managed files). The trueup skill (`skills/trueup/`)
is the part that asks a person and writes prose; this package never does.
"""

from __future__ import annotations

__version__ = "0.1.0a1"
