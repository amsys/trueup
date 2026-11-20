---
id: purpose-and-state
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-11-18
---

# Purpose and state of trueup

This page is a dated record. The maintainer wrote it on 2026-10-12, as a
critical review of trueup before it was public, and added a status
section after each later round of work. It says what trueup is for, what
the evidence of that date showed, and what plan followed.

## Read this first

Much of the text below describes a state that is in the past. The state
on 2026-11-18 is this:

- trueup is public at <https://github.com/amsys/trueup>, with the tag
  `v0.1.0a1`. The text below says "no remote, no tag" up to 2026-11-09;
  that is no longer true.
- CI runs on each push, on Python 3.11 and 3.14.
- The plugin is installed and in daily use on the maintainer's machine.
  Nobody else has confirmed an install yet.
- Each of the ten findings F1 to F10 has a later status below. Read the
  status sections, the newest last, before you rely on a finding.

Some words need an explanation:

- **The owner** is the maintainer of trueup.
- **A round** is one cycle of design, build and review. The rounds have
  numbers, and the design sections of a round share its number: round 14
  made sections D14.1 to D14.23 of
  [the architecture](../ARCHITECTURE.md).
- **`target-rust`, `target-mixed`** and similar names stand for private
  repositories of the maintainer that trueup ran on. Their real names
  are not given.
- **A path that starts with `.state/`** is a private work record of the
  maintainer. git does not track that directory, so a clone does not
  have these files. The paths stay in the text as a record of the
  source.
- **A commit id** from before 2026-11-17, such as `257ca52`, is in the
  maintainer's private history. The public history starts with one
  commit that holds the result of them all.
- **"This machine"** is the maintainer's computer.

## The page as written on 2026-10-12

Every number comes from a command that ran on this machine on that date;
the last section lists the commands. The page reads the working tree,
which holds round 3 and round 4 uncommitted on commit `257ca52`.

## Purpose

The README and the [brief](../BRIEF.md) describe trueup as a
documentation and code-comment baseline, a hygiene check, and a Claude
Code plugin that applies the baseline to any repository. That is the
stated purpose. The honest purpose is narrower and more useful to say:

1. **trueup enforces one house standard.** The standard is the owner's:
   Simplified Technical English, a banned-word list, pages under `docs/`
   with front matter and an index, a closed comment-marker registry, and
   one strict or clean lint rule set per language. The standard is an
   opinion, written down and made checkable. It is not a community
   standard, and no second maintainer has read it.
2. **trueup guards against agent residue.** Most of its rows exist
   because agents leave things behind: scratch files, copies, a crowded
   root, build output, secrets in a fixture, a page outside `docs/`. The
   hooks, the dirty-tree refusal and the "never commit" rule all follow
   from that. The target user is a person who runs agents on many
   repositories and wants each one to look the same the next morning.
3. **trueup is three merged projects.** The standard pages and the lint
   configurations came out of meridian on 2026-09-24. The meridian
   reference checker, `ref_check.py`, came in on 2026-10-03 as one frozen
   file. The hygiene rows came from the repo-medic research. The brief
   holds them together, but a reader meets three vocabularies: checks
   a to i, finding rows, and design ids D1 to D12.
4. **trueup is also the test bed of the owner's agent pipeline.** All 17
   commits are pipeline waves or rounds. Seven run directories with 66
   records sit under `.state/`. The repository builds itself with the
   tools it checks, which is a strength for dogfooding and a cost for
   anyone who reads the design.

In one sentence: trueup is the enforcement arm of one person's repository
policy, built by that person's agents, with one external adopter so far.

## State on 2026-10-12

| Measure | Value |
|---|---|
| Commits | 17, from 2026-09-24 to 2026-10-07; no remote, no tag |
| Uncommitted | 33 files changed, 6207 insertions, 15 new files (round 3 and round 4) |
| Package | 22 modules, 16,221 lines; `ref_check.py` alone is 2707 |
| Tests | 35 files, 19,078 lines, 1200 tests; one full run takes about five minutes |
| Design prose | `ARCHITECTURE.md` 4417 lines (245 KB), 107 design sections, 43 invariants |
| Reference and skill | `reference/trueup.md` 1104 lines (81 KB); `SKILL.md` 1004 lines (68 KB) |
| Self-check, working tree | `check` exit 0, plan empty; `refs` 0 failures, 1328 references |
| Self-check, clean checkout | score 3, one `agents-missing` warning (see F4) |
| Plugin | not installed in Claude Code on this machine; no `trueup` skill in a session |
| Adopters | `target-rust/src` (committed: `trueup.toml`, `ref_check.toml`, a pre-commit hook that runs `trueup refs`) |

