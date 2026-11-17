---
id: research-code-rules
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-09-24
---

# Research: strict and clean rule sets for each language

## Summary

Two modes exist. **Clean** runs the default rule set of the language linter,
plus a shared change-tracking layer. **Strict** adds the metrics that SonarQube
measures: cognitive complexity, cyclomatic complexity, function length,
parameter count, nesting depth, duplication, dead code and security checks.
The shared layer is the same in both modes: a file header, a docstring on
each public unit, a reason on each suppression, a reference from each test to
a design id, a docstring coverage number and a test coverage number that
cannot fall. Per-language tools cover all eight languages. SonarQube, semgrep
and CodeQL do not fit inside a per-repository tool. pre-commit is the runner.
All sources were read on 2026-09-24.

## 1. SonarQube, semgrep and CodeQL

**What a quality gate is.** "A quality gate consists of a set of conditions
against which the code is measured during analysis." The built-in gate,
"Sonar way", has four conditions on new code: no new issues, all new security
hotspots reviewed, coverage at or above 80.0 %, duplication at or below 3.0 %
(Sonar, quality gates page).

**What the Sonar way profile is.** SonarQube ships one built-in quality
profile per language, called "Sonar way". It "activates a set of rules
applicable to most projects and is a starting point" (Sonar, quality profiles
page). The exact rule list per language lives in the server, not in a file.

**Default thresholds.** The Sonar rule site did not resolve from this
network. The values below come from the analyzer source code on GitHub:

| Rule | Meaning | Default | Source |
|---|---|---|---|
| S3776 | cognitive complexity of a function | 15 | sonar-python `CognitiveComplexityFunctionCheck.java`, `DEFAULT_THRESHOLD = 15` |
| S1541 | cyclomatic complexity of a function | 15 (Python) | sonar-python `FunctionComplexityCheck.java`, `DEFAULT_MAXIMUM_FUNCTION_COMPLEXITY_THRESHOLD = 15` |
| S107 | parameters of a function | 13 (Python) | sonar-python `TooManyParametersCheck.java`, `DEFAULT_MAX = 13` |
| S134 | nesting of control flow | 4 (Python) | sonar-python `NestedControlFlowDepthCheck.java`, `DEFAULT_MAX = 4` |
| S138 | lines in a function | 100 (Python), 150 (PHP) | sonar-python and sonar-php `TooManyLinesInFunctionCheck.java` |
| S1192 | duplicated string literal | 3 occurrences, 5 characters | sonar-php `StringLiteralDuplicatedCheck.java` |

The JavaScript defaults for S107 (7), S134 (3) and S138 (200) are common
knowledge but were not read from source in this session (unverified).

**Open-source equivalent per rule.** Each Sonar metric has a free
counterpart in every language except shell and SQL. The language sections
below name them. The cognitive complexity definition is public (Sonar,
"Cognitive Complexity" white paper), and gocognit, clippy, Biome,
eslint-plugin-sonarjs, revive and complexipy implement it.

**Is SonarQube Community Build a sane option inside a per-repository tool?**
No. The Community Build is free and open source under LGPL 3.0 and analyzes
"40+ programming languages" (SonarSource/sonarqube README). It is a server
with a database, a web UI and a scanner. A quality gate needs the server.
The result does not live in the repository, and a fresh clone cannot
reproduce it without the server. Rust is not on the Community Build list as
far as the README shows (unverified). SonarQube for IDE (formerly SonarLint)
runs inside an editor, not on a command line; the documentation page for it
returned 404 during this session, so its scope is unverified.

**semgrep.** The community edition is LGPL 2.1 (semgrep `LICENSE`). It runs
on a command line: `semgrep scan --config auto`. The exit code is 0 with
findings unless `--error` is set; then it is 1. Exit 2 is a failure, 3 is a
syntax error under `--strict`, 7 is an invalid rule (semgrep CLI reference).
`semgrep ci --oss-only` keeps to the open-source engine. semgrep fits a
per-repository tool as a **security** layer in strict mode. It does not
measure complexity or length. The registry ruleset `p/default` needs network
access on first run.

**CodeQL.** The CLI licence forbids use "for or during automated analysis,
CI or CD" and use "in connection with any codebase that is not an Open Source
Codebase" unless the user holds a GitHub Advanced Security licence
(codeql-cli-binaries `LICENSE.md`). The GitHub Action is MIT but wraps the
same CLI (codeql-action README). CodeQL is out for a per-repository tool
that runs on private code.

**Verdict.** Per-language tooling wins. It runs offline, its configuration
is a file in the repository, and its exit code gates a commit. semgrep is an
optional strict-mode security layer. SonarQube and CodeQL are not options.

## 2. Tools per language

The matrix below names one tool per metric per language. The language
sections give the rule ids, the thresholds, the config files, the install
commands, the command lines and the exit codes.

| Metric | Python | Rust | TS/JS | Shell | SQL | Go | PHP | Vue |
|---|---|---|---|---|---|---|---|---|
| Cognitive complexity | complexipy | clippy `cognitive_complexity` | eslint-plugin-sonarjs or Biome | none | none | gocognit via golangci-lint | phpmd has none; lizard has none | as TS |
| Cyclomatic complexity | ruff `C901` | none in clippy; lizard | eslint `complexity` | none | none | gocyclo / cyclop | phpmd `CyclomaticComplexity` | as TS |
| Function length | ruff `PLR0915` (statements) | clippy `too_many_lines` | eslint `max-lines-per-function` | none | none | funlen | phpmd `ExcessiveMethodLength` | eslint plus `vue/max-lines-per-block` |
| Parameter count | ruff `PLR0913` | clippy `too_many_arguments` | eslint `max-params` | none | none | revive `argument-limit` | phpmd `ExcessiveParameterList` | as TS plus `vue/max-props` |
| Nesting depth | ruff `PLR1702` | clippy `excessive_nesting` | eslint `max-depth` | none | none | nestif / revive `max-control-nesting` | none in phpmd; lizard has none | as TS plus `vue/max-template-depth` |
| Duplication | jscpd | jscpd | jscpd | jscpd | jscpd | dupl via golangci-lint | phpcpd (fork) | jscpd |
| Dead code | vulture, ruff `F401`/`F841`/`ARG` | rustc `dead_code`, `unused` | knip, eslint `no-unused-vars` | shellcheck SC2034 | none | `unused`, `unparam` | phpmd `unusedcode` | as TS, `vue/no-unused-*` |
| Security | ruff `S` (bandit) | cargo-audit | eslint-plugin-sonarjs, semgrep | shellcheck | none | gosec | semgrep, psalm taint (unverified) | as TS |
| Docstrings | ruff `D` | rustc `missing_docs` | eslint-plugin-jsdoc `require-jsdoc` | header check (external) | header check (external) | revive `exported`, `package-comments` | phpcs `Squiz.Commenting.*` | jsdoc on `<script>` |
| Types | mypy or pyright | rustc | tsc | none | none | go build | phpstan, psalm | vue-tsc |

A cross-language fallback exists for the size metrics: **lizard** computes
cyclomatic complexity, function length and parameter count for Python,
JavaScript, TypeScript, Go, PHP, Rust and VueJS. It does not read shell or
ANSI SQL (lizard README). Its defaults are CCN 15 and length 1000, and "the
exit code of lizard will be none-Zero if there are warnings".

## 3. The strict list and the clean list

**Principles.**

1. One threshold per metric across all languages where a tool allows it. The
   value comes from Sonar or from the most common tool default, in that
   order. A reader then learns one number, not eight.
