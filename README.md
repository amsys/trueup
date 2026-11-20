# trueup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](CHANGELOG.md)

trueup checks a git repository for mess and helps you remove it. One
command reports misplaced and unlinked documents, comments that break
the comment standard, scratch files, build artifacts, committed secrets,
a crowded root and missing health files such as `SECURITY.md`. Each
finding has a stable id. `trueup apply` carries out only the findings
that you approve by id.

trueup is a command-line tool and a Claude Code plugin. The command line
needs only Python and git. The plugin adds a skill that reads the
report with you, asks what to keep, and applies what you approve. It
also sets up the lint rules of each language in one of two modes, strict
or clean. New here? [Your first run](docs/tutorial/first-run.md) takes
five minutes.

**Status: alpha.** trueup works on its author's repositories, and few
other people have run it. Expect false positives. The commands, the
`trueup.toml` keys and the finding ids can change before version 0.1.0.
`check` is read-only, so a first run is safe. Please
[report](https://github.com/amsys/trueup/issues) each wrong finding and
each crash: that is the testing this version needs.

What sets it apart from other tools:

1. **It knows where a page belongs.** When a document is in the wrong
   place, trueup reads the git history to propose where to move it.
2. **You approve by id.** Each finding has a stable id, and each is
   automatic (trueup can repair it) or manual (trueup tells you what to
   do). Nothing changes until you name the id.
3. **One plan.** Documents, comments and repository hygiene are in the
   same report.
4. **It is tested to converge.** The test suite scrambles a tidy
   repository and proves that trueup brings it back, and that more mess
   never gets a better score.
5. **It runs offline.** The same input gives the same report. trueup
   uses no hosted service and opens no pull request. The one network
   lookup, a package-registry check in the plugin's install guard, is
   off unless you set `[guard] registry = true`.

## Install

trueup needs Python 3.11 or later and git. It uses the Python standard
library only. It is not on PyPI yet, so install the command from GitHub:

```sh
uv tool install git+https://github.com/amsys/trueup
```

`pipx install git+https://github.com/amsys/trueup` does the same. Then
`trueup --version` prints the version.

trueup uses two tools when they are on your path, and works without
them: `gitleaks` for the secret scan (else a built-in scan) and `tokei`
to count code lines (else a built-in count). `trueup lint` runs the
linters of your languages, such as `ruff`, `vale` and `shellcheck`.

To use trueup in Claude Code, add this repository as a plugin
marketplace and install the plugin:

```
/plugin marketplace add amsys/trueup
/plugin install trueup@trueup
```

The plugin runs its own copy of the package, so the skill and the hooks
work without the command. The pre-commit entry and the default checker
mode do run the `trueup` command, so install it too when you use them.

## Usage

Run the check from the root of the repository that you want to examine.
It changes nothing:

```sh
trueup check --root .
```

In Claude Code, open the repository and ask in your own words, for
example "true up this repository" or "check the docs and comment
standard here". The skill reports first and applies only what you
approve; [apply-trueup](docs/how-to/apply-trueup.md) steps through a
full run.

With no install, run the package directory of a clone instead:
`python3 /path/to/trueup/trueup check --root .`. On a two-file repository
with no `trueup.toml`, the output starts like this (the tree hashes are
cut short):

```
# trueup check
<!-- trueup tree head=5a2bff2... status=6e340b9... -->

profile minimal (no trueup.toml; pass --profile house for the house standard)
tier T0 (5 or fewer language files, no manifest, no CI)
counter tokei
secrets gitleaks
score 0 (tier T0)
- docs 0.0 (0 paths)
- files 0.0 (0 of 2 files)
- health 0.0 (0 of 2 required)
- root 0.0 (0 entries, budget 8)
- security 0.0 (0 findings)

## Plan (1)

- [ ] gitignore:.gitignore — [ERROR] .gitignore lacks .scratch/ — append .scratch/ to .gitignore
```

`check` exits 0 when the plan is empty, 1 when it holds a finding, and 2
on bad input or an internal error.

`trueup check --changed` scopes the same check to the files that differ
from `HEAD`. Inside a Claude Code session, a `Stop` hook runs a check
scoped to the files that session itself changed: see
[the trueup reference](docs/reference/trueup.md#hooks).
For a repository with an existing backlog, `trueup baseline` freezes
today's count, so CI can fail only on a new problem; see
[gate CI with a baseline](docs/how-to/gate-ci-with-a-baseline.md).

A target repository keeps only `trueup.toml` (and, in copy mode,
`ref_check.py` and `ref_check.toml`). `trueup lint` runs the linters of
each language with configs that it makes at run time, and
`trueup template pre-commit` prints the one pre-commit hook that runs it.
The standard is a profile: `house` or `minimal`, or a profile of your
own under `~/.config/trueup/profiles/`. A repository with a `trueup.toml`
runs `house` when the file names no profile. A repository with no
`trueup.toml` and no user default file runs `minimal`, and the report
says so. `--profile NAME` selects one for a run; see
[the profiles](docs/reference/trueup.md#profiles).

[The trueup reference](docs/reference/trueup.md) lists every command, the
`trueup.toml` keys, the findings, the rule sets and the score.

## The standards

The `house` profile checks two written standards. You can read them, and
use them without trueup:

- [The comment standard](docs/reference/comment-standard.md) gives the
  comment rules of each language and the lint command that checks them.
- [The document standard](docs/reference/document-standard.md) gives the
  rules of a page under `docs/` and of the root README.

## The reference checker

`trueup refs` checks that references are true. A comment or a test can
cite a section of your design document by its id, and a document can link
to a section of a different document. The checker fails when the cited id
or the linked heading does not exist.

A link can also carry a pin, which is a short hash of the section that
it points to. When the text of that section changes, the checker reports
the link, so that a person reads the two texts again. This link has a
pin:
[the command line of the checker](docs/ARCHITECTURE.md#d23--command-line-and-exit-codes "pin:08ee34e2").
The [configuration file](docs/ARCHITECTURE.md#d25--configuration-file-ref_checktoml "pin:2c5f796f")
of the checker is `ref_check.toml`.

The documents call this checker "the meridian check". The name comes from
meridian, the project that the checker was part of before it moved here.

## Documents

Start at the index, [docs/README.md](docs/README.md). Then read:

- [Your first run](docs/tutorial/first-run.md): a five-minute tutorial on
  a practice repository.
- [The trueup reference](docs/reference/trueup.md): the command line,
  `trueup.toml`, the findings, the rule sets and the score.
- [Apply trueup](docs/how-to/apply-trueup.md): install the plugin, run the
  skill, approve, and verify.
- [Gate CI with a baseline](docs/how-to/gate-ci-with-a-baseline.md): freeze
  today's findings and fail CI only on a new one.
- [The comment standard](docs/reference/comment-standard.md): the comment
  rules of the five languages, the lint commands, and the marker registry.
- [The document standard](docs/reference/document-standard.md): the page
  rules, the root README rules, and the further rules trueup checks.
- [The brief](docs/BRIEF.md): the goals, the limits and the decisions
  taken.
- [Architecture](docs/ARCHITECTURE.md): the design record, section by
  section, with the tests that verify each one. It is long; use it to
  look up one section, not to learn the tool.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most useful help now is a
run on your own repository and an
[issue](https://github.com/amsys/trueup/issues) for each wrong finding.
The maintainer's contact address is <dev@amsys.cz>.
[SECURITY.md](SECURITY.md) says how to report a security problem, and
[CHANGELOG.md](CHANGELOG.md) lists the changes of each version.

## License

[MIT](LICENSE).
