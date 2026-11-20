---
id: brief
type: explanation
audience: [maintainer, agent]
status: current
last_reviewed: 2026-11-18
---

# trueup brief

trueup checks a git repository for mess and helps a person remove it. It
has three parts that work as one tool:

- a written standard for documents and for code comments, with a lint
  rule set for each language;
- a hygiene check for the files of the repository: scratch files, build
  output, secrets, a crowded root and missing health files;
- a reference checker, `trueup/ref_check.py`, which proves the references
  between code, design documents and law texts.

A person runs trueup as the `trueup` command or as a Claude Code plugin
with a skill. This page states the problem, the goals, the limits and the
decisions taken.

## How to read this page

- This page is a record. A decision that a later one replaced stays in
  the text, marked "Superseded" with the date and the replacement.
- An id such as `D5.4` names a section of
  [the architecture](ARCHITECTURE.md). An id such as `S9` names a success
  criterion on this page.
- "The owner" is the maintainer of trueup.
- "The meridian check" is the reference checker. meridian is the project
  that the checker was part of before it moved into this repository on
  2026-10-03. That project is archived and is not public.
- A "target" is a repository that trueup checks.

## Problem statement

A repository's documents grow without a plan. The README says one thing,
the pages under `docs/` say another, and nothing links them. Each language
in the repository has its own lint habits, or none. A change to code or to
a document goes unreported, and a reader acts on the wrong text. The tools
to catch this exist for each language, but no one sets them up the same way
twice.

## Goals

1. **Documents.** One run of the skill on a repository makes its
   documentation readable, linked together, and conformant to the
   standard-readme specification or a stricter standard that this
   repository defines. It also puts each page, copy and junk file where
   the standard or the history of the repository says it belongs
   (D10.1). The research page
   [research-documentation](explanation/research-documentation.md) selects
   the standard.
2. **Code.** For each programming language in the repository, the skill sets
   up one of two modes. **Strict** installs the strictest reasonable rule
   set: cognitive complexity limits, function length, parameter count,
   nesting depth, duplication, dead code, and the full lint rule set, in the
   shape of a SonarQube quality profile. **Clean** installs the basic lint
   rule set. Both modes share one floor: a method that tracks all code and
   all documentation so that any change is caught. The research page
   [research-code-rules](explanation/research-code-rules.md) defines both
   rule sets per language. Superseded on 2026-11-02 by D15.37: no mode
   installs a file in the target since D14.6 (2026-10-16); `trueup lint`
   renders the rule set of each mode into a temporary directory at run
   time.
3. **Dead code.** Strict mode fails on unused code. The research page
   [research-dead-code](explanation/research-dead-code.md) decides whether
   graphify adds anything to the native tools.

## Success criteria

Each criterion is an outcome that one command or one observation can show.

- **S1. Report first.** A run of the skill on a repository writes a findings
  report with the proposed changes for each language and each document, and
  changes nothing until a person approves.
- **S2. Recorded modes.** After approval, the repository holds
  `trueup.toml` at its root with the mode of each language
  (`strict`, `clean` or `off`), the documentation level and the date of the
  run. A second run reads it and does not ask again.
- **S3. Installed checks.** After approval, the repository holds the lint
  configurations of the chosen mode, one pre-commit configuration that runs
  them, a `ref_check.toml` that matches the mode, in copy mode a copy of
  `trueup/ref_check.py` at the path the target's `[refs] path` key names
  (in global mode, the default, the hook runs `trueup refs` from one
  install on the machine, D9.1), and one CI workflow that runs the same
  commands. Superseded on 2026-11-02 by D15.37: since D14.8 (2026-10-16)
  the target holds only `trueup.toml` and, in copy mode, the checker
  pair; `trueup lint` is the check, and `trueup template` prints the
  pre-commit entry and the CI workflow.
- **S4. Document skeletons.** After approval, the repository has a
  `docs/README.md` index, front matter on each page under `docs/`, the root
  files that the standard requires, and a README with the sections in the
  standard order. `trueup refs --root .` reports zero failures with
  `layout` and `readme` on.
- **S5. Small code asks.** When a language has little code in the
  repository, the report asks before that language's checks are turned on.
  The research defines the threshold. The code lines are counted by tokei,
  or a built-in counter when tokei is absent.