2. Clean is the linter default plus the shared layer. Nothing else.
3. Strict adds every metric and every optional rule group that the tool
   marks stable. Preview or nursery rules stay out.
4. Every finding is an error. Warnings hide. eslint gets `--max-warnings 0`,
   clippy gets `-D warnings`, Biome gets `--error-on-warnings`.

**Uniform strict thresholds.**

| Metric | Strict value | Why this value |
|---|---|---|
| Cognitive complexity | 15 | Sonar S3776 default; Biome default; golangci-lint recommends 10 to 20 |
| Cyclomatic complexity | 10 | ruff `C901` default, cyclop default, revive default, phpmd default |
| Function length | 60 lines; Python 50 statements (ruff PLR0915, no line limit); none for shell and SQL | funlen default; between eslint 50 and clippy 100 |
| Parameters | 5 | ruff and pylint default; eslint 3 is too tight for constructors |
| Nesting depth | 4 | eslint `max-depth` default and Sonar S134 Python default |
| Duplication | 3 % of lines, 100 tokens | Sonar way gate 3 %; PMD CPD example uses 100 tokens |
| Boolean terms in one condition | 5 | ruff `PLR0916` default |
| File length | 1000 lines | pylint `max-module-lines` default; eslint 300 is per file type |

**The shared change-tracking layer (both modes).** This layer is what makes
a silent change impossible. It has six parts:

1. **File header.** Each file starts with a comment that gives its purpose.
   Python `D100`, Rust `missing_docs` on the crate, TypeScript
   `jsdoc/require-file-overview`, Go `package-comments`, PHP
   `Squiz.Commenting.FileComment`. Shell and SQL need an external check (the
   linters have no such rule).
2. **Docstring on each public unit.** Python `D1xx`, Rust `missing_docs`,
   TypeScript `jsdoc/require-jsdoc` with `publicOnly`, Go revive `exported`,
   PHP `Squiz.Commenting.FunctionComment` and `ClassComment`.
3. **Reason on each suppression.** Python `PGH004` and `RUF100`, Rust
   `allow_attributes_without_reason`, TypeScript `ban-ts-comment` with
   `allow-with-description` and `eslint-comments/require-description`, Go
   `nolintlint` with `require-explanation` and `require-specific`, PHP
   `phpcs:ignore -- reason` and `@phpstan-ignore identifier (reason)`, SQL
   `--warn-unused-ignores`. Shell and SQL reasons need the external check.
4. **Reference from each test to a design id.** The reference checker
   `ref_check.py` reads `arch:` in a test docstring and fails on an unknown
   id, on a changed law section, and on a design claim with no test. This is
   the only tool in the list that ties code to documents.
5. **Docstring coverage number.** interrogate (Python), `cargo doc` warnings
   count (Rust, via `missing_docs`), jsdoc rule counts (TS). The number goes
   in a file and the check fails when it falls (a ratchet).
6. **Test coverage number.** coverage.py, cargo-llvm-cov, c8 or Vitest, `go
   test -cover`, PHPUnit. The number goes in a file and the check fails when
   it falls.

Parts 5 and 6 catch a change that removes a test or a docstring without a
lint finding. Part 4 catches a design change with no test change. Parts 1
to 3 catch code that arrives with no explanation.

## 4. Docstring and doc coverage

| Language | Tool | Threshold option | Default | Realistic threshold |
|---|---|---|---|---|
| Python | interrogate | `--fail-under` | 80.0 (interrogate docs) | clean 80, strict 100 with `ignore-private = true` |
| Python | docstr-coverage | `--fail-under` | 100.0; `--accept-empty` exits 0 on no files (docstr-coverage README) | same as above |
| Rust | rustc `missing_docs` | lint level | allow by default | clean and strict: `-D missing_docs`; strict adds `clippy::missing_errors_doc` and `clippy::missing_panics_doc` (pedantic) |
| TS/JS | eslint-plugin-jsdoc `require-jsdoc` | `publicOnly`, `require` | in the recommended config; `require.FunctionDeclaration` true, others false (rule doc) | clean: `publicOnly: true`; strict: also `ClassDeclaration`, `MethodDefinition`, `ArrowFunctionExpression` |
| Go | revive `exported`, `package-comments` | rule on or off | not in golangci-lint `standard` set | clean and strict: both rules on. Go doc comments must start with the name (go.dev/doc/comment) |
| PHP | phpcs `Squiz.Commenting.FunctionComment`, `ClassComment`, `FileComment` | sniff on or off | not in PSR-12 | clean: `Missing` codes only; strict: whole sniffs |
| Shell, SQL | none | external check of the first comment line | | header only |

interrogate has a `style = "google"` option that counts a class as covered
when either the class or `__init__` has a docstring (interrogate docs). Use
it, because the comment standard picks Google sections.

A realistic threshold is 100 % on public units and no rule on private
units. A ratchet is better than a fixed number: the check stores the last
value and fails when the new value is lower. interrogate and docstr-coverage
both take a float, so the stored value can be exact.

## 5. Test coverage and mutation testing

**Coverage tools and their gate.**

| Language | Tool | Gate option | Exit on failure | Source |
|---|---|---|---|---|
| Python | coverage.py | `coverage report --fail-under=MIN` | 2 | coverage.py `cmd_report` |
| Rust | cargo-llvm-cov | `--fail-under-lines <MIN>`, `--fail-under-functions`, `--fail-under-regions` | 1 | cargo-llvm-cov README |
| TS/JS | c8 | `c8 --check-coverage --lines 100 npm test`; `--100` sets all four | non-zero | c8 README |
| TS/JS | Vitest | `coverage.thresholds.lines` etc.; `perFile`; `autoUpdate`; `100` | non-zero (unverified) | Vitest coverage config |
| Go | `go test -cover -coverprofile=cover.out` then `go tool cover -func=cover.out` | none built in; a script reads the `total:` line | script | cmd/go testing flags |
| PHP | PHPUnit `--coverage-text`, `--coverage-clover` | none built in; "no option to fail the test run based on achieving a minimum coverage percentage" | script | PHPUnit 12 text UI |
| Shell | none read in this session (kcov is the usual answer, unverified) | | | |
| SQL | none | | | |

**Mutation tools.**

| Language | Tool | Gate | Exit codes | Source |
|---|---|---|---|---|
| Python | mutmut | none documented; `mutmut run`, `mutmut browse`, `mutmut export-cicd-stats` | unverified | mutmut docs |
| Rust | cargo-mutants | fails on any missed mutant; `--in-diff DIFF_FILE` limits to changed regions | 0 caught all, 1 usage, 2 missed, 3 timeout, 4 baseline fails | mutants.rs |
| TS/JS | Stryker | `thresholds: { high: 80, low: 60, break: null }`; `break` set makes exit 1 | 1 below `break` | Stryker configuration |
| Go | gremlins `gremlins unleash`; go-mutesting | threshold flags exist (unverified) | unverified | gremlins README |
| PHP | Infection | `--min-msi`, `--min-covered-msi` "used with CI server to automatically control tests quality" | non-zero below threshold (unverified) | Infection CLI options |

**Where each fits.**

- Clean: coverage runs and the total goes into a ratchet file. No fixed
  number. Zero failures on day one, as the reference checker does.
- Strict: coverage on new code at 80 % (the Sonar way gate) and a ratchet on
  the total. Mutation testing on the diff only: cargo-mutants `--in-diff`,
  Stryker incremental mode (unverified flag name), Infection with a git diff
  filter (unverified flag name). A full mutation run is too slow for a
  commit hook and belongs in a nightly job.

