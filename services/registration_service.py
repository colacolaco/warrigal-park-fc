"""Registration capability — and the club's most important business rule.

Business rule (Project Charter, section 3.3):

    A player under 18 cannot complete registration unless at least one guardian
    record is linked; otherwise the registration is refused with a reason.

The rule is enforced in exactly one place, :func:`complete_registration`, so it
cannot be bypassed by calling a different entry point.  ``tests/test_guardian_rule.py``
tests this file directly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from models.database import Database
from services.guardian_service import has_guardian
from services.member_service import get_member
from services.validation import (
    AGE_OF_MAJORITY,
    BusinessRuleError,
    ValidationError,
    age_group_for,
    calculate_age,
    is_minor,
    parse_date,
    require_text,
)

STATUSES = ("started", "complete", "withdrawn")

# The reason text is part of the requirement: the registrar must be told *why*
# a registration was refused, not merely that it failed.
REFUSAL_NO_GUARDIAN = (
    "Registration refused: {name} is under 18 (age {age} on {on}) and has no "
    "linked guardian. Link a parent or guardian record, then complete the "
    "registration again."
)


def _row_to_dict(db: Database, row: Any) -> dict[str, Any]:
    registration = dict(row)
    member = get_member(db, registration["member_id"])
    registration["member"] = member
    registration["member_name"] = member["full_name"] if member else "unknown"
    registration["age_at_registration"] = member["age"] if member else None
    return registration


def start_registration(
    db: Database,
    member_id: int,
    season: int,
    age_group: str | None = None,
) -> dict[str, Any]:
    """Open a registration in ``started`` status.

    Starting a registration never requires a guardian — only *completing* it
    does.  This lets the registrar capture a walk-in on sign-on day and chase
    the guardian paperwork afterwards.
    """
    member = get_member(db, member_id)
    if member is None:
        raise ValidationError(f"member {member_id} does not exist")
    if not member["is_active"]:
        raise BusinessRuleError(
            f"{member['full_name']} is inactive; reactivate the member before "
            "registering them for a season"
        )

    season = _validate_season(season)
    existing = db.query_one(
        "SELECT * FROM registration WHERE member_id = ? AND season = ?",
        (member_id, season),
    )
    if existing is not None:
        raise BusinessRuleError(
            f"{member['full_name']} already has a "
            f"{existing['status']} registration for season {season}"
        )

    group = age_group or age_group_for(parse_date(member["date_of_birth"]))
    cursor = db.execute(
        """
        INSERT INTO registration (member_id, season, age_group, status)
        VALUES (?, ?, ?, 'started')
        """,
        (member_id, season, require_text(group, "age group", 20)),
    )
    registration_id = int(cursor.lastrowid)
    db.audit("registration", registration_id, "start", f"season {season} {group}")
    return get_registration(db, registration_id)  # type: ignore[return-value]


def get_registration(db: Database, registration_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM registration WHERE id = ?", (registration_id,))
    return _row_to_dict(db, row) if row else None


def find_registrations(
    db: Database,
    season: int | None = None,
    status: str | None = None,
    age_group: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM registration WHERE 1 = 1"
    params: list[Any] = []
    if season is not None:
        sql += " AND season = ?"
        params.append(_validate_season(season))
    if status:
        status = status.strip().lower()
        if status not in STATUSES:
            raise ValidationError(f"status must be one of {', '.join(STATUSES)}")
        sql += " AND status = ?"
        params.append(status)
    if age_group:
        sql += " AND age_group = ?"
        params.append(age_group)
    sql += " ORDER BY season DESC, age_group, member_id"
    return [_row_to_dict(db, row) for row in db.query(sql, params)]


def complete_registration(
    db: Database,
    registration_id: int,
    age_group: str | None = None,
    on: date | None = None,
) -> dict[str, Any]:
    """Complete a registration, enforcing the under-18 guardian rule.

    :param on: the date the registration is being completed.  The club records
        the player's age *on this date* (Confluence decision record D-004), so
        a player who turns 18 mid-season is judged by their age at registration.

    :raises BusinessRuleError: when the player is under 18 and has no guardian.
        The registration is left in ``started`` status and
        ``refusal_reason`` is stored, so the registrar can see why.
    """
    registration = get_registration(db, registration_id)
    if registration is None:
        raise ValidationError(f"registration {registration_id} does not exist")
    if registration["status"] == "complete":
        raise BusinessRuleError("this registration is already complete")
    if registration["status"] == "withdrawn":
        raise BusinessRuleError(
            "this registration was withdrawn; start a new registration instead"
        )

    member = registration["member"]
    if member is None:
        raise ValidationError("the member for this registration no longer exists")

    on = on or date.today()
    date_of_birth = parse_date(member["date_of_birth"])
    age = calculate_age(date_of_birth, on)

    # ---------------- the business rule ----------------
    if is_minor(date_of_birth, on) and not has_guardian(db, member["id"]):
        reason = REFUSAL_NO_GUARDIAN.format(
            name=member["full_name"], age=age, on=on.isoformat()
        )
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE registration
                   SET refusal_reason = ?, updated_at = datetime('now')
                 WHERE id = ?
                """,
                (reason, registration_id),
            )
            conn.execute(
                "INSERT INTO audit_log (entity, entity_id, action, detail) "
                "VALUES ('registration', ?, 'refuse', ?)",
                (registration_id, reason),
            )
        raise BusinessRuleError(reason)
    # ---------------------------------------------------

    group = age_group or registration["age_group"]
    if age_group is None:
        # Keep the stored age group sensible for a player whose age moved.
        group = age_group_for(date_of_birth, on)

    with db.transaction() as conn:
        conn.execute(
            """
            UPDATE registration
               SET status = 'complete', age_group = ?, refusal_reason = NULL,
                   updated_at = datetime('now')
             WHERE id = ?
            """,
            (group, registration_id),
        )
        conn.execute(
            "INSERT INTO audit_log (entity, entity_id, action, detail) "
            "VALUES ('registration', ?, 'complete', ?)",
            (registration_id, f"age {age} on {on.isoformat()}, group {group}"),
        )
    return get_registration(db, registration_id)  # type: ignore[return-value]


