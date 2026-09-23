"""Web layer — routing and request handling for the club registration system.

The application uses only the Python standard library (``http.server`` and
``sqlite3``) so that a clean checkout runs with no installation step.  All
business rules live in the ``services`` package; this module translates HTTP
requests into service calls and renders the result.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import htmlview as hv
from config import Settings, get_settings
from models.database import Database
from models.seed_data import seed
from services import guardian_service as gs
from services import member_service as ms
from services import registration_service as rs
from services import team_service as ts
from services.validation import BusinessRuleError, ValidationError
from theme import THEME

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger("warrigal.web")

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------
ROUTES: list[tuple[str, re.Pattern[str], Callable[..., Any]]] = []


def route(method: str, pattern: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a handler for ``method`` and a regular-expression path."""
    compiled = re.compile(f"^{pattern}$")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        ROUTES.append((method.upper(), compiled, func))
        return func

    return decorator


class Redirect(Exception):
    """Raised by a handler to send a 303 See Other response."""

    def __init__(self, location: str) -> None:
        super().__init__(location)
        self.location = location


class Request:
    """A parsed request handed to a handler.

    ``urllib`` returns every field as a list of values.  Because each control in
    this application's forms has a single value, the lists are flattened here —
    once, at the boundary — so that ``req.form`` can be handed straight to a
    service.  Leaving the lists in place is the classic source of a bug where a
    date arrives as ``"['2016-05-04']"`` instead of ``"2016-05-04"``.
    """

    def __init__(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        form: dict[str, list[str]],
        db: Database,
        settings: Settings,
    ) -> None:
        self.method = method
        self.path = path
        self.query = {key: values[0] for key, values in query.items() if values}
        self.form = {key: values[0] for key, values in form.items() if values}
        self.db = db
        self.settings = settings
        # A notice raised by a handler that is about to render a page itself
        # (as opposed to redirecting).  Stored on the request rather than in a
        # server-side session, which keeps the deployment configuration trivial.
        self.notice: tuple[str, str] | None = None

    def get(self, name: str, default: str = "") -> str:
        if name in self.form:
            return self.form[name]
        if name in self.query:
            return self.query[name]
        return default

    def get_int(self, name: str, default: int | None = None) -> int | None:
        raw = self.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def has(self, name: str) -> bool:
        return name in self.form or name in self.query


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@route("GET", "/")
def dashboard(req: Request) -> str:
    db = req.db
    season = int(THEME["season"])
    members = ms.find_members(db)
    registrations = rs.find_registrations(db, season=season)
    complete = [r for r in registrations if r["status"] == "complete"]
    started = [r for r in registrations if r["status"] == "started"]
    withdrawn = [r for r in registrations if r["status"] == "withdrawn"]
    teams = ts.find_teams(db, season=season)
    guardians = gs.find_guardians(db)

    stats = hv.table(
        ["Measure", "Value", "Note"],
        [
            ["Active members", f'<span class="num">{len(members)}</span>', "players on the club register"],
            ["Guardian records", f'<span class="num">{len(guardians)}</span>', "adult contacts"],
            ["Registrations, season " + str(season), f'<span class="num">{len(registrations)}</span>', "all statuses"],
            ["&nbsp;&nbsp;&mdash; complete", f'<span class="num">{len(complete)}</span>', "player is cleared to play"],
            ["&nbsp;&nbsp;&mdash; started", f'<span class="num">{len(started)}</span>', "waiting on guardian paperwork"],
            ["&nbsp;&nbsp;&mdash; withdrawn", f'<span class="num">{len(withdrawn)}</span>', "not registering this season"],
            ["Teams created", f'<span class="num">{len(teams)}</span>', "for season " + str(season)],
        ],
    )

    incomplete = [
        r for r in registrations
        if r["status"] == "started" and r["age_at_registration"] is not None
        and r["age_at_registration"] < 18
        and not gs.has_guardian(db, r["member_id"])
    ]
    if incomplete:
        rows = [
            [
                hv.link(f"/registrations/{r['id']}", r["member_name"]),
                str(r["age_at_registration"]),
                r["age_group"],
                hv.status_badge(r["status"]),
            ]
            for r in incomplete
        ]
        risk = hv.card(
            f"Guardian rule: {len(incomplete)} junior registration(s) blocked",
            hv.rule_callout(
                "These players are <strong>under 18 with no linked guardian</strong>. "
                "They must be given a guardian record before their registration can "
                "be completed &mdash; the system will refuse completion and tell you why."
            )
            + hv.table(["Player", "Age", "Age group", "Status"], rows),
        )
    else:
        risk = hv.card(
            "Guardian rule",
            hv.rule_callout(
                "Every junior registration currently on file has a linked guardian. "
                "The rule is still enforced on every completion attempt."
            ),
        )

    body = (
        hv.page_title("Registrar dashboard", f"season {season}")
        + hv.help_text(
            "One screen replacing the paper forms, the 43-column Excel master and "
            "the second data-entry pass into PlayRegister."
        )
        + risk
        + hv.card("Registration totals", stats)
    )
    return hv.layout("Dashboard", body, active="/", notice=_pop_notice(req), environment=req.settings.env)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
