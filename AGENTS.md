# Working on trueup

This file gives the working rules of this repository. A coding agent
reads it at the start of a session. The rules are the same for a person;
[CONTRIBUTING.md](CONTRIBUTING.md) has the setup steps.

## Find your way

- Start at the index of the documents, [docs/README.md](docs/README.md).
- [How trueup works](docs/explanation/how-trueup-works.md) maps the code
  by subject: read it before you change a module.
- [The trueup reference](docs/reference/trueup.md) lists every command,
  flag, exit code, configuration key and finding.
- [The architecture](docs/ARCHITECTURE.md) is the design record. The
  tests cite its section ids, such as `D5.4`.
- The package is `trueup/`. It uses the Python standard library only.
  The tests are in `tests/`, the skill of the plugin is
  `skills/trueup/SKILL.md`, and the hooks of the plugin are in
  `hooks/hooks.json`.

## Rules for a change

- Make the smallest change that does the task. Do not refactor code that
  the task does not touch; open an issue for it.
- Add or update a test with each change of behaviour. Never weaken, skip
  or delete a test to make it pass. If a test is wrong, say so.
- When you change a command, a flag, an exit code, a configuration key or
  a finding, update the reference page and the skill in the same change.
- Write a commit message as a conventional commit, for example
  `fix(drift): read a URL that ends in the package name`.
- Commit and push only when the person you work for asks.

## Rules for text

- Documents and comments use Simplified Technical English: short
  sentences, active voice, one topic for each paragraph.
- No word from [the banned-word list](trueup/data/banned.txt) appears in
  prose or in a comment.
- A page under `docs/` obeys
  [the document standard](docs/reference/document-standard.md), and the
  index links to it.
- Code comments obey
  [the comment standard](docs/reference/comment-standard.md). A source
  file starts with a header comment that gives its purpose, with no
  author and no date. A suppression names the rule code and gives a
  reason.

## Check your work

Run these from the root of the repository before you say that a change is
done:

```sh
python3 trueup check --root .
python3 trueup lint --root .
python3 trueup refs --root .
pytest tests/test_cli.py
```

`check` must end with "The plan is empty". `lint` needs `ruff` and `vale`
on the path. Run the test files of the modules that you changed; the full
suite (`pytest -q`) takes about 3 minutes and also runs in CI on each
push. Read the output of each command. An exit code alone is not proof.
