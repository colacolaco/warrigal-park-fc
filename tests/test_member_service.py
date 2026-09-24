"""Tests for the Member capability."""

from __future__ import annotations

import unittest

from services import guardian_service as guardians
from services import member_service as members
from services import registration_service as registrations
from services.validation import ValidationError
from tests.base import ServiceTestCase


class MemberCrudTests(ServiceTestCase):
    def test_create_read_update_deactivate(self) -> None:
        created = members.create_member(
            self.db,
            {
                "first_name": "  Imogen ",
                "last_name": "Reyes",
                "date_of_birth": "2013-04-02",
                "gender": "f",
                "phone": "0413 222 333",
                "email": "imogen.reyes@example.com",
            },
        )
        # Input is trimmed and normalised on the way in.
        self.assertEqual(created["first_name"], "Imogen")
        self.assertEqual(created["gender"], "F")
        self.assertTrue(created["is_active"])

        read_back = members.get_member(self.db, created["id"])
        self.assertEqual(read_back["full_name"], "Imogen Reyes")
        self.assertEqual(read_back["date_of_birth"], "2013-04-02")

        updated = members.update_member(
            self.db, created["id"], {"phone": "0499 000 111"}
        )
        self.assertEqual(updated["phone"], "0499 000 111")
        self.assertEqual(updated["last_name"], "Reyes", "unspecified fields are kept")

        deactivated = members.deactivate_member(
            self.db, created["id"], "moved to another club"
        )
        self.assertFalse(deactivated["is_active"])
        # Soft delete: the record survives and is still readable.
        self.assertIsNotNone(members.get_member(self.db, created["id"]))
        visible = members.find_members(self.db)
        self.assertNotIn(created["id"], [m["id"] for m in visible])
        everything = members.find_members(self.db, include_inactive=True)
        self.assertIn(created["id"], [m["id"] for m in everything])

        reactivated = members.reactivate_member(self.db, created["id"])
        self.assertTrue(reactivated["is_active"])

    def test_deactivate_is_recorded_in_the_audit_log(self) -> None:
        member = self.member_by_last_name("Petrov", "Noah")
        members.deactivate_member(self.db, member["id"], "knee injury, out for the season")
        rows = self.db.query(
            "SELECT action, detail FROM audit_log WHERE entity = 'member' "
            "AND entity_id = ? ORDER BY id",
            (member["id"],),
        )
        self.assertEqual(rows[0]["action"], "deactivate")
        self.assertIn("knee injury", rows[0]["detail"])

    def test_search_matches_first_or_last_name(self) -> None:
        by_last = members.find_members(self.db, "Marsh")
        by_first = members.find_members(self.db, "Marsh")
        self.assertEqual({m["id"] for m in by_last}, {m["id"] for m in by_first})
        self.assertEqual(len(by_last), 2, "both Jayden Marsh records are returned")
        self.assertEqual(len(members.find_members(self.db, "Nguyen")), 2)

    def test_same_name_players_are_distinguishable(self) -> None:
        """The same-name requirement: results carry date of birth and id."""
        matches = members.find_members(self.db, "Jayden Marsh")
        self.assertEqual(len(matches), 2)
        birth_dates = sorted(m["date_of_birth"] for m in matches)
        ids = sorted(m["id"] for m in matches)
        self.assertEqual(len(set(birth_dates)), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_search_with_no_match_returns_an_empty_list(self) -> None:
        self.assertEqual(members.find_members(self.db, "zzzz-not-a-player"), [])

    def test_validation_rejects_bad_input(self) -> None:
        bad_records = [
            {"first_name": "", "last_name": "Reyes", "date_of_birth": "2013-04-02"},
            {"first_name": "Imogen", "last_name": "  ", "date_of_birth": "2013-04-02"},
            {"first_name": "Imogen", "last_name": "Reyes", "date_of_birth": ""},
            {"first_name": "Imogen", "last_name": "Reyes", "date_of_birth": "not a date"},
            {"first_name": "Imogen", "last_name": "Reyes",
             "date_of_birth": "2099-01-01"},
            {"first_name": "Imogen", "last_name": "Reyes",
             "date_of_birth": "2013-04-02", "email": "not-an-email"},
            {"first_name": "Imogen", "last_name": "Reyes",
             "date_of_birth": "2013-04-02", "phone": "123"},
        ]
        for record in bad_records:
            with self.subTest(record=record), self.assertRaises(ValidationError):
                members.create_member(self.db, record)

    def test_age_group_is_suggested_from_the_date_of_birth(self) -> None:
        junior = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        self.assertTrue(junior["suggested_age_group"].startswith("U"))
        self.assertLess(junior["age"], 18)

        adult = members.create_member(
            self.db,
            {"first_name": "Riley", "last_name": "Tan", "date_of_birth": "1999-02-01"},
        )
        self.assertEqual(adult["suggested_age_group"], "Seniors")

    def test_updating_a_missing_member_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            members.update_member(self.db, 99999, {"first_name": "Nobody"})
        with self.assertRaises(ValidationError):
            members.deactivate_member(self.db, 99999)

    def test_member_count_excludes_inactive_members(self) -> None:
        before = members.member_count(self.db)
        member = self.member_by_last_name("Petrov", "Noah")
        members.deactivate_member(self.db, member["id"])
        self.assertEqual(members.member_count(self.db), before - 1)
        self.assertEqual(members.member_count(self.db, include_inactive=True), before)


class MemberRelationshipTests(ServiceTestCase):
    def test_deactivated_member_keeps_registration_history(self) -> None:
        """Soft delete exists so history survives; prove it does."""
        member = self.member_by_last_name("Nguyen", "Ava")
        history_before = registrations.registration_history(self.db, member["id"])
        members.deactivate_member(self.db, member["id"], "left the club")
        history_after = registrations.registration_history(self.db, member["id"])
        self.assertEqual(len(history_before), len(history_after))
        self.assertNotEqual(history_after, [])

    def test_inactive_member_cannot_be_given_a_new_guardian_link(self) -> None:
        from services.validation import BusinessRuleError

        member = self.member_by_last_name("Petrov", "Noah")
        guardian = guardians.find_guardians(self.db)[0]
        members.deactivate_member(self.db, member["id"])
        with self.assertRaises(BusinessRuleError):
            guardians.link_guardian(self.db, member["id"], guardian["id"])


if __name__ == "__main__":
    unittest.main()
