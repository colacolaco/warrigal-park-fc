"""Member capability — create, find, update and deactivate player records."""

from __future__ import annotations

from datetime import date
from typing import Any

from models.database import Database
from services.validation import (
    ValidationError,
    age_group_for,
    calculate_age,
    optional_email,
    optional_phone,
    parse_date,
    parse_gender,
    require_text,
)

FIELDS = ("id", "first_name", "last_name", "date_of_birth", "email", "phone",
          "gender", "is_active", "created_at", "updated_at")


def _row_to_dict(row: Any) -> dict[str, Any]:
    member = dict(row)
    member["is_active"] = bool(member["is_active"])
    member["full_name"] = f"{member['first_name']} {member['last_name']}"
    member["age"] = calculate_age(parse_date(member["date_of_birth"]))
    member["suggested_age_group"] = age_group_for(parse_date(member["date_of_birth"]))
    return member


def create_member(db: Database, data: dict[str, Any]) -> dict[str, Any]:
    """Create a member.  Raises :class:`ValidationError` on bad input."""
    first_name = require_text(data.get("first_name"), "first name")
    last_name = require_text(data.get("last_name"), "last name")
    date_of_birth = parse_date(data.get("date_of_birth"), "date of birth")
    if date_of_birth > date.today():
        raise ValidationError("date of birth cannot be in the future")

    cursor = db.execute(
        """
        INSERT INTO member (first_name, last_name, date_of_birth, email, phone, gender)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            first_name,
            last_name,
            date_of_birth.isoformat(),
            optional_email(data.get("email")),
            optional_phone(data.get("phone")),
            parse_gender(data.get("gender")),
        ),
    )
    member_id = int(cursor.lastrowid)
    db.audit("member", member_id, "create", f"{first_name} {last_name}")
    return get_member(db, member_id)  # type: ignore[return-value]


def get_member(db: Database, member_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM member WHERE id = ?", (member_id,))
    return _row_to_dict(row) if row else None


def find_members(
    db: Database,
    name: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """Search by name.

    Both the first and last name are matched, so searching ``"Marsh"`` finds
    ``Jayden Marsh`` and searching ``"Jayden"`` finds him too.  Players who
    share a name are all returned — the club's requirement that same-name
    players can be told apart is served by returning the date of birth and the
    record id alongside each result.
    """
    sql = "SELECT * FROM member WHERE 1 = 1"
    params: list[Any] = []
    if not include_inactive:
        sql += " AND is_active = 1"
    if name:
        needle = f"%{name.strip()}%"
        sql += (
            " AND (first_name LIKE ? OR last_name LIKE ? "
            "OR (first_name || ' ' || last_name) LIKE ?)"
        )
        params.extend([needle, needle, needle])
    sql += " ORDER BY last_name, first_name, date_of_birth"
    return [_row_to_dict(row) for row in db.query(sql, params)]


def update_member(db: Database, member_id: int, data: dict[str, Any]) -> dict[str, Any]:
    current = get_member(db, member_id)
    if current is None:
        raise ValidationError(f"member {member_id} does not exist")

    first_name = require_text(data.get("first_name", current["first_name"]), "first name")
    last_name = require_text(data.get("last_name", current["last_name"]), "last name")
    date_of_birth = parse_date(
        data.get("date_of_birth", current["date_of_birth"]), "date of birth"
    )
    email = optional_email(data.get("email", current["email"]))
    phone = optional_phone(data.get("phone", current["phone"]))
    gender = parse_gender(data.get("gender", current["gender"]))

    db.execute(
        """
        UPDATE member
           SET first_name = ?, last_name = ?, date_of_birth = ?, email = ?,
               phone = ?, gender = ?, updated_at = datetime('now')
         WHERE id = ?
        """,
        (first_name, last_name, date_of_birth.isoformat(), email, phone, gender, member_id),
    )
    db.audit("member", member_id, "update", f"{first_name} {last_name}")
    return get_member(db, member_id)  # type: ignore[return-value]


def deactivate_member(db: Database, member_id: int, reason: str = "") -> dict[str, Any]:
    """Soft delete: the record is kept for history, but the member is inactive.

    Hard deletion is deliberately *not* offered — a player's registration
    history must survive them leaving the club.
    """
    current = get_member(db, member_id)
    if current is None:
        raise ValidationError(f"member {member_id} does not exist")
    if not current["is_active"]:
        return current
    db.execute(
        "UPDATE member SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
        (member_id,),
    )
    db.audit("member", member_id, "deactivate", reason or "not supplied")
    return get_member(db, member_id)  # type: ignore[return-value]


def reactivate_member(db: Database, member_id: int) -> dict[str, Any]:
    current = get_member(db, member_id)
    if current is None:
        raise ValidationError(f"member {member_id} does not exist")
    db.execute(
        "UPDATE member SET is_active = 1, updated_at = datetime('now') WHERE id = ?",
        (member_id,),
    )
    db.audit("member", member_id, "reactivate")
    return get_member(db, member_id)  # type: ignore[return-value]


def member_count(db: Database, include_inactive: bool = False) -> int:
    sql = "SELECT COUNT(*) AS n FROM member"
    if not include_inactive:
        sql += " WHERE is_active = 1"
    row = db.query_one(sql)
    return int(row["n"]) if row else 0
