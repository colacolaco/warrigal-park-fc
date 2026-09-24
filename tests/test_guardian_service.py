"""Tests for the Guardian capability."""

from __future__ import annotations

import unittest

from services import guardian_service as guardians
from services import member_service as members
from services.validation import BusinessRuleError, ValidationError
from tests.base import ServiceTestCase


class GuardianCrudTests(ServiceTestCase):
    def test_create_requires_a_contact_method(self) -> None:
        with self.assertRaises(ValidationError):
            guardians.create_guardian(
                self.db, {"first_name": "Ada", "last_name": "Osei"}
            )
        created = guardians.create_guardian(
            self.db,
            {"first_name": "Ada", "last_name": "Osei", "email": "ada.osei@example.com"},
        )
        self.assertEqual(created["contact"], "ada.osei@example.com")

    def test_relationship_must_be_known(self) -> None:
        with self.assertRaises(ValidationError):
            guardians.create_guardian(
                self.db,
                {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678",
                 "relationship": "godparent"},
            )
        for relationship in ("parent", "guardian", "carer", "other"):
            created = guardians.create_guardian(
                self.db,
                {"first_name": "Ada", "last_name": f"Osei-{relationship}",
                 "phone": "0412 345 678", "relationship": relationship},
            )
            self.assertEqual(created["relationship"], relationship)

    def test_guardian_can_be_linked_to_many_juniors(self) -> None:
        guardian = self.guardian_by_name("Nguyen", "Thao")
        children = guardians.list_juniors_for_guardian(self.db, guardian["id"])
        names = sorted(c["full_name"] for c in children)
        self.assertEqual(names, ["Ava Nguyen", "Liam Nguyen"])
        self.assertTrue(all(c["is_minor"] for c in children))

    def test_link_is_idempotent(self) -> None:
        member = self.member_by_last_name("Petrov", "Noah")
        guardian = self.guardian_by_name("Nguyen", "Thao")
        guardians.link_guardian(self.db, member["id"], guardian["id"])
        guardians.link_guardian(self.db, member["id"], guardian["id"])
        self.assertEqual(
            len(guardians.list_guardians_for_member(self.db, member["id"])), 2
        )

    def test_link_rejects_unknown_records(self) -> None:
        member = self.member_by_last_name("Petrov", "Noah")
        guardian = self.guardian_by_name("Nguyen", "Thao")
        with self.assertRaises(ValidationError):
            guardians.link_guardian(self.db, 99999, guardian["id"])
        with self.assertRaises(ValidationError):
            guardians.link_guardian(self.db, member["id"], 99999)

    def test_update_syncs_to_every_linked_child(self) -> None:
        guardian = self.guardian_by_name("Marsh", "Sandra")
        children_before = guardians.list_juniors_for_guardian(self.db, guardian["id"])
        self.assertEqual(len(children_before), 2)

        updated = guardians.update_guardian(
            self.db, guardian["id"], {"phone": "0455 123 456", "email": "new@example.com"}
        )
        self.assertEqual(updated["phone"], "0455 123 456")

        for child in children_before:
            linked = guardians.list_guardians_for_member(self.db, child["id"])
            primary = [g for g in linked if g["is_primary"]]
            self.assertTrue(primary, "the primary guardian link must survive an update")
            self.assertEqual(primary[0]["phone"], "0455 123 456")

            # The roster view reads the guardian's current contact, so the sync
            # is visible wherever the club actually looks at a junior's contact.
            from services import registration_service as registrations  # noqa: F401
            contacts = [g["contact"] for g in linked]
            self.assertIn("0455 123 456", contacts)

    def test_update_cannot_remove_the_last_contact_method(self) -> None:
        guardian = self.guardian_by_name("Nguyen", "Thao")
        with self.assertRaises(ValidationError):
            guardians.update_guardian(
                self.db, guardian["id"], {"phone": "", "email": ""}
            )

    def test_unlink_last_guardian_of_unregistered_junior_is_allowed(self) -> None:
        """The protection applies to registered juniors, not to every junior."""
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        guardian = guardians.create_guardian(
            self.db, {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"}
        )
        guardians.link_guardian(self.db, player["id"], guardian["id"])
        guardians.unlink_guardian(self.db, player["id"], guardian["id"])
        self.assertFalse(guardians.has_guardian(self.db, player["id"]))

    def test_primary_link_is_reported_first(self) -> None:
        member = self.member_by_last_name("Marsh", "Jayden")
        linked = guardians.list_guardians_for_member(self.db, member["id"])
        self.assertTrue(linked[0]["is_primary"])

    def test_search_guardians_by_name(self) -> None:
        self.assertEqual(len(guardians.find_guardians(self.db, "Marsh")), 2)
        self.assertEqual(guardians.find_guardians(self.db, "Nobody"), [])

    def test_has_guardian_reflects_the_link_table(self) -> None:
        member = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        guardian = guardians.create_guardian(
            self.db, {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"}
        )
        self.assertFalse(guardians.has_guardian(self.db, member["id"]))

        guardians.link_guardian(self.db, member["id"], guardian["id"])
        self.assertTrue(guardians.has_guardian(self.db, member["id"]))

        guardians.unlink_guardian(self.db, member["id"], guardian["id"])
        self.assertFalse(guardians.has_guardian(self.db, member["id"]))

    def test_unlink_rejects_unknown_member(self) -> None:
        with self.assertRaises(ValidationError):
            guardians.unlink_guardian(self.db, 99999, 1)

    def test_unlink_guardian_from_a_different_member_does_nothing(self) -> None:
        """Unlinking a guardian who is not linked must not raise or corrupt data."""
        member = self.member_by_last_name("Petrov", "Noah")
        guardian = self.guardian_by_name("Nguyen", "Thao")
        before = len(guardians.list_guardians_for_member(self.db, member["id"]))
        guardians.unlink_guardian(self.db, member["id"], guardian["id"])
        after = len(guardians.list_guardians_for_member(self.db, member["id"]))
        self.assertEqual(before, after)

    # -- helpers -----------------------------------------------------------
    def guardian_by_name(self, last_name: str, first_name: str) -> dict:
        matches = [
            g for g in guardians.find_guardians(self.db, last_name)
            if g["first_name"] == first_name
        ]
        self.assertTrue(matches, f"no seeded guardian named {first_name} {last_name}")
        return matches[0]


class GuardianDependencyTests(ServiceTestCase):
    def test_relinking_restores_a_removed_guardian(self) -> None:
        """Removing a link and adding it back must leave exactly one link.

        A player with no open registration is used so that the protection which
        stops the last guardian being removed from a registered junior does not
        apply — that protection has its own test in test_guardian_rule.py.
        """
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        guardian = guardians.create_guardian(
            self.db, {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"}
        )

        guardians.link_guardian(self.db, player["id"], guardian["id"], is_primary=True)
        self.assertEqual(len(guardians.list_guardians_for_member(self.db, player["id"])), 1)

        guardians.unlink_guardian(self.db, player["id"], guardian["id"])
        self.assertEqual(len(guardians.list_guardians_for_member(self.db, player["id"])), 0)

        guardians.link_guardian(self.db, player["id"], guardian["id"], is_primary=True)
        relinked = guardians.list_guardians_for_member(self.db, player["id"])
        self.assertEqual(len(relinked), 1)
        self.assertTrue(relinked[0]["is_primary"])

    def test_removing_the_last_guardian_of_a_registered_junior_is_refused(self) -> None:
        """The compliance protection, exercised through the same entry point."""
        member = self.member_by_last_name("Nguyen", "Ava")
        linked = guardians.list_guardians_for_member(self.db, member["id"])
        self.assertTrue(linked)
        with self.assertRaises(BusinessRuleError):
            guardians.unlink_guardian(self.db, member["id"], linked[0]["id"])
        self.assertTrue(guardians.has_guardian(self.db, member["id"]))


if __name__ == "__main__":
    unittest.main()
