---
id: baseline-research
type: explanation
audience: [maintainer, agent]
status: current
last_reviewed: 2026-09-20
---

# Universal Documentation and Code Comment Baseline — Layers 1, 2, 3

## TL;DR
- Layer 2 (the comment standard) is the true gap and has a clear best design: one page, one docstring format per language enforced by the linter already installed (ruff `D` with `convention`, clippy `missing_docs`/`undocumented_unsafe_blocks`, `eslint-plugin-jsdoc`+`@typescript-eslint/ban-ts-comment`, shellcheck+Google header, sqlfluff), plus a closed marker registry and a rule that every suppression carries a reason.
- Layer 3 needs almost no new code: the flat `arch_refs.py` design is sound and matches real prior art (Rust `compiletest //@ reference:` maps rule ids to tests; OpenFastTrace `[type->id]` tags). Use one marker grammar `ref: <target>/<id>`, keep tests-to-design and design-to-tests both ways, pin legislation by the lawsmu `key` (which already carries the version), and add a per-section `content_sha256` to the archiver for drift.
- The three layers join through stable ids. Ship the standard through the same channel that already builds `AGENTS.md` (the agent-configuration generator, from its core blocks), keep the checker opt-in per repository, and keep each check starting at zero failures.

## Key Findings
1. **A prior-art match exists for Layer 3.** The Rust project added, per rust-lang/compiler-team issue #783 (ehuss), a compiletest header "`//@ reference: destructors.scope.nesting`" and tooling to "collect these identifiers into a JSON file that the Reference tooling can use to generate coverage information" — modelled on Ferrocene's FLS annotations. First tags shipped in Rust 1.84.0 (PR #132376) and 1.87.0 (PR #137242); a public coverage matrix now lives at `doc.rust-lang.org/nightly/reference/test-summary.html`. This is the same shape as `arch:`, generalised. (strong)
2. **Check a (id exists) can be done by an installed link checker.** `lychee --include-fragments` checks anchor fragments in Markdown/HTML. If a marker is written as a relative link with a fragment (`docs/ARCHITECTURE.md#d1-7`), lychee proves the target heading exists — no new code for check a. It does not do check b or c. (strong)
3. **One docstring format per language maps to an already-installed linter with exact rule ids.** ruff `D` rules with `[tool.ruff.lint.pydocstyle] convention = "google"`; clippy `missing_docs` and `undocumented_unsafe_blocks` (the `// SAFETY:` convention); `eslint-plugin-jsdoc` for TSDoc/JSDoc; shellcheck plus the Google Shell Style Guide header; sqlfluff. (strong)
4. **Every linter in scope can demand a reason on a suppression.** ruff: `PGH004` bans blanket `# noqa` and forces a code; `RUF100` removes unused ones. typescript-eslint: `@typescript-eslint/ban-ts-comment` with `allow-with-description` and (recommended default) `minimumDescriptionLength: 3` — the strict config raises this to 10. eslint: `@eslint-community/eslint-plugin-eslint-comments` `require-description`. Rust 1.81+: `#[expect(lint, reason = "…")]` and clippy `allow_attributes_without_reason`. (strong/partial)
5. **Vale already lints comments in source code across languages via tree-sitter.** The `comment.line` / `comment.block` scopes and a `[formats] rs = md` mapping let the Layer 1 prose linter read comments too. So one prose linter covers docs and comments. (strong)
6. **Code–comment inconsistency is a measured, real problem.** Per Tan et al., "iComment: Bugs or Bad Comments?" (SOSP 2007, Purdue): "iComment automatically extracts 1832 rules from comments with 90.8–100% accuracy and detects 60 comment-code inconsistencies, 33 new bugs and 27 bad comments, in the latest versions of the four programs" (Linux, Mozilla, Wine, Apache); 19 (12 bugs, 7 bad comments) were confirmed by developers. Later work (Radmanesh, 2024, "Investigating the Impact of Code Comment Inconsistency on Bug Introducing Using an LLM Model," M.Sc. thesis, Univ. of Calgary, arXiv:2409.10781) found via GPT-3.5 + odds-ratio analysis that "inconsistent changes are around 1.5 times more likely to lead to a bug-introducing commit than consistent changes" (7-day window total odds ratio = 1.5195). This justifies a decay rule, not just style. (strong)
7. **Prompt injection through code comments is documented.** OWASP lists "code comments and documentation that AI coding assistants analyze" as an indirect-injection vector; measured work shows hidden-comment injection influencing agents. This makes the "no authorship claim" rule and a comment-content rule a security control, not taste. (strong/partial)
8. **Legislation ids are a solved design.** Akoma Ntoso `eId` uses a hierarchical, structural, human-readable id (`sec_4__subsec_2`), with `wId` retaining the old id after renumbering; legislation.gov.uk gives point-in-time URIs (`/id/{type}/{year}/{number}/section/{n}/{yyyy-mm-dd}`). lawsmu's `key` already encodes work+version. (strong)
9. **AGENTS.md is the cross-tool entry file; Claude Code reads CLAUDE.md and imports AGENTS.md.** Codex, Cursor, Copilot coding agent, Windsurf, Aider, Zed, Jules read AGENTS.md natively; Gemini CLI uses GEMINI.md unless configured. This confirms the baseline's entry route. (strong)
10. **Safety standards demand bidirectional traceability.** DO-178C §6.5 (Software Verification Process Traceability) requires bidirectional trace data across requirements, code and tests — Vector's DO-178C whitepaper states the section requires "bi-directional traceability between requirements and test cases, test cases, and test procedures and test procedures and test results"; ISO 26262 requires the same principle across all development phases (LDRA: "ISO 26262 also requires that this traceability is bidirectional… Part 4 also requires adherence to the principle of bidirectional traceability… common to all phases of development"). The "both ways" design of checks a/b + c is the accepted practice. (strong; exact table letters not verified against the copyrighted standard text)

