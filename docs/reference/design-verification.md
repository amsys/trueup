---
id: design-verification
type: reference
audience: [maintainer, agent]
status: current
last_reviewed: 2026-11-21
---

# Design verification

This page is the test record of
[the trueup architecture](../ARCHITECTURE.md). Each entry gives one claim
of the architecture and the tests that prove it. An entry that has no test
says so and gives the reason.

## Verification

An id names a claim. `D5.4` is a section of the architecture, `I-23` is
an invariant, `S11` is an acceptance criterion and `LOW-7` is an item of
a review. The criteria S1 to S24 are in [the brief](../BRIEF.md); S25 and
S26 are in the architecture. A test cites the ids that it proves in its
docstring.

The entries are in this order: unit tests, integration tests, acceptance
tests, then groups for the later work, in time order. A group has the
name of its round, its wave or its subject. The entries of D13, D14 and
D15 follow the group of D12 with no heading of their own. A round is one
cycle of design, build and review, and a wave is one batch of work in a
round.
[The index](../README.md#words-that-the-records-use) explains the other
words of the records.

**Unit.** Pure functions of the checker, called in process with text or a
small temporary tree as input.

- D2.1: a table of marker texts and the references or the `malformed` result
  that each one gives, for the anchored rule and the legacy rule.
- D2.2: a table of comments and the R1 or R2 result of each one.
- D2.4: the text of the line for each kind of failure.
- D2.5: a valid file, an absent file, an unknown key (exit 2), and a `# D1:`
  comment that passes with `local_tags = ["D"]` and fails without it.
- D2.7: section limits, the hash normalisation, the order of versions.
- D2.8: the declared ids, the claims and the open rows of given texts.
- D2.9: a table of suppressions with and without a reason, and of headers.
- D2.10: slugs, code spans, fenced blocks, schemes, fragments, the root
  files, and the pin rule: the section limits, the hash, a stale pin, and a
  pin that does not apply.
- I-1: marker text in a string literal, in Markdown and in an unlisted
  extension gives no reference. Examine this one first.
- I-4: a Python file with a syntax error gives `unreadable`.

**Integration.** The checker or a linter runs as a child process on a
materialised fixture tree (D4.3).

- D1.2 and D1.3: a tree with the five languages gives the expected references.
- D2.3: the flags, the summary line and the three exit codes.
- D2.6 and I-7: the edge file of a tree is equal to an expected file, and two
  runs give the same bytes.
- D4.2 and I-10: a changed section, an unchanged section, an absent section,
  and a pin that is the newest version.
- D1.6 and I-3: each file under `tests/refs/fixtures/` ends in `.txt`.
- I-2: a `ref_check.toml` with a key other than `[scan] ignore` that tries
  to skip a path gives exit 2, and no environment variable skips a path;
  `[scan] ignore` takes a path out of checks a to i; its globs match as the
  survey's globs do; `apply` renders it, and `check` and the hook then
  agree on an ignored page.
- I-8: a run leaves the tree unchanged, apart from the edge file.
- D1.1, D2.12 and I-11: a copy of the checker with a different name in a different
  tree passes under `pytest` and as a direct run.
- D2.13: a fixture tree for each kind of check h gives the line of that kind,
  a clean tree gives no line, and with `layout` absent no tree gives a failure
  of check h.
- D2.14: a fixture tree for each kind of check i gives the line of that kind,
  a clean tree gives no line, and with `readme` absent no tree gives a failure
  of check i. The root `README.md` of this repository gives no failure.

- D2.11, D1.5, D2.9, D4.3 and I-12: for each language, the wrong fixture
  fails the command that the page names, the corrected fixture passes, and
  the form with a reason continues to suppress.
- D1.4 and I-9: the page has the five blocks and its registry table is equal
  to `REGISTRY`.
- D1.6: the acceptance tests of S11 and S12 materialise their fixture trees
  and run the lint commands of the page on them.

D1.5's rule stays as written for these five languages: a test that needs a
tool which is absent fails, it does not skip, and `tests/test_lint_fixtures.py`
still does that for Python, Rust, TypeScript, shell and SQL. `trueup`'s own
sixteen rule sets are a different case: `trueup` ships every rule set
whether or not the target has the tool for it, and reports a missing one as
a `tool-missing` finding (D5.4) rather than assuming it is there. So a
rule-set test whose tool is absent skips by design and names the tool
(`test_rulesets.py`). A hook whose tool is absent and that has no test of
its own is listed as unverified in the reference page.

- D5.10 and D5.8: the plugin manifest, the marketplace entry and the hook
  wiring match the architecture, and `python3 trueup` runs as a directory
  (`test_plugin_manifest.py`, `test_cli.py`); the guard asks about a new root
  file, a scratch-looking write outside `.scratch/`, and a `git add` of a
  scratch-looking path, and its reason names `[root] allow` or
  `.scratch/`; it allows a base-list name, a `[root] allow` name, a file
  already on disk, and a write under `.scratch/`; SessionStart prints the
  tier, the root rule and the scratch rule, and the line that points at
  the trueup skill (`test_hooks.py`); the managed-file rule it also
  prints (D5.8) has no test of its own.
- D5.11: a missing or unknown subcommand, `apply` with neither or both of
  `--ids` and `--all-auto`, and an unknown hook event each exit 2; a
  `ConfigError` becomes exit 2; `--root` falls back to the git top level
  (`test_cli.py`, through `cli.main`). `check` exits 0 on an empty plan
  and 1 on a plan that holds a finding; `python3 trueup check`, run in its
  own process, gives the same exit 1 on the messy fixture; `--out` and
  `--json` write the two reports (`test_check.py`). `apply` exits 0 on
  success and 2 on a bad id, `--mode` or `--set` (`test_apply.py`). No
  test yet forces `apply`'s exit 1 (a handler that failed).
- D5.3: loading and rendering `trueup.toml` is a round trip, an unknown key
  or a bad value raises `ConfigError`, and a glob, id or reason holding a
  quote or a backslash still parses back (`test_config.py`, `test_apply.py`).
- D5.4: the eight slop rows, the tier pick (T0, T1, T3 and the
  `trueup.toml` override), the per-tier health items, the agent-file
  check, the document rules (README length, the changelog shape, a
  broken `superseded_by` link, a stale `current` page, the banned-word
  floor, and the `ref_check.py` fold-in), and `check`'s merge of all four
  rows into one sorted plan are each proved on their own inputs
  (`test_survey.py`, `test_hygiene.py`, `test_health.py`,
  `test_docrules.py`, `test_managed.py`, `test_check.py`).
- D5.5 and I-25: each of the sixteen rule sets renders its template files
  with a header comment, and where the tool it calls is on this machine the
  rendered hook passes a small good sample and fails a small bad one; the
  Vale `Banned.yml` token list is equal to `trueup/data/banned.txt`
  (`test_rulesets.py`).
- D5.6, I-21, I-24 and I-26: a managed file absent, unchanged, changed with
  the header, and changed with no header each give the finding the architecture
  states; the pre-commit hooks render in a fixed order; a `protect` glob
  is never touched; `ref_check.py` on disk that differs from the bundled
  copy gives a manual warning (`test_managed.py`, `test_apply.py`).
- D5.7: the score's five categories, each capped at its own weight, the
  root category's budget widened by `[root] allow`, the health category
  divided by the tier's required item count, and the total scaled by 100
  / 90 (`test_score.py`, `test_health.py`).
- I-18, I-19 and I-20: `check` leaves the target byte-identical; `apply`
  checks every requested id against the current plan before writing
  anything: an unknown, `info` or manual id exits 2 with no file changed,
  even beside a good id; a second `apply --all-auto` changes no byte
  after the first (`test_check.py`, `test_apply.py`).
- I-22: a hook payload with no `trueup.toml` at the found root, broken or
  empty JSON on standard input, a `cwd` with no `.git` above it, and the
  `ConfigError` a malformed `trueup.toml` raises each give no output and
  exit 0 (`test_hooks.py`); the exact `hooks.json` guard command does the
  same on a git repository with no `trueup.toml`
  (`test_plugin_manifest.py`). Limit: the `ConfigError` test runs the
  `guard` event only. On `session`, a malformed `trueup.toml` prints one
  notice line and exits 0 (D15.7), so I-22 holds there for the exit code
  only.
- I-23: `apply` never runs `git commit`, `git push` or `git clean`, and the
  rows that would otherwise read a secret file's content skip it by name
  instead (`test_hygiene.py`, `test_apply.py`).
- D6.17 and I-21: `collect(root)` with no `only` gives the v1 result; with
  `only`, it drops every repo-wide finding and reports no score; `check
  --changed` scopes the plan to `changes.working_set(root)` and exits 1
  only on a scoped finding (`test_changes.py`,
  `test_check.py::test_check_changed_scopes_findings_to_the_change_set`,
  `test_cli.py::test_check_rejects_changed_and_baseline_together`).
- D6.2: the session snapshot replaces on the source `startup` or `clear`
  and keeps its first write on `resume`, `compact` or `fork`; `session_set`
  falls back to `working_set` with no snapshot, or with one for another
  root (`test_changes.py`,
  `test_hooks.py::test_session_writes_the_snapshot_and_resume_keeps_the_first`,
  `test_plugin_manifest.py`).
- D6.3 and I-15: the Stop guard blocks on a plan scoped to the session's
  own changed files, lists up to 10 findings, and is silent when
  `stop_hook_active` is true
  (`test_hooks.py::test_stop_blocks_on_a_new_scratch_file_and_names_it`,
  `::test_stop_is_silent_when_stop_hook_active`,
  `::test_stop_is_silent_without_trueup_toml`).
- D6.4: the interface reminder fires once per path on a matched signal, and
  stays silent once `README.md` or a `docs/reference/**` path has a change
  this session, or the written path sits outside the root
  (`test_hooks.py::test_interface_reminds_once_per_path`,
  `::test_interface_is_silent_outside_root_and_without_plugin_data`).
- D6.5: each of the four drift rules (`drift-flag`, `drift-undocumented`,
  `drift-package`, `drift-command`) fires on its bad fixture and stays
  silent on the matching good one (`test_drift.py`).
- D6.6: `key` drops the line number from a `secret-content`, `changelog` or
  `refcheck` id and keeps every other id unchanged; `trueup baseline`
  writes `.trueup-baseline.json` and no other file (`test_baseline.py`,
  `test_cli.py::test_baseline_writes_the_file_and_prints_a_summary_line`).
- D6.7 and I-16: `check --baseline` exits 2 with no baseline file, 0 on an
  unchanged repository, and 1 on a new finding key, and adds the same
  `Gate` fields to the Markdown and the JSON report; a score rise with no
  new key passes (D15.21)
  (`test_check.py`,
  `test_baseline.py::test_compare_passes_a_score_rise_with_no_new_key`).
  The CI-delivery half of D6.7 — `pip install --target <tmp> .` and
  `python3 -m pip wheel .` succeeding, and `.pre-commit-hooks.yaml`'s
  shape — has no automated test in this repository; D6.7 of the
  architecture states it as a hand-run check instead.
- D6.8: each ratchet source (the Python docstring `ast` count, a Cobertura
  report, a Go coverprofile, an lcov report) parses correctly, a drop past
  the 0.1 tolerance is a `ratchet_drops` entry, and a recorded metric with
  no report now is a `missing_reports` entry (`test_baseline.py`).
- D6.9 and I-25: the form entries (`unlock`, `underscore`, `leverage`) fire on a
  verb fixture and stay silent on the paired noun fixture, and `harness`
  is silent in each use since D15.16, for
  the Python matcher and for a real `vale` run alike, and a `prose` finding
  naming 10 or more distinct words carries the `[[keep]]` hint line
  (`test_docrules.py`, `test_check.py`,
  `test_rulesets.py::test_vale_banned_forms_match_the_python_matcher`).
- D6.10 and I-23: a banner followed by a placeholder line or a comment gives
  no finding, and a key-shaped block built at test time in `tmp_path`
  (random base64, never committed) does
  (`test_hygiene.py::test_secret_content_spares_a_private_key_placeholder`).
- The local-tags change: this repository's `trueup/ref_check.py` stays
  byte-equal to the bundled copy after the change
  (`test_managed.py::test_ref_check_is_the_bundled_copy_byte_for_byte`,
  I-26). This repository has no test of its own for the `local_tags`
  behavior: the rule lives inside the checker module, not in a `trueup/`
  module beside it. Two tests under `tests/refs/` prove it at its source
  instead —
  `tests/refs/test_markers.py::test_a_local_tag_passes_the_registry_check_only_with_the_key`
  (a `# D1:` comment passes with `local_tags = ["D"]` and fails without
  it) and `tests/refs/test_config.py::test_the_registry_table_reads_the_local_tags`
  (the loader reads `[registry] local_tags`) — so no test here cites that
  section by number.
- D6.12: a `duplicate` group entirely under a `fixtures/`, `testdata/` or
  `__snapshots__/` directory gives no finding, and the `docs` category
  scales with distinct paths, capped at 10
  (`test_hygiene.py::test_duplicate_skips_a_group_entirely_under_a_fixtures_directory`,
  `test_score.py::test_docs_category_scales_and_caps_at_ten_distinct_paths`).
- D6.13: each tool-gated rule set's rendered hook, run on the real tool,
  passes a good sample and fails a bad one, and the test skips (naming the
  tool) only when it is absent (`test_rulesets.py`, one test per
  tool family: shfmt, golangci-lint, phpstan/phpcs/phpmd, eslint for
  TypeScript and Vue, vale).
- D6.14 and I-13: one fixture with a file under an `ignore` glob gives the
  same present-language set with the built-in counter and with `tokei`
  (`test_survey.py::test_tokei_scope_matches_builtin_for_ignored_files`,
  `test_check.py`).
- D6.15: each LOW item of
  [the D6.15 table](../ARCHITECTURE.md#d615--review-debt) has its own
  regression test, or a
  stated reason it needed none, recorded in
  `.state/runs/trueup-v2/07-low.md`; for example
  `test_hooks.py::test_importing_hooks_does_not_pull_in_survey_or_rulesets`
  (LOW-7) and
  `test_apply.py::test_ids_with_no_config_id_ignores_set_and_writes_no_trueup_toml`
  (LOW-9). The fixes are also exercised across `test_check.py`,
  `test_managed.py` and `test_hooks.py`.
- The field-trial record: the page
  [Field trial](../explanation/field-trial.md) states the six repositories,
  their tier, their score before and after, and the judged finding
  counts. It has no automated test: it reports a hand-judged trial, not a
  code behavior; the check is
  `grep -n 'Field trial' docs/explanation/field-trial.md`, which finds the
  page heading. The raw record is
  `.state/runs/trueup-v2/00-field-trial.md`.
- I-14: every git call in `changes.py` and `hooks.py` carries
  `--no-optional-locks`, and running each hook on a temporary repository
  leaves `git status --porcelain` and the `.git/index` mtime unchanged
  (`test_changes.py::test_working_set_uses_no_optional_locks`,
  `test_hooks.py::test_each_hook_writes_only_below_plugin_data`).
- I-17: a subprocess run of the Stop guard on this repository, with one
  changed file, records one `stop` line in the timing log
  (`test_hooks.py::test_stop_on_this_repo_records_its_time`).
- D5.3 and D5.6: a `[refs] path` value that is relative, ends in `.py` and
  has no `..` or `.` part and no backslash round-trips through `config.render`; a bad value raises
  `ConfigError`; `render()` writes the checker's bytes at `cfg.refs_path`,
  and a module at a custom path that differs from the bundled copy is a
  manual `warn`. The pre-commit snippet has no `ref-check` entry since
  D14.9, so no test of that entry stays
  (`test_config.py`,
  `test_managed.py::test_render_writes_the_checker_at_a_custom_refs_path`,
  `::test_file_finding_byte_equality_follows_refs_path`).
- D5.11: `trueup refs` is a listed subcommand; it forwards its tokens to
  `trueup.ref_check.main` unchanged, adds the resolved git top level only
  when no `--root`, `--root=`, `-h` or `--help` token is given, and exits
  2 with no git repository and no `--root`
  (`test_cli.py::test_refs_is_a_listed_subcommand`,
  `::test_refs_forwards_its_tokens_to_ref_check_main`,
  `::test_refs_adds_the_resolved_root_when_none_is_given`,
  `::test_refs_leaves_a_root_or_help_token_alone`,
  `::test_refs_without_root_outside_git_exits_two`).

**Acceptance.** One command for each criterion of the brief.

- S11 and S12: the acceptance tests are in the trueup repository, with the
  comment standard page and the lint configurations.
- S13: D2.2 on a fixture tree. S14: D1.3 on a design fixture and a law fixture.
- S15 and S16: D2.8 on fixture trees.
- S17: D4.2 on the fixture archive with two versions.
- S18: I-6 on an empty tree and on a tree with code and no marker.
- S19: D5.1. The checker runs on this repository with the five switches on
  and gives exit 0. D4.1 is proved by the same run.
- S20: D1.7, D4.4 and I-5. The unchanged selftest passes.
- S21: D2.6. S22: D2.10 on a fixture `docs/` tree and on this repository.

**Security floor (wave B).** One entry for each D7 section and each new
invariant.

- D7.2: a `package.json` with a dependency and no lockfile gives
  `lockfile:package.json`; the same manifest with `package-lock.json`, and
  a `pyproject.toml` with no dependency, give none; a workspace member with
  the lockfile at the root gives none; a broken manifest gives one
  (`test_lockfile.py::test_fixture_fires_gives_one_lockfile_finding`,
  `::test_fixture_silent_gives_no_lockfile_finding`,
  `::test_workspace_member_with_lockfile_at_root_is_silent`,
  `::test_broken_manifest_fails_closed`).
- D7.3, I-23 and I-30: a fake `gitleaks` on `PATH` maps the working tree
  and the history entries to the right ids and engine, and no finding or
  output holds the secret; a failing or slow fake gives `built-in` with a
  note; `collect` skips or runs the built-in row; the report prints the
  `secrets` line; `baseline` and `check --baseline` scan the history; a
  real gitleaks run skips when the tool is absent
  (`test_secrets.py::test_fake_gitleaks_maps_working_tree_entries_and_drops_the_secret`,
  `::test_fake_gitleaks_maps_history_entries`,
  `::test_a_failing_gitleaks_gives_built_in_with_a_note`,
  `::test_a_gitleaks_timeout_gives_built_in_with_a_note`,
  `::test_collect_skips_the_built_in_row_when_gitleaks_ran`,
  `::test_the_report_names_the_engine_after_the_counter_line`,
  `::test_baseline_and_check_baseline_scan_the_history`,
  `::test_real_gitleaks_finds_the_assembled_key_and_hides_it`); the
  gitleaks config, and no lint hook runs gitleaks since D14.6
  (`test_managed.py::test_lint_hooks_start_with_the_language_hooks_and_hold_no_gitleaks`,
  `::test_gitleaks_config_lists_the_ignore_globs_as_anchored_regexes`).
- D7.4 and I-32: every `uses:` matches the pin pattern; the CI text has
  one osv-scanner step and a comment that says when to remove it; the
  five fallback comments are present; the job checks out every commit and
  installs gitleaks by checksum before `trueup check`, which runs the
  scan since D14.9
  (`test_managed.py::test_ci_pins_every_action_to_a_commit_sha`,
  `::test_ci_has_the_osv_step_and_tells_when_to_remove_it`,
  `::test_ci_keeps_the_five_fallback_comments`,
  `::test_ci_installs_gitleaks_by_checksum_before_check`).
- D7.5: the clean config of each language flags one security bad file
  (`test_rulesets.py::test_python_ruff_config_flags_a_security_bad_file`,
  `::test_typescript_eslint_config_flags_a_security_bad_file`,
  `::test_go_golangci_lint_config_flags_a_security_bad_file`).
- D7.6: public requires `SECURITY.md` at T0, T1, T2 and T3; private does
  not (`test_health.py::test_security_required_at_every_tier_when_public`,
  `::test_required_item_count_matches_the_tier_table`).
- D7.7 and I-29: each install table row and each skip rule; deny for an
  unknown package, ask for a young one, no decision and a `systemMessage`
  for an unreachable registry; no output holds `allow`; a registry deny
  wins over the scratch `git add` ask (D15.31); the guard imports
  `registry` only for an install
  (`test_hooks.py::test_install_table_rows`,
  `::test_install_skip_rules`,
  `::test_install_guard_denies_unknown_package`,
  `::test_install_guard_asks_for_young_package`,
  `::test_install_guard_unreachable_gives_system_message`,
  `::test_install_guard_deny_wins_over_the_scratch_git_add_ask`,
  `::test_install_guard_imports_registry_only_for_an_install`).
- D7.8: a local `http.server` gives each answer type per ecosystem; the
  npm cap; the go escape; the cache hit, the TTL, the `Unreachable`
  non-cache, the corrupt cache file; no cache without
  `$CLAUDE_PLUGIN_DATA`
  (`test_registry.py::test_404_is_unknown_in_every_ecosystem`,
  `::test_npm_long_record_hits_the_cap_and_is_old`,
  `::test_go_escape_and_lowest_version`,
  `::test_cache_hit_needs_no_request`,
  `::test_cache_entry_older_than_ttl_is_looked_up_again`,
  `::test_unreachable_is_not_cached`,
  `::test_corrupt_cache_file_is_treated_as_empty`,
  `::test_no_cache_without_plugin_data`).
- D7.9 and I-31: a public fixture gives the three `platform:*` ids with the
  filled owner, repository and branch; private gives none; no subprocess
  call in `trueup/` has `gh` as its executable
  (`test_health.py::test_platform_findings_fire_with_filled_values_when_public`,
  `::test_platform_findings_use_placeholders_with_no_github_origin`,
  `::test_platform_findings_absent_when_private`,
  `::test_trueup_never_calls_gh`).
- D7.10: the reference page has one `## Security floor` section after the
  health section, with one table row per row name, a cited control per
  row, the Baseline version, the gaps, the lockfile pair table that equals
  `_LOCK_PAIRS`, and the other wave B facts
  (`test_security_floor.py::test_security_floor_section_follows_the_health_section`,
  `::test_security_floor_table_has_one_row_per_d7_10_row`,
  `::test_security_floor_names_the_baseline_version_and_the_gaps`,
  `::test_security_floor_lockfile_table_matches_lock_pairs`,
  `::test_reference_page_states_the_other_wave_b_facts`).
- I-28: only `registry.py` imports `urllib.request`, `http.client` or
  `socket`, and the scan sees every import form
  (`test_registry.py::test_only_registry_imports_network_modules`,
  `::test_network_import_scan_sees_every_form`).
- I-33: every managed file renders to the same bytes with `shutil.which`
  patched to give a path and to give `None`
  (`test_managed.py::test_render_does_not_read_the_tools_on_the_path`).
- Wave done-check: `python3 -m trueup check --root .` exits 0,
  `python3 -m pytest` passes, and `pre-commit run --all-files` passes.

**target-rust first-run fixes (D8).** One entry per D8 section.

- D8.1: the `refcheck` row before the first `apply` equals the row after
  it; `--config` reads another file, an absent one gives exit 2, and the
  usage line names it; the real bundled copy gives no finding on a
  conforming repository
  (`test_check.py::test_first_check_reports_the_refcheck_findings_that_apply_leaves`,
  `refs/test_cli.py::test_config_flag_reads_the_configuration_from_another_file`,
  `test_docrules.py::test_refcheck_fold_in_runs_the_bundled_copy`).
- D8.2: a marker below a `.git` file or directory gives no reference, the
  same marker with no `.git` gives one; a page below a nested repository
  is not a page of the root
  (`refs/test_scan.py::test_a_marker_in_a_nested_repository_gives_no_reference`,
  `::test_a_page_in_a_nested_repository_is_not_a_page_of_the_root`).
- D8.3: the managed manifest gives no `lockfile` finding and the same file
  with no marker gives one; the marker at another path exempts nothing;
  the `node_modules` info finding is present, then absent with the
  directory or with no TypeScript or Vue
  (`test_lockfile.py::test_a_managed_manifest_gives_no_lockfile_finding`,
  `::test_the_managed_marker_exempts_only_the_managed_path`,
  `test_managed.py::test_tool_findings_name_the_absent_eslint_packages`).
- D8.4: a page of cue blocks gives no finding, a real use beside them
  fires on its own line, a cue in a source comment changes nothing, a
  real `vale` run agrees on the same page, and each of the twenty-one block
  shapes of the shared table fires on the same lines in both engines
  (`test_docrules.py::test_a_markdown_block_that_quotes_the_list_gives_no_finding`,
  `::test_a_real_use_beside_a_quoted_list_still_fires`,
  `::test_a_cue_in_a_source_comment_does_not_silence_the_word`,
  `::test_quoted_list_shapes_fire_on_the_expected_lines`,
  `test_rulesets.py::test_vale_block_ignores_match_the_quoted_list_rule`,
  `::test_vale_quoted_list_shapes_match_the_python_matcher`).
- D8.5: the plural noun and the leading-underscore sentence are silent,
  the verb and the passive fire; the `leverage` noun is silent and the verb
  fires; the Python matcher and a real `vale` run agree on each form
  fixture
  (`test_docrules.py::test_banned_word_form_plural_noun_underscores_is_silent`,
  `::test_banned_word_form_leverage_noun_is_silent_verb_fires`,
  `::test_banned_word_form_noun_use_is_silent_verb_use_fires`,
  `test_rulesets.py::test_vale_banned_forms_match_the_python_matcher`).
- D8.6: the template section names the eight lexed extensions and the hook
  types agree; a string literal in an `.mjs`, `.sh` or `.sql` file gives
  no Vale alert while a `.js` comment does
  (`test_rulesets.py::test_vale_source_section_lists_only_the_extensions_vale_lexes`,
  `::test_vale_does_not_read_a_string_literal_of_an_unlexed_extension`).
- D8.7: `load` reads the key and rejects a bad shape, `render` writes and
  round-trips it, the rendered `ref_check.toml` carries it, a hand edit of
  the managed file is drift, the key silences the project's tags on the
  first `check` and after `apply`, and the `unregistered` action names it
  (`test_config.py::test_load_reads_refs_local_tags`,
  `::test_load_rejects_bad_refs_local_tags`,
  `::test_render_writes_refs_local_tags_and_round_trips`,
  `::test_refs_local_tag_shape_equals_the_checkers`,
  `test_managed.py::test_render_ref_check_config_carries_the_local_tags`,
  `::test_a_hand_edit_of_the_managed_ref_check_toml_is_drift`,
  `test_check.py::test_refs_local_tags_silence_the_projects_own_tags`,
  `test_docrules.py::test_refcheck_unregistered_action_names_local_tags`).
- D8.8: three copied manifests under `.state/` give T3, and an `ignore`
  glob for them gives no manifest and another tier
  (`test_survey.py::test_manifests_under_an_ignore_glob_do_not_count_for_the_tier`).

**target-rust second-run fixes (D9).** One entry per D9 section with code.

- D9.1: the mode defaults to `global`, `copy` and `layout` read back,
  a mode outside the two or a `path` without copy mode is a config
  error, and `render` round-trips the table; in global mode `render`
  has no checker entry and the pre-commit snippet runs `trueup lint`
  only (D14.9); in copy mode `render` writes the bundled checker with
  the managed header on its first line, and `trueup lint` runs that
  copy; an old copy is an `info` finding and
  `apply` leaves it in place; `trueup` absent from the path gives the
  install finding in global mode only; the CI workflow names the install
  in one placeholder comment, the same in both modes (D14.9); in both modes a kept finding fails neither
  `check` nor the hook's command, and a new one fails both
  (`test_config.py::test_refs_mode_defaults_to_global_and_layout_to_on`,
  `::test_load_reads_refs_mode_path_and_layout`,
  `::test_load_rejects_a_bad_refs_mode_or_layout_or_a_path_without_copy_mode`,
  `::test_render_writes_refs_mode_and_layout_and_round_trips`,
  `test_managed.py::test_global_mode_renders_no_checker_copy_and_the_lint_hook`,
  `::test_copy_mode_renders_the_copy_with_the_header`,
  `::test_global_mode_reports_an_old_copy_as_info`,
  `::test_global_mode_names_trueup_when_it_is_not_on_the_path`,
  `::test_ci_names_the_trueup_install_in_one_placeholder_comment`,
  `test_apply.py::test_apply_in_global_mode_writes_no_copy_and_leaves_an_old_one_in_place`,
  `test_check.py::test_a_kept_refcheck_finding_fails_neither_check_nor_the_hook`).
- D9.2: the checker reads `[keep] failures` and rejects another shape or
  key; a kept failure is not printed, not counted, gives exit 0 and the
  notice, and a new failure beside it gives exit 1; `failure_ids` adds
  the tail and the count where ids repeat; `docrules` builds its ids
  with that function; the managed `ref_check.toml` carries the kept ids
  and the `check` render does not
  (`refs/test_config.py::test_the_keep_table_reads_the_failure_ids`,
  `::test_a_keep_table_outside_the_schema_gives_exit_two`,
  `refs/test_cli.py::test_a_kept_failure_is_not_printed_not_counted_and_gives_exit_zero`,
  `::test_failure_ids_add_the_tail_and_the_count_where_ids_repeat`,
  `test_docrules.py::test_refcheck_ids_come_from_the_checkers_failure_ids`,
  `test_managed.py::test_render_ref_check_config_carries_the_kept_failures`,
  `test_check.py::test_a_kept_refcheck_finding_fails_neither_check_nor_the_hook`).
- D9.3: the rendered copy starts with the header; a copy that differs
  and keeps the header is an automatic error, one with no header a
  manual warn; every rendered text file, the copy included, opens with
  the header
  (`test_managed.py::test_copy_mode_renders_the_copy_with_the_header`,
  `::test_an_older_trueup_copy_with_the_header_is_an_automatic_error`,
  `::test_every_rendered_file_starts_with_the_header`).
- D9.4: `layout = false` reads, renders and round-trips, and the
  rendered `ref_check.toml` turns the switch off and leaves the others
  on
  (`test_config.py::test_load_reads_refs_mode_path_and_layout`,
  `::test_render_writes_refs_mode_and_layout_and_round_trips`,
  `test_managed.py::test_render_ref_check_config_turns_layout_off`).
- D9.5: every package fragment holds the eslint 10 ranges, and this
  repository's `lint/ts/package.json` holds the same ones, so the real
  eslint tests of D5.5 run on eslint 10
  (`test_rulesets.py::test_eslint_packages_ask_for_eslint_10_and_the_matching_plugins`,
  `::test_lint_ts_follows_the_template_ranges`).
- D9.6: both clippy entries pass `--keep-going` and deny
  `missing_docs`; a real run on a three-crate workspace accepts the flag
  and names the failing crate and the independent one
  (`test_rulesets.py::test_clippy_entries_keep_going_and_keep_missing_docs`,
  `::test_rust_clippy_checks_every_crate_that_does_not_depend_on_a_failing_one`).

**Round 3, wave A (D10).** One entry for each D10 section that has a
test. The entries of the other D10 sections come with their tests.

- D10.3: a backup word in the extension chain, a copy suffix on a
  document, and a `scratch` or `untitled` prefix at any extension are
  scratch; a copy suffix on a source extension and the names
  `template.py`, `notes_service.py` and `v0_v1.rs` are not; a clean name
  under a top-level `tmp/`, `temp/` or `scratch/` is scratch for
  `check`, and the guard hook asks about the new names but lets a clean name
  under `tmp/` through; a bare basename in another directory exempts
  nothing, a relative or a full path does; when no tracked copy of a
  content stays, one `scratch` finding is manual with the last-copy
  evidence, also for an `artifact` copy, an untracked copy and a small
  file; a copy names its kept original, and `duplicate` drops a path
  that `scratch` flags
  (`test_hygiene.py::test_scratch_backup_word_in_the_extension_chain_is_scratch`,
  `::test_scratch_copy_suffix_in_a_document_name_is_scratch`,
  `::test_scratch_copy_suffix_never_matches_a_source_extension`,
  `::test_scratch_prefix_matches_any_extension`,
  `::test_scratch_i_fp_names_stay_clean`,
  `::test_looks_scratch_path_flags_a_clean_name_under_a_scratch_directory`,
  `::test_looks_scratch_path_needs_an_exact_directory_segment`,
  `::test_scratch_row_flags_a_clean_name_under_a_scratch_directory`,
  `::test_scratch_exemption_needs_a_relative_or_slashed_mention`,
  `::test_scratch_last_copy_keeps_one_removal_manual`,
  `::test_scratch_last_copy_rule_also_counts_an_artifact_copy`,
  `::test_scratch_last_copy_rule_skips_an_untracked_copy`,
  `::test_scratch_last_copy_rule_needs_a_tracked_kept_original`,
  `::test_scratch_last_copy_rule_holds_for_a_small_content`,
  `::test_scratch_copy_evidence_names_the_kept_original`,
  `::test_duplicate_drops_a_path_the_scratch_row_already_flags`,
  `test_hooks.py::test_guard_asks_on_the_widened_scratch_name_patterns`,
  `::test_guard_ignores_the_scratch_directory_rule`).
- D10.4: `dist/` beside a Go manifest is an `artifact` directory, and an
  artifact directory that holds a tracked page is a manual finding that
  names the page
  (`test_hygiene.py::test_artifact_flags_dist_beside_a_go_manifest`,
  `::test_artifact_directory_holding_a_tracked_page_is_manual`).
- D10.5: `apply` of an `artifact` id adds no `.gitignore` line when a
  line already covers the path
  (`test_apply.py::test_artifact_gitignore_line_is_not_repeated_when_already_covered`).

**Round 3, wave B (D10).** One entry for each D10 section or invariant of
this wave that has a test.

- D10.2: a Markdown page outside `docs/` is a candidate; a non-Markdown
  file, a `docs` segment at any depth, a standard root page at the root
  in any case, a `README.md`, `CHANGELOG.md` or `SKILL.md` at any depth,
  a dot or fixture segment and a path that `scratch` flags are not; a
  standard root name in a subdirectory is; `collect` adds one finding for
  each page and the move plan to `CheckRun`, and both reports print it; a
  scoped run has no moves and reports only the pages in its scope
  (`test_layout.py::test_candidate_filter_accepts_a_plain_misplaced_page`,
  `::test_candidate_filter_rejects_a_non_markdown_file`,
  `::test_candidate_filter_rejects_any_docs_segment`,
  `::test_candidate_filter_rejects_a_standard_root_page_case_insensitively`,
  `::test_candidate_filter_rejects_a_standard_root_page_only_at_depth_zero`,
  `::test_candidate_filter_rejects_readme_changelog_and_skill_anywhere`,
  `::test_candidate_filter_rejects_hidden_and_fixture_segments`,
  `::test_candidate_filter_rejects_a_scratch_flagged_path`,
  `::test_locate_excludes_a_path_the_scratch_row_already_flagged`,
  `test_check.py::test_collect_wires_layout_into_the_move_plan`,
  `::test_collect_scoped_run_has_no_moves_and_scopes_the_doc_misplaced_row`,
  `::test_check_changed_drops_hygiene_rows_outside_the_change_set`).
- D10.6: with no candidate, no git command runs; history places a renamed
  page, and a target that exists now is refused; a broken link places a
  page or a directory by a basename that one surveyed path holds, and a
  basename that two paths hold, candidate or not, gives no link target;
  a target outside the repository is refused; the standard reads the
  `type`, and uses `docs/<basename>` with `layout = false` or `docs =
  "readme"`; a directory whose pages move the same way is one move, and
  siblings that disagree, a lone page, a code directory, an ancestor whose
  target holds other files and a target that another move fills are not;
  a non-Markdown file goes with a directory move only when evidence places
  it; `protect` on the source, the target or a file inside the directory
  stops the move; two moves with one target, or a file target inside a
  directory target, are both dropped and the evidence names the shared
  target; a broken link gets the move hint or the fix-the-link hint, and
  its id does not change; a scoped call gives findings only in its scope,
  no moves and no notes
  (`test_layout.py::test_locate_with_no_candidate_runs_no_history_scan`,
  `::test_locate_history_evidence_resolves_a_renamed_page`,
  `::test_locate_history_target_rejected_when_the_old_path_exists_now`,
  `::test_locate_link_evidence_resolves_a_unique_basename_match`,
  `::test_locate_link_evidence_is_skipped_when_two_candidates_share_a_basename`,
  `::test_locate_link_evidence_counts_every_surveyed_file_with_the_basename`,
  `::test_locate_link_evidence_resolves_a_directory_by_basename`,
  `::test_locate_directory_link_evidence_is_skipped_when_two_directories_share_a_basename`,
  `::test_locate_directory_link_evidence_counts_a_file_with_the_basename`,
  `::test_locate_refuses_a_file_link_target_outside_the_repository`,
  `::test_locate_refuses_a_directory_link_target_outside_the_repository`,
  `::test_locate_standard_evidence_uses_front_matter_type`,
  `::test_locate_standard_evidence_falls_back_with_layout_off`,
  `::test_locate_standard_evidence_falls_back_with_docs_readme`,
  `::test_locate_groups_a_renamed_directory_into_one_move`,
  `::test_locate_groups_a_lone_page_with_a_sibling_renamed_out_of_docs`,
  `::test_locate_directory_link_carries_a_non_markdown_file`,
  `::test_locate_keeps_individual_moves_when_siblings_disagree`,
  `::test_locate_keeps_a_lone_page_a_file_move_when_its_sibling_has_no_evidence`,
  `::test_locate_keeps_a_lone_candidate_a_file_move_with_no_sibling`,
  `::test_locate_never_moves_a_code_directory_for_one_page`,
  `::test_locate_never_moves_a_code_directory_on_page_history_only`,
  `::test_locate_units_skip_an_ancestor_whose_target_already_holds_other_content`,
  `::test_locate_units_skip_a_target_that_another_move_fills`,
  `::test_locate_protect_veto_on_the_target_blocks_the_move`,
  `::test_locate_protect_veto_on_the_source_blocks_the_move`,
  `::test_locate_protect_on_a_contained_file_blocks_the_directory_move`,
  `::test_locate_drops_two_standard_moves_with_the_same_target`,
  `::test_locate_drops_a_history_move_and_a_link_move_with_the_same_target`,
  `::test_locate_gives_no_first_wins_target_to_two_history_pages`,
  `::test_collisions_group_a_file_target_inside_a_directory_target`,
  `::test_locate_broken_link_evidence_note_names_the_new_location`,
  `::test_locate_broken_link_hint_when_the_match_already_lives_under_docs`,
  `::test_locate_evidence_notes_never_rename_a_finding_id`,
  `::test_locate_scoped_gives_findings_only_for_pages_in_only`,
  `::test_locate_scoped_with_no_candidate_in_only_gives_no_note`,
  `test_check.py::test_collect_applies_the_broken_link_note_without_changing_the_refcheck_id`).
- D10.7: a move rewrites an inbound link and an outbound link; a
  directory move keeps its inner links, keeps a `./` link and a trailing
  `/`, and carries its other file; a fragment is kept one time; a
  percent-escaped target is rewritten; only the destination changes, not
  the same words in the link text, a reference label or a code span; two
  equal links on one line change one time each; a link that was already
  broken does not change; a protected file is left broken and printed;
  an unknown `move:` id exits 2 and changes nothing
  (`test_move.py::test_move_rewrites_an_inbound_link_from_outside_the_move`,
  `::test_move_rewrites_an_outbound_link_from_the_moved_file`,
  `::test_directory_move_keeps_its_inner_links_and_carries_a_non_markdown_file`,
  `::test_directory_move_keeps_link_forms_that_need_no_change`,
  `::test_move_rewrites_a_link_with_a_fragment_without_doubling_it`,
  `::test_move_rewrites_a_percent_encoded_link_target`,
  `::test_move_rewrites_a_link_whose_text_equals_its_target`,
  `::test_move_rewrites_a_reference_definition_whose_label_equals_its_target`,
  `::test_move_never_changes_a_code_span_before_the_link`,
  `::test_move_rewrites_two_equal_links_on_one_line_once_each`,
  `::test_move_never_changes_a_broken_link_on_the_same_line`,
  `::test_a_protected_file_is_left_broken_and_printed`,
  `::test_an_unknown_move_id_exits_two_and_changes_nothing`).
- D10.8: `Score.raw` gives the text of each category, also for an empty
  plan, and the Markdown and JSON reports print it next to each category
  (`test_score.py::test_raw_counts_text_per_category`,
  `::test_raw_counts_default_empty_without_crashing`,
  `test_check.py::test_check_report_carries_raw_counts_next_to_each_category`).
- I-34: a page moves only by its named `move:` id, and `--all-auto`
  leaves a misplaced page where it is
  (`test_move.py::test_move_rewrites_an_inbound_link_from_outside_the_move`,
  `::test_move_rewrites_an_outbound_link_from_the_moved_file`,
  `::test_all_auto_never_moves_a_page`).
- I-38: a move does not rewrite a protected file and prints its links as
  left broken; `protect` on the source, the target or a file inside a
  directory stops the move
  (`test_move.py::test_a_protected_file_is_left_broken_and_printed`,
  `test_layout.py::test_locate_protect_veto_on_the_target_blocks_the_move`,
  `::test_locate_protect_veto_on_the_source_blocks_the_move`,
  `::test_locate_protect_on_a_contained_file_blocks_the_directory_move`).

**Round 3, wave D (D10).** The acceptance tests S23 and S24 of D10.10, on
the `converge` fixture.

- D10.10: the `converge` fixture, scrambled by the ten operations of
  `SCRAMBLE_OPS`, gives the tidy tree back after `check`, `apply
  --all-auto`, `check` and `apply` of each move id, with `layout` on and
  off; one operation at a time gives a longer plan and a higher score
  than the tidy tree
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_gives_a_longer_plan_and_a_higher_score`).
- I-36: the seven scrambled pages give seven `doc-misplaced` findings,
  and the two pages of `misc/design/` give one directory move; each scramble
  operation, with `layout` on and off, gives a longer plan and a higher
  score than the tidy tree
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_gives_a_longer_plan_and_a_higher_score`).
- I-37: after the four steps, `git ls-files -s` of the scrambled tree,
  with blob hashes, equals the tidy tree apart from the files trueup
  writes, and a new `check` gives no move
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`).

**Round 3, follow-up (D10).** The review fixes of round 3. Each entry
names the tests that came with its fix.

- D10.2: a kept `doc-misplaced` page keeps its finding and gets no move,
  and a directory that holds a kept page is no directory move; a root
  page that a `[root] allow` glob names is not a candidate, the same name
  in a subdirectory is
  (`test_layout.py::test_locate_gives_a_kept_page_its_finding_but_no_move`,
  `::test_locate_kept_page_stops_its_directory_unit`,
  `::test_candidate_filter_honours_root_allow_at_depth_zero_only`,
  `::test_locate_root_allow_exempts_a_root_page`).
- D10.3: a path that the `artifact` row flags gets no `scratch` finding
  (`test_hygiene.py::test_scratch_gives_no_finding_for_a_path_the_artifact_row_flags`).
- D10.4: a package `README.md` under `node_modules/` does not make the
  `artifact` directory manual
  (`test_hygiene.py::test_artifact_node_modules_readme_does_not_make_the_directory_manual`).
- D10.6: a kept page gets no move, stops its directory unit, and a
  broken link to its place gets no note; a file move or a directory move
  onto a target that exists is refused, and the evidence names the
  target; a committed and a staged rename of a non-ASCII page give
  `history` evidence when the repository quotes paths
  (`test_layout.py::test_locate_gives_a_kept_page_its_finding_but_no_move`,
  `::test_locate_gives_a_broken_link_to_a_kept_page_no_note`,
  `::test_locate_kept_page_stops_its_directory_unit`,
  `::test_locate_refuses_a_file_move_onto_an_existing_target`,
  `::test_locate_refuses_a_directory_move_onto_an_existing_directory`,
  `::test_history_renames_reads_a_committed_non_ascii_rename`,
  `::test_history_renames_reads_a_staged_non_ascii_rename`).
- D10.7: git paths are read unquoted, so a tracked non-ASCII file is
  tracked, a non-ASCII page gets its link rewrite and no `code mentions`
  line, and a protected non-ASCII file keeps its `artifact` directory; a
  `.markdown` page gets its link rewrite; a moved file's link takes the
  canonical form, a file that does not move keeps a link that still
  resolves, and `./b.md` stays; a directory move needs `<source>/` for a
  code mention; a link that was already broken does not change; the
  directory prefix maps `misc/a.md` but not `miscellany.md`
  (`test_hygiene.py::test_tracked_paths_splits_on_nul_for_a_non_ascii_path`,
  `test_move.py::test_move_rewrites_a_link_in_a_non_ascii_page`,
  `::test_untrack_keeps_a_directory_with_a_protected_non_ascii_file`,
  `::test_move_rewrites_a_link_in_a_markdown_suffix_page`,
  `::test_moved_file_links_take_the_canonical_form`,
  `::test_unmoved_file_keeps_a_link_that_still_resolves`,
  `::test_directory_move_code_mentions_need_the_trailing_slash`,
  `::test_rewrite_links_leaves_a_link_that_was_already_broken`,
  `::test_move_mapper_directory_prefix_does_not_match_a_sibling_file`,
  `test_layout.py::test_history_renames_reads_a_committed_non_ascii_rename`,
  `::test_history_renames_reads_a_staged_non_ascii_rename`).
- D10.9: the tidy `converge` tree gets no `doc-misplaced` and no
  `scratch` finding, and each scramble operation gives a longer plan and
  a higher score than the tidy tree
  (`test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`,
  `::test_one_scramble_operation_gives_a_longer_plan_and_a_higher_score`).
- I-24: an `artifact` directory that holds a protected non-ASCII file is
  skipped
  (`test_move.py::test_untrack_keeps_a_directory_with_a_protected_non_ascii_file`).
- I-37: two moves that undo a scramble give back the tidy text of a
  moved page byte for byte; the `converge` link `../glossary.md`, which
  still resolves after the scramble, is rewritten to the tidy form
  (`test_move.py::test_moved_file_links_take_the_canonical_form`,
  `::test_unmoved_file_keeps_a_link_that_still_resolves`,
  `test_convergence.py::test_scrambled_fixture_converges_to_its_tidy_source`).
- I-39: a broken-link note names the new place of a page or a file with
  the same name, the refcheck id does not change, and a broken link to
  the place of a kept page gets no note
  (`test_layout.py::test_locate_broken_link_evidence_note_names_the_new_location`,
  `::test_locate_broken_link_hint_when_the_match_already_lives_under_docs`,
  `::test_locate_evidence_notes_never_rename_a_finding_id`,
  `::test_locate_gives_a_broken_link_to_a_kept_page_no_note`).

**Round 4 (D12).** One entry for each D12 section or invariant that has a
test. S25 and S26 are the acceptance tests of D12.1 and D12.9.

- D12.1: the tree identity is `None` outside git, gives `head` and a
  status hash, changes on a second edit of a modified file and on a new
  untracked file, works from a subdirectory root, and writes no object;
  the JSON report holds `tree`, `null` outside git; `apply --plan` needs
  `--ids` or `--all-auto`, refuses a bad file, `--mode`, `--set`, an id
  the file does not hold and a plan file inside the root, and never
  collects again; the saved plan of the `converge` fixture applies later
  and gives the same files, its move ids apply, and a second edit
  refuses the run (S25)
  (`test_changes.py::test_tree_identity_is_none_outside_a_git_work_tree`,
  `::test_tree_identity_gives_head_and_a_status_hash`,
  `::test_tree_identity_changes_on_a_second_edit_of_a_modified_file`,
  `::test_tree_identity_changes_with_a_new_untracked_file`,
  `::test_tree_identity_works_from_a_subdirectory_root`,
  `::test_tree_identity_writes_no_object_and_keeps_the_index`,
  `test_check.py::test_check_json_holds_the_tree_identity`,
  `::test_check_json_tree_is_null_outside_git`,
  `test_cli.py::test_apply_plan_needs_ids_or_all_auto`,
  `::test_apply_plan_passes_the_file_to_apply_run`,
  `test_saved_plan.py::test_s25_saved_plan_all_auto_gives_the_same_files_as_a_live_run`,
  `::test_s25_saved_plan_applies_its_move_ids`,
  `::test_s25_second_edit_of_a_modified_file_refuses_and_writes_nothing`,
  `::test_saved_plan_run_never_collects_again`,
  `::test_saved_plan_with_a_plan_file_inside_the_root_refuses`,
  `::test_saved_plan_refuses_mode_and_set`,
  `::test_saved_plan_refuses_a_bad_file`,
  `::test_saved_plan_refuses_an_id_the_file_does_not_hold`,
  `::test_load_saved_run_reads_plan_findings_and_moves`,
  `::test_load_saved_run_raises_config_error_on_a_missing_file`,
  `::test_cli_apply_plan_runs_the_saved_plan`).
- D12.2: `dirty_paths` lists modified and untracked paths and both sides
  of a rename, and is empty outside git; `apply` refuses a dirty finding
  path, a dirty side file, a dirty move source and a dirty page whose
  link a move rewrites; a dirty path the run does not touch, and a dirty
  managed file with the header, are no reason to refuse; `--allow-dirty`
  lets the run go on; the stamp edits only the `run_date` line
  (`test_dirty_tree.py::test_dirty_paths_lists_modified_untracked_and_both_rename_sides`,
  `::test_dirty_paths_is_empty_outside_git`,
  `::test_apply_refuses_a_finding_path_with_uncommitted_changes`,
  `::test_apply_refuses_a_side_file_with_uncommitted_changes`,
  `::test_allow_dirty_lets_the_run_continue`,
  `::test_a_dirty_path_the_run_does_not_touch_is_no_reason_to_refuse`,
  `::test_move_refuses_a_dirty_page_whose_link_it_would_rewrite`,
  `::test_move_refuses_a_dirty_source`,
  `::test_a_dirty_managed_file_with_the_header_is_not_a_conflict`,
  `::test_stamp_edits_only_the_run_date_line`,
  `::test_cli_passes_allow_dirty`,
  `test_repin.py::test_apply_repin_refuses_a_dirty_page`).
- D12.3: line 2 of the Markdown report is the tree comment; outside git
  `check` exits 2 and writes no report (D15.2); the boxes sit on exactly the approvable ids, and the
  parity parse still gives each id; `approvable` holds the move, re-pin
  and setup ids; `--from-report` applies the ticked ids as `--ids` does,
  the setup box and a re-pin box, collects once, and refuses a report
  with no tree comment, a changed tree, an id that is not approvable, no
  ticked box and a path cut short by a dash; the CLI runs it and keeps
  it apart from `--ids` and `--plan`
  (`test_from_report.py::test_markdown_line_two_is_the_tree_comment`,
  `::test_check_outside_git_writes_no_report_so_no_tree_comment_exists`,
  `::test_boxes_sit_on_exactly_the_approvable_ids`,
  `::test_box_line_forms_and_the_parity_parse`,
  `::test_approvable_maps_each_id_to_what_it_acts_on`,
  `::test_approvable_holds_the_repin_ids`,
  `::test_from_report_applies_the_ticked_ids_as_ids_does`,
  `::test_from_report_applies_the_setup_box`,
  `::test_from_report_applies_a_ticked_repin`,
  `::test_from_report_collects_once`,
  `::test_from_report_refuses_a_report_with_no_tree_comment`,
  `::test_from_report_refuses_a_changed_tree`,
  `::test_from_report_refuses_a_ticked_id_that_is_not_approvable`,
  `::test_from_report_refuses_a_report_with_no_ticked_box`,
  `::test_from_report_cuts_a_path_with_a_dash_and_refuses`,
  `::test_cli_from_report_runs_the_ticked_ids`,
  `::test_cli_from_report_excludes_ids_and_plan`,
  `test_check.py::test_collect_wires_layout_into_the_move_plan`).
- D12.4: the SARIF run has its shape and levels, skips kept findings,
  gives locations and escapes a path that is not UTF-8; `check --sarif`
  writes the file and keeps the exit code, is refused inside the root
  unless an `ignore` glob covers it, and goes with `--changed`
  (`test_sarif.py::test_render_sarif_shape_and_levels`,
  `::test_render_sarif_skips_kept_findings`,
  `::test_render_sarif_locations`,
  `::test_render_sarif_escapes_a_surrogate_path`,
  `::test_check_sarif_writes_file_and_keeps_exit_code`,
  `::test_check_sarif_refused_inside_root`,
  `::test_check_sarif_allowed_inside_root_when_ignored`,
  `::test_check_changed_sarif`).
- D12.6: one re-pin entry for each stale pin with one clear fix, none for
  a line with two matching links or a pin that does not apply; the JSON
  and Markdown reports carry the entries; an approved id writes the new
  pin, `--all-auto` does not, an unknown id writes nothing, and a changed
  line refuses; a saved plan loads and applies the entries and refuses a
  bad one
  (`test_repin.py::test_repins_gives_one_entry_per_stale_pin`,
  `::test_repins_skips_a_line_with_two_matching_links`,
  `::test_repins_skips_a_pin_that_does_not_apply`,
  `::test_check_json_and_markdown_carry_the_repins`,
  `::test_check_json_repins_is_empty_with_no_stale_pin`,
  `::test_apply_repin_id_writes_the_new_pin`,
  `::test_apply_all_auto_does_not_repin`,
  `::test_apply_unknown_repin_id_writes_nothing`,
  `::test_apply_repin_refuses_a_line_that_changed`,
  `::test_saved_plan_loads_and_applies_the_repins`,
  `::test_saved_plan_with_a_bad_repins_entry_is_refused`).
- D12.7 (replaced by D14.8 and D14.10): no tier set holds the agent
  rules file `.claude/rules/trueup.md`, at T1 or T2, with or without a
  page under `docs/`; an old file with the header on the first line
  after its front matter gives a `managed-legacy` row, and a rules file
  that a person wrote gives no row
  (`test_managed.py::test_no_agent_rules_file_is_in_the_t2_set_and_an_old_one_is_legacy`,
  `::test_agent_rules_file_needs_t2_without_a_docs_page`,
  `::test_agent_rules_file_header_is_the_first_line_after_front_matter`,
  `::test_agent_rules_file_that_is_not_trueups_stays_out_of_the_set`).
- D12.8: strict Python has the `pydoclint` hook after `complexipy`
  (`test_rulesets.py::test_python_strict_has_the_pydoclint_hook_after_complexipy`).
- D12.9: `docs` defaults to `auto`, and `resolve_docs` maps it by tier;
  the render gives the tier set at T0, T1 and T2, keeps a managed file on
  disk below its tier, keeps the copy-mode checker at any tier, names gitleaks
  in no lint hook (D14.6), and keeps `auto` in
  `trueup.toml`; no setup finding asks for a path above the tier; the
  refcheck row runs in readme mode with the config of the tier set; the
  tier pick counts no trueup path and still counts a workflow of the
  target; at T1 with no config, one setup row and the real findings show,
  the row is not in the plan, `--all-auto` never takes it, and its id
  writes the tier set only; a T0 tree gets no row (S26)
  (`test_config.py::test_docs_default_is_auto_in_config_and_in_a_file_without_the_key`,
  `::test_resolve_docs_maps_auto_by_tier_and_keeps_an_explicit_mode`,
  `test_managed.py::test_render_t1_holds_the_t1_files_only`,
  `::test_render_t1_with_a_docs_page_holds_ref_check_toml`,
  `::test_render_t2_holds_ci_gitleaks_ref_check_and_vale`,
  `::test_render_vale_needs_t2_even_with_docs_full`,
  `::test_render_t0_holds_nothing_until_trueup_toml_exists`,
  `::test_render_copy_mode_checker_is_in_the_set_at_any_tier`,
  `::test_render_keeps_a_managed_file_on_disk_below_its_tier`,
  `::test_setup_findings_never_ask_for_a_path_above_the_tier`,
  `::test_no_lint_hook_names_gitleaks_or_its_config`,
  `::test_render_keeps_docs_auto_in_trueup_toml`,
  `test_docrules.py::test_no_config_resolves_docs_by_tier`,
  `::test_refcheck_runs_in_readme_mode_with_the_tier_set_config`,
  `::test_refcheck_at_t1_without_a_docs_page_runs_with_no_switch`,
  `::test_refcheck_at_t1_with_a_docs_page_runs_with_the_readme_switches`,
  `test_survey.py::test_tier_t0_stays_t0_after_trueup_writes_its_files`,
  `::test_tier_t1_stays_t1_when_trueup_files_pass_the_file_count`,
  `::test_a_workflow_of_the_target_still_counts_as_ci`,
  `test_setup_optin.py::test_t1_check_shows_one_setup_row_and_the_real_findings`,
  `::test_setup_row_is_not_in_the_plan`,
  `::test_markdown_report_lists_the_setup_row`,
  `::test_apply_setup_id_writes_the_tier_set_only`,
  `::test_all_auto_never_takes_the_setup_row`,
  `::test_t0_tree_gets_no_setup_row_and_no_write`,
  `::test_setup_findings_without_offer_gives_the_per_file_rows`,
  `::test_setup_findings_with_a_config_gives_the_per_file_rows`,
  `::test_setup_id_with_a_config_present_is_unknown`,
  `::test_check_json_holds_the_setup_row`).
- D12.10: `_tracked_paths`, `_list_files`, `_history_renames` and
  `apply._git` keep the bytes of a name that is not UTF-8; `check` in
  Markdown and JSON, `check --out`, a code mention and `apply --ids
  move:<that name>` run with no crash
  (`test_non_utf8_paths.py::test_tracked_paths_keep_the_bad_bytes`,
  `::test_list_files_keep_the_bad_bytes`,
  `::test_history_renames_do_not_crash`,
  `::test_staged_rename_of_bad_name_is_read`,
  `::test_apply_git_keeps_the_bad_bytes`,
  `::test_check_prints_bad_names`,
  `::test_check_out_writes_bad_names`,
  `::test_code_mentions_print_bad_names`,
  `::test_apply_moves_a_bad_name`).
- D12.11: the `artifact` row counts a `.markdown` page and ignores a
  scratch-looking page; `locate` skips a directory unit whose target
  exists, also when git ignores the file in it, and leaves out a
  scratch-looking path with no `scratch` finding
  (`test_hygiene.py::test_artifact_directory_holding_a_markdown_suffix_page_is_manual`,
  `::test_artifact_ignores_a_scratch_looking_page_in_the_directory`,
  `test_layout.py::test_locate_refuses_a_directory_move_onto_an_existing_directory`,
  `::test_locate_skips_a_directory_unit_whose_target_holds_an_ignored_file`,
  `::test_locate_excludes_a_scratch_looking_path_without_a_scratch_finding`).
- I-40: a saved plan or a report acts on its own ids, collects at most
  once, and a changed tree refuses the run
  (`test_saved_plan.py::test_s25_second_edit_of_a_modified_file_refuses_and_writes_nothing`,
  `::test_saved_plan_run_never_collects_again`,
  `test_from_report.py::test_from_report_collects_once`,
  `::test_from_report_refuses_a_changed_tree`).
- I-41: `apply` without `--allow-dirty` writes no dirty path that it
  touches, except trueup's own managed output
  (`test_dirty_tree.py::test_apply_refuses_a_finding_path_with_uncommitted_changes`,
  `::test_a_dirty_managed_file_with_the_header_is_not_a_conflict`).
- I-43: a 48-file T1 tree stays T1 after the opt-in
  (`test_setup_optin.py::test_48_file_t1_tree_stays_t1_after_the_opt_in`).
- D13.1: a code segment, an extra `code_dirs` name or agent front matter
  takes a page out of the candidate set; the tables round-trip
  (`test_code_dirs.py::test_a_code_segment_takes_a_page_out_of_the_candidate_set`,
  `::test_extra_code_dirs_extend_the_default_list`,
  `::test_locate_skips_an_agent_definition_by_its_front_matter`,
  `::test_locate_reads_layout_code_dirs_from_the_config`,
  `::test_layout_and_binary_tables_round_trip`).
- D13.2: the sniff runs at T3 only; a linked file and an allowed file get
  no finding
  (`test_hygiene.py::test_binary_sniff_runs_only_at_t3`,
  `::test_binary_spares_a_file_that_a_page_links_to`,
  `::test_binary_allow_glob_spares_a_file`).
- D13.4: each hook adds one timing line below `$CLAUDE_PLUGIN_DATA`
  (`test_hooks.py::test_each_hook_writes_only_below_plugin_data`).

- D14.1: the layers give one effective config, and a profile name with no
  file stops `apply` at exit 2
  (`test_config.py::test_profile_path_finds_a_builtin_and_a_user_profile`,
  `test_apply.py::test_apply_refuses_a_set_profile_that_resolves_to_no_file`).
- D14.2: a profile or a user file cannot set a target-only key, an empty
  list differs from an absent key, and an error names its file
  (`test_config.py::test_a_profile_or_user_file_cannot_set_a_target_only_key`,
  `test_config.py::test_an_empty_root_base_replaces_the_list_and_differs_from_absent`,
  `test_config.py::test_an_error_in_a_profile_file_names_the_file`).
- D14.3: `--set` marks its keys explicit, and a write keeps the keys that
  the file set
  (`test_apply.py::test_merge_marks_the_set_keys_and_languages_explicit`,
  `test_apply.py::test_apply_keeps_the_keys_the_file_set_and_writes_set_tier_auto`).
- D14.4: the readers use the banned list and the docs directory in force
  (`test_docrules.py::test_banned_words_follows_the_prose_keys`,
  `test_docrules.py::test_page_checks_read_the_docs_dir_in_force`).
- D14.5: the checker reads `[layout]`, and the docs directory moves the
  design file of checks a and c
  (`refs/test_config.py::test_the_layout_table_reads_the_docs_dir_and_the_three_rule_switches`,
  `refs/test_layout.py::test_docs_dir_moves_the_design_of_checks_a_and_c`).
- D14.6: a lint run leaves the target unchanged and keeps the ruff cache in
  the temporary directory
  (`test_lint.py::test_lint_writes_nothing_under_the_root`,
  `test_lint.py::test_hooks_get_the_ruff_cache_in_the_temporary_directory`).
- D14.7: absent eslint packages give one row that names the install
  (`test_managed.py::test_tool_findings_name_the_absent_eslint_packages`).
- D14.8: each old managed file gives one `info` row, and `LEGACY_PATHS`
  holds each old path
  (`test_managed.py::test_managed_legacy_is_info_for_each_file_an_earlier_trueup_wrote`,
  `test_managed.py::test_legacy_paths_hold_the_old_managed_files_and_the_names_stay`).
- D14.9: the health actions name `trueup template`
  (`test_health.py::test_health_actions_name_trueup_template`).
- D14.10: the agent rules template is gone
  (`test_hooks.py::test_the_agent_rules_template_is_gone`).
- D14.11: the guard allows the wider base list, and `[root] base` replaces
  it (`test_hooks.py::test_guard_allows_the_widened_base_list`,
  `test_hooks.py::test_guard_root_base_replaces_the_list_and_root_allow_extends_it`).
- D14.12: an attribute-list id and an HTML id are link targets
  (`refs/test_links.py::test_attribute_list_id_gives_the_id_and_the_plain_slug`,
  `refs/test_links.py::test_html_id_and_name_attributes_are_anchors`).
- D14.13: a Maven tree moves to T1, and `build/` beside a Gradle file is
  build output (`test_survey.py::test_maven_tree_moves_from_t0_to_t1`,
  `test_hygiene.py::test_build_beside_build_gradle_is_build_output`).
- D14.14: a scoped secret scan finds what the full scan finds for a changed
  file, and the history scan ignores the scope
  (`test_secrets.py::test_history_scan_ignores_only`,
  `test_secrets.py::test_real_gitleaks_scoped_scan_matches_the_full_run_for_a_changed_file`).
- D14.15: the prose pre-filter gives the same hits as the loop, and the
  merge covers every config field
  (`test_docrules.py::test_prefilter_gives_the_same_hits_as_the_per_entry_loop`,
  `test_profiles.py::test_merge_covers_every_config_field`).
- D14.16: the package data holds the built-in profiles. The doc items of
  this section have no test
  (`test_plugin_manifest.py::test_the_wheel_package_data_holds_the_builtin_profiles`).
- D14.17: a real ruff run leaves no cache under the root
  (`test_lint.py::test_real_ruff_writes_no_cache_under_the_root`).
- D14.18: a user default file does not change the JSON of a target with a
  file, and a user profile with a built-in name stops `check`
  (`test_check.py::test_a_user_default_file_does_not_change_check_json_of_a_target_with_trueup_toml`,
  `test_check.py::test_a_user_profile_with_a_built_in_name_makes_check_exit_two`).
- D14.19: `--set profile` writes the key, and `apply` writes no profile
  value into the target file
  (`test_apply.py::test_set_profile_is_written_and_a_bad_name_is_refused`,
  `test_apply.py::test_apply_leaves_no_profile_key_in_the_target_file`).
- D14.20: one failed tool gives exit 1, and a bad config gives exit 2
  (`test_lint.py::test_a_failing_tool_gives_exit_1`,
  `test_lint.py::test_a_config_error_exits_2`).
- D14.21: a scoped run of the drift rows parses only the changed files
  (`test_drift.py::test_a_scoped_run_parses_only_the_scoped_and_the_named_files`).
- D14.22: an eslint hook runs with no shell, and a file of the target goes
  on the command only when it exists
  (`test_rulesets.py::test_eslint_hook_runs_npx_from_the_eslint_dir_with_no_shell`,
  `test_rulesets.py::test_owned_file_args_pass_a_target_file_only_when_it_exists`).
- D14.23: each adopter file keeps its values through one render
  (`test_adopters.py::test_adopter_file_survives_one_render`).
- D15.1: an unexpected exception gives one line and exit 2, and a deep file
  is `unreadable`, not a crash
  (`test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_a_deep_python_file_is_unreadable_not_a_crash`).
- D15.2: `check` outside git exits 2 with one line, and a git failure raises
  (`test_cli.py::test_check_outside_git_exits_two_with_one_line`,
  `test_changes.py::test_dirty_paths_raises_when_git_fails`).
- D15.3: `check --json` has schema 1, the note and the line of each finding
  (`test_check.py::test_check_json_is_schema_1_with_a_secret_note_and_a_line_per_finding`).
- D15.4: a missing tool gives exit 2, and `--skip-missing` restores the skip
  (`test_lint.py::test_a_missing_tool_and_a_failed_tool_give_exit_2`,
  `test_lint.py::test_a_missing_tool_exits_2_and_skip_missing_restores_the_skip`).
- D15.5: `--install` adds jscpd and sqlfluff, and sqlfluff runs from the
  tools directory
  (`test_lint.py::test_install_adds_jscpd_for_strict_and_sqlfluff_for_sql`,
  `test_lint.py::test_sqlfluff_runs_from_the_tools_dir`).
- D15.6: a target with no file resolves `minimal`, and an adopted target
  with no key resolves `house`
  (`test_profile_default.py::test_a_target_that_is_not_adopted_resolves_the_minimal_profile`,
  `test_profile_default.py::test_an_adopted_target_with_no_profile_key_resolves_house`).
- D15.7: a hook with no `trueup.toml` stops before the CLI import, and an
  old Python stays silent
  (`test_launcher.py::test_hook_without_trueup_toml_exits_before_the_cli_import`,
  `test_launcher.py::test_old_python_hook_exits_0_silently`).
- D15.8: a keep prefix keeps the rows of its page only, and a fingerprint id
  keys by rule and path
  (`refs/test_config.py::test_a_keep_prefix_keeps_every_failure_of_a_page_and_no_other_page`,
  `test_baseline.py::test_key_of_a_fingerprint_id_is_the_rule_and_the_path`).
- D15.9: an automatic `scratch` row needs a whole-stem name, and a name-only
  shape is manual
  (`test_hygiene.py::test_scratch_proven_needs_a_whole_stem_name`,
  `test_convergence.py::test_a_name_only_scramble_shape_gives_a_manual_row`).
- D15.10: the content of a `.env` file proves the row, and a read error
  gives a manual row
  (`test_hygiene.py::test_secret_file_flags_a_dotenv_by_name_and_proves_it_by_content`,
  `test_hygiene.py::test_secret_file_kind_is_manual_on_a_read_error`).
- D15.11: a NUL byte decides a big file
  (`test_hygiene.py::test_binary_over_a_mebibyte_is_decided_by_a_nul_byte`).
- D15.12: the floor is 256 bytes, and a group whose members a page names is
  dropped (`test_hygiene.py::test_duplicate_floor_is_256_bytes`,
  `test_hygiene.py::test_duplicate_group_whose_members_are_all_referenced_is_dropped`).
- D15.13: a content tree gives one `info` row, and a Markdown mention does
  not exempt a directory
  (`test_layout.py::test_locate_gives_a_content_tree_one_info_row`,
  `test_layout.py::test_locate_ignores_a_directory_named_only_in_markdown`).
- D15.14: health names match without case, and any licence name counts
  (`test_health.py::test_health_names_match_without_case_and_with_the_extra_candidates`,
  `refs/test_readme.py::test_licence_present_matches_any_case_and_extension`).
- D15.15: the platform rows are `info` and stay out of the plan
  (`test_health.py::test_platform_findings_are_info_and_stay_out_of_the_plan`).
- D15.16: the noun use of a form entry is silent, and the verb use fires
  (`test_docrules.py::test_banned_word_form_noun_use_is_silent_verb_use_fires`).
- D15.17: a Cargo workspace gives one command per binary member, and an
  ignored path gives `info`
  (`test_drift.py::test_a_cargo_workspace_gives_one_command_per_binary_member`,
  `test_drift.py::test_an_ignored_command_path_gives_info`).
- D15.18: a heredoc holds no suppression, and each Markdown case gives only
  its real broken links
  (`refs/test_comments.py::test_check_f_reads_no_suppression_in_a_heredoc`,
  `refs/test_links.py::test_each_markdown_case_gives_only_its_real_broken_links`).
- D15.19: the Rust reader strips the longest leader, and doc comments are
  marker positions
  (`refs/test_readers.py::test_the_rust_reader_strips_the_longest_leader`,
  `refs/test_readers.py::test_rust_doc_comments_are_marker_positions`).
- D15.20: a gitleaks timeout gives the engine row and the built-in rows, and
  the scan maps working-tree entries
  (`test_secrets.py::test_a_gitleaks_timeout_gives_a_secret_engine_row_and_the_built_in_rows`,
  `test_secrets.py::test_fake_gitleaks_maps_working_tree_entries_and_drops_the_secret`).
- D15.21: the score counts each covered file once, and a score rise or a
  clean deletion passes the gate
  (`test_score.py::test_files_category_counts_covered_files_once`,
  `test_baseline.py::test_compare_passes_a_score_rise_with_no_new_key`,
  `test_baseline.py::test_deleting_clean_files_passes_the_baseline_gate`).
- D15.22: a run opens no symlink target outside the root, and the secret
  scan skips such a link
  (`test_fsread.py::test_a_run_over_symlinks_opens_neither_target`,
  `test_secrets.py::test_full_scan_skips_a_symlink_that_leaves_the_root`).
- D15.23: a run parses each Python file once, and a checker timeout gives
  one error row
  (`refs/test_speed.py::test_each_python_file_parses_and_tokenizes_once`,
  `test_docrules.py::test_refcheck_timeout_gives_one_refcheck_run_error`).
- D15.24: the hook log keeps its last 10,000 lines, and the Stop hook has a
  limit of 30 seconds
  (`test_hooks.py::test_hook_log_over_1_mib_keeps_its_last_10000_lines`,
  `test_plugin_manifest.py::test_stop_hook_has_a_30_second_timeout`).
- D15.25: the locator follows a rename chain, stops at a cycle and says when
  the history is shallow
  (`test_layout.py::test_history_follows_the_rename_chain_back_to_a_docs_path`,
  `test_layout.py::test_history_target_stops_at_a_cycle`,
  `test_layout.py::test_shallow_clone_says_history_is_unavailable`).
- D15.26: a deep or test-directory manifest does not count for the tier, and
  another language is listed
  (`test_survey.py::test_manifests_deep_or_under_a_test_directory_do_not_count_for_the_tier`,
  `test_survey.py::test_other_languages_are_listed_as_present_with_no_rule_set`).
- D15.27: a write through a symlink is refused, and a crafted saved row is
  refused
  (`test_apply.py::test_write_through_a_symlink_out_of_the_root_is_refused`,
  `test_saved_plan.py::test_saved_plan_refuses_a_crafted_row_that_does_not_hold`).
- D15.28: a rule set has no `nightly` field, and the strict phpmd limits
  hold (`test_rulesets.py::test_rule_set_has_no_nightly_field`,
  `test_rulesets.py::test_phpmd_strict_reports_at_the_value_after_the_limit`).
- D15.29: a higher layer resets a list, and a bad `[[eslint.off]]` entry is
  an error
  (`test_profiles.py::test_a_higher_layer_resets_eslint_off_and_root_base`,
  `test_config.py::test_load_rejects_a_bad_eslint_off_entry`).
- D15.30: `docrules` and the checker give the same pages through one parser
  (`test_docrules.py::test_docrules_and_the_checker_give_the_same_pages`,
  `test_layout.py::test_front_matter_type_reads_the_checkers_parser`).
- D15.31: the guard asks about a new scratch write and leaves an existing
  file alone
  (`test_hooks.py::test_guard_asks_on_a_new_scratch_write_outside_scratch_dir`,
  `test_hooks.py::test_guard_leaves_an_existing_scratch_named_file_alone`).
- D15.32: the install guard is off by default and skips a private index
  (`test_hooks.py::test_install_guard_is_off_by_default`,
  `test_hooks.py::test_install_guard_skips_a_package_from_a_private_index`,
  `test_config.py::test_guard_defaults_and_round_trip`).
- D15.33: `hooks.json` wires `Stop` and `PostToolUse`, with no
  `SubagentStop`
  (`test_plugin_manifest.py::test_hooks_json_wires_stop_and_post_tool_use`).
- D15.34: the session text gives the tier and docs mode in force, the house
  line and the command that runs
  (`test_hooks.py::test_session_tier_and_docs_are_the_ones_in_force`,
  `test_hooks.py::test_session_text_for_the_house_profile`,
  `test_hooks.py::test_session_hint_names_the_command_that_runs`).
- D15.35: the guard reads `git add` per shell segment
  (`test_hooks.py::test_git_add_is_read_per_shell_segment`,
  `test_hooks.py::test_git_add_paths_cut_at_each_segment`).
- D15.36: each command, flag and anchor that the skill names exists
  (`test_skill_drift.py::test_skill_names_only_real_commands_and_flags`,
  `test_skill_drift.py::test_skill_anchors_resolve`).
- D15.37: `TRUEUP_OWN_PATHS` holds the four files that trueup still writes.
  The doc items of this section have no test
  (`test_survey.py::test_own_paths_are_the_four_files_trueup_still_writes`).
- D15.38: the tests name a missing lint tool and a committed copy of this
  repository has an empty plan, and the rewritten tests assert behaviour.
  The CI matrix has no local test: it runs on each push
  (`test_lint_fixtures.py::test_a_missing_lint_tool_skips_with_its_name`,
  `test_self_check.py::test_check_on_a_committed_copy_of_this_repository_has_an_empty_plan`,
  `test_survey.py::test_tools_reflects_shutil_which`,
  `test_lint.py::test_run_takes_the_root_the_paths_and_the_two_switches`).
- I-27: a committed copy of this repository has an empty plan
  (`test_self_check.py::test_check_on_a_committed_copy_of_this_repository_has_an_empty_plan`).
- I-35: within one plan, one copy of a scratch content stays manual; with
  two equal scratch copies, `--all-auto` with no saved plan removes both
  across its passes, and `apply --plan` removes only the automatic one
  (`test_hygiene.py::test_scratch_last_copy_keeps_one_removal_manual`,
  `test_convergence.py::test_all_auto_removes_two_equal_scratch_copies_across_passes`,
  `test_saved_plan.py::test_saved_plan_removes_only_the_automatic_one_of_two_equal_scratch_copies`).
- I-42: no setup row asks for a path above the tier, and `managed-legacy` is
  `info`
  (`test_managed.py::test_setup_findings_never_ask_for_a_path_above_the_tier`,
  `test_managed.py::test_managed_legacy_is_info_for_each_file_an_earlier_trueup_wrote`).
- I-44: a target file shuts out the user default file, and an unknown
  profile is exit 2
  (`test_profiles.py::test_user_default_applies_only_without_a_target_file`,
  `test_profile_default.py::test_an_unknown_profile_flag_is_exit_2_on_every_target`).
- I-45: `apply` writes no profile value into the target file
  (`test_apply.py::test_apply_leaves_no_profile_key_in_the_target_file`).
- I-46: a user file with a built-in name is an error
  (`test_profiles.py::test_user_file_with_a_builtin_name_is_an_error`).
- I-47: a lint run writes nothing under the root, and ruff leaves no cache
  there (`test_lint.py::test_lint_writes_nothing_under_the_root`,
  `test_lint.py::test_real_ruff_writes_no_cache_under_the_root`).
- I-48: the `house` config of a target file equals that file over the
  defaults, and `check --json` of `tests/fixtures/messy` under `house`
  equals a stored output of commit 720b5d2, except the rows of an allow
  list in which each entry names its design id
  (`test_profiles.py::test_house_effective_equals_the_target_file_alone`,
  `test_house_baseline.py::test_house_gives_the_output_of_720b5d2_except_the_allowed_rows`).
  Limit: the four adopter trees cannot be rebuilt (the stored head of
  target-web is gone), so no test compares an adopter with its round-13
  output. 720b5d2 is later than round 13 and earlier than the `profile`
  key.
- I-49: `.env` bytes stay out of each output, and only a matching secret
  proves the row
  (`test_apply.py::test_secret_file_is_untracked_and_its_bytes_stay_out_of_every_output`,
  `test_hygiene.py::test_secret_file_flags_a_dotenv_by_name_and_proves_it_by_content`).
- I-50: a read stops at its cap and refuses a FIFO and a symlink out of the
  root; a `house` run, a baseline run and a move over such symlinks end
  and open neither target; the checker gives `unreadable` for them; and
  `check` ends on an untracked FIFO symlink, a staged `/dev/zero`
  symlink and a `.gitignore` FIFO symlink
  (`test_fsread.py::test_read_capped_returns_a_file_within_the_cap`,
  `test_fsread.py::test_fifo_is_refused_without_blocking`,
  `test_fsread.py::test_symlink_out_of_the_root_is_refused`,
  `test_fsread.py::test_a_house_run_opens_no_managed_or_health_symlink`,
  `test_fsread.py::test_a_baseline_over_symlinks_ends_and_opens_neither_target`,
  `test_fsread.py::test_a_move_over_symlinks_ends_and_rewrites_the_real_page`,
  `test_fsread.py::test_the_report_read_refuses_a_symlink_out_of_the_root`,
  `refs/test_readers.py::test_a_symlink_to_a_fifo_gives_unreadable_and_no_hang`,
  `refs/test_readers.py::test_a_symlink_out_of_the_root_gives_unreadable`,
  `test_listed_paths.py::test_an_untracked_fifo_symlink_does_not_hang_check`,
  `test_listed_paths.py::test_a_staged_dev_zero_symlink_does_not_fail_check`,
  `test_listed_paths.py::test_a_gitignore_fifo_symlink_stops_tokei_at_its_limit`).
  Limit: the tokei case skips when tokei is not installed. A declared
  source of D16.2 is named by the target, so the checker follows a
  symlink there and can read a page outside the root.
- I-51: a write through a parent or a last component that is a symlink is
  refused
  (`test_apply.py::test_write_through_a_symlink_out_of_the_root_is_refused`,
  `test_apply.py::test_symlink_inside_the_root_is_refused_as_a_last_component`).
- I-52: an internal error is exit 2, and an empty survey is a config error
  (`test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `refs/test_cli.py::test_main_turns_an_unexpected_exception_into_one_line_and_exit_two`,
  `test_cli.py::test_a_saved_plan_run_of_an_empty_survey_is_a_config_error`,
  `test_cli.py::test_lint_of_a_repository_with_no_tracked_file_is_a_config_error`).
