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
)