## Details by research group

### 8.1 Layer 1 — one route for a person and an agent
- **Entry route (q1).** AGENTS.md is read natively by Codex CLI, Cursor, GitHub Copilot coding agent, Windsurf, Aider, Zed, Jules and more; Claude Code reads CLAUDE.md and the recommended pattern is a one-line import of AGENTS.md; Gemini CLI reads GEMINI.md unless set to read AGENTS.md. OpenAI Codex sets `project_doc_max_bytes` to a 32 KiB default (configurable in `~/.codex/config.toml`); combined instruction files beyond this are silently truncated. (strong) Route `AGENTS.md → docs/README.md → pages` is correct: keep AGENTS.md thin (build/test/convention facts + links), put depth in docs. Token cost is not published per tool; treat "each step's token cost" as unknown and control it by keeping AGENTS.md small.
- **Front matter (q2).** No agent tool is documented to parse arbitrary page front matter to pre-filter pages before reading. Cursor `.mdc` rules and Copilot `.instructions.md` use YAML front matter with `globs`/`description` for scoping, but that is for rule files, not doc pages. So front matter helps humans and your own tooling (and a future graph), not agent filtering today. (partial)
- **One form for both (q3).** Evidence favours one page with structure both can use: agents read the same Markdown humans do. The differentiator is stable ids and short sections, not a separate agent format. (partial)
- **llms.txt (q4).** `llms.txt` is a website-root file to guide LLMs to site content, per llmstxt.org: "We propose adding a /llms.txt markdown file to websites to provide LLM-friendly content. The file can be placed at the site root, or at any path within it, covering the pages under that path." It is not designed for inside a code repository; AGENTS.md fills that role. Use llms.txt only if you publish a docs site. (strong)
- **Section ids (q5).** Stable ids come from an explicit token in the heading, not the slug. Slugs break when titles change; numbers break on renumber. Akoma Ntoso solves this with `eId` (structural) + `wId` (retained old id). Recommendation: give design sections an explicit id token (`D1.7`) inside the heading so the id survives a title edit.

### 8.2 Layer 2 — comment structure
- **Docstring formats and linters (q6, q7).**
  - Python: PEP 257 defines docstrings; ruff `D` rules enforce, with `[tool.ruff.lint.pydocstyle] convention = "google" | "numpy" | "pep257"` (setting a convention force-disables incompatible rules). `interrogate` measures docstring coverage; its CLI help (v1.7.0) reads "-f, --fail-under INT | FLOAT  Fail when coverage % is less than a given amount. [default: 80.0]". (strong)
  - Rust: rustdoc `///` doc comments; clippy `missing_docs` (via `#![warn(missing_docs)]`), `missing_safety_doc` (public unsafe fn needs a `# Safety` section), and `undocumented_unsafe_blocks` which requires a `// SAFETY:` comment on every `unsafe` block. (strong)
  - TypeScript/JS: TSDoc is the spec; `eslint-plugin-jsdoc` (flat config `flat/recommended-typescript-error`) enforces presence and shape; `eslint-plugin-tsdoc` only checks TSDoc syntax conformance. (strong)
  - Shell: Google Shell Style Guide — "Start each file with a description of its contents" (top-level comment immediately after the hashbang); function header comments listing Globals/Arguments/Outputs/Returns; shellcheck is the linter. (strong)
  - SQL: sqlfluff is the linter; it supports `-- noqa` suppression. Docstring convention for SQL is weak/none — use a file header comment only. (partial)
