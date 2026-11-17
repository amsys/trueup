---
id: research-comparable-tools
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-10-08
---

# Research: comparable tools, and the plan for round 4

Six research notes, fetched on 2026-10-07, survey about 190 tools that
check, tidy, document or trace a repository. They sit outside this
repository, in the folder `Repo standardization tools vs trueup/` under
the owner's downloads: `ai_repo_agents.md`, `docs_comments_file_hygiene.md`,
`multi_linters_and_installers.md`, `repo_standards_checkers.md`,
`tidying_and_placement.md` and `traceability_and_compliance.md`. This page
keeps what matters for trueup: the facts, the ideas worth copying, the
ideas rejected, and the plan for round 4. Each fact names its note. A
claim the notes could not confirm from a primary source says so.

The state of trueup that this page measures against is round 3
(2026-10-08, uncommitted on `257ca52`): the organizer role (D10.1), the
move plan (D10.6), the `move` handler (D10.7) and the convergence tests
(D10.10). See the [brief](../BRIEF.md) and the
[architecture](../ARCHITECTURE.md).

## Summary

- **No surveyed tool does trueup's job as a whole.** Each note ends with
  the same gap: repository checkers test file presence, not document
  quality (standards note); meta-linters run tools but hold no rule of
  their own (multi-linter note); placement tools flag, rewrite or delete
  but do not say where a file belongs, apart from three LLM skills with no
  release history (tidying note); traceability tools key on ids but repair
  no path after a move (traceability note).
- **Four things trueup does that nothing surveyed does.** It proposes a
  page's destination from git history (`basis: history`, D10.6). It gives
  every finding a stable, readable id and splits automatic from manual
  action. It reports documents, comments and hygiene in one plan. It
  proves convergence with a metamorphic test (S23, S24).
- **Five precedents worth copying.** A saved plan that `apply` runs
  exactly (Terraform `-out`, OpenRewrite `rewrite.patch`, Nx
  `migrations.json`). A refusal to change a dirty tree (`cargo fix
  --allow-dirty`). Approval by checkbox in a report (Renovate dashboard).
  SARIF as the output format that CI platforms read. A command that
  re-pins a link on approval (Doorstop `clear`, tracey `bump`).
- **Six ecosystem moves to record.** repolinter archived on 2026-02-06.
  gitleaks is "feature complete", security patches only; MegaLinter moved
  to betterleaks. pydocstyle and darglint are archived; ruff and pydoclint
  replace them. unimported is archived; knip replaces it. Code Climate
  Quality is retired; Qlty replaces it. The hosted Allstar app is retired.

## 1. Where trueup sits, per note

| Note | Active tools | What the category does | What trueup does there | Gap the note names |
|---|---|---|---|---|
| AI repository agents | about 27 | Read a rule file as context; a few block with hooks (Claude Code `PreToolUse`, Codex `prefix_rule`); plan-then-approve as prose; fixes as PRs | Guard hook and Stop guard (D5.8, D6.3); report first, apply on approval; no PR | No machine-readable plan with per-item approval; no schema for document or comment rules |
| Documents, comments, file hygiene | 50 to 55 plus 4 aggregators | Per-tool linters with their own config; fix modes for formatters and spell-correctors; coverage gates only for Python and Go | Vale, ruff `D`, interrogate, revive `exported`, jscpd, the banned list, `last_reviewed` staleness, the `scratch` and `duplicate` rows | No single schema for a repository standard; SARIF is the shared output, not the shared input |
| Multi-linters and installers | about 20 | Trunk and Qlty: init, hooks, hold-the-line at line level; MegaLinter and Super-Linter: CI containers; cruft and Copier: template drift | `apply` writes lint configs under `lint/`, one pre-commit config, one CI workflow; changed-file scope (D6.17); baseline gate (D6.7) | No tool judges document or comment quality; no tool checks where files live; no "what would change and why" report except Renovate and Nx |
| Repository standards checkers | about 16 | File presence (repolinter, now archived; repo-review), security posture (Scorecard, Allstar, Legitify), IDP scorecards (Cortex, Port, OpsLevel) | Health rows per tier (D5.4), security floor against OSPS Baseline (D7.10), platform controls (D7.9) | All document checks reduce to "file exists" or "regex matches"; no plan artifact with an approval step |
| Tidying and placement | about 45 | Boundary enforcers flag; codemods rewrite with a dry run; dedupers delete by an ordering rule; three LLM skills propose a destination | The locator with three bases (D10.6); `git mv` plus a link rewrite (D10.7); automatic copy removal (D10.3) | No classic tool proposes "move X to Y"; none derives the target from git history; none approves moves by id |
| Traceability and compliance | about 22 | Id-keyed links between requirements, code and tests; licence headers (REUSE, license-eye); OSCAL on Markdown | The reference checker (D1 to D4): `ref:`, `arch:`, `law:`, pins on links, drift against a law archive | No tool repairs a path-based relation after a move; no interactive approval; the approval model is "check command plus git review" |

