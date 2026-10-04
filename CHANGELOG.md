# Change log

All notable changes to the Warrigal Park FC Member Registration & Team Roster
System are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The branch that produced each release is named in the heading, so a reader can
find the corresponding merge commit.

## [Unreleased]

### Fixed
- `static/styles.css`: the file opened with `#` comment lines, which are Markdown
  syntax rather than CSS. They were invalid tokens that caused the `:root` rule to
  be discarded, so every `var(--brand)`, `var(--accent)` and related custom
  property resolved to nothing. The visible effect was that the club header, the
  main navigation and every card had no background colour. The comments are now
  valid CSS comments, and the stylesheet contains no non-ASCII bytes.
- `app.py`: sixteen placeholder values were written as HTML entities (`&mdash;`)
  and then passed through the escaping helper, which escaped the ampersand so the
  page displayed the literal text. They are now the real characters. The same
  correction removes a literal `&middot;` from the team page subtitle.
- `README.md`: repaired non-ASCII characters (the em dashes and the directory-tree
  diagram) that a text-editor roundtrip had corrupted. The file was rewritten as
  UTF-8 and the damaged characters restored.

### Added
- `docs/DEPLOYMENT.md`: configuration and deployment guide.
- `scripts/run_tests_for_evidence.py`: writes a clean transcript of the test run
  to `docs/test-evidence.txt`, so the evidence is the program's own output rather
  than a screenshot of a shell.
- `docs/test-evidence.txt`: the transcript produced by that script.

## [1.3.0] - 2026-09-28 — release/1.3.0

### Added
- Team and roster capability: create a team for a season, place registered
  players into it, move players between teams within a season, remove players,
  and list a team's full roster (`services/team_service.py`).
- Business rule: a player can only be placed in a team when they hold a
  **completed** registration for that season.
- `team_roster()` reporting view, showing the linked guardian's contact for a
  junior and the player's own contact for an adult.
- `roster_contact_gaps()` quality check, listing players the coordinator cannot
  ring.
- Views page: team roster with contacts, the juniors linked to a guardian, and a
  member's registration history.
- Season summary by age group and gender, for the association nomination report.
- `deploy/` configuration: `Procfile`, `systemd` unit, Dockerfile, environment
  files for development, test and production.

### Changed
- `README.md` rewritten around the five capabilities, the quick start and the
  configuration table.

## [1.2.0] - 2026-09-27 — release/1.2.0

### Added
- Season registration with the status flow `started` → `complete` →
  `withdrawn` (`services/registration_service.py`).
- **The under-18 guardian rule**: completing a registration for a player under
  18 is refused unless at least one guardian record is linked. The refusal names
  the player, their age and the date the completion was attempted.
- `refusal_reason` column on `registration`, so a refusal is visible to the
  registrar rather than being silently discarded.
- Decision record D-004 implemented: age is judged on the date the registration
  is *completed*, not on the first day of the season.
- Test suite `tests/test_guardian_rule.py`, covering the refusal path, the
  success path, the adult path, the birthday boundary, and the attempt to bypass
  the rule through `amend_registration()`.
- `audit_log` table and schema migration 1.2.0.

### Changed
- `amend_registration()` routes a status change to `complete` back through
  `complete_registration()`, so the rule cannot be bypassed.

## [1.1.0] - 2026-09-26 — release/1.1.0

### Added
- Guardian capability: create, find and update guardian records
  (`services/guardian_service.py`).
- `member_guardian` link table: one guardian may be linked to many juniors, and
  a junior may have more than one guardian.
- Contact synchronisation: updating a guardian's phone or email is immediately
  visible on every linked child's record, because children reference the
  guardian record instead of copying its values.
- Business rule: the last guardian cannot be removed from a junior who holds an
  open registration for a season.
- `has_guardian()` helper, used by the registration rule.
- Guardian pages: register, detail, link and unlink.

### Changed
- A guardian must hold at least one contact method (phone or email).
- Schema migration 1.1.0 adds `member.notes`.

## [1.0.0] - 2026-09-24 — release/1.0.0

### Added
- Project skeleton and the standard-library-only web layer (`app.py`), so a
  clean checkout runs with no installation step.
- Configuration module with multi-environment support, `.env` loading and safe
  defaults (`config.py`, `config/env.example`).
- SQLite persistence with schema versioning and one-directional migrations
  (`models/database.py`, `models/schema.sql`).
- Member capability: create, find, update, deactivate and reactivate, with
  search by first or last name, and same-name players distinguished by date of
  birth and record id.
- Deactivation implemented as a soft delete, so registration history survives a
  player leaving the club.
- Fictitious sample roster (`models/seed_data.py`), including one junior with a
  started registration and no guardian, which demonstrates the under-18 rule on
  a fresh install.
- `.gitignore` covering the database, `.env` files, caches and editor files.
- `README.md`, `docs/BRANCHING_STRATEGY.md`, `docs/CONTRIBUTING.md`.

[Unreleased]: https://github.com/colacolaco/warrigal-park-fc/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/colacolaco/warrigal-park-fc/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/colacolaco/warrigal-park-fc/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/colacolaco/warrigal-park-fc/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/colacolaco/warrigal-park-fc/releases/tag/v1.0.0
