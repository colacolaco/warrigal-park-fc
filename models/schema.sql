-- ---------------------------------------------------------------------------
-- Warrigal Park FC — Member Registration & Team Roster System
-- Database schema, version 1.2.0
--
-- Design notes
--   * A member is a person registered with the club (junior or senior).
--   * A guardian is an adult contact.  One guardian may be linked to many
--     juniors through the member_guardian link table (many-to-many, because a
--     junior may have more than one guardian and siblings share guardians).
--   * A registration ties a member to a season with a lifecycle status.
--   * A team belongs to a season and an age group; team_member places
--     registered players into teams.
-- ---------------------------------------------------------------------------

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- --------------------------------------------------------------------------
-- Member
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    date_of_birth   TEXT    NOT NULL,              -- ISO-8601 YYYY-MM-DD
    email           TEXT,
    phone           TEXT,
    gender          TEXT    NOT NULL DEFAULT 'U'
                            CHECK (gender IN ('F', 'M', 'U')),
    is_active       INTEGER NOT NULL DEFAULT 1
                            CHECK (is_active IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_member_name
    ON member (last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_member_active
    ON member (is_active);

-- --------------------------------------------------------------------------
-- Guardian
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guardian (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    relationship    TEXT    NOT NULL DEFAULT 'parent'
                            CHECK (relationship IN
                                   ('parent', 'guardian', 'carer', 'other')),
    email           TEXT,
    phone           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_guardian_name
    ON guardian (last_name, first_name);

-- Many-to-many: a junior may have several guardians, siblings share guardians.
CREATE TABLE IF NOT EXISTS member_guardian (
    member_id       INTEGER NOT NULL REFERENCES member (id) ON DELETE CASCADE,
    guardian_id     INTEGER NOT NULL REFERENCES guardian (id) ON DELETE CASCADE,
    is_primary      INTEGER NOT NULL DEFAULT 0
                            CHECK (is_primary IN (0, 1)),
    linked_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (member_id, guardian_id)
);

CREATE INDEX IF NOT EXISTS idx_member_guardian_guardian
    ON member_guardian (guardian_id);

-- --------------------------------------------------------------------------
-- Registration
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id       INTEGER NOT NULL REFERENCES member (id) ON DELETE CASCADE,
    season          INTEGER NOT NULL,
    age_group       TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'started'
                            CHECK (status IN
                                   ('started', 'complete', 'withdrawn')),
    refusal_reason  TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (member_id, season)
);

CREATE INDEX IF NOT EXISTS idx_registration_season
    ON registration (season, age_group);

-- --------------------------------------------------------------------------
-- Team and roster
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    age_group       TEXT    NOT NULL,
    season          INTEGER NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, season)
);

CREATE TABLE IF NOT EXISTS team_member (
    team_id         INTEGER NOT NULL REFERENCES team (id) ON DELETE CASCADE,
    member_id       INTEGER NOT NULL REFERENCES member (id) ON DELETE CASCADE,
    squad_number    TEXT,
    joined_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_team_member_member
    ON team_member (member_id);

-- --------------------------------------------------------------------------
-- Audit trail — written by every service on every state change, so the
-- change log can be reconstructed from the database as well as from Git.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    entity          TEXT    NOT NULL,
    entity_id       INTEGER,
    action          TEXT    NOT NULL,
    detail          TEXT
);
