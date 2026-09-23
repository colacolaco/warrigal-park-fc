"""Guardian capability.

Supports the club's core data-quality requirement: one guardian record can be
linked to several junior members (siblings), and updating the guardian's contact
details updates every linked child's view of that contact in one step, because
the children reference the guardian record rather than copying it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from models.database import Database
from services.member_service import get_member
from services.validation import (
    BusinessRuleError,
    ValidationError,
    calculate_age,
    is_minor,
    optional_email,
    optional_phone,
    parse_date,
    require_text,
)

RELATIONSHIPS = ("parent", "guardian", "carer", "other")


def _row_to_dict(row: Any, linked: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    guardian = dict(row)
    guardian["full_name"] = f"{guardian['first_name']} {guardian['last_name']}"
    guardian["contact"] = guardian.get("phone") or guardian.get("email") or ""
    guardian["linked_children"] = linked or []
    guardian["linked_count"] = len(guardian["linked_children"])
    return guardian


def create_guardian(db: Database, data: dict[str, Any]) -> dict[str, Any]:
    first_name = require_text(data.get("first_name"), "guardian first name")
    last_name = require_text(data.get("last_name"), "guardian last name")
    relationship = str(data.get("relationship") or "parent").strip().lower()
    if relationship not in RELATIONSHIPS:
        raise ValidationError(
            f"relationship must be one of {', '.join(RELATIONSHIPS)}"
        )
    email = optional_email(data.get("email"))
    phone = optional_phone(data.get("phone"))
    if not email and not phone:
        raise ValidationError(
            "a guardian needs at least one contact method (phone or email)"
        )

    cursor = db.execute(
        """
        INSERT INTO guardian (first_name, last_name, relationship, email, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        (first_name, last_name, relationship, email, phone),
    )
    guardian_id = int(cursor.lastrowid)
    db.audit("guardian", guardian_id, "create", f"{first_name} {last_name}")
    return get_guardian(db, guardian_id)  # type: ignore[return-value]


