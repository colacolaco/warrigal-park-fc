"""Base test case: an in-memory database with the fictitious sample data."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.database import Database  # noqa: E402
from models.seed_data import seed  # noqa: E402
from services import member_service as members  # noqa: E402


class ServiceTestCase(unittest.TestCase):
    """Shared fixture: a fresh in-memory database for every test.

    Using ``:memory:`` means the tests never touch the development database and
    can run in parallel, and a clean checkout can run them with no setup.
    """

    seeded: bool = True

    def setUp(self) -> None:
        self.db = Database(":memory:").initialise()
        if self.seeded:
            seed(self.db)
        self.addCleanup(self.db.close)

    # -- helpers -----------------------------------------------------------
    def member_by_last_name(self, last_name: str, first_name: str | None = None) -> dict:
        matches = [
            m for m in members.find_members(self.db, last_name)
            if first_name is None or m["first_name"] == first_name
        ]
        self.assertTrue(matches, f"no seeded member named {first_name} {last_name}")
        return matches[0]

    def all_members(self) -> list[dict]:
        return members.find_members(self.db, include_inactive=True)
