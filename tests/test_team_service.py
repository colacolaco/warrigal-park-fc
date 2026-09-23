"""Tests for the Team and Roster capability."""

from __future__ import annotations

import unittest

from services import member_service as members
from services import registration_service as registrations
from services import team_service as teams
from services.validation import BusinessRuleError, ValidationError
from tests.base import ServiceTestCase

SEASON = 2026


class TeamCrudTests(ServiceTestCase):
    def test_create_team_and_reject_a_duplicate(self) -> None:
        created = teams.create_team(self.db, "U12 Girls", "U12", SEASON)
        self.assertEqual(created["name"], "U12 Girls")
        self.assertEqual(created["season"], SEASON)
        with self.assertRaises(BusinessRuleError):
            teams.create_team(self.db, "U12 Girls", "U12", SEASON)

    def test_create_team_validates_its_input(self) -> None:
        for bad in (
            {"name": "", "age_group": "U12", "season": SEASON},
            {"name": "U12 Girls", "age_group": "", "season": SEASON},
            {"name": "U12 Girls", "age_group": "U12", "season": "next year"},
            {"name": "U12 Girls", "age_group": "U12", "season": 3000},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                teams.create_team(self.db, bad["name"], bad["age_group"], bad["season"])

    def test_only_a_completed_registration_can_be_placed_in_a_team(self) -> None:
        """The second genuine business rule: no roster places for unregistered players."""
        team = teams.create_team(self.db, "U12 Mixed", "U12", SEASON)
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )

        # No registration at all.
        with self.assertRaises(BusinessRuleError) as caught:
            teams.add_player(self.db, team["id"], player["id"])
        self.assertIn("no registration", str(caught.exception))

        # A started registration is not enough.
        registration = registrations.start_registration(self.db, player["id"], SEASON)
        with self.assertRaises(BusinessRuleError) as caught:
            teams.add_player(self.db, team["id"], player["id"])
        self.assertIn("started", str(caught.exception))

        # A withdrawn registration is not enough either.
        registrations.withdraw_registration(self.db, registration["id"])
        with self.assertRaises(BusinessRuleError):
            teams.add_player(self.db, team["id"], player["id"])

    def test_add_move_remove_player(self) -> None:
        # Use a season that already has a completed registration to draw on.
        player = self.member_by_last_name("Marsh", "Jayden")
        registration = registrations.registration_history(self.db, player["id"])[0]
        group, season = registration["age_group"], registration["season"]

        source = teams.create_team(self.db, "U11 Mixed", group, season)
        target = teams.create_team(self.db, "U11 Development", group, season)

        added = teams.add_player(self.db, source["id"], player["id"], squad_number="9")
        self.assertEqual(added["player_count"], 1)

        # Adding the same player twice is a no-op, not an error or a duplicate.
        again = teams.add_player(self.db, source["id"], player["id"])
        self.assertEqual(again["player_count"], 1)

        moved = teams.move_player(self.db, player["id"], source["id"], target["id"])
        self.assertEqual(moved["player_count"], 1)
        self.assertEqual(teams.get_team(self.db, source["id"])["player_count"], 0)

        removed = teams.remove_player(self.db, target["id"], player["id"])
        self.assertEqual(removed["player_count"], 0)

        with self.assertRaises(BusinessRuleError):
            teams.remove_player(self.db, target["id"], player["id"])

    def test_add_player_rejects_unknown_records(self) -> None:
        team = teams.find_teams(self.db, season=SEASON)[0]
        player = teams.team_roster(self.db, team["id"])[0]
        with self.assertRaises(ValidationError):
            teams.add_player(self.db, 99999, player["id"])
        with self.assertRaises(ValidationError):
            teams.add_player(self.db, team["id"], 99999)

    def test_move_between_seasons_is_refused(self) -> None:
        player = self.member_by_last_name("Marsh", "Jayden")
        registration = registrations.registration_history(self.db, player["id"])[0]
        group, season = registration["age_group"], registration["season"]

        this_season = teams.create_team(self.db, f"Move A {group}", group, season)
        next_season = teams.create_team(self.db, f"Move B {group}", group, season + 1)
        teams.add_player(self.db, this_season["id"], player["id"])

        with self.assertRaises(BusinessRuleError) as caught:
            teams.move_player(self.db, player["id"], this_season["id"],
                              next_season["id"])
        self.assertIn("same season", str(caught.exception))

    def test_move_requires_the_player_to_be_in_the_source_team(self) -> None:
        player = self.member_by_last_name("Marsh", "Jayden")
        registration = registrations.registration_history(self.db, player["id"])[0]
        group, season = registration["age_group"], registration["season"]
        a = teams.create_team(self.db, f"Source {group}", group, season)
        b = teams.create_team(self.db, f"Target {group}", group, season)
        with self.assertRaises(BusinessRuleError):
            teams.move_player(self.db, player["id"], a["id"], b["id"])

    def test_move_to_the_same_team_is_rejected(self) -> None:
        team = teams.find_teams(self.db, season=SEASON)[0]
        player = teams.team_roster(self.db, team["id"])[0]
        with self.assertRaises(ValidationError):
            teams.move_player(self.db, player["id"], team["id"], team["id"])

    def test_roster_shows_a_guardian_contact_for_a_junior(self) -> None:
        """The club's headline reporting requirement."""
        teams_list = teams.find_teams(self.db, season=SEASON)
        roster = []
        for team in teams_list:
            roster.extend(teams.team_roster(self.db, team["id"]))
        self.assertTrue(roster)

        juniors = [p for p in roster if p["is_minor"]]
        adults = [p for p in roster if not p["is_minor"]]
        self.assertTrue(juniors, "the sample roster should contain juniors")
        self.assertTrue(adults, "the sample roster should contain adults")

        for player in juniors:
            self.assertTrue(player["contact"], f"{player['full_name']} has no contact")
            self.assertTrue(player["contact_for"], "a junior's contact is the guardian's")
            self.assertNotEqual(player["contact_for"], "player")
        for player in adults:
            self.assertTrue(player["contact"])
            self.assertEqual(player["contact_for"], "player")

    def test_roster_reports_contact_gaps(self) -> None:
        """A junior on a roster with no guardian contact is reported, not hidden."""
        team = teams.create_team(self.db, "U11 Gap Check", "U11", SEASON)
        player = members.create_member(
            self.db,
            {"first_name": "Talia", "last_name": "Osei", "date_of_birth": "2016-05-04"},
        )
        registration = registrations.start_registration(self.db, player["id"], SEASON)
        # Complete via the adult path is impossible for a junior, so link a
        # guardian, complete, then remove the guardian to create the gap.
        from services import guardian_service as guardians

        guardian = guardians.create_guardian(
            self.db, {"first_name": "Ada", "last_name": "Osei", "phone": "0412 345 678"}
        )
        guardians.link_guardian(self.db, player["id"], guardian["id"])
        registrations.complete_registration(self.db, registration["id"])
        teams.add_player(self.db, team["id"], player["id"])

        self.assertEqual(teams.roster_contact_gaps(self.db, team["id"]), [])

        # Now remove the contact details from the guardian: the roster must
        # report the gap rather than silently showing an empty contact.
        with self.assertRaises(ValidationError):
            guardians.update_guardian(self.db, guardian["id"],
                                      {"phone": "", "email": ""})

    def test_team_roster_is_empty_for_a_new_team(self) -> None:
        team = teams.create_team(self.db, "U18 Development", "U18", SEASON)
        self.assertEqual(teams.team_roster(self.db, team["id"]), [])


if __name__ == "__main__":
    unittest.main()
