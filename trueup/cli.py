"""The `trueup` command line: argparse wiring for survey, check, apply and hook.

`main` builds the parser, resolves `--root`, and dispatches to one handler
per subcommand. Each handler imports its own module inside its body, not at
the top of this file, so this module needs no edit when a handler's
dependency changes (arch: D5.10, D5.11). `survey`, `check`, `apply` and
`hook` call `trueup.survey`, `trueup.report`, `trueup.apply` and
`trueup.hooks`. `refs` is the odd one out: `main` reads it off `argv`
itself, before argparse ever runs, and forwards the rest of the tokens to
`trueup.ref_check.main` unparsed.

`lint [PATH ...]` runs the linters of the effective config, with each
tool config rendered into a temporary directory; `lint --install` installs
the eslint packages, jscpd and sqlfluff in the trueup cache; a missing tool
makes `lint` exit 2 unless `--skip-missing` is given (arch: D14.6, D14.7,
D15.4, D15.5).

`survey`, `check`, `baseline`, `apply` and `lint` take `--profile NAME`. `main`
runs the handler inside `config.profile_flag`, which sets `TRUEUP_PROFILE`
for the run and restores it after the run, so every `config.load` of the
run sees the same profile and the value never leaks (arch: D14.1, D14.18,
D15.6). `refs` and `hook` have no flag; they read `TRUEUP_PROFILE` from
the environment.

`template <name>` prints one text that trueup no longer manages: the
pre-commit snippet, the CI workflow, `.editorconfig` or a health page. It
reads no target, so it has no `--root` (arch: D14.9, D14.22).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import traceback
from pathlib import Path

from trueup import __version__
from trueup import config as config_mod
from trueup.config import ConfigError

HOOK_EVENTS: tuple[str, ...] = ("session", "guard", "stop", "interface")
"""The events of the `hook` subcommand (arch: D6.3). argparse exits 2 on any other name."""

PROFILE_ENV = "TRUEUP_PROFILE"
"""The environment variable that `--profile` sets (arch: D14.1, L4)."""


def main(argv: list[str] | None = None) -> int:
    """Run the trueup CLI.

    Args:
        argv: The argument list to parse, in place of `sys.argv[1:]`. `None`
            uses `sys.argv[1:]`.

    Returns:
        The process exit code: the handler's own code, or 2 when a handler
        raises `ConfigError` (arch: D5.11) or any other exception
        (arch: D15.1). A `hook` command returns 0 on any exception (I-22). For `refs`, this is
        `trueup.ref_check.main`'s own code: 0 no failure, 1 one failure or
        more, 2 a bad command line or `ref_check.toml`.
    """
    if argv is None:
        argv = sys.argv[1:]
    # A path name that is not UTF-8 must print, not crash (D12.10).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="surrogateescape")
    try:
        if argv and argv[0] == "refs":
            return _run_refs(argv[1:])
        parser = _build_parser()
        args = parser.parse_args(argv)
        name = getattr(args, "profile", None)
        _set_profile(name)
        with config_mod.profile_flag(name):
            return args.handler(args)
    except ConfigError as exc:
        print(f"trueup: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # reason: D15.1 last-resort handler
        if _is_hook(argv):
            return 0  # I-22: a hook stays silent
        if os.environ.get("TRUEUP_DEBUG") == "1":
            traceback.print_exc()
        print(
            f"trueup: internal error: {type(exc).__name__}: {exc} "
            "(set TRUEUP_DEBUG=1 for the traceback)",
            file=sys.stderr,
        )
        return 2


def _is_hook(argv: list[str]) -> bool:
    """Say whether the command line runs the `hook` subcommand (arch: D15.1).

    Args:
        argv: The argument list that `main` got.

    Returns:
        True when the first word that is not an option is `hook`.
    """
    words = [word for word in argv if not word.startswith("-")]
    return bool(words) and words[0] == "hook"


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the four subcommands.

    Returns:
        A parser with `survey`, `check`, `apply`, `hook` and `refs` wired as
        required subcommands (arch: D5.11). An invocation with none of them,
        or with a bad option, exits 2 through argparse's own error path.
        `refs` is registered only so `trueup --help` lists it: `main`
        forwards its real tokens to `_run_refs` before this parser ever
        sees them, so its own `add_help=False` and the catch-all positional
        below are never exercised.
    """
    parser = argparse.ArgumentParser(
        prog="trueup",
        description="Check and fix a repository against the trueup hygiene baseline.",
    )
    parser.add_argument("--version", action="version", version=f"trueup {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    survey_parser = subparsers.add_parser(
        "survey", help="print a JSON inventory of the target repository"
    )
    survey_parser.add_argument("--root", type=Path, default=None)
    _add_profile_argument(survey_parser)
    survey_parser.set_defaults(handler=_run_survey)

    check_parser = subparsers.add_parser(
        "check", help="report the current plan of findings"
    )
    check_parser.add_argument("--root", type=Path, default=None)
    _add_profile_argument(check_parser)
    check_parser.add_argument("--json", action="store_true")
    check_parser.add_argument("--out", type=Path, default=None)
    check_parser.add_argument(
        "--sarif",
        type=Path,
        default=None,
        help="also write the findings as SARIF 2.1.0 to FILE (arch: D12.4)",
    )
    check_parser.add_argument(
        "--changed",
        action="store_true",
        help="scope the plan to this session's own changed files (arch: D6.17)",
    )
    check_parser.add_argument(
        "--baseline",
        action="store_true",
        help="compare the plan against .trueup-baseline.json",
    )
    check_parser.set_defaults(handler=_run_check)

    baseline_parser = subparsers.add_parser(
        "baseline",
        help="write .trueup-baseline.json from the current plan (arch: D6.6)",
    )
    baseline_parser.add_argument("--root", type=Path, default=None)
    _add_profile_argument(baseline_parser)
    baseline_parser.set_defaults(handler=_run_baseline)

    apply_parser = subparsers.add_parser("apply", help="carry out approved findings")
    apply_parser.add_argument("--root", type=Path, default=None)
    _add_profile_argument(apply_parser)
    ids_group = apply_parser.add_mutually_exclusive_group(required=True)
    ids_group.add_argument(
        "--ids", type=str, default=None, help="comma-separated finding ids"
    )
    ids_group.add_argument(
        "--all-auto", action="store_true", help="apply every automatic finding"
    )
    ids_group.add_argument(
        "--from-report",
        type=Path,
        default=None,
        help="apply the ticked boxes of a Markdown report of check (arch: D12.3)",
    )
    apply_parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="act on the plan that check --json saved in FILE (arch: D12.1)",
    )
    apply_parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="apply although a path it writes has uncommitted changes (arch: D12.2)",
    )
    apply_parser.add_argument(
        "--mode", action="append", default=[], help="LANG=MODE[,LANG=MODE...]"
    )
    apply_parser.add_argument(
        "--set", dest="set_", action="append", default=[], help="KEY=VALUE"
    )
    apply_parser.set_defaults(handler=_run_apply)

    lint_parser = subparsers.add_parser(
        "lint",
        help="run the linters of the effective config on the target (arch: D14.6)",
    )
    lint_parser.add_argument("--root", type=Path, default=None)
    _add_profile_argument(lint_parser)
    lint_parser.add_argument(
        "--changed",
        action="store_true",
        help="lint the working-tree change set only (arch: D14.6)",
    )
    lint_parser.add_argument(
        "--install",
        action="store_true",
        help="install the eslint packages, jscpd and sqlfluff in the trueup cache; uses the network (arch: D14.7, D15.5)",
    )
    lint_parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="skip a tool that is not installed, with one line, instead of exit 2 (arch: D15.4)",
    )
    lint_parser.add_argument(
        "paths", nargs="*", metavar="PATH", help="repo paths to lint (arch: D14.6)"
    )
    lint_parser.set_defaults(handler=_run_lint)

    template_parser = subparsers.add_parser(
        "template",
        help="print the text of one file trueup no longer manages (arch: D14.9)",
    )
    template_parser.add_argument("name", nargs="?", default=None)
    template_parser.set_defaults(handler=_run_template)

    hook_parser = subparsers.add_parser(
        "hook", help="run one Claude Code hook: session, guard, stop or interface"
    )
    hook_parser.add_argument("event", choices=list(HOOK_EVENTS))
    hook_parser.set_defaults(handler=_run_hook)

    refs_parser = subparsers.add_parser(
        "refs",
        add_help=False,
        help="run the reference checker (trueup.ref_check); see trueup refs --help",
    )
    refs_parser.add_argument("argv", nargs=argparse.REMAINDER)
    refs_parser.set_defaults(handler=lambda args: _run_refs(args.argv))

    return parser


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    """Add the `--profile NAME` option to one subcommand parser (arch: D14.1).

    Args:
        parser: The subcommand parser that gets the option.
    """
    parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help="use the profile NAME for this run; sets TRUEUP_PROFILE (arch: D14.1, D15.6)",
    )