- **File header (q8).** Practice measured in the agent-configuration repository (27/28 shell, 5/5 Python) already matches the Google guide's "start each file with a description." Make a short header mandatory; keep it to purpose + key facts, not author/date churn.
- **Where mandatory/optional/forbidden (q9).** Evidence-based sources: Ousterhout, *A Philosophy of Software Design* (Ch. 13) — "The guiding principle for comments is that comments should describe things that aren't obvious from the code," and, rebutting Martin, "Well-written comments are not failures. They increase the value of code…". Martin, *Clean Code* (Ch. 4) — "The proper use of comments is to compensate for our failure to express ourself in code… Comments are always failures." The synthesis both support: mandatory at module and public-API boundaries and at `unsafe`/non-obvious logic; forbidden when they restate the code. (strong)
- **Marker registries (q10).** OpenFastTrace uses `[covered-type->id~name~revision]` tags embedded in comments; Allure uses `@link`/`@issue`/`@testcase` decorators; PEP 350 catalogued codetags (rejected but a useful catalogue); Conventional Comments defines a `label [decoration]: subject` grammar for review comments. All define grammar + meaning + a tool. (strong)
- **Suppression reason (q11).** ruff `PGH004` (blanket noqa banned), `RUF100` (unused noqa); typescript-eslint `ban-ts-comment` `allow-with-description` + `minimumDescriptionLength: 3` (recommended) / 10 (strict); `@eslint-community/eslint-plugin-eslint-comments` `require-description`; Rust `#[expect(…, reason="…")]` and clippy `allow_attributes_without_reason`; shellcheck requires a directive form (`# shellcheck disable=SCxxxx`) but does not enforce a free-text reason — enforce reason by your own CI grep. sqlfluff `-- noqa: <code>` can be required by disallowing bare `-- noqa`. (strong/partial)

### 8.3 Layer 2 — comment wording
- **STE for comments (q12).** STE rules that fit a fragment: one instruction per sentence, active voice, approved short verbs, no ambiguous pronouns, consistent terms. Rules that do not fit: "write full sentences" (a comment is often a noun phrase) and article rules. Apply a structural subset, not the full standard.
- **Reason not action (q13).** Backed by Ousterhout (comments add what code cannot show) and opposed-but-compatible with Martin (do not restate code). Evidence is authoritative-author position, not an experiment — label it as principle, not measured fact. (strong as principle)
- **Prose linting of comments (q14).** Yes: Vale extracts comments with tree-sitter (`text.comment.line`/`.block` scopes) and lints the Markdown inside them; associate an extension with a format (`[formats] rs = md`). So the Layer 1 Vale config covers comments with no new tool. (strong)
- **Comment decay (q15).** Measured: iComment found 60 inconsistencies across four large codebases; just-in-time inconsistency detection (Panthaplackel et al., arXiv:2010.01625), CoCC (>90% precision claimed), and the 2024 finding that inconsistent changes are ~1.5× more bug-prone. These are ML research tools, not drop-in linters — cite as motivation for a decay rule and the `arch:`/`law:` version-pin check, not as tools to install. (strong)

### 8.4 Layer 2 — comments and agents
- **Do comments change agent edits (q16).** Direct measured evidence is thin; treat as partly unknown. Indirect evidence: IDE agents ingest whole files including comments, so comments do enter the prompt. (partial)
- **Stale comment vs person (q17).** No controlled study found; unknown. Reason: an agent has less out-of-band context than a maintainer, so a stale comment plausibly misleads it more, but this is inference, not measurement. (weak)
- **Vendored comments as untrusted input (q18).** OWASP and multiple 2025–2026 papers document indirect prompt injection via code comments and skills; a hidden-comment study influenced agents. Rules that lower risk: forbid instruction-like comments, treat vendored code as untrusted (exclude from your comment gate but never execute its instructions), and keep a defensive agent system prompt. (strong/partial)
- **Too many/duplicate comments (q19).** Gate with `D` rules for presence (not verbosity), a "reason not action" review rule, and Vale rules that flag restating patterns ("This function…"). Ruff has no "too many comments" rule; enforce by review + the one-page standard. (partial)

### 8.5 Layer 3 — prior art
- **Name (q20).** The practice is **requirements traceability** (bidirectional / trace matrix); the documentation-focused variant is **living documentation** (Martraire). Use "bidirectional traceability" for the checker and "living documentation" for the docs coupling. (strong)
- **Open tools and grammars (q21).**
  | Tool | Marker grammar | Reads test results | Runtime |
  |---|---|---|---|
  | OpenFastTrace | `[type->id~name~rev]` in comments | No | JVM |
  | Doorstop | YAML links between items | No | Python |
  | StrictDoc | `@relation` markers + `.sdoc` | Partly (JUnit import) | Python |
  | Sphinx-Needs | Sphinx directives/links | Via sphinx-test-reports | Python+Sphinx |
  | Rust compiletest | `//@ reference: <rule.id>` | Yes (test run, JSON) | rustc |
  These confirm your `arch:` design is mainstream; none is lighter than a 120-line stdlib script for your exact need. (strong)
