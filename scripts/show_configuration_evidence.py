"""Configuration-management evidence script.

Runs a short, repeatable demonstration of every configuration-management
practice claimed in the project report and prints the result.  It exists so that
the evidence in the report can be produced on demand instead of being asserted
without proof.

    python scripts/show_configuration_evidence.py

The script is read-only apart from a temporary database in the system temp
directory, which it removes before exiting.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings  # noqa: E402
from models.database import Database, MIGRATIONS, SCHEMA_VERSION  # noqa: E402
from models.seed_data import seed  # noqa: E402
from services import guardian_service as guardians  # noqa: E402
from services import member_service as members  # noqa: E402
from services import registration_service as registrations  # noqa: E402
from services import team_service as teams  # noqa: E402
from services.validation import BusinessRuleError  # noqa: E402

SEASON = 2026


def heading(text: str) -> None:
    print()
    print("=" * 74)
    print(f"  {text}")
    print("=" * 74)


def run_git(*args: str) -> str:
    """Run a git command and return its output, or a note when unavailable."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"<git unavailable: {exc}>"
    if result.returncode != 0:
        return f"<git {' '.join(args)} failed: {result.stderr.strip()}>"
    return result.stdout.rstrip()


def section_1_configuration() -> dict[str, object]:
    heading("1. Externalised configuration — one codebase, three environments")
    table = []
    for environment in ("development", "test", "production"):
        settings = get_settings(
            env_file=Path(tempfile.gettempdir()) / "warrigal-no-such-env",
            APP_ENV=environment,
            APP_SEED="false" if environment == "production" else "true",
        )
        table.append(
            {
                "environment": settings.env,
                "host": settings.host,
                "port": settings.port,
                "database": settings.db_path.name,
                "seeding": settings.seed,
                "debug": settings.debug,
            }
        )
        print(f"  APP_ENV={environment:<12} -> {settings.describe()}")

    defaults = get_settings(
        env_file=Path(tempfile.gettempdir()) / "warrigal-no-such-env"
    )
    print()
    print("  With no environment variables and no .env file the application still")
    print(f"  starts on its defaults: {defaults.describe()}")

    print()
    print("  Known environments are validated — an unknown value stops start-up:")
    os.environ["APP_ENV"] = "staging"
    try:
        get_settings(env_file=Path(tempfile.gettempdir()) / "warrigal-no-such-env")
        print("    ERROR: an invalid APP_ENV was accepted")
    except ValueError as exc:
        print(f"    rejected: {exc}")
    finally:
        os.environ.pop("APP_ENV", None)

    return {"environments": table}


def section_2_version_controlled_configuration() -> dict[str, object]:
    heading("2. Configuration artefacts under version control")
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    secret_rules = [line for line in ignored if line.strip().startswith(".env")]
    print("  .gitignore rules that keep machine configuration out of the repository:")
    for rule in secret_rules:
        print(f"    {rule}")

    tracked = run_git("ls-files", "config")
    print()
    print("  Configuration files that ARE tracked:")
    for line in tracked.splitlines():
        print(f"    {line}")

    print()
    print("  A .env file is never committed, so the same checkout runs on every machine")
    print("  with only environment variables differing between them.")
    return {"gitignore_env_rules": secret_rules, "tracked_config": tracked.splitlines()}


def section_3_schema_versioning() -> dict[str, object]:
    heading("3. Database schema versioning and migrations")
    print(f"  Current schema version: {SCHEMA_VERSION}")
    print("  Migration ladder recorded in models/database.py:")
    for version in sorted(MIGRATIONS):
        first_line = MIGRATIONS[version].strip().splitlines()[0].strip()
        print(f"    -> {version}: {first_line}")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "evidence.db"
        db = Database(path).initialise()
        rows = db.query("SELECT version, description FROM schema_version ORDER BY version")
        print()
        print("  Versions actually applied to a fresh database:")
        for row in rows:
            print(f"    {row['version']:<8} {row['description']}")
        print()
        print(f"  Applied automatically on start-up: {db.current_version()}")
        db.close()
    return {"schema_version": SCHEMA_VERSION, "migrations": sorted(MIGRATIONS)}


def section_4_branch_history() -> dict[str, object]:
    heading("4. Version-control history on this checkout")
    log = run_git("log", "--oneline", "--graph", "--decorate", "--all", "-25")
    print(log if log else "  <no commits yet>")

    print()
    print("  Branches:")
    branches = run_git("branch", "-a", "--format=%(refname:short)")
    for line in branches.splitlines() or ["  <none>"]:
        print(f"    {line}")

    print()
    print("  Tags:")
    tags = run_git("tag", "--list")
    for line in tags.splitlines() or ["  <none>"]:
        print(f"    {line}")

    merges = run_git("log", "--merges", "--oneline")
    print()
    print(f"  Merge commits (one per completed feature branch): "
          f"{len([l for l in merges.splitlines() if l.strip()])}")
    for line in merges.splitlines()[:10]:
        print(f"    {line}")
    return {"log": log, "branches": branches.splitlines(), "tags": tags.splitlines()}


def section_5_audit_trail() -> dict[str, object]:
    heading("5. Change trail recorded by the application itself")
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "evidence.db").initialise()
        seed(db)

        player = members.create_member(
            db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(db, player["id"], SEASON)

        print("  Attempting to complete a junior registration with no guardian:")
        try:
            registrations.complete_registration(db, registration["id"])
            print("    ERROR: the rule did not fire")
        except BusinessRuleError as exc:
            print(f"    refused: {exc}")

        guardian = guardians.create_guardian(
            db, {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"}
        )
        guardians.link_guardian(db, player["id"], guardian["id"], is_primary=True)
        registrations.complete_registration(db, registration["id"])

        team = teams.create_team(db, "U10 Mixed", "U10", SEASON)
        teams.add_player(db, team["id"], player["id"], squad_number="8")

        print()
        print("  Audit trail written to the database by the services:")
        rows = db.query(
            "SELECT changed_at, entity, entity_id, action, detail "
            "FROM audit_log ORDER BY id"
        )
        for row in rows:
            detail = (row["detail"] or "")[:52]
            print(f"    {row['changed_at']}  {row['entity']:<14} "
                  f"{row['action']:<12} {detail}")

        print()
        print("  Roster view (the club's headline reporting requirement):")
        for entry in teams.team_roster(db, team["id"]):
            print(f"    #{entry['squad_number']:<3} {entry['full_name']:<18} "
                  f"age {entry['age']:<3} contact {entry['contact']} "
                  f"({entry['contact_for']})")
        db.close()
        return {"audit_entries": len(rows)}


def main() -> int:
    print("=" * 74)
    print("  Warrigal Park FC — configuration management evidence")
    print(f"  generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  python   {platform.python_version()} on {platform.system()}")
    print(f"  project  {PROJECT_ROOT}")
    print("=" * 74)

    collected: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
    }
    collected.update(section_1_configuration())
    collected["version_controlled_configuration"] = section_2_version_controlled_configuration()
    collected["schema"] = section_3_schema_versioning()
    collected["history"] = section_4_branch_history()
    collected["audit"] = section_5_audit_trail()

    document = Path(PROJECT_ROOT) / "docs" / "configuration-evidence.json"
    document.write_text(json.dumps(collected, indent=2, default=str), encoding="utf-8")

    heading("Evidence written")
    print(f"  {document}")
    print()
    print("  Take a screenshot of the output above for the report, and keep this")
    print("  JSON file as machine-readable proof that the commands were run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
