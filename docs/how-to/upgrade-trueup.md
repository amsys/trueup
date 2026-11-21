---
id: upgrade-trueup
type: how-to
audience: [maintainer, agent, user]
status: current
last_reviewed: 2026-11-20
---

# Upgrade trueup

Read this page when a target moves to a new version of trueup. It gives
the steps to remove the old managed lint tree, and for each version the
changes that can change the result of a run. The commands, keys and
findings are in [the trueup reference](../reference/trueup.md).

## Moving from the managed lint tree

Before D14.8, `apply` wrote a tree of lint files into the target. Now
the target keeps only `trueup.toml` (and, in copy mode, the checker
pair), and `trueup lint` renders the tool configs at run time. The old
files stay where they are until the person removes them; trueup never
removes them. `check` gives one `managed-legacy` info row for each old
file that an earlier trueup wrote, and the row changes no exit code.

`managed.LEGACY_PATHS` holds the old managed paths:

- `.pre-commit-config.yaml`
- `.github/workflows/trueup.yml`
- `.editorconfig`
- `lint/jscpd.json`
- `lint/gitleaks/gitleaks.toml`
- `.claude/rules/trueup.md`
- `lint/typescript/eslint.config.mjs`
- `lint/typescript/package.json`
- `lint/typescript/node_modules`
- `lint/vale/.vale.ini`, and the eight files under `lint/vale/styles/`:
  `Trueup/Banned.yml`, `Contractions.yml`, `FirstPerson.yml`,
  `Latin.yml`, `SentenceLength.yml`, `We.yml`, `Will.yml` and
  `config/vocabularies/Trueup/accept.txt`

The rule-set files under `lint/<language>/` that carry the managed
header (for example `lint/python/ruff.toml`) get the same row.

The steps for one target:

1. Run `check` and read the `managed-legacy` rows.
2. Replace the old local hooks of `.pre-commit-config.yaml` with the
   one entry that `trueup template pre-commit` prints:

   ```yaml
   repos:
     - repo: local
       hooks:
         - id: trueup-lint
           name: trueup lint
           entry: trueup lint
           language: system
           pass_filenames: true
           require_serial: true
   ```

   Keep the hooks of the target's own in the same file. Remove the
   managed header line, so the file is the target's own.
3. With TypeScript or Vue on, run `trueup lint --install` once on each
   machine. It uses the network.
4. Run `trueup lint` and fix or record what it reports.
5. Remove each old file with `git rm`. Keep the files that the target
   owns: the eslint suppressions file and the pydoclint baseline. Their
   paths are the `[eslint] suppressions` and `[python]
   pydoclint_baseline` keys, so they can stay where they are.
6. For a CI workflow or an `.editorconfig` that the target wants to
   keep, remove the managed header line, or replace the file with the
   text of `trueup template ci` or `trueup template editorconfig`.

Since 2026-11-02 the old paths are not in the list of trueup's own
files that the tier pick does not count (`survey.TRUEUP_OWN_PATHS`,
D15.37). They count for the tier and the root budget, so a target that
still holds them can change tier (a T0 tree can reach T2); step 5
removes them. The
lockfile exemption of the old `lint/typescript/package.json` stays
(D8.3).

A repository can also use the `trueup-lint` hook of
`.pre-commit-hooks.yaml` (`language: python`) as a `repo:` entry, with
`https://github.com/amsys/trueup` as `repo:` and a tag as `rev:`.

## Upgrade notes

**The JSON managed-file marker (v2).** A managed JSON file this repository
renders with no comment syntax (`lint/jscpd.json`,
`lint/typescript/package.json`) now carries a top-level `"_managed":
"trueup"` key, so `trueup` can tell its own file from one a person wrote by
hand under the same path. For one version, a file with no marker is still
read as managed when its keys and values match the old, marker-less form
that `trueup` wrote before this change (apart from a short list of values
every version is free to differ on, such as a pinned dependency version).
A person's own file under the same path, one `trueup` never wrote, is
unaffected: it was already a manual, unmanaged finding, and stays one.

**Checker modes (2026-10-07).** A target set up before this version has
a checker copy at `ref_check.py` and a hook entry `python3 ref_check.py
--root .`. With no `[refs] mode` key it is now in global mode. The steps
to move it:

1. Install trueup once on the machine: `uv tool install --editable
   <plugin root>` (the editable install follows the trueup working tree),
   or `pipx install <plugin root>`. Each machine that commits needs this.