## What the evidence confirms

- **Read-only means read-only.** `check` ran on two external repositories
  and `git status` had the same line count before and after each run
  (I-18).
- **The self-check holds on this machine.** `check` and `refs` both pass
  on the working tree. The one kept finding is the source document that
  quotes the banned list on purpose.
- **The test suite is large and green on an idle machine.** 1197 tests
  passed and 2 skipped for tools this machine lacks. The one failure is a
  wall-clock test that passes alone (F9).
- **One real adoption works.** target-rust/src runs `trueup refs` from the global
  install in its pre-commit hook, and the files trueup wrote there are
  committed in target-rust.
- **The research is real.** Four research pages and a 190-tool survey
  back the decisions. The comparable-tools page says where trueup sits
  and which claims are distinct. The five claims in the README match what
  is built.

## Findings

Ranked by what they cost the owner.

### F1. The plugin form is not in use

The README leads with the plugin: a skill and five hooks (`SessionStart`,
`PreToolUse` guard, `PostToolUse` interface, `Stop`, `SubagentStop`).
On 2026-11-02 D15.33 removed `SubagentStop`, so four hook events stay.
`installed_plugins.json` and `known_marketplaces.json` on this machine
name no trueup, and a session in this repository lists no `trueup` skill.
So the hooks and the skill have run only inside tests. The delivery that
people use is the command line, installed once with `uv tool install
--editable`, and the pre-commit hook. The product that the README
describes and the product that runs are not the same thing. That gap also
hides the cost of the hooks: the `Stop` hook on this repository takes 1.3
to 1.8 seconds (F9), and nobody has felt that in a session.

### F2. The locator treats Markdown-as-code as misplaced pages

