"""The database schema, as an append-only list of migrations.

Migration N upgrades the database from version N-1 to N; the version lives in
SQLite's `PRAGMA user_version`. Never edit a migration once it has shipped in a
release: add a new one at the end instead.
"""

from typing import Final

MIGRATIONS: Final[tuple[str, ...]] = (
    # 1. Settings: Kura's preferences, one JSON value per key.
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL  -- JSON
    ) STRICT;
    """,
    # 2. Plans and their changes: the undo journal for every rename, move and quarantine.
    """
    CREATE TABLE plans (
        id         INTEGER PRIMARY KEY,
        title      TEXT NOT NULL,
        created_at TEXT NOT NULL,
        applied_at TEXT,
        undone_at  TEXT
    ) STRICT;

    CREATE TABLE changes (
        id           INTEGER PRIMARY KEY,
        plan_id      INTEGER NOT NULL REFERENCES plans (id),
        position     INTEGER NOT NULL,
        kind         TEXT NOT NULL CHECK (kind IN ('move', 'quarantine')),
        source       TEXT NOT NULL,
        target       TEXT NOT NULL,
        label        TEXT NOT NULL,
        reason       TEXT NOT NULL,
        state        TEXT NOT NULL DEFAULT 'planned'
                     CHECK (state IN ('planned', 'moving', 'done', 'failed', 'undoing', 'undone')),
        problem      TEXT,
        created_dirs TEXT NOT NULL DEFAULT '[]',  -- JSON: folders this change created
        UNIQUE (plan_id, position)
    ) STRICT;
    """,
    # 3. The library: the folders Kura looks after, every video found in them, and the scans.
    """
    CREATE TABLE folders (
        id       INTEGER PRIMARY KEY,
        path     TEXT NOT NULL UNIQUE COLLATE NOCASE,
        added_at TEXT NOT NULL
    ) STRICT;

    CREATE TABLE files (
        id        INTEGER PRIMARY KEY,
        folder_id INTEGER NOT NULL REFERENCES folders (id) ON DELETE CASCADE,
        path      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        size      INTEGER NOT NULL,
        modified  INTEGER NOT NULL,  -- nanoseconds since 1970, as Windows reports it
        found_at  TEXT NOT NULL,
        seen_at   TEXT NOT NULL,     -- the last scan that found it
        gone_at   TEXT,              -- a later scan didn't find it
        probed_at TEXT,              -- when ffprobe read it; NULL while it's still to read
        probe     TEXT,              -- ffprobe's JSON report
        problem   TEXT,              -- why it couldn't be read, in words
        duration  REAL,              -- seconds
        width     INTEGER,
        height    INTEGER,
        codec     TEXT               -- the picture's codec, such as hevc
    ) STRICT;
    CREATE INDEX files_by_folder ON files (folder_id);

    CREATE TABLE scans (
        id          INTEGER PRIMARY KEY,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        state       TEXT NOT NULL CHECK (state IN ('running', 'paused', 'done', 'failed')),
        stage       TEXT NOT NULL CHECK (stage IN ('finding', 'reading', 'done')),
        problem     TEXT
    ) STRICT;
    """,
)