def amend_registration(
    db: Database,
    registration_id: int,
    age_group: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Amend the age group or status of an existing registration."""
    registration = get_registration(db, registration_id)
    if registration is None:
        raise ValidationError(f"registration {registration_id} does not exist")

    new_group = registration["age_group"]
    if age_group:
        new_group = require_text(age_group, "age group", 20)

    if status:
        status = status.strip().lower()
        if status not in STATUSES:
            raise ValidationError(f"status must be one of {', '.join(STATUSES)}")
        if status == "complete":
            # Re-route through the rule so amending cannot bypass it.
            complete_registration(db, registration_id, age_group=new_group)
            return get_registration(db, registration_id)  # type: ignore[return-value]

    db.execute(
        """
        UPDATE registration
           SET age_group = ?, status = ?, updated_at = datetime('now')
         WHERE id = ?
        """,
        (new_group, status or registration["status"], registration_id),
    )
    db.audit(
        "registration",
        registration_id,
        "amend",
        f"age_group={new_group} status={status or registration['status']}",
    )
    return get_registration(db, registration_id)  # type: ignore[return-value]


def withdraw_registration(
    db: Database, registration_id: int, reason: str = ""
) -> dict[str, Any]:
    """Withdraw a registration (the player is no longer registering this season)."""
    registration = get_registration(db, registration_id)
    if registration is None:
        raise ValidationError(f"registration {registration_id} does not exist")

    db.execute(
        """
        UPDATE registration
           SET status = 'withdrawn', refusal_reason = ?, updated_at = datetime('now')
         WHERE id = ?
        """,
        (reason or "withdrawn by the registrar", registration_id),
    )
    db.audit("registration", registration_id, "withdraw", reason or "not supplied")
    return get_registration(db, registration_id)  # type: ignore[return-value]


def registration_history(db: Database, member_id: int) -> list[dict[str, Any]]:
    """View: a member's complete registration history, newest season first."""
    rows = db.query(
        "SELECT * FROM registration WHERE member_id = ? ORDER BY season DESC",
        (member_id,),
    )
    return [_row_to_dict(db, row) for row in rows]


def _validate_season(season: object) -> int:
    try:
        value = int(str(season).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError("season must be a four-digit year, for example 2026") from exc
    if not 2000 <= value <= 2100:
        raise ValidationError("season must be between 2000 and 2100")
    return value


def summarise_season(db: Database, season: int, on: date | None = None) -> dict[str, Any]:
    """View: registration totals by age group and gender (club president's report)."""
    season = _validate_season(season)
    rows = db.query(
        """
        SELECT r.age_group, m.gender, r.status, COUNT(*) AS n
          FROM registration r
          JOIN member m ON m.id = r.member_id
         WHERE r.season = ?
         GROUP BY r.age_group, m.gender, r.status
        """,
        (season,),
    )
    by_group: dict[str, dict[str, int]] = {}
    by_gender: dict[str, int] = {"F": 0, "M": 0, "U": 0}
    total = 0
    for row in rows:
        count = int(row["n"])
        group = by_group.setdefault(
            row["age_group"], {"complete": 0, "started": 0, "withdrawn": 0}
        )
        group[row["status"]] = group.get(row["status"], 0) + count
        if row["status"] == "complete":
            by_gender[row["gender"]] = by_gender.get(row["gender"], 0) + count
            total += count
    return {
        "season": season,
        "by_age_group": by_group,
        "completed_by_gender": by_gender,
        "completed_total": total,
    }


def assert_majority_rule_documented() -> str:
    """Small self-documenting helper used by the report screenshots."""
    return (
        f"Members under {AGE_OF_MAJORITY} require a linked guardian to complete "
        "registration (decision record D-004: age is judged on the date the "
        "registration is completed)."
    )
