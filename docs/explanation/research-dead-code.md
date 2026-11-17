---
id: research-dead-code
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-09-24
---

# Research: dead code, graphify and the native tools

## Summary

The question: should the repository-setup tool require `graphify` and use its
graph to find dead code? The answer is no. On the test repository the graph
gave 156 candidates and 0 real dead functions. Precision was 0 of 156. The
two candidates that were not pytest entry points were both false positives:
the extractor drops calls made inside nested functions and lambdas. Native
tools model entry points, visibility and reachability; graphify does not.
Native tools also give an exit code; graphify gives a graph to query.
The recommendation is option (b): native tools find dead code, and graphify
is optional, for cross-language orientation, docs-to-code links and impact
queries. The AST-only path costs no model tokens and runs in about two seconds.

## Schema findings

Source: `graphify-out/graph.json` of the test repository, built by graphify
0.9.39 at commit `49d5f573`, and the installed package under
`~/.local/share/uv/tools/graphifyy/lib/python3.12/site-packages/graphify/`.

The file is a node-link JSON document: `directed`, `multigraph`, `nodes`,
`links`, `hyperedges`, `built_at_commit`. The `directed` flag is `false`.
Each link still carries `source` and `target`, so a script can read direction
from the link, but graphify's own traversal treats the graph as undirected.

Nodes (741). Every node has `label`, `file_type`, `source_file`,
`source_location` (`L<n>`), `_origin`, `id`, `community`, `community_name`.
There is no `type` field for the kind of symbol. The kind comes from flags:

| Kind | How to detect | Count |
|---|---|---|
| function or method | `_callable: true`, label ends in `()` | 264 |
| class | `_callable_class: true` | 7 |
| file | `file_type: code`, no callable flag | part of 326 code nodes |
| docstring | `file_type: rationale` | 286 |
| Markdown section | `file_type: document` | 125 |
| shell script, shell function | `file_type: concept` with `metadata.kind` | 4 |

Edges (1274). Every edge has `relation`, `confidence`, `confidence_score`,
`source_file`, `source_location`, `weight`, `_origin`, and 577 have `context`.

| Relation | Count | Confidence | Meaning |
|---|---|---|---|
| `contains` | 383 | EXTRACTED | file → function or class; section → subsection |
| `calls` | 382 | EXTRACTED | function → function, from a call expression |
| `rationale_for` | 286 | EXTRACTED | docstring node → its function or file |
| `references` | 113 | EXTRACTED | function → class, context `parameter_type`, `return_type`, `generic_arg`, `collection`, `decorator` |
| `imports` | 64 | EXTRACTED | file → module |
| `imports_from` | 30 | EXTRACTED | file → module member |
| `indirect_call` | 13 | INFERRED, mean 0.57 | callable passed as a value, heuristic |
| `defines` | 2 | EXTRACTED | file → constant |
| `inherits` | 1 | EXTRACTED | class → base class |

All 741 nodes and all 1274 edges carry `_origin: ast`. No edge in this graph
came from a model. The 13 `indirect_call` edges are heuristic guesses made
by the AST engine (`extractors/engine.py`), not by a model. The graph report
records "Token cost: 0 input · 0 output".

Parsers. The installed package parses code with tree-sitter grammars. The
grammar packages present are: bash, c, cpp, c-sharp, elixir, fortran, go,
groovy, java, javascript, json, julia, kotlin, lua, objc, php, powershell,
python, ruby, rust, scala, swift, typescript, verilog, zig.

| Language | Extractor | Parser |
|---|---|---|
| Python | `extract_python` | tree-sitter AST |
| Rust | `extract_rust` | tree-sitter AST |
| TypeScript, JavaScript | `extract_js` | tree-sitter AST |
| Go | `extract_go` | tree-sitter AST |
| PHP | `extract_php` | tree-sitter AST |
| Shell (`.sh`, `.bash`) | `extractors/bash.py` | tree-sitter AST, plus regex for `source` paths |
| SQL | `extractors/sql.py` | needs `tree_sitter_sql`; that package is not installed, so `.sql` files return an error record and no nodes |
| Vue | `extract_vue` | masks everything outside `<script>`, parses the script with the TS or JS grammar; the template is not parsed; dynamic `import()` is recovered by regex |
| Markdown | `extract_markdown` | heading tree, links and identifiers by regex |