def _set_profile(name: str | None) -> None:
    """Check the `--profile` value, before any config load (arch: D14.1, D14.18, D15.6).

    The flag wins over `TRUEUP_PROFILE` and over the `profile` key of the
    target file and of the user default file, on every target. `main`
    sets it for the run with `config.profile_flag`. A run without
    `--profile` keeps the variable as the environment gave it.

    Args:
        name: The `--profile` value, or `None` when the option was not
            given.

    Raises:
        ConfigError: `name` is not a valid profile name, or it resolves to
            no file in either search path. The message starts with
            `--profile:`.
    """
    if name is None:
        return
    config_mod.profile_path(name, named_by="--profile")


def _resolve_root(root_arg: Path | None) -> Path:
    """Resolve the target repository root.

    Args:
        root_arg: The `--root` value the person gave, or `None` to fall
            back to the git top level of the working directory.

    Returns:
        The resolved, absolute root path.

    Raises:
        ConfigError: `root_arg` is not a directory (arch: D15.2), or it is
            `None` and the working directory is not inside a git repository.
    """
    if root_arg is not None:
        if not root_arg.is_dir():
            raise ConfigError(f"--root {root_arg}: not a directory")
        return root_arg.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfigError(
            "--root was not given and the working directory is not a git repository"
        ) from exc
    return Path(result.stdout.strip()).resolve()


