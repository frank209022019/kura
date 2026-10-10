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
)
