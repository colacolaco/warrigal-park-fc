"""Fictitious sample data.

Every name, phone number and email address below is invented.  The Project
Charter's compliance constraint forbids using any real child's details, and the
club's own preference is that the sample data resembles a real sign-on day as
closely as possible so that the registrar can be trained on it.
"""

from __future__ import annotations

from models.database import Database

SEASON = 2026

# (first, last, date of birth, gender, phone, email)
MEMBERS = [
    # Juniors, as at the February 2026 sign-on day
    ("Jayden", "Marsh", "2014-03-08", "M", None, None),
    ("Jayden", "Marsh", "2013-11-02", "M", None, None),          # same-name player
    ("Ava", "Nguyen", "2015-06-21", "F", None, None),
    ("Liam", "Nguyen", "2017-01-30", "M", None, None),           # sibling
    ("Ruby", "Middleton", "2012-09-14", "F", None, None),
    ("Noah", "Petrov", "2011-04-17", "M", None, None),
    ("Isla", "Okafor", "2016-08-05", "F", None, None),
    ("Cooper", "Buchanan", "2010-12-19", "M", "0400 111 222", None),
    ("Mia", "Delacroix", "2013-02-27", "F", None, None),
    ("Ethan", "Whitlam", "2009-07-11", "M", "0400 333 444", None),
    # Seniors, registering in their own right
    ("Grace", "Ferraro", "2003-05-02", "F", "0400 555 666", "grace.ferraro@example.com"),
    ("Tom", "Halloran", "1998-10-25", "M", "0400 777 888", None),
    ("Priya", "Raman", "2001-01-09", "F", "0400 999 000", "priya.raman@example.com"),
    ("Nathan", "Okonjo", "1995-03-30", "M", "0401 234 567", None),
]

GUARDIANS = [
    ("Sandra", "Marsh", "parent", "0412 000 101", "sandra.marsh@example.com"),
    ("Peter", "Marsh", "parent", "0412 000 102", None),
    ("Thao", "Nguyen", "parent", "0412 000 201", "thao.nguyen@example.com"),
    ("Daniel", "Middleton", "parent", "0412 000 301", None),
    ("Elena", "Petrov", "parent", "0412 000 401", "elena.petrov@example.com"),
    ("Chidi", "Okafor", "guardian", "0412 000 501", None),
    ("Marion", "Buchanan", "parent", "0412 000 601", None),
    ("Sophie", "Delacroix", "parent", "0412 000 701", "sophie.delacroix@example.com"),
    ("Andrew", "Whitlam", "parent", "0412 000 801", None),
]

# member index (0-based, in the order above) -> list of guardian indexes
LINKS = [
    (0, [0, 1]),        # Jayden Marsh (2014)  -> Sandra + Peter
    (1, [0, 1]),        # Jayden Marsh (2013)  -> same guardians: siblings
    (2, [2]),           # Ava Nguyen           -> Thao
    (3, [2]),           # Liam Nguyen          -> Thao, sibling of Ava
    (4, [3]),           # Ruby Middleton       -> Daniel
    (5, [4]),           # Noah Petrov          -> Elena
    (6, [5]),           # Isla Okafor          -> Chidi (a guardian, not a parent)
    (7, [6]),           # Cooper Buchanan      -> Marion
    (8, [7]),           # Mia Delacroix        -> Sophie
    (9, [8]),           # Ethan Whitlam        -> Andrew
]

# Members who hold a started registration but still have no guardian: this is
# the walk-in case the registrar hits on sign-on day.
STARTED_WITHOUT_GUARDIAN = [("Tyler", "Brennan", "2015-10-12", "M")]

# Completed registrations, by member index and age group
COMPLETED = {
    0: "U11", 1: "U12", 2: "U10", 3: "U9", 4: "U13", 5: "U14",
    6: "U10", 7: "U15", 8: "U13", 9: "U16",
    10: "Seniors", 11: "Seniors", 12: "Seniors", 13: "Seniors",
}

TEAMS = [
    ("U13 Girls", "U13", SEASON),
    ("U13 Mixed", "U13", SEASON),
    ("U15 Mixed", "U15", SEASON),
    ("Seniors Women", "Seniors", SEASON),
    ("Seniors Men", "Seniors", SEASON),
]