def _run_survey(args: argparse.Namespace) -> int:
    """Handle `trueup survey`.

    Args:
        args: The parsed arguments, holding `root`.

    Returns:
        0 on success.
    """
    import json

    from trueup import hygiene, survey as survey_mod

    root = _resolve_root(args.root)
    survey = hygiene.drop_managed_data_files(survey_mod.run(root))
    data = survey_mod.as_dict(survey)
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def _run_check(args: argparse.Namespace) -> int:
    """Handle `trueup check`.

    Args:
        args: The parsed arguments, holding `root`, `json`, `out`,
            `sarif`, `changed` and `baseline`.

    Returns:
        With neither `--changed` nor `--baseline`: 0 when the plan is
        empty, 1 when it is not. With `--baseline`: `report.check`'s own
        exit code (arch: D6.7). 2 when `--changed` is given with
        `--baseline` or `--out` (arch: D5.11, D6.17).
    """
    from trueup import report as report_mod

    if args.changed and args.baseline:
        print(
            "trueup: --changed and --baseline cannot be used together",
            file=sys.stderr,
        )
        return 2
    if args.changed and args.out is not None:
        print("trueup: --changed and --out cannot be used together", file=sys.stderr)
        return 2
    root = _resolve_root(args.root)
    if args.changed:
        return report_mod.check_changed(root, as_json=args.json, sarif=args.sarif)
    return report_mod.check(
        root,
        as_json=args.json,
        out=args.out,
        baseline=args.baseline,
        sarif=args.sarif,
    )


def _run_baseline(args: argparse.Namespace) -> int:
    """Handle `trueup baseline`.

    Args:
        args: The parsed arguments, holding `root`.

    Returns:
        0 always: `baseline.write` raises on a bad `trueup.toml`, which
        `main` turns into exit 2 (arch: D6.6).
    """
    from trueup import baseline as baseline_mod

    root = _resolve_root(args.root)
    num_keys, score_total = baseline_mod.write(root)
    print(f"baseline: {num_keys} keys, score {score_total}")
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    """Handle `trueup apply`.

    Args:
        args: The parsed arguments, holding `root`, `ids`, `all_auto`,
            `plan`, `allow_dirty`, `from_report`, `mode` and `set_`.

    Returns:
        0 on success, 1 when a handler failed, 2 when an argument is bad or
        an id is unknown, not in the plan, or not automatic (arch: D5.11,
        D5.6), or when `--plan` names a bad or stale file (arch: D12.1),
        or `--from-report` names a report with no tree comment or a stale
        one (arch: D12.3).
    """
    from trueup import apply as apply_mod

    root = _resolve_root(args.root)
    ids = args.ids.split(",") if args.ids else None
    return apply_mod.run(
        root,
        ids=ids,
        all_auto=args.all_auto,
        mode_args=args.mode,
        set_args=args.set_,
        plan=args.plan,
        allow_dirty=args.allow_dirty,
        from_report=args.from_report,
    )


def _run_lint(args: argparse.Namespace) -> int:
    """Handle `trueup lint` (arch: D14.6, D14.7, D15.4).

    Args:
        args: The parsed arguments, holding `root`, `changed`, `install`,
            `skip_missing` and `paths`.

    Returns:
        `trueup.lint.run`'s own exit code: 0 each tool passed, 1 one
        failed, 2 a bad command line or config or a missing tool; with
        `--install`, the first non-zero exit code of the installs.
    """
    from trueup import lint as lint_mod

    root = _resolve_root(args.root)
    return lint_mod.run(
        root,
        args.paths,
        changed=args.changed,
        install=args.install,
        skip_missing=args.skip_missing,
    )


