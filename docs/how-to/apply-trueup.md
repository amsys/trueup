---
id: apply-trueup
type: how-to
audience: [maintainer, agent, user]
status: current
last_reviewed: 2026-11-02
---

# Apply trueup to a repository

This page steps through one run of the trueup skill on a repository: get
the plugin, let the skill report, approve what you want, and check the
result. For what each command and finding does, read
[the trueup reference](../reference/trueup.md).

## Before you start

You need Claude Code, Python 3.11 or later, and a git repository: trueup
reads the tracked and untracked files that `git` gives, and a root that
is not in a git work tree exits 2. The skill runs a stdlib-only Python
package with `python3`, so the plugin needs no install of its own.

The `trueup` command on the path is a different matter. The pre-commit
entry (`trueup template pre-commit`) and the default global checker mode
run `trueup lint` and `trueup refs`, so each machine that commits needs
`trueup` on its path, one time:
`uv tool install git+https://github.com/amsys/trueup`, or
`pipx install git+https://github.com/amsys/trueup`. The skill reports
`tool-missing:refs/trueup` until it is there. A repository whose CI, or
another machine, cannot install trueup sets `[refs] mode = "copy"` in
`trueup.toml`; `apply` then writes a copy of the checker into the
repository, and `trueup lint` runs that copy with `python3`.

A superrepository (a `.gitmodules` file at the root) is more than one
target. Each submodule is its own repository, with its own tier and
`trueup.toml`, and the skill trues it up on its own. The superrepository
is a target too, for its own files; the skill first proposes `ignore`
globs for copies of a submodule's sources, such as run records, so they
do not pick its tier.

## 1. Install the plugin

This repository is its own plugin marketplace. Point Claude Code at it
on GitHub (a path to a local clone works too):

```
/plugin marketplace add amsys/trueup
/plugin install trueup@trueup
```

The name after `@` is the marketplace name that
`.claude-plugin/marketplace.json` gives. Claude Code reads that file and
`.claude-plugin/plugin.json` from the repository, and the plugin is then
available in any session.

## 2. Start the skill

Open Claude Code in the repository you want to true up, and ask for it in
your own words: "true up this repository", "check the docs and comment
standard here", or "what is the slop score of this repository". The
`trueup` skill's own description names these and other triggers, so
Claude Code loads it without you naming it directly.

## 3. Read the report

The skill runs `trueup check` into a scratch directory outside your
repository, so nothing changes yet. `check` runs no code from your
repository: it reads files, and runs the `ref_check.py` that ships with
the plugin, never the one in your repository. It shows you the report: the
profile, the tier, the score, the plan of findings, each with its
evidence and its action, the findings you kept earlier, and the `info`
findings.

On a repository with no `trueup.toml` and no user default file, the
report runs the `minimal` profile and its header says
`profile minimal (no trueup.toml; pass --profile house for the house standard)`.
The skill passes `--profile house` on its first check, because the
`trueup.toml` that the setup writes runs `house`.

## 4. Answer the question set

On a repository with no `trueup.toml` yet, the skill asks one set of
questions: the mode (`strict`, `clean` or `off`) for each language it
found, whether to turn on a language with little code yet, and whether
the repository is `public`. It asks about the tier only when the picked
tier looks wrong for the repository. On a later run, with `trueup.toml`
already in place, the skill does not ask these again; it asks only about
the findings in the plan.

At tier T0 or T1, the setup is one opt-in row, `setup:trueup.toml`. From
T2, the `config:trueup.toml` row asks for the file.

## 5. Approve and apply

Say which findings to act on: all the automatic ones, a named subset, or
none. The skill runs `trueup apply` with your choice. `apply` writes
`trueup.toml` first, then carries out the other approved findings in plan
order, and prints one line per action. `trueup.toml` is the only file
that the setup writes. In copy mode, the `file-managed` rows of the
checker pair write `ref_check.py` (at `[refs] path`) and
`ref_check.toml`. `apply` writes no hook, no CI workflow and no lint
config.

`apply` refuses to write a path that has uncommitted changes, and exits 2
with nothing written; commit or stash the change first, or pass
`--allow-dirty`. It never runs `git commit`, `git push`, or `git clean`,
so your working tree stays yours to commit.

An automatic row needs content to prove it. `apply` removes a scratch
file only when git tracks it and its name proves scratch (`notes.md`,
`tmp.txt`, `x.bak`); it uses `git rm`, so git can restore it. A name
that only looks like scratch (`README.old.md`, `scratch_fold.rs`) is a
manual finding, for you to delete or move under `.scratch/`. If a name
is not scratch at all (`docs/notes.md`, say), add it to `[scratch]
allow` in `trueup.toml`, or add a `[[keep]]` entry.

For a finding that needs judgement — new prose, a health file's text, a
front-matter field — the skill writes it after you approve, then re-runs
`check`. A health row names its template, for example
`trueup template security`.

## 6. Verify

The skill runs `trueup check` again and expects exit 0. For each finding
still in the plan, it tells you why: not approved, failed, or new.

Then run the linters with `trueup lint --root .`. It renders the tool
configs of each language into a temporary directory and writes nothing
in the repository. It exits 0 when each tool passed, 1 when a tool
failed, and 2 when a configured tool is not installed; it names each
missing tool first. Install the tool and run it again, or pass
`--skip-missing` on purpose. `trueup lint --install` installs the eslint
packages, jscpd and sqlfluff; it is the one `lint` path that uses the
network.

To run the linters before each commit, save the pre-commit entry as the
repository's own file:

```sh
trueup template pre-commit > .pre-commit-config.yaml
```

It holds one `repo: local` hook, `trueup-lint`, with
`entry: trueup lint` and `language: system`. To gate CI, read
[gate CI with a baseline](gate-ci-with-a-baseline.md).

## Running it again

`trueup.toml` now holds your modes, your `public` setting, your tier and
the findings you declined (`[[keep]]`). The next run reads it, and the
skill does not ask the question set again. When every plan finding was
applied, done by hand or kept, and the repository did not change since,
`check` exits 0 and the plan is empty.
