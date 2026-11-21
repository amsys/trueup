---
name: trueup
description: Bring a repository in line with the trueup hygiene baseline when asked to true up, tidy, clean up or audit a repo, apply the doc standard or the comment standard, set lint modes (strict, clean, off), find slop, or re-check a repo with a trueup.toml. Load it also before you edit trueup/ or hooks/; docs/reference/trueup.md holds the commands, flags, exit codes, config keys and finding rules.
---

# trueup

This skill runs trueup on one target repository. The scripts do the
deterministic work: `check` finds the problems, and `apply` makes the
changes that the person approves. You ask the person, you classify, and
you write the prose. You never commit.

## Before you start

Tell the person these two facts before the first command.

1. **The hooks follow the session, not `ROOT`.** A hook never reads the
   `ROOT` of this skill. When `ROOT` is not the repository of the
   session's working directory, the hooks check that other repository,
   or no repository. Then the guard does not protect `ROOT`, and the Stop
   hook and the interface reminder do not see your changes in `ROOT`. To
   get the hooks on `ROOT`, the person starts the session in `ROOT`. Else
   run `check --changed --root "ROOT"` yourself before you finish.
2. **`--all-auto` can remove the last copy of a content.** In one plan,
   the automatic ids never remove every tracked copy of a content: one
   copy is manual, with `the last copy of this content`. But each pass of
   `--all-auto` collects a new plan. When a pass removes the other
   copies, the next plan sees the last copy as a scratch file with no
   copy, and its id is automatic, so the next pass removes it. So examine
   the scratch copies with the person before `--all-auto`. When the person
   wants to keep that content, first give the file a clean name
   (`git mv`) or add it to `[scratch] allow`. Or use `--ids`, which runs
   one pass on one plan.

## Where the facts are

`docs/reference/trueup.md` is the one normative page for the commands,
the flags, the exit codes, the `trueup.toml` keys and the finding rules.
This skill keeps only the procedure: ask, classify, approve, apply,
verify. When you need a fact, read the reference section that this skill
links. In an installed plugin the page is `PLUGIN/docs/reference/trueup.md`.

When code in `trueup/` or `hooks/` changes a fact, update the reference
page. When it changes what you ask, approve or do, update this skill. Do
both in the same session.

## Names in this skill

- `PLUGIN` is `${CLAUDE_PLUGIN_ROOT}`, the plugin root. If that variable is
  empty, use the directory two levels above this skill's own directory.
- `ROOT` is the absolute path of the target repository. Get it with
  `git rev-parse --show-toplevel` in the directory the person names, or in
  the working directory. Always pass `--root "ROOT"`.
- `SCRATCH` is a directory outside `ROOT` for the report files. Use the
  session scratchpad directory when the session names one. Else make one
  with `mktemp -d`. Do not put the report inside `ROOT`.

Shell state does not persist between Bash calls. Write the full command
each time, with the real paths in place of `PLUGIN`, `ROOT` and `SCRATCH`.

## Hard rules

1. Never run `git commit`, `git push`, `git add`, `git stash`,
   `git checkout`, `git reset` or `git clean`. `apply` runs `git rm`,
   `git rm --cached` and `git mv` itself, and only for approved ids. Leave the tree
   uncommitted and say so in the report.
2. Apply only the ids that the person approved. Give `apply` only those
   ids. Use `--all-auto` only when the person approves every automatic
   finding (see "Before you start"). A `move:` id needs its own approval:
   `--all-auto` never runs a move (see "Move plan").
3. `check` writes nothing in `ROOT` and runs no code from `ROOT`. It
   writes the report files only to `--out`. Keep `--out` outside `ROOT`.
   `lint` writes nothing in `ROOT`, but its tools can run code of `ROOT`
   (for example, `cargo clippy` builds the crate, and
   `vendor/bin/phpstan` is a file of `ROOT`).
   `baseline` writes `ROOT/.trueup-baseline.json` and no other file. Run
   it only when the person asks for a baseline.
4. Never open a file that a `secret-file` finding names. Never print or
   quote secret text. `secret-content` evidence gives a pattern name and a
   line number only; keep it that way in what you write.
5. Never write `LICENSE`, `AGENTS.md` or `CLAUDE.md`. Report those
   findings to the person.
6. Never overwrite a file that has no trueup header. `apply` does not do
   it, and you do not do it by hand.
7. Do not change a path that matches a `protect` glob in `trueup.toml`.

## Commands

