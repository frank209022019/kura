# SQLite (Kura's database)

Everything Kura knows lives in one [SQLite](https://sqlite.org) file, `kura.db`, in the data folder.
There is no database server: Python's built-in `sqlite3` module opens the file directly. One file is
easy to back up, export, move to another drive, and open with any SQLite tool.

## Files

| File | What it holds |
| --- | --- |
| `kura/db.py` | `connect()`, `migrate()`, `schema_version()` |
| `kura/migrations.py` | The schema, as an append-only list of SQL scripts |
| `kura/export.py` | The export zip, which includes a consistent copy of the database |

## Connecting

`db.connect(path)` opens the database the way Kura always uses it:

- `journal_mode = WAL`: readers keep working while a write happens, and a crash can't corrupt the
  file.
- `foreign_keys = ON`: relationships are enforced.
- `busy_timeout = 5000`: a writer waits up to five seconds for another instead of failing.
- Rows come back as `sqlite3.Row` (by name: `row["key"]`).

The API opens one connection per request (the `Database` dependency) and closes it afterwards.
Connections may move between threads but are never shared by two at once.

Write in transactions: `with conn: conn.execute(...)` commits on success and rolls back on error.
Always pass values as parameters (`?`), never with f-strings.

## Migrations

The schema version is SQLite's `PRAGMA user_version`. `migrations.py` holds `MIGRATIONS`, a tuple of
SQL scripts: script 1 takes a new database to version 1, script 2 to version 2, and so on.
`migrate()` runs the missing ones in order, each inside its own transaction, so a failure leaves the
database exactly as it was. A database newer than the running Kura is refused with a clear message
rather than touched.

To change the schema, append a script; never edit one that has shipped in a release. Use `STRICT`
tables, give every table a primary key, and add the new data to the export.

## The tables

| Table | Since | Holds |
| --- | --- | --- |
| `settings` | 1 | Kura's preferences: one JSON value per key |
| `plans` | 2 | Tidy-up plans: a title, and when each was made, applied and undone |
| `changes` | 2 | The undo journal: each plan's moves and quarantines in order, with their state (`planned`, `moving`, `done`, `failed`, `undoing`, `undone`), any problem, and the folders each one created |
| `folders` | 3 | The library folders, unique whatever their case |
| `files` | 3, 4 | Every video a scan found: its folder, path, size and time (to notice changes), when it was found, last seen and gone, and once read, ffprobe's JSON report with the duration, size and codec at a glance, or why it couldn't be read. Since 4, what it is: its title, the AniList entry it matched, its season and episode as TMDB numbers them, how sure Kura is (`sure`, `unsure`, `none`, `extra`, `ignored`) with the best guesses for review, and whether the owner pinned it |
| `scans` | 3, 4 | Each scan: when it started and finished, its state (`running`, `paused`, `done`, `failed`), its stage (`finding`, `reading`, `identifying`, `checking`, `done`), any problem, and a note on what it couldn't do though it finished |
| `titles` | 4 | Each anime and film in the library: its kind (`series`, `movie`, `ova`, `special`), name, year and release date (lists sort by it), its TMDB show or film and the AniList entry it was found by, whether it's airing, its poster, and when its episode list was last asked for |
| `episodes` | 4 | Each title's episode list, from TMDB (or AniList's count without a key): season (0 for the specials), number, name, air date and length |

The queue and history come with the features that need them.

## Backups and export

- Consistent copies use SQLite's backup API (`source.backup(copy)`), never a file copy of a database
  in use. The export does this; nightly backups (keep 7) will too.
- The exported `kura.db` is switched to `journal_mode = DELETE`, so it is one self-contained file.

## Looking inside

```powershell
cd engine; uv run python -c "import sqlite3; print(sqlite3.connect('.dev-data/kura.db').execute('select * from settings').fetchall())"
```

Or open `kura.db` in any SQLite browser while Kura isn't writing.