Extractors that use no AST at all: `apex.py`, `blade.py`, `dart.py`,
`razor.py`, `sln.py`, `pascal_forms.py`, `markdown.py`. Everything else
in `extractors/` imports tree-sitter.

Coverage gap observed on Python. The extractor makes nodes for top-level
functions and methods. Nested functions are not always nodes: `test_cli.py`
has 17 `def` lines and 16 function nodes, `test_failures.py` has 11 and 9.
Calls made inside a nested function or a lambda produce no `calls` edge.
That gap is the cause of both false positives below.

## Experiment

Question: which function and class nodes have no inbound `calls`,
`references`, `indirect_call`, `imports`, `imports_from`, `inherits` or
`defines` edge from another node? `contains` and `rationale_for` are
structural and do not count as use.

Script, run from the root of the test repository:

```python
#!/usr/bin/env python3
# Print function and class nodes of a graphify graph that have no inbound
# call, reference, import or inheritance edge from any other node.
import json
import sys
from collections import Counter, defaultdict

GRAPH = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
USE = {"calls", "references", "indirect_call", "imports", "imports_from",
       "inherits", "defines"}
STRUCTURAL = {"contains", "rationale_for"}

g = json.load(open(GRAPH))
nodes = {n["id"]: n for n in g["nodes"]}
edges = g["links"]

# Direction check: which end of a structural edge is the code node?
dir_check = Counter()
for e in edges:
    if e["relation"] in STRUCTURAL:
        s, t = nodes[e["source"]], nodes[e["target"]]
        dir_check[(e["relation"], s["file_type"], "->", t["file_type"])] += 1
print("structural edge directions:", dict(dir_check))

inbound = defaultdict(set)
for e in edges:
    if e["relation"] in USE and e["source"] != e["target"]:
        inbound[e["target"]].add(e["source"])

callables = [n for n in nodes.values()
             if n.get("_callable") or n.get("_callable_class")]
cands = [n for n in callables if not inbound[n["id"]]]

print(f"callable nodes: {len(callables)}  "
      f"(classes: {sum(1 for n in callables if n.get('_callable_class'))})")
print(f"candidates with no inbound use edge: {len(cands)}")
by_file = Counter(n["source_file"] for n in cands)
print("candidates per file:", dict(by_file))
print()
for n in sorted(cands, key=lambda n: (n["source_file"], n["source_location"])):
    print(f"{n['source_file']}:{n['source_location']}\t{n['label']}")
```

Output, condensed. The numbers come from the 741-node graph built at commit
`49d5f573`. A graph rebuilt after later changes gives other counts.

```text
structural edge directions: {('contains', 'code', '->', 'code'): 269,
  ('rationale_for', 'rationale', '->', 'code'): 286,
  ('contains', 'document', '->', 'document'): 114}
callable nodes: 264  (classes: 7)
candidates with no inbound use edge: 156
```

Verification of the 156 candidates by grep in the source:

| Group | Count | Verdict |
|---|---|---|
| `test_*` functions in `tests/` | 149 | pytest entry points; live |
| `test_*` functions in `ref_check.py` | 5 | pytest entry points of the self-check; live |
| `_heading_slugs()` at `ref_check.py:1724` | 1 | called at line 1921 inside the nested function `slugs_of`; live; false positive |
| `_regex_positions()` at `ref_check.py:761` | 1 | called by four lambdas in the `READERS` table at lines 786 to 789; live; false positive |

The graph holds no edge into either of the last two. It holds edges out of
them (`_heading_slugs() -> _md_lines_outside_fences()`, and `references`
edges for the parameter types of `_regex_positions()`), so the nodes exist
and the callers are the gap.

Precision: 0 of 156 candidates are dead, so precision is 0.0 %. A name rule
that removes `test_*` leaves 2 candidates; both are false positives, so
precision after the name rule is 0 of 2. No true dead function exists in
this repository as far as the graph, vulture and ruff can tell, so recall
cannot be measured here.

Second opinion from native tools on the same tree, read-only:

| Tool | Command | Findings |
|---|---|---|
| vulture 2.16 | `vulture ref_check.py tests/` | 5 unused functions, all the `test_*` self-checks in `ref_check.py`, each at 60 % confidence; `--min-confidence 100` reports none |
| ruff 0.16.8 | `ruff check --select F401,F841,ARG ref_check.py tests/` | 2 findings: ARG001 unused argument `archive` (line 365) and `root` (line 390); no unused import, no unused variable |

vulture gives the same five entry points, but marks them with 60 %, its
lowest confidence, and it says why: "unused function". The graph gives the
same names as bare nodes with no confidence and no reason.

## Comparison with the native tools

All pages read on 2026-09-24.

| Language | Native tool | What it finds | Precision notes | Install and command; exit code |
|---|---|---|---|---|
| Python | vulture | unused imports, variables, arguments, attributes, classes, functions, methods, properties, unreachable code | Confidence per kind: arguments and unreachable code 100 %, imports 90 %, everything else 60 %. "Due to Python's dynamic nature, static code analyzers like Vulture are likely to miss some dead code." False positives are handled with a whitelist module (`--make-whitelist`) or `--min-confidence 100`. | `pip install vulture`; `vulture <paths>`; exit 0 none found, 1 invalid input, 2 bad arguments, 3 dead code found |
| Python | deadcode | rules DC01 to DC13: unused variable, function, class, method, attribute, name, import, property, unreachable code | Tuned with `--ignore-names`, `--ignore-names-in-files`, `--exclude`, and `# noqa: DC0n`. Can rewrite files with `--fix`; `--fix --dry` shows the change first. | `pip install deadcode`; `deadcode .`; exit 1 when unused names are found |
| Python | ruff F401, F841, ARG | unused import, unused local variable, unused function or method argument | Local scope only; it does not find an unused function. F401 respects re-exports with `import x as x` or `__all__`; fixes in `__init__.py` are preview. F841 skips names that match `dummy-variable-rgx` (a leading `_`). ARG001 reports arguments that an interface or a callback forces to exist. | `pip install ruff`; `ruff check --select F401,F841,ARG <paths>`; exit 0 clean, 1 violations, 2 abnormal end |
| Rust | rustc `dead_code` lint | "detects unused, unexported items" | Runs on every build, warn by default, part of `#[warn(unused)]`. `pub` items in a library crate are never reported, because the compiler cannot see the callers. `#[allow(dead_code)]` silences. | no install; `cargo build` or `cargo clippy`; `RUSTFLAGS="-D dead_code"` turns the warning into a build failure |
| Rust | cargo-udeps | unused entries in `Cargo.toml` `[dependencies]` | Uses the real build, so it is precise. "It needs Rust nightly to actually run." | `cargo install cargo-udeps --locked`; `cargo +nightly udeps`; non-zero when unused dependencies are found |
| Rust | cargo-machete | unused entries in `Cargo.toml`, "in a fast (yet imprecise) way" | Scans source text for the crate name. Crates used only through a macro trigger false positives unless `--with-metadata`; `[package.metadata.cargo-machete] ignored = [...]` and `renamed` fix the rest. | `cargo install cargo-machete`; `cargo machete`; `--json` prints `{}` when nothing is found (the README states no exit-code contract) |
| TypeScript | knip | unused files, unused exports, unused types, enum members, class members, unused and unlisted dependencies, unresolved imports | Starts from entry files that plugins discover from configuration; a missing plugin or a dynamic entry point gives false "unused file". `--include-entry-exports` widens the export check for private repositories. Built-in compilers for `.vue`, `.svelte`, `.astro`, `.mdx` strip the script block only; "when you need that fidelity, override any built-in with the framework's own compiler". | `npm init @knip/config` or `npx knip`; exit 1 on issues, `--max-issues N` and `--no-exit-code` relax it |
| TypeScript | ts-prune | unused exports according to `tsconfig.json`. Status on 2026-10-07: dormant, and knip replaces it; so do unimported and depcheck, which are archived or dormant. | Exports used only inside their own file are listed as `(used in module)`; `--unusedInModule` hides them. No knowledge of entry points; every file is a root. | `npm install --save-dev ts-prune`; `npx ts-prune`; "Without `--error`, findings do not cause a nonzero exit status." |
| TypeScript | eslint `no-unused-vars` | variables, functions and arguments that are declared and not used in one file | Per file only. An export is a use, so an unused export is never reported. `args: after-used`, `caughtErrors: all` defaults; `/* exported name */` marks globals. | `npm install --save-dev eslint`; `npx eslint .`; exit 0 clean, 1 errors, 2 configuration or internal problem |
| Go | staticcheck U1000 | unused code: functions, types, fields, constants and variables that nothing in the package or its importers uses | Exported identifiers of a package that another package may import count as used. Test files are analysed by default. | `go install honnef.co/go/tools/cmd/staticcheck@latest`; `staticcheck ./...`; non-zero exit when it prints a problem |
| Go | deadcode (`golang.org/x/tools/cmd/deadcode`) | "reports unreachable functions": builds a call graph from every `main` with Rapid Type Analysis | Whole-program and sound for func values, interface methods and reflection. Functions used only by tests are dead unless `-test`. Marker-interface methods are reported although they must stay. `-whylive=<func>` shows a path. | `go install golang.org/x/tools/cmd/deadcode@latest`; `deadcode -test ./...`; the page states no exit code, so a non-empty output is the signal |
| PHP | phpstan | unused private properties, methods and constants | Private members only, by design: "native PHPStan does not perform full-codebase analysis of unused code"; the extension `shipmonk/dead-code-detector` adds public members. | `composer require --dev phpstan/phpstan`; `vendor/bin/phpstan analyse`; exit 0 no errors, non-zero otherwise |
| PHP | psalm `UnusedClass`, `UnusedMethod` | unused classes, methods, properties, constants, variables | Reachability from entry points: the public API, top-level code, free functions and code outside the project. Framework-invoked methods need `@api` on the class; `@psalm-suppress` silences without marking as used. | `composer require --dev vimeo/psalm`; `vendor/bin/psalm --find-dead-code` or `findUnusedCode="true"` in `psalm.xml`; exit 0 clean, 1 problem running, 2 issues found |
| Shell | shellcheck SC2034 | "foo appears unused": a variable that is assigned and never read | Variables only; no function-level check exists. Indirect use (`${!name}`, `eval`, `declare -n`, `export "$name"`) is reported on purpose: "known to be unsolvable in the most general case". `# shellcheck disable=SC2034` per line. | distribution package; `shellcheck <files>`; exit 0 no issues, 1 issues, 2 file not processed, 3 or 4 bad invocation |
| SQL | none | nothing | No native tool finds an unused table, view or routine from source alone; that needs the live catalog and query logs. graphify's SQL extractor needs `tree_sitter_sql`, which is not installed. | — |
| Vue | knip with the vue plugin | unused files, exports and dependencies in `.vue` and script files | The plugin enables when `vue` is in `dependencies`; it adds `vue.config.*` as configuration. The built-in `.vue` compiler keeps the script block only, so a component used only from a template is not seen. | `npx knip`; exit 1 on issues |
| Vue | eslint-plugin-vue `no-unused-components` | "registering components that are not used inside templates" | Only components registered in `components:`; `<script setup>` imports are handled by `no-unused-vars` with `vue-eslint-parser` v9 or later. `ignoreWhenBindingPresent` (default true) suppresses all reports when `<component :is>` appears. In preset `flat/essential`. | `npm install --save-dev eslint eslint-plugin-vue`; `npx eslint .`; exit 1 on errors |