# (team index, member index, squad number)
ROSTERS = [
    (0, 4, "7"),    # Ruby Middleton  -> U13 Girls
    (0, 8, "11"),   # Mia Delacroix   -> U13 Girls
    (1, 2, "3"),    # Ava Nguyen      -> U13 Mixed
    (1, 0, "9"),    # Jayden Marsh    -> U13 Mixed
    (2, 5, "5"),    # Noah Petrov     -> U15 Mixed
    (2, 7, "1"),    # Cooper Buchanan -> U15 Mixed
    (2, 9, "10"),   # Ethan Whitlam   -> U15 Mixed
    (3, 10, "4"),   # Grace Ferraro   -> Seniors Women
    (3, 12, "8"),   # Priya Raman     -> Seniors Women
    (4, 11, "6"),   # Tom Halloran    -> Seniors Men
    (4, 13, "2"),   # Nathan Okonjo   -> Seniors Men
]


def seed(db: Database, force: bool = False) -> bool:
    """Load the sample data.  Returns ``True`` when data was inserted.

    The function is idempotent: it does nothing when the member table already
    holds records, so restarting the server never duplicates the roster.
    """
    existing = db.query_one("SELECT COUNT(*) AS n FROM member")
    if existing and int(existing["n"]) > 0 and not force:
        return False

    member_ids: list[int] = []
    for first, last, dob, gender, phone, email in MEMBERS:
        cursor = db.execute(
            """
            INSERT INTO member (first_name, last_name, date_of_birth, gender,
                                phone, email)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (first, last, dob, gender, phone, email),
        )
        member_ids.append(int(cursor.lastrowid))

    extra_ids: list[int] = []
    for first, last, dob, gender in STARTED_WITHOUT_GUARDIAN:
        cursor = db.execute(
            """
            INSERT INTO member (first_name, last_name, date_of_birth, gender)
            VALUES (?, ?, ?, ?)
            """,
            (first, last, dob, gender),
        )
        extra_ids.append(int(cursor.lastrowid))

    guardian_ids: list[int] = []
    for first, last, relationship, phone, email in GUARDIANS:
        cursor = db.execute(
            """
            INSERT INTO guardian (first_name, last_name, relationship, phone, email)
            VALUES (?, ?, ?, ?, ?)
            """,
            (first, last, relationship, phone, email),
        )
        guardian_ids.append(int(cursor.lastrowid))

    for member_index, guardian_indexes in LINKS:
        for position, guardian_index in enumerate(guardian_indexes):
            db.execute(
                """
                INSERT OR IGNORE INTO member_guardian (member_id, guardian_id, is_primary)
                VALUES (?, ?, ?)
                """,
                (member_ids[member_index], guardian_ids[guardian_index],
                 1 if position == 0 else 0),
            )

    # Completed registrations — all the players above are juniors or adults who
    # registered in their own right, so every one of them may be completed.
    registration_ids: dict[int, int] = {}
    for member_index, age_group in COMPLETED.items():
        cursor = db.execute(
            """
            INSERT INTO registration (member_id, season, age_group, status)
            VALUES (?, ?, ?, 'complete')
            """,
            (member_ids[member_index], SEASON, age_group),
        )
        registration_ids[member_index] = int(cursor.lastrowid)

    # The walk-in case: a started registration with no guardian, which the
    # under-18 rule will refuse to complete until a guardian is linked.
    for member_id in extra_ids:
        db.execute(
            """
            INSERT INTO registration (member_id, season, age_group, status)
            VALUES (?, ?, 'U11', 'started')
            """,
            (member_id, SEASON),
        )

    team_ids: list[int] = []
    for name, age_group, season in TEAMS:
        cursor = db.execute(
            "INSERT INTO team (name, age_group, season) VALUES (?, ?, ?)",
            (name, age_group, season),
        )
        team_ids.append(int(cursor.lastrowid))

    for team_index, member_index, squad_number in ROSTERS:
        db.execute(
            """
            INSERT OR IGNORE INTO team_member (team_id, member_id, squad_number)
            VALUES (?, ?, ?)
            """,
            (team_ids[team_index], member_ids[member_index], squad_number),
        )

    db.audit("system", None, "seed", f"loaded fictitious sample data for {SEASON}")
    return True