## 6. The "small code asks" rule

**What existing tools do.** GitHub linguist counts bytes per language. It
excludes "binary data, vendored code, generated code, documentation, or
\[files\] defined as `data` (e.g. SQL) or `prose` (e.g. Markdown) languages"
(linguist, how-linguist-works). Two facts follow. First, linguist has no
minimum: one shell script makes shell "present". Second, SQL never counts,
because its type is `data`. A tool that copies linguist would never ask
about SQL. tokei and scc count files and lines per language and have no
presence threshold either. tokei respects `.gitignore` and a `.tokeignore`
file. scc adds a complexity estimate per file (scc README).

**Recommended rule.** Count with tokei (`tokei --output json`) or scc. A
language is "present" when it has at least one file and at least 50 lines of
code outside vendored and generated paths. Below that, the tool asks before
it turns the language's checks on. Above that, it turns them on and reports.
Fifty lines is a judgement, not a measured value: one shell script of 20
lines is the case the rule must catch, and a 60-line script already carries
enough logic to break. Generated and vendored paths follow linguist's
`vendor.yml` and `generated.rb` lists, which the tool can copy.

## 7. pre-commit or lefthook as the single runner

**pre-commit** reads `.pre-commit-config.yaml` with `repos`, `rev` and
`hooks`, installs each hook in its own environment and runs it on the staged
files; `pre-commit run --all-files` runs on all files (pre-commit docs). Hook
environments exist for python, node, golang, rust, script and system, among
others. Official or well-known hooks exist for six of the eight languages:

| Language | Hook repository | Hook ids | Source |
|---|---|---|---|
| Python | `astral-sh/ruff-pre-commit` | `ruff-check`, `ruff-format` | ruff-pre-commit README |
| Rust | `doublify/pre-commit-rust` | `fmt`, `cargo-check` (a `clippy` id is likely, unverified) | pre-commit-rust README |
| TS/JS/Vue | `pre-commit/mirrors-eslint`; `biomejs/pre-commit` | `eslint` with `files: \.[jt]sx?$` and `additional_dependencies` for plugins | mirrors-eslint README; pre-commit hooks list |
| Shell | `shellcheck-py/shellcheck-py`; `scop/pre-commit-shfmt` | `shellcheck`; `shfmt` | both READMEs |
| SQL | `sqlfluff/sqlfluff` | `sqlfluff-lint`, `sqlfluff-fix` | sqlfluff `.pre-commit-hooks.yaml` |
| Go | `golangci/golangci-lint` | `golangci-lint`, `golangci-lint-full`, `golangci-lint-fmt`, `golangci-lint-config-verify` | golangci-lint `.pre-commit-hooks.yaml` |
| PHP | none on the official list | use `repo: local` with `language: system` | pre-commit hooks list |

The pre-commit hook list has no PHP entry. A `local` repo with `entry:
vendor/bin/phpstan analyse` and `language: system` covers it. The same
`local` form runs `ref_check.py`, interrogate, complexipy and the ratchets.

**lefthook** reads `lefthook.yml`, installs scripts into `.git/hooks/` and
runs `jobs` with `glob` filters and `{staged_files}` (lefthook docs). It has
no hook registry and no environment management: every tool must already be
on the path. That is simpler and faster but moves the install problem to
the user.

**prek** is a Rust reimplementation of pre-commit that reads the same config
and a `prek.toml` (ruff-pre-commit README mentions it). It is young
(unverified maturity).

**Verdict.** pre-commit. Its registry covers six languages, its `local` form
covers the rest, and its config is one file that a fresh clone can run.

## Python

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | ruff | `select = ["ALL"]` minus formatter conflicts, or the list below | ruff default set (`F`, `E`, `B`, `UP`, `RUF` and more) | ruff rules page |
| Cognitive complexity | complexipy | `complexipy . --max-complexity-allowed 15` | off | complexipy README; ruff issue #2418 is open |
| Cyclomatic | ruff `C901` | `max-complexity = 10` (default) | off | ruff settings |
| Function length | ruff `PLR0915` | `max-statements = 50` (default) | off | ruff settings |
| Parameters | ruff `PLR0913`, `PLR0917` | `max-args = 5`, `max-positional-args = 5` (defaults) | off | ruff settings |
| Nesting | ruff `PLR1702` (preview) | `max-nested-blocks = 4` (default 5) | off | ruff settings |
| Branches, returns, booleans | `PLR0912`, `PLR0911`, `PLR0916` | 12, 6, 5 (defaults) | off | ruff settings |
| Duplication | jscpd | `--threshold 3` | off | jscpd README |
| Dead code | vulture; ruff `F401`, `F841`, `ARG`, `ERA001` | `vulture src --min-confidence 80`; exit 3 on findings | ruff defaults cover `F401`, `F841` | vulture README |
| Security | ruff `S` | on | off | ruff rules page |
| Types | mypy `--strict` or pyright `typeCheckingMode: "strict"` | on | pyright `standard` (its default) | mypy CLI; pyright configuration |
| Docstrings | ruff `D`, `convention = "google"` | all `D` | all `D` (comment standard) | comment standard |
| Doc coverage | interrogate | `--fail-under 100` with `ignore-private` | ratchet from 80 | interrogate docs |
| Suppression | `# noqa: F401  # reason: ...` | `PGH004`, `RUF100` | same | comment standard |
| TODO | `TD002` to `TD005` | on | on | comment standard |
| Coverage | coverage.py | `--fail-under` 80 on new code, ratchet on total | ratchet | coverage.py |
| Mutation | mutmut | diff only, nightly | off | mutmut docs |

Config file: `ruff.toml` at the root, or `[tool.ruff]` in `pyproject.toml`.
Install: `uv tool install ruff` or `pip install ruff`. Command: `ruff check
.`. Exit codes: 0 clean, 1 findings, 2 abnormal (ruff linter page).

Strict `ruff.toml`:

```toml
# Strict rule set. Thresholds follow the uniform table in research-code-rules.
[lint]
select = ["ALL"]
ignore = ["COM812", "ISC001"]  # conflict with ruff format

[lint.pydocstyle]
convention = "google"

[lint.mccabe]
max-complexity = 10

[lint.pylint]
max-args = 5
max-positional-args = 5
max-branches = 12
max-returns = 6
max-statements = 50
max-nested-blocks = 4
max-bool-expr = 5
```

Clean `ruff.toml`:

```toml
# Clean rule set: ruff defaults plus the comment standard.
[lint]
extend-select = ["D", "PGH004", "RUF100", "TD002", "TD003", "TD004", "TD005"]

[lint.pydocstyle]
convention = "google"
```

The two `ignore` codes are the pair that ruff documents as formatter
conflicts (unverified against the current list; run `ruff check` once and
read the warning).