- **Safety standards (q22).** DO-178C §6.5 requires bidirectional trace data (requirements↔code↔tests); ISO 26262 requires bidirectional traceability as a principle common to all development phases (Part 6 for software). This is exactly your "both ways" (checks a/b from tests→design, check c from design→tests). (strong; exact clause numbers per vendor whitepapers, not the copyrighted standard)
- **Stale-doc-on-code-change tools (q23).** Swimm (code-coupled docs, auto-sync, CI flags stale docs) and doctest (Python/Rust) keep docs executable. Swimm is commercial/SaaS and heavier than needed; doctest only checks runnable examples. (strong)

### 8.6 Layer 3 — identifier schemes
- **What makes an id stable (q24).** An explicit, structural token beats a slug or a content hash for identity: slugs break on title edits, pure sequence numbers break on renumber, and a content hash changes on any edit (so it is good for *drift*, not identity). Best: structural id for identity + content hash for change detection — the Akoma Ntoso `eId`/`wId` split. (strong)
- **arc42/MADR/C4 ids (q25).** MADR files are numbered (`0001-…md`); arc42 sections are numbered chapters; C4 has no id scheme of its own (Structurizr uses element names/keys). So Layer 3 must add explicit ids to design sections — the `D<n>.<m>` token — because these frameworks do not supply stable per-section ids. (partial)
- **Akoma Ntoso eId (q26).** `eId` is an Expression-level, hierarchical, structural id built from role abbreviations (`sec`, `subsec`, `subpara`, `para`, `list`, `point`) joined by `__`, e.g. `sec_4__subsec_2`. `wId` keeps the original id after renumbering. Work/Expression/Manifestation separate the act, a version, and a file. (strong)
- **Point-in-time URIs (q27).** legislation.gov.uk: identifier URI `/id/{type}/{year}/{number}/section/{n}`; point-in-time by appending a date `/section/8/2015-03-27`; `/enacted` for original. ELI and USLM are parallel schemes. (strong)
- **Smallest change for lawsmu (q28).** lawsmu already has `key = "acts/Income_Tax_Act/v13"` (work+version) and section headings `### <num>. <title>`. The smallest id is `<key> s.<num>` (e.g. `acts/Income_Tax_Act/v13 s.111`) — exactly the brief's proposed `law:` form. Add only a per-section hash for drift; no subsection ids needed yet.

### 8.7 Layer 3 — mechanism
- **Installed tool for check a (q29).** Yes — `lychee --include-fragments` proves an anchor target exists if markers are written as relative links with fragments. This removes the need for custom code for check a on the architecture target. For the law target, a link into the lawsmu Markdown anchor works the same way. Caveat: lychee's slug algorithm can differ from a site renderer; run it against the same Markdown it will resolve. (strong)
- **Smallest cross-language marker (q30).** A comment line beats a docstring/decorator/attribute because every language has a line comment and shell/SQL have no docstrings. Use a comment line with a fixed prefix; keep the docstring form for Python tests where it already works.
- **Regex vs parser (q31).** A line regex is enough to *find* markers and ids in every language and needs no dependency (matches your stdlib-first rule). A parser is only needed to know *which construct* a marker attaches to (function vs block) and to avoid matching a delimiter inside a string literal. Vale/tree-sitter already solves the string-literal problem for prose; for id existence, regex is sufficient. Recommendation: regex for extraction, Python `ast` for the Python test case you already have.
- **Extend to production code (q32).** Checks a (id exists) and the version/drift check make sense in production code. Check b (marked files stay marked) makes sense per-file. Check c (every verification claim has a test) stays test-only, because production code is not the proof.

### 8.8 Layer 3 — drift and versions
- **Pin the version (q33).** Pin, because lawsmu `key` already carries the version (`/v13`). Resolving to "current" hides amendments. Cost: each new Act version makes pinned refs "behind"; that is the signal you want — the drift check lists exactly those sites. Do not auto-bump.
- **Hash unit (q34).** The section is the correct unit for lawsmu today (headings stop at section; subsections are unanchored list items). Sentence-level is too fine and noisy; whole-document (the existing `content_sha256`) is too coarse to name a site. Add a per-section hash.
- **Rules-as-code (q35).** OpenFisca attaches a `reference` (legislative URL) to each variable and dates each parameter value; Catala puts statute text and code in one literate source. Both keep code in step by tying each rule to a citation. Your `law:` marker is the OpenFisca `reference` pattern made checkable.

