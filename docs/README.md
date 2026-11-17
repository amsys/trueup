---
id: docs-index
type: reference
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-11-02
---

# trueup documents

This page is the index of all documents in this repository. Start here. A
person and an agent read the same pages.

## Pages

Add each new page to this table.

| Type | Page | Content |
|---|---|---|
| Reference | [Architecture](ARCHITECTURE.md) | The design of the baseline and the plugin: the standard page, the lint configurations, the plugin's commands, findings, rule sets, score and hooks, and their verification |
| Reference | [The trueup reference](reference/trueup.md) | The command line, `trueup.toml`, the findings tables, the rule-set table with what this machine could verify, the score formula and the four hook events (`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`) |
| Reference | [The comment standard](reference/comment-standard.md) | The comment rules of the five languages, the lint commands, and the marker registry |
| Reference | [The document standard](reference/document-standard.md) | The page rules of check h, the root README rules of check i, and the further rules `trueup` checks |
| How-to | [Apply trueup](how-to/apply-trueup.md) | Install the plugin and the `trueup` command, run the skill, answer its questions, approve, and verify with `trueup check` and `trueup lint` |
| How-to | [Gate CI with a baseline](how-to/gate-ci-with-a-baseline.md) | Write a baseline, add `trueup check --baseline` to a target's CI, and read what makes it fail |
| Explanation | [Baseline research](explanation/baseline-research.md) | The research that the project starts from: findings, the decision list, and the first draft of the standard |
| Explanation | [Brief](BRIEF.md) | Problem statement, goals, success criteria, non-goals and the decisions taken |
| Explanation | [Research: dead code](explanation/research-dead-code.md) | Whether graphify or the native tools of each language should find dead code |
| Explanation | [Research: code rules](explanation/research-code-rules.md) | The strict and clean rule sets for each of the eight languages, with thresholds and sources |
| Explanation | [Research: documentation](explanation/research-documentation.md) | The documentation standard of a repository: standard-readme, the guides, links, prose tools, front matter, staleness, a survey of eight repositories, and the proposed rule list |
| Explanation | [Research: repository hygiene](explanation/research-repo-hygiene.md) | Tools and standards for repository hygiene, the root files, the slop taxonomy, and a draft specification under the working name `repo-medic` |
| Explanation | [Research: comparable tools](explanation/research-comparable-tools.md) | The 2026-10-07 survey of about 190 tools in six categories: where trueup sits, the precedents to copy, the ideas ranked, and the plan for round 4 |
| Explanation | [Purpose and state](explanation/purpose-and-state.md) | The 2026-10-12 analysis: what trueup is for, the state of the repository with its evidence, ten findings from the self-check and two real targets, and the plan that follows, with its status on 2026-11-02 |

No tutorial page exists yet.

The baseline research page is a source document. Its text stays as received,
with two changes: the front matter is new, and the name of a private tool is
replaced with a general description.

The repository hygiene research page is also a source document. Its text
stays as received, with three changes: the front matter is new, one banned
word is removed from a quote of scorecard.dev, and one rule name that used
another banned word is now "Safe to re-run". The page uses the working name
`repo-medic`. The product name is `trueup`, see the
[brief](BRIEF.md#decisions-taken).

## Page rules

Each page in `docs/` obeys the
[document standard](reference/document-standard.md). Check h of the checker
enforces the page rules, and this repository turns it on.