- I-53: an automatic `scratch`, `secret-file` or `binary` row needs a
  whole-stem name or content
  (`test_hygiene.py::test_scratch_proven_needs_a_whole_stem_name`,
  `test_hygiene.py::test_scratch_row_is_automatic_only_for_a_proven_tracked_name`,
  `test_hygiene.py::test_secret_file_row_dotenv_auto_only_with_a_matching_secret`,
  `test_hygiene.py::test_binary_over_a_mebibyte_is_decided_by_a_nul_byte`).

**Round 16 (D16).** One entry for each section of round 16 that changes
code, and for each new invariant. A section that changes only documents
or cite lines has no entry.

- D16.1: `trueup check`, `trueup lint` and the checker run on a tracked
  file below a mode-000 directory and do not raise
  (`test_path_probes.py::test_a_command_does_not_raise_below_an_unreadable_directory`,
  `test_path_probes.py::test_ref_check_does_not_raise_below_an_unreadable_directory`).
  Limit: the suite runs on Python 3.14, where the old probes also return
  False. On 2026-11-12 these two tests and the three tests that failed
  on 3.11 passed under Python 3.11.15 (`uv run --python 3.11`). The CI
  matrix now runs the suite on Python 3.11 and 3.14 on each push.
- D16.2: each declaration shape declares, a mention and a fenced block
  do not, a typo id fails, a missing source fails with one row, and the
  keys parse, render and reach the checker
  (`refs/test_declared_sources.py::test_a_design_on_many_pages_declares_each_id`,
  `refs/test_declared_sources.py::test_a_three_part_id_is_one_id`,
  `refs/test_declared_sources.py::test_each_declaration_shape_declares`,
  `refs/test_declared_sources.py::test_a_mention_does_not_declare`,
  `refs/test_declared_sources.py::test_a_fenced_block_does_not_declare`,
  `refs/test_declared_sources.py::test_a_typo_id_fails_at_each_citation`,
  `refs/test_declared_sources.py::test_a_missing_source_fails_with_one_row_per_entry`,
  `test_config.py::test_refs_declared_and_id_forms_parse_merge_and_round_trip`,
  `test_config.py::test_the_id_form_rule_equals_the_checkers`,
  `test_managed.py::test_render_ref_check_config_carries_the_declared_sources`,
  `test_hooks.py::test_session_text_names_the_declared_pages`). Limit:
  the run on a copy of target-rust (0 `unknown-id`, and the planted bad ids fail)
  is not a test of this repository.
