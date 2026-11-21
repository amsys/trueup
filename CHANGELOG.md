# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The version
numbers follow [PEP 440](https://peps.python.org/pep-0440/).

## [Unreleased]

### Added

- A tutorial, "Your first run": five minutes on a practice repository.
- `[refs] law_archive` in `trueup.toml`: the path of a law archive.
  trueup renders it into the checker config as `[targets.law] archive`,
  at every tier. Before, only a hand-written `ref_check.toml` could set
  a law archive, and trueup reported that file as drift.

### Changed

- The claims of the design, the section `## Verification`, moved from
  `docs/ARCHITECTURE.md` to `docs/reference/design-verification.md`.
  `[refs] declared` in `trueup.toml` names both pages, so `trueup refs`
  reads the claims on the new page: its check c proves that each claim
  has a test. A test fails when no page that check c reads holds the
  claims.

## [0.1.0a1] - 2026-11-16

The first public version. It is an alpha: the commands, the
`trueup.toml` keys and the finding ids can change before 0.1.0.

### Added

- `trueup check`: a read-only report of the documents, the comments, the
  root, the scratch files, the secrets and the health files of a
  repository, with a score and a plan of findings with stable ids.
- `trueup apply`: carries out the findings that you approve by id.
- `trueup baseline` and `trueup check --baseline`: a gate for CI that
  fails only on a new finding.
- `trueup lint`: runs the linters of each language with configs made at
  run time, in the mode `strict` or `clean`.
- `trueup refs`: the reference checker for design ids, comment markers
  and document links.
- `trueup template`: prints the starting text of a health file or a
  tool config.
- The profiles `house` and `minimal`, and user profiles.
- The Claude Code plugin: the `trueup` skill and the four hooks.
- `trueup --version`.