def _run_template(args: argparse.Namespace) -> int:
    """Handle `trueup template <name>` (arch: D14.9, D14.22).

    Args:
        args: The parsed arguments, holding `name`.

    Returns:
        0 after the text is on stdout. 2 when no name is given or the name
        is not known; the names go to stderr.
    """
    from trueup import managed

    if args.name not in managed.TEMPLATE_NAMES:
        given = (
            "no template name"
            if args.name is None
            else f"unknown template {args.name!r}"
        )
        print(
            f"trueup template: {given}; the names are: "
            + ", ".join(managed.TEMPLATE_NAMES),
            file=sys.stderr,
        )
        return 2
    sys.stdout.write(managed.template_text(args.name))
    return 0


def _run_hook(args: argparse.Namespace) -> int:
    """Handle `trueup hook session|guard|stop|interface`.

    argparse exits 2 before this handler runs when the event name is not
    one of `HOOK_EVENTS` (LOW-5).

    Args:
        args: The parsed arguments, holding `event`.

    Returns:
        0 always for a known event: the hooks fail open (arch: D5.11, I-22).
    """
    from trueup import hooks as hooks_mod

    return hooks_mod.run(args.event, stdin=sys.stdin)


def _run_refs(argv: list[str]) -> int:
    """Handle `trueup refs`: forward every token after the subcommand, unparsed.

    `main` reads `argv[0] == "refs"` itself and calls this before
    `_build_parser().parse_args` ever runs, so no token here passes through
    argparse (arch: D5.11). With no `--root`, `--root=...`, `-h` or
    `--help` token, this adds `--root <git top level>` at the front, the
    same default every other subcommand uses.

    In global mode, with no `--config` token, this renders the checker
    config of the effective config into a temporary directory outside the
    root and adds `--config <that file>`, so the hook reads the same
    config as `check` (arch: D14.5). In copy mode, or when the root has no
    config, the checker reads `<root>/ref_check.toml` as before.

    Args:
        argv: The tokens after `refs`.

    Returns:
        `trueup.ref_check.main`'s own exit code: 0 no failure, 1 one
        failure or more, 2 a bad command line or `ref_check.toml`.

    Raises:
        ConfigError: No `--root` token is given and the working directory
            is not a git repository, or the config of the root does not
            load.
    """
    import tempfile

    from trueup import ref_check

    names_root_or_help = any(
        token == "--root" or token.startswith("--root=") or token in ("-h", "--help")  # noqa: S105  # reason: token is an argv string, not a credential
        for token in argv
    )
    if not names_root_or_help:
        argv = ["--root", str(_resolve_root(None)), *argv]
    text = _refs_config_text(argv)
    if text is None:
        return ref_check.main(argv)
    with tempfile.TemporaryDirectory(prefix="trueup-refs-") as scratch:
        config_path = Path(scratch) / "ref_check.toml"
        config_path.write_text(text, encoding="utf-8")
        return ref_check.main([*argv, "--config", str(config_path)])


def _refs_config_text(argv: list[str]) -> str | None:
    """Give the checker config that `trueup refs` passes in global mode (arch: D14.5).

    Args:
        argv: The tokens after `refs`, with a `--root` token.

    Returns:
        `None` when a token is `--config`, `-h` or `--help`, when the
        `--root` value is not a directory, when the target is not adopted
        (`config.load_layers(root).adopted`, arch: D15.6), or when the
        config is in copy mode, or when the root is not in a git work tree
        (arch: D15.2): the checker then runs as the
        person asked. Else the text of `managed.render_ref_check_config`
        with the `[keep]` table, or an empty text when
        `managed.refcheck_switches_on` is false, the same gate `check`
        uses (`docrules._refcheck_config_text`).
    """
    from trueup import config as config_mod
    from trueup import managed
    from trueup import survey as survey_mod

    root: Path | None = None
    for index, token in enumerate(argv):
        if (
            token == "--config"  # noqa: S105  # reason: token is an argv string, not a credential
            or token.startswith("--config=")
            or token in ("-h", "--help")
        ):
            return None
        if token == "--root" and index + 1 < len(argv):  # noqa: S105  # reason: token is an argv string, not a credential
            root = Path(argv[index + 1])
        elif token.startswith("--root="):
            root = Path(token.removeprefix("--root="))
    if root is None or not root.is_dir():
        return None
    root = root.resolve()
    layers = config_mod.load_layers(root)
    cfg = layers.effective
    if not layers.adopted or cfg.refs_mode == "copy":
        return None
    # D15.2: the checker is git-free, so a plain directory skips the survey.
    if not survey_mod.in_work_tree(root):
        return None
    survey = survey_mod.run(root)
    if not managed.refcheck_switches_on(cfg, survey):
        return ""
    return managed.render_ref_check_config(cfg, survey, keep=True)