What the table shows. Each native tool has an entry-point model that fits
its language: `main` for Go, the public API for psalm, `pub` for rustc,
entry files for knip, `test_*` for pytest via vulture's whitelist. The
graphify graph has no entry-point model. A test function and a dead
function look the same: a callable node with no inbound edge.

## Cost

Measured on 2026-09-24 on a copy of the test repository in a scratch
directory, with every model key removed from the environment. The
repository's own graph was not touched.

| Command | Wall time | Result |
|---|---|---|
| `graphify update <copy>`, no change | 1.5 s | "No code-graph topology changes detected; outputs left untouched." |
| `graphify update <copy>`, one new function | 2.4 s | rebuilt 742 nodes, 1275 edges, 42 communities; rewrote `graph.json`, `graph.html`, `GRAPH_REPORT.md`; renamed 16 communities by their hub |
| `graphify extract <fresh> --code-only` | 1.7 s | 28 code files, 616 nodes, 1135 edges, 36 communities; 233 Markdown files skipped |
| `graphify extract <fresh>` without a key | 0.7 s, exit 1 | "error: no LLM API key found (233 doc/paper/image file(s) need semantic extraction)" |

Does `extract` call a model? Yes, for documents. The command is "headless
full extraction (AST + semantic LLM)". Backends: gemini, kimi, claude,
openai, deepseek, ollama, azure, bedrock, and any OpenAI-compatible or
Anthropic-compatible endpoint. `detect_backend()` picks the first key it
finds, in that order. With `--code-only` no key is needed and no model is
called. Code is always parsed locally; only Markdown, papers and images go
to a model. The test repository's graph holds 125 Markdown section nodes
and records zero tokens, so a local path for Markdown exists in the
agent-driven `/graphify` flow, but the headless CLI does not expose it.