## 2. Findings that matter

### 2.1 Approval and apply models

- Only two agent-layer mechanisms block an action: Claude Code hooks (exit
  2, or `permissionDecision: deny`) and Codex execpolicy rules
  (`prefix_rule(..., decision="forbidden")` in Starlark under
  `.codex/rules/`). Rule files such as `CLAUDE.md`, `AGENTS.md` and
  `.cursor/rules/*.mdc` are context, not enforcement. The Claude Code
  memory page says so: "To block an action regardless of what Claude
  decides, use a PreToolUse hook instead." (agents note)
- A plan that is later applied exactly exists in Terraform (`plan -out`,
  "an opaque file" that `apply` consumes), OpenRewrite (`rewrite:dryRun`
  writes `rewrite.patch`; `failOnDryRunResults` fails CI when changes are
  pending) and Nx (`nx migrate` writes `migrations.json`, "No source code
  is touched yet"). No tool in the agents, tidying or standards notes has
  a plan with stable per-item ids. (agents, multi-linter, tidying notes)
- Terraform's `-detailed-exitcode` gives 0 for no change, 1 for an error
  and 2 for changes pending. trueup's `check` gives 0 for an empty plan, 1
  for a plan and 2 for a bad command or configuration. The shape is the
  same; only the numbers 1 and 2 are swapped. No change is needed, but the
  reference page should state the contract next to the Terraform one, so
  a CI author sees it at once. (agents note)
- `cargo fix` refuses to run on a dirty working tree unless `--allow-dirty`
  is given. trueup's `apply` has no such check. (agents note)
- Renovate's Dependency Dashboard is an issue with Markdown checkboxes; a
  ticked box approves one update. Dependabot groups updates into one PR by
  pattern. Moderne's dry run lists repositories with a "change reason" per
  file; the user selects repositories and then a commit strategy. Trunk's
  default `check` prompts per fix; ast-grep and comby prompt per match.
  Per-hunk approval exists only locally; in CI the unit is the PR.
  (agents, multi-linter, tidying notes)
- Maintainers push back on unverified AI changes: curl ended its bug
  bounty in January 2026 over "AI slop"; Godot and Blender maintainers
  called LLM PRs "draining and demoralizing"; GitHub shipped PR-limiting
  controls in February 2026. trueup opens no PR and runs on no schedule,
  which the brief already fixes as a non-goal. (agents note)

### 2.2 Agents and rule files

- `AGENTS.md` is the one cross-vendor convention, stewarded by the Agentic
  AI Foundation under the Linux Foundation, read by Codex, Jules, Cursor,
  Copilot, Factory, Augment, Devin, Amp and Claude Code (from v2.1.277,
  only when no `CLAUDE.md` exists in the working directory or above).
  CodeRabbit reads `**/AGENTS.md`, `**/CLAUDE.md`, `.cursor/rules/*`,
  `copilot-instructions.md` and more by default. trueup's health check
  (`AGENTS.md` exists, `CLAUDE.md` links to it) matches this. (agents note)
- Claude Code reads `.claude/rules/*.md` with an optional `paths:` front
  matter for path-scoped rules, and `/doctor prompt-audit` audits the rule
  files. Codex `/init` writes `AGENTS.md`. Both vendors call `/init` the
  nearest thing to "bring a repository up to standard". (agents note)
- No vendor has a schema for document, comment or layout rules; the field
  is prose. A rule file that trueup emitted would be read, as Markdown, by
  every agent. The brief's non-goal "no generated agent entry file" covers
  `AGENTS.md` and `CLAUDE.md`; it says nothing about a rules file under
  `.claude/rules/`. This is an owner question (Q3 below). (agents note)

### 2.3 Documents and comments

- Docstring coverage with a percentage gate exists for Python
  (interrogate, docstr-coverage `--fail-under`) and Go (revive
  `comments-density`, a minimum comment-to-code ratio). Rust measures it on
  nightly only (`rustdoc --show-coverage`) with no gate. TypeScript, Java
  and C have presence rules and "warnings as errors", which gate 100
  percent of the selected scope. trueup already runs interrogate in strict
  Python and revive `exported` and `package-comments` in both Go sets.
  (hygiene note)
- The Python stack has consolidated: pydocstyle, archived 2023-11-03,
  points to ruff; darglint, archived 2022-12-16, is replaced by pydoclint
  (0.11.0, 2026-10-02) and by ruff's preview `DOC` rules. pydoclint checks
  that the sections of a docstring match the signature, with a baseline
  mode. trueup's Python rule set has ruff `D` and no signature check.
  (hygiene note)
- Prose: Vale 3.24.0 adds `vale test`, a test runner for rules; `vale
  sync` now installs the package release that the running Vale supports.
  Harper (Automattic, Rust) is an offline grammar checker with an LSP,
  English only. write-good and alex are dormant. typos (crate-ci) is a
  spell-corrector with a fix mode and a low false-positive design.
  (hygiene note)
- Markdown linting converges on markdownlint's rule ids; rumdl (Rust)
  reads markdownlint config and has 85 rules with a fix mode. trueup runs
  no Markdown structure linter. (hygiene note)
- Orphan pages are a static-site feature: MkDocs
  `validation.nav.omitted_files` under `--strict`, Sphinx's toctree warning
  under `-W`. trueup's `unindexed` is the same check without a site
  generator. Freshness is displayed, not enforced, everywhere else; the
  one dedicated expiry tool, docdecay, last released in June 2020. trueup's
  `last_reviewed` staleness rule (S7) has no maintained peer. (hygiene
  note)
- Swimm is the one commercial product whose CI check fails when code
  coupled to a document changes. It is proprietary and has repositioned
  toward an "agentic context layer". trueup's pin on a link (D2.10) and
  drift against a law archive (D4.2) are the open equivalents. (hygiene
  note)
- CodeRabbit is the only review bot that acts on a document standard
  repository-wide: "generate docstrings" opens a follow-up PR. Every other
  bot comments or offers a one-click suggestion. (agents note)

### 2.4 Hygiene, duplicates and placement

- No surveyed linter has a named rule for committed `.DS_Store`,
  `Thumbs.db` or `node_modules`; the field prevents them with `.gitignore`
  templates. trueup's `artifact` and `scratch` rows are the only named
  detectors found. (hygiene, tidying notes)
- Dedupers pick the original by an ordering rule: rmlint `-S pOma` (first
  path, most hard links, oldest mtime, alphabetical), jdupes "first file
  in each set". None consults git history, so none can tell the copy with
  the richer history from the fresh one. trueup's `scratch` evidence `copy
  of <original>` and the last-copy rule (I-35) are stricter. (tidying
  note)
- Clone detection has no shared unit: tokens (PMD CPD), token and line
  pairs (SonarQube), structure (Qlty), percent (jscpd). jscpd 5 is a Rust
  binary with 224 formats; its README says Markdown files "are split into
  their embedded languages first". Whether it also compares prose blocks
  is not stated. The brief defers near-duplicate pages to a shingled
  Jaccard check; jscpd may already do the work. This is an experiment for
  round 4 (plan item B2). (hygiene, tidying notes)
- Git stores no rename metadata. `-M` re-derives renames by similarity on
  read (default 50 percent), and `--follow` works for one file. The
  history mining tools (git-who, hercules, code-maat, CodeScene change
  coupling) report ownership and co-change pairs and stop there. trueup's
  locator reads `git log -M --diff-filter=R` renames and is the only tool found
  that turns history into a destination. (tidying note)
- Three LLM skills propose destinations: "declutter" (a proposal document
  with a moves table, a delete table and a decisions table; "Always use
  git mv"), "reorg" (a local model reads content; "Nothing is ever moved
  without your approval"), and "relocate" (code units, not files). None
  shows a version, a date or a maintainer. (tidying note)
- Static-site tools keep path-derived identity and add redirects on a move
  (Docusaurus client redirects, Antora `page-aliases` with a redirect
  facility). Note tools either update links on rename (Foam, Dendron) or
  use a path-independent id (Zettelkasten). trueup rewrites relative links
  on a move; a page's `id` in front matter is already path-independent.
  (tidying note)
- Secrets: gitleaks (v8.30.1, 2026-03-21) is "feature complete", with
  security patches only; the maintainer moved to Betterleaks, and
  MegaLinter's REPOSITORY category now lists betterleaks, not gitleaks.
  trueup's secret engine (D7.3) calls gitleaks. (hygiene note)
- File hygiene tools: editorconfig-checker (7 properties, `-fix` for three
  of them), ls-lint (naming rules per directory in one YAML file, no fix),
  pre-commit-hooks 6.0.0 (31 hooks, 9 fixers). The note calls
  editorconfig-checker plus ls-lint "the closest thing to a declarative,
  language-agnostic file-level standard", and it covers formatting and
  naming only. (hygiene note)

### 2.5 Traceability

- All nine active requirements tools key links on an id, not a path, so a
  move breaks nothing by itself. What breaks is a path-based relation
  (StrictDoc `File`, Doorstop `references: path`) and a renamed id. Only
  StrictDoc documents a hidden machine id (MID) that matches nodes across
  renames. No tool uses git rename detection to repair a link. (traceability
  note)
- Two tools build a revision into the reference so a stale link is
  visible: OpenFastTrace (`req~name~1`; "Incrementing the revision voids
  all existing links") and tracey (`r[auth.login+3]`; `tracey bump`
  re-stages changed rules, and `tracey pre-commit` fails "if rule text
  changed without a version bump"). Doorstop stores a fingerprint per
  link and reports a "suspect link" when the parent changed; `doorstop
  clear` accepts it. trueup's `stale-pin` is the same signal; trueup has
  no command that writes the new pin, by design (I-8). (traceability note)
- Terminology differs by tool: "orphaned" and "uncovered" (OFT), "no
  links" and "suspect" (Doorstop), "dead link" (Sphinx-Needs), "orphan"
  (dependency-cruiser), "stale" and "unmapped" (tracey). trueup's
  `unindexed`, `broken-link` and `stale-pin` sit in that family.
  (traceability note)
- Licence headers are the one place where "law to file" exists: REUSE
  (`reuse lint`, `reuse annotate`, SPDX tags), license-eye and addlicense.
  trueup has a file-header rule (`no-header`) and no SPDX rule.
  (traceability note)
- The 2026 activity in this category is agent integration: OpenFastTrace
  ships a "Spec-driven Development Skill", tracey has `mcp` and `skill
  install`, Reqstool has `mcp`, compliance-trestle describes "agentic
  authoring" with a human in the loop. (traceability note)

### 2.6 Standards checkers and platforms

- repolinter (TODO Group), the one general open-source "required files"
  linter, was archived on 2026-02-06. Its default ruleset had 26 rules
  (licence, README, contributing, code of conduct, changelog, security
  file, CI integration, no binaries, licence headers) and ran fixes by
  default with `--dryRun` to disable. repo-review (Scientific Python) is
  the active successor, Python-centric, with checks as plugin classes.
  trueup's health rows cover the same ground per tier. (standards note)
- OpenSSF Scorecard v5.5.0 has 19 checks, each scored 0 to 10, weighted
  by risk. It "will now skip checks that don't apply to the current repo
  type" and reads rulesets when classic branch protection is
  inaccessible. The OSPS Baseline (v2026.08.28) is a standard with no
  checker of its own; trueup's security floor already cites it. trueup's
  CI template pins actions by commit hash and sets `permissions:`, which
  are the Pinned-Dependencies and Token-Permissions checks. (standards
  note)
- Fleet enforcement moved from bots to platforms: Google's
  sync-repo-settings shut down on 2025-08-05 and recommends Terraform; the
  OpenSSF-hosted Allstar app retired; GitHub rulesets import and export
  JSON; GitLab compliance pipelines are deprecated in favour of pipeline
  execution policies. trueup's platform controls (D7.9) sit on the
  platform side of that move. (standards note)
- The 2026 pattern for fixes in IDP scorecards is "scorecard failure, then
  a coding agent, then a PR" (Port's self-heal guide, OpsLevel's agent).
  Approval is the PR merge. No scorecard tool holds a plan artifact.
  (standards note)
- Three per-rule features worth noting: Cortex `effectiveFrom` dates a
  rule's start (a staged rollout of a standard); ArchUnit
  `FreezingArchRule` stores known violations in a committed text file and
  reports only new ones; Allstar's "repo override" gate decides whether a
  repository may weaken the central policy. trueup's `[[keep]]` entries and
  the baseline file (D6.6) are the first two; the third has no equivalent
  because trueup has no central policy. (standards, tidying notes)

### 2.7 Status changes, for the rule sets and the research pages

| Tool | Status on 2026-10-07 | Where trueup names it |
|---|---|---|
| repolinter | archived 2026-02-06; npm 0.12.0 (2025-05) | repository hygiene research |
| gitleaks | v8.30.1 (2026-03-21); "feature complete"; successor Betterleaks | secret engine (D7.3), rule sets |
| pydocstyle | archived 2023-11-03; use ruff `D` | code rules research |
| darglint | archived 2022-12-16; use pydoclint or ruff `DOC` | code rules research |
| unimported, depcheck, ts-prune | archived or dormant; use knip 6.40.0 | dead-code research, rule sets |
| Code Climate Quality | API disabled 2025-07-18; docs redirect to Qlty | repository hygiene research |
| write-good, alex | dormant since 2021 and 2023 | documentation research |
| husky | no release after v9.1.7 (late 2024); lefthook, lint-staged and pre-commit active | documentation research |
| Allstar hosted app | retired; self-host as a GitHub Action | security floor page |
| Sweep GitHub bot, Mentat | retired or archived | none |
| Grit | acquired by Honeycomb, April 2025 | none |

Round 4 marked these in the research pages that name them, in one
sentence each, so a reader does not install an archived tool (C2). The
kept source page `research-repo-hygiene.md` is left as received.

## 3. What trueup has that the field lacks

These are the claims the README and the brief can make, each backed by
one note's "gap" section.

1. **A destination from history.** The locator's `history` basis reads
   `git log -M --diff-filter=R` renames. The tidying note found no tool, classic or
   LLM, that derives a target from git history.
2. **Stable ids and the automatic-or-manual split.** Every finding has an
   id `<rule>:<path>`, and a move has `move:<source>`. The notes found
   per-item approval only as interactive prompts or as a whole-PR merge.
3. **One plan for documents, comments and hygiene.** The multi-linter and
   standards notes both say that no tool in their category judges document
   or comment quality, and none checks where files live.
4. **Convergence as an acceptance test.** S23 scrambles a tidy repository
   and proves the tree returns; S24 proves that more mess never scores
   better. No surveyed tool states an equivalent property.
5. **Offline, deterministic, no PR.** Every review bot and IDP scorecard
   is a hosted service that ends in a PR. The maintainers' complaints in
   the agents note are about that pipeline.

## 4. Ideas, ranked

The verdict column is one recommendation each. "Round 4" means the plan
below has it. "Ask" means the owner decides first (section 6). "Later"
means recorded here and not scheduled. "No" means rejected, with the
reason in section 5.

| # | Idea | Precedent | What it closes in trueup | Cost | Verdict |
|---|---|---|---|---|---|
| 1 | **Saved plan.** `check` writes the plan with the ids, the move targets and the identity of the tree it read (`HEAD` plus a hash of `git status --porcelain -z`). `apply --plan FILE` applies the ids of that file and refuses when the tree changed. | Terraform `-out`, OpenRewrite `rewrite.patch`, Nx `migrations.json` | I-35 across the passes of one `--all-auto` run (round 3, open item 10); L4, a mixed `--ids` that takes the target from the first `collect`; the check-then-apply gap between two sessions | medium | Round 4, A1 |
| 2 | **Dirty-tree refusal.** `apply` refuses when a path it would write, move or remove is dirty in `git status`, unless `--allow-dirty`. | `cargo fix --allow-dirty` | A person's unsaved edit lost under a `move` or a managed-file write | small | Round 4, A2 |
| 3 | **Checkbox approval.** The Markdown report lists each manual item as `- [ ] <id>`; `apply --from-report FILE` reads the ticked ids. | Renovate dashboard; "declutter" proposal tables | The person approves in the report they already read, with no id copying | small, after 1 | Round 4, A3 |
| 4 | **SARIF output.** `check --sarif FILE` writes the plan as SARIF 2.1.0; the CI template uploads it to code scanning. | markdownlint-cli2, revive, hadolint, jscpd, gitleaks, MegaLinter all emit SARIF; reviewdog reads it | Findings appear as PR annotations with no trueup-specific reader | small | Round 4, B1 |
| 5 | **Near-duplicate pages through jscpd.** Run the experiment: two pages that share 80 percent of their prose, through the jscpd that strict mode already installs. If jscpd reports them, a `duplicate-near` row (manual, warn) folds its output in. If not, the brief's deferred shingled-Jaccard check stays deferred. | jscpd 224 formats; the brief's deferral | The brief's "near-duplicate documents" deferral, at the cost of one row and no new algorithm | small experiment, then small or none | Round 4, B2 |
| 6 | **Re-pin on approval.** A `stale-pin` finding gets the id `repin:<path>:<line>`, manual. `apply --ids repin:...` writes the new pin. The checker stays read-only (I-8); `apply` is the writer, as it is for every other managed change. | Doorstop `clear`, tracey `bump` | The hand edit of an eight-digit hash after each reviewed section change | small | Round 4, B3 |
| 7 | **State the exit-code contract.** One table on the reference page: 0 empty plan, 1 plan, 2 bad input; next to Terraform's 0, 1, 2 so a CI author maps it. | Terraform `-detailed-exitcode` | A documentation gap only | tiny | Round 4, C1 |
| 8 | **Status notes in the research pages.** One sentence per archived or renamed tool in section 2.7, in the page that names it. | none | A reader installs gitleaks or pydocstyle as if current | small | Round 4, C2 |
| 9 | **Agent rules file.** `apply` writes `.claude/rules/trueup.md` (the standard in ten lines, `paths:` scoped to `docs/**`) and, when `.codex/` exists, a `prefix_rule` that forbids `git add` of a scratch name. | Claude Code `.claude/rules/`, Codex execpolicy | The guard hook protects Claude Code sessions only | small | Ask, Q3 |
| 10 | **pydoclint in strict Python.** Add pydoclint (Google style) to the strict Python set, so a docstring's sections match the signature. | pydoclint replaces darglint | A docstring that names a parameter that no longer exists | small; one more tool | Ask, Q4 |
| 11 | **Comment density for Go in strict.** revive `comments-density` with a minimum ratio. | revive | Nothing reported yet | tiny | Ask, Q4 |
| 12 | **Docs page naming rule.** A page under `docs/` has a kebab-case stem, as a `layout` kind. | ls-lint | Mixed `HOWTO-run.md` and `running.md` names, as target-rust shows | small | Ask, Q5 |
| 13 | **SPDX headers for public T2 and above.** `reuse lint` as a health row when `public` is true. | REUSE, license-eye | No rule today | small; one more tool | Ask, Q6 |
| 14 | **Markdown structure linter.** rumdl or markdownlint-cli2 in the docs set. | hygiene note | Trailing spaces, missing language on fences, heading levels | small; one more tool | Later |
| 15 | **A `FreezingArchRule`-style store for refcheck.** Already present as `[keep] failures` (D9.2). | ArchUnit | nothing | none | Done |
| 16 | **Scorecard-aligned CI.** Pinned actions and least-privilege permissions. Already present in the CI template. | Scorecard | nothing | none | Done |

### Round 4 records

- **Near-duplicate pages (idea 5, B2).** The experiment ran with
  jscpd 4.3.0. Two pages that share 80 percent of their
  prose were reported only when the run named the format `markdown`. The
  strict configuration of trueup has no Markdown format. `check` cannot
  start `npx`, because `check` runs offline (I-18). So no `duplicate-near`
  row exists, and the brief's deferral stays. The record is the only
  output of B2 (D12.5).
- **SARIF in CI (idea 4, B1).** `check --sarif FILE` writes the file. The
  CI step that uploads it to code scanning waits until trueup has an
  install source: today it has no remote and no tag. The step is recorded
  and not built.

## 5. Ideas rejected

- **Line-level hold-the-line.** Trunk and Qlty report only new issues per
  line. trueup's changed-file scope (D6.17) is per file. A line-level
  baseline needs a diff parser and a store per line; the baseline gate
  (D6.7) already stops regressions per key. The cost is not worth the
  gain for a tool that runs on a whole repository by design.
- **A central policy repository.** Allstar, safe-settings and Cortex keep
  the standard in an admin repository so a checked repository cannot
  weaken it. trueup's standard is the plugin itself, versioned with its
  code; a target can only `keep` a finding, with a reason that the report
  prints. That is the right gate for one owner with many repositories.
- **Opening PRs or running on a schedule.** The agents note's maintainer
  evidence (curl, Godot, Blender) argues against it, and the brief has it
  as a non-goal.
- **A cross-tool rule schema.** The hygiene note calls it the gap: "no
  single schema that expresses repo standard rules once and compiles them
  into each tool's config". trueup compiles its standard into eight lint
  configs already, from `trueup.toml` modes. Publishing that schema for
  other tools is a product, not a round.
- **A model that reads content to place a file** (the "reorg" skill). The
  locator's three bases are deterministic and testable; S23 depends on
  that.
- **Removing gitleaks now.** It still releases security patches. Record
  the successor (C2) and revisit when Betterleaks has a stable release and
  a `--redact` equivalent.

## 6. Plan for round 4

### Step 0: close round 3

Round 3 is uncommitted on `257ca52`. Its report,
`.state/report-trueup-round3.md`, lists open items H1, M1 to M4, I-35
across passes, and the traceability items. The owner decides H1 to M4,
the round is committed, and only then does round 4 start. Idea 1 (the
saved plan) is the fix for I-35 across passes and L4, so those two stay
open until A1 lands.

### Wave A: the plan as an artifact

- **A1. Saved plan.** `check --json` gains `"tree": {"head": <sha>,
  "status": <sha256 of git status --porcelain -z>}`. `apply --plan FILE`
  reads a `check --json` file, applies its automatic ids (with
  `--all-auto`) or the named ids (`--ids`), and refuses with exit 2 and
  one line when `tree` differs from the current tree. With `--plan`,
  `apply` does not re-collect between passes: the ids and the targets
  come from the file. Design section D12.1; invariant I-40: "the ids and
  targets that `apply --plan` acts on are those of the file, never of a
  new collect".
- **A2. Dirty-tree refusal.** Before the first write, `apply` lists the
  paths it will write, move or remove, and compares them with
  `git status --porcelain -z`. An intersection refuses the run with exit 2
  and the paths, unless `--allow-dirty`. Managed files that trueup wrote
  in an earlier run and the person did not edit are not dirty, so the
  common case passes. D12.2, I-41.
- **A3. Checkbox approval.** The Markdown report prints each manual item
  as `- [ ] <id>: <action>`. `apply --from-report FILE` reads the ticked
  ids and runs them as `--ids`. With a `tree` block in the report's
  front matter (A1), the same refusal applies. D12.3.
- Acceptance: S25, "a saved plan applies the same ids on a second machine
  or a later day, or refuses". The convergence fixture gains one case
  where the tree changes between `check` and `apply`.

### Wave B: outputs and one experiment

- **B1. SARIF.** `check --sarif FILE`. One `run`, one `rule` per finding
  rule with its severity, one `result` per finding with `ruleId`, the
  path, line 1 (trueup findings have no line) and the evidence as the
  message. The CI template uploads it with `github/codeql-action/upload-sarif`,
  pinned by hash. D12.4.
- **B2. Near-duplicate experiment.** Two pages, 80 percent shared prose,
  through `npx jscpd` with the strict configuration. Record the result in
  this page. If positive, a `duplicate-near` row, manual, warn, in `docs`
  (D12.5); the brief's deferral row changes. If negative, the deferral
  stands and this page says why.
- **B3. Re-pin.** `stale-pin` findings carry `repin:<path>:<line>`.
  `apply --ids repin:...` writes the pin of D2.10 step 3 for that link.
  I-8 holds: `ref_check.py` does not change. D12.6.

### Wave C: documents

- **C1.** The exit-code table on the reference page, with the Terraform
  mapping.
- **C2.** One status sentence per tool of section 2.7 in the research
  page that names it, and the gitleaks successor note on the security
  floor page.
- **C3.** The README and the brief state the five claims of section 3.
- **C4.** `SKILL.md` and the reference page describe `--plan`,
  `--allow-dirty`, `--from-report`, `--sarif` and `repin:`.

### Owner questions

- **Q1.** A1: is the saved plan the `check --json` file itself, or a
  smaller file with ids and targets only? Recommendation: the JSON file,
  one format fewer.
- **Q2.** A2: refuse on any intersection, or only for `move:` and remove
  actions? Recommendation: any intersection; a managed-file overwrite of
  a hand edit is the same loss.
- **Q3.** Idea 9: may `apply` write `.claude/rules/trueup.md` and a Codex
  rule? Recommendation: yes for `.claude/rules/`, because the non-goal is
  about the entry file; no for Codex until the owner uses it.
- **Q4.** Ideas 10 and 11: add pydoclint to strict Python and
  `comments-density` to strict Go? Recommendation: pydoclint yes, with a
  baseline on first run; density no, because `exported` already gates
  every public symbol.
- **Q5.** Idea 12: a naming rule for pages under `docs/`? Recommendation:
  not yet; target-rust keeps `HOWTO-run.md` on purpose, and a rename is a move the
  person must approve.
- **Q6.** Idea 13: SPDX headers for public repositories? Recommendation:
  later, with the public-only health files, when a public target exists.

### Done check for the round

```sh
python3 -m pytest -q -p no:cacheprovider
python3 trueup refs --root .
python3 trueup check --root . --json          # plan 0
```

Then the target-rust scramble of round 3 (the script `target-rust-scramble.sh` in the
owner's `.state/` directory, which git does not track) must give the
round-3 numbers or better: messy converges to tidy after the approved
moves, and the saved plan from the first `check` applies on the messy
clone with no re-collect.