### 8.9 Layer 3 — LLM failure modes
- **Invented id caught, what escapes (q36).** Check a catches an invented id. It does not catch: an invented *claim* about a real id (check d "meaning" — not built), invented prose in a docstring, or a plausible-but-wrong citation to the wrong section. (partial)
- **Cite-but-prove-nothing (q37).** No cheap static check proves a test exercises the cited design. This is the known "no check of meaning" limit. A cheap proxy: require the test to name the id AND to assert something (lint for asserts), but this is weak. A full solution needs mutation testing or human review. (partial)
- **Agent removes markers to pass (q38).** The per-file rule (check b) resists this: removing one marker breaks the file's "all-or-none." Additional guard: keep the `## Verification` list under review so check c fires if a claim loses its test; and protect the design file in review.

### 8.10 Graph
- **Graph value (q39).** Queries with real value beyond the flat checker: "which functions depend on Income Tax Act s.111" and "shortest path from a changed section to a test" — these need transitive, cross-repo edges the flat checker does not hold. "Which tests prove D1.7" and "which sections have no test" are already answered by checks a/c. So the graph adds value mainly for the legislation-impact and cross-repo cases.
- **graphify external edges (q40).** Unknown. No public evidence found that the user's `graphify` reads `arch:` markers or imports external edges. Treat as unknown until the local tool is read. Recommendation: emit markers to a small JSON side-file (like Rust compiletest's JSON) so any graph can import edges without parsing source.

## Decision list (section 10)

**Layer 1**
1. **Entry route.** Options: (a) `AGENTS.md → docs/README.md → pages`; (b) a bespoke index. Trade-off: (a) uses the file every agent already reads and keeps one source of truth; (b) costs maintenance and is unread by default. **Default: (a).** *Clear best answer.*
2. **Front matter fields.** Options: (a) `id, type, audience, status, last_reviewed`; (b) none. Trade-off: fields help humans and your own tooling/graph filter, but no agent tool parses them today, so they cost a little discipline for future gain. **Default: (a), small set.** *User must choose* (cost vs future value).
3. **Design-section ids.** Options: (a) `D<n>.<m>` everywhere; (b) per-repo scheme. Trade-off: one form makes the checker and graph uniform; a per-repo form fits local history but breaks cross-repo queries. **Default: (a).** *Clear best answer.*

**Layer 2**
4. **Home of the standard.** Options: (a) a core block generated into each `AGENTS.md`; (b) a skill; (c) a `docs/` page. Trade-off: (a) reuses the existing distribution channel and reaches every agent; a skill/page needs its own sync. **Default: (a) block, with the skill importing it.** *Clear best answer.*
5. **Docstring format per language.** Options: Google vs NumPy vs pep257 (Py); rustdoc; TSDoc; Google shell; SQL header. Trade-off: Google is the most tool- and human-readable and ruff supports it; NumPy suits scientific code. **Default: Google (Py), rustdoc, TSDoc, Google shell, file-header-only SQL.** *Clear best answer* (except NumPy for a data-heavy repo — then *user must choose*).
6. **File header.** Options: (a) mandatory short header; (b) optional. Trade-off: practice is already ~consistent; mandatory costs one line, optional lets it rot. **Default: (a), purpose + key facts, no author/date.** *Clear best answer.*
7. **Content rule wording.** Options: (a) "Write the reason, not the action"; (b) longer rubric. Trade-off: (a) fits one page and memory; (b) is precise but unmemorable. **Default: (a) with one good/bad example per language.** *Clear best answer.*
8. **STE for comments.** Options: (a) structural subset + script; (b) advice only. Trade-off: a script gates objectively but must start at zero failures; advice is free but unchecked. **Default: (a) subset checked by Vale on comment scopes.** *Clear best answer.*
9. **Marker registry.** Options: (a) closed list with a check; (b) open list. Trade-off: closed is checkable and resists invented markers; open is flexible but ungovernable. **Default: (a) closed.** *Clear best answer.*
10. **Suppression reason.** Options: (a) reason mandatory; (b) not. Trade-off: mandatory reasons are enforceable in every linter here and aid review; optional is easier day one. **Default: (a) mandatory.** *Clear best answer.*
11. **Enforcement model.** Options: (a) one native linter per language; (b) one cross-language comment extractor. Trade-off: native linters are installed and precise; a single extractor is uniform but new code. **Default: (a) native linters + Vale for prose across all.** *Clear best answer.*
12. **Zero-failure adoption.** Options: (a) per-file opt-in like check b; (b) blanket. Trade-off: (a) starts at zero and grows; (b) fails thousands on day one and gets deleted. **Default: (a).** *Clear best answer* (core lesson of the 1509-failure measurement on smart-trader).

