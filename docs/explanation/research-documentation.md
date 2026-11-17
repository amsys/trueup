---
id: research-documentation
type: explanation
audience: [maintainer, agent]
status: draft
last_reviewed: 2026-09-24
---

# Research: the documentation standard of a repository

## Summary

- standard-readme is a strict order of 16 sections. Its linter is a remark
  preset with 7 rules, marked "work in progress" since 2016. Check i covers
  the same core (title, description, Install, Usage, License) and adds four
  rules that standard-readme lacks: a contiguous badge block, a licence file,
  License last, and a link to the document index.
- None of the eight surveyed repositories follows standard-readme. All eight
  have a licence file. Seven have an issue template. Three have `AGENTS.md`.
- The best rules are the ones a tool can check. Links, front matter, section
  order, heading structure, changelog shape, staleness, and a banned-word
  list are all checkable today with meridian, markdownlint, lychee and Vale.
- Voice, tone, and the Diátaxis fit of a page are taste. The standard states
  them as guidelines and does not gate on them.
- The [baseline research](baseline-research.md) settled the entry route and
  the id scheme. This page settles the README rules, the community files, the
  front matter cost, the link rules, the prose tools and the staleness rule.
  It disagrees with the baseline on one point: front matter is now a decision,
  not a user choice, and its rendering cost on GitHub is stated.

## Findings

### 1. standard-readme: the exact specification