`graphify update` as a hook after each change. The time is fine: about two
seconds on 2.5 k lines of Python. The side effects are not: every run with
a topology change rewrites a 744 KB `graph.json`, a `graph.html` and a
report, and renames communities. After a refactor that deletes code,
`update` refuses to write a smaller graph unless `--force` or
`GRAPHIFY_FORCE=1` is set. graphify's own `hook install` puts the rebuild
into git `post-commit` and `post-checkout`, detached, which is the better
place. A per-edit hook adds noise to every diff and gives nothing the
post-commit hook does not.

`hook-guard`. `graphify hook-guard search|read` is a PreToolUse hook for
Claude Code and Codebuddy. It reads the tool call as JSON from stdin. When
`graphify-out/graph.json` exists under the current directory and the call
is a grep-like Bash command, a Grep call, or a Read of an indexed code file,
it prints an `additionalContext` nudge toward `graphify query`. It always
exits 0 and fails open on any error. In strict mode (`--strict`) it denies
the first raw Read per session with a `permissionDecision`, then downgrades
to the nudge. It looks only at `graphify-out/graph.json` relative to the
session's working directory; it does not walk up to a parent. A stale graph
for the target file softens to a nudge.

## Recommendation

Option (b): use the native tools for dead code, and treat graphify as an
optional map, never as a requirement.

Reasons, with the evidence above:

1. Precision. The graph gave 156 candidates and 0 dead functions on the
   test repository. The two non-test candidates were live code that the
   extractor could not see: a call inside a nested function and calls inside
   lambdas. A dead-code check that reports live code as dead gets switched
   off after the first false report.
2. No entry-point model. Every native tool encodes what "used" means for
   its language: `main`, `pub`, the public API, entry files, test names. The
   graph has one flat notion of an inbound edge. Adding the missing rules on
   top of the graph would rebuild vulture or deadcode with fewer facts.
3. No contract. The native tools give an exit code and a stable message
   format. graphify is a query tool; a dead-code list would need the script
   above, plus per-language rules, plus a whitelist, all maintained by the
   setup tool.
4. Language coverage is uneven. SQL needs a grammar that is not installed.
   Vue templates are masked out, so template-only use is invisible. Shell
   functions become `concept` nodes with no call edges to Python.
5. Requirement cost. A required `graphify extract` on a repository with
   Markdown needs a model key or the `--code-only` flag, and adds 744 KB of
   generated output per repository.

What graphify is good for, and the native tools are not:

- One map across languages. A Python file, a shell script, an ESLint config
  and a Markdown page sit in one graph with `contains`, `imports` and
  `references` edges. No native tool crosses a language border.
- Docs-to-code links. Markdown sections are nodes; identifiers in a page
  become `references` edges to code; docstrings become `rationale_for`
  nodes. A `graphify path "D2.4" "_check_h"` style query answers "which
  code implements this design section" from the graph.
- Orientation for an agent. `god-nodes` lists the hubs, `explain` gives a
  node and its neighbours, `affected` walks reverse edges to estimate the
  blast radius of a change, `query` gives a budgeted BFS answer. All of
  this runs locally at zero token cost once the graph exists.
