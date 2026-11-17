"""The pipeline entry point for the checker tests.

The pipeline names this path, so the path stays. The tests come from
`trueup.ref_check` (D2.12) and this file defines none of its own (D1.7). A
direct run does the three legacy checks a, b and c, as the old file did (I-5).
"""

import sys
from pathlib import Path

# The repository holds the checker at `trueup/ref_check.py`. A direct run of
# this file puts `tests/refs/` on the path, not the root, so the line below
# adds the root first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trueup.ref_check import (
    test_cited_ids_exist_in_the_design,
    test_every_test_in_a_marked_file_has_a_marker,
    test_verification_claims_have_a_test,
)

if __name__ == "__main__":
    checks = [
        ("a", test_cited_ids_exist_in_the_design),
        ("b", test_every_test_in_a_marked_file_has_a_marker),
        ("c", test_verification_claims_have_a_test),
    ]
    for name, check in checks:
        check()
        print(f"check {name}: OK")
    print("arch refs: OK")
