---
id: how-trueup-works
type: explanation
audience: [maintainer, agent]
status: current
last_reviewed: 2026-11-20
---

# How trueup works

This page is a map of the code for a person who reads it for the first
time. It follows the subjects, not the design rounds. Each statement
names a module or a function, so you can open the file and read on. For
the commands and their flags, read
[the trueup reference](../reference/trueup.md). For the reason behind a
rule, read the design section that the code cites.

## The three parts

trueup is a Claude Code plugin with three parts:

- **The package, `trueup/`.** Python code that uses the standard library
  only. It finds problems and makes only the changes that have one right
  answer. `python3 trueup <command>` runs it with no install step.
- **The skill, [`skills/trueup/SKILL.md`](../../skills/trueup/SKILL.md).**
  The steps that the model follows. The skill asks the person, picks the
  modes and writes the prose. The package never does that.
- **The hooks, [`hooks/hooks.json`](../../hooks/hooks.json).** Four
  hook events of Claude Code: `SessionStart`, `PreToolUse`, `PostToolUse`
  and `Stop`. Each event runs `trueup hook <event>` from the plugin
  root, with the names `session`, `guard`, `interface` and `stop`.

The manifest `.claude-plugin/plugin.json` names the plugin. The
repository root is the plugin root.

## The path of `trueup check`

`check` finds the problems of a target repository and prints a report.
It changes no file. The steps are in order:

1. `__main__.py` adds the parent directory of the package to `sys.path`
   and calls `cli.main`. The installed `trueup` command calls `cli.main`
   directly.
2. `cli.main` builds the parser and sets the profile for the run with
   `config.profile_flag`. Its handler `_run_check` finds the root and
   calls `report.check`. With `--changed`, it calls
   `report.check_changed`, which limits the run to the files of
   `changes.working_set`.
3. `report.check` loads the config with `config.load`. Then it reads the
   identity of the working tree with `changes.tree_identity`, before any
   row reads a file.
4. `report.collect` runs the finding rows. It is the one place where all
   the rows meet:
   - `survey.run` lists the files that git tracks or would add, counts
     the lines of each language and picks the tier.
   - `secrets.scan` runs gitleaks when it is on the path.
   - `hygiene.hygiene_findings` gives the nine slop rows, such as
     scratch files, build artifacts and secret files.
   - `health.health_findings` gives the missing community files.
   - `docrules.docrules_findings` gives the document rows. It also runs
     the bundled `ref_check.py` as a child process.
   - `managed.setup_findings` compares the managed files with the disk.
   - `layout.locate` gives the `doc-misplaced` rows and the move plan.
   - `drift.drift_findings` compares the docs with the code.

   A run with `--changed` skips the health and setup rows and the
   checker.
5. `findings.protect_findings` makes each finding on a `protect` glob
   manual. `findings.build_plan` keeps the `error` and `warn` findings
   that no `[[keep]]` entry matches. That list is the plan.
   `findings.sorted_findings` gives the fixed order.
6. `score.compute` gives the slop score of the plan. With `--baseline`,
   `baseline.load` and `baseline.compare` give the gate.
7. `report.render_markdown` and `report.render_json` render the report.
   `--out` writes both files, and `--sarif` writes a SARIF file.
8. The exit code is 0 when the plan is empty and 1 when it is not. With
   `--baseline`, the gate gives the code. A bad config or an error gives
   2.

## The path of `trueup apply`

`apply` carries out the findings that the person approves.
`cli._run_apply` calls `apply.run`, which does these steps:

1. It finds the plan. With `--plan FILE`, it reads the plan that
   `check --json` saved, and it calls no `report.collect`. Else it calls
   `report.collect`. With `--from-report FILE`, the ticked boxes of a
   Markdown report give the ids. A saved plan and a report must have the
   same tree identity as the tree now.
2. `_validate` checks each requested id against the plan, the move plan
   and the re-pin entries. An unknown id or an id that is not automatic
   stops the run with exit 2 before any write (I-19). With `--all-auto`,
   the selection is every automatic finding of the plan.
3. When a path that the run touches has changes that are not
   committed, the run stops, unless `--allow-dirty` is given.
4. `_one_pass` writes `trueup.toml` first when a `config` id is
   approved, with `config.render`. Then it calls one handler for each
   other finding, from the table `_HANDLERS`. The `file-managed` handler
   writes the text that `managed.render` gives. With `--all-auto` and no
   saved plan, `run` collects a new plan and makes a new pass. It stops
   when a pass changes nothing or after `_MAX_PASSES` passes.
5. Approved re-pins run next, then approved moves. A move runs `git mv`
   and rewrites the relative links that the move changed.
6. When the run changed a file, it writes the date to `run_date` in
   `trueup.toml`.

Each write goes through `_safe_target`, which refuses a path outside the
root (I-51). `apply` never runs `git commit`, `git push` or `git clean`
(I-23).

## lint, refs and the hooks

**`trueup lint`.** `lint.run` reads the config layers and stops when the
target is not adopted. It renders the tool config of each enabled rule
set into a temporary directory. Then it runs each lint hook of
`managed.lint_hooks`, which reads the table `rulesets.RULESETS`, and
then the checker. It writes nothing under the root (I-47). A missing tool
gives exit 2, unless `--skip-missing` is given.

**`trueup refs`.** `cli.main` reads `refs` before the parser runs and
gives the other tokens, unparsed, to `ref_check.main`. `ref_check.main`
calls `ref_check.run`, which runs the nine checks a to i and prints
nothing. For example, check a tests that each cited id exists in the
design, and check g tests the document links. Exit 0 means no failure.