## Rust

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | clippy | `-W clippy::pedantic` plus the restriction lints below | clippy default (`cargo clippy`) | clippy usage |
| Cognitive complexity | `clippy::cognitive_complexity` (restriction group) | `cognitive-complexity-threshold = 15` (default 25) | off | clippy source `cognitive_complexity.rs`; lint configuration |
| Cyclomatic | none in clippy | lizard `-C 10` | off | lizard README |
| Function length | `clippy::too_many_lines` (pedantic) | `too-many-lines-threshold = 60` (default 100) | off | clippy source `functions/mod.rs`; lint configuration |
| Parameters | `clippy::too_many_arguments` (complexity, on by default) | `too-many-arguments-threshold = 5` (default 7) | default 7 | lint configuration |
| Nesting | `clippy::excessive_nesting` (complexity; off until a threshold is set) | `excessive-nesting-threshold = 4` | off | clippy source `excessive_nesting.rs` |
| Duplication | jscpd | `--threshold 3` | off | jscpd README |
| Dead code | rustc `dead_code`, `unused` | `-D warnings` | warn | clippy usage |
| Security | cargo-audit | `cargo audit` | off | cargo-audit README |
| Docstrings | rustc `missing_docs`; `clippy::missing_safety_doc`; `clippy::undocumented_unsafe_blocks` | plus `clippy::missing_errors_doc`, `clippy::missing_panics_doc` (pedantic) | the three (comment standard) | comment standard; clippy lint list |
| Doc coverage | `missing_docs` is binary | `-D missing_docs` and `clippy::missing_docs_in_private_items` (restriction) | `-D missing_docs` | clippy source `missing_doc.rs` |
| Suppression | `#[expect(lint, reason = "...")]` | `clippy::allow_attributes_without_reason`, `clippy::allow_attributes` | `allow_attributes_without_reason` | comment standard |
| Format | rustfmt | `cargo fmt --all -- --check` exits 1 on a diff | same | rustfmt README |
| Coverage | cargo-llvm-cov | `--fail-under-lines 80` on new code, ratchet on total | ratchet | cargo-llvm-cov README |
| Mutation | cargo-mutants | `cargo mutants --in-diff <diff>`; exit 2 on a missed mutant | off | mutants.rs |

Config file: `clippy.toml` or `.clippy.toml` next to `Cargo.toml`; lint
levels in `[lints.clippy]` of `Cargo.toml` or on the command line. Install:
`rustup component add clippy rustfmt`; `cargo install cargo-llvm-cov`;
`cargo install --locked cargo-mutants`. Command: `cargo clippy --all-targets
-- -D warnings`. Exit: non-zero when a denied lint fires (clippy usage).

Strict `clippy.toml`:

```toml
# Strict thresholds. Group levels live in Cargo.toml [lints.clippy].
cognitive-complexity-threshold = 15
too-many-arguments-threshold = 5
too-many-lines-threshold = 60
excessive-nesting-threshold = 4
```

Strict `Cargo.toml` fragment:

```toml
[lints.rust]
missing_docs = "deny"

[lints.clippy]
pedantic = { level = "deny", priority = -1 }
cognitive_complexity = "deny"
excessive_nesting = "deny"
missing_docs_in_private_items = "deny"
allow_attributes_without_reason = "deny"
allow_attributes = "deny"
undocumented_unsafe_blocks = "deny"
```

Clean: the command line of the comment standard, unchanged:
`cargo clippy --quiet -- -D missing_docs -D clippy::missing_safety_doc -D
clippy::undocumented_unsafe_blocks -D clippy::allow_attributes_without_reason`.

Note: `cognitive_complexity` sits in the **restriction** group in the
current source, not in nursery as older posts say. It is stable to enable.

## TypeScript and JavaScript

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | eslint 9 flat config, typescript-eslint | `strict-type-checked` + `stylistic-type-checked` | `recommended` | typescript-eslint configs |
| Cognitive complexity | eslint-plugin-sonarjs `cognitive-complexity`; or Biome `noExcessiveCognitiveComplexity` | 15 | off | sonarjs README (rule id verified, default unverified); Biome rule page (default 15, range 1 to 254) |
| Cyclomatic | eslint `complexity` | `["error", 10]` (default 20) | off | eslint rule page |
| Function length | eslint `max-lines-per-function` | `["error", { max: 60, skipBlankLines: true, skipComments: true }]` (default 50) | off | eslint rule page |
| Parameters | eslint `max-params` | `["error", 5]` (default 3) | off | eslint rule page |
| Nesting | eslint `max-depth` | `["error", 4]` (default 4) | off | eslint rule page |
| Statements, file length | `max-statements` 10, `max-lines` 300 (defaults) | on | off | eslint rule pages |
| Duplication | sonarjs `no-identical-functions`, `no-duplicate-string`; jscpd | on; `--threshold 3` | off | sonarjs README; jscpd README |
| Dead code | knip; eslint `no-unused-vars` | `knip` (exit 1 on findings) | `no-unused-vars` (in recommended) | knip CLI reference |
| Security | sonarjs recommended; semgrep `p/javascript` (unverified ruleset name) | on | off | semgrep CLI |
| Docstrings | eslint-plugin-jsdoc | `flat/recommended-typescript-error` + `require-jsdoc` with `publicOnly: true` and `require` for classes, methods and arrows | `flat/recommended-typescript-error` (comment standard) | jsdoc rule page |
| File header | `jsdoc/require-file-overview` | on | on | comment standard, D2.9 |
| Suppression | `ban-ts-comment` `allow-with-description`; `eslint-comments/require-description` | both, `minimumDescriptionLength: 10` (unverified option name) | both | comment standard |
| Types | `tsc --noEmit` with `"strict": true` | on | on | (well known, unverified page) |
| Coverage | c8 or Vitest | `--check-coverage --lines 80`; Vitest `coverage.thresholds` | ratchet | c8 README; Vitest |
| Mutation | Stryker | `thresholds.break = 60`, incremental | off | Stryker configuration |

Config file: `eslint.config.mjs` at the root. Install: `npm install -D eslint
typescript-eslint eslint-plugin-jsdoc @eslint-community/eslint-plugin-eslint-comments
eslint-plugin-sonarjs`. Command: `npx eslint --max-warnings 0 .`. Exit codes:
0 clean, 1 at least one error or more warnings than `--max-warnings`, 2
configuration or internal error (eslint CLI reference).

Strict `eslint.config.mjs`:

```javascript
// Strict rule set for TypeScript. Thresholds follow the uniform table.
import tseslint from "typescript-eslint";
import jsdoc from "eslint-plugin-jsdoc";
import sonarjs from "eslint-plugin-sonarjs";
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";

export default tseslint.config(
  {
    files: ["**/*.ts", "**/*.tsx"],
    extends: [
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      jsdoc.configs["flat/recommended-typescript-error"],
      sonarjs.configs.recommended,
    ],
    languageOptions: { parserOptions: { projectService: true } },
    plugins: { "eslint-comments": eslintComments },
    rules: {
      "complexity": ["error", 10],
      "max-depth": ["error", 4],
      "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
      "max-params": ["error", 5],
      "max-statements": ["error", 10],
      "max-lines": ["error", 300],
      "sonarjs/cognitive-complexity": ["error", 15],
      "jsdoc/require-jsdoc": ["error", {
        publicOnly: true,
        require: { FunctionDeclaration: true, ClassDeclaration: true, MethodDefinition: true, ArrowFunctionExpression: true },
      }],
      "jsdoc/require-file-overview": "error",
      "@typescript-eslint/ban-ts-comment": ["error", { "ts-expect-error": "allow-with-description" }],
      "eslint-comments/require-description": "error",
    },
  },
);
```

Clean: the existing `lint/ts/eslint.config.mjs` of the comment standard,
extended with `tseslint.configs.recommended`.

Biome is an alternative when a repository has no eslint. `biome lint` exits
non-zero on diagnostics; `--error-on-warnings` turns warnings into failures;
config is `biome.json` (Biome CLI reference). It has no jsdoc or Vue plugin,
so it cannot carry the shared layer alone.