2. Run `check`. Expect `file-managed:.pre-commit-config.yaml` (the hook
   entry becomes `trueup refs --root .`), `file-managed:ref_check.toml`
   when a `refcheck:` id is kept (the `[keep]` table), the `info` finding
   `refs-copy:ref_check.py`, and, for a repository whose pages keep fixed
   paths, the chance to replace the `no-front-matter` keep entries with
   `[refs] layout = false`.
3. `apply` the `file-managed` ids, then `git rm ref_check.py`.
4. Run `pre-commit run --all-files`: the `ref-check` hook now passes on
   the kept findings.

A repository whose CI runs the hooks keeps the copy: set `[refs] mode =
"copy"` before step 2. Its old copy has no trueup header, so the first
`check` gives the manual `file-managed` warn: `git rm ref_check.py`, run
`check` again, and `apply` the automatic error for the absent copy. From
then on the copy carries the header, and `apply` rewrites it at each
update. CI cannot install trueup until it has a git source.

A target whose `trueup.toml` set `[refs] path` before this version, with
no `mode`, now exits 2 on every command: add `mode = "copy"` above the
`path` line. The `refs-copy` finding looks at `ref_check.py` of the root
only; an old copy at another path gets no finding, so delete it by hand.
`target-rust/src` is one target to move; `target-mixed/src` and this
repository's calibration repositories are others.

**`[scan] ignore` (2026-10-16).** A target with `ignore` globs gets
`file-managed:ref_check.toml`: the rendered file now holds `[scan] ignore`.
In copy mode, apply it together with the `file-managed` id of the checker
copy: an older copy does not know the `[scan]` table and exits 2 on it. In
global mode the installed `trueup` must be this version or later.

**Trust round, wave A (2026-11-02).** These changes can change the
result of a run that passed before:

- A target with no `trueup.toml` and no user default file runs
  `minimal`, not `house` (D15.6). Pass `--profile house` to see the house
  rows before the setup.
- `survey`, `check`, `apply`, `baseline` and `lint` exit 2 outside a git
  work tree, and all but `survey` exit 2 on a root with no file to check
  (D15.2). `survey` prints the empty survey there and exits 0.
- `trueup lint` exits 2 when a tool is not installed (D15.4). Install the
  tool, or add `--skip-missing` to the call. A CI job that ran
  `trueup lint` with a missing tool now fails.
- `trueup lint` runs jscpd and sqlfluff only from the tools directory
  (D15.5). Run `trueup lint --install` once on each machine.
- `secret-content` and `changelog` ids hold a fingerprint, not a line
  number (D15.8). A keep written for an old line-numbered id
  (`secret-content:<path>:<n>` or `changelog:<path>:<n>`) now matches
  nothing, and `check` shows a `keep-stale` row for it. Replace it with
  the new id from `check --json`, or keep the file by prefix
  (`secret-content:<path>`). `target-rust/src` holds such a keep. This
  repository's own `trueup.toml` dropped the keep
  `prose:tests/test_docrules.py`: its `keep-stale` row showed that it
  kept nothing.
- The keys of `.trueup-baseline.json` do not change, so an existing
  baseline file stays valid.

**Trust round, wave B (2026-11-02).** These changes can change the plan
of a run:

- `scratch` is automatic only for a tracked name that proves scratch
  (D15.9). `README.old.md`, `* copy.*` and `.swp` scratch rows, and each
  other candidate that only looks like scratch, are manual now. An
  `apply --all-auto` that removed them before leaves them for the owner.
- `secret-file` reads 64 bytes of a key name, and the secret scan of an
  `.env` file decides that row (D15.10). A public certificate gives no
  row; a key name with an unknown head and an `.env` file with no proven
  secret are manual now.
- A text file over 1 MiB gives an `info` `large-text` row, not a
  `binary` warn (D15.11).
- `duplicate` skips a file under 256 bytes, and a group whose every copy
  is in use (D15.12).
- A page in a tooling tree, a generated page, a page whose directory a
  build file names, and the pages of a content tree get no
  `doc-misplaced` row and no move (D15.13).
- `platform:*` rows are `info`, so they no longer make `check` exit 1
  (D15.15). A `[[keep]]` entry for one of them still matches it and does
  not go stale.
- `harness` is not banned any more (D15.16).
- A `drift-command` path that git ignores, or that a build file names,
  is `info` (D15.17).
