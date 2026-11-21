---
id: trueup
type: reference
audience: [maintainer, agent]
status: current
last_reviewed: 2026-11-02
---

# trueup reference

This page lists what `trueup` checks and installs, and how to run it by
hand. For the steps a person follows with the Claude Code skill, read
[apply-trueup](../how-to/apply-trueup.md). For the steps to gate CI on a
baseline, read
[gate CI with a baseline](../how-to/gate-ci-with-a-baseline.md). For the
design behind these commands, read [ARCHITECTURE.md](../ARCHITECTURE.md),
sections D5.3 to D5.11, D6.2 to D6.17, D7.1 to D7.10, D8.1 to D8.8,
D9.1 to D9.6, D10.2 to D10.8, D12.1 to D12.10 and D13.1 to D13.6.
The profiles, `trueup lint` and `trueup template` are D14.1 to D14.23.
The trust round is D15.1 to D15.38; this page states D15.1 to D15.29 of
it.

## Command line

`trueup` is a stdlib-only Python package. Run it as a directory, with no
install step:

```sh
python3 trueup <command> [options]
```

Inside a Claude Code plugin, the skill runs it as
`python3 "${CLAUDE_PLUGIN_ROOT}/trueup" <command>`.

| Command | Purpose | Exit code |
|---|---|---|
| `survey [--root DIR]` | Print a JSON inventory of the target: files, languages, tools on the path, the picked tier. When no file stays after the `ignore` globs, it prints the empty survey and exits 0. | 0, or 2 on a bad `trueup.toml` or on one of the [errors](#errors) |
| `check [--root DIR] [--json] [--out DIR] [--sarif FILE]` | Print the findings report: Markdown by default, JSON with `--json`. It runs no code from the target (see [trueup check](#trueup-check)). | 0 when the plan is empty, 1 when it holds a finding, 2 on a bad `trueup.toml`, on one of the [errors](#errors), or when `--out` or `--sarif` is inside the root and no `ignore` glob covers it |
| `check --changed [--root DIR] [--json]` | Scope the plan to the changed files: the working tree against `HEAD`, plus untracked files, less ignored and deleted files (`trueup/changes.py` `working_set`). It runs no `refcheck` row and drops every repo-wide finding (see [trueup check](#trueup-check)). | 0 when the scoped plan is empty, 1 when it holds a finding, 2 when combined with `--baseline` or `--out` |
| `check --baseline [--root DIR] [--json]` | Compare the plan against `.trueup-baseline.json` instead of judging it directly (see [Baseline](#baseline)). Reads the file; writes nothing (I-18, I-16). | 0 when nothing new; 1 when a finding key's count rose, a ratchet dropped, or a ratchet report the baseline recorded is now missing (the score is information only, D15.21); 2 when no baseline file exists, when the file is not a trueup baseline (see [Baseline](#baseline)), or on a bad `trueup.toml` |
| `baseline [--root DIR]` | Run a full `check` and write `.trueup-baseline.json`: the plan's finding counts and the clean-mode ratchet values. Writes that one file and nothing else, and prints `baseline: <n> keys, score <s>`. | 0, or 2 on a bad `trueup.toml` |
| `apply [--root DIR] (--ids ID[,ID...] \| --all-auto \| --from-report FILE) [--plan FILE] [--allow-dirty] [--mode LANG=MODE[,...]] [--set KEY=VALUE ...]` | Carry out the named ids, or every automatic finding (see [Approval ids](#approval-ids), [Saved plan](#saved-plan) and [Dirty tree](#dirty-tree)). Prints one line per action. | 0 on success, 1 when one handler, one `git mv` or one re-pin failed, or a write was refused because it resolves outside the root (the rest still ran; see [Writes stay in the root](#writes-stay-in-the-root)), 2 when an id is unknown, not in the current plan, or not automatic, when a `move:` or `repin:` id is not in its plan, when a `--mode` or `--set` value is bad, when the saved plan or the report is bad or its tree changed, when an automatic row of the saved plan does not hold on the tree now, when a touched path has uncommitted changes, or on a bad `trueup.toml` — with nothing written |
| `lint [--root DIR] [--profile NAME] [--changed] [--install] [--skip-missing] [PATH ...]` | Run the linters of the rule sets in force on the target, with tool configs that it renders into a temporary directory at run time (see [trueup lint](#trueup-lint)). Writes nothing under the root (I-47). | 0 when each tool ran and exited 0, 1 when one tool failed, 2 when a tool is not installed and `--skip-missing` is absent (also when another tool failed), on a bad `trueup.toml` or profile, on `PATH` together with `--changed`, when the target has no `trueup.toml` and no user default file exists, or on one of the [errors](#errors); with `--install`, the first exit code of the install commands that is not 0 |
| `template <name>` | Print one template to standard output: a file that trueup no longer manages, for the person to keep as their own (see [trueup template](#trueup-template)). Takes no `--root`. | 0, or 2 for no name or an unknown name |
| `hook session\|guard\|stop\|interface` | Read one JSON object from standard input and run one Claude Code hook (see [Hooks](#hooks)). | 0 for any of the four events; argparse exits 2 before the handler runs for any other event name |
| `refs [--root DIR] [--edges FILE] [--config FILE]` | Run the reference checker directly (see [trueup refs](#trueup-refs)). `--config FILE` reads `FILE` in place of `ROOT/ref_check.toml`. | 0 no failure, 1 one failure or more, 2 a bad command line, a bad `ref_check.toml`, or an absent `--config` file |

`--root` defaults to the git top level of the working directory; give it
when the working directory is not inside the target's own git repository.
A `--root` that is not a directory exits 2 with `trueup: --root <path>: not a directory`.
`--changed` and `--baseline` cannot be given together, and neither can
`--changed` and `--out`; `--baseline` and `--out` can. `trueup refs` is the
exception: with none of `--root`, `--root=...`, `-h` or `--help` among its
own tokens, it adds `--root <git top level>` itself, the same default.

`trueup --version` prints `trueup <version>` and exits 0. Give that line
in a bug report.

`--profile NAME` is an option of `survey`, `check`, `baseline`, `apply`
and `lint`. It holds for one run. `main` sets `TRUEUP_PROFILE` before
any config load and restores the old value after the run, also on an
error, so the value never leaks into a later run in the same process.
The profile `NAME` replaces the one that `trueup.toml` names (see
[Profiles](#profiles)). `refs` and `hook` have no such option; they read
`TRUEUP_PROFILE` from the environment. `apply --profile NAME` changes
the config of that run only and writes no `profile` key; `apply --set
profile=NAME` writes the key. The flag check reads the name shape, and
that the profile file exists in the built-in directory or at
`$XDG_CONFIG_HOME/trueup/profiles/<name>.toml`. An unknown or invalid
name exits 2 on every target, adopted or not. The message starts with
`trueup: --profile: ...` when the flag named the profile, and with
`trueup: TRUEUP_PROFILE: ...` when the variable named it.

The Markdown report of a full `check` prints the profile line after the
tree comment: `profile <name> (<path>)`. A target that is not adopted
(see [Precedence](#precedence)) prints in its place
`profile minimal (no trueup.toml; pass --profile house for the house standard)`.
The JSON report holds `profile`, with `name`, `path` and `source` (D14.3,
D15.3). The Markdown report of `check --changed` has no profile line;
its JSON report holds the same `profile` object.

`--mode` sets a language's mode: `LANG=strict`, `LANG=clean` or `LANG=off`,
comma-separated for more than one. `--set` writes a `trueup.toml` field:
`tier=auto|T0|T1|T2|T3`, `public=true|false`, `docs=auto|full|readme`,
`stale_days=<positive integer>`, or `profile=<name>` (lower-case letters,
digits and hyphens). `apply` writes each key that `--set` names, also
when its value is the default.

### Exit codes

`check` and `apply` use the same three values (D12.12). The last column
maps them to the `-detailed-exitcode` option of Terraform `plan`, so a CI
author can reuse a known rule.

| Exit code | `check` | `apply` | Terraform `-detailed-exitcode` |
|---|---|---|---|
| 0 | The plan is empty. | All named actions succeeded. | 0: no change |
| 1 | The plan holds a finding. | One handler, one `git mv` or one re-pin failed, or a write was refused because it resolves outside the root. | 2: changes pending (trueup 1 is a plan, not an error) |
| 2 | Bad input: a bad `trueup.toml`, a bad flag combination, `--out` or `--sarif` inside the root, or one of the [errors](#errors). | Bad input: an unknown or not automatic id, a bad value, a bad or stale saved plan or report, a saved automatic row that does not hold on the tree now, a touched path with uncommitted changes, or one of the [errors](#errors). Nothing is written. | 1: error |
| 2 | Internal error: an exception that is not a `ConfigError` (see [Errors](#errors)). | Internal error, as for `check`. | 1: error |

The two tools swap the meaning of 1 and 2. In Terraform, 1 is an error and
2 is a plan. In trueup, 1 is a plan and 2 is bad input.

### Errors

Each error below exits 2 with one line on standard error (D15.1, D15.2,
D15.7). No error is silent.

- **Git is required.** `survey`, `check`, `apply`, `baseline` and `lint`
  read the tracked files. A root that is not in a git work tree
  (`survey.in_work_tree(root)`) gives
  `trueup: <root>: not a git repository; trueup reads tracked files`.
  `trueup refs` does not need git: with no work tree it runs the checker
  with its own defaults, and with no `--config` text.
- **A git command fails.** The line is
  `trueup: git <cmd> failed in <root>: <first stderr line>`. A branch with
  no commit yet (an unborn `HEAD`) is not an error: the survey counts 0
  contributors.
- **No file to check.** When no file stays after the `ignore` globs,
  `check`, `baseline` and `apply` (through `report.collect`), and `lint`,
  give
  `trueup: <root>: no tracked file to check (after [scan] ignore)`.
  `survey` prints the empty survey and exits 0.
- **A config file cannot be read.** A `trueup.toml` or a profile file
  that cannot be read, or is not UTF-8, raises a `ConfigError`:
  `trueup: <file>: cannot read: <reason>`. `check` loads `trueup.toml`
  before it reads the tree identity, so a bad file gives its own message,
  not a git message.
- **A bad config value.** A config error starts with the full path of
  the file, the target `trueup.toml` too (D15.29). An unknown table key
  reads `[refs] bogus: unknown key; allowed: 'mode', 'path', ...`; a
  table key that is not a table reads `[<table>] must be a table`. A
  `run_date` that is not empty and not an ISO date reads
  `run_date must be a date as YYYY-MM-DD`. A rule that reads two keys
  runs on the merged layers (see [Precedence](#precedence)).
- **A bad baseline file.** See [Baseline](#baseline).
- **An internal error.** An exception that is not a `ConfigError` gives
  `trueup: internal error: <Type>: <msg> (set TRUEUP_DEBUG=1 for the traceback)`.
  With `TRUEUP_DEBUG=1` the traceback prints first. A `hook` command stays
  silent and exits 0 (I-22). `ref_check.py` has the same handler, with the
  prefix `ref_check:`, and exits 2.
- **An old Python.** The launcher `python3 trueup` needs Python 3.11 or
  later. An older Python gives
  `trueup: needs Python 3.11 or later, this is <x.y.z>`. A `hook` command
  exits 0 with no output.

A file that a reader cannot parse because the parse runs out of memory
(`MemoryError`) or of recursion depth (`RecursionError`) is skipped, and
is no error: the drift and baseline readers skip it, and the checker
reports it as `unreadable`.

### trueup check

`--out DIR` also writes `DIR/trueup-report.md` and
`DIR/trueup-report.json`. `check` writes nothing else, and runs no code
from the target: the `refcheck` row runs the bundled `ref_check.py`,
never the target's copy (D8.1, D9.2). Give it a `DIR` outside the
target, or an ignored one, and the target stays byte-identical. The
Markdown report lists every finding once, under `Plan`, `Kept` (a finding
`[[keep]]` names, with its reason) or `Info`, and the JSON `findings` key
holds every finding (see [JSON report](#json-report)).

`check --changed` reads no session snapshot, so a file that was already
changed before the session also counts; the Stop hook (see
[Hooks](#hooks)) uses the snapshot instead. The repo-wide findings that
it drops are `health`, `setup` and `root-budget`; the report carries no
score, since a score is for the whole repository. It makes no move plan
and runs no git history scan (see the `doc-misplaced` row).

### JSON report

`check --json` prints schema 1 (D15.3). The full report has the keys
`schema`, `profile`, `secret_engine`, `secret_note`, `survey`,
`findings`, `plan`, `kept`, `moves`, `repins`, `score` and `tree`, and
`baseline` under `--baseline`.

| Key | Value |
|---|---|
| `schema` | The integer `1` (`report.JSON_SCHEMA`). |
| `profile` | `{"name", "path", "source"}`. `source` is `--profile`, `TRUEUP_PROFILE`, `target`, `user default` or `built-in default` (see [Precedence](#precedence)). It is never `null`: a target that is not adopted gives `{"name": "minimal", "path": ".../data/profiles/minimal.toml", "source": "built-in default"}`. |
| `secret_engine` | `gitleaks` or `built-in` (see [Secret engine](#secret-engine)). |
| `secret_note` | A string: `""` when gitleaks ran to the end or is not on the path, else the note, for example `gitleaks failed: exit 2`. It is the same text as the Markdown line `secrets built-in (<note>)`. |
| `findings`, `plan` | Finding objects with `id`, `rule`, `category`, `severity`, `path`, `evidence`, `action`, `auto` and `line`. `line` is an integer: the 1-based line that the finding points at, or `0` when it points at no single line (see [Ids, lines and keeps](#ids-lines-and-keeps)). |
| `kept` | The `id` and `reason` of each kept finding. `kept[].id` is the finding id, not the keep id; `reason` is the reason of the keep that matched. |
| `tree` | The tree identity, `{"head", "status"}` (see [Saved plan](#saved-plan)). |

`check --changed --json` has the keys `schema`, `scope` (`"changed"`),
`profile`, `secret_engine`, `secret_note`, `survey`, `findings`, `plan`,
`kept`, `tree` and `score` (`null`). Its `kept` holds the kept `error`
and `warn` findings inside the scope, and its `tree` is read before the
rows run.

In code, `report.render_json(..., secret_note="")` renders the full
report and
`report.render_changed_json(run, *, kept=None, tree=None, profile=None)`
renders the `--changed` report.

### Approval ids

`--all-auto` repeats on the new plan, up to five passes, until a pass
changes nothing. `apply --ids` accepts four kinds of id (D12.3). `apply.approvable` gives
this one list, and the Markdown report puts a box on exactly these ids:

| Id | Source | `--all-auto` |
|---|---|---|
| An automatic plan finding, for example `scratch:x.bak` | `plan` | yes |
| `move:<source>` | the move plan (see [Move plan](#move-plan)) | no |
| `repin:<path>:<line>` | the re-pin plan (see [Re-pin plan](#re-pin-plan)) | no |
| `setup:trueup.toml` | the setup opt-in row (see [Setup findings](#setup-findings)) | no |

The Markdown report prints an approval id with a box:

```text
<!-- trueup tree head=1a2b3c4... status=9f8e... -->
- [ ] scratch:x.bak — [ERROR] 'x.bak' looks like a scratch file — git rm x.bak
- [ ] move:HOWTO.md → docs/HOWTO.md (standard: ...)
- [ ] repin:README.md:12 → pin:0a1b2c3d (docs/reference/trueup.md#exit-codes)
```

Line 2 of the report, after `# trueup check`, is the tree comment. A
`check --changed` report has none. Every other finding keeps the line
`- [<LABEL>] <id> — <evidence> — <action>`, with no box.

### Saved plan

`apply --plan FILE` acts on the plan that `check --json` saved in `FILE`
(D12.1). Give it with `--ids` or `--all-auto`:

```sh
python3 trueup check --root DIR --json > /tmp/plan.json
python3 trueup apply --root DIR --plan /tmp/plan.json --all-auto
```

The `tree` key of the file is the identity of the working tree at check
time: `HEAD`, and a hash of `git status` and of the content of each listed
path. `apply` compares it with the tree now. It refuses with exit 2 and
writes nothing when the file is bad, has no `tree` (or `null`), when the tree changed (`trueup: the tree changed since the plan was
saved; run trueup check again`, or `trueup: <path> is inside the root and git does not ignore it, so it changes the tree; keep it outside the root, or under .scratch/ once gitignore:.gitignore is applied` when the plan file itself is
the change), or when `--mode` or `--set` is given. A
second edit of a file that is already modified also changes the tree.

The ids, the move targets and the re-pin values come from the file.
`--all-auto` takes the automatic findings of the saved `plan`. The run
makes one pass and collects no new plan (I-40).

Before the first write, `apply --plan` checks every automatic plan row of
the file on the tree now, with no second collect (D15.27). A row holds
when all of these are true:

- its id is `<rule>:<path>` (a `config` id starts with `config:`);
- its rule is a rule that `apply` handles, and the rule allows `auto`;
- the content test of the rule holds now: `scratch` proves scratch and
  git tracks the file; `artifact` matches the artifact pattern;
  `secret-file` gives the automatic result; `generated` has its marker
  in the first 5 lines; `gitignore` is the path `.gitignore`;
  `file-managed` names a file of the rendered set.

The tests are `findings.AUTO_RULES`, and `findings.auto_row_holds`
applies them. A row that fails gives
`unknown id <id>: the saved row does not hold on the tree now` on
standard error, then `nothing written`, each with the `trueup: ` prefix,
and the exit is 2. This also holds when `--ids` does not name the row.
For `secret-file` on a saved plan, the secret paths are the paths of the
saved `secret-content` findings of the file; the JSON report has no new
key for them.

Keep the plan file outside the root, or under an ignored path. `.scratch/`
is ignored only after you apply `gitignore:.gitignore`. An untracked plan
file inside the root that git does not ignore changes the tree, so `apply`
refuses it with the line that names the file.

`apply --from-report FILE` reads a Markdown report that `check --out`
wrote, after a person ticked boxes (`- [x] ` or `- [X] `). It takes no
`--ids`, `--all-auto` or `--plan`. The tree comment on line 2 must match
the tree now, else `apply` refuses with the same line. A report with no
tree comment (`check --changed`) refuses with
`trueup: the report has no tree comment; save a full check of a git root with trueup check --out, then tick its boxes`. The id of a ticked
line is the text up to the first ` — ` or ` → `. `apply` makes one
collect, validates the ids against the approval ids, and makes one pass.
A path that holds ` — ` cuts its id short; the short id fails
validation, so the run refuses and writes nothing.

### Dirty tree

Before the first write, `apply` compares the paths it touches with the
paths that have uncommitted changes in `git status` (D12.2). The touched
paths are the paths of each selected finding, the source, the target and
each Markdown file whose links a move rewrites, the page of each re-pin,
and `trueup.toml` when the run writes the config. A dirty managed file
that carries the trueup header is trueup's own output and does not
count. When a touched path is dirty, `apply` prints one line for each
path, `trueup: <path> has changes that are not committed`, then `trueup:
commit or stash them, or pass --allow-dirty`, and exits 2 with nothing
written. `--allow-dirty` lets the run go on.

`run_date` in `trueup.toml` changes only when the run changed a file
(D15.27). The `run_date` stamp edits text only; it does not render the
file:

- A top-level `run_date = ...` line (also indented, or with a quoted key)
  changes in place.
- With no such line, `run_date = "<date>"` goes in before the first
  table header, and before the comment and blank lines just above that
  header. A file with no table gets the line at the end.
- Comments and text that is not committed stay. The stamp keeps the line
  ending of the file (CRLF stays CRLF).
- When a parse of the edited text differs from the file in more than
  `run_date` (for example a multi-line `run_date` string), the stamp
  renders the target layer instead. The comments then go, but the file
  stays valid TOML.

The stamp is still no touch for the dirty check: it is not a touched
path (I-41 holds, gate ruling 2026-11-02). A refused stamp prints
`failed run_date: ...`, and the exit is 1.

Config writes (`--mode`, `--set`, `config:*`) still render the whole
file, so a comment does not survive them. The rendered header has a
second line:
`# comments do not survive a config write; trueup writes this file`.

### Writes stay in the root

`apply` writes only below the root (D15.27, I-51). Before each write,
`apply._safe_target` resolves the parent of the path with
`os.path.realpath`. A write whose parent resolves outside the root, or
whose last component is a symlink, is refused with
`refused: <rel> resolves outside the repository`. Each write opens the
file with `os.O_NOFOLLOW`. This holds for `.gitignore`, `.gitattributes`,
managed files, `trueup.toml`, the link rewrite of a move and a re-pin.

A refused write prints the handler line
`failed <id>: refused: <rel> resolves outside the repository`. The other
ids still run, and the exit is 1. A refused stamp prints
`failed run_date: ...`.

### SARIF output

`check --sarif FILE` also writes the findings as one SARIF 2.1.0 run
(D12.4). It goes with `--json`, `--out` and `--changed`, and it does not
change the exit code. A `FILE` inside the root that no `ignore` glob
covers gives exit 2, as for `--out`.

- One result for each finding that is not kept. `ruleId` is the rule.
  `level` is `error`, `warning` or `note` for `error`, `warn` or `info`.
  `message.text` is `<evidence> — <action>`. `partialFingerprints` holds
  `trueupId/v1`, the finding id.
- The location is the path. `region.startLine` is the finding's `line`,
  else the line of a `refcheck:` id, else 1. A repo-wide finding has no
  location.
- `tool.driver.rules` has one entry for each rule, with the most severe
  level of that rule.

No CI step of the CI template uploads the file: CI cannot install
trueup yet (see [Follow-ups](../explanation/field-trial.md#follow-ups)).

### trueup lint

`trueup lint` runs the linters of the rule sets in force (D14.6). The
target holds no lint config of trueup: each config is rendered from the
effective config into a temporary directory for the run, and each tool
gets it through its config flag.

1. The command loads the config layers and surveys the target. A
   present language with no mode in `[languages]` runs as `clean`.
2. It selects the files: each surveyed file at or under each `PATH`;
   with `--changed`, the surveyed files of the working-tree change set;
   else every surveyed file. A path that an `ignore` glob matches is
   dropped. A `PATH` outside the root, or with no surveyed file, prints
   one line and is skipped.
3. It renders the rule-set files of each enabled language into a
   temporary directory, `jscpd.json` when a language is `strict`, the
   Vale style when `docs` resolves to `full` (with `Banned.yml` from the
   banned list in force, I-25), and, in global mode, the checker config.
4. It runs each hook of the enabled rule sets on its files, from the
   root, as pre-commit selects them (`files`, `types_or`, `exclude`). A
   whole-tree hook runs when the selection is the full survey or holds
   a file of its language.
5. It runs the reference checker when the selection is the full survey
   or holds a Markdown page or a source file: the bundled
   `ref_check.py` with the rendered config in global mode, or the
   target's copy at `[refs] path` in copy mode.

A tool that is not installed prints
`trueup lint: <tool> is not installed; <label> did not run`, where
`<label>` names each `<language> <mode>` that needs the tool, and the
run goes on (D15.4). After the run, when a tool is missing, `lint`
prints
`trueup lint: <n> tool(s) missing: a, b; install them, or pass --skip-missing`
and exits 2. A missing tool and a failed tool in one run also give 2.
The function is `lint.run(root, paths, *, changed, install, skip_missing=False)`.
`--skip-missing` (`lint.run(..., skip_missing=True)`) gives the old
behaviour: one skip line for each tool that is not installed in place of
exit 2, and the exit code of the tools that ran. The
run does not run gitleaks: `check` runs it for the secret rows. With
`--changed`, gitleaks scans only the changed files.

jscpd scans the root (D15.5). Its entry is
`{tools}/node_modules/.bin/jscpd --config {cfg}/jscpd.json .`, run from
the root. The `jscpd.json` template has `"gitignore": true` and no
`"path"`, so jscpd scans the root less the paths that `.gitignore`
covers. The sqlfluff entry, in clean and strict mode, is
`{tools}/sqlfluff/bin/sqlfluff lint --config {cfg}/sql/.sqlfluff`.
`{cfg}` is the temporary config directory of the run. `{tools}` is the
tools directory, `$XDG_CACHE_HOME/trueup/tools/<hash>/`
(`lint.tools_dir()`): `<hash>` is the first 16 hex digits of the SHA-256
of the tools manifest (`rulesets.render_tools_manifest()`). In code,
`{tools}` is
`cache_home()/tools/<16 hex of sha256 of rulesets.render_tools_manifest()>`.
The manifest
holds the versions, jscpd `4.3.0` and sqlfluff `4.3.0`
(`rulesets.JSCPD_VERSION`, `rulesets.SQLFLUFF_VERSION`), so a new
version gets a new directory. A plain `lint` never runs `npx` with a
package name (no `npx jscpd`), and never runs `uvx`: a tool that is not in the tools
directory is a missing tool.

eslint, knip and vue-tsc run from the eslint package directory,
`$XDG_CACHE_HOME/trueup/eslint/<hash>/` (`~/.cache/trueup/eslint/<hash>/`
when the variable is unset), one directory for each set of TypeScript
and Vue modes (D14.7). Until `trueup lint --install` has run, eslint
prints `trueup lint: eslint packages are not installed; run trueup lint --install`
and counts as the missing tool `eslint packages`, and `check` gives the
`tool-missing:typescript/node_modules` info row. Each run writes the
eslint config as `run-<pid>.mjs` in that directory and removes it at the
end.

`trueup lint --install` installs the tools that the config needs, and
lints nothing. Every install runs, and the exit code is the first one that is not 0:

- the eslint packages, when TypeScript or Vue is on: it writes the
  package.json of the eslint package directory and runs
  `npm install --prefix <that directory> --no-audit --no-fund`;
- jscpd, when any language is `strict`:
  `npm install --prefix {tools} --no-audit --no-fund jscpd@4.3.0`;
- sqlfluff, when `sql` is not `off`: `uv venv {tools}/sqlfluff`, then
  `uv pip install --python {tools}/sqlfluff sqlfluff==4.3.0`.

With nothing to install, it prints
`trueup lint: TypeScript, Vue, SQL and strict modes are off; nothing to install`
and exits 0. `--install` is the only `lint` path that uses the network
(I-28), and it runs only on request. The eslint package directory and
the tools directory are both part of that second network path (D14.7).

Two files belong to the target, and `lint` passes each only when it
exists under the root (I-47): the eslint suppressions file (`[eslint]
suppressions`, D13.6) and the pydoclint baseline (`[python]
pydoclint_baseline`, D12.8). trueup never writes either file.

### trueup template

`trueup template <name>` prints one text to standard output (D14.9).
Save it where the target wants it; the file is then the target's own,
and no row of `check` compares it with the template. No printed text
holds a trueup header line. With no name, or an unknown name, the
command prints the names and exits 2.

| Name | Text | Usual place |
|---|---|---|
| `pre-commit` | One `repo: local` hook that runs `trueup lint` (see [Moving from the managed lint tree](../how-to/upgrade-trueup.md#moving-from-the-managed-lint-tree)) | `.pre-commit-config.yaml` |
| `editorconfig` | The editor settings that the rule sets assume | `.editorconfig` |
| `ci` | A GitHub Actions workflow with pinned actions (I-32): a comment where the trueup install step goes, a gitleaks install, the step `pip install ruff==0.15.9 vale==3.26.0.1`, a comment that names the install of the other tools (`trueup lint --install` for jscpd, sqlfluff and the eslint packages) and `trueup lint --skip-missing` as the opt-out, `trueup check --root .`, `trueup lint --root .`, and the `osv-scanner` step | `.github/workflows/trueup.yml` |
| `contributing` | A contributing guide | `CONTRIBUTING.md` |
| `security` | A security policy | `SECURITY.md` |
| `code-of-conduct` | A code of conduct | `CODE_OF_CONDUCT.md` |
| `changelog` | A changelog skeleton | `CHANGELOG.md` |
| `issue-template` | An issue template | `.github/ISSUE_TEMPLATE.md` |
| `pr-template` | A pull-request template | `.github/PULL_REQUEST_TEMPLATE.md` |

The action of each health row names its template, for example `write
SECURITY.md; run trueup template security`.

### trueup refs

Every token after `refs` goes to `trueup.ref_check.main` unparsed, so its
own `--help` prints the checker's usage line, not this command's. It
reads the `[keep]` table of the config file, so a kept `refcheck` finding
is not printed, not counted and no reason for exit 1 (D9.2); in global
mode the `ref-check` pre-commit hook runs this command (D9.1). The
checker accepts the flags of `ref_check.REFS_FLAGS`:
`--root --edges --config --help -h` (D15.36).

## Profiles

A profile is a named set of `trueup.toml` keys. A profile holds the
standard; the target file holds only what the target wants different.
So a repository copies nothing but `trueup.toml`. The design of this
round is D14.1 to D14.23 of [ARCHITECTURE.md](../ARCHITECTURE.md); the
profiles are D14.1 to D14.3.

### Search paths

| File | Place |
|---|---|
| Built-in profile | `trueup/data/profiles/<name>.toml` of the trueup install: `house` and `minimal` |
| User profile | `$XDG_CONFIG_HOME/trueup/profiles/<name>.toml` |
| User default file | `$XDG_CONFIG_HOME/trueup/trueup.toml` |

`$XDG_CONFIG_HOME` empty or unset means `~/.config`.

- A name has lower-case letters, digits and hyphens, and starts with a
  letter or a digit. Another name exits 2.
- `house` and `minimal` always read the built-in file. Any other name
  reads only the user profile file.
- A user file `profiles/house.toml` or `profiles/minimal.toml` exits 2
  on every run, with the message `profiles/house.toml shadows the
  built-in profile house; rename it`. So a built-in name gives the same
  rules on every machine (I-46).
- A name that resolves to no file exits 2 on every target, adopted or
  not, and the message names both search paths. trueup never falls back
  to `house` (I-44).

### Precedence

Five layers fill the config, low to high. A higher layer replaces a key
of a lower layer. A list replaces the lower list; `[languages]` merges
per language. A layer that sets `[[eslint.off]]`, or `[eslint] off = []`,
replaces the lower list, with no per-rule merge (D15.29).
`[root] base = "code"` sets the code list again over a lower layer.

| Layer | Source | Read when |
|---|---|---|
| 1 | the defaults in the code | always |
| 2 | the profile file | always |
| 3 | the user default file | only when the target has no `trueup.toml` |
| 4 | the target `trueup.toml` | when it exists |
| 5 | `--profile`, `apply --set`, `apply --mode` | when given |

Two rules read the merged config, after the layers (D15.29):

- `refs.path` needs `refs.mode = "copy"` after the layers merge, so a
  profile can give the mode and the target the path. Else the run exits
  2, and the error starts with the path of the highest layer that sets
  `refs.path` or `refs.mode`.
- A higher `[layout]` switch wins over a lower `[refs] layout`. Checker
  check h and the typed docs target read only the three `[layout]`
  switches. A key check inside one table of one file still runs per
  file: `[refs] layout` cannot stand beside a `[layout]` switch in the
  same file.

The profile resolves on every target, adopted or not (D15.6). A target
is adopted when `<root>/trueup.toml` exists or the user default file
`$XDG_CONFIG_HOME/trueup/trueup.toml` exists
(`config.load_layers(root).adopted`). The profile name comes from the
first of: `--profile`, `TRUEUP_PROFILE`, the `profile` key of the target
file, and the `profile` key of the user default file (only without a
target file). When no layer names a profile, the built-in default is
`house` on an adopted target, and `minimal` on a target that is not
adopted. The JSON `profile.source` names the layer that gave the name:
`--profile`, `TRUEUP_PROFILE`, `target`, `user default` or
`built-in default`.

On a target that is not adopted, every row reads the `minimal` config:
no banned-word `prose` rows, no `refcheck` registry, comment, layout or
README rows (the link rules stay on), and no `agents-missing` or
`claude-not-linked` rows. So a `# NOTE:`, `// A1:` or `H3:` label gives
no `refcheck` row there. With `profile = "house"`, or `--profile house`,
the same label gives `refcheck:<path>:<line>:unregistered`. The setup
rows (`config:trueup.toml`, `setup:trueup.toml`,
`file-managed:trueup.toml`, `gitignore:.gitignore`) and the
`trueup.toml` that `apply` writes do not change: they describe the
adopted target, which runs `house`. `trueup lint` there still exits 2
with `trueup lint: no trueup.toml and no user default file; run trueup check`,
and `trueup refs` there runs the checker with its own defaults.

A target with a `trueup.toml` never reads the user default file, so its
output is the same on every machine that has the same profile (I-44).
A target with no `trueup.toml` and a user default file counts as
adopted: `check`, `lint` and `apply` read the user default file, and no
`config:trueup.toml` row comes. The hooks stay off in that target: they
need the target's own file (I-22). Such a target gives different output
on a machine with another user default file; the profile line of the
report shows which file was read.

### The built-in profiles

`house` is the standard of this repository, and the default on an
adopted target; `minimal` is the default on a target that is not
adopted. The `house` file writes every key at its default value, so it
also lists the keys that a profile can set. With `house` in force,
`check` gives the same findings as before profiles existed, apart from
the changes of this release (I-48). `minimal` keeps the hygiene rows and the link check, and turns
the house rules off:

| Key | `house` | `minimal` |
|---|---|---|
| `docs` | `auto` | `readme` |
| `[layout] front_matter`, `types`, `index` | `true` | `false` |
| `[prose] banned` | `builtin` | `off` |
| `[refs] registry`, `comments` | `true` | `false` |
| `[refs] links` | `true` | `true` |
| `[health] agents` | `true` | `false` |
| `[health] files` | `tier` | `readme` |
| `[scratch] gitignore` | `true` | `false` |

Each other key has the same value in both.

`house.toml` shows `[[eslint.off]]` as a commented example, because the
key has no entry by default. Its header no longer says that it applies
when no layer names a profile: on a target that is not adopted,
`minimal` applies (see [Precedence](#precedence)).

### Write a profile

1. Make the directory `$XDG_CONFIG_HOME/trueup/profiles/`.
2. Write `<name>.toml` there, with the keys that differ from the code
   defaults. The keys and their values are those of
   [trueup.toml](#trueuptoml), less `version`, `run_date`, `[[keep]]`
   and `profile`: a profile that sets one of them exits 2. A profile
   cannot name another profile. Copy the lines of `minimal.toml` that
   you need.
3. Select it: `profile = "<name>"` in the target's `trueup.toml`
   (`apply --set profile=<name>` writes the line), or `--profile <name>`
   for one run, or `profile = "<name>"` in the user default file for
   each target that has no `trueup.toml`.
4. Run `check` and read the profile line of the report.

For example, a profile that keeps the house standard, but bans only the
project's own words and keeps the pages in `doc/`:

```toml
[layout]
docs_dir = "doc"

[prose]
banned = "off"
extra = ["frobnicate"]
```

A `[prose] banned` path in a user profile is relative to `profiles/`.

A committed `profile` key that names a user profile works only on a
machine that has the file. In CI and on another machine, the run exits
2 and names the two paths. For a shared repository, use a built-in
profile, or set the keys in `trueup.toml` itself.

## trueup.toml

`trueup` keeps one file, `trueup.toml`, at the target's root. A person can
edit it; `trueup apply` also writes it. The file is one of five config
layers (see [Profiles](#profiles)): a key that the file does not set
comes from the profile in force, and the defaults below are the values
of the built-in `house` profile. `apply` writes the keys that the file
already holds, the keys that it sets, and each value that differs from
the default; it never copies a value of a profile into the file (I-45).

Since D14.8, a target in global mode holds no `ref_check.toml` and no
eslint config of trueup. Where a row below says that `apply` renders a
key into the managed `ref_check.toml` (`ignore`, `[refs] local_tags`,
`[refs] law_archive`, `[refs] layout`, `[[keep]]`), `check`, `trueup lint` and `trueup refs`
render the key into the checker config of each run (D14.5); only in
copy mode does the managed `ref_check.toml` hold it, with its
`file-managed` row. Where a row says that `apply` renders a key into
`lint/typescript/eslint.config.mjs` (`[[eslint.off]]`), `trueup lint`
renders it into the eslint config of each run, and no `file-managed`
row comes. For the pre-commit hooks and the gitleaks allowlist of the
`ignore` row: `trueup lint` drops an ignored path from its selection,
and the gitleaks config that `check` renders holds the globs. A
`[refs] layout` that the file sets is written back, also when it is
`true`; it sets the three `[layout]` switches, and it cannot stand
beside them (D14.2).

| Key | Values | Meaning |
|---|---|---|
| `version` | `1` | The config schema version. |
| `run_date` | `YYYY-MM-DD`, or empty | The date of the last `apply` that changed a file. `run_date` must be empty or an ISO date; another value exits 2 with `run_date must be a date as YYYY-MM-DD` (D15.29). `apply` edits only this line (see [Dirty tree](#dirty-tree)). |
| `profile` | A profile name: lower-case letters, digits and hyphens; default absent (`house` on an adopted target, see [Precedence](#precedence)) | The profile whose keys fill the keys that this file does not set (see [Profiles](#profiles)). `TRUEUP_PROFILE` and `--profile` win over it. A name that resolves to no profile file exits 2. |
| `tier` | `auto`, `T0`, `T1`, `T2`, `T3` | `auto` picks the tier from the survey; any other value overrides the pick. |
| `public` | `true`, `false` | `true` makes a licence required at tier T0, makes `SECURITY.md` required at every tier, adds the other public-only health files (C2 and a code of conduct) at tier T2 and up, and adds the three `platform:*` info rows (see [Security floor](#security-floor)). `public = false` written in the target's own `trueup.toml` also drops the `health-license` row at every tier, and the checker config of the run gets `[checks] licence = false`, which turns off the checker rule `no-licence-file` and the `no-section` failure for a missing `License` section (D15.14). An unset `public` keeps the licence rows. `config.public_is_false(cfg, root)` gives this answer; when `cfg.explicit` is `None` (the effective config), it reads the target layer of `root`. |
| `docs` | `auto`, `full`, `readme`; default `auto` | `auto` gives `readme` at T0 and T1 and `full` at T2 and T3; `trueup.toml` keeps the word `auto` (D12.9). `full` runs every document rule; `readme` turns off the changelog shape check, the page-status checks, the Vale style, and the `layout`/`readme` switches of `ref_check.toml`. The `ref_check.py` fold-in runs in both modes. |
| `stale_days` | A positive integer, default 180 | How old a `status: current` page's `last_reviewed` may get before P8 reports it. |
| `ignore` | A list of glob patterns | Left out of the survey and every finding. `apply` renders the globs into the managed `ref_check.toml` as `[scan] ignore`, so the `ref-check` hook and `trueup refs` skip the same paths as `check`, which reads the rendered text from the first run (I-2). A changed `ignore` list therefore gives a `file-managed:ref_check.toml` finding; apply it. Below the tier where `ref_check.toml` is managed, the checker runs with no config, so the globs do not reach `refcheck` there. `apply` also adds each glob to the `exclude` pattern of each pre-commit hook that gets the file names (ruff, eslint, Vale, shellcheck and the like), and to the gitleaks allowlist, so the hooks skip the same paths. A hook that scans the whole tree (`pass_filenames: false`) reads its own tool config instead. |
| `protect` | A list of glob patterns | `apply` never writes or removes a path these match; the matching finding turns manual. No move has a protected source or target, or one under a protected directory; a directory that holds a protected file never moves as one unit; a move never rewrites the links of a protected file. A `doc-misplaced` finding on a protected page stays in the plan: add a `[[keep]]` entry for a page that stays. |
| `[root] allow` | A list of names or globs | Extra names the guard hook allows at the target's root, beyond the base list. Its length also widens the `root-budget` row's numeric budget by the same count. A root page that one of them names is not a `doc-misplaced` candidate; the same name in a subdirectory still is (D10.2). |
| `[scratch] allow` | A list of globs | Paths the `scratch` row and the guard hook let through whatever the name looks like. A glob matches the repo-relative path or the basename, for example `docs/notes.md` or `notes-*.md`. |
| `[scratch] gitignore` | `true`, `false`; default `true` | `true` gives the `gitignore:.gitignore` row when `.gitignore` lacks the `.scratch/` line. `false` turns the row off. |
| `[root] base` | A list of names or globs, or `"code"`; default absent | Replaces the base list of root names that the guard hook allows (see [Hooks](#hooks)). `[root] allow` still adds to it. Absent, the code list is in force (D14.11). `[root] base = "code"` sets the code list again over a lower layer (D15.29). |
| `[guard] registry` | `true`, `false`; default `false` | `true` turns on the install guard of the `PreToolUse` hook: it looks up each package name that a `Bash` install command names on its public registry (see [Hooks](#hooks)). `false` gives no lookup, so no hook opens a network connection (D15.32). |
| `[guard] private_packages` | A list of package-name globs; default `[]` | Names that the install guard never looks up, for example `corp-*` or `@corp/*`. A glob matches the whole name, case-sensitive (D15.32). |
| `[layout] code_dirs` | A list of directory names with no `/`; default empty | Directories of Markdown-as-code. A Markdown file under one of them is not a `doc-misplaced` page. The list adds to the default segments `agents`, `claude`, `prompts`, `rules`, `skills` and `templates` (D13.1). |
| `[layout] docs_dir` | One directory name of letters, digits, `_`, `.` and `-`, not `.` or `..`; default `docs` | The directory of the documentation pages. The document rows, the locator, the health places, the scratch exemption of a `-v<n>` page and the checker read it (D14.4). The index is `<docs_dir>/README.md` and the design is `<docs_dir>/ARCHITECTURE.md`. |
| `[layout] front_matter` | `true`, `false`; default `true` | `false` turns off the checker rules `no-front-matter`, `bad-field` and `duplicate-id`. |
| `[layout] types` | `true`, `false`; default `true` | `false` turns off the checker rule `misplaced`, and a move target is `<docs_dir>/<name>`, with no type directory. |
| `[layout] index` | `true`, `false`; default `true` | `false` turns off the checker rules `unindexed` and `no-index-link`. |
| `[binary] allow` | A list of globs; default empty | Files the `binary` and `large-text` rows let through, for example review screenshots kept on purpose. A glob matches the repo-relative path or the basename (D13.2, D15.11). |
| `[prose] banned` | `builtin`, `off`, or the path of a file; default `builtin` | The banned list of the `prose` row and of the Vale style. `builtin` is `trueup/data/banned.txt`; `off` is no list. A path is relative to the directory of the file that sets it, and the file has the `banned.txt` form: one entry for each line that is not blank, `word` or `word => <regex>`. A missing file exits 2. |
| `[prose] extra` | A list of entries in the `banned.txt` form; default empty | Entries added after the entries of the list. With `banned = "off"` they are the whole list. An empty list in force turns the `prose` row off (I-25). |
| `[refs] mode` | `global`, `copy`; default `global` | Where `trueup lint` and a `ref-check` hook find the checker (D9.1). In global mode the target holds no copy and no `ref_check.toml`: `trueup lint` runs the bundled checker, and `trueup refs` renders the checker config into a temporary directory (D14.5). `trueup` must be on the path of each machine that commits: `uv tool install --editable <plugin root>`, or `pipx install <plugin root>`. `check` reports `tool-missing:refs/trueup` while it is absent, and `refs-copy:ref_check.py` while an old copy sits at the root. In copy mode `apply` writes the bundled checker at `[refs] path` and the managed `ref_check.toml`, and the copy runs as `python3 <path> --root .` with no install. Copy mode is for this repository (its copy is the source), and for a repository whose CI or another machine cannot install trueup. `apply` writes the key to `trueup.toml` when the file sets it, also at `global`, and when it is `copy` (D14.3). |
| `[refs] path` | A relative path, no `..` or `.` part, no backslash, ending in `.py`; default `ref_check.py`; copy mode only | Where `apply` writes the reference checker module in the target. `trueup lint` runs the copy at this path. The `ruff-format` hook leaves out `ref_check.py` at the root. `apply` writes the key to `trueup.toml` when the file sets it, also at the default, and when it is not the default (D14.3). `refs.path` needs `refs.mode = "copy"` after the layers merge: a profile can give the mode, and the target the path (D15.29). Else the key is a configuration error (exit 2), and the error starts with the path of the highest layer that sets `refs.path` or `refs.mode`. |
| `[refs] registry` | `true`, `false`; default `true` | `false` turns off check e of the checker: a marker word outside the closed registry (D2.2) is not a failure. |
| `[refs] comments` | `true`, `false`; default `true` | `false` turns off check f of the checker: the suppression reason and the file header (D2.9). |
| `[refs] links` | `true`, `false`; default `true` | `false` turns off check g of the checker: the document link rules (D2.10). |
| `[refs] declared` | A list of paths or globs relative to the root; a `..` segment is allowed, and an absolute path is an error; default empty | The pages that declare the design ids for checks a and c of the checker (D16.2). A glob expands with `glob.glob(recursive=True)`, sorted. When this key or `[refs] id_forms` is set, the checker uses the configured reader (see [How the checker reads a file](#how-the-checker-reads-a-file)). With `id_forms` alone, the one page is `<docs_dir>/ARCHITECTURE.md`. A literal path that does not exist, or a glob that matches no file, gives one `no-target` failure for the entry, and the run exits 1 (I-56). The checker config holds the key as `[targets.arch] sources`, at every tier. A profile does not set it. |
| `[refs] id_forms` | A list of at most 16 forms of at most 24 characters each, with no white space and no comma; default empty | The forms of a design id (D16.2), for example `["D<n>.<m>", "D<n>.<m>.<k>", "D-<n>", "I-<n>"]`. A lower-case name in angle brackets means one or more digits, and each other character is literal. A form holds one placeholder or more and one literal character or more. A placeholder cannot come just before a digit or another placeholder. No regular expression comes from the target, so a target cannot make the checker backtrack. With `declared` alone, the forms are `D<n>.<m>` and `I-<n>`. The checker config holds the key as `[targets.arch] forms`. A profile does not set it. |
| `[refs] accepted_reader_changes` | A list of change names with no white space and no comma; default empty | The reader changes that fail now, not warn (D16.3). Until the target names a change here, a failure that the change adds is a warning (see [How the checker reads a file](#how-the-checker-reads-a-file)). The checker config holds the key as `[targets.arch] accepted`. This key alone does not turn on the configured reader. A profile does not set it. |
| `[eslint] suppressions` | A repo path; default `lint/typescript/eslint-suppressions.json` | The eslint bulk suppressions file of the target (D13.6). `trueup lint` passes it with `--suppressions-location` only when the file exists. |
| `[python] pydoclint_baseline` | A repo path; default `lint/python/pydoclint-baseline.txt` | The pydoclint baseline of the target (D12.8). `trueup lint` passes it with `--baseline` only when the file exists. |
| `[health] agents` | `true`, `false`; default `true` | `false` turns off the `agents-missing` and `claude-not-linked` rows. |
| `[health] files` | `tier`, `readme`; default `tier` | Which health files are required. `tier` uses the tier table (see [Tier and health](#tier-and-health)). `readme` requires `README.md` only: `health-readme` is the one health file row. The `minimal` profile sets `readme` (D15.14). Another value exits 2. |
| `[refs] local_tags` | A list of uppercase prefixes, for example `["X", "G"]`; default empty | The project's own comment-tag prefixes (`// X1:`, `// G2:`). `apply` renders them into the managed `ref_check.toml` as `[registry] local_tags`, and `check` runs the checker with them from the first run, so the checker's rule R1 does not report them as `unregistered` (D8.7). A prefix followed by digits counts as the same tag. `apply` writes the key to `trueup.toml` when the file sets it, also as an empty list, and when it is not empty (D14.3). |
| `[refs] law_archive` | A non-empty string: a path relative to the root, or absolute; default absent | The law archive of the `law` references (see [Law references](#law-references)). `apply` renders it into the managed `ref_check.toml` as `[targets.law] archive`, and `check`, `trueup lint` and `trueup refs` give it to the checker at every tier (D16.13). Absent, each `law` reference fails with `no-target`. Another value exits 2, and the message names `refs.law_archive`. `apply` writes the key to `trueup.toml` only when it is set. Do not write `[targets.law]` into `ref_check.toml` by hand: a hand edit is a `file-managed:ref_check.toml` finding, and the next `apply` removes it (D2.5). |
| `[refs] layout` | `true`, `false`; default `true` | `false` turns check h of the checker off: `apply` renders `[checks] layout = false` into `ref_check.toml`, and `check` runs with it from the first run (D9.4). No page under `docs/` then gets a `no-front-matter`, `bad-field`, `misplaced`, `unindexed` or `duplicate-id` finding, also a page added later. For pages that keep fixed paths the project's own tools read, or a page a tool regenerates. One `[[keep]]` entry per page is the narrower choice: it keeps the rule for new pages. `apply` writes the key to `trueup.toml` when the file sets it, also at `true`, and when it is `false` (D14.3). A higher `[layout]` switch wins over a lower `[refs] layout`; checker check h and the typed docs target read only the `[layout]` switches (D15.29). |
| `[languages]` | One key per language, value `strict`, `clean` or `off` | The mode of each of the eight languages: `python`, `rust`, `typescript`, `vue`, `shell`, `sql`, `go`, `php`. |
| `[[eslint.off]]` | `rule`, `reason`; default none | One entry per eslint rule that is off for this repository, for a rule that flags normal code in bulk. `rule` is an eslint rule name, for example `security/detect-object-injection` (letters, digits, `@`, `_`, `.`, `-` and `/`). `reason` is one line and not empty. A missing key, an extra key, a bad name, an empty reason, a line break in it or a repeated rule exits 2. `apply` renders the entries into the managed `lint/typescript/eslint.config.mjs` as a last config object that sets each rule to `"off"`, with the reason as a comment on its line; `check` reports `file-managed:lint/typescript/eslint.config.mjs` until it is applied. eslint accepts `"off"` for a name it does not know, so a misspelt rule stays on. No effect while TypeScript and Vue are `off` (D13.5). A layer that sets `[[eslint.off]]`, or `[eslint] off = []`, replaces the lower list; there is no per-rule merge (D15.29). |
| `[[keep]]` | `id`, `reason` | One entry per finding a person declined, with the reason. A keep id keeps the finding with that id, and each finding whose id starts with the keep id and `:` (see [Ids, lines and keeps](#ids-lines-and-keeps)). A kept id never rejoins the plan. A keep that matches no finding gives a `keep-stale` info row. A kept `doc-misplaced:<path>` id keeps a page where it is: the page gets no move, and a directory that holds it never moves as one unit (D10.6). A kept `refcheck:` id also goes into the `[keep]` table of the managed `ref_check.toml`, prefix removed, so the `ref-check` hook and `trueup refs` keep it too; after a new entry, `apply` the `file-managed:ref_check.toml` finding, else the hook still fails on that line (D9.2). |

`config.KEYS` is the sorted tuple of every dotted key that a config
layer can set: each key of the table above as `<table>.<key>` (for
example `layout.docs_dir`, `guard.registry` and
`guard.private_packages`), plus `profile`, `languages` and `eslint.off`
(D15.36). The skill drift test checks each key that the skill names
against it.

## Findings

Every finding has an id (`<rule>:<path>` in most rows; a repo-wide finding
has an empty path, so its id ends in `:`), a category, a severity (`error`,
`warn` or `info`), the evidence, the action, and whether `apply` can carry
it out with no prose judgement (`auto`). The plan is every `error` and
`warn` finding that no `[[keep]]` id matches (see
[Ids, lines and keeps](#ids-lines-and-keeps)); an `info` finding never
joins the plan.

### Ids, lines and keeps

A finding id does not change when the line of the finding moves (D15.8).

- `secret-content:<path>:<fp>` and `changelog:<path>:<fp>`: `fp` is the
  first 12 hex digits of `sha256(path + "\0" + stripped line)`
  (`findings.line_fingerprint`). trueup computes it for both secret
  engines; for gitleaks it reads line `StartLine` of the tracked file. A
  line that it cannot read (a read error, a symlink, a line past the end)
  gives `<rule>:<StartLine>` in place of `fp`. The `changelog` fingerprint
  is the one of the defect line, line 1 for a missing `## [Unreleased]`
  heading. Equal ids in one file add `:2`, `:3` in file order
  (`findings.number_repeats`).
- `refcheck:` and `secret-history:` ids keep their line.
- Each finding has a `line` (`Finding.line`, default `0`): the 1-based
  line that it points at, or `0` when it points at no single line. The
  rows that set it are `secret-content` (both engines), `secret-history`,
  `changelog` and `refcheck`. `Finding` has the last field `line: int = 0`.
- The id and keep helpers are in `trueup.findings`:
  `keep_match(finding_id, keep)`, `stale_keeps(findings, keep)`,
  `line_fingerprint(path, line)` and `number_repeats(ids)`.

A keep id `k` keeps the finding id `k` and each finding id that starts
with `k:` (`findings.keep_match`). An exact match comes first, else the
longest such prefix. The match stops at a `:` boundary, so `prose:docs/a`
does not keep `prose:docs/abc.md`. For example:

- `refcheck:docs/a.md` keeps every checker row of the page;
- `doc-misplaced` keeps every misplaced page in place;
- `prose` keeps every banned-word row;
- `secret-content:app.py` keeps every secret line of a file.

The same rule applies to the plan, the `Kept` section and JSON `kept`,
SARIF, the `doc-misplaced` move locator, and the checker:
`ref_check.py` matches its `[keep] failures` entries the same way
(`ref_check.keep_match`, a copy of the function), so
`refcheck:docs/a.md` renders `failures = ["docs/a.md"]` and the hook
command keeps the page too.

| Rule | Detects | Severity | Auto |
|---|---|---|---|
| `keep-stale` | A `[[keep]]` id that matches no finding, of any severity (`findings.stale_keeps`). Id `keep-stale:<keep id>`, category `setup`, path `trueup.toml`, line 0. The evidence is `keeps nothing`; the action is `remove the [[keep]] entry or fix its id`. Only a full run gives it: `check`, `check --baseline`, `baseline` and `apply`. `check --changed` gives none. As an `info` row it never joins the plan, so it does not change the exit code. | info | no |

### The slop and security rows

Every row runs on the surveyed files: what `git ls-files --cached --others
--exclude-standard` lists (tracked files and untracked files that git does
not ignore), minus the `ignore` globs.

The rows read file content through one bounded reader, `trueup/fsread.py`
(D15.22, I-50): `read_capped(root, rel, max_bytes)`,
`read_text_capped(root, rel, max_bytes)` and `read_head(root, rel, n)`.
A read gives no content for a path that `lstat` cannot see, a device,
FIFO or socket, a symlink whose target is outside the root or is not a
regular file, and, for the two capped reads, a file longer than the cap.
So no content read of trueup follows a symlink out of the root, opens a
device or FIFO, or reads more than its cap (I-50).

The content reads below go through `fsread`. A text read
has a 1 MiB cap; a head read (`read_head`) reads only the first bytes:

- survey: the line counter and the workspace check. A file over the cap
  counts as a file with 0 lines.
- hygiene: the hash, the `generated` marker, the lockfile manifests, the
  link index, the reference index and `.gitattributes`, and the
  `secret-file`, `secret-content` and `binary` rows.
- layout: the page text, the generated marker and the agent head.
- drift: the manifests, the docs, the sources and the `Makefile`.
- docrules: the prose row, the README length, the changelog rows, the
  page rows and the re-pin reads (D16.10). A symlink out of the root
  gives no text.
- baseline: the `.py` files of the docstring ratchet. The coverage
  reports and the baseline file are outputs, not surveyed files. They
  have a 64 MiB cap, so a large report does not read as absent. A
  symlink out of the root reads as absent, as it does for every other
  read.
- apply: the two reads of `_move_rewrites` and `_dirty_conflicts`. A
  page over the cap, and a symlink to a regular file out of the root,
  stop the move with `refused: <rel> ...`: the run cannot see the links
  of the page. A device, a FIFO and a page that does not decode get no
  rewrite and do not stop the move.
- health: the `## Contributing` heading and the `CLAUDE.md` link.
- managed: the header reads, the setup-file compare and `.gitignore`.

A file over the cap gives no text to the row. A file that the hash
cannot read leaves the `duplicate` group. The gitleaks copy (see
[Secret engine](#secret-engine)) skips a symlink whose target is outside
the root.

The checker `ref_check.py` ships as one file and cannot import `fsread`
(decision 14). Its own reader has the same rules and a 16 MiB cap
(D16.10). A device, a FIFO, a file over the cap and a symlink out of the
root each give one `unreadable` row.

Two subprocess readers do not use `fsread`. Each has its own guard
(D16.10):

- `changes._blob_shas` gives `git hash-object --stdin-paths` only a
  regular file that is not a symlink (`os.lstat`). A listed symlink gets
  the blob sha of its link text, as git stores a symlink, so a new link
  target still changes the tree identity. A FIFO, a device or a socket
  gets the fixed value `""` and is never opened. The identity of a
  regular file does not change. The identity of a tree that lists a
  symlink does change, so a plan saved over such a tree before round 16
  gives exit 2 one time (see [Saved plan](#saved-plan)).
- The `tokei` call has a time limit of 60 s (`survey.TOKEI_TIMEOUT_S`),
  because tokei opens `.gitignore` during its walk, and a `.gitignore`
  symlink to a FIFO stops it. On expiry the survey uses the built-in
  line counter, as when tokei is not installed, and prints one line on
  standard error: `trueup: tokei did not end in 60 s; the survey uses
  the built-in line counter`. The counts never become a silent zero.

| Rule | Detects | Severity | Auto |
|---|---|---|---|
| `scratch` | A scratch-looking path that no other surveyed text file refers to. A name is scratch when it is a `*.bak`, `*.orig`, `*.rej`, `*.swp`, `*~`, `* copy.*` or `Copy of *` name; when a suffix after its first `.` is `.old`, `.bak`, `.orig` or `.backup` (`README.old.md`, `x.bak.py`); when its stem is `tmp`, `temp`, `scratch`, `notes` or `untitled`, alone or followed by digits or by `-`, `_` or a space, and its last extension is none, `.txt`, `.md`, `.log`, `.tmp`, `.out` or `.old`; when its stem is `scratch` or `untitled` followed by digits, or by `-`, `_` or a space and more text, at any extension (`scratch_fold.rs`); or when its last extension is one of that document list or `.rst` and its stem ends in a `_` or `-` followed by `v<n>`, `draft`, `copy`, `old` or `backup`, or ends in ` copy` or ` copy <n>` (`ARCHITECTURE_v2_draft.md`); or when its stem is exactly `draft`, with optional digits, and its last extension is in the document list (`draft.md`, not `draft-rfc.md`). A path whose first segment is `tmp`, `temp` or `scratch` is scratch whatever the name. So `tmp-draft.md` and `notes.md` count; `template.py`, `temp_table.sql`, `notes.py`, `notes_service.py`, `tmp_file.rs` and `v0_v1.rs` do not. A `.keep` or `.gitkeep` file is never scratch. Under `<docs_dir>/`, at any depth, a `-v<n>` or `_v<n>` suffix on a document name is a versioned page, not scratch; `check` and the guard hook share this test (`hygiene.under_docs_dir`, D15.9). A file is exempt when another surveyed text file holds its path relative to that file's own directory (a link, or `rm tmp_notes.txt` in a root `Makefile` for a root file), or holds its full path when the path has a `/`. A bare basename in a file of another directory does not exempt it. Nothing under `.scratch/`, no secret-file name, and nothing `ignore`, `[root] allow` (at the root) or `[scratch] allow` names. When a kept file has the same content, the evidence adds `copy of <original>`. A path that `artifact` flags (`tmp/out.pyc`) gets no `scratch` finding: the `artifact` remedy covers it (D10.3). | error | yes, `git rm`, only when git tracks the file, its name proves scratch, and no directory segment is `vendor`, `third_party` or `node_modules` (D15.9). A name proves scratch when it is `*.bak`, `*.orig`, `*.rej` or `*~`, or when its stem is exactly `notes`, `tmp`, `temp`, `scratch`, `draft` or `untitled`, with optional digits, and its last extension is none, `.txt`, `.md`, `.log`, `.tmp`, `.out` or `.old` (`hygiene.scratch_proven`). Every other tracked candidate is manual, with the action ``check the file; if it is scratch, `git rm <path>`; else rename it or add a [scratch] allow glob``: for example `docs/notes-2024.md`, `temp-sensors.md`, `scratch_buffer.rs`, `CHANGELOG-v2.md`, `README.old.md`, `* copy.*` and `*.swp`. No when git does not track the file: delete it by hand or move it under `.scratch/`, since `apply` never deletes a file git cannot restore. No for one copy when no other tracked copy of the content stays (the others are scratch or build output): the evidence is `the last copy of this content`, so the automatic ids of one plan never remove every copy. Each pass of `apply --all-auto` collects a new plan, and a later pass can see the last copy as a scratch file with no copy and remove it: examine the scratch copies before `--all-auto` (I-35) |
| `artifact` | A build or cache directory (`__pycache__`, `node_modules`, `.pytest_cache`, `.mypy_cache`, an `.egg-info`, `target/` beside `Cargo.toml`, `dist/` or `build/` beside a root `Cargo.toml`, `pyproject.toml`, `package.json`, `go.mod` or `composer.json`), one finding for the top-most such directory, id ending in `/`; or a `.pyc`/`.pyo`/`.class`/`.o` file, or `.DS_Store`, outside one. | error | yes, untrack (`git rm --cached -r` for a directory) and one `.gitignore` line, which `apply` leaves out when a line already covers the path (`git check-ignore --no-index`). No when the directory holds a tracked `*.md` page that could be a `doc-misplaced` candidate: the evidence adds `holds <page>`; move the page out, and the next `check` gives the automatic id. A package `README.md`, or a page under `node_modules`, `vendor`, `third_party` or a dot segment, does not count (D10.4) |
| `duplicate` | The same SHA-256 as another surveyed file, 256 bytes or more (`_DUPLICATE_MIN_SIZE`, D15.12). One finding per later path in a group, unless every path in the group sits under a `fixtures/`, `testdata/` or `__snapshots__/` directory, which gives no finding (it is test data kept on purpose). A path that `scratch` or `artifact` flags leaves the group first: that row already removes it. A group whose every remaining member another surveyed text file refers to, by the reference rule of the `scratch` row, gives no finding: each copy is in use. When a path and the first path of its group have the same basename and the same number of segments, and differ in exactly one directory segment, the evidence is `same content as <original>; the paths differ in one directory segment`, and the action is `if these are variants on purpose, add a [[keep]] entry with the reason; else keep one`. The id and the severity do not change (D16.6). | warn | no |
| `doc-misplaced` | A Markdown page (`.md` or `.markdown`) outside `docs/`, one finding for each page, also when its move takes a whole directory (`trueup/layout.py`). Not a candidate: a path with a `docs` segment at any depth; a standard root page at the root (`README`, `CHANGELOG`, `CONTRIBUTING`, `LICENSE`, `SECURITY`, `CODE_OF_CONDUCT`, `AGENTS`, `CLAUDE`, `SUPPORT`, `ACCESSIBILITY` or `pull_request_template` with `.md`, in any case, so `README.old.md` is not one); a page in the root `PULL_REQUEST_TEMPLATE/` directory (GitHub reads these pages there, see [GitHub community health files](#github-community-health-files)); a `README.md`, `CHANGELOG.md` or `SKILL.md` at any depth; a root file that a `[root] allow` glob names; a path with a segment that starts with `.`, or that is `fixtures`, `testdata`, `__snapshots__`, `vendor`, `third_party` or `node_modules`; a path with a directory segment that is `agents`, `claude`, `prompts`, `rules`, `skills`, `templates` or a `[layout] code_dirs` name; a file whose front matter has `name` and `description` and no `type` (an agent or skill definition, D13.1); and a path that `scratch` flags, so each path has one remedy. Then the locator drops a candidate that a move would break, so it gets no finding and no move (D15.13): a page with a directory segment `change_log`, `changelog`, `locale`, `content` or `_templates`; a page whose first 5 lines hold `auto-generated`, `autogenerated`, `generated by`, `code generated`, `@generated` or `do not edit`, in any case; a page whose directory, or the parent of that directory when the parent has two or more segments, the text of a surveyed file that is not Markdown names with a trailing `/` (`docs/site/` in a build script); and each page of a content tree, a top-level directory with more than 20 candidate pages, which gives one `doc-tree` row in their place. The `artifact` row still reads the candidate rule before this step. It runs with each `docs` value and each `[refs] layout` value. Category `files`. The evidence starts with `Markdown page outside docs/`, then names the move and its target, or says why there is none: `protected`, `a [[keep]] entry keeps it in place` (only in the `## Kept` section of the Markdown report), `target <target> exists, move it by hand`, `target <target> is claimed by more than one page`, `the page is not tracked; git add it, then run trueup check again` (an untracked page gets no move, D15.27), or, in a scoped run, `the move plan comes from a full check` (see [Move plan](#move-plan)). | warn | no; approve the `move:` id that the action names, or add a `[[keep]]` entry for a page that stays |
| `doc-tree` | A content tree: a top-level directory outside `<docs_dir>/` with more than 20 `doc-misplaced` candidate pages after the other locator drops (D15.13). One row per tree, id `doc-tree:<dir>/`, path `<dir>/`, category `files`, in place of a `doc-misplaced` row for each page. The evidence is `holds <n> pages; trueup does not move a content tree`; the action is `none; the pages stay outside <docs_dir>/`. | info | no |
| `generated` | A `Code generated ... DO NOT EDIT` or `@generated` marker in the first 5 lines, with no matching `.gitattributes` line, and not a lockfile. | warn | yes, add the `.gitattributes` line |
| `secret-file` | A basename that looks like a key or environment file: `.env`, `.env.*` (except a name that ends `.example`, `.sample`, `.template` or `.dist`), `*.pem`, `*.key`, `*.p12`, `*.pfx`, or `id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519`. The content decides the result, which is one of three (D15.10, I-49). A key name: trueup reads the first 64 bytes through `fsread.read_head`. A private PEM banner (after leading white space, `-----BEGIN ` with `PRIVATE KEY-----` on the first line) or a PKCS#12 head (byte `0x30` and the PKCS#7 data OID) gives the automatic row. A public PEM banner on the first line (`CERTIFICATE`, `X509 CRL`, `PUBLIC KEY`, `CERTIFICATE REQUEST`) gives no row. Any other head gives the manual row: a certificate after a label line, a Keynote `.key`, a DER key, a file it cannot read. An `.env` name: automatic only when a `secret-content` finding of this run, from either engine, names the path; else manual. The built-in scan reads `.env` files for this. No byte of either file goes into a finding, a log or the JSON. The evidence is `'<name>' looks like a secret or key file`. | error | yes for the automatic row: untrack and `.gitignore`, with no line when one already covers the path; the action is `untrack the file and add it to .gitignore; rotate the secret, the history still holds it`. No for the manual row. The action for a key name is `check whether the file holds a private key; if it does, untrack it, add it to .gitignore and rotate the key`; for an `.env` name it is `check whether the file holds a secret; if it does not, add a [[keep]] entry`. A manual row does not tell the owner to rotate a secret that trueup has not proven; the key action says "rotate" only for a file that does hold a private key |
| `secret-content` | A private-key block, an AWS access key id, a GitHub token or a Slack token, inside another text file under 1 MiB. The built-in scan also reads an `.env` file, so its path can prove the `secret-file` row; it never reads a key-named file (D15.10). A `BEGIN ... PRIVATE KEY` banner counts only when one of the next 3 lines, stripped, is 40 or more base64 characters, so a documentation placeholder such as `<paste private.pem contents>` after the banner does not match. One finding for each line: two secrets on one line give one finding, and its evidence names every pattern or rule, `<path>:<line> matches <name>, <name>` (built-in names such as `an AWS access key id`, `a Slack token`, `a private key block`; gitleaks rule ids such as `aws-access-token`). The evidence never holds the matched text. Id `secret-content:<path>:<fp>` (see [Ids, lines and keeps](#ids-lines-and-keeps)). When `gitleaks` is on the path, gitleaks gives this row with the same id shape, and the built-in patterns do not run (see [Security floor](#security-floor)). | error | no |
| `secret-history` | A secret that gitleaks finds in any commit of the git history. Only `trueup baseline` and `check --baseline` scan the history, and only when `gitleaks` is on the path. Id `secret-history:<fingerprint>`; the evidence names the file, the line, the gitleaks rule and the commit, never the secret. | error | no; rotate the secret, a history rewrite is the owner's decision |
| `secret-engine` | gitleaks is on the path and its run failed: a timeout, a start failure, a non-zero exit or a report that is not a JSON list (D15.20). One repo-wide row, id `secret-engine:`, category `security`, empty path. The evidence is the note of the failure, the text of `secret_note` (for example `gitleaks failed: exit 2`). The action is `rerun the check, or fix the gitleaks run; the built-in engine ran instead`. The built-in `secret-content` rows still run. A scoped run (`check --changed`) keeps the row. The row is in the plan, so `check` exits 1 and the `security` category of the score is full. | error | no |
| `lockfile` | A tracked manifest that declares dependencies and has no tracked lockfile of its ecosystem in its own directory or an ancestor directory (see [Security floor](#security-floor)). Id `lockfile:<manifest>`. The manifest `lint/typescript/package.json` with the `"_managed": "trueup"` marker gives no finding: an earlier trueup wrote it for the tools of the eslint hook (D8.3), and since D14.8 it is a `managed-legacy` path that gets an info row only. | error | no; the action names the lock command of the ecosystem |
| `binary` | A file with a NUL byte in its first 8 KiB, with no `filter=lfs` in `.gitattributes`: any file over 1 MiB is sniffed at every tier, and a file over 100 KiB is sniffed at T3 only (D13.2, D15.11). The sniff reads through `fsread.read_head`. A file over 1 MiB with no NUL byte there gets `large-text` instead. Not flagged: a file that a Markdown file of the survey links to by relative path (evidence, not residue), a file that a `[binary] allow` glob names, and a secret-named file (the `secret-file` row covers it, and I-49 bars a longer read). The evidence is `<path> is <n> bytes`. | warn | no; move the file to Git LFS, add it to `.gitignore`, link it from the page it supports, or add a `[binary] allow` glob |
| `large-text` | A file over 1 MiB with no NUL byte in its first 8 KiB, with no `filter=lfs` in `.gitattributes` (D15.11). Category `files`. The evidence is `<path> is <n> bytes of text`; the action is `none needed; add a [binary] allow glob to silence it`. The `binary` exemptions apply: a linked file, a `[binary] allow` glob and a secret-named file get no row. | info | no |
| `root-budget` | More root entries than the tier's budget (T0 8, T1 15, T2 25, T3 35) plus `[root] allow`. An entry that holds only files that trueup writes (`trueup.toml`, `ref_check.toml`, `.trueup-baseline.json`, `ref_check.py`) does not count. An old managed path (`lint/`, `.editorconfig`, `.pre-commit-config.yaml`, `.github/workflows/trueup.yml`, `.claude/rules/trueup.md`) is the person's file since D14.8 and counts (D15.37). One repo-wide finding. | warn | no |

### Tier and health

`trueup` picks a tier the same way every time: T3 for a workspace, three or
more manifests, or ten or more contributors; T0 for five or fewer language
files with no manifest and no CI; T1 for fifty or fewer files with two or
fewer contributors and no tag; T2 otherwise. A `tier` value in
`trueup.toml` overrides the pick. The pick counts no file that trueup
writes (`survey.TRUEUP_OWN_PATHS`: `trueup.toml`, `ref_check.toml`,
`.trueup-baseline.json` and `ref_check.py`), so `apply` never changes
the tier (I-43). The paths of the old managed tree (`lint/`,
`.editorconfig`, `.pre-commit-config.yaml`,
`.github/workflows/trueup.yml`, `.claude/rules/trueup.md`) left that
list on 2026-11-02 (D15.37): trueup no longer writes them, so they are
the person's files and count for the tier, the root budget and CI. So
an adopter of an earlier trueup can change tier (a T0 tree can reach
T2). A workflow at
`.github/workflows/trueup.yml` counts as CI. A CI file is any of
`.github/workflows/*.yml` or `*.yaml`, `.gitlab-ci.yml`,
`.circleci/config.yml`, `Jenkinsfile`, `.travis.yml`,
`azure-pipelines.yml`, `bitbucket-pipelines.yml`, `.woodpecker.yml`,
`.woodpecker/*.yml`, `.drone.yml`, `.forgejo/workflows/*`,
`.gitea/workflows/*` and `.buildkite/pipeline.yml`. The language files
of the pick also count the extensions of other common languages, such
as Java, C, C++, C#, Ruby and Swift, and a manifest is also `pom.xml`,
`build.gradle`, `Gemfile`, `CMakeLists.txt` and the like (D14.13).

Tier: a manifest counts for the tier only at the root or one level down,
and not under `tests`, `test`, `fixtures`, `testdata`, `__snapshots__` or
`examples` (D15.26). So `pkg/pyproject.toml` counts, and
`a/b/pyproject.toml` and `examples/pyproject.toml` do not. The survey
`manifests` list keeps every path.

Survey JSON key `other_languages`: language family to
`present, no rule set`, for files outside the eight languages (`java`,
`kotlin`, `c`, `cpp`, `scala`, `groovy` and more), for example
`{"java": "present, no rule set"}`. Their files count for the tier, and
no rule set covers them. The `languages` table keeps the eight.

| Item | T0 | T1 | T2 | T3 |
|---|---|---|---|---|
| `README.md`, `.gitignore` | required | required | required | required |
| A licence file | when `public` | required | required | required |
| `.editorconfig`: no row since D14.8; `trueup template editorconfig` prints one, and `apply` no longer writes it | — | — | — | — |
| `CHANGELOG.md` | — | once tagged | once tagged | required |
| A contributing guide (R8) | — | — | required | required |
| `SECURITY.md` (C1) | when `public` | when `public` | when `public` | when `public` |
| A code of conduct | — | — | when `public` | when `public` |
| An issue template and a PR template (C2) | — | — | when `public` | when `public` |
| `CODEOWNERS` | — | — | — | required |

An item required only at the next tier gives an `info` finding, not an
error. All health items are manual prose: `apply` writes none of them,
and the action of each names its template.

Each item has its own rule, and each row is repo-wide, with the id
`<rule>:` and an empty path. Category `health`; the severity is `error`
for a required item and `info` for an item of the next tier; no row is
automatic. The evidence is `none of <candidates> is present` or
`required at <tier>, not at <tier>`.

| Item | Rule |
|---|---|
| `README.md` | `health-readme` |
| `.gitignore` | `health-gitignore` |
| A licence file | `health-license` |
| A changelog | `health-changelog` |
| A contributing guide | `health-contributing` |
| `SECURITY.md` | `health-security` |
| A code of conduct | `health-code-of-conduct` |
| An issue template | `health-issue-template` |
| A PR template | `health-pr-template` |
| `CODEOWNERS` | `health-codeowners` |

Each health candidate matches in any case, in each part of its path
(D15.14). So `readme.md` satisfies `health-readme`. A licence file is a
root file named `LICENSE`, `LICENCE` or `COPYING`, in any case and with
any extension; `health.py` and the checker share this test
(`ref_check.licence_present(root)`). A changelog is `CHANGELOG.md`,
`CHANGES.md` or `<docs_dir>/CHANGELOG.md`. A contributing guide is
`CONTRIBUTING.md`, `CONTRIBUTING.rst`, `.github/CONTRIBUTING.md` or
`<docs_dir>/CONTRIBUTING.md`, or a `## Contributing` section of the
README. `public = false` in the target's `trueup.toml` drops the licence
item at every tier; an unset `public` keeps it.
`[health] files = "tier" | "readme"` picks the list: `tier`, the
default, uses the tier table, and `readme` drops every item but
`README.md`.

`health.required_item_count(tier, public, tags, agents=, files=, licence=)`
counts the required items for the slop score; the keyword
arguments say whether the agent rows count (not at T0), which `[health]
files` is in force, and whether the licence item counts. `score.py`
does not pass the keyword arguments of
`required_item_count(..., agents=, files=, licence=)` yet, so the score
still counts the tier table alone.

#### GitHub community health files

GitHub reads these files at these places. The health rows count a file at
each place in this table, and the `doc-misplaced` row gives no finding for
a page at a place in this table. The `docs/` and `.github/` places are
never `doc-misplaced` candidates. Where a file can be at more than one
place, GitHub uses the first that it finds: `.github/`, then the root,
then `docs/`. GitHub reads file names in any case. Research date:
2026-10-16.

| File | Places that GitHub reads | Health row | Source |
|---|---|---|---|
| `CONTRIBUTING.md` | `.github/`, root, `docs/` | `health-contributing` | [Setting guidelines for repository contributors](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors) |
| `CODE_OF_CONDUCT.md` | `.github/`, root, `docs/` | `health-code-of-conduct` | [Adding a code of conduct to your project](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/adding-a-code-of-conduct-to-your-project) |
| `SECURITY.md` | `.github/`, root, `docs/` | `health-security` | [Creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file) |
| `SUPPORT.md` | `.github/`, root, `docs/` | none | [Adding support resources to your project](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/adding-support-resources-to-your-project) |
| `ACCESSIBILITY.md` | `.github/`, root, `docs/` | none | [Creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file) |
| `CODEOWNERS` | `.github/`, root, `docs/` | `health-codeowners` | [About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) |
| Pull request template: `pull_request_template.*` (`.md`, `.txt`), or any file in a `PULL_REQUEST_TEMPLATE/` directory | `.github/`, root, `docs/` | `health-pr-template` | [Creating a pull request template](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository) |
| Issue templates: `*.md`, issue forms `*.yml`, and the chooser `config.yml` (not a template) | `.github/ISSUE_TEMPLATE/` only; the health row also takes the older single file `.github/ISSUE_TEMPLATE.md` | `health-issue-template` | [About issue and pull request templates](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates) |
| `FUNDING.yml` | `.github/` only | none | [Displaying a sponsor button](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/displaying-a-sponsor-button-in-your-repository) |
| `VULNERABILITY_REPORT.yml` | `.github/` only | none | [Creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file) |
| Discussion category forms | `.github/DISCUSSION_TEMPLATE/` only | none | [Creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file) |

GitHub does not read `GOVERNANCE.md` (it is not in GitHub's list), so a
root `GOVERNANCE.md` is a `doc-misplaced` candidate. A licence file has
no default: GitHub reads it only in the repository itself. The guard's
base list of root names does not hold the health names, so the guard
denies a new root health file until `[root] allow` names it; `.github/`
is a place that GitHub reads first, so write a new health file there.

#### Managed set by tier

Each managed file has a minimum tier (D12.9). A check above the tier is
never a failure: no finding asks for a managed file above the tier, and
no finding asks to remove a managed file (I-42).

Since D14.8 the managed set is `trueup.toml` and, in copy mode, the
checker pair. Every lint config is rendered at run time by `trueup
lint`, and every other file that trueup managed before is a template
(see [trueup template](#trueup-template)).

| Managed path | Minimum tier |
|---|---|
| `trueup.toml` | T1, or present on disk |
| copy-mode checker (`[refs] path`) | any tier, when `[refs] mode = "copy"` |
| `ref_check.toml` | when `[refs] mode = "copy"`: T2; T1 when the survey holds a Markdown page under `<docs_dir>/` |

A file below its minimum tier stays managed when its file on disk is
trueup's: it carries the managed header, or, for `trueup.toml`, it
exists. A T0 repository with no `trueup.toml` gets no setup file.

From tier T1, `trueup` also checks, read-only (C4): `AGENTS.md` is on
disk, and, when `CLAUDE.md` exists, it is either a symlink to `AGENTS.md`
or names it with `@AGENTS.md`. Each failed check gives a `warn` finding. A
missing `CLAUDE.md` gives no finding. `[health] agents = false` turns
both checks off. `trueup` never writes `AGENTS.md` or `CLAUDE.md`.

When `public` is `true`, at every tier, `trueup` also adds three manual
`platform:*` findings, category `security`, severity `info` (D15.15). An
`info` row never joins the plan, so a tidy public tree has an empty plan
and `check` exits 0. They name settings of the hosting platform that
`trueup` cannot read. The
[Security floor](#security-floor) section lists them.

### Document rules

The README length check, the banned-word floor and `refcheck` run for
`docs = "full"` and `docs = "readme"` alike. The other three rules run
only for `full`. With `docs = "auto"`, the mode in force is `readme` at T0
and T1 and `full` at T2 and T3.

| Rule | Checks | Notes |
|---|---|---|
| `readme-length` (R10) | `README.md` over 200 lines. | warn, manual: split the page |
| `prose` (W1) | A banned word or phrase from `trueup/data/banned.txt`, case-free, whole word, in Markdown prose or in a source comment of the eight languages. A `banned.txt` line is either a bare word or `word => <regex>`; a form entry bans only the shape after `=>` (`leverage` and `underscore` as verbs, `unlock` in its hype sense), so the same word used as a noun stays silent (D6.9, D8.5). The built-in list has no `harness` entry: decision 11 of D15 took it out of `banned.txt` and out of the Vale `Banned.yml` (D15.16, I-25), so `harness` in any use gives no row, and the two files stay equal line for line. A Markdown block that quotes the list gives no finding: a list item with its indented lines (nested items and a loose continuation included), or a paragraph with the lines up to a blank line (a list it introduces included), whose first three lines hold a cue (`banned`, `never use`, `do not use`, `don't use`, `forbidden`, `prohibited` or `not allowed`); a heading, quote or table row is neutral. The Vale template holds the same rule as `BlockIgnores`, proven on one table of twenty-one shapes, and a source comment keeps the plain rule (D8.4). In the Markdown report of a full `check`, a finding whose evidence names 10 or more distinct banned words also gets one hint line, `hint: this file may quote the list on purpose; add a [[keep]] entry with a reason`. | error, manual, one finding per file |
| `changelog` (C6) | `CHANGELOG.md`, when present: an `## [Unreleased]` heading, `## [x.y.z] - YYYY-MM-DD` versions in descending order, and `### <type>` headings only from Added, Changed, Deprecated, Removed, Fixed, Security. | error per defect, manual; id `changelog:<path>:<fp>` (see [Ids, lines and keeps](#ids-lines-and-keeps)); `docs = "full"` only |
| `refs-reader-change` | One line `ref_check: <n> warnings from reader change <name>; ...` in the output of the `refcheck` run (D16.3, see [How the checker reads a file](#how-the-checker-reads-a-file)). One finding for each change: id `refs-reader-change:<name>`, evidence `<n> warnings from reader change <name>`, action `fix the markers, or add <name> to [refs] accepted_reader_changes in trueup.toml to fail on them`. | info, manual; changes no exit code |
| `superseded` (P7) | A `status: superseded` page under `docs/` with no `superseded_by`, or one naming an id no page under `docs/` declares. | error, manual; `docs = "full"` only |
| `stale` (P8) | A `status: current` page under `docs/` whose `last_reviewed` is older than `stale_days`. | error, manual; `docs = "full"` only |
| `refcheck` | One run of the bundled `ref_check.py` against the target, from the target's root; the target's own copy never runs. The run reads the `ref_check.toml` that `apply` would write for the config in force (every switch on for `full`, `layout` and `readme` off for `readme`, plus `[refs] local_tags` and the `ignore` globs as `[scan] ignore`), from a file outside the target, so the row before the first `apply` equals the row after it (D8.1). When `ref_check.toml` is not in the tier set, the run uses no config file, as the hook does: every switch off, checks a to d on, and no `[scan] ignore` (D12.9). With `[scan] ignore`, no check reads a file that a glob matches, so an ignored path gets no `refcheck` finding in `check` and no failure in the hook (I-2). The checker does not enter a directory with its own `.git` entry, a submodule or a nested clone (D8.2). One finding per failure line, id `refcheck:` plus the checker's failure id `<path>:<line>:<kind>`; where lines share that id, the text after the detail's last `: ` is added (`refcheck:README.md:1:no-section:Install`), then `:1`, `:2` if ids still repeat (D9.2). The run leaves the `[keep]` table out, so a kept finding is still listed under `Kept`. A `broken-link` line comes from check g: the path part of a local link ends at the first `?` or `#`, so a query string such as `sim.html?preset=a` resolves as `sim.html` (D2.10). `[refs] layout = false` turns check h off (D9.4). The action of an `unregistered` line names `[refs] local_tags`. A `stale-pin` line with one clear fix also gets a `repin:` id (see [Re-pin plan](#re-pin-plan)). When the checker exits 2 (its own error, not a failure of the target), the row gives one `refcheck-run:` finding in place of its rows: rule `refcheck-run`, category `docs`, severity `error`, manual, with the last line of the checker's standard error as the evidence. An exit 1 with no failure line that parses still gives one `refcheck:` finding. The checker run has a limit of 120 seconds (D15.23). After that time, the row gives one `refcheck-run:` finding with the evidence `ref_check.py timed out after 120 s`. | error, manual; both docs modes |

### How the checker reads a file

The checker runs nine checks, a to i. These rules decide what checks f,
g, h and i read (D15.18, D15.19, D15.30). They add no command, flag,
exit code, rule id or JSON key. The rules for design ids and reader
changes at the end of this section add the three `[refs]` keys of round
16 and the `refs-reader-change` info row (D16.2, D16.3).

Each read of a target file has the limits of I-50 (D16.10). A device, a
FIFO, a file over 16 MiB and a symlink out of the root each give one
`unreadable` failure. A path below a directory that the run cannot read
gives no exception on Python 3.11 to 3.14, so an unreadable docs
directory gives `no-target` (D16.1).

Markdown, for check g (`links`), for every reader of
`_md_lines_outside_fences`, and for the link rewrite of `apply`:

- A fenced block opens with 3 or more backticks or tildes. Only a line of
  the same character, at least as long, with no text after it, closes
  it. So a line of three backticks and `bash`, inside a block that three
  backticks opened, does not close the block.
- A line with an indent of 4 columns or more (a tab is 4) after a blank line, outside a list, opens an indented code block. The block holds the next lines that are blank or have that indent. Its links and headings are not read.
- A code span is a run of backticks, its text, and the same run. So a
  span that two backticks open holds a single backtick and ends at the
  next two backticks.
- A link target can hold one level of balanced parentheses
  (`[x](file_(x).md)`). `\[x\](y.md)` is not a link.
- `[^1]: text` is a footnote, not a reference definition.
- A link target that starts with a placeholder `${NAME}` (a letter or
  `_`, then letters, digits or `_`) is not checked, in an inline link
  and in a reference definition (D16.4). The rule reads the raw target,
  before percent decoding. A placeholder that is not at the start
  (`docs/${X}/missing.md`), `.$name.md`, and a link with no placeholder
  on a `.tmpl.md` page still give `broken-link`.
- A target that starts with `/` resolves from the root
  (`[x](/docs/page.md)`). `/../x.md` leaves the root and is broken.
- Anchors: a setext heading (a text line over a `===` or `---` line)
  gives a slug. Each heading also gives the slug of its text with the
  HTML entities decoded: `## Fish &amp; Chips` gives `#fish--chips`, and
  `#fish-amp-chips` still resolves.

The root README, for check i (`readme`):

- Blank lines and HTML blocks can come before the H1. An HTML block starts with a line whose first text is `<` and ends at a blank line; one that starts with `<!--` ends at `-->`. An `<h1>` inside the block is the title. The title block, and so the badge block, starts at the H1 line.
- Other text before the H1 still gives `no-title` (`line 1 is not a
  title`).
- `Quick Start`, `Quickstart` and `Getting Started` count as the
  `Install` section, as `Installation` does.
- `no-index-link` applies only when `<docs_dir>/README.md` exists.
- `no-licence-file` fails when the root has no licence file
  (`ref_check.licence_present`); its detail is
  `no LICENSE, LICENCE or COPYING file at the root`. The checker key
  `[checks] licence` (a bool,
  default `true`) turns off `no-licence-file` and the `no-section`
  failure for `License`. `render_ref_check_config` writes
  `licence = false` only when the target's `trueup.toml` sets
  `public = false`.

Front matter, for check h (`layout`) and the other readers of the one
parser, `ref_check._front_matter`:

- `key:` with no value, followed by `  - item` lines, is a list. Check h
  reads it as `[item, item]`, so `audience:` followed by `  - maintainer`
  passes. A bad item gives `value is not allowed: audience: [robot]` on
  the key line.
- One pair of matching quotes around a scalar or an item is removed (`id: "page"` reads `page`). Unmatched quotes stay.
- `trueup.docrules` (P7 `superseded`, P8 `stale`) and `trueup.layout`
  (the `type` field of the `doc-misplaced` standard target, and the
  agent definition test) read front matter with
  `ref_check._front_matter`. `layout` reads `type` only from a valid,
  closed block.
- A docs page is a path that `ref_check.is_doc_page(rel, docs_dir)`
  accepts. docrules applies it to `survey.files`, so a page below a
  `SKIP_DIRS` segment (`node_modules`, `vendor`, `graphify-out`,
  `site-packages`, `target`, `venv`) is not a docrules page.

Marker readers and check f (`comments`):

- Shell: a heredoc body and its closing line are no marker position and
  no suppression position. `<<WORD`, `<<'WORD'`, `<<"WORD"` and
  `<<-WORD` open one; `<<-WORD` closes on a line of tabs and `WORD`. An
  opening with no closing line opens none (`$((1 << 2))`). `<<<` and a
  whole-line comment open none.
- Rust: a `///` or `//!` line is a marker position with the docstring
  rules, as a Python docstring is: R2 applies, and the R1 tags (`NOTE:`)
  do not. A `//` line stays a comment. `////` is a plain comment.

Design ids, for checks a and c (D16.2):

- With none of `[refs] declared`, `[refs] id_forms` and
  `[refs] accepted_reader_changes` set, the checker reads
  `<docs_dir>/ARCHITECTURE.md` with the patterns of D2.8, and gives the
  rows of the release before round 16 (I-54).
- With `declared` or `id_forms` set, the configured reader reads each
  source. On a line outside a fenced block, the id is the first token
  of one of these shapes: a heading of any level (`## D18.2 Wire
  protocol`), the first cell of a table row, with or without bold, or
  the bold lead of a list item or a paragraph (`- **D9.3** ...`). A
  mention anywhere else does not declare. An id that two sources
  declare is declared.
- A source must be a regular file of at most 16 MiB. A symlink source is
  followed, because the target names the page. A directory, a FIFO, a
  file over the cap and a file that is not UTF-8 each give one
  `unreadable` failure at that source.
- A missing source gives one `no-target` failure for each entry, at
  `<entry>` line 1: `declared source not found: <entry>; <n> citations
  not checked`. `<n>` is the count of the whole run, the same on each
  row. While a source is missing, check a gives no `unknown-id`
  failure, because it cannot decide (I-56).
- With every source found, an id that no source declares gives one
  `unknown-id` failure for each citation (I-55).
- Check c reads `## Verification` of each source that holds the
  section, with the same id forms. A failure names the source as the
  entry wrote it (I-57).
- When no source holds `## Verification`, check c has no claims and
  gives no failure. A page that holds the claims must be a source.
- The SessionStart design-id line names the pages of `[refs] declared`
  when the key is set.

Reader changes (D16.3):

- A release that widens what the checker reads registers the change in
  `ref_check.READER_CHANGES` for that one release. The table is empty in
  this release. The Rust reader of D15.19 is not registered: a target
  with no new config behaves as before.
- A failure from a marker at a position that a registered change
  matches is a warning, unless the target names the change in
  `[refs] accepted_reader_changes`. The checker prints the failure line
  as `warning: <failure line>`, then one line for each change:
  `ref_check: <n> warnings from reader change <name>; add it to [refs]
  accepted_reader_changes to fail on them`. A warning does not change
  the exit code (I-58).
- `trueup check` gives one `refs-reader-change:<name>` info row for each
  change, with the count (see [Document rules](#document-rules)).
- In the next release the change leaves the table, and its failures
  count.

### Law references

A `law` reference points at one section of one version of a law
document in a law archive (D1.3, D2.7). Set the archive with
`[refs] law_archive` in `trueup.toml` (D16.13).

A marker has one of two forms (D2.1):

- `law: <doc-type>/<slug>/<version> s.<section>`, for example
  `law: acts/Income_Tax_Act/v13 s.111`.
- `ref: law/<doc-type>/<slug>/<version>/s.<section>`, for example
  `ref: law/acts/Income_Tax_Act/v13/s.111`.

`<doc-type>` is lower-case letters and `_`. `<slug>` is letters, digits
and `_`. `<version>` is `base` or `v<N>`. `<section>` is digits, then
zero or more upper-case letters.

The checker reads this archive shape and nothing else:

```text
<archive>/<doc-type>/<slug>/<version>/document.md
```

- A section heading is a line that starts with `### <section>. `. The
  checker compares the number as exact text. When a number repeats, the
  first heading is the section.
- The section text starts at its heading. It ends before the next
  heading of level 1 to 3, or at the end of the file.
- Check a: a missing pinned `document.md`, or no heading for the
  section, gives `unknown-id`. A file that the checker cannot read gives
  `unreadable`. With no archive set, each `law` reference gives
  `no-target` with `target law is not configured: <id>`.
- The order of versions is `base` first, then `v<N>` by the integer
  `N`. The newest version is the last directory in that order that
  holds a `document.md`.
- Check d compares the pinned version with the newest version (D4.2).
  When the pin is the newest version, or the section text is the same,
  it reports nothing. A section that the newest version does not hold
  gives `unknown-id` with `section absent in <version>: <id>`. A changed
  section gives `drift` with `section text changed in <version>: <id>`.
- The checker compares the SHA-256 of each section text after it
  changes each run of white space to one space and removes the white
  space at the two ends. So a new line wrap is not a change. The checker
  calculates the hash itself and reads no hash from the archive.
- To repair a `drift` row, read the new text, correct the code if
  necessary, then change the pin to the new version. The checker never
  changes a pin (I-8).

### Re-pin plan

A `refcheck` finding with the detail `pinned section changed: <target>`
means that the section a pinned link names has changed (D12.6). When
the line holds exactly one Markdown link with that target and a pin, and
the target section exists, `check` proposes a re-pin with the id
`repin:<path>:<line>`. Else the finding stays manual. A re-pin is not a
finding, and the `refcheck` id does not change.

The Markdown report prints `## Re-pin plan (n)` with one box line for
each entry, `- [ ] <repin id> → pin:<new> (<target>)`. The JSON report
holds `repins`, a list sorted by id; each entry has `id`, `path`, `line`,
`target`, `old_pin` and `new_pin`.

`apply --ids repin:<path>:<line>` reads the line again. When exactly one
link with the target and `pin:<old_pin>` is there, it replaces the old
pin with the new pin in that line only. Else that id fails with exit 1
and a reason. `--all-auto` never takes a `repin:` id.

### Docs drift rows

Four rules compare `README.md` and the tracked `docs/**/*.md` pages against
the code, regardless of the `docs` setting. Every row reads only files
already on disk; none runs a target command or looks up a tool on the path
(I-18, I-21). The static flag set of a command comes from `ast.parse` of the
project's own `.py` files outside `tests/` (`.add_argument(` calls and
`@click.option`), a regex on Go's `.Flags()`/`.PersistentFlags()` calls and
on the standard `flag` package (`flag.Bool`, `String`, `Int`, `Int64`,
`Uint`, `Uint64`, `Float64` and `Duration`, and each `...Var` form), or
Rust's `#[arg(long = "x")]` and `.long("x")`; a command with no flags found
gives no `drift-flag` row, since the rule never guesses (D15.17). A
`.py` file is one command `python3 <path>`; `python3 <pkg>` names only the
flags of `<pkg>/__main__.py`, when `<pkg>/__init__.py` exists. A Cargo
`[workspace]` root gives one command for each member (the `members`
globs, matched with `fnmatch` over the surveyed `*/Cargo.toml` files)
that has `src/main.rs` or a `[[bin]]` table; its flags come from that
member's `.rs` files only. A root `[package]` still gives one command
that reads every `.rs` file. `drift` and `baseline` parse a `.py` file
with `ast.parse(text, filename=...)` inside
`warnings.catch_warnings()` with `SyntaxWarning` ignored, so a target's
bad escape sequence prints nothing. A doc's fenced
code block counts when its info string is `sh`, `bash`, `shell`, `console`,
`fish`, or empty.

| Rule | Severity | Id | Fires when |
|---|---|---|---|
| `drift-flag` | warn | `drift-flag:<doc>:<flag>` | A doc line runs a known project command with a `--flag` the command's own parser does not define. |
| `drift-undocumented` | info | `drift-undocumented:<src>:<flag>` | A flag the code defines appears in no doc. |
| `drift-package` | warn | `drift-package:README.md` | The README's install section has install lines (`pip install`, `npm install`, `cargo install`, `go install <module>@<version>`, `go install .`, `go install ./...`, `go get` and similar), and none names this project's own manifest or `.`. The own names are the `name` of `pyproject.toml`, `package.json`, `Cargo.toml` or `composer.json`, and the `module` path of `go.mod`. A Go line also names the project with `./...`, or with the module path or a path below it (`<module>/cmd/<name>`), the `@<version>` removed. A URL names the project when its last path segment, with `@<ref>`, `#<fragment>` and `.git` removed, is one of the own names (`pip install git+https://host/owner/<name>@v1`). |
| `drift-command` | warn, or info | `drift-command:<doc>:<token>` | A doc's shell code block runs a path git does not track, an `npm run <script>` with no such script, or a `make <target>` with no such target. A missing path is `info`, not `warn`, when git ignores it (a build output that `.gitignore` names), or when the `Makefile` text or a `package.json` `scripts` value names it (D15.17). An `npm run` or `make` defect stays `warn`. |

All four rows are category `docs`, manual (`auto=False`).

The drift module runs no process. For the ignored paths,
`report.collect` takes the missing path tokens from
`drift.missing_command_paths(survey)`, runs one
`git check-ignore --no-index --stdin -z` for them, and passes the set
as the `ignored` argument of
`drift_findings(survey, only, ignored=frozenset())`. When that git call
fails, the set is empty, so no row turns `info` by an error.

A fifth rule, `drift-manifest` (category `docs`, severity `info`,
manual), gives one row `drift-manifest:<manifest>` when a key that the
drift rows read is not a table: `project` or `project.scripts` in
`pyproject.toml`, or `package` in `Cargo.toml`. The evidence is
`manifest not readable: <key> is not a table`; the action is
`fix the manifest so the drift rows can read it`. The reader skips that
manifest. A scoped
`check --changed` run narrows the files these rows read to the changed set,
except `drift-command`'s check for whether a candidate path is tracked,
which always tests the full survey.

### Setup findings

`managed.py` compares what it would render against the files on disk.

| Rule | When | Severity | Auto |
|---|---|---|---|
| `setup` | T0 or T1, `trueup.toml` is absent, and no user default file exists. One row, id `setup:trueup.toml`, in place of the `config` and `tool-missing` rows. The evidence is `<n> setup files: <paths>`; the action is `run trueup apply --ids setup:trueup.toml to write them`. No row when the tier set is empty (T0). | info | yes, by its id only; `--all-auto` never takes it. `apply --ids setup:trueup.toml` writes `trueup.toml`, the one file of the tier set at T0 and T1 since D14.8 |
| `config` | `trueup.toml` is absent and no user default file exists (T2 and up), or a present language has no mode. Under a user default file, no `config:trueup.toml` row comes. | error (or `info` for a language below the present line count) | yes for the error case |
| `file-managed` | A managed file of the tier set (see [Managed set by tier](#managed-set-by-tier)) is absent, or differs and still carries the managed header. Blank lines and comment lines do not count as a difference. | error | yes |
| `file-managed` | A managed file differs and carries no managed header. | error | no; `trueup` never overwrites an unmanaged file |
| `file-managed` | Copy mode: the module at `[refs] path` is not byte-equal to the copy `trueup` ships, and its first line is the trueup header (a copy an earlier trueup wrote, D9.3). | error | yes |
| `file-managed` | Copy mode: the module at `[refs] path` is not byte-equal to the copy `trueup` ships, and has no trueup header (a person's own file, or a copy from before 2026-10-07). | warn | no; an unedited copy from an earlier trueup: `git rm` it, then `apply` the absent-copy error that follows; else merge by hand |
| `refs-copy` | Global mode: a file sits at `ref_check.py` of the root, and nothing runs it (D9.1). | info | no; `git rm ref_check.py` when it is trueup's old copy |
| `gitignore` | `.gitignore` lacks a line `trueup` needs (`.scratch/`), and `[scratch] gitignore` is `true`. | error | yes |
| `managed-legacy` | A file of the old managed lint tree that an earlier trueup wrote: a `LEGACY_PATHS` path (see [Moving from the managed lint tree](../how-to/upgrade-trueup.md#moving-from-the-managed-lint-tree)), or a file under `lint/` whose first line is the managed header or whose JSON holds `"_managed": "trueup"`. A file with no such mark is the target's own and gets no row. The action is `trueup no longer manages this file; remove it when you have moved to trueup lint (see the reference page)`. | info | no; the row informs, it never asks (I-42) |
| `tool-missing` | An enabled rule set, or the Vale style, needs a tool that is not on the path. With TypeScript or Vue on and no `node_modules` in the eslint package directory, `tool-missing:typescript/node_modules` names `run trueup lint --install`; it uses the network, so `check` never runs it (D14.7). In global mode with no `trueup` on the path, `tool-missing:refs/trueup` names the one-time install that the pre-commit entry and `trueup refs` need (D9.1). | info | no |

The `gitignore` row and every other row stay beside the `setup` row. After
the opt-in, `trueup.toml` exists, and the next `check` gives one
`file-managed` row for each file of the tier set that does not match: in
copy mode, the checker pair. A
target with its own `.pre-commit-config.yaml`, CI workflow or
`.editorconfig` gets no row for it.

### Agent rules file

Since D14.10 trueup writes no agent rules file. The `SessionStart` hook
prints the rules of the effective config at the start of each session
(see [Hooks](#hooks)): Simplified Technical English (under the profile
`house` only), the page types under
`<docs_dir>/` when `[layout] types` is on, the comment marker registry
when `[refs] comments` is on, design-id citations when `[refs] registry`
is on, the root rule, the scratch rule, the managed-file rule, and a
`trueup check` before the agent finishes. An old
`.claude/rules/trueup.md` that an earlier trueup wrote gets a
`managed-legacy` info row. There is no Codex rule.

## Security floor

The security floor is the set of rows, managed files and hooks that look
for a security defect. The table maps each one to a control of the Open
Source Project Security Baseline (OSPS Baseline), version v2026.08.28.
That version was the current version on <https://baseline.openssf.org> on
2026-10-04. A row with no Level 1 control says `none at Level 1` and
names the level of the nearest control, when one exists.

| Row | What it checks | OSPS Baseline Level 1 control |
|---|---|---|
| `lockfile` | A manifest that declares dependencies has a tracked lockfile. | OSPS-QA-02.01 (a dependency list for the direct dependencies; a lockfile also pins the indirect dependencies) |
| `secret-file` | No tracked key or environment file, by file name; the first 64 bytes of a key name, or the secret scan of an `.env` file, decide whether the row is automatic (I-49). | OSPS-BR-07.01 |
| `secret-content` | No secret pattern in a tracked text file: gitleaks when it is on the path, else the built-in patterns. | OSPS-BR-07.01 |
| `secret-history` | No secret in a commit of the git history (gitleaks only). | OSPS-BR-07.01 |
| CI action pins | Each `uses:` line of the CI template (`trueup template ci`) ends in `@<40 hex> # <tag>`. | none at Level 1; no level names action pins. The `permissions: contents: read` line of the same workflow meets OSPS-AC-04.01 (Level 2). |
| `osv-scanner` step | The CI template scans the dependencies for known vulnerabilities when a lockfile is tracked. | none at Level 1; OSPS-VM-05.03 (Level 3) |
| SAST rule sets | The clean rule sets add ruff `S`, `eslint-plugin-security` and `gosec` (through golangci-lint). | none at Level 1; OSPS-VM-06.02 (Level 3) |
| `health-security` | A `SECURITY.md` at every tier when `public` is `true`. | OSPS-VM-02.01 |
| install guard | With `[guard] registry = true`, the `PreToolUse` hook checks each package that a `Bash` install command names against its registry. It is off by default (D15.32). | none at Level 1; OSPS-VM-05.03 (Level 3) names malicious dependencies |
| `platform:branch-protection` | A pull request and one review on the default branch, no force push, no deletion. Manual. | OSPS-AC-03.01 and OSPS-AC-03.02; the review is OSPS-QA-07.01 (Level 3) |
| `platform:mfa` | Two-factor authentication is required for the organization. Manual. | OSPS-AC-01.01 |
| `platform:least-privilege` | No collaborator has more access than the work needs. Manual. | OSPS-AC-02.01 |

### Gaps

On 2026-11-03 this machine had `gitleaks` on the path, and did not have
`osv-scanner`, `gosec` as a standalone tool, or `semgrep`. So these
parts are not verified here:

- gitleaks: most tests use a fake `gitleaks` script that writes a known
  report. The three tests of a real gitleaks run in
  `tests/test_secrets.py` ran and passed on 2026-11-03; on a machine
  with no gitleaks they skip and name the tool. No lint hook runs
  gitleaks: `check` runs it for the secret rows.
- osv-scanner: a test checks the rendered CI step. No test runs the
  scanner.
- gosec: the Go test runs `golangci-lint` with its `gosec` linter. No test
  runs the standalone `gosec` tool.
- semgrep: no rule set uses it.

The CI pins and the gitleaks archive checksum are the values of
2026-10-04. The three `platform:*` rows are manual: `trueup` cannot read
the platform settings, and it never runs `gh` (I-31).

### Lockfile pairs

The `lockfile` row reads one table, `_LOCK_PAIRS` in `trueup/hygiene.py`:

| Manifest | Lockfile names |
|---|---|
| `Cargo.toml` | `Cargo.lock` |
| `pyproject.toml` | `uv.lock`, `poetry.lock`, `pdm.lock`, `pylock.toml`, `pylock.<name>.toml` |
| `Pipfile` | `Pipfile.lock` |
| `package.json` | `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lock`, `bun.lockb` |
| `go.mod` | `go.sum` |
| `composer.json` | `composer.lock` |

Rules:

- A manifest that declares no dependencies gives no finding. A manifest
  that does not parse declares dependencies.
- A lockfile in the manifest's directory or in an ancestor directory up
  to the root counts. This rule covers a workspace with one lockfile at
  its root.
- A lockfile that git does not track does not count.
- The finding is an `error` at every tier. Its action names the lock
  command of the ecosystem, for example `run uv lock (or poetry lock, pdm
  lock) and commit the lockfile`.
- In a scoped run, the row keeps a finding only when its manifest is in
  the changed set.
- A manifest that is not UTF-8 is skipped, and gives one
  `manifest-unreadable:<path>` row: category `security`, severity
  `info`, manual. The evidence is
  `<path> is not UTF-8, so the lockfile row skips it`; the action is
  `save the manifest as UTF-8`. The workspace test of the tier pick reads
  such a manifest as absent.

### Secret engine

The report prints the secret engine on the line after `counter <name>`:
`secrets gitleaks` or `secrets built-in`. When gitleaks is on the path and
fails, the line is `secrets built-in (gitleaks failed: <reason>)`, the
built-in patterns run, and the plan holds one `secret-engine` error row
(see [The slop and security rows](#the-slop-and-security-rows)). The JSON report has the key `"secret_engine"`,
and the key `"secret_note"`: `""` when gitleaks ran to the end or is not
on the path, else the note in the brackets, for example
`gitleaks failed: exit 2`.

- `check` and `check --changed` run
  `gitleaks dir . --redact --no-banner --exit-code 0 --report-format json`
  in a temporary directory that holds a copy of the surveyed files
  (D15.20). The full run now scans such a copy, as the scoped run does:
  the full run copies every surveyed file, and `check --changed` copies
  the changed files only (D14.14). So a build tree that git ignores, or
  any other path outside the survey, is not scanned and gives no
  finding. `check` on target-rust/src takes 2.5 s.
- A symlink whose resolved target is outside the root is not copied for gitleaks (D15.22).
- `trueup baseline` and `check --baseline` run `gitleaks git .` with the
  same options on the history. They give `secret-history` findings, so
  the baseline file and the gate count the same keys.
- Each call renders the gitleaks config of the effective config into a
  temporary directory outside the target and passes `--config <that
  file>` (D14.22 item 2). The report goes to the same directory. A
  target's `lint/gitleaks/gitleaks.toml` is not read.
- `trueup` keeps only the file, the line, the rule id, the commit and the
  fingerprint of each report entry. It never reads the secret text
  (I-23, I-30). In code, `_entry_fields`, `_history_finding` and
  `_content_findings` map a report entry; `secrets._map_entry` is gone.
- `scripts/check_targets.py`, the script of the field runs: a run whose
  `secret_engine` differs from the configured one (`gitleaks` when it is
  on the path of the script, else `built-in`) is an error
  `secret engine <engine>: <note>`. So a gitleaks timeout does not pass
  as a good run.
- The `secret-file` row always runs. It reads the file name, and for a
  key name the first 64 bytes through `fsread.read_head`; an `.env` name
  takes its answer from the `secret-content` rows of this run (D15.10,
  I-49).

### Gitleaks managed file and hook

Status on 2026-10-07: gitleaks is at v8.30.1 and its maintainers call it
feature complete. The successor is Betterleaks, which MegaLinter now lists.
trueup still calls gitleaks. A change to the successor needs its own row.

The gitleaks config is no longer a managed file (D14.8). `check`,
`baseline` and `check --baseline` render it at each run into a
temporary directory (D14.22 item 2). It holds `[extend] useDefault =
true`. When `trueup.toml` has `ignore` globs, it also holds one
`[[allowlists]]` table with one anchored path regex per glob, in config
order. An old `lint/gitleaks/gitleaks.toml` gets a `managed-legacy` info
row, and nothing reads it.

The config always holds one `[[rules]]` override of `generic-api-key`,
before the path allowlist (D16.5). Its one `[[rules.allowlists]]` table
has `regexTarget = "secret"` and one exact-match regex for each value of
`managed.PUBLISHED_TEST_VALUES`: values that a public standard prints.
Today the list holds the sample `Sec-WebSocket-Key` of RFC 6455. The
code builds the value, so the source holds no literal key. gitleaks
drops a row only when the whole matched value is on the list. Another
value on the same line pattern still gives a row, and so does the same
value under another rule (I-59). trueup never reads the matched text
(I-30). The built-in patterns do not match the value: on 2026-11-12, no
pattern matched it on four line shapes. A test value of one project
stays a `[[keep]]` entry.

The text below describes the pre-commit hook and the CI workflow that
trueup managed before D14.8. `trueup lint` runs no gitleaks hook, and
the CI template runs `trueup check`, whose secret rows run gitleaks.

The managed pre-commit file has a shared `gitleaks` pre-commit hook,
after `ref-check` and before the language hooks. It runs
`gitleaks git --pre-commit --staged --redact --no-banner --config
lint/gitleaks/gitleaks.toml`. Below T2 the config file is not in the set,
so the hook has no `--config` part and gitleaks uses its own defaults. When `gitleaks` is not on the path, it
prints `gitleaks not on the path: secret scan skipped` and passes. The
hook text is the same on every machine (I-33).

The managed CI workflow installs a fixed gitleaks version and checks the
archive with `sha256sum -c`. After `pre-commit run --all-files`, it runs
`gitleaks git . --redact --no-banner --config lint/gitleaks/gitleaks.toml`
on the full history (`fetch-depth: 0`). So CI enforces the scan.

## Rule sets

`trueup` ships sixteen rule sets: eight languages, each in `strict` and
`clean` mode. `trueup lint` renders every config file that a rule set
needs into a temporary directory at each run, and every hook names that
file with its config flag (D14.6); no config file lands in the target. `clean` runs the linter's own rules; `strict` turns on more of
them and, where a tool exists, adds a duplication check and a dead-code
check. A tool missing from the target gives a `tool-missing` finding
(above); `trueup` still ships the rule set.

The table below states which hooks of each rule set a test on this
machine ran end to end, against a small passing and a small failing
sample. "No test" means the tool is on this machine but no test runs that
hook. "Unverified here" means the tool is not on this machine, so no test ran
that hook; where a test for it exists, the test skips and names the tool,
so `pytest -rs` lists it. A tool missing from
a target is not a defect in the rule set: `trueup` reports it as a
`tool-missing` finding.

| Language | Clean | Strict |
|---|---|---|
| Python | `ruff check` verified; `ruff format --check`: no test, and its hook leaves out `ref_check.py` | `ruff check` verified; `ruff format --check`: no test, and its hook leaves out `ref_check.py`; `vulture`, `interrogate`, `complexipy`, `pydoclint` unverified here |
| Rust | `cargo clippy` verified, with `--keep-going` on a three-crate workspace; `cargo fmt --check`: no test | `cargo clippy` verified; `cargo fmt --check`: no test; `cargo machete` unverified here |
| TypeScript | `eslint` verified on eslint 10, with the eslint packages this repository has under `lint/ts/` (the ranges of the templates, D9.5); the `[[eslint.off]]` block and the suppressions file verified (D13.5, D13.6) | `eslint` verified, with `eslint-plugin-sonarjs` under `lint/ts/`; `knip` unverified here (not installed) |
| Vue | `eslint` verified, with `eslint-plugin-vue` under `lint/ts/`; `vue-tsc` unverified here (not installed) | `eslint` verified; `vue-tsc` and `knip` unverified here (not installed) |
| Shell | `shellcheck` verified | `shellcheck` verified; `shfmt` verified |
| SQL | `sqlfluff` verified (sqlfluff 4.3.0 in a local venv from the uv cache, offline) | `sqlfluff` verified (sqlfluff 4.3.0 in a local venv from the uv cache, offline) |
| Go | `golangci-lint` verified (`config verify`, then a good and a bad package) | `golangci-lint` verified; stderr carries no `deprecated` warning, proving `wsl` and `gomodguard` are off |
| PHP | `phpstan`, `phpcs` and `phpmd` verified, through the machine's composer global vendor directory | `phpstan`, `phpcs` and `phpmd` verified, with `phpstan/phpstan-strict-rules` from the same vendor directory |

The strict rule sets set these limits (D15.28):

- TypeScript strict eslint block is an array: a typed object for `ts,tsx,mts,cts` and an untyped object (`tseslint.configs.strict` and `stylistic`) for `js,jsx,mjs,cjs`, with the same thresholds, sonarjs, security and jsdoc.
- Vue strict script block sets complexity 10, max-depth 4, max-params 5, max-lines-per-function 60 and sonarjs cognitive 15. The fragment imports sonarjs as `vueSonar`.
- Vue strict package-strict.json devDependencies list eslint-plugin-sonarjs ^4.2.2.
- phpmd strict: CyclomaticComplexity reportLevel 11 and ExcessiveMethodLength minimum 61 (allow 10 and 60); parameters stay at 6 (allows 5).
- Python strict ruff selects `ALL` and ignores `COM812`, `ISC001`, `CPY`, `S603` and `S607`, each with a reason in the file. `CPY` is off because the comment standard rules out a copyright header; ruff 0.17 raises `CPY001` without the ignore (D16.7). On 2026-11-12 the strict ruff tests passed with ruff 0.15.9 and 0.17.4.
- Function length: Python 50 statements (ruff PLR0915, no line limit), none for shell and SQL. The function-length row of `docs/explanation/research-code-rules.md` says the same.
- A rule set has no nightly commands: the RuleSet.nightly field and all its values are removed, and the rules module docstring no longer mentions a nightly CI job.

The five comment-standard languages of D1.5 follow a different rule: in
`tests/test_lint_fixtures.py`, a test that needs a missing tool fails. It
does not skip.

Four facts about the hooks that a person sees at commit time:

- Strict Python has a `pydoclint` hook after `complexipy` (D12.8). It
  checks that the sections of a Google docstring match the signature,
  with `--arg-type-hints-in-docstring=False` and
  `--check-return-types=False`. When the baseline file
  (`[python] pydoclint_baseline`, default
  `lint/python/pydoclint-baseline.txt`) exists, `trueup lint` adds
  `--baseline <path>`, so the hook fails only on new defects. Without
  the file, pydoclint runs with no baseline. The person writes the file
  with pydoclint's own `--generate-baseline=True` option and commits it;
  trueup never writes it (I-47). A target with no `pydoclint` on the path
  gets the `tool-missing:python/pydoclint` info finding.

- The eslint templates ask for eslint 10 (D9.5); eslint 9 is in
  maintenance and its last releases are deprecated on the registry.
  eslint 10 runs on Node 20.19, 22.13 or 24 and later; trueup does not
  read the Node version.
- The eslint hook reads the bulk suppressions file
  `lint/typescript/eslint-suppressions.json` when it exists (D13.6). The
  file holds a count of errors per file and rule; eslint reports a rule
  in a file only when its count grows. It covers rules at `error` only:
  a warning still fails under `--max-warnings 0`. The target owns the
  file and commits it; trueup does not write or check it. With no file,
  the hook runs as before. When a fix makes a count too high, the hook
  exits 2 with `There are suppressions left that do not occur anymore`:
  run the prune command and commit the smaller file, so the count only
  goes down. The commands, from the root:

  ```
  # create the file: freeze the errors of today
  npx --prefix lint/typescript eslint --config lint/typescript/eslint.config.mjs --suppressions-location lint/typescript/eslint-suppressions.json --suppress-all .
  # prune it: remove the counts that no longer occur
  npx --prefix lint/typescript eslint --config lint/typescript/eslint.config.mjs --suppressions-location lint/typescript/eslint-suppressions.json --prune-suppressions .
  ```

  `.` lints the whole tree, also the paths under the `ignore` globs that
  the hook leaves out; name the source directories in place of `.` when
  an ignored path holds JS or TS. To turn a noisy rule off with a reason
  in place of a count, use `[[eslint.off]]` (see
  [trueup.toml](#trueuptoml)).
- Both clippy entries deny `missing_docs` and pass `--keep-going` to
  cargo (D9.6). A denied lint is a compile error, so a crate that fails
  hides every crate that depends on it, and the count grows after the
  fix; `--keep-going` still checks the crates that do not depend on it.
  To see the full count before any fix, run the entry with `-W` in place
  of each `-D`: every crate compiles and every lint prints as a warning.

Since D14.6, `trueup lint` runs the hooks above with configs that it
renders at run time, so the paths `lint/typescript/eslint.config.mjs`
and `--prefix lint/typescript` of the suppressions bullet are the old
managed tree. The suppressions file itself stays the target's: its path
is `[eslint] suppressions`, and `trueup lint` passes it only when it
exists. `trueup lint` passes no extra eslint option, and its eslint
config exists only while a run lasts, so in this release a person runs
the create and prune commands with an eslint config of their own. The
pydoclint baseline follows the same rule: its path is `[python]
pydoclint_baseline`.

The strict duplication check (`jscpd`, rendered once when any language is
`strict`) is verified: a test runs `lint --install`, and the duplication
hook exits 1 on two identical files. The test skips, and names the
reason, when the npm registry is not reachable. The Vale prose check (below) is verified: a real `vale` run catches a
banned word in a Markdown file and in a source comment alike.

The Vale hook reads Markdown and the comments of the eight extensions
Vale lexes as code: `.py`, `.rs`, `.ts`, `.tsx`, `.js`, `.jsx`, `.go` and
`.php`. Vale reads `.mjs`, `.cjs`, `.mts`, `.cts`, `.sh`, `.sql` and
`.vue` as plain text, string literals included, and no setting adds a
lexer, so the template leaves them out (D8.6). The `prose` row of `check`
reads the comments of those files instead. A `.php` file needs its
`<?php` tag for Vale to find its comments.

## Move plan

A full `check` proposes where each `doc-misplaced` page belongs
(`trueup/layout.py`, D10.6). Each proposal is a move with an id
`move:<source>`. A move is not a finding: it is not in the plan, and the
score does not read it. `apply` runs a move only when its id is in
`--ids`. `--all-auto` never runs a move, and `check` never moves a file.

### Where a page belongs

The locator tries three sources of evidence in this order, and the first
target that passes the checks below wins:

| Basis | Evidence | Target |
|---|---|---|
| `history` | A rename into the page's path, from `git log -M --diff-filter=R` or a staged rename. A staged rename wins, then the newest commit. | The old path of the rename. |
| `link` | A refcheck `broken-link` finding whose missing target has a basename that exactly one surveyed path holds (a file or a directory of files, candidate or not), and that path is the page, or, for a link that ends in `/`, a directory that holds it. | The missing target, or for a directory link, the missing directory plus the page's path inside the directory. |
| `standard` | No history and no link evidence. | `docs/<type>/<basename>` for a front matter `type` of `tutorial`, `how-to`, `reference` or `explanation`; else `docs/<basename>`. With `[refs] layout = false` or `docs = "readme"`, always `docs/<basename>`. |

A `history` or `link` target is refused when it is absolute or goes out of
the repository (`..`), when a surveyed file is at that path now, or when
it has no `docs` segment and is not a standard root page at the root. A
directory target is also refused when a surveyed file is under it now. A
refused target sends the page to the next source. The history scan runs
git with `core.quotePath=false`, so a renamed page with a non-ASCII name
gets `history` evidence too.

The `history` basis also holds in these cases (D15.25):

- With `--root` at a subdirectory, git gives each rename with the
  subdirectory prefix. The locator reads the prefix once
  (`git rev-parse --show-prefix`), keeps only the renames inside it, and
  strips it, so the `history` basis holds.
- The locator follows the rename chain back to the newest old path that
  passes (a `docs_dir` segment or a standard root page). A cycle in the
  chain stops the walk.
- In a shallow clone (`git rev-parse --is-shallow-repository` prints
  `true`), the history can be incomplete. A `standard`-basis evidence
  then ends with `; history unavailable (shallow clone)`.

A directory becomes one move of kind `dir` (`move:misc/design/` to
`docs/design/`) when each Markdown file under it is a candidate with the
same target directory, it holds two candidates or more, or one candidate
and another file, evidence places each non-Markdown file under the target
too, no file under it matches `protect`, and the target directory is
empty and no other move fills it. The largest such directory wins. Its
other files move with it. Each other page gets its own move of kind
`file`.

`move:` ids exist only for tracked pages (D15.27). The locator reads the
tracked files (`Survey.tracked`) and gives no move to an untracked page.

No move is proposed when:
- git does not track the page. The page keeps its `doc-misplaced` row,
  with the reason
  `the page is not tracked; git add it, then run trueup check again`. A
  directory that holds an untracked file is never one directory move;
- `protect` matches its source, its target, or a parent directory of
  either. The page's evidence says `protected`;
- the page has a `[[keep]]` entry. A directory that holds a kept page is
  never one move, so its other pages get file moves;
- a file or a directory is at its target in the work tree now, for each
  basis. `git mv` onto a file fails, and onto a directory it puts the
  source inside it. The page's evidence ends with `target <target>
  exists, move it by hand`;
- another move has the same target, or a file target is inside the target
  of a directory move. Each move in that group is dropped, and the page's
  evidence says `target <target> is claimed by more than one page`.

A refcheck `broken-link` finding gets one hint added to its evidence. The
finding id does not change, so a `[[keep]]` entry for it still holds:
- `the target is now at <source>; approve move:<source>` when the missing
  target is the target of a move;
- `a file with this name is at <path>; fix the link` when exactly one
  surveyed file has the basename of the missing target and it is not a
  `doc-misplaced` page. Fix that link by hand: no move id fixes a link.

A broken link to the place of a kept page gets neither hint.

### The report

The Markdown report prints `## Move plan (n)` after `## Plan`, one line
for each move:

```text
- [ ] move:misc/design/ → docs/design/ (history: renamed from docs/design/a.md in 1a2b3c4)
```

The JSON report holds `moves`, a list sorted by id. Each item has `id`,
`source`, `target`, `kind` (`file` or `dir`), `basis` (`history`, `link`
or `standard`), `evidence` and `pages` (the `doc-misplaced` pages that the
move covers). A source and a target end in `/` for a directory. A scoped
run (`check --changed`) makes no move plan.

### Apply a move

Run the steps in this order:

1. `check`: read the plan and the move plan.
2. `apply --ids <approved automatic ids>`, or `apply --all-auto`: remove
   copies and junk, for example `README.old.md`. This can change the
   evidence of a move.
3. `check` again: take the move ids from this move plan.
4. `apply --ids '<move ids>'`: run the approved moves.

`apply` checks each `move:` id against the current move plan. An id that
is not in it gives `<id> is not in the current move plan`, and `apply`
exits 2 with nothing written. One `--ids` can hold `move:` ids and
finding ids: the findings run first, then the moves, in the order of the
move plan. For each move, `apply`:

1. reads each tracked `*.md` and `*.markdown` file. `git ls-files -z`
   lists them, so a non-ASCII name is not quoted;
2. checks the target and each link rewrite by the rule of
   [Writes stay in the root](#writes-stay-in-the-root), makes the
   target's parent directories, and runs `git mv <source> <target>`, then
   prints `moved <source> to <target>`. When `git mv` fails, it removes
   the directories that it made;
3. rewrites each relative link (inline link, image or reference
   definition) whose target moved, or that a moved file holds, so it
   resolves from the new place. It changes only the link destination. It
   keeps the fragment and a trailing `/`. A file that does not move keeps
   a link that still resolves. In a file that moves, each link takes the
   canonical form, the relative path from the file's new directory; a
   link in that form, with or without one leading `./`, does not change,
   for example `./b.md`. So two moves that undo a scramble give the old
   text back (D10.7, I-37). It skips a link with a scheme, a link that
   starts with `#` or `/`, a fenced block, an indented code block and a
   code span, by the same fence, code span and link rules as check g
   (see [How the checker reads a file](#how-the-checker-reads-a-file)).
   A link that was broken before the move does not change;
4. leaves a file that matches `protect` as it is, and prints each of its
   lines with a link the move breaks as `left broken: <file>:<line>`;
5. prints each tracked file that is not Markdown and holds the source path
   as `code mentions <source>: <file>:<line>`. For a directory move the
   search text ends in `/` (`misc/`), so the bare word `misc` is not a
   mention. `git grep` runs with `core.quotePath=false`, so a non-ASCII
   Markdown page is not reported as code. It does not change that file:
   read the code and fix it by hand.

When `git mv` fails, `apply` prints `failed <move id>: <error>`, runs the
other moves, and exits 1. `apply` does not commit. A move whose source,
target or rewritten page has uncommitted changes is refused before the
first write (see [Dirty tree](#dirty-tree)).

### A page that stays

A page that must stay outside `docs/`, for example because a tool reads
it at a fixed path, gets a `[[keep]]` entry with the id
`doc-misplaced:<path>`. The finding then leaves the plan, the page gets
no move, and a directory that holds it never moves as one unit. `protect`
only stops the move: the finding stays in the plan with the evidence
`protected`. Use `protect` as well when `apply` must never touch the page.

## The slop score

`trueup check` prints a score from 0 (best) to 100, across five weighted
categories that sum to 90: security 25, files 20, docs 20, root 15, health
10. A finding counts only when it is in the plan (an `error` or `warn`
finding that is not kept) *and* its category is one of these five. A plan
finding in the sixth category, `setup` (a missing `trueup.toml` or
language mode, a managed file that is absent or differs from what `trueup`
would write, or a missing `.gitignore` line), never moves the score, the
same as an `info` finding or a kept one — the "Setup findings" table above lists that
category's rules. For a category with weight `w` and `n` plan findings in
it:

- security: `w` when `n > 0`, else 0.
- files: `w * min(1, 10 * covered / max(1, file count))`. `covered` is
  the number of surveyed files that a `files` plan finding covers, each
  file once (D15.21). A finding path that ends in `/` covers each
  surveyed file under it; another path covers itself; a path that is no
  surveyed file counts 1. So one `artifact` row for a directory of 40
  files counts 40.
- docs: `w * min(1, distinct paths / 10)`, counting the distinct `path`
  values among the docs findings, not the finding count. So one rule that
  fires on many lines of one file counts once.
- root: `w * min(1, entries over the budget / 10)`, where the budget is
  the tier's root budget plus the length of `[root] allow`. This category
  counts root entries, not findings.
- health: `w * min(1, n / max(1, required items at this tier))`.

`score = round(sum(categories) * 100 / 90)`. The report prints the total
and each category's value with its raw input in brackets (D10.8), for
example `- files 11.4 (40 of 702 files)`. The raw texts are:

| Category | Raw text |
|---|---|
| security | `<n> findings` |
| files | `<covered> of <file count> files` |
| docs | `<distinct paths> paths` |
| root | `<entries over the budget> entries, budget <budget>` |
| health | `<n> of <required items> required` |
| setup | `<n> findings` (JSON only; `setup` has no weight) |

The JSON `score` object holds the same texts as `raw`, keyed by category.
A `doc-misplaced` finding is in the `files` category, so a page outside
`docs/` raises `files`. The `refcheck` findings on its links still count in
`docs`. The formula is a proposal this repository uses
to summarise a `check` run; no other tool has calibrated it, and a lower
number is not a claim about a repository beyond what its own plan findings
already say.

### Calibration

A field trial ran `check --json`, read-only, against six repositories
under both the pre-calibration formula (v1: `docs` counted every finding,
and a `duplicate` group scored the same inside a fixture tree as anywhere
else) and the current formula (v2: this page's formula above). Each
repository's findings were opened and judged by hand as a true positive, a
false positive, or noise (an accurate finding on data kept on purpose,
such as a test fixture). The trial rank orders the six repositories by
that hand count of true-positive findings in the five scored categories
(fewest first, ties broken by the lower v1 score):

| Repo | v1 score | v2 score | Trial rank | True-positive scored findings |
|---|---|---|---|---|
| trueup (control) | 0 | 0 | 1 | 0 |
| meridian (Python) | 21 | 0 | 2 | 0 |
| target-php (PHP, Vue) | 3 | 3 | 3 | 1 |
| target-go (Go) | 38 | 10 | 4 | 4 |
| target-py/src (Python, TypeScript) | 18 | 16 | 5 | 7 |
| target-mixed/src (Python, shell, SQL, TypeScript) | 30 | 30 | 6 | 20 |

Ordering the repositories by v2 score gives exactly this trial rank; v1
does not (it ranks meridian 4th, target-go last, and swaps target-py/src and
target-php). meridian's v1 score came entirely from 19 `duplicate`
findings inside one intentionally-duplicated fixture tree, judged noise;
the v2 duplicate exemption removes all of them, so its score drops to 0.
target-go's v1 score carried about 28 of its 38 points (the full
`security` weight of 25, times 100 / 90) from two `secret-content`
false positives (a PEM banner used as a documentation placeholder); with
that rule already fixed before this calibration, its v2 score reflects
only its four genuine findings. target-mixed/src does not move: its
`ref_check.toml` has no `local_tags` yet, so the same `unregistered`-marker
false positives that saturated its `docs` category in v1 still fill the
same cap in v2 (`min(1, distinct paths / 10)` reaches 1 either way once a
false-positive rule fires on more than ten files). Fixing that is an
owner follow-up to this repository, not a `trueup` change.

## Baseline

`trueup baseline` writes `.trueup-baseline.json` at the target root from a
full `check` run; `check --baseline` compares the current plan against it
instead of judging the plan directly. This is the legacy-adoption path: a
repository with years of existing findings can freeze today's count and
fail only on a new one.

`trueup baseline [--root DIR]` runs `collect(root)` in full, with the
history secret scan (see [Secret engine](#secret-engine)), prints
`baseline: <n> keys, score <s>`, and exits 0 (or 2 on a bad `trueup.toml`).
It is the only command that writes `.trueup-baseline.json`; `check`, with
any flag, writes nothing (I-16).

The file:

```json
{
  "version": 1,
  "score": 22,
  "findings": {"<key>": <count>},
  "ratchet": {"<language>": {"docstring": <float>, "test": <float>}}
}
```

`findings` counts only plan findings (`error` or `warn`, not kept), by key.
A key drops the line part from an id that carries one:
`secret-content:<path>:<fp>` and `changelog:<path>:<fp>`, with or without
a `:<n>` repeat number, become `<rule>:<path>`, by the rule name
(`baseline.key`); `refcheck:<path>:<line>:<kind>[:<tail>][:<n>]` becomes
`refcheck:<path>:<kind>[:<tail>]`. Every other id is its own key. A key
stays readable; it is never a hash. The key shape did not change with
D15.8, so an existing baseline file stays valid.

`ratchet` holds one float metric per language that is present and set to
`clean` (a `strict` language already has fixed floors):

| Metric | Language | Source | Value |
|---|---|---|---|
| `docstring` | python | stdlib `ast` over the surveyed `.py` files outside `tests/` | percent of public modules, classes and functions with a docstring |
| `test` | python | `coverage.xml` (Cobertura) at the root | `line-rate` × 100 |
| `test` | go | `coverage.out` (coverprofile) at the root | covered statements / statements × 100 |
| `test` | typescript | `coverage/lcov.info` | sum of LH / sum of LF × 100 |
| `test` | rust | `lcov.info` at the root | sum of LH / sum of LF × 100 |

An absent report gives no `test` value; a recorded `test` value with no
report on the next run fails the gate rather than passing silently.
The report read is bounded (D16.10): a report over 64 MiB, a device, a
FIFO and a symlink out of the root read as absent. A
report older than the code is not detected: CI must write it in the same
job that runs `check --baseline`.

`trueup check --baseline [--root DIR] [--json]` reads the file and reports
a `Gate`:

- `new`: finding ids whose key's count rose above the recorded count.
- `score_before`, `score_now`: the baseline's score and this run's score.
  They are information only: a score rise alone does not fail the gate
  (D15.21).
- `ratchet_drops`: `"<lang>:<metric> <before> -> <now>"` for a ratchet
  value that dropped by more than 0.1.
- `missing_reports`: `"<lang>:<metric>"` for a ratchet value the baseline
  recorded that this run could not measure.
- `tighten`: keys whose count fell, or vanished; informational only, never
  a gate failure.

With no baseline file, it prints `no baseline: run trueup baseline` and
exits 2: `baseline.load` gives `None` for an absent file. A file that is
not valid JSON, or that has a bad shape, raises a `ConfigError` and exits 2
with `trueup: .trueup-baseline.json: not a trueup baseline: <why>`. The
shape is: `findings` a map of integers, `score` an integer, and
`ratchet` a map of maps of numbers. Otherwise it exits 1 when `new`, `ratchet_drops` or
`missing_reports` is not empty (`baseline.failed` reads only these
three); else it exits 0, even when the plan itself is not empty or the
score rose. So `git rm` of clean files, which makes the file count
smaller and the score higher, does not fail the gate. The Markdown report adds a
`## Baseline` section (score, new, ratchet drops, missing reports,
tighten); the JSON report adds a `"baseline"` key with the same fields.

To gate a CI pipeline on a baseline, read
[gate CI with a baseline](../how-to/gate-ci-with-a-baseline.md).

## Hooks

`hooks/hooks.json` wires four Claude Code events to `python3
"${CLAUDE_PLUGIN_ROOT}/trueup" hook <event>`: `SessionStart` and
`PreToolUse` to `hook session` and `hook guard`, `Stop` to `hook stop`,
and `PostToolUse` to `hook interface`. It has no `SubagentStop` group, so
the stop check runs for the main session only, and a subagent never gets
its block (D15.33). Every one finds the
target's root by walking up from the `cwd` of the hook's JSON input (or the
process's own working directory when `cwd` is absent) to the first
directory holding `.git`, and does nothing when that root has no
`trueup.toml`. A user default file does not turn a hook on (D14.11). Anything unexpected — bad JSON, an exception — also gives no
output and exit 0.

The launcher `python3 trueup` makes this gate before it imports
`trueup.cli` (D15.7). Below Python 3.11 a `hook` call exits 0 with no
output. Else the launcher reads standard input once. Blank input counts
as `{}`; bad JSON, or a value that is not a JSON object, gives exit 0.
With no `.git` root, or no `<root>/trueup.toml`, it exits 0. Else it
passes the text that it read on to the CLI
(`sys.stdin = io.StringIO(text)`). A `trueup.toml` that is not valid
turns the hooks off: `hook session` prints
`trueup: trueup.toml is not valid: <message>; the trueup hooks are off until it is fixed`
and exits 0, and `guard`, `stop` and `interface` stay silent. A hook writes only below `$CLAUDE_PLUGIN_DATA`, never in
the target tree, and every git call it makes uses `--no-optional-locks`, so
`git status` never refreshes `.git/index`.

**SessionStart** writes a session snapshot when `$CLAUDE_PLUGIN_DATA` is
set: `$CLAUDE_PLUGIN_DATA/sessions/<session_id>.json` holds the `HEAD` sha,
the blob sha of each file the working tree already changed, and a
`reminded` list, empty at the start, where the interface reminder records
each path it names. A `startup` or `clear` source
replaces the file; `resume`, `compact` or `fork` write it only when none
exists, so the session's first snapshot stays. This is how `Stop` and
`PostToolUse` below tell a session's own edits from dirt that was already
there. It also prints the rules of the effective config, in place of
an agent rules file in the target (D14.10):

```text
trueup: profile <name>, tier <tier>, docs <docs>.
Languages: <lang>=<mode>, ...
Write docs in Simplified Technical English: short sentences, active voice, one topic a page.
Put a page under <docs_dir>/ in one type: tutorial, how-to, reference or explanation.
Start a comment marker with a registry word: ref, arch, law, SAFETY or TODO.
Cite a design id only in a form that <docs_dir>/ARCHITECTURE.md declares.
Root rule: a new file at the repository root must be on the base list or in [root] allow in trueup.toml.
Scratch rule: a tmp/temp/scratch/notes/*.bak/*.orig/*~-style name goes under .scratch/, never tracked elsewhere.
Managed-file rule: apply rewrites trueup.toml; edit it by hand or with apply --set.
Run <command> check before you finish. Fix each finding or report it.
```

`tier` and `docs` are the values in force, not the raw keys (D15.34).
With `tier = "auto"`, `tier` is the tier of the survey of the root
(`survey.run(root).tier`). `docs` is the mode in force for that tier
(`config.resolve_docs`), so `docs = "auto"` prints `readme` or `full`.
The Simplified Technical English line prints only under the profile
`house`. `<command>` is `trueup` when `trueup` is on `PATH`; else it is
`python3 <launcher>`, the directory that holds the hook module, so the
line says `python3 <launcher> check`. The `Languages` line comes only
when a mode is set. The page-type line needs `[layout] types`, the
marker line `[refs] comments`, and the design-id line `[refs] registry`.

**PreToolUse**, matched on `Write` and `Bash`, asks. Only the install
guard can deny:

- A `Write` to a file that exists gives no decision: the `Write` is an
  edit (D15.31).
- A `Write` to a new file with a scratch-looking name gets `ask`
  (D15.31). The guard uses the `scratch` row's own name rule and
  exemptions: nothing under `.scratch/`, and nothing `ignore`,
  `[root] allow` (at the root) or `[scratch] allow` names, gets the
  question. A `-v<n>` document name under `<docs_dir>/` is a versioned
  page, not scratch, as for `check` (D14.12). The guard does not use the
  directory rule: a clean name under `tmp/`, `temp/` or `scratch/` is
  let through, because an ignored local `tmp/` is common. `check`
  reports such a file when git does not ignore it. This check comes
  first, so a new root file with a scratch-looking name gets one scratch
  ask, not the root question as well.
- A `Write` to a new file whose parent is the target's root gets `ask`,
  unless its name is on the base list, in `[root] allow`, or already on
  disk (D14.11). The base list is `[root] base` when it is set; else
  the code list: `README*`, `LICENSE*`, `trueup.toml`, `.gitignore`,
  CI and tool files such as `Dockerfile`, `CODEOWNERS`,
  `.gitlab-ci.yml`, `tsconfig.json` and `requirements*.txt`, the
  standard root pages in any case (`CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md` and the like), every manifest name and every
  lockfile name. The reason says to add the name to `[root] allow` to
  stop the question.
- A `Bash` command whose `git add` names a scratch-looking path, read
  relative to the root, with the same exemptions, gets `ask` (D15.31).
  The scratch guard never denies. The check reads `git add` per shell
  segment (D15.35): it cuts the command at the shell operators, as the
  install guard below does, drops the leading `sudo`, `env` and
  `NAME=value` words of each segment, and reads the path tokens of each
  segment that starts with `git add`. So `echo git add x` gives nothing,
  and `cd d && git add x`, `sudo git add x` and `NAME=v git add x`
  count. `git -C <dir> add`, `git stage`, and `git add -A` or `--all`
  pass through unseen.
- The guard sees only `Write` calls and `git add`. A file that a Bash
  command writes (`touch`, `>`, a heredoc, `mv`) is not seen (D15.31).

A decision is the standard Claude Code JSON shape, with a reason naming
the allow-list key or `.scratch/` that would have let the write through.

**The install guard.** For a `Bash` command, the install guard runs after
the checks above, also when they gave an `ask` (D15.31, D15.32). Its
deny wins over the scratch `git add` ask; else the scratch ask stays the
answer, and its reason comes first when the install guard also asks.
The guard is off unless `[guard] registry = true` (D15.32): by default
it makes no lookup. It splits the command
into segments at the shell operators, and drops the leading `sudo`, `env`
and `NAME=value` tokens of each segment. A segment that starts with one of
these is an install:

| Registry | Leading tokens |
|---|---|
| PyPI | `pip install`, `pip3 install`, `python -m pip install`, `python3 -m pip install`, `uv pip install`, `uv add`, `poetry add`, `pdm add` |
| npm | `npm install`, `npm i`, `npm add`, `pnpm add`, `yarn add`, `bun add` |
| crates.io | `cargo add` |
| Go module proxy | `go get`, `go install` |
| Packagist | `composer require` |

Options, paths, URLs, archives and local Go packages are not package
names; a version or an extra is removed from a name. The guard does not
look up a package (D15.32):

- when its segment holds `--index-url`, `--extra-index-url`, `-i` or
  `--registry` (a long option also in the `--option=value` form);
- when it is an npm scoped name (`@scope/x`) and a line of
  `<root>/.npmrc` starts with `@scope:registry=`;
- when it is an npm name and a line of `<root>/.npmrc` starts with
  `registry=`;
- when its name matches a `[guard] private_packages` glob.

The guard reads no user-level `pip.conf` or `.npmrc`. For each other
name, the guard asks the registry when the package first appeared
(`trueup/registry.py`, the only module that opens a network connection,
I-28):

- Not on the registry: `"permissionDecision": "deny"`, with the reason
  `trueup: <name> is not on <registry>. Check the spelling. ...`.
- First release less than 30 days ago: `"permissionDecision": "ask"`,
  with the date and a request to check the publisher, the source
  repository and the download count.
- The registry did not answer: no decision. The hook prints a
  `systemMessage` that says the guard did not check the name.

A deny wins over an ask. The guard never gives `allow` (I-29). Each call
waits at most 2 seconds, and one command at most 5 seconds. When
`$CLAUDE_PLUGIN_DATA` is set, the answers stay in
`$CLAUDE_PLUGIN_DATA/registry-cache.json` for 24 hours; a registry that
did not answer is not cached.

**Stop** scopes a check to the files the session's own
snapshot says changed: `git diff --name-only` against the snapshot's
`HEAD` sha plus untracked files, only the files still on disk, less each
file whose blob sha is still the one the snapshot holds. With no snapshot, a snapshot for another
root, or one with no `HEAD` sha, it uses the working tree against `HEAD`
plus untracked files instead. When that scoped plan holds a finding,
the hook prints one block decision and exits 0:

```json
{"decision": "block", "reason": "trueup: <n> finding(s) in files changed this session. Fix them, or add a [[keep]] entry with a reason in trueup.toml, then finish.\n- <id>: <evidence>\n..."}
```

At most the first 10 findings are listed; a longer plan ends with a line
naming `check --changed` to see the rest. The hook never blocks a second
time on the same stop: when the payload's `stop_hook_active` is true, it
prints nothing (I-15). It is meant to run in under 1 second on this
repository (I-17), by skipping `refcheck` and reading only the changed
files in the document rows. `hooks/hooks.json` gives the `Stop` entry
`"timeout": 30`. When Claude Code stops the hook at that time, the stop
goes on (fail-open, D15.24).

Each hook run whose gate passed (the root holds `trueup.toml`) adds one
line `{"date", "event", "seconds"}` to
`$CLAUDE_PLUGIN_DATA/hook-times.jsonl` (D13.4, D15.24). When the file is
over 1 MiB, the write cuts it to its last 10,000 lines. `python3
scripts/hook_times.py` prints the run count, median, 95th percentile and
largest time of each event. The time starts after Python and the imports
are ready, so the wait in a session is longer by the interpreter start.

**PostToolUse**, matched on `Write|Edit|MultiEdit`, reminds once per file
that a change to a public interface (a Python CLI's
`add_argument(`/`add_parser(`/`@click.` in a `.py` file, an
`__init__.py`'s `__all__`, a `pyproject.toml` `[project.scripts]` or
`name =` line, a `package.json`'s `"bin"`/`"exports"`/`"name"`, a Rust
`#[arg(`/`#[command(`, or a Go `cobra.Command{`/`.Flags().`) has no README or `docs/reference/` change
yet this session, with `additionalContext`:

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "trueup: <path> changes a public interface (<signal>). README.md and docs/reference/ have no change this session. Update them if the interface changed."}}
```

It matches static text only (the text the `Write`, `Edit` or `MultiEdit`
call puts in the file) and runs no target code. A path it already reminded
about this session gets no second reminder. When the session has no
snapshot file yet, the hook writes one to record the path. When
`$CLAUDE_PLUGIN_DATA` is not set, or the `session_id` does not match
`^[A-Za-z0-9_-]{1,128}$`, the hook cannot record the path, so it gives no
reminder at all. Known limit: a file a `Bash` command writes
never triggers `PostToolUse`.

### Hook times (2026-11-09)

The hook log of this machine holds 13,069 hook runs from 2026-10-29 to
2026-11-09 (`python3 scripts/hook_times.py`). The times are in-process
times: they start after Python and the imports are ready.

| Event | Median | 95th percentile | Largest |
|---|---|---|---|
| `guard` | 1 ms | 4 ms | not recorded |
| `interface` | 1 ms | not recorded | not recorded |
| `stop` | 5 ms | 1.02 s | 2.64 s |
| `session` | not recorded | 0.174 s | not recorded |

The wall time of one `guard` call, with the interpreter start, is 0.07
to 0.31 s (the soundness audit of 2026-11-02). The 95th percentile of
`stop` is above the 1 s goal of I-17. The largest recorded `stop` time
is far below the 30 s limit of the `Stop` entry.

Decision of the owner on 2026-11-09: keep the plugin. The README stays
as it is, with the plugin and the `trueup` command side by side. This
note closes P5 and F1 of
[purpose and state](../explanation/purpose-and-state.md).

The upgrade steps are in [Upgrade trueup](../how-to/upgrade-trueup.md), and the field trial and the follow-ups are in [Field trial](../explanation/field-trial.md).