- Freshness. `built_at_commit` in the graph and the `GRAPH_REPORT.md`
  freshness section let a hook say "this graph is stale" without a rebuild.

Concrete shape for the setup tool:

- Install and run the native dead-code tools per language that the
  repository contains, with their exit codes as the gate: vulture and ruff
  for Python; `cargo clippy` with `-D dead_code` and cargo-machete for
  Rust; knip and eslint for TypeScript and Vue; staticcheck and deadcode
  for Go; phpstan and psalm for PHP; shellcheck for shell; nothing for SQL.
- Offer `graphify extract --code-only` as an optional step. Never gate a
  check on the graph. Put the rebuild in `post-commit` through
  `graphify hook install`, not in a per-edit hook. Keep `graphify-out/`
  out of version control.

## Sources

- graphify 0.9.39, `graphify --help`, read 2026-09-24.
- graphify 0.9.39 installed source, `~/.local/share/uv/tools/graphifyy/lib/python3.12/site-packages/graphify/` (`cli.py` `_run_hook_guard`, `extract.py` `_DISPATCH` and `_LANG_FAMILY_BY_EXT`, `extractors/engine.py`, `extractors/sql.py`, `extractors/bash.py`, `llm.py` `detect_backend`), read 2026-09-24.
- Test repository graph, `graphify-out/graph.json` and `GRAPH_REPORT.md`, built at commit `49d5f573`, read 2026-09-24.
- vulture README, https://github.com/jendrikseipp/vulture/blob/main/README.md, read 2026-09-24.
- deadcode README, https://github.com/albertas/deadcode/blob/main/README.md, read 2026-09-24.
- Ruff rules F401, F841, ARG001, https://docs.astral.sh/ruff/rules/unused-import/, https://docs.astral.sh/ruff/rules/unused-variable/, https://docs.astral.sh/ruff/rules/unused-function-argument/; exit codes, https://docs.astral.sh/ruff/linter/, read 2026-09-24.
- The rustc book, warn-by-default lints, `dead_code`, https://doc.rust-lang.org/rustc/lints/listing/warn-by-default.html, read 2026-09-24.
- cargo-udeps README, https://github.com/est31/cargo-udeps/blob/master/README.md, read 2026-09-24.
- cargo-machete README, https://github.com/bnjbvr/cargo-machete/blob/main/README.md, read 2026-09-24.
- Knip, CLI arguments, getting started, compilers, Vue plugin, https://knip.dev/reference/cli, https://knip.dev/overview/getting-started, https://knip.dev/features/compilers, https://knip.dev/reference/plugins/vue, read 2026-09-24.
- ts-prune README, https://github.com/nadeesha/ts-prune/blob/master/README.md, read 2026-09-24.
- ESLint `no-unused-vars` and CLI exit codes, https://eslint.org/docs/latest/rules/no-unused-vars, https://eslint.org/docs/latest/use/command-line-interface, read 2026-09-24.
- Staticcheck checks and getting started, https://staticcheck.dev/docs/checks/, https://staticcheck.dev/docs/getting-started/, read 2026-09-24.
- deadcode command, https://pkg.go.dev/golang.org/x/tools/cmd/deadcode, read 2026-09-24.
- PHPStan, "Detecting Unused Private Properties, Methods, and Constants", https://phpstan.org/blog/detecting-unused-private-properties-methods-constants; command line usage, https://phpstan.org/user-guide/command-line-usage, read 2026-09-24.
- Psalm, `UnusedMethod`, configuration `findUnusedCode`, command line usage, installation, https://psalm.dev/docs/running_psalm/issues/UnusedMethod/, https://psalm.dev/docs/running_psalm/configuration/, https://psalm.dev/docs/running_psalm/command_line_usage/, https://psalm.dev/docs/running_psalm/installation/, read 2026-09-24.
- ShellCheck SC2034 and manual page, https://www.shellcheck.net/wiki/SC2034, https://github.com/koalaman/shellcheck/blob/master/shellcheck.1.md, read 2026-09-24.
- eslint-plugin-vue `no-unused-components` and user guide, https://eslint.vuejs.org/rules/no-unused-components.html, https://eslint.vuejs.org/user-guide/, read 2026-09-24.
