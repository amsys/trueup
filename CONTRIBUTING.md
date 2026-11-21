# Contributing

Thank you for looking at trueup.

## Before you start

- Read [how trueup works](docs/explanation/how-trueup-works.md) to see
  how the code is built, and [the brief](docs/BRIEF.md) for the goals and
  the decisions already taken. [The architecture](docs/ARCHITECTURE.md)
  is the record to look up one section by its id.
- Read [the comment standard](docs/reference/comment-standard.md) and
  [the document standard](docs/reference/document-standard.md): every file
  you touch, code or prose, follows one of them.
- Open an issue before a large change, so the design can be agreed first.

## Set up

```sh
git clone https://github.com/amsys/trueup
cd trueup
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest
```

The package has no dependency. The full test suite has about 2,000
tests and takes about 3 minutes; `pytest tests/test_cli.py` runs one
file. Do not run two suites at the same time on one machine: the
`golangci-lint` tests fail when a second run is active.

## Making a change

1. Create a branch for your change.
2. Keep the change to what you set out to do. Note anything else you spot
   as a separate issue instead of folding it in.
3. Add or update a test for the change. A rule that has no test to prove
   it is not done yet.
4. Run the checks from the root of the repository:

   ```sh
   python3 trueup check --root .
   python3 trueup lint --root .
   python3 trueup refs --root .
   pytest tests/test_cli.py
   ```

   `check` must end with "The plan is empty". `lint` needs `ruff` and
   `vale` on the path. Run the test files of the modules that you
   changed; the full suite (`pytest -q`) also runs in CI on each push.

   `trueup refs` runs the reference checker: it proves that each design
   id that a comment or a test cites exists, and that each link between
   documents resolves. Its command line and exit codes are in
   [the architecture](docs/ARCHITECTURE.md#d23--command-line-and-exit-codes "pin:08ee34e2").
   A test for a tool this machine does not have skips and names the tool;
   `pytest -rs` lists those.
5. Open a pull request that describes what changed and why.

## Code style

- The `trueup` package uses the Python standard library only. Its code
  uses `from __future__ import annotations`, `pathlib`, `subprocess` with
  argument lists (never `shell=True`), and gives deterministic, sorted
  output. The tests use `pytest`.
- Every source file starts with a header comment giving its purpose, with
  no author and no date. Every public module, class and function has a
  Google-style docstring.
- No word from the banned-word list
  ([`trueup/data/banned.txt`](trueup/data/banned.txt)) appears in prose, a
  comment or code — except inside that file itself, the Vale `Banned.yml`
  style, and a test fixture that must hold one on purpose.
- A comment states what the code does now. A comment that no longer
  matches the code it sits on is a defect.

## Reporting a bug

Open an issue with the steps to reproduce it, what you expected, and what
happened instead.