- The checker reads more Markdown forms (D15.18) and Rust `///` and
  `//!` lines as marker positions (D15.19). A Rust target can get many
  more `refcheck` rows.
  Real target: target-rust/src gives 670 failures and 617 references (was 11 and 0): 617 `unknown-id`, 44 `malformed`, 9 `unregistered`.

**Trust round, wave C (2026-11-03).** These changes can change the
result of a run:

- A gitleaks run that fails gives a `secret-engine` error row, so
  `check` exits 1 (D15.20). Fix the gitleaks run; the built-in rows
  still run.
- `check --baseline` no longer fails on a score rise alone (D15.21). The
  `files` category counts covered files, not findings.
- A file over 1 MiB gives no text to a text read (survey, hygiene,
  layout, drift), and a symlink out of the root or a device gives no
  content (D15.22). The line counter counts such a file with 0 lines.
- A manifest deeper than one level, or under a test or example
  directory, no longer counts for the tier (D15.26). A target can get a
  lower tier.
- An untracked page gets no move (D15.27). `apply --plan` refuses a
  saved automatic row that does not hold on the tree now, and `apply`
  refuses a write that resolves outside the root.
- The `run_date` stamp keeps the comments of `trueup.toml`; a config
  write still drops them (D15.27).
- `refs.path` with copy mode from another layer is valid now; a layer
  that sets `[[eslint.off]]` replaces the lower list; a higher `[layout]`
  switch wins over a lower `[refs] layout`; a bad `run_date` exits 2
  (D15.29).
- The strict TypeScript rule set also lints `js,jsx,mjs,cjs` files, and
  the Vue and phpmd strict limits changed (D15.28). A target can get new
  lint failures.

**Trust round, own paths (2026-11-02).** This change can change the tier
and the root budget of a target:

- The old managed paths (`lint/`, `.editorconfig`,
  `.pre-commit-config.yaml`, `.github/workflows/trueup.yml`,
  `.claude/rules/trueup.md`) count for the tier, the root budget and CI
  (D15.37). Only `trueup.toml`, `ref_check.toml`, `.trueup-baseline.json`
  and `ref_check.py` stay out. An adopter of an earlier trueup can get a
  higher tier or a `root-budget` warning; remove the old files (see
  [Moving from the managed lint tree](#moving-from-the-managed-lint-tree)).

**Round 16 (2026-11-09).** With none of the three new `[refs]` keys set,
the checker gives the same rows as before (I-54). These changes can
change the result of a run:

- Reader changes (D16.3). From this release on, a release that widens
  what the checker reads registers the change for one release. The new
  failures of that change are `warning:` lines and one
  `refs-reader-change:<name>` info row, and the exit code does not
  change. Fix the markers in that release, because the next release
  fails on them. To fail on them at once, add the name to
  `[refs] accepted_reader_changes`. No change is registered in this
  release.
- A design on more than one page, or with other id forms, can set
  `[refs] declared` and `[refs] id_forms` (D16.2). A source that is
  missing on a machine, for example a page outside the root in a clone,
  fails the run with one `no-target` row.
- A link target that starts with `${NAME}` no longer gives `broken-link`
  (D16.4).
- The rendered gitleaks config drops the `generic-api-key` row of the
  RFC 6455 sample key (D16.5). A `[[keep]]` entry for that row then gives
  `keep-stale`: remove it.
- A `duplicate` row whose two paths differ in one directory segment has
  a new evidence and action text. Its id does not change (D16.6).
- The strict ruff config ignores `CPY` (D16.7).
- More reads are bounded (D16.10). The reads of `docrules`, `baseline`,
  `apply`, `health` and `managed` refuse a device, a FIFO, a symlink out
  of the root and a file over the cap. The checker gives `unreadable`
  for each of them. A coverage report or baseline file that is a symlink
  out of the root reads as absent, so a recorded `test` value fails the
  gate as a missing report.
- A `move:` id stops with `failed <move id>: refused: <rel> ...` when a
  tracked Markdown page is over the read cap, or is a symlink to a
  regular file out of the root, because the run cannot see the links of
  that page (owner ruling 11 of round 16). Move such a page by hand. A
  device, a FIFO and a page that does not decode do not stop a move.
- The tree identity of a listed symlink is the sha of its link text
  (D16.10). A plan saved over such a tree before this release gives
  exit 2 one time: run `check` again.
- The tokei call has a limit of 60 s. On expiry the survey uses the
  built-in counter and prints one line (D16.10).
- On Python 3.11 to 3.13, a path below a directory that the run cannot
  read no longer raises (D16.1).