def get_guardian(db: Database, guardian_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM guardian WHERE id = ?", (guardian_id,))
    if row is None:
        return None
    return _row_to_dict(row, list_juniors_for_guardian(db, guardian_id))


def find_guardians(db: Database, name: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM guardian WHERE 1 = 1"
    params: list[Any] = []
    if name:
        needle = f"%{name.strip()}%"
        sql += (
            " AND (first_name LIKE ? OR last_name LIKE ? "
            "OR (first_name || ' ' || last_name) LIKE ?)"
        )
        params.extend([needle, needle, needle])
    sql += " ORDER BY last_name, first_name"
    return [_row_to_dict(row) for row in db.query(sql, params)]


def update_guardian(db: Database, guardian_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Update a guardian.

    Because linked children are read through ``member_guardian`` rather than
    holding a copy of the contact details, this single UPDATE is immediately
    visible on every linked child's record.  The method returns the list of
    children that were affected so the user interface can confirm the sync.
    """
    current = get_guardian(db, guardian_id)
    if current is None:
        raise ValidationError(f"guardian {guardian_id} does not exist")

    first_name = require_text(data.get("first_name", current["first_name"]), "first name")
    last_name = require_text(data.get("last_name", current["last_name"]), "last name")
    relationship = str(
        data.get("relationship", current["relationship"]) or "parent"
    ).strip().lower()
    if relationship not in RELATIONSHIPS:
        raise ValidationError(
            f"relationship must be one of {', '.join(RELATIONSHIPS)}"
        )
    email = optional_email(data.get("email", current["email"]))
    phone = optional_phone(data.get("phone", current["phone"]))
    if not email and not phone:
        raise ValidationError(
            "a guardian needs at least one contact method (phone or email)"
        )

    db.execute(
        """
        UPDATE guardian
           SET first_name = ?, last_name = ?, relationship = ?, email = ?,
               phone = ?, updated_at = datetime('now')
         WHERE id = ?
        """,
        (first_name, last_name, relationship, email, phone, guardian_id),
    )
    children = list_juniors_for_guardian(db, guardian_id)
    db.audit(
        "guardian",
        guardian_id,
        "update",
        "synced to " + (", ".join(c["full_name"] for c in children) or "no children"),
    )
    return get_guardian(db, guardian_id)  # type: ignore[return-value]


def link_guardian(
    db: Database,
    member_id: int,
    guardian_id: int,
    is_primary: bool = False,
) -> dict[str, Any]:
    """Link a guardian to a member.  Idempotent — linking twice is harmless."""
    member = get_member(db, member_id)
    if member is None:
        raise ValidationError(f"member {member_id} does not exist")
    if get_guardian(db, guardian_id) is None:
        raise ValidationError(f"guardian {guardian_id} does not exist")
    if not member["is_active"]:
        raise BusinessRuleError(
            f"{member['full_name']} is inactive and cannot be given a guardian"
        )

    db.execute(
        """
        INSERT INTO member_guardian (member_id, guardian_id, is_primary)
        VALUES (?, ?, ?)
        ON CONFLICT (member_id, guardian_id)
        DO UPDATE SET is_primary = excluded.is_primary
        """,
        (member_id, guardian_id, 1 if is_primary else 0),
    )
    db.audit(
        "member_guardian",
        member_id,
        "link",
        f"guardian {guardian_id} linked to member {member_id}",
    )
    return get_guardian(db, guardian_id)  # type: ignore[return-value]


def unlink_guardian(db: Database, member_id: int, guardian_id: int) -> None:
    """Remove a link.

    Refused while the member has a pending or complete registration for a
    season they are still a minor in, because that would leave a junior
    registered without a guardian — exactly the compliance failure the club
    wants to prevent.
    """
    member = get_member(db, member_id)
    if member is None:
        raise ValidationError(f"member {member_id} does not exist")

    open_registration = db.query_one(
        """
        SELECT r.season, r.status
          FROM registration r
         WHERE r.member_id = ? AND r.status IN ('started', 'complete')
         ORDER BY r.season DESC
         LIMIT 1
        """,
        (member_id,),
    )
    remaining = db.query_one(
        """
        SELECT COUNT(*) AS n FROM member_guardian
         WHERE member_id = ? AND guardian_id <> ?
        """,
        (member_id, guardian_id),
    )
    remaining_n = int(remaining["n"]) if remaining else 0

    if open_registration is not None and remaining_n == 0 and is_minor(
        parse_date(member["date_of_birth"])
    ):
        raise BusinessRuleError(
            f"{member['full_name']} is under 18 and holds a "
            f"{open_registration['status']} registration for season "
            f"{open_registration['season']}; link another guardian before removing "
            "the last one"
        )

    db.execute(
        "DELETE FROM member_guardian WHERE member_id = ? AND guardian_id = ?",
        (member_id, guardian_id),
    )
    db.audit("member_guardian", member_id, "unlink", f"guardian {guardian_id} removed")


def list_guardians_for_member(db: Database, member_id: int) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT g.*, mg.is_primary
          FROM guardian g
          JOIN member_guardian mg ON mg.guardian_id = g.id
         WHERE mg.member_id = ?
         ORDER BY mg.is_primary DESC, g.last_name, g.first_name
        """,
        (member_id,),
    )
    return [_row_to_dict(row) for row in rows]


def list_juniors_for_guardian(db: Database, guardian_id: int) -> list[dict[str, Any]]:
    """View: every junior linked to a guardian, with the guardian's contact."""
    rows = db.query(
        """
        SELECT m.*, mg.is_primary
          FROM member m
          JOIN member_guardian mg ON mg.member_id = m.id
         WHERE mg.guardian_id = ?
         ORDER BY m.last_name, m.first_name
        """,
        (guardian_id,),
    )
    children = []
    for row in rows:
        child = dict(row)
        child["is_active"] = bool(child["is_active"])
        child["full_name"] = f"{child['first_name']} {child['last_name']}"
        child["age"] = calculate_age(parse_date(child["date_of_birth"]))
        child["is_minor"] = is_minor(parse_date(child["date_of_birth"]))
        children.append(child)
    return children


def has_guardian(db: Database, member_id: int) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM member_guardian WHERE member_id = ?", (member_id,)
    )
    return bool(row and int(row["n"]) > 0)
