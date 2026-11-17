# Security policy

## Reporting a vulnerability

Do not open a public issue for a security problem. Use one of these two
private channels:

- The "Report a vulnerability" button on the Security tab of
  <https://github.com/amsys/trueup>.
- An email to <dev@amsys.cz>.

Give these items in the report:

- The steps to reproduce the problem.
- What an attacker could do with it.
- The affected version (`trueup --version`) or commit.

You get a first reply in seven days or less.

## Supported versions

trueup is alpha software. Only the newest commit of the `main` branch
gets security fixes.

## What trueup runs and reads

- `check` reads the files of the target repository. It runs no code from
  the target.
- `lint` runs the linters that are installed on your machine, on the
  files of the target.
- `apply` changes only what you approve by id.
- `check` opens no network connection. Two things do, and only when you
  ask: `trueup lint --install` downloads linters with `npm` and `uv`, and
  the install guard of the plugin looks up package names on the public
  registries when `trueup.toml` sets `[guard] registry = true`. The
  default is `false`.
