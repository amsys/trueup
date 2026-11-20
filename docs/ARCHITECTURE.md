---
id: architecture
type: reference
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-10-03
---

# trueup architecture

This page is the design of the whole plugin: the checker, the comment
standard page, the lint configurations and commands, and the hygiene and
setup rules. An anchor `D<n>.<m>` or `I-<n>` is stable: a later stage
refers to it by that id.

Sections D1 to D4 and invariants I-1 to I-12 are the design of the meridian
check, the reference checker that the archived meridian project built
before it merged into this repository on 2026-10-03; they keep their ids
and their text. Sections D5 and D6, and invariants I-13 to I-27, are
trueup's own. The tests of this repository cite these ids. The decision
numbers and the ids that start with Q or R stay in the archived meridian
repository's own design and brief. `trueup/ref_check.py` is the one
checker source (I-26); a change to it is made here.

## How to read this page

This page is a design record, and it is long. Do not read it from start
to end. To learn how to use trueup, read
[the trueup reference](reference/trueup.md) instead. Come here to look up
one section: a test, a comment or a different page cites a section by its
id, and the subject index below lists the sections of each subject.

- The sections are in the order in which they were designed, not in the
  order of the subjects. The work was done in rounds, and a section has
  the number of its round: D14.3 is a section of round 14.
- A later section can replace an earlier one. The earlier text stays,
  with a note that names the section in force. In the subject index, the
  section in force comes first.
- "The owner" is the maintainer of trueup. A "target" is a repository
  that trueup checks; names such as `target-rust` stand for private
  repositories of the maintainer.
- A path that starts with `.state/` is a private work record of the
  maintainer. git does not track that directory, so a clone does not have
  these files. The paths stay in the text as a record of the source.
- A commit id from before 2026-11-17 is in the maintainer's private
  history. The public history starts with one commit.

## Subject index

The ids are numbered by round, not by subject. This table gives the
sections of each subject. The section in force comes first, then the
older sections in round order.

| Subject | Sections |
|---|---|
| Checker (`ref_check.py`) | D1.1 to D1.7, D2.1 to D2.14, D4.1, D4.2, D8.1, D8.4, D8.7, D9.1 to D9.4 |
| Config (`trueup.toml`) | D14.1 to D14.4, D15.29, D5.3, D8.7, D9.1, D9.4, D12.9, D13.1, D13.2, D13.5 |
| Survey and tiers | D5.4, D6.14, D12.9, D12.10 |
| Findings: hygiene rows | D5.4, D6.12, D7.2, D10.3 to D10.5, D12.11, D13.2 |
| Findings: docs rows | D5.4, D6.5, D6.9, D6.15 |
| Page locator and move plan | D10.1, D10.2, D10.6, D10.7, D10.12, D12.11, D13.1 |
| Managed files and rule sets | D14.6 to D14.9, D15.28, D5.5, D5.6, D6.8, D6.13, D7.4, D7.5, D8.3, D9.5, D9.6, D12.7 to D12.9, D13.5, D13.6 |
| Apply, saved plan, approval | D15.27, D14.19, D5.6, D12.1 to D12.3, D12.6 |
| Report, score, SARIF | D5.7, D6.12, D10.8, D12.4 |
| Hooks | D14.10, D14.11, D15.7, D15.24, D15.31 to D15.35, D5.8, D6.2 to D6.4, D7.7, D7.8, D13.4 |
| Security | D6.10, D7.1 to D7.12, D14.12, D14.22 |
| Baseline and changed-file scope | D6.6, D6.7, D6.17, D14.14, D14.21 |
| Process: local targets | D6.16, D13.3, D14.15, D14.22 |
| Config layers and profiles | D14.1 to D14.4, D14.18, D14.19, D14.23 |
| Checker config, `trueup lint`, templates, managed set | D14.5 to D14.10, D14.20 |
| Hooks after round 14 | D14.10, D14.11, D14.21 |
| Tiers, defect fixes, hot spots | D14.12 to D14.14 |
| Round 14: universal config | D14.1 to D14.23 |
| Round 15: trust on a stranger's repository | D15.1 to D15.38 |

## D1.1 — The checker, `trueup/ref_check.py`

One Python file at `trueup/ref_check.py`. It uses the standard library only
and needs Python 3.11 or later (`tomllib`). It is the skill template of
decision 22: a different repository gets it by a file copy, in copy mode
(D9.1); in global mode, the default, the target runs `trueup refs`.

The file has three entry points with one behaviour:

- A command line (D2.3).
- pytest test functions (D2.12), for a copy with the name
  `tests/refs/test_arch_refs.py`.
- A direct run with no argument, `python3 <file>`, which the existing selftest
  uses (D4.4).

Inside, one pure function does the work: `run(root: Path) -> Report`. A
`Report` holds a sorted list of `Failure` records, a sorted list of `Edge`
records, the excused ids of check c (D2.8), and the configuration that the
run read (D4.1). The entry points only print a `Report` and set the exit
code. The checker has nine checks:

| Check | Kind of failure | Criterion | Switch |
|---|---|---|---|
| a. A cited id exists in its target | `unknown-id`, `no-target`, `malformed` | S14 | always on |
| b. Marked test files stay marked | `unmarked` | S15 | always on |
| c. A `## Verification` claim has a test | `unproved` | S16 | always on |
| d. A pinned law section did not change | `drift` | S17 | always on |
| e. A marker is in the registry | `unregistered` | S13 | `registry` |
| f. A suppression and a file have their comment | `no-reason`, `no-header` | S11, S12 | `comments` |
| g. A document link resolves, and its pin matches (D2.10) | `broken-link`, `stale-pin`, `malformed` | S22 | `links` |
| h. A document page obeys the page rules (D2.13) | `no-front-matter`, `bad-field`, `misplaced`, `unindexed`, `duplicate-id` | the page rules of `docs/README.md` | `layout` |
| i. The root `README.md` obeys the README rules (D2.14) | `no-readme`, `no-title`, `no-description`, `no-section`, `misordered`, `no-licence-file`, `badges-scattered`, `no-index-link` | the README rules of D2.14 | `readme` |

A file that the scanner cannot read gives `unreadable` from all checks.

Why one file: S20 runs the unchanged selftest, and that selftest copies one
file with the name `arch_refs.py` (D1.7). Why checks e to i have a switch:
S18 (D2.5, I-6).

## D1.2 — The scanner and the position rule

The scanner walks the root and gives each file to one reader by its
extension. No other property of a path selects or removes a file.

| Language | Extensions | Reader | Marker positions |
|---|---|---|---|
| Python | `.py` | `ast` and `tokenize` | a line of a module, class or function docstring; a comment token |
| Rust | `.rs` | line regex | a whole-line comment: `//`, `///`, `//!` |
| TypeScript | `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs` | line regex | a whole-line comment: `//` |
| Shell | `.sh`, `.bash` | line regex | a whole-line comment: `#` |
| SQL | `.sql` | line regex | a whole-line comment: `--` |

A whole-line comment is a line where the comment leader is the first text
that is not white space. In the four regex languages, a comment after code on
the same line is not a marker position. A correct rule for that case needs a
lexer, and decision 15 selects the regex. In the other regex readers, a
marker-shaped line inside a multi-line string gives a false failure. A
shell heredoc gives none since D15.18.

Each reader decodes a file as UTF-8. A byte order mark at the start is not
part of the text. The Python reader has one more rule, because the language
has it: a `coding:` line in the first two lines of the file selects the
encoding (PEP 263). No other reader has such a rule. A file that does not
decode gives `unreadable` (I-4), and this includes a binary file with a
listed extension.

The four JavaScript extensions use the TypeScript reader, and the language
name of such a file is `typescript`. A marker in a file with an unlisted
extension is not read, and the run reports nothing for it (I-1). The standard
page says so.

The scanner does not descend into a directory whose name starts with `.`, or
whose name is in the constant `SKIP_DIRS = {"node_modules", "vendor",
"graphify-out", "site-packages", "target", "venv"}`. This is the set of the
existing checker, plus `target` and `venv`. It holds code from other parties,
and build output that is not a copy of the source. `build` and `dist` are not
in it. They hold copies of the source, so a stale copy gives a failure line
that the user can see, and `build` is also a usual name for first-party code.
The scanner skips a name in the set at each depth, so first-party code must
not be in a directory with such a name. Nothing can add to it (I-2). The
scanner also does not enter a directory that holds its own `.git` entry:
that is another repository (D8.2).

A file is a test file when its name matches `test_*.py`. For the four regex
languages a file is a test file when a directory in its path has the name
`tests`, or when its stem ends in `_test`, `.test` or `.spec`.

Each marker belongs to a unit. In Python the unit is the module, or the
function or class whose line range holds the marker. In the regex languages
the unit is the file, and the unit name is `-`.

Markdown is not in the table. A Markdown file is never a source of markers. A
document refers to a design section with a link, and check g verifies that
link. A link can also carry a pin, the hash of the section that it cites
(D2.10). A pin is a property of the link, not a reference, so the run counts
no edge for it.

## D1.3 — Targets

A target is a name and a function `resolve(id) -> ok | failure`. There are two
targets. The table of targets is a constant in the checker. A new target is a
change to this design.

- `arch`: the ids in `docs/ARCHITECTURE.md` of the root (D2.8).
- `law`: the sections of a version of a document in a lawsmu archive (D2.7).
  The archive path comes from `ref_check.toml` (D2.5). With no path, each
  `law` reference fails with `no-target`.

A missing `docs/ARCHITECTURE.md` is not a failure by itself. Then each `arch`
reference fails with `no-target`, and check c has no claim to examine.

## D1.4 — The comment standard page

`docs/reference/comment-standard.md` is the one page of S11. It has one section
for each of the five languages and one section for the marker registry. Each
language section states: the docstring format (decision 5, Google for Python
by Q6), the file header rule (decision 6), the content rule with one example
(decision 7), the suppression form with its reason (D2.9), the marker form
(D2.1), and the lint command (D2.11).

The page is the source that people read. The lint configurations and the
checker are the source that machines run. Two links keep them in step: the
tests take the lint command from the page (D2.11), and the registry table of
the page must be equal to the constant in the checker (I-9).

## D1.5 — Lint configurations

Replaced by D14.6 (2026-10-16) for targets: `trueup lint` renders the
tool configs at run time. `lint/` stays the comment-standard kit of this
repository (D14.8).

The directory `lint/` holds one configuration for each linter. Decision 11
applies: the linter of the language does the work where it has a rule. The
checker does the work only where no linter has a rule.

| Language | Linter | Configuration | Rules that the standard needs |
|---|---|---|---|
| Python | ruff | `lint/ruff.toml` | `D` with `convention = "google"`, `PGH004`, `RUF100`, `TD002` to `TD005` |
| Rust | rustc and clippy | flags in the command | `missing_docs`, `clippy::missing_safety_doc`, `clippy::undocumented_unsafe_blocks`, `clippy::allow_attributes_without_reason` |
| TypeScript | eslint | `lint/ts/eslint.config.mjs`, `lint/ts/package.json` and its lock file | `jsdoc` `flat/recommended-typescript-error`, `@typescript-eslint/ban-ts-comment` with `allow-with-description`, `eslint-comments/require-description` |
| Shell | shellcheck | none | default rules |
| SQL | sqlfluff | `lint/.sqlfluff` | default rules, `dialect = ansi` |

Rules with no linter: the suppression reason for Python, shell and SQL, and
the file header for shell and SQL. Check f supplies them (D2.9).

eslint and its three plugins install from `lint/ts/package.json` with `npm
ci`. sqlfluff runs through `uvx` with a pinned version. Each needs the network
one time. A test that needs a tool which is absent fails. It does not skip.

## D1.6 — Layout, fixtures and tests

```
trueup/ref_check.py      the one checker source; stdlib only; no trueup import
trueup/cli.py            `refs` subcommand -> ref_check.main(argv)
trueup/config.py         [refs] path, default "ref_check.py"
trueup/managed.py        render(): writes the module bytes at cfg.refs_path
trueup/docrules.py       refcheck row runs trueup/ref_check.py
tests/refs/              the meridian check's 20 test files, conftest.py, fixtures/, legacy/
docs/ARCHITECTURE.md     one page: the meridian check's D1-D4 and failure ids, trueup D5-D6
docs/BRIEF.md            one brief, S1 to S24
```

A fixture tree is a small repository that is wrong on purpose. On disk each
file in it has `.txt` added to its name: `test_gate.py.txt`,
`ARCHITECTURE.md.txt`, `document.md.txt`. No reader of D1.2 and no linter
selects a `.txt` file, so a fixture on disk is inert. One test helper,
`materialise(case: str, dest: Path) -> Path`, copies a tree to a temporary
directory and removes the `.txt` suffix. A test then runs the checker or a
linter with that directory as the root.

Each test is a Python test with an `arch:` marker in its docstring (Q9). A
test docstring contains the text `arch:` only as its marker (D2.1, legacy
rule).

## D1.7 — The shim and the legacy selftest

The expand stage copied the existing checker to `tests/refs/test_arch_refs.py`. It
does checks a, b and c for this repository until the new checker exists. Then
that file becomes a shim: it imports the test functions of D2.12 from
`trueup.ref_check` and defines nothing. The path stays, because the pipeline names
it. There is one source, and the quoted marker in the old docstring goes away
with the old file.

`tests/refs/legacy/test-arch-refs.sh` is a copy of the selftest of the existing
checker. Its SHA-256 is
`84bf5d91df201500638b0823f84139e184b6505d6634ca803abe073fed87ce8e`. One test
verifies that hash, so a change to the copy is a test failure (S20). The
directory name is not `vendor`, so the scanner reads the file.

## D2.1 — Marker grammar

One grammar, with two aliases (Q2).

```
marker     = keyword ":" SP body [ SP "-" SP free-text ]
keyword    = "ref" | "arch" | "law"
ref body   = reference *( "," SP reference )
reference  = "arch/" arch-id  |  "law/" law-key "/s." section
arch body  = arch-id *( "," SP arch-id )  |  "none" [ SP "-" SP reason ]
law body   = law-key SP "s." section
arch-id    = "D" 1*DIGIT "." 1*DIGIT  |  "I-" 1*DIGIT
law-key    = doc-type "/" slug "/" version
doc-type   = 1*( a-z | "_" )           ; "acts" today
slug       = 1*( A-Z | a-z | 0-9 | "_" )
version    = "base" | "v" 1*DIGIT
section    = 1*DIGIT *( A-Z )
```

Examples: `ref: arch/D1.2, arch/I-1`, `arch: D1.2, I-1 - the gate closes`,
`ref: law/acts/Income_Tax_Act/v13/s.111`, `law: acts/Income_Tax_Act/v13 s.111`.

The anchored rule. At a marker position, a marker is recognised only when the
keyword is the first text of the docstring line or of the comment, after the
leader and white space. Text such as "use `ref:` here" in the middle of a
sentence is not a marker. A recognised `ref:` or `law:` marker whose body does
not parse fails with `malformed`.

The legacy rule. In a docstring of a test file (`test_*.py`), `arch:` is found
with the regex of the existing checker, `arch:\s*([^\n]+)` with no anchor and
no case, and the ids are all matches of `D\d+\.\d+|I-\d+` in the captured
text. A captured text that starts with `none` gives no id and marks the unit.
This is what decision 21 and S20 keep. One rule is new: a captured text with
no id that does not start with `none` fails with `malformed`.

The canonical form of a reference is the pair (`target`, `id`): (`arch`,
`D1.2`) or (`law`, `acts/Income_Tax_Act/v13/s.111`). The aliases give the same
pair. A body that repeats a pair gives that pair one time, so `arch: D1.2,
D1.2` is one reference: one record in the edge file (D2.6) and at most one
failure line (D2.4).

## D2.2 — Marker registry

The registry is one constant in the checker, `REGISTRY`, and one table on the
standard page (I-9). It is closed: no configuration adds to it.

| Marker | Meaning | Checked by |
|---|---|---|
| `ref:` | a reference to a target | checks a, d |
| `arch:` | a test proves these design ids | checks a, b, c |
| `law:` | code implements this section of law | checks a, d |
| `SAFETY:` | why an `unsafe` block is sound (Rust) | clippy |
| `TODO(<owner>):` | work that is owed, with a link | ruff `TD` rules in Python |

Check e reads comments, and for rule R2 also docstring lines. A comment is a
marker candidate by one of two rules:

- **R1, tag.** The first text of the comment matches
  `[A-Z][A-Z0-9_]+(\([^)]*\))?:`. Examples: `FIXME:`, `HACK:`, `NB:`. A tag
  whose word is a prefix of `[registry] local_tags` (D2.5), or such a prefix
  followed only by digits, is not a candidate. Example: with
  `local_tags = ["D"]`, `D:` and `D1:` are not candidates, and `DONE:` is one.
- **R2, reference shape.** The first text matches `[A-Za-z][A-Za-z0-9_-]*:` and
  the remainder parses as a `ref` body, an `arch` body with one id or more, or
  a `law` body. Examples: `refs: arch/D1.2`, `design: D1.2, I-1`.

A candidate whose word is not in `REGISTRY` fails with `unregistered`. R2 is
the rule that catches a misspelled keyword, which otherwise is a reference
that no check reads.

## D2.3 — Command line and exit codes

```text
python3 ref_check.py [--root DIR] [--edges FILE] [--config FILE]
```

- `--root DIR`: the repository to examine. Default: the first parent directory
  of the checker file that holds `ref_check.toml` or `docs/ARCHITECTURE.md`.
  If there is none, the second parent of the file, as in the existing checker.
- `--root=DIR` is the same flag as `--root DIR`. A root that is not a
  directory gives exit 2.
- `--edges FILE`: write the edge file (D2.6). With no flag, no file is written.
  `FILE` can be at any path, below the root or outside it. If the file
  exists, the checker replaces it. The user names the path, and I-8 limits
  the checker to that one file.
- `--config FILE`: read `FILE` as the configuration in place of
  `ROOT/ref_check.toml` (D8.1). `--config=FILE` is the same flag. A named
  file that is absent gives exit 2.
- `--help` or `-h`: print the usage text on standard output and exit 0. The
  first line of the text is `usage: python3 ref_check.py [--root DIR] [--edges
  FILE] [--config FILE]`.

Standard output gets one line for each failure (D2.4), in sorted order, then
one summary line: `ref_check: <n> failures, <m> references`. Exit 0 means no
failure. Exit 1 means one failure or more. Exit 2 means that the command line
or `ref_check.toml` is not valid, with one line on standard error.

After a run, standard error gets zero to three notice lines, in this
order. A notice is not a failure. It changes no exit code and no line on
standard output.

- `ref_check: checks off: <letters>`, when one or more check switches of D2.5
  are off. `<letters>` holds the letters of those checks from `e`, `f`, `g`,
  `h` and `i`, in that order, joined by `, `. Example: `ref_check: checks off:
  e, g`.
- `ref_check: excused by an open plan row: <ids>`, when check c has one or
  more excused ids (D2.8). `<ids>` holds those ids, sorted as text, joined by
  `, `.
- `ref_check: kept: <n>`, when `[keep] failures` of D2.5 names one or more
  failures of the run (D9.2). A kept failure is not printed and not
  counted.

There is no flag that selects checks, and no flag that removes paths.
`--config` names the file that holds the switches; it selects no check by
itself.

## D2.4 — Failure line format

```
<path>:<line>: [<kind>] <detail>
```

`<path>` is relative to the root, with `/`. `<line>` starts at 1. When the
failure has an id, the id is the last text of the line. The details are:

| Kind | Detail |
|---|---|
| `unknown-id` | `<unit> cites <id>` for `arch`; `<unit> cites <canonical law id>` for `law`. When the section is absent only in the newest version: `<unit>: section absent in <version>: <id>` |
| `no-target` | `<unit>: target <target> is not configured: <id>` |
| `malformed` | `<unit>: marker does not parse: <marker text>`. From check g: `pin has no link on its line: <pin title>`, on the line of the title |
| `unmarked` | `<unit>` |
| `unproved` | `claimed in ## Verification, proved by no test: <id>`. The path is `docs/ARCHITECTURE.md` and the line is the first line under `## Verification` that names the id |
| `drift` | `<unit>: section text changed in <version>: <id>` |
| `unregistered` | `<unit>: marker not in the registry: <word>` |
| `no-reason` | `<unit>: suppression has no reason: <suppression text>` |
| `no-header` | `file has no header comment` with line 1 |
| `broken-link` | `link does not resolve: <link target>` |
| `unreadable` | `file cannot be read: <error class>` |
| `no-front-matter` | `file has no front matter` with line 1 |
| `bad-field` | `field is absent: <key>` with line 1, or `value is not allowed: <key>: <value>` on the line of the key |
| `misplaced` | `page of type <type> is not below docs/<type>/` on the line of `type` |
| `unindexed` | `docs/README.md has no link to this page` with line 1 |
| `duplicate-id` | `id is also on <path>: <id>` on the line of `id` |
| `stale-pin` | `pinned section changed: <link target>` or `pin does not apply: <link target>`, on the line of the link |
| `no-readme` | `no README.md at the root` with line 1 |
| `no-title` | `line 1 is not a title` with line 1 |
| `no-description` | `no paragraph after the title` with line 1 |
| `no-section` | `section is absent: <name>` with line 1. `<name>` is `Install`, `Usage` or `License` |
| `misordered` | `License is not the last section` on the line of the heading |
| `no-licence-file` | `no LICENSE, LICENSE.md or COPYING at the root` with line 1 |
| `badges-scattered` | `badge is outside the block under the title` on the line of the badge |
| `no-index-link` | `no link to docs/README.md` with line 1 |

The five kinds from `no-front-matter` to `duplicate-id` are from check h
(D2.13). The owner added them on 2026-09-22 (R-14). `stale-pin` is from check
g (D2.10), which also gives the second `malformed` detail (R-16). The last
eight kinds are from check i (D2.14), and their path is
`README.md`. The owner added them on 2026-09-22 (R-16). No earlier row
changed.

For `no-reason`, `<unit>` is the unit of D1.2 that holds the suppression
line. A Python file that does not parse takes `module`. For `broken-link`,
`<line>` is the line that holds the link or the reference definition, and the
detail is the same for a target outside the root, an absent target and an
absent fragment.

Check c gives one line for each id. The lines for checks a, b and c match the
patterns that the legacy selftest greps: `test_gate.py:.* test_bad cites D9.9`,
`test_gate.py:.* test_unmarked` and `proved by no test: D1.2$`.

An identical failure appears one time in a report. The run removes
duplicates. For example, checks g and h both report a docs page that does
not decode.

## D2.5 — Configuration file, `ref_check.toml`

The file is optional and lives at the root. With `--config FILE`, the
checker reads `FILE` in its place (D8.1). Its full schema:

```toml
[checks]
registry = true     # check e
comments = true     # check f
links = true        # check g
layout = true       # check h, added by the owner on 2026-09-22 (R-14)
readme = true       # check i, added by the owner on 2026-09-22 (R-16)

[registry]
local_tags = ["D", "O"]         # tag prefixes that rule R1 does not report

[keep]
failures = ["docs/a.md:1:no-front-matter"]   # failure ids reported as kept (D9.2)

[scan]
ignore = ["docs/features/**"]   # globs no check reads, from trueup.toml ignore (I-2)

[targets.law]
archive = "../lawsmu/archive"   # relative to the root, or absolute
```

Each key is optional. A check switch that is absent is `false`. An unknown
table or key is an error with exit 2, so a misspelled switch cannot turn a
check off without a report. `[scan] ignore` is the one key for a path to
skip, and no other is to be added (I-2).

`ignore` is a list of globs, with the rules of the `trueup.toml` `ignore`
key: `*` matches in one path segment, `**` across segments, `?` one
character. No check reads a file whose path matches a glob: checks a to f
do not scan it, checks g and h do not read it as a page, and check i does
not run when a glob matches `README.md`. An unreadable directory that a
glob matches gives no `unreadable` failure. A value that is not a list of
non-empty strings is an error with exit 2. `apply` renders the key from
`trueup.toml` `ignore`, and from nothing else. A hand edit is a
`file-managed:ref_check.toml` drift finding, and the next `apply` writes the
rendered text again. The checker holds its own copy of the glob rules,
because it imports nothing from the package; a test keeps the copy equal to
the survey's rules.

`local_tags` is a list of prefixes. Each prefix is one or more uppercase
letters. An absent key gives no local tag. Any other value is an error with
exit 2. The key names tag words, not paths: the scan still reads each file
(I-2), and a local tag only stops rule R1 of D2.2 for that word.

`failures` is a list of failure ids (D9.2). A failure whose id is in the
list is kept: not printed, not counted, and no reason for exit 1. The key
names failure lines, not paths: the scan still reads each file (I-2).

This repository sets the five switches to `true` and sets no law archive.

## D2.6 — Edge file schema

One JSON document, UTF-8, keys in the order shown, two spaces of indent, a
final newline. It holds one record for each reference, which means one for
each (`target`, `id`) pair of each marker. `arch: none` gives no record.

```json
{
  "schema": 1,
  "edges": [
    {
      "source": "tests/test_gate.py",
      "line": 12,
      "unit": "test_gate_closes",
      "marker": "arch",
      "target": "arch",
      "id": "D1.2",
      "status": "ok"
    }
  ]
}
```

`marker` is the keyword as written. `status` is `ok` or the kind of the
failure of check a or d for that reference. The records are sorted by
`source`, `line`, `target`, `id`. The file has no time, no host name and no
absolute path (I-7). Failed references are in the file too: a graph needs the
edge that is wrong as much as the edge that is right.

## D2.7 — Law archive shape and the section hash

The `law` target reads this shape and nothing else:

```
<archive>/<doc-type>/<slug>/<version>/document.md
```

This is the lawsmu shape as observed. A reference resolves in these steps:

1. The pinned file is `<archive>/<law-key>/document.md`. If it is absent, the
   result is `unknown-id`.
2. A section heading is a line that matches `^### <section>\. `, with the
   section number compared as exact text. If no line matches in the pinned
   file, the result is `unknown-id`.
3. The section text starts at the heading line. It ends before the next line
   that matches `^#{1,3} `, or at the end of the file.
4. The section hash is the SHA-256 of the section text after this
   normalisation: decode as UTF-8, replace each run of white space with one
   space, remove white space at the two ends. A change of line wrap between
   two extractions is thus not a change of text.
5. The order of versions is `base` first, then `v<N>` by the integer `N`. The
   newest version is the last directory of `<archive>/<doc-type>/<slug>/` in
   that order that holds a `document.md`.

A section number can repeat in one document. In `Income_Tax_Act/v13`, 37
numbers repeat, because each Schedule starts its numbers at 1 again. For each
of the 37, the first heading is the one in the main body of the Act. The rule
is thus: the first line that matches is the section. An item of a Schedule
has no id (non-goal 3 of the brief applies in the same way).

The checker calculates the hash. It does not read a hash from the archive.
This definition is the "necessary shape" of Q7: when the lawsmu archiver adds
a `content_sha256` for each section, it uses steps 2 to 4, and a later design
change can let the checker read it. That change is outside this repository.

## D2.8 — Design target shape

The parse rules are those of the existing checker, regex for regex:

- A design id is declared by a heading line `^## (D\d+\.\d+) ` or by a list
  line `^- \*\*(I-\d+)\b` in `docs/ARCHITECTURE.md`.
- The claims are all matches of `D\d+\.\d+|I-\d+` in the text between the line
  `## Verification` and the next `## ` heading or the end of the file.
- An id has an open plan row when a line of `PLAN.md` matches `\|\s*open\s*\|`
  and contains the id. A missing `PLAN.md` gives no open row.
- Check c: `owed = claims - cited - open`. `cited` holds the `arch` ids of all
  references whose source is a test file (D1.2).
- An excused id is an id in `claims - cited` that is also in `open`. It is
  not a failure. The run names the excused ids in one notice line on standard
  error (D2.3), so a reader can tell a proved claim from an excused one. An
  id that a test cites is proved, not excused.
- Check b: in a `test_*.py` file, if the module docstring or the docstring of
  one `test_*` function holds a reference marker or `arch: none`, then each
  `test_*` function must hold one, unless the module docstring holds one.
  Functions and async functions at all depths count, as `ast.walk` finds
  them. Check b applies to Python test files only (Q3).

## D2.9 — Suppression reason and file header

Check f has two rules, for the languages where no linter has the rule.

Suppression reason, for Python, shell and SQL. For Python and shell the reason
is the text after a second comment leader on the same line. For SQL the reason
is the text of a `/* ... */` block comment on the same line, before the `--` of
the suppression. sqlfluff reads all text after `noqa:` as the rule list, so a
second leader there stops the suppression:

| Language | Suppression, regex on the comment text | Form that passes |
|---|---|---|
| Python | `noqa\b(:\s*[A-Z]+[0-9]+(\s*,\s*[A-Z]+[0-9]+)*)?` | `# noqa: F401  # reason: kept for the side effect` |
| Shell | `shellcheck\s+disable=\S+` | `# shellcheck disable=SC2086  # the word split is wanted` |
| SQL | `noqa\b(:\s*[A-Za-z0-9_.,\s]+?)?` | `SELECT a,b FROM t;  /* the vendor fixes this layout */ -- noqa: LT01` |

A Python or shell suppression with no second leader, or with no text after it,
fails with `no-reason`. A SQL suppression with no block comment before it on
the line, or with an empty one, fails with `no-reason`. For Rust and TypeScript
the linters of D1.5 have the rule.

File header, for shell and SQL. After an optional `#!` line, the first line
that is not empty must be a whole-line comment. If it is not, the file fails
with `no-header`. For Python, Rust and TypeScript the linters have the rule
(`D100`, `missing_docs`, `jsdoc/require-file-overview`).

## D2.10 — Document link rules

Check g reads each `*.md` file under `docs/` of the root, with the walk of
D1.2. It also reads each `*.md` file at depth 0 of the root, for example
`README.md` and `PLAN.md`, but not a name that starts with `.` (R-16).

- It ignores fenced code blocks and inline code spans. An example link in a
  code span is thus not a link.
- A link is `[text](target)` or a reference definition `[label]: target`. The
  destination is the text inside `<...>`, or else the text before the first
  white space. A title, such as `"The title"`, is not part of it. A
  destination that starts with a URL scheme (`[a-z][a-z0-9+.-]*:`) is not
  examined.
- The fragment is the text after the first `#`. The path part is the text
  before the first `?` or `#`. A query string, such as `?preset=a&set=b`,
  is thus not part of the path. The failure detail keeps it.
- The checker decodes percent-encoding in the path part and in the fragment.
  The path part resolves relative to the file that holds the link. It must be
  a file or a directory inside the root.
- A fragment must be equal to a heading slug of the target file, or of the
  same file when the path part is empty. The slug is the GitHub algorithm:
  replace each inline link or image with its text, remove each HTML tag, make
  the heading text lower case, remove each character that is not a letter or
  a digit of any script, a space, `-` or `_`, replace each space with `-`, and
  add `-1`, `-2` for a slug that repeats. Headings in fenced code blocks do
  not count. A fragment is examined only when the target is a `.md` file.
- The failure detail gives the destination as written, with no title.

A link can carry a pin in its title: `[text](<path>#<fragment> "pin:<hex>")`,
or the same title on a reference definition. A title that does not start
with `pin:` is not a pin. A link with no pin has no pin rule (S18). The pin
rule runs only on a link that resolves; else the link gives `broken-link`
only.

A pinned link and its title stay on one line. Check g reads one line at a
time, so a title on the next line belongs to no link. The check fails
closed (I-4): a pin title in quotes that no link on its line owns gives
`malformed`, with the detail `pin has no link on its line: <pin title>`, on
the line of the title. A title inside a fenced block or a code span is not a
pin title.

1. **Applies.** The target is a `.md` file, the link has a fragment, and
   the text after `pin:` is eight lower-case hex digits. If not, the link
   fails with `stale-pin` and the detail `pin does not apply: <link
   target>`.
2. **Section.** The section starts at the heading line whose slug is the
   fragment. It ends before the next heading line of the same or a higher
   level, or at the end of the file. A heading of a lower level stays
   inside. A heading in a fenced code block does not end the section, but
   its text is part of the section.
3. **Hash.** The section hash is that of D2.7 step 4: the SHA-256 of the
   section text with each run of white space replaced by one space, and
   white space removed at the two ends. The pin is the first eight hex
   digits of it.
4. **Compare.** A pin that is not equal to the section hash fails with
   `stale-pin` and the detail `pinned section changed: <link target>`.

The line of a `stale-pin` failure is the line of the link. The checker never
writes a pin (I-8). A person reads the changed section, corrects the text
near the link, and writes the new pin. The function `section_pin(text,
fragment)` of the checker gives the pin of one section of a file text, or
`None` when no heading has that slug.

## D2.11 — Lint commands

On the standard page, each language section holds one fenced code block with
the info string `sh lint:<language>`, where `<language>` is `python`, `rust`,
`typescript`, `shell` or `sql`. Each line of the block is one command, run
from the root. `{files}` is the placeholder for the files to lint, and
`{crate}` is the placeholder for the directory of a Rust crate. The fixture
tests read these blocks, replace the placeholders and run each line. A
fixture fails the lint command when one line exits non-zero.

The commands:

- python: `ruff check --config lint/ruff.toml {files}` and
  `python3 ref_check.py --root {root}`
- rust: `cargo clippy --quiet --manifest-path {crate}/Cargo.toml -- -D
  missing_docs -D clippy::missing_safety_doc -D
  clippy::undocumented_unsafe_blocks -D clippy::allow_attributes_without_reason`
- typescript: `npx --prefix lint/ts eslint --config lint/ts/eslint.config.mjs
  {files}`
- shell: `shellcheck {files}` and `python3 ref_check.py --root {root}`
- sql: `uvx sqlfluff@<pinned version> lint --config lint/.sqlfluff {files}` and
  `python3 ref_check.py --root {root}`

`{root}` is the directory that holds the files, with a `ref_check.toml` that
sets `comments = true`.

## D2.12 — pytest entry points

The checker defines these functions at module level. Each one calls
`run(ROOT)`, where `ROOT` is the default root of D2.3, and asserts that the
report has no failure of its kinds. The assert message holds the failure
lines of D2.4.

```python
def test_cited_ids_exist_in_the_design(): ...           # unknown-id, no-target, malformed
def test_every_test_in_a_marked_file_has_a_marker(): ... # unmarked
def test_verification_claims_have_a_test(): ...          # unproved
def test_pinned_law_sections_did_not_change(): ...       # drift
def test_markers_are_in_the_registry(): ...              # unregistered
def test_suppressions_and_files_have_their_comment(): ...# no-reason, no-header
def test_document_links_resolve(): ...                   # broken-link, stale-pin
def test_documents_follow_the_layout(): ...              # the five kinds of check h
def test_readme_follows_the_standard(): ...              # the eight kinds of check i
def test_each_source_file_can_be_read(): ...             # unreadable
```

The first three names are the names of the existing checker. `run` is
calculated one time for each process.

## D2.13 — Document layout (check h)

Check h enforces the page rules of `docs/README.md`. Its switch is
`[checks] layout`. The switch is off when absent (S18). Check h reads each
`*.md` file under `docs/` of the root, with the walk of D1.2. The index is
`docs/README.md`. The pipeline pages are `docs/BRIEF.md` and
`docs/ARCHITECTURE.md`.

1. **Front matter.** Line 1 is `---`, and a later line `---` closes the
   block. Each line between is `<key>: <value>`. If not, the file fails with
   `no-front-matter` on line 1, and the rules 2 to 5 skip it.
2. **Fields.** `id`, `type`, `audience`, `status` and `last_reviewed` are
   present. `id` matches `[a-z0-9]+(-[a-z0-9]+)*`. `type` is `tutorial`,
   `how-to`, `reference` or `explanation`. `audience` is `[<a>, ...]` with
   one value or more of `maintainer`, `agent`, `user`. `status` is `draft`,
   `current` or `superseded`. `last_reviewed` is a real date `YYYY-MM-DD`.
   The check does not examine other keys. A failure is `bad-field`, on the
   line of the key, or on line 1 for an absent key.
3. **Directory.** A page other than the index and the two pipeline pages is
   below `docs/<type>/`, where `<type>` is the value of its `type` field. A
   failure is `misplaced`, on the line of `type`.
4. **Index.** The index holds a link (D2.10) that resolves to each page
   other than itself. A failure is `unindexed`, on line 1 of the page.
5. **Unique id.** An `id` value is on one page only. Each page after the
   first, in path order, fails with `duplicate-id` on the line of `id`.

The records of a pipeline run are not pages. They are in `features/` at the
root, outside `docs/` (R-13). No directory below `docs/` is out of check h
(I-2).

The detail of each kind, for the new rows of D2.4:

| Kind | Detail |
|---|---|
| `no-front-matter` | `file has no front matter` |
| `bad-field` | `field is absent: <key>` or `value is not allowed: <key>: <value>` |
| `misplaced` | `page of type <type> is not below docs/<type>/` |
| `unindexed` | `docs/README.md has no link to this page` |
| `duplicate-id` | `id is also on <path>: <id>` |

The pytest entry point of D2.12 is `test_documents_follow_the_layout`. It
asserts no failure of the five kinds. The build row adds the claim of this
section under `## Verification` with its tests, not before: an id there is a
claim.

## D2.14 — Root README (check i)

Check i enforces the README rules below. Its switch is `[checks] readme`.
The switch is off when absent (S18). Check i reads one file, `README.md` at
the root. The name is fixed, as `docs/README.md` is for check h, and no key
changes it (I-2). A `README.rst` or a `README.md` in a subdirectory is not
read. The rules come from a survey of common README guides.

The file is decoded as UTF-8, and a byte order mark is not part of the
text. A file that is absent fails with `no-readme` on line 1. A file that
does not decode fails with `unreadable` (I-4). In both cases the rules do
not run. A line in a fenced code block is not a heading, a paragraph or a
badge (D2.10). A heading is an ATX heading, `#` to `######`.

1. **Title.** Line 1 is a heading of level 1 (`# <text>`), or it starts
   with an HTML `<h1` tag in any case. The title block is line 1, or for an
   HTML title the lines up to the first line that holds `</h1>`. If line 1
   is not a title, or an HTML title has no `</h1>`, the file fails with
   `no-title`, and the title block is empty.
2. **Badge block.** A badge is an image inside a link,
   `[![<alt>](<image>)](<target>)`. After the title block and its blank
   lines, a run of lines that hold only badges and white space is the badge
   block. A badge on a different line fails with `badges-scattered`, one
   failure for each line. An HTML `<img>` tag is not a badge, and the check
   does not examine it.
3. **Description.** After the title block, the badge block and the blank
   lines, the next line exists and is not a heading and not a fence line.
   If not, the file fails with `no-description`.
4. **Sections.** The file has a heading of level 2 with the text
   `Install` or `Installation`, one with `Usage`, and one with `License`.
   The text is compared exactly. Each absent section fails with
   `no-section`, in the order `Install`, `Usage`, `License`.
5. **Licence.** When a `License` heading has a heading of level 2 after
   it, the file fails with `misordered` on the line of the first `License`
   heading. When the root has no file `LICENSE`, `LICENSE.md` or `COPYING`,
   the file fails with `no-licence-file`. The check does not read the
   licence file, and it does not compare the licence name (R-16).
6. **Index link.** The file holds a link of D2.10, with no URL scheme,
   whose path part resolves to `docs/README.md` of the root. If not, the
   file fails with `no-index-link`.

The details and lines of the eight kinds are in D2.4. The path of each is
`README.md`. Check g examines the links of `README.md` under its own switch
(D2.10), so a broken link is `broken-link`, not a check i kind.

The pytest entry point of D2.12 is `test_readme_follows_the_standard`. It
asserts no failure of the eight kinds.

## D3.1 — Invariants

- **I-1 Position rule.** A reference is read only from a marker position of
  D1.2, by the anchored rule or the legacy rule of D2.1. Text in a string
  literal, in a Markdown file, or in a file with an extension that D1.2 does
  not list is never a reference.
- **I-2 One exclusion, from trueup.toml.** `[scan] ignore` of
  `ref_check.toml` is the one key that removes a file from the checks
  (D2.5). `apply` renders it from the `ignore` globs of `trueup.toml`, and
  from nothing else. No other configuration key, flag or environment
  variable removes a file or a directory from the scan. `SKIP_DIRS` is a
  constant. Amended by the owner on 2026-10-16. The reason: `trueup.toml`
  `ignore` promises that a path is left out of every finding, and the
  `ref-check` hook must agree with `check`. Before, `check` and the hook
  reported `refcheck` failures on ignored paths (88 pages under
  `docs/features/` in one target).
- **I-3 Inert fixtures.** Each file under `tests/refs/fixtures/` has a name that
  ends in `.txt`. A marker that is wrong on purpose exists only there, or in a
  string literal of a test.
- **I-4 Fail closed.** A source file that cannot be read or parsed, a marker
  that does not parse, a reference to a target with no configuration, and an
  unknown configuration key each give a failure or exit 2. None is skipped.
- **I-5 Legacy parity.** For a repository whose only markers are `arch:`
  markers in `test_*.py` docstrings, checks a, b and c give the verdict of
  the existing `arch_refs.py`. The unchanged selftest passes against the
  checker.
- **I-6 Zero at the start.** On a root with no marker and no
  `ref_check.toml`, the checker exits 0 and prints no failure line.
- **I-7 Same input, same bytes.** Two runs on the same tree give the same
  standard output and the same edge file, byte for byte.
- **I-8 Read only.** The checker writes the edge file and nothing else. It
  never changes a marker or a pinned version.
- **I-9 One registry.** The registry table on the standard page is equal to
  `REGISTRY` in the checker.
- **I-10 Drift by number.** Check d compares the pinned version with the
  newest version, by section number only. It does not follow a section to a
  new number (Q10).
- **I-11 One file.** The checker is one file that imports the standard
  library only, and it operates after a copy to a different name and
  directory.
- **I-12 A reason does not break a suppression.** For each form that passes in
  D2.9, the linter of that language continues to honour the suppression.

## D4.1 — One checker run

1. Find the root (D2.3). Read `ref_check.toml` if it exists. A file that is
   not valid stops the run with exit 2.
2. Walk the root (D1.2). For each file with a listed extension, read the
   marker positions. A read error gives `unreadable` and the walk continues.
3. Parse each marker (D2.1) into references. Give each one a unit.
4. Check a: resolve each reference against its target (D1.3).
5. Check b and check c (D2.8).
6. Check d: for each `law` reference that resolved, compare hashes (D4.2).
7. Checks e, f and g, each only if its switch is on.
8. Sort the failures and the edges. Print. Write the edge file if requested.
   Set the exit code.

The checker parses each target file one time for each run.

## D4.2 — Drift check of one law reference

1. The reference resolved in check a: the pinned file has the section.
2. Find the newest version (D2.7, step 5). If it is the pinned version, the
   status is `ok` and the check stops.
3. Find the section in the newest version by its number. If it is absent, the
   result is `unknown-id` with the detail "section absent in" (Q10, D2.4).
4. Calculate the two section hashes. If they are different, the result is
   `drift`. If they are equal, the check reports nothing for this site.

The repair of a drift report is a human action: read the new text, correct
the code if necessary, then change the pin. The checker does not do it (I-8).

## D4.3 — A fixture test

1. The test calls `materialise(case, tmp_path)` (D1.6). The TypeScript pair
   is the one exception (R-3). Its destination is a new directory below
   `<root>/.fixture-run/`. Git ignores that directory, and the test removes
   what it made there. eslint uses the working directory as its base path
   and ignores a file outside it with exit 0. D2.11 runs each line from the
   root, so the pair must be below the root. The walk of the checker does
   not enter a directory whose name starts with `.`, so the pair stays
   invisible to `python3 ref_check.py --root .`.
2. It runs `python3 ref_check.py --root <dir>` as a child process, or the lint
   command of D2.11.
3. It asserts the exit code and the exact failure lines. For a pair of
   fixtures (wrong, corrected) it asserts that the corrected one gives exit 0
   and no failure line, so standard output is the summary line of D2.3 alone.

## D4.4 — The legacy selftest run

1. The test verifies the SHA-256 of `tests/refs/legacy/test-arch-refs.sh` (D1.7).
2. It copies that script and `trueup/ref_check.py` to one temporary directory. The
   copy of the checker has the name `arch_refs.py`.
3. It runs the script with `bash`. The script builds its own fixture, copies
   `arch_refs.py` to `tests/refs/test_arch_refs.py` there, and runs it with
   `python3` and no argument four times.
4. The test asserts exit 0 of the script.

In that fixture the checker finds the root from its own path, finds no
`ref_check.toml`, and thus runs checks a to d only.

## D5.1 — The breaking scenario

The brief names three places where marker text is not a reference. A fourth
one was found in the expand stage. The design handles each one by the
position of the text, and no path list exists.

| Place | Why it is not read, or why it is correct |
|---|---|
| Documents that quote markers | Markdown is never a source of markers (D1.2, I-1). Documents refer by links, and check g skips code spans (D2.10). |
| Fixtures that are wrong on purpose | Each fixture file ends in `.txt`, so no reader selects it. It becomes a source file only in a temporary directory (D1.6, I-3). |
| Marker text in string literals of tests | The Python reader uses `ast` and `tokenize`. A string literal is not a docstring and not a comment token (I-1). |
| The docstring of the copied `arch_refs.py` | The file becomes a shim with no quoted marker (D1.7). Until then only the old checker runs here, and it skips its own file. |

Why this does not hide real references. The one exclusion key is
`[scan] ignore` (I-2). It comes from the `trueup.toml` `ignore` key, which
also takes the path out of every other trueup finding, so it is not a way
to repair one false failure: that is a `[keep]` failure id (D9.2). A real
reference in a `.txt` file is not possible, because a `.txt` file is not
code. The remaining ways for text to escape are narrow and stated in D5.2.

What stays a trap for the authors of this repository: a comment in
`ref_check.py` or in a test must not start with a marker keyword unless it is
a real marker, and a test docstring must not contain `arch:` in its prose. A
violation shows as a `malformed` or `unknown-id` failure in the self-check
(S19). It fails in the open, and the repair is to move the example into a
string or a document.

## D5.2 — Other failure modes

- **A heredoc or a multi-line string in a regex language** whose line starts
  with a comment leader and a keyword is read as a marker. The result is a
  false failure, not a hidden reference. The repair is one space of change to
  the literal. The vendored selftest has no such line.
- **A marker after code on one line** in a regex language is not read. The
  standard page states that a marker is a whole-line comment. R2 cannot catch
  this case. It is the accepted cost of decision 15.
- **Extraction noise in the law archive.** A new version with changed page
  artefacts inside a section reports drift where the law did not change. The
  white-space rule of D2.7 removes the line-wrap case only. The cost is one
  human look and a new pin, and the direction is safe.
- **A number that exists only in a Schedule.** The first-match rule of D2.7
  then resolves a reference to the Schedule item. This was observed as
  possible, not as present. A reference to a section of the main body is not
  affected.
- **A section with a new number** reports as absent or as changed (Q10). The
  checker does not follow it (I-10).
- **The archive is absent.** Each `law` reference fails with `unknown-id` or
  `no-target`. A build without the archive is red, not green (I-4).
- **A test cites an id but proves nothing.** No check finds this (q36, q37,
  non-goal 1).

## D5.3 — Config

`trueup.toml` lives at the root. `config.load(root)` reads it with
`tomllib` and returns `None` when the file is absent, or raises a
configuration error (exit 2) on an unknown key or a bad value.
`config.render(cfg)` writes it back as text, in one fixed key order, so two
writes of the same config give the same bytes (I-21). Keys: `version`,
`run_date` (the date of the last apply that changed a file), `tier`
(`auto`, `T0`, `T1`, `T2`, `T3`), `public`, `docs` (`full` or `readme`),
`stale_days`, `ignore` (globs left out of the survey and every finding),
`protect` (globs that `apply` never changes, I-24), a `[root]` table with
`allow` (extra root entries, D5.8), a `[scratch]` table with `allow`
(globs, matched against a path or a basename, that the `scratch` row and
the guard let through, D5.8), a `[refs]` table with `mode` (`global`, the
default, or `copy`, D9.1), `path` (copy mode only: the checker
module's path at the target, relative to the root, ending in `.py`
with no `..` or `.` part and no backslash; default `"ref_check.py"`; written only when it is
not the default, D5.6), `local_tags` (D8.7) and `layout` (D9.4), a `[languages]` table (one key per
language, value `strict`, `clean` or `off`), and one `[[keep]]` entry per
finding the person declined, each with its reason.

## D5.4 — Findings

A finding is:

```python
@dataclass(frozen=True)
class Finding:
    id: str          # "<rule>:<path>", stable and readable, never a hash
    rule: str
    category: str    # security | files | docs | root | health | setup
    severity: str    # error | warn | info
    path: str
    evidence: str    # one line; never the matched secret text (I-23)
    action: str      # one line: what apply does, or what the person does
    auto: bool       # True: apply can act on this with no prose judgement
```

The plan is every finding with severity `error` or `warn` whose id is not
in `keep`. An `info` finding never joins the plan.

Survey (`survey.py`) lists the tracked and untracked files that `git
ls-files` gives, minus the `ignore` globs, and counts lines per language
(the built-in counter, or `tokei` when it is on the path) to mark each
language present and to pick a tier; the root `ref_check.py` that `apply`
copies in counts towards no language, so it never turns Python on: T3 for a workspace, three or more
manifests, or ten or more contributors; T0 for five or fewer files across
all eight languages combined, no manifest and no CI; T1 for fifty or fewer
files in total, two or fewer contributors, and no published tag; T2
otherwise. A `tier` value in the config overrides the pick. The pick
counts no file that trueup writes, so `apply` never changes the tier
(D12.9 step 7, I-43).

The slop rows (`hygiene.py`) run on every surveyed file: `scratch` (a
scratch-looking name that no other file refers to by its path (D10.3): a backup or copy glob, or a
`tmp`, `temp`, `scratch`, `notes` or `untitled` stem, alone or followed by
digits or a separator, with no extension or a text or log one, so
`template.py` and `temp_table.sql` pass; never under `.scratch/`, never a
secret-file name, never a path `ignore`, `[root] allow` or `[scratch]
allow` names; automatic only when git tracks the file), `artifact` (a
build or cache directory, with `dist/` and `build/` counted when a root
manifest exists (D10.4), one finding for the top-most one, or a
build-output file outside one), `duplicate` (the same content as another file), `generated` (a
generated-file marker with no matching `.gitattributes` line),
`secret-file` (a key or environment file — its content is never read),
`secret-content` (a secret pattern inside another text file), `binary` (an
oversized or binary file with no LFS filter), and `root-budget` (more root
entries than the tier's budget plus `[root] allow`; an entry that holds
only trueup's files does not count, D12.9 step 7).

Health (`health.py`) checks, per tier: `README.md` and `.gitignore` at
every tier; a licence file, required from T1 and, at T0, only when
`public` is true; `CHANGELOG.md`, required at T1 and T2 once a tag exists,
and always at T3; either `CONTRIBUTING.md` or a README `## Contributing`
section, from T2; the public-only files (`SECURITY.md`, a code of conduct,
an issue template and a pull-request template) when `public` is true,
from T2; `CODEOWNERS` at T3; and `.editorconfig`, which is managed, from
T1. The minimum tier of `.editorconfig` and of each other managed file is
in the table of D12.9. It also checks, from T1, that `AGENTS.md` exists on disk and that
`CLAUDE.md` is either a symlink to it or names it; trueup never writes
either file.

Document rules (`docrules.py`) run when the docs mode in force is `full`;
a smaller set runs for `readme`. The default `docs = "auto"` gives
`readme` at T0 and T1 and `full` at T2 and T3 (D12.9). They check: the README and CHANGELOG rules above; a page
marked `status: superseded` with no working `superseded_by`, or a `status:
current` page whose `last_reviewed` is older than `stale_days`; the one
banned-word list at `trueup/data/banned.txt`, matched case-free as a whole
word in prose and in source comments (I-25), where a Markdown block that
quotes the list gives no finding (D8.4); and a run of the bundled
`ref_check.py` against the target, from the target root, with the
`ref_check.toml` that `apply` would write (D8.1), in both docs modes
(D12.9 step 6), folded in as one finding per failure line, id `refcheck:` plus the checker's own failure
id (D9.2). `check` never runs the target's
own `ref_check.py` (I-18).

## D5.5 — Rule sets

Amended by D14.6 and D15.28 (2026-11-02): `trueup lint` runs the hooks of
the rule sets, and `RuleSet.nightly` is gone.

`rulesets.py` holds sixteen rule sets: eight languages (Python, Rust,
TypeScript, Vue, shell, SQL, Go, PHP) times two modes, `strict` and
`clean`. Each rule set is:

```python
@dataclass(frozen=True)
class Hook:
    id: str; name: str; entry: str
    types_or: tuple[str, ...] = ()
    pass_filenames: bool = True
    files: str = ""
    exclude: str = ""            # paths the hook never sees; ruff format leaves out ref_check.py (I-26)

@dataclass(frozen=True)
class RuleSet:
    language: str; mode: str
    files: dict[str, str]        # target path -> template path
    hooks: tuple[Hook, ...]      # pre-commit hooks this rule set adds
    tools: tuple[str, ...]       # executables the hooks need
```

Every config file that a rule set writes lands under `lint/<language>/` of
the target, never at the target's root, and every hook passes that path to
its tool by name. A rule set with no config file (shell in `clean` mode,
for one) still has hooks: `clean` runs the linter's own rules, `strict`
turns on more of them and adds a duplication check and a dead-code check
where a tool exists for it. A tool missing from the target gives an `info`
finding (D5.4); trueup ships the rule set anyway, and its own tests skip,
naming the missing tool.

## D5.6 — Managed files and apply

Replaced by D14.8 and D14.19 (2026-10-16).

`managed.py` renders every file that trueup owns, from the config and the
survey: `trueup.toml` itself, `ref_check.toml`, in copy mode the checker
copy at `[refs] path` (D9.1), `.pre-commit-config.yaml`, the CI workflow, `.editorconfig`, the
agent rules file (D12.7), one file per enabled rule set (D5.5), and,
when `docs` resolves to `full`, the Vale style files. The set depends on
the tier: the table of D12.9 gives the minimum tier of each path, and a
file on disk that is trueup's stays in the set at any tier (I-42). Below
T2 with no `trueup.toml`, the setup rows fold into one opt-in row,
`setup:trueup.toml` (D12.9). Every rendered file starts with a header line that names
trueup as its manager, the checker copy included (D9.3), except
`trueup.toml` (its own first line) and a JSON file or the Vale
vocabulary word list, whose format holds no comment and which trueup
instead knows by its path under `lint/`. A rendered file that is absent is
an automatic `file-managed` finding; present and equal to the rendered
content (blank and comment-only lines aside) gives no finding; present and
different is an automatic finding when it still carries the header line,
or when its format holds no comment and its path sits under `lint/`;
present, different, and neither of those is a manual finding, because
trueup never overwrites a file it does not manage (I-24).

In `.pre-commit-config.yaml`, the Vale hook gets an `exclude` pattern that
names the path of each `[[keep]]` entry whose id is `prose:<path>`. Thus
the hook and `check` decline the same files. Each hook that gets the file
names (`pass_filenames` true, for example ruff, eslint and Vale) also
gets the `ignore` globs of `trueup.toml` in its `exclude` pattern. The
regex of each glob comes from the glob rules of the survey, as in the
gitleaks allowlist (D7.3). Thus these hooks and `check` skip the same
paths. A hook that scans the whole tree gets no pattern from the globs: its
tool reads its own config. A hook with no kept path and no glob has no
`exclude` line. `ref_check.toml` carries `[registry] local_tags`
from `[refs] local_tags` (D8.7) and `[keep] failures` from the kept
`refcheck:` ids (D9.2); `check` runs the checker with that rendered text
less the `[keep]` table (D8.1).

`apply.py` checks every requested id against the current plan before it
writes anything: an id the plan does not hold, or one that is not
automatic, stops the whole run at exit 2 with no file changed (I-19). It
then carries out each accepted id by its rule: `config` writes
`trueup.toml`; `file-managed` writes the rendered content; `artifact` and
`secret-file` untrack the path (`git rm --cached`, with `-r` for a
directory) and add one line for it to `.gitignore`; `scratch` removes a
tracked path (`git rm`) and never deletes a file git does not track; `generated` adds a
`.gitattributes` line; `gitignore` adds the missing line; `setup` writes
the files of the opt-in (D12.9). Before the first write, `apply` refuses
a path with uncommitted changes unless `--allow-dirty` is given (D12.2,
I-41). A path under a
`protect` glob never reaches a handler (I-24). `apply` never runs `git
commit`, `git push` or `git clean` (I-23).

## D5.7 — Score

`score.py` scores the plan findings of five of the six finding categories —
security, files, docs, root and health — with fixed weights that sum to
ninety: security 25, files 20, docs 20, root 15, health 10. A plan finding
in the sixth category, `setup` (the `config`, `file-managed`, `gitignore`
and `tool-missing` rules of D5.6), never moves the score, the same as an
`info` finding or a kept one. Each of the five scored categories' raw value
grows with its own finding count, capped at its weight (a lone security
finding already fills that category), except `docs`, which grows with its
distinct `path` count instead, so one systemic rule that fires on many
lines of one file counts once (D6.12). A `duplicate` group whose every
path sits under a `fixtures/`, `testdata/` or `__snapshots__/` directory
gives no finding at all, in `hygiene.py`, before the score ever sees it
(D6.12): that pattern is intended test data, not slop. The report prints
`score N (tier Tx)` and the value of each category. The score is a
proposal, not a measurement that another tool has checked, and the
reference page says so.

## D5.8 — Guard hooks

Amended by D14.11 and D15.31 (2026-11-02): the base list is wider, and
the guard asks about a scratch name, it does not deny.

`hooks.py`, wired through `hooks/hooks.json`, runs on two Claude Code
events. It finds the target root by walking up from the hook's working
directory to the first directory that holds `.git`, and it acts only when
`<root>/trueup.toml` exists there; otherwise, and on any exception, it
prints nothing and exits 0 (I-22).

SessionStart prints a short plain-text notice: the `tier` and `docs`
values of `trueup.toml`, the language modes, the root rule, the scratch-file rule, the managed-file rule, and a
line that points at the trueup skill.

PreToolUse, matched on `Write` and `Bash`, guards the root estate. The
allowed root entries are the ones already on disk, plus a fixed base list
(`README*`, `LICENSE*`, the language manifests, `trueup.toml`,
`.gitignore`, the `.claude` and `.github` directories, and their kin), plus `[root] allow` from the config. A
`Write` to a new file whose parent is the root, and whose name is not on
that list, is denied; so is a `Write` to a scratch-looking name outside
`.scratch/`. A `Bash` command that runs `git add` on a scratch-looking path
is denied. The scratch check is the `scratch` row's own rule and
exemptions (`hygiene.looks_scratch` and `hygiene.scratch_exempt`), so a
path under `ignore`, `[scratch] allow`, or `[root] allow` at the root is
let through. The denial message names the allow-list key, or `.scratch/`,
that would have let the write through.

## D5.9 — Self-check

This repository carries its own `trueup.toml`: `tier = "auto"`, `docs =
"full"`, `ignore` set to the fixture and template directories (wrong or
generic on purpose), `[languages] python = "clean"`, `[root] allow` naming
the plugin's own top-level directories, and one `[[keep]]` entry per
research page whose quoted source text holds a banned word. `apply
--all-auto` installs the managed files from that config. After it runs,
`python3 trueup check --root .` exits 0 (I-27); `trueup/ref_check.py`
is the one checker source (I-26); and `ruff check --config
lint/python/ruff.toml` passes on `trueup/` and `tests/`.

## D5.10 — Plugin layout

Amended by D14.16 and D15.33 (2026-11-02): packaging follows D14.16, and
`hooks/hooks.json` has four hook events and no `SubagentStop`.

The plugin root is this repository's root, and its own directory
marketplace:

```
.claude-plugin/plugin.json       manifest: name, version, description, author, licence
.claude-plugin/marketplace.json  the one plugin entry, sourced from "./"
hooks/hooks.json                 SessionStart and PreToolUse (D5.8)
skills/trueup/SKILL.md           the steps the model follows (D5.11, D5.3)
trueup/                          the stdlib-only Python package
  __main__.py                    puts the package parent on sys.path, calls trueup.cli.main()
  cli.py, config.py, survey.py, findings.py, hygiene.py, health.py,
  docrules.py, rulesets.py, managed.py, score.py, report.py, apply.py,
  hooks.py                       one module per topic named below
  ref_check.py                   the one checker source (I-26)
  data/banned.txt                the banned-word list (I-25)
  templates/                     the rule-set files, health text and CI workflow
```

The scripts under `trueup/` decide and write only what has one right
answer. The model, through the skill, asks the person, picks a mode, and
writes prose. `python3 trueup <cmd>` runs `trueup/__main__.py` with no
install step and no `PYTHONPATH` change, so one entry point serves the
hooks, the skill and the tests alike.

## D5.11 — CLI

```
python3 trueup survey [--root DIR]
python3 trueup check  [--root DIR] [--json] [--out DIR]
python3 trueup apply  [--root DIR] (--ids ID[,ID...] | --all-auto) [--mode LANG=MODE[,...]] [--set KEY=VALUE ...]
python3 trueup hook session|guard
```

`refs` forwards its own tokens to the checker's command line (D2.3)
before argparse ever sees them, so its flags are not this parser's own:

```text
python3 trueup refs   [--root DIR] [--edges FILE]
```

`--root` defaults to the git top level of the working directory. `survey`
prints a JSON inventory and exits 0, or 2 on a bad `trueup.toml`. `check`
prints a Markdown report (JSON with `--json`); `--out DIR` also writes
`DIR/trueup-report.md` and `DIR/trueup-report.json`, and `DIR` sits outside
the root or is ignored, so `check` leaves the root as it found it (I-18).
The Markdown report lists every finding once, under `Plan`, `Kept` (with
the `[[keep]]` reason) or `Info`; the JSON report holds `plan`, `findings`
and `kept`, so both list the same findings.
Its exit code is 0 for an empty plan, 1 for a plan that is not empty, 2 for
a usage or a configuration error. `apply` prints one line per action and
exits 0 on success, 1 when one handler failed (the rest still ran), or 2
when an id is unknown, not in the current plan, or not automatic — with no
file written in that case (I-19). `hook` reads one JSON object from
standard input (D5.8). `refs` forwards every token after it, unparsed,
to `trueup.ref_check.main`; with no `--root`, `--root=`, `-h` or
`--help` token, it adds the git top level at the front first, the same
default every other subcommand uses. Its exit code is the checker's
own: 0 no failure, 1 one failure or more, 2 a bad command line or
`ref_check.toml` (D2.3).

## D6.1 — Alternatives

- **A list of excluded paths.** Rejected at first: the brief shows that it
  hides real references. Amended on 2026-10-16 (I-2): one list, `[scan]
  ignore`, rendered only from `trueup.toml` `ignore`. A free list in
  `ref_check.toml` stays rejected.
- **Nested roots, each fixture with its own `ref_check.toml`.** Rejected: a
  configuration file in a directory would hide that directory. It is the path
  list in a different form.
- **Fixtures only as string literals in tests.** Passes. Rejected: a Rust crate
  or a law document inside a Python string is hard to read and to lint by
  hand. The `.txt` rule has the same safety with one helper.
- **A package with modules in place of one file.** Rejected: S20 and decision
  22 need a file that operates after a copy.
- **lychee for S22.** Rejected: it is not installed, S22 needs relative links
  and fragments only, and one more tool means one more report format.
- **Read the section hash from the archive (decision 18 as written).**
  Rejected for now: the archive has no such field, and Q7 forbids the change
  from here. The checker calculates the hash, which is one path, not two.
- **One anchored rule for `arch:` too.** Rejected: decision 21 keeps check a
  to c as they are, and a repository with old markers must not change its
  verdict (I-5).
- **A switch for each file (decision 12) for checks e, f, g.** Rejected: it
  needs one more marker. A switch for each repository gives S18 with fewer
  parts.
- **A parser for each language (tree-sitter).** Rejected by decision 15 and by
  I-11.
- **Vale for Simplified Technical English (decision 8).** Not in this design:
  no success criterion measures it.
- **Two checkers side by side in this repository.** Rejected: the old file
  quotes a marker, and two sources of checks a to c can disagree.

## D6.2 — Session snapshot

```python
# trueup/changes.py
def snapshot_path(session_id: str) -> Path | None
def write_snapshot(root: Path, session_id: str) -> None
def read_snapshot(session_id: str) -> Snapshot | None
def session_set(root: Path, session_id: str) -> frozenset[str]
```

The `session` hook (SessionStart, D5.8) writes a snapshot when
`trueup.toml` exists and `$CLAUDE_PLUGIN_DATA` is set. The file is
`$CLAUDE_PLUGIN_DATA/sessions/<session_id>.json`:

```json
{"version": 1, "root": "<abs root>", "head": "<sha or empty>",
 "dirty": {"<path>": "<blob sha>"}, "reminded": ["<path>"]}
```

- `dirty` holds each path of `working_set(root)` with its blob sha from one
  `git hash-object --stdin-paths` call.
- For the source `startup` or `clear`, the hook replaces the file. For
  `resume`, `compact` or `fork`, it writes the file only when no file
  exists, so the first snapshot stays.
- A `session_id` that does not match `^[A-Za-z0-9_-]{1,128}$` gets no file;
  `snapshot_path` then gives `None`. It also gives `None` when
  `$CLAUDE_PLUGIN_DATA` is not set.
- At each write, the hook deletes the other snapshot files that are older
  than 7 days.
- `session_set` gives `git diff --name-only <head>` (tracked changes, with
  the commits of the session), plus untracked files, minus each path whose
  current blob sha is equal to `dirty[path]`, minus deleted paths. With no
  snapshot, or with a snapshot for a different root, it gives
  `working_set(root)`. With an empty `head` (no commit yet), it uses
  `working_set` only.

## D6.3 — Stop guard

Amended by D15.33 (2026-11-02): `hooks/hooks.json` has no `SubagentStop`
entry. Only the `Stop` entry stays.

`hooks/hooks.json` adds `Stop` and `SubagentStop` entries with the command
`python3 "${CLAUDE_PLUGIN_ROOT}/trueup" hook stop`, the same launcher shape
as the `session` entry. The hook events of `trueup/cli.py` are `session`,
`guard`, `stop` and `interface`.

`hook stop` does these steps:

1. It reads the JSON object on standard input. On any error in these steps,
   it exits 0 and prints nothing (I-22).
2. It finds the root as D5.8 says. With no root or no `trueup.toml`, it
   exits 0 and prints nothing (I-22).
3. When `payload["stop_hook_active"]` is true, it exits 0 and prints nothing
   (I-15). The agent got the list one time. A second block can make a loop.
4. `paths = session_set(root, payload["session_id"])`. When `paths` is
   empty, it exits 0.
5. `run = collect(root, only=paths)`. When the plan is empty, it exits 0
   and prints nothing.
6. It prints one JSON object, `{"decision": "block", "reason": <text>}`, and
   exits 0. The first line of `<text>` is `trueup: <n> finding(s) in files
   changed this session. Fix them, or add a [[keep]] entry with a reason in
   trueup.toml, then finish.` Each next line is `- <id>: <evidence>`, for the
   first 10 findings. When there are more, the last line is `- ... <k> more:
   run python3 <plugin>/trueup check --changed`.

The hook takes less than 1 s on this repository (I-17). The hook module
imports nothing from `survey` or `rulesets` before step 2. `SubagentStop`
does the same steps: its payload has the same `session_id`, so it uses the
same snapshot.

## D6.4 — Interface reminder

`hooks/hooks.json` adds a `PostToolUse` entry with the matcher
`Write|Edit|MultiEdit` and the command `... hook interface`.

1. The hook does steps 1 and 2 of D6.3.
2. It makes `tool_input.file_path` relative to the root. A path outside the
   root gives no output.
3. The text to test is `old_string` and `new_string` for `Edit`, the old and
   new strings of all edits for `MultiEdit`, and `content` for `Write`.
4. The path is an interface file when one of these signals is true. The hook
   only matches static text. It runs no target code.

   | Signal | Match |
   |---|---|
   | Python CLI | a `.py` file whose text has `add_argument(`, `add_parser(` or `@click.` |
   | Python exports | `__init__.py` whose text has `__all__` |
   | Python scripts | `pyproject.toml` whose text has `[project.scripts]`, or the `[project]` `name` line |
   | Node | `package.json` whose text has `"bin"`, `"exports"` or `"name"` |
   | Rust CLI | a `.rs` file whose text has `#[arg(` or `#[command(` |
   | Go CLI | a `.go` file whose text has `cobra.Command{` or `.Flags().` |

   A `name` line counts when the last table header above it in the text is
   `[project]`, or when no header is above it (an `Edit` text is often a
   part of the file).
5. With no signal, or with the path already in the snapshot's `reminded`
   list, the hook prints nothing.
6. When `session_set(...)` holds `README.md` or a `docs/reference/**` path,
   the hook prints nothing. Else it adds the path to `reminded` (its only
   write, below `$CLAUDE_PLUGIN_DATA`) and prints
   `{"hookSpecificOutput": {"hookEventName": "PostToolUse",
   "additionalContext": "trueup: <path> changes a public interface
   (<signal>). README.md and docs/reference/ have no change this session.
   Update them if the interface changed."}}`.

Known limit: a file that a Bash command writes does not start the
`PostToolUse` hook.

## D6.5 — Docs drift rows

`trueup/drift.py` holds `drift_findings(survey: Survey, only: frozenset[str]
| None) -> list[Finding]`, and `collect` calls it. Each row has the category
`docs` and `auto=False`. No row runs target code or looks up a tool on the
path (I-18, I-21). The docs are `README.md` and the tracked `docs/**/*.md`
files.

In a scoped run (D6.17), the rows still read the manifests, the flag sources
and the tracked path set from the full survey, because these are facts
about the code, not about the changed files. `drift-flag`, `drift-package`
and `drift-command` read only the docs in `only`. `drift-undocumented` reads
every doc. The rows then keep only the findings whose `path` is in `only`.
Thus a scoped run gives no drift finding that the full run does not give.
When `only` holds no doc, no `.py` file, no `go.mod` and no `Cargo.toml`,
the rows read nothing.

| Rule | Severity | Id | Fires when |
|---|---|---|---|
| `drift-flag` | warn | `drift-flag:<doc>:<flag>` | a doc line runs a project command with a `--flag` that is not in the static flag set of that command |
| `drift-undocumented` | info | `drift-undocumented:<src>:<flag>` | no doc names a static flag |
| `drift-package` | warn | `drift-package:README.md` | the README install section has install lines, and none names a manifest name or `.` |
| `drift-command` | warn | `drift-command:<doc>:<token>` | a shell code block runs a path that git does not track, `npm run <s>` with no such script, or `make <t>` with no such target |

Static flag sets, per command name:

- Python: `ast.parse` of the tracked `.py` files outside `tests/` that call
  `.add_argument(`. Each string constant argument that starts with `--` is
  a flag, and so is the argument of `@click.option("--x")`. The command
  names are the `[project.scripts]` keys, and `python3 <path>` or `python3
  <pkgdir>` for that file or its package.
- Go: a regex on the `.Flags()` and `.PersistentFlags()` calls. The second
  argument string gives `--<name>`. The command is the last segment of the
  `go.mod` module.
- Rust: `#[arg(long = "x")]` and `.long("x")` only. The command is the
  `[package] name` of `Cargo.toml`. The rule does not infer a flag from a
  field name.
- A command with an empty flag set gives no `drift-flag` row.

Doc parsing reads the fenced blocks with the info string `sh`, `bash`,
`shell`, `console`, `fish`, or no info string. It removes a leading `$ `,
the environment assignments `X=y` and `sudo` from each line. Inline code
spans count for `drift-flag` only. The install section is the README
section whose heading matches `/install/i`. The install lines are `pip
install`, `uv tool install`, `uv add`, `pipx install`, `npm i` or `npm
install` (with or without `-g`), `cargo install`, `go install <mod>@`,
`go install .`, `go install ./...`, `go get` and `composer require`. `-r
file`, `-e .` and `.` count as the manifest. The project's own names are
the `name` of `pyproject.toml`, `package.json`, `Cargo.toml` and
`composer.json`, and the `module` path of `go.mod`. In a `go install` or
`go get` line, `./...` also counts, and so does a module path, with its
`@<version>` removed, that equals the `go.mod` module or is a path below it
(`<module>/cmd/<name>`). `go get` is an install line because `uv add` and
`composer require`, the library installs of two other languages, are too.
Amended on 2026-10-16: before, no Go line could name the project, so each
Go README gave a false `drift-package` row.

## D6.6 — Baseline keys and file

```python
# trueup/baseline.py
def key(f: Finding) -> str
def build(run: CheckRun, ratchet: dict[str, dict[str, float]]) -> dict
def render(data: dict) -> str          # sorted keys, indent 2, "\n" at the end
def load(root: Path) -> dict | None    # None when the file is absent
def compare(base: dict, run: CheckRun, ratchet_now: dict[str, dict[str, float]]) -> Gate
```

- `key` removes line numbers. `secret-content:<path>:<line>` becomes
  `secret-content:<path>`. `changelog:<path>:<line>` becomes
  `changelog:<path>`. `refcheck:<path>:<line>:<kind>[:<tail>][:<n>]`
  becomes `refcheck:<path>:<kind>`. The id gets `:<tail>` and `:<n>` only
  when two failures have the same `path:line:kind`, so the key does not
  keep them. The count holds the number of failures. Each other id is its
  own key.
  A key stays readable and is never a hash (D5.4).
- The file is `.trueup-baseline.json` at the root: `{"version": 1, "score":
  <int>, "findings": {"<key>": <count>}, "ratchet": {"<lang>":
  {"docstring": <float>, "test": <float>}}}`. It records only the plan
  findings (error or warn, not kept).
- `trueup baseline [--root R]` runs `collect(root)` in full, measures the
  ratchet values (D6.8), writes the file, prints `baseline: <n> keys, score
  <s>` and exits 0. It writes that one file and no other file (I-16).
- The file is data, not a managed file. `setup_findings` and the hygiene
  rows ignore it by name. `trueup survey` and `check` both remove it from
  the survey, so the two commands give the same `files`.

## D6.7 — Baseline gate and CI delivery

Amended by D14.9 and D15.21 (2026-11-02): the CI template is the text of
D14.9, and the gate does not compare the score.

`trueup check --baseline [--root R] [--json]` writes nothing (I-18, I-16).

```python
@dataclass(frozen=True)
class Gate:
    new: tuple[str, ...]              # finding ids whose key count went up
    score_before: int
    score_now: int
    ratchet_drops: tuple[str, ...]    # "<lang>:<metric> <before> -> <now>"
    missing_reports: tuple[str, ...]  # "<lang>:test" recorded, no report now
    tighten: tuple[str, ...]          # keys whose count went down (info only)
```

- With no baseline file, it prints `no baseline: run trueup baseline` and
  exits 2.
- It exits 1 when `new`, `ratchet_drops` or `missing_reports` is not empty,
  or when `score_now > score_before`. Else it exits 0, also when the plan is
  not empty. The new ids of a key are the current findings for that key
  after the recorded count, in id order.
- The Markdown report adds a `## Baseline` section (new, drops, missing,
  tighten). The JSON report adds `"baseline": {...}` with the `Gate` fields.
  A `check` with no flag does not change.

CI delivery: `.pre-commit-hooks.yaml` at the root of this repository
declares `id: trueup-baseline`, `name: trueup baseline gate`, `language:
python`, `entry: trueup check --baseline --root .`, `pass_filenames: false`
and `always_run: true`. `pyproject.toml` declares `[project.scripts] trueup
= "<module>:<func>"`, which runs the same CLI as `python3 trueup`. It also
declares the minimum that pip needs: `[build-system]` with setuptools, a
`version` equal to the version in `.claude-plugin/plugin.json`, and
`[tool.setuptools] packages` with `trueup` and its package data (`data/`,
`templates/`). A how-to page gives the `.pre-commit-config.yaml` entry for a
target (`repo: <trueup git url>`, `rev: <tag or sha>`). It tells the reader
that a private repository needs CI credentials for the clone. The managed
CI workflow of a target already runs `pre-commit run --all-files`, so no
template changes.

## D6.8 — Clean-mode ratchets

```python
# trueup/baseline.py
def ratchet_values(survey: Survey, cfg: Config) -> dict[str, dict[str, float]]
```

The ratchet values come from file reads only (I-18). `trueup baseline`
stores them in the `ratchet` field of the baseline, and `check --baseline`
compares them. Only languages that are present and set to `clean` in
`trueup.toml` get values: a `strict` mode already has fixed floors.

| Metric | Language | Source | Value |
|---|---|---|---|
| docstring | python | stdlib `ast` over the surveyed `.py` files outside `tests/` | percent of public modules, classes and functions (name does not start with `_`) that have a docstring, 1 decimal |
| test | python | `coverage.xml` (Cobertura) at the root | `line-rate` × 100 |
| test | go | `coverage.out` (coverprofile) at the root | covered statements / statements × 100 |
| test | typescript | `coverage/lcov.info` | sum of LH / sum of LF × 100 |
| test | rust | `lcov.info` at the root | sum of LH / sum of LF × 100 |

- An absent report gives no `test` value. A recorded `test` value with no
  report now gives a `missing_reports` entry, so the gate fails.
- A drop is `now < before - 0.1`. The baseline does not store a rise until
  the next `trueup baseline` run.
- Limit: the gate does not find a report that is older than the code. CI
  must write the report in the same job.

## D6.9 — Banned word forms

A line of `trueup/data/banned.txt` is `word` or `word => <regex>`. The word
is the word that RULES rule 7 names. The regex is the banned form of that
word. The regex uses only the syntax that Python `re` and Go RE2 read the
same way: no lookaround, no backreference, no possessive quantifier. The
Python matcher and Vale both match case-free, with the pattern wrapped as
`\b(?:<regex>)\b`.

The field trial found three words whose noun use is not banned. Each of
them gets a form entry that matches only its verb use. For one of the three,
the form entry also matched a rare plural noun; D8.5 removed that match and
added a form entry for `leverage`.

- `docrules._word_pattern(term)` becomes `_entry_pattern(entry)`. The
  finding message still names the word.
- In `lint/vale/styles/Trueup/Banned.yml`, the token of a bare word is the
  word, and the token of a form entry is its regex. I-25 holds as: the RULES
  words are equal to the `banned.txt` words (left of `=>`), and the
  `Banned.yml` tokens are equal to the `banned.txt` patterns, in the same
  order.
- Each trial case has a fixture whose noun use gives no finding, and each
  of the three words has a fixture whose verb use gives a finding. The
  Python matcher and a real `vale` run (D6.13) both use these fixtures.

A policy file that quotes the list gets no matcher change in this design;
D8.4 adds the quoted-list rule for Markdown. Under a `prose` finding that
names 10 or more different words, the Markdown report adds the line `hint:
this file may quote the list on purpose; add a [[keep]] entry with a
reason`.

## D6.10 — Secret body check

`_secret_content` keeps its loop per line for the single-line patterns. The
private-key pattern becomes a block rule. A BEGIN banner line counts only
when one of the next 3 lines, stripped, matches `^[A-Za-z0-9+/=]{40,}$`.
The finding line is the banner line. The evidence has no matched text
(I-23). The tests use a banner with a placeholder line and a banner with a
comment line, which give no finding. A test also builds a key-shaped block
(random base64, lines of 64 characters) in `tmp_path` at test time, which
gives a finding. The repository holds no key-shaped block.

## D6.11 — Local tags

The change is made directly in `trueup/ref_check.py` (I-26).

- The `ref_check.toml` schema adds `[registry] local_tags = ["D", "O"]`: a
  list of uppercase prefixes, empty by default.
- A comment tag that the R1 regex matches is not a marker candidate when
  its word is equal to a prefix, or is a prefix followed only by digits.
- This page names the key in the R1 rule text (D2.2) and in the
  configuration section (D2.5). A test shows that a `# D1:` comment passes
  with the key and fails without it.
- The task that makes this change records `git status --short` before it
  starts. It touches only the files it names and makes no commit.
- `trueup.toml` later gained `[refs] local_tags`, which `apply` renders
  into this table (D8.7).

## D6.12 — Score calibration

D6.9, D6.10 and D6.11 come before this change. Two formula changes come
from the field trial:

1. Docs: `20 * min(1.0, distinct_docs_paths / 10)`. `distinct_docs_paths`
   is the number of different `path` values among the docs findings (not
   the finding count). So one rule that fires many times in one file counts
   one time.
2. Duplicates: a `duplicate` group whose paths are all below a `fixtures/`,
   `testdata/` or `__snapshots__/` directory gives no finding, because it
   is test data.

Security stays a step: one real secret fills the category. The calibration
task runs `check --json` again, read-only, on the six trial repositories.
It records a "Calibration" table in `docs/reference/trueup.md` (v1 score,
v2 score, trial rank). The tests that pin the old shapes change by design.
The D5.7 text changes to agree.

## D6.13 — Tool-verified rule sets

Each test that needs a tool runs the real tool on a good sample and a bad
sample in `tmp_path`. It skips only when the tool is absent. No test uses
`pytest.fail` as a placeholder.

| Tool | Test setup | Pass condition |
|---|---|---|
| shfmt | the rendered strict hook arguments on a good and a bad `.sh` file | good exit 0; bad exit not 0 |
| golangci-lint | a temporary module and the rendered `lint/go/golangci.yml` per mode; `config verify`, then `run ./...` | verify prints nothing; good gives "0 issues"; bad gives 1 issue or more; stderr has no `deprecated` |
| phpstan, phpcs, phpmd | a temporary project with `vendor` linked to the output of `composer global config vendor-dir --absolute`; the rendered hook commands | good exit 0; bad exit not 0, per tool |
| eslint with ts strict, vue clean and strict | a temporary directory with `node_modules` linked to `lint/ts/node_modules`, and the rendered `eslint.config.mjs` | good exit 0; bad exit not 0 |
| vale | `lint/vale/.vale.ini` on a good and a bad `.md` file | a banned verb gives a finding; the noun fixtures of D6.9 give none |
| tokei | `test_check_reports_name_the_counter` checks the counter name that the survey reports, not "built-in" | passes with and without tokei |

The real tools force these template changes: Go strict turns off the
deprecated linters `wsl` and `gomodguard`; the strict samples do not use
`fmt.Print*`; the sonarjs pin in `typescript/package-strict.json` becomes
`^4.2.1`; phpstan strict needs `phpstan/phpstan-strict-rules` in the global
composer vendor directory. The tests find a tool on the path with
`shutil.which`, find the PHP tools through the global vendor directory, and
find the eslint plugins through `lint/ts/node_modules`.

## D6.14 — Survey counter scope

`_tokei_counts(root, files)` keeps only the tokei JSON `reports` whose path
is in `files`, and adds up only those. It gives no file list to tokei,
because the argument list of a large repository is too long. So the
language presence does not depend on which counter ran (I-13). The test
uses one fixture with a JavaScript file below an `ignore` glob: the set of
present languages is the same with and without tokei.

## D6.15 — Review debt

The source is `.state/runs/trueup-plugin/06-review.md`, items LOW-1 to
LOW-10. A test proves each fix, or
`.state/runs/trueup-v2/07-low.md` gives the reason to close the item.

| Item | Location | Action |
|---|---|---|
| LOW-1 | `trueup/report.py` | fix as the review says |
| LOW-2 | `trueup/managed.py`, JSON managed marker | fix; for one version, also accept the old form with no header as managed, and say so in an "Upgrade notes" section of `docs/reference/trueup.md` |
| LOW-3 | `trueup/hooks.py` `_git_add_paths` | fix as the review says |
| LOW-4 | `trueup/managed.py` | fix as the review says |
| LOW-5 | `plugin.json`, the reference page, `trueup/cli.py` | fix with the new hook events (D6.3) |
| LOW-6 | the closed v1 contract file in `.state/` | close: it is a process record, not a part of the product |
| LOW-7 | the import chain from `hooks` through `hygiene` and `survey` to `rulesets` | fix with lazy imports; the D6.3 time test measures it |
| LOW-8 | `trueup/hooks.py` `_find_root` and the "Hooks" section of the skill | fix as the review says |
| LOW-9 | `trueup/apply.py` | fix as the review says |
| LOW-10 | the `Vale.Spelling` level in `lint/vale/.vale.ini` | fix; the real vale test (D6.13) checks it |

## D6.16 — Field trial record

`docs/reference/trueup.md` gets a "Field trial" section. It gives the six
repositories, the tier, the score before and after, the counts of true
findings, false findings and noise, the run time, and each false finding
with the section that fixed it (D6.9 to D6.12). The raw trial record stays
in `.state/runs/trueup-v2/00-field-trial.md`.

## D6.17 — Changed-file scope

```python
# trueup/report.py
def collect(root: Path, only: frozenset[str] | None = None) -> CheckRun
# trueup/changes.py
def working_set(root: Path) -> frozenset[str]
```

When `only` is `None`, `collect` gives the v1 result, byte for byte (I-21).
`apply` calls `collect(root)`, so it validates against the full plan (I-19).

When `only` holds paths (POSIX, relative to the root), the survey runs in
full. The `prose`, `readme`, `changelog` and `pages` rows read only the
files in `only`. The drift rows (D6.5) give the findings of a full run whose
`path` is in `only`. The `refcheck` row does not run; the
pre-commit hook still runs `ref_check.py`. After all rows, `collect` keeps
only the findings whose `path` is in `only`. It drops the repo-wide findings
(path `.`, `health`, `setup` and `root-budget`). `CheckRun.score` is `None`,
because a score is for the full repository.

`trueup check --changed [--root R] [--json]` uses the change set that
`changes.working_set(root)` gives: the working tree against `HEAD`, plus
untracked files, minus ignored files. It exits 1 when the scoped plan is not
empty, else 0. The JSON report adds `"scope": "changed"` and `"score":
null`. `--changed` together with `--baseline` is a usage error (exit 2).

Each git call in `changes.py` runs as `git --no-optional-locks -C <root>
...`, so `git status` does not refresh `.git/index` (I-18, I-14). The status
call is `status --porcelain=v1 -z --untracked-files=all`. A renamed entry
gives its new path. A deleted path is dropped.

## D7.1 — Architecture of the wave

This design adds a security floor: new and changed parts, with their
boundaries.

| Part | File | Kind | Rows |
|---|---|---|---|
| lockfile row | `trueup/hygiene.py` | new row function `_lockfile` | B1 |
| lockfile table | `trueup/hygiene.py` | one table `_LOCK_PAIRS`; `_LOCKFILE_NAMES` is derived from it | B1 |
| secret engine | `trueup/secrets.py` | new module: gitleaks run, parse, map to findings | B2 |
| gitleaks config | `trueup/managed.py`, `trueup/templates/gitleaks/gitleaks.toml` | new managed file `lint/gitleaks/gitleaks.toml` | B2 |
| pre-commit | `trueup/rulesets.py`, `trueup/managed.py` | new shared hook `gitleaks` | B2 |
| CI template | `trueup/templates/ci/trueup.yml`, `trueup/managed.py` | SHA pins, gitleaks step, osv-scanner step, fallback comments | B2, B3, B4 |
| SAST | `trueup/templates/rules/{python,typescript,go}/*` | clean sets gain S, eslint-plugin-security, gosec | B5 |
| SECURITY.md | `trueup/health.py` | `_security_required` | B6 |
| install guard | `trueup/hooks.py` | Bash branch calls `install_guard` | B7 |
| registry | `trueup/registry.py` | new module: the only network code | B7 |
| platform rows | `trueup/health.py` | three manual findings when `public` | B8 |
| security floor | `docs/reference/trueup.md` | new section and table | B9 |

`trueup/` stays stdlib only. gitleaks and osv-scanner are external
executables. `registry.py` uses `urllib.request`. No new `trueup.toml` key.

## D7.2 — Lockfile row (B1)

```python
_LOCK_PAIRS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cargo.toml", ("Cargo.lock",)),
    ("pyproject.toml", ("uv.lock", "poetry.lock", "pdm.lock", "pylock.toml")),
    ("Pipfile", ("Pipfile.lock",)),
    ("package.json", ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
                      "pnpm-lock.yaml", "bun.lock", "bun.lockb")),
    ("go.mod", ("go.sum",)),
    ("composer.json", ("composer.lock",)),
)
_LOCKFILE_NAMES: frozenset[str]   # every lockfile name above; the generated row reads it
def _lockfile(survey: Survey) -> list[Finding]: ...
def _declares_dependencies(name: str, text: str) -> bool: ...
```

Rules:

1. The row reads the tracked, not-ignored file list of the survey. A
   manifest is a file whose base name is a key of `_LOCK_PAIRS`. A
   `pylock.<name>.toml` file also counts as a Python lockfile.
2. A manifest that declares no dependencies gives no finding.
   `_declares_dependencies` reads the text with `tomllib` or `json`:
   - `pyproject.toml`: a non-empty `[project] dependencies`,
     `[project.optional-dependencies]`, `[dependency-groups]`, or a
     `[tool.poetry.dependencies]` table with a key other than `python`.
   - `Pipfile`: a non-empty `[packages]` or `[dev-packages]`.
   - `package.json`: a non-empty `dependencies`, `devDependencies`,
     `optionalDependencies` or `peerDependencies`.
   - `Cargo.toml`: a non-empty `[dependencies]`, `[dev-dependencies]`,
     `[build-dependencies]` or `[workspace.dependencies]`.
   - `go.mod`: a `require` directive.
   - `composer.json`: a key of `require` or `require-dev` other than `php`
     and `ext-*`.
   - A manifest that does not parse declares dependencies (fail closed).
3. A manifest that declares dependencies needs one of its lockfile names in
   its own directory or in an ancestor directory up to the root. The
   ancestor rule covers Cargo, npm, pnpm and yarn workspaces, which keep
   one lockfile at the workspace root.
4. A lockfile that git does not track does not count.
5. Finding: `id=f"lockfile:{manifest}"`, `rule="lockfile"`,
   `category="security"`, `severity="error"` at every tier, `path=manifest`,
   `auto=False`, `evidence=f"{manifest} declares dependencies and has no lockfile"`,
   `action` = the lock command of the ecosystem, one line, for example
   `run uv lock (or poetry lock, pdm lock) and commit the lockfile`.
6. The row joins `hygiene_findings` after `_secret_content`. In a scoped
   run (`only`), the row keeps a finding only when its manifest is in
   `only` (D6.17 rule, path not empty).
7. A manifest with trueup's `"_managed": "trueup"` marker gives no finding
   (D8.3).

Effect on this repository: `pyproject.toml` declares no dependencies, and
`lint/ts/package.json` has `lint/ts/package-lock.json`. The row stays
silent here.

## D7.3 — Secret engine (B2)

```python
# trueup/secrets.py
@dataclass(frozen=True)
class EngineRun:
    engine: str                    # "gitleaks" | "built-in"
    note: str                      # "" or one line: why gitleaks did not run
    findings: tuple[Finding, ...]

GITLEAKS_CONFIG_PATH = "lint/gitleaks/gitleaks.toml"
GITLEAKS_TIMEOUT_S = 120

def scan(root: Path, survey: Survey, history: bool) -> EngineRun | None: ...
```

Rules:

1. `scan` returns `None` when `gitleaks` is not on the path. The caller
   then keeps the built-in `secret-content` row, and the engine is
   `built-in`.
2. When gitleaks is on the path, `scan` runs one of these, with the
   working directory set to `root`, and the report written to a file in a
   `tempfile.TemporaryDirectory()` outside the target:
   - working tree (`check`, `check --changed`):
     `gitleaks dir . --redact --no-banner --exit-code 0 --report-format json --report-path <tmp>/r.json`
   - history (`trueup baseline`, `check --baseline`):
     `gitleaks git . --redact --no-banner --exit-code 0 --report-format json --report-path <tmp>/r.json`
   - When `<root>/lint/gitleaks/gitleaks.toml` exists, both add
     `--config lint/gitleaks/gitleaks.toml`.
3. A non-zero exit, a timeout, or a report that is not a JSON list makes
   `scan` return `EngineRun("built-in", "gitleaks failed: <reason>", ())`.
   The caller then runs the built-in row. The report header prints the
   note.
4. Mapping. trueup reads only `File`, `StartLine`, `RuleID`, `Commit` and
   `Fingerprint` of each entry. It never reads `Secret` or `Match`, and it
   never copies them into a finding. A path that is ignored or not tracked
   (working tree) gives no finding.
   - working tree: `id=f"secret-content:{File}:{StartLine}"`,
     `evidence=f"{File}:{StartLine} matches {RuleID}"`. The id has the same
     shape as the built-in row, so the baseline keys do not change when the
     engine changes.
   - history: `rule="secret-history"`, `id=f"secret-history:{Fingerprint}"`,
     `path=File`, `evidence=f"{File}:{StartLine} matches {RuleID} in commit {Commit[:12]}"`,
     `action="rotate the secret; a history rewrite is the owner's decision"`.
   - both: `category="security"`, `severity="error"`, `auto=False`.
5. When gitleaks ran, the built-in `secret-content` row does not run. The
   `secret-file` row always runs: it reads file names only, never content,
   and it catches a tracked `.env` that holds no known pattern.
6. Wiring. `report.collect(root, only=None, history=False)` calls
   `secrets.scan(root, survey, history)` once. It passes the result to
   `hygiene.hygiene_findings(survey, secret_findings)`, where
   `secret_findings` is `None` (run the built-in `secret-content` row) or
   the tuple from gitleaks (use it, skip the built-in row). `CheckRun`
   gains `secret_engine: str` and `secret_note: str`. The `trueup baseline`
   command and `check --baseline` call `collect` with `history=True`;
   every other caller keeps the default.
7. The report prints `secrets <engine>` on the line after `counter <name>`,
   plus ` (<note>)` when the note is not empty. The JSON report adds
   `"secret_engine": "<engine>"`. The test that compares the JSON report
   with the v1 join adds this one key to its expected value and changes
   nothing else. Both `trueup baseline` and `check --baseline` use the
   history mode, so the baseline file and the gate count the same keys.
8. `lint/gitleaks/gitleaks.toml` is a managed file at every tier when
   `docs` is any value (it does not depend on docs). Its text:
   `[extend] useDefault = true`, then one `[[allowlists]]` table with
   `paths` = one regex per `trueup.toml` `ignore` glob (glob to regex,
   anchored), in config order. With no ignore glob, the file holds the
   `[extend]` table only. It starts with the managed header comment.
9. Pre-commit: a shared hook `gitleaks`, after `ref-check` and before the
   language hooks:
   `entry: sh -c 'command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks not on the path: secret scan skipped"; exit 0; }; exec gitleaks git --pre-commit --staged --redact --no-banner --config lint/gitleaks/gitleaks.toml'`,
   `language: system`, `pass_filenames: false`. The hook text does not
   depend on the machine (I-33). CI installs gitleaks, so CI enforces.
10. Test data: a test that needs a secret assembles it in code at run time
    (for example `"AKIA" + "Q" * 16`) and writes it into a copy of a
    fixture directory under `tmp_path`. No committed file holds a string
    that a secret scanner matches.

## D7.4 — CI template (B2, B3, B4)

Replaced by D14.9 (2026-10-16): the function is now
`managed.render_ci()`, with no argument.

`render_ci(cfg: Config, survey: Survey) -> str`. The new parameter gives
the tracked lockfiles (`_LOCKFILE_NAMES`, D7.2). `render` already has the
survey and passes it.

Rules:

1. Every `uses:` line has the form
   `- uses: <owner>/<repo>[/<path>]@<40 hex> # <tag>`. The pin is found with
   `git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>`
   (peeled `^{}` line when the tag is annotated) and written into the
   template. Pins: `actions/checkout`, `actions/setup-python`, and the
   osv-scanner action. `permissions: contents: read` stays.
2. The install lines from the modes stay as they are (D5.6). One more line
   installs gitleaks at a fixed version: a `curl` of the release archive
   from `github.com/gitleaks/gitleaks/releases`, a `sha256sum -c` of the
   archive against the checksum that the release publishes, and an extract
   to `/usr/local/bin`.
3. A step `- run: gitleaks git . --redact --no-banner --config lint/gitleaks/gitleaks.toml`
   runs after `pre-commit run --all-files`. The checkout of that job uses
   `fetch-depth: 0`, so the history scan sees every commit.
4. When the survey shows one tracked lockfile or more, `render_ci` adds an
   osv-scanner step, pinned by SHA, that scans the repository recursively.
   With no lockfile, the step is absent (osv-scanner fails on a tree with
   no package source).
5. Below the osv-scanner place, the template keeps five comment lines, one
   per ecosystem, with the fallback command: `pip-audit`, `cargo audit`,
   `npm audit --audit-level=high`, `govulncheck ./...`, `composer audit`.
   They are comments in every render.
6. `render_ci` still raises `RuntimeError` when a marker is gone.
7. In global mode (D9.1), one comment line below the install marker names
   the trueup install that the `ref-check` hook needs.

Effect on this repository: `lint/ts/package-lock.json` is tracked, so the
osv-scanner step is present. The self-check gives
`file-managed:.github/workflows/trueup.yml` and
`file-managed:.pre-commit-config.yaml` and
`file-managed:lint/gitleaks/gitleaks.toml` until `apply --ids` rewrites
them. The task that changes the templates runs that apply.

## D7.5 — SAST in the clean rule sets (B5)

1. Python clean template (`ruff-clean.toml`): `extend-select` gains `"S"`.
   `extend-ignore` gains `"S603"` and `"S607"`, with a comment that gives
   the reason: a subprocess call with a list of arguments and no shell; a
   `which()` path adds nothing. `[lint.per-file-ignores]` gains
   `"**/tests/**"` and `"**/test_*.py"` = `["S101", "S105", "S106", "S108"]`
   (owner, 2026-10-04), reason: tests use `assert`, fake credentials and
   temporary paths on purpose.
2. Python strict already selects `ALL`. It gains the same per-file test
   ignores and the same `S603`, `S607` ignore with the reason.
3. TypeScript clean and strict: `package-*.json` gains
   `eslint-plugin-security`; the eslint block adds
   `security.configs.recommended`. Vue follows the TypeScript files it
   shares.
4. Go clean: `golangci-clean.yml` enables `gosec`. Go strict enables it
   when it does not already.
5. This repository: fix the `S101` in `trueup/ref_check.py` (raise an
   exception in place of `assert`). `S105` (`cli.py`, a variable named
   `token`), `S110` (`hooks.py`, the fail-open `except`) and `S314`
   (`baseline.py`, stdlib XML of a coverage report that the target's own
   tool wrote) each get a per-line suppression with the rule code and a
   reason. `lint/ts`: `npm install -D eslint-plugin-security` (network
   allowed), lockfile updated.
6. Each D6.13 tool-verified test keeps its good and bad files. Each of the
   three languages gains one bad file that only the new rules flag (Python
   `eval(input())`, TypeScript `eval(x)` or a non-literal `RegExp`, Go
   `exec.Command(variable)` under gosec G204). The clean config must flag
   it and must pass the good file.

## D7.6 — SECURITY.md when public (B6)

`_security_required(tier, public, tags)` returns `public` at every tier.
A rule that holds at T0 and T2 but not at T1 has no reason, so this design
takes every tier. The health table on the reference page shows "when
public" in all four columns. The skill's question set item 3 says: `true`
adds `LICENSE` and `SECURITY.md` at every tier, and at T2 and above the
other public files.

## D7.7 — Install guard (B7)

```python
# trueup/hooks.py
def _check_install(command: str) -> tuple[str, str] | None: ...
#   returns ("deny" | "ask", reason) or None; prints a systemMessage itself
#   when a lookup could not run
```

1. The guard runs only where `trueup.toml` exists (I-22 unchanged).
2. `_guard` calls `_check_install` for `tool_name == "Bash"` after the
   existing `_check_bash`. A deny from either wins. Else an `ask` gives
   `permissionDecision: "ask"`. Else no decision.
3. Command reading. Split the command with `shlex.split` on the existing
   `_SHELL_BREAKS`. In each segment, drop leading `sudo`, `env`, and
   `NAME=value` tokens. A segment is an install when its leading tokens
   match one row of this table:

   | Ecosystem | Leading tokens |
   |---|---|
   | pypi | `pip install`, `pip3 install`, `python -m pip install`, `python3 -m pip install`, `uv pip install`, `uv add`, `poetry add`, `pdm add` |
   | npm | `npm install`, `npm i`, `npm add`, `pnpm add`, `yarn add`, `bun add` |
   | crates | `cargo add` |
   | go | `go get`, `go install` |
   | packagist | `composer require` |

4. Package names. Skip tokens that start with `-`. After `-r`,
   `--requirement`, `-c`, `--constraint`, `-e`, `--editable`, `-i`,
   `--index-url`, `--extra-index-url`, `--registry`, `--features`, `-F`,
   skip the next token too. Skip a token that is a path or a URL (starts
   with `.`, `/` or `~`, holds `://`, starts with `git+`, or ends in
   `.whl`, `.tar.gz` or `.tgz`). Strip a version or extra: pypi cuts at the
   first of `[=<>!~;@ `; npm cuts at the last `@` that is not at position
   0; crates cuts at `@`; go cuts at `@`; packagist cuts at `:`. `go get`
   and `go install` without `@` and a module path with no dot in the first
   element (a local package) are skipped. A segment with no name left
   (bare `npm install`) is not checked.
5. For each name, `registry.first_release(ecosystem, name)` (D7.8):
   - `Unknown` gives deny: `trueup: <name> is not on <registry>. Check the
     spelling. Do not install a package that you cannot find on the
     registry.`
   - a release date less than 30 days before now gives ask:
     `trueup: <name> first appeared on <registry> on <date> (<n> days ago).
     Check the publisher, the source repository and the download count
     before you install it.`
   - `Unreachable` gives no decision. The hook prints
     `{"systemMessage": "trueup: <registry> did not answer; the install guard did not check <name>."}`
     and exits 0.
6. The guard never prints `permissionDecision: "allow"` (I-29).
7. `hooks.py` imports `registry` inside `_check_install`, and only when a
   segment is an install. The import test and the timing bound I-17 stay
   true.

## D7.8 — Registry lookups and cache (B7)

```python
# trueup/registry.py
@dataclass(frozen=True)
class Unknown: ...
@dataclass(frozen=True)
class Unreachable:
    reason: str
Answer = datetime | Unknown | Unreachable

BASE_URLS: dict[str, str] = {
    "pypi": "https://pypi.org",
    "npm": "https://registry.npmjs.org",
    "crates": "https://crates.io",
    "go": "https://proxy.golang.org",
    "packagist": "https://repo.packagist.org",
}
CALL_TIMEOUT_S = 2.0
RUN_BUDGET_S = 5.0
CACHE_TTL_S = 86400
NPM_BYTE_CAP = 1 << 20

def first_release(ecosystem: str, name: str, *, deadline: float) -> Answer: ...
```

1. Lookups, one per ecosystem. HTTP 404 (and 410 for go) gives `Unknown`.
   A timeout, a connection error, a 5xx, or a body that does not parse
   gives `Unreachable`.
   - pypi: `GET /pypi/<name>/json`; the earliest `upload_time_iso_8601` of
     any file of any release. A package with no file gives `Unknown`.
   - npm: `GET /<name>` (a scoped name has its `/` encoded as `%2f`); read
     at most `NPM_BYTE_CAP` bytes. With the whole body read: `time.created`.
     With the cap hit: the package has a long record, so it is old; the
     answer is the Unix epoch (a young package has a short record).
   - crates: `GET /api/v1/crates/<name>` with a `User-Agent:
     trueup-install-guard (<plugin version>)` header; `crate.created_at`.
   - go: `GET /<escaped module>/@v/list` (capital letters escaped as `!` +
     lower case); the lowest semantic version; then `GET
     /<escaped module>/@v/<version>.info`; its `Time`. An empty list: `GET
     /<escaped module>/@latest` and its `Time`.
   - packagist: `GET /p2/<vendor>/<package>.json`; the earliest `time` of
     the versions under `packages[<name>]`.
2. Every call uses `min(CALL_TIMEOUT_S, deadline - now)`. The hook sets
   `deadline = start + RUN_BUDGET_S`. A name whose turn comes after the
   deadline is `Unreachable("time budget")`.
3. Cache. When `$CLAUDE_PLUGIN_DATA` is set, the cache file is
   `$CLAUDE_PLUGIN_DATA/registry-cache.json`: a JSON object
   `{"<ecosystem>:<name>": {"t": <checked epoch>, "first": "<iso date>" | null}}`,
   with `null` for `Unknown`. An entry younger than `CACHE_TTL_S` is the
   answer. `Unreachable` is never cached. A write goes to a temporary file
   in the same directory, then `os.replace`. A cache file that does not
   parse is treated as empty. With no `$CLAUDE_PLUGIN_DATA`, there is no
   cache (I-14).
4. No other module in `trueup/` opens a network connection (I-28).

## D7.9 — Platform controls (B8)

When `public` is true, at every tier, `health_findings` adds three
findings: `category="security"`, `severity="warn"`, `auto=False`,
`path=""`, evidence `trueup cannot read this setting; check it on the
platform`.

| Id | Control | action |
|---|---|---|
| `platform:branch-protection` | pull request and one review on the default branch, no force push, no deletion | `gh api -X PUT repos/OWNER/REPO/branches/BRANCH/protection -F 'required_pull_request_reviews[required_approving_review_count]=1' -F enforce_admins=true -F required_status_checks=null -F restrictions=null -F allow_force_pushes=false -F allow_deletions=false` |
| `platform:mfa` | two-factor authentication required for the organization | check: `gh api orgs/ORG --jq .two_factor_requirement_enabled`; the API cannot set it, so the action also names `https://github.com/organizations/ORG/settings/security` |
| `platform:least-privilege` | no collaborator holds more access than the work needs | list: `gh api repos/OWNER/REPO/collaborators --jq '.[] \| select(.permissions.admin) \| .login'`; lower one: `gh api -X PUT repos/OWNER/REPO/collaborators/USER -f permission=push` |

1. OWNER, REPO and ORG come from `git remote get-url origin` when it is a
   `github.com` URL (https or ssh form); BRANCH from `git symbolic-ref
   --short refs/remotes/origin/HEAD` without the `origin/` prefix. When
   either is not available, the placeholder stays in the text. The git
   calls are read only and use `--no-optional-locks` where the command
   takes it.
2. trueup never runs `gh` (I-31). A person who checks the `gh api` syntax
   by hand runs no `gh` command against a real repository from this code.
3. A person who has set a control adds a `[[keep]]` entry for its id.
4. A scoped run drops these findings (path is empty, D6.17).

## D7.10 — Security floor page (B9)

`docs/reference/trueup.md` gains a section `## Security floor` after the
health section. It has one table: `| Row | What it checks | OSPS Baseline
Level 1 control |`, one line per row: `lockfile`, `secret-file`,
`secret-content`, `secret-history`, the CI pins, osv-scanner, the SAST
sets, `health-security`, the install guard, the three `platform:*` rows.
The section names the OSPS Baseline version and date it cites, and the
exact control id per row. A row with no Level 1 control says `none at
Level 1` and names the level that has one, if any. The section also states
the gaps: tool rows (gitleaks, osv-scanner, gosec) that this machine did
not verify.

The reference page also gains: the `lockfile` and `secret-history` rows in
the findings tables, the lockfile pair table (from `_LOCK_PAIRS`), the
`secrets <engine>` report line, the gitleaks managed file and hook, the
install guard in the Hooks section, the new health cells (D7.6). The skill
(`skills/trueup/SKILL.md`) gains the same facts in its own words: the
`secrets` line, the install guard and its three outcomes, the platform
rows and their keep entries, and question item 3.

## D7.11 — Failure analysis

The breaking scenario: **a managed file that depends on the machine.** An
obvious design adds the gitleaks hook "when the binary is present".
`render` then becomes a function of `PATH`. The developer's machine has
gitleaks, the CI runner has not (or the reverse), and each side reports
`file-managed:.pre-commit-config.yaml` against the other side's file
forever. This design survives it: the hook text is the same on every
machine and tests for the binary at run time (D7.3 rule 9), and I-33 makes
the rule explicit and testable (render twice with `shutil.which` patched
to both answers; same bytes).

Other failure modes, and the answer:

- **npm records are large.** A popular package's record is tens of MB; a
  2 s budget cannot read it. The byte cap turns size into the answer
  "old" (D7.8 rule 1).
- **Guard false positive on quoted text.** `echo "pip install x"` is one
  token after `shlex.split`, so no segment starts with `pip`. A command
  that `shlex` cannot split (unbalanced quote) is not checked.
- **A fixture secret blocks a push or fails the history scan.** No
  committed file holds a matching string (D7.3 rule 10); `ignore` globs
  flow into the gitleaks allowlist (D7.3 rule 8).
- **Baseline churn when gitleaks is installed later.** Working-tree ids
  keep the built-in shape. History ids appear only in history mode, which
  both the baseline writer and the gate use.
- **gitleaks prints the secret.** `--redact` is on in every call, and
  trueup reads neither `Secret` nor `Match`. A test checks the report and
  the standard output for the assembled secret (I-30).
- **The guard blocks the session when the network is down.**
  `Unreachable` gives no decision; the 5 s budget bounds the delay.

## D7.12 — Alternatives

- **The gitleaks hook only when the binary is present.** Rejected: render
  depends on the machine (D7.11).
- **The upstream gitleaks pre-commit repo (`language: golang`).**
  Rejected: every other hook is `language: system`, and it needs a Go
  build on each machine.
- **Explicit `allow` when the registry is down.** Rejected: it skips
  Claude Code's own permission prompt.
- **Exclude secret files from gitleaks.** Rejected: those files hold the
  leaks.
- **Env vars that point the registry at a fake server.** Rejected: a
  setting that only tests need. Tests patch `registry.BASE_URLS` and run a
  local `http.server`.
- **A full packument parse for npm.** Rejected: size; the cap answers the
  question that matters.
- **SECURITY.md at T0 only.** Rejected: no reason for a T1 gap (D7.6).

## D8.1 — First-run refcheck parity

`check` runs the bundled checker with the `ref_check.toml` that `apply`
would write for the config in force, not with the file on disk.

- `managed.render_ref_check_config(cfg)` is the one source of that text.
  `render` uses it, with the `[keep]` table, for the managed file, and
  `docrules._refcheck_findings` uses it, without that table, for the run
  (D9.2).
- `docrules_findings` builds the config in force with
  `managed.effective_config(cfg, survey)`, writes the text to a file in a
  temporary directory outside the root, and runs the checker with
  `--config <that file>`. The root gets no file (I-18).
- `ref_check.py` gains the flag `--config FILE` (`--config=FILE` is the
  same flag). `load_config(root, path)` reads `path` in place of
  `root/ref_check.toml`. A named file that is absent gives exit 2. A
  relative law archive still resolves against the root. The `checks off`
  notice follows the file that was read. `--config` names a file; it does
  not select a check, so D2.3's rule holds.
- The temporary directory is the system's (`tempfile`), the same as the
  gitleaks report of D7.3. A `TMPDIR` set to a directory inside the root
  puts the short-lived file inside the root for the length of the run;
  trueup does not guard against that setting.
- `trueup refs` and the `ref-check` pre-commit hook keep reading the
  target's own `ref_check.toml`. After `apply` that file is the rendered
  text, so all three agree.

Effect: the `refcheck` row before the first `apply` equals the row after
it. On target-rust/src the first `check` gave 4 findings and the second 243; the
plan the person approves is now the plan `apply` leaves behind. A
repository with no README now gets `refcheck:README.md:1:no-readme` next
to `health-readme`, as it does after `apply`.

## D8.2 — Nested repository boundary

The scanner does not enter a directory below the root that holds its own
`.git` entry, a file (a submodule) or a directory (a plain clone). The
docs page list of checks g and h applies the same rule. This is the
boundary `git ls-files` draws for the survey, so the `refcheck` row and
the other rows see the same files. Each nested repository is its own
target with its own checker run. The rule is a property of the tree, not
a configuration key, so I-2 holds. `trueup refs` uses the same walk.

## D8.3 — Managed manifest and the install note

Replaced by D14.7 and D14.8 (2026-10-16).

- The `lockfile` row gives no finding for the manifest at
  `lint/typescript/package.json` when its text is a JSON object with
  `"_managed": "trueup"`, the marker `managed._mark_json` writes. The
  marker in a project's own manifest at another path exempts nothing. Its packages are the tools of
  the eslint hook, installed under `lint/typescript/node_modules` with
  `npm install --prefix lint/typescript`, not dependencies of the
  project. `hygiene.py` reads the marker by shape, since `managed.py`
  imports `hygiene.py`.
- trueup cannot ship the lockfile: writing one needs the registry, and
  trueup never opens the network outside the install guard (I-28).
- When TypeScript or Vue is on and `lint/typescript/node_modules` is
  absent, `managed._tool_findings` adds the `info` finding
  `tool-missing:typescript/node_modules`. Its action names the install
  command, says it uses the network, and asks for a `node_modules/` line in
  `.gitignore`. trueup never runs the install.

## D8.4 — Quoted-list rule

A Markdown block that states the vocabulary rule quotes the banned words;
it does not use them. The block gives no `prose` finding.

- A block is a list item or a paragraph. A list item starts at a bullet
  or a number and continues over each indented line, a nested item
  included, and over a blank line that an indented line follows (a loose
  item). It ends at a line with no indent: a new item starts a new block,
  any other line starts a paragraph. A paragraph starts at a line with no
  indent that is not an item, and continues over every line up to a blank
  line, bullets and numbers included, so a lead-in sentence keeps the list
  it introduces. A heading, a block quote and a table row (`#`, `>`, `|`
  first) are neutral: they end a block and belong to none.
- A block quotes the list when one of its first three lines matches
  `\b(?:banned|never use|do not use|don't use|forbidden|prohibited|not allowed)\b`,
  case-free. `docrules._drop_quoted_blocks` blanks such a block before the
  word scan. A block with no cue in that window keeps the plain rule, also
  when another block of the page has a cue.
- The Vale template's `[*.md]` section holds the same rule as two
  `BlockIgnores` regexes, one per block kind, with the same cue
  alternation and the same three-line window. Vale runs `BlockIgnores` on
  a backtracking engine (it accepts lookahead, and an unbounded window
  took minutes on this repository's architecture page), so the window is
  what keeps the hook fast; the value holds no comma, because Vale splits
  the setting on commas. `tests/conftest.py` holds a table of twenty-one
  block shapes; one test runs it through `check` and one through a real
  `vale` run, and both fire on the same lines.
- The rule is for Markdown only. Vale's `BlockIgnores` does not apply to a
  code format, so a source comment keeps the plain rule in both engines.
- The hint line of D6.9 stays for a page that quotes the list with no cue.

Measurement (2026-10-07, `.state/runs/fix-target-rust-findings/00-evidence.md`):
over target-rust, trueup, target-mixed/src and about 600 community plugin pages, every
block with a cue was a quote, and no real use had a cue. A count rule (3 or
more distinct words in a block) also had no false negative, but Vale cannot
count, so the two engines would disagree. Known gaps, the
same in both engines: a quoted mention in double quotes with no cue still
fires; a real use in the same paragraph as a cue (`This is slop. Never use
it.`) is silent; a heading, quote or table row that holds a cue keeps the
plain rule.

## D8.5 — Verb-only forms: underscore and leverage

Two form entries of `trueup/data/banned.txt` change (D6.9 shape):

- `underscore => underscor(?:es|ed|ing) (?:the|a|an|its|their|our|this|that|these|those|your|his|her|my|it|them|every|all|how|why|what|by)|underscore (?:the|a|an|its|their|our|this|these|those|your|his|her|my|it|them|every|all|how|why|what)`.
  Every verb form needs a following determiner, pronoun, question word or
  `by`. The bare form `underscore` takes no `that` and no `by`: `a leading
  underscore that marks a private name` is the noun. The noun, singular or
  plural (`two underscores`, `leading underscores`), is silent. D6.9
  accepted the plural noun as a residual risk; the target-rust run hit it, so this
  design removes it.
- `leverage => to leverage|leverag(?:es|ed|ing)|(?:we|you|they|i|can|could|will|would|should|must|may|might) leverage|leverage (?:the|a|an|its|their|our|this|that|these|those|your|his|her|my|it|them|every|all|existing|new|modern|both|each|some|any|AI|LLMs?|machine learning)`.
  A subject or auxiliary before the word (`we leverage Redis`), a
  determiner or pronoun after it, or an inflected form marks the verb. The
  noun (`more leverage on the bolt`) is silent; `exposure to leverage` is
  the one noun shape that still matches.

Both `Banned.yml` copies carry the same patterns (I-25). The `harness` row
keeps its shape. A residual risk stays for the three rows: a noun followed
by a determiner (`the harness the tests use`) matches, because RE2 has no
lookbehind, and the Vale copy must read the same regex.

## D8.6 — Vale source extensions

The Vale template's source section names the extensions Vale lexes as
code: `py`, `rs`, `ts`, `tsx`, `js`, `jsx`, `go`, `php`. For `mjs`, `cjs`,
`mts`, `cts`, `sh`, `sql` and `vue` Vale has no comment lexer: it reads the
whole file as prose, string literals included, and no `[formats]` mapping
or `Lang` key adds a lexer (a mapping to `js` gives no alert at all, a
mapping to `javascript` gives plain text again). The section leaves them
out, and the Vale hook's `types_or` names the same languages; pre-commit
tags `.mjs` and `.cjs` as `javascript`, so the hook still hands them to
Vale, where no section matches and no alert comes. The `prose` row of
`check` reads the comments of all eight languages, so those files are still
checked, by `check` alone.

## D8.7 — `[refs] local_tags`

`trueup.toml` gains the key `[refs] local_tags`, a list of uppercase
prefixes, the shape `ref_check.py` checks for `[registry] local_tags`
(`[A-Z]+`; a test keeps the two patterns equal, since `config.py` does not
import the checker). `config.render` writes the `[refs]` table when `path`
is not the default or `local_tags` is not empty.
`managed.render_ref_check_config` appends `[registry]` with the list, so
`apply` renders it into the managed `ref_check.toml`, and `check` runs with
it from the first run (D8.1). A hand edit of the managed `ref_check.toml`
is an automatic `file-managed` error and the next `apply` drops it, which
is why the key lives in `trueup.toml`. The action of an `unregistered`
`refcheck` finding names the key.

## D8.8 — Superrepository guidance

A root with a `.gitmodules` file is a superrepository. Each submodule is
its own target: its own survey, tier, `trueup.toml` and managed files. The
superrepository is a target too, for its own files. Snapshot copies of a
submodule's sources (run records under `.state/`, `pre/` trees) give
`duplicate`, `binary` and `lockfile` findings and a tier from the copied
manifests; the skill proposes `ignore` globs for them first. A manifest
under an `ignore` glob leaves the survey, so it does not pick the tier. The
tier rule itself does not change: on target-rust, 4 of the 10 copied manifests sat
under `docs/features/*/pre/`, not under a dot directory, so a dot-directory
rule would not have helped.

## D8.9 — Alternatives

- **An `info` finding that names the checks `apply` will switch on
  (D8.1).** Rejected: the plan would still change size after `apply`.
- **Import the checker and call `run` in process (D8.1).** Rejected: the
  fold-in runs the checker as a child process in the target root, and the
  tests prove that with stand-in scripts; one flag keeps that shape.
- **Ship a lockfile beside the managed `package.json` (D8.3).** Rejected:
  writing one needs the network (I-28), and a stale lockfile pins old
  tool versions for every target.
- **A count rule for the quoted list (D8.4).** Rejected: Vale cannot count
  distinct words, so `check` would pass a page the Vale hook fails.
- **`[formats] mjs = js` in the Vale template (D8.6).** Rejected: Vale then
  gives no alert for the file at all, a silent skip.
- **A dot-directory rule for manifests in the tier (D8.8).** Rejected: the
  target-rust copies sat under `docs/` too; `ignore` globs cover both.

## D9.1 — Checker modes

Amended by D14.5 and D14.8 (2026-10-16): `trueup` makes the checker
config text from `trueup.toml` at each run, and a target in global mode
keeps no checker file.

`trueup.toml` gains `[refs] mode`, `"global"` (the default) or `"copy"`.

- **global.** The target holds no checker copy. The `ref-check` hook runs
  `trueup refs --root .` with `language: system`, as every other tool hook
  does. `render` has no checker entry, and the Python `ruff-format` hook
  has no `exclude`. `check` adds the `info` finding `tool-missing:refs/trueup`
  when `trueup` is not on the path; its action names
  `uv tool install --editable <plugin root>` (`pipx install <plugin root>`
  also works) and says that the hook runs `trueup refs`. A file at
  `ref_check.py` of the root gives the `info` finding
  `refs-copy:ref_check.py`: nothing runs it in this mode, and the person
  deletes it when it is trueup's old copy (`git rm ref_check.py`). `apply`
  removes nothing it did not write in the same run. `[refs] path` with
  this mode is a configuration error (exit 2): the key has no effect
  without a copy. `render_ci` adds one comment line below the install
  marker of the CI workflow that names the hook and asks for an install of
  trueup from its git source; no install command can be rendered, because
  trueup has no package source, and I-33 holds: the line is a function of
  the config.
- **copy.** The behaviour before this design: `apply` writes the bundled
  checker at `[refs] path` (default `ref_check.py`), the hook runs
  `python3 <path> --root .`, `ruff-format` excludes the path, and the copy
  is a managed file (D9.3). This repository uses it with
  `path = "trueup/ref_check.py"`: its copy is the source.

Why global is the default: the owner asked for one checker on the machine,
not a copy in each repository (2026-10-07). One editable install follows
the trueup working tree, so every target's hook runs the same version, and
no target needs a hand merge at each update. Why copy stays: this
repository, and a target whose CI, or another machine, cannot install
trueup. trueup has no git remote yet, so no CI can install it today. The
person picks the mode in `trueup.toml`; the skill does not ask, because
`tool-missing:refs/trueup` and `refs-copy` guide the first run.

## D9.2 — Kept failures in `ref_check.toml`

The hook and `check` must agree on the findings a person declined.
`ref_check.toml` gains the table `[keep]` with the key `failures`, a list
of failure ids.

- A failure id is `<path>:<line>:<kind>`, plus `:<tail>` when two failures
  of the run share that text (the tail is the detail after its last `: `,
  each run of white space or commas written as `-`), plus `:<n>` when ids
  still repeat, counting from 1 in sorted order. `ref_check.failure_ids`
  gives the ids of a sorted failure list. `docrules` builds its
  `refcheck:` ids with the same function, on `Failure` records parsed
  from the printed lines, so the id in a `[[keep]]` entry is `refcheck:`
  plus the checker's own id.
- `run` moves each failure whose id is in `[keep] failures` from
  `Report.failures` to `Report.kept`, both sorted. `main` prints and
  counts only `failures`, so the exit code is 0 when every failure is
  kept, and it adds the notice `ref_check: kept: <n>` on standard error
  after the other notices. The pytest entry points read `failures`, so
  they agree with the command line.
- `managed.render_ref_check_config(cfg, keep=True)` writes the table from
  the `[[keep]]` ids that start with `refcheck:`, prefix removed, sorted;
  with no such id the table is absent. `render` uses `keep=True`, so
  `apply` writes it, and a `[[keep]]` entry added by hand makes
  `file-managed:ref_check.toml` an automatic finding that the next
  `apply` carries out, as the Vale `exclude` of D5.6 does. `check` runs
  the checker with `keep=False` and applies `[[keep]]` itself, so the
  report still lists the kept findings under `Kept`.
- I-2 holds: an id names one failure line. The file is still scanned, and
  every other failure of that file is reported.

## D9.3 — The checker copy carries the managed header

Line 1 of `trueup/ref_check.py` is the managed header, before the module
docstring. `apply` still writes the file byte for byte (I-26), so every
copy it writes carries the header. `_file_finding` compares the copy by
bytes: equal gives no finding; different with the header on line 1 gives
an automatic `file-managed` error that `apply` rewrites; different with no
header gives the manual warn, which is now the case of a person's own
file, or of a copy that an earlier trueup wrote before this design.

Why: a copy from before an update of the checker is not an edit. The target-rust
run of 2026-10-07 showed that every checker update turned into a hand
merge in every target. A hash of the written copy in `trueup.toml` was
rejected: it adds a key and a write of `trueup.toml` for the answer the
header already gives. The header is a comment line: ruff reads the module
docstring after it, the Python reader of D1.2 finds no marker in it, and
the legacy selftest of D1.7 copies the file as it is.

## D9.4 — `[refs] layout`

`trueup.toml` gains `[refs] layout`, `true` (the default) or `false`.
`render_ref_check_config` writes `[checks] layout = false` when the value
is `false` or `docs` is `readme`; `check` runs with it from the first run
(D8.1), and the hook follows after `apply`.

Trade-off: with `false`, every page rule of check h is off for the whole
repository (no `no-front-matter`, `bad-field`, `misplaced`, `unindexed` or
`duplicate-id` failure), also for a page added later. One `[[keep]]` entry
per page keeps the rule for new pages, but it costs one entry per page and
cannot serve a page a tool regenerates (target-rust's `docs/traceability.md` loses
its front matter at each regeneration). A path glob that exempts pages
from check h only is rejected: the amended I-2 (2026-10-16) allows one
path key, `[scan] ignore` from `trueup.toml` `ignore`, and that key takes
the path out of every check and every trueup finding, not out of check h
alone. A page that no tool should read at all goes under `ignore`. A page
that stays a page keeps `layout = false` or a `[[keep]]` entry. `docs = "readme"` stays wider: it also drops the
`changelog`, `superseded` and `stale` rows, the Vale style, and check i.

## D9.5 — eslint 10

The eslint package templates ask for `eslint ^10.0.0` and for the plugin
versions whose peer range names eslint 10 (registry, 2026-10-07):
typescript-eslint `^8.71.0`, eslint-plugin-jsdoc `^65.2.0`,
`@eslint-community/eslint-plugin-eslint-comments` `^4.8.1`,
eslint-plugin-sonarjs `^4.2.2`, eslint-plugin-vue `^10.11.1`,
vue-eslint-parser `^10.4.1`, vue-tsc `^3.3.0`, knip `^6.40.0`.
`eslint-plugin-security ^4.2.0` declares no eslint peer and stays.
`typescript` stays `^5.7.0 || ^6.0.0`, the range typescript-eslint
accepts (`<6.1.0`); TypeScript 7 is out of that range. eslint 9 is in
maintenance, and its last releases are deprecated on the registry ("no
longer supported"). `lint/ts/package.json` of this repository follows the
clean template plus sonarjs and vue, so the eslint tests of D6.13 run on
eslint 10. eslint 10 needs Node 20.19, 22.13 or 24 and later; the
`tool-missing` row reads the path only, not the Node version. A test keeps
the four package fragments on one eslint range, with major 10.

## D9.6 — clippy: `missing_docs` stays in clean, `--keep-going`

`missing_docs` stays in the clean clippy entry: D1.5 names it as a rule
the comment standard needs, the research page sets it for clean and
strict, and the Python clean set enforces the same rule with ruff `D`.
Both clippy entries gain `--keep-going`. A `-D` lint is a compile error,
so a crate that fails hides every crate that depends on it; without the
flag cargo stops scheduling after the first failure, so the set of checked
independent crates depends on timing (measured 2026-10-07 on a
three-crate workspace: `a` fails, `b` depends on `a`, `c` is independent;
`b` is never checked). With the flag every crate that does not depend on
a failing crate is checked. The dependents stay hidden until the failing
crate is fixed; the skill says so in its Verify step, and tells the person
how to see the full count before any fix: run the hook's entry with `-W`
in place of each `-D`, so every crate compiles and every lint prints as a
warning. `trueup check` runs no target command (I-18), so the report
cannot count them.

## D9.7 — Alternatives

- **A pre-commit hook repository for the checker (D9.1).** Rejected:
  trueup has no remote and no tag. A local path as `repo:` works
  (pre-commit 4.6.2 cloned it at a sha and ran the hook, 2026-10-07), but
  it binds the managed file to one machine, and a sha `rev` makes every
  target drift at each trueup commit.
- **`trueup refs` reads `[[keep]]` itself (D9.2).** Rejected: the copy
  mode hook runs the checker with no trueup, so the hook and `check` would
  still disagree there.
- **The checker reads `[[keep]]` from `trueup.toml` (D9.2).** Rejected:
  `check` could then not list the kept findings, and `--config` would read
  two files.
- **A hash of the written copy in `trueup.toml` (D9.3).** Rejected above.
- **`[refs] checks_off = [...]` (D9.4).** Rejected: nothing needs a second
  switch yet; a boolean per switch is additive.
- **`-W missing_docs` in clean (D9.6).** Rejected: `-D warnings` turns it
  back into an error, and the standard needs the rule.
- **A rendered `pip install` line for trueup in CI (D9.1).** Rejected:
  trueup has no package source, and `pip install trueup` would fetch an
  unrelated package of that name.

## D10.1 — Organizer role

trueup is an organizer that reports first. `check` says what is out of
place and where it belongs. `apply` removes copies and junk by automatic
ids. It moves a page only by a `move:` id that the person names (I-34).
S1 stays true: nothing moves without approval.

The brief changes as follows:
- Goal 1 adds: each page, copy and junk file goes where the standard or
  the history of the repository says it belongs.
- Tool configurations still never move. A misplaced page moves on an
  approved `move:` id from the move plan (D10.6, D10.7).
- The `scratch` row removes a copy of a tracked file that has a scratch
  or copy name (D10.3).
- S23 (convergence) and S24 (metamorphic) are new. See D10.10.

I-23 and the `apply.py` module docstring also change: `apply` runs git
only as `rm`, `rm --cached`, `mv` and read-only commands.

## D10.2 — The `doc-misplaced` row

The hygiene rule `doc-misplaced` has category `files`, severity `warn` and
`auto=False`. Its id is `doc-misplaced:<path>`. Each page gives one
finding, also when the move unit is a directory (I-36).

A surveyed file is a candidate when all of these are true:
- its name ends in `.md` or `.markdown`;
- no path segment is `docs`. A `docs/` at any depth is a docs tree;
- it is not a standard root page at the root: `README`, `CHANGELOG`,
  `CONTRIBUTING`, `LICENSE`, `SECURITY`, `CODE_OF_CONDUCT`, `AGENTS`,
  `CLAUDE`, `SUPPORT`, `ACCESSIBILITY` or `pull_request_template`, each
  with `.md`. The match is exact and ignores case. The guard's `README*`
  glob is not used, because it matches `README.old.md`. The same name in
  a subdirectory gets no exemption from this item. The last three are
  GitHub community health pages that GitHub reads at the root, see the
  GitHub table of the reference page;
- it is not a page in the root `PULL_REQUEST_TEMPLATE/` directory, the
  place where GitHub reads more than one pull request template;
- it is not a root file that a `[root] allow` glob of `trueup.toml`
  names. The match is `fnmatch.fnmatchcase` on the path, the same match
  that the `scratch` row uses for a root file. A path in a subdirectory
  gets no exemption from this item. `_is_candidate` takes the globs as
  the keyword argument `root_allow`, and `locate` gives it
  `cfg.root_allow`;
- its basename is not `README.md`, `CHANGELOG.md` or `SKILL.md` in any
  directory;
- no path segment starts with `.`;
- no segment is `fixtures`, `testdata`, `__snapshots__`, `vendor`,
  `third_party` or `node_modules` (the fixture set of D6.12);
- `hygiene.scratch_looking` (D12.11) does not accept it, so the `scratch`
  row (D10.3) would not flag it. Each path gets one remedy.

One remedy for each path is also true between `scratch` and `artifact`:
a path that the `artifact` row flags gets no `scratch` finding (D10.3).

The rule runs at both docs levels and with each `[refs] layout` value.
`layout = false` stops the type-folder and front-matter rules inside
`docs/` (D9.4). It does not let a page stay outside `docs/`. A `[[keep]]`
entry keeps a page where it is: the page gets its finding, which the plan
then leaves out, and it gets no move (D10.6). A `protect` glob only stops
the move: the finding stays in the plan.

The evidence starts with `Markdown page outside docs/`. When a move of
D10.6 covers the page, the evidence continues with `; <move id> to
<target> (<basis>: <evidence>)`, and the action is `approve <move id>`.
When no move covers the page, the evidence continues with `; ` and one
reason, and the action is `add a [[keep]] entry`. The reasons are:
- `protected`: a `protect` glob stopped the move (I-38);
- `a [[keep]] entry keeps it in place`: the `doc-misplaced` id of the
  page is a keep id (D10.6). The plan leaves this finding out, so only
  the `## Kept` section of the Markdown report shows this text;
- `target <target> exists, move it by hand`: a file or a directory is at
  the target in the work tree now (D10.6);
- `target <target> is claimed by more than one page`: the target is
  shared (D10.6);
- `the move plan comes from a full check`: the check is scoped (D10.12).

A scoped check (an `only` set) gives a finding only for a candidate in the
set.

`trueup/layout.py` holds the rule and D10.6. `trueup/apply.py` holds
D10.7. `report.collect` calls `layout.locate` after `hygiene_findings`
and `docrules_findings`, because it needs the refcheck
broken links. It then applies the evidence notes of D10.6, runs the drift
rows, and then runs `protect_findings`.

## D10.3 — Scratch names

`looks_scratch(basename)` keeps its signature and adds these patterns:
- **Backup in the extension chain.** A suffix after the first `.` is
  `.old`, `.bak`, `.orig` or `.backup`: `README.old.md`, `x.bak.py`.
- **Copy suffix, documents only.** The extension is in
  `_SCRATCH_WORD_SUFFIXES` or is `.rst`, and the stem ends in one or more
  of `[_-](v\d+|draft|copy|old|backup)`, or in ` copy( \d+)?`:
  `ARCHITECTURE_v2_draft.md`. A source extension never matches, so
  `v0_v1.rs` gives no finding.
- **Scratch prefix, any extension.** The stem is `scratch` or
  `untitled`, then only digits, or a `-`, `_` or space and more text:
  `scratch_fold.rs`, `untitled2.py`. `scratchpad.rs` gives no finding. `tmp`,
  `temp` and `notes` stay limited to document extensions, so
  `template.py`, `notes_service.py` and `tmp_file.rs` give no finding.

`looks_scratch_path(path)` returns `looks_scratch(basename)`, or true when
the first segment is `tmp`, `temp` or `scratch`. `_scratch` uses it. The
guard hook uses `looks_scratch` only. It gets the new name patterns but
not the directory rule, because an ignored local `tmp/` is common and
`check` finds a tracked one.

**Exemption (D10.12).** `_mentioned_elsewhere(basename)` becomes
`_referenced(path)`. A file is exempt only when another surveyed text file
F holds one of these:
- the path of the file relative to the directory of F,
  `relpath(path, dir(F))`. This covers a Markdown link, and a root
  `Makefile` line `rm tmp_notes.txt` for a root file;
- the full repository path of the file, when that path holds a `/`.

A bare basename in a file in another directory does not exempt a file.

**One remedy.** `_scratch` gives no finding for a path that `artifact`
flags: a file id, or a path under a directory id. The `artifact` remedy
covers that path. So a tracked `tmp/out.pyc` or `scratch_1.pyc` gives
one `artifact` finding and no `scratch` finding. `hygiene_findings` runs
`_artifact` first and gives its paths to `_scratch`. The last-copy group
below keeps its input: only the `scratch` findings that `_scratch` gives
are filtered.

**Last copy (I-35).** `_scratch` groups the surveyed files by content
hash, at any size. The 64-byte minimum of `duplicate` does not apply here.
In a group that holds a `scratch` path, a member is kept when `scratch`
does not flag it and it is not under a path or a directory that
`artifact` flags. When no kept member is tracked, the first sorted
`scratch` finding that is automatic gets `auto=False` and the evidence
`the last copy of this content`. A `scratch` finding on an untracked file
is already manual, so it does not take this place.

The rule applies to one plan. `apply --all-auto` collects a new plan
before each pass. When one pass removes the other copies, the next pass
sees the last copy as a scratch file with no copy, and its id is
automatic. So one `--all-auto` run can remove the last copy. The skill
tells the person to examine the scratch copies before `--all-auto`.

**Copies.** `_duplicate` removes each path that `scratch` or `artifact`
flags, and each path under a directory that `artifact` flags, before it
selects the original. When a group also holds a kept member, each
`scratch` evidence in the group gets `; copy of <original>`, where the
original is the first sorted kept member. The last-copy evidence replaces
this text. The `scratch` row removes the file with `git rm` by an
automatic id, so no new rule is necessary. A pair where no side is
scratch stays a manual `duplicate` warning.

## D10.4 — `dist/` and `build/`

`_artifact_directory(parts, has_cargo, has_manifest)` counts `dist/` and
`build/` as build output when a root file has a name in
`survey.MANIFEST_NAMES`. `target/` still needs `Cargo.toml`.

When an artifact directory holds a tracked `*.md` or `*.markdown` page,
its `artifact`
finding gets `auto=False`. The evidence adds `; holds <page>`, with the
first such page in survey order. A blanket `git rm --cached -r` does not
untrack the page. The action stays the same. When the page is out of the
directory, the next `check` gives the automatic finding again.

Only a page that `layout._is_candidate(path, scratch_paths)` accepts
counts (D10.2, D12.11). `scratch_paths` holds each surveyed path for
which `hygiene.scratch_looking(path, cfg)` is true, so a scratch-looking
page does not make the finding manual. `_artifact` gives no `root_allow`. So a package `README.md`, or
a page under `node_modules`, `vendor`, `third_party` or a segment that
starts with `.`, does not make the finding manual. A tracked
`node_modules/` with package READMEs is an automatic
`artifact:node_modules/` finding. A tracked `dist/guide.md` beside a
manifest still makes `artifact:dist/` manual. `hygiene` imports `layout`
at module level. `layout.locate` imports `scratch_looking` from `hygiene`
inside the function body, to avoid a circular import (D12.11).

## D10.5 — `.gitignore` coverage

`_handle_untrack` serves the `artifact` and the `secret-file` rows. After
the `git rm --cached` step and before it calls `_append_lines`, it runs
`git check-ignore --no-index -q -- <finding path>`. The finding path is
`<dir>/` for a directory and `<path>` for a file. Exit 0 means that a
line already covers the path, so nothing is added. Each other exit code
means that `_append_lines` runs. `--no-index` makes the result
independent of the index: without it, git reports a tracked path as not
ignored.
`managed.missing_gitignore_lines` has the same literal-line gap
(`.scratch/` against `/.scratch/`). It is reported and not changed.

## D10.6 — The locator and the move plan

`layout.locate(root, survey, cfg, findings, only=None)` returns a
`LayoutResult`:

```python
@dataclass(frozen=True)
class Move:
    id: str            # "move:<source>"; source ends in "/" for a directory
    source: str
    target: str
    kind: str          # "file" | "dir"
    basis: str         # "history" | "link" | "standard"
    evidence: str      # e.g. "renamed from docs/design/a.md in 1a2b3c4"
    pages: tuple[str, ...]   # the doc-misplaced pages the move covers

@dataclass(frozen=True)
class LayoutResult:
    findings: list[Finding]          # doc-misplaced
    moves: list[Move]                # sorted by id
    evidence_notes: dict[str, str]   # finding id -> text added to evidence
```

`findings` holds the findings that `hygiene_findings` and
`docrules_findings` gave. The locator reads the refcheck `broken-link`
findings from it. It finds the scratch-looking paths with
`hygiene.scratch_looking` (D12.11), not from the `scratch` findings. It
runs neither row again.
`locate` changes no file and runs only read-only git commands.

**Scoped mode.** When `only` is not `None`, only the candidates in `only`
give findings, with the reason `the move plan comes from a full check`.
`moves` is `[]`, `evidence_notes` is `{}`, and no git command runs.

**Evidence.** For each candidate, the locator tries these sources of
evidence in this order. The first source that gives an acceptable target
wins.

1. **History.** This step runs only when a candidate exists. `git diff
   --cached -M --diff-filter=R --name-status` gives the staged renames,
   and one `git log -M --diff-filter=R --name-status --format=%h` gives
   the committed renames. For each new path P, a staged rename wins over a
   committed one, and the newest commit wins over an older one. The old
   path O of P is the target. One hop is enough. A rename only places a
   candidate. It never makes a candidate. The evidence is `renamed from
   <O> in <hash>`, or `renamed from <O> in a staged change`. Both git
   commands run with `-c core.quotePath=false`, so a non-ASCII path comes
   back as written and not as a quoted octal string (D10.7).
2. **Link.** A refcheck `broken-link` finding names a missing target T.
   The locator removes the fragment and resolves T against the directory
   of the linking file. It then counts the surveyed paths that have the
   basename of T: each surveyed file and each directory that holds a
   surveyed file, candidate or not. When that count is not exactly one,
   the link gives no evidence.
   - A link that does not end in `/` names a file. When the one path with
     the basename is the candidate itself, T is its target.
   - A link that ends in `/` names a directory. When the one path with
     the basename is a directory S that holds a candidate, each candidate
     P under S that is still open gets the target `T + relpath(P, S)`.
   The evidence is `named by a broken link in <linking file>`.
3. **Standard.** A front matter `type` in `_PAGE_TYPES` gives
   `docs/<type>/<basename>`, with the evidence `the standard target for a
   <type> page`. With no type, with `layout = false`, or with `docs =
   "readme"`, the target is `docs/<basename>`, with the evidence `the
   standard target for an untyped page`.

**Acceptance.** A target from history or from a file link is accepted only
when all of these are true:
- the normalized POSIX path is relative: it does not start with `/`, and
  it has no `..` segment. A target outside the repository is refused;
- the survey does not hold the target now;
- the target has a `docs` segment, or is a standard root page at the
  root.

A directory target from a link is accepted only when it is relative with
no `..` segment, has a `docs` segment, and no surveyed file sits under it
now. When a target is refused, the locator tries the next source. The
standard target is always inside the repository. After the vetoes, a
target of each basis can still be refused because it exists (see
"Existing target").

**Units.** The locator tries each directory S that holds a candidate,
the shallowest first, so the largest S wins. S becomes one move of kind
`dir`, `move:S/` to `D/`, when all of these are true:
- S holds two or more open candidates, or one open candidate and a
  non-Markdown file;
- no file under S matches `protect`, no page under S is kept (see "Kept
  pages"), and no file under S is already in another directory move;
- each Markdown file under S is a candidate whose target is
  `D + relpath(page, S)`, for the same D;
- evidence places each non-Markdown file under S at
  `D + relpath(file, S)`: history renamed it from that path, or a broken
  link names that path or a directory that holds it. The standard places
  pages only, never the code or the assets beside them;
- no surveyed file sits under D now, and no other move puts a page under
  D.

The non-Markdown files of S move with it. The basis and the evidence of
the move are those of the first page in sorted order. Each candidate that
no directory move takes gets its own move of kind `file`.

**Vetoes (I-38).** When the source, the target or a parent directory of
either matches `protect`, the move is not proposed. The `doc-misplaced`
evidence then says `protected`. A directory that holds a protected file
never becomes a unit, so a directory move never carries a protected file.

**Kept pages.** `locate` reads `cfg.keep`. A candidate whose
`doc-misplaced` id is a keep id gets its finding, with the reason `a
[[keep]] entry keeps it in place`, and no move. `build_plan` leaves the
finding out of the plan. For units, a kept page counts as a protected
file: a directory that holds a kept page never becomes a unit, and the
other pages of that directory get file moves. So `CheckRun.moves` never
holds a move for a kept page, and no broken-link note names a kept page
(see "Broken-link evidence").

**Existing target.** After the vetoes, the locator refuses each move
whose target exists in the work tree now (`os.path.lexists`), for each
basis and each kind. `git mv` onto a file fails, and `git mv` onto a
directory puts the source inside it. The `doc-misplaced` evidence of each
page of the move then ends with `; target <target> exists, move it by
hand`. A directory target keeps its `/` in this text.

**One target, one move.** After these checks, the locator groups the moves
by target. A file target that is inside the target of a directory move is
in the group of that directory target. When a group holds more than one
move, the locator drops each move in the group, for each basis. The
`doc-misplaced` evidence of each page in the group then says `target
<target> is claimed by more than one page`. `git mv` cannot put two
sources on one target, and a first-wins rule would pick a page at random.

**Broken-link evidence (I-39).** The notes are made after the move plan is
final:
- When the resolved target T of a `broken-link` finding is the target of
  a move, `evidence_notes[id]` is `the target is now at <source>; approve
  <move id>`.
- Else, when exactly one surveyed file has the basename of T and that
  file is not a candidate, the note is `a file with this name is at
  <path>; fix the link`. This note is a hint. A link fix is never a move
  id, so each plan has one remedy. This note is also made when there is
  no candidate.

A kept page has no move, and it is a candidate, so a broken link to the
place of a kept page gets neither note.

`collect` appends each note to the evidence of its finding, after `; `,
with `dataclasses.replace`. The finding ids and the checker detail do not
change.

**Report.** `CheckRun` gets `moves: list[Move]`. A move is not a finding.
It is not in the plan, and the score does not read it. The Markdown report
prints `## Move plan (n)` after `## Plan` and before `## Kept`, one line
for each move: `- move:<source> → <target> (<basis>: <evidence>)`. D12.3
adds the box: the line is now `- [ ] move:<source> → ...`. When
the move plan is empty, the section is not printed. The JSON report adds
`"moves"` (D10.12).

## D10.7 — The `move` handler

`apply --ids` accepts `move:` ids. `_validate_moves` checks them against
`run.moves` of the first `collect`, not against the plan. The other ids
go to `_validate` as before. When an id fails either check, `apply`
prints each error, then `nothing written`, and exits 2 before any file
changes. A `move:` id that is not in the move plan gives `<id> is not in
the current move plan`. One `--ids` can mix `move:` ids and plan ids: the
plan ids run first, then the moves, in the order of the move plan.
`--all-auto` never reads `moves`: its three filters see only plan
findings, so I-34 is true by structure. `--ids` and `--all-auto` stay
exclusive (D5.11).

For each approved move, `apply` does these steps:

1. It reads each tracked Markdown file, `*.md` or `*.markdown` (the
   suffixes of `_is_candidate`), before the move, so each rewrite sees
   the tree before the move.
2. **Link rewrite.** `map(p)` is the new path of `p`: the target for the
   source of a file move, a prefix replace for a directory move, and the
   same path for each other path. The prefix of a directory move ends in
   `/`, so `misc/` maps `misc/a.md` but not `miscellany.md`. For each
   tracked Markdown file F, at its
   old location `old(F)` and new location `map(old(F))`, `apply` reads
   each relative link L: an inline link, an image or a reference
   definition. It uses the regular expressions, the fence rule and the
   code span rule of ref_check's `_md_links`. It skips a scheme, a link
   that starts with `#` or `/`, a link in a fenced block, and a code span.
   It decodes a percent escape before it resolves the path.
   - `t = normpath(join(dir(old(F)), path(L)))`.
   - When `t` did not exist before the move, the link was already broken,
     and it does not change. After a move back, that link resolves again
     with no rewrite.
   - The canonical form is `c = relpath(map(t), dir(map(old(F))))`, with
     a trailing `/` when the link has one.
   - When F does not move (`map(old(F)) = old(F)`) and the link still
     resolves to `map(t)`, it does not change. So a hand-written form
     such as `sub/../b.md` stays in a file that does not move.
   - When F moves, the link does not change only when its path, with one
     leading `./` removed, equals `c`. So `./b.md` stays `./b.md`. A link
     that still resolves but is not in the form `c` is rewritten to `c`.
     Two moves that undo a scramble then give the tidy text back byte
     for byte (I-37).
   - Else `apply` writes `c`. It encodes the path again, keeps the
     fragment, and changes only the destination characters. The link
     text, a reference label, a title and the rest of the line stay the
     same.
3. A file that matches `protect` is not rewritten (I-38). Each line of it
   that has a link the move changes is printed as `left broken: F:line`.
4. It makes the parent directory of the target, then runs `git mv
   <source> <target>`. For a directory, the paths have no trailing `/`.
   It prints `moved <source> to <target>`, then writes each rewritten
   file at its new path.
5. Each tracked file that is not Markdown (`.md` or `.markdown`) and
   holds the source path (`git -c core.quotePath=false grep -n -F`) is
   printed as `code mentions <source>: file:line`. It does not change.
   The search text is `Move.source`: `<source>/` for a directory move,
   `<source>` for a file move. So a bare name such as `misc` in code is
   not a mention of the directory move `move:misc/`.

When `git mv` fails, `apply` prints `failed <move id>: <error>`, runs the
other moves, and exits 1.

**Paths from git.** Each git command of `apply` and `hygiene` that lists
paths reads them unquoted. `git ls-files -z` gives paths split on `NUL`:
`hygiene._tracked_paths`, step 1 above, and the `git ls-files -- <dir>/`
that lists the files of an `artifact` directory for its protect check in
`_handle_untrack` (I-24). `git log`,
`git diff --name-status` (D10.6) and `git grep` (step 5) run with `-c
core.quotePath=false`. Without this, git quotes a non-ASCII path in octal
when `core.quotePath` is true, and the quoted path matches no surveyed
path: a non-ASCII page is not read, a tracked non-ASCII file looks
untracked, and a renamed non-ASCII page gets no `history` evidence.

The order of operations is `check`, `apply --all-auto`, `check`, then
`apply --ids <move ids>`. The automatic ids remove copies and junk, for
example `README.old.md`, and that can change the evidence of a move. So
the move ids come from the second `check`. The skill and the reference
page give this order. `touched_paths(finding)` does not change. Moves have
their own protect test (the vetoes of D10.6 and step 3).

## D10.8 — Score and raw counts

The weights and the formulas do not change. `doc-misplaced` is in the
category `files`, so a docs mess now changes `files`. `Score.raw` holds
the raw input of each category as text (D10.12). The Markdown report
prints one line for each weighted category, `- <category> <points>
(<raw>)`, for example `- docs 20.0 (124 paths)` and `- files 11.4 (40 of
702 files)`. The JSON score object adds `"raw"`, which also holds
`setup`. A scoped check has no score, so it has no raw counts. S24 tests
the rule that more mess never gives a lower score.

## D10.9 — Invariants

The invariants of this round are I-34 to I-39 (see Invariants). The tests
also keep a false-positive rule that has no I-id: the `check --json` plan
of this repository stays empty, the tidy fixture gets no `doc-misplaced`
and no new `scratch` finding, and `looks_scratch` is false for
`template.py`, `notes_service.py` and `v0_v1.rs`.

## D10.10 — Acceptance: convergence and metamorphic

**Fixture.** `tests/fixtures/converge/` holds a tidy tree, with `.txt`
suffixes, read through `conftest.materialise`:
- `Cargo.toml`, `src/fold.rs` and `ui/app.js`;
- `src/notes.rs`, which holds the string `"notes.txt"`. The string is in
  the tidy tree, as in target-rust, where tidy test code holds it. A file that the
  scramble adds would stay after `apply`, and the trees could not be
  equal;
- `README.md`, which links to `docs/ARCHITECTURE.md`, `docs/design/`,
  `docs/running.md` and `docs/IDEAS.md`;
- `docs/ARCHITECTURE.md`, `docs/running.md`, `docs/IDEAS.md`,
  `docs/glossary.md` and `docs/traceability.md`;
- `docs/design/a.md` and `docs/design/b.md`, where `a.md` links to
  `../ARCHITECTURE.md`, to `b.md` and to `../glossary.md`, and
  `docs/design/fig.png`, a small binary.

A helper `_tidy(tmp_path)` runs `git init`, adds the tree and commits.
`SCRAMBLE_OPS` is a list of ten named Python callables. They make the same
kind of mess as `.state/target-rust-scramble.sh`, in the order of the list. Each
one makes one change and commits:
- the pages move to the root, with `running.md` to `HOWTO-run.md`;
- `docs/design` moves to `misc/design`, and `docs/glossary.md` moves to
  `misc/glossary.md`. The link `../glossary.md` in `a.md` still resolves
  after this operation. A move of `misc/design/` alone keeps it
  resolving, to the wrong file, so only the canonical form of D10.7 gives
  the tidy text back;
- `docs/traceability.md` moves to `out/traceability.md`;
- the copies `README.old.md`, `ARCHITECTURE_v2_draft.md`,
  `tmp/scratch_fold.rs` and `dist/app.bundle.js` are added;
- the junk `notes.txt`, `target/debug/old` and `.env` is added. The bare
  basename in `src/notes.rs` does not exempt `notes.txt` (D10.3).

**S23 (I-37).** The test applies each operation, then runs `collect`,
`apply --all-auto`, `collect` and `apply --ids` with each move id. It runs
`collect` and `apply --all-auto` on the tidy repository too. It compares
`git ls-files -s` of the two trees, with blob hashes, and leaves out the
files that trueup writes: `trueup.toml`, `ref_check.toml`,
`.pre-commit-config.yaml`, `.gitignore`, `.editorconfig`, `lint/**`,
`.github/workflows/**` and `findings.APPLY_SIDE_FILES`. Before it reads
the list, `git add -u` stages the text that `apply` wrote to tracked
files. It adds no new path. The two lists are equal, and a new `collect`
gives an empty move plan. The test runs with `layout` on, and again with
a committed `trueup.toml` that sets `[refs] layout = false`.

The test gives the move ids to `apply --ids` in two calls: first the ids
up to `move:misc/design/` in sorted order, then the rest. Between the two
calls, a `collect` must give no `broken-link` finding for
`docs/design/a.md`. With `_rewrite_links` replaced by an identity
function, this check fails.

The S23 test also checks two invariants on the way. After `apply
--all-auto`, each scrambled page is still at its scrambled path (I-34).
The second `collect` gives one `doc-misplaced` finding for each of the
seven pages, and one `move:misc/design/` id for the two pages in that
directory (I-36). The tidy tree gets no `doc-misplaced` and no `scratch`
finding.

**S24 (I-36).** For each operation and each `layout` value, the plan of the
scrambled tree is not shorter than the tidy plan, and `score.total` is not
lower than the tidy total.

Unit tests cover the scratch patterns, the exemption, the last copy and
the guard (D10.3), the duplicate that defers to scratch, `dist/` (D10.4),
the `.gitignore` line that is not added twice (D10.5), the note and the
unchanged id (I-39), history, link, standard, units and vetoes (D10.6),
and D10.7: the inbound rewrite, the outbound rewrite, a directory move
that keeps its inner links, a protected file left broken, and an unknown
move id that exits 2.

A D-id or I-id in `## Verification` needs a test that cites it (check c).
Each Verification line comes in the same task as its test, never before.

## D10.11 — The skill and the reference page

`skills/trueup/SKILL.md` and `docs/reference/trueup.md` change in the same
task as the code that they describe. They give:
- the new rules and patterns: `doc-misplaced`, the scratch patterns, the
  exemption and `dist/`;
- the move plan section and the `move:` ids;
- the four-step order of D10.7;
- the raw counts in the report;
- `[[keep]]` against `protect` for pages that must stay.

## D10.12 — Gap closures

- **Exemption.** D10.3 gives the amended text: a path relative to the
  directory of the file that holds it, or a full path with a `/`.
- **Scoped check.** Under `check --changed` or an `only` set,
  `doc-misplaced` findings are scoped as each other row: only candidates
  in the changed set. `moves` is empty, no history scan runs, and the
  Markdown report prints no move plan. Only a full `check` gives the move
  plan.
- **JSON shape of one move.** `dataclasses.asdict(Move)` gives `{"id",
  "source", "target", "kind", "basis", "evidence", "pages": [...]}`. The
  top-level key `"moves"` is a list sorted by id. Under a scoped
  `collect`, `CheckRun.moves` is `[]`. The JSON report of `check
  --changed` has its own shape, with no `"moves"` key and no `"kept"`
  key.
- **Raw counts.** `Score` gets `raw: dict[str, str]`, default `{}`, keyed
  by category:
  - `security`: `"<n> findings"`;
  - `files`: `"<n> of <m> files"`;
  - `docs`: `"<n> paths"`;
  - `root`: `"<n> entries, budget <b>"`;
  - `health`: `"<n> of <r> required"`;
  - `setup` (not weighted): `"<n> findings"`.

  The Markdown category line is `- <category> <points> (<raw>)`. The JSON
  score object adds `"raw": {...}`.
- **D5.4.** The D5.4 lines on the scratch exemption and on `dist/` point
  to D10.3 and D10.4.

**Alternatives.** These designs were rejected:

- **A new `copy` rule.** Rejected: the `scratch` row already removes the
  file by an automatic id.
- **Move ids as plan findings with a third auto state.** Rejected: it
  changes three `--all-auto` filters and `_validate`. A separate move
  plan keeps I-34 true by structure.
- **One `doc-misplaced` finding for each directory.** Rejected: it breaks
  I-36.
- **A "now at" hint in the checker detail.** Rejected: it changes the
  `[keep]` ids (I-39).
- **A link-fix id next to the move id.** Rejected: the two remedies undo
  each other, and the tree never converges.
- **New score weights.** Rejected: `files` has space left, and the raw
  counts show the rest.
- **The directory rule in the guard hook.** Rejected: it blocks common
  local `tmp/` writes, and `check` finds a tracked one.

## D12.0 — Architecture of the round

Round 4 closes the round-3 items (H1, M1, M2, L1, L2), makes the managed
set depend on the tier (A0), and adds the saved plan, the dirty-tree
refusal, checkbox approval, SARIF output, re-pin ids, an agent rules file
and a pydoclint hook. The table gives the file that owns each part.

| Part | File | Sections |
|---|---|---|
| git byte reads, tree identity, dirty paths | `trueup/changes.py` | D12.1, D12.2 |
| survey file list and tier pick | `trueup/survey.py` | D12.9, D12.10 |
| config schema (`docs = "auto"`) | `trueup/config.py` | D12.9 |
| managed set per tier, setup opt-in, rules file, pydoclint hook | `trueup/managed.py`, `trueup/rulesets.py`, `trueup/templates/claude/` | D12.7, D12.8, D12.9 |
| refcheck fold-in, re-pin entries | `trueup/docrules.py` | D12.6, D12.9 |
| hygiene rows | `trueup/hygiene.py` | D12.10, D12.11 |
| move plan | `trueup/layout.py` | D12.9, D12.10, D12.11 |
| report: JSON tree, Markdown boxes, SARIF | `trueup/report.py` | D12.1, D12.3, D12.4, D12.6 |
| apply: saved plan, dirty refusal, approval ids, re-pin, run-date stamp | `trueup/apply.py` | D12.1, D12.2, D12.3, D12.6, D12.9 |
| CLI flags, stream encoding | `trueup/cli.py` | D12.1 to D12.4, D12.10 |
| documents | `docs/`, `README.md`, `skills/trueup/SKILL.md` | D12.12 |

Limits that stay true:

- `check` writes nothing in the target and opens no network connection
  (I-18, I-28).
- `trueup/ref_check.py` does not change (I-8, I-26). `apply` and
  `docrules` call only its read-only helpers: `section_pin`, `_link_pin`
  and `_md_links`.
- A finding id keeps the form `<rule>:<path>...`. No id of an earlier
  round changes.

## D12.1 — Saved plan (A1)

`apply --plan FILE` acts on a plan that `check --json` saved in `FILE`.
It refuses a tree that differs from the tree of the saved plan.

**Tree identity.** `changes.tree_identity(root)` gives `None` outside a
git work tree. Else it gives `{"head": <HEAD>, "status": <sha256 hex>}`.
The hash input is the raw bytes of `git status --porcelain=v1 -z
--untracked-files=all -- .`, then `\0`, then the blob hash of each listed
path that exists on disk, joined by `\0`. The blob hashes are necessary:
the porcelain text does not change when a person edits a file that is
already modified. The reads write no object and do not refresh
`.git/index` (I-18).

**JSON report.** `render_json` adds two keys and changes no other key:
`"tree"`, the value of `tree_identity` (JSON `null` outside git), and
`"repins"` (D12.6).

**Apply.** `apply --plan FILE` takes `--ids` or `--all-auto`. It refuses
the run with exit 2, one `trueup:` line and no write when:

- the file cannot be read, is not JSON, or is not a `check --json` file;
- the file has no `tree`, or `tree` is `null`;
- `tree` differs from `tree_identity(root)`. The line is
  `trueup: the tree changed since the plan was saved; run trueup check again`.
  When the plan file is inside the root and git does not ignore it, the
  file itself changed the tree, so the line names it instead:
  `trueup: <path> is inside the root and git does not ignore it, so it changes the tree; keep it outside the root, or under .scratch/ once gitignore:.gitignore is applied`;
- `--mode` or `--set` is given. They change the managed set, so they
  need a new `check`.

`apply.load_saved_run(path)` reads the file into `apply.SavedRun`: `plan`,
`findings`, `moves` (as `layout.Move`) and `repins` (as
`docrules.Repin`). A bad file raises `ConfigError`.

The sequence of `apply --plan FILE --ids X` (or `--all-auto`):

1. Load `FILE` and compare its tree. Refuse on each rule above.
2. Validate the ids against `FILE` with `approvable` (D12.3).
   `--all-auto` takes the automatic findings of the saved `plan`.
3. Do the dirty check (D12.2).
4. Make one pass. `apply` does not call `report.collect` between passes,
   before the moves or before the re-pins. The managed-file text comes
   from `managed.render` of the config on disk, which is the config of
   the saved plan, because the tree is the same.
5. Stamp the run date (D12.2). Print the actions.

Without `--plan` and without `--from-report`, `apply` keeps the flow of
D5.6: collect, the passes, and a new collect for each pass (I-35).

Keep the plan file outside the root, or under an ignored path. `.scratch/`
is ignored only after the `gitignore:.gitignore` finding is applied. An
untracked plan file inside the root that git does not ignore changes the
tree hash, so `apply` refuses it with the line that names the file.

**S25 (I-40).** A saved plan applies later or refuses. On the messy
`converge` fixture, `check --json` writes the plan to a file outside the
root. `apply --plan <file> --all-auto` then gives the same files as
`apply --all-auto` on a fresh copy. The move ids of the file apply with
`--plan --ids`. A second case edits a tracked file that is already
modified, between `check` and `apply`: `apply` exits 2 and writes
nothing.

## D12.2 — Dirty-tree refusal (A2) and the run-date stamp

`apply` refuses to write a path that has uncommitted changes (I-41).

**Dirty paths.** `changes.dirty_paths(root)` gives each path of `git
status --porcelain=v1 -z --untracked-files=all`: modified, added and
untracked paths, and both sides of a rename. It decodes them with
`surrogateescape`. Outside git the set is empty.

**Touched paths.** `apply._touched` gives the paths that the run writes,
moves or removes:

- the paths of each selected finding (`findings.touched_paths`);
- for each move, its source, its target and each Markdown file whose
  links the move rewrites. `apply` finds these files before the first
  `git mv`, with the same function that rewrites them;
- for each re-pin, its page;
- `trueup.toml`, only when the run writes the config: a `config`
  finding, `--mode`, `--set` or the setup opt-in.

**Exemption.** A dirty path that `managed.render` also gives, and whose
file on disk carries the managed header, is trueup's own earlier output.
It does not count.

**Refusal.** When a touched path is dirty and not exempt, and
`--allow-dirty` is absent, `apply` exits 2 before the first write. It
prints one line for each path, `trueup: <path> has changes that are not
committed`, then `trueup: commit or stash them, or pass --allow-dirty`.

**Stamp.** `_stamp_run_date` replaces only the `run_date = ...` line of
`trueup.toml`, in place, when that line exists. A hand edit and a comment
in the file stay. It renders the whole file again only when the line is
absent. The stamp is not a touched path for the dirty check.

**Tests.** A test that runs `apply` on a fixture with no commit, and that
does not test the dirty rule, commits the fixture in its setup. A test
about an uncommitted state passes `--allow-dirty`. Each such test cites
D12.2 in a comment.

## D12.3 — Checkbox approval (A3) and approval ids

**Approval ids.** `apply.approvable(run)` maps each id that `--ids`
accepts to what it acts on: the automatic plan findings, the `move:` ids
(D10.7), the `repin:` ids (D12.6) and the setup opt-in
`setup:trueup.toml` (D12.9). `_validate`, `--plan` and `--from-report`
use this one map. The Markdown report puts a box on exactly these ids.

**Markdown report.**

- Line 2, after `# trueup check`, is
  `<!-- trueup tree head=<head> status=<status> -->` when the tree is
  known. Outside git the line is absent.
- An approvable finding prints as
  `- [ ] <id> — [<LABEL>] <evidence> — <action>`.
- A move prints as `- [ ] <move id> → <target> (<basis>: <evidence>)`.
- A re-pin prints as `- [ ] <repin id> → pin:<new> (<target>)`.
- Every other finding keeps the line
  `- [<LABEL>] <id> — <evidence> — <action>`.

The parse `split("] ", 1)[1].split(" — ", 1)[0]` gives the id for both
finding line forms.

**`apply --from-report FILE`.** It is the third member of the group with
`--ids` and `--all-auto`. It also takes no `--plan`.

1. Read the tree comment. When it is absent (`check --changed`, or a root
   outside git), refuse with exit 2 and the line
   `trueup: the report has no tree comment; save a full check of a git root with trueup check --out, then tick its boxes`.
   When it differs from the tree now, refuse with exit 2 and the I-40
   line, or with the line that names the report file when that file is
   inside the root and git does not ignore it.
2. Take the ids. Each line that starts with `- [x] ` or `- [X] ` gives
   one id: the text up to the first ` — ` or ` → `, stripped.
3. Make one `report.collect(root)`. Validate the ids with `approvable`.
   An unknown id gives exit 2, and nothing is written.
4. Do steps 3 to 5 of D12.1: the dirty check, one pass and the stamp. No
   second collect.

A path that holds ` — ` cuts its id short. The short id fails
validation, so the run refuses and writes nothing.

## D12.4 — SARIF output (B1)

`check --sarif FILE` also writes the findings as SARIF 2.1.0. It goes
with `--json`, `--out` and `--changed`. The `--out` refusal rule
(`_out_refused`) applies: a `FILE` inside the root that no `ignore` glob
covers gives exit 2, and nothing is written. The exit code of `check`
does not change.

`report.render_sarif(findings, kept_ids)` gives one run:

- `tool.driver`: `name` is `trueup`. `rules` has one entry for each rule
  of the results, `{"id": rule, "defaultConfiguration": {"level":
  <level>}}`, with the most severe level of that rule.
- One result for each finding that is not kept: `ruleId` is the rule;
  `level` is `error`, `warning` or `note` for `error`, `warn` or `info`;
  `message.text` is `<evidence> — <action>`; `partialFingerprints` is
  `{"trueupId/v1": <finding id>}`.
- `locations`: one `physicalLocation` with `artifactLocation.uri`, the
  path, and `region.startLine`. The line is the number after the path in
  a `refcheck:` id, else 1. A finding with an empty path has no
  `locations`.
- The file is `json.dumps(..., indent=2, sort_keys=True)` with the
  default `ensure_ascii`, so a path that is not UTF-8 is escaped.

There is no CI upload step. The CI job does not install trueup, and
trueup has no install source that a runner can get.

## D12.5 — Near-duplicate experiment (B2): record only

jscpd 4.3.0 found a pair of pages that share 80 percent of their text,
by paragraph, only with `format: ["markdown"]`. The strict jscpd config
has no Markdown format, and `check` cannot run `npx` (offline, I-18). The
research page gives the result and the method. The brief row
"Near-duplicate documents?" says that the experiment ran, and why no row
exists. There is no code change, no row and no hook.

## D12.6 — Re-pin on approval (B3)

An approved `repin:` id writes the new pin of a pinned reference whose
section changed.

**Entries.** `docrules.Repin` is a frozen dataclass: `id`
(`repin:<path>:<line>`), `path`, `line`, `target` (the link target with
its fragment, from the failure detail), `old_pin` and `new_pin` (eight
lower-case hex characters). `docrules.repins(root, findings)` reads each
`refcheck` finding whose detail is `pinned section changed: <target>`. It
reads line `line` of `path` and finds the Markdown links
(`ref_check._md_links`) with that target and a pin
(`ref_check._link_pin`). When there is exactly one such link, and
`ref_check.section_pin(<target page text>, <fragment>)` is not `None`,
it gives one `Repin`. Else it gives no entry, and the finding stays
manual. The entries sort by id.

**Report.** `CheckRun.repins` holds the entries. The JSON report has
`"repins"`, a list of objects sorted by id. The Markdown report has the
section `## Re-pin plan (n)` with one box line for each entry (D12.3).

**Apply.** `apply --ids repin:<path>:<line>` validates the id with
`approvable`. It reads the line again. Exactly one link with `target` and
`pin:<old_pin>` must be there, else the id fails with exit 1 and a
reason. It replaces `pin:<old_pin>` with `pin:<new_pin>` in that line
only. `--all-auto` never takes a `repin:` id.

The `refcheck:...:stale-pin` finding and its id do not change, so the
`[[keep]]` keys and the baseline keys stay. `trueup/ref_check.py` does
not change (I-8).

## D12.7 — Agent rules file (Q3)

Replaced by D14.10 (2026-10-16).

`.claude/rules/trueup.md` is a managed path. `managed.render` gives it
from the template `trueup/templates/claude/trueup-rules.md`. Its minimum
tier is that of `ref_check.toml` (the D12.9 table).

- Lines 1 to 4 are front matter: `---`, `paths:`, `  - "docs/**"`,
  `---`. Claude Code then loads the file only for a page under `docs/`.
- Line 5 is the managed header as an HTML comment:
  `<!-- Managed by trueup. Edit trueup.toml, then run the trueup skill. -->`.
- At most ten lines follow. They give the standard: Simplified Technical
  English, one topic for each page, the page types under `docs/`, the
  marker registry, design-id citations and the scratch names to keep out
  of git. No word of the banned list occurs.

`managed.header_line` and `_is_managed_on_disk` read the header of this
path on the first line after the closing `---`. There is no Codex rule.

This repository writes the file with
`python3 trueup apply --root . --ids file-managed:.claude/rules/trueup.md`,
so the self-check (I-27) stays green.

## D12.8 — pydoclint in strict Python (Q4)

`RULESETS[("python", "strict")]` has one more hook after `complexipy`
(I-21 order): id `pydoclint`, `pass_filenames` false. Its entry is one
`sh -c` command. When `lint/python/pydoclint-baseline.txt` is absent, the
command first writes it (`--generate-baseline=True`). Then it runs
`pydoclint --style=google --arg-type-hints-in-docstring=False
--check-return-types=False --baseline=lint/python/pydoclint-baseline.txt .`.
`tools` has `pydoclint`, so a target without it gets a
`tool-missing:python/pydoclint` info finding.

The baseline file is not a managed path. trueup never renders it. The
revive `comments-density` rule is not added.

## D12.9 — Managed set per tier and the setup opt-in (A0)

Replaced by D14.8 (2026-10-16).

The managed set depends on the tier (I-42, I-43). A small repository gets
its real findings and one opt-in row, not one error for each setup file.

**Table.** The minimum tier of each managed path (`managed._min_tier`):

| Managed path | Minimum tier |
|---|---|
| `trueup.toml` | T1, or present on disk |
| `.pre-commit-config.yaml` | T1 |
| `.editorconfig` | T1 |
| language lint files (rule-set files, the eslint pair, `lint/jscpd.json`) | T1 |
| `ref_check.toml`, `.claude/rules/trueup.md` | T2; T1 when the survey holds a Markdown page under `docs/` |
| `.github/workflows/trueup.yml`, `lint/gitleaks/gitleaks.toml` | T2 |
| Vale files | T2, and only when `docs` resolves to `full` |
| copy-mode checker (`[refs] path`) | any tier, when `[refs] mode = "copy"` |

A path below its minimum tier stays in the set when its file on disk is
trueup's: `_is_managed_on_disk` says so, or, for `trueup.toml`, the file
exists. The Vale files go as one group.

**Steps.**

1. `config.py`: `docs` takes `auto`, `full` or `readme`, and the default
   is `auto`. `--set docs=auto` is valid. `config.resolve_docs(cfg, tier)`
   gives the mode in force: an explicit `full` or `readme` wins; `auto`,
   or no config, gives `readme` at T0 and T1 and `full` at T2 and T3.
2. Readers resolve the mode when they read it, not in
   `effective_config`: `docrules` (the docs gate), `layout.locate` (the
   `standard` target) and `managed.render` (every file but
   `trueup.toml`). The rendered `trueup.toml` keeps `auto`. The session
   hook prints the stored value.
3. `managed.render(cfg, survey)` gives the tier set. It renders the full
   map, then keeps a path when the tier is at or above the path's minimum
   tier, or when the path stays by the on-disk rule. The gitleaks
   pre-commit hook names `--config lint/gitleaks/gitleaks.toml` only when
   that path is in the set; else gitleaks runs with its own default.
   `apply` and `check` read this one function, so what `check` compares
   is what `apply` writes.
4. `managed.setup_findings(survey, cfg, offer=True)`: when `cfg` is
   `None` and the tier is T0 or T1, the `config`, `file-managed` and
   `tool-missing` findings fold into one finding. Its id is
   `setup:trueup.toml`, rule and category `setup`, severity `info`, path
   `trueup.toml`, `auto` true. The evidence is
   `<n> setup files: <paths, sorted, comma-separated>`. The action is
   `run trueup apply --ids setup:trueup.toml to write them`. When the set
   is empty (T0), there is no finding. The `gitignore` finding and every
   other row stay. With `offer=False` the function gives one finding for
   each file, as before.
5. `apply --ids setup:trueup.toml` writes `trueup.toml` and each file of
   `setup_findings(survey, cfg, offer=False)` in one pass. `--all-auto`
   never takes it: an `info` finding is not in the plan. After the
   opt-in, `trueup.toml` exists, so the next `check` gives one row for
   each file of the tier set. With a `trueup.toml`, the setup id is
   unknown (exit 2).
6. The `refcheck` row runs in both docs modes. Its config text is
   `render_ref_check_config(<resolved config>, keep=False)` when
   `ref_check.toml` is in the tier set. Else the checker runs as with no
   `ref_check.toml`: every switch off, checks a to d on. This is the
   config that the `ref-check` hook has after `apply` (D8.1).
7. `survey.py`: the tier pick counts no trueup path. The file count, the
   language file count and `has_ci` leave out `trueup.toml`,
   `ref_check.toml`, `.pre-commit-config.yaml`, `.editorconfig`,
   `.github/workflows/trueup.yml`, `.claude/rules/trueup.md`,
   `.trueup-baseline.json` and each path under `lint/`
   (`survey.is_trueup_path`). `Survey.files` does not change. So a
   repository whose only CI is trueup's workflow keeps the tier it had
   before `apply` wrote that workflow. This repository stays T2: it has a
   manifest and more than 50 files. `Survey.root_entries` leaves out the
   same paths and the root `ref_check.py`, so the `root-budget` row and
   the `root` score count no root entry that holds only trueup's files. A
   `.github/` that also holds a file of the project still counts.

**S26 (I-42, I-43).** A small repository gets real findings, not setup
noise. A T1 fixture with 9 files (one README, a `main.js` with one
unregistered marker, a `package.json`, no `.scratch/` line in
`.gitignore`) and no `trueup.toml`: `check` gives the `refcheck` marker
row, the `gitignore` row and one `setup:trueup.toml` info row. It gives
no `file-managed` row and no `config` row. `apply --ids
setup:trueup.toml` writes `trueup.toml`, `.pre-commit-config.yaml`,
`.editorconfig` and the eslint pair. It writes no CI workflow, no
gitleaks config, no `ref_check.toml` and no Vale file. The next `check`
gives tier T1 and no setup row. A 48-file T1 variant stays T1 after the
opt-in (I-43). A T0 fixture (2 files) gets no setup row and no write.

## D12.10 — Path names that are not UTF-8 (H1, M2)

trueup reads git path names as bytes and decodes them with
`errors="surrogateescape"`. A byte that is not UTF-8 then goes through
the run and back to git with no change.

- `hygiene._tracked_paths`, `apply._git`, `apply._print_code_mentions`,
  `layout._history_renames` (both calls) and `survey._list_files` decode
  with `surrogateescape`. `survey._list_files` runs `git ls-files -z` and
  splits on `\0`.
- `cli.main` sets `errors="surrogateescape"` on `sys.stdout` and
  `sys.stderr` one time. Each report file (`--out`, `--sarif`) is written
  with `errors="surrogateescape"`, or is JSON with `ensure_ascii`.
- One test repository tracks `b"caf\xe9.md"` and `b"x\xe9.tmp"`. `check`
  in Markdown and JSON, `check --out`, and `apply --ids move:<that path>`
  run on it with no crash. The move test first asserts that the plan
  holds the `move:` id.

Out of scope: `cli._resolve_root` decodes the root name in strict mode.

## D12.11 — Round-3 closures M1, L1, L2

This section closes the open round-3 items.

- **M1.** `_directory_moves` skips a directory unit when its target path
  exists in the work tree, even when git ignores the target. The locator
  gives the root to `_directory_moves` for this check.
- **L1.** `_is_candidate` accepts `.md` and `.markdown`. The `artifact` row
  uses `_is_candidate`, so both suffixes count the same (D10.4).
- **L2.** `hygiene.scratch_looking(path, cfg)` is the one test for a
  scratch-looking path. The `scratch` row, the `artifact` row (through
  `_is_candidate`) and `layout.locate` all call it. `locate` no longer
  reads the `scratch` findings. This rule replaces any earlier text that
  says `locate` takes its scratch set from the `scratch` findings.

## D12.12 — Documents (C1-C4)

Round 4 changes these documents:

- C1: the reference page has the subsection "Exit codes" under "Command
  line". One table gives the exit codes of `check` and `apply`, and maps
  them to the Terraform `-detailed-exitcode` values: Terraform gives 0
  for no change, 1 for an error and 2 for a plan; trueup gives 1 for a
  plan and 2 for bad input.
- C2: each page that names a tool of research page section 2.7 has one
  status sentence for that tool. The kept source page
  `docs/explanation/research-repo-hygiene.md` does not change. The
  security floor section of the reference page has the gitleaks
  successor note. Templates and `rulesets.py` comments do not change.
- C3: `README.md` and the brief give the five claims of research page
  section 3, each only as behaviour that is built.
- C4: `skills/trueup/SKILL.md` and the reference page describe `--plan`,
  `--from-report`, `--allow-dirty`, `--sarif`, `repin:`, `setup:`,
  `docs = "auto"`, the tier table of D12.9, the rules file and pydoclint.
  The last task of the round writes C4, after every flag exists.

This file has the D12 sections, I-40 to I-43, S25 and S26. D5.4 and D5.6
point to the D12.9 table. I-35 names the flow of I-40. The brief row
"Repository tiers?" cites D12.9. A task declares each heading and id
before a test cites it.

## D13.0 — Architecture of the round

Round 5 carries out the plan of
`docs/explanation/purpose-and-state.md` (P0 to P8). It fixes two
false-positive classes that the local targets showed (F2, F3), adds a
script that runs the local targets after a round (P1), makes the
self-check true on a clean checkout (P4), and records hook times in
place of a wall-clock bound in the unit suite (P5, F9).

| Part | File | Sections |
|---|---|---|
| Markdown-as-code in the candidate rule | `trueup/layout.py`, `trueup/hygiene.py` | D13.1 |
| `binary` row: links, tier floor, allow globs | `trueup/hygiene.py` | D13.2 |
| `[layout]` and `[binary]` tables | `trueup/config.py` | D13.1, D13.2 |
| local targets run | `scripts/check_targets.py` | D13.3 |
| hook timing log | `trueup/hooks.py`, `scripts/hook_times.py` | D13.4 |
| `[[eslint.off]]` | `trueup/config.py`, `trueup/rulesets.py`, `trueup/managed.py` | D13.5 |
| eslint bulk suppressions file | `trueup/rulesets.py` | D13.6 |

D13.5 and D13.6 come from the first run on target-web/3d, after the plan.

## D13.1 — Markdown-as-code

A Markdown file that a tool reads as input is code, not a page: an agent
definition, a skill body, a prompt, a rule file or a template. D10.2
exempted a dotted segment and the basename `SKILL.md` only. On
target-mixed/src, 57 of 57 `doc-misplaced` items were wrong for this
reason (F2).

Two more items take a file out of the D10.2 candidate set:

- a directory segment (not the basename) is in `layout.CODE_SEGMENTS`
  (`agents`, `claude`, `prompts`, `rules`, `skills`, `templates`) or in
  `[layout] code_dirs` of `trueup.toml`. The config list adds to the
  default list; it does not replace it. `layout.code_dirs(cfg)` gives
  the list in force, and `_is_candidate` takes it as the keyword
  argument `code_dirs`. The `artifact` row gives the same list;
- the file starts with a front matter block whose top-level keys hold
  `name` and `description` and no `type`. `locate` reads the first
  4 KiB of each candidate for this test (`_is_agent_definition`). A line
  that is not a top-level `<key>:` line is skipped, so a list value does
  not stop the read.

`[layout]` takes only `code_dirs`, a list of directory names with no
`/`. `render` writes the table only when the list is not empty, so a
target that never sets it keeps the same bytes (D5.3). The key is not
`[docs] code_dirs`, because `docs` is a top-level string key (D12.9) and
TOML cannot hold both.

## D13.2 — The `binary` row asks before it warns

On target-rust/src, 34 of 52 plan items were `binary` warnings on PNG review
evidence (F3). The row of D5.4 changes in three ways:

- a file that a `.md` or `.markdown` file of the survey links to by
  relative path gets no finding. The links come from the read-only
  helper `ref_check._md_links`. A target that leaves the root does not
  count. The pages are read only when a file is a candidate;
- below T3 the NUL-byte sniff does not run. Only a file over 1 MiB gets a
  finding. At T3 the 100 KiB sniff of D5.4 stays;
- a `[binary] allow` glob that matches the repo path (`matches_ignore`)
  or the basename (`fnmatch.fnmatchcase`) spares the file, the same
  match as `[scratch] allow`.

`[binary]` takes only `allow`, a list of strings. `render` writes the
table only when the list is not empty.

## D13.3 — Local targets run

`scripts/check_targets.py` runs the working copy's `check --json`,
read-only, on each local target repository: target-rust/src, target-mixed/src and
the four field-trial repositories of D6.16. It counts the plan items per
rule and the moves, writes the counts to `.state/targets/<date>.json`,
and compares them to the last stored file. It prints `GREW` for each
rule count that grew and exits 1 when one grew or a check failed. The
script is a process tool. It is not part of the package and no test runs
it, because the targets exist on one machine only.

## D13.4 — Hook timing log

The unit suite does not hold a wall-clock bound: on a loaded machine the
Stop hook took 1.17 to 1.83 s and the I-17 test failed (F9). `hooks.run`
now measures the time of each dispatch and adds one line
`{"date", "event", "seconds"}` to `$CLAUDE_PLUGIN_DATA/hook-times.jsonl`.
The time starts after the interpreter and the imports are ready, so it is
less than the time Claude Code waits. Nothing is written when
`$CLAUDE_PLUGIN_DATA` is not set, and a write error is ignored (I-22).
This file and the session snapshot are the only files a hook writes
(I-14).

`scripts/hook_times.py` prints the run count, the median, the 95th
percentile and the largest time of each event. The plugin is installed
on this machine for the trial of P5. The decision on the delivery form
waits for one week of real sessions.

## D13.5 — `[[eslint.off]]`

On target-web/3d (TypeScript clean) the eslint hook gave 1,567
warnings. 1,483 were `security/detect-object-injection` on ordinary
`obj[key]` lookups in numeric code, and 59 were
`security/detect-non-literal-fs-filename` in Node tools that read their
own files. The eslint config is a managed file (D5.6): a hand edit is
drift, and the next `apply` drops it. So `trueup.toml` must be able to
turn a rule off, with the reason on record.

- `trueup.toml` takes an array of tables `[[eslint.off]]`. Each entry
  holds exactly `rule` and `reason`. `rule` is an eslint rule name
  (`config._ESLINT_RULE`: letters, digits, `@`, `_`, `.` and `-`, in
  parts split by `/`), so it holds no space and no quote. `reason` is
  not empty and is one line: it holds no control character and no
  U+2028 or U+2029, because it goes into a `//` comment. A repeated rule
  is an error. Each error is a `ConfigError`, so the run exits 2 with a
  `trueup:` line (D5.11).
- `Config.eslint_off` maps the rule to the reason. `render` writes the
  entries after `[languages]`, sorted by rule, and writes no line when
  there is no entry, so a target that never sets the key keeps the same
  bytes (D5.3). `apply` writes `trueup.toml` through `render`, so it
  keeps the entries.
- `render_eslint_config` adds a last config object, `offBlock`, when
  the map is not empty. Its `rules` set each rule to `"off"`, sorted,
  with the reason as a comment at the end of the line. The object has no
  `files` key: it applies to each file that an earlier block matches,
  and it adds no file. It comes last, so it wins. A changed rule or
  reason changes a code line, so `check` reports
  `file-managed:lint/typescript/eslint.config.mjs` (D5.6).
- Measured on eslint 10.12 (2026-10-16): `"off"` for a rule of a plugin
  that the block of a file does not load (`security/...` on a `.vue`
  file) gives no error. `"off"` for a rule name that eslint does not
  know gives no error either. So a misspelt rule stays on and its
  findings stay: the person sees that the entry did nothing.
- The key is `[[eslint.off]]`, not a key under `[languages]`.
  `[languages]` maps each language to a mode string (D5.3), and the
  entries belong to the eslint config that TypeScript and Vue share
  (D5.5), not to one language. The entries have no effect while
  TypeScript and Vue are both `off`.
- The key is for a rule that flags normal code in bulk. One finding
  gets a disable comment with a reason (the comment standard).

## D13.6 — The eslint bulk suppressions file

A codebase that adopts the clean rule set can start with many errors
(target-web/3d: 1,063, about 1,050 of them jsdoc). eslint 9.24 and later
can freeze the errors of a day in a bulk suppressions file:
`--suppress-all` writes a count per file and rule, and a later run
reports a rule in a file only when its count grows. A suppression
covers a rule at `error` only, so a warning still fails the hook under
`--max-warnings 0`.

- The file is `lint/typescript/eslint-suppressions.json`
  (`rulesets.ESLINT_SUPPRESSIONS_TARGET`), beside the eslint pair, not
  at the root (D5.5). Its paths are relative to the directory eslint
  runs in, the root, as for the hook.
- Measured on eslint 10.12 (2026-10-16), with `--suppressions-location`
  naming the file:
  - (a) The file is absent: eslint prints `The suppressions file does
    not exist`, lints nothing and exits 2. So the hook gives the flag
    only when the file exists, through `sh -c 'if test -f <file>; then
    set -- --suppressions-location <file> "$@"; fi; exec npx ...
    --max-warnings 0 "$@"' eslint`. A target with no file runs as
    before. With the file removed, every error comes back: the gate gets
    stricter, not weaker.
  - (b) A suppression no longer occurs (a count is higher than the
    errors found): eslint reports the other problems as usual, prints
    `There are suppressions left that do not occur anymore`, names
    `--prune-suppressions` and `--pass-on-unpruned-suppressions`, and
    exits 2. It compares only the files of the run, so a commit that
    touches one file does not see the suppressions of the others, and an
    entry of a removed file does not fail the hook.
  - A count that grows reports each error of that rule in that file
    (exit 1).
- The hook does not pass `--pass-on-unpruned-suppressions`. A partial
  fix fails the commit with a message that names the fix; the person
  runs the prune command and commits the smaller file. So the count only
  goes down. With the flag, the file could keep a count that the code no
  longer has, which is room for a new error later.
- trueup does not render, check or remove the file: the target writes
  it with eslint and owns it. It is not in the managed set (D5.6), so no
  `file-managed` row reads it. Its name matches no scratch pattern
  (D10.3), it is not at the root (D5.8) and not under a build directory
  (D10.4), and it is not a manifest, so the `lockfile` row and the
  managed manifest exemption (D8.3) do not change. A test applies a
  TypeScript target, commits the file, and finds no finding on it.
- The commands, from the root. Create: `npx --prefix lint/typescript
  eslint --config lint/typescript/eslint.config.mjs
  --suppressions-location lint/typescript/eslint-suppressions.json
  --suppress-all .`. Prune: the same with `--prune-suppressions` in
  place of `--suppress-all`; it also drops the entries of removed
  files. `.` lints the whole tree, and the eslint config does not hold
  the `ignore` globs of `trueup.toml` (only the `exclude` of the hook
  does, D5.6). When an ignored path holds JS or TS, name the source
  directories in place of `.`.

## D14.1 — Configuration layers

Round 14 makes trueup universal. Before it, the house standard was code:
the `docs` directory name, the banned list, the agent rules file and the
`.scratch/` line were fixed for every target, and a target held a tree
of managed lint files. Now one `Config` shape carries the standard, and
five layers fill it. A higher layer replaces a key of a lower layer.

| Layer | File | Read when |
|---|---|---|
| L0 code defaults | `Config()` in `trueup/config.py` | always |
| L1 profile | a built-in `trueup/data/profiles/<name>.toml`, or a user `$XDG_CONFIG_HOME/trueup/profiles/<name>.toml` | always |
| L2 user default | `$XDG_CONFIG_HOME/trueup/trueup.toml` | only when the target has no `trueup.toml` |
| L3 target | `<root>/trueup.toml` | when it exists |
| L4 command line | `--profile NAME`, `apply --set`, `apply --mode` | when given |

`config.load_layers` reads the files and merges them.

- `config.config_home()` is `$XDG_CONFIG_HOME/trueup`, and
  `config.cache_home()` is `$XDG_CACHE_HOME/trueup`. An empty or unset
  variable gives `~/.config` or `~/.cache` (`Path.home()`).
- The profile name comes from the first of these that is set:
  `TRUEUP_PROFILE` (the `--profile` flag sets it in the process), the
  `profile` key of the target file, the `profile` key of the user
  default file (read only without a target file), and then `house`.
- A profile name matches `config.PROFILE_NAME`,
  `[a-z0-9][a-z0-9-]*`. Another name is a `ConfigError` that names the
  file or the variable that set it.
- `config.BUILTIN_PROFILES` is `("house", "minimal")`. A built-in name
  always reads the file under `trueup/data/profiles/`. Any other name
  reads only the user file under `profiles/`.
- At each load, `_profile_path` probes `profiles/house.toml` and
  `profiles/minimal.toml` in the user directory. When one exists, the
  load is a `ConfigError`: `profiles/house.toml shadows the built-in
  profile house; rename it`. So `profile = "house"` gives the same rules
  on every machine (I-46).
- A name that resolves to no file is a `ConfigError` that names the
  built-in directory and the user path. trueup never falls back to
  `house` (I-44).
- A profile file and the user default file take the `trueup.toml`
  schema with these limits: `version`, `run_date` and `[[keep]]` are
  target-only keys, and a profile file cannot set `profile` (no chain of
  profiles). The user default file can set `profile`. An error in one of
  these two files names that file.
- `house.toml` writes each key at its default value, so it also
  documents the keys. `minimal.toml` holds the `minimal` column of
  D14.2. A key that a profile does not set keeps its code default.

## D14.2 — The configurable standard

Each rule of the house standard that a target can want different is now a
key of `trueup.toml`. The default of each key is the `house` value, so a
target with no new key keeps its findings (I-48). `docs` is a top-level
string key, so the docs settings live in `[layout]`.

| Key | Type | `house` | `minimal` | Was |
|---|---|---|---|---|
| `profile` | a D14.1 name | absent (`house`) | not set | new |
| `[layout] docs_dir` | one directory name of letters, digits, `_`, `.` and `-`; not `.` or `..` | `"docs"` | `"docs"` | the string `docs` in the code |
| `[layout] front_matter` | bool | `true` | `false` | the checker rules `no-front-matter`, `bad-field`, `duplicate-id` |
| `[layout] types` | bool | `true` | `false` | the checker rule `misplaced` and the type directories of the move target |
| `[layout] index` | bool | `true` | `false` | the checker rules `unindexed` and `no-index-link` |
| `[prose] banned` | `"builtin"`, `"off"` or a file path | `"builtin"` | `"off"` | the fixed `trueup/data/banned.txt` |
| `[prose] extra` | a list of entries in the `banned.txt` form | `[]` | `[]` | new |
| `[refs] registry` | bool | `true` | `false` | the registry check, always on |
| `[refs] comments` | bool | `true` | `false` | the comment check, always on |
| `[refs] links` | bool | `true` | `true` | the link check, always on |
| `[root] base` | a list of globs | absent (the D14.11 list) | absent | the fixed guard list |
| `[health] agents` | bool | `true` | `false` | the `agents-missing` and `claude-not-linked` rows |
| `[scratch] gitignore` | bool | `true` | `false` | the `.scratch/` line of the `gitignore:.gitignore` row |
| `[eslint] suppressions` | a repo path | `"lint/typescript/eslint-suppressions.json"` | the same | the fixed path of D13.6 |
| `[python] pydoclint_baseline` | a repo path | `"lint/python/pydoclint-baseline.txt"` | the same | the fixed path of D12.8 |
| `docs` | `auto`, `full`, `readme` | `"auto"` | `"readme"` | unchanged |

Rules.

- `[refs] layout` stays. `layout = false` sets `front_matter`, `types`
  and `index` to `false` together, and `layout = true` sets them to
  `true`. A file that sets `[refs] layout` and one of the three
  `[layout]` switches is a `ConfigError`. `render` writes `layout` as the
  file set it, and then does not write the three switches.
- `[prose] banned` as a path is relative to the directory of the file
  that set it: the root for a target file, `profiles/` for a user
  profile. `_resolve_banned` makes it absolute in the effective config;
  the target layer keeps the text as written, so `render` writes it
  back. The file has the `banned.txt` form: one entry for each line that
  is not blank, `word` or `word => <regex>`. A missing file is a
  `ConfigError` at load.
- `[prose] extra` entries come after the entries of the file, in order.
  With `banned = "off"`, the `extra` entries are the whole list, so a
  project can ban only its own words.
- `[root] base` replaces the code list of D14.11 when it is set.
  `[root] allow` still adds to the list in force.
- The marker registry (D2.2) stays frozen and closed. `[refs]
  local_tags` (D8.7) stays the only key for the project's own tags.
- A profile can set `tier` and `docs`. `resolve_docs` runs on the
  effective config, so a profile with `docs = "readme"` applies to a
  target file that has no `docs` line.

## D14.3 — Config loading and rendering

Amended by D15.6 (2026-11-02): `config.load` always gives the effective
config. `config.load_target` keeps `None` for a target with no file.

`trueup/config.py` holds one `Config` dataclass and one loader.

- `Config` keeps its earlier fields and adds `profile`,
  `layout_docs_dir`, `layout_front_matter`, `layout_types`,
  `layout_index`, `prose_banned`, `prose_extra`, `refs_registry`,
  `refs_comments`, `refs_links`, `root_base`, `health_agents`,
  `scratch_gitignore`, `eslint_suppressions`,
  `python_pydoclint_baseline` and `explicit`. `explicit` is the set of
  dotted keys that the target file set, for example `"tier"`,
  `"root.allow"`, `"languages.python"` or `"keep"`. It is `None` for a
  profile file, for the user default file and for the effective config.
- `Layers` holds `effective` (every layer merged; each reader takes
  this), `target` (the target file alone, with `explicit`, or `None`),
  `profile` (the resolved name), `profile_path` (the file of the
  profile) and `user_default` (the L2 file when it was read).
- `load_layers(root)` gives `Layers`, or `None` when neither
  `<root>/trueup.toml` nor the user default file exists. `load(root)` is
  `load_layers(root).effective` and `load_target(root)` is
  `load_layers(root).target`. A reader that tests `load(root) is None`
  keeps the meaning "not adopted". The hooks test `load_target` (D14.11).
- `_parse(raw, *, source, layer)` validates one file. `layer` is
  `"target"`, `"profile"` or `"user"`, and it controls the target-only
  and no-chain rules of D14.1.
- `_overlay` merges one layer over the lower layers. For each dotted key
  that the higher file set, `_MERGE_FIELDS` names the fields that it
  replaces. A scalar and a list replace; a list does not add to the lower
  list. `[languages]` merges per language and `[[eslint.off]]` per rule;
  the higher layer wins. `[[keep]]` comes only from the target file. The
  effective `profile` field is the name when a layer or the variable
  named it, else `None`.
- Cache. `_CACHE` keys on the root, `TRUEUP_PROFILE` and
  `config_home()`, and holds the `(path, st_mtime_ns, st_size)` of each
  file that the load read or probed. A later call gives the cached
  layers when no stat changed. `check` loads the config about ten times;
  the cache makes each later load cost a set of `stat` calls.
  `clear_cache()` empties it; the autouse test fixture calls it (D14.15).
- `render(cfg)` writes the header comment, `version`, and each key whose
  dotted name is in `cfg.explicit` or whose value differs from
  `Config()`. No key is always written: `render(Config())` is the header
  and `version = 1`. A file that `load_target` read renders to the keys
  that it held, also a key at its default value. The key order is fixed,
  so a second render of the same config gives the same bytes (D5.3).
- `apply` renders only `Layers.target`. `apply._merge` adds each `--set`
  key, each `--mode` language and `languages` to `explicit`, so `--set
  tier=auto` is written although it is the default. `apply --set
  profile=<name>` writes the key; the value must match `PROFILE_NAME`.
  When the target has no file, `apply` creates one only through the
  `config:trueup.toml` or `setup:trueup.toml` id, and `_stamp_run_date`
  writes nothing.
- The `config:trueup.toml` row comes only when `load` gives `None`.
  Under the user default file the effective config is not `None`, so no
  such row comes, and `apply` does not write a target file that would
  stop the user default file.
- `report.profile_block(root)` gives `{"name", "path"}`. `check --json`
  holds it as `profile`, beside `survey`. The Markdown report prints
  `profile <name> (<path>)` after the tree comment. The SessionStart
  notice prints the name (D14.10).

## D14.4 — Where each key is read

| Key | Readers, by function |
|---|---|
| `layout_docs_dir` | `layout._is_candidate`, `_acceptable`, `_acceptable_directory`, `_standard_target`; `docrules._docs_pages`; the health rows, which build the `{docs_dir}/` places at call time; `managed.refcheck_switches_on`; `hygiene.looks_scratch_path` and `hooks._scratch_denied` (D14.12 C2); the checker, through `[layout] docs_dir` (D14.5) |
| `layout_front_matter`, `layout_types`, `layout_index` | the checker, through `[layout]` (D14.5); `layout._standard_target` gives `{docs_dir}/{basename}`, with no type directory, when `types` is `false` |
| `prose_banned`, `prose_extra` | `docrules.banned_words(cfg)`: `builtin` reads `trueup/data/banned.txt` through `_load_banned_words()`, a path reads that file, `off` gives no entry, then the `extra` entries follow. `_prose_findings` takes the list, and an empty list turns the prose pass off. `trueup lint` renders the Vale `Banned.yml` from the same list (I-25) |
| `refs_registry`, `refs_comments`, `refs_links` | `managed.render_ref_check_config` (D14.5) |
| `root_base` | `hooks.base_root_allow` (D14.11) |
| `health_agents` | `health.health_findings`: `_agents_findings` runs only when it is `true` |
| `scratch_gitignore` | `managed._per_file_setup_findings`: the `gitignore:.gitignore` row comes only when it is `true` |
| `eslint_suppressions`, `python_pydoclint_baseline` | `rulesets.owned_file_args`, for `trueup lint` (D14.6) |
| `profile` | `config.load_layers`; `hooks._session` prints the name and adds the Simplified Technical English line only under `house` (D15.34) |

## D14.5 — The checker config text

`trueup/ref_check.py` stays one file that imports nothing from the
package (I-26). Its config schema gains a `[layout]` table with the keys
`docs_dir`, `front_matter`, `types` and `index`, and its `Config` gains
the same four fields with the defaults `"docs"`, `true`, `true` and
`true`. The checker reads the docs pages from `root / docs_dir` and the
design from `root / docs_dir / "ARCHITECTURE.md"`. In check h,
`no-front-matter`, `bad-field` and `duplicate-id` run behind
`front_matter`, `misplaced` runs behind `types`, and `unindexed` runs
behind `index`. Check i runs `no-index-link` on `{docs_dir}/README.md`
behind `index`. `[checks] layout = false` still turns off all of check
h. The `[scan] ignore` table of D13 stays where it was.

`managed.render_ref_check_config(cfg, survey, keep=True)` renders the
checker config from the effective config (D14.22 item 3):

- `on = refcheck_switches_on(cfg, survey)`: true at T2 and T3, and at
  T1 when `survey.files` holds a `.md` or `.markdown` page under
  `{docs_dir}/` (D14.22 item 12).
- `full = on and resolve_docs(cfg, survey.tier) == "full"`.
- `[checks]`: `registry = on and refs_registry`, `comments = on and
  refs_comments`, `links = on and refs_links`, `layout = full and
  refs_layout and (front_matter or types or index)`, `readme = full`.
- `[layout]` with all four keys, only when one of them is not its
  default.
- `[registry] local_tags`, the `[keep]` table (only with `keep`) and
  `[scan] ignore` as before.

Three callers run the checker with this text, from a file in a
temporary directory: `docrules._refcheck_config_text` (the `check` pass,
`keep=False`), `trueup lint` (`keep=True`), and `cli._run_refs` in global
mode when the person gives no `--config` (`keep=True`). When
`refcheck_switches_on` is false, the text is empty, so every switch is
off. In copy mode `trueup refs` and the copy read `<root>/ref_check.toml`
as before. So `ref_check.toml` is a managed file in copy mode only
(D14.8).

## D14.6 — `trueup lint`

`trueup/lint.py` holds the command; `cli` adds the subcommand.

```
trueup lint [--root DIR] [--profile NAME] [--changed] [--install] [PATH ...]
```

`lint.run(root, paths, *, changed, install)` does these steps.

1. `config.load_layers(root)`. `None` prints `trueup lint: no
   trueup.toml and no user default file; run trueup check` and gives
   exit 2. Then `survey.run(root)`, and `cfg =
   managed.effective_config(layers.effective, survey)`: a present
   language with no mode runs as `clean`.
2. Selection. With `PATH ...`: each surveyed file at or under each
   path; a path outside the root or with no surveyed file prints one
   line and is skipped. With `--changed`: the surveyed files in
   `changes.working_set(root)`. With neither: every surveyed file. A
   path that a `cfg.ignore` glob matches is dropped. `PATH` and
   `--changed` together give exit 2.
3. Render. `tempfile.TemporaryDirectory(prefix="trueup-lint-")` is
   `cfgdir`. Each `RuleSet.files` entry of each enabled rule set is
   written to `cfgdir/<key>`, with the token `__TRUEUP_ROOT__`
   (`rulesets.ROOT_TOKEN`) replaced by the absolute root (the php
   templates use it in `paths`, `excludePaths` and `includes`). The
   eslint pair is not written here (D14.7). When a language is
   `strict`, `cfgdir/jscpd.json` follows. When `docs` resolves to
   `full`, the Vale files go to `cfgdir/vale/`, and `Banned.yml` comes
   from `docrules.banned_words(cfg)`; with an empty list, no
   `Banned.yml` is written. In global mode, the checker config of D14.5
   goes to `cfgdir/ref_check.toml`. Nothing is written under the root
   (I-47).
4. Hooks. For each `Hook` of `managed.lint_hooks(cfg)`, in `LANGUAGES`
   order, the selected files that match `hook.files`, `hook.types_or`
   and not `hook.exclude`, as pre-commit selects them. A hook with
   `pass_filenames` and no file is skipped. A whole-tree hook runs when
   the selection is the full survey or holds a file of its language.
   The command is `shlex.split(hook.entry)`, each token formatted with
   `cfg=cfgdir`, `eslint=<eslint package directory>` and `root=root`,
   then `rulesets.owned_file_args`, then the files; the working
   directory is the root. `lint_hooks` holds no gitleaks hook: `check`
   runs gitleaks for `secret-content`.
5. Checker. When the selection is the full survey or holds a Markdown
   page or a source file, the bundled `ref_check.py` runs with `--root`
   and `--config cfgdir/ref_check.toml`. In copy mode the target's copy
   at `[refs] path` runs with no `--config`; a missing copy prints one
   line and is skipped.
6. A tool that is not on the path (`shutil.which` on the first token
   after `env` and its assignments; a `vendor/bin/...` tool must be an
   executable file under the root) prints `trueup lint: <tool> is not on
   the path; <language> <mode> skipped`, once, and the run goes on.
   eslint with no `node_modules` in its package directory prints
   `trueup lint: eslint packages are not installed; run trueup lint
   --install`.
7. Exit 0 when each tool that ran exited 0; 1 when one did not (each
   tool prints its own output, and lint adds `<hook> failed (exit
   <n>)`); 2 on a `ConfigError` or a bad command line.

Hook table (`trueup/rulesets.py`).

- `RuleSet.files` keys have no `lint/` prefix: `python/ruff.toml`,
  `rust/clippy.toml`, `shell/shellcheckrc`, `sql/.sqlfluff`,
  `go/golangci.yml`, `php/phpstan.neon`, `php/phpcs.xml`,
  `php/phpmd.xml`. They are paths under `cfgdir`.
- `Hook.entry` uses `{cfg}`, `{eslint}` and `{root}`: for example `ruff
  check --config {cfg}/python/ruff.toml`, `shellcheck --rcfile
  {cfg}/shell/shellcheckrc --severity style`, `golangci-lint run -c
  {cfg}/go/golangci.yml ./...`, `vendor/bin/phpstan analyse -c
  {cfg}/php/phpstan.neon`, `npx jscpd@4 --config {cfg}/jscpd.json` and
  `vale --config {cfg}/vale/.vale.ini`. clippy reads its config through
  `CLIPPY_CONF_DIR={cfg}/rust`.
- eslint runs as `npx --prefix {eslint} eslint --config
  {eslint}/run-<pid>.mjs --max-warnings 0`. The `sh -c 'if test -f
  ...'` wrapper of D13.6 is gone. `owned_file_args` adds
  `--suppressions-location <[eslint] suppressions>` only when that file
  exists under the root, so the D13.6 rule holds in Python.
- pydoclint (strict Python) gets `--baseline <[python]
  pydoclint_baseline>` only when that file exists under the root. The
  person creates the file; trueup never writes it (I-47).

## D14.7 — The eslint package directory

Amended by D15.5 (2026-11-02): `trueup lint --install` also installs
jscpd and sqlfluff in the tools directory of the trueup cache. They are
part of the second network path (I-28).

`managed.eslint_dir(cfg)` is `config.cache_home() / "eslint" /
<first 16 hex digits of the SHA-256 of the package.json>`, where the
package.json is `rulesets.render_eslint_package(typescript, vue)` for
the effective modes. It is `None` when TypeScript and Vue are both off.
Each set of packages has its own directory, outside every target.

eslint 10 finds its plugins from the directory of its config file
upward, and it has no option to look in a different directory. So
`trueup lint` writes the config of the run as
`<eslint_dir>/run-<pid>.mjs` (`rulesets.ESLINT_RUN_CONFIG`), from
`render_eslint_config(typescript, vue, cfg.eslint_off)` (D13.5 is
unchanged), and removes it in a `finally`.

`trueup lint --install` writes the package.json into the eslint package
directory, runs `npm install --prefix <eslint_dir> --no-audit
--no-fund`, and exits with npm's exit code; it lints nothing. It is the
second path that opens the network (I-28); a plain `lint` never runs
npm. The plugin cache under `~/.claude/plugins/` is not used, because an
update of the plugin replaces it.

`managed._tool_findings` gives `tool-missing:typescript/node_modules`
(`info`) when TypeScript or Vue is on and the eslint package directory
holds no `node_modules`. Its action is `run trueup lint --install`.

## D14.8 — The managed set after this round

`managed.render(cfg, survey)` gives only these paths:

| Path | When |
|---|---|
| `trueup.toml` | from T1, or at any tier when the file exists; the text is `config.render` of the target layer (D14.3) |
| the checker copy at `[refs] path` | `[refs] mode = "copy"`, at any tier |
| `ref_check.toml` | `[refs] mode = "copy"`; T1 when `refcheck_switches_on`, else T2, or when the file on disk is trueup's |

The earlier paths are in one tuple, `managed.LEGACY_PATHS`:
`.pre-commit-config.yaml`, `.github/workflows/trueup.yml`,
`.editorconfig`, `lint/jscpd.json`, `lint/gitleaks/gitleaks.toml`,
`.claude/rules/trueup.md`, `lint/typescript/eslint.config.mjs`,
`lint/typescript/package.json`, `lint/typescript/node_modules` and the
nine Vale files under `lint/vale/`. The names of the constants stay
importable (D14.22 item 10). One row reads the tuple:

- `managed-legacy:<path>`, category `setup`, severity `info`, not
  automatic. It comes for a `LEGACY_PATHS` file that an earlier trueup
  wrote (the managed header, the `"_managed": "trueup"` JSON key, or,
  for a file with no comment syntax, the path), for
  `lint/typescript/node_modules` when it exists, and for a surveyed file
  under `lint/` whose first line is the managed header or whose JSON
  holds the managed key. A file with no such mark is the person's own
  and gets no row. The action is `trueup no longer manages this file;
  remove it when you have moved to trueup lint (see the reference
  page)`. An `info` row never joins the plan (D5.4), so it changes no
  exit code (I-42).

Other rows.

- `file-managed` rows come only for the paths of the table. A target
  with its own `.pre-commit-config.yaml` gets no finding for it.
- `gitignore:.gitignore` comes only when `[scratch] gitignore` is true.
- The `tool-missing:<lang>/<tool>` info rows stay, because `trueup lint`
  needs the tools. `tool-missing:refs/trueup` stays in global mode.
- `setup:trueup.toml` (the T0 and T1 opt-in) folds the `config` and
  `tool-missing` rows only.
- `survey.TRUEUP_OWN_PATHS` and `is_trueup_path` keep their entries in
  this release, so a target that still holds the old files keeps its
  tier (I-43).
- `_min_tier` keeps the copy-mode rule. The T1 rule of `ref_check.toml`
  is `refcheck_switches_on` (D14.5).

This repository is its own adopter, in copy mode. Its old managed
output was removed with a plain `rm`, never `git rm`: `lint/python/`,
`lint/gitleaks/`, `lint/vale/` and `.claude/rules/trueup.md`.
`.editorconfig` and `.github/workflows/trueup.yml` stay as the
repository's own files, with no managed header; the workflow runs
`trueup lint` and `trueup check`. `.pre-commit-config.yaml` is the
repository's own file, with a `repo: local` entry that runs `trueup
lint` (D14.9). `lint/ruff.toml`, `lint/.sqlfluff` and `lint/ts/` are the
D1.5 configs of this repository and stay. `ref_check.toml` is rendered
again in copy mode.

## D14.9 — Templates and the pre-commit entry

```
trueup template <name>
```

prints one text and exits 0. No name, or an unknown name, prints the
names on standard error and exits 2. `template` takes no `--root`.
`managed.template_text(name)` maps each name to its text.

| Name | Text |
|---|---|
| `pre-commit` | `managed.render_pre_commit()`: a `repos:` list with one `repo: local` hook, `id: trueup-lint`, `name: trueup lint`, `entry: trueup lint`, `language: system`, `pass_filenames: true`, `require_serial: true` |
| `editorconfig` | `trueup/templates/editorconfig` |
| `ci` | `managed.render_ci()`: `trueup/templates/ci/trueup.yml`, with pinned actions (I-32), an install step that holds a placeholder comment for the trueup install, then `trueup check --root .` and `trueup lint --root .` |
| `contributing`, `security`, `code-of-conduct`, `changelog`, `issue-template`, `pr-template` | the page under `trueup/templates/health/`, less its first skeleton line |

No printed text holds a trueup header line: the person owns the file.
The action text of a health row names `trueup template <name>`.

`.pre-commit-hooks.yaml` of this repository holds a `trueup-lint` hook
(`entry: trueup lint`, `language: python`, `pass_filenames: true`,
`require_serial: true`) for the day the repository has a remote, beside
`trueup-baseline`.

## D14.10 — SessionStart text replaces the agent rules file

`hooks._session` prints the agent rules from the effective config, in
place of a rules file in the target:

```
trueup: profile <name>, tier <tier>, docs <docs>.
Languages: <lang>=<mode>, ...
Write docs in Simplified Technical English: short sentences, active voice, one topic a page.
Put a page under <docs_dir>/ in one type: tutorial, how-to, reference or explanation.
Start a comment marker with a registry word: ref, arch, law, SAFETY or TODO.
Cite a design id only in a form that <docs_dir>/ARCHITECTURE.md declares.
Root rule: a new file at the repository root must be on the base list or in [root] allow in trueup.toml.
Scratch rule: a tmp/temp/scratch/notes/*.bak/*.orig/*~-style name goes under .scratch/, never tracked elsewhere.
Managed-file rule: apply rewrites trueup.toml; edit it by hand or with apply --set.
Run trueup check before you finish. Fix each finding or report it.
```

The `Languages` line comes only when a mode is set. The page-type line
comes only when `[layout] types` is true, the marker line only when
`[refs] comments` is true, and the design-id line only when `[refs]
registry` is true. `trueup/templates/claude/trueup-rules.md` is deleted,
and `.claude/rules/trueup.md` is a `LEGACY_PATHS` entry.

## D14.11 — Hooks: the target gate, the base list, `ask`

- `hooks._dispatch` returns before any other work when
  `config.load_target(root)` is `None`; then it takes `cfg =
  config.load(root)`. So a user default file never turns a hook on in a
  repository that has no `trueup.toml` (I-22).
- `hooks.base_root_allow(cfg)` gives the base list of root globs:
  `cfg.root_base` when it is set; else `_CODE_ROOT_ALLOW` (the earlier
  entries, CI and tool files such as `Dockerfile`, `CODEOWNERS`,
  `.gitlab-ci.yml`, `tsconfig.json` and `requirements*.txt`), each name
  of `layout._STANDARD_ROOT_NAMES` as a glob that ignores case
  (`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` and the
  others), `survey.MANIFEST_NAMES` (D14.13) and
  `hygiene._LOCKFILE_NAMES`, with no duplicates. `[root] allow` and the
  entries on disk add to it.
- `_check_write`: a new root file that none of the base list, `[root]
  allow` and the entries on disk names gets `ask`, not `deny`. The
  reason says to add the name to `[root] allow` to stop the question. A
  scratch-looking name still gets `deny`. The guard never answers
  `allow` (I-29).
- `hooks._scratch_denied(path, cfg)` takes the `v<n>` exemption under
  `cfg.layout_docs_dir` (D14.12 C2), so the guard and `check` agree on
  each name.

## D14.12 — Defect fixes

The public targets of `00-request.md` showed five defects.

**C1 drift and baseline.** `drift._python_flags` and
`baseline._python_docstring_percent` catch `(SyntaxError, ValueError,
RecursionError)`. A file that `ast.parse` cannot read gives no flags, or
is skipped. Before the fix, one cpython file stopped every `check`.

**C2 a `-v<n>` page under the docs directory.** `hygiene.looks_scratch`
is unchanged. `hygiene._versioned_document(name)` is true when only the
`v<n>` copy marker makes a document name scratch.
`hygiene.looks_scratch_path(path, docs_dir)` does not count such a name
when the first segment of the path is `docs_dir`; `draft`, `copy`,
`old`, `backup` and ` copy` still count there. `scratch_looking` passes
`cfg.layout_docs_dir`, and the guard applies the same exemption
(D14.11).

**C3 anchors.** `ref_check._heading_slugs(text)` gives a larger set: the
GitHub slug of each ATX heading, as before; the value of each `id` or
`name` attribute of an HTML tag outside fenced code, in single or double
quotes; the id of an attribute list `{#x}` at the end of a heading, and
the slug of the heading text without it; and the python-markdown `toc`
slug of each heading (`_toc_slug`). The set only grows, so each fragment
that resolved before still resolves.

**C4 `.pem`.** `hygiene._is_secret_file(root, path)`: for a `.pem` name
it reads at most the first 64 bytes. A first line that starts with
`-----BEGIN CERTIFICATE-----`, `-----BEGIN X509 CRL-----`, `-----BEGIN
PUBLIC KEY-----` or `-----BEGIN CERTIFICATE REQUEST-----` is public and
gives no `secret-file` row. Any other first line, an empty file or a
read error gives the row. Each other secret name stays a name-only test.
No finding holds bytes of the file (I-23).

**C5 the guard.** D14.11.

## D14.13 — Tier model

`trueup/survey.py`.

- `TIER_EXTENSIONS` holds every extension of `LANGUAGE_EXTENSIONS` and
  `java kt kts scala groovy c h cc cpp cxx hpp hh cs fs rb swift m mm
  dart ex exs erl hs ml mli clj cljs lua pl pm r jl zig nim nix el`.
  `run` uses it for `total_lang_files` only. `LANGUAGE_EXTENSIONS` and
  `Survey.languages` do not change (I-13): the comment scan and the rule
  sets keep eight languages.
- `MANIFEST_NAMES` adds `pom.xml`, `build.gradle`, `build.gradle.kts`,
  `settings.gradle`, `settings.gradle.kts`, `Gemfile`,
  `CMakeLists.txt`, `meson.build`, `Package.swift`, `mix.exs`,
  `pubspec.yaml`, `build.sbt`, `setup.py`, `deno.json`, `Makefile.PL`,
  `cabal.project`, `stack.yaml` and `flake.nix`. `requirements*.txt` is
  not a manifest: several at depth would push a repository to T3 by the
  three-manifest rule. `hygiene._artifact` reads the same tuple, so
  `build/` beside a root `build.gradle` or `CMakeLists.txt` is build
  output.
- `CI_PATHS`: `has_ci` is true when a tier file matches
  `.github/workflows/*.yml` or `*.yaml`, `.gitlab-ci.yml`,
  `.circleci/config.yml`, `Jenkinsfile`, `.travis.yml`,
  `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `.woodpecker.yml`,
  `.woodpecker/*.yml`, `.drone.yml`, `.forgejo/workflows/*`,
  `.gitea/workflows/*` or `.buildkite/pipeline.yml`. `is_trueup_path`
  still removes trueup's own workflow first (I-43).
- The thresholds of `_pick_tier` do not change. On the measured targets,
  the Maven fixture moves from T0 to T1, and each other target keeps its
  tier.

## D14.14 — Hot spots and `--changed` scope

- **Banned words.** `docrules._prefilter(words)` compiles one
  alternation of every entry, case-free, once for each distinct tuple
  (`functools.lru_cache`). `_first_hits` runs the entry patterns only on
  the lines that the alternation hits, so the findings are the same as
  those of the loop over every entry. One alternation alone is not the
  scanner, because it changes the finding on entries that overlap.
  `_prose_findings` tests the extension before it reads a file.
- **Scratch references.** `hygiene._scratch` builds one index before the
  candidate loop: each other text file is read once (1 MiB cap), the
  texts are grouped by directory, and one corpus holds them all.
  `_referenced(path, index)` searches the group of the directory of the
  candidate for its relative path, and the corpus for its full path. The
  D10.12 rules hold: a bare basename in a file of another directory does
  not count.
- **Hygiene under `--changed`.** `hygiene_findings(survey,
  secret_findings=None, only=None)`. With `only`, `_scope` gives the
  paths that the `scratch`, `artifact` and `duplicate` rows check: the
  changed paths and, when one of them looks like scratch or is 64 bytes
  or more, each other member of a content group that holds one of them.
  The `duplicate` row runs only when the changed set holds a file of 64
  bytes or more. `report.collect` passes `only`. So the Stop hook builds
  no scratch index when no changed file looks like scratch.
- **Secrets under `--changed`.** `secrets.scan(root, survey, history,
  only=None)`. With `only` in working-tree mode, the scan set is the
  changed paths that the survey holds and that are a file or a symlink
  on disk. trueup copies them into a temporary tree with the same
  relative paths and runs `gitleaks dir` there. The report paths and the
  config path globs are the same as in a full run. trueup also copies
  `.gitleaksignore`, because gitleaks reads it from its working
  directory. An empty scan set
  starts no gitleaks. History mode ignores `only`. D6.17 holds: a secret
  finding is local to its file.
- **Link notes.** `layout._broken_link_evidence_notes` looks up each
  target basename in `_basename_index`, built once from the surveyed
  files. I-39 holds: the notes add evidence only.
- **Drift under `--changed`.** `drift.drift_findings(survey, only)`:
  `drift-undocumented` parses only the `.py` files in `only`, and
  `drift-flag` parses what the changed docs name. D6.17 holds: the
  scoped findings equal the full-run findings whose path is in `only`.

## D14.15 — Tests

- `tests/conftest.py` has an autouse fixture. It points
  `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` at directories under
  `tmp_path`, removes `TRUEUP_PROFILE`, and calls `config.clear_cache()`
  before and after each test. So no test reads the real profiles, user
  default file or cache. D14.23 item 2 adds `UV_CACHE_DIR`.
- `tests/fixtures/adopters/<name>/trueup.toml` holds copies of the four
  adopter files (D14.22 item 1). `tests/test_adopters.py` proves the
  round trip of D14.23 item 1 on each.
- `tests/test_profiles.py`: the built-in files, the precedence of the
  layers, a user profile that resolves and one that does not (exit 2,
  both search paths in the message), a user file with a built-in name,
  a bad name, the user default file only without a target file, the
  same `check --json` with and without a user default file beside a
  target file, `apply` that writes no key of the profile, and the cache.
- `tests/test_docrules.py`, `tests/test_hygiene.py` and
  `tests/test_layout.py` keep their expected findings: the pre-filter,
  the index and the notes lookup change no row.
- `tests/test_lint.py` and `tests/test_template.py` cover D14.6, D14.7
  and D14.9; `trueup lint --install` mocks the subprocess, so no test
  opens the network.
- Each new test cites `arch: D14.<m>` in its docstring.

## D14.16 — Docs, skill, brief, packaging

- `docs/ARCHITECTURE.md`: the D14 sections, the subject index rows, the
  round 14 row and the invariant changes of D14.17.
- `docs/reference/trueup.md`: every D14.2 key in the config table; a
  profiles section with the search paths, the precedence, the two
  built-in profiles and how to write a profile; `trueup lint`, `trueup
  template` and `--profile`; the managed set of D14.8; and a section on
  the move from the managed lint tree, with `LEGACY_PATHS` and the
  pre-commit entry.
- `docs/BRIEF.md`: a decision row of 2026-10-16. The house standard is
  the `house` profile, a repository copies nothing but `trueup.toml`, and
  `trueup lint` renders the tool configs at run time.
- `docs/explanation/purpose-and-state.md`: a status entry for the round.
- `skills/trueup/SKILL.md`: the first run, the approval, the adoption of
  a JS or TS codebase, the hooks and the verify steps follow D14.6 to
  D14.10, with the pre-commit entry and no `npm install --prefix
  lint/typescript`.
- `pyproject.toml`: the package data `data/*` becomes `data/**/*`, so
  the wheel holds `trueup/data/profiles/`.
- `README.md`: one line for `trueup lint` where it names the managed
  set.

## D14.17 — Invariant amendments and new invariants

The text is in [Invariants](#invariants).

- I-22 gains the target gate: a user default file never turns a hook on.
- I-23 gains the `.pem` exception of D14.12 C4.
- I-25 becomes "one banned list in force for a run".
- I-28 gains `trueup lint --install` as the second network path.
- I-33 gains the rule that `render` writes only the target layer.
- I-42 gains the `managed-legacy` row: it informs, it never asks.
- I-44 to I-48 are new: same file, same output; `apply` writes the
  target layer; built-in names are fixed; `lint` writes nothing under
  the root; `house` is the earlier output.

## D14.18 — Case 1: `check` on a target with a profile

1. `cli` resolves the root. `--profile NAME` sets `TRUEUP_PROFILE` in
   `os.environ` before any load (`cli._set_profile`).
2. `survey.run` calls `config.load(root)`. The loader reads the target
   file and its `profile` key, finds the profile file (the built-in
   directory for a built-in name, the user directory for any other
   name) and merges the layers over `Config()`. Later loads come from
   the cache.
3. `report.collect` runs the rows with the effective config. The
   checker reads the D14.5 text from a temporary directory.
4. The Markdown report prints `profile <name> (<path>)`, and the JSON
   report holds the `profile` block.

A profile name that resolves nowhere stops the run at exit 2 before any
row runs, with a message that names both search paths. `check
--baseline` stops the same way before it compares.

## D14.19 — Case 2: `apply` round trip

1. `apply` loads the layers. The run starts from `layers.target`, or from
   no config when the target has no file.
2. `_merge` adds the modes and the `--set` values to the target layer
   and to `explicit`.
3. `config.render(target)` writes the file: the explicit keys and the
   values that are not the default. No value of a profile or of the user
   default file reaches the file (I-45).
4. `managed.render(effective, survey)` gives `trueup.toml` and, in copy
   mode, the checker pair. The handlers run. `_stamp_run_date` changes
   the `run_date` line only when the target file exists.

## D14.20 — Case 3: `lint`

`lint.run` does the steps of D14.6. The temporary directory goes away
when the `with` block ends, and the eslint run config goes away in a
`finally`, also when a tool fails. A test takes a snapshot of the tree
before and after a run, and finds no change under the root (I-47).

## D14.21 — Case 4: the Stop hook under `--changed`

`hooks._dispatch` gates on `load_target`. The Stop hook runs
`report.collect(root, only=<session set>)`: the document rows narrowed
to the changed files, the locator scoped, drift scoped to the changed
`.py` files and the docs that they name, hygiene with `only` (no scratch
index when no changed file looks like scratch), and no checker run. The
time targets on this machine are 2 s on the target-rust superrepository and 3 s
on the fastapi clone; the last stage of the round measures them and
reports the numbers. They are not a fail condition, because the machine
is loaded (D14.22 item 8).

**Failure analysis.** The scenario that is most likely to break the
round: a committed `profile = "mine"` whose file is only in the user
directory of the owner, read in CI, on another machine or in the test
suite.

- The failure is loud. The loader raises `ConfigError`, the run exits
  2, and the message names both search paths (D14.1). CI fails at once
  and tells which file to add or which name to change. No run passes on
  weaker rules.
- `check --baseline` exits 2 before it compares, so the baseline gate
  (D6.7) cannot drift without a report.
- `apply` writes only the target layer, so no value of the profile goes
  into the committed file (D14.3, I-45). A test of D14.15 proves it.
- The test suite cannot read the real profiles of the owner: the
  autouse fixture moves `XDG_CONFIG_HOME` under `tmp_path` (D14.15).
- The hooks fail open as before (I-22). A `ConfigError` in a hook
  prints nothing and gives exit 0; the person sees the error at the next
  `check`.
- A built-in name gives the same rules on each machine (I-46).

The residual risk: a target with no `trueup.toml` that uses the user
default file of the owner gives an output that depends on the machine.
The owner asked for this: a target can hold nothing. The report prints
`profile <name> (<path>)`, so a CI log shows which profile file the run
read.

**Alternatives.** These designs were rejected:

- **Profiles with `extends`.** It needs a chain walk and a cycle check,
  and no person needs it yet. A person copies the lines of
  `minimal.toml` that they need.
- **A profile that holds a complete `Config`, with the target over
  it.** Each new key makes an edit of each user profile necessary.
- **The user default file as a layer under a target file too.** It
  breaks I-44: the same committed file gives a different output on each
  machine.
- **A persistent render cache for the tool configs.** A render takes
  milliseconds, and a cache adds invalidation errors. Only the eslint
  package directory persists, because `npm install` is slow and uses the
  network (D14.7).
- **A managed `.pre-commit-config.yaml` that calls `trueup lint`.** The
  target still holds a trueup file, and fastapi, which has its own
  pre-commit file, keeps a permanent error.
- **One alternation regex as the banned-word scanner.** It changes the
  findings where entries overlap. It is a pre-filter instead (D14.14).
- **Configurable marker words.** D2.2 is frozen; `[refs] local_tags`
  covers the tags of a project.
- **`deny` for an unknown root file, with a longer list.** A list is
  never complete: `pom.xml` today, the next manifest tomorrow. `ask`
  keeps the person in control, and I-29 stays true (D14.11).
- **`--profile` as an argument of each `load` call.** That is ten call
  sites in five modules. The environment variable `TRUEUP_PROFILE` is
  one line, and CI can use it too (D14.22 item 5).

In each pair, the design with fewer moving parts won.

## D14.22 — Gap resolutions

These items answer the gaps that the task split of the round found.
Each one states what the code does.

1. **Adopter sources.** `tests/fixtures/adopters/` holds read-only
   copies of four `trueup.toml` files: this repository (`trueup`),
   target-web (`target-web`), target-web-3d (`target-web-3d`) and target-rust/src
   (`target-rust-src`).
2. **gitleaks config.** `secrets.scan` renders
   `managed.render_gitleaks_config(cfg)` into its own
   `TemporaryDirectory(prefix="trueup-gitleaks-")` and passes `--config
   <that file>`, as D8.1 does for the checker. A target's
   `lint/gitleaks/gitleaks.toml` is not read any more; it is a
   `LEGACY_PATHS` entry. `render_gitleaks_config` keeps its name and its
   output.
3. **`render_ref_check_config` signature.** It is
   `render_ref_check_config(cfg, survey, keep=True)`. The tier comes from
   `survey.tier`, and `refcheck_switches_on` and `resolve_docs` run
   inside. The callers are `docrules._refcheck_config_text`,
   `managed.render`, `lint` and `cli._run_refs`; `cli._run_refs` runs
   `survey.run(root)` first.
4. **`trueup template`.** `managed.render_pre_commit()` and
   `managed.render_ci()` take no argument. `managed.template_text(name)`
   maps every D14.9 name to its text; `editorconfig` and the health
   pages read `rulesets.template_path`. `render_editorconfig` is not
   needed.
5. **`--profile` placement.** `survey`, `check`, `baseline`, `apply` and
   `lint` take `--profile NAME`, and each sets `TRUEUP_PROFILE` before any
   load. `refs` has no flag, because it gives its tokens to the checker
   unparsed; it reads `TRUEUP_PROFILE` from the environment. `hook` has
   no flag. `apply --profile` changes the effective config of the run and
   writes nothing; `apply --set profile=<name>` writes the key.
6. **Guard scratch rule.** The narrow reading: the guard takes the
   `v<n>` exemption under the docs directory and no directory rule.
   `hooks._scratch_denied` calls `looks_scratch(name)` and
   `_versioned_document(name)` for a path whose first segment is
   `cfg.layout_docs_dir`. `looks_scratch_path` keeps the `tmp`, `temp`
   and `scratch` directory rule for `check` only.
7. **I-48 reference output.** Before the first task of the round,
   `trueup check --json` of eleven targets went into
   `.state/runs/trueup-universal/00-check-baseline/`. The last stage
   compares each target with
   `.state/runs/trueup-universal/tools/compare_check.py` and sorts each
   row that differs as allowed (a removed `file-managed` row of a
   `LEGACY_PATHS` path, a new `managed-legacy` info row, a `tool-missing`
   action text, a row that D14.12 fixes, a tier move of D14.13, the new
   `profile` block) or not explained. A row that is not explained is a
   failure.
8. **Timing targets.** The target-rust superrepository root (2058 files) and a
   fastapi clone. The last stage measures `trueup check --changed` after
   it touches one tracked `.py` file, and reports the time beside the 2 s
   and 3 s targets.
9. **Maven fixture.** A test builds a temporary tree with 20 `.java`
   files, `pom.xml`, `.gitlab-ci.yml` and `doc/guide.md`, and commits it
   with `git -c commit.gpgsign=false commit`.
10. **Lockfile exemption.** `rulesets.ESLINT_PACKAGE_TARGET` keeps its
    name and value as a `LEGACY_PATHS` member, and `hygiene` keeps the
    D8.3 exemption in this release. So a target that still holds the old
    `lint/typescript/package.json` gets no `lockfile` row.
11. **eslint base path.** With `--config <a file outside the root>` and
    the root as the working directory, eslint 10.12 lints the files on
    the command line, and `files: ["**/*.ts"]` matches them. `lint.run`
    always runs in the root and passes the files. One test runs the real
    eslint when `lint/ts/node_modules` of this repository exists, with
    the config in `tmp_path`, and finds that a known bad file fails; it
    skips otherwise.
12. **`refcheck_switches_on`.** `managed.refcheck_switches_on(cfg,
    survey)` comes from the docs-page arm of `_min_tier`. It is true at
    T2 and T3, and at T1 when `survey.files` holds a Markdown page under
    `{docs_dir}/` at any depth.
13. **phpstan `includes`.** The `__TRUEUP_ROOT__` token applies to every
    path of the php templates: `paths`, `excludePaths` and `includes`.

## D14.23 — Amendments after wave C

Three facts of the code changed the design after the third wave of the
round, on 2026-10-16.

1. **Adopter round trip.** This item replaces the byte rule of D14.15. A
   hand-written `trueup.toml` holds its own comments, key order and
   blank lines, and `render` writes its own order with no comment. So a
   byte equality with the original text cannot hold. The rule is a value
   round trip and a fixed point. For each adopter fixture, `cfg =
   load_target(dir)`, `text = render(cfg)`, and `cfg2 =
   _parse(tomllib.loads(text), ...)`, the same path that `load_target`
   takes. Then `cfg2 == cfg`, `explicit` included, so no key that the
   file set goes away and no value changes. Also `render(cfg2) ==
   text`: a second render gives the same bytes (D5.3). I-45 and I-48
   keep their meaning: `apply` on an adopter changes no value and adds
   no new key.
2. **The fixture keeps the uv cache.** `uvx` also reads
   `XDG_CACHE_HOME`, so the offline rule-set tests that run `uvx
   sqlfluff@4.3.0` lost their cache under the fixture of D14.15. When
   `UV_CACHE_DIR` is not set, the fixture sets it to the real uv cache:
   `$XDG_CACHE_HOME/uv` as it was before the fixture ran, else
   `~/.cache/uv`. The cache of trueup itself (`config.cache_home()`)
   stays under `tmp_path`.
3. **Tests written before the resolver.** Two tests of
   `tests/test_config.py` set `profile = "mine"` in a target file. Under
   D14.1 a name with no file is a `ConfigError`, so each test first
   writes an empty `profiles/mine.toml` under the `XDG_CONFIG_HOME` of
   the fixture.

## Round 15 — Trust on a stranger's repository

Round 15 (D15) makes trueup safe to run on a repository that its owner
did not prepare for it. The soundness audit of 2026-11-02 found that
trueup failed silently, ran the house standard on a target that did not
ask for it, removed files on a name match alone, read files without a
bound and gated on the score. Sections D15.1 to D15.38 and invariants
I-49 to I-53 are the design of the fix.

### Owner decisions of 2026-11-02

The sections cite these decisions by number.

1. Fail-open is for hooks only. `check`, `lint`, `apply`, `refs` and
   `baseline` fail loud: an unexpected exception is exit 2 and one line,
   a degraded engine or a skipped tool shows in the text and the JSON,
   and an empty survey is an error.
2. A target with no `trueup.toml` and no user default file runs the
   `minimal` profile, and the report header says so. `--profile` wins.
   This replaces the silent `house` run (brief row of 2026-11-02).
3. Automatic means that content proves it. `scratch`, `secret-file` and
   `binary` stay rules, but the automatic flag needs content evidence. A
   name-only or size-only match is manual.
4. `trueup lint` exits 2 when a configured tool is absent, after it names
   each missing tool. `--skip-missing` gives the earlier behaviour.
5. A plain `lint` opens no network. jscpd and sqlfluff run only from a
   local install that `lint --install` made.
6. The score counts findings per covered file, and the baseline gate
   reads the per-key counts only, never the score (brief row of
   2026-11-02).
7. The scratch guard asks; it never denies. The install guard's registry
   lookup is off by default.
8. The `SubagentStop` hook entry goes. The Stop hook blocks once, for the
   parent session only.
9. A `[[keep]]` id matches by prefix. `secret-content` and `changelog`
   ids carry a content fingerprint in place of a line number. A keep
   that matches nothing is an `info` row.
10. Platform rows are `info`, never plan rows.
11. The word `harness` leaves the built-in banned list.
12. `RuleSet.nightly` goes, and brief S8 is superseded.
13. A config write of `trueup.toml` loses its comments; the run-date
    stamp never re-renders the file.
14. The one-file checker constraint (D1.1) stays. Closed on 2026-11-09
    (owner ruling 4 of round 16): copy mode ships one file, so the checker
    stays one file.
15. Python 3.11 is the floor, and CI tests it.

### Components

| Component | Changes |
|---|---|
| `trueup/__main__.py` | version gate, hook fast path (D15.7) |
| `trueup/cli.py` | top-level handler (D15.1), root checks (D15.2), profile flag scope (D15.6), `lint --skip-missing` (D15.4) |
| `trueup/config.py` | `Layers.adopted`, `Layers.profile_source`, `load` never `None` (D15.6); merged cross-key checks, resets, `run_date` (D15.29); `[guard]` keys (D15.32); `[health] files` (D15.14); `_read_toml` errors (D15.1); public `KEYS` (D15.36) |
| `trueup/fsread.py` (new) | one bounded reader (D15.22) |
| `trueup/survey.py` | git failures raise (D15.2); tier manifests, other languages (D15.26); bounded reads (D15.22); own paths (D15.37) |
| `trueup/changes.py` | `_git` text, the dirty check refuses on a git failure (D15.2) |
| `trueup/report.py` | JSON schema 1 (D15.3); keeps, stale keeps, SARIF line (D15.8); engine row (D15.20); ignored command paths (D15.17) |
| `trueup/findings.py` | `Finding.line`, `keep_match` (D15.8); `AUTO_RULES` (D15.27) |
| `trueup/score.py`, `trueup/baseline.py` | covered files, gate by keys (D15.21); key by rule (D15.8); catches and shape check (D15.1) |
| `trueup/hygiene.py`, `trueup/secrets.py` | scratch, secret-file, binary, duplicate (D15.9 to D15.12); ids (D15.8); tracked copy scan (D15.20); bounded reads (D15.22) |
| `trueup/layout.py` | tooling exemptions, doc tree, generated pages (D15.13); history (D15.25); untracked moves (D15.27); keep prefix (D15.8); one parser (D15.30) |
| `trueup/health.py`, `trueup/drift.py` | names, licence, `public` (D15.14); platform rows (D15.15); drift (D15.17); catches (D15.1) |
| `trueup/ref_check.py`, `trueup/docrules.py` | Markdown and README (D15.18); Rust leaders (D15.19); speed (D15.23); one parser (D15.30); licence helper (D15.14); catches (D15.1); keep prefix (D15.8); changelog id (D15.8) |
| `trueup/lint.py`, `trueup/rulesets.py`, templates | missing tools (D15.4); jscpd and sqlfluff local (D15.5); rule sets (D15.28) |
| `trueup/apply.py` | stamp, writes, plan validation, untracked moves, cache (D15.27, D15.29) |
| `trueup/hooks.py`, `hooks/hooks.json` | session notice (D15.7); log cap, timeout (D15.24); scratch asks (D15.31); install guard (D15.32); no `SubagentStop` (D15.33); session text (D15.34); `git add` segments (D15.35) |
| `trueup/data/` | `banned.txt` and the Vale style (D15.16); `house.toml`, `minimal.toml` (D15.14, D15.29) |
| `scripts/check_targets.py` | engine check (D15.20) |
| docs, skill, CI, tests | D15.36 to D15.38 |

### Sequences

1. `check` on a stranger's repository: `cli.main` → `_resolve_root`
   (D15.2) → `config.profile_flag` → `load_layers` (`minimal`, source
   `built-in default`, D15.6) → `survey.run` (git required, bounded
   reads) → `secrets.scan` on the tracked copy (D15.20) → the rules
   (content evidence) → `build_plan` with prefix keeps → stale keeps →
   render (schema 1, profile line). An unexpected exception gives exit 2
   and one line.
2. A hook in a repository with no `trueup.toml`: the `__main__` version
   check → read standard input → walk up to `.git` → no `trueup.toml` →
   exit 0, no import, no log line.
3. `apply --plan saved.json --ids X`: load the saved rows → the
   `AUTO_RULES` predicate for each approved row on the current tree → the
   dirty check (a git failure refuses) → the handlers through
   `_safe_target` → the stamp line edit → the cache clear.

### Failure analysis

1. **Decision 2 turns the suite red in more than 30 places.** The D15.6
   change runs first and alone. It pins `profile = "house"` on each test
   that relied on the silent `house` run, so each test keeps what it
   tested. Every later change starts from a green suite.
2. **S23 cannot converge after D15.9 and D15.10.** The S23 scramble
   operations change to junk that content proves, and a second test
   asserts that the realistic shapes give manual rows (D15.38).
3. **The checker change (D15.18, D15.19) moves `apply._rewrite_links`.**
   One change owns `ref_check.py` and runs `tests/test_move.py`.
4. **A doc edit records a fact that a later code change alters.** The doc
   edits of a group of changes land after the code of that group, and the
   skill drift test (D15.36) finds what remains.

### Alternatives rejected

- Keep `load() is None` and change the fallbacks to `minimal`: more
  sites, and "not adopted" would still mean two things.
- Collect again in `apply --plan` to validate the rows: I-40 forbids it.
- Run `git check-ignore` inside drift: a pinned test forbids a subprocess
  there. The caller passes the set.
- Use the gitleaks fingerprint for line-free ids: it holds the line.
  trueup computes a content fingerprint.
- Split `ref_check.py` into a package: decision 14 defers it.

## D15.1 — Loud failures

Decision 1. `cli.main(argv)` puts the whole dispatch inside one handler:

```python
try:
    ...
except ConfigError as exc:          # unchanged
    print(f"trueup: {exc}", file=sys.stderr); return 2
except Exception as exc:            # noqa: BLE001  # reason: D15.1 last-resort handler
    if _is_hook(argv): return 0     # I-22: a hook stays silent
    if os.environ.get("TRUEUP_DEBUG") == "1": traceback.print_exc()
    print(f"trueup: internal error: {type(exc).__name__}: {exc} "
          "(set TRUEUP_DEBUG=1 for the traceback)", file=sys.stderr)
    return 2
```

`MemoryError` and `RecursionError` are subclasses of `Exception`. So they
come to this handler when no narrow catch takes them. `KeyboardInterrupt`
and `SystemExit` pass. `_is_hook(argv)` is true when the first word that
is not an option is `hook`.

Each narrow catch below gives the named result, never an abort.

| Site | Before | After |
|---|---|---|
| `drift._python_flags` | catches `(SyntaxError, ValueError, RecursionError)` | adds `MemoryError`; an empty flag set |
| `baseline._python_docstring_percent` | the same | adds `MemoryError`; skips the file |
| `ref_check.run` | no `RecursionError`, no `MemoryError` | adds both to the `unreadable` failure tuple |
| `ref_check._python_test_functions` | the same | adds both; `[]` |
| `drift.py` manifest readers | `.get` on a value that is not a table | a value that is not a `dict` gives one drift `info` row `drift-manifest:<path>` "manifest not readable: <key> is not a table", and the reader skips it |
| `hygiene._lockfile`, `survey._has_workspace` | `UnicodeDecodeError` escapes | skip the file; hygiene adds one `info` row `manifest-unreadable:<path>` "not UTF-8"; survey treats the file as absent |
| `baseline.load`, `baseline.compare` | `None` or a crash | `load` raises `ConfigError("<file>: not a trueup baseline: <why>")` for bad JSON or a bad shape (`findings: dict[str, int]`, `score: int`, `ratchet: dict[str, dict[str, number]]`) |
| `config._read_toml` | `OSError`, `UnicodeDecodeError` escape | `ConfigError("<path>: cannot read: <reason>")` |
| `report.check` | `tree_identity` runs before the config load, and the message names `--changed` | load the config first; `changes._git` gives `git <cmd> failed in <root>: <first stderr line>`, with no `--changed` text |
| `docrules._refcheck_findings` | the whole stderr in one finding | exit 2 of the checker gives one `refcheck-run:` error finding; its evidence is the last stderr line |

`ref_check.main` gets its own last-resort handler with the same one-line
text (prefix `ref_check:`) and exit 2, because it runs as a subprocess
and in copy mode. The exit-code table of the reference page gains the
row "internal error: 2". I-52 states the rule.

## D15.2 — Git is required

- `survey._list_files` first runs `git rev-parse --is-inside-work-tree`
  with the root as the working directory. A directory that is not a work
  tree gives `ConfigError(f"{root}: not a git repository; trueup reads tracked files")`.
  A failure of `git ls-files` gives
  `ConfigError(f"git ls-files failed in {root}: {stderr}")`.
- `survey._count_contributors` first runs `git rev-parse --verify -q
  HEAD`. No `HEAD` (an unborn branch) gives 0, because `git log` exits
  128 there. Any other failure raises as above. `_count_tags` raises on
  a failure.
- An empty survey (zero files after `ignore`) is
  `ConfigError(f"{root}: no tracked file to check (after [scan] ignore)")`
  from `check`, `apply`, `baseline` and `lint`. `survey` prints the empty
  survey and exits 0, because its output is the survey itself. An unborn
  `HEAD` with untracked files is not empty.
- `changes.dirty_paths` raises on a git failure. It does not return an
  empty set.
- `cli._resolve_root`: a `--root` that does not exist, or is not a
  directory, raises `ConfigError(f"--root {path}: not a directory")`.
- `hygiene._tracked_paths` raises in the same way.
- `trueup refs` needs no git. `cli._refs_config_text` skips the survey
  when `git rev-parse` fails, so `refs` on a plain directory works.
- A test fixture that runs trueup on a directory gives it `git init` and
  one tracked file.

## D15.3 — Report JSON schema 1

The full `check --json` keys are `schema` (int, `1`), `profile`,
`secret_engine`, `secret_note` (a string, `""` when there is none),
`survey`, `findings`, `plan`, `kept`, `moves`, `repins`, `score`, `tree`,
and `baseline` when the run is gated. `profile` is `{"name", "path",
"source"}`. `source` is one of `built-in default`, `user default`,
`target`, `TRUEUP_PROFILE` and `--profile` (D15.6). Each finding object
gains `line` (int, 0 when there is none; D15.8).

The `--changed --json` keys are `schema`, `scope`, `profile`,
`secret_engine`, `secret_note`, `survey`, `findings`, `plan`, `kept` (the
kept findings inside the scope), `tree` and `score` (`null`, as before).

The text header prints the profile line for every target:
`profile <name> (<path>)`. For the built-in default on a target that is
not adopted, the line is
`profile minimal (no trueup.toml; pass --profile house for the house standard)`.
`render_json` gives each new argument a keyword default, so the test that
compares the unscoped JSON with the version 1 join only gains the new
keys.

## D15.4 — `trueup lint` fails when a tool is absent

Decision 4.

- `lint._run_hooks` returns `(failed: bool, missing: list[str])`. A
  missing tool, and an eslint run with no installed packages, each add
  one entry to `missing` and print one line,
  `<tool> is not installed; <label> did not run`.
- `lint._run`: after the run, when `missing` is not empty and
  `skip_missing` is false, it prints one line, the prefix `trueup lint:`
  and then `<n> tool(s) missing: a, b; install them, or pass --skip-missing`,
  and returns 2. When one tool fails and one tool is missing in the same
  run, the result is 2.
- The new flag `--skip-missing` (bool) of `trueup lint` calls
  `lint.run(..., skip_missing=True)`. It gives the earlier behaviour: the
  skip lines, and the exit code of the tools that ran.
- `templates/ci/trueup.yml` stays static (D14.9: it reads no config). It
  installs `ruff` and `vale` at pinned versions, keeps one comment line
  that names the language tools and gives the `--skip-missing` flag of
  `trueup lint` as the opt-out, and runs `trueup lint --root .`.
- The test "a missing tool is skipped with one line" inverts: exit 2, and
  the same tree with `--skip-missing` gives 0.

## D15.5 — jscpd scans the root, from a local install

Decision 5. Amends I-28 and D14.7.

- `templates/rules/jscpd.json` loses `"path"` and gains
  `"gitignore": true`.
- `Hook.entry` gains the format field `{tools}`: the tools directory
  `config.cache_home() / "tools" / <16 hex of the sha256 of the tools manifest>`.
  `JSCPD_HOOK.entry` is
  `"{tools}/node_modules/.bin/jscpd --config {cfg}/jscpd.json ."`. The
  working directory is the root, and `.` is the path argument. The
  missing check uses the tool name `{tools}/node_modules/.bin/jscpd`.
- The sqlfluff clean and strict entries are
  `{tools}/sqlfluff/bin/sqlfluff lint --config {cfg}/sql/.sqlfluff`.
- `lint --install` installs these tools, next to the eslint packages
  when TypeScript or Vue is on. jscpd `4.3.0` exact
  (`npm install --prefix {tools} jscpd@4.3.0`) when any language is
  `strict`. sqlfluff `4.3.0` (`uv venv {tools}/sqlfluff`, then
  `uv pip install --python {tools}/sqlfluff sqlfluff==4.3.0`) when `sql`
  is on. No other part of `lint` opens the network.
- A plain `lint` never runs `npx` with a package name, and never runs
  `uvx`. A hook whose local tool is absent is a missing tool under D15.4.
- The tools directory is part of the second network path of I-28 and
  D14.7. `tests/conftest.py` keeps `UV_CACHE_DIR`.
- A test with two equal 300-line files and `python = "strict"` runs the
  real jscpd that `lint --install` gave, and the duplication hook exits
  1. It skips with a named reason when npm is offline. A unit test with
  `_Recorder` asserts that no argument vector starts with `npx jscpd` or
  with `uvx`.

## D15.6 — The profile resolves on every target

Decision 2. Amends D14.3 and I-48.

- `config.load_layers(root) -> Layers` never returns `None`. `Layers`
  gains `adopted: bool` (a target `trueup.toml` or the user default file
  exists) and `profile_source: str` (the D15.3 values).
- Resolution order, the first hit wins: the `--profile` flag,
  `TRUEUP_PROFILE`, the `profile` of the target, the `profile` of the
  user default file. Else `minimal` when the target is not adopted, and
  `house` when it is. The source names are `--profile`,
  `TRUEUP_PROFILE`, `target`, `user default` and `built-in default`.
- An unknown or invalid name is a `ConfigError` on every target, adopted
  or not. When the flag set the name, the message starts with
  `--profile:`. When the variable set it, the message starts with
  `TRUEUP_PROFILE:`.
- `config.load(root) -> Config` always returns the effective config.
  `load_target(root)` keeps `None` for "no target file"; the hook gate
  uses it. Each reader that tested `load(root) is None` for "not adopted"
  tests `load_layers(root).adopted`: `managed._config_findings`,
  `managed.setup_findings`, `cli._refs_config_text`, `lint._run` (a
  target that is not adopted stays exit 2), `report.profile_block`,
  `apply._stamp_run_date` and `secrets.scan`. The fallbacks
  `cfg if cfg is not None else Config()` stay: they are dead for `load`,
  and callers that pass `None` still use them.
- The flag: `cli.main` runs the handler inside
  `config.profile_flag(name)`. This context manager sets
  `os.environ["TRUEUP_PROFILE"]` and a module value
  `config._FLAG_PROFILE`, and restores both on exit, also on an error.
  `_read_layers` reads `_FLAG_PROFILE` first. The config cache key gains
  the flag value. `_set_profile` checks that the file exists in both
  search paths, not only that the name matches the pattern.
- A test that relied on the silent `house` run sets `profile = "house"`
  (or passes `--profile house`), so it keeps what it tested. The test of
  a target that is not adopted expects `minimal` with the source
  `built-in default`.
- On a target that is not adopted, `minimal` turns the checker registry,
  comments, layout and readme checks off, and links stay on. So a tree
  with `# NOTE:`, `// A1:` and `H3:` labels gives no `refcheck` row, and
  the same tree with `profile = "house"` gives the `unregistered` rows.
- I-48 changes: "With `profile = "house"` set, the fixtures give the
  round-13 findings."

## D15.7 — The launcher gates before import

`trueup/__main__.py` does these steps before `from trueup.cli import
main`:

1. When `sys.version_info < (3, 11)`: for `argv[1] == "hook"`, exit 0
   with no output. Else print
   `trueup: needs Python 3.11 or later, this is <x.y.z>` to stderr and
   exit 2.
2. For `argv[1] == "hook"`: read standard input once and `json.loads`
   it (bad JSON gives exit 0). Take the payload `cwd`, else
   `os.getcwd()`. Walk up to the first directory that holds `.git`. When
   `<root>/trueup.toml` does not exist, exit 0 with no output. Else
   import `trueup.cli` and pass the text on as `io.StringIO`
   (`hooks.run(event, stdin=...)`). The walk uses the same rule as
   `hooks._find_root`, and a test pins the two equal on three paths.
3. A malformed `trueup.toml`: `hooks._dispatch` catches the
   `ConfigError` of `load_target`. For `event == "session"` it prints one
   line on stdout,
   `trueup: trueup.toml is not valid: <message>; the trueup hooks are off until it is fixed`,
   and exits 0. The other events stay silent.

The fast path uses the standard library only (`sys`, `json`, `io`, `os`,
`pathlib`), and no `tomllib`.

## D15.8 — Ids and keeps

Decision 9.

- `Finding` gains a last field `line: int = 0`.
- `findings.keep_match(finding_id: str, keep: Mapping[str, str]) -> str | None`
  returns the keep id that matches: an exact match first, else the
  longest keep id `k` for which `finding_id.startswith(k + ":")`. The
  match stops at a segment: `prose:docs/a` never keeps
  `prose:docs/abc.md`. `build_plan`, `report.kept_findings`,
  `layout.locate` and `managed.kept_failure_ids` use it. `ref_check.run`
  applies the same prefix rule to its `[keep] failures` list. A copy of
  the function lives in `ref_check.py` (D1.1), and a test pins both equal
  on a table.
- New id shapes:
  - `secret-content:<path>:<fp>`, where
    `fp = sha256((path + "\0" + line.strip()).encode()).hexdigest()[:12]`.
    trueup computes it for both engines. For gitleaks it reads line
    `StartLine` of the tracked file; a read failure uses
    `rule + ":" + StartLine`. Equal lines in one file add `:2`, `:3` in
    file order.
  - Two secrets on one line give one finding. Its `evidence` lists every
    rule name, and `line` holds the line number.
  - `changelog:<path>:<fp>`, with the same fingerprint of the defect
    line.
  - `refcheck:` and `repin:` ids keep their line. A keep of
    `refcheck:docs/a.md` keeps every checker row of the page by prefix.
- `baseline.key(finding)` drops the last segment for `secret-content`
  and `changelog` by the rule name, not by `isdigit`. The key stays
  `<rule>:<path>`.
- SARIF `_sarif_line` reads `finding.line`, then the line of a
  `refcheck:` id, else 1.
- Stale keeps: on a full run only, after `build_plan`, each `[[keep]]` id
  that matches no finding gives
  `Finding(id=f"keep-stale:{k}", rule="keep-stale", category="setup", severity="info", path="trueup.toml", evidence="keeps nothing", action="remove the [[keep]] entry or fix its id")`.
  A keep that the checker used (a `refcheck:` keep whose failure
  `ref_check` kept) counts as used.
- The `trueup.toml` of this repository loses its
  `prose:tests/test_docrules.py` keep when the stale row shows it.
- A target that keeps a `secret-content` id with a line number sees it
  become stale. The reference page gains an upgrade note for the new id
  shape.

## D15.9 — scratch: automatic needs a whole-stem name

Decision 3. Part of I-53.

- New `hygiene.scratch_proven(path: str) -> bool`. It is true when the
  basename is `*.bak`, `*.orig` or `*.rej`, or ends in `~`. It is also
  true when the stem before the last suffix is exactly one of `notes`,
  `tmp`, `temp`, `scratch`, `draft` or `untitled`, with optional digits
  after it, and the suffix is in `_SCRATCH_WORD_SUFFIXES`. `draft` joins
  the candidate set only as a whole stem (`draft(\d+)?`), not in
  `_SCRATCH_WORD`.
- `_scratch` sets
  `auto = is_tracked and scratch_proven(path) and not vendored(path)`.
  `vendored(path)` is true for a segment in
  `{"vendor", "third_party", "node_modules"}` at any depth (the names of
  `layout._EXEMPT_SEGMENTS`). A `protect` glob already makes a row manual
  (I-24).
- A candidate that is not proven stays a manual row, for example
  `docs/notes-2024.md`, `temp-sensors.md`, `scratch_buffer.rs`,
  `CHANGELOG-v2.md`, `README.old.md`, `* copy.*` and `.swp`. The action
  of a manual scratch row is "check the file; if it is scratch, `git rm`
  it; else rename it or add a [scratch] allow glob".
- The basenames `.keep` and `.gitkeep` are never scratch.
- The `-v<n>` exemption holds at any depth under the docs directory
  (`docs_dir in parts[:-1]`), in `hygiene.looks_scratch_path` and in
  `hooks._scratch_denied`. Both use one shared helper,
  `hygiene.under_docs_dir(path, docs_dir)`.
- `_referenced` already drops a referenced candidate before the
  automatic decision.

## D15.10 — secret-file: content decides the automatic flag

Decision 3. I-49 replaces the secret clauses of I-23. Part of I-53.

- `hygiene._secret_file_kind(root, path, secret_paths) -> str | None`
  gives `None` (no row), `"manual"` or `"auto"`.
  - Key names (`.pem`, `.key`, `.p12`, `.pfx`, `id_rsa`, `id_dsa`,
    `id_ecdsa`, `id_ed25519`): read at most 64 bytes through `fsread`
    (D15.22). The result is `"auto"` when the head, after `lstrip()`,
    starts with `b"-----BEGIN "` and its first line contains
    `b"PRIVATE KEY-----"`. It is also `"auto"` when `head[0] == 0x30`
    and the head holds the PKCS#12 data OID bytes
    `06 09 2a 86 48 86 f7 0d 01 07 01`. It is `None` when the first line
    is a public PEM banner (`_PUBLIC_PEM_BANNERS`). Else it is
    `"manual"`: a certificate after a label line, a Keynote `.key`, a DER
    key, or a file that cannot be read.
  - `.env` names: `"auto"` when the path is in `secret_paths`, the paths
    of the `secret-content` findings of this run, from either engine.
    Else `"manual"`. `_secret_content` now scans `.env*` files too, with
    a capped read, so `secret_paths` covers them under both engines.
- The manual action for a key name is "check whether the file holds a
  private key; if it does, untrack it, add it to .gitignore and rotate
  the key". For an `.env` name it is "check whether the file holds a
  secret; if it does not, add a [[keep]] entry". The word "rotate"
  occurs only in the automatic action.
- A test that approves `secret-file:.env` builds, at run time, an `.env`
  whose content the patterns match. The test that no row opens the
  content of a secret file asserts I-49: heads of 64 bytes, and no byte
  in the output.

## D15.11 — binary: a NUL byte decides

Decision 3. Part of I-53.

- For each file over `_BINARY_MAX_SIZE` (1 MiB), at every tier, trueup
  reads the first 8 KiB through `fsread`. A NUL byte gives the `binary`
  warn row, as before. No NUL byte gives the `large-text` row:
  `severity="info"`, `category="files"`, `auto=False`, evidence
  `"<path> is <n> bytes of text"`, and action
  `"none needed; add a [binary] allow glob to silence it"`.
- The sniff from 100 KiB to 1 MiB stays at T3 only (D13.2).
- `[binary] allow` globs and the linked-page rule spare both rows.
- A secret-named file over 1 MiB gets neither row. The `secret-file` row
  covers the path, and I-49 forbids a longer read.
- A test that used `b"0" * n` as binary content uses NUL content, and
  gains a `large-text` twin.

## D15.12 — duplicate: a floor and referenced pairs

- One constant, `_DUPLICATE_MIN_SIZE = 256`. `_scope` and
  `_holds_duplicate_size` read it.
- A group goes when every remaining member is `_referenced` by name from
  tracked text. The row stays manual.
- Groups of per-variant files with the same basename are an open owner
  question. Nothing is built for them.
- A test with content of about 100 bytes pads it to 300 bytes.

## D15.13 — No move that breaks tooling

All in `layout.locate`, after `_is_candidate`. `_is_candidate` also feeds
the `artifact` row and does not change.

- Exempt segments for page candidates: `change_log`, `changelog`,
  `locale`, `content` and `_templates`. `templates` and dot directories
  are exempt already.
- Referenced directory: one index for each run, made only when a
  candidate exists, over the text of the tracked files that are not
  Markdown (`hygiene._reference_index`). A page whose directory `d`, or
  the parent of `d` when that parent has two or more segments, occurs as
  `d + "/"` in that text gives no `doc-misplaced` row and no `move:`.
- Content tree: a directory outside the docs directory with more than 20
  candidate pages, counted at its top-most directory below the root,
  loses those pages and gives one `info` row `doc-tree:<dir>/`, "holds
  <n> pages; trueup does not move a content tree".
- Generated page: when the first 5 lines match
  `(?i)\b(auto-?generated|generated by|code generated|@generated|do not edit)\b`,
  the page gives no row. This is in the layout only. `hygiene._generated`
  does not change (I-27: the `AGENTS.md` of this repository starts with
  "GENERATED by").
- An untracked page gets no `move:` (D15.27).

## D15.14 — Health names, licence and `public`

- One shared candidate test in `ref_check.py` (the one-file checker,
  D1.1): `licence_present(root) -> bool`. It matches `LICENSE`,
  `LICENCE` and `COPYING`, each with any extension, at the root, in any
  case. `health.py` imports it. `health-readme` accepts `readme.md` in
  any case. `health-contributing` adds `CONTRIBUTING.rst`.
  `health-changelog` adds `CHANGES.md` and `<docs_dir>/CHANGELOG.md`.
  Health matches every candidate in any case.
- `public = false` written in the target layer
  (`"public" in cfg.explicit`) turns `health-license` off.
  `render_ref_check_config` then writes `[checks] licence = false`. This
  new checker key (bool, default true) turns off `no-licence-file` and
  the `no-section` License failure. An unset `public` keeps the earlier
  behaviour. The health test helper writes `public = false` only when the
  test sets it.
- New key `[health] files = "tier" | "readme"`, default `"tier"`.
  `minimal.toml` sets `"readme"`: then only `health-readme` is required.
- `required_item_count` counts `agents-missing` and `claude-not-linked`
  in the denominator when `[health] agents` is on and the tier is not
  T0. So the numerator and the denominator count the same set.

## D15.15 — Platform rows are info

Decision 10. `health._platform_findings` gives `severity="info"`. The
category stays `security`. A tidy public T0 tree has a plan of 0 rows
and exit 0.

## D15.16 — The banned list

Decision 11. Amends I-25.

The `harness` entry leaves `trueup/data/banned.txt` and
`trueup/templates/vale/styles/Trueup/Banned.yml`. The two files stay
equal line for line. `CANONICAL_BANNED` in `tests/test_rulesets.py`
drops the word. The verb fixtures stay and expect no row. I-25 changes:
"The built-in file matches RULES rule 7, except the word that decision
11 of D15 removed; the `AGENTS.md` prose keeps the verb rule."

## D15.17 — Drift

- `drift_findings(survey, only, ignored=frozenset())` gains an argument.
  `report.collect` gets the missing command-path tokens from a first
  drift pass, `drift.missing_command_paths(survey) -> list[str]`, runs
  one `git check-ignore --no-index --stdin -z` for them, and passes the
  set. drift itself starts no subprocess.
- A command token under an ignored path, or named in the Makefile text
  or in a `scripts` value of `package.json`, gives `severity="info"`.
- `python3 <pkg>` names the flags of `<pkg>/__main__.py` only.
- `_GO_FLAG` also reads
  `flag.(Bool|String|Int|Int64|Uint|Uint64|Float64|Duration)(Var)?`.
- A Cargo `[workspace]` root reads its members: `fnmatch` expands the
  globs over the surveyed `*/Cargo.toml`. Each member with `src/main.rs`
  or `[[bin]]` gives one command, with the flags of that member's `.rs`
  files.
- drift and baseline call `ast.parse(text, filename=str(path))` inside
  `warnings.catch_warnings()` with
  `warnings.simplefilter("ignore", SyntaxWarning)`.

## D15.18 — Checker Markdown and README rules

One fence tracker in `_md_lines_outside_fences`, which also serves
`apply._rewrite_links`. An opening fence of 3 or more backticks or tildes
closes on the same character with at least the same length. A line with
an indent of 4 spaces after a blank line, outside a list, is code. Then:

- `_CODE_SPAN` matches a run of backticks, the text, and the same run.
- `_MD_LINK` takes one level of balanced parentheses in the target, and
  no match after a backslash (`(?<!\\)\[`).
- `_MD_REFERENCE`: a label that starts with `^` is a footnote, not a
  link.
- `_heading_slugs` reads setext headings (a text line followed by `===`
  or `---`), and applies `html.unescape` to the heading text before the
  slug.
- Check g: a target that starts with `/` resolves from the root.
- Check i: HTML block lines before the first H1 are allowed. `title_end`
  comes from the H1 line. `no-index-link` applies only when
  `<docs_dir>/README.md` exists. `Quick Start`, `Quickstart` and
  `Getting Started` count as `Install`.
- Front matter: `key:` followed by `  - item` lines is a list. One pair
  of matching quotes around a scalar goes.
- The shell reader and the suppression reader of check f:
  `<<-?\s*['"]?(\w+)['"]?` opens a heredoc. A line equal to `WORD` (or
  tabs and `WORD` after `<<-`) closes it. A heredoc line is no marker
  position and no suppression position.
- D1.2 gains: "In the other regex readers, a marker-shaped line inside a
  multi-line string gives a false failure."
- Each case gets a fixture under `tests/refs/fixtures/<case>/`. A checker
  test that expects `no-index-link` with no index page gets a
  `docs/README.md.txt` in its fixture.

## D15.19 — Rust doc-comment leaders

`READERS["rust"]` strips the longest of `///`, `//!` and `//`. It sets
`MarkerPosition.docstring = True` for `///` and `//!`, so only R2 applies
there, as for a Python docstring. A test goes through `run` on a fixture
with `src/lib.rs` (`/// arch: D1.1`, `//! arch: D1.2`) and asserts both
edges. The `run` docstring says nine checks. On a large Rust target the
`refcheck` rows can grow by a factor of 60; the round report explains
that growth.

## D15.20 — Secrets on tracked files

- `secrets.scan(..., only=None, history=False)`: the full run uses the
  D14.14 copy path over `survey.files`
  (`scan_paths = _scan_paths(root, survey, frozenset(survey.files))`).
  `history=True` keeps `gitleaks git`. The copy skips a symlink whose
  resolved target is outside the root (D15.22).
- A gitleaks failure (a timeout, a start failure, an exit code or a bad
  report) gives one finding
  `Finding(id="secret-engine:", rule="secret-engine", category="security", severity="error", path="", evidence=<note>, action="rerun the check, or fix the gitleaks run; the built-in engine ran instead")`,
  and the JSON `secret_note` (D15.3). The built-in rows still run.
- `scripts/check_targets.py::run_check`: a run whose `secret_engine` is
  not the configured engine is an error,
  `error = f"secret engine {engine}: {note}"`. The configured engine is
  `"gitleaks"` when `shutil.which("gitleaks")` finds it in the process of
  the script, else `"built-in"`. `tests/test_check_targets.py` gains
  that case with stubs for `subprocess.run` and `shutil.which`.
- Target: `check` on a large adopter tree in under 30 s.

## D15.21 — Score per covered file; the gate reads keys only

Decision 6. Amends D6.7.

- `score.compute`: `covered` is the number of surveyed files that a
  files-category plan finding covers. A finding path that ends in `/`
  covers every surveyed file under it. Another path covers itself. A
  path that is no surveyed file counts 1. Each file counts once.
  `files = 20 * min(1, 10 * covered / max(1, N))`, and the raw text is
  `"<covered> of <N> files"`.
- `baseline.failed(gate)` is
  `bool(gate.new or gate.ratchet_drops or gate.missing_reports)`. The
  score stays in `Gate`, in the text and in the JSON as information.
- The baseline test "a score rise fails with no new key" inverts. A new
  baseline test: `git rm` of four clean files, then `check --baseline`
  exits 0.
- S24 gains a committed-cache operation (40 `.pyc` files under
  `src/app/__pycache__/`, `git add -f`) and the clean-deletion operation
  (D15.38).

## D15.22 — Bounded reads

New module `trueup/fsread.py`:

```python
def read_capped(root: Path, rel: str, max_bytes: int) -> bytes | None:
    """Read at most max_bytes of a tracked file under root.

    Returns None for: a path that lstat cannot see; a device, FIFO or socket;
    a symlink whose resolved target is outside root.resolve() or is not a
    regular file; a file longer than max_bytes (read max_bytes + 1 to know).
    """

def read_text_capped(root: Path, rel: str, max_bytes: int) -> str | None:
    """read_capped, decoded as UTF-8 with errors="ignore"."""

def read_head(root: Path, rel: str, n: int) -> bytes | None:
    """The first n bytes, same refusals, no length limit on the file."""
```

These readers change to it:

- `hygiene.py`: `_read_text_capped`; `_sha256`, which hashes only when
  `read_capped(..., _BINARY_MAX_SIZE)` succeeds, so a larger file leaves
  the duplicate and last-copy groups; `_secret_content`; `_binary`;
  `_is_secret_file` and `_secret_file_kind`; `_lockfile`;
  `_linked_paths`; `_reference_index`; `_generated`.
- `survey.py`: `_read_text` (the line counter, 1 MiB for each file; a
  larger file counts with 0 lines) and `_has_workspace`.
- `layout.py`: `_read_text` and `_is_agent_definition`.
- `drift.py`: `_read_text`.
- `secrets._copy_paths`: skip a symlink out of the root.

D16.10 adds named reads of `docrules.py`, `baseline.py`, `apply.py`,
`health.py` and `managed.py` to this list. The checker (`ref_check.py`) cannot import
`fsread` (decision 14). D16.10 gives it its own reader, with the same
rules and a 16 MiB cap. I-50 states the rule. A test makes a tracked `zero.txt -> /dev/zero` and an
`outside.txt -> /etc/os-release`; `report.collect` ends, and a spy on
`open` and `os.open` records neither target.

## D15.23 — Checker speed

- `_docstring_line_numbers` builds the line start offsets once for each
  file (UTF-8 byte offsets, as `ast.get_source_segment` cuts), and does
  not call `ast.get_source_segment`.
- One parse and one tokenize for each `.py` file in a run: `run` keeps a
  cache for the run, `{path: (tree, units, comments)}`, that
  `_python_positions`, `_check_b` (`_python_test_functions`) and
  `_check_f` read.
- `unit_at` uses a bisect over sorted spans.
- `failure_ids` uses two `collections.Counter` passes.
- `_iter_source_files` prunes a directory when an ignore glob of the form
  `<prefix>/**` covers it.
- `docrules._refcheck_findings` sets `timeout=120`. A `TimeoutExpired`
  gives one `refcheck-run:` error finding, "ref_check.py timed out after
  120 s".
- The tests assert call counts, not seconds: `ast.get_source_segment` is
  patched to raise; an `ast.parse` spy sees one call for each file;
  `failure_ids` equals the earlier function on 5,000 failures.
- Targets: this repository in under 3 s, and a file of 28,000 lines in
  under 5 s.

## D15.24 — Hook log and Stop timeout

- `hooks.run` writes a timing line only when `_dispatch` reports that
  the gate passed. `_dispatch` returns `bool`.
- `_record_time`: when the log is over 1 MiB, it keeps the last 10,000
  lines (a temporary file in the same directory, then `os.replace`). A
  line lost in a race is acceptable.
- `hooks/hooks.json` sets `"timeout": 30` on the Stop entry. A kill
  fails open (I-22).

## D15.25 — History locator

- `_history_renames` runs `git rev-parse --show-prefix` once. It keeps
  only the renames whose old and new paths start with the prefix, and
  strips the prefix from both. This applies to the staged and the
  committed calls.
- New `_history_target(path, history_map, accept)`, used by
  `_resolve_targets` only, follows `old` back through the map until
  `accept` holds. A visited set stops a cycle. The other readers keep the
  map of the newest rename.
- When `git rev-parse --is-shallow-repository` gives `true`, a
  `standard`-basis evidence ends with
  `; history unavailable (shallow clone)`.

## D15.26 — Tier manifests and other languages

- `Survey.manifests` keeps every path. The tier counts a manifest only
  when its path has at most two parts and no directory part is in
  `{"tests", "test", "fixtures", "testdata", "__snapshots__", "examples"}`.
- `Survey.other_languages: tuple[str, ...] = ()`. The default keeps
  direct constructions valid. The value comes from
  `_EXTRA_TIER_EXTENSIONS` by family (`java`, `kotlin`, `c`, `cpp`,
  `scala`, `groovy` and more). The survey text prints it as "present, no
  rule set", and `survey.as_dict` holds it. `languages` keeps the eight.
- The test of manifests under an ignore glob moves its three manifests to
  depth 1.

## D15.27 — apply safety

Decision 13. I-51 states the write rule.

- **Stamp.** `_stamp_run_date` reads the text of `trueup.toml`, with no
  parse and no `load_target`. A top-level `run_date = ...` line: replace
  that line only. No such line: insert `run_date = "<date>"` after the
  last top-level key line and before the first table header (a line that
  starts with `[`), or append it when there is no table. Comments and
  uncommitted text stay. The gate ruling of 2026-11-02 keeps I-41: the
  stamp is not a touch for the dirty check, and the test that the stamp
  edits only the `run_date` line keeps its expectation.
- **Saved secret paths.** For the `secret-file` predicate on a saved
  plan, the secret paths are the paths of the `secret-content` findings
  of the saved run (the `findings` list of the plan file). No new JSON
  key.
- **Config writes** (`--mode`, `--set`, `config:*`) still re-render.
  `config.render` writes a header line, "comments do not survive a
  config write; trueup writes this file".
- **Writes stay in the root.** One helper,
  `apply._safe_target(ctx, rel) -> Path`. `os.path.realpath` of the
  parent must be under `ctx.root.resolve()`. A final component that is a
  symlink is refused. A refusal reads
  `refused: <rel> resolves outside the repository`, as a `ConfigError`
  does. `_write_file`, `_append_lines` (`.gitignore`, `.gitattributes`),
  the link-rewrite loop of `_move_one` and `_repin_one` use it. Writes
  open with `os.O_NOFOLLOW`.
- `_move_one` runs `git mv -n source target` first, to validate. It
  makes the target parent only after that passes.
- **Plan validation.** `findings.AUTO_RULES: Mapping[str, Callable[[Path, Finding], bool]]`
  holds one static predicate for each handled rule. `apply` checks it on
  the current tree with no second collect (I-40). A row passes when its
  id equals `f"{rule}:{path}"` (a `config` id starts with `config:`), its
  rule is in `apply._RULES`, `auto` is allowed for the rule, and the
  predicate holds: `scratch` → `hygiene.scratch_proven(path)` and
  tracked; `artifact` → the artifact pattern; `secret-file` →
  `_secret_file_kind == "auto"` with the secret paths of the saved run;
  `generated` → the marker in the first 5 lines; `gitignore` → the path
  `.gitignore`; `file-managed` → a path in `ctx.rendered`. A saved row
  that fails is an unknown id: exit 2, and no write.
- `move:` ids exist only for tracked pages. `layout.locate` filters the
  candidates by the `git ls-files` output, which `Survey` gains as
  `tracked: frozenset[str]`. The default empty set means "all".
- `config.clear_cache()` runs after each apply write (D15.29).

## D15.28 — Rule sets

Decision 12.

- TypeScript strict: the strict block is an array. It holds a typed
  object for `ts,tsx,mts,cts` and an untyped object for `js,jsx,mjs,cjs`
  with `tseslint.configs.strict`, `stylistic`, sonarjs, security, jsdoc
  and the same thresholds.
- Vue strict: `complexity` 10, `max-depth` 4, `max-params` 5,
  `max-lines-per-function` 60 and the sonarjs cognitive limit 15 for the
  script block. The fragment imports sonarjs under its own name
  (`vueSonar`), and the Vue strict package lists
  `eslint-plugin-sonarjs`.
- phpmd strict: `CyclomaticComplexity reportLevel` 11 and
  `ExcessiveMethodLength minimum` 61, so 10 and 60 are allowed. The
  parameter limit 6 stays, so 5 is allowed.
- Python: the promise text of the brief and of
  `docs/explanation/research-code-rules.md` says "statements 50 (ruff
  PLR0915); no line limit" for Python, and "none" for shell and SQL.
- `RuleSet.nightly` goes, with its values, its docstrings and the D5.5
  code block line. Brief S8 and the brief rows on extras, coverage gates
  and mutation testing are superseded (D15.37).

## D15.29 — Config layers

- The cross-key rules run on the merged config in `_read_layers`, after
  the overlays: `refs.path` needs a merged `refs_mode == "copy"`. The
  checks for each file stay only for keys inside one table of one file.
- `managed.py` and `layout.py` stop reading `cfg.refs_layout`. The three
  `[layout]` switches, set at parse, decide, so a higher `[layout]`
  switch wins over a lower `[refs] layout`.
- A layer that sets `[[eslint.off]]` (or `[eslint] off = []`) replaces
  the lower list: `"eslint.off"` joins `_MERGE_FIELDS`.
  `[root] base = "code"` resets to the code list.
- `run_date`: `""` stays `None`. A value that is not empty must pass
  `datetime.date.fromisoformat`.
- An error message names the bad key
  (`[refs] bogus: unknown key; allowed: ...`) and starts with the full
  path of the file.
- `config.clear_cache()` runs after every apply write.
- `house.toml` gives `[[eslint.off]]` as a commented example, and drops
  the text "applies when no layer names a profile". The reader table of
  D14.4 gains `hooks._session`.

## D15.30 — One front-matter parser and one page rule

`docrules._front_matter`, `layout._front_matter_type` and the block walk
of `layout._is_agent_definition` use `ref_check._front_matter`, in its
D15.18 form. Pages: `ref_check.is_doc_page(rel: str, docs_dir: str) ->
bool` is true for a `.md` path under `docs_dir` with no segment that
starts with a dot and no `SKIP_DIRS` segment. The checker keeps its disk
walk, and docrules applies the predicate to `survey.files`. A test pins
both page sets equal on a fixture with no ignored page. This change
lands with D15.18 or after it.

## D15.31 — The scratch guard asks

Decision 7. `hooks._check_write` runs the scratch test after
`path.exists()`. An existing file gives `None`. A new scratch-named file
gives `("ask", <reason>)`. A Bash `git add` of a scratch-looking path
also gives `ask` (gate ruling of 2026-11-02). The deny of the install
guard still wins over an ask. The skill says that the guard does not see
Bash writes (`touch`, `>`, a heredoc, `mv`).

## D15.32 — Install guard

Decision 7.

- New table `[guard]`: `registry` (bool, default `false`) and
  `private_packages` (a list of name globs, default `[]`). The keys go
  into `_TOP_LEVEL_KEYS`, `_MERGE_FIELDS`, `_parse_values`, `render`,
  `house.toml` and `minimal.toml`.
- `_check_install(command, cfg, root)` returns `None` when
  `cfg.guard_registry` is false. When it is true, it skips a package in
  these cases: the command holds `--index-url`, `--extra-index-url`,
  `-i` or `--registry`; the name is a scope `@s/x` and `<root>/.npmrc`
  has `@s:registry=`; `<root>/.npmrc` has `registry=`; or the name
  matches a `private_packages` glob.
- README claim 5 and the brief claim "Offline and deterministic" keep
  "offline", with the qualifier "the install guard's registry lookup is
  off unless `[guard] registry = true`".
- The registry tests set `registry = true`.

## D15.33 — Stop only

Decision 8. Amends D6.3. `hooks/hooks.json` loses the `SubagentStop`
group. `test_plugin_manifest.py` asserts
`"SubagentStop" not in hooks["hooks"]`. The `hooks.py` docstrings, the
reference page, the skill ("four hook entries") and
`docs/explanation/purpose-and-state.md` change with it.

## D15.34 — SessionStart text

- The text gives the tier and the docs mode in force: the tier of
  `survey.run(root)` when `tier = "auto"`, and
  `config.resolve_docs(cfg, tier)`.
- The STE line prints only when the profile name is `house`.
- The command hint uses `trueup` when `shutil.which("trueup")` finds it,
  else `python3 <launcher>`, as `_stop` does.

## D15.35 — Bash `git add` segments

`_git_add_paths` cuts the command into shell segments with the
`_install_names` cutter (`punctuation_chars`, `_SHELL_BREAKS`). It drops
leading `sudo`, `env` and `NAME=value` words, and matches
`segment[:2] == ["git", "add"]`. `echo git add notes.md` gives nothing;
`cd d && git add notes.md` gives the scratch ask.

## D15.36 — The skill matches the code

- `config.KEYS: tuple[str, ...]` holds every dotted key: the
  `_MERGE_FIELDS` keys, and `profile`, `languages`, `eslint.off` and
  `guard.*`.
- `tests/test_skill_drift.py` checks `skills/trueup/SKILL.md`. It scans
  only code spans, and lines that hold `PLUGIN/trueup"` or start with a
  subcommand word. Each trueup command and flag that the skill names
  exists in `cli._build_parser()` (a walk of the subparsers) or in a
  `REFS_FLAGS` constant in `ref_check.py`. Each config key in a
  `[table] key` or `key =` form exists in `config.KEYS`; the exempt list
  is `[scan] ignore`, `[checks] *`, `[keep] failures` and the checker's
  keys. Each template name exists in `managed.TEMPLATE_NAMES`. Each
  `trueup.md#anchor` exists in `ref_check._heading_slugs` of the
  reference page. A short explicit list of keys that the skill must name
  (the ten that the audit found missing, and `guard.registry` and
  `health.files`) is checked in the other direction.
- The skill fixes its stale statements, names `check --sarif` and the
  missing keys, moves the start-of-run warning and the `--all-auto`
  deletion trap into the first screen, and keeps one copy-mode caveat
  that the other places link to.

## D15.37 — Documents after the trust round

- Superseded marks: "Superseded on 2026-11-02 by D15.<m>: <one line>."
  In this page, the first line of each old section is "Replaced by
  D14.<x> (2026-10-16)", or "Amended by D14.<x> and D15.<y>
  (2026-11-02): <what changed>" when only a part is replaced.
- The brief gains the decision rows for decision 2 (the `minimal`
  default) and decision 6 (the score per covered file, the gate by
  keys), dated 2026-11-02.
- The baseline how-to adds `trueup check --baseline --root .` as its own
  CI step. trueup installs from a clone path (`pip install <clone
  path>`) until a remote exists.
- `survey.TRUEUP_OWN_PATHS` is `trueup.toml`, `ref_check.toml`,
  `.trueup-baseline.json` and `ref_check.py`. `lint/` and the old
  managed paths leave it. When the self-check then shows a plan row, the
  `trueup.toml` of this repository gets an `ignore` entry. The code does
  not make an exception for it.
- Each page that the round touches gets `last_reviewed: 2026-11-02`. The
  reference page and the two how-tos become `status: current`.
- `## Verification` claims every D15 id, every D14 id, I-27, I-35, I-42
  and I-44 to I-53, each with the test that cites it. The range
  of criteria in this page ends at S24.
- D14.18 to D14.21 change their titles from "S1:" to "Case 1:" and so
  on. The tests `test_s1_` and `test_s2_` of `tests/test_acceptance.py`
  become `test_s11_` and `test_s12_`, and the matching test of
  `tests/test_check.py` cites D14.18.

## D15.38 — Tests and CI

Decision 15.

- `.github/workflows/trueup.yml` runs a job matrix
  `python-version: ["3.11", "3.14"]`. It installs pytest and the tools
  it can (ruff, vale, gitleaks, shellcheck, `npm ci --prefix lint/ts`),
  runs `pytest -q -rs -p no:cacheprovider`, and appends the `SKIPPED`
  lines to `$GITHUB_STEP_SUMMARY`. The `schedule` trigger and the
  nightly header go (decision 12).
- S23: the converge fixture gains `.gitignore` (with `.scratch/`),
  `LICENSE`, `AGENTS.md`, a `CLAUDE.md` that links `AGENTS.md`, and
  `trueup.toml` (`profile = "house"`, `[languages]` for rust and
  typescript). The test asserts that the tidy plan is `[]`, applies only
  the scrambled tree, and compares it with the tidy source. The scramble
  operations that D15.9 and D15.10 make manual change to junk that
  content proves: an `.env` that holds a private-key block built at run
  time, `ARCHITECTURE.md.orig`, `src/fold.rs.bak` and `README.md~`. A
  second test asserts that the compound-stem and placeholder `.env`
  shapes give manual rows.
- S24: for each operation in `SCRAMBLE_OPS`, the plan and the score are
  strictly greater than the tidy values. `NEUTRAL_OPS` (the clean
  deletion) keeps the plan equal, and `check --baseline` exits 0. The
  committed-cache operation joins `SCRAMBLE_OPS`.
- `test_lint_fixtures.py` and `test_acceptance.py` skip with the tool
  name when the first token of a block line is not on `PATH`, or when
  `lint/ts/node_modules` is absent. Fixture runs go under `tmp_path`;
  the TypeScript line runs with `cwd=tree` and an absolute
  `REPO / "lint/ts"`. The Stop timing test uses a fixture repository with
  two commits. A new I-27 test copies the tracked files into `tmp_path`,
  commits, runs `report.collect`, and asserts the plan `[]`.
- `scripts/sync_adopters.py` holds a table from name to path and a
  `--check` flag. It refreshes the adopter snapshots, and the
  snapshot header records the date. Since 2026-11-16 the table holds
  only this repository: the three other snapshots come from private
  repositories, so their names are replaced and they stay as they are.
- Tests that only pass through get real assertions. The `D6.15` padding
  leaves the 25 blocks that hold it.
- Each change of this round starts with a test that fails.

## D16.0 — Scope and order

Round 16 has twelve sections, D16.1 to D16.12. Each section names one
change. The D16 headings come first in this page, because a test can
cite only a declared id. The Verification claims come last.

The Medium and Low review findings and every design smell go in the
report. They are not part of this round.

## D16.1 — Path probes that do not raise below Python 3.14

On Python 3.11 to 3.13, `Path.exists`, `is_file`, `is_dir` and
`is_symlink` raise PermissionError for a path below an unreadable
directory. On 3.14 they return False. The `os.path` forms return False
on every version.

Each site that such a path can reach uses the `os.path` probe. There is
no new helper. `ref_check.py` stays one file with the standard library
only. `baseline.py` and `drift.py` filter `DeprecationWarning` as well
as `SyntaxWarning`. An unreadable `docs/` gives `no-target` on every
version.

## D16.2 — Declaration sources and id forms

Two keys, `[refs] declared` and `[refs] id_forms`, are off by default.
`declared` lists paths or globs relative to the root. An absolute path
is an error. A `..` segment can name a page outside the root, because
the target names the page. `id_forms` lists id
forms such as `D<n>.<m>`. A placeholder `<x>` means digits. Every other
character is literal. A form has at most 24 characters, and a target has
at most 16 forms. No regular expression comes from a target.

When either key is set, the checker uses the configured reader. A
declaration is the first token of a heading, of a table row, or of a
bold lead on a line outside a fenced block. A mention anywhere else does
not declare. An id declared on two sources is declared.

A literal source that does not exist, or a glob that matches nothing,
gives one `no-target` row. The row says how many citations were not
checked. While a source is missing, check a gives no `unknown-id` row.
With neither key set, the checker uses today's patterns.

## D16.3 — A reader change warns before it fails

A release that widens what the checker reads registers the change in
`ref_check.READER_CHANGES` for one release. A failure from a marker at a
position that a registered change matches is a warning. It does not
change the exit code. The target fails on it after it lists the change
in `[refs] accepted_reader_changes`. `trueup check` gives one info row
`refs-reader-change:<name>` with the count. The table is empty in this
release.

## D16.4 — A placeholder link target is not a broken link

In check g, a link whose raw target starts with `${NAME}` is skipped,
for inline links and reference definitions. The test reads the raw
target. A placeholder that is not at the start, and a link with no
placeholder, still fail.

## D16.5 — Published test values are not secrets

`managed.py` holds `PUBLISHED_TEST_VALUES`, built in code. The rendered
gitleaks config adds an allowlist for the rule `generic-api-key`. Each
entry is an exact match of the whole value. A value that another rule
catches still gives a row. trueup does not read the matched text.

## D16.6 — Label a same-basename duplicate

A duplicate group whose two paths have the same basename and differ in
one directory segment gets a clear evidence text and an action that
names `[[keep]]`. The row stays manual. Every other group keeps its
text.

## D16.7 — Strict Python lint on a newer ruff

The strict ruff config ignores the `CPY` rules, with a reason. The
comment standard rules out a copyright header.

## D16.8 — Narrow the padded cites

Each test cite line names only the ids that its assertions prove. Only
cite lines change. Every claimed id keeps at least one test.

## D16.9 — The two Verification gaps

I-35 gets a test for two equal scratch copies under `--all-auto`, with a
contrast test for a saved plan. I-48 gets a stored baseline from commit
720b5d2 and an allow list in which each difference names its design id.

## D16.10 — I-50 holds under every profile

The reads that this section names go through `fsread` with a 1 MiB cap:
`docrules._read_text` and `_read_page`, `apply._move_rewrites` and
`_dirty_conflicts`, two reads of `health.py` and four of `managed.py`.
The other reads of `apply.py` take a plan or report file from the
command line, or a file that the same run then writes. This section does
not change them.
`baseline._read` is the one exception to the cap: it reads a coverage
report or the baseline file with a 64 MiB cap (`_REPORT_READ_CAP`),
because the gate fails on a missing report (D6.7). The checker has its
own `_read_text`, which refuses a file that is not regular, a file over
its 16 MiB cap, and a symlink out of the root. As in `fsread`, the
symlink test examines the last path component only. A refused read is
an unreadable file to the caller.

A move has one more rule. `apply._refuse_hidden_page` stops the move when
the read refuses a regular file out of the root or a file over the cap,
because the file can hold a link that the move changes. A device, a FIFO
and a page that does not decode get no rewrite and do not stop the move.

Two more readers can open a path that `git status` lists (addendum of
2026-11-10, owner ruling 12). `changes._blob_shas` gives
`git hash-object` only a regular file that is not a symlink. A symlink
gets the blob sha of its link text, as git stores a symlink, so a new
link target still changes the tree identity. A FIFO, a device or a
socket gets the fixed value `""` and is never opened. The identity of a
regular file does not change. `survey._tokei_counts` runs tokei with a
time limit of 60 s, because tokei opens `.gitignore` during its walk. On
expiry the survey uses the built-in counter, as when tokei is not
installed, and prints one line that names tokei and the limit.

## D16.11 — Documents

This page gets the D16 headings and I-54 to I-59 first, and the
Verification claims last. `docs/reference/trueup.md`, the purpose page
and the skill follow the code of this round.

## D16.12 — Small ledger items

Closed with no change. The ten `noqa` comments in `lint/ruff.toml` name
rules that the gate enables, so they stay. The report names the file as
a config that disagrees with the gate.

## Invariants

- **I-18 Check writes nothing.** `check` leaves every file under the root
  byte-identical, with or without `--out`, whose directory sits outside the
  root or is ignored. It runs no code from the target: the `refcheck` row
  runs the bundled `ref_check.py`.
- **I-19 Apply validates first.** An id that the current plan does not hold,
  or one that is not automatic, stops the run at exit 2 before any file
  changes.
- **I-20 Safe to re-run.** After `apply --all-auto`, `check` reports no
  automatic finding, and a second `apply --all-auto` changes no byte.
- **I-21 Deterministic output.** The same tree and the same date give a
  byte-identical report and byte-identical rendered files; findings sort by
  category order, then by id.
- **I-22 Hooks fail open and stay silent.** A missing `trueup.toml`, broken
  JSON on standard input, or any exception gives exit 0 and no output.
  A user default file never turns a hook on; the gate is the target's
  own `trueup.toml` (D14.11).
- **I-23 No commit; trueup reads no secret.** `apply` runs git only as
  `rm`, `rm --cached`, `mv` and read-only commands such as `ls-files`,
  `grep` and `check-ignore` (D10.1). It never runs `git commit`, `git
  push` or `git clean`. trueup's own code never opens a file
  that the `secret-file` row names, and never puts matched secret text in a
  finding, a report or a hook message. An external scanner that trueup
  runs (gitleaks) may read every file; it runs with `--redact`, and trueup
  keeps only file, line, rule id, commit and fingerprint. The one
  exception is a `.pem` file: trueup reads its first 64 bytes to tell a
  certificate from a key, and puts none of them in a finding (D14.12).
- **I-24 Unmanaged files are never overwritten**, and a `protect` glob is
  never changed by `apply`.
- **I-25 One banned list.** One banned list is in force for a run: the
  built-in file `trueup/data/banned.txt`, or the file and entries that
  `[prose]` names (D14.2). The `prose` row and the Vale `Banned.yml` that
  `trueup lint` renders read that same list. The built-in file matches
  RULES rule 7, multi-word phrases included, except the word that decision
  11 of D15 removed. The `AGENTS.md` prose keeps the verb rule (amended
  2026-11-02, D15.16).
- **I-26 One checker source.** `trueup/ref_check.py` is the only copy in
  this repository, and, in copy mode (D9.1), `apply` writes it byte for
  byte at the target's `[refs] path`.
- **I-27 Self-check.** `python3 trueup check --root .` exits 0 on this
  repository.
- **I-13 Presence does not depend on the counter.** Language presence and
  the tier are the same whether the built-in counter or `tokei` counts the
  lines (D6.14).
- **I-14 Hooks write only plugin data.** A hook writes only below
  `$CLAUDE_PLUGIN_DATA`, never in the target tree. Each git call that can
  refresh the index (`status`, `diff`) uses `--no-optional-locks`. The
  `ls-files`, `log`, `tag` and `rev-parse` calls take no optional lock and
  do not change. After each hook runs on a temporary repository, `git
  status --porcelain` and the `.git/index` mtime are unchanged.
- **I-15 The Stop guard blocks at most once.** It never blocks when
  `stop_hook_active` is true (D6.3). With the flag set and a changed file,
  the hook prints nothing and exits 0.
- **I-16 Only the baseline command writes the baseline.** Only `trueup
  baseline` writes `.trueup-baseline.json`. `check` writes nothing, with
  any flags, `--baseline` and `--changed` included (D6.6, D6.7).
- **I-17 The Stop guard is fast.** The Stop guard takes less than 1 s wall
  time on this repository (D6.3). The bound is a field measurement: each
  run records its time in the hook timing log (D13.4), and the unit suite
  checks only that the record is written.
- **I-28 One network module.** Only `trueup/registry.py` opens a network
  connection. `survey`, `check`, `baseline`, `apply` and `refs` open none.
  `trueup lint --install` is the second network path: it runs `npm
  install` in the eslint package directory and installs jscpd and
  sqlfluff in the tools directory, only on request (D14.7, D15.5).
- **I-29 The guard never allows.** The install guard gives `deny`, `ask`,
  or no decision. No hook prints `permissionDecision: "allow"`.
- **I-30 Redacted secrets.** Every gitleaks call has `--redact`. A test
  with an assembled secret finds it in no finding, report or output.
- **I-31 trueup never runs `gh`.** No subprocess call in `trueup/` has
  `gh` as its executable. Platform rows only print commands.
- **I-32 Pinned actions.** Every `uses:` in the rendered CI workflow ends
  in `@<40 hex> # <tag>`.
- **I-33 Render does not read the machine.** Every managed file is a
  function of the config and the tracked tree only, never of the tools on
  the path. `load` reads the profile and user default files; `render`
  reads none of them and writes only the target layer (D14.3).
- **I-34 Nothing moves without a named id.** A page moves only by a
  `move:` id that the person names. `--all-auto` never runs a move.
- **I-35 The last copy stays, in one plan.** Within one plan, the
  automatic ids never remove every tracked copy of a content. Across the
  passes of one `apply --all-auto` run with no saved plan, a new plan can
  show the remaining copy as a scratch file with no copy, and a later
  pass can remove it (D10.3). The skill tells the person to examine the
  scratch copies before `--all-auto`. `apply --plan` and `apply
  --from-report` make one pass on one plan and collect no new plan
  (I-40), so in that flow the last copy stays.
- **I-36 One finding for each misplaced page.** The move unit does not
  change the count. One scramble operation never gives a smaller plan or a
  lower score (S24).
- **I-37 Convergence.** After `check`, `apply --all-auto`, `check` and
  `apply` of each move id, a scrambled fixture is equal to its tidy source
  (S23).
- **I-38 Protect stops a move.** A move never has a `protect` path, or a
  path under a protected directory, as its source or target. A directory
  move never carries a protected file, and a move never rewrites a
  protected file.
- **I-39 Evidence only.** The broken-link notes of D10.6 add evidence
  only. Refcheck finding ids and `[keep]` failure ids do not change.
- **I-40 Saved plan is exact.** The ids, move targets and re-pin values
  that `apply --plan` or `apply --from-report` acts on are those of the
  saved plan, or of the one collect that `--from-report` makes at the
  matching tree. `apply` never collects again in that run. A tree that
  differs from the saved identity gives exit 2 and no write (D12.1,
  D12.3).
- **I-41 No silent overwrite of an uncommitted edit.** `apply` without
  `--allow-dirty` writes, moves or removes no path that has uncommitted
  changes. The exceptions are trueup's own managed output, which carries
  the managed header, and the `run_date` line of `trueup.toml` (D12.2).
- **I-42 A check above the tier is never a failure.** No finding asks to
  add a managed path when the tier is below the path's minimum tier, and
  no finding asks to remove a managed file. The brief row "Repository
  tiers?" holds for the managed set too (D12.9). `managed-legacy` is
  `info`: it informs, it never asks (D14.8).
- **I-43 trueup's own files never change the tier.** The tier that
  `survey` picks is the same before and after `apply`: the pick counts no
  path that trueup writes (D12.9 step 7). The root budget also counts no
  root entry that holds only trueup's files.
- **I-44 Same file, same output.** A target that holds `trueup.toml`
  never reads the user default file. A profile name that resolves
  nowhere is exit 2, never a fall back. So two machines with the same
  target tree and the same built-in or committed profile give the same
  `check` output (D14.1).
- **I-45 `apply` writes the target layer.** No value of a profile or of
  the user default file reaches a target's `trueup.toml` through `apply`
  (D14.3, D14.19).
- **I-46 Built-in names are fixed.** `house` and `minimal` cannot be
  shadowed by a user file (D14.1).
- **I-47 `lint` writes nothing under the root.** Rendered configs live in
  a temporary directory or the cache. A tool file that the target owns
  (the eslint suppressions file, the pydoclint baseline) is passed only
  when it exists (D14.6, D14.7). trueup writes no file under the root. A
  cache that a tool writes by itself is the tool's cache, for example
  the cargo `target/` directory. trueup sets `RUFF_CACHE_DIR` to
  `<cfgdir>/ruff-cache`, so ruff writes no `.ruff_cache` under the root.
- **I-48 `house` is the earlier output.** With `profile = "house"` set
  (amended 2026-11-02, D15.6), on the
  test fixtures and on the four adopters, the `check --json` findings
  are the same as the output of round 13, except the rows that D14.22
  item 7 allows: removed `file-managed` rows, new `managed-legacy` info
  rows, the `tool-missing` action text, the defects that D14.12 fixes,
  the tier moves of D14.13 and the new `profile` block.
- **I-49 trueup reads a secret file only within a bound.** trueup reads
  at most 64 bytes of a key-named file, and scans an `.env` file with the
  secret patterns. No byte of either goes into a finding, a log or the
  JSON. This replaces the secret clauses of I-23; the git clauses of I-23
  stay (D15.10).
- **I-50 Bounded reads.** A content read of trueup never follows a
  symlink out of the root, never opens a device or FIFO, and never reads
  more than its cap (D15.22).
- **I-51 apply writes stay below the root.** `apply` writes only below
  the root. A path whose parent resolves outside the root, or whose last
  component is a symlink, is refused (D15.27).
- **I-52 Loud failure.** `check`, `lint`, `apply`, `refs` and `baseline`
  never exit 1 on an internal error, and never report an empty survey as
  a result (D15.1, D15.2).
- **I-53 Content evidence.** An automatic row of the `scratch`,
  `secret-file` or `binary` rule rests on the content of the file or on
  a whole-stem scratch name. A name-only or size-only match is manual
  (D15.9 to D15.11).
- **I-54 Default reader.** With none of `[refs] declared`, `id_forms`
  and `accepted_reader_changes` set, the checker reads one page with
  today's patterns and gives the same rows as before round 16 (D16.2).
- **I-55 Undeclared id fails.** With every source found, an id that no
  source declares gives one `unknown-id` row per citation (D16.2).
- **I-56 Missing source fails.** A missing source fails the run with one
  `no-target` row per entry. The row names how many citations were not
  checked (D16.2).
- **I-57 One reader for a and c.** Check a and check c read the same
  sources with the same id forms (D16.2).
- **I-58 Reader change warns first.** A failure from a registered reader
  change does not change the exit code until the target accepts the
  change. After that it fails (D16.3).
- **I-59 Allowlist by whole value.** The published-value allowlist drops
  only rows whose whole matched value is on the list. Another value on
  the same line pattern still gives a row (D16.5).

## Frozen

- D2.1: the marker grammar.
- D2.2: the closed marker registry.
- D2.6: the edge file schema.
- D3.1: the invariants I-1 to I-12.

D2.4 and D2.5 left this list on 2026-09-22 (R-16).

An item in this list changes only under an `H` ruling in `FABLE.md`. The
design stage adds the plan row that fills this list. A human closes that row.

## Verification

A test cites the ids that it proves in its docstring. The ids below are all
the claims of this design. The criteria S1 to S24 are in the brief.

**Unit.** Pure functions of the checker, called in process with text or a
small temporary tree as input.

- D2.1: a table of marker texts and the references or the `malformed` result
  that each one gives, for the anchored rule and the legacy rule.
- D2.2: a table of comments and the R1 or R2 result of each one.
- D2.4: the text of the line for each kind of failure.
- D2.5: a valid file, an absent file, an unknown key (exit 2), and a `# D1:`
  comment that passes with `local_tags = ["D"]` and fails without it.
- D2.7: section limits, the hash normalisation, the order of versions.
- D2.8: the declared ids, the claims and the open rows of given texts.
- D2.9: a table of suppressions with and without a reason, and of headers.
- D2.10: slugs, code spans, fenced blocks, schemes, fragments, the root
  files, and the pin rule: the section limits, the hash, a stale pin, and a
  pin that does not apply.
- I-1: marker text in a string literal, in Markdown and in an unlisted
  extension gives no reference. Examine this one first.
- I-4: a Python file with a syntax error gives `unreadable`.

**Integration.** The checker or a linter runs as a child process on a
materialised fixture tree (D4.3).

- D1.2 and D1.3: a tree with the five languages gives the expected references.
- D2.3: the flags, the summary line and the three exit codes.
- D2.6 and I-7: the edge file of a tree is equal to an expected file, and two
  runs give the same bytes.
- D4.2 and I-10: a changed section, an unchanged section, an absent section,
  and a pin that is the newest version.
- D1.6 and I-3: each file under `tests/refs/fixtures/` ends in `.txt`.
- I-2: a `ref_check.toml` with a key other than `[scan] ignore` that tries
  to skip a path gives exit 2, and no environment variable skips a path;
  `[scan] ignore` takes a path out of checks a to i; its globs match as the
  survey's globs do; `apply` renders it, and `check` and the hook then
  agree on an ignored page.
- I-8: a run leaves the tree unchanged, apart from the edge file.
- D1.1, D2.12 and I-11: a copy of the checker with a different name in a different
  tree passes under `pytest` and as a direct run.
- D2.13: a fixture tree for each kind of check h gives the line of that kind,
  a clean tree gives no line, and with `layout` absent no tree gives a failure
  of check h.
- D2.14: a fixture tree for each kind of check i gives the line of that kind,
  a clean tree gives no line, and with `readme` absent no tree gives a failure
  of check i. The root `README.md` of this repository gives no failure.

- D2.11, D1.5, D2.9, D4.3 and I-12: for each language, the wrong fixture
  fails the command that the page names, the corrected fixture passes, and
  the form with a reason continues to suppress.
- D1.4 and I-9: the page has the five blocks and its registry table is equal
  to `REGISTRY`.
- D1.6: the acceptance tests of S11 and S12 materialise their fixture trees
  and run the lint commands of the page on them.

D1.5's rule stays as written for these five languages: a test that needs a
tool which is absent fails, it does not skip, and `tests/test_lint_fixtures.py`
still does that for Python, Rust, TypeScript, shell and SQL. `trueup`'s own
sixteen rule sets are a different case: `trueup` ships every rule set
whether or not the target has the tool for it, and reports a missing one as
a `tool-missing` finding (D5.4) rather than assuming it is there. So a
rule-set test whose tool is absent skips by design and names the tool
(`test_rulesets.py`). A hook whose tool is absent and that has no test of
its own is listed as unverified in the reference page.

- D5.10 and D5.8: the plugin manifest, the marketplace entry and the hook
  wiring match this design, and `python3 trueup` runs as a directory
  (`test_plugin_manifest.py`, `test_cli.py`); the guard asks about a new root
  file, a scratch-looking write outside `.scratch/`, and a `git add` of a
  scratch-looking path, and its reason names `[root] allow` or
  `.scratch/`; it allows a base-list name, a `[root] allow` name, a file
  already on disk, and a write under `.scratch/`; SessionStart prints the
  tier, the root rule and the scratch rule, and the line that points at
  the trueup skill (`test_hooks.py`); the managed-file rule it also
  prints (D5.8) has no test of its own.
- D5.11: a missing or unknown subcommand, `apply` with neither or both of
  `--ids` and `--all-auto`, and an unknown hook event each exit 2; a
  `ConfigError` becomes exit 2; `--root` falls back to the git top level
  (`test_cli.py`, through `cli.main`). `check` exits 0 on an empty plan
  and 1 on a plan that holds a finding; `python3 trueup check`, run in its
  own process, gives the same exit 1 on the messy fixture; `--out` and
  `--json` write the two reports (`test_check.py`). `apply` exits 0 on
  success and 2 on a bad id, `--mode` or `--set` (`test_apply.py`). No
  test yet forces `apply`'s exit 1 (a handler that failed).
- D5.3: loading and rendering `trueup.toml` is a round trip, an unknown key
  or a bad value raises `ConfigError`, and a glob, id or reason holding a
  quote or a backslash still parses back (`test_config.py`, `test_apply.py`).
- D5.4: the eight slop rows, the tier pick (T0, T1, T3 and the
  `trueup.toml` override), the per-tier health items, the agent-file
  check, the document rules (README length, the changelog shape, a
  broken `superseded_by` link, a stale `current` page, the banned-word
  floor, and the `ref_check.py` fold-in), and `check`'s merge of all four
  rows into one sorted plan are each proved on their own inputs
  (`test_survey.py`, `test_hygiene.py`, `test_health.py`,
  `test_docrules.py`, `test_managed.py`, `test_check.py`).
- D5.5 and I-25: each of the sixteen rule sets renders its template files
  with a header comment, and where the tool it calls is on this machine the
  rendered hook passes a small good sample and fails a small bad one; the
  Vale `Banned.yml` token list is equal to `trueup/data/banned.txt`
  (`test_rulesets.py`).
- D5.6, I-21, I-24 and I-26: a managed file absent, unchanged, changed with
  the header, and changed with no header each give the finding this design
  states; the pre-commit hooks render in a fixed order; a `protect` glob
  is never touched; `ref_check.py` on disk that differs from the bundled
  copy gives a manual warning (`test_managed.py`, `test_apply.py`).
- D5.7: the score's five categories, each capped at its own weight, the
  root category's budget widened by `[root] allow`, the health category
  divided by the tier's required item count, and the total scaled by 100
  / 90 (`test_score.py`, `test_health.py`).
- I-18, I-19 and I-20: `check` leaves the target byte-identical; `apply`
  checks every requested id against the current plan before writing
  anything: an unknown, `info` or manual id exits 2 with no file changed,
  even beside a good id; a second `apply --all-auto` changes no byte
  after the first (`test_check.py`, `test_apply.py`).
- I-22: a hook payload with no `trueup.toml` at the found root, broken or
  empty JSON on standard input, a `cwd` with no `.git` above it, and the
  `ConfigError` a malformed `trueup.toml` raises each give no output and
  exit 0 (`test_hooks.py`); the exact `hooks.json` guard command does the
  same on a git repository with no `trueup.toml`
  (`test_plugin_manifest.py`). Limit: the `ConfigError` test runs the
  `guard` event only. On `session`, a malformed `trueup.toml` prints one
  notice line and exits 0 (D15.7), so I-22 holds there for the exit code
  only.
- I-23: `apply` never runs `git commit`, `git push` or `git clean`, and the
  rows that would otherwise read a secret file's content skip it by name
  instead (`test_hygiene.py`, `test_apply.py`).
- D6.17 and I-21: `collect(root)` with no `only` gives the v1 result; with
  `only`, it drops every repo-wide finding and reports no score; `check
  --changed` scopes the plan to `changes.working_set(root)` and exits 1
  only on a scoped finding (`test_changes.py`,
  `test_check.py::test_check_changed_scopes_findings_to_the_change_set`,
  `test_cli.py::test_check_rejects_changed_and_baseline_together`).
- D6.2: the session snapshot replaces on the source `startup` or `clear`
  and keeps its first write on `resume`, `compact` or `fork`; `session_set`
  falls back to `working_set` with no snapshot, or with one for another
  root (`test_changes.py`,
  `test_hooks.py::test_session_writes_the_snapshot_and_resume_keeps_the_first`,
  `test_plugin_manifest.py`).
- D6.3 and I-15: the Stop guard blocks on a plan scoped to the session's
  own changed files, lists up to 10 findings, and is silent when
  `stop_hook_active` is true
  (`test_hooks.py::test_stop_blocks_on_a_new_scratch_file_and_names_it`,
  `::test_stop_is_silent_when_stop_hook_active`,
  `::test_stop_is_silent_without_trueup_toml`).
- D6.4: the interface reminder fires once per path on a matched signal, and
  stays silent once `README.md` or a `docs/reference/**` path has a change
  this session, or the written path sits outside the root
  (`test_hooks.py::test_interface_reminds_once_per_path`,
  `::test_interface_is_silent_outside_root_and_without_plugin_data`).
- D6.5: each of the four drift rules (`drift-flag`, `drift-undocumented`,
  `drift-package`, `drift-command`) fires on its bad fixture and stays
  silent on the matching good one (`test_drift.py`).
- D6.6: `key` drops the line number from a `secret-content`, `changelog` or
  `refcheck` id and keeps every other id unchanged; `trueup baseline`
  writes `.trueup-baseline.json` and no other file (`test_baseline.py`,
  `test_cli.py::test_baseline_writes_the_file_and_prints_a_summary_line`).
- D6.7 and I-16: `check --baseline` exits 2 with no baseline file, 0 on an
  unchanged repository, and 1 on a new finding key or a score rise, and
  adds the same `Gate` fields to the Markdown and the JSON report
  (`test_check.py`,
  `test_baseline.py::test_compare_flags_a_score_rise_even_with_no_new_key`).
  The CI-delivery half of D6.7 — `pip install --target <tmp> .` and
  `python3 -m pip wheel .` succeeding, and `.pre-commit-hooks.yaml`'s
  shape — has no automated test in this repository; this design's own text
  states it as a hand-run check instead.
- D6.8: each ratchet source (the Python docstring `ast` count, a Cobertura
  report, a Go coverprofile, an lcov report) parses correctly, a drop past
  the 0.1 tolerance is a `ratchet_drops` entry, and a recorded metric with
  no report now is a `missing_reports` entry (`test_baseline.py`).
- D6.9 and I-25: the three form entries (`harness`, `unlock`, `underscore`)
  fire on a verb fixture and stay silent on the paired noun fixture, for
  the Python matcher and for a real `vale` run alike, and a `prose` finding
  naming 10 or more distinct words carries the `[[keep]]` hint line
  (`test_docrules.py`, `test_check.py`,
  `test_rulesets.py::test_vale_banned_forms_match_the_python_matcher`).
- D6.10 and I-23: a banner followed by a placeholder line or a comment gives
  no finding, and a key-shaped block built at test time in `tmp_path`
  (random base64, never committed) does
  (`test_hygiene.py::test_secret_content_spares_a_private_key_placeholder`).
- The local-tags change: this repository's `trueup/ref_check.py` stays
  byte-equal to the bundled copy after the change
  (`test_managed.py::test_ref_check_is_the_bundled_copy_byte_for_byte`,
  I-26). This repository has no test of its own for the `local_tags`
  behavior: the rule lives inside the checker module, not in a `trueup/`
  module beside it. Two tests under `tests/refs/` prove it at its source
  instead —
  `tests/refs/test_markers.py::test_a_local_tag_passes_the_registry_check_only_with_the_key`
  (a `# D1:` comment passes with `local_tags = ["D"]` and fails without
  it) and `tests/refs/test_config.py::test_the_registry_table_reads_the_local_tags`
  (the loader reads `[registry] local_tags`) — so no test here cites that
  section by number.
- D6.12: a `duplicate` group entirely under a `fixtures/`, `testdata/` or
  `__snapshots__/` directory gives no finding, and the `docs` category
  scales with distinct paths, capped at 10
  (`test_hygiene.py::test_duplicate_skips_a_group_entirely_under_a_fixtures_directory`,
  `test_score.py::test_docs_category_scales_and_caps_at_ten_distinct_paths`).
- D6.13: each tool-gated rule set's rendered hook, run on the real tool,
  passes a good sample and fails a bad one, and the test skips (naming the
  tool) only when it is absent (`test_rulesets.py`, one test per
  tool family: shfmt, golangci-lint, phpstan/phpcs/phpmd, eslint for
  TypeScript and Vue, vale).
- D6.14 and I-13: one fixture with a file under an `ignore` glob gives the
  same present-language set with the built-in counter and with `tokei`
  (`test_survey.py::test_tokei_scope_matches_builtin_for_ignored_files`,
  `test_check.py`).
- D6.15: each LOW item of the table above has its own regression test, or a
  stated reason it needed none, recorded in
  `.state/runs/trueup-v2/07-low.md`; for example
  `test_hooks.py::test_importing_hooks_does_not_pull_in_survey_or_rulesets`
  (LOW-7) and
  `test_apply.py::test_ids_with_no_config_id_ignores_set_and_writes_no_trueup_toml`
  (LOW-9). The fixes are also exercised across `test_check.py`,
  `test_managed.py` and `test_hooks.py`.
- The field-trial record: the trueup reference page's own "Field trial"
  section states the six repositories, their tier, their score before and
  after, and the judged finding counts. It has no automated test: it
  reports a hand-judged trial, not a code behavior; the check is
  `grep -n 'Field trial' docs/reference/trueup.md`, which finds the
  section heading. The raw record is
  `.state/runs/trueup-v2/00-field-trial.md`.
- I-14: every git call in `changes.py` and `hooks.py` carries
  `--no-optional-locks`, and running each hook on a temporary repository
  leaves `git status --porcelain` and the `.git/index` mtime unchanged
  (`test_changes.py::test_working_set_uses_no_optional_locks`,
  `test_hooks.py::test_each_hook_writes_only_below_plugin_data`).
- I-17: a subprocess run of the Stop guard on this repository, with one
  changed file, records one `stop` line in the timing log
  (`test_hooks.py::test_stop_on_this_repo_records_its_time`).
- D5.3 and D5.6: a `[refs] path` value that is relative, ends in `.py` and
  has no `..` or `.` part and no backslash round-trips through `config.render`; a bad value raises
  `ConfigError`; `render()` writes the checker's bytes at `cfg.refs_path`,
  the rendered `ref-check` pre-commit entry and the Python `ruff-format`
  exclusion both follow it, and a module at a custom path that differs
  from the bundled copy is a manual `warn`
  (`test_config.py`,
  `test_managed.py::test_render_writes_the_checker_at_a_custom_refs_path`,
  `::test_render_pre_commit_follows_a_custom_refs_path`,
  `::test_file_finding_byte_equality_follows_refs_path`).
- D5.11: `trueup refs` is a listed subcommand; it forwards its tokens to
  `trueup.ref_check.main` unchanged, adds the resolved git top level only
  when no `--root`, `--root=`, `-h` or `--help` token is given, and exits
  2 with no git repository and no `--root`
  (`test_cli.py::test_refs_is_a_listed_subcommand`,
  `::test_refs_forwards_its_tokens_to_ref_check_main`,
  `::test_refs_adds_the_resolved_root_when_none_is_given`,
  `::test_refs_leaves_a_root_or_help_token_alone`,
  `::test_refs_without_root_outside_git_exits_two`).

**Acceptance.** One command for each criterion of the brief.

- S11 and S12: the acceptance tests are in the trueup repository, with the
  comment standard page and the lint configurations.
- S13: D2.2 on a fixture tree. S14: D1.3 on a design fixture and a law fixture.
- S15 and S16: D2.8 on fixture trees.
- S17: D4.2 on the fixture archive with two versions.
- S18: I-6 on an empty tree and on a tree with code and no marker.
- S19: D5.1. The checker runs on this repository with the five switches on
  and gives exit 0. D4.1 is proved by the same run.
- S20: D1.7, D4.4 and I-5. The unchanged selftest passes.
- S21: D2.6. S22: D2.10 on a fixture `docs/` tree and on this repository.

**Security floor (wave B).** One entry for each D7 section and each new
invariant.

- D7.2: a `package.json` with a dependency and no lockfile gives
  `lockfile:package.json`; the same manifest with `package-lock.json`, and
  a `pyproject.toml` with no dependency, give none; a workspace member with
  the lockfile at the root gives none; a broken manifest gives one
  (`test_lockfile.py::test_fixture_fires_gives_one_lockfile_finding`,
  `::test_fixture_silent_gives_no_lockfile_finding`,
  `::test_workspace_member_with_lockfile_at_root_is_silent`,
  `::test_broken_manifest_fails_closed`).
- D7.3, I-23 and I-30: a fake `gitleaks` on `PATH` maps the working tree
  and the history entries to the right ids and engine, and no finding or
  output holds the secret; a failing or slow fake gives `built-in` with a
  note; `collect` skips or runs the built-in row; the report prints the
  `secrets` line; `baseline` and `check --baseline` scan the history; a
  real gitleaks run skips when the tool is absent
  (`test_secrets.py::test_fake_gitleaks_maps_working_tree_entries_and_drops_the_secret`,
  `::test_fake_gitleaks_maps_history_entries`,
  `::test_a_failing_gitleaks_gives_built_in_with_a_note`,
  `::test_a_gitleaks_timeout_gives_built_in_with_a_note`,
  `::test_collect_skips_the_built_in_row_when_gitleaks_ran`,
  `::test_the_report_names_the_engine_after_the_counter_line`,
  `::test_baseline_and_check_baseline_scan_the_history`,
  `::test_real_gitleaks_finds_the_assembled_key_and_hides_it`); the
  gitleaks config and hook
  (`test_managed.py::test_gitleaks_hook_text_is_fixed_and_follows_ref_check`,
  `::test_gitleaks_config_lists_the_ignore_globs_as_anchored_regexes`).
- D7.4 and I-32: every `uses:` matches the pin pattern; the osv-scanner
  step is present with a tracked lockfile and absent without; the five
  fallback comments are present; the gitleaks step scans the full history
  (`test_managed.py::test_ci_pins_every_action_to_a_commit_sha`,
  `::test_ci_osv_step_follows_the_tracked_lockfiles`,
  `::test_ci_keeps_the_five_fallback_comments`,
  `::test_ci_scans_the_full_history_with_gitleaks`,
  `::test_ci_raises_when_the_osv_step_is_gone`).
- D7.5: the clean config of each language flags one security bad file
  (`test_rulesets.py::test_python_ruff_config_flags_a_security_bad_file`,
  `::test_typescript_eslint_config_flags_a_security_bad_file`,
  `::test_go_golangci_lint_config_flags_a_security_bad_file`).
- D7.6: public requires `SECURITY.md` at T0, T1, T2 and T3; private does
  not (`test_health.py::test_security_required_at_every_tier_when_public`,
  `::test_required_item_count_matches_the_tier_table`).
- D7.7 and I-29: each install table row and each skip rule; deny for an
  unknown package, ask for a young one, no decision and a `systemMessage`
  for an unreachable registry; no output holds `allow`; the guard imports
  `registry` only for an install
  (`test_hooks.py::test_install_table_rows`,
  `::test_install_skip_rules`,
  `::test_install_guard_denies_unknown_package`,
  `::test_install_guard_asks_for_young_package`,
  `::test_install_guard_unreachable_gives_system_message`,
  `::test_install_guard_runs_after_check_bash_and_its_deny_wins`,
  `::test_install_guard_imports_registry_only_for_an_install`).
- D7.8: a local `http.server` gives each answer type per ecosystem; the
  npm cap; the go escape; the cache hit, the TTL, the `Unreachable`
  non-cache, the corrupt cache file; no cache without
  `$CLAUDE_PLUGIN_DATA`
  (`test_registry.py::test_404_is_unknown_in_every_ecosystem`,
  `::test_npm_long_record_hits_the_cap_and_is_old`,
  `::test_go_escape_and_lowest_version`,
  `::test_cache_hit_needs_no_request`,
  `::test_cache_entry_older_than_ttl_is_looked_up_again`,
  `::test_unreachable_is_not_cached`,
  `::test_corrupt_cache_file_is_treated_as_empty`,
  `::test_no_cache_without_plugin_data`).
- D7.9 and I-31: a public fixture gives the three `platform:*` ids with the
  filled owner, repository and branch; private gives none; no subprocess
  call in `trueup/` has `gh` as its executable
  (`test_health.py::test_platform_findings_fire_with_filled_values_when_public`,
  `::test_platform_findings_use_placeholders_with_no_github_origin`,
  `::test_platform_findings_absent_when_private`,
  `::test_trueup_never_calls_gh`).
- D7.10: the reference page has one `## Security floor` section after the
  health section, with one table row per row name, a cited control per
  row, the Baseline version, the gaps, the lockfile pair table that equals
  `_LOCK_PAIRS`, and the other wave B facts
  (`test_security_floor.py::test_security_floor_section_follows_the_health_section`,
  `::test_security_floor_table_has_one_row_per_d7_10_row`,
  `::test_security_floor_names_the_baseline_version_and_the_gaps`,
  `::test_security_floor_lockfile_table_matches_lock_pairs`,
  `::test_reference_page_states_the_other_wave_b_facts`).
- I-28: only `registry.py` imports `urllib.request`, `http.client` or
  `socket`, and the scan sees every import form
  (`test_registry.py::test_only_registry_imports_network_modules`,
  `::test_network_import_scan_sees_every_form`).
- I-33: every managed file renders to the same bytes with `shutil.which`
  patched to give a path and to give `None`
  (`test_managed.py::test_render_does_not_read_the_tools_on_the_path`).
- Wave done-check: `python3 -m trueup check --root .` exits 0,
  `python3 -m pytest` passes, and `pre-commit run --all-files` passes.

**target-rust first-run fixes (D8).** One entry per D8 section.

- D8.1: the `refcheck` row before the first `apply` equals the row after
  it; `--config` reads another file, an absent one gives exit 2, and the
  usage line names it; the real bundled copy gives no finding on a
  conforming repository
  (`test_check.py::test_first_check_reports_the_refcheck_findings_that_apply_leaves`,
  `refs/test_cli.py::test_config_flag_reads_the_configuration_from_another_file`,
  `test_docrules.py::test_refcheck_fold_in_runs_the_bundled_copy`).
- D8.2: a marker below a `.git` file or directory gives no reference, the
  same marker with no `.git` gives one; a page below a nested repository
  is not a page of the root
  (`refs/test_scan.py::test_a_marker_in_a_nested_repository_gives_no_reference`,
  `::test_a_page_in_a_nested_repository_is_not_a_page_of_the_root`).
- D8.3: the managed manifest gives no `lockfile` finding and the same file
  with no marker gives one; the marker at another path exempts nothing;
  the `node_modules` info finding is present, then absent with the
  directory or with no TypeScript or Vue
  (`test_lockfile.py::test_a_managed_manifest_gives_no_lockfile_finding`,
  `::test_the_managed_marker_exempts_only_the_managed_path`,
  `test_managed.py::test_tool_findings_name_the_absent_eslint_packages`).
- D8.4: a page of cue blocks gives no finding, a real use beside them
  fires on its own line, a cue in a source comment changes nothing, a
  real `vale` run agrees on the same page, and each of the nineteen block
  shapes of the shared table fires on the same lines in both engines
  (`test_docrules.py::test_a_markdown_block_that_quotes_the_list_gives_no_finding`,
  `::test_a_real_use_beside_a_quoted_list_still_fires`,
  `::test_a_cue_in_a_source_comment_does_not_silence_the_word`,
  `::test_quoted_list_shapes_fire_on_the_expected_lines`,
  `test_rulesets.py::test_vale_block_ignores_match_the_quoted_list_rule`,
  `::test_vale_quoted_list_shapes_match_the_python_matcher`).
- D8.5: the plural noun and the leading-underscore sentence are silent,
  the verb and the passive fire; the `leverage` noun is silent and the verb
  fires; the Python matcher and a real `vale` run agree on each form
  fixture
  (`test_docrules.py::test_banned_word_form_plural_noun_underscores_is_silent`,
  `::test_banned_word_form_leverage_noun_is_silent_verb_fires`,
  `::test_banned_word_form_noun_use_is_silent_verb_use_fires`,
  `test_rulesets.py::test_vale_banned_forms_match_the_python_matcher`).
- D8.6: the template section names the eight lexed extensions and the hook
  types agree; a string literal in an `.mjs`, `.sh` or `.sql` file gives
  no Vale alert while a `.js` comment does
  (`test_rulesets.py::test_vale_source_section_lists_only_the_extensions_vale_lexes`,
  `::test_vale_does_not_read_a_string_literal_of_an_unlexed_extension`).
- D8.7: `load` reads the key and rejects a bad shape, `render` writes and
  round-trips it, the rendered `ref_check.toml` carries it, a hand edit of
  the managed file is drift, the key silences the project's tags on the
  first `check` and after `apply`, and the `unregistered` action names it
  (`test_config.py::test_load_reads_refs_local_tags`,
  `::test_load_rejects_bad_refs_local_tags`,
  `::test_render_writes_refs_local_tags_and_round_trips`,
  `::test_refs_local_tag_shape_equals_the_checkers`,
  `test_managed.py::test_render_ref_check_config_carries_the_local_tags`,
  `::test_a_hand_edit_of_the_managed_ref_check_toml_is_drift`,
  `test_check.py::test_refs_local_tags_silence_the_projects_own_tags`,
  `test_docrules.py::test_refcheck_unregistered_action_names_local_tags`).
- D8.8: three copied manifests under `.state/` give T3, and an `ignore`
  glob for them gives no manifest and another tier
  (`test_survey.py::test_manifests_under_an_ignore_glob_do_not_count_for_the_tier`).

**target-rust second-run fixes (D9).** One entry per D9 section with code.

- D9.1: the mode defaults to `global`, `copy` and `layout` read back,
  a mode outside the two or a `path` without copy mode is a config
  error, and `render` round-trips the table; in global mode `render`
  has no checker entry and the hook runs `trueup refs`, in copy mode the
  copy and the python3 hook; an old copy is an `info` finding and
  `apply` leaves it in place; `trueup` absent from the path gives the
  install finding in global mode only; the CI workflow names the install
  in global mode only; in both modes a kept finding fails neither
  `check` nor the hook's command, and a new one fails both
  (`test_config.py::test_refs_mode_defaults_to_global_and_layout_to_on`,
  `::test_load_reads_refs_mode_path_and_layout`,
  `::test_load_rejects_a_bad_refs_mode_or_layout_or_a_path_without_copy_mode`,
  `::test_render_writes_refs_mode_and_layout_and_round_trips`,
  `test_managed.py::test_global_mode_renders_no_checker_copy_and_the_refs_hook`,
  `::test_copy_mode_renders_the_copy_with_the_header_and_the_python_hook`,
  `::test_global_mode_reports_an_old_copy_as_info`,
  `::test_global_mode_names_trueup_when_it_is_not_on_the_path`,
  `::test_ci_names_the_trueup_install_in_global_mode_only`,
  `test_apply.py::test_apply_in_global_mode_writes_no_copy_and_leaves_an_old_one_in_place`,
  `test_check.py::test_a_kept_refcheck_finding_fails_neither_check_nor_the_hook`).
- D9.2: the checker reads `[keep] failures` and rejects another shape or
  key; a kept failure is not printed, not counted, gives exit 0 and the
  notice, and a new failure beside it gives exit 1; `failure_ids` adds
  the tail and the count where ids repeat; `docrules` builds its ids
  with that function; the managed `ref_check.toml` carries the kept ids
  and the `check` render does not
  (`refs/test_config.py::test_the_keep_table_reads_the_failure_ids`,
  `::test_a_keep_table_outside_the_schema_gives_exit_two`,
  `refs/test_cli.py::test_a_kept_failure_is_not_printed_not_counted_and_gives_exit_zero`,
  `::test_failure_ids_add_the_tail_and_the_count_where_ids_repeat`,
  `test_docrules.py::test_refcheck_ids_come_from_the_checkers_failure_ids`,
  `test_managed.py::test_render_ref_check_config_carries_the_kept_failures`,
  `test_check.py::test_a_kept_refcheck_finding_fails_neither_check_nor_the_hook`).
- D9.3: the rendered copy starts with the header; a copy that differs
  and keeps the header is an automatic error, one with no header a
  manual warn; every rendered text file, the copy included, opens with
  the header
  (`test_managed.py::test_copy_mode_renders_the_copy_with_the_header_and_the_python_hook`,
  `::test_an_older_trueup_copy_with_the_header_is_an_automatic_error`,
  `::test_every_rendered_file_starts_with_the_header`).
- D9.4: `layout = false` reads, renders and round-trips, and the
  rendered `ref_check.toml` turns the switch off and leaves the others
  on
  (`test_config.py::test_load_reads_refs_mode_path_and_layout`,
  `::test_render_writes_refs_mode_and_layout_and_round_trips`,
  `test_managed.py::test_render_ref_check_config_turns_layout_off`).
- D9.5: every package fragment holds the eslint 10 ranges, and this
  repository's `lint/ts/package.json` holds the same ones, so the real
  eslint tests of D5.5 run on eslint 10
  (`test_rulesets.py::test_eslint_packages_ask_for_eslint_10_and_the_matching_plugins`,
  `::test_lint_ts_follows_the_template_ranges`).
- D9.6: both clippy entries pass `--keep-going` and deny
  `missing_docs`; a real run on a three-crate workspace accepts the flag
  and names the failing crate and the independent one
  (`test_rulesets.py::test_clippy_entries_keep_going_and_keep_missing_docs`,
  `::test_rust_clippy_checks_every_crate_that_does_not_depend_on_a_failing_one`).

**Round 3, wave A (D10).** One entry for each D10 section that has a
test. The entries of the other D10 sections come with their tests.

- D10.3: a backup word in the extension chain, a copy suffix on a
  document, and a `scratch` or `untitled` prefix at any extension are
  scratch; a copy suffix on a source extension and the names
  `template.py`, `notes_service.py` and `v0_v1.rs` are not; a clean name
  under a top-level `tmp/`, `temp/` or `scratch/` is scratch for
  `check`, and the guard hook denies the new names but lets a clean name
  under `tmp/` through; a bare basename in another directory exempts
  nothing, a relative or a full path does; when no tracked copy of a
  content stays, one `scratch` finding is manual with the last-copy
  evidence, also for an `artifact` copy, an untracked copy and a small
  file; a copy names its kept original, and `duplicate` drops a path
  that `scratch` flags
  (`test_hygiene.py::test_scratch_backup_word_in_the_extension_chain_is_scratch`,
  `::test_scratch_copy_suffix_in_a_document_name_is_scratch`,
  `::test_scratch_copy_suffix_never_matches_a_source_extension`,
  `::test_scratch_prefix_matches_any_extension`,
  `::test_scratch_i_fp_names_stay_clean`,
  `::test_looks_scratch_path_flags_a_clean_name_under_a_scratch_directory`,
  `::test_looks_scratch_path_needs_an_exact_directory_segment`,
  `::test_scratch_row_flags_a_clean_name_under_a_scratch_directory`,
  `::test_scratch_exemption_needs_a_relative_or_slashed_mention`,
  `::test_scratch_last_copy_keeps_one_removal_manual`,
  `::test_scratch_last_copy_rule_also_counts_an_artifact_copy`,
  `::test_scratch_last_copy_rule_skips_an_untracked_copy`,
  `::test_scratch_last_copy_rule_needs_a_tracked_kept_original`,
  `::test_scratch_last_copy_rule_holds_for_a_small_content`,
  `::test_scratch_copy_evidence_names_the_kept_original`,
  `::test_duplicate_drops_a_path_the_scratch_row_already_flags`,
  `test_hooks.py::test_guard_denies_the_widened_scratch_name_patterns`,
  `::test_guard_ignores_the_scratch_directory_rule`).
- D10.4: `dist/` beside a Go manifest is an `artifact` directory, and an
  artifact directory that holds a tracked page is a manual finding that
  names the page
  (`test_hygiene.py::test_artifact_flags_dist_beside_a_go_manifest`,
  `::test_artifact_directory_holding_a_tracked_page_is_manual`).
- D10.5: `apply` of an `artifact` id adds no `.gitignore` line when a
  line already covers the path
  (`test_apply.py::test_artifact_gitignore_line_is_not_repeated_when_already_covered`).

**Round 3, wave B (D10).** One entry for each D10 section or invariant of
this wave that has a test.

- D10.2: a Markdown page outside `docs/` is a candidate; a non-Markdown
  file, a `docs` segment at any depth, a standard root page at the root
  in any case, a `README.md`, `CHANGELOG.md` or `SKILL.md` at any depth,
  a dot or fixture segment and a path that `scratch` flags are not; a
  standard root name in a subdirectory is; `collect` adds one finding for
  each page and the move plan to `CheckRun`, and both reports print it; a
  scoped run has no moves and reports only the pages in its scope
  (`test_layout.py::test_candidate_filter_accepts_a_plain_misplaced_page`,
  `::test_candidate_filter_rejects_a_non_markdown_file`,
  `::test_candidate_filter_rejects_any_docs_segment`,
  `::test_candidate_filter_rejects_a_standard_root_page_case_insensitively`,
  `::test_candidate_filter_rejects_a_standard_root_page_only_at_depth_zero`,
  `::test_candidate_filter_rejects_readme_changelog_and_skill_anywhere`,
  `::test_candidate_filter_rejects_hidden_and_fixture_segments`,
  `::test_candidate_filter_rejects_a_scratch_flagged_path`,
  `::test_locate_excludes_a_path_the_scratch_row_already_flagged`,
  `test_check.py::test_collect_wires_layout_into_the_move_plan`,
  `::test_collect_scoped_run_has_no_moves_and_scopes_the_doc_misplaced_row`,
  `::test_check_changed_drops_hygiene_rows_outside_the_change_set`).
- D10.6: with no candidate, no git command runs; history places a renamed
  page, and a target that exists now is refused; a broken link places a
  page or a directory by a basename that one surveyed path holds, and a
  basename that two paths hold, candidate or not, gives no link target;
  a target outside the repository is refused; the standard reads the
  `type`, and uses `docs/<basename>` with `layout = false` or `docs =
  "readme"`; a directory whose pages move the same way is one move, and
  siblings that disagree, a lone page, a code directory, an ancestor whose
  target holds other files and a target that another move fills are not;
  a non-Markdown file goes with a directory move only when evidence places
  it; `protect` on the source, the target or a file inside the directory
  stops the move; two moves with one target, or a file target inside a
  directory target, are both dropped and the evidence names the shared
  target; a broken link gets the move hint or the fix-the-link hint, and
  its id does not change; a scoped call gives findings only in its scope,
  no moves and no notes
  (`test_layout.py::test_locate_with_no_candidate_runs_no_history_scan`,
  `::test_locate_history_evidence_resolves_a_renamed_page`,
  `::test_locate_history_target_rejected_when_the_old_path_exists_now`,
  `::test_locate_link_evidence_resolves_a_unique_basename_match`,
  `::test_locate_link_evidence_is_skipped_when_two_candidates_share_a_basename`,
  `::test_locate_link_evidence_counts_every_surveyed_file_with_the_basename`,
  `::test_locate_link_evidence_resolves_a_directory_by_basename`,
  `::test_locate_directory_link_evidence_is_skipped_when_two_directories_share_a_basename`,
  `::test_locate_directory_link_evidence_counts_a_file_with_the_basename`,
  `::test_locate_refuses_a_file_link_target_outside_the_repository`,
  `::test_locate_refuses_a_directory_link_target_outside_the_repository`,
  `::test_locate_standard_evidence_uses_front_matter_type`,
  `::test_locate_standard_evidence_falls_back_with_layout_off`,
  `::test_locate_standard_evidence_falls_back_with_docs_readme`,
  `::test_locate_groups_a_renamed_directory_into_one_move`,
  `::test_locate_groups_a_lone_page_with_a_sibling_renamed_out_of_docs`,
  `::test_locate_directory_link_carries_a_non_markdown_file`,
  `::test_locate_keeps_individual_moves_when_siblings_disagree`,
  `::test_locate_keeps_a_lone_page_a_file_move_when_its_sibling_has_no_evidence`,
  `::test_locate_keeps_a_lone_candidate_a_file_move_with_no_sibling`,
  `::test_locate_never_moves_a_code_directory_for_one_page`,
  `::test_locate_never_moves_a_code_directory_on_page_history_only`,
  `::test_locate_units_skip_an_ancestor_whose_target_already_holds_other_content`,
  `::test_locate_units_skip_a_target_that_another_move_fills`,
  `::test_locate_protect_veto_on_the_target_blocks_the_move`,
  `::test_locate_protect_veto_on_the_source_blocks_the_move`,
  `::test_locate_protect_on_a_contained_file_blocks_the_directory_move`,
  `::test_locate_drops_two_standard_moves_with_the_same_target`,
  `::test_locate_drops_a_history_move_and_a_link_move_with_the_same_target`,
  `::test_locate_gives_no_first_wins_target_to_two_history_pages`,
  `::test_collisions_group_a_file_target_inside_a_directory_target`,
  `::test_locate_broken_link_evidence_note_names_the_new_location`,
  `::test_locate_broken_link_hint_when_the_match_already_lives_under_docs`,
  `::test_locate_evidence_notes_never_rename_a_finding_id`,
  `::test_locate_scoped_gives_findings_only_for_pages_in_only`,
  `::test_locate_scoped_with_no_candidate_in_only_gives_no_note`,
  `test_check.py::test_collect_applies_the_broken_link_note_without_changing_the_refcheck_id`).
- D10.7: a move rewrites an inbound link and an outbound link; a
  directory move keeps its inner links, keeps a `./` link and a trailing
  `/`, and carries its other file; a fragment is kept one time; a
  percent-escaped target is rewritten; only the destination changes, not
  the same words in the link text, a reference label or a code span; two
  equal links on one line change one time each; a link that was already
  broken does not change; a protected file is left broken and printed;
  an unknown `move:` id exits 2 and changes nothing
  (`test_move.py::test_move_rewrites_an_inbound_link_from_outside_the_move`,
  `::test_move_rewrites_an_outbound_link_from_the_moved_file`,
  `::test_directory_move_keeps_its_inner_links_and_carries_a_non_markdown_file`,
  `::test_directory_move_keeps_link_forms_that_need_no_change`,
  `::test_move_rewrites_a_link_with_a_fragment_without_doubling_it`,
  `::test_move_rewrites_a_percent_encoded_link_target`,
  `::test_move_rewrites_a_link_whose_text_equals_its_target`,
  `::test_move_rewrites_a_reference_definition_whose_label_equals_its_target`,
  `::test_move_never_changes_a_code_span_before_the_link`,
  `::test_move_rewrites_two_equal_links_on_one_line_once_each`,
  `::test_move_never_changes_a_broken_link_on_the_same_line`,
  `::test_a_protected_file_is_left_broken_and_printed`,
  `::test_an_unknown_move_id_exits_two_and_changes_nothing`).
- D10.8: `Score.raw` gives the text of each category, also for an empty
  plan, and the Markdown and JSON reports print it next to each category
  (`test_score.py::test_raw_counts_text_per_category`,
  `::test_raw_counts_default_empty_without_crashing`,
  `test_check.py::test_check_report_carries_raw_counts_next_to_each_category`).
- I-34: a page moves only by its named `move:` id, and `--all-auto`
  leaves a misplaced page where it is
  (`test_move.py::test_move_rewrites_an_inbound_link_from_outside_the_move`,
  `::test_move_rewrites_an_outbound_link_from_the_moved_file`,
  `::test_all_auto_never_moves_a_page`).
- I-38: a move does not rewrite a protected file and prints its links as
  left broken; `protect` on the source, the target or a file inside a
  directory stops the move
  (`test_move.py::test_a_protected_file_is_left_broken_and_printed`,
  `test_layout.py::test_locate_protect_veto_on_the_target_blocks_the_move`,
  `::test_locate_protect_veto_on_the_source_blocks_the_move`,
  `::test_locate_protect_on_a_contained_file_blocks_the_directory_move`).

**Round 3, wave D (D10).** The acceptance tests S23 and S24 of D10.10, on
the `converge` fixture.

- D10.10: the `converge` fixture, scrambled by the ten operations of
  `SCRAMBLE_OPS`, gives the tidy tree back after `check`, `apply
  --all-auto`, `check` and `apply` of each move id, with `layout` on and
  off; one operation at a time never gives a shorter plan or a lower
  score
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_never_gives_a_smaller_plan_or_a_lower_score`).
- I-36: the seven scrambled pages give seven `doc-misplaced` findings,
  and the two pages of `misc/design/` give one directory move; each scramble
  operation, with `layout` on and off, gives a plan that is not shorter
  and a score that is not lower than the tidy tree
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_never_gives_a_smaller_plan_or_a_lower_score`).
- I-37: after the four steps, `git ls-files -s` of the scrambled tree,
  with blob hashes, equals the tidy tree apart from the files trueup
  writes, and a new `check` gives no move
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`).

**Round 3, follow-up (D10).** The review fixes of round 3. Each entry
names the tests that came with its fix.

- D10.2: a kept `doc-misplaced` page keeps its finding and gets no move,
  and a directory that holds a kept page is no directory move; a root
  page that a `[root] allow` glob names is not a candidate, the same name
  in a subdirectory is
  (`test_layout.py::test_locate_gives_a_kept_page_its_finding_but_no_move`,
  `::test_locate_kept_page_stops_its_directory_unit`,
  `::test_candidate_filter_honours_root_allow_at_depth_zero_only`,
  `::test_locate_root_allow_exempts_a_root_page`).
- D10.3: a path that the `artifact` row flags gets no `scratch` finding
  (`test_hygiene.py::test_scratch_gives_no_finding_for_a_path_the_artifact_row_flags`).
- D10.4: a package `README.md` under `node_modules/` does not make the
  `artifact` directory manual
  (`test_hygiene.py::test_artifact_node_modules_readme_does_not_make_the_directory_manual`).
- D10.6: a kept page gets no move, stops its directory unit, and a
  broken link to its place gets no note; a file move or a directory move
  onto a target that exists is refused, and the evidence names the
  target; a committed and a staged rename of a non-ASCII page give
  `history` evidence when the repository quotes paths
  (`test_layout.py::test_locate_gives_a_kept_page_its_finding_but_no_move`,
  `::test_locate_gives_a_broken_link_to_a_kept_page_no_note`,
  `::test_locate_kept_page_stops_its_directory_unit`,
  `::test_locate_refuses_a_file_move_onto_an_existing_target`,
  `::test_locate_refuses_a_directory_move_onto_an_existing_directory`,
  `::test_history_renames_reads_a_committed_non_ascii_rename`,
  `::test_history_renames_reads_a_staged_non_ascii_rename`).
- D10.7: git paths are read unquoted, so a tracked non-ASCII file is
  tracked, a non-ASCII page gets its link rewrite and no `code mentions`
  line, and a protected non-ASCII file keeps its `artifact` directory; a
  `.markdown` page gets its link rewrite; a moved file's link takes the
  canonical form, a file that does not move keeps a link that still
  resolves, and `./b.md` stays; a directory move needs `<source>/` for a
  code mention; a link that was already broken does not change; the
  directory prefix maps `misc/a.md` but not `miscellany.md`
  (`test_hygiene.py::test_tracked_paths_splits_on_nul_for_a_non_ascii_path`,
  `test_move.py::test_move_rewrites_a_link_in_a_non_ascii_page`,
  `::test_untrack_keeps_a_directory_with_a_protected_non_ascii_file`,
  `::test_move_rewrites_a_link_in_a_markdown_suffix_page`,
  `::test_moved_file_links_take_the_canonical_form`,
  `::test_unmoved_file_keeps_a_link_that_still_resolves`,
  `::test_directory_move_code_mentions_need_the_trailing_slash`,
  `::test_rewrite_links_leaves_a_link_that_was_already_broken`,
  `::test_move_mapper_directory_prefix_does_not_match_a_sibling_file`,
  `test_layout.py::test_history_renames_reads_a_committed_non_ascii_rename`,
  `::test_history_renames_reads_a_staged_non_ascii_rename`).
- D10.9: the tidy `converge` tree gets no `doc-misplaced` and no
  `scratch` finding, and no scramble operation gives a shorter plan or a
  lower score than the tidy tree
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_never_gives_a_smaller_plan_or_a_lower_score`).
- I-24: an `artifact` directory that holds a protected non-ASCII file is
  skipped
  (`test_move.py::test_untrack_keeps_a_directory_with_a_protected_non_ascii_file`).
- I-37: two moves that undo a scramble give back the tidy text of a
  moved page byte for byte; the `converge` link `../glossary.md`, which
  still resolves after the scramble, is rewritten to the tidy form
  (`test_move.py::test_moved_file_links_take_the_canonical_form`,
  `::test_unmoved_file_keeps_a_link_that_still_resolves`,
  `test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`).
- I-39: a broken-link note names the new place of a page or a file with
  the same name, the refcheck id does not change, and a broken link to
  the place of a kept page gets no note
  (`test_layout.py::test_locate_broken_link_evidence_note_names_the_new_location`,
  `::test_locate_broken_link_hint_when_the_match_already_lives_under_docs`,
  `::test_locate_evidence_notes_never_rename_a_finding_id`,
  `::test_locate_gives_a_broken_link_to_a_kept_page_no_note`).

**Round 4 (D12).** One entry for each D12 section or invariant that has a
test. S25 and S26 are the acceptance tests of D12.1 and D12.9.

- D12.1: the tree identity is `None` outside git, gives `head` and a
  status hash, changes on a second edit of a modified file and on a new
  untracked file, works from a subdirectory root, and writes no object;
  the JSON report holds `tree`, `null` outside git; `apply --plan` needs
  `--ids` or `--all-auto`, refuses a bad file, `--mode`, `--set`, an id
  the file does not hold and a plan file inside the root, and never
  collects again; the saved plan of the `converge` fixture applies later
  and gives the same files, its move ids apply, and a second edit
  refuses the run (S25)
  (`test_changes.py::test_tree_identity_is_none_outside_a_git_work_tree`,
  `::test_tree_identity_gives_head_and_a_status_hash`,
  `::test_tree_identity_changes_on_a_second_edit_of_a_modified_file`,
  `::test_tree_identity_changes_with_a_new_untracked_file`,
  `::test_tree_identity_works_from_a_subdirectory_root`,
  `::test_tree_identity_writes_no_object_and_keeps_the_index`,
  `test_check.py::test_check_json_holds_the_tree_identity`,
  `::test_check_json_tree_is_null_outside_git`,
  `test_cli.py::test_apply_plan_needs_ids_or_all_auto`,
  `::test_apply_plan_passes_the_file_to_apply_run`,
  `test_saved_plan.py::test_s25_saved_plan_all_auto_gives_the_same_files_as_a_live_run`,
  `::test_s25_saved_plan_applies_its_move_ids`,
  `::test_s25_second_edit_of_a_modified_file_refuses_and_writes_nothing`,
  `::test_saved_plan_run_never_collects_again`,
  `::test_saved_plan_with_a_plan_file_inside_the_root_refuses`,
  `::test_saved_plan_refuses_mode_and_set`,
  `::test_saved_plan_refuses_a_bad_file`,
  `::test_saved_plan_refuses_an_id_the_file_does_not_hold`,
  `::test_load_saved_run_reads_plan_findings_and_moves`,
  `::test_load_saved_run_raises_config_error_on_a_missing_file`,
  `::test_cli_apply_plan_runs_the_saved_plan`).
- D12.2: `dirty_paths` lists modified and untracked paths and both sides
  of a rename, and is empty outside git; `apply` refuses a dirty finding
  path, a dirty side file, a dirty move source and a dirty page whose
  link a move rewrites; a dirty path the run does not touch, and a dirty
  managed file with the header, are no reason to refuse; `--allow-dirty`
  lets the run go on; the stamp edits only the `run_date` line
  (`test_dirty_tree.py::test_dirty_paths_lists_modified_untracked_and_both_rename_sides`,
  `::test_dirty_paths_is_empty_outside_git`,
  `::test_apply_refuses_a_finding_path_with_uncommitted_changes`,
  `::test_apply_refuses_a_side_file_with_uncommitted_changes`,
  `::test_allow_dirty_lets_the_run_continue`,
  `::test_a_dirty_path_the_run_does_not_touch_is_no_reason_to_refuse`,
  `::test_move_refuses_a_dirty_page_whose_link_it_would_rewrite`,
  `::test_move_refuses_a_dirty_source`,
  `::test_a_dirty_managed_file_with_the_header_is_not_a_conflict`,
  `::test_stamp_edits_only_the_run_date_line`,
  `::test_cli_passes_allow_dirty`,
  `test_repin.py::test_apply_repin_refuses_a_dirty_page`).
- D12.3: line 2 of the Markdown report is the tree comment, absent
  outside git; the boxes sit on exactly the approvable ids, and the
  parity parse still gives each id; `approvable` holds the move, re-pin
  and setup ids; `--from-report` applies the ticked ids as `--ids` does,
  the setup box and a re-pin box, collects once, and refuses a report
  with no tree comment, a changed tree, an id that is not approvable, no
  ticked box and a path cut short by a dash; the CLI runs it and keeps
  it apart from `--ids` and `--plan`
  (`test_from_report.py::test_markdown_line_two_is_the_tree_comment`,
  `::test_markdown_has_no_tree_comment_outside_git`,
  `::test_boxes_sit_on_exactly_the_approvable_ids`,
  `::test_box_line_forms_and_the_parity_parse`,
  `::test_approvable_maps_each_id_to_what_it_acts_on`,
  `::test_approvable_holds_the_repin_ids`,
  `::test_from_report_applies_the_ticked_ids_as_ids_does`,
  `::test_from_report_applies_the_setup_box`,
  `::test_from_report_applies_a_ticked_repin`,
  `::test_from_report_collects_once`,
  `::test_from_report_refuses_a_report_with_no_tree_comment`,
  `::test_from_report_refuses_a_changed_tree`,
  `::test_from_report_refuses_a_ticked_id_that_is_not_approvable`,
  `::test_from_report_refuses_a_report_with_no_ticked_box`,
  `::test_from_report_cuts_a_path_with_a_dash_and_refuses`,
  `::test_cli_from_report_runs_the_ticked_ids`,
  `::test_cli_from_report_excludes_ids_and_plan`,
  `test_check.py::test_collect_wires_layout_into_the_move_plan`).
- D12.4: the SARIF run has its shape and levels, skips kept findings,
  gives locations and escapes a path that is not UTF-8; `check --sarif`
  writes the file and keeps the exit code, is refused inside the root
  unless an `ignore` glob covers it, and goes with `--changed`
  (`test_sarif.py::test_render_sarif_shape_and_levels`,
  `::test_render_sarif_skips_kept_findings`,
  `::test_render_sarif_locations`,
  `::test_render_sarif_escapes_a_surrogate_path`,
  `::test_check_sarif_writes_file_and_keeps_exit_code`,
  `::test_check_sarif_refused_inside_root`,
  `::test_check_sarif_allowed_inside_root_when_ignored`,
  `::test_check_changed_sarif`).
- D12.6: one re-pin entry for each stale pin with one clear fix, none for
  a line with two matching links or a pin that does not apply; the JSON
  and Markdown reports carry the entries; an approved id writes the new
  pin, `--all-auto` does not, an unknown id writes nothing, and a changed
  line refuses; a saved plan loads and applies the entries and refuses a
  bad one
  (`test_repin.py::test_repins_gives_one_entry_per_stale_pin`,
  `::test_repins_skips_a_line_with_two_matching_links`,
  `::test_repins_skips_a_pin_that_does_not_apply`,
  `::test_check_json_and_markdown_carry_the_repins`,
  `::test_check_json_repins_is_empty_with_no_stale_pin`,
  `::test_apply_repin_id_writes_the_new_pin`,
  `::test_apply_all_auto_does_not_repin`,
  `::test_apply_unknown_repin_id_writes_nothing`,
  `::test_apply_repin_refuses_a_line_that_changed`,
  `::test_saved_plan_loads_and_applies_the_repins`,
  `::test_saved_plan_with_a_bad_repins_entry_is_refused`).
- D12.7: the rules file is in the T2 set with its front matter and
  header, needs T2 when no page is under `docs/`, has its header on the
  first line after the front matter, and stays out of the set when the
  file on disk is not trueup's
  (`test_managed.py::test_agent_rules_file_is_in_the_t2_set_with_front_matter_and_header`,
  `::test_agent_rules_file_needs_t2_without_a_docs_page`,
  `::test_agent_rules_file_header_is_the_first_line_after_front_matter`,
  `::test_agent_rules_file_that_is_not_trueups_stays_out_of_the_set`).
- D12.8: strict Python has the `pydoclint` hook after `complexipy`
  (`test_rulesets.py::test_python_strict_has_the_pydoclint_hook_after_complexipy`).
- D12.9: `docs` defaults to `auto`, and `resolve_docs` maps it by tier;
  the render gives the tier set at T0, T1 and T2, keeps a managed file on
  disk below its tier, keeps the copy-mode checker at any tier, names the
  gitleaks config only when it is in the set, and keeps `auto` in
  `trueup.toml`; no setup finding asks for a path above the tier; the
  refcheck row runs in readme mode with the config of the tier set; the
  tier pick counts no trueup path and still counts a workflow of the
  target; at T1 with no config, one setup row and the real findings show,
  the row is not in the plan, `--all-auto` never takes it, and its id
  writes the tier set only; a T0 tree gets no row (S26)
  (`test_config.py::test_docs_default_is_auto_in_config_and_in_a_file_without_the_key`,
  `::test_resolve_docs_maps_auto_by_tier_and_keeps_an_explicit_mode`,
  `test_managed.py::test_render_t1_holds_the_t1_files_only`,
  `::test_render_t1_with_a_docs_page_holds_ref_check_toml`,
  `::test_render_t2_holds_ci_gitleaks_ref_check_and_vale`,
  `::test_render_vale_needs_t2_even_with_docs_full`,
  `::test_render_t0_holds_nothing_until_trueup_toml_exists`,
  `::test_render_copy_mode_checker_is_in_the_set_at_any_tier`,
  `::test_render_keeps_a_managed_file_on_disk_below_its_tier`,
  `::test_setup_findings_never_ask_for_a_path_above_the_tier`,
  `::test_gitleaks_hook_names_the_config_only_when_it_is_in_the_set`,
  `::test_render_keeps_docs_auto_in_trueup_toml`,
  `test_docrules.py::test_no_config_resolves_docs_by_tier`,
  `::test_refcheck_runs_in_readme_mode_with_the_tier_set_config`,
  `::test_refcheck_at_t1_without_a_docs_page_runs_with_no_switch`,
  `::test_refcheck_at_t1_with_a_docs_page_runs_with_the_readme_switches`,
  `test_survey.py::test_tier_t0_stays_t0_after_trueup_writes_its_files`,
  `::test_tier_t1_stays_t1_when_trueup_files_pass_the_file_count`,
  `::test_a_workflow_of_the_target_still_counts_as_ci`,
  `test_setup_optin.py::test_t1_check_shows_one_setup_row_and_the_real_findings`,
  `::test_setup_row_is_not_in_the_plan`,
  `::test_markdown_report_lists_the_setup_row`,
  `::test_apply_setup_id_writes_the_tier_set_only`,
  `::test_all_auto_never_takes_the_setup_row`,
  `::test_t0_tree_gets_no_setup_row_and_no_write`,
  `::test_setup_findings_without_offer_gives_the_per_file_rows`,
  `::test_setup_findings_with_a_config_gives_the_per_file_rows`,
  `::test_setup_id_with_a_config_present_is_unknown`,
  `::test_check_json_holds_the_setup_row`).
- D12.10: `_tracked_paths`, `_list_files`, `_history_renames` and
  `apply._git` keep the bytes of a name that is not UTF-8; `check` in
  Markdown and JSON, `check --out`, a code mention and `apply --ids
  move:<that name>` run with no crash
  (`test_non_utf8_paths.py::test_tracked_paths_keep_the_bad_bytes`,
  `::test_list_files_keep_the_bad_bytes`,
  `::test_history_renames_do_not_crash`,
  `::test_staged_rename_of_bad_name_is_read`,
  `::test_apply_git_keeps_the_bad_bytes`,
  `::test_check_prints_bad_names`,
  `::test_check_out_writes_bad_names`,
  `::test_code_mentions_print_bad_names`,
  `::test_apply_moves_a_bad_name`).
- D12.11: the `artifact` row counts a `.markdown` page and ignores a
  scratch-looking page; `locate` skips a directory unit whose target
  exists, also when git ignores the file in it, and leaves out a
  scratch-looking path with no `scratch` finding
  (`test_hygiene.py::test_artifact_directory_holding_a_markdown_suffix_page_is_manual`,
  `::test_artifact_ignores_a_scratch_looking_page_in_the_directory`,
  `test_layout.py::test_locate_refuses_a_directory_move_onto_an_existing_directory`,
  `::test_locate_skips_a_directory_unit_whose_target_holds_an_ignored_file`,
  `::test_locate_excludes_a_scratch_looking_path_without_a_scratch_finding`).
- I-40: a saved plan or a report acts on its own ids, collects at most
  once, and a changed tree refuses the run
  (`test_saved_plan.py::test_s25_second_edit_of_a_modified_file_refuses_and_writes_nothing`,
  `::test_saved_plan_run_never_collects_again`,
  `test_from_report.py::test_from_report_collects_once`,
  `::test_from_report_refuses_a_changed_tree`).
- I-41: `apply` without `--allow-dirty` writes no dirty path that it
  touches, except trueup's own managed output
  (`test_dirty_tree.py::test_apply_refuses_a_finding_path_with_uncommitted_changes`,
  `::test_a_dirty_managed_file_with_the_header_is_not_a_conflict`).
- I-43: a 48-file T1 tree stays T1 after the opt-in
  (`test_setup_optin.py::test_48_file_t1_tree_stays_t1_after_the_opt_in`).
- D13.1: a code segment, an extra `code_dirs` name or agent front matter
  takes a page out of the candidate set; the tables round-trip
  (`test_code_dirs.py::test_a_code_segment_takes_a_page_out_of_the_candidate_set`,
  `::test_extra_code_dirs_extend_the_default_list`,
  `::test_locate_skips_an_agent_definition_by_its_front_matter`,
  `::test_locate_reads_layout_code_dirs_from_the_config`,
  `::test_layout_and_binary_tables_round_trip`).
- D13.2: the sniff runs at T3 only; a linked file and an allowed file get
  no finding
  (`test_hygiene.py::test_binary_sniff_runs_only_at_t3`,
  `::test_binary_spares_a_file_that_a_page_links_to`,
  `::test_binary_allow_glob_spares_a_file`).
- D13.4: each hook adds one timing line below `$CLAUDE_PLUGIN_DATA`
  (`test_hooks.py::test_each_hook_writes_only_below_plugin_data`).

- D14.1: the layers give one effective config, and a profile name with no
  file stops `apply` at exit 2
  (`test_config.py::test_profile_path_finds_a_builtin_and_a_user_profile`,
  `test_apply.py::test_apply_refuses_a_set_profile_that_resolves_to_no_file`).
- D14.2: a profile or a user file cannot set a target-only key, an empty
  list differs from an absent key, and an error names its file
  (`test_config.py::test_a_profile_or_user_file_cannot_set_a_target_only_key`,
  `test_config.py::test_an_empty_root_base_replaces_the_list_and_differs_from_absent`,
  `test_config.py::test_an_error_in_a_profile_file_names_the_file`).
- D14.3: `--set` marks its keys explicit, and a write keeps the keys that
  the file set
  (`test_apply.py::test_merge_marks_the_set_keys_and_languages_explicit`,
  `test_apply.py::test_apply_keeps_the_keys_the_file_set_and_writes_set_tier_auto`).
- D14.4: the readers use the banned list and the docs directory in force
  (`test_docrules.py::test_banned_words_follows_the_prose_keys`,
  `test_docrules.py::test_page_checks_read_the_docs_dir_in_force`).
- D14.5: the checker reads `[layout]`, and the docs directory moves the
  design file of checks a and c
  (`refs/test_config.py::test_the_layout_table_reads_the_docs_dir_and_the_three_rule_switches`,
  `refs/test_layout.py::test_docs_dir_moves_the_design_of_checks_a_and_c`).
- D14.6: a lint run leaves the target unchanged and keeps the ruff cache in
  the temporary directory
  (`test_lint.py::test_lint_writes_nothing_under_the_root`,
  `test_lint.py::test_hooks_get_the_ruff_cache_in_the_temporary_directory`).
- D14.7: absent eslint packages give one row that names the install
  (`test_managed.py::test_tool_findings_name_the_absent_eslint_packages`).
- D14.8: each old managed file gives one `info` row, and `LEGACY_PATHS`
  holds each old path
  (`test_managed.py::test_managed_legacy_is_info_for_each_file_an_earlier_trueup_wrote`,
  `test_managed.py::test_legacy_paths_hold_the_old_managed_files_and_the_names_stay`).
- D14.9: the health actions name `trueup template`
  (`test_health.py::test_health_actions_name_trueup_template`).
- D14.10: the agent rules template is gone
  (`test_hooks.py::test_the_agent_rules_template_is_gone`).
- D14.11: the guard allows the wider base list, and `[root] base` replaces
  it (`test_hooks.py::test_guard_allows_the_widened_base_list`,
  `test_hooks.py::test_guard_root_base_replaces_the_list_and_root_allow_extends_it`).
- D14.12: an attribute-list id and an HTML id are link targets
  (`refs/test_links.py::test_attribute_list_id_gives_the_id_and_the_plain_slug`,
  `refs/test_links.py::test_html_id_and_name_attributes_are_anchors`).
- D14.13: a Maven tree moves to T1, and `build/` beside a Gradle file is
  build output (`test_survey.py::test_maven_tree_moves_from_t0_to_t1`,
  `test_hygiene.py::test_build_beside_build_gradle_is_build_output`).
- D14.14: a scoped secret scan finds what the full scan finds for a changed
  file, and the history scan ignores the scope
  (`test_secrets.py::test_history_scan_ignores_only`,
  `test_secrets.py::test_real_gitleaks_scoped_scan_matches_the_full_run_for_a_changed_file`).
- D14.15: the prose pre-filter gives the same hits as the loop, and the
  merge covers every config field
  (`test_docrules.py::test_prefilter_gives_the_same_hits_as_the_per_entry_loop`,
  `test_profiles.py::test_merge_covers_every_config_field`).
- D14.16: the package data holds the built-in profiles. The doc items of
  this section have no test
  (`test_plugin_manifest.py::test_the_wheel_package_data_holds_the_builtin_profiles`).
- D14.17: a real ruff run leaves no cache under the root
  (`test_lint.py::test_real_ruff_writes_no_cache_under_the_root`).
- D14.18: a user default file does not change the JSON of a target with a
  file, and a user profile with a built-in name stops `check`
  (`test_check.py::test_a_user_default_file_does_not_change_check_json_of_a_target_with_trueup_toml`,
  `test_check.py::test_a_user_profile_with_a_built_in_name_makes_check_exit_two`).
- D14.19: `--set profile` writes the key, and `apply` writes no profile
  value into the target file
  (`test_apply.py::test_set_profile_is_written_and_a_bad_name_is_refused`,
  `test_apply.py::test_apply_leaves_no_profile_key_in_the_target_file`).
- D14.20: one failed tool gives exit 1, and a bad config gives exit 2
  (`test_lint.py::test_a_failing_tool_gives_exit_1`,
  `test_lint.py::test_a_config_error_exits_2`).
- D14.21: a scoped run of the drift rows parses only the changed files
  (`test_drift.py::test_a_scoped_run_parses_only_the_scoped_and_the_named_files`).
- D14.22: an eslint hook runs with no shell, and a file of the target goes
  on the command only when it exists
  (`test_rulesets.py::test_eslint_hook_runs_npx_from_the_eslint_dir_with_no_shell`,
  `test_rulesets.py::test_owned_file_args_pass_a_target_file_only_when_it_exists`).
- D14.23: each adopter file keeps its values through one render
  (`test_adopters.py::test_adopter_file_survives_one_render`).
- D15.1: an unexpected exception gives one line and exit 2, and a deep file
  is `unreadable`, not a crash
  (`test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_a_deep_python_file_is_unreadable_not_a_crash`).
- D15.2: `check` outside git exits 2 with one line, and a git failure raises
  (`test_cli.py::test_check_outside_git_exits_two_with_one_line`,
  `test_changes.py::test_dirty_paths_raises_when_git_fails`).
- D15.3: `check --json` has schema 1, the note and the line of each finding
  (`test_check.py::test_check_json_is_schema_1_with_a_secret_note_and_a_line_per_finding`).
- D15.4: a missing tool gives exit 2, and `--skip-missing` restores the skip
  (`test_lint.py::test_a_missing_tool_and_a_failed_tool_give_exit_2`,
  `test_lint.py::test_a_missing_tool_exits_2_and_skip_missing_restores_the_skip`).
- D15.5: `--install` adds jscpd and sqlfluff, and sqlfluff runs from the
  tools directory
  (`test_lint.py::test_install_adds_jscpd_for_strict_and_sqlfluff_for_sql`,
  `test_lint.py::test_sqlfluff_runs_from_the_tools_dir`).
- D15.6: a target with no file resolves `minimal`, and an adopted target
  with no key resolves `house`
  (`test_profile_default.py::test_a_target_that_is_not_adopted_resolves_the_minimal_profile`,
  `test_profile_default.py::test_an_adopted_target_with_no_profile_key_resolves_house`).
- D15.7: a hook with no `trueup.toml` stops before the CLI import, and an
  old Python stays silent
  (`test_launcher.py::test_hook_without_trueup_toml_exits_before_the_cli_import`,
  `test_launcher.py::test_old_python_hook_exits_0_silently`).
- D15.8: a keep prefix keeps the rows of its page only, and a fingerprint id
  keys by rule and path
  (`refs/test_config.py::test_a_keep_prefix_keeps_every_failure_of_a_page_and_no_other_page`,
  `test_baseline.py::test_key_of_a_fingerprint_id_is_the_rule_and_the_path`).
- D15.9: an automatic `scratch` row needs a whole-stem name, and a name-only
  shape is manual
  (`test_hygiene.py::test_scratch_proven_needs_a_whole_stem_name`,
  `test_convergence.py::test_a_name_only_scramble_shape_gives_a_manual_row`).
- D15.10: the content of a `.env` file proves the row, and a read error
  gives a manual row
  (`test_hygiene.py::test_secret_file_flags_a_dotenv_by_name_and_proves_it_by_content`,
  `test_hygiene.py::test_secret_file_kind_is_manual_on_a_read_error`).
- D15.11: a NUL byte decides a big file
  (`test_hygiene.py::test_binary_over_a_mebibyte_is_decided_by_a_nul_byte`).
- D15.12: the floor is 256 bytes, and a group whose members a page names is
  dropped (`test_hygiene.py::test_duplicate_floor_is_256_bytes`,
  `test_hygiene.py::test_duplicate_group_whose_members_are_all_referenced_is_dropped`).
- D15.13: a content tree gives one `info` row, and a Markdown mention does
  not exempt a directory
  (`test_layout.py::test_locate_gives_a_content_tree_one_info_row`,
  `test_layout.py::test_locate_ignores_a_directory_named_only_in_markdown`).
- D15.14: health names match without case, and any licence name counts
  (`test_health.py::test_health_names_match_without_case_and_with_the_extra_candidates`,
  `refs/test_readme.py::test_licence_present_matches_any_case_and_extension`).
- D15.15: the platform rows are `info` and stay out of the plan
  (`test_health.py::test_platform_findings_are_info_and_stay_out_of_the_plan`).
- D15.16: the noun use of a form entry is silent, and the verb use fires
  (`test_docrules.py::test_banned_word_form_noun_use_is_silent_verb_use_fires`).
- D15.17: a Cargo workspace gives one command per binary member, and an
  ignored path gives `info`
  (`test_drift.py::test_a_cargo_workspace_gives_one_command_per_binary_member`,
  `test_drift.py::test_an_ignored_command_path_gives_info`).
- D15.18: a heredoc holds no suppression, and each Markdown case gives only
  its real broken links
  (`refs/test_comments.py::test_check_f_reads_no_suppression_in_a_heredoc`,
  `refs/test_links.py::test_each_markdown_case_gives_only_its_real_broken_links`).
- D15.19: the Rust reader strips the longest leader, and doc comments are
  marker positions
  (`refs/test_readers.py::test_the_rust_reader_strips_the_longest_leader`,
  `refs/test_readers.py::test_rust_doc_comments_are_marker_positions`).
- D15.20: a gitleaks timeout gives the engine row and the built-in rows, and
  the scan maps working-tree entries
  (`test_secrets.py::test_a_gitleaks_timeout_gives_a_secret_engine_row_and_the_built_in_rows`,
  `test_secrets.py::test_fake_gitleaks_maps_working_tree_entries_and_drops_the_secret`).
- D15.21: the score counts each covered file once, and a score rise or a
  clean deletion passes the gate
  (`test_score.py::test_files_category_counts_covered_files_once`,
  `test_baseline.py::test_compare_passes_a_score_rise_with_no_new_key`,
  `test_baseline.py::test_deleting_clean_files_passes_the_baseline_gate`).
- D15.22: a run opens no symlink target outside the root, and the secret
  scan skips such a link
  (`test_fsread.py::test_a_run_over_symlinks_opens_neither_target`,
  `test_secrets.py::test_full_scan_skips_a_symlink_that_leaves_the_root`).
- D15.23: a run parses each Python file once, and a checker timeout gives
  one error row
  (`refs/test_speed.py::test_each_python_file_parses_and_tokenizes_once`,
  `test_docrules.py::test_refcheck_timeout_gives_one_refcheck_run_error`).
- D15.24: the hook log keeps its last 10,000 lines, and the Stop hook has a
  limit of 30 seconds
  (`test_hooks.py::test_hook_log_over_1_mib_keeps_its_last_10000_lines`,
  `test_plugin_manifest.py::test_stop_hook_has_a_30_second_timeout`).
- D15.25: the locator follows a rename chain, stops at a cycle and says when
  the history is shallow
  (`test_layout.py::test_history_follows_the_rename_chain_back_to_a_docs_path`,
  `test_layout.py::test_history_target_stops_at_a_cycle`,
  `test_layout.py::test_shallow_clone_says_history_is_unavailable`).
- D15.26: a deep or test-directory manifest does not count for the tier, and
  another language is listed
  (`test_survey.py::test_manifests_deep_or_under_a_test_directory_do_not_count_for_the_tier`,
  `test_survey.py::test_other_languages_are_listed_as_present_with_no_rule_set`).
- D15.27: a write through a symlink is refused, and a crafted saved row is
  refused
  (`test_apply.py::test_write_through_a_symlink_out_of_the_root_is_refused`,
  `test_saved_plan.py::test_saved_plan_refuses_a_crafted_row_that_does_not_hold`).
- D15.28: a rule set has no `nightly` field, and the strict phpmd limits
  hold (`test_rulesets.py::test_rule_set_has_no_nightly_field`,
  `test_rulesets.py::test_phpmd_strict_reports_at_the_value_after_the_limit`).
- D15.29: a higher layer resets a list, and a bad `[[eslint.off]]` entry is
  an error
  (`test_profiles.py::test_a_higher_layer_resets_eslint_off_and_root_base`,
  `test_config.py::test_load_rejects_a_bad_eslint_off_entry`).
- D15.30: `docrules` and the checker give the same pages through one parser
  (`test_docrules.py::test_docrules_and_the_checker_give_the_same_pages`,
  `test_layout.py::test_front_matter_type_reads_the_checkers_parser`).
- D15.31: the guard asks about a new scratch write and leaves an existing
  file alone
  (`test_hooks.py::test_guard_asks_on_a_new_scratch_write_outside_scratch_dir`,
  `test_hooks.py::test_guard_leaves_an_existing_scratch_named_file_alone`).
- D15.32: the install guard is off by default and skips a private index
  (`test_hooks.py::test_install_guard_is_off_by_default`,
  `test_hooks.py::test_install_guard_skips_a_package_from_a_private_index`,
  `test_config.py::test_guard_defaults_and_round_trip`).
- D15.33: `hooks.json` wires `Stop` and `PostToolUse`, with no
  `SubagentStop`
  (`test_plugin_manifest.py::test_hooks_json_wires_stop_and_post_tool_use`).
- D15.34: the session text gives the tier and docs mode in force, the house
  line and the command that runs
  (`test_hooks.py::test_session_tier_and_docs_are_the_ones_in_force`,
  `test_hooks.py::test_session_text_for_the_house_profile`,
  `test_hooks.py::test_session_hint_names_the_command_that_runs`).
- D15.35: the guard reads `git add` per shell segment
  (`test_hooks.py::test_git_add_is_read_per_shell_segment`,
  `test_hooks.py::test_git_add_paths_cut_at_each_segment`).
- D15.36: each command, flag and anchor that the skill names exists
  (`test_skill_drift.py::test_skill_names_only_real_commands_and_flags`,
  `test_skill_drift.py::test_skill_anchors_resolve`).
- D15.37: `TRUEUP_OWN_PATHS` holds the four files that trueup still writes.
  The doc items of this section have no test
  (`test_survey.py::test_own_paths_are_the_four_files_trueup_still_writes`).
- D15.38: the tests name a missing lint tool and a committed copy of this
  repository has an empty plan, and the rewritten tests assert behaviour.
  The CI matrix has no local test: it first runs when a remote exists
  (`test_lint_fixtures.py::test_a_missing_lint_tool_skips_with_its_name`,
  `test_self_check.py::test_check_on_a_committed_copy_of_this_repository_has_an_empty_plan`,
  `test_survey.py::test_tools_reflects_shutil_which`,
  `test_lint.py::test_run_takes_the_root_the_paths_and_the_two_switches`).
- I-27: a committed copy of this repository has an empty plan
  (`test_self_check.py::test_check_on_a_committed_copy_of_this_repository_has_an_empty_plan`).
- I-35: within one plan, one copy of a scratch content stays manual; with
  two equal scratch copies, `--all-auto` with no saved plan removes both
  across its passes, and `apply --plan` removes only the automatic one
  (`test_hygiene.py::test_scratch_last_copy_keeps_one_removal_manual`,
  `test_convergence.py::test_all_auto_removes_two_equal_scratch_copies_across_passes`,
  `test_saved_plan.py::test_saved_plan_removes_only_the_automatic_one_of_two_equal_scratch_copies`).
- I-42: no setup row asks for a path above the tier, and `managed-legacy` is
  `info`
  (`test_managed.py::test_setup_findings_never_ask_for_a_path_above_the_tier`,
  `test_managed.py::test_managed_legacy_is_info_for_each_file_an_earlier_trueup_wrote`).
- I-44: a target file shuts out the user default file, and an unknown
  profile is exit 2
  (`test_profiles.py::test_user_default_applies_only_without_a_target_file`,
  `test_profile_default.py::test_an_unknown_profile_flag_is_exit_2_on_every_target`).
- I-45: `apply` writes no profile value into the target file
  (`test_apply.py::test_apply_leaves_no_profile_key_in_the_target_file`).
- I-46: a user file with a built-in name is an error
  (`test_profiles.py::test_user_file_with_a_builtin_name_is_an_error`).
- I-47: a lint run writes nothing under the root, and ruff leaves no cache
  there (`test_lint.py::test_lint_writes_nothing_under_the_root`,
  `test_lint.py::test_real_ruff_writes_no_cache_under_the_root`).
- I-48: the `house` config of a target file equals that file over the
  defaults, and `check --json` of `tests/fixtures/messy` under `house`
  equals a stored output of commit 720b5d2, except the rows of an allow
  list in which each entry names its design id
  (`test_profiles.py::test_house_effective_equals_the_target_file_alone`,
  `test_house_baseline.py::test_house_gives_the_output_of_720b5d2_except_the_allowed_rows`).
  Limit: the four adopter trees cannot be rebuilt (the stored head of
  target-web is gone), so no test compares an adopter with its round-13
  output. 720b5d2 is later than round 13 and earlier than the `profile`
  key.
- I-49: `.env` bytes stay out of each output, and only a matching secret
  proves the row
  (`test_apply.py::test_secret_file_is_untracked_and_its_bytes_stay_out_of_every_output`,
  `test_hygiene.py::test_secret_file_flags_a_dotenv_by_name_and_proves_it_by_content`).
- I-50: a read stops at its cap and refuses a FIFO and a symlink out of the
  root; a `house` run, a baseline run and a move over such symlinks end
  and open neither target; the checker gives `unreadable` for them; and
  `check` ends on an untracked FIFO symlink, a staged `/dev/zero`
  symlink and a `.gitignore` FIFO symlink
  (`test_fsread.py::test_read_capped_returns_a_file_within_the_cap`,
  `test_fsread.py::test_fifo_is_refused_without_blocking`,
  `test_fsread.py::test_symlink_out_of_the_root_is_refused`,
  `test_fsread.py::test_a_house_run_opens_no_managed_or_health_symlink`,
  `test_fsread.py::test_a_baseline_over_symlinks_ends_and_opens_neither_target`,
  `test_fsread.py::test_a_move_over_symlinks_ends_and_rewrites_the_real_page`,
  `test_fsread.py::test_the_report_read_refuses_a_symlink_out_of_the_root`,
  `refs/test_readers.py::test_a_symlink_to_a_fifo_gives_unreadable_and_no_hang`,
  `refs/test_readers.py::test_a_symlink_out_of_the_root_gives_unreadable`,
  `test_listed_paths.py::test_an_untracked_fifo_symlink_does_not_hang_check`,
  `test_listed_paths.py::test_a_staged_dev_zero_symlink_does_not_fail_check`,
  `test_listed_paths.py::test_a_gitignore_fifo_symlink_stops_tokei_at_its_limit`).
  Limit: the tokei case skips when tokei is not installed. A declared
  source of D16.2 is named by the target, so the checker follows a
  symlink there and can read a page outside the root.
- I-51: a write through a parent or a last component that is a symlink is
  refused
  (`test_apply.py::test_write_through_a_symlink_out_of_the_root_is_refused`,
  `test_apply.py::test_symlink_inside_the_root_is_refused_as_a_last_component`).
- I-52: an internal error is exit 2, and an empty survey is a config error
  (`test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `test_cli.py::test_a_saved_plan_run_of_an_empty_survey_is_a_config_error`,
  `test_cli.py::test_lint_of_a_repository_with_no_tracked_file_is_a_config_error`).
- I-53: an automatic `scratch`, `secret-file` or `binary` row needs a
  whole-stem name or content
  (`test_hygiene.py::test_scratch_proven_needs_a_whole_stem_name`,
  `test_hygiene.py::test_scratch_row_is_automatic_only_for_a_proven_tracked_name`,
  `test_hygiene.py::test_secret_file_row_dotenv_auto_only_with_a_matching_secret`,
  `test_hygiene.py::test_binary_over_a_mebibyte_is_decided_by_a_nul_byte`).

**Round 16 (D16).** One entry for each section of round 16 that changes
code, and for each new invariant. A section that changes only documents
or cite lines has no entry.

- D16.1: `trueup check`, `trueup lint` and the checker run on a tracked
  file below a mode-000 directory and do not raise
  (`test_path_probes.py::test_a_command_does_not_raise_below_an_unreadable_directory`,
  `test_path_probes.py::test_ref_check_does_not_raise_below_an_unreadable_directory`).
  Limit: the suite runs on Python 3.14, where the old probes also return
  False. On 2026-11-12 these two tests and the three tests that failed
  on 3.11 passed under Python 3.11.15 (`uv run --python 3.11`). The CI
  matrix has not run.
- D16.2: each declaration shape declares, a mention and a fenced block
  do not, a typo id fails, a missing source fails with one row, and the
  keys parse, render and reach the checker
  (`refs/test_declared_sources.py::test_a_design_on_many_pages_declares_each_id`,
  `refs/test_declared_sources.py::test_a_three_part_id_is_one_id`,
  `refs/test_declared_sources.py::test_each_declaration_shape_declares`,
  `refs/test_declared_sources.py::test_a_mention_does_not_declare`,
  `refs/test_declared_sources.py::test_a_fenced_block_does_not_declare`,
  `refs/test_declared_sources.py::test_a_typo_id_fails_at_each_citation`,
  `refs/test_declared_sources.py::test_a_missing_source_fails_with_one_row_per_entry`,
  `test_config.py::test_refs_declared_and_id_forms_parse_merge_and_round_trip`,
  `test_config.py::test_the_id_form_rule_equals_the_checkers`,
  `test_managed.py::test_render_ref_check_config_carries_the_declared_sources`,
  `test_hooks.py::test_session_text_names_the_declared_pages`). Limit:
  the run on a copy of target-rust (0 `unknown-id`, and the planted bad ids fail)
  is not a test of this repository.
- D16.3: the table ships empty, a registered change turns its failures
  into warnings with exit 0, an accepted change fails again, and `check`
  gives one info row
  (`refs/test_reader_changes.py::test_the_registry_ships_empty`,
  `refs/test_reader_changes.py::test_a_registered_change_turns_its_failure_into_a_warning`,
  `refs/test_reader_changes.py::test_an_accepted_change_fails_again`,
  `refs/test_reader_changes.py::test_the_command_prints_the_warning_and_exits_0`,
  `test_docrules.py::test_a_reader_change_gives_one_info_row_and_no_error`).
  Limit: the table is empty in this release, so each test registers a
  fake change with monkeypatch.
- D16.4: a link target that starts with `${NAME}` is skipped, and a
  placeholder that is not at the start still fails
  (`refs/test_links.py::test_a_link_target_that_starts_with_a_placeholder_is_skipped`).
- D16.5: the rendered gitleaks config holds the one rule override, and
  the installed gitleaks drops the published value and reports another
  value of the same shape
  (`test_managed.py::test_gitleaks_config_lists_the_ignore_globs_as_anchored_regexes`,
  `test_secrets.py::test_real_gitleaks_drops_only_the_published_value`).
  Limit: the second test skips when gitleaks is not on the path.
- D16.6: a pair that differs in one directory segment gets the label,
  and other pairs keep the plain text
  (`test_hygiene.py::test_duplicate_labels_paths_that_differ_in_one_directory_segment`,
  `test_hygiene.py::test_duplicate_keeps_the_plain_text_for_other_paths`).
- D16.7: the strict ruff config ignores `CPY` with a reason, and the
  skill says so
  (`test_skill_drift.py::test_skill_names_the_cpy_ignore_of_the_strict_ruff_config`).
  Limit: that test reads the config and runs no ruff. The ruff runs are
  the strict cases of
  `test_rulesets.py::test_python_ruff_config_passes_good_fails_bad`,
  `test_rulesets.py::test_python_ruff_config_flags_a_security_bad_file`
  and
  `test_rulesets.py::test_python_strict_ruff_config_enforces_the_nesting_threshold`,
  which cite no round 16 id. On 2026-11-12 they passed with ruff 0.15.9
  and 0.17.4.
- D16.9: see I-35 and I-48 (`test_convergence.py`, `test_saved_plan.py`,
  `test_house_baseline.py`).
- D16.10: the named reads refuse a FIFO, a device, a symlink out of the
  root and a file over the cap; a move stops on a page over the cap or a
  page link out of the root; the tree identity hashes a symlink's link
  text and opens no FIFO; and tokei stops at its limit
  (`test_fsread.py::test_read_text_refuses_what_the_rows_must_not_open`,
  `test_fsread.py::test_a_move_refuses_a_page_over_the_cap_and_changes_nothing`,
  `test_fsread.py::test_a_move_refuses_a_page_link_out_of_the_root_and_opens_no_target`,
  `refs/test_readers.py::test_a_file_over_the_read_cap_gives_unreadable`,
  `test_listed_paths.py::test_a_symlink_gets_the_blob_sha_of_its_link_text`,
  `test_listed_paths.py::test_the_identity_of_a_regular_file_is_unchanged`,
  and the tests of I-50).
- I-54: with no new key set, the checker gives the rows of today, and
  the rendered checker config holds no new table
  (`refs/test_declared_sources.py::test_with_no_key_set_the_checker_keeps_todays_rows`,
  `test_managed.py::test_render_ref_check_config_carries_the_declared_sources`).
- I-55: an id that no found source declares fails at each citation
  (`refs/test_declared_sources.py::test_a_typo_id_fails_at_each_citation`,
  `refs/test_declared_sources.py::test_a_mention_does_not_declare`).
- I-56: a missing source, also in a clone without a page outside the
  root, fails with one `no-target` row per entry
  (`refs/test_declared_sources.py::test_a_missing_source_fails_with_one_row_per_entry`,
  `refs/test_declared_sources.py::test_a_clone_without_the_outside_source_fails_with_one_row`).
- I-57: checks a and c read the same sources and forms
  (`refs/test_declared_sources.py::test_checks_a_and_c_read_the_same_sources_and_forms`).
- I-58: a registered change warns with exit 0 until it is accepted, and
  then fails with exit 1
  (`refs/test_reader_changes.py::test_the_command_prints_the_warning_and_exits_0`,
  `refs/test_reader_changes.py::test_the_command_exits_1_for_an_accepted_change`).
- I-59: the installed gitleaks drops only the whole published value
  (`test_secrets.py::test_real_gitleaks_drops_only_the_published_value`).
  Limit: the test skips when gitleaks is not on the path.
