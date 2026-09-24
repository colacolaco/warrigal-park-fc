"""Team and roster capability.

Creates a team for a season, places registered players into it, moves players
between teams and removes them.  A player can only be placed in a team if they
hold a completed registration for that season — this is the second genuine
business rule in the application, and it is what stops the registrar building a
roster out of players who never finished signing on.
"""

from __future__ import annotations

from typing import Any

from models.database import Database
from services.member_service import get_member
from services.validation import (
    BusinessRuleError,
    ValidationError,
    calculate_age,
    is_minor,
    parse_date,
    require_text,
)


def _team_to_dict(db: Database, row: Any, with_roster: bool = False) -> dict[str, Any]:
    team = dict(row)
    count = db.query_one(
        "SELECT COUNT(*) AS n FROM team_member WHERE team_id = ?", (team["id"],)
    )
    team["player_count"] = int(count["n"]) if count else 0
    if with_roster:
        team["roster"] = team_roster(db, team["id"])
    return team


def create_team(
    db: Database, name: str, age_group: str, season: int | str
) -> dict[str, Any]:
    name = require_text(name, "team name", 60)
    age_group = require_text(age_group, "age group", 20)
    try:
        season_number = int(str(season).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError("season must be a four-digit year") from exc
    if not 2000 <= season_number <= 2100:
        raise ValidationError("season must be between 2000 and 2100")

    existing = db.query_one(
        "SELECT id FROM team WHERE name = ? AND season = ?", (name, season_number)
    )
    if existing is not None:
        raise BusinessRuleError(
            f"team {name!r} already exists for season {season_number}"
        )

    cursor = db.execute(
        "INSERT INTO team (name, age_group, season) VALUES (?, ?, ?)",
        (name, age_group, season_number),
    )
    team_id = int(cursor.lastrowid)
    db.audit("team", team_id, "create", f"{name} {age_group} season {season_number}")
    return get_team(db, team_id)  # type: ignore[return-value]


def get_team(db: Database, team_id: int, with_roster: bool = False) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM team WHERE id = ?", (team_id,))
    return _team_to_dict(db, row, with_roster) if row else None


def find_teams(
    db: Database, season: int | None = None, age_group: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM team WHERE 1 = 1"
    params: list[Any] = []
    if season is not None:
        sql += " AND season = ?"
        params.append(int(season))
    if age_group:
        sql += " AND age_group = ?"
        params.append(age_group)
    sql += " ORDER BY season DESC, age_group, name"
    return [_team_to_dict(db, row) for row in db.query(sql, params)]


def _require_completed_registration(db: Database, member_id: int, season: int) -> None:
    row = db.query_one(
        "SELECT status FROM registration WHERE member_id = ? AND season = ?",
        (member_id, season),
    )
    if row is None:
        raise BusinessRuleError(
            "the player has no registration for this season; register them first"
        )
    if row["status"] != "complete":
        raise BusinessRuleError(
            f"the player's registration for this season is '{row['status']}'; "
            "only a completed registration can be placed in a team"
        )


def add_player(
    db: Database, team_id: int, member_id: int, squad_number: str | None = None
) -> dict[str, Any]:
    """Place a registered player into a team."""
    team = get_team(db, team_id)
    if team is None:
        raise ValidationError(f"team {team_id} does not exist")
    member = get_member(db, member_id)
    if member is None:
        raise ValidationError(f"member {member_id} does not exist")
    if not member["is_active"]:
        raise BusinessRuleError(f"{member['full_name']} is inactive")

    _require_completed_registration(db, member_id, int(team["season"]))

    already = db.query_one(
        "SELECT team_id FROM team_member WHERE team_id = ? AND member_id = ?",
        (team_id, member_id),
    )
    if already is not None:
        return get_team(db, team_id, with_roster=True)  # type: ignore[return-value]

    db.execute(
        "INSERT INTO team_member (team_id, member_id, squad_number) VALUES (?, ?, ?)",
        (team_id, member_id, (squad_number or "").strip() or None),
    )
    db.audit("team_member", team_id, "add", f"member {member_id} -> team {team_id}")
    return get_team(db, team_id, with_roster=True)  # type: ignore[return-value]


def move_player(db: Database, member_id: int, from_team_id: int, to_team_id: int) -> dict[str, Any]:
    """Move a player between teams, keeping the roster of both teams correct."""
    if from_team_id == to_team_id:
        raise ValidationError("the source and destination team are the same")
    source = get_team(db, from_team_id)
    target = get_team(db, to_team_id)
    if source is None:
        raise ValidationError(f"team {from_team_id} does not exist")
    if target is None:
        raise ValidationError(f"team {to_team_id} does not exist")
    if str(source["season"]) != str(target["season"]):
        raise BusinessRuleError(
            "a player can only be moved between teams in the same season"
        )

    present = db.query_one(
        "SELECT 1 FROM team_member WHERE team_id = ? AND member_id = ?",
        (from_team_id, member_id),
    )
    if present is None:
        raise BusinessRuleError("the player is not in the source team")

    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM team_member WHERE team_id = ? AND member_id = ?",
            (from_team_id, member_id),
        )
        conn.execute(
            "INSERT INTO team_member (team_id, member_id) VALUES (?, ?)",
            (to_team_id, member_id),
        )
        conn.execute(
            "INSERT INTO audit_log (entity, entity_id, action, detail) "
            "VALUES ('team_member', ?, 'move', ?)",
            (member_id, f"team {from_team_id} -> team {to_team_id}"),
        )
    return get_team(db, to_team_id, with_roster=True)  # type: ignore[return-value]


def remove_player(db: Database, team_id: int, member_id: int) -> dict[str, Any]:
    team = get_team(db, team_id)
    if team is None:
        raise ValidationError(f"team {team_id} does not exist")
    present = db.query_one(
        "SELECT 1 FROM team_member WHERE team_id = ? AND member_id = ?",
        (team_id, member_id),
    )
    if present is None:
        raise BusinessRuleError("the player is not in this team")
    db.execute(
        "DELETE FROM team_member WHERE team_id = ? AND member_id = ?",
        (team_id, member_id),
    )
    db.audit("team_member", team_id, "remove", f"member {member_id}")
    return get_team(db, team_id, with_roster=True)  # type: ignore[return-value]


def team_roster(db: Database, team_id: int) -> list[dict[str, Any]]:
    """View: a team's roster, with a contact for every player.

    The contact shown is the player's own phone when they are an adult, and the
    first linked guardian's phone for a junior — which is what the junior
    coordinator actually needs when standing on the sideline at 7pm.
    """
    rows = db.query(
        """
        SELECT m.id, m.first_name, m.last_name, m.date_of_birth, m.phone,
               m.email, m.is_active, tm.squad_number,
               (SELECT g.first_name || ' ' || g.last_name
                  FROM guardian g
                  JOIN member_guardian mg ON mg.guardian_id = g.id
                 WHERE mg.member_id = m.id
                 ORDER BY mg.is_primary DESC, g.id
                 LIMIT 1) AS guardian_name,
               (SELECT COALESCE(g.phone, g.email)
                  FROM guardian g
                  JOIN member_guardian mg ON mg.guardian_id = g.id
                 WHERE mg.member_id = m.id
                 ORDER BY mg.is_primary DESC, g.id
                 LIMIT 1) AS guardian_contact
          FROM member m
          JOIN team_member tm ON tm.member_id = m.id
         WHERE tm.team_id = ?
         ORDER BY m.last_name, m.first_name
        """,
        (team_id,),
    )
    roster = []
    for row in rows:
        player = dict(row)
        player["full_name"] = f"{player['first_name']} {player['last_name']}"
        date_of_birth = parse_date(player["date_of_birth"])
        player["age"] = calculate_age(date_of_birth)
        player["is_minor"] = is_minor(date_of_birth)
        if player["is_minor"]:
            player["contact"] = player["guardian_contact"] or ""
            player["contact_for"] = player["guardian_name"] or ""
        else:
            player["contact"] = player["phone"] or player["email"] or ""
            player["contact_for"] = "player"
        roster.append(player)
    return roster


def roster_contact_gaps(db: Database, team_id: int) -> list[dict[str, Any]]:
    """Quality check: players on a roster for whom no contact can be shown."""
    return [
        {
            "member_id": player["id"],
            "name": player["full_name"],
            "problem": "no guardian contact on file"
            if player["is_minor"]
            else "no contact number on file",
        }
        for player in team_roster(db, team_id)
        if not player["contact"]
    ]