Run each command as `python3 "PLUGIN/trueup" <command>`: that launcher
needs no install. Where this skill writes `trueup <command>`, it means
the same command. A bare `trueup` runs only when trueup is on the path,
and the pre-commit entry runs a bare `trueup lint` (see
`tool-missing:refs/trueup` in "Manual items"). The commands, their
flags and their exit codes are in
[the command line](../../docs/reference/trueup.md#command-line) and
[the exit codes](../../docs/reference/trueup.md#exit-codes). This skill
runs these forms:

- `check --root "ROOT" --out "SCRATCH"`: the full report. Read
  `SCRATCH/trueup-report.json`.
- `check --root "ROOT" --json > "SCRATCH/plan.json"`: a saved plan (see
  "Saved plan and checkboxes").
- `check --root "ROOT" --changed`: your own edits only (see "Scoped
  check").
- `check --root "ROOT" --out "SCRATCH" --sarif "SCRATCH/trueup.sarif"`:
  the report and the findings as SARIF 2.1.0, only when the person asks
  for a code scanning file (see
  [SARIF output](../../docs/reference/trueup.md#sarif-output)). `--sarif`
  does not change the exit code. Keep the file outside `ROOT`.
- `check --root "ROOT" --baseline --out "SCRATCH"` and
  `baseline --root "ROOT"`: only when the person asks (see "Baseline
  gate").
- `apply --root "ROOT" --ids '<ids>' [--mode ...] [--set ...]`: the
  approved ids. Put the id list in single quotes, because ids hold paths.
- `refs --root "ROOT"`: the reference checker alone, with the checker
  config that `check` uses.
- `lint --root "ROOT"`, `lint --root "ROOT" --changed` and
  `lint --root "ROOT" PATH ...`: the linters of the rule sets in force
  (see "Lint and templates").
- `lint --root "ROOT" --install`: only when the person agrees, because it
  uses the network (see "Manual items"). It installs the eslint packages,
  jscpd and sqlfluff in the trueup cache, outside `ROOT`.
- `lint --root "ROOT" --skip-missing`: only when the person agrees that
  the tools that are not installed stay unverified (see "Lint and
  templates").
- `template <name>`: prints the text of one file that trueup does not
  manage. It takes no `--root`.
- `--profile NAME` on `survey`, `check`, `baseline`, `apply` and `lint`:
  one run with another profile (see
  [the profiles](../../docs/reference/trueup.md#profiles)). It writes
  nothing.
- Do not run `hook ...` from this skill. `hooks/hooks.json` runs it.

How to read an exit code:

- Exit 1 from `check` means that the plan is not empty. That is normal on
  a first run.
- Exit 2 from any command means bad input, and nothing is written. Show
  the `trueup:` or `trueup apply:` lines to the person, fix the call, and
  run it again. A bad `trueup.toml` stops the run: show the message and
  stop.
- Exit 2 with `trueup: <root>: not a git repository; trueup reads tracked files`:
  trueup reads only tracked files, so it needs a git work tree. Tell the
  person and stop. Exit 2 with `no tracked file to check (after [scan] ignore)`:
  the `ignore` globs leave no file. Show the globs to the person.
- Exit 2 with `trueup: internal error: ...` is a defect in trueup, not in
  `ROOT`. Show the line to the person and stop. When the person wants to
  report it, run the same command again with `TRUEUP_DEBUG=1` to get the
  traceback (see [the errors](../../docs/reference/trueup.md#errors)).
- `apply` exits 2 when a path it would write, move or remove has
  uncommitted changes (see
  [the dirty tree](../../docs/reference/trueup.md#dirty-tree)). Show the
  paths to the person. Do not commit or stash for them (hard rule 1).
  Pass `--allow-dirty` only when the person says that `apply` may
  overwrite those changes.
- `apply` exits 1 when one handler, one move or one re-pin failed. The
  other ids still ran. Show the `failed` lines and run `check` again. A
  line `failed <id>: refused: <rel> resolves outside the repository`
  means that the path, or its parent, is a symlink out of `ROOT`. Do not
  write that path by hand. Show the line to the person (see
  [writes stay in the root](../../docs/reference/trueup.md#writes-stay-in-the-root)).
- `apply --plan` exits 2 with
  `unknown id <id>: the saved row does not hold on the tree now` when a
  saved automatic row no longer holds, and writes nothing. Run `check`
  again and ask again (see "Saved plan and checkboxes").
- `lint` exits 1 when one tool failed; the output of each tool passes
  through. `lint` exits 2 when a tool is not installed: it prints one
  `trueup lint: <tool> is not installed; <label> did not run` line for
  each such tool, then one `trueup lint: <n> tool(s) missing: ...` line.
  Show these lines (see "Lint and templates"). `lint` also exits 2 when
  `ROOT` has no `trueup.toml` and the person has no user default file.

In global mode, `refs` and `lint` make the checker config from
`trueup.toml` at each run, as `check` does, so a new `[[keep]]` entry or
`ignore` glob counts at once. Copy mode has a gap here (see
[copy mode](#copy-mode)).

## Read the report

Read `SCRATCH/trueup-report.json`. Do not parse the Markdown: it is for
a person and puts each finding in one line of text. The JSON gives each
field by name. A box in the Markdown marks each id that `apply --ids`
accepts (see [the approval ids](../../docs/reference/trueup.md#approval-ids)),
so a box does not mean that the finding is automatic. Use the `auto`
field.

- `schema`: the version of the report, `1` (see
  [the JSON report](../../docs/reference/trueup.md#json-report)).
- `plan`: the findings to act on. Each has `id`, `rule`, `category`,
  `severity`, `path`, `evidence`, `action`, `auto` and `line` (the line
  that the finding points at, or `0`).
- `findings`: every finding, including kept and `info` findings. `info`
  findings never enter the plan. They say what the next tier needs, which
  tools are missing (`tool-missing:<lang>/<tool>`), which installs
  `trueup lint` and the pre-commit entry need
  (`tool-missing:typescript/node_modules`, `tool-missing:refs/trueup`),
  which old checker copy can go (`refs-copy:ref_check.py`), which files
  of the old managed lint tree are still there (`managed-legacy:<path>`),
  which small languages need a mode
  (`config:languages.<lang>`), which checker reader changes gave
  warnings (`refs-reader-change:<name>`), which flags no doc names
  (`drift-undocumented`), which `[[keep]]` entries keep nothing
  (`keep-stale:<id>`), which manifests trueup cannot read
  (`drift-manifest`, `manifest-unreadable`), which big files hold text
  (`large-text`), which content trees stay outside the docs directory
  (`doc-tree`), and which platform settings to check (`platform:*`). See
  "Manual items" for each.
- `kept`: the `id` and `reason` of each finding that a `[[keep]]` entry
  holds out of the plan.
- `tree`: the identity of the working tree that `apply --plan` compares.
- `repins`: the re-pin plan (see "Re-pin plan").
- `moves`: the move plan (see "Move plan").
- `setup:trueup.toml` in `findings`: below T2 with no `trueup.toml`, this
  one row takes the place of the setup rows (see "First run").
- `score`: `total` (0 is best), `tier`, `categories` and `raw`, the count
  behind each category as text. Give the person the raw counts too: a
  category at its maximum hides how large the problem is. The `files`
  raw text counts covered files (`<covered> of <N> files`), so one
  `artifact` row for a big directory counts each file in it. See
  [the slop score](../../docs/reference/trueup.md#the-slop-score).
- `survey`: `tier`, `tier_reason`, `counter` and the languages.
  `other_languages` maps each language family outside the eight (for
  example `java`) to `present, no rule set`: trueup has no rule set for
  it. Tell the person that `trueup lint` does not lint those files.
- `profile`: the `name`, `path` and `source` of the profile in force (see
  [the precedence](../../docs/reference/trueup.md#precedence)). Tell the
  person when it is not `house`. On a target with no `trueup.toml` and
  no user default file it is `minimal`, with the source
  `built-in default`.
- `secret_engine`: `gitleaks` or `built-in` (see
  [the secret engine](../../docs/reference/trueup.md#secret-engine)). Tell
  the person when the engine is `built-in`: the scan is weaker, and
  `secret-history` findings need gitleaks. `secret_note` is not empty
  when gitleaks failed: show the note, and say that the built-in patterns
  ran in its place. Then the plan also holds the `secret-engine:` error
  row (see "Manual items").

What each rule detects, its severity and whether `apply` can do it are in
[the findings](../../docs/reference/trueup.md#findings), with
[the slop and security rows](../../docs/reference/trueup.md#the-slop-and-security-rows),
[tier and health](../../docs/reference/trueup.md#tier-and-health),
[the document rules](../../docs/reference/trueup.md#document-rules),
[the docs drift rows](../../docs/reference/trueup.md#docs-drift-rows) and
[the setup findings](../../docs/reference/trueup.md#setup-findings).
Read the row there before you explain a finding to the person.

The docs drift rows (`drift-flag`, `drift-command`, `drift-package`,
`drift-undocumented`) are never automatic, so `apply` does not accept a
drift id. Fix it by hand (see "Manual items"), or add a `[[keep]]` entry
when the person agrees.

## First run (no trueup.toml in ROOT)

0. **Superrepository.** When `ROOT/.gitmodules` exists, `ROOT` is a
   superrepository. Each submodule it lists is its own target: its own
   `ROOT`, survey, tier and `trueup.toml`. Ask the person
   which target to true up first, and run this skill once per target.
   `check` and `refs` do not enter a submodule from the superrepository.
   For the superrepository itself, look at the survey before "Show": run
   records and snapshot copies of a submodule's sources (`.state/`, `pre/`
   trees under `docs/`) give `duplicate`, `binary` and `lockfile` findings
   and pick the tier from copied manifests. Propose `ignore` globs for
   those paths first (for example `".state/**"`,
   `"docs/features/*/pre/**"`), write them to `trueup.toml` when the
   person agrees, and run `check` again. A manifest under an `ignore` glob
   does not count for the tier. Neither does a manifest more than one
   level down, or under `tests`, `test`, `fixtures`, `testdata`,
   `__snapshots__` or `examples` (see
   [tier and health](../../docs/reference/trueup.md#tier-and-health)).
1. **Check.** Run
   `python3 "PLUGIN/trueup" check --root "ROOT" --profile house --out "SCRATCH"`.
   With no `trueup.toml` in `ROOT` and no user default file, a plain
   `check` runs the `minimal` profile, and its header says
   `profile minimal (no trueup.toml; pass --profile house for the house standard)`.
   The setup writes a `trueup.toml` that runs `house`, so
   `--profile house` shows the plan that the person adopts. When the
   person asks for another profile, run `check` again with that
   `--profile`. Exit 1 is normal here. Exit 2 means that `trueup.toml` or
   its profile is bad, or that `ROOT` is not a git work tree: show the
   `trueup:` message and stop. With no `trueup.toml` in `ROOT` and a user
   default file of the person (`$XDG_CONFIG_HOME/trueup/trueup.toml`),
   `check` reads that file and gives no `config:trueup.toml` row (see
   [the precedence](../../docs/reference/trueup.md#precedence)). Then leave
   out `--profile house`, so the profile of that file holds. The hooks
   stay off until `ROOT` has its own `trueup.toml`.
2. **Show.** Give the person the score, the tier with its reason, and the
   plan grouped by category (security, files, docs, root, health, setup).
   Mark each finding as automatic or manual. List the `tool-missing` info
   findings as tools that cannot be verified here; `tool-missing:refs/trueup`
   is different, it names the one install the person's commits need (see
   "Manual items"). `check` makes the checker config from the config in
   force at each run, so the `refcheck` findings already use its
   switches, and the plan does not grow after `apply`. At T0 and T1 with no `trueup.toml`, the setup
   is one `setup:trueup.toml` info row: it writes `trueup.toml`, the one
   file that a target keeps (see
   [the managed set by tier](../../docs/reference/trueup.md#managed-set-by-tier)).
   At T0 the tier set is
   empty, so there is no row. Show the `managed-legacy` info rows as one
   group: files that an earlier trueup wrote, and that `trueup lint` and
   `trueup template` now replace (see "Lint and templates").
   When many pages fail `no-front-matter` because
   their paths are fixed, say that `[layout] front_matter = false` is the
   alternative to one `[[keep]]` entry per page (see "Keep, ignore and
   protect"). When many `doc-misplaced` pages sit in one directory of
   agent, skill or prompt files, say that `[layout] code_dirs` is the
   alternative (see "Keep, ignore and protect"). Show the move plan apart
   from the plan: each `move:` id
   with its source, target and basis. When several `refcheck` `unregistered` findings
   share a tag prefix (`X1`, `X2`, `G1`: the prefix is the letters before
   the digits), group them by prefix and name the count per prefix; the
   question set asks about them.
3. **Ask.** Ask the question set below with AskUserQuestion.
4. **Approve.** Ask which ids to apply: all automatic ids, a subset, or
   none. Ask which manual findings you may do. Record each declined
   finding and its reason for step 7. Ask about the moves after step 5
   (see "Move plan").
5. **Apply.** Run `apply` with the approved automatic ids and the answers
   (see "Approve and apply"). Show its output. Then run `check` again, and
   do the moves the person approves (see "Move plan"). Then run `lint`
   and offer the pre-commit entry (see "Lint and templates").
6. **Manual items.** Do the approved manual items (see "Manual items").
7. **Declined items.** Add one `[[keep]]` entry per declined finding to
   `trueup.toml` (see "Keep, ignore and protect").
8. **Verify.** Do the verify step.

### The question set

Ask these in one AskUserQuestion call. The tool takes at most four
questions, so use a second call when you have more.

1. One question per present language: `strict`, `clean` or `off`.
   Recommend `clean`. `strict` adds more checks to `trueup lint` (for
   example dead code, docstring coverage, complexity and `pydoclint` for
   Python) and the jscpd duplication check. See
   [the rule sets](../../docs/reference/trueup.md#rule-sets).
2. One question per language with files but below 50 code lines (an `info`
   `config:languages.<lang>` finding): `off`, `clean` or `strict`.
   Recommend `off`.
3. Public: is the repository public? `true` adds `LICENSE` and
   `SECURITY.md` at every tier, and at T2 and above `CODE_OF_CONDUCT.md`,
   an issue template and a pull-request template. It also adds the three
   `platform:` info rows (see "Manual items"). `false` also drops the
   licence row and the README `License` section check at every tier.
   With no answer, `public` stays unset and the licence rows stay.
4. Tier: ask only when the auto tier looks wrong for the repository. Offer
   `auto` (recommended) and the tier you think fits, with the reason.
5. Local tags: only when `unregistered` findings share prefixes. Show the
   prefixes with their counts and ask whether they are the project's own
   comment tags. The approved prefixes go to `[refs] local_tags` in
   `trueup.toml` (see "Keep, ignore and protect"), by hand, before
   `apply`; the next `check` then drops those findings. A prefix that the
   person does not approve stays a manual `refcheck` finding.

Ask about nothing else unless the person raises it. `docs` stays `auto`
unless the person asks for `full` or `readme`; `auto` follows the tier.
`profile` stays unset, which gives the `house` profile once `ROOT` has
a `trueup.toml`, unless the person asks for another. `minimal` keeps the hygiene rows and the link check,
turns the house rules for pages, banned words and comment markers
off, and asks only for `README.md` of the health files
(`[health] files = "readme"`; see
[the built-in profiles](../../docs/reference/trueup.md#the-built-in-profiles)).
`[refs] mode` stays `global` unless the person asks for `copy` (see
"Keep, ignore and protect"): copy mode lets the checker run where
trueup is not installed.

trueup writes no agent rules file. The `SessionStart` hook prints the
agent rules of the config in force at the start of each session (see
[the agent rules file](../../docs/reference/trueup.md#agent-rules-file)
and "Hooks"). An old `.claude/rules/trueup.md` that an earlier trueup
wrote is a `managed-legacy` info row.

## Approve and apply

Build one `apply` call from the approvals and the answers:

- Put each approved automatic id in `--ids`, in one comma-separated list.
- Put each language answer in `--mode`: `--mode 'python=clean,sql=off'`.
  An `off` answer is a real value: it stops the question on the next run.
- Put the public answer in `--set public=true` or `--set public=false`.
- Put a tier override in `--set tier=T2`. Leave `tier` out for `auto`.
- At T0 or T1 with no `trueup.toml`, put `setup:trueup.toml` in `--ids`
  when the person wants trueup set up. It writes `trueup.toml`.
  `--all-auto` never takes it. Without it, no setup file is written, and
  the other ids still apply.
- Put a profile answer in `--set profile=<name>`: it writes the
  `profile` key. `--profile <name>` changes one run only and writes
  nothing.

Example:

```
python3 "PLUGIN/trueup" apply --root "ROOT" \
  --ids 'config:trueup.toml,config:languages.python,gitignore:.gitignore' \
  --mode 'python=clean,sql=off' --set public=false
```

What each automatic id does (`git rm`, `git rm --cached` and a
`.gitignore` line, a `.gitattributes` line, a rendered file) is in the
`Auto` column of
[the slop and security rows](../../docs/reference/trueup.md#the-slop-and-security-rows)
and in [the setup findings](../../docs/reference/trueup.md#setup-findings).
Tell the person what each approved id will do before you run it.

Facts about `apply` that the person must know:

- A `config:languages.<lang>` id with no `--mode` for that language
  writes `clean`.
- A tracked scratch file is removed with `git rm` only when its name
  proves scratch (`*.bak|*.orig|*.rej|*~`, or a whole stem from
  `notes|tmp|temp|scratch|draft|untitled` plus digits, such as `notes.md`
  or `tmp2.txt`) and it is not under `vendor`,
  `third_party` or `node_modules`. Every other scratch row is manual
  (see "Manual items"). An untracked scratch file is manual too: `apply`
  never deletes a file that git cannot restore.
- An automatic `secret-file` finding untracks the file and keeps the
  working copy. trueup proved the secret: a private key head, or a
  `secret-content` line in the `.env` file. The secret is still in the
  git history. Tell the person to rotate it. A manual `secret-file` row
  is not proven (see "Manual items").
- Before the first write, `apply` refuses a path with uncommitted changes
  (see "Commands"). Run `check` and `apply` on a tree where the person
  has committed or put aside their own edits, or get their agreement to
  `--allow-dirty`.
- `--all-auto` repeats its pass on the new plan, up to five times, until a
  pass changes nothing. So it can also apply automatic findings that the
  first pass creates, for example a `file-managed` row. Use it
  only when the person accepts that.
- `--all-auto` can remove the last copy of a content (see "Before you
  start"). Examine the scratch copies with the person first.
- After `--ids`, the next `check` can show new automatic findings that the
  first write made visible. Show them and ask again. Do not apply them
  without approval.
- When the report holds `tool-missing:refs/trueup`, say that the
  pre-commit entry (see "Lint and templates") runs `trueup lint`, so each
  commit fails in that entry until trueup is installed on this machine
  (see "Manual items"). The person installs first, or adds the entry
  later.
- Config writes (`--mode`, `--set`, a `config:*` id) write `trueup.toml`
  again in its fixed layout. They keep the values, but they drop the
  comments that a person added; the header line
  `# comments do not survive a config write; trueup writes this file`
  says so. Tell the person before such a write. The `run_date` stamp is
  not a config write: it edits only its own line and keeps the comments.
- `apply` writes only below `ROOT`. It refuses a path whose parent
  resolves outside `ROOT`, or whose last part is a symlink.

To record a mode or setting when no automatic id is approved, edit
`trueup.toml` by hand (see "Keep, ignore and protect"). Do not use
`--all-auto` for this.

## Lint and templates

A target keeps only `trueup.toml` (and, in copy mode, the checker pair).
`trueup lint` writes each tool config into a temporary directory at each
run, so the target holds no lint config of trueup (see
[trueup lint](../../docs/reference/trueup.md#trueup-lint)). A file that
the target owns, such as a pre-commit config or a CI workflow, comes
from `trueup template <name>` (see
[trueup template](../../docs/reference/trueup.md#trueup-template)).

1. Run `python3 "PLUGIN/trueup" lint --root "ROOT"`. Show each
   `trueup lint:` line to the person. A tool that is not installed did
   not run and is not verified, and the run exits 2. Ask the person:
   install the tool, or run `lint --skip-missing` and list the tool as
   unverified.
2. With TypeScript or Vue on, eslint needs its packages in the trueup
   cache. With a `strict` language, jscpd also runs from the trueup
   cache, and with SQL on, sqlfluff does too. `lint --install` installs
   all three (see `tool-missing:typescript/node_modules` in "Manual
   items").
3. Offer the pre-commit entry. `python3 "PLUGIN/trueup" template
   pre-commit` prints it:

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

   With no `.pre-commit-config.yaml` in `ROOT`, write this text there
   when the person agrees. When the file exists, show the entry, and the
   person merges it: never overwrite a file that has no trueup header
   (hard rule 6). The entry runs `trueup`, so trueup must be on the path
   of each machine that commits (see `tool-missing:refs/trueup` in
   "Manual items").
4. Offer the other templates only when the person asks or a finding
   names one: `ci`, `editorconfig` and the health pages. Write the text
   to the place that the person picks. The file is then the target's
   own, and no `check` row compares it with the template.
5. For the `managed-legacy` rows, follow
   [moving from the managed lint tree](../../docs/how-to/upgrade-trueup.md#moving-from-the-managed-lint-tree):
   put the pre-commit entry in place of the old local hooks, run
   `trueup lint`, then ask whether to remove the old files. Remove a file
   with `git rm` only when the person approves that path. Keep the eslint
   suppressions file and the pydoclint baseline: they are the target's
   own. `apply` never removes an old file.

## Saved plan and checkboxes

Two ways let the person approve ids at one time and apply them later,
with no new plan between. Use them when the person reads the report
outside this session, or when time passes between the report and the
approval. The rules are in
[the saved plan](../../docs/reference/trueup.md#saved-plan).

- **Saved plan.** Run
  `python3 "PLUGIN/trueup" check --root "ROOT" --json > "SCRATCH/plan.json"`.
  Later run
  `python3 "PLUGIN/trueup" apply --root "ROOT" --plan "SCRATCH/plan.json" --ids '<ids>'`
  (or `--all-auto`). Give `--mode` and `--set` in a plain `apply` call,
  not with `--plan`.
- **Checkboxes.** Run `check --out "SCRATCH"`. The person ticks boxes in
  `SCRATCH/trueup-report.md` (`- [ ]` to `- [x]`). Then run
  `python3 "PLUGIN/trueup" apply --root "ROOT" --from-report "SCRATCH/trueup-report.md"`.

Both refuse with exit 2 and write nothing when the tree changed since the
`check`. `--plan` also refuses when a saved automatic row does not hold
on the tree now: `unknown id <id>: the saved row does not hold on the tree now`,
also for a row that `--ids` does not name. Then run `check` again and ask
again. Never put the plan file or
the report inside `ROOT`: an untracked file there changes the tree. A
report from `check --changed` has no tree comment: save a full
`check --out` instead.

## Re-pin plan

A `refcheck` finding with `pinned section changed: <target>` can come
with a `repin:<path>:<line>` id in `## Re-pin plan` (see
[the re-pin plan](../../docs/reference/trueup.md#re-pin-plan)). A re-pin
only writes the new hash: it does not prove that the text still says what
the section now says. So read the section and the line that cites it with
the person first. Then apply the approved `repin:` ids with `--ids`.
`--all-auto` never runs a re-pin. When the id fails with exit 1, run
`check` again.

## Move plan

trueup reports first. `check` says which Markdown page sits outside
`docs/` (a `doc-misplaced` finding) and where it belongs (a `move:` id in
the move plan). `apply` moves a page only by a `move:` id that the person
approved. `--all-auto` never runs a move.

Which pages are candidates, the evidence texts, and how `check` picks a
target (`history`, then `link`, then `standard`) are in
[the move plan](../../docs/reference/trueup.md#move-plan) and
[where a page belongs](../../docs/reference/trueup.md#where-a-page-belongs).
A page under a Markdown-as-code directory (the default segments and
`[layout] code_dirs`), or an agent file with `name` and `description`
front matter and no `type`, is not a candidate. A page that a move
would break gets no row and no move: a page under a `change_log`,
`changelog`, `locale`, `content` or `_templates` directory, a page that
says it is generated in its first 5 lines, and a page whose directory a
file that is not Markdown names (for example a build script). A top
directory with more than 20 candidate pages is a content tree: one
`doc-tree` info row takes the place of its pages (see "Manual items").

`move:` ids exist only for tracked pages. An untracked page keeps its
`doc-misplaced` row, with the reason
`the page is not tracked; git add it, then run trueup check again`, and
gets no move. You do not run `git add` (hard rule 1): ask the person to
add the page, then run `check` again. In a shallow clone, a `standard`
target can hide a rename: its evidence ends with
`; history unavailable (shallow clone)`. Say that the history basis was
not available, and ask more carefully.

Run the steps in this order:

1. `check`. Show the plan and the move plan.
2. `apply --ids` with the approved automatic ids (or `--all-auto` when the
   person approves every automatic finding). This removes copies and junk
   such as `README.old.md`, which can change the evidence of a move.
3. `check` again. Show the move plan of this run. For each move, give the
   source, the target, the basis and the evidence, and ask: move it, keep
   the page where it is, or leave it for later. A `standard` target is
   trueup's guess: say so, and ask more carefully than for `history`.
4. `apply --ids` with the approved `move:` ids only, for example
   `--ids 'move:HOWTO-run.md,move:misc/design/'`.

After a move (see
[apply a move](../../docs/reference/trueup.md#apply-a-move)):

- `apply` rewrites the relative Markdown links that the move changes. It
  does not rewrite a protected file: it prints `left broken:
  <file>:<line>`. Tell the person.
- It prints `code mentions <source>: <file>:<line>` for each file that is
  not Markdown and still names the old path. It does not change code.
  Show these lines and ask before you change the code.
- When it exits 2 because a `move:` id is not in the current move plan,
  run `check` again and take the ids from that run.
- It does not commit. The moves show as renames in `git status`.

When a broken link has the hint `a file with this name is at <path>; fix
the link`, fix that link by hand: no move id fixes it.

A page that must stay where it is gets a `[[keep]]` entry with the id
`doc-misplaced:<path>` (see
[a page that stays](../../docs/reference/trueup.md#a-page-that-stays)).
`protect` alone is not enough: it stops the move, but the finding stays
in the plan with the evidence `protected`. When the person says that the
flagged pages are really agent, skill, prompt or template files in one
directory, offer `[layout] code_dirs` for that directory name rather than
one `[[keep]]` entry per page.

## Keep, ignore and protect

These keys have no `apply` flag. Edit `trueup.toml` by hand, and only
after the person agrees. Keep the key order of the file. Each key, its
values and its effect are in
[the trueup.toml keys](../../docs/reference/trueup.md#trueuptoml).

- `[[keep]]`: one block per declined finding, with `id` and `reason`. Use
  the exact id from the report. A keep id also keeps each finding whose
  id starts with the keep id and `:` (see
  [ids, lines and keeps](../../docs/reference/trueup.md#ids-lines-and-keeps)).
  So `refcheck:docs/a.md` keeps every checker row of that page, and
  `secret-content:app.py` every secret line of the file. Propose a
  shorter id only when the person wants to keep the whole group, and say
  that it also keeps later findings of that group. A keep that keeps
  nothing gives a `keep-stale:<id>` info row (see "Manual items").

  ```toml
  [[keep]]                     # a finding the person declined, with the reason
  id = "prose:docs/explanation/x.md"
  reason = "source document, text as received"
  ```

  A kept `prose:<path>` id leaves the row out of the plan, but
  `trueup lint` still runs Vale on that page: tell the person. A kept
  `refcheck:` id counts at once in global mode (in copy mode, see
  [copy mode](#copy-mode)).
- `ignore`: globs left out of the survey and all findings, for example
  `"tests/fixtures/**"` for fixtures that are wrong on purpose. `check`
  drops the `refcheck` findings on these paths from the first run, and
  `trueup lint` does not lint them. In global mode, `refs` and `lint`
  read the globs at each run (in copy mode, see [copy mode](#copy-mode)).
  Use `ignore` for a path that no check should read; for a page that
  stays a page, use `[[keep]]` or a `[layout]` switch.
- `protect`: globs that `apply` never changes or removes. A finding on a
  protected path becomes manual.
- `[root] allow`: root names beyond the base list. Propose it for a root
  file that a tool or a pipeline needs (for example `HANDOFF.md`).
- `[scratch] allow`: globs for names that only look like scratch, for
  example `"docs/notes.md"`.
- `[layout] code_dirs`: directory names (no `/`) that hold
  Markdown-as-code. A Markdown file under one of them, or under a default
  segment (`agents`, `claude`, `prompts`, `rules`, `skills`,
  `templates`), is not a `doc-misplaced` page. Neither is a file whose
  front matter has `name` and `description` and no `type`. Offer it when
  the person says a flagged directory holds agent, skill or prompt files.
  For one page, a `[[keep]]` entry is enough.
- `[binary] allow`: globs, matched on the path or the basename, that the
  `binary` and `large-text` rows let through. Offer it when the person keeps a binary on
  purpose and no page links to it.
- `[refs] mode`: `global` (the default) or `copy`. In global mode
  `trueup lint` and `trueup refs` run the checker that ships with
  trueup. Copy mode adds the checker copy and `ref_check.toml` to the
  target, so `python3 ref_check.py --root .` runs where trueup is not
  installed (see [copy mode](#copy-mode)).
- `[refs] path`: copy mode only. Where the target holds its copy of the
  checker. Leave the default unless the person asks. `refs.path` needs
  `refs.mode = "copy"` after the layers merge, so the mode can come from
  a profile.
- `[refs] local_tags`: the project's own comment-tag prefixes, for
  example `[refs] local_tags = ["X", "G", "P"]`, uppercase letters only.
- `[refs] law_archive`: the law archive of the `law:` references, a path
  relative to `ROOT` or absolute, for example
  `[refs] law_archive = "../laws/archive"`. This key is the one way to
  set a law archive. trueup renders it into the checker config as
  `[targets.law] archive`, at every tier. Offer it when the `refcheck`
  rows give `no-target` lines `target law is not configured`. The
  archive shape is in
  [Law references](../../docs/reference/trueup.md#law-references).
- `[refs] declared` and `[refs] id_forms`: the design pages and the id
  forms of the checker. Offer them when the `refcheck` rows give many
  `unknown-id` lines for ids that a page of the project declares, but
  not `ARCHITECTURE.md` of the docs directory. `[refs] declared` lists
  the pages as paths or globs relative to `ROOT`. A `..` segment can
  name a page outside `ROOT`. `[refs] id_forms` lists the id forms, for
  example `[refs] id_forms = ["D<n>.<m>", "D<n>.<m>.<k>", "I-<n>"]`. A
  name in angle brackets stands for digits, and each other character is
  literal. Do not write a regular expression. A page declares an id only
  in a heading, in the first cell of a table row, or in a bold lead.
  When a page is not there, for example in a clone that does not hold a
  page outside `ROOT`, the checker gives one `no-target` row for it and
  does not check the cited ids, so the run fails. Tell the person that
  each page must exist on each machine that commits.
- `[refs] accepted_reader_changes`: the names of the checker reader
  changes that fail now. A release that reads more of the source
  registers the change for one release. Until then the failures that it
  adds are warnings, and `check` gives one `refs-reader-change` row (see
  "Manual items"). Add a name only when the person agrees.
- `[[eslint.off]]`: one block per eslint rule to turn off, with `rule`
  and `reason`. Offer it only for a rule that flags normal code in bulk
  (for example `security/detect-object-injection` on numeric code), and
  only with a reason the person agrees to. `trueup lint` reads it at the
  next run; there is no file to apply. For one finding, the code gets a
  disable comment with a reason instead. A `[[eslint.off]]` list in
  `trueup.toml` replaces the list of the profile, so copy each entry of
  the profile that must stay.

  ```toml
  [[eslint.off]]
  rule = "security/detect-object-injection"
  reason = "numeric code indexes objects by computed keys; the rule flags each lookup"
  ```

- `[layout] front_matter`, `[layout] types` and `[layout] index`: each
  `false` turns off one group of page rules for every page under the docs
  directory, also a page added later: that is the cost.
  `[layout] front_matter = false` turns off `no-front-matter`,
  `bad-field` and `duplicate-id`; `[layout] types = false` turns off
  `misplaced`; `[layout] index = false` turns off `unindexed` and
  `no-index-link`. Propose the switch that fits when the pages keep fixed
  paths that the project's own tools read, or when a tool regenerates a
  page (front matter would be lost at each regeneration). Prefer one
  `[[keep]]` entry per page when the pages are few, because that keeps
  the rule for new pages. `[refs] layout` is the older key that sets the
  three switches at once, and one file cannot set it beside them: do not
  propose it.

Propose the other keys only when a finding or the person asks for one.
What each does is in
[the trueup.toml keys](../../docs/reference/trueup.md#trueuptoml):
`[layout] docs_dir` (the docs directory, default `docs`),
`[prose] banned` and `[prose] extra` (the banned list of the `prose`
row), `[refs] registry`, `[refs] comments` and `[refs] links` (checker
checks e, f and g), `[health] agents` (the `agents-missing` and
`claude-not-linked` rows), `[health] files = "readme"` (only
`README.md` of the health files), `[root] base` (the base list of root
names), `[scratch] gitignore` (the `.scratch/` line of `.gitignore`),
`stale_days = 180` (the age of a `stale` page), and
`[guard] registry` and `[guard] private_packages` (see "Hooks").
`version` and `run_date` are written by trueup: do not edit them.

### Copy mode

In copy mode (`[refs] mode = "copy"`), `refs` and the checker copy read
`ROOT/ref_check.toml`, not `trueup.toml`. `check` makes its checker
config from `trueup.toml` at each run, so it does not have this gap.

- Before the first `apply`, `ref_check.toml` does not exist, so the copy
  runs with every switch off.
- A change to `trueup.toml` after the last `apply` (a `[[keep]]` entry,
  an `ignore` glob, a `[refs]` or `[layout]` key) gives a
  `file-managed:ref_check.toml` finding. Apply it, and the checker
  copy's `file-managed` id when the report holds one. Until then the copy
  still fails on a kept line and still reads an ignored path, while
  `check` passes.
- Never edit `ref_check.toml` by hand, also not its `[scan] ignore`,
  `[registry]` or `[targets.law]` table: the file is managed, the edit is
  a `file-managed` drift finding, and the next `apply` drops it. To set a
  law archive, set `[refs] law_archive` in `trueup.toml`.
- To move a target from a copy to global mode, follow
  [the upgrade notes](../../docs/how-to/upgrade-trueup.md#upgrade-notes).

### Adopt an existing JS or TS codebase

When the eslint run of `trueup lint` fails on many old errors (often
jsdoc), offer the eslint bulk suppressions file (see
[the rule sets](../../docs/reference/trueup.md#rule-sets)). It freezes
today's errors, so eslint fails only on new ones. It does not cover
warnings: first fix them, or turn a bulk rule off with `[[eslint.off]]`.
The file is at the `[eslint] suppressions` path (default
`lint/typescript/eslint-suppressions.json`). `trueup lint` gives it to
eslint when it exists, and never writes it.

1. After the person agrees, make the file with eslint's `--suppress-all`
   option and `--suppressions-location <that path>`. The eslint config
   of `trueup lint` exists only while a run lasts, so in this release
   the command needs an eslint config of the person's own (see the
   reference page). Ask the person to run it, or run it with the config
   that the person names.
2. Tell the person to commit that file. trueup does not manage it.
3. When a fix makes a count too high, eslint fails with `suppressions
   left that do not occur anymore`. Prune the file with
   `--prune-suppressions` and the same config, and commit the smaller
   file. Do not add `--pass-on-unpruned-suppressions`.

## Manual items

Manual findings have `auto` false. Do only the approved ones. Write
plain, short sentences.

| Rule | What you do |
|---|---|
| `health-readme` | Write `README.md` (see the README items below). |
| `health-gitignore` | Write `.gitignore` for the languages of the survey. |
| `health-license` | Ask the person to add a licence file at the root: `LICENSE`, `LICENCE` or `COPYING`, in any case, with any extension. Do not pick a license and do not write the file. When the repository is private and needs no licence, offer `public = false` in `trueup.toml` (`apply --set public=false`): it drops this row and the README `License` check. |
| `health-changelog` | Adapt the text of `trueup template changelog`. |
| `health-contributing` | Adapt the text of `trueup template contributing`, or add a `## Contributing` section to the README. |
| `health-security` | Adapt the text of `trueup template security`. Ask the person for the contact address. |
| `health-code-of-conduct` | Adapt the text of `trueup template code-of-conduct`. Ask the person for the contact address. |
| `health-issue-template` | Adapt the text of `trueup template issue-template` into `.github/ISSUE_TEMPLATE/bug_report.md`. Any `.md` or `.yml` template in `.github/ISSUE_TEMPLATE/` satisfies the row; `config.yml` alone does not. |
| `health-pr-template` | Adapt the text of `trueup template pr-template` into `.github/PULL_REQUEST_TEMPLATE.md`. |
| `health-codeowners` | Ask the person who owns which paths, then write `CODEOWNERS`. |
| `agents-missing`, `claude-not-linked` | Tell the person. Do not write `AGENTS.md` or `CLAUDE.md`. |
| `readme-length` | Move sections of the README into pages under `docs/`, and link them from the README. |
| `prose` | Remove or rephrase each banned word the evidence names. If the page is a source document, or it quotes the banned list on purpose, propose a `[[keep]]` entry. |
| `changelog` | Fix the headings: `## [Unreleased]`, `## [x.y.z] - YYYY-MM-DD` in descending order, and only Added, Changed, Deprecated, Removed, Fixed or Security below them. |
| `superseded` | Add `superseded_by: <id>` with the id of the page that replaces it. Ask when you do not know it. |
| `stale` | Read the page and compare it with the code. Fix what is wrong, then set `last_reviewed` to today. Or ask whether it is superseded. |
| `scratch` (untracked) | Ask: delete the file by hand, move it under `.scratch/`, or add it to `[scratch] allow`. |
| `scratch` (tracked, `check the file`) | The name only looks like scratch (`docs/notes-2024.md`, `README.old.md`, `* copy.*`, `*.swp`), or the file is under `vendor`, `third_party` or `node_modules`. Read the file and show the person what it holds. Ask: remove it with `git rm`, give it a clean name with `git mv`, or add a `[scratch] allow` glob. Do not remove it without that answer. |
| `scratch` (`the last copy of this content`) | No other tracked copy of this content stays: the other copies are scratch or build output. So `apply` keeps this one. Ask: give this file a clean name (`git mv`), remove it by hand with `git rm`, or add it to `[scratch] allow`. |
| `artifact` (`holds <page>`) | The build directory holds a tracked page, so `apply` does not untrack it. Ask where the page belongs, move it out with `git mv`, then run `check` again: the `artifact` id is then automatic. |
| `refcheck` | Fix the reference that the checker names, then run `check` again. For an `unregistered` line (`marker not in the registry: X1`), ask whether the tag is the project's own; if so, add its prefix to `[refs] local_tags`. For a `no-front-matter` line on a page whose path is fixed, or that a tool regenerates, propose `[layout] front_matter = false` when there are many such pages, else a `[[keep]]` entry. A declined `refcheck` id goes into `[[keep]]` (in copy mode, see [copy mode](#copy-mode)). For a `stale-pin` line with a `repin:` id, see "Re-pin plan". For many `unknown-id` lines on ids that a page of the project declares, offer `[refs] declared` and `[refs] id_forms` (see "Keep, ignore and protect"). A `no-target` line `declared source not found: <entry>` names an entry of `[refs] declared` that names no file: ask whether the entry is wrong or the page is missing on this machine. |
| `refs-reader-change` (info) | This trueup reads more of the source than the last release, and the change `<name>` gives new checker failures. The evidence gives the count. For one release they are `warning:` lines, and the row changes no exit code. Run `python3 "PLUGIN/trueup" refs --root "ROOT"` to see each warning. Fix the markers that they name, because the next release fails on them. Add the name to `[refs] accepted_reader_changes` only when the person wants the checker to fail on them now. |
| `refcheck-run` | The checker itself failed (exit 2), so no `refcheck` row came. The evidence is the last line of its error output. Show it to the person, and run `python3 "PLUGIN/trueup" refs --root "ROOT"` to see the whole message. Fix the config that it names when the person agrees, or report a defect of trueup. |
| `keep-stale` (info) | A `[[keep]]` entry keeps nothing. Show it. Ask: remove the entry, or fix its id with an id from the report. A keep of an old line-numbered `secret-content:<path>:<n>` or `changelog:<path>:<n>` id is one of these: replace it with the new id, or with the `<rule>:<path>` prefix. |
| `drift-manifest` (info), `manifest-unreadable` (info) | trueup cannot read the manifest: a key that the drift rows read is not a table, or the file is not UTF-8. Tell the person. Fix the manifest only when they agree. |
| `tool-missing:typescript/node_modules` (info) | eslint needs its packages in the trueup cache, outside `ROOT`. Tell the person to run `python3 "PLUGIN/trueup" lint --root "ROOT" --install` one time on each machine. It uses the network, so run it only when the person agrees. The packages need Node 20.19, 22.13 or 24 or later. The same command installs jscpd (a `strict` language) and sqlfluff (SQL on) in the trueup cache. |
| `tool-missing:refs/trueup` (info) | `trueup refs` and the `trueup-lint` pre-commit entry need `trueup` on the path. Every commit on this machine fails in that entry until the person runs `uv tool install --editable PLUGIN` (or `pipx install PLUGIN`) one time, and the same on each machine that commits. Say this before you write the entry (see "Lint and templates"). Show the command from the action. Run it only when the person agrees: it adds a tool to their path. |
| `refs-copy:ref_check.py` (info) | Nothing runs this file. When its first line is the trueup header, or its docstring starts with `Check that each reference in the source matches its target`, it is trueup's old copy: ask, then `git rm ref_check.py`. Any other file with that name is the person's; leave it. `apply` never removes it. |
| `managed-legacy` (info) | An earlier trueup wrote this file, and `trueup lint` or `trueup template` now gives it. The row changes no exit code. Follow step 5 of "Lint and templates". Do not remove a file that the person did not approve. |
| `drift-flag` | Fix the doc, or add the flag to the argument parser. Ask the person which one is correct. |
| `drift-package` | Name the project's own package, or `.`, in an install line of the README. For Go, that is the `module` path of `go.mod` (`go install <module>@latest`, or a path below it such as `<module>/cmd/<name>@latest`). A URL whose last path segment is the package name also names it (`pip install git+https://host/owner/<name>`). |
| `drift-command` | Fix the doc so that it names a real path, script or target. An `info` row names a path that git ignores, or that the `Makefile` or a `package.json` script names: a build output, often correct. Ask before you change the doc. |
| `drift-undocumented` (info) | Tell the person. Document the flag, or ask whether it is dead code. |
| `duplicate` | Show both paths. Ask which to keep, or why both are needed. When the evidence says `the paths differ in one directory segment`, the two files can be variants on purpose, for example one for each platform or version. Ask the person. If they keep both on purpose, add a `[[keep]]` entry with their reason. Else keep one. |
| `doc-misplaced` | Show the move that the action names, with its target and basis (see "Move plan"). Ask: approve the `move:` id, or keep the page where it is with a `[[keep]]` entry and a reason. When the person says the page is an agent, skill or prompt file, offer `[layout] code_dirs` for its directory rather than `[[keep]]` for each page of it. With `protected` in the evidence there is no move, and you do not move a protected path: propose a `[[keep]]` entry. With `claimed by more than one page` there is no move either: ask where each page goes, move it by hand with `git mv` and fix its links, or add a `[[keep]]` entry. With `exists, move it by hand` a file or a directory is already at the target: show both, ask how to merge them or where the page goes instead, or add a `[[keep]]` entry. With `the page is not tracked` there is no move: ask the person to `git add` the page (you do not run it), then run `check` again. |
| `large-text` (info) | A text file over 1 MiB. The row changes no exit code. Tell the person. When the file stays on purpose, offer a `[binary] allow` glob to silence it. |
| `doc-tree` (info) | A directory outside `docs/` holds more than 20 pages, so trueup proposes no move for them. Tell the person. Do not move the pages. |
| `binary` | Ask: Git LFS, `.gitignore`, or keep. When the person keeps the file on purpose (screenshots, review evidence), offer to link it from a page by a relative path, or to add a `[binary] allow` glob. A linked file gets no finding. |
| `secret-file` (manual, key name) | trueup read 64 bytes and found no private key head and no public banner: a certificate after a label line, a Keynote `.key`, a DER key, or a file it cannot read. Do not open the file (hard rule 4). Ask the person to check it. When it holds a private key: untrack it with `git rm --cached`, add it to `.gitignore`, and tell them to rotate the key. When it does not, add a `[[keep]]` entry with the person's reason. |
| `secret-file` (manual, `.env`) | No secret pattern matched in the file, so trueup did not prove a secret. Do not open the file (hard rule 4). Ask the person whether it holds a secret. When it does not, add a `[[keep]]` entry with their reason. When it does, untrack it with `git rm --cached`, add it to `.gitignore`, and tell them to rotate the secret. |
| `secret-content` | Tell the person the file and the line (the `line` field; the evidence names each pattern on that line). Ask them to remove and rotate the secret. Do not open or print the secret. |
| `secret-engine` | gitleaks is on the path, and its run failed (a timeout, a start failure, an exit or a bad report). The evidence is the note. The built-in patterns ran in its place, so the secret scan is weaker. Show the note. Ask the person to fix the gitleaks run, then run `check` again. Add a `[[keep]]` entry only when the person accepts the weaker scan. |
| `secret-history` | Tell the person the file, the line and the commit. Ask them to rotate the secret. A history rewrite is their decision. Do not run it. |
| `lockfile` | Show the lock command that the action names. Run it only when the person agrees, because it can use the network. The person commits the lockfile. |
| `platform:branch-protection`, `platform:mfa`, `platform:least-privilege` (info) | trueup cannot read these platform settings. The rows are `info`: they never enter the plan and change no exit code. Show the person the `gh` command of the action, and the person runs it. Do not run `gh` yourself. When the person says the setting is in place, add a `[[keep]]` entry with the id (for example `platform:mfa:`) and a reason such as `MFA required, checked on <date>`. |
| `root-budget` | Propose moves or `[root] allow` entries. Moving files is the person's decision. |
| `file-managed` with no trueup header | Show the difference. The person merges it by hand. In copy mode, a checker copy with no header is the person's file (merge by hand) or an unedited copy from a trueup before 2026-10-07 (ask, `git rm` it, run `check`, apply the absent-copy error). |

Rules for the health skeletons:

- `trueup template <name>` prints each skeleton with no trueup header
  line. The action of the health row names the template.
- Replace each general sentence with facts of this repository: its setup
  command, its test command, its branch and review flow. Ask the person
  for facts you cannot read from the repository.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CODEOWNERS`
  and the pull-request template count at the root, in `.github/` or in
  `docs/`, the places that GitHub reads (see
  [GitHub community health files](../../docs/reference/trueup.md#github-community-health-files)).
  These names are on the base list of the guard hook, so a new root
  file with one of them gets no question. For any other new root name,
  the guard asks the person (see "Hooks").
- A root `SUPPORT.md`, `ACCESSIBILITY.md` or pull-request template gets
  no `doc-misplaced` finding: GitHub reads it there. Do not propose a
  move for it.

README items (the document standard, run by `ref_check.py`):

- The first text is a level 1 heading, then a description paragraph.
  Blank lines and an HTML block (a logo, an `<h1>`) can come before it.
- Level 2 sections `Install` (or `Installation`, `Quick Start`,
  `Quickstart`, `Getting Started`), `Usage` and `License`, with
  `License` last. With `public = false` in `trueup.toml`, `License` and
  the licence file are not checked.
- A link to `docs/README.md`, when that page exists.

Document pages under `docs/` (when the docs mode in force is `full`):

- Each page starts with front matter: `id`, `type`, `audience`, `status`,
  `last_reviewed`.
- `type` is `tutorial`, `how-to`, `reference` or `explanation`, and the
  page is in `docs/<type>/`. Choose the type from what the page does:
  teaches, gives steps, states facts, or gives reasons. Ask when a page
  does two of these.
- `audience` is one or more of `maintainer`, `agent`, `user`, as one
  value, a `[a, b]` list or a block of `  - item` lines. `status` is
  `draft`, `current` or `superseded`. `last_reviewed` is an ISO date.
- `docs/README.md` links each page.

## Verify

1. Run `python3 "PLUGIN/trueup" check --root "ROOT" --out "SCRATCH"`.
   Expect exit 0. If it exits 1, list each finding that stays in the plan
   and say why: not approved, failed, or new.
2. Run `python3 "PLUGIN/trueup" lint --root "ROOT"`. It runs what the
   `trueup-lint` pre-commit entry runs, on every surveyed file. Expect
   exit 0. If it exits 1, show the output of the tool that failed, and
   fix or report each problem.
   - Each tool that is not installed prints
     `trueup lint: <tool> is not installed; <label> did not run`, and the
     run exits 2. When the person agreed to skip those tools (see "Lint
     and templates"), run `lint --skip-missing`, and list the tools as
     unverified.
   - In global mode the checker reads `trueup.toml` at each run. In copy
     mode, apply a `file-managed:ref_check.toml` finding first (see
     [copy mode](#copy-mode)).
   - The Vale check does not read the comments of every language; `check`
     reads the others (see
     [the rule sets](../../docs/reference/trueup.md#rule-sets)).
   - eslint prints `trueup lint: eslint packages are not installed; run
     trueup lint --install` until the packages are in the trueup cache
     (see "Manual items"). With many old errors, see "Adopt an existing
     JS or TS codebase".
   - The clippy check denies its lints, so a crate that fails hides every
     crate that depends on it: the count grows after a fix. Say so when it
     fails. To show the full count before any fix, run its command one
     time with `-W` in place of each `-D`.
   - The strict ruff config ignores the `CPY` rules, because the comment
     standard rules out a copyright header. Do not add one to a file.
   - Strict Python runs `pydoclint` with no baseline unless the file at
     `[python] pydoclint_baseline` exists. trueup never writes that file.
     When the person wants one, show the command of the reference page;
     the person commits the file.
3. If `pre-commit` is on the path and `ROOT/.pre-commit-config.yaml`
   holds the `trueup-lint` entry, run `pre-commit run --all-files` in
   `ROOT`. `--all-files` checks the files that git tracks, so a new file
   that is not staged is not checked. Say so. If `pre-commit` is absent,
   say that the pre-commit entry is unverified.
4. Report: the score before and after, the ids applied, the manual items
   done, the kept ids with reasons, the unverified tools, and that nothing
   is committed. Give `git status --short` so the person can see the
   changes.

## Second run (trueup.toml in ROOT)

`trueup.toml` holds the modes, `public`, `tier` and `docs`. Do not ask the
question set again.

1. Run `check` as in step 1 of the first run.
2. Exit 0: the plan is empty. Say so, give the score, and stop.
3. Exit 1: show only the plan. Ask about each finding: apply, do by hand,
   or keep. Ask the mode question only for a new
   `config:languages.<lang>` finding.
4. Then do steps 5 to 8 of the first run.

On a repository that did not change since the last clean run, `check`
exits 0 and the plan is empty, and the checker of `trueup lint` passes
too, because it reads the kept ids (in copy mode, see
[copy mode](#copy-mode)).

## Scoped check

Use `check --changed` to check your own edits while you work, for example
before you finish a task. It does not replace the full `check`. Its scope
and the rows it skips are in
[the command line](../../docs/reference/trueup.md#command-line).

- The scope is every changed tracked file and every untracked file,
  also a file that was already changed before your session.
- It skips the health and setup rows, `refcheck` and each repo-wide
  finding, and it gives no score. So an exit 0 from `--changed` does not
  mean that the full `check` exits 0.
- It makes no move plan. Run the full `check` to get the `move:` ids.

## Baseline gate

A baseline lets a repository with many old findings adopt trueup. CI then
fails only on a new problem, not on each old one. Make a baseline only
when the person asks for one. The file, the keys, the ratchet values and
the gate rules are in [the baseline](../../docs/reference/trueup.md#baseline).

1. If a language is `clean` in `trueup.toml` and has tests, write its
   coverage report first, else the baseline has no `test` value for it.
2. Run `python3 "PLUGIN/trueup" baseline --root "ROOT"`. It runs the full
   `check`, then writes `ROOT/.trueup-baseline.json`. Tell the person to
   commit that file. You do not commit.
3. Run `python3 "PLUGIN/trueup" check --root "ROOT" --baseline --out "SCRATCH"`
   and expect exit 0. Exit 2 with `not a trueup baseline` means that the
   file is not valid: show the message, and make a new baseline only when
   the person asks. The gate fails only on a new finding key, a ratchet
   drop or a missing report. A score rise alone does not fail it: give
   the score as information.

To lock in lower counts later, the person can run `baseline` again. Run
it again only when `check --baseline` exits 0: `baseline` records each
current finding, so a new finding would become part of the baseline.

To gate CI, read `PLUGIN/docs/how-to/gate-ci-with-a-baseline.md`.

## Hooks

`hooks/hooks.json` runs four hook entries: `hook session` (on
`SessionStart`), `hook guard` (on `PreToolUse`), `hook interface` (on
`PostToolUse`) and `hook stop` (on `Stop`). There is no `SubagentStop`
entry, so a subagent that you start never gets the stop block; only your
own stop does. What each one does is in [the hooks](../../docs/reference/trueup.md#hooks).
Each hook finds its root from the working directory of the session, and
acts only when that root holds `trueup.toml`. A user default file does
not turn the hooks on. A `trueup.toml` that is not valid turns them off:
the `SessionStart` hook prints
`trueup: trueup.toml is not valid: <message>; the trueup hooks are off until it is fixed`.
Show it to the person, and fix the file when they agree. Below Python
3.11 the hooks stay silent. The Stop hook has a limit of 30 seconds;
after that time, the stop goes on with no check.

The hooks follow the session, not `ROOT` (see "Before you start").

The `SessionStart` hook prints the agent rules of the config in force:
the profile, the tier and the docs mode in force (with `tier = "auto"`,
the survey tier, and the mode that `config.resolve_docs` gives for it,
never the raw `auto`), the language modes, and the rules for docs,
comment markers, the root, scratch names and `trueup.toml`. The
Simplified Technical English line comes only under the profile `house`.
When `[refs] declared` is set, the design-id line names those pages, not
`ARCHITECTURE.md`.
The last line names the command to run: `trueup check` when `trueup` is
on `PATH`, else `python3 <launcher> check`. Follow them. trueup keeps no
rules file in the target.

The guard asks; it does not deny. When it asks about a new root file
whose name is not on its base list or in `[root] allow`, the person
decides. To stop the question for that name, propose a `[root] allow`
entry. When it asks about a new scratch-looking name outside `.scratch/`
(a `Write`, or a `git add` that the person runs), do not work around it.
Write the file under `.scratch/`, or ask the person to add the name to
`[scratch] allow`. A `Write` to a file that exists gets no question. The
guard sees only `Write` calls and `git add`: Bash writes (`touch`, `>`,
a heredoc, `mv`) are not seen. So never make a scratch file with a Bash
write to get past the question. The rule still holds, and `check` can
still report the file.

The install guard is off unless `[guard] registry = true`. When it is
on and denies a package, do not install it another way. Check the name,
or ask the person. When it asks, the person decides. When it gives a
`systemMessage`, tell the person that the guard did not check the
package. A package from a private index (an index option of the
install command, or a registry line in `ROOT/.npmrc`) gets no lookup;
for other private names, propose `[guard] private_packages` globs (see
[the install guard](../../docs/reference/trueup.md#hooks)).

When the interface reminder names a file, read `README.md` and the pages
under `docs/reference/`. Update them if the interface changed. If it did
not change, continue.

When `hook stop` blocks, fix each finding it lists. Do not add a
`[[keep]]` entry unless the person agrees (see "Keep, ignore and
protect"). Do not stop again only to get past the block: the hook does
not block a second time, so the findings stay. List each finding that you
cannot fix in your report. The `check --changed` command that the block
names can show more findings than the block: its scope also holds files
that were changed before the session.
