---
id: comment-standard
type: reference
audience: [maintainer, agent]
status: current
last_reviewed: 2026-09-21
---

# The comment standard

This page is the contract for comments in this repository. A person reads this
page. A machine runs the lint configurations in `lint/` and the checker
`ref_check.py`. The two stay in step through two links:

- Each language section holds the lint command. The fixture tests read the
  command from this page, replace the placeholders, and run it.
- The registry table on this page is equal to the constant `REGISTRY` in the
  checker.

The design of the checker, the meridian check, is in
[the architecture](../ARCHITECTURE.md). The index of all pages is in
[the document index](../README.md).

## The three rules

1. A file starts with a header comment. The header gives the purpose. It does
   not give an author or a date.
2. A suppression gives a rule code and a reason. A blanket suppression fails.
3. A marker word comes from the registry table below. An unknown marker word
   fails.

## Placeholders

Each lint command uses these placeholders. A test replaces each one before it
runs the line.

| Placeholder | Meaning |
|---|---|
| `{files}` | The files to lint, separated by a space |
| `{root}` | The directory that holds the files, with a `ref_check.toml` that sets `comments = true` |
| `{crate}` | The directory of a Rust crate, which holds `Cargo.toml` |

## Python

**Docstring format.** PEP 257 with Google sections. ruff enforces it with the
`D` rules and `convention = "google"`.

**File header.** The module docstring is the first statement of the file.

**Content rule.** A docstring is mandatory for a module, a public class and a
public function. It is optional for a private helper. It must not restate the
signature.

```python
def pinned_version(law_key: str) -> str:
    """Give the version that the archive pins for one law key.

    Args:
        law_key: The key of the law, for example `acts/Income_Tax_Act/v13`.

    Returns:
        The version directory name.
    """
```

**Suppression form.** A second `#` leader carries the reason.

```python
import audit_hooks  # noqa: F401  # reason: the import registers the hooks
```

**Marker form.** A test cites design ids in its docstring. Production code
cites a target in a comment.

```python
def test_gate_closes():
    """The gate closes when the report holds one failure.

    arch: D1.4, I-9
    """

# ref: law/acts/Income_Tax_Act/v13/s.111
```

**Lint command.**

```sh lint:python
ruff check --config lint/ruff.toml {files}
python3 trueup refs --root {root}
```

## Rust

**Docstring format.** rustdoc. A public item gets `///`. An `unsafe` block
gets a `// SAFETY:` comment. A function with an `unsafe` contract gets a
`# Safety` section.

**File header.** A `//!` module comment is the first text of the file.
`missing_docs` enforces it.

**Content rule.** A doc comment is mandatory for a public item and for every
`unsafe` block. It is optional for a private item. It must not restate the
signature.

```rust
//! Parse one marker line.

/// Give the ids that one `arch` body names.
pub fn arch_ids(body: &str) -> Vec<String> {
    // SAFETY: the slice is inside the buffer, because `end` came from `len`.
    unsafe { buffer.get_unchecked(..end) }
}
```

**Suppression form.** Use `#[expect]` with a reason. clippy enforces the
reason with `allow_attributes_without_reason`.

```rust
#[expect(clippy::too_many_arguments, reason = "the C API fixes the shape")]
```

**Marker form.** A comment line, or a line of the module comment.

```rust
// ref: arch/D2.1
//! arch: D2.1
```

**Lint command.**

```sh lint:rust
cargo clippy --quiet --manifest-path {crate}/Cargo.toml -- -D missing_docs -D clippy::missing_safety_doc -D clippy::undocumented_unsafe_blocks -D clippy::allow_attributes_without_reason
```

## TypeScript

**Extensions.** The checker reads `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`,
`.mjs` and `.cjs` files with the TypeScript reader. The marker form below
applies to each of them.
A marker in a file with an unlisted extension is not read.

