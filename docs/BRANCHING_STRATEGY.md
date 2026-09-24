# Branching strategy

This document describes how a change travels from an idea to a released version
in the Warrigal Park FC Member Registration & Team Roster System. It is the
reference the configuration-management report points to.

## 1. The model

A trimmed Git Flow model: one permanent branch, one integration branch per
release, and short-lived feature branches cut from that integration branch.

```
main        ──●────────────────●──────────────────●──────────────►  released versions
               ╲              ╱ ╲                ╱
                ╲            ╱   ╲              ╱
release/*        ●──●──●──●─●     (v1.1.0)     ●  integration + stabilisation
                  ╲    ╱   ╲                    ╱
feature/*          ●──●     ●──●               ●  one user story each
```

| Branch | Lives for | Purpose | Merged into |
| --- | --- | --- | --- |
| `main` | permanently | Every commit on `main` is a released, tested version. Never commit directly. | — |
| `release/<version>` | one release | Integration and stabilisation of the stories committed to that release. | `main` (via pull request) |
| `feature/<story-id>-<slug>` | one user story | All work on a single user story, including its tests. | `release/<version>` (via pull request) |
| `hotfix/<issue>` | until fixed | An urgent fix to a released version. | `main` and the open `release/*` |

### Naming rules

```
feature/US-004-guardian-entity
feature/US-007-guardian-validation
release/1.0.0
hotfix/guardian-sync-null-phone
```

The story identifier comes first so that a branch name and a row on the product
backlog always line up.

## 2. How a change travels

1. **Cut a feature branch** from the current `release/*` branch.
   ```bash
   git switch release/1.1.0
   git pull --ff-only
   git switch -c feature/US-007-guardian-validation
   ```

2. **Commit in small steps** using the convention in `docs/CONTRIBUTING.md`.
   A branch should tell the story of the change in its commit messages.

3. **Rebase rather than merge** while the branch is still private, so the
   integration history stays linear:
   ```bash
   git fetch origin
   git rebase origin/release/1.1.0
   ```

4. **Run the tests** before opening the pull request:
   ```bash
   python -m unittest discover -s tests -t . -v
   ```

5. **Open a pull request** into `release/<version>` and complete the checklist in
   `docs/CONTRIBUTING.md`. The build must be green and the Definition of Done
   (below) satisfied.

6. **Merge with `--no-ff`** so that the merge commit records the existence of the
   branch even after it is deleted:
   ```bash
   git switch release/1.1.0
   git merge --no-ff feature/US-007-guardian-validation
   git branch -d feature/US-007-guardian-validation
   ```

7. **Release**: merge `release/<version>` into `main`, tag it, and update the
   change log:
   ```bash
   git switch main
   git merge --no-ff release/1.1.0
   git tag -a v1.1.0 -m "Guardian entity and under-18 validation rule"
   git push origin main --tags
   ```

## 3. Definition of Done

A user story is done when all of the following hold. This is the list quoted in
the Project Charter (success criterion S4).

- [ ] The code is on a story-named branch, not on `main`.
- [ ] Commits use the conventional format and reference the story id.
- [ ] The pull request has been reviewed by a second person.
- [ ] Automated tests cover the story, including its refusal path.
- [ ] `python -m unittest discover -s tests -t .` passes on a clean checkout.
- [ ] No critical defect is open against the story.
- [ ] `CHANGELOG.md` and the relevant document in `docs/` describe the change.
- [ ] Configuration changes are in `config/env.example`, never in a `.env` file.

## 4. Configuration management

Configuration is treated as an artefact under version control in the same way as
source code, with one deliberate exception.

| Kind of setting | Example | Where it lives | Version controlled |
| --- | --- | --- | --- |
| Structural configuration | the list of routes, the theme colours, the database schema | in the source (`app.py`, `theme.py`, `models/schema.sql`) | **yes** |
| Environment configuration template | `APP_PORT`, `APP_DB_PATH` with safe defaults | `config/env.example` | **yes** |
| Environment configuration values | the real port and database path on a machine | `.env` | **no** — listed in `.gitignore` |
| Secrets | `APP_SECRET_KEY` in production | environment variable set by the host | **never** |

Rules that follow from the table:

1. Source code must run correctly with **no `.env` file at all**, using the
   defaults in `config.py`. A clean checkout must never fail for a missing
   configuration file.
2. A new setting is added to `config/env.example` with a safe default, to
   `config.py`'s `DEFAULTS` dictionary, and to the table in `README.md` in the
   same commit.
3. Changing a value in `config/env.example` is a change to the configuration
   baseline, so it is recorded in `CHANGELOG.md`.

### Database schema versioning

`models/database.py` holds the schema version and a `MIGRATIONS` dictionary
mapping a version to the SQL that upgrades *to* it. Upgrading is one-directional
and additive; a change is applied once and recorded in the `schema_version`
table.

| Version | Change |
| --- | --- |
| 1.0.0 | Initial schema: member, guardian, member_guardian, registration, team, team_member |
| 1.1.0 | `member.notes` added |
| 1.2.0 | `audit_log` table added |

## 5. Release history

| Tag | Date | Release branch | Contents |
| --- | --- | --- | --- |
| `v1.0.0` | 2026-09-24 | `release/1.0.0` | Project skeleton, member CRUD, database schema and migrations |
| `v1.1.0` | 2026-09-26 | `release/1.1.0` | Guardian entity, guardian linking and contact synchronisation |
| `v1.2.0` | 2026-09-27 | `release/1.2.0` | Season registration, the under-18 validation rule, status flow |
| `v1.3.0` | 2026-09-28 | `release/1.3.0` | Teams and rosters, reporting views, deployment configuration |

## 6. Why this model

- `main` is always in a releasable state, which is what the club needs when a
  volunteer has to run the system two weeks before sign-on day.
- Feature branches keep an unfinished story out of the integration branch, so a
  slip on one story never blocks the release of another.
- Story-named branches and `--no-ff` merges make the project's history readable
  six months later, when nobody remembers which change introduced a behaviour.
- Keeping secrets out of the repository is a compliance requirement, not a
  preference: the club holds personal information about children.
