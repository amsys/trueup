#!/usr/bin/env bash
# Selftest for arch_refs.py. Build a fixture repo, run the three checks,
# then break one check at a time and confirm it fails with the right name.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/docs" "$T/tests"

cat > "$T/docs/ARCHITECTURE.md" <<'EOF'
# Design

## D1.1 — Gate

Text.

## D1.2 — Ledger

Text that names `## Verification` inline, as I-14 does in a real design.

## Invariants

- **I-1 Fail closed.** Text.

## Verification

Unit proves D1.1, D1.2 and I-1.
EOF

cat > "$T/PLAN.md" <<'EOF'
| id | rulings | what | files | done-check | tier | state |
|---|---|---|---|---|---|---|
| T1 | | D1.2: the ledger | src/x.py | pytest | S | open |
EOF

write_gate() {
  cat > "$T/tests/test_gate.py" <<'EOF'
def test_gate_closes():
    """arch: D1.1, I-1 - the gate fails closed."""
    assert True
EOF
}
cat > "$T/tests/test_plain.py" <<'EOF'
def test_no_marker_here():
    assert True
EOF
cp "$HERE/arch_refs.py" "$T/tests/test_arch_refs.py"

run() { (cd "$T" && python3 tests/test_arch_refs.py 2>&1); }
fail=0

# 1. The clean fixture passes. D1.2 is claimed but an open row owns it.
write_gate
if out="$(run)"; then echo "PASS: clean fixture: $out"
else echo "FAIL: clean fixture should pass:"; echo "$out"; fail=1; fi

# 2. An unknown id fails check a and names the test.
write_gate
printf '\ndef test_bad():\n    """arch: D9.9 - stale."""\n    assert True\n' >> "$T/tests/test_gate.py"
if out="$(run)"; then echo "FAIL: D9.9 should fail check a"; fail=1
elif grep -q 'test_gate.py:.* test_bad cites D9.9' <<<"$out"; then echo "PASS: check a names test_bad D9.9"
else echo "FAIL: check a wrong message:"; echo "$out"; fail=1; fi

# 3. An unmarked test in a marked file fails check b and names it.
write_gate
printf '\ndef test_unmarked():\n    assert True\n' >> "$T/tests/test_gate.py"
if out="$(run)"; then echo "FAIL: unmarked test should fail check b"; fail=1
elif grep -q 'test_gate.py:.* test_unmarked' <<<"$out"; then echo "PASS: check b names test_unmarked"
else echo "FAIL: check b wrong message:"; echo "$out"; fail=1; fi

# 4. Closing the row makes D1.2 owed: check c fails and names D1.2 only.
write_gate
sed -i 's/| open |/| done |/' "$T/PLAN.md"
if out="$(run)"; then echo "FAIL: closed row should make D1.2 owed"; fail=1
elif grep -q 'proved by no test: D1.2$' <<<"$out"; then echo "PASS: check c names D1.2"
else echo "FAIL: check c wrong message:"; echo "$out"; fail=1; fi

exit "$fail"