**Docstring format.** TSDoc. eslint enforces it with `jsdoc`
`flat/recommended-typescript-error`.

**File header.** A block comment at the top of the file gives the purpose.

**Content rule.** A doc comment is mandatory for an exported declaration. It
is optional for an internal one. It must not restate a type, because the
signature holds the type.

```typescript
/** Read the marker registry and give the closed word set. */
export function registryWords(): Set<string> {
  return new Set(Object.keys(REGISTRY));
}
```

**Suppression form.** A description follows the directive.
`@typescript-eslint/ban-ts-comment` uses `allow-with-description`, and
`eslint-comments/require-description` covers an eslint directive.

```typescript
// @ts-expect-error the vendor types lag one release
// eslint-disable-next-line no-console -- the CLI prints the report here
```

**Marker form.** A comment line.

```typescript
// ref: arch/D2.11
```

**Lint command.**

```sh lint:typescript
npx --prefix lint/ts eslint --config lint/ts/eslint.config.mjs {files}
```

## Shell

**Docstring format.** None. A shell file uses header comments, in the shape of
the Google shell style guide.

**File header.** After the optional `#!` line, the first line that is not
empty must be a whole-line comment. Check f enforces this rule, because
shellcheck does not have it.

**Content rule.** A header is mandatory for the file and for a function that
is not obvious. A function header names Globals, Args, Outputs and Returns.
An obvious line gets no comment.

```sh
#!/usr/bin/env bash
# Run the checker four times and compare the verdict with the old one.

# Copy the checker into the fixture.
# Globals: FIXTURE
# Args: $1 the source file
# Returns: 0 when the copy works
install_checker() {
  cp "$1" "${FIXTURE}/tests/test_arch_refs.py"
}
```

**Suppression form.** A second `#` leader carries the reason. Check f enforces
the reason.

```sh
# shellcheck disable=SC2086  # the word split is wanted
```

**Marker form.** A comment line.

```sh
# ref: arch/D2.9
```

**Lint command.**

```sh lint:shell
shellcheck {files}
python3 trueup refs --root {root}
```

## SQL

**Docstring format.** None. A SQL file uses a header comment.

**File header.** The first line that is not empty must be a whole-line `--`
comment that gives the purpose. Check f enforces this rule.

**Content rule.** A comment is mandatory for the file header and for a query
that is not obvious. It must not restate the SQL.

```sql
-- Give the taxable income of each company for one year.
-- The join drops a company with no return, which the report wants.
SELECT company_id, SUM(amount) AS taxable
FROM returns
GROUP BY company_id;
```

**Suppression form.** A `/* ... */` block comment carries the reason. It comes
on the same line, just before the `--` of the suppression. The `-- noqa`
comment stays bare, because sqlfluff reads all text after `noqa:` as the rule
list. Check f enforces the reason. A `-- noqa` with no block comment, or with
an empty one, fails. The form `-- noqa: LT01  -- reason` also fails.

```sql
SELECT a,b FROM t;  /* the vendor fixes this layout */ -- noqa: LT01
```

**Marker form.** A comment line.

```sql
-- ref: arch/D2.9
```

**Lint command.**

```sh lint:sql
uvx sqlfluff@4.3.0 lint --config lint/.sqlfluff {files}
python3 trueup refs --root {root}
```

## The marker registry

The registry is closed. No configuration adds a word to it. This table is
equal to `REGISTRY` in `ref_check.py`, row for row.

| Marker | Meaning | Checked by |
|---|---|---|
| `ref:` | a reference to a target | checks a, d |
| `arch:` | a test proves these design ids | checks a, b, c |
| `law:` | code implements this section of law | checks a, d |
| `SAFETY:` | why an `unsafe` block is sound (Rust) | clippy |
| `TODO:` | work that is owed, with a link | ruff `TD` rules in Python |

A marker is read only at the start of a comment, or at the start of a
docstring line. Text in the middle of a sentence is not a marker.