`check` on `target-mixed/src` gives a plan of 143 items. 57 are
`doc-misplaced` and 51 of them are moves. The sources include
`claude/agents/python-reviewer.md`, `claude/skills/runner/build.md` and
their siblings: agent definitions and skill bodies, which are code that
happens to be Markdown. Three of the proposed targets collide ("claimed by
more than one page"). The candidate rule in `layout.py` exempts a dotted
segment and the basename `SKILL.md`, nothing more; target-mixed keeps its
agent files under `claude/` with no dot, so every one of them is a
candidate. On target-rust/src the dotted `.claude/` happened to protect the same
kind of file. The move plan is the feature the README names first, and on
the owner's main repository it is wrong 57 times out of 57.

The v2 field trial recorded 61 false positives for target-mixed/src and
said each shape was fixed. The organizer role of round 3 came after that
trial, so it never ran against this repository. Each round has added rows,
and each new row has found its false-positive class on a real target, not
in a fixture. Nothing today runs the local targets again after a round.

### F3. The binary row flags product screenshots

`check` on `target-rust/src` gives 52 items. 34 are
`binary:` warnings on PNG files of 100 to 200 KB under
`crates/app-flight/tools/shots/` and `.impeccable/review/`, each with the
advice "move the file to Git LFS, or add it to `.gitignore`". The rule is
a NUL byte in the first 8 KB of any file above 100 KB. For a UI project
these files are review evidence, referenced on purpose. The row has no
allow list, no type awareness and no per-tier threshold. Two thirds of the
plan on the one adopter is noise.

### F4. The self-check depends on files that git does not hold

`.gitignore` lists `/AGENTS.md` and `/CLAUDE.md`, because a generator
outside this repository writes them. A checkout that holds every tracked
and untracked file, but not the ignored ones, scores 3 with
`agents-missing: AGENTS.md is not on disk`. S9 ("this repository passes
its own standard") is true on this machine only. The managed CI workflow
in `.github/workflows/trueup.yml` would see that warning, but it has never
run (F5).

### F5. No remote, no tag, no CI run, no local git hook

The repository has no remote and no tag. The CI workflow exists and has
never run. `.git/hooks/pre-commit` does not exist, so the pre-commit
configuration that trueup wrote for itself enforces nothing on a commit.
The meridian README links to `github.com/amsys/trueup`, which does not
exist. The reference page has listed "a git source for trueup" under
Follow-ups since v2 (2026-09-29). Every self-check so far was a session
running it by hand.

### F6. The design prose outweighs the code it describes

The three normative texts total 394 KB: the architecture at 245 KB, the
reference at 81 KB and the skill at 68 KB. The package is 580 KB of Python
with `ref_check.py` and the tests 654 KB. By rule, the skill owns the
commands, flags, exit codes and finding rules, the reference page lists
them and the architecture designs them, so one change costs three edits.
The round 4 review found two places where the text and the code already
disagree (a `git log --follow` claim where the code runs `git log -M`, and
a stale docstring on the pass limit). The design ids are numbered by
round, D5 to D12, not by subject: to find the design of the move plan a
reader must know that it was round 3. The skill's front-matter description
is 1301 characters, which every session loads when the plugin is
installed.

### F7. Four days of work wait on twelve questions

6207 uncommitted insertions sit on `257ca52`. The resume record lists
twelve owner questions, six to close round 3 and six for round 4. Round 4
was then built on top of the uncommitted round 3, and reviewed, with the
commit still open. The next round would start three layers deep. The
process records that explain this live under `.state/`, which is ignored,
and `ARCHITECTURE.md` points at ten `.state/...` paths that a clone cannot
follow.

### F8. Complexity sits where the risk is

`ruff --select C901` at the strict threshold of 15 flags nine functions:
`apply.run` (20), the checker's `_check_g`, `_check_h` and `_check_i` (20
each), `layout._directory_moves` (18), `config._parse` (17),
`hygiene._declares_dependencies` (17), `ref_check.run` (17) and
`ref_check.main` (16). `apply.run` is the one function that writes to a
target. The checker file is excluded from `ruff format` and frozen by
I-26, which kept meridian's one-file rule. Inside a package that rule no
longer buys anything, and it keeps 2707 lines in one module.

### F9. One wall-clock test fails under load

`test_stop_on_this_repo_takes_under_one_second` asserts that the `Stop`
hook finishes in under one second on this repository. In two full runs,
each with other `check` runs on the machine, it took 1.17 to 1.83
seconds and failed. Alone, on an idle machine, it passed. The test is
not wrong about the hook; it is wrong about where a performance bound
belongs. A bound in the unit suite depends on the machine and on what
else runs, so a green suite needs an idle machine.

### F10. The one earlier adopter still runs the old copy

`target-mixed/src` holds a 2379-line copy of the meridian checker
and a `ref_check.toml` with no `local_tags`, and no `trueup.toml`. The
current checker is 2707 lines. Global mode (D9.1) exists because copies
go stale; the owner's main repository is the example. Its `check` today
reports 50 `refcheck` and 18 `file-managed` items for that reason, on top
of F2.

## What this page did not check

The author read the brief, the index, the README, the reference outline,
the field-trial section, the round 4 review and the candidate rule of the
locator, and sampled the rest. Nobody has read all 16,221 lines of the
package for this page. The secrets engine, the registry lookups and the
drift checker ran only through the test suite. The rule sets of the eight
languages were not run against a fixture here; gitleaks, eslint, sqlfluff
and jscpd are not on this machine, so their tests skip.

## Plan

The plan keeps to the findings above. Each step names its done-check.
The owner decides the order; the recommended order is the one below.

### P0. Close the open loop

Answer the twelve questions in `.state/runs/trueup-round3/RESUME.md`, or
decide to commit the work as it stands with the two MEDIUM items of the
round 4 review recorded as follow-ups. Then commit. No new round starts
on an uncommitted tree. Done-check: `git status --porcelain` is empty.

### P1. Run the local targets after every round

Add one script that runs `trueup check --json` on each local repository
in a list (`target-rust/src`, `target-mixed/src`, the four trial repositories that
still exist), counts the plan items per rule, and compares the counts to
the last stored run. It writes the counts to `.state/targets/<date>.json`
and prints each rule whose count grew. This is the cheapest way to catch
F2 and F3 before a review does, and it is what the field trial did once by
hand. Done-check: the script runs in under two minutes and reports the
two growths this page found.

### P2. Teach the locator what Markdown-as-code looks like

A Markdown file is not a page when any segment is in a small list
(`agents`, `skills`, `prompts`, `rules`, `claude`, `.claude`, `.github`,
`templates`), or when its front matter has `name` and `description` and
no `type`. Put the list in `trueup.toml` under `[docs] code_dirs` so a
target can extend it. One fixture copies the target-mixed shape. Done-check:
`check` on target-mixed/src gives zero `doc-misplaced` items under
`claude/`, and the convergence tests still pass.

### P3. Make the binary row ask before it warns

A binary file that a tracked page or README references by relative link
is evidence, not residue, and gets no finding. For the rest, raise the
floor to 1 MB below T3 and add `[binary] allow` globs. Done-check: `check`
on target-rust/src reports only the unreferenced screenshots, and the target-rust owner
agrees with each one.

### P4. Make the self-check true on a clean checkout

Either track `AGENTS.md` and `CLAUDE.md` in this repository, so the
generator's next run shows up as a diff, or let the health row read a
`[health] generated = ["AGENTS.md", "CLAUDE.md"]` key. The first is
simpler and is recommended. Done-check: a fresh clone scores 0.

### P5. Decide the delivery form, then live with it

Install the plugin on this machine and run it in two real sessions on
target-rust/src for one week, with the hook times recorded. If the hooks earn
their place, the README stays as it is. If they do not, the README leads
with the command line and the pre-commit hook, and the plugin becomes an
option. Replace the one-second assertion (F9) with a recorded timing that
the session report shows. Done-check: a dated note in the reference page
with the measured hook times and the decision.

### P6. Give the repository a remote, a tag and a hook

Push to a private remote, tag `v0.1.0`, install the pre-commit hook here
with `pre-commit install`, and let the CI workflow run once. Fix the dead
link in the meridian README. Done-check: one green CI run and a tag.

### P7. Cut the three-way duplication

Make `docs/reference/trueup.md` the one normative page for commands,
flags, exit codes, config keys and finding rules. The skill then links to
the reference for facts and keeps only the procedure: ask, classify,
approve, verify. Shorten the skill description to two sentences. Move the
round-numbered design sections under one `## History` heading and add a
subject index at the top of the architecture (checker, findings, apply,
hooks, layout, security). This is a long change and the last one, because
it does not change behaviour. Done-check: `trueup refs` still reports
zero failures, and one fact (the exit codes) appears in one tracked page.

### P8. Migrate target-mixed/src to global mode

Write its `trueup.toml` with `[refs] mode = "global"` and
`local_tags = ["D", "O", "K", "L", "S"]`, remove the checker copy, and
run `check`. Done-check: zero `refcheck` and `file-managed` items there.

## Status on 2026-10-14

The owner chose to run the whole plan. Each step and its result:

- P0: done. Round 3, its follow-up and round 4 are commit `d2eda7e`.
  The ruff format drift is commit `97678db`.
- P1: done. `scripts/check_targets.py` runs the six local targets in
  about 9 s. A baseline from commit `257ca52` shows `doc-misplaced` grow
  from 0 to 57 on target-mixed/src (F2). The `binary` count on target-rust/src was
  34 before round 3 too, so F3 is an old false positive, not a growth.
- P2: done (D13.1). target-mixed/src goes from 57 to 22 `doc-misplaced`
  items, none under `claude/`. The rest are pages or files that a target
  can name in `[layout] code_dirs`. The key is `[layout] code_dirs`, not
  `[docs] code_dirs`, because `docs` is a string key.
- P3: done (D13.2). target-rust/src is T3, so the 100 KiB sniff stays. None of
  its 34 PNG files is linked from a page, so all 34 stay. A
  `[binary] allow` entry in target-rust's `trueup.toml` is the target-rust owner's choice.
- P4: done. `AGENTS.md` and `CLAUDE.md` are no longer ignored. A copy of
  the tracked and untracked files, committed in a new repository,
  scores 0.
- P5: started. The plugin is installed at user scope on this machine.
  Each hook run writes its time (D13.4); `scripts/hook_times.py` reads
  the log. The first Stop run on this repository, with a dirty tree,
  took 1.36 s. The decision note waits for one week of sessions.
- P6: partly done. The pre-commit hook is installed here. The meridian
  README no longer links to the missing remote. The owner deferred the
  remote, the tag and the CI run.
- P7: partly done. The skill links to the reference page for facts and
  keeps the procedure: 39841 bytes from 67658, and a description of 392
  characters. The architecture has a subject index. The design sections
  stay in round order, because a move under a new heading changes every
  anchor that pages and pins cite.
- P8: partly done. target-mixed/src has a `trueup.toml` in global mode
  with `local_tags = ["D", "O", "K", "L", "S"]`, no checker copy, and
  `test.sh` runs `trueup refs`. 42 `refcheck` items stay: its markers
  also use `A`, `C`, `E`, `H`, `M`, `T` and `NOTHING`, and its
  `ref_check.toml` is not the managed one. 19 `file-managed` items stay
  until the owner adopts the managed lint and CI files.

## Status on 2026-10-16

The owner asked for a universal tool: it works on a tiny, a medium and a
huge repository, it holds no rule for one project, it is highly
configurable, and a target copies no helper file. Round 14 (D14.1 to
D14.23) does this. The work was in the working tree on that date; it is
commit `1b35435` now.

- The standard is data. The house standard is the built-in profile
  `house`, and `minimal` is a second built-in profile. A person can add
  profiles and a user default file under `$XDG_CONFIG_HOME/trueup/`.
  Fifteen new keys make the docs directory, the page rules, the banned
  list, the checker switches, the root base list, the agent rows and the
  `.scratch/` line configurable (D14.1 to D14.4).
- A target keeps only `trueup.toml`, and, in copy mode, the checker
  pair. `trueup lint` renders each tool config into a temporary
  directory at run time (D14.6, D14.7). `trueup template` prints the
  pre-commit entry, the CI workflow, `.editorconfig` and the health
  pages, and the agent rules are SessionStart text (D14.8 to D14.10).
  The old managed files get a `managed-legacy` info row only.
- Five defects of the public targets are fixed: the drift crash on
  cpython, the `-v<n>` scratch name of a docs page, HTML and `toc`
  anchors, the public `.pem` file, and the guard, which now asks about
  an unknown root file (D14.11, D14.12).
- The tier pick counts more languages, manifests and CI files, so a
  Maven project with GitLab CI is no longer T0 (D14.13).
- The three hot spots of the fastapi profile have a fix: a pre-filter
  for the banned words, one index for the scratch references, and a
  basename index for the link notes. `--changed` also narrows the
  hygiene and drift rows (D14.14).
- This repository removed its own old managed output, and its
  `.editorconfig`, CI workflow and pre-commit file are now its own
  (D14.8).

Open at this date: the skill and the README follow the code in the next
step. The last step runs the full test suite, compares `check --json` of
eleven targets with the reference output of the round (I-48), and
measures the Stop hook. Three gaps stay for the owner. No row checks
`.editorconfig` any more. `trueup lint` cannot create or prune the
eslint suppressions file, so a person runs eslint with a config of their
own for it. The how-to page `how-to/apply-trueup.md` still says that
`apply` installs a `ref-check` pre-commit hook.

## Status on 2026-11-02

Round 15 (D15) is the trust round: it makes trueup safe and honest on a
repository that never heard of it. Its work is in the working tree, not
committed. The updates to the findings and the plan:

- F1 and P5: still open. The plugin is installed and has run in real
  sessions since 2026-10-29. From that date to 2026-11-03 the hook log
  (`scripts/hook_times.py`) holds 8355 guard runs (median 0.001 s), 1359
  interface runs, 45 session runs and 2003 stop runs (median 0.005 s,
  95th percentile 1.01 s, maximum 1.94 s). The decision on the delivery
  form stays with the owner. The README now gives the plugin and the
  `trueup` command install side by side.
- F5: partly closed. The local git hook exists (`.git/hooks/pre-commit`).
  The repository still has no remote and no tag, so its own CI workflow
  has never run, and a CI runner of a target installs trueup from a
  clone path (see
  [gate CI with a baseline](../how-to/gate-ci-with-a-baseline.md)).
- F6: worse. The architecture is 362 KB (6540 lines), the reference is
  165 KB (2250 lines) and the skill is 61 KB (964 lines), against 820 KB
  of package Python. P7 cut the skill once; each round since added text
  to all three.
- F8: worse. `ruff --select C901` at 15 now flags eleven functions:
  `apply.run` (21), `config._parse_values` (25),
  `hygiene._declares_dependencies` (17), `layout._directory_moves` (18),
  `report.render_markdown` (16), `secrets.scan` (17), and in the checker
  `run` (17), `_check_g` (20), `_check_h` (21), `_check_i` (22) and
  `main` (18). The one-file checker rule stays (decision 14 of the round);
  the split is a question for the owner.
- The 2026-10-16 gap on the how-to page is closed: `how-to/apply-trueup.md`
  no longer says that `apply` installs a hook.
- The survey counts the old managed paths (`lint/`, `.editorconfig`,
  `.pre-commit-config.yaml`, `.github/workflows/trueup.yml`,
  `.claude/rules/trueup.md`) as the person's files (D15.37). Only
  `trueup.toml`, `ref_check.toml`, `.trueup-baseline.json` and
  `ref_check.py` stay out of the tier and the root budget. So the
  self-check of this repository counts `lint`, `.editorconfig`,
  `.github` and `.pre-commit-config.yaml` as root entries, and stays at
  tier T2, inside its root budget of 25.

The numbers of this section come from `wc -c` and `wc -l` on the three
pages, `cat trueup/*.py | wc -c`, the `ruff` command of the evidence
below, `python3 scripts/hook_times.py`, `git remote -v`, `git tag` and
`python3 -m trueup check --root . --json`, run on 2026-11-03.

## Status on 2026-11-09

Round 16 (D16) closes open items of the trust round and of the target-rust field
run. Its work is in the working tree, not committed. The updates to the
findings and the plan:

- F1 and P5: closed by owner ruling 5 of round 16. The hook log holds
  13,069 runs from 2026-10-29 to 2026-11-09. The owner keeps the plugin,
  and the README stays as it is. The times and the decision are in
  [hook times](../reference/trueup.md#hook-times-2026-11-09).
- The one-file checker rule (decision 14 of round 15) is closed: copy
  mode ships one file, so the checker stays one file (owner ruling 4).
  The complexity of the checker functions (F8) stays.
- target-rust: the checker can read a design that is on more than one page and
  uses other id forms (`[refs] declared` and `[refs] id_forms`, D16.2).
  The run on target-rust waits for the finish session of the round.
- Python 3.11: on 2026-11-12, the three tests that failed on 3.11 after
  round 15 passed under Python 3.11.15 (D16.1). The CI matrix has not
  run, because the repository has no remote (F5).
- The trust review found that a `house` run hangs on a tracked symlink
  to a FIFO (I-50). Round 16 routes those reads through bounded readers
  and adds tests (D16.10).

## Status on 2026-11-18

trueup is public as the alpha version 0.1.0a1. The updates to the
findings and the plan:

- F5 and P6: closed. The repository is at
  <https://github.com/amsys/trueup>. The public history starts with one
  commit, and the tag is `v0.1.0a1`, not the `v0.1.0` of the plan,
  because the version is an alpha. The CI workflow runs on each push, on
  Python 3.11 and 3.14: the lint hooks, `trueup check` on this
  repository, the test suite, a secret scan and a dependency scan.
- F4 and S9: the self-check now runs in CI on a clean checkout, so it no
  longer depends on one machine. `AGENTS.md` and `CLAUDE.md` are plain
  tracked files that a person edits.
- F1: the command installs from the public repository
  (`uv tool install git+https://github.com/amsys/trueup`). The plugin
  install from the public repository is not confirmed by a second person
  yet.
- F6 stays open. The architecture is 397 KB and the reference is 178 KB.
  The architecture now starts with a section that says how to read it,
  and [a tutorial](../tutorial/first-run.md) gives a new reader a
  shorter way in.
- The purpose stated above has one change. trueup is still one person's
  standard, but the `minimal` profile, user profiles and the keys of
  `trueup.toml` let a different person use a part of it or replace it.
  Reports from other people's repositories are the test that this
  version needs.

## Evidence

Commands that produced the numbers above, run from the root of this
repository on 2026-10-12:

```sh
git log --format='%ad %h %s' --date=short
git diff --stat | tail -1
git status --porcelain | grep '^??'
wc -l trueup/*.py tests/*.py docs/ARCHITECTURE.md docs/reference/trueup.md skills/trueup/SKILL.md
python3 trueup check --root .
python3 trueup refs --root .
python3 trueup check --root target-rust/src --json
python3 trueup check --root target-mixed/src --json
ruff check trueup --select C901 --config 'lint.mccabe.max-complexity=15'
UV_OFFLINE=1 python3 -m pytest -q
grep -c trueup ~/.claude/plugins/installed_plugins.json
```

The clean-checkout run copied every tracked and untracked file, but no
ignored file, into a scratch directory, ran `git init` and one commit
there, and then ran `check`.

Test suite results of the day:

- Full run, with two `check` runs on other repositories in parallel:
  1197 passed, 1 failed, 2 skipped, in 322 seconds. The failure is F9.
- The failed test alone, on an idle machine: 1 passed.