- **S6. Prose lint.** Vale runs with a style that flags the banned
  vocabulary and a subset of ASD-STE100, on documents and on comments.
- **S7. Staleness.** A page whose `last_reviewed` date is older than the
  configured number of days is reported.
- **S8. Strict extras.** In strict mode, mutation testing and a dead-code
  gate run for each language that has a tool for them. Superseded on
  2026-11-02 by D15.28: decision 12 deletes the nightly job, so no rule
  set runs mutation testing; the dead-code tools of the strict rule sets
  (`vulture`, `knip`, `cargo machete`) still run in `trueup lint`.
- **S9. Self-check.** This repository passes its own standard: the checker
  reports zero failures, the lint commands pass, and the skill's report on
  this repository proposes no change.
- **S10. Eight languages.** Python, Rust, TypeScript and JavaScript, shell,
  SQL, Go, PHP and Vue single-file components each have a strict and a
  clean rule set.
- **S11. Comment standard.** One page states the comment standard for
  Python, Rust, TypeScript, shell and SQL. For each language, a fixture
  that breaks a rule fails the lint command that the page names. The
  corrected fixture passes.
- **S12. Suppression reason.** For each language, a fixture with a
  suppression that has no reason fails. The same suppression with a reason
  passes.
- **S13. Closed registry.** A fixture with a marker that is not in the
  registry fails.
- **S14. Id exists.** A reference to an id that is not in its target
  fails. This applies to a design target and to a law target.
- **S15. Marked files stay marked.** In a file where one unit has a
  marker, a unit without a marker fails. A file with no marker passes.
- **S16. Design to code.** A design id under `## Verification` that no
  test cites fails, unless an open `PLAN.md` row names that id.
- **S17. Drift.** A reference is pinned to version N of an act. A fixture
  archive holds version N+1. If the text of the cited section changed, the
  checker reports that site. If the text did not change, the checker
  reports nothing for that site.
- **S18. Zero failures at the start.** The checker exits 0 and prints no
  failure on a repository that has no marker.
- **S19. Self-check.** The checker passes on this repository. The example
  markers in its documents and fixtures cause no false failure.
- **S20. Old markers continue to work.** The selftest of the existing
  `arch:` checker passes without a change to that selftest.
- **S21. Edge file.** One run writes a machine-readable file with one
  record for each reference: source file, line, target and id.
- **S22. Document links.** Each relative link and fragment in `docs/`
  resolves. A link to a heading that does not exist fails.
- **S23. Convergence.** A tidy fixture repository is scrambled in the
  same ways as a real one: pages leave `docs/`, and copies and junk files
  come in. After `check`, `apply --all-auto`, `check` and `apply` of each
  approved `move:` id, its tracked files are equal to the tidy source,
  apart from the files trueup writes (D10.10).
- **S24. More mess never scores better.** Each single scramble operation
  gives a plan that is not shorter, and a score that is not lower, than
  the tidy repository (D10.10).

## What trueup has that the field lacks

The five claims below describe behaviour that is built today (D12.12).
The research page `explanation/research-comparable-tools.md` holds the
evidence for each.

1. A destination from history: the `history` basis of the locator reads
   `git log -M --diff-filter=R` renames.
2. Stable ids and the automatic-or-manual split: a finding has the id
   `<rule>:<path>`, a move has `move:<source>`, and `apply --ids` takes the
   ones you approve.
3. One plan for documents, comments and hygiene.
4. Convergence as an acceptance test (S23, S24).
5. Offline and deterministic: no hosted service, and no pull request.
   The install guard's registry lookup is off unless
   `[guard] registry = true` (D15.32).

## Non-goals

- No second checker. `trueup/ref_check.py` proves references; the language
  linters prove code rules; Vale proves prose rules. The skill sets them up
  and reads their output.
- No hosted service. Every check runs offline on the repository.
- No generated agent entry file. A person or a different tool writes
  `AGENTS.md` and `CLAUDE.md`; `trueup` only checks that they are there
  and linked (D5.4).
- No published package in the first version. A repository copies what it
  needs. On 2026-10-16 the profiles row below replaced the second
  sentence: a repository copies only `trueup.toml` (D14.8). Since
  2026-11-17 the command installs from the public git repository; it is
  not on PyPI.