**Layer 3**
13. **Marker grammar.** Options: (a) one grammar `ref: <target>/<id>`; (b) one marker per target (`arch:`, `law:`). Trade-off: (a) is uniform and future-proof; (b) matches the built tool and reads naturally. **Default: (a) `ref: arch/D1.7`, `ref: law/acts/Income_Tax_Act/v13/s.111`, with `arch:` kept as an alias during migration.** *User must choose* (migration cost vs uniformity).
14. **Marker location.** Options: (a) docstring; (b) comment line; (c) both. Trade-off: docstrings work only where they exist; a comment line works in every language. **Default: (c) both — docstring for Python tests, comment line elsewhere.** *Clear best answer.*
15. **Regex vs parser.** Options: (a) regex per language; (b) parser per language. Trade-off: regex is stdlib and enough for id existence; a parser is needed only to bind a marker to a construct. **Default: (a) regex, plus Python `ast` where already used.** *Clear best answer.*
16. **Tests only vs +production.** Options: (a) tests only; (b) tests + production. Trade-off: tests only is proven and simple; production extends coverage but only checks a/b/drift there. **Default: start (a), extend to (b) for check a + drift once stable.** *User must choose* (scope/timing).
17. **Pin legislation version.** Options: (a) pin (`/v13`); (b) resolve-to-current + drift. Trade-off: pin makes drift explicit and uses the existing `key`; resolve hides amendments. **Default: (a) pin.** *Clear best answer.*
18. **Section hash location.** Options: (a) add to the archiver output; (b) compute in the checker. Trade-off: in the archiver it is stored once and shared; in the checker it recomputes and can drift from normalisation. **Default: (a) add per-section `content_sha256` to lawsmu.** *Clear best answer.*
19. **Subsection ids.** Options: (a) extend lawsmu to id subsections; (b) stop at section. Trade-off: subsection ids need anchors lawsmu does not emit; section-level matches current headings. **Default: (b) stop at section now; revisit if a rule cites `(2)(a)`.** *User must choose* (precision vs archiver work).
20. **Flat vs graph.** Options: (a) flat checker only; (b) flat + graph edges. Trade-off: flat answers most queries with no dependency; the graph adds cross-repo/impact queries but needs graphify support (unknown). **Default: (a) now; emit a JSON edge file so a graph can import later.** *Clear best answer.*
21. **Keep or change the three checks.** Options: (a) keep a/b/c; (b) redesign for the general model. Trade-off: a/b/c already generalise (registry swaps per target); a redesign risks the zero-failure property. **Default: (a) keep; add a version/drift check as the fourth.** *Clear best answer.*
22. **Where the general checker lives.** Options: (a) pipeline skill template; (b) standalone tool. Trade-off: a template ships with the skill and stays opt-in; a standalone tool is reusable but is new infrastructure. **Default: (a) skill template now; promote to a tool only if reused across many repos.** *User must choose* (reuse pressure).

## The one-page code comment standard (draft)

**Global rules (all languages).**
- Write the reason, not the action. A comment says why, or names a non-obvious constraint. It never restates the code.
- One page, one style. Short sentences, active voice, approved terms, one topic each (STE subset).
- No comment claims or hints that an agent wrote the code (RULES.md rule 8). The banned-word list applies to comment text, not identifiers (rule 7).
- A file starts with a short header comment: purpose and key facts. No author/date churn.
- Every suppression carries a rule code and a reason.
- Markers come from the closed registry below. An unknown marker is an error.

| Language | Docstring format | Enforcing linter + rule ids | File header | Mandatory / optional / forbidden | Suppression form + reason setting | Marker form |
|---|---|---|---|---|---|---|
| Python | PEP 257, Google sections | ruff `D` + `[tool.ruff.lint.pydocstyle] convention="google"`; `interrogate --fail-under` (default 80.0) for coverage | module docstring line 1 | Mandatory: module, public class/func, non-obvious block. Optional: private helpers. Forbidden: restating signature | `# noqa: <code>  <reason>`; enforce with `PGH004` (no blanket) + `RUF100` (no stale) | docstring `arch: D1.7, I-3` / comment `# ref: law/…` |
| Rust | rustdoc `///`, `# Safety` section | clippy `missing_docs`, `missing_safety_doc`, `undocumented_unsafe_blocks` | `//!` module doc at top | Mandatory: public items, every `unsafe` block (`// SAFETY:`). Optional: private. Forbidden: obvious restatement | `#[allow(lint)]`→prefer `#[expect(lint, reason="…")]`; clippy `allow_attributes_without_reason` | `// ref: arch/D1.7` / doc `//! arch: …` |
| TypeScript | TSDoc | `eslint-plugin-jsdoc` (`flat/recommended-typescript-error`); `@typescript-eslint/ban-ts-comment` | top-of-file block comment | Mandatory: exported decls. Optional: internal. Forbidden: type restatement (types are in the signature) | `// @ts-expect-error <reason>` with `ban-ts-comment: allow-with-description, minimumDescriptionLength:3`; `eslint-comments/require-description` | `// ref: arch/D1.7` |
| Shell | Google header + function header | shellcheck; Google Shell Style Guide | header immediately after hashbang | Mandatory: file header, non-obvious function (Globals/Args/Outputs/Returns). Forbidden: obvious lines | `# shellcheck disable=SCxxxx  # <reason>` (reason enforced by CI grep, not shellcheck) | `# ref: arch/D1.7` |
| SQL | file header comment (no docstring standard) | sqlfluff | `-- <purpose>` at top | Mandatory: file header, non-obvious query. Forbidden: restating SQL | `-- noqa: <code>` (disallow bare `-- noqa` by convention) | `-- ref: arch/D1.7` |

