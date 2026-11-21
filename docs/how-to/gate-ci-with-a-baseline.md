---
id: gate-ci-with-a-baseline
type: how-to
audience: [maintainer, agent, user]
status: current
last_reviewed: 2026-11-02
---

# Gate CI with a baseline

This page steps through adding `trueup check --baseline` to a repository's
CI, so a pull request fails only on a new problem, not on every problem the
repository already had. For what the baseline file holds and what the gate
checks, read [the trueup reference](../reference/trueup.md#baseline).

## Before you start

You need the `trueup` command on your machine and on the CI runner, at
the same version. trueup has no package on PyPI, so both install it
from GitHub: `pip install git+https://github.com/amsys/trueup@<tag>`, or on your
own machine `uv tool install git+https://github.com/amsys/trueup@<tag>`. Name a
tag, for example `v0.1.0a1`, so the gate does not change when trueup
does. `pre-commit` can also clone the `trueup-baseline` hook of this
repository's `.pre-commit-hooks.yaml`: give `https://github.com/amsys/trueup`
as `repo:` and the tag as `rev:`.

The gate also reads gitleaks: when `gitleaks` is on the path,
`trueup baseline` and `check --baseline` scan the git history for secrets
(see [Secret engine](../reference/trueup.md#secret-engine)). Write the
baseline with the same tools that CI has. A history scan in CI that the
baseline did not have gives new keys, and the gate fails on its first
run.

## 1. Write the baseline

From the target repository's root, with a checkout you are happy to
freeze:

```sh
trueup baseline --root .
```

This writes `.trueup-baseline.json`: the count of every plan finding by
key, the score for information, and, for each language set to `clean`,
its docstring or test-coverage ratchet value. It prints
`baseline: <n> keys, score <s>`. Commit the file:

```sh
git add .trueup-baseline.json
git commit -m "chore: add trueup baseline"
```

`.trueup-baseline.json` is one of the files that trueup writes, so it
does not change the tier or the root budget.

## 2. Add the gate to CI

Start from the CI template, and save it as the target's own workflow:

```sh
trueup template ci > .github/workflows/trueup.yml
```

The template checks out the full history, sets up Python, installs
gitleaks, ruff and vale, and then runs `trueup check --root .`,
`trueup lint --root .` and `osv-scanner`. It has no baseline step, and
no trueup install: a comment marks the place for the install.

Make three changes:

1. At the comment `# install trueup here`, add the install step:

   ```yaml
   - run: pip install git+https://github.com/amsys/trueup@<tag>
   ```

2. After the tool installs, add the gate as its own step:

   ```yaml
   - run: trueup check --baseline --root .
   ```

3. Remove the step `- run: trueup check --root .`. That step exits 1
   while the plan holds a finding, so on a repository with a backlog it
   fails each run. The baseline step replaces it.

Keep `trueup lint --root .` only when the linters of the target pass
today. `trueup lint` has no baseline: it exits 1 on a lint failure and 2
when a configured tool is not installed. Install the tools of your
languages at the comment of the template, or pass `--skip-missing` on
purpose.

For a CI that is not GitHub Actions, add the same two commands, the
install and `trueup check --baseline --root .`, to the job that the
target already runs. A ratchet that reads a coverage report needs that
report from the same job (see
[the baseline section of the reference](../reference/trueup.md#baseline)).

## 3. Read what makes it fail

The gate exits 1 when:

- a finding's key has more instances than the baseline recorded (a new
  problem, not one already accepted);
- a `clean`-mode ratchet value (docstring or test coverage) dropped by
  more than a tenth of a point; or
- a ratchet value the baseline recorded has no report to measure it from
  today (for example, the job that wrote `coverage.xml` stopped doing
  so).

It exits 2 when `.trueup-baseline.json` is absent or is not a trueup
baseline, or on a bad `trueup.toml`.

The gate does not read the score. The score stays in the report as
information, so a clean deletion, which changes the file count and so
the score, does not fail the gate. The gate does not fail on a
finding the baseline already counted, even though the plan is still not
empty; that is the point of a baseline for a repository with a backlog.

## 4. Tighten it later

When the backlog shrinks (a finding fixed, a ratchet value improved), the
report lists the key under `tighten`. Run `trueup baseline --root .`
again and commit the new file. The gate then holds the repository to the
better number from then on; it never drops a requirement on its own.