Source: [spec.md](https://github.com/RichardLitt/standard-readme/blob/master/spec.md)
and the project README, read 2026-09-24.

General requirements of the spec:

- The file is called `README` with a format extension (`.md`, `.org`,
  `.html`). Translations are `README.<BCP 47 tag>.md`. `README.md` is
  English when more than one language exists.
- Sections appear in the order below. Optional sections may be omitted.
- Section titles are fixed unless a section says otherwise.
- The file has no broken links.
- Code examples are linted the same way as the project code.

The section list, in order, with its status:

| # | Section | Status |
|---|---|---|
| 1 | Title | Required |
| 2 | Banner | Optional |
| 3 | Badges | Optional |
| 4 | Short Description | Required |
| 5 | Long Description | Optional |
| 6 | Table of Contents | Required; optional under 100 lines |
| 7 | Security | Optional |
| 8 | Background | Optional |
| 9 | Install | Required; optional for a documentation repository. `Dependencies` subsection required for unusual dependencies |
| 10 | Usage | Required; optional for a documentation repository. `CLI` subsection required when a CLI exists |
| 11 | Extra Sections | Optional, zero or more, each with its own title |
| 12 | API | Optional |
| 13 | Maintainer(s) | Optional |
| 14 | Thanks | Optional |
| 15 | Contributing | Required |
| 16 | License | Required |

The linter is
[standard-readme-preset](https://github.com/RichardLitt/standard-readme-preset),
a remark-lint preset at version 1.0.13. Its `index.js` loads seven rules:
`appropriate-heading`, `file-stem`, `file-extension`,
`require-file-extension`, `no-unknown-sections`, `require-sections` and
`section-order`. The project README calls the linter "work in progress" and
points to tracking issue #5. The preset checks structure only. It does not
check links, the licence file, or the content of a section.

Comparison with meridian check i (D2.14):

| Rule | standard-readme | check i |
|---|---|---|
| Title is line 1 | Yes (Title required) | Yes, `# ` or `<h1` |
| Badges in one block | No rule | Yes, `badges-scattered` |
| Description after title | Yes (Short Description) | Yes, `no-description` |
| Table of contents | Required over 100 lines | No rule |
| `Install` section | Required, title fixed | Required, `Install` or `Installation` |
| `Usage` section | Required, title fixed | Required |
| `Contributing` section | Required | No rule |
| `License` section | Required, last by order | Required, last, `misordered` |
| Licence file at root | No rule | Yes, `no-licence-file` |
| Link to the document index | No rule | Yes, `no-index-link` |
| Full section order | Yes, all 16 | No rule beyond License last |
| Unknown section titles | Linter rejects them | No rule |
| No broken links | Yes, stated, not linted | Check g, not check i |
| README file name | Fixed with capitals | Fixed, `README.md` only |

What standard-readme requires and check i does not: Contributing, a table of
contents over 100 lines, the exact title `Install`, and the full order. What
check i requires and standard-readme does not: the badge block, the licence
file, and the index link.

### 2. What "better than standard-readme" means

Each guide below is stated with what it prescribes, what a machine can
check, and what is taste. All read 2026-09-24.

**Make a README** ([makeareadme.com](https://www.makeareadme.com/)). Suggests
twelve parts: Name, Description, Badges, Visuals, Installation, Usage,
Support, Roadmap, Contributing, Authors and acknowledgment, License, Project
status. Its template has four sections: Installation, Usage, Contributing,
License. It says "too long is better than too short" and, when a README is
too long, to use "another form of documentation". Checkable: the presence of
the four template sections. Taste: the rest.

**GitHub community health files**
([creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file),
[about community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories)).
The supported files are `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, discussion
category forms, `FUNDING.yml`, `GOVERNANCE.md`, issue and pull request
templates, `SECURITY.md` and `SUPPORT.md`. GitHub looks in three places in
this order: the `.github` folder, the root, the `docs` folder. A public
`.github` repository of the account supplies defaults. The community profile
checklist looks for README, CODE_OF_CONDUCT, LICENSE, CONTRIBUTING, a
security policy, and templates. An issue template counts only in
`.github/ISSUE_TEMPLATE` with `name:` and `about:` (Markdown) or `name:` and
`description:` (YAML form). Checkable: file presence in the three locations,
and the template keys. Taste: the content of each file.

**Keep a Changelog 1.1.0** ([keepachangelog.com](https://keepachangelog.com/en/1.1.0/)).
Seven principles: for humans, one entry per version, group the same types,
versions and sections are linkable, latest first, a release date per version,
state whether the project follows Semantic Versioning. Six change types:
`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. An
`Unreleased` section at the top. Checkable: the heading shape
`## [x.y.z] - YYYY-MM-DD`, the type headings from the closed set, descending
order, the `Unreleased` section. Taste: the wording of an entry.

**Diátaxis** ([diataxis.fr](https://diataxis.fr/),
[start here](https://diataxis.fr/start-here/),
[as a guide to work](https://diataxis.fr/how-to-use-diataxis/)). Four kinds of
documentation with four needs: tutorials, how-to guides, reference,
explanation. The site says to use it "as a guide, not a plan", to "work one
step at a time", and that documentation is "complete, not finished".
Checkable: a `type` field from the closed set of four, and the directory per
type (check h rules 2 and 3). Taste: whether a page is really of its type.

**Google developer documentation style guide**
([highlights](https://developers.google.com/style/highlights)). Second person,
active voice, American spelling, conditions before instructions, sentence
case for titles and headings, numbered lists for sequences, descriptive link
text, alt text, unambiguous dates, code font for code, bold for UI. The Vale
package [errata-ai/Google](https://github.com/errata-ai/Google) has 36 rules,
among them `Passive`, `We`, `FirstPerson`, `Headings`, `Will`, `Latin`,
`Contractions`, `WordList`, `Spelling`. Checkable: all 36 by pattern. Taste:
"conversational and friendly".

**Microsoft Writing Style Guide**
([top 10 tips](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)).
Bigger ideas with fewer words, write like you speak, get to the point, be
brief, do not capitalize when in doubt, skip periods in headings and short
list items, serial comma, one space after a period, revise weak writing. The
Vale package [errata-ai/Microsoft](https://github.com/errata-ai/Microsoft)
has 47 rules, among them `SentenceLength`, `Wordiness`, `Passive`,
`Acronyms`, `Headings`, `Terms`, `Contractions`. Checkable: the 47 rules.
Taste: "project friendliness".

**Write the Docs**
([beginners guide](https://www.writethedocs.org/guide/writing/beginners-guide-to-docs/),
[docs as code](https://www.writethedocs.org/guide/docs-as-code/)). The README
template: a one-line problem statement, Features, Installation, Contribute
(issue tracker, source), Support, License. Docs as code: issue trackers,
version control, plain text markup, code review, automated tests, and the
option to "block merging of new features" when the documentation is absent.
Checkable: the automated tests and the merge gate. Taste: the template.

**ASD-STE100** ([asd-ste100.org](https://www.asd-ste100.org/),
[about STE](https://www.asd-ste100.org/about_STE.html)). Issue 9 was released
on 15 January 2025. The standard is 53 writing rules in 9 sections and a
dictionary of about 900 approved words, each with one meaning and one part of
speech, plus about 1200 unapproved words with alternatives. Technical nouns
and verbs of the project are permitted. The official copy is free on request,
and the text and the dictionary are under copyright. Checkable: sentence
length, contractions, passive voice, `-ing` forms, and a substitution list of
unapproved words, all by pattern. Not checkable by pattern: one meaning per
word, and the part-of-speech rule; those need a parser. The length limits of
20 words for a procedural sentence and 25 for a descriptive sentence come from
the rules (rule numbers unverified).

**arc42** ([docs.arc42.org](https://docs.arc42.org/home/)). Twelve sections:
Introduction and Goals, Constraints, Context and Scope, Solution Strategy,
Building Block View, Runtime View, Deployment View, Crosscutting Concepts,
Architecture Decisions, Quality Requirements, Risks and Technical Debt,
Glossary. Checkable: the section headings. Taste: the depth of each.

**C4** ([c4model.com](https://c4model.com/)). Four abstractions (software
system, container, component, code), four core diagrams (system context,
container, component, code), three supporting diagrams, notation and tooling
independent. Checkable: nothing in Markdown without a model file. Taste:
which levels to draw.

**MADR** ([adr.github.io/madr](https://adr.github.io/madr/),
[template](https://github.com/adr/madr/blob/develop/template/adr-template.md)).
Optional front matter `status`, `date`, `decision-makers`, `consulted`,
`informed`. `status` is one of `proposed`, `rejected`, `accepted`,
`deprecated`, `superseded by ADR-0123`. Headings: title, Context and Problem
Statement, Decision Drivers, Considered Options, Decision Outcome,
Consequences, Confirmation, Pros and Cons of the Options, More Information.
Files are `docs/decisions/NNNN-title-with-dashes.md`.
[adr-tools](https://github.com/npryce/adr-tools) defaults to `doc/adr`.
Checkable: the file name, the status set, the required headings. Taste: the
options and their pros and cons.

**llms.txt** ([llmstxt.org](https://llmstxt.org/)). A site-root file: one H1
(the only required part), a blockquote summary, free paragraphs without
headings, then H2 file lists of `[name](url): notes`, with an `## Optional`
list. The v2 page says agents "now use websites constantly". It is a website
convention, not a repository one. Checkable: the shape. Not needed inside a
repository; `AGENTS.md` and `docs/README.md` fill that role.

**AGENTS.md** ([agents.md](https://agents.md/)). Plain Markdown with no
required fields. The closest file to the edited file wins. A user prompt
overrides it. Agents run the test commands listed in it. A monorepo uses
nested files; the site cites 88 in one OpenAI repository. Checkable: the file
exists, and it links to the document index. Taste: everything else.

### 3. Linking

**How well-run repositories link.** The survey in finding 7 shows three
patterns. A repository with a documentation site links from the README to the
site with absolute URLs (prettier, go, kubernetes, cpython). A repository
with in-tree documentation links with repository-relative paths to the index
(django: `docs/intro/install.txt`, `docs/README`; rust: `INSTALL.md`,
`CONTRIBUTING.md`). A repository with no `docs/` keeps sibling pages at the
root and links to them from the README (ripgrep: `GUIDE.md`, `FAQ.md`,
`CHANGELOG.md`, 13 links). The Sphinx repositories use a per-area index
(`docs/howto/index.txt`, `Doc/c-api/index.rst`) and a root contents page.

**Tools.** [lychee](https://github.com/lycheeverse/lychee) checks Markdown,
relative URLs, and anchor fragments with `--include-fragments`. `--offline`
checks local files only and blocks the network. `--base-url` resolves
relative links, `--root-dir` resolves absolute local paths, `--cache` stores
results in `.lycheecache`, `--exclude-path` skips paths, and `GITHUB_TOKEN`
lifts the GitHub rate limit. Its feature table says it respects rate limits
where markdown-link-check does not.
[markdown-link-check](https://github.com/tcort/markdown-link-check) offers
`ignorePatterns`, `replacementPatterns`, `projectBaseUrl`, `httpHeaders`,
`timeout`, `retryOn429`, `retryCount`, `fallbackRetryDelay` and
`aliveStatusCodes`.
[markdownlint](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md)
has `MD051` (a fragment must match a heading of the same file, with
`ignore_case` and `ignored_pattern`), `MD042` (no empty link), `MD052`
(reference label defined), `MD053` (no unused definition), `MD034` (no bare
URL) and `MD059` (no "click here"). Sphinx has a `linkcheck` builder with
`linkcheck_anchors`, `linkcheck_ignore`, `linkcheck_retries` and
`linkcheck_allowed_redirects`. meridian check g (D2.10) resolves relative
paths, decodes percent-encoding, matches fragments to the GitHub slug, and
verifies a pin (the first eight hex digits of the SHA-256 of the section).

**Stable ids.** The baseline research found that no surveyed framework
supplies a stable per-section id: MADR numbers files, arc42 numbers chapters,
C4 has none. An explicit token in the heading (`D2.14`) survives a title
edit; a slug does not. This page confirms that finding and adds nothing to
it.

**What breaks links most.** In order of frequency in the surveyed tools'
option lists and in the design of check g:

1. A moved or renamed file. Every tool reports it. Only a checker that runs
   before merge stops it.
2. A retitled heading. The slug changes, the fragment goes stale. `MD051`
   and check g report it; lychee reports it only with `--include-fragments`.
3. A duplicated heading. GitHub appends `-1`, `-2`; a link to the first slug
   silently points to the wrong section.
4. A link written relative to the repository root instead of the file.
   lychee needs `--root-dir` for it; check g treats it as broken.
5. External URL rot and rate limits. Only a network check finds it; it fails
   at random in CI and needs a cache, retries and an allow list.
6. A link split over two lines, or a link in a code span. Check g reads one
   line at a time and ignores code spans (D2.10); a pin title on the next
   line is `malformed`.
7. Percent-encoding and case. `MD051` has `ignore_case`; check g decodes
   percent-encoding.

### 4. Prose quality tools

**Vale** ([styles](https://vale.sh/docs/topics/styles/)). A rule extends one
of these checks: `existence`, `substitution`, `occurrence`, `repetition`,
`consistency`, `conditional`, `capitalization`, `metric`, `readability`,
`spelling`, `sequence`, `script`. Packages: Google (36 rules), Microsoft (47
rules), [write-good](https://github.com/errata-ai/write-good) (8 rules:
`Cliches`, `E-Prime`, `Illusions`, `Passive`, `So`, `ThereIs`, `TooWordy`,
`Weasel`), [proselint](https://github.com/errata-ai/proselint) (34 rules,
from `Airlinese` to `Very`).

**Which rules are worth enforcing.** A rule with a closed list and a plain
match gives few false alerts: `Spelling` with a project `Vocab`, a
`substitution` word list, `We` and `FirstPerson`, `Latin` (`e.g.`, `i.e.`),
`Will` (future tense), `Exclamation`, `SentenceLength` (`occurrence`), and a
repository-owned `existence` rule for a banned-word list. A rule that guesses
grammar gives noise: `Passive` and `E-Prime` (a be-verb plus a participle
matches many correct sentences), `Weasel` and `TooWordy` (word lists that
include ordinary words), `Headings` capitalization (a heading that holds a
code identifier fails), `Wordiness` and `Hedging`. Alert level matters: a
guessing rule stays at `suggestion` and does not gate.

**Vale and ASD-STE100.** Vale can enforce a subset: sentence length,
contractions, passive voice, `-ing` forms, phrasal verbs, and unapproved
words with an approved alternative. A third-party linter, stuffbucket/vale
(a separate pure-Go tool, not the errata-ai Vale), implements exactly this
subset and states that it is an approximation, not certified, and that the
official dictionary is under copyright; it builds its word rules from the
MIT-licensed OpenSTE wordset. The one-meaning-per-word rule and the
part-of-speech rule need a parser and stay outside pattern tools. Conclusion:
Vale enforces the STE subset that matters for a repository page; the rest is
review.

**markdownlint.** 53 rules. Worth enforcing: `MD001` (heading levels step by
one), `MD003` (one heading style), `MD022` (blank lines around headings),
`MD025` (one H1), `MD040` (fence language), `MD041` (first line is H1; it
accepts a `title` in front matter), `MD042`, `MD045` (alt text), `MD051`,
`MD052`, `MD053`, `MD059`. `MD043` (required heading structure) can enforce a
README section order for one file glob. Noise: `MD013` (line length) fights
a pinned link that must stay on one line (D2.10); `MD033` (inline HTML)
fights a badge block and an `<a name>` anchor; `MD024` (duplicate headings)
fights a changelog with repeated `### Added`.

**textlint** ([README](https://github.com/textlint/textlint)) ships no
rules; each rule is an npm package; Markdown and plain text are supported by
default. **alex** ([alexjs.com](https://alexjs.com/)) finds gender-favouring,
polarising and other unequal phrasing, for example `his` → `their`. Both are
Node tools. Status on 2026-10-07: write-good has been dormant since 2021
and alex since 2023. Vale covers the same ground for a repository that has no Node
toolchain, so neither is in the recommended set.

### 5. Front matter

**GitHub.** GitHub renders a YAML block between `---` lines at the top of a
Markdown file as a two-column table in the rendered page. Verified on
[prettier/prettier docs/index.md](https://github.com/prettier/prettier/blob/main/docs/index.md)
on 2026-09-24: the rendered HTML holds `<table><tr><th>id</th><td>index</td>`
before the first paragraph. GitHub has no documentation page for this
behaviour; a
[community discussion](https://github.com/orgs/community/discussions/70092)
traces the syntax to Jekyll. The cost of front matter on GitHub is one small
table above the title.

**What the tools expect.**

| Tool | Format | Fields it reads | Unknown keys |
|---|---|---|---|
| [Jekyll](https://jekyllrb.com/docs/front-matter/) | YAML | `layout`, `permalink`, `published`, `date`, `category`, `categories`, `tags`, `title` | Passed to templates |
| [Hugo](https://gohugo.io/content-management/front-matter/) | YAML, TOML, JSON | `title`, `date`, `lastmod`, `publishDate`, `expiryDate`, `draft`, `description`, `slug`, `aliases`, `weight`, `type`, `layout`, `keywords`, `tags` under `params` | Custom keys go under `params` (unverified whether a top-level custom key still warns) |
| [MkDocs](https://www.mkdocs.org/user-guide/writing-your-docs/#meta-data) | YAML or MultiMarkdown | `template`, `title`; all keys go to the theme template | Passed to the template |
| [Docusaurus](https://docusaurus.io/docs/api/plugins/@docusaurus/plugin-content-docs#markdown-front-matter) | YAML | `id`, `title`, `description`, `slug`, `tags`, `draft`, `unlisted`, `sidebar_position`, `sidebar_label`, `last_update: {date, author}`, `toc_min_heading_level`, `hide_title` | Available as `frontMatter` (unverified whether it warns) |
| [Obsidian](https://help.obsidian.md/properties) | YAML (JSON accepted, saved as YAML) | Defaults `tags`, `aliases`, `cssclasses`, `publish`, `permalink`, `description`, `image`, `cover`; types Text, List, Number, Checkbox, Date | Shown as properties |
| [GitHub Docs](https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter) (the docs site, not github.com) | YAML | `title`, `versions`, `intro`, layout and content-type keys | Linted by their content linter |

**Portable field set.** Two names mean the same thing in more than one tool:
`title` (Jekyll, Hugo, MkDocs, Docusaurus, GitHub Docs) and `tags` (Jekyll,
Hugo, Docusaurus, Obsidian). `description` is in Hugo, Docusaurus, Obsidian.
`draft` is in Hugo and Docusaurus. `date` variants differ everywhere
(`date`, `lastmod`, `last_update`). The meridian set `id`, `type`,
`audience`, `status`, `last_reviewed` collides with nothing: `id` and
`type` exist in Docusaurus and Hugo with a compatible meaning (a unique id; a
content type). No tool rejects the set. No agent tool reads it (the AGENTS.md
FAQ: "no required fields", the agent "parses the text").

### 6. Documentation in step with code

| Mechanism | What it proves | Source |
|---|---|---|
| Python `doctest` | An interactive example in a docstring still gives the shown output | [docs.python.org](https://docs.python.org/3/library/doctest.html) |
| Sphinx `sphinx.ext.doctest` and `linkcheck` | Snippets in `.rst` pages run; external links resolve, with `linkcheck_anchors` | [sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/builders/index.html) |
| rustdoc documentation tests | Every code block in a doc comment compiles and runs under `cargo test` | [rustdoc book](https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html) |
| mdBook `test` | Rust code blocks in a book run; the page says the Rust book uses it because examples "could get outdated" | [mdBook](https://rust-lang.github.io/mdBook/cli/test.html) |
| Go example functions | An `ExampleXxx` with an `// Output:` comment runs under `go test` and appears in the package documentation | [go.dev/blog/examples](https://go.dev/blog/examples) |
| interrogate | Docstring coverage with `--fail-under 95` in tox or pre-commit | [interrogate](https://interrogate.readthedocs.io/en/latest/) |
| ADR `status` | A decision is `accepted`, `deprecated` or `superseded by ADR-NNNN`; a superseded record points forward | [MADR template](https://github.com/adr/madr/blob/develop/template/adr-template.md) |
| docdecay | Reads a front matter `owner`, compares the file age with a threshold, and can set `out_of_date: true` in the file; meant for CI | [pypi.org/project/docdecay](https://pypi.org/project/docdecay/) |
| A repository policy script | One project requires a human "Last reviewed" line no more than 90 days old on each hand-written reference page, checked by a script | [gastownhall/beads issue #5665](https://github.com/gastownhall/beads/issues/5665) |
| meridian pins and `arch:` citations | A cited section has not changed since the citation (`stale-pin`); a design claim has a test (check c) | meridian D2.10, D2.13 |

Two mechanisms carry over to any repository without a language runtime: a
date field with a maximum age, and a content hash on a cited section. The
first catches a page nobody looked at. The second catches a page whose
source changed. Neither proves the page is right; a doctest does, for the
lines it covers.

### 7. What well-known repositories do

Observed on 2026-09-24 from the default branch of each repository through
the GitHub API and raw files. Line counts are of the README source.

| Repository | README | Level 2 sections (or as noted) | Root health files | Documentation tree | Index |
|---|---|---|---|---|---|
| rust-lang/rust | `README.md`, 80 lines, 296 words, no badge | Why Rust?, Quick Start, Installing from Source, Getting Help, Contributing, License, Trademark | `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `INSTALL.md`, `RELEASES.md`, `LICENSE-APACHE`, `LICENSE-MIT`, `REUSE.toml`, `AGENTS.md`, `CLAUDE.md` | `src/doc/`, 666 Markdown pages, depth 6, books as subdirectories (book, reference, nomicon, rustc, rustdoc, unstable-book, edition-guide, style-guide) | `src/doc/index.md`; the contributor guide is a separate site |
| python/cpython | `README.rst`, 236 lines, 1102 words, no badge | General Information, Contributing, Using Python, Build Instructions, What's New, Documentation, Testing, Installing multiple versions, Release Schedule, Copyright and License Information | `LICENSE`, `AGENTS.md`; `.github/` holds `CONTRIBUTING.rst`, `SECURITY.md`, `CODEOWNERS`, 4 issue forms, a PR template | `Doc/`, 562 reST pages, depth 2 (`Doc/<area>/<page>`) | `Doc/contents.rst`; `Doc/README.rst` is a build guide; style rules live in the separate devguide |
| golang/go | `README.md`, 43 lines, 177 words, no badge | (level 3) Download and Install, Contributing | `CONTRIBUTING.md`, `LICENSE`, `SECURITY.md`; `.github/CODE_OF_CONDUCT.md`, 9 issue forms, a PR template | `doc/` holds release notes only, 33 pages; user documentation is on go.dev | `doc/README.md` explains release notes; the README links to go.dev with absolute URLs |
| kubernetes/kubernetes | `README.md`, 101 lines, 435 words, 2 badges and a logo | To start using K8s, To start developing K8s, Support, Community Meetings, Adopters, Governance, Roadmap | `CHANGELOG.md` and `CHANGELOG/`, `CONTRIBUTING.md`, `SUPPORT.md`, `SECURITY_CONTACTS`, `LICENSE`, `LICENSES/`, `AGENTS.md`; `.github/SECURITY.md`, 4 issue forms, a PR template | `docs/` holds only `.gitignore` and `OWNERS`; documentation is in the `website` and `community` repositories | None in this repository |
| django/django | `README.rst`, 55 lines, 270 words, no badge | Django, Supporting the Development of Django | `CONTRIBUTING.rst`, `LICENSE`, `LICENSE.python`; `.github/` holds `CODE_OF_CONDUCT.md`, `SECURITY.md`, `FUNDING.yml`, a PR template | `docs/`, 679 reST pages (`.txt`), depth 5, areas `intro`, `howto`, `topics`, `ref`, `faq`, `internals`, `misc`, each with an index | `docs/index.txt` and `docs/contents.txt`; the README links to `docs/intro/install.txt`, the tutorials, and `docs/README` with relative paths |
| fastapi/fastapi | `README.md`, 536 lines, 2408 words, about 22 badges and images | Sponsors, Opinions, FastAPI mini documentary, Typer, Requirements, Installation, Example, Example upgrade, Performance, Dependencies, License | `LICENSE` only; `.github/ISSUE_TEMPLATE` holds `config.yml` and one privileged form | `docs/`, 1656 pages across languages, depth 5, MkDocs with a 332-line `docs/en/mkdocs.yml` nav | `docs/en/docs/index.md`, 582 lines, mirrors the README and carries `include_yaml` front matter |
| prettier/prettier | `README.md`, 105 lines, 236 words, about 10 badges | Intro, Badge, Contributing | `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`, `changelog_unreleased/`; `.github/SECURITY.md`, 2 issue templates, a PR template | `docs/`, 93 pages, depth 3, Docusaurus front matter `id` and `title` on each page | `docs/index.md` (`id: index`); the README links to `prettier.io/docs/...` with absolute URLs, not to `docs/` |
| BurntSushi/ripgrep | `README.md`, 542 lines, 2874 words, 4 badges | (level 3, all) CHANGELOG, Documentation quick links, Screenshot, Quick examples, Why should I use ripgrep?, Why shouldn't I, Is it really faster, Feature comparison, Playground, Installation, Building, Running tests, Related tools, Vulnerability reporting, Translations | `CHANGELOG.md`, `CONTRIBUTING.md`, `COPYING`, `LICENSE-MIT`, `FAQ.md`, `GUIDE.md`; `.github/FUNDING.yml`, 2 issue templates | No `docs/`; three root pages | The README is the index: 13 relative links to `GUIDE.md`, `FAQ.md`, `CHANGELOG.md` |

Facts across the eight:

- README length: 43 to 542 lines. The two longest (fastapi, ripgrep) carry
  content that the others put in a docs tree or a site.
- Zero of eight follow standard-readme. Only fastapi and rust have a
  `License` heading at level 2. ripgrep uses level 3 for every heading.
  Two have `Contributing` at level 2 (rust, prettier).
- Eight of eight have a licence file. Seven have issue templates. Six have a
  `CONTRIBUTING` file. Five have a `SECURITY` file. Three have `AGENTS.md`
  (rust, cpython, kubernetes). Three have a root `CHANGELOG.md` (kubernetes,
  prettier, ripgrep); rust has `RELEASES.md`.
- One of eight uses front matter (prettier, for Docusaurus).
- The documentation tree is 2 to 6 levels deep. Sphinx repositories use an
  index per area. Django's areas map onto Diátaxis (`intro` = tutorial,
  `howto`, `ref`, `topics` = explanation).
- No repository has a `docs/README.md` that is the index. Django's
  `docs/README.rst` and CPython's `Doc/README.rst` are build guides.

## Comparison table

| Rule | standard-readme | GitHub community standards | meridian check h/i | Recommended |
|---|---|---|---|---|
| README title on line 1 | Required | Description in repository settings, not the file | Required (`no-title`) | Required |
| Short description after title | Required | No rule | Required (`no-description`) | Required |
| Badges in one block | No rule | No rule | Required (`badges-scattered`) | Required |
| Table of contents | Required over 100 lines | No rule | No rule | Not required; GitHub renders a heading menu (unverified) and a README over 200 lines is the problem, not the missing TOC |
| `Install` section | Required, fixed title | No rule | Required, `Install` or `Installation` | Required, either title |
| `Usage` section | Required | No rule | Required | Required |
| `Contributing` section | Required | `CONTRIBUTING` file in the checklist | No rule | Required as a section or a root file |
| `License` section last | Required by order | `LICENSE` file in the checklist | Required (`misordered`) | Required |
| Licence file | No rule | Required for a checkmark | Required (`no-licence-file`) | Required |
| Security policy | Optional section | `SECURITY.md` in the checklist | No rule | Recommended for a public repository |
| Code of conduct | No rule | `CODE_OF_CONDUCT.md` in the checklist | No rule | Optional |
| Support | No rule | `SUPPORT.md` | No rule | A `Support` section in the README, or `SUPPORT.md` |
| Issue and PR templates | No rule | In the checklist with required keys | No rule | Recommended for a public repository |
| Link to the document index | No rule | No rule | Required (`no-index-link`) | Required |
| No broken links | Stated, not linted | No rule | Check g | Required, check g plus a scheduled external check |
| Page front matter | No rule | No rule | Five fields (check h) | Five fields, plus `superseded_by` when `status: superseded` |
| Page type and directory | No rule | No rule | Diátaxis four (check h) | Diátaxis four plus `decision` |
| Index links every page | No rule | No rule | Required (`unindexed`) | Required |
| Changelog | No rule | No rule | No rule | Optional; Keep a Changelog shape when present |
| Staleness | No rule | No rule | `last_reviewed` is a date only | Maximum age per status |
| Prose rules | Code examples linted like code | No rule | No rule | Vale: banned words, STE subset, spelling |
| Markdown shape | Valid Markdown | No rule | No rule | markdownlint subset |
| `AGENTS.md` | No rule | No rule | No rule | Required, links to the index |

## Decision list

1. **Base of the README rule.** Options: (a) adopt standard-readme with its
   linter; (b) keep check i and add `Contributing`. Recommended: (b). Reason:
   the standard-readme linter is unfinished after nine years, its fixed order
   of 16 sections fits a library and not a service or a tool, and none of
   the eight surveyed repositories follows it. Check i already covers the
   core. Add `Contributing` as a section or a root file, because GitHub's
   checklist and standard-readme both ask for it.
2. **Section title exactness.** Options: (a) `Install` only; (b) `Install` or
   `Installation`. Recommended: (b). Reason: makeareadme, Write the Docs and
   fastapi use `Installation`; a rule that rejects a common correct title
   costs adoption and gains nothing.
3. **Table of contents.** Options: (a) require it over 100 lines; (b) do not
   require it. Recommended: (b). Reason: a hand-written TOC drifts and is a
   second list of headings to check; the rule that matters is a length
   guideline (decision 12).
4. **Front matter on pages.** Options: (a) YAML front matter, five fields;
   (b) an HTML comment block, invisible on GitHub; (c) none. Recommended:
   (a). Reason: every site generator and Obsidian read YAML front matter;
   an HTML comment is read by nothing; the cost is one small table at the
   top of a GitHub-rendered page. This closes the choice the baseline left
   open.
5. **Contractions.** Options: (a) follow Google and Microsoft, use them;
   (b) follow STE, do not use them. Recommended: (b). Reason: the pages are
   read by agents and by readers whose first language is not English; STE
   rule and the meridian wording rules already say no contractions; turn off
   `Google.Contractions` and `Microsoft.Contractions` in Vale.
6. **Internal versus external links.** Options: (a) lychee for both, on
   every run; (b) check g for internal links on every run, lychee with
   `--cache` on a schedule for external links. Recommended: (b). Reason: an
   internal check is offline and deterministic; an external check fails at
   random on rate limits and needs a cache, retries and an allow list, so it
   must not block a commit.
7. **Staleness.** Options: (a) no rule beyond the date format; (b) a maximum
   age of `last_reviewed` per status: 180 days for `current`, none for
   `draft` and `superseded`. Recommended: (b). Reason: docdecay and the
   90-day policy above show the pattern works; 90 days is aggressive for a
   small repository, 365 lets a page rot for a year. Least certain of the
   numbers; the check must take the days from the config.
8. **Decision records.** Options: (a) only `ARCHITECTURE.md` with `D<n>.<m>`
   sections; (b) add MADR pages as a fifth type `decision` under
   `docs/decisions/`, with `status` from the MADR set. Recommended: (b), as
   an option, not a requirement. Reason: the design page holds the current
   design; a decision record holds why an option lost, which a design page
   does not keep. Check h needs a fifth type value and directory; the MADR
   `status` set is small and checkable.
9. **Changelog.** Options: (a) require `CHANGELOG.md`; (b) optional, but in
   Keep a Changelog shape when present. Recommended: (b). Reason: three of
   eight surveyed repositories keep one at the root; a library needs it and
   a one-file tool may not; a wrong shape is checkable, absence is a
   project choice.
10. **Community files.** Options: (a) require the full GitHub set; (b)
    require `LICENSE`, recommend `CONTRIBUTING`, `SECURITY` and issue
    templates for a public repository, leave `CODE_OF_CONDUCT`, `GOVERNANCE`
    and `FUNDING` optional. Recommended: (b). Reason: the survey shows the
    licence at eight of eight, templates at seven, `CONTRIBUTING` at six,
    `SECURITY` at five, and the rest below half. The check must accept the
    three GitHub locations.
11. **Prose linter.** Options: (a) adopt the Google or Microsoft Vale package
    whole; (b) a repository-owned Vale style: a banned-word `existence`
    rule, an STE subset (sentence length, contractions, `-ing` forms, a
    substitution list), `Vale.Spelling` with a `Vocab`, and `We`,
    `FirstPerson`, `Latin` borrowed from Google. Recommended: (b). Reason:
    the packages carry rules that conflict with each other and with STE, and
    `Headings` capitalization fails on code identifiers. Only the banned
    words and spelling gate; the rest are suggestions.
12. **README length.** Options: (a) a hard cap; (b) a guideline of 200
    lines with a warning. Recommended: (b). Reason: makeareadme says too long
    beats too short; the survey shows the long READMEs duplicate a docs
    tree. A warning names the page to split without blocking a commit.
13. **markdownlint line length.** Options: (a) `MD013` at 80; (b) off.
    Recommended: (b). Reason: a pinned link and its title must stay on one
    line (D2.10), and a 80-column rule forces the wrap that breaks it.
14. **`AGENTS.md`.** Options: (a) optional; (b) required at the root, thin,
    with a link to `docs/README.md`. Recommended: (b). Reason: the baseline
    fixed the route `AGENTS.md → docs/README.md → pages`; a route with no
    first hop does not exist; three of eight large repositories now ship the
    file.

## Proposed rule list

Each rule is one sentence. The check names the tool that enforces it.

**Root README**

| # | Rule | Check |
|---|---|---|
| R1 | Line 1 of `README.md` is a level 1 heading or an HTML `<h1>`. | meridian check i |
| R2 | Every badge sits in one block of lines after the title. | meridian check i |
| R3 | A paragraph follows the title and the badge block. | meridian check i |
| R4 | The file has level 2 headings `Install` or `Installation`, `Usage`, and `License`. | meridian check i |
| R5 | `License` is the last level 2 heading. | meridian check i |
| R6 | The root has `LICENSE`, `LICENSE.md` or `COPYING`. | meridian check i |
| R7 | The file links to `docs/README.md` with a relative path. | meridian check i |
| R8 | The file has a `Contributing` heading, or the root or `.github/` has `CONTRIBUTING.md`. | new check needed |
| R9 | The file has a `Support` heading, or the root or `.github/` has `SUPPORT.md`. | new check needed |
| R10 | The file is at most 200 lines; a longer file gets a warning that names the split. | new check needed (warning) |
| R11 | Every link in the file resolves. | meridian check g |
| R12 | The order of the sections is Install, Usage, extra sections, Contributing, License. | markdownlint `MD043` on `README.md` (partial: fixed structure only) |

**Community files**

| # | Rule | Check |
|---|---|---|
| C1 | A public repository has `SECURITY.md` in the root, `.github/` or `docs/`. | new check needed |
| C2 | A public repository has at least one issue template in `.github/ISSUE_TEMPLATE/` with `name` and `about` (Markdown) or `name` and `description` (form). | new check needed |
| C3 | `CODE_OF_CONDUCT.md`, `GOVERNANCE.md` and `FUNDING.yml` are optional and follow the GitHub locations when present. | not checkable, guideline only |
| C4 | `AGENTS.md` exists at the root and links to `docs/README.md`. | new check needed |
| C5 | `AGENTS.md` holds build, test and convention facts and links, and no design prose. | not checkable, guideline only |
| C6 | A `CHANGELOG.md`, when present, has an `Unreleased` section, version headings `## [x.y.z] - YYYY-MM-DD` in descending order, and type headings from `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. | new check needed |

**Pages under `docs/`**

| # | Rule | Check |
|---|---|---|
| P1 | A page starts with YAML front matter between `---` lines. | meridian check h |
| P2 | The front matter gives `id`, `type`, `audience`, `status`, `last_reviewed` with the allowed values. | meridian check h |
| P3 | `type` is `tutorial`, `how-to`, `reference`, `explanation` or `decision`. | meridian check h (extend the set) |
| P4 | A page other than the index and the pipeline pages sits below `docs/<type>/`. | meridian check h |
| P5 | `docs/README.md` links to every page. | meridian check h |
| P6 | No two pages share an `id`. | meridian check h |
| P7 | A page with `status: superseded` gives `superseded_by: <id>` and that id exists. | new check needed |
| P8 | A page with `status: current` has `last_reviewed` at most 180 days old; the days come from the config. | new check needed |
| P9 | A `decision` page has `status` from `proposed`, `rejected`, `accepted`, `deprecated`, `superseded`, and the headings Context and Problem Statement, Considered Options, Decision Outcome. | new check needed |
| P10 | A page has one level 1 heading, after the front matter. | markdownlint `MD025`, `MD041` with `front_matter_title` |
| P11 | Heading levels step by one and have blank lines around them. | markdownlint `MD001`, `MD022` |
| P12 | A fenced code block names its language. | markdownlint `MD040` |
| P13 | An image has alt text; a link has descriptive text and is not empty. | markdownlint `MD045`, `MD059`, `MD042` |
| P14 | A design section that other pages cite carries an explicit id token in its heading (`D2.14`). | meridian check a (id exists) |

**Links**

| # | Rule | Check |
|---|---|---|
| L1 | An internal link uses a path relative to the file, not to the repository root. | meridian check g |
| L2 | A fragment equals a GitHub heading slug of the target file. | meridian check g; markdownlint `MD051` for the same file |
| L3 | A link to a design or law section carries a pin, and the pin matches the section. | meridian check g (`stale-pin`) |
| L4 | A pinned link and its title stay on one line. | meridian check g (`malformed`) |
| L5 | A reference-style link has a defined label, and every definition is used. | markdownlint `MD052`, `MD053` |
| L6 | An external URL resolves; the check runs on a schedule with `--cache`, retries and an allow list, and does not block a commit. | lychee |
| L7 | A page does not link into a fenced code block or rely on a heading inside one. | meridian check g (headings in fences do not count) |

**Prose**

| # | Rule | Check |
|---|---|---|
| W1 | A page does not use a word from the banned-word list. | Vale, repository `existence` rule, level `error` |
| W2 | A sentence has at most 25 words; a list item or a step has at most 20. | Vale, `occurrence` rule, level `warning` |
| W3 | A page does not use contractions. | Vale, `substitution` rule |
| W4 | A page does not use first person. | Vale, Google `We` and `FirstPerson` |
| W5 | A page uses `for example` and `that is`, not `e.g.` and `i.e.`. | Vale, Google `Latin` |
| W6 | A page uses the present tense for what the code does. | Vale, Google `Will`, level `suggestion` |
| W7 | A word is in the dictionary or in the repository `Vocab`. | Vale `Spelling` |
| W8 | A page states one topic per sentence and uses the active voice. | not checkable, guideline only (passive-voice rules stay at `suggestion`) |
| W9 | A page is of its Diátaxis type: a tutorial teaches, a how-to solves, a reference states, an explanation reasons. | not checkable, guideline only |
| W10 | A heading is in sentence case. | Vale `capitalization`, level `suggestion`, exceptions for code identifiers |

**Documentation in step with code**

| # | Rule | Check |
|---|---|---|
| S1 | A code example in a page runs where the language has a runner. | `python -m doctest`, `cargo test` doc tests, `mdbook test`, `go test` examples |
| S2 | A design claim under `## Verification` has a test that cites it. | meridian check c |
| S3 | A cited section that changes fails the citing page until the pin is renewed. | meridian check g |
| S4 | A public function has a docstring; coverage does not fall under the configured floor. | interrogate `--fail-under`, or the language linter from the comment standard |

## Sources

All read on 2026-09-24.

1. standard-readme specification — https://github.com/RichardLitt/standard-readme/blob/master/spec.md
2. standard-readme README — https://github.com/RichardLitt/standard-readme
3. standard-readme-preset (linter) — https://github.com/RichardLitt/standard-readme-preset
4. Make a README — https://www.makeareadme.com/
5. GitHub, creating a default community health file — https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file
6. GitHub, about community profiles — https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories
7. Keep a Changelog 1.1.0 — https://keepachangelog.com/en/1.1.0/
8. Diátaxis — https://diataxis.fr/, https://diataxis.fr/start-here/, https://diataxis.fr/how-to-use-diataxis/
9. Google developer documentation style guide, highlights — https://developers.google.com/style/highlights
10. Microsoft Writing Style Guide, top 10 tips — https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice
11. Write the Docs, beginner's guide — https://www.writethedocs.org/guide/writing/beginners-guide-to-docs/
12. Write the Docs, docs as code — https://www.writethedocs.org/guide/docs-as-code/
13. ASD-STE100 — https://www.asd-ste100.org/ and https://www.asd-ste100.org/about_STE.html
14. stuffbucket/vale, an STE approximation — https://github.com/stuffbucket/vale
15. arc42 template sections — https://docs.arc42.org/home/ and https://arc42.org/overview
16. C4 model — https://c4model.com/
17. MADR — https://adr.github.io/madr/ and https://github.com/adr/madr/blob/develop/template/adr-template.md
18. adr-tools — https://github.com/npryce/adr-tools
19. llms.txt — https://llmstxt.org/
20. AGENTS.md — https://agents.md/
21. lychee — https://github.com/lycheeverse/lychee
22. markdown-link-check — https://github.com/tcort/markdown-link-check
23. markdownlint rules — https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md
24. Vale styles — https://vale.sh/docs/topics/styles/
25. Vale packages — https://github.com/errata-ai/Google, https://github.com/errata-ai/Microsoft, https://github.com/errata-ai/write-good, https://github.com/errata-ai/proselint
26. textlint — https://github.com/textlint/textlint
27. alex — https://alexjs.com/
28. Jekyll front matter — https://jekyllrb.com/docs/front-matter/
29. Hugo front matter — https://gohugo.io/content-management/front-matter/
30. MkDocs meta-data — https://www.mkdocs.org/user-guide/writing-your-docs/
31. Docusaurus docs plugin front matter — https://docusaurus.io/docs/api/plugins/@docusaurus/plugin-content-docs
32. Obsidian properties — https://help.obsidian.md/properties (read from the help source repository)
33. GitHub Docs, using YAML frontmatter — https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter
34. GitHub community discussion on front matter tables — https://github.com/orgs/community/discussions/70092
35. prettier docs/index.md rendered on GitHub (front matter table observed) — https://github.com/prettier/prettier/blob/main/docs/index.md
36. Python doctest — https://docs.python.org/3/library/doctest.html
37. Sphinx builders and doctest extension — https://www.sphinx-doc.org/en/master/usage/builders/index.html, https://www.sphinx-doc.org/en/master/usage/extensions/doctest.html
38. rustdoc documentation tests — https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html
39. mdBook test — https://rust-lang.github.io/mdBook/cli/test.html
40. Testable examples in Go — https://go.dev/blog/examples
41. interrogate — https://interrogate.readthedocs.io/en/latest/
42. docdecay — https://pypi.org/project/docdecay/
43. gastownhall/beads issue #5665, 90-day review policy — https://github.com/gastownhall/beads/issues/5665
44. Repository survey through the GitHub API and raw files: rust-lang/rust, python/cpython, golang/go, kubernetes/kubernetes, django/django, fastapi/fastapi, prettier/prettier, BurntSushi/ripgrep
45. meridian, D2.10, D2.13, D2.14 and the document standard page — local, this workspace
46. Baseline research — [baseline-research.md](baseline-research.md)