**Marker registry (draft).**

| Marker | Meaning | Grammar | Checking tool |
|---|---|---|---|
| `arch:` (alias of `ref: arch/…`) | this test proves these design ids | `arch: D<n>.<m>[, I-<n>]…` or `arch: none - <reason>` | `arch_refs.py` (checks a/b/c) |
| `ref:` | generalised reference to any target | `ref: <target>/<id>` where target ∈ {arch, law} | general checker + `lychee --include-fragments` for check a |
| `law:` (alias of `ref: law/…`) | this code implements this section of law | `law: acts/<Slug>/v<N> s.<num>` | general checker + per-section hash drift |
| `SAFETY:` | justifies an `unsafe` block (Rust) | `// SAFETY: <invariant argument>` | clippy `undocumented_unsafe_blocks` |
| suppression | one lint rule off for one line | per linter, code + reason required | each linter (`PGH004`/`RUF100`, `ban-ts-comment`, `expect(reason)`) |
| `TODO` | tracked deferred work | `# TODO(owner): <text> <issue-link>` | ruff `TD002`/`TD003`/`TD004`/`TD005` |

## The general reference checker (design)
- **Marker grammar.** One prefix `ref:` + `<target>/<id>`; `arch:` and `law:` are aliases for readability and migration. Extract with a line regex; no parser dependency.
- **Id schemes.** arch: `D<n>.<m>`, `I-<n>`. law: `acts/<Slug>/v<N> s.<num>`, reusing the lawsmu `key`.
- **Checks generalised.** (a) id exists in the registry (design headings, or lawsmu key+section). (b) in a marked file, every unit is marked. (c) each `## Verification` claim (arch) or each section in a declared scope (law) has a test/code, unless an open `PLAN.md` row exempts it. (d, new) drift: the cited section's hash changed between the pinned and current version.
- **Registry per target.** arch ids parsed from `docs/ARCHITECTURE.md`; law ids parsed from the lawsmu archive with per-section `content_sha256`.
- **Extraction approach.** Regex for id existence across all languages (stdlib, matches "installed-tool-first" rule); Python `ast` for the existing test case; Vale/tree-sitter for prose *inside* comments. A per-language parser is not justified for id existence.
- **Reuse before new code.** Check a can be delegated to `lychee --include-fragments` if markers are written as relative links with fragments — no new code. Checks b/c/d need the small script.

**Prior-art comparison.**

| Prior art | Does check a | Does "both ways" | Reads test results | Fits zero-failure, stdlib, opt-in |
|---|---|---|---|---|
| lychee `--include-fragments` | Yes (fragment exists) | No | No | Yes (installed) |
| OpenFastTrace | Yes | Yes | No | No (JVM) |
| Doorstop / StrictDoc / Sphinx-Needs | Yes | Yes | Partly | No (own doc format) |
| Rust compiletest `//@ reference:` | Yes | Yes (id↔test, JSON) | Yes | Model to copy (emit JSON) |
| Semgrep custom rule | Yes (pattern present) | No | No | Possible but new rules |
| Your `arch_refs.py` | Yes | Yes | Indirect | Yes |

**Conclusion:** `lychee` already does check a, so no new code is needed for id existence if markers are links. The rest (b/c/d) is best kept as the existing 120-line stdlib script, mirroring Rust compiletest's JSON-emit pattern for a future graph.

## Integrated best design

**How the three layers join through stable ids.** A design section carries an explicit id (`D1.7`). A test docstring or a production comment cites it (`ref: arch/D1.7`). A law section is identified by the lawsmu `key` + section (`ref: law/acts/Income_Tax_Act/v13 s.111`). The checker follows the id from code to target (checks a/b) and from target to code (check c) and watches the section hash (check d). The same id is the anchor a person clicks and the node a future graph stores.

