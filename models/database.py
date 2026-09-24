"""Database access helpers.

Thin wrapper around :mod:`sqlite3`.  Keeping every SQL call behind this module
means the business services never build SQL themselves, which makes the domain
rules easy to unit test against an in-memory database.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from config import PROJECT_ROOT

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = "1.2.0"

MIGRATIONS: dict[str, str] = {
    # version -> SQL applied when upgrading *to* that version
    "1.1.0": "ALTER TABLE member ADD COLUMN notes TEXT;",
    "1.2.0": """
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            changed_at TEXT NOT NULL DEFAULT (datetime('now')),
            entity     TEXT NOT NULL,
            entity_id  INTEGER,
            action     TEXT NOT NULL,
            detail     TEXT
        );
    """,
}


class Database:
    """A tiny connection holder.

    ``sqlite3`` connections are not thread safe, so the web layer creates one
    :class:`Database` per request.  Tests create one per test case and point it
    at ``:memory:``.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- schema ------------------------------------------------------------
    def initialise(self) -> "Database":
        """Create the schema, then run any pending migrations."""
        self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) "
            "VALUES (?, ?)",
            ("1.0.0", "initial schema"),
        )
        self._apply_migrations()
        self._conn.commit()
        return self

    def current_version(self) -> str:
        row = self._conn.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC, version DESC "
            "LIMIT 1"
        ).fetchone()
        return row["version"] if row else "0.0.0"

    def _apply_migrations(self) -> None:
        applied = {
            row["version"]
            for row in self._conn.execute("SELECT version FROM schema_version")
        }
        for version in sorted(MIGRATIONS):
            if version in applied:
                continue
            self._conn.executescript(MIGRATIONS[version])
            self._conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, f"migration to {version}"),
            )

    # -- queries -----------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params))

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Group several statements so a partial update can never be committed."""
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def audit(self, entity: str, entity_id: int | None, action: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit_log (entity, entity_id, action, detail) VALUES (?, ?, ?, ?)",
            (entity, entity_id, action, detail),
        )


def default_database_path() -> Path:
    """Fallback path used by scripts that do not load the settings object."""
    return PROJECT_ROOT / "data" / "warrigal_park.db"
