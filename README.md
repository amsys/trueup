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
`check` is read-only, so a first run is safe. Please report each wrong
finding and each crash.

What sets it apart from other tools:

1. **It knows where a page belongs.** When a document is in the wrong
   place, trueup reads the git history to propose where to move it.
2. **You approve by id.** Each finding is automatic (trueup can repair
   it) or manual (trueup tells you what to do). Nothing changes until you
   name the id.
3. **One plan.** Documents, comments and hygiene share one report.
4. **It is tested to converge.** The tests scramble a tidy repository
   and prove that trueup brings it back, and that more mess never scores
   better.
5. **It runs offline.** The same input gives the same report. trueup
   opens no pull request. Two things use the network, and both are off
   until you ask: `trueup lint --install`, and a registry check in the
   plugin's install guard, which needs `[guard] registry = true`.

## Install

trueup needs Python 3.11 or later and git. It uses the Python standard
library only. It is not on PyPI yet, so install the command from GitHub:

```sh
uv tool install git+https://github.com/amsys/trueup
```

`pipx install git+https://github.com/amsys/trueup` does the same. Then
`trueup --version` prints the version.

trueup uses `gitleaks` and `tokei` when they are on your path, and has a
built-in scan and count without them.

In Claude Code, add the marketplace and install the plugin:

```
/plugin marketplace add amsys/trueup
/plugin install trueup@trueup
```

The plugin runs its own copy of the package. Install the command too
for the pre-commit entry and the default checker mode.

## Usage

Run the check from the root of the repository that you want to examine.
It changes nothing. With no install, run `python3 /path/to/trueup/trueup
check --root .` from a clone.

```sh
trueup check --root .
```

On a two-file repository with no `trueup.toml`, the output starts like
this (the tree hashes are cut short):

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

- `trueup check --changed` scopes the check to the files that differ from
  `HEAD` and the untracked files; see
  [the command line](docs/reference/trueup.md#command-line).
- `trueup baseline` freezes today's count, so CI fails only on a new
  problem; see [gate CI with a baseline](docs/how-to/gate-ci-with-a-baseline.md).
- `trueup apply` carries out the findings that you approve by id; in
  Claude Code, the skill does this with you, as
  [apply trueup](docs/how-to/apply-trueup.md) shows.
- `trueup lint` runs the linters of your languages, such as `ruff`,
  `vale` and `shellcheck`. The standard is a profile; see
  [the profiles](docs/reference/trueup.md#profiles).

[The trueup reference](docs/reference/trueup.md) lists every command.

## The standards

The `house` profile checks two standards that you can use without trueup:
[the comment standard](docs/reference/comment-standard.md) and
[the document standard](docs/reference/document-standard.md).

## The reference checker

`trueup refs` checks that a cited design id or a linked heading exists,
and fails when it does not. A link can carry a pin, which is a short hash
of the section that it points to; the checker reports the link when that
section changes. This link has a pin:
[the command line of the checker](docs/ARCHITECTURE.md#d23--command-line-and-exit-codes "pin:08ee34e2").
You set the checker in the `[refs]` table of `trueup.toml`. In copy mode
trueup also writes a generated
[`ref_check.toml`](docs/ARCHITECTURE.md#d25--configuration-file-ref_checktoml "pin:a9815859"),
which you do not edit.

## Documents

Start at the index, [docs/README.md](docs/README.md). Then read:

- [Your first run](docs/tutorial/first-run.md): a tutorial.
- [How trueup works](docs/explanation/how-trueup-works.md): the code, by
  subject.
- [The trueup reference](docs/reference/trueup.md): every command, key and
  finding.
- [Apply trueup](docs/how-to/apply-trueup.md): install the plugin and run
  the skill.
- [Gate CI with a baseline](docs/how-to/gate-ci-with-a-baseline.md): fail
  CI only on a new finding.
- [The brief](docs/BRIEF.md): the goals and the decisions.
- [Architecture](docs/ARCHITECTURE.md): the design record. It is long; use
  it to look up one section, not to learn the tool.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most useful help now is a
run on your own repository and an
[issue](https://github.com/amsys/trueup/issues) for each wrong finding.
The maintainer's address is <dev@amsys.cz>. [SECURITY.md](SECURITY.md)
covers security reports, and [CHANGELOG.md](CHANGELOG.md) lists changes.

## License

[MIT](LICENSE).
