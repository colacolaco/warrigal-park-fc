"""Automated tests for the club's core business rule.

Rule: a player under 18 cannot complete a registration unless at least one
guardian record is linked; otherwise the registration is refused with a reason.

This suite is the mitigation for project risk R1 (guardian business rule
implemented incorrectly) recorded in the Project Charter.
"""

from __future__ import annotations

import unittest
from datetime import date

from services import guardian_service as guardians
from services import member_service as members
from services import registration_service as registrations
from services.validation import BusinessRuleError, ValidationError
from tests.base import ServiceTestCase

SEASON = 2026


class GuardianRuleTests(ServiceTestCase):
    """The rule itself."""

    def test_junior_without_guardian_is_refused_with_a_reason(self) -> None:
        """A junior with no linked guardian cannot be completed."""
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)

        with self.assertRaises(BusinessRuleError) as caught:
            registrations.complete_registration(
                self.db, registration["id"], on=date(2026, 2, 7)
            )

        message = str(caught.exception)
        self.assertIn("under 18", message)
        self.assertIn("no linked guardian", message)
        self.assertIn("Talia Osei", message)
        # The reason must be actionable: it names the age and the completion date.
        self.assertIn("age 9", message)
        self.assertIn("2026-02-07", message)

    def test_refused_registration_is_left_started_and_records_the_reason(self) -> None:
        """A refusal must not silently lose the registrar's work."""
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)

        with self.assertRaises(BusinessRuleError):
            registrations.complete_registration(
                self.db, registration["id"], on=date(2026, 2, 7)
            )

        stored = registrations.get_registration(self.db, registration["id"])
        self.assertEqual(stored["status"], "started")
        self.assertIn("under 18", stored["refusal_reason"])

        audit = self.db.query(
            "SELECT action FROM audit_log WHERE entity = 'registration' "
            "AND entity_id = ? ORDER BY id",
            (registration["id"],),
        )
        self.assertEqual([row["action"] for row in audit], ["start", "refuse"])

    def test_junior_with_a_guardian_completes(self) -> None:
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)
        guardian = guardians.create_guardian(
            self.db,
            {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"},
        )
        guardians.link_guardian(self.db, player["id"], guardian["id"], is_primary=True)

        completed = registrations.complete_registration(
            self.db, registration["id"], on=date(2026, 2, 7)
        )
        self.assertEqual(completed["status"], "complete")
        self.assertIsNone(completed["refusal_reason"])

    def test_adult_registers_without_a_guardian(self) -> None:
        """A player aged 18 or over registers in their own right."""
        player = members.create_member(
            self.db,
            {"first_name": "Riley", "last_name": "Tan", "date_of_birth": "2007-02-01"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)
        completed = registrations.complete_registration(
            self.db, registration["id"], on=date(2026, 2, 7)
        )
        self.assertEqual(completed["status"], "complete")

    def test_age_is_judged_on_the_completion_date(self) -> None:
        """A player who turns 18 the day before completing needs no guardian.

        This is decision record D-004: age is judged on the date the
        registration is completed, not on the first day of the season.
        """
        player = members.create_member(
            self.db,
            {"first_name": "Jordan", "last_name": "Fell",
             "date_of_birth": "2008-02-08"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)

        # One day short of the eighteenth birthday: still a minor, still refused.
        with self.assertRaises(BusinessRuleError):
            registrations.complete_registration(
                self.db, registration["id"], on=date(2026, 2, 7)
            )

        # On the eighteenth birthday the rule no longer applies.
        completed = registrations.complete_registration(
            self.db, registration["id"], on=date(2026, 2, 8)
        )
        self.assertEqual(completed["status"], "complete")

    def test_amend_to_complete_cannot_bypass_the_rule(self) -> None:
        """Changing the status through amend must still enforce the rule."""
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)

        with self.assertRaises(BusinessRuleError):
            registrations.amend_registration(
                self.db, registration["id"], status="complete"
            )
        self.assertEqual(
            registrations.get_registration(self.db, registration["id"])["status"],
            "started",
        )

    def test_one_guardian_can_serve_several_juniors(self) -> None:
        """A single guardian linked to siblings satisfies the rule for both."""
        first = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        second = members.create_member(
            self.db,
            {"first_name": "Kofi", "last_name": "Osei", "date_of_birth": "2018-01-19"},
        )
        guardian = guardians.create_guardian(
            self.db,
            {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"},
        )
        guardians.link_guardian(self.db, first["id"], guardian["id"])
        guardians.link_guardian(self.db, second["id"], guardian["id"])

        for player in (first, second):
            registration = registrations.start_registration(self.db, player["id"], SEASON)
            completed = registrations.complete_registration(self.db, registration["id"])
            self.assertEqual(completed["status"], "complete")

        self.assertEqual(guardian["id"], guardians.get_guardian(self.db, guardian["id"])["id"])
        self.assertEqual(
            len(guardians.list_juniors_for_guardian(self.db, guardian["id"])), 2
        )

    def test_updating_a_guardian_updates_every_linked_child(self) -> None:
        """The sync requirement: one edit, all children's contacts change."""
        first = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        second = members.create_member(
            self.db,
            {"first_name": "Kofi", "last_name": "Osei", "date_of_birth": "2018-01-19"},
        )
        guardian = guardians.create_guardian(
            self.db,
            {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"},
        )
        guardians.link_guardian(self.db, first["id"], guardian["id"])
        guardians.link_guardian(self.db, second["id"], guardian["id"])

        guardians.update_guardian(
            self.db, guardian["id"], {"phone": "0499 888 777"}
        )

        for player in (first, second):
            linked = guardians.list_guardians_for_member(self.db, player["id"])
            self.assertEqual(linked[0]["phone"], "0499 888 777")
        self.assertEqual(
            len(guardians.list_juniors_for_guardian(self.db, guardian["id"])), 2
        )

    def test_last_guardian_cannot_be_removed_from_a_registered_junior(self) -> None:
        player = self.member_by_last_name("Marsh", "Jayden")
        linked = guardians.list_guardians_for_member(self.db, player["id"])
        # Remove every guardian but one, then attempt to remove the last one.
        for guardian in linked[:-1]:
            guardians.unlink_guardian(self.db, player["id"], guardian["id"])

        with self.assertRaises(BusinessRuleError):
            guardians.unlink_guardian(self.db, player["id"], linked[-1]["id"])
        self.assertTrue(guardians.has_guardian(self.db, player["id"]))

    def test_seeded_walk_in_case_is_blocked(self) -> None:
        """The seeded Tyler Brennan case demonstrates the rule on a fresh install."""
        started = registrations.find_registrations(
            self.db, season=SEASON, status="started"
        )
        self.assertTrue(started, "the sample data should contain a walk-in case")
        walk_in = started[0]
        self.assertFalse(guardians.has_guardian(self.db, walk_in["member_id"]))
        with self.assertRaises(BusinessRuleError):
            registrations.complete_registration(self.db, walk_in["id"])


class RegistrationLifecycleTests(ServiceTestCase):
    """Status flow and validation around the rule."""

    def test_status_flow_started_complete_withdrawn(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        registration = registrations.start_registration(self.db, player["id"], 2027)
        self.assertEqual(registration["status"], "started")

        completed = registrations.complete_registration(self.db, registration["id"])
        self.assertEqual(completed["status"], "complete")

        withdrawn = registrations.withdraw_registration(
            self.db, registration["id"], "family moved interstate"
        )
        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertEqual(withdrawn["refusal_reason"], "family moved interstate")

    def test_a_member_cannot_register_twice_in_one_season(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        registrations.start_registration(self.db, player["id"], 2027)
        with self.assertRaises(BusinessRuleError):
            registrations.start_registration(self.db, player["id"], 2027)

    def test_withdrawn_registration_cannot_be_completed(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        registration = registrations.start_registration(self.db, player["id"], 2027)
        registrations.withdraw_registration(self.db, registration["id"])
        with self.assertRaises(BusinessRuleError):
            registrations.complete_registration(self.db, registration["id"])

    def test_inactive_member_cannot_start_a_registration(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        members.deactivate_member(self.db, player["id"], "left the club")
        with self.assertRaises(BusinessRuleError):
            registrations.start_registration(self.db, player["id"], 2027)

    def test_invalid_season_is_rejected(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        for bad_season in (1888, 2999, "twenty twenty-six"):
            with self.assertRaises(ValidationError):
                registrations.start_registration(self.db, player["id"], bad_season)

    def test_registration_history_lists_every_season(self) -> None:
        player = self.member_by_last_name("Nguyen", "Ava")
        registrations.start_registration(self.db, player["id"], 2027)
        history = registrations.registration_history(self.db, player["id"])
        self.assertEqual([h["season"] for h in history], [2027, 2026])

    def test_season_summary_counts_only_completed_registrations(self) -> None:
        summary = registrations.summarise_season(self.db, 2026)
        complete = registrations.find_registrations(
            self.db, season=2026, status="complete"
        )
        self.assertEqual(summary["completed_total"], len(complete))
        self.assertGreater(summary["completed_total"], 0)


if __name__ == "__main__":
    unittest.main()