**The hooks.** `__main__.py` exits 0 at once for a `hook` call when the
repository has no `trueup.toml`. Else `hooks.run` reads one JSON object
from standard input and calls one handler. `session` writes a session
snapshot below `$CLAUDE_PLUGIN_DATA` and prints a notice. `guard` asks
or denies on a new root file, a new scratch file, `git add` and a
package install; the install check calls `registry.first_release`.
`interface` reminds the agent, once for each path, to update the docs
after a change to a public interface. `stop` blocks one time when the
files of the session hold findings. A hook fails open: any error gives
exit 0 and no output (I-22).

## The modules

| File | Purpose | Design ids its docstring cites |
|---|---|---|
| `__init__.py` | Marks the package; states what the package decides and what the skill decides | none |
| `__main__.py` | The launcher of `python3 trueup`: the Python version gate and the fast exit of a hook | D15.7 |
| `cli.py` | The argparse wiring; one handler for each subcommand | D5.10, D5.11, D14.1, D14.6, D14.9, D15.4 |
| `config.py` | Reads, merges and writes `trueup.toml` and the config layers | D5.3, D14.1, D14.3, D15.6 |
| `survey.py` | The inventory of a target: files, languages, tools, tier | D5.4 |
| `changes.py` | The changed files of the working tree and of a session; the tree identity | D6.2, D6.17 |
| `fsread.py` | The one bounded file reader | D15.22 |
| `findings.py` | The `Finding` shape, the plan rule, the sort order and the `[[keep]]` match | D5.4, D15.8, D15.27 |
| `hygiene.py` | The nine slop rows over every surveyed file | D5.4, D7.2 |
| `secrets.py` | Runs gitleaks and maps its report to findings | D7.3 |
| `health.py` | The community-health files and the agent-file check | D5.4, D7.6, D7.9 |
| `docrules.py` | README length, changelog, page status, banned words, the checker run, re-pins | D5.4, D12.6, D12.9 |
| `drift.py` | The four rows that compare the docs with the code | D6.5 |
| `layout.py` | The `doc-misplaced` row and the move plan | D10.2, D10.6, D10.7, D10.12 |
| `managed.py` | Renders the managed files and the templates; the `setup` rows | D5.6, D14.8, D14.9 |
| `rulesets.py` | The rule sets of each language in `strict` and `clean` mode | D5.5, D14.6 |
| `score.py` | The slop score: five weighted categories over the plan | D5.7 |
| `baseline.py` | The baseline file, the gate and the ratchets | D6.6 to D6.8 |
| `report.py` | The `check` driver: `collect`, `check` and the renderers | D5.7, D5.11 |
| `apply.py` | Carries out the approved findings, moves and re-pins | D5.6, D10.7, D12.1, D12.3, D12.6 |
| `lint.py` | Runs the linters of the effective config | D14.6, D14.7, D14.20, D15.4, D15.5 |
| `hooks.py` | The session, guard, stop and interface hooks | D5.8, D6.2 to D6.4, D14.11 |
| `registry.py` | Package registry lookups for the install guard | D7.8 |
| `ref_check.py` | The reference checker: the scan, the nine checks, the report | none; see the row "Checker" of the subject index |

`trueup/data/banned.txt` holds the banned-word list (I-25).
`trueup/templates/` holds the rule-set files, the health texts and the CI
workflow.

## Rules that you must know

- **Standard library only.** No module of `trueup/` imports a package
  from outside the standard library. Python 3.11 is the oldest version
  that the launcher accepts.
- **Deterministic, sorted output.** The same tree and the same date give
  a byte-identical report (I-21). `findings.sorted_findings` sorts by
  category order, then by id. `config.render` writes the keys in one
  fixed order (D5.3), and the JSON report has sorted keys.
- **`ref_check.py` is one file that imports nothing from the package.**
  In copy mode (D9.1), `apply` writes it byte for byte into the target,
  at the `[refs] path` of the config (I-26). So a rule that both sides
  need is in two places. For example, `ref_check.keep_match` is a copy of
  `findings.keep_match`, and a test keeps the two equal.
- **`check` is read-only.** It leaves every file under the root
  byte-identical (I-18). `--out` and `--sarif` must point outside the
  root, or to a path that an `ignore` glob covers.
- **One network module.** Only `registry.py` opens a network connection.
  `trueup lint --install` is the one other path to the network (I-28).
- **Hooks fail open.** A hook gives exit 0 on any error (I-22).

## Where the tests are

- For most modules, the tests of `trueup/<module>.py` are in
  `tests/test_<module>.py`, for example `tests/test_apply.py`.
- The tests of `report.py` are mainly in `tests/test_check.py` and
  `tests/test_sarif.py`.
- The tests of `__main__.py` are in `tests/test_launcher.py`.
- The tests of `ref_check.py` are in `tests/refs/`. Their fixtures are in
  `tests/refs/fixtures/`.
- Other test files follow a subject, not a module. For example,
  `tests/test_saved_plan.py` tests `apply --plan`, and
  `tests/test_self_check.py` runs `check` on a copy of this repository.

The full suite takes about 15 minutes. Run the test files of the modules
that you change.

## How to find a design section

The code cites design sections by id, such as `D5.4`, and invariants by
id, such as `I-21`. The architecture page holds them in the order of the
design rounds, not by subject. To find one, start at
[the subject index of the architecture](../ARCHITECTURE.md#subject-index).
It lists the sections of each subject, with the section in force first.
The invariants are in [the section Invariants](../ARCHITECTURE.md#invariants).
The docstring of a module names the sections that the module follows.
A later section can replace one of them, so look each id up in the
subject index before you rely on it.
