# Warrigal Park FC — Member Registration & Team Roster System

A small web application for a community football club. It replaces the club's
43-column Excel master spreadsheet and the duplicate second data-entry pass that
the volunteer registrar currently performs twice a year.

ISYS3001 Managing Software Development — Assessment 2 (individual).
GitHub account: **colacolaco**

---

## 1. What the application does

Five capabilities, exactly as scoped in the Project Charter:

| Capability | What it does |
| --- | --- |
| **Member** | Create, find, update and deactivate player records. Stores name, date of birth, contact details and gender. Search by name (including same-name matches). Data is persisted. |
| **Guardian** | Create, find and update guardian records. One guardian can be linked to many junior players. Updating a guardian's contact details automatically syncs to every linked child. |
| **Registration** | Register a player for a season with status `started` / `complete` / `withdrawn`. A player **under 18 cannot complete registration without a linked guardian** — the registration is refused with a reason. A player aged 18+ registers in their own right. |
| **Team & Roster** | Create a team for a season (name + age group). Place registered players into a team, move them between teams, remove them. List a team's full roster. |
| **Views** | Team roster with a contact for each player; a member's registration history; the juniors linked to a given guardian. |

The key business rule (a junior registration must have a guardian) is enforced in
`services/registration_service.py` and has its own automated test suite in
`tests/test_guardian_rule.py`.

## 2. Quick start (three commands)

```bash
git clone <repository-url>
cd warrigal-park-fc
python run.py
```

Then open <http://127.0.0.1:5000> in a browser.

**There is nothing to install.** The application is built entirely on the Python
standard library (`http.server`, `sqlite3`, `json`), so a clean checkout runs on
any machine with Python 3.9 or newer. The database is created automatically on
first run and seeded with fictitious sample data.

Run the automated test suite with:

```bash
python -m unittest discover -s tests -t . -v
```

## 3. Running in a different environment

Configuration is externalised so the same code runs in development, test and
production without editing source files.

| Setting | Environment variable | Default |
| --- | --- | --- |
| Environment name | `APP_ENV` | `development` |
| Host to bind | `APP_HOST` | `127.0.0.1` |
| Port to bind | `APP_PORT` | `5000` |
| SQLite database file | `APP_DB_PATH` | `data/warrigal_park.db` |
| Database URL (optional override) | `DATABASE_URL` | (none) |
| Seed sample data on start | `APP_SEED` | `true` |
| Debug logging | `APP_DEBUG` | `false` |

Copy the template and edit it for your machine:

```bash
cp config/env.example .env
```

Values in `.env` are loaded automatically at start-up. `.env` is git-ignored, so
machine-specific settings never leak into the repository — only
`config/env.example` is version controlled.

## 4. Project structure

```
warrigal-park-fc/
|-- run.py                    # entry point
|-- wsgi.py                   # production entry point (gunicorn/waitress)
|-- app.py                    # HTTP routing and request handling (web layer)
|-- config.py                 # configuration loader (.env aware, multi-environment)
|-- services/                 # business logic - the only place domain rules live
|   |-- member_service.py
|   |-- guardian_service.py
|   |-- registration_service.py
|   `-- team_service.py
|-- models/                   # schema, persistence helpers, sample data
|   |-- database.py
|   |-- schema.sql
|   `-- seed_data.py
|-- static/                   # stylesheet and front-end assets
|-- tests/                    # automated tests (unittest)
|-- config/                   # environment configuration templates
|-- deploy/                   # deployment configuration and scripts
`-- docs/                     # branch strategy, change log, contribution guide
```

## 5. Documentation

| Document | Purpose |
| --- | --- |
| `docs/BRANCHING_STRATEGY.md` | The branching model and how a change travels from branch to release |
| `docs/CONTRIBUTING.md` | Commit message convention and pull-request checklist |
| `CHANGELOG.md` | Human-readable release history |
| `docs/DEPLOYMENT.md` | How the application is configured and deployed |

## 6. Privacy and compliance note

All data in `models/seed_data.py` is **fictitious**. No real children's details,
no student ID and no personal information appear anywhere in this repository, in
line with the Project Charter's compliance constraint.