## Shell

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | shellcheck | `--severity style --enable all` | default (severity `style` is the default) | shellcheck man page |
| Metrics | none | none exist for shell | none | lizard has no shell reader |
| Duplication | jscpd (Shell is in its formats) | `--threshold 3` | off | jscpd README |
| Dead code | shellcheck SC2034 (unused variable) | on by default | on | shellcheck (rule id well known, unverified page) |
| Format | shfmt | `shfmt -d -i 2 -ci -bn .` errors on a diff | `shfmt -d .` | shfmt man page |
| Header | external check f | on | on | comment standard, D2.9 |
| Suppression | `# shellcheck disable=SC2086  # reason` | external check f enforces the reason; shellcheck has no reason field | same | shellcheck wiki Ignore; D2.9 |
| Tests, coverage | none read this session (bats and kcov are the usual pair, unverified) | | | |

Config file: `.shellcheckrc` in the script directory or a parent, with
`key=value` lines such as `enable=all` (man page). shfmt reads
`.editorconfig` when no flags are given (shfmt man page). Install: distro
package `shellcheck`; `go install mvdan.cc/sh/v3/cmd/shfmt@latest`. Command:
`shellcheck --severity style *.sh`. Exit codes: 0 no issues, 1 issues, 2 a
file could not be processed, 3 bad syntax on the command line, 4 bad option
(man page).

Strict `.shellcheckrc`:

```
# Strict: every optional check on.
enable=all
```

Clean: no file. Both modes run the header and reason check.

## SQL

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | sqlfluff | all rules (`rules = all`) | `core` group (the only group) | sqlfluff rule configuration |
| Metrics | none | none exist | none | |
| Duplication | jscpd (SQL is in its formats) | `--threshold 3` | off | jscpd README |
| Dead code | none | | | |
| Header | external check f | on | on | D2.9 |
| Suppression | `/* reason */ -- noqa: LT01` | `--warn-unused-ignores` plus check f | check f | sqlfluff `commands.py`; D2.9 |
| Format | `sqlfluff fix` | `sqlfluff format` (unverified subcommand) | off | |

Config file: `.sqlfluff` at the root, or `[tool.sqlfluff.*]` in
`pyproject.toml`; a `.sqlfluffignore` file lists paths (sqlfluff ignoring
page). Install: `uvx sqlfluff@4.3.0` (the comment standard pins it).
Command: `sqlfluff lint --config .sqlfluff <files>`. Exit codes:
`EXIT_SUCCESS` 0, `EXIT_FAIL` 1 on violations, `EXIT_ERROR` 2; `--nofail`
forces 0 (sqlfluff `commands.py`). Inline forms: `-- noqa`, `-- noqa: CP02`,
`-- noqa: disable=AL02`, `-- noqa: enable=all` (ignoring page). sqlfluff has
no reason field; the block comment before `--` carries it (D2.9).

Strict `.sqlfluff`:

```ini
[sqlfluff]
dialect = ansi
rules = all
warn_unused_ignores = True
```

Clean: `dialect = ansi` only, as today.

## Go

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | golangci-lint v2 | `default: all` minus a short disable list | `default: standard` | golangci-lint config file; migration guide |
| Cognitive complexity | gocognit | `min-complexity: 15` (default 30; docs recommend 10 to 20) | off | golangci-lint settings |
| Cyclomatic | cyclop or gocyclo | `max-complexity: 10` (cyclop default 10; gocyclo default 30) | off | golangci-lint settings |
| Function length | funlen | `lines: 60`, `statements: 40` (defaults) | off | golangci-lint settings |
| Parameters | revive `argument-limit` | 5 (revive default 8) | off | revive rules |
| Nesting | nestif; revive `max-control-nesting` | nestif `min-complexity: 4` (default 5); revive 4 (default 5) | off | golangci-lint settings; revive rules |
| Duplication | dupl | `threshold: 100` (default 150 tokens) | off | golangci-lint settings |
| Dead code | `unused`, `unparam`, revive `unused-parameter` | on | `unused` (in standard) | golangci-lint linters |
| Security | gosec | on | off | gosec README |
| Docstrings | revive `exported`, `package-comments` | on | on | revive rules; go.dev/doc/comment |
| Suppression | `//nolint:gocyclo // reason` | nolintlint `require-explanation: true`, `require-specific: true`, `allow-unused: false` | same | golangci-lint false positives; nolintlint settings |
| Line length | lll | 120 (default) | off | golangci-lint settings |
| Maintainability | maintidx | `under: 20` (default) | off | golangci-lint settings |
| Format | `golangci-lint fmt` (gofmt, gofumpt, goimports) | on | gofmt | migration guide |
| Coverage | `go test -cover -coverprofile=cover.out ./...` then `go tool cover -func=cover.out` | script reads `total:`; 80 on new code, ratchet | ratchet | cmd/go |
| Mutation | gremlins | diff only, nightly (flags unverified) | off | gremlins README |

Config file: `.golangci.yml` at the root with `version: "2"`. Install:
binary from the release page, or `go install
github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest` (unverified
module path). Command: `golangci-lint run ./...`. Exit codes: 0 success, 1
issues found, 2 warning in test, 3 failure, 4 timeout, 5 no Go files, 6 no
config file detected, 7 error was logged (`pkg/exitcodes/exitcodes.go`).

Strict `.golangci.yml`:

```yaml
# Strict rule set. Thresholds follow the uniform table.
version: "2"
linters:
  default: all
  disable:
    - depguard        # needs a project-specific import list
    - exhaustruct     # too noisy for option structs
  settings:
    gocognit:
      min-complexity: 15
    cyclop:
      max-complexity: 10
    funlen:
      lines: 60
      statements: 40
    nestif:
      min-complexity: 4
    dupl:
      threshold: 100
    lll:
      line-length: 120
    nolintlint:
      allow-unused: false
      require-explanation: true
      require-specific: true
    revive:
      enable-default-rules: true
      rules:
        - name: exported
        - name: package-comments
        - name: argument-limit
          arguments: [5]
        - name: max-control-nesting
          arguments: [4]
formatters:
  enable: [gofmt, gofumpt, goimports]
```

Clean `.golangci.yml`:

```yaml
# Clean rule set: standard linters plus the comment standard.
version: "2"
linters:
  default: standard
  enable: [revive, nolintlint]
  settings:
    nolintlint:
      require-explanation: true
      require-specific: true
    revive:
      enable-default-rules: true
      rules:
        - name: exported
        - name: package-comments
formatters:
  enable: [gofmt]
```

The two `disable` entries in strict are a judgement (unverified against a
real run). staticcheck runs inside golangci-lint; its standalone exit code
was not found in the CLI page read this session.

