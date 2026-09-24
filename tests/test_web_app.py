"""End-to-end tests for the web layer.

Each test starts a real HTTP server on an ephemeral port against a temporary
database file and drives it with ``urllib``, so what is tested is the same path
a browser takes — routing, form parsing, service calls, error rendering and
redirects.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app import build_server
from config import get_settings


class WebTestCase(unittest.TestCase):
    """Start one server for the whole class and talk to it over HTTP."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.settings = get_settings(
            env_file=Path(cls._tmpdir.name) / "no-such-env-file",
            APP_ENV="test",
            APP_HOST="127.0.0.1",
            APP_PORT="0",
            APP_DB_PATH=str(Path(cls._tmpdir.name) / "test.db"),
            APP_SEED="true",
            APP_DEBUG="false",
        )
        cls.server = build_server(cls.settings, seed_data=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._tmpdir.cleanup()

    # -- helpers -----------------------------------------------------------
    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path: str) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(self.url(path), timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:  # pragma: no cover - defensive
            return error.code, error.read().decode("utf-8")

    def post(self, path: str, data: dict[str, object]) -> tuple[int, str, str]:
        """POST a form and follow the redirect, returning (status, body, location)."""
        payload = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(self.url(path), data=payload, method="POST")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # noqa: D102
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8"), response.headers.get("Location", "")
        except urllib.error.HTTPError as error:
            location = error.headers.get("Location", "") if error.headers else ""
            body = error.read().decode("utf-8") if error.fp else ""
            return error.code, body, location

    def _id_before(self, html: str, needle: str, markers: tuple[str, ...]) -> str:
        """Return the id in the nearest link that precedes ``needle``.

        The listing pages render each record's name inside a link, so the id can
        be read straight out of the href rather than by trusting row order.
        """
        position = html.find(needle)
        self.assertNotEqual(position, -1, f"{needle!r} not found in the page")
        start = -1
        marker = ""
        for candidate in markers:
            found = html.rfind(candidate, 0, position)
            if found > start:
                start, marker = found, candidate
        if start == -1:
            for candidate in markers:
                found = html.find(candidate, position)
                if found != -1:
                    start, marker = found, candidate
                    break
        self.assertNotEqual(start, -1, f"no link for {needle!r}")

        digits = ""
        for character in html[start + len(marker):]:
            if character.isdigit():
                digits += character
            else:
                break
        self.assertTrue(digits, f"no id found in the link for {needle!r}")
        return digits

    def _first_id(self, html: str, marker: str) -> str:
        start = html.find(marker)
        self.assertNotEqual(start, -1, f"{marker} not present")
        digits = ""
        for character in html[start + len(marker):]:
            if character.isdigit():
                digits += character
            else:
                break
        return digits


class PageSmokeTests(WebTestCase):
    """Every page the club uses must render without a server error."""

    def test_pages_render(self) -> None:
        for path in ("/", "/members", "/guardians", "/registrations", "/teams", "/views"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200, f"{path} returned {status}")
                self.assertIn("Warrigal Park FC", body)
                self.assertNotIn("Traceback", body)

    def test_detail_pages_render(self) -> None:
        for path in ("/members/1", "/guardians/1", "/registrations/1", "/teams/1"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertNotIn("Traceback", body)

    def test_unknown_member_is_handled_gracefully(self) -> None:
        status, body = self.get("/members/999999")
        self.assertEqual(status, 200)
        self.assertIn("does not exist", body)

    def test_stylesheet_is_served(self) -> None:
        status, body = self.get("/static/styles.css")
        self.assertEqual(status, 200)
        self.assertIn("--brand", body)

    def test_path_traversal_outside_static_is_refused(self) -> None:
        status, _ = self.get("/static/../config.py")
        self.assertIn(status, (403, 404))

    def test_health_endpoint_reports_configuration_and_rules(self) -> None:
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["environment"], "test")
        self.assertTrue(payload["rules"])


class GuardianRuleThroughTheWebTests(WebTestCase):
    """The rule must hold when exercised through the user interface."""

    def test_completing_a_junior_registration_without_a_guardian_is_refused(self) -> None:
        status, body, _ = self.post(
            "/members",
            {"first_name": "Talia", "last_name": "Osei",
             "date_of_birth": "2016-05-04", "gender": "F"},
        )
        self.assertEqual(status, 303)

        # Find the new member id from the members list.
        _, listing = self.get("/members?q=Osei")
        member_id = self._id_before(listing, "Osei", ("/members/",))

        status, _, location = self.post(
            "/registrations",
            {"member_id": member_id, "season": "2026", "age_group": "U10"},
        )
        registration_id = location.rsplit("/", 1)[-1]

        status, body, _ = self.post(
            f"/registrations/{registration_id}/complete", {}
        )
        self.assertEqual(status, 200)
        self.assertIn("under 18", body)
        self.assertIn("no linked guardian", body)
        self.assertIn("rules stopped that action", body)

    def test_seeded_junior_with_a_guardian_can_be_completed_over_http(self) -> None:
        """Complete a registration after linking a guardian, entirely over HTTP."""
        # Create a junior with no guardian and open a registration for them.
        self.post(
            "/members",
            {"first_name": "Nadia", "last_name": "Farrow",
             "date_of_birth": "2015-07-07", "gender": "F"},
        )
        _, listing = self.get("/members?q=Farrow")
        member_id = self._id_before(listing, "Farrow", ("/members/",))

        _, _, location = self.post(
            "/registrations",
            {"member_id": member_id, "season": "2026", "age_group": "U11"},
        )
        registration_id = location.rsplit("/", 1)[-1]

        # Create and link a guardian for that player.
        _, _, guardian_location = self.post(
            "/guardians",
            {"first_name": "Marta", "last_name": "Farrow",
             "relationship": "parent", "phone": "0466 555 444", "email": ""},
        )
        guardian_id = guardian_location.rsplit("/", 1)[-1]
        status, _, _ = self.post(
            "/guardians/link",
            {"member_id": member_id, "guardian_id": guardian_id},
        )
        self.assertEqual(status, 303)

        # Now the same registration can be completed.
        status, _, _ = self.post(f"/registrations/{registration_id}/complete", {})
        self.assertEqual(status, 303)
        _, after = self.get(f"/registrations/{registration_id}")
        self.assertIn("Complete", after)

    # -- helpers -----------------------------------------------------------
    def _id_before(self, html: str, needle: str, markers: tuple[str, ...]) -> str:
        """Return the id in the nearest link that precedes ``needle``.

        The listing pages render a record's name inside a link, so the id can be
        read straight out of the href rather than by trusting row order.
        """
        position = html.find(needle)
        self.assertNotEqual(position, -1, f"{needle!r} not found in the page")
        start = -1
        marker = ""
        for candidate in markers:
            found = html.rfind(candidate, 0, position)
            if found > start:
                start, marker = found, candidate
        if start == -1:
            for candidate in markers:
                found = html.find(candidate, position)
                if found != -1:
                    start, marker = found, candidate
                    break
        self.assertNotEqual(start, -1, f"no link for {needle!r}")

        digits = ""
        for character in html[start + len(marker):]:
            if character.isdigit():
                digits += character
            else:
                break
        self.assertTrue(digits, f"no id found in the link for {needle!r}")
        return digits

    def _first_id(self, html: str, marker: str) -> str:
        start = html.find(marker)
        self.assertNotEqual(start, -1, f"{marker} not present")
        digits = ""
        for character in html[start + len(marker):]:
            if character.isdigit():
                digits += character
            else:
                break
        return digits

    """Creating and editing records through the HTML forms."""
    def test_create_guardian_then_link_then_view(self) -> None:
        status, _, location = self.post(
            "/guardians",
            {"first_name": "Zara", "last_name": "Whitfield",
             "relationship": "parent", "phone": "0455 111 222", "email": ""},
        )
        self.assertEqual(status, 303)
        guardian_id = location.rsplit("/", 1)[-1]

        _, page = self.get(f"/guardians/{guardian_id}")
        self.assertIn("Zara Whitfield", page)
        self.assertIn("0455 111 222", page)

    def test_invalid_member_form_shows_a_helpful_error(self) -> None:
        status, body, _ = self.post(
            "/members",
            {"first_name": "Talia", "last_name": "Osei",
             "date_of_birth": "not-a-date", "gender": "F"},
        )
        self.assertEqual(status, 200)
        self.assertIn("did not look right", body)
        self.assertIn("date of birth", body)

    def test_deactivate_then_reactivate_through_forms(self) -> None:
        status, _, location = self.post(
            "/members",
            {"first_name": "Marco", "last_name": "Bellini",
             "date_of_birth": "2012-05-05", "gender": "M"},
        )
        member_id = location.rsplit("/", 1)[-1]

        self.post(f"/members/{member_id}/deactivate", {"reason": "left the club"})
        _, page = self.get(f"/members/{member_id}")
        self.assertIn("Inactive", page)

        self.post(f"/members/{member_id}/reactivate", {})
        _, page = self.get(f"/members/{member_id}")
        self.assertIn("Active", page)

    def test_create_team_and_place_a_registered_player(self) -> None:
        # Noah Petrov is a seeded junior with a completed registration.
        _, page = self.get("/members?q=Petrov")
        member_id = self._id_before(page, "Petrov", ("/members/",))

        status, _, location = self.post(
            "/teams",
            {"name": "U15 Development", "age_group": "U15", "season": "2026"},
        )
        self.assertEqual(status, 303)
        team_id = location.rsplit("/", 1)[-1]

        status, _, _ = self.post(
            "/teams/add",
            {"team_id": team_id, "member_id": member_id, "squad_number": "14"},
        )
        self.assertEqual(status, 303)

        _, roster_page = self.get(f"/teams/{team_id}")
        self.assertIn("Petrov", roster_page)
        self.assertIn("14", roster_page)

    def test_withdraw_a_registration_through_the_form(self) -> None:
        """Withdrawal is available whatever state the seeded case is in."""
        self.post(
            "/members",
            {"first_name": "Owen", "last_name": "Castellano",
             "date_of_birth": "2016-02-02", "gender": "M"},
        )
        _, listing = self.get("/members?q=Castellano")
        member_id = self._id_before(listing, "Castellano", ("/members/",))
        _, _, location = self.post(
            "/registrations",
            {"member_id": member_id, "season": "2026", "age_group": "U10"},
        )
        registration_id = location.rsplit("/", 1)[-1]

        status, _, _ = self.post(
            f"/registrations/{registration_id}/withdraw",
            {"reason": "family relocated"},
        )
        self.assertEqual(status, 303)
        _, page = self.get(f"/registrations/{registration_id}")
        self.assertIn("Withdrawn", page)


if __name__ == "__main__":
    unittest.main()