- D16.3: the table ships empty, a registered change turns its failures
  into warnings with exit 0, an accepted change fails again, and `check`
  gives one info row
  (`refs/test_reader_changes.py::test_the_registry_ships_empty`,
  `refs/test_reader_changes.py::test_a_registered_change_turns_its_failure_into_a_warning`,
  `refs/test_reader_changes.py::test_an_accepted_change_fails_again`,
  `refs/test_reader_changes.py::test_the_command_prints_the_warning_and_exits_0`,
  `test_docrules.py::test_a_reader_change_gives_one_info_row_and_no_error`).
  Limit: the table is empty in this release, so each test registers a
  fake change with monkeypatch.
- D16.4: a link target that starts with `${NAME}` is skipped, and a
  placeholder that is not at the start still fails
  (`refs/test_links.py::test_a_link_target_that_starts_with_a_placeholder_is_skipped`).
- D16.5: the rendered gitleaks config holds the one rule override, and
  the installed gitleaks drops the published value and reports another
  value of the same shape
  (`test_managed.py::test_gitleaks_config_lists_the_ignore_globs_as_anchored_regexes`,
  `test_secrets.py::test_real_gitleaks_drops_only_the_published_value`).
  Limit: the second test skips when gitleaks is not on the path.
- D16.6: a pair that differs in one directory segment gets the label,
  and other pairs keep the plain text
  (`test_hygiene.py::test_duplicate_labels_paths_that_differ_in_one_directory_segment`,
  `test_hygiene.py::test_duplicate_keeps_the_plain_text_for_other_paths`).