## PHP

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Types | phpstan | `--level max` (10 is the highest of 11 levels) plus phpstan-strict-rules | level 6 (judgement) | phpstan rule levels; strict-rules README |
| Types (alternative) | psalm | level 1 (strictest of 1 to 8; default 2) | off | psalm error levels |
| Cognitive complexity | none in phpmd or phpstan | lizard has none either; gap | off | |
| Cyclomatic | phpmd `CyclomaticComplexity` | `reportLevel` 10 (default) | off | phpmd codesize |
| NPath | phpmd `NPathComplexity` | 200 (default) | off | phpmd codesize |
| Function length | phpmd `ExcessiveMethodLength` | `minimum` 60 (default 100) | off | phpmd codesize |
| Parameters | phpmd `ExcessiveParameterList` | `minimum` 6 (rule fires at the value; default 10) | off | phpmd codesize |
| Class size | `ExcessiveClassLength` 1000, `TooManyMethods` 25, `TooManyPublicMethods` 10, `ExcessiveClassComplexity` 50 | defaults | off | phpmd codesize |
| Nesting | none in phpmd | lizard does not report nesting; gap | off | |
| Duplication | phpcpd (systemsdk fork) | `--min-lines 5 --min-tokens 70 --max-percentage 3` | off | phpcpd README |
| Dead code | phpmd `unusedcode` (`UnusedPrivateField`, `UnusedLocalVariable`, `UnusedPrivateMethod`, `UnusedFormalParameter`) | on | on | phpmd unusedcode |
| Style | php-cs-fixer or phpcs PSR-12 | `@PSR12` + `@Symfony` (php-cs-fixer sets, unverified names) | `@PSR12` | php-cs-fixer usage |
| Docstrings | phpcs `Squiz.Commenting.FunctionComment`, `ClassComment`, `FileComment` | whole sniffs | `.Missing` codes only | phpcs sniff source |
| Suppression | `// phpcs:ignore Std.Cat.Sniff -- reason`; `// @phpstan-ignore identifier (reason)`; `@SuppressWarnings(PHPMD.Rule)` | `reportUnmatchedIgnoredErrors: true` (phpstan default) | same | phpcs advanced usage; phpstan ignoring |
| Coverage | PHPUnit `--coverage-clover` | script reads the Clover total; 80 on new code | ratchet | PHPUnit text UI |
| Mutation | Infection | `--min-msi 60 --min-covered-msi 80` on the diff, nightly | off | Infection CLI options |

Config files: `phpstan.neon.dist` (name from common use; the levels page
does not list names), `phpmd.xml` ruleset, `.php-cs-fixer.dist.php`,
`phpcs.xml.dist` (search order `.phpcs.xml`, `phpcs.xml`, `.phpcs.xml.dist`,
`phpcs.xml.dist`), `infection.json5`. Install: `composer require --dev
phpstan/phpstan phpstan/phpstan-strict-rules phpmd/phpmd
friendsofphp/php-cs-fixer squizlabs/php_codesniffer infection/infection
systemsdk/phpcpd` (package names other than phpstan-strict-rules unverified).

Commands and exit codes:

- `vendor/bin/phpstan analyse --level max src`: 0 means no errors (phpstan
  CLI page); a non-zero code on errors (value unverified).
- `vendor/bin/phpmd src text codesize,unusedcode,design`: 0 clean, 1
  exception, 2 violations, 3 a file could not be processed;
  `--ignore-violations-on-exit` forces 0 (phpmd documentation).
- `vendor/bin/php-cs-fixer check`: bit flags 0 ok, 1 general error, 4
  invalid syntax, 8 files need fixing, 16 application config error, 32 fixer
  config error, 64 exception (php-cs-fixer usage).
- `vendor/bin/phpcs`: as of 4.0, 0 clean, 1 fixable issues, 2 non-fixable
  issues, 3 both, 16 processing error, 64 requirements not met (phpcs
  advanced usage). `ignore_warnings_on_exit` and `ignore_errors_on_exit`
  change this (phpcs configuration options).
- `vendor/bin/phpcpd src`: non-zero on clones unless
  `--ignore-violations-on-exit` (phpcpd README).

Strict `phpmd.xml`:

```xml
<?xml version="1.0"?>
<!-- Strict phpmd ruleset. Thresholds follow the uniform table. -->
<ruleset name="strict">
  <rule ref="rulesets/codesize.xml/CyclomaticComplexity">
    <properties><property name="reportLevel" value="10"/></properties>
  </rule>
  <rule ref="rulesets/codesize.xml/ExcessiveMethodLength">
    <properties><property name="minimum" value="60"/></properties>
  </rule>
  <rule ref="rulesets/codesize.xml/ExcessiveParameterList">
    <properties><property name="minimum" value="6"/></properties>
  </rule>
  <rule ref="rulesets/codesize.xml/NPathComplexity"/>
  <rule ref="rulesets/codesize.xml/ExcessiveClassComplexity"/>
  <rule ref="rulesets/unusedcode.xml"/>
  <rule ref="rulesets/design.xml"/>
  <rule ref="rulesets/cleancode.xml"/>
</ruleset>
```

Clean `phpmd.xml`: `rulesets/unusedcode.xml` only. Both modes run phpstan,
phpcs with the three commenting sniffs, and the reference checker.

## Vue single-file components

Vue adds a parser and a rule set on top of the TypeScript section. The
`<script>` block gets every TypeScript rule; the `<template>` block gets
eslint-plugin-vue.

| Aspect | Tool | Strict | Clean | Source |
|---|---|---|---|---|
| Lint set | eslint-plugin-vue | `flat/recommended` (all rules as errors: the `-error` variants) | `flat/essential` | eslint-plugin-vue user guide |
| Parser | vue-eslint-parser with `parserOptions.parser: "@typescript-eslint/parser"` | on | on | user guide |
| Template depth | `vue/max-template-depth` | `{ maxDepth: 8 }` (no default; judgement) | off | rule page |
| Props | `vue/max-props` | `{ maxProps: 10 }` (no default; judgement) | off | rule page |
| Block length | `vue/max-lines-per-block` | `{ template: 200, script: 300, style: 200, skipBlankLines: true }` (no default) | off | rule page |
| Script lang | `vue/block-lang` | `{ script: { lang: "ts" } }` | off | rules page (uncategorized) |
| Dead code | `vue/no-unused-components`, `vue/no-unused-vars` | in `flat/essential` | on | rule page |
| Types | `vue-tsc --noEmit` | on | on | vue-tsc README |
| Script metrics | eslint core and sonarjs rules from the TS section | on | off | eslint rule pages |
| Duplication | jscpd (Vue is in its formats); lizard reads VueJS | `--threshold 3` | off | jscpd, lizard READMEs |
| Coverage | Vitest with `@vitest/coverage-v8` | `coverage.thresholds` | ratchet | Vitest coverage |

Config: same `eslint.config.mjs`, with a second block for `**/*.vue`.
Install: `npm install -D eslint-plugin-vue vue-eslint-parser vue-tsc`.
Command: `npx eslint --max-warnings 0 . && npx vue-tsc --noEmit`. Exit codes
as eslint; vue-tsc exits as tsc (non-zero on a type error, unverified).

Strict fragment for `eslint.config.mjs`:

```javascript
// Vue block. Add after the TypeScript block.
import pluginVue from "eslint-plugin-vue";

export default [
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: "@typescript-eslint/parser" } },
    rules: {
      "vue/block-lang": ["error", { script: { lang: "ts" } }],
      "vue/max-template-depth": ["error", { maxDepth: 8 }],
      "vue/max-props": ["error", { maxProps: 10 }],
      "vue/max-lines-per-block": ["error", { template: 200, script: 300, style: 200, skipBlankLines: true }],
    },
  },
];
```

The three Vue size limits have no upstream default. The values are a
starting point, not a measured value.

## Decision list

