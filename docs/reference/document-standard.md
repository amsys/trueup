---
id: document-standard
type: reference
audience: [maintainer, agent]
status: current
last_reviewed: 2026-09-25
---

# The document standard

This page is the contract for a document page in this repository, and for
the root `README.md`. A person reads this page. The checker `ref_check.py`
runs the same rules under two switches: `[checks] layout` (check h) for a
page under `docs/`, and `[checks] readme` (check i) for the root
`README.md`. The design of both checks, the meridian check, is in
[the architecture](../ARCHITECTURE.md).

## Page rules (check h)

Each page under `docs/`, except a pipeline page, obeys these rules. The
index is [docs/README.md](../README.md).

1. **Front matter.** The page starts with `---`, a block of `<key>: <value>`
   lines, and a closing `---`.
2. **Fields.** The block gives `id`, `type`, `audience`, `status` and
   `last_reviewed`.

   | Field | Values |
   |---|---|
   | `id` | Lower-case words with hyphens. No other page uses it. |
   | `type` | `tutorial`, `how-to`, `reference` or `explanation` |
   | `audience` | A list of one value or more of `maintainer`, `agent`, `user`, for example `[maintainer, agent]` |
   | `status` | `draft`, `current` or `superseded` |
   | `last_reviewed` | An ISO date, `YYYY-MM-DD` |

3. **Directory.** A page other than the index and the two pipeline pages,
   `BRIEF.md` and `ARCHITECTURE.md`, is below `docs/<type>/`.
4. **Index.** The index holds a link to each page.
5. **Unique id.** No two pages share an `id`.

The full rules and failure kinds are in
[D2.13 of the architecture](../ARCHITECTURE.md#d213--document-layout-check-h).

## Root README rules (check i)

The root `README.md` obeys these rules. Check i reads no other file.

1. **Title.** The first text is a heading of level 1. Blank lines and an
   HTML block can come before it.
2. **Badge block.** A badge after the title stays inside one run of lines
   with no other text between them.
3. **Description.** A paragraph follows the title block and the badge
   block.
4. **Sections.** The file has a level 2 heading `Install` or
   `Installation`, one `Usage`, and one `License`.
5. **Licence.** `License` is the last section, and the root has a file
   named `LICENSE`, `LICENCE` or `COPYING`, in any case and with any
   extension.
6. **Index link.** The file links to `docs/README.md`.

The full rules and failure kinds are in
[D2.14 of the architecture](../ARCHITECTURE.md#d214--root-readme-check-i).

## Rules that trueup checks

`ref_check.py`'s check h and check i, above, are the layout rules. The
`trueup check` command (D5.4) checks a further set of rules from the
proposed rule list of
[research-documentation](../explanation/research-documentation.md#proposed-rule-list),
on any repository it checks, with or without a `trueup.toml`. C6, P7 and
P8 run only when the docs mode is `full`. The default, `docs = "auto"`,
gives `full` at tiers T2 and T3 and `readme` at T0 and T1. The other
rules always run. [The trueup reference](trueup.md) gives the full findings
table; this is the short list of which rule is which.

| Rule | What it checks | trueup's version |
|---|---|---|
| R8 | A contributing guide: a heading or a separate file. | Required from tier T2. A `README.md` `## Contributing` heading satisfies it, or `CONTRIBUTING.md` (root, `.github/` or `docs/`). |
| R10 | `README.md` over 200 lines gets a warning. | Unchanged: a warning, naming the split, once `README.md` passes 200 lines. |
| C1 | A public repository has `SECURITY.md`. | Required at every tier, only when `trueup.toml` sets `public = true`. |
| C2 | A public repository has an issue template. | Required from tier T2, only when `public = true`; a pull-request template is required alongside it. |
| C4 | `AGENTS.md` exists and links to the index. | Check-only, from tier T1: a warning when `AGENTS.md` is missing, and a warning when `CLAUDE.md` exists but neither symlinks to `AGENTS.md` nor names it with `@AGENTS.md`. trueup does not check the link to the index, and never writes either file. |
| C6 | `CHANGELOG.md`'s shape: `Unreleased`, descending versions, closed type headings. | Unchanged, checked when `CHANGELOG.md` is present and `docs = "full"`. |
| P7 | A `status: superseded` page names a `superseded_by` id that exists. | Unchanged, for pages under `docs/`, when `docs = "full"`. |
| P8 | A `status: current` page's `last_reviewed` is not older than the configured days. | The day count is `trueup.toml`'s `stale_days`, default 180. Pages under `docs/`, when `docs = "full"`. |
| W1 | No page uses a banned word. | One list, `trueup/data/banned.txt`, read case-free as a whole word or phrase, in the prose of every surveyed Markdown file (code spans and fenced blocks left out) and in the comment lines of the eight languages; the Vale `Banned.yml` style holds the same list. |

## A pinned link

A link to a section of a document can carry a pin, so a reader sees when
the cited section changes. The pin is the first eight hex digits of the
SHA-256 of the section text, in the link title:
`[text](path#fragment "pin:<hex>")`. The full rule is
[D2.10](../ARCHITECTURE.md#d210--document-link-rules). Check g reports a
pin that no longer matches the section with the kind `stale-pin`.

Keep the link and its title on one line. Do not wrap the line between the
link target and the pin. Check g reads one line at a time, and it reports a
pin title that no link on its line owns with the kind `malformed`.
