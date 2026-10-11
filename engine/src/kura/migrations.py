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
    # 4. Identification: the titles in the library (TMDB's shows and films, or AniList's entries
    #    without a TMDB key), their episode lists, and what each video is. Scans gain the stages
    #    after reading; SQLite can't change a CHECK, so that table is made again.
    """
    CREATE TABLE titles (
        id         INTEGER PRIMARY KEY,
        kind       TEXT NOT NULL CHECK (kind IN ('series', 'movie', 'ova', 'special')),
        name       TEXT NOT NULL,
        year       INTEGER,
        released   TEXT,     -- first aired, or the film's release: lists sort by it
        tmdb_type  TEXT CHECK (tmdb_type IN ('tv', 'movie')),
        tmdb_id    INTEGER,
        anilist_id INTEGER,  -- the AniList entry it was found by
        airing     INTEGER NOT NULL DEFAULT 0 CHECK (airing IN (0, 1)),
        poster     TEXT,     -- TMDB's image path, or AniList's cover address
        checked_at TEXT,     -- when its episode list was last asked for
        UNIQUE (tmdb_type, tmdb_id)
    ) STRICT;
    CREATE UNIQUE INDEX titles_by_anilist ON titles (anilist_id) WHERE tmdb_id IS NULL;

    CREATE TABLE episodes (
        title_id INTEGER NOT NULL REFERENCES titles (id) ON DELETE CASCADE,
        season   INTEGER NOT NULL,  -- 0 holds the specials
        number   INTEGER NOT NULL,
        name     TEXT,
        aired    TEXT,
        minutes  INTEGER,
        PRIMARY KEY (title_id, season, number)
    ) STRICT, WITHOUT ROWID;

    ALTER TABLE files ADD COLUMN title_id INTEGER REFERENCES titles (id) ON DELETE SET NULL;
    ALTER TABLE files ADD COLUMN anilist_id INTEGER;   -- the AniList entry it matched
    ALTER TABLE files ADD COLUMN season INTEGER;       -- where it sits in its title, numbered
    ALTER TABLE files ADD COLUMN episode INTEGER;      -- as TMDB numbers it; NULL for a film
    ALTER TABLE files ADD COLUMN episode_end INTEGER;  -- the last episode, when it holds several
    ALTER TABLE files ADD COLUMN matched TEXT
        CHECK (matched IN ('sure', 'unsure', 'none', 'extra', 'ignored'));
    ALTER TABLE files ADD COLUMN confidence INTEGER;
    ALTER TABLE files ADD COLUMN guesses TEXT;         -- JSON: the best guesses, for review
    ALTER TABLE files ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1));
    ALTER TABLE files ADD COLUMN identified_at TEXT;   -- NULL while it's still to identify
    CREATE INDEX files_by_title ON files (title_id);

    CREATE TABLE scans_next (
        id          INTEGER PRIMARY KEY,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        state       TEXT NOT NULL CHECK (state IN ('running', 'paused', 'done', 'failed')),
        stage       TEXT NOT NULL CHECK (
                        stage IN ('finding', 'reading', 'identifying', 'checking', 'done')),
        problem     TEXT,
        note        TEXT     -- what the scan couldn't do, though it finished
    ) STRICT;
    INSERT INTO scans_next (id, started_at, finished_at, state, stage, problem)
        SELECT id, started_at, finished_at, state, stage, problem FROM scans;
    DROP TABLE scans;
    ALTER TABLE scans_next RENAME TO scans;
    """,
    # 5. How AniList relates the entries the library has to others (sequel, prequel, film,
    #    side story...): what ties a franchise together.
    """
    CREATE TABLE anilist_links (
        anilist_id INTEGER NOT NULL,  -- an entry Kura matched files to
        related_id INTEGER NOT NULL,  -- an entry AniList relates it to
        relation   TEXT NOT NULL,     -- SEQUEL, PREQUEL, PARENT, SIDE_STORY, ALTERNATIVE, ...
        PRIMARY KEY (anilist_id, related_id)
    ) STRICT, WITHOUT ROWID;
    """,
    # 6. The conversion queue: each file waiting, converting or converted, in the owner's order,
    #    with what it takes to put the original back. A plan says whether it tidied or converted.
    """
    CREATE TABLE jobs (
        id              INTEGER PRIMARY KEY,
        file_id         INTEGER NOT NULL REFERENCES files (id) ON DELETE CASCADE,
        method          TEXT NOT NULL CHECK (method IN ('remux', 'reencode', 'fast', 'best')),
        position        INTEGER NOT NULL,  -- the order the queue takes them in
        state           TEXT NOT NULL DEFAULT 'queued' CHECK (
                            state IN ('queued', 'running', 'replacing', 'done', 'failed',
                                      'skipped', 'restored')),
        added_at        TEXT NOT NULL,
        started_at      TEXT,
        finished_at     TEXT,
        problem         TEXT,              -- why it failed, in words
        plan_id         INTEGER REFERENCES plans (id),  -- the original set aside, the result put
                                                        -- in its place
        source_size     INTEGER,           -- the original as it was, to put it back
        source_modified INTEGER,
        source_probe    TEXT,
        output_size     INTEGER
    ) STRICT;
    CREATE INDEX jobs_by_state ON jobs (state, position);

    ALTER TABLE plans ADD COLUMN kind TEXT NOT NULL DEFAULT 'tidy'
        CHECK (kind IN ('tidy', 'convert'));
    """,
    # 7. The result a conversion made, as ffprobe read it: History says what each file became,
    #    even once its original is back.
    """
    ALTER TABLE jobs ADD COLUMN output_probe TEXT;
    """,
    # 8. When what a change set aside was cleared out of quarantine: after that it can't come back.
    """
    ALTER TABLE changes ADD COLUMN cleared_at TEXT;
    """,
    # 9. Kura's words never name a media server (the owner, 2026-10-11): what earlier tidy-ups
    #    said is put the way it says it now.
    """
    UPDATE plans SET title = REPLACE(title, ' for Plex', '') WHERE title LIKE '% for Plex';
    UPDATE changes SET reason = REPLACE(reason, 'Named for Plex', 'Named and filed')
        WHERE reason LIKE 'Named for Plex%';
    """,
)