| # | Decision | Options | Recommended default | Reason |
|---|---|---|---|---|
| D1 | Engine | SonarQube Community Build; per-language tools | per-language tools | Runs offline, config lives in the repo, exit code gates a commit. SonarQube needs a server; CodeQL's licence forbids CI on private code. |
| D2 | Thresholds | each tool's default; one uniform table | uniform table (15, 10, 60, 5, 4, 3 %) | One number per metric is easier to learn and to explain. Each value is a documented default of at least one tool. |
| D3 | Cognitive complexity in Python | skip (ruff has none); complexipy; flake8 plugin | complexipy in strict | ruff issue #2418 is open. complexipy has a pre-commit hook. flake8 would add a second linter. |
| D4 | Runner | pre-commit; lefthook; prek | pre-commit | Hooks exist for six of eight languages; `local` covers PHP and the custom checks. lefthook needs every tool pre-installed. |
| D5 | Language presence | linguist rules; any file; N lines | at least 1 file and 50 code lines by tokei, else ask | linguist has no minimum and drops SQL as `data`. Fifty lines separates a glue script from logic. |
| D6 | Docstring coverage gate | fixed 80; fixed 100; ratchet | clean: ratchet from the current value; strict: 100 on public units | A fixed number fails on day one in an old repo. A ratchet never fails on day one and never lets the value fall. |
| D7 | Test coverage gate | none; fixed 80; ratchet; 80 on new code | clean: ratchet; strict: 80 on new code plus ratchet | Same reason as D6. 80 on new code is the Sonar way gate. |
| D8 | Mutation testing | none; full run; diff only | strict only, diff only, in a nightly job | A full run takes hours. `--in-diff`, Stryker incremental and Infection diff filters keep it to minutes. |
| D9 | Duplication tool | one per language; jscpd for all | jscpd for all eight, `--threshold 3` | One tool, 224 formats, SARIF output. dupl and phpcpd stay as extras. |
| D10 | Shell and SQL metrics | accept the gap; lizard | accept the gap | No tool reads shell or ANSI SQL for complexity. Header, reason, duplication and shellcheck `enable=all` remain. |
| D11 | TS engine | eslint; Biome | eslint | Biome has no jsdoc, Vue or sonarjs plugin, so it cannot carry the shared layer. Biome stays as the cognitive complexity fallback. |
| D12 | Warnings | allow; fail | fail (`--max-warnings 0`, `-D warnings`, `--error-on-warnings`) | A warning that nobody reads is a silent change. |
| D13 | PHP type checker | phpstan; psalm; both | phpstan, `--level max` in strict, level 6 in clean | phpstan-strict-rules and the `@phpstan-ignore identifier (reason)` form fit the suppression rule. The clean level is a judgement. |
| D14 | Security layer | none; linter-native; semgrep | linter-native in clean (`S`, gosec, cargo-audit); semgrep added in strict | semgrep needs network on first run and a registry ruleset choice. |

## Sources

All read on 2026-09-24.

