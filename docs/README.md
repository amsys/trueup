---
id: docs-index
type: reference
audience: [maintainer, agent, user]
status: current
last_reviewed: 2026-11-18
---

# trueup documents

This page is the index of all documents in this repository. Start here. A
person and an agent read the same pages.

## Where to start

- **You want to try trueup.** Read
  [Your first run](tutorial/first-run.md), then
  [Apply trueup](how-to/apply-trueup.md).
- **You want to look something up.** [The trueup reference](reference/trueup.md)
  lists every command, configuration key and finding.
- **You want to read or change the code.** Read
  [How trueup works](explanation/how-trueup-works.md), a map of the code
  by subject.
- **You want to know why trueup works as it does.** Read
  [the brief](BRIEF.md). The architecture and the research pages are
  records of the design work. They are long, and they use the ids and
  the words of that work, which
  [a list below](#words-that-the-records-use) explains.

## Pages

Add each new page to this table.

| Type | Page | Content |
|---|---|---|
| Tutorial | [Your first run](tutorial/first-run.md) | Five minutes on a practice repository: run `check`, read the report, approve a finding by id, and check again |
| Reference | [Architecture](ARCHITECTURE.md) | The design of the baseline and the plugin: the standard page, the lint configurations, the plugin's commands, findings, rule sets, score and hooks |
| Reference | [Design verification](reference/design-verification.md) | The claims of the architecture: each design id that a test must prove, and the tests that prove it. Check c reads this page |
| Reference | [The trueup reference](reference/trueup.md) | The command line, `trueup.toml`, the findings tables, the rule-set table with what this machine could verify, the score formula and the four hook events (`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`) |
| Reference | [The comment standard](reference/comment-standard.md) | The comment rules of the five languages, the lint commands, and the marker registry |
| Reference | [The document standard](reference/document-standard.md) | The page rules of check h, the root README rules of check i, and the further rules `trueup` checks |
| How-to | [Apply trueup](how-to/apply-trueup.md) | Install the plugin and the `trueup` command, run the skill, answer its questions, approve, and verify with `trueup check` and `trueup lint` |
| How-to | [Gate CI with a baseline](how-to/gate-ci-with-a-baseline.md) | Write a baseline, add `trueup check --baseline` to a target's CI, and read what makes it fail |
| How-to | [Upgrade trueup](how-to/upgrade-trueup.md) | Move a target from the old managed lint tree to `trueup lint`, and the changes of each version that can change the result of a run |
| Explanation | [Baseline research](explanation/baseline-research.md) | The research that the project starts from: findings, the decision list, and the first draft of the standard |
| Explanation | [Brief](BRIEF.md) | Problem statement, goals, success criteria, non-goals and the decisions taken |
| Explanation | [Research: dead code](explanation/research-dead-code.md) | Whether graphify or the native tools of each language should find dead code |
| Explanation | [Research: code rules](explanation/research-code-rules.md) | The strict and clean rule sets for each of the eight languages, with thresholds and sources |
| Explanation | [Research: documentation](explanation/research-documentation.md) | The documentation standard of a repository: standard-readme, the guides, links, prose tools, front matter, staleness, a survey of eight repositories, and the proposed rule list |
| Explanation | [Research: repository hygiene](explanation/research-repo-hygiene.md) | Tools and standards for repository hygiene, the root files, the slop taxonomy, and a draft specification under the working name `repo-medic` |
| Explanation | [Research: comparable tools](explanation/research-comparable-tools.md) | The 2026-10-07 survey of about 190 tools in six categories: where trueup sits, the precedents to copy, the ideas ranked, and the plan for round 4 |
| Explanation | [How trueup works](explanation/how-trueup-works.md) | A map of the code for a first reader: the three parts, the path of `check` and of `apply`, a table of the modules, the rules to know and where the tests are |
| Explanation | [Purpose and state](explanation/purpose-and-state.md) | A dated record: the maintainer's critical review of 2026-10-12, with ten findings, the plan that followed, and a status section for each later date up to 2026-11-18 |
| Explanation | [Field trial](explanation/field-trial.md) | The judged findings of the field trial on six repositories, the false-positive shapes of the later runs with the section that fixed each one, and the follow-ups that are not trueup code |

## Words that the records use

The architecture, the brief and the research pages were written while
trueup was private. They keep these words:

- **The owner** is the maintainer of trueup.
- **A round** is one cycle of design, build and review. Design sections
  have the number of their round: `D14.3` is a section of round 14.
- **A target** is a repository that trueup checks. `target-rust`,
  `target-mixed`, `target-web` and similar names stand for private
  repositories of the maintainer.
- **meridian** is the private, archived project that the reference
  checker came from. "The meridian check" is that checker, `trueup refs`.
- **A path that starts with `.state/`** is a private work record of the
  maintainer. git does not track it, so a clone does not have it.
- **A commit id** from before 2026-11-17 is in the maintainer's private
  history. The public history starts with one commit.

## Source documents

The baseline research page is a source document. Its text stays as received,
with two changes: the front matter is new, and the names of two private tools
are replaced with a general description.

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