- D16.7: the strict ruff config ignores `CPY` with a reason, and the
  skill says so
  (`test_skill_drift.py::test_skill_names_the_cpy_ignore_of_the_strict_ruff_config`).
  Limit: that test reads the config and runs no ruff. The ruff runs are
  the strict cases of
  `test_rulesets.py::test_python_ruff_config_passes_good_fails_bad`,
  `test_rulesets.py::test_python_ruff_config_flags_a_security_bad_file`
  and
  `test_rulesets.py::test_python_strict_ruff_config_enforces_the_nesting_threshold`,
  which cite no round 16 id. On 2026-11-12 they passed with ruff 0.15.9
  and 0.17.4.
- D16.9: see I-35 and I-48 (`test_convergence.py`, `test_saved_plan.py`,
  `test_house_baseline.py`).
- D16.10: the named reads refuse a FIFO, a device, a symlink out of the
  root and a file over the cap; a move stops on a page over the cap or a
  page link out of the root; the tree identity hashes a symlink's link
  text and opens no FIFO; and tokei stops at its limit
  (`test_fsread.py::test_read_text_refuses_what_the_rows_must_not_open`,
  `test_fsread.py::test_a_move_refuses_a_page_over_the_cap_and_changes_nothing`,
  `test_fsread.py::test_a_move_refuses_a_page_link_out_of_the_root_and_opens_no_target`,
  `refs/test_readers.py::test_a_file_over_the_read_cap_gives_unreadable`,
  `test_listed_paths.py::test_a_symlink_gets_the_blob_sha_of_its_link_text`,
  `test_listed_paths.py::test_the_identity_of_a_regular_file_is_unchanged`,
  and the tests of I-50).