1. Sonar, quality gates: https://docs.sonarsource.com/sonarqube-server/latest/instance-administration/quality-gates/
2. Sonar, introduction to quality gates (Sonar way conditions): https://docs.sonarsource.com/sonarqube-server/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates
3. Sonar, quality profiles: https://docs.sonarsource.com/sonarqube-server/latest/instance-administration/quality-profiles/
4. Sonar, Cognitive Complexity white paper: https://www.sonarsource.com/docs/CognitiveComplexity.pdf
5. SonarSource/sonarqube README (Community Build, LGPL 3.0): https://github.com/sonarsource/sonarqube
6. sonar-python `CognitiveComplexityFunctionCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-python/master/python-checks/src/main/java/org/sonar/python/checks/CognitiveComplexityFunctionCheck.java
7. sonar-python `TooManyParametersCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-python/master/python-checks/src/main/java/org/sonar/python/checks/TooManyParametersCheck.java
8. sonar-python `NestedControlFlowDepthCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-python/master/python-checks/src/main/java/org/sonar/python/checks/NestedControlFlowDepthCheck.java
9. sonar-python `TooManyLinesInFunctionCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-python/master/python-checks/src/main/java/org/sonar/python/checks/TooManyLinesInFunctionCheck.java
10. sonar-python `FunctionComplexityCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-python/master/python-checks/src/main/java/org/sonar/python/checks/FunctionComplexityCheck.java
11. sonar-php `TooManyLinesInFunctionCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-php/master/php-checks/src/main/java/org/sonar/php/checks/TooManyLinesInFunctionCheck.java
12. sonar-php `StringLiteralDuplicatedCheck.java`: https://raw.githubusercontent.com/SonarSource/sonar-php/master/php-checks/src/main/java/org/sonar/php/checks/StringLiteralDuplicatedCheck.java
13. semgrep CLI reference (exit codes): https://semgrep.dev/docs/cli-reference
14. semgrep local scans: https://semgrep.dev/docs/getting-started/cli
15. semgrep LICENSE (LGPL 2.1): https://raw.githubusercontent.com/semgrep/semgrep/develop/LICENSE
16. CodeQL CLI terms: https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md
17. codeql-action README: https://github.com/github/codeql-action
18. ruff rules: https://docs.astral.sh/ruff/rules/
19. ruff settings: https://docs.astral.sh/ruff/settings/
20. ruff linter (exit codes, noqa, RUF100): https://docs.astral.sh/ruff/linter/
21. ruff issue #2418, cognitive complexity: https://github.com/astral-sh/ruff/issues/2418
22. complexipy README: https://github.com/rohaquinlop/complexipy
23. flake8-cognitive-complexity README: https://github.com/Melevir/flake8-cognitive-complexity
24. vulture README: https://github.com/jendrikseipp/vulture
25. mypy command line (`--strict` list): https://mypy.readthedocs.io/en/stable/command_line.html
26. pyright configuration: https://raw.githubusercontent.com/microsoft/pyright/main/docs/configuration.md
27. pylint options: https://pylint.readthedocs.io/en/stable/user_guide/configuration/all-options.html
28. interrogate: https://interrogate.readthedocs.io/en/latest/
29. docstr-coverage README: https://github.com/HunterMcGushion/docstr_coverage
30. coverage.py report: https://coverage.readthedocs.io/en/latest/commands/cmd_report.html
31. mutmut docs: https://mutmut.readthedocs.io/en/latest/
32. ruff-pre-commit README: https://github.com/astral-sh/ruff-pre-commit
33. clippy lint configuration: https://doc.rust-lang.org/clippy/lint_configuration.html
34. clippy usage: https://doc.rust-lang.org/clippy/usage.html
35. clippy lint list: https://rust-lang.github.io/rust-clippy/master/index.html
36. clippy source, `cognitive_complexity.rs`: https://raw.githubusercontent.com/rust-lang/rust-clippy/master/clippy_lints/src/cognitive_complexity.rs
37. clippy source, `excessive_nesting.rs`: https://raw.githubusercontent.com/rust-lang/rust-clippy/master/clippy_lints/src/excessive_nesting.rs
38. clippy source, `functions/mod.rs`: https://raw.githubusercontent.com/rust-lang/rust-clippy/master/clippy_lints/src/functions/mod.rs
39. clippy source, `attrs/mod.rs`: https://raw.githubusercontent.com/rust-lang/rust-clippy/master/clippy_lints/src/attrs/mod.rs
40. clippy source, `missing_doc.rs`: https://raw.githubusercontent.com/rust-lang/rust-clippy/master/clippy_lints/src/missing_doc.rs
41. rustfmt README: https://github.com/rust-lang/rustfmt
42. cargo-llvm-cov README: https://github.com/taiki-e/cargo-llvm-cov
43. cargo-mutants book: https://mutants.rs/ and https://mutants.rs/print.html
44. cargo-audit: https://github.com/rustsec/rustsec/tree/main/cargo-audit
45. pre-commit-rust: https://github.com/doublify/pre-commit-rust
46. eslint `complexity`: https://eslint.org/docs/latest/rules/complexity
47. eslint `max-depth`: https://eslint.org/docs/latest/rules/max-depth
48. eslint `max-lines-per-function`: https://eslint.org/docs/latest/rules/max-lines-per-function
49. eslint `max-params`: https://eslint.org/docs/latest/rules/max-params
50. eslint `max-lines`: https://eslint.org/docs/latest/rules/max-lines
51. eslint `max-statements`: https://eslint.org/docs/latest/rules/max-statements
52. eslint `no-unused-vars`: https://eslint.org/docs/latest/rules/no-unused-vars
53. eslint CLI (exit codes, `--max-warnings`): https://eslint.org/docs/latest/use/command-line-interface
54. typescript-eslint shared configs: https://typescript-eslint.io/users/configs/
55. eslint-plugin-sonarjs README: https://unpkg.com/eslint-plugin-sonarjs/README.md
56. Biome `noExcessiveCognitiveComplexity`: https://biomejs.dev/linter/rules/no-excessive-cognitive-complexity/
57. Biome CLI: https://biomejs.dev/reference/cli/
58. eslint-plugin-jsdoc README: https://github.com/gajus/eslint-plugin-jsdoc
59. eslint-plugin-jsdoc `require-jsdoc`: https://raw.githubusercontent.com/gajus/eslint-plugin-jsdoc/main/docs/rules/require-jsdoc.md
60. eslint-plugin-eslint-comments `require-description`: https://github.com/eslint-community/eslint-plugin-eslint-comments/blob/main/docs/rules/require-description.md
61. knip CLI (exit codes): https://knip.dev/reference/cli
62. jscpd README: https://github.com/kucherenko/jscpd
63. PMD CPD: https://pmd.github.io/pmd/pmd_userdocs_cpd.html
64. lizard README: https://raw.githubusercontent.com/terryyin/lizard/master/README.rst
65. c8 README: https://github.com/bcoe/c8
66. Vitest coverage guide and config: https://vitest.dev/guide/coverage.html and https://vitest.dev/config/coverage.html
67. Stryker configuration: https://stryker-mutator.io/docs/stryker-js/configuration/
68. mirrors-eslint: https://github.com/pre-commit/mirrors-eslint
69. shellcheck man page: https://www.mankier.com/1/shellcheck
70. shellcheck wiki, Ignore: https://github.com/koalaman/shellcheck/wiki/Ignore
71. shfmt man page: https://raw.githubusercontent.com/mvdan/sh/master/cmd/shfmt/shfmt.1.scd
72. shellcheck-py: https://github.com/shellcheck-py/shellcheck-py
73. pre-commit-shfmt: https://github.com/scop/pre-commit-shfmt
74. sqlfluff CLI: https://docs.sqlfluff.com/en/stable/reference/cli.html
75. sqlfluff rule configuration: https://docs.sqlfluff.com/en/stable/configuration/rule_configuration.html
76. sqlfluff ignoring: https://docs.sqlfluff.com/en/stable/configuration/ignoring_configuration.html
77. sqlfluff `commands.py` (exit codes): https://raw.githubusercontent.com/sqlfluff/sqlfluff/main/src/sqlfluff/cli/commands.py
78. sqlfluff pre-commit hooks: https://github.com/sqlfluff/sqlfluff/blob/main/.pre-commit-hooks.yaml
79. golangci-lint settings: https://golangci-lint.run/docs/linters/configuration/
80. golangci-lint linters: https://golangci-lint.run/docs/linters/
81. golangci-lint config file: https://golangci-lint.run/docs/configuration/file/
82. golangci-lint false positives (nolint): https://golangci-lint.run/docs/linters/false-positives/
83. golangci-lint v2 migration guide: https://golangci-lint.run/docs/product/migration-guide/
84. golangci-lint exit codes: https://raw.githubusercontent.com/golangci/golangci-lint/main/pkg/exitcodes/exitcodes.go
85. golangci-lint pre-commit hooks: https://raw.githubusercontent.com/golangci/golangci-lint/main/.pre-commit-hooks.yaml
86. gocognit README: https://github.com/uudashr/gocognit
87. gocyclo README: https://github.com/fzipp/gocyclo
88. revive rules: https://raw.githubusercontent.com/mgechev/revive/master/RULES_DESCRIPTIONS.md
89. staticcheck CLI: https://staticcheck.dev/docs/running-staticcheck/cli/
90. gosec README: https://github.com/securego/gosec
91. Go doc comments: https://go.dev/doc/comment
92. cmd/go testing flags: https://pkg.go.dev/cmd/go#hdr-Testing_flags
93. gremlins README: https://github.com/go-gremlins/gremlins
94. go-mutesting README: https://github.com/zimmski/go-mutesting
95. phpstan rule levels: https://phpstan.org/user-guide/rule-levels
96. phpstan ignoring errors: https://phpstan.org/user-guide/ignoring-errors
97. phpstan command line: https://phpstan.org/user-guide/command-line-usage
98. phpstan-strict-rules: https://github.com/phpstan/phpstan-strict-rules
99. psalm error levels: https://psalm.dev/docs/running_psalm/error_levels/
100. phpmd code size rules: https://phpmd.org/rules/codesize.html
101. phpmd unused code rules: https://phpmd.org/rules/unusedcode.html
102. phpmd documentation (exit codes): https://phpmd.org/documentation/index.html
103. phpmd suppress warnings: https://phpmd.org/documentation/suppress-warnings.html
104. php-cs-fixer usage: https://cs.symfony.com/doc/usage.html
105. phpcs advanced usage: https://github.com/PHPCSStandards/PHP_CodeSniffer/wiki/Advanced-Usage
106. phpcs configuration options: https://github.com/PHPCSStandards/PHP_CodeSniffer/wiki/Configuration-Options
107. phpcs `Squiz.Commenting.FunctionComment` sniff: https://github.com/PHPCSStandards/PHP_CodeSniffer/blob/master/src/Standards/Squiz/Sniffs/Commenting/FunctionCommentSniff.php
108. phpcpd fork README: https://github.com/systemsdk/phpcpd
109. PHPUnit 12 code coverage and text UI: https://docs.phpunit.de/en/12.0/code-coverage.html and https://docs.phpunit.de/en/12.0/textui.html
110. Infection CLI options: https://infection.github.io/guide/command-line-options.html
111. eslint-plugin-vue user guide: https://eslint.vuejs.org/user-guide/
112. eslint-plugin-vue rules: https://eslint.vuejs.org/rules/
113. `vue/max-props`, `vue/max-template-depth`, `vue/max-lines-per-block`: https://eslint.vuejs.org/rules/max-props.html, https://eslint.vuejs.org/rules/max-template-depth.html, https://eslint.vuejs.org/rules/max-lines-per-block.html
114. vue-tsc README: https://github.com/vuejs/language-tools/tree/master/packages/tsc
115. pre-commit docs: https://pre-commit.com/
116. pre-commit hooks list: https://pre-commit.com/hooks.html
117. lefthook: https://lefthook.dev/ and https://lefthook.dev/configuration/
118. linguist, how it works: https://raw.githubusercontent.com/github-linguist/linguist/main/docs/how-linguist-works.md
119. linguist overrides: https://github.com/github-linguist/linguist/blob/main/docs/overrides.md
120. tokei README: https://github.com/XAMPPRocky/tokei
121. scc README: https://github.com/boyter/scc
122. Local: `docs/reference/comment-standard.md`, `docs/ARCHITECTURE.md` D1.5, D2.9, D2.11, `lint/ruff.toml`, `lint/.sqlfluff`, `lint/ts/eslint.config.mjs`, `lint/ts/package.json` and `README.md` of the reference checker repository.
