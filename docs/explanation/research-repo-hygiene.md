---
id: research-repo-hygiene
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-09-25
---

# Repository Hygiene Framework: Research Baselines and Draft Specification (working name: `repo-medic`)

Build it. No existing tool does the full job: study a repo, adapt to its size, restructure it, and rewrite its docs behind an approval gate. Existing tools cover single checks (repolinter, Scorecard, repo-review, markdownlint, knip) or rewrite prose only (the "unslop" skills; the most installed, theclaymethod/unslop, shows 2,293 all-time installs on the skills.sh registry as of 5 August 2026). Drop "unslop" as the name. It is already used for at least five Claude Code skills on GitHub (theclaymethod/unslop, maxgoff/unslop, asavvin-pixel/unslop, poteto/pstack `unslop`, MohamedAbdallah-14/unslop) and an npm package, all about AI prose, not repo structure. Of the names checked, `repo-medic` is the best option, but nobody has confirmed it is free.

## TL;DR

- **The gap is real.** Linters check for problems but do not fix them. Scaffolders (copier, cookiecutter) create new repos but cannot adopt an existing one; copier's own "adopt" workflow is still an open feature request. Prose "unslop" skills rewrite text but do not touch structure. A skill that surveys → plans → applies → verifies, with tiers for small, medium and large repos, fills that gap.
- **The root-estate problem can only be partly solved.** The `.config/` convention works in cosmiconfig-based tools and a growing list (mise, lefthook, cspell, cargo-nextest, goreleaser, rubocop). ESLint, Ruff, MkDocs and Docker Compose have declined it. Manifests (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`) and `LICENSE` must stay at the root. The realistic goal: consolidate into manifests first, move to `.config/` or `.github/` second, and document every exception.
- **Ship in four stages:** a Claude Code skill (dry-run by default, human approval gate), then Claude Code hooks (PreToolUse blocks new root files and scratch files, SessionStart injects the baseline), then a pre-commit/CI mode that fails on slop-score regressions, then a scheduled "gardener" that opens Renovate-style cleanup PRs.

---

## Part A — Standards and Baselines

### A1. README standards: what each one prescribes

| Source | URL | Required / core sections | Notable rules |
|---|---|---|---|
| standard-readme (RichardLitt) | https://github.com/RichardLitt/standard-readme/blob/main/spec.md | Title, Banner, Badges, Short Description, Long Description, Table of Contents, Security, Background, Install, Usage, Extra Sections, API, Maintainers, Thanks, Contributing, License, in that order | Sections "must appear in order given below"; the title must match the repo, folder and package-manager names; the short description must be under 120 characters and must match the package-manager and GitHub descriptions; the README "must not contain broken links"; code examples should be linted like the rest of the code |
| standard-readme-preset (linter) | https://github.com/RichardLitt/standard-readme-preset | Contributing and License required | ToC required when the file, excluding the ToC, exceeds 100 lines; top-level heading must match the directory name |
| GitHub "About READMEs" | https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes | What the project does, why it is useful, how to get started, where to get help, who maintains it | Rendered from `.github/`, root, or `docs/` (that precedence); content beyond 500 KiB is truncated; relative links recommended; "longer documentation is best suited for wikis" |
| Make a README | https://www.makeareadme.com | Name, Description, Badges, Visuals, Installation, Usage, Support, Roadmap, Contributing, Authors, License, Project status | Suggestions, not requirements (not re-fetched this pass) |
| Art of README | https://github.com/hackergrrl/art-of-readme | Name, one-liner, usage, API, installation, license | "Cognitive funneling": most important content first; brevity (not re-fetched this pass) |
| readme-best-practices | https://github.com/jehna/readme-best-practices | Template: description, getting started, developing, features, configuration, contributing, links, licensing | Template-based (not re-fetched this pass) |
| Awesome README | https://github.com/matiassingers/awesome-readme | Curated examples, not a spec | Use it as an example corpus, not as rules |
| Google developer documentation style guide | https://developers.google.com/style | Style, not structure | Second person, active voice, present tense, sentence-case headings, code in code font (not re-fetched this pass) |
| Diátaxis | https://diataxis.fr/ | Four kinds: tutorials, how-to guides, reference, explanation | Organise docs around user needs; keep the four kinds separate |
| Divio documentation system (origin) | https://docs.divio.com/documentation-system/ | Same four kinds | Diátaxis is the continued, renamed form by the same author, Daniele Procida |

**Where they disagree:**
- **Order and rigidity.** standard-readme makes order and titles mandatory. GitHub and Make a README only suggest. The tool should use standard-readme's order as a default and never fail a repo on order alone.
- **Background vs. up-front description.** standard-readme puts motivation in a Long Description/Background section. Art of README says to lead with usage. For T0/T1 repos, lead with a one-liner and usage.
- **Where long docs go.** GitHub points to wikis. Diátaxis points to a structured `docs/` tree. For T2+ repos, use `docs/` in the Diátaxis split. Wikis are not versioned with the code, so they drift.
- **Security.** standard-readme has a Security section in the README. GitHub and Scorecard expect a separate `SECURITY.md`. Use `SECURITY.md` and put a one-line link in the README.

### A2. Community health and supporting files

**GitHub rules (verified):**
- Default community health files live in a **public** repo named `.github`. GitHub looks in this order: the `.github` folder, the root, then `docs/`.
- You **cannot** create a default licence. "License files must be added to individual repositories."
- Issue templates must be in `.github/ISSUE_TEMPLATE`. If a repo has *any* file in its own `.github/ISSUE_TEMPLATE`, none of the org defaults are used.
- Source: https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file
- Supported defaults include CODE_OF_CONDUCT.md, CONTRIBUTING.md, FUNDING.yml, GOVERNANCE.md, issue/PR templates and config.yml, SECURITY.md, SUPPORT.md, and discussion category forms.

| File / convention | Primary source | Location | What the tool checks |
|---|---|---|---|
| CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, SUPPORT.md, GOVERNANCE.md | GitHub docs (above) | `.github/`, root, or `docs/`; or org `.github` repo | Exists (locally or inherited from the org); links resolve |
| LICENSE | https://choosealicense.com, Scorecard License check | Root (or `LICENSES/` for REUSE) | Scorecard looks for LICENSE, LICENCE, COPYING, COPYRIGHT (+ .html/.txt/.md) at top level, and also a `LICENSES/` directory |
| FUNDING.yml | GitHub docs | `.github/` | Valid YAML |
| CODEOWNERS | https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners | `.github/`, root, or `docs/` | Every path has an owner (T3); owners exist |
| Issue/PR templates | GitHub docs | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | Present for T2+ |
| Keep a Changelog | https://keepachangelog.com | `CHANGELOG.md` at root | `## [Unreleased]` section; Added/Changed/Deprecated/Removed/Fixed/Security groups |
| Semantic Versioning | https://semver.org | n/a | Tags match `vMAJOR.MINOR.PATCH` |
| Conventional Commits | https://www.conventionalcommits.org | n/a | `type(scope)!: subject` share in recent history |
| Contributor Covenant | https://www.contributor-covenant.org | `CODE_OF_CONDUCT.md` | Enforcement contact is filled in, not left as a placeholder |
| OpenSSF Scorecard | https://github.com/ossf/scorecard/blob/main/docs/checks.md | n/a | Binary-Artifacts (high risk), Security-Policy (SECURITY.md at top level or `.github/`), License, Dangerous-Workflow, Token-Permissions, Pinned-Dependencies, etc. |
| OpenSSF Best Practices badge | https://www.bestpractices.dev/en/criteria | n/a | Passing-level criteria: basics, change control, reporting, quality, security, analysis (not re-fetched this pass) |
| REUSE | https://reuse.software/spec/ | `LICENSES/`, SPDX headers or `REUSE.toml` | `reuse lint` passes |
| EditorConfig | https://editorconfig.org | `.editorconfig` at root with `root = true` | Present for T1+ |
| CITATION.cff | https://citation-file-format.github.io | Root | Valid for research/data repos |
| .gitattributes / .gitignore | https://git-scm.com/docs/gitattributes, https://github.com/github/gitignore | Root (and nested as needed) | Ecosystem template coverage; `linguist-generated` marks generated files |
| AGENTS.md | https://github.com/agentsmd/agents.md | Root, plus nested per package | Plain Markdown with no required fields; the nearest file to the edited file wins |
| CLAUDE.md | https://code.claude.com/docs | Root, `.claude/` | Claude Code does not read AGENTS.md natively; import it with `@AGENTS.md` or use a symlink |
| .cursorrules / `.cursor/rules/*.mdc` | Cursor docs | `.cursor/rules/` | `.cursorrules` is legacy; `.mdc` files carry description/globs/alwaysApply frontmatter |
| .github/copilot-instructions.md | GitHub Copilot docs | `.github/` | Present only if the team uses Copilot |

**Agent-file policy for the tool:** keep one canonical `AGENTS.md`. Make `CLAUDE.md` a thin file that contains `@AGENTS.md` plus any Claude-only notes. Do not maintain duplicate prose in `.cursorrules` or `copilot-instructions.md`. Keep AGENTS.md short. OpenAI's Codex docs ("Custom instructions with AGENTS.md") say Codex "stops adding files once the combined size reaches the limit defined by project_doc_max_bytes (32 KiB by default)". The cap covers all AGENTS.md files combined, not each file, and one secondary source reports 64 KiB in newer versions, so check it at runtime.

### A3. Root-directory conventions and config consolidation

**The `.config/` convention**
- **Proposals.** pi0/config-dir (https://github.com/pi0/config-dir) and the older dot-config (https://github.com/dot-config/dot-config.github.io). pi0's rule: "When the `.config/` directory exists, tools read the config files inside this directory", using `.config/[name].[ext]`, with optional `.config/[name]/` nesting.
- **Loader support.** cosmiconfig searches `.config/{NAME}rc`, `.config/{NAME}rc.json|yaml|yml|js|ts|mjs|cjs` by default. Any tool on a recent cosmiconfig inherits this (https://github.com/cosmiconfig/cosmiconfig). c12 (unjs) also supports it.
- **Supports `.config/`** (pi0 tracker, https://github.com/pi0/config-dir/discussions/6): c12, cosmiconfig, nuxt, nitro, unbuild, marklint, rubocop, mise, goreleaser, vue-mess-detector, cargo-nextest, lefthook, hk, rumdl, cspell, air, ryl. The dot-config list adds ansible-lint, ansible-navigator, doc8, Mill and molecule.
- **Open requests:** vite, vitest, biome, golangci-lint, dprint, prisma, unified-engine (remark), editorconfig, crate-ci/committed, and GitHub itself (`.config/github`, community discussion #178064, Oct 2025).
- **Declined** (maintainers suggest overriding the config path instead): ESLint (#18294), drizzle, MkDocs, Docker Compose, Ruff.
- **Consequence:** `.config/` is a partial solution. The tool must hold a per-tool capability table. It must never move a config file into `.config/` for a tool that will not find it.

**Per-ecosystem layout baselines**
- **Rust:** Cargo package layout (https://doc.rust-lang.org/cargo/guide/project-layout.html): `src/lib.rs`, `src/main.rs`, `src/bin/`, `benches/`, `examples/`, `tests/`. Workspaces: a root `Cargo.toml` with `[workspace]` and members under `crates/`.
- **Go:** use the official https://go.dev/doc/modules/layout. Do **not** apply golang-standards/project-layout. In issue #117 (9 April 2021), Russ Cox wrote that it "is not a standard Go project layout" and that "the vast majority of packages in the Go ecosystem do not put the importable packages in a pkg subdirectory" (https://github.com/golang-standards/project-layout/issues/117). The only compiler-enforced rule is `internal/`.
- **Python:** src layout (https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/). `pyproject.toml` is the single config (PEP 518/621). The Scientific Python guide (https://learn.scientific-python.org/development/) is the most checkable baseline. Frappe apps follow the bench app layout (`<app>/<app>/hooks.py`, `modules.txt`, `pyproject.toml`), so do not impose src layout on Frappe apps.
- **JS/TS:** `package.json` carries tool keys (prettier, eslintConfig for legacy configs, jest, babel, browserslist, lint-staged, commitlint). ESLint flat config (`eslint.config.js`) replaced `.eslintrc*` and has no package.json key.
- **Monorepos:** `pnpm-workspace.yaml`, `turbo.json` and `nx.json` at root; packages under `packages/` or `apps/`; per-package README.

**Root-file relocation table**

"Verified" = confirmed in this research pass. "Known" = standard tool behaviour, not re-checked this pass. Check "Known" rows in the tool's current docs before automating them.

| File | Can move? | Where / how | Status |
|---|---|---|---|
| `README.md` | Yes, but should not | `.github/README.md` or `docs/README.md` render on GitHub, but package registries and clones expect root | Verified (GitHub) |
| `LICENSE` / `COPYING` | **No** | Must stay at root: no org default possible; Scorecard and registries look at top level; `LICENSES/` allowed for REUSE | Verified |
| `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `SECURITY.md`, `GOVERNANCE.md` | Yes | `.github/` (GitHub precedence: `.github` → root → `docs`) or inherit from org `.github` repo | Verified |
| `CODEOWNERS` | Yes | `.github/CODEOWNERS` | Known |
| `FUNDING.yml` | Must be in `.github/` | — | Verified (listed as `.github` default) |
| `CHANGELOG.md` | Keep at root | Keep a Changelog convention; release tooling (release-please, changesets, cargo-release) expects root or a per-package path | Known |
| `CITATION.cff` | **No** | GitHub reads it from root | Known |
| `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml` | **No** | Manifests define the project root | Known |
| `pnpm-workspace.yaml`, `turbo.json`, `nx.json` | **No** | Workspace roots | Known |
| `tsconfig.json` | Keep at root | `tsc -p path` works, but editors resolve the nearest `tsconfig.json`; moving it breaks IDE type-checking | Known |
| `.eslintrc*` / `eslint.config.js` | Partially | Flat config: `eslint -c path`; editor needs a matching setting. `.config/` declined (#18294) | Verified (declined) |
| `.prettierrc*` | Yes → `package.json` | `"prettier"` key, or `--config path`. `.config/` requested in discussion #17234, not supported | Verified (discussion) / Known (key) |
| `.stylelintrc*` | Likely → `.config/stylelintrc.*` | Depends on stylelint's cosmiconfig version; else `package.json` `stylelint` key | Unknown (verify) |
| `commitlint.config.*` | Likely → `.config/commitlintrc.*` or `package.json` `commitlint` key | cosmiconfig-based | Unknown (verify `.config/`); Known (key) |
| `.lintstagedrc*` | Yes → `package.json` `lint-staged` key | `--config` flag also | Known |
| `jest.config.*`, `.babelrc`, `.browserslistrc` | Yes → `package.json` keys (`jest`, `babel`, `browserslist`) | — | Known |
| `vite.config.*`, `vitest.config.*` | Flag only | `--config path`; `.config/` requested, open | Verified (open) |
| `biome.json` | Flag only | `--config-path`; `.config/` open discussion | Verified (open) |
| `setup.cfg`, `tox.ini`, `.flake8`, `pytest.ini`, `.coveragerc`, `mypy.ini`, `.isort.cfg` | Yes → `pyproject.toml` `[tool.*]` | Exception: flake8 has no native pyproject support; migrate flake8 to Ruff instead | Known |
| `ruff.toml` / `.ruff.toml` | Yes → `pyproject.toml` `[tool.ruff]` | `.config/ruff.toml` declined | Verified (declined) |
| `.pre-commit-config.yaml` | Flag only | `pre-commit run -c path` and `pre-commit install -c path` | Known (verify install behaviour) |
| `lefthook.yml` | Yes → `.config/lefthook.yml` | — | Verified |
| `.mise.toml` / `.tool-versions` / `.nvmrc` / `.python-version` | Yes → `.config/mise.toml` (mise) | Only if the team uses mise; nvm/pyenv still read their own files | Verified (mise) |
| `cspell.json` | Yes → `.config/cspell.json` | — | Verified |
| `.goreleaser.yaml` | Yes → `.config/goreleaser.yaml` | — | Verified |
| `nextest.toml` | Must be `.config/nextest.toml` | — | Verified |
| `rustfmt.toml`, `clippy.toml`, `deny.toml`, `rust-toolchain.toml` | Mostly no | rustfmt/clippy search upward from the source; `rust-toolchain.toml` must be at the dir root; `cargo deny --config path` | Known |
| `.editorconfig` | **No** | Editors search the file's directory and parents; `.config/editorconfig` is an open request (#568) | Verified (open) |
| `.gitignore`, `.gitattributes` | **No** (root copy) | Git reads them per-directory; nested files allowed | Known |
| `Makefile` / `justfile` | Keep at root | `make -f path` works but breaks the `make` muscle memory; keep one task runner at root | Known |
| `Dockerfile` | Yes | `docker build -f docker/Dockerfile .` | Known |
| `docker-compose.yml` / `compose.yaml` | Flag/env only | `-f path` or `COMPOSE_FILE`; `.config/` declined (docker/compose#11640) | Verified (declined) |
| `.env.example` | Keep at root | Discoverability next to the ignored `.env` | Known |
| `mkdocs.yml` | Flag only | `mkdocs build -f path`; `.config/` declined | Verified (declined) |
| `renovate.json` | Yes → `.github/renovate.json` | Renovate reads `.github/` | Known |
| `.github/dependabot.yml`, `.github/workflows/` | Fixed | — | Known |
| `.markdownlint*`, `.vale.ini`, `lychee.toml`, `.gitleaks.toml` | Flag/env | `--config`; vale also `VALE_CONFIG_PATH`; gitleaks `GITLEAKS_CONFIG` | Known |

### A4. Popular repositories as baselines

**Caveat:** these layout notes come from prior knowledge. They were not re-fetched on 24 September 2026. The skill should confirm them at runtime (`gh api repos/OWNER/REPO/contents`) before using them as a reference profile.

| Repo | Ecosystem | What it shows | Deviation from "standards" and why |
|---|---|---|---|
| BurntSushi/ripgrep | Rust | README plus separate `GUIDE.md` and `FAQ.md` at root; `CHANGELOG.md`; dual licence files (`LICENSE-MIT`, `UNLICENSE`, `COPYING`) | Long user docs as root Markdown files, not `docs/`; it works because the set is small and each file is named for its purpose |
| tokio-rs/tokio | Rust workspace | Cargo workspace, one crate per directory, per-crate README/CHANGELOG | Workspace members at the root, not under `crates/` |
| astral-sh/ruff | Rust + Python | Cargo workspace under `crates/`, `pyproject.toml` for the Python wheel, docs in `docs/` (MkDocs) | Many root config files; high tool density is normal for a tool that ships to two ecosystems |
| kubernetes/kubernetes | Go | `cmd/`, `pkg/`, `staging/`, `vendor/`, `hack/`, `OWNERS` files; user docs live on kubernetes.io | Uses `pkg/` and `vendor/`, the pattern Russ Cox says most Go repos do not need; justified at 100+ maintainer scale |
| spf13/cobra | Go | Flat library at root, docs site in a subfolder | Flat layout is the Go norm for libraries |
| psf/requests | Python | Sphinx `docs/`, `HISTORY.md` (not CHANGELOG) | Name differs from Keep a Changelog; the tool must accept equivalents |
| fastapi/fastapi | Python | `docs/{lang}/` MkDocs, multilingual | Parts of the README are generated; the tool must detect generated READMEs and not hand-edit them |
| pydantic/pydantic | Python | MkDocs `docs/`, `pyproject.toml`-centred config | — |
| vitejs/vite | TS monorepo | pnpm workspace, `packages/`, VitePress `docs/` | — |
| prettier/prettier | JS | Its own website, `docs/` Markdown, `CHANGELOG.md` | Many root dotfiles |
| microsoft/TypeScript | TS | Large root, `SECURITY.md`, `CONTRIBUTING.md` | Build tooling at root; scale justifies it |
| vercel/turborepo | Rust + TS monorepo | `crates/` and `packages/` side by side | Mixed-ecosystem monorepo profile needed |
| evildmp/diataxis-documentation-framework | Docs | Sphinx docs-as-code | Docs repo tier: no install/usage sections |

**Pattern:** good repos deviate from standards for reasons of scale (kubernetes), ecosystem (Go flat layout) or generation (fastapi). The tool's "respect existing conventions" rule must detect *consistent* deviation and leave it alone.

### A5. Existing tools and the gap

| Tool | Checks | Fixes? | Status / note |
|---|---|---|---|
| repolinter (TODO Group) | File existence and contents rules (LICENSE, README, CONTRIBUTING, license headers) | Limited | GitHub shows: "This repository was archived by the owner on Feb 6, 2026. It is now read-only." Last npm release is 0.12.0; npm audit showed 8 vulnerabilities (issue #324). Use it for ideas, not as a dependency |
| OpenSSF Scorecard | 18 checks across 3 themes per scorecard.dev (security practices, source code risk, build process risk); an OpenSSF blog post from March 2024 says 19. Weighted 0–10 | No | Active; the benchmark target |
| GitHub community profile | Presence of health files | No | UI only |
| repo-review + sp-repo-review | Plugin framework; Scientific Python guide checks (PC, RF, MY, GH families) | No | Output: rich/svg/html/json; runs via CLI, `gh:org/repo`, WebAssembly, pre-commit, Actions. **Best architecture model for the check layer** |
| cookiecutter | Scaffold new projects | n/a | No update path |
| copier | Scaffold + `copier update` 3-way merge using `.copier-answers.yml` (`_commit`, `_src_path`) | Updates | Adopting an existing repo is an open request (`copier adopt`, issue #2486) |
| projen, hygen | Synthesised or generated config | Regenerates | projen owns files; conflicts with hand edits |
| pre-commit | Hook runner | Via hooks | The delivery vehicle for stage 2 |
| markdownlint, vale, cspell | Markdown style, prose style, spelling | markdownlint `--fix` | vale is the right engine for anti-slop prose rules |
| lychee | Broken links | No | — |
| editorconfig-checker, check-jsonschema | Whitespace, config schema validity | No | — |
| gitleaks | Secrets (regex + entropy) | No | Never auto-fix secrets |
| licensee, REUSE tool | Licence detection, SPDX compliance | `reuse annotate` | — |
| Dependabot / Renovate | Dependency updates | Opens PRs | **Model for stage 4**: grouped PRs, schedules, config in `.github/` |
| ast-grep, codemods | Structural search/rewrite | Yes | Reference rewriting after moves |
| vulture, knip, deadcode, cargo-udeps, cargo-machete | Dead code, unused files/deps | knip has `--fix` | knip is the only one here that also finds unused *files* |
| "unslop" skills (theclaymethod/unslop, Cursor pstack `unslop`, mcpmarket listings) | AI prose patterns; one diff-based code-slop cleaner | Rewrite | Prose only, not repo structure |
| "Declutter Project Structure", "Janitor Code Cleanup", "GitHub Repo Curator", danielrosehill `claude-janitor` | Repo cleanup skills | Partial | Closest competitors; scope and quality not assessed this pass |
| Sweep, Aider, OpenHands | General coding agents | Yes | No hygiene baseline, no tiers |

**What none of them do together:** tier classification, a reference graph built before moving anything, root-estate relocation with a per-tool capability table, doc rewriting tied to verified commands, a manifest for drift re-checks, and agent-facing guard hooks. That combination is the product.

### A6. Slop taxonomy with detection heuristics

| Slop item | Detection heuristic / metric | Tool to reuse |
|---|---|---|
| Dead/orphan files | Not in the import graph, not referenced by any tracked file (grep of basename/path), not an entry point, not in CI | knip, vulture, deadcode, cargo-machete; custom reference graph |
| Duplicate files | Content hash equality; near-duplicate via shingled Jaccard > 0.9 | `git ls-files` + hashing |
| Committed build artifacts | Path matches `dist/`, `build/`, `target/`, `*.pyc`, `node_modules/`; also listed in the ecosystem `.gitignore` template | github/gitignore templates; Scorecard Binary-Artifacts |
| Generated files not ignored | Header markers ("Code generated … DO NOT EDIT", `@generated`); lockfiles are allowed | Regex |
| Stale scratch files | Name matches `tmp*`, `scratch*`, `notes*`, `TODO.md`, `*.bak`, `*.orig`, `untitled*`, `test2.py`; last commit > 180 days ago; zero references | `git log -1 --format=%ct -- path` |
| Orphan scripts | In `scripts/` or root, executable, not referenced by Makefile/package.json scripts/CI/docs | Reference graph |
| Multiple overlapping READMEs | More than one README in root/`.github`/`docs`; heading overlap > 50% | Markdown AST diff |
| Docs contradict code | CLI flags in docs not in `--help` output; documented functions missing from the public API; code blocks that fail to run | Parse `--help`; doctest; mdsh/`cargo test --doc`/`pytest --doctest-glob` |
| Oversized root | Count of tracked root entries; T1 > 15, T2 > 25 is a flag | `git ls-tree --name-only HEAD` |
| Committed secrets / `.env` | gitleaks rules + Shannon entropy on strings; tracked `.env` without `.example` suffix | gitleaks |
| Binary blobs | File > 1 MiB, or non-text MIME, not under LFS | `git ls-files -s` + size; `.gitattributes` LFS check |
| Vendored code | `vendor/`, `third_party/`; copied licence headers | Flag only; vendoring can be intentional |
| Outdated dependencies | Registry lag; no Dependabot/Renovate config | Scorecard Dependency-Update-Tool |
| Missing licence | Scorecard License check logic | Scorecard / licensee |
| Broken links | HTTP status, anchor existence | lychee |
| Stale config for removed tools | Config file present for a tool not in dependencies/CI (e.g. `.travis.yml` with GitHub Actions active; `.eslintrc` alongside `eslint.config.js`) | Capability table lookup |
| Inconsistent naming | Mixed kebab/snake/camel in sibling files; entropy of the naming-style distribution | Custom |
| Commented-out code | Comment blocks that parse as code (≥ 3 consecutive lines) | Tree-sitter parse of comment bodies |
| Stale branches | Merged or > 180 days without commits | `git for-each-ref` |
| AI-generated filler prose | Density of banned phrases ("delve", "seamless", "robust", "it's worth noting"); hedges per 100 words; emoji in headings; repeated summaries (sentence embedding similarity between intro and conclusion > 0.85); list-heavy paragraphs; readability (Flesch-Kincaid grade > 14 for READMEs) | vale custom style; unslop-style phrase lists |
| AI-generated code slop | Excess comments restating code, defensive try/catch in trusted paths, `any` casts, placeholder tests (per the diff-based unslop code cleaner) | ast-grep rules |

---

## Part B — Specification

### B1. Purpose, scope, non-goals

**Purpose.** Take any repository, measure its slop, and turn it into a repository whose structure, root and docs match a baseline fitted to its tier and ecosystem. Change nothing without approval.

**Scope.**
- Files and directories.
- Root estate.
- README and supporting docs.
- Community health files.
- Agent instruction files.
- Reference rewriting after moves.
- Continuous guarding through hooks and CI.

**Non-goals.**
- Not a linter for code style. Delegate to ruff, clippy, eslint and biome.
- Not a security scanner. Delegate to gitleaks and Scorecard; only report their results.
- Does not rewrite git history. No `filter-repo` in the default mode.
- Does not choose licences.
- Does not change public API or published entry points.

### B2. Naming

**Verdict:**
- **Drop "unslop".** It is heavily used for the same idea applied to prose.
- **"medic"** is weak on its own: Medic Mobile owns `github.com/medic` and the `@medic` npm scope.
- **Prefer `repo-medic`.** It turned up nothing on any platform checked, keeps the user's metaphor, and says what it does.
- **Runner-up:** `tidyrepo`.

The availability data comes from a sub-research pass on 24 September 2026. Most registry pages could not be fetched directly. "Unknown" means not verified; it does not mean free.

| Name | npm | PyPI | crates.io | GitHub org/user | Claude skill/plugin | Notes |
|---|---|---|---|---|---|---|
| unslop | taken | taken (probably) | unknown | taken (probably) | taken (many) | npm `unslop@0.1.7`; theclaymethod/unslop, maxgoff/unslop, asavvin-pixel/unslop, Cursor pstack `unslop`, MohamedAbdallah-14/unslop (ships a Python CLI, `pip install unslop`, per awesome-claude-code issue #1641), mshumer/unslop, several mcpmarket listings |
| medic | unknown | unknown | unknown | taken (probably) | unknown | Medic Mobile org and `@medic` npm scope |
| repo-medic | unknown | unknown | unknown | unknown | unknown | No hits anywhere. **Recommended** |
| tidyrepo | unknown | unknown | unknown | unknown | unknown | No hits. Runner-up |
| gardener | taken | unknown | unknown | taken | similar | SAP Kubernetes Gardener org; npm `gardener` 1.1.4. Good name for the stage-4 bot *mode*, not the product |
| curator | taken | unknown | unknown | unknown | similar | "GitHub Repo Curator" skill does repo cleanup |
| declutter | taken | unknown | unknown | unknown | taken | "Declutter Project Structure" skill: direct clash |
| repo-doctor | unknown | unknown | unknown | unknown | unknown | 9+ GitHub repos with this exact name for repo health checkers |
| janitor | taken | taken (probably) | taken | unknown | taken (many) | "Janitor Code Cleanup", `claude-janitor`: direct clash |
| mise-en-place | unknown | unknown | unknown | unknown | unknown | Confusable with the dev tool `mise` |
| rootless | unknown | unknown | unknown | unknown | unknown | Generic container/macOS term |
| kempt | unknown | unknown | unknown | unknown | unknown | Several small GitHub repos named kempt |
| spruce | taken | taken (probably) | unknown | unknown | unknown | — |
| fettle | unknown | unknown | taken | unknown | taken (effectively) | crates.io `fettle` is a Claude Code PreToolUse hook: clash |
| rehab | unknown | unknown | unknown | unknown | unknown | No hits; tone may put people off |

**Before committing to a name,** run `npm view NAME`, `pip index versions NAME`, `cargo search NAME` and `curl -sI https://github.com/NAME` for each shortlisted name.

### B3. Architecture

**Skill layout** (Claude Code skill; name ≤ 64 chars, lowercase/hyphens; description ≤ 1,024 chars; SKILL.md body under 500 lines, per https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):

```
repo-medic/
├── SKILL.md                 # phases, gates, rules (<500 lines)
├── references/
│   ├── tiers.md             # T0–T3 baselines
│   ├── profiles/            # rust.md, python.md, frappe.md, node-ts.md, go.md, monorepo.md, docs.md
│   ├── root-policy.md       # relocation table (A3)
│   ├── slop-taxonomy.md     # A6 heuristics
│   └── writing-rules.md     # anti-slop prose rules
├── scripts/
│   ├── survey.py            # inventory, git churn, ref graph → survey.json
│   ├── score.py             # slop score
│   ├── plan.py              # ranked change list → plan.json + plan.md
│   ├── apply.py             # git mv / rm / rewrite, one commit per change group
│   ├── refs.py              # reference rewriting (imports, CI paths, doc links)
│   └── verify.sh            # build/test/link-check before & after
└── assets/templates/        # README-T0..T3.md, AGENTS.md, CONTRIBUTING.md, SECURITY.md
```

Scripts do the deterministic work. The model does classification and prose judgement. This keeps runs reproducible and keeps context small, because scripts are executed, not loaded.

**Phase 1: Survey (read-only)**
- **Inventory:** `git ls-files` with sizes, MIME type, last-commit time and commit count (churn) over the last 12 months.
- **Ecosystem detection:** manifests (`Cargo.toml`, `pyproject.toml`, `package.json`, `go.mod`, Frappe `hooks.py`), lockfiles, CI files.
- **Reference graph:** language import graphs (via knip/vulture/deadcode where available, tree-sitter otherwise), plus path references found in CI YAML, Makefile, package.json scripts, Dockerfiles and Markdown links.
- **Docs inventory:** every `*.md`, headings, code blocks, link targets.
- **Classification:** tier (B4), ecosystem(s), mono vs. single package, kind (library / application / CLI / infra / docs / data).
- **Consistency fingerprint:** naming style, config location style, docs style. Used by the "respect conventions" rule.
- **Output:** `survey.json`, slop score, findings report.

**Phase 2: Plan**
- Each proposed change carries: id, category, target paths, action (move / delete / merge / rewrite / create), impact (score delta), risk (low/med/high), reversibility and the references it touches.
- Rank changes by impact ÷ risk.
- Group changes into commits that can be reviewed one by one: root estate, dead files, docs, health files, agent files.
- **Mandatory approval gate:** show `plan.md` and apply nothing until the user approves all groups or a selected subset. High-risk items (deletes of files with any reference, moves touching CI) need per-item approval.

**Phase 3: Apply**
- Work on a new branch `repo-medic/<date>`. Use `git mv` for moves so history is kept. Deletes are plain `git rm` commits, reversible by revert.
- **Reference rewriting after each move:** imports (ast-grep rules per language), CI paths (`.github/workflows/*.yml`), Dockerfile `COPY`, Makefile targets, package.json scripts, Markdown relative links.
- **Verification before and after each group:** the detected build command, the test command, `lychee` on docs, and each tool's own config check (`prettier --find-config-path`, `eslint --print-config`, `ruff check --show-settings`). If any check that passed before now fails, revert that group automatically and mark it "blocked".
- **Output:** commits, or a PR via `gh pr create`.

**Phase 4: Verify**
- Re-run Survey. Show before/after slop score, per-category deltas, root entry count and the diffstat.
- Write `.config/repo-medic/manifest.json` (B8).

### B4. Adaptation to complexity

**Tier classification.** The rule is deterministic and the first match wins; the user can override it.

| Tier | Signals | Required files | Optional | Never add |
|---|---|---|---|---|
| **T0** script/snippet | ≤ 5 tracked source files, no manifest or a trivial one, no CI | `README.md` (title, one-liner, usage, licence line), `.gitignore`, `LICENSE` if public | — | CONTRIBUTING, CoC, templates, docs/, CHANGELOG |
| **T1** small project | ≤ 50 files, one package, ≤ 2 contributors in 12 months | T0 + `.editorconfig`, `CHANGELOG.md` if tagged releases exist, one CI workflow | `AGENTS.md` | Issue templates, CODEOWNERS, ADRs |
| **T2** library/app | One package, > 50 files or ≥ 3 contributors or published to a registry | T1 + `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` (public repos), issue/PR templates, `docs/` (Diátaxis once docs exceed ~3 pages), `AGENTS.md` + `CLAUDE.md` import | `CITATION.cff` (research), `SUPPORT.md` | Per-package docs |
| **T3** monorepo/org | Workspace manifest, or ≥ 3 packages, or ≥ 10 contributors | T2 + `CODEOWNERS`, per-package README + CHANGELOG, `docs/adr/`, nested `AGENTS.md` per package, `GOVERNANCE.md` if multi-org | Org `.github` repo for shared health files | — |

**Adaptation rule:** a check that is not required at the repo's tier is never reported as a failure. At most it appears as "available at next tier".

**Baseline profiles.** A profile is a versioned YAML file; the tier sets the base and the profile adds to it.
- **rust:** Cargo layout; workspace members under `crates/` for new workspaces (do not move existing ones); `rustfmt.toml`, `clippy.toml` and `deny.toml` stay at root; `.config/nextest.toml`; `cargo-machete` for unused deps; doc tests count as docs verification.
- **python:** src layout for new libraries (do not convert existing flat layouts without approval); all tool config in `pyproject.toml`; Ruff replaces flake8/isort/black config; checks aligned with sp-repo-review.
- **frappe:** bench app layout is authoritative; never move `hooks.py`, `modules.txt`, `patches.txt`, or module/doctype folders; README covers `bench get-app` / `bench install-app`.
- **node-ts:** tool config in `package.json` keys where the tool supports them; `.config/` only for tools on the capability list; one lockfile.
- **go:** follows go.dev/doc/modules/layout; flag `pkg/` in small repos as optional simplification, never auto-move.
- **monorepo:** pnpm/turbo/nx root files fixed; per-package baseline applied recursively at that package's own tier.
- **docs:** Diátaxis tree; no install/usage requirement.

### B5. Root-estate policy

1. **Allowed at root:**
   - manifests and lockfiles;
   - workspace files;
   - `README`, `LICENSE`/`COPYING`, `CHANGELOG`, `CITATION.cff`;
   - `.gitignore`, `.gitattributes`, `.editorconfig`;
   - one task runner (`Makefile` or `justfile`);
   - `.env.example`;
   - `AGENTS.md`, `CLAUDE.md`;
   - tool configs from the "No" / "Keep at root" rows of the A3 table.
2. **Order of consolidation:**
   - (a) Merge into the ecosystem manifest (`pyproject.toml [tool.*]`, `package.json` keys).
   - (b) Move to `.config/<tool>.<ext>`, but only for tools on the verified capability list.
   - (c) Move community files to `.github/`.
   - (d) Move scripts to `scripts/`, long docs to `docs/`.
   - (e) If none of these apply, leave the file and record the reason in the report.
3. **Never** relocate by adding a CLI flag in some places (e.g. `eslint -c`) unless every invocation site is updated: CI, pre-commit, editor settings and package scripts. If any site is unknown, do not move the file.
4. **Root budget:**
   - T0 ≤ 8 entries;
   - T1 ≤ 15;
   - T2 ≤ 25;
   - T3 ≤ 35 (dotfiles count).
   - Going over budget adds to the score; it does not block.

### B6. Safety rules

- **Dry-run by default.** `apply` requires an explicit approved plan id.
- **Reversible only.** Work on a branch, keep each group as its own commit, never force-push, never rewrite history, never run `git clean -fdx`.
- **Secrets:** never read, print, move or commit files matching secret patterns (`.env`, `*.pem`, `id_*`, gitleaks hits). Report them as "rotate and remove from history manually".
- **Licences:** never edit licence text or SPDX headers. Only add missing files, and only from a licence the user names.
- **Public API:** never move or rename paths that appear in `exports`/`main`/`bin` (package.json), `[project.scripts]`/`[project.entry-points]`, `[lib]`/`[[bin]]`, Go module paths, Frappe `hooks.py` targets, or any documented import path.
- **Allow/deny lists:** a `protect` glob list is never touched; an `ignore` list is excluded from the survey.
- **Respect consistent repos:** if the consistency fingerprint shows one coherent convention, for example docs in `documentation/` everywhere, adopt it as the local baseline and do not impose the standard.
- **Safe to re-run:** a second run on an unchanged repo must produce an empty plan. This is enforced by a test.
- **Generated files:** never hand-edit files with generation markers. Fix the generator input or report the file.

### B7. Documentation rewriting rules

- **README template by tier:**
  - T0: title, one-liner, usage, licence.
  - T1: adds install and development sections.
  - T2: standard-readme order (Title, badges ≤ 4, short description < 120 characters, install, usage, API link, contributing link, licence).
  - T3: root README is a map of packages plus a quick start; details live per package.
- **Anti-slop prose rules** (enforced by a bundled vale style):
  - one idea per paragraph;
  - sentences ≤ 25 words on average;
  - no hedges ("might", "may potentially", "it's worth noting");
  - no filler openers ("In today's…", "This comprehensive guide…");
  - no emoji in headings;
  - no summary that restates the intro;
  - every command in a code block is one that was actually run during Verify, with its exit code recorded;
  - exact names for flags, files and versions.
- **Diátaxis split for T2+ when docs exceed ~3 pages:** `docs/tutorials/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/`. Existing pages are classified by the model, and the user confirms the classification.
- **Keeping docs in sync with code:**
  - doctests (`cargo test --doc`, `pytest --doctest-glob='*.md'`) and executable examples;
  - lychee link check;
  - **docs drift detection:** parse CLI `--help` and compare flags with the flags mentioned in the README; compare the public API symbols with the API reference headings; flag install commands whose package name differs from the manifest name (a standard-readme rule).

### B8. Output artifacts

**Findings report** (`repo-medic-report.md` + `.json`): a summary table (tier, ecosystem, score, root count), then findings grouped by category. Each finding has an id, path, evidence (e.g. "last commit 2023-04-02, 0 references"), severity and proposed action.

**Slop score** (0–100, lower is better). This is a weighted sum of normalised category penalties, capped per category.

| Category | Weight | Counts |
|---|---|---|
| Security hygiene (secrets, tracked `.env`, binaries) | 25 | Any hit gives the category its full penalty |
| Dead/duplicate/scratch/artifact files | 20 | Share of tracked files flagged |
| Docs quality (missing required sections, broken links, drift, AI-prose density) | 20 | Per required item + drift count |
| Root estate (over budget, relocatable files at root) | 15 | Entries over budget + relocatable count |
| Health files for tier | 10 | Missing required files |
| Stale config for removed tools / inconsistent naming | 10 | Count |

Scores are only comparable within a tier. Report the tier next to every score.

**Config file:** `.config/repo-medic.toml`. Also read `[tool.repo-medic]` in `pyproject.toml` and `"repo-medic"` in `package.json`. This follows the consolidation policy the tool itself enforces.

```toml
profile = "python@1"          # baseline profile + version
tier = "auto"                 # or T0..T3
protect = ["legacy/**", "docs/api/**"]
ignore = ["data/**"]
[root]
budget = 20
allow = ["justfile"]
[rules]
disable = ["naming-consistency"]
[ci]
fail_on_regression = 5        # score points
```

**Manifest:** `.config/repo-medic/manifest.json` records the tool version, profile@version, tier, applied plan ids, score before and after, the capability-table version, and the timestamp. Later runs diff against it to detect drift, and to propose upgrades when a new profile version ships. This is the same idea as copier's `_commit`.

**Agent files written:**
- `AGENTS.md` (commands, layout map, root policy, "do not create files at root; scratch goes in `.scratch/` which is git-ignored", doc update rule).
- `CLAUDE.md` containing `@AGENTS.md`.
- Both kept short. By default Codex stops loading AGENTS.md files once their combined size reaches `project_doc_max_bytes` (32 KiB), per OpenAI's Codex AGENTS.md guide.

### B9. Hooks and continuous mode

**Progression and what each stage needs:**

| Stage | Trigger | Needs | Output |
|---|---|---|---|
| 1. Skill | User invokes | SKILL.md + scripts | Report, plan, PR |
| 2. Claude Code hooks | Agent actions | `.claude/settings.json` hooks + manifest + capability table | Blocks/warnings in session |
| 3a. Git hooks | `git commit` | pre-commit hook `repo-medic check --staged` | Blocks scratch/root files |
| 3b. CI | PR | GitHub Action, baseline score from manifest | PR comment + fail on regression |
| 4. Gardener | Schedule (weekly) | GitHub App or Action with `contents: write`, `pull-requests: write`; grouping config | Renovate-style cleanup PRs |

**(a) Claude Code hooks** (https://code.claude.com/docs/en/hooks). Hooks can be shell commands, HTTP endpoints, MCP tool calls, LLM prompts or subagents. PreToolUse is the only event that can block a tool call, through exit code 2 or `permissionDecision: "deny"`. Exit 2 on SessionStart blocks nothing and only shows stderr.

| Event | Use here |
|---|---|
| SessionStart (matcher: startup/resume/clear/compact) | Inject the baseline summary and root policy via `additionalContext`; register `watchPaths` for the repo root |
| Setup (`--init`, `--maintenance` in `-p` mode) | One-shot survey in CI/headless runs |
| UserPromptSubmit | When the prompt mentions "notes", "scratch" or "temp file", add context pointing to `.scratch/` |
| PreToolUse (matcher `Write\|Edit\|Bash`) | **Deny** creating a new root-level file that is not on the allow list; deny `*.bak`, `notes*.md`, `tmp*` outside `.scratch/`; deny `git add` of scratch paths |
| PostToolUse (matcher `Write\|Edit`) | If a changed file is a public interface (CLI arg parser, exported module, `[project.scripts]`), add a reminder to update README/reference docs |
| Stop / SubagentStop | Run a fast `repo-medic check --changed`; if new slop appeared this turn, return feedback so the agent cleans up before finishing |
| PreCompact | Save a findings checkpoint so the baseline survives compaction |
| Notification | Optional desktop alert when a block happens |
| FileChanged (listed in secondary guides; confirm in the reference before relying on it) | React to files created outside tool calls |

**(b) Git hooks:** ship a `.pre-commit-hooks.yaml` with `repo-medic-check` (staged files only, < 1 s target). Also support lefthook, which reads `.config/lefthook.yml`.

**(c) CI mode:** a GitHub Action runs Survey on the PR head and on the base. It posts a sticky comment with the score delta and new findings, and fails when the delta exceeds `fail_on_regression`. It uses read-only token permissions, which avoids Scorecard's Token-Permissions finding.

**(d) Gardener:** a weekly scheduled run. It opens at most one PR per category, reuses an existing open PR instead of opening a duplicate (Renovate's model), and never auto-merges deletes. The PR body carries the evidence for each change.

### B10. How far it can go: ranked roadmap

| # | Capability | Feasibility | Risk | Note |
|---|---|---|---|---|
| 1 | Root-estate consolidation with capability table | High | Low | Core value; the table needs maintenance |
| 2 | Health files per tier + AGENTS.md/CLAUDE.md | High | Low | Templates |
| 3 | Scratch/artifact/duplicate removal | High | Low–Med | Reference graph required |
| 4 | Agent guard hooks | High | Low | Stops slop at the source |
| 5 | Broken links + README section conformance | High | Low | lychee + remark |
| 6 | Licence and secret hygiene (report-only) | High | Low | Delegate to gitleaks/REUSE |
| 7 | AI-slop detection in prose | High | Low | vale style; the rewrite needs review |
| 8 | CI regression gate + health badge | High | Low | Badge = tier + score |
| 9 | Docs drift detection (CLI/API vs docs) | Medium | Low | Per-language parsers |
| 10 | CHANGELOG generation from commits | Medium | Low | Only if Conventional Commits share > ~70% |
| 11 | Dead-code detection | Medium | Med | Wrap knip/vulture/deadcode/cargo-machete; report, don't delete code by default |
| 12 | Dependency pruning | Medium | Med | cargo-machete/knip; verify build |
| 13 | Self-benchmark vs Scorecard | Medium | Low | Run Scorecard, map findings |
| 14 | Learn the repo's own conventions and enforce them | Medium | Med | From the consistency fingerprint |
| 15 | Shareable baseline profile library | Medium | Low | Versioned, like copier templates |
| 16 | Diátaxis restructuring of existing docs | Medium | Med | Model classification + human confirm |
| 17 | Docs generation from code with verification | Medium | Med | Only generate what can be executed |
| 18 | Migration to Conventional Commits | Low–Med | Low | Commitlint + template; no history rewrite |
| 19 | ADR extraction from git history | Low | Med | Drafts only; decisions need human authorship |
| 20 | AI-slop detection in code | Medium | Med | ast-grep rules; high false-positive risk |
| 21 | Monorepo restructuring | Low | High | Many references; phased PRs only |
| 22 | Org-wide baseline enforcement | Medium | Med | Org `.github` repo for defaults; fleet gardener |
| 23 | Upstream contributions (`.config/` support PRs to tools) | Low | Low | Fixes the root problem at the source |

### B11. Open questions for you

1. **Name.** Accept `repo-medic`, and should I run the four registry CLI checks first?
2. **Scratch policy.** Use a git-ignored `.scratch/`, or block scratch files entirely?
3. **Default mode.** PR-only, or allow local commits on the current branch?
4. **Deletes.** Always per-item approval, or group approval for "zero references and older than 180 days"?
5. **Frappe.** Which bench/app conventions are non-negotiable beyond `hooks.py`, `modules.txt`, `patches.txt`?
6. **`.config/` vs. manifests.** When both work (e.g. commitlint), prefer `package.json` keys (fewer files) or `.config/` (fewer root entries)?
7. **Agent files.** AGENTS.md canonical with a CLAUDE.md import, or CLAUDE.md canonical?
8. **CI.** Fail on regression from day one, or report-only for the first month?
9. **Scope of prose rewriting.** README only, or all Markdown?

## Caveats

- **Registry availability** of names is mostly "unknown". Direct registry pages could not be fetched in this pass.
- **Repo layouts in A4 and "Known" rows in A3** come from prior knowledge and were not re-verified on 24 September 2026. They must be checked at runtime.
- **`.config/` support changes quickly.** The pi0 tracker is community-maintained. Re-check it before each profile release.
- **Scorecard weights** quoted elsewhere come from secondary guides. Use the check definitions in `ossf/scorecard/docs/checks.md` as the authority.
- **Claude Code hook events** evolve. FileChanged and a few newer events were seen only in secondary guides.
- **Slop-score weights** are a proposal, not a validated metric. Calibrate them on 20–30 real repos across tiers before publishing a badge.