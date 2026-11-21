---
id: field-trial
type: explanation
audience: [maintainer, agent]
status: current
last_reviewed: 2026-11-20
---

# Field trial

This page records how trueup did on real repositories before its first
release. It gives the judged findings of the field trial, the false
positive shapes of the later runs and the section that fixed each one,
and the follow-ups that are not trueup code. The commands and the rules
are in [the trueup reference](../reference/trueup.md).

Before the fixes below landed, a field trial ran `trueup survey` then
`trueup check --json` (timed) and `check` (text) against six repositories,
read-only throughout: `git status --short` before and after every run
matched, and `trueup apply` never ran. Every finding was opened and judged
by hand as a true positive (TP), a false positive (FP), or noise (an
accurate finding on data kept on purpose, such as a test fixture). The
[Calibration](../reference/trueup.md#calibration) table above gives the same six repositories'
score before and after; this section adds the tier, the judged counts, and
the run time. The TP, FP and NOISE columns count every plan finding,
`setup` findings too (meridian's 16 TP are all first-run `config`,
`file-managed` and `gitignore` findings); the Calibration table counts
only findings in the five scored categories.

| Repo | Tier | Score before | Score after | TP | FP | NOISE | Time |
|---|---|---|---|---|---|---|---|
| trueup (control) | T2 | 0 | 0 | 0 | 0 | 0 | 2.34s |
| meridian (Python) | T2 | 21 | 0 | 16 | 0 | 19 | 1.05s |
| target-mixed/src (Python, shell, SQL, TypeScript) | T3 | 30 | 30 | 43 | 61 | 0 | 1.93s |
| target-py/src (Python, TypeScript) | T2 | 18 | 16 | 28 | 1 | 0 | 2.21s |
| target-go (Go) | T2 | 38 | 10 | 22 | 2 | 0 | 1.01s |
| target-php (PHP, Vue) | T2 | 3 | 3 | 28 | 0 | 0 | 0.95s |
| **Total (six repos)** | | | | **137** | **64** | **19** | |

The trial found six false-positive shapes:

| Id | Shape | Fixed by |
|---|---|---|
| FP-1 | `prose` banned the noun "harness" ("the test harness"), not only the verb the rule targets. | [D6.9](../ARCHITECTURE.md#d69--banned-word-forms), a form entry that matches the verb use alone |
| FP-2 | `prose` banned "unlock" even in its literal sense ("unlock the vault"). | D6.9, a form entry |
| FP-3 | `prose` cannot tell a policy file that quotes the banned list on purpose from a violation. | D6.9, a hint line under a finding naming 10 or more distinct words |
| FP-4 | `prose` banned the noun "underscore" (the `_` character), not only the verb sense. | D6.9, a form entry; the plural noun by [D8.5](../ARCHITECTURE.md#d85--verb-only-forms-underscore-and-leverage) |
| FP-5 | `secret-content` matched a PEM `BEGIN PRIVATE KEY` banner used as a documentation placeholder, with no key material after it. | [D6.10](../ARCHITECTURE.md#d610--secret-body-check), the banner now needs a base64-looking line within 3 lines after it |
| FP-6 | `refcheck` treated a project's own comment-tag convention (`# D1:`, `# O1:`, …) as an unrecognized trueup marker. | [D6.11](../ARCHITECTURE.md#d611--local-tags), `ref_check.toml`'s `[registry] local_tags` key; set through `trueup.toml`'s `[refs] local_tags` since [D8.7](../ARCHITECTURE.md#d87--refs-local_tags) |

The first run on a superrepository and its Rust submodule (target-rust, 2026-10-07)
found five more shapes, and one under-report:

| Id | Shape | Fixed by |
|---|---|---|
| FP-7 | `refcheck` walked into a submodule of the target and reported its files, which the survey never lists. | [D8.2](../ARCHITECTURE.md#d82--nested-repository-boundary), the walk stops at a nested `.git` |
| FP-8 | `lockfile` fired on `lint/typescript/package.json`, the manifest trueup itself writes. | [D8.3](../ARCHITECTURE.md#d83--managed-manifest-and-the-install-note), the managed marker exempts it; an `info` finding names the install |
| FP-9 | `prose` fired on a list item or paragraph that quotes the banned list to state the rule (`Never use: ...`). | [D8.4](../ARCHITECTURE.md#d84--quoted-list-rule), the cue rule in `check` and in the Vale template |
| FP-10 | `prose` fired on the plural noun `underscores` and on the noun `leverage`. | [D8.5](../ARCHITECTURE.md#d85--verb-only-forms-underscore-and-leverage), verb-only form entries |
| FP-11 | The Vale hook fired on a string literal (`Page.navigate`) in an `.mjs` file, which Vale reads as plain text. | [D8.6](../ARCHITECTURE.md#d86--vale-source-extensions), the template names the lexed extensions only |
| UR-1 | The first `check` ran the checker with every switch off, because the target had no `ref_check.toml` yet; `apply` then wrote one, and the next `check` grew from 4 to 243 `refcheck` findings. | [D8.1](../ARCHITECTURE.md#d81--first-run-refcheck-parity), `check` runs the checker with the rendered `ref_check.toml` |

The second run on target-rust/src (2026-10-07) found one more shape, and three
gaps:

| Id | Shape | Fixed by |
|---|---|---|
| FP-12 | `file-managed:ref_check.py` gave a manual warn on a copy nobody edited: the copy an earlier trueup wrote, before an update of the checker. | [D9.3](../ARCHITECTURE.md#d93--the-checker-copy-carries-the-managed-header), the copy carries the header, so `apply` rewrites it; in global mode ([D9.1](../ARCHITECTURE.md#d91--checker-modes)) there is no copy |
| G-1 | The `ref-check` hook failed on 35 findings that `[[keep]]` held out of the plan: the standalone checker read `ref_check.toml` only. | [D9.2](../ARCHITECTURE.md#d92--kept-failures-in-ref_checktoml), the `[keep]` table |
| G-2 | The layout check could not be switched off for a repository whose pages keep fixed paths; the only way out was one `[[keep]]` entry per page. | [D9.4](../ARCHITECTURE.md#d94--refs-layout), `[refs] layout = false` |
| G-3 | The checker was a copy in each repository, so each update of trueup left an old copy in every target. | [D9.1](../ARCHITECTURE.md#d91--checker-modes), global mode runs `trueup refs` from one install |

A run on target-web/3d (2026-10-16) found two more shapes:

| Id | Shape | Fixed by |
|---|---|---|
| FP-13 | `refcheck` read the query string of a local link (`../public/sim.html?preset=...`) as part of the file path, so 30 links to a file that exists failed with `broken-link`. | [D2.10](../ARCHITECTURE.md#d210--document-link-rules), the path part ends at the first `?` |
| FP-14 | The `vale` hook failed on `.state/runs/` records and on `public/vendor/three/`, paths that the `ignore` globs leave out of `check`, so each commit of a run record failed. The `eslint` hook got the same paths. | [D5.6](../ARCHITECTURE.md#d56--managed-files-and-apply), each hook that gets the file names excludes the `ignore` globs |

FP-1 (18), FP-2 (1) and FP-3 (2) drove 21 of target-mixed/src's 61 false
positives; the other 40 were FP-6. FP-4 was target-py/src's one false
positive. FP-5 alone drove about 28 of target-go's 38 v1 points (the
`security` category is a step function, so one false positive filled its
full weight of 25). FP-6 is fixed in `ref_check.py` and re-copied into this repository,
but target-mixed/src's own `ref_check.toml` does not yet set `local_tags`
(see [Follow-ups](#follow-ups)), so its score does not move in the
Calibration table above. The raw trial record, with the evidence for every
row, is `.state/runs/trueup-v2/00-field-trial.md`, a private work record
of the maintainer that is not in this repository.

## Follow-ups

Not done by this version, and not `trueup` code:

- **target-mixed's own `trueup.toml`.** [D6.11](../ARCHITECTURE.md#d611--local-tags)
  adds the `[registry] local_tags` key so a project's own comment-tag
  convention (`# D1:`, `# O1:`, `# K2:`, `# L1:`, `# S1:`) is not read as an
  unrecognized trueup marker (FP-6, above). Since
  [D8.7](../ARCHITECTURE.md#d87--refs-local_tags) the key is set in
  `trueup.toml`, as `[refs] local_tags = ["D", "O", "K", "L", "S"]`, and
  `apply` renders it into the managed `ref_check.toml`; a hand edit of that
  file is drift. `target-mixed/src` still needs the key; until then,
  `check` on that repository keeps reporting the FP-6 findings.
  `target-rust/src` has it since 2026-10-07.
- **A git source for trueup.** Since 2026-11-16 the source is
  `https://github.com/amsys/trueup`: a CI runner installs trueup with
  `pip install git+https://github.com/amsys/trueup@<tag>`, and the
  `trueup-baseline` hook of
  [gate CI with a baseline](../how-to/gate-ci-with-a-baseline.md) names
  it as `repo:`. Open: the CI template still has only a comment where
  the install goes, and a repository whose CI cannot reach GitHub
  keeps the checker copy ([D9.1](../ARCHITECTURE.md#d91--checker-modes)).
- **Quoted mentions in double quotes.** A banned word quoted on its own
  (`"seamless"`) in a block with no cue still gives a `prose` finding
  ([D8.4](../ARCHITECTURE.md#d84--quoted-list-rule) names the gap). Five
  such blocks sat in community plugin docs, none in target-rust.
- **The meridian check's MADR decision page type.** The document-layout
  check (check h), merged from the archived meridian project, recognizes
  four page types: `tutorial`, `how-to`, `reference` and `explanation`. A
  fifth, `decision` (a [MADR](https://adr.github.io/madr/)-style
  architecture decision record under `docs/decisions/`), needs adding to
  its `_PAGE_TYPES` and its layout check. Not started.
