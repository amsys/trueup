---
id: first-run
type: tutorial
audience: [user]
status: current
last_reviewed: 2026-11-18
---

# Your first run

This tutorial takes about five minutes. You make a small repository with
two problems in it, let trueup find them, and let trueup repair them. At
the end you know how to read a report and how to approve a finding.

You need Python 3.11 or later, git, and the `trueup` command. The
[README](../../README.md#install) says how to install it.

## 1. Make a repository to practise on

Use a new directory, so that nothing of yours can change:

```sh
mkdir practice && cd practice
git init
printf '# example\n\nA small page.\n' > README.md
printf 'print("hi")\n' > app.py
printf 'draft\n' > notes.tmp
git add -A
git commit -m "feat: start"
```

The file `notes.tmp` is the first problem: a scratch file that is
committed. The second problem is one that you cannot see yet.

## 2. Run the check

```sh
trueup check --root .
```

`check` reads the repository and changes nothing. It prints this report
(your hash values are different):

```
# trueup check
<!-- trueup tree head=9253e33... status=6e340b9... -->

profile minimal (no trueup.toml; pass --profile house for the house standard)
tier T0 (5 or fewer language files, no manifest, no CI)
counter tokei
secrets gitleaks
score 22 (tier T0)
- docs 0.0 (0 paths)
- files 20.0 (1 of 3 files)
- health 0.0 (0 of 2 required)
- root 0.0 (0 entries, budget 8)
- security 0.0 (0 findings)

## Plan (2)

- [ ] scratch:notes.tmp — [ERROR] 'notes.tmp' looks like a scratch file — git rm notes.tmp
- [ ] gitignore:.gitignore — [ERROR] .gitignore lacks .scratch/ — append .scratch/ to .gitignore
```

Read it from the top:

- **profile** is the set of rules in use. A repository with no
  `trueup.toml` gets `minimal`, a short set that is safe for any
  repository.
- **tier** is the size class of the repository, from T0 (very small) to
  T3 (large). A larger tier requires more files, such as a contributing
  guide. trueup never asks a small repository for the files of a large
  one.
- **counter** and **secrets** name the tools in use. If `tokei` or
  `gitleaks` is not on your machine, these lines name a built-in
  replacement.
- **score** counts the mess. 0 is a tidy repository, and a higher number
  is worse.
- **Plan** lists the findings. Each line has an id (`scratch:notes.tmp`),
  a severity, what is wrong, and what trueup proposes to do.

The command exits with 1, because the plan holds a finding.

## 3. Approve one finding by its id

trueup changes only what you approve. Approve the second finding:

```sh
trueup apply --root . --ids gitignore:.gitignore
```

trueup prints `wrote .gitignore`. The file now holds one line,
`.scratch/`. That directory is the place for scratch files, and git now
ignores it.

## 4. Approve all the automatic findings

Some findings are automatic: trueup can repair them without a decision
from you. The others are manual, and trueup only tells you what to do.
Apply the automatic findings that are left:

```sh
trueup apply --root . --all-auto
```

trueup prints `removed notes.tmp`. It ran `git rm`, so the removal is
staged and not yet committed. You can still look at it with
`git status`, and undo it.

## 5. Commit and check again

trueup never commits. That step is yours:

```sh
git add -A
git commit -m "chore: tidy the repository"
trueup check --root .
```

The report now ends with this line, and the command exits with 0:

```
The plan is empty. Nothing to do.
```

## What to do next

- Run `trueup check --root .` in a repository of your own. It is
  read-only, so the run is safe.
- If a finding is wrong for your repository, you can keep it: see
  [the trueup reference](../reference/trueup.md) for the `[[keep]]` entry
  of `trueup.toml`. If the finding is wrong for every repository, please
  [open an issue](https://github.com/amsys/trueup/issues).
- To use the stricter `house` standard, the lint rule sets and the Claude
  Code plugin, read [Apply trueup](../how-to/apply-trueup.md).
- To add trueup to CI in a repository that already has many findings,
  read [Gate CI with a baseline](../how-to/gate-ci-with-a-baseline.md).
