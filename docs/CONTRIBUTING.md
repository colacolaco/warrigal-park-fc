# Contributing

## 1. Before you start

```bash
git clone <repository-url>
cd warrigal-park-fc
python -m unittest discover -s tests -t . -v
```

There is nothing to install. If the tests pass, your environment matches the
project's baseline.

## 2. Work on a branch

Never commit to `main`. Cut a story-named branch from the current release branch:

```bash
git switch release/1.3.0
git switch -c feature/US-009-roster-contact-gap
```

## 3. Commit message convention

```
<type>(<scope>): <short imperative summary>

<body: why the change was made, not what the diff shows>

<footer: references>
```

| Type | Use for |
| --- | --- |
| `feat` | a new capability or user story |
| `fix` | a defect fix |
| `test` | tests only |
| `docs` | documentation only |
| `refactor` | a change that neither adds a feature nor fixes a defect |
| `config` | configuration, deployment or tooling change |
| `chore` | housekeeping that does not touch application behaviour |

Allowed scopes: `member`, `guardian`, `registration`, `team`, `views`, `db`,
`config`, `deploy`, `tests`.

Examples from this repository:

```
feat(registration): refuse completion for a junior with no guardian

A registration for a player under 18 is refused unless at least one
guardian record is linked. The refusal reason names the player, their age
and the date the completion was attempted so the registrar can act on it.

Refs: US-007
```

```
fix(guardian): keep at least one contact method on a guardian

A guardian could be saved with an empty phone and an empty email, which
made the roster contact column blank for every linked junior.
```

```
config(deploy): read the port from the environment

The port was hard coded, so the university demonstration host could not
choose a free port.
```

Rules:

- Imperative mood in the subject line ("add", not "added").
- Subject line at most 72 characters, no trailing full stop.
- One logical change per commit. If the subject line needs "and", it is two
  commits.
- Never commit a real `.env`, a database file, or any personal information about
  a child.

## 4. Tests

Every behavioural change arrives with tests.

```bash
python -m unittest discover -s tests -t . -v          # everything
python -m unittest tests.test_guardian_rule -v        # one suite
python -m unittest tests.test_guardian_rule.GuardianRuleTests.test_junior_without_guardian_is_refused_with_a_reason -v
```

Test expectations for this project:

- The under-18 guardian rule has a test for its **refusal** path, not only its
  success path. A rule that is only tested when it passes is not tested.
- Tests use an in-memory database, so no test may depend on a file left behind by
  another test.
- Tests must not depend on the order they run in.

## 5. Pull request checklist

- [ ] The branch name matches the story id it implements.
- [ ] The full test suite passes on a clean checkout.
- [ ] New behaviour has tests; changed behaviour has updated tests.
- [ ] `README.md` is updated if a command, setting or route changed.
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]`.
- [ ] `config/env.example` documents any new setting, with a safe default.
- [ ] No `.env` file, secret, database file or personal data is included.
- [ ] Screenshots or a note are attached if the user interface changed.

## 6. Reviewing

A review answers three questions:

1. Does the change do what the story says, including when the input is wrong?
2. Can it be understood and maintained in six months by someone who was not
   involved?
3. Does it follow the rules above?

Comment on the code, not the person. If a review comment will take more than a
few minutes to address, open a follow-up issue rather than holding the pull
request open.

## 7. Reporting a problem

Open an issue with:

- what you did,
- what you expected,
- what happened instead,
- the exact command you ran and the full output.

Never paste real member data into an issue. Replace names with fictitious ones.