- D16.13: the key parses and merges, a bad value exits 2 with a message
  that names `refs.law_archive`, `render` writes the key only when it is
  set, and the rendered checker config holds `[targets.law] archive` only
  when the key is set, also below the tier gate
  (`test_config.py::test_refs_law_archive_parses_merges_and_round_trips`,
  `test_config.py::test_refs_law_archive_rejects_a_bad_value`,
  `test_config.py::test_a_bad_refs_law_archive_exits_2_and_names_the_key`,
  `test_managed.py::test_render_ref_check_config_carries_the_law_archive`,
  `test_managed.py::test_a_law_archive_is_rendered_below_the_tier_gate`).
- I-54: with no new key set, the checker gives the rows of today, and
  the rendered checker config holds no new table
  (`refs/test_declared_sources.py::test_with_no_key_set_the_checker_keeps_todays_rows`,
  `test_managed.py::test_render_ref_check_config_carries_the_declared_sources`).
- I-55: an id that no found source declares fails at each citation
  (`refs/test_declared_sources.py::test_a_typo_id_fails_at_each_citation`,
  `refs/test_declared_sources.py::test_a_mention_does_not_declare`).
- I-56: a missing source, also in a clone without a page outside the
  root, fails with one `no-target` row per entry
  (`refs/test_declared_sources.py::test_a_missing_source_fails_with_one_row_per_entry`,
  `refs/test_declared_sources.py::test_a_clone_without_the_outside_source_fails_with_one_row`).
- I-57: checks a and c read the same sources and forms
  (`refs/test_declared_sources.py::test_checks_a_and_c_read_the_same_sources_and_forms`).
- I-58: a registered change warns with exit 0 until it is accepted, and
  then fails with exit 1
  (`refs/test_reader_changes.py::test_the_command_prints_the_warning_and_exits_0`,
  `refs/test_reader_changes.py::test_the_command_exits_1_for_an_accepted_change`).
- I-59: the installed gitleaks drops only the whole published value
  (`test_secrets.py::test_real_gitleaks_drops_only_the_published_value`).
  Limit: the test skips when gitleaks is not on the path.