@route("GET", "/members")
def members_list(req: Request) -> str:
    db = req.db
    name = req.get("q")
    include_inactive = req.get("show") == "all"
    members = ms.find_members(db, name or None, include_inactive=include_inactive)

    search = (
        '<form method="get" action="/members" class="inline-form">'
        + hv.field("q", "Search by name", name,
                   hint="matches first or last name, e.g. Marsh")
        + hv.field("show", "Show", "all" if include_inactive else "active",
                   options=[("active", "Active members only"), ("all", "Include deactivated")])
        + '<button type="submit">Search</button>'
        + hv.link("/members", "Clear", "button ghost")
        + "</form>"
    )

    rows = []
    for member in members:
        rows.append(
            [
                str(member["id"]),
                hv.link(f"/members/{member['id']}", member["full_name"]),
                member["date_of_birth"],
                f'<span class="num">{member["age"]}</span>',
                hv.esc(member["suggested_age_group"]),
                hv.esc(member["phone"] or member["email"] or "&mdash;"),
                hv.badge("Active", THEME["success"]) if member["is_active"]
                else hv.badge("Inactive", THEME["text_muted"]),
                hv.link(f"/members/{member['id']}", "Open", "button tiny secondary"),
            ]
        )

    body = (
        hv.page_title("Members", f"{len(members)} record(s)")
        + hv.help_text(
            "Create, find, update and deactivate player records. Search returns "
            "same-name players separately, distinguished by date of birth and id."
        )
        + hv.card("Search", search)
        + hv.card(
            "Member register",
            hv.table(
                ["ID", "Name", "Date of birth", "Age", "Suggested group",
                 "Contact", "Status", ""],
                rows,
                caption="Deactivation is a soft delete: the record is kept so the "
                        "player's registration history survives.",
            ),
        )
        + hv.card(
            "Add a member",
            f'<form method="post" action="/members" class="stack">'
            + hv.field("first_name", "First name", required=True)
            + hv.field("last_name", "Last name", required=True)
            + hv.field("date_of_birth", "Date of birth", input_type="date",
                       required=True, hint="used to decide the age group and the "
                                           "under-18 guardian rule")
            + hv.field("gender", "Gender", "U",
                       options=[("F", "Female"), ("M", "Male"), ("U", "Not recorded")])
            + hv.field("phone", "Phone", input_type="tel")
            + hv.field("email", "Email", input_type="email")
            + '<div class="actions"><button type="submit">Create member</button></div>'
            + "</form>",
        )
    )
    return hv.layout("Members", body, active="/members",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", "/members")
def members_create(req: Request) -> str:
    member = ms.create_member(req.db, dict(req.form))
    _set_notice(req, "ok", f"Member {member['full_name']} created (id {member['id']}).")
    raise Redirect(f"/members/{member['id']}")


@route("GET", r"/members/(?P<member_id>\d+)")
def member_detail(req: Request, member_id: str) -> str:
    db = req.db
    member = ms.get_member(db, int(member_id))
    if member is None:
        return _not_found(req, f"Member {member_id} does not exist")

    guardians = gs.list_guardians_for_member(db, member["id"])
    history = rs.registration_history(db, member["id"])
    teams = [
        team for team in ts.find_teams(db)
        if any(p["id"] == member["id"] for p in ts.team_roster(db, team["id"]))
    ]

    profile = hv.table(
        ["Field", "Value"],
        [
            ["Member id", str(member["id"])],
            ["Name", hv.esc(member["full_name"])],
            ["Date of birth", hv.esc(member["date_of_birth"])],
            ["Age", f'<span class="num">{member["age"]}</span>'],
            ["Suggested age group", hv.esc(member["suggested_age_group"])],
            ["Gender", hv.esc(member["gender"])],
            ["Phone", hv.esc(member["phone"] or "&mdash;")],
            ["Email", hv.esc(member["email"] or "&mdash;")],
            ["Status", hv.badge("Active", THEME["success"]) if member["is_active"]
             else hv.badge("Inactive", THEME["text_muted"])],
            ["Under 18", "Yes &mdash; a guardian is required to complete registration"
             if member["age"] < 18 else "No"],
            ["Created", hv.esc(member["created_at"])],
            ["Last updated", hv.esc(member["updated_at"])],
        ],
    )

    guardian_rows = [
        [
            hv.link(f"/guardians/{g['id']}", g["full_name"]),
            hv.esc(g["relationship"]),
            hv.esc(g["phone"] or g["email"] or "&mdash;"),
            "Yes" if g.get("is_primary") else "No",
            '<form method="post" action="/guardians/unlink" class="actions">'
            + hv.hidden("member_id", member["id"])
            + hv.hidden("guardian_id", g["id"])
            + '<button class="tiny ghost" type="submit">Remove link</button></form>',
        ]
        for g in guardians
    ]

    all_guardians = gs.find_guardians(db)
    linkable = [
        (str(g["id"]), f"{g['full_name']} ({g['relationship']})")
        for g in all_guardians
        if g["id"] not in {x["id"] for x in guardians}
    ]
    link_form = (
        '<form method="post" action="/guardians/link" class="inline-form">'
        + hv.hidden("member_id", member["id"])
        + hv.field("guardian_id", "Link an existing guardian", "",
                   options=[("", "&mdash; choose a guardian &mdash;")] + linkable,
                   hint="or create a new guardian on the Guardians page")
        + '<button type="submit">Link guardian</button></form>'
    ) if linkable else hv.empty_state(
        "Every guardian on file is already linked to this member. Create another "
        "guardian on the Guardians page if needed."
    )

    history_rows = [
        [
            str(r["season"]),
            hv.esc(r["age_group"]),
            hv.status_badge(r["status"]),
            hv.esc(r["refusal_reason"] or "&mdash;"),
            hv.link(f"/registrations/{r['id']}", "Open", "button tiny secondary"),
        ]
        for r in history
    ]

    edit_form = (
        f'<form method="post" action="/members/{member["id"]}/update" class="stack">'
        + hv.field("first_name", "First name", member["first_name"], required=True)
        + hv.field("last_name", "Last name", member["last_name"], required=True)
        + hv.field("date_of_birth", "Date of birth", member["date_of_birth"],
                   input_type="date", required=True)
        + hv.field("gender", "Gender", member["gender"],
                   options=[("F", "Female"), ("M", "Male"), ("U", "Not recorded")])
        + hv.field("phone", "Phone", member["phone"] or "", input_type="tel")
        + hv.field("email", "Email", member["email"] or "", input_type="email")
        + '<div class="actions"><button type="submit">Save changes</button></div>'
        + "</form>"
    )

    if member["is_active"]:
        state_form = (
            f'<form method="post" action="/members/{member["id"]}/deactivate" class="stack">'
            + hv.field("reason", "Reason (recorded in the audit log)",
                       hint="for example: left the club at the end of the season")
            + '<div class="actions"><button class="secondary" type="submit">'
            "Deactivate member</button></div></form>"
            + '<p class="page-help">A deactivated member is hidden from the register '
              "but keeps every registration and roster record.</p>"
        )
    else:
        state_form = (
            f'<form method="post" action="/members/{member["id"]}/reactivate">'
            '<button type="submit">Reactivate member</button></form>'
        )

    new_registration = (
        f'<form method="post" action="/registrations" class="inline-form">'
        + hv.hidden("member_id", member["id"])
        + hv.field("season", "Season", THEME["season"], input_type="number")
        + hv.field("age_group", "Age group", member["suggested_age_group"],
                   hint="suggested from the date of birth")
        + '<button type="submit">Start registration</button></form>'
    )

    body = (
        hv.page_title(member["full_name"], f"member id {member['id']}")
        + '<p class="page-help">'
        + hv.link("/members", "&larr; back to the member register")
        + "</p>"
        + hv.card("Profile", profile)
        + f'<div class="grid-2">'
        + hv.card("Guardians linked to this member", hv.table(
            ["Guardian", "Relationship", "Contact", "Primary", ""], guardian_rows)
            + link_form)
        + hv.card("Registration history",
                  hv.table(["Season", "Age group", "Status", "Note", ""], history_rows)
                  + new_registration)
        + "</div>"
        + f'<div class="grid-2">'
        + hv.card("Update details", edit_form)
        + hv.card("Deactivate or reactivate", state_form
                  + (hv.table(["Team", "Age group", "Season"],
                              [[hv.link(f"/teams/{t['id']}", t["name"]),
                                hv.esc(t["age_group"]), str(t["season"])] for t in teams],
                              caption="Teams this member currently appears in")
                     if teams else ""))
        + "</div>"
    )
    return hv.layout(member["full_name"], body, active="/members",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", r"/members/(?P<member_id>\d+)/update")
def member_update(req: Request, member_id: str) -> str:
    ms.update_member(req.db, int(member_id), dict(req.form))
    _set_notice(req, "ok", "Member details updated.")
    raise Redirect(f"/members/{member_id}")


@route("POST", r"/members/(?P<member_id>\d+)/deactivate")
def member_deactivate(req: Request, member_id: str) -> str:
    member = ms.deactivate_member(req.db, int(member_id), req.get("reason"))
    _set_notice(req, "ok", f"{member['full_name']} deactivated (soft delete).")
    raise Redirect(f"/members/{member_id}")


@route("POST", r"/members/(?P<member_id>\d+)/reactivate")
def member_reactivate(req: Request, member_id: str) -> str:
    member = ms.reactivate_member(req.db, int(member_id))
    _set_notice(req, "ok", f"{member['full_name']} reactivated.")
    raise Redirect(f"/members/{member_id}")


# ---------------------------------------------------------------------------
# Guardians
# ---------------------------------------------------------------------------
@route("GET", "/guardians")
def guardians_list(req: Request) -> str:
    db = req.db
    name = req.get("q")
    guardians = gs.find_guardians(db, name or None)

    rows = []
    for guardian in guardians:
        children = guardian["linked_children"]
        rows.append(
            [
                str(guardian["id"]),
                hv.link(f"/guardians/{guardian['id']}", guardian["full_name"]),
                hv.esc(guardian["relationship"]),
                hv.esc(guardian["phone"] or guardian["email"] or "&mdash;"),
                f'<span class="num">{len(children)}</span>',
                hv.esc(", ".join(c["full_name"] for c in children) or "&mdash;"),
            ]
        )

    body = (
        hv.page_title("Guardians", f"{len(guardians)} record(s)")
        + hv.help_text(
            "One guardian record can be linked to several junior players. Editing "
            "the contact details here updates every linked child immediately."
        )
        + hv.card("Search", '<form method="get" action="/guardians" class="inline-form">'
                  + hv.field("q", "Search by name", name)
                  + '<button type="submit">Search</button>'
                  + hv.link("/guardians", "Clear", "button ghost") + "</form>")
        + hv.card("Guardian register",
                  hv.table(["ID", "Name", "Relationship", "Contact",
                            "Linked juniors", "Children"], rows))
        + hv.card(
            "Add a guardian",
            '<form method="post" action="/guardians" class="stack">'
            + hv.field("first_name", "First name", required=True)
            + hv.field("last_name", "Last name", required=True)
            + hv.field("relationship", "Relationship", "parent",
                       options=[("parent", "Parent"), ("guardian", "Guardian"),
                                ("carer", "Carer"), ("other", "Other")])
            + hv.field("phone", "Phone", input_type="tel",
                       hint="at least one of phone or email is required")
            + hv.field("email", "Email", input_type="email")
            + '<div class="actions"><button type="submit">Create guardian</button></div>'
            + "</form>",
        )
    )
    return hv.layout("Guardians", body, active="/guardians",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", "/guardians")
def guardians_create(req: Request) -> str:
    guardian = gs.create_guardian(req.db, dict(req.form))
    _set_notice(req, "ok", f"Guardian {guardian['full_name']} created.")
    raise Redirect(f"/guardians/{guardian['id']}")


@route("GET", r"/guardians/(?P<guardian_id>\d+)")
def guardian_detail(req: Request, guardian_id: str) -> str:
    db = req.db
    guardian = gs.get_guardian(db, int(guardian_id))
    if guardian is None:
        return _not_found(req, f"Guardian {guardian_id} does not exist")

    children = guardian["linked_children"]
    child_rows = [
        [
            hv.link(f"/members/{child['id']}", child["full_name"]),
            child["date_of_birth"],
            f'<span class="num">{child["age"]}</span>',
            hv.badge("Under 18", THEME["brand_primary"]) if child["is_minor"]
            else hv.badge("18 or over", THEME["text_muted"]),
            "Yes" if child.get("is_primary") else "No",
        ]
        for child in children
    ]

    unlinked = ms.find_members(db)
    unlinked = [m for m in unlinked if m["id"] not in {c["id"] for c in children}]
    link_form = (
        '<form method="post" action="/guardians/link" class="inline-form">'
        + hv.hidden("guardian_id", guardian["id"])
        + hv.field("member_id", "Link this guardian to a member", "",
                   options=[("", "&mdash; choose a member &mdash;")]
                   + [(str(m["id"]), f"{m['full_name']} ({m['date_of_birth']})")
                      for m in unlinked])
        + '<button type="submit">Link member</button></form>'
    ) if unlinked else hv.empty_state(
        "Every active member is already linked to this guardian."
    )

    edit_form = (
        f'<form method="post" action="/guardians/{guardian["id"]}/update" class="stack">'
        + hv.field("first_name", "First name", guardian["first_name"], required=True)
        + hv.field("last_name", "Last name", guardian["last_name"], required=True)
        + hv.field("relationship", "Relationship", guardian["relationship"],
                   options=[("parent", "Parent"), ("guardian", "Guardian"),
                            ("carer", "Carer"), ("other", "Other")])
        + hv.field("phone", "Phone", guardian["phone"] or "", input_type="tel")
        + hv.field("email", "Email", guardian["email"] or "", input_type="email")
        + '<div class="actions"><button type="submit">Save and sync to children</button>'
        + "</div></form>"
        + ('<p class="page-help">Saving this form updates '
           + str(len(children)) + " linked child record(s) in the same operation.</p>"
           if children else "")
    )

    body = (
        hv.page_title(guardian["full_name"], f"guardian id {guardian['id']}")
        + '<p class="page-help">' + hv.link("/guardians", "&larr; back to the guardian register") + "</p>"
        + hv.card("Contact details", hv.table(
            ["Field", "Value"],
            [["Guardian id", str(guardian["id"])],
             ["Name", hv.esc(guardian["full_name"])],
             ["Relationship", hv.esc(guardian["relationship"])],
             ["Phone", hv.esc(guardian["phone"] or "&mdash;")],
             ["Email", hv.esc(guardian["email"] or "&mdash;")],
             ["Linked juniors", f'<span class="num">{len(children)}</span>'],
             ["Last updated", hv.esc(guardian["updated_at"])]]))
        + f'<div class="grid-2">'
        + hv.card("Linked players", hv.table(
            ["Player", "Date of birth", "Age", "Junior", "Primary"], child_rows)
            + link_form)
        + hv.card("Update and sync", edit_form)
        + "</div>"
    )
    return hv.layout(guardian["full_name"], body, active="/guardians",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", r"/guardians/(?P<guardian_id>\d+)/update")
def guardian_update(req: Request, guardian_id: str) -> str:
    guardian = gs.update_guardian(req.db, int(guardian_id), dict(req.form))
    _set_notice(
        req, "ok",
        f"Guardian details saved and synced to {guardian['linked_count']} linked "
        f"child record(s).",
    )
    raise Redirect(f"/guardians/{guardian_id}")


@route("POST", "/guardians/link")
def guardian_link(req: Request) -> str:
    member_id = req.get_int("member_id")
    guardian_id = req.get_int("guardian_id")
    if member_id is None or guardian_id is None:
        _set_notice(req, "error", "Choose both a member and a guardian to create a link.")
        raise Redirect("/guardians")
    guardian = gs.link_guardian(req.db, member_id, guardian_id)
    member = ms.get_member(req.db, member_id)
    _set_notice(req, "ok",
                f"{guardian['full_name']} linked to {member['full_name'] if member else member_id}.")
    raise Redirect(f"/members/{member_id}")


@route("POST", "/guardians/unlink")
def guardian_unlink(req: Request) -> str:
    member_id = req.get_int("member_id")
    guardian_id = req.get_int("guardian_id")
    gs.unlink_guardian(req.db, int(member_id), int(guardian_id))
    _set_notice(req, "ok", "Guardian link removed.")
    raise Redirect(f"/members/{member_id}")


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------
@route("GET", "/registrations")
def registrations_list(req: Request) -> str:
    db = req.db
    season = req.get_int("season", int(THEME["season"]))
    status = req.get("status") or None
    registrations = rs.find_registrations(db, season=season, status=status)
    summary = rs.summarise_season(db, season or int(THEME["season"]))

    rows = []
    for r in registrations:
        rows.append(
            [
                str(r["id"]),
                hv.link(f"/members/{r['member_id']}", r["member_name"]),
                f'<span class="num">{r["age_at_registration"]}</span>',
                hv.esc(r["age_group"]),
                hv.status_badge(r["status"]),
                hv.esc(r["refusal_reason"] or "&mdash;"),
                hv.link(f"/registrations/{r['id']}", "Open", "button tiny secondary"),
            ]
        )

    summary_rows = [
        [hv.esc(group),
         f'<span class="num">{counts.get("complete", 0)}</span>',
         f'<span class="num">{counts.get("started", 0)}</span>',
         f'<span class="num">{counts.get("withdrawn", 0)}</span>',
         f'<span class="num">{sum(counts.values())}</span>']
        for group, counts in sorted(summary["by_age_group"].items())
    ]
    gender = summary["completed_by_gender"]

    body = (
        hv.page_title("Registrations", f"{len(registrations)} record(s)")
        + hv.help_text(
            "Season registration with the status flow started / complete / "
            "withdrawn. Completion is refused for a player under 18 with no "
            "linked guardian."
        )
        + hv.rule_callout(
            "<strong>Under-18 rule:</strong> completing a registration for a player "
            "under 18 requires at least one linked guardian. The refusal reason is "
            "recorded against the registration."
        )
        + hv.card("Filter", '<form method="get" action="/registrations" class="inline-form">'
                  + hv.field("season", "Season", season, input_type="number")
                  + hv.field("status", "Status", status or "",
                             options=[("", "All statuses"), ("started", "Started"),
                                      ("complete", "Complete"), ("withdrawn", "Withdrawn")])
                  + '<button type="submit">Apply</button>'
                  + hv.link("/registrations", "Reset", "button ghost") + "</form>")
        + hv.card("Registration records",
                  hv.table(["ID", "Player", "Age", "Age group", "Status", "Note", ""],
                           rows))
        + f'<div class="grid-2">'
        + hv.card(f"Season {season} totals by age group",
                  hv.table(["Age group", "Complete", "Started", "Withdrawn", "Total"],
                           summary_rows,
                           caption="Report used for the team nominations due to the "
                                   "association on 1 March."))
        + hv.card("Completed registrations by gender",
                  hv.table(["Gender", "Completed"],
                           [["Female", f'<span class="num">{gender.get("F", 0)}</span>'],
                            ["Male", f'<span class="num">{gender.get("M", 0)}</span>'],
                            ["Not recorded", f'<span class="num">{gender.get("U", 0)}</span>'],
                            ["<strong>Total</strong>",
                             f'<span class="num"><strong>{summary["completed_total"]}</strong></span>']]))
        + "</div>"
    )
    return hv.layout("Registrations", body, active="/registrations",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", "/registrations")
def registrations_create(req: Request) -> str:
    member_id = req.get_int("member_id")
    season = req.get_int("season", int(THEME["season"]))
    registration = rs.start_registration(
        req.db, int(member_id), int(season), req.get("age_group") or None
    )
    _set_notice(req, "ok",
                f"Registration {registration['id']} started for "
                f"{registration['member_name']} (season {registration['season']}).")
    raise Redirect(f"/registrations/{registration['id']}")


@route("GET", r"/registrations/(?P<registration_id>\d+)")
def registration_detail(req: Request, registration_id: str) -> str:
    db = req.db
    registration = rs.get_registration(db, int(registration_id))
    if registration is None:
        return _not_found(req, f"Registration {registration_id} does not exist")

    member = registration["member"] or {}
    guardians = gs.list_guardians_for_member(db, registration["member_id"]) \
        if registration.get("member_id") else []

    detail = hv.table(
        ["Field", "Value"],
        [
            ["Registration id", str(registration["id"])],
            ["Player", hv.link(f"/members/{registration['member_id']}",
                               registration["member_name"] if registration.get("member_name") else "")],
            ["Age on the registration date",
             f'<span class="num">{registration["age_at_registration"]}</span>'],
            ["Season", str(registration["season"])],
            ["Age group", hv.esc(registration["age_group"])],
            ["Status", hv.status_badge(registration["status"])],
            ["Created", hv.esc(registration["created_at"])],
            ["Last updated", hv.esc(registration["updated_at"])],
            ["Note", hv.esc(registration["refusal_reason"] or "&mdash;")],
        ],
    )

    if registration["status"] == "started":
        actions = (
            '<div class="actions">'
            f'<form method="post" action="/registrations/{registration["id"]}/complete">'
            f'<button type="submit">Complete registration</button></form>'
            f'<form method="post" action="/registrations/{registration["id"]}/withdraw" '
            'class="inline-form">'
            + hv.field("reason", "Withdrawal reason", "withdrawn by the registrar")
            + '<button class="secondary" type="submit">Withdraw</button></form>'
            "</div>"
        )
    elif registration["status"] == "complete":
        actions = (
            f'<form method="post" action="/registrations/{registration["id"]}/withdraw" '
            'class="inline-form">'
            + hv.field("reason", "Withdrawal reason", "withdrawn by the registrar")
            + '<button class="secondary" type="submit">Withdraw registration</button></form>'
        )
    else:
        actions = hv.empty_state(
            "This registration is withdrawn. Start a new registration from the "
            "member's page if the player returns."
        )

    amend = (
        f'<form method="post" action="/registrations/{registration["id"]}/amend" '
        'class="inline-form">'
        + hv.field("age_group", "Age group", registration["age_group"])
        + '<button type="submit">Save age group</button></form>'
    )

    guardian_block = hv.table(
        ["Guardian", "Relationship", "Contact"],
        [[hv.link(f"/guardians/{g['id']}", g["full_name"]), hv.esc(g["relationship"]),
          hv.esc(g["phone"] or g["email"] or "&mdash;")] for g in guardians],
    ) if guardians else hv.empty_state(
        "No guardian is linked to this player."
    )

    is_minor = (registration["age_at_registration"] or 0) < 18
    if is_minor and not guardians:
        rule_block = hv.rule_callout(
            "<strong>This registration cannot be completed.</strong> The player is "
            "under 18 and has no linked guardian. Use the Guardians page to create "
            "or link a guardian, then return here."
        )
    else:
        rule_block = hv.rule_callout(
            "The under-18 guardian rule is satisfied or not applicable for this "
            "registration."
            if not is_minor else
            "The under-18 guardian rule is satisfied: a guardian is linked."
        )

    body = (
        hv.page_title(f"Registration {registration['id']}", registration["member_name"] if registration.get("member_name") else "")
        + '<p class="page-help">' + hv.link("/registrations", "&larr; back to registrations") + "</p>"
        + rule_block
        + hv.card("Registration", detail)
        + f'<div class="grid-2">'
        + hv.card("Change status", actions + amend)
        + hv.card("Guardians on file", guardian_block)
        + "</div>"
    )
    return hv.layout(f"Registration {registration['id']}", body, active="/registrations",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", r"/registrations/(?P<registration_id>\d+)/complete")
def registration_complete(req: Request, registration_id: str) -> str:
    registration = rs.complete_registration(req.db, int(registration_id))
    _set_notice(req, "ok",
                f"Registration {registration['id']} completed for "
                f"{registration['member_name']}.")
    raise Redirect(f"/registrations/{registration_id}")


@route("POST", r"/registrations/(?P<registration_id>\d+)/withdraw")
def registration_withdraw(req: Request, registration_id: str) -> str:
    rs.withdraw_registration(req.db, int(registration_id), req.get("reason"))
    _set_notice(req, "warn", "Registration withdrawn.")
    raise Redirect(f"/registrations/{registration_id}")


@route("POST", r"/registrations/(?P<registration_id>\d+)/amend")
def registration_amend(req: Request, registration_id: str) -> str:
    rs.amend_registration(req.db, int(registration_id),
                          age_group=req.get("age_group") or None)
    _set_notice(req, "ok", "Registration updated.")
    raise Redirect(f"/registrations/{registration_id}")


# ---------------------------------------------------------------------------
# Teams and rosters
# ---------------------------------------------------------------------------
@route("GET", "/teams")
def teams_list(req: Request) -> str:
    db = req.db
    season = req.get_int("season", int(THEME["season"]))
    teams = ts.find_teams(db, season=season)

    rows = [
        [str(team["id"]),
         hv.link(f"/teams/{team['id']}", team["name"]),
         hv.esc(team["age_group"]),
         str(team["season"]),
         f'<span class="num">{team["player_count"]}</span>',
         hv.link(f"/teams/{team['id']}", "Open roster", "button tiny secondary")]
        for team in teams
    ]

    body = (
        hv.page_title("Teams and rosters", f"{len(teams)} team(s)")
        + hv.help_text(
            "Create a team for a season, place registered players into it, move "
            "players between teams and remove them. Only a player with a completed "
            "registration for the season can be placed in a team."
        )
        + hv.card("Season", '<form method="get" action="/teams" class="inline-form">'
                  + hv.field("season", "Season", season, input_type="number")
                  + '<button type="submit">Apply</button></form>')
        + hv.card("Teams", hv.table(
            ["ID", "Team", "Age group", "Season", "Players", ""], rows))
        + hv.card("Create a team",
                  '<form method="post" action="/teams" class="stack">'
                  + hv.field("name", "Team name", "", required=True,
                             hint="for example: U13 Girls")
                  + hv.field("age_group", "Age group", "", required=True,
                             hint="for example: U13")
                  + hv.field("season", "Season", THEME["season"], input_type="number",
                             required=True)
                  + '<div class="actions"><button type="submit">Create team</button></div>'
                  + "</form>")
    )
    return hv.layout("Teams", body, active="/teams",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", "/teams")
def teams_create(req: Request) -> str:
    team = ts.create_team(req.db, req.get("name"), req.get("age_group"),
                          req.get("season"))
    _set_notice(req, "ok", f"Team {team['name']} created for season {team['season']}.")
    raise Redirect(f"/teams/{team['id']}")


@route("GET", r"/teams/(?P<team_id>\d+)")
def team_detail(req: Request, team_id: str) -> str:
    db = req.db
    team = ts.get_team(db, int(team_id), with_roster=True)
    if team is None:
        return _not_found(req, f"Team {team_id} does not exist")

    roster_rows = [
        [hv.esc(player["squad_number"] or "&mdash;"),
         hv.link(f"/members/{player['id']}", player["full_name"]),
         f'<span class="num">{player["age"]}</span>',
         hv.badge("Under 18", THEME["brand_primary"]) if player["is_minor"]
         else hv.badge("18+", THEME["text_muted"]),
         hv.esc(player["contact"] or "&mdash;"),
         hv.esc(player["contact_for"] or "&mdash;"),
         '<form method="post" action="/teams/remove" class="actions">'
         + hv.hidden("team_id", team["id"])
         + hv.hidden("member_id", player["id"])
         + '<button class="tiny ghost" type="submit">Remove</button></form>']
        for player in team["roster"]
    ]

    on_roster = {p["id"] for p in team["roster"]}
    eligible = [
        r for r in rs.find_registrations(db, season=int(team["season"]), status="complete")
        if r["member_id"] not in on_roster
    ]
    add_form = (
        '<form method="post" action="/teams/add" class="inline-form">'
        + hv.hidden("team_id", team["id"])
        + hv.field("member_id", "Add a registered player", "",
                   options=[("", "&mdash; choose a player &mdash;")]
                   + [(str(r["member_id"]),
                       f"{r['member_name']} ({r['age_group']}, reg {r['id']})")
                      for r in eligible],
                   hint="only players with a completed registration for this season")
        + hv.field("squad_number", "Squad number", "", hint="optional")
        + '<button type="submit">Add to roster</button></form>'
    ) if eligible else hv.empty_state(
        "No further player has a completed registration for this season."
    )

    other_teams = [t for t in ts.find_teams(db, season=int(team["season"]))
                   if t["id"] != team["id"]]
    move_form = (
        '<form method="post" action="/teams/move" class="inline-form">'
        + hv.hidden("from_team_id", team["id"])
        + hv.field("member_id", "Move a player from this team", "",
                   options=[("", "&mdash; choose a player &mdash;")]
                   + [(str(p["id"]), p["full_name"]) for p in team["roster"]])
        + hv.field("to_team_id", "To team", "",
                   options=[("", "&mdash; choose a team &mdash;")]
                   + [(str(t["id"]), f"{t['name']} ({t['age_group']})")
                      for t in other_teams])
        + '<button type="submit">Move player</button></form>'
    ) if team["roster"] and other_teams else hv.empty_state(
        "A move needs at least one player on this roster and a second team in the "
        "same season."
    )

    gaps = ts.roster_contact_gaps(db, team["id"])
    gaps_block = hv.table(
        ["Player", "Problem"],
        [[hv.link(f"/members/{g['member_id']}", g["name"]), hv.esc(g["problem"])]
         for g in gaps],
        caption="Roster quality check — players the coordinator cannot ring.",
    ) if gaps else '<p class="page-help">Every player on this roster has a contact number.</p>'

    body = (
        hv.page_title(team["name"], f"{team['age_group']} &middot; season {team['season']}")
        + '<p class="page-help">' + hv.link("/teams", "&larr; back to teams") + "</p>"
        + hv.card("Roster with contacts",
                  hv.table(["No.", "Player", "Age", "Category", "Contact",
                            "Contact is", ""], roster_rows,
                           caption="For a junior the contact shown is the linked "
                                   "guardian; for an adult it is the player."))
        + f'<div class="grid-2">'
        + hv.card("Add a player", add_form)
        + hv.card("Move a player", move_form)
        + "</div>"
        + hv.card("Contact gaps on this roster", gaps_block)
    )
    return hv.layout(team["name"], body, active="/teams",
                     notice=_pop_notice(req), environment=req.settings.env)


@route("POST", "/teams/add")
def team_add(req: Request) -> str:
    team_id = req.get_int("team_id")
    member_id = req.get_int("member_id")
    if team_id is None or member_id is None:
        _set_notice(req, "error", "Choose a player to add to the roster.")
        raise Redirect("/teams")
    ts.add_player(req.db, int(team_id), int(member_id), req.get("squad_number"))
    _set_notice(req, "ok", "Player added to the roster.")
    raise Redirect(f"/teams/{team_id}")


@route("POST", "/teams/move")
def team_move(req: Request) -> str:
    from_team = req.get_int("from_team_id")
    to_team = req.get_int("to_team_id")
    member_id = req.get_int("member_id")
    if None in (from_team, to_team, member_id):
        _set_notice(req, "error", "Choose a player and a destination team.")
        raise Redirect(f"/teams/{from_team}" if from_team else "/teams")
    ts.move_player(req.db, int(member_id), int(from_team), int(to_team))
    _set_notice(req, "ok", "Player moved to the destination team.")
    raise Redirect(f"/teams/{to_team}")


@route("POST", "/teams/remove")
def team_remove(req: Request) -> str:
    team_id = req.get_int("team_id")
    member_id = req.get_int("member_id")
    ts.remove_player(req.db, int(team_id), int(member_id))
    _set_notice(req, "warn", "Player removed from the roster.")
    raise Redirect(f"/teams/{team_id}")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
@route("GET", "/views")
def views_index(req: Request) -> str:
    db = req.db
    season = req.get_int("season", int(THEME["season"]))
    teams = ts.find_teams(db, season=season)

    roster_rows = []
    for team in teams:
        for player in ts.team_roster(db, team["id"]):
            roster_rows.append([
                hv.link(f"/teams/{team['id']}", team["name"]),
                hv.esc(team["age_group"]),
                hv.link(f"/members/{player['id']}", player["full_name"]),
                hv.esc(player["contact"] or "&mdash;"),
                hv.esc(player["contact_for"] or "&mdash;"),
            ])

    guardians = gs.find_guardians(db)
    guardian_rows = [
        [hv.link(f"/guardians/{g['id']}", g["full_name"]),
         hv.esc(", ".join(f"{c['full_name']} ({c['age']})" for c in g["linked_children"])
                or "&mdash;"),
         f'<span class="num">{g["linked_count"]}</span>']
        for g in guardians
    ]

    members = ms.find_members(db)
    history_rows = []
    for member in members:
        history = rs.registration_history(db, member["id"])
        history_rows.append([
            hv.link(f"/members/{member['id']}", member["full_name"]),
            " &rarr; ".join(
                f"{r['season']}: {r['age_group']} "
                f"<span style=\"color:{THEME['text_muted']}\">({r['status']})</span>"
                for r in history
            ) or "&mdash;",
            f'<span class="num">{len(history)}</span>',
        ])

    body = (
        hv.page_title("Views", f"season {season}")
        + hv.help_text(
            "The three reporting views the club asked for: a team roster with a "
            "contact for every player, a member's registration history, and the "
            "juniors linked to a guardian."
        )
        + hv.card("View 1 &mdash; team roster with a contact for each player",
                  hv.table(["Team", "Age group", "Player", "Contact",
                            "Contact belongs to"], roster_rows))
        + hv.card("View 2 &mdash; the juniors linked to a guardian",
                  hv.table(["Guardian", "Linked players", "Count"], guardian_rows))
        + hv.card("View 3 &mdash; a member's registration history",
                  hv.table(["Member", "Registration history", "Records"], history_rows))
    )
    return hv.layout("Views", body, active="/views",
                     notice=_pop_notice(req), environment=req.settings.env)


# ---------------------------------------------------------------------------
# JSON API (used by tests and by the configuration-management evidence script)
# ---------------------------------------------------------------------------
@route("GET", "/api/health")
def api_health(req: Request) -> str:
    return json.dumps(
        {
            "status": "ok",
            "environment": req.settings.env,
            "database": str(req.settings.db_path.name),
            "schema_version": req.db.current_version(),
            "members": ms.member_count(req.db),
            "rules": [rs.assert_majority_rule_documented()],
        },
        indent=2,
    )


@route("GET", "/api/members")
def api_members(req: Request) -> str:
    return json.dumps(ms.find_members(req.db, req.get("q") or None), indent=2, default=str)


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------
def _set_notice(req: Request, kind: str, message: str) -> None:
    """Record a notice for the page the handler is about to render.

    Redirecting handlers do not need this: a redirect replaces the whole page,
    so the result of a POST is shown on the destination page instead.  This is
    used by handlers that answer a request in place, such as the error page.
    """
    req.notice = (kind, message)


def _pop_notice(req: Request) -> tuple[str, str] | None:
    return req.notice


# ---------------------------------------------------------------------------
# Error rendering
# ---------------------------------------------------------------------------
def _not_found(req: Request, message: str) -> str:
    body = hv.page_title("Not found") + hv.card("Nothing to show here",
                                                f"<p>{hv.esc(message)}</p>")
    return hv.layout("Not found", body, active=req.path,
                     notice=("error", message))


class ClubRequestHandler(BaseHTTPRequestHandler):
    """Translate one HTTP request into a service call and an HTML response."""

    settings: Settings
    server_version = "WarrigalParkFC/1.2"

    # -- request dispatch --------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - required name
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/static/"):
            return self._serve_static(path)

        query = urllib.parse.parse_qs(parsed.query)
        form: dict[str, list[str]] = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            form = urllib.parse.parse_qs(raw)

        db = Database(self.settings.db_path).initialise()
        try:
            request = Request(method, path, query, form, db, self.settings)
            for route_method, pattern, handler in ROUTES:
                if route_method != method:
                    continue
                match = pattern.match(path)
                if not match:
                    continue
                try:
                    html = handler(request, **match.groupdict())
                except Redirect as redirect:
                    return self._send_redirect(redirect.location, request)
                except (ValidationError, BusinessRuleError) as exc:
                    LOGGER.info("rejected %s %s: %s", method, path, exc)
                    return self._send_error_page(request, exc)
                return self._send_html(html)
            self._send_redirect("/", None)
        except Exception:  # pragma: no cover - safety net
            LOGGER.error("unhandled error on %s %s\n%s", method, path,
                         traceback.format_exc())
            self._send_plain(HTTPStatus.INTERNAL_SERVER_ERROR,
                             "An unexpected error occurred. See the server log.")
        finally:
            db.close()

    # -- responses ---------------------------------------------------------
    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _send_plain(self, status: HTTPStatus, text: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_redirect(self, location: str, request: Request | None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error_page(self, request: Request, exc: Exception) -> None:
        """A refused action is explained on the page, in the registrar's words."""
        message = str(exc)
        if isinstance(exc, BusinessRuleError):
            notice = ("warn", message)
            heading = "The club's rules stopped that action"
            explanation = (
                "This is the system protecting the club's data: the action you "
                "asked for would have broken a rule. Nothing was saved."
            )
        else:
            notice = ("error", message)
            heading = "That did not look right"
            explanation = "Correct the highlighted value and try again. Nothing was saved."

        body = (
            hv.page_title(heading)
            + hv.rule_callout(f"<strong>{hv.esc(message)}</strong>")
            + f'<p class="page-help">{hv.esc(explanation)}</p>'
            + f'<p class="page-help">{hv.link(request.path, "&larr; go back")}</p>'
        )
        html = hv.layout(heading, body, active=request.path, notice=notice,
                         environment=request.settings.env)
        self._send_html(html, HTTPStatus.OK)

    def _serve_static(self, path: str) -> None:
        relative = path[len("/static/"):]
        if ".." in relative or relative.startswith("/"):
            return self._send_plain(HTTPStatus.FORBIDDEN, "forbidden")
        target = (STATIC_DIR / relative).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._send_plain(HTTPStatus.NOT_FOUND, "not found")
        content_types = {".css": "text/css; charset=utf-8",
                         ".js": "application/javascript; charset=utf-8",
                         ".png": "image/png", ".svg": "image/svg+xml",
                         ".ico": "image/x-icon"}
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type",
                         content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if self.settings.debug:
            LOGGER.info("%s - %s", self.address_string(), format % args)


def build_server(settings: Settings, seed_data: bool | None = None) -> ThreadingHTTPServer:
    """Create the HTTP server.  Used by ``run.py`` and by the tests."""
    db = Database(settings.db_path).initialise()
    try:
        if seed_data if seed_data is not None else settings.seed:
            seed(db)
    finally:
        db.close()

    handler = type("BoundClubRequestHandler", (ClubRequestHandler,),
                   {"settings": settings})
    return ThreadingHTTPServer((settings.host, settings.port), handler)


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO if settings.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = build_server(settings)
    url = f"http://{settings.host}:{settings.port}/"
    print("=" * 68)
    print("  Warrigal Park FC - Member Registration & Team Roster System")
    print(f"  {settings.describe()}")
    print(f"  Open this address in a browser:  {url}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 68)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
