-- Internship Task Tracking System : SQLite schema
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    leader_id   INTEGER REFERENCES interns(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'team_lead')),
    team_id       INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS interns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    dit_id       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email        TEXT NOT NULL,
    phone        TEXT NOT NULL,
    college      TEXT NOT NULL,
    role         TEXT NOT NULL,
    joining_date TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS team_members (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id   INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    intern_id INTEGER NOT NULL UNIQUE REFERENCES interns(id) ON DELETE CASCADE,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_code        TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    description      TEXT,
    intern_id        INTEGER NOT NULL REFERENCES interns(id) ON DELETE CASCADE,
    assigned_date    TEXT NOT NULL,
    due_date         TEXT NOT NULL,
    submission_date  TEXT,
    status           TEXT NOT NULL DEFAULT 'Not Started'
        CHECK (status IN ('Not Started','In Progress','Submitted','Under Review','Completed','Rejected','Overdue')),
    assessment_status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (assessment_status IN ('Pending','Under Review','Approved','Rejected')),
    assessment_score REAL CHECK (assessment_score IS NULL OR (assessment_score >= 0 AND assessment_score <= 100)),
    remarks          TEXT,
    created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (due_date >= assigned_date)
);

CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    assessor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      TEXT NOT NULL CHECK (status IN ('Pending','Under Review','Approved','Rejected')),
    score       REAL CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    remarks     TEXT,
    assessed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username   TEXT,
    action     TEXT NOT NULL,
    entity     TEXT,
    entity_id  INTEGER,
    details    TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_intern   ON tasks(intern_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due      ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_members_team   ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_assess_task    ON assessments(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_created   ON activity_logs(created_at);