**Agent entry route.** `AGENTS.md` (thin: build/test/convention facts + links, under Codex's 32 KiB `project_doc_max_bytes` cap) → `docs/README.md` (Diátaxis index) → pages. `CLAUDE.md` imports `AGENTS.md`. Add `GEMINI.md` only if Gemini CLI is used and not configured to read AGENTS.md.

**Page front matter (recommended).** `id`, `type` (Diátaxis quadrant), `audience`, `status`, `last_reviewed`. State clearly: no current agent tool auto-filters on these; they serve humans, CI, and a future graph.

**Section id scheme.** Design: explicit `D<n>.<m>` and `I-<n>` tokens inside headings (survives title edits, unlike slugs). Legislation: reuse `key` + `s.<num>`; add a per-section hash. This mirrors Akoma Ntoso `eId` (structural id) + `wId` (retained old id) — adopt the retain-old-id idea if design sections are ever renumbered.

**Proposed Claude Code skill file tree.**
```
skill/
  SKILL.md                 # contract: entry route, comment standard summary, checker adoption Q
  references/
    comment-standard.md    # the one-page table (this document's standard)
    marker-registry.md     # the closed registry
    reference-checker.md   # marker grammar, id schemes, checks a/b/c/d
  scripts/
    arch_refs.py           # existing 120-line stdlib checker (checks a/b/c)
    ref_check.py           # generalised: target registry + drift (check d)
    lychee.toml            # include_fragments = "anchor-only" for check a
```

**Distribution.** Generate the comment-standard block into each `AGENTS.md` from the core blocks of the agent-configuration generator — the same channel the baseline already uses. The skill imports the same block, so there is one source of truth.

## Proven practice vs proposal
- **Proven (read from files / measured, per the brief):** `arch_refs.py` (120 lines, stdlib, commit `41cf838`), its 4/4 selftest, the `arch:` grammar, the per-file check b (blanket rule failed 1509× on smart-trader), the `## Verification` drift detector, the repo-init step-5b opt-in, the practice counts of the agent-configuration repository (39 TS / 28 sh / 5 Py / 4 SQL; 27/28 shell headers; 5/5 Python module docstrings), the lawsmu front matter and section-heading shape.
- **Proven (external primary sources):** ruff `D`/convention/`PGH004`/`RUF100`/`TD003`; `interrogate --fail-under` default 80.0; clippy `missing_docs`/`missing_safety_doc`/`undocumented_unsafe_blocks`; `ban-ts-comment` `allow-with-description`/`minimumDescriptionLength`; Vale comment scopes + tree-sitter; lychee `--include-fragments`; Rust compiletest `//@ reference:` (issue #783, Rust 1.84/1.87); OpenFastTrace tag grammar; Akoma Ntoso `eId`/`wId`; legislation.gov.uk point-in-time URIs; OpenFisca `reference`; AGENTS.md tool support + Codex 32 KiB cap; DO-178C §6.5 / ISO 26262 bidirectional traceability (vendor whitepapers); iComment (SOSP 2007) counts; the 1.5× bug-proneness finding (arXiv:2409.10781).
- **Proposal (not yet built or decided):** the `ref:` unified grammar, the `law:` checker, the per-section hash in lawsmu, check d (drift), the JSON edge-emit for a graph, the front-matter field set, promoting the checker to a standalone tool.

## Caveats and unknowns
- The local files in section 13 (`~/.claude/*`, the agent-configuration repository, lawsmu, graphify) are not accessible to me. All facts about them are taken as given from the brief; the 1509 and drift-section numbers are from a memory note dated 2026-09-15 and were not re-measured.
- **graphify:** whether it reads `arch:` markers or imports external edges is unknown; no public project matching the described commands (`graphify-out/graph.json`, `path`/`explain`/`merge-graphs`) was confirmed. Treat as unknown until the local tool is read.
- **TypeScript comment practice** in the agent-configuration repository was not sampled — unknown.
- **Per-tool token cost** of each entry-route step is not published — unknown; control by keeping AGENTS.md small and under the 32 KiB cap.
- **Agent front-matter filtering:** no evidence any agent tool auto-filters doc pages by front matter today.
- **Comment effect on agent edits (q16/q17):** direct measured evidence is thin; stated as partial/weak.
- **shellcheck and sqlfluff** enforce a suppression *code* but not a free-text *reason*; a reason must be enforced by your own CI, not the linter.
- **DO-178C / ISO 26262** exact table letters and clause numbers are from vendor whitepapers (Vector, LDRA, Jama), not the copyrighted standard text; the bidirectional principle and the §6.5 name are consistently confirmed.
- ASD-STE100 rules are paraphrased throughout; its dictionary is not reproduced.