- No check of meaning. The checker cannot prove that a test exercises the
  design section that it cites.
- No graph and no graph queries. The edge file of S21 is the only output
  for a graph.
- No automatic change of a pinned version.
- No machine-learning tool for comment decay.
- No new tool that extracts comments from all languages. Each language
  uses the linter that is already installed.
- No write to a different repository.

## Decisions taken

| Decision | Result |
|---|---|
| Home of the skill | `skills/trueup/SKILL.md`, in this repository as a Claude Code plugin (D5.10). |
| Apply mode | Report first, apply on approval. |
| Configuration | `trueup.toml` at the root of the target repository. |
| Installed items | `trueup apply` writes the lint configurations, a pre-commit configuration, `ref_check.toml` (with a copy of `ref_check.py` in copy mode, D9.1), a CI workflow, `.editorconfig`, an agent rules file, and the Vale style when `docs` resolves to `full` (D5.6). Each file has a minimum tier (D12.9). After approval, the skill writes the health files that have a skeleton under `trueup/templates/health/` (for example `CHANGELOG.md` and `CONTRIBUTING.md`) by adapting that skeleton. On 2026-10-16 the profiles row below replaced this row (D14.8). |
| Languages | Python, Rust, TypeScript and JavaScript, shell, SQL, Go, PHP, Vue. |
| Extras in scope | Prose lint with the banned-vocabulary list, a staleness check on `last_reviewed`, mutation testing in strict mode, a dead-code gate in strict mode. Superseded on 2026-11-02 by D15.28: mutation testing left with the nightly job (decision 12); the other extras stay. |
| Split from meridian | The comment standard, the document standard, the lint configurations and the research moved here on 2026-09-24. meridian keeps the checker, its design and its brief. |
| 2026-11-02 — The `minimal` profile on a target that is not adopted | The owner asked that trueup be safe to run on a stranger's repository. A target with no `trueup.toml` and no user default file runs the built-in `minimal` profile, and the report header says `profile minimal (no trueup.toml; pass --profile house for the house standard)`. `--profile` and `TRUEUP_PROFILE` win over it, and an adopted target with no `profile` key keeps `house`. This replaces the silent `house` run of the profiles row below, and amends D14.3 (D15.6). |
| 2026-11-02 — Score per covered file; the gate reads keys only | The `files` part of the score counts the surveyed files that a plan finding covers, not the findings. Before, one finding for a committed cache directory of 40 files added 40 files to the denominator, so more mess gave a lower score (S24). The baseline gate fails only on a new key, a ratchet drop or a missing report; it never reads the score, so a clean deletion no longer fails the gate. The score stays in the text and the JSON as information. This amends D6.7 (D15.21). |
| 2026-10-16 — Profiles and run-time lint configs | The owner asked for a universal tool that a target runs as an external command, with no copied files. The house standard is the built-in `house` profile; `minimal` is a second built-in profile, and a person can add profiles and a user default file under `$XDG_CONFIG_HOME/trueup/` (D14.1, D14.2). A repository copies nothing but `trueup.toml`, and, in copy mode, the checker pair. Tool configs are rendered at run time by `trueup lint` into a temporary directory (D14.6). The pre-commit entry, the CI workflow, `.editorconfig` and the health pages are templates that `trueup template` prints, and the agent rules are SessionStart text (D14.8 to D14.10). This row replaces the "Installed items" row and the non-goal sentence "A repository copies what it needs". |
| 2026-10-07 — Checker modes | The owner asked for one checker on the machine, not a copy in each repository. `[refs] mode` is `global` by default: the `ref-check` hook runs `trueup refs` from one `uv tool install --editable` of this repository. `copy` stays for this repository and for a target whose CI cannot install trueup (D9.1). |
| 2026-10-03 — Merge of meridian into trueup | The checker moves into this repository as the one source file, `trueup/ref_check.py`, run through `trueup refs`. The D2.1 map renumbers trueup's own design ids and the D2.2 map renumbers meridian's S-ids and D-ids on arrival. The meridian repository becomes an archived pointer. |
| Name | `trueup`, chosen on 2026-09-25. To true up is to bring a thing back into line. The name replaces `anti-slop` and the working name `repo-medic` of the [repository hygiene research](explanation/research-repo-hygiene.md#b2-naming). On that date npm, PyPI and crates.io had no package with the name. |

## Decisions from the research

The three research pages closed the open questions on 2026-09-24.

| Question | Decision |
|---|---|
| Which standard is "better than standard-readme"? | meridian's check i plus a `Contributing` section or file, and the community files: `LICENSE` required; `CONTRIBUTING`, `SECURITY` and issue templates recommended for a public repository. The section order of standard-readme is the template. Front matter, the index, a staleness rule, a prose lint and a thin `AGENTS.md` come on top. The rule list is in [research-documentation](explanation/research-documentation.md#proposed-rule-list). |
| Decision records? | Deferred. MADR pages as a fifth page type `decision` under `docs/decisions/` still need a change to the meridian check's layout check (check h) first; not part of this version. |
| Threshold for "small code asks"? | A language is present with at least one file and 50 code lines, counted by tokei, or a built-in counter when tokei is absent (D5.4). Below that, the report asks. |
| Threshold for staleness? | 180 days for `status: current`, none for `draft` and `superseded`. The number comes from `trueup.toml`. |
| Does strict mode run SonarQube itself? | No. Native tools with one uniform threshold table: cognitive complexity 15, cyclomatic 10, function length 60 lines, 5 parameters, nesting 4, duplication 3 percent. For function length, Python has 50 statements (ruff PLR0915) and no line limit, and shell and SQL have none (D15.28). |
| Does graphify take part in the dead-code gate? | No. The experiment gave zero precision. Native tools gate dead code. An optional `graphify extract --code-only` map, never a gate, is deferred: the trueup skill does not run graphify in this version. |
| Coverage gates? | Strict mode ships fixed gates (D5.5): for Python, 100 percent docstrings on public units (`interrogate`) and 80 percent line coverage in the nightly job; for Rust, 80 percent line coverage in the nightly job. Go's nightly job reports coverage with no gate. A ratchet from the current value in clean mode is deferred: it needs a coverage tool and a store for the ratchet value, and no task here installs a coverage tool. Superseded on 2026-11-02 by D15.28: no nightly job exists, so no line-coverage gate runs; `interrogate` still runs in strict Python, and the baseline ratchet (D6.6) reads a coverage report that the target writes. |
| Mutation testing? | Strict mode only, in the nightly job of the CI workflow (D5.5): `mutmut` for Python, `cargo mutants` on the diff for Rust, `stryker` for TypeScript and Vue, `infection` for PHP. Superseded on 2026-11-02 by D15.28: decision 12 deletes the nightly job; the owner can bring mutation testing back in a later round. |
| Runner? | pre-commit. Every hook is `repo: local` with `language: system`, so it calls the tool on the path (D5.6). The linters run with warnings as errors where they have the option, for example `eslint --max-warnings 0` and `clippy -D warnings`. Superseded on 2026-11-02 by D15.37: since D14.6 `trueup lint` runs the hooks of the rule sets itself; the one pre-commit entry, `trueup-lint`, runs `trueup lint` (`trueup template pre-commit`). |
| Near-duplicate documents? | Deferred, and the jscpd experiment ran (D12.5). jscpd 4.3.0 reported two pages that share 80 percent of their prose only with the format `markdown`. The strict configuration has no Markdown format, and `check` cannot start `npx` offline. So no row exists. The `duplicate` row (D5.4) finds an exact content match by hash; a shingled-Jaccard check is future work. |

## Decisions on the repository hygiene research

The [repository hygiene research](explanation/research-repo-hygiene.md)
proposed a larger tool than the goals above on their own. The owner closed
each open question below on 2026-09-25. The hygiene core the owner took in
runs as `trueup check` and `trueup apply`, next to the document and code
rules above; the rest stays out of this version.

| Question | Research proposal | Decision |
|---|---|---|
| Repository tiers? | Four tiers T0 to T3 by file count, packages and contributors. A tier sets the required files. A check above the tier is never a failure. ([B4](explanation/research-repo-hygiene.md#b4-adaptation-to-complexity)) | In scope. `trueup` picks T0 to T3 from the file count, the manifests, a workspace marker, the contributor count, a CI workflow and the tag count, or a `tier` override in `trueup.toml` (D5.4). The rule "a check above the tier is never a failure" holds for the managed files too: each managed file has a minimum tier, and no finding asks for a file above the tier or asks to remove a managed file. Below T2 with no `trueup.toml`, the setup files are one opt-in row, `setup:trueup.toml`. The default `docs = "auto"` gives `readme` below T2 and `full` from T2 (D12.9). |
| Root file moves? | Move tool configurations into the manifest, then `.config/`, then `.github/`, from a table of what each tool supports. ([A3](explanation/research-repo-hygiene.md#a3-root-directory-conventions-and-config-consolidation), [B5](explanation/research-repo-hygiene.md#b5-root-estate-policy)) | Split. Moving tool configurations is out of scope: they never move. `trueup` installs every lint configuration under `lint/<language>/` so it never grows the root estate (D5.5; since 2026-10-16, `trueup lint` renders them into a temporary directory and installs none, D14.6), and reports a crowded root as a `root-budget` warning (D5.4). Moving pages is in scope: a Markdown page outside `docs/` gets a `doc-misplaced` finding and a `move:` id in the move plan; it moves only when a person approves that id (D10.1, D10.6, D10.7). |
| Dead files, scratch files, build output? | Find them with a reference graph and remove them after approval. ([A6](explanation/research-repo-hygiene.md#a6-slop-taxonomy-with-detection-heuristics)) | Split. A scratch-looking name, a build or cache path, and a generated file each have their own row in scope, by name and content patterns, not a reference graph (D5.4). Finding a dead file by a reference graph stays out of scope; strict mode's own dead-code tool gates that per language. The `scratch` row removes a copy of a tracked file that has a scratch or copy name, by an automatic id (D10.3). |
| Slop score? | A weighted score from 0 to 100 and a CI gate on a regression. ([B8](explanation/research-repo-hygiene.md#b8-output-artifacts)) | Split. The score is in scope: five weighted categories, printed with every `check` (D5.7). A CI gate on it is out of scope; the report states the score is a proposal, not a measurement another tool has checked. |
| Agent hooks? | Claude Code hooks that block a new root file or a scratch file. ([B9](explanation/research-repo-hygiene.md#b9-hooks-and-continuous-mode)) | In scope. The guard hook denies a new, un-allowed root file and a scratch-looking write or `git add`; pre-commit stays the runner for the lint rule sets (D5.8). |
| Scheduled cleanup bot? | A weekly job that opens cleanup pull requests. ([B9](explanation/research-repo-hygiene.md#b9-hooks-and-continuous-mode)) | Out of scope. `trueup` reports and applies on request; it opens no pull request and runs on no schedule of its own. |
| Agent files? | The tool writes `AGENTS.md` and a `CLAUDE.md` that imports it. ([B8](explanation/research-repo-hygiene.md#b8-output-artifacts)) | Check-only. From T1, `trueup` warns when `AGENTS.md` is missing or `CLAUDE.md` does not link to it; it never writes either file. The non-goal stands: a person or a different tool writes them (D5.4). |
| Location of the configuration? | `.config/repo-medic.toml`, or a `[tool]` table in the manifest. ([B8](explanation/research-repo-hygiene.md#b8-output-artifacts)) | `trueup.toml` at the root (D5.3). |
| Community files? | A per-tier list of health files, with `.github/` as their home. ([A2](explanation/research-repo-hygiene.md#a2-community-health-and-supporting-files)) | In scope. The per-tier list in D5.4: README and `.gitignore` at every tier, a licence from T1 (at T0 when `public` is true), `.editorconfig` from T1 (superseded on 2026-11-02 by D15.37: no row checks `.editorconfig` since D14.8; `trueup template editorconfig` prints one), a changelog once tagged, a contributing guide from T2, the public-only files from T2 when `public` is true, and `CODEOWNERS` at T3. |

## Layout

One repository, run as a Claude Code plugin. The standard pages are under
`docs/reference/`, the research under `docs/explanation/`, and
`docs/README.md` is the index. `trueup lint` renders the lint
configurations of a target into a temporary directory at run time, so a
target holds no lint configuration of `trueup` (D14.6). The skill is
`skills/trueup/SKILL.md`, and the stdlib-only Python package it runs is
`trueup/` (D5.10). `trueup/ref_check.py`, run through
`trueup refs`, runs the document and comment checks on this repository.
