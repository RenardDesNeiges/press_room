"""SQLite persistence layer for the press-room webapp.

Schema:
- users            : username + password hash
- user_files       : per-user readers_interests.md and feeds.yml
- issues           : one row per user per day
- issue_artifacts  : per-issue pipeline outputs (filtered/parsed/editorial/editorial.mp3)
- prepared_entries : per-issue prepared articles, one row per EID
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from werkzeug.security import check_password_hash, generate_password_hash

from src.config import (
    DEFAULT_DB_PATH,
    DATA_DIR,
    DEFAULT_EXCLUDED_DOMAINS,
    schedule_now,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    editorial_minutes INTEGER NOT NULL DEFAULT 5,
    excluded_domains TEXT,
    filter_mode TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    pipeline_version INTEGER NOT NULL DEFAULT 0,
    run_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, day)
);

CREATE TABLE IF NOT EXISTS issue_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(issue_id, stage)
);

CREATE TABLE IF NOT EXISTS prepared_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    eid TEXT NOT NULL,
    data TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    media TEXT,
    url TEXT,
    date TEXT,
    lang TEXT,
    author TEXT,
    source TEXT,
    similarity_score REAL,
    rerank_reason TEXT,
    theme TEXT,
    country TEXT,
    section TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(issue_id, eid)
);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Lightweight migrations for DBs created before a column existed.
        issue_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(issues)").fetchall()
        }
        if "run_at" not in issue_cols:
            conn.execute("ALTER TABLE issues ADD COLUMN run_at TEXT")
        if "pipeline_version" not in issue_cols:
            conn.execute(
                "ALTER TABLE issues ADD COLUMN pipeline_version "
                "INTEGER NOT NULL DEFAULT 0"
            )
        user_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "editorial_minutes" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN editorial_minutes "
                "INTEGER NOT NULL DEFAULT 5"
            )
        if "excluded_domains" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN excluded_domains TEXT"
            )
        if "filter_mode" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN filter_mode TEXT"
            )
        if "is_admin" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
        prepared_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(prepared_entries)").fetchall()
        }
        for col, ddl in PREPARED_COLUMNS_DDL.items():
            if col not in prepared_cols:
                conn.execute(f"ALTER TABLE prepared_entries ADD COLUMN {ddl}")

    # Backwards compatibility: archive each user's feeds.yml / readers file onto
    # every past issue that never archived them (source files were only stored in
    # user_files before pipeline_version=1).
    backfill_issue_source_files(db_path)
    backfill_issue_editorials(db_path)
    # v0 issues stay blob-only; drop any legacy integer-EID rows that a prior
    # migration wrote into the relational table.
    discard_legacy_prepared_eids(db_path)


def create_user(username: str, password: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Create a user and return its id. Raises if the username exists."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        return int(cursor.lastrowid)


def get_user(username: str, db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def verify_user(username: str, password: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    user = get_user(username, db_path)
    if user is None:
        return False
    return check_password_hash(user["password_hash"], password)


def update_username(user_id: int, new_username: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Rename a user. Raises IntegrityError if the new username already exists."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET username = ? WHERE id = ?", (new_username, user_id)
        )


def update_password(user_id: int, new_password: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Set a new password hash for a user."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )


def set_user_file(
    user_id: int, name: str, content: str, db_path: Path = DEFAULT_DB_PATH
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_files (user_id, name, content) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, name) DO UPDATE SET content = excluded.content, "
            "updated_at = datetime('now')",
            (user_id, name, content),
        )


def get_user_file(
    user_id: int, name: str, db_path: Path = DEFAULT_DB_PATH
) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT content FROM user_files WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        return row["content"] if row else None


def list_user_files(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> dict[str, str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name, content FROM user_files WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {row["name"]: row["content"] for row in rows}


def list_users(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM users ORDER BY username").fetchall()


def get_user_by_id(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def user_is_admin(user: sqlite3.Row | None) -> bool:
    """Return True if a users row carries the admin flag.

    Missing/old rows (DB not yet migrated) are treated as non-admin.
    """
    if user is None:
        return False
    try:
        return bool(user["is_admin"])
    except (KeyError, IndexError, TypeError):
        return False


def is_admin_user(username: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Return True if the given username exists with admin rights."""
    return user_is_admin(get_user(username, db_path))


def set_admin(
    username: str, is_admin: bool = True, db_path: Path = DEFAULT_DB_PATH
) -> bool:
    """Grant or revoke admin rights for a user. Returns True if updated."""
    flag = 1 if is_admin else 0
    with connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE users SET is_admin = ? WHERE username = ?", (flag, username)
        )
    return cursor.rowcount > 0


def delete_user(username: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Remove a user and (cascade) its files/issues/artifacts. Returns True if removed."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
    return cursor.rowcount > 0


def list_users_with_counts(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    """All users plus a ``run_count`` of issues (pipeline runs) each has."""
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT u.id, u.username, u.is_admin, u.created_at, "
            "(SELECT COUNT(*) FROM issues i WHERE i.user_id = u.id) AS run_count "
            "FROM users u ORDER BY u.username"
        ).fetchall()


def get_editorial_minutes(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Return the target editorial read time (minutes, clamped 2-10)."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT editorial_minutes FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    minutes = int(row["editorial_minutes"]) if row else 5
    return max(2, min(10, minutes))


def set_editorial_minutes(user_id: int, minutes: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET editorial_minutes = ? WHERE id = ?",
            (max(2, min(10, int(minutes))), user_id),
        )


def get_excluded_domains(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """Return the user's archive.ph-excluded domains.

    Falls back to the built-in default list when the user has never set their
    own (retroactive compatibility for pre-existing accounts).
    """
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT excluded_domains FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or row["excluded_domains"] is None:
        return sorted(DEFAULT_EXCLUDED_DOMAINS)
    domains = [
        d.strip()
        for d in row["excluded_domains"].splitlines()
        if d.strip()
    ]
    return domains


def set_excluded_domains(user_id: int, domains: list[str], db_path: Path = DEFAULT_DB_PATH) -> None:
    """Store the user's archive.ph-excluded domains (one per line).

    Passing an empty list clears the exclusions entirely (nothing is excluded).
    """
    cleaned = [d.strip() for d in domains if d.strip()]
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET excluded_domains = ? WHERE id = ?",
            ("\n".join(cleaned), user_id),
        )


def get_filter_mode(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> str:
    """Return the user's article date filter mode: "24h" or "today".

    Defaults to "24h" (the classic "less than X times old" window) when the user
    has never set their own preference.
    """
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT filter_mode FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["filter_mode"] if row and row["filter_mode"] == "today" else "24h"


def set_filter_mode(user_id: int, mode: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Store the user's article date filter mode ("24h" or "today")."""
    if mode == "today":
        value = "today"
    else:
        value = None
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET filter_mode = ? WHERE id = ?", (value, user_id)
        )


def seed_default_files(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Copy the demo feeds.yml and readers_interests.md into a user's config files."""
    for name in ("feeds.yml", "readers_interests.md"):
        path = DATA_DIR / name
        if path.exists():
            set_user_file(user_id, name, path.read_text(encoding="utf-8"), db_path)


def get_or_create_issue(
    user_id: int, day: str, db_path: Path = DEFAULT_DB_PATH
) -> int:
    """Return the issue id for a user/day, creating the row if needed.

    ``run_at`` records when the pipeline last ran for this issue.
    """
    run_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM issues WHERE user_id = ? AND day = ?", (user_id, day)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE issues SET run_at = ? WHERE id = ?", (run_at, row["id"])
            )
            return int(row["id"])
        cursor = conn.execute(
            "INSERT INTO issues (user_id, day, run_at) VALUES (?, ?, ?)",
            (user_id, day, run_at),
        )
        return int(cursor.lastrowid)


def set_artifact(
    issue_id: int, stage: str, content: bytes, db_path: Path = DEFAULT_DB_PATH
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO issue_artifacts (issue_id, stage, content) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(issue_id, stage) DO UPDATE SET content = excluded.content, "
            "created_at = datetime('now')",
            (issue_id, stage, content),
        )


def get_artifact(
    issue_id: int, stage: str, db_path: Path = DEFAULT_DB_PATH
) -> bytes | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT content FROM issue_artifacts WHERE issue_id = ? AND stage = ?",
            (issue_id, stage),
        ).fetchone()
        return row["content"] if row else None


def list_issues(user_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    """Return all issues for a user, most recent first."""
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM issues WHERE user_id = ? ORDER BY day DESC", (user_id,)
        ).fetchall()


def latest_issue(
    user_id: int, db_path: Path = DEFAULT_DB_PATH
) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM issues WHERE user_id = ? ORDER BY day DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def get_issue(
    user_id: int, day: str, db_path: Path = DEFAULT_DB_PATH
) -> sqlite3.Row | None:
    """Return the issue row for a user/day, or None."""
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM issues WHERE user_id = ? AND day = ?", (user_id, day)
        ).fetchone()


def set_pipeline_version(
    issue_id: int, version: int, db_path: Path = DEFAULT_DB_PATH
) -> None:
    """Stamp which pipeline version produced an issue (0 = legacy, 1 = current)."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE issues SET pipeline_version = ? WHERE id = ?",
            (int(version), issue_id),
        )


SOURCE_FILES = ("feeds.yml", "readers_interests.md")


def backfill_issue_source_files(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Archive every user's feeds.yml/readers_interests.md onto issues that lack it.

    Before ``pipeline_version`` 1, the source files were only kept in
    ``user_files`` (mutable), never frozen per issue. This copies the *current*
    user file into every issue that has no archived copy, so the admin pipeline
    inspector stays debuggable for historical issues. Returns the written count.
    """
    written = 0
    for user in list_users(db_path):
        for name in SOURCE_FILES:
            content = get_user_file(user["id"], name, db_path)
            if content is None:
                continue
            for issue in list_issues(user["id"], db_path):
                if get_artifact(issue["id"], name, db_path) is None:
                    set_artifact(
                        issue["id"], name, content.encode("utf-8"), db_path
                    )
                    written += 1
    return written


def backfill_issue_editorials(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Promote stored editorials to their own artifact row (pipeline_version 1).

    In pipeline_version 0, the editorial text + headline lived inside the
    ``prepared_entries`` blob. pipeline_version 1 stores them in a dedicated
    ``editorial`` row. Every issue whose ``prepared_entries`` carries a title/
    editorial is upgraded: the editorial row is written (if missing) and the
    issue is stamped ``pipeline_version=1``. Returns the number upgraded.
    """
    upgraded = 0
    for (issue_id,) in _prepared_issue_ids(db_path):
        if get_artifact(issue_id, "editorial", db_path) is not None:
            continue
        try:
            blob = get_artifact(issue_id, "prepared_entries", db_path)
            data = yaml.safe_load(blob.decode("utf-8", errors="replace")) or {}
        except Exception:
            continue
        if data.get("editorial") is None and data.get("title") is None:
            continue
        editorial_yaml = yaml.safe_dump(
            {
                "title": data.get("title"),
                "editorial": data.get("editorial"),
            },
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).encode("utf-8")
        set_artifact(issue_id, "editorial", editorial_yaml, db_path)
        set_pipeline_version(issue_id, 1, db_path)
        upgraded += 1
    return upgraded


def _prepared_issue_ids(db_path: Path) -> list[tuple[int]]:
    """Return the issue ids that store a ``prepared_entries`` artifact."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT issue_id FROM issue_artifacts "
            "WHERE stage = 'prepared_entries'"
        ).fetchall()
    return [(int(row["issue_id"]),) for row in rows]


def list_artifacts(issue_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    """Return (stage, size_bytes, created_at) for every artifact of an issue."""
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT stage, length(content) AS size_bytes, created_at "
            "FROM issue_artifacts WHERE issue_id = ? ORDER BY created_at",
            (issue_id,),
        ).fetchall()


# --- prepared entries (relational layout, pipeline_version 1) -----------------

# Columns that may be added to a pre-existing prepared_entries table.
PREPARED_COLUMNS_DDL = {
    "data": "data TEXT",
    "title": "title TEXT",
    "summary": "summary TEXT",
    "media": "media TEXT",
    "url": "url TEXT",
    "date": "date TEXT",
    "lang": "lang TEXT",
    "author": "author TEXT",
    "source": "source TEXT",
    "similarity_score": "similarity_score REAL",
    "rerank_reason": "rerank_reason TEXT",
    "theme": "theme TEXT",
    "country": "country TEXT",
    "section": "section TEXT",
    "position": "position INTEGER NOT NULL DEFAULT 0",
}

PREPARED_COLUMNS = (
    "eid",
    "data",
    "title",
    "summary",
    "media",
    "url",
    "date",
    "lang",
    "author",
    "source",
    "similarity_score",
    "rerank_reason",
    "theme",
    "country",
    "section",
    "position",
)

# Entry fields whose *text* can be queried/filtered directly (columns in the table).
_QUERY_FIELDS = ("title", "source", "section", "theme", "country", "lang")


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    """Rebuild an entry dict from a prepared_entries row.

    The ``data`` column holds the full original entry (lossless): when present,
    it is parsed and returned as-is. Older/partially-populated rows fall back to
    building the dict from the typed columns.
    """
    raw_data = row["data"]
    if raw_data:
        try:
            stored = yaml.safe_load(raw_data)
            if isinstance(stored, dict):
                entry = dict(stored)
                entry["EID"] = row["eid"]
                return entry
        except (KeyError, ValueError, TypeError):
            pass
    entry: dict[str, Any] = {}
    for col in ("title", "summary", "media", "url", "date", "lang", "author",
                "source", "similarity_score", "rerank_reason", "theme", "country",
                "section"):
        value = row[col]
        if value is not None:
            entry[col] = value
    entry["EID"] = row["eid"]
    return entry


def set_prepared_entries(
    issue_id: int, entries: list[dict[str, Any]], db_path: Path = DEFAULT_DB_PATH
) -> int:
    """Replace all prepared entries of an issue with rows from ``entries``.

    The full original entry dict is kept verbatim in the ``data`` column, and its
    main fields are denormalised into typed columns for query/filter. Each entry
    is keyed by ``(issue_id, eid)`` so a re-run overwrites in place. Returns the
    number of rows written.
    """
    with connect(db_path) as conn:
        conn.execute("DELETE FROM prepared_entries WHERE issue_id = ?", (issue_id,))
        for position, entry in enumerate(entries):
            eid = entry.get("EID")
            data_text = yaml.safe_dump(
                dict(entry), allow_unicode=True, sort_keys=False, default_flow_style=False
            )
            conn.execute(
                "INSERT INTO prepared_entries "
                "(issue_id, eid, data, title, summary, media, url, date, lang, "
                "author, source, similarity_score, rerank_reason, theme, country, "
                "section, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    issue_id,
                    str(eid),
                    data_text,
                    entry.get("title"),
                    entry.get("summary"),
                    entry.get("media"),
                    entry.get("url"),
                    entry.get("date"),
                    entry.get("lang"),
                    entry.get("author"),
                    entry.get("source"),
                    entry.get("similarity_score"),
                    entry.get("rerank_reason"),
                    entry.get("theme"),
                    entry.get("country"),
                    entry.get("section"),
                    position,
                ),
            )
    return len(entries)


def get_prepared_entries(
    issue_id: int, db_path: Path = DEFAULT_DB_PATH
) -> list[dict[str, Any]]:
    """Return all prepared entries of an issue, ordered by their section order."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM prepared_entries WHERE issue_id = ? ORDER BY position, id",
            (issue_id,),
        ).fetchall()
    return [_row_to_entry(row) for row in rows]


def get_prepared_entry(
    issue_id: int, eid: str | int, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any] | None:
    """Return a single prepared entry by EID, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM prepared_entries WHERE issue_id = ? AND eid = ?",
            (issue_id, str(eid)),
        ).fetchone()
    return _row_to_entry(row) if row else None


def count_prepared_entries(issue_id: int, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Return the number of prepared entries stored for an issue."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM prepared_entries WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
    return int(row["n"])


def discard_legacy_prepared_eids(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Delete prepared_entries rows whose EID uses the legacy integer format.

    Current EIDs are strings of the form ``<user>_<date>_<time>_<seq>``. Rows
    keyed by a bare integer EID are leftovers of the v0 pipeline and would
    collide with the contemporary rows of a re-run, so they are dropped. Returns
    the number of rows removed.
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM prepared_entries WHERE eid NOT GLOB '*[^0-9]*'"
        )
        return cursor.rowcount


def _seed_user_account(username: str, password: str, db_path: Path) -> None:
    """(Re)create one demo account with config files and today's seeded issue."""
    data_dir = DATA_DIR

    with connect(db_path) as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        user_id = int(cursor.lastrowid)

    seed_default_files(user_id, db_path)

    today = schedule_now().date().isoformat()
    issue_id = get_or_create_issue(user_id, today, db_path)

    for stage, filename in (
        ("filtered_entries", "filtered_entries.yml"),
        ("parsed_entries", "parsed_entries.yml"),
        ("editorial_mp3", "editorial.mp3"),
    ):
        path = data_dir / filename
        if path.exists():
            content = path.read_bytes()
            set_artifact(issue_id, stage, content, db_path)

    # Archive the seeded source files onto the issue (pipeline_version 1 flow).
    for name in SOURCE_FILES:
        content = get_user_file(user_id, name, db_path)
        if content:
            set_artifact(issue_id, name, content.encode("utf-8"), db_path)

    prepared_path = data_dir / "prepared_entries.yml"
    seeded_entries: list[dict[str, Any]] = []
    if prepared_path.exists():
        try:
            prepared_data = yaml.safe_load(prepared_path.read_text(encoding="utf-8")) or {}
        except Exception:
            prepared_data = {}
        editorial_yaml = yaml.safe_dump(
            {
                "title": prepared_data.get("title"),
                "editorial": prepared_data.get("editorial"),
            },
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).encode("utf-8")
        set_artifact(issue_id, "editorial", editorial_yaml, db_path)
        seeded_entries = prepared_data.get("entries") or []
    if seeded_entries:
        # Demo source files still carry legacy integer EIDs; re-key them to the
        # contemporary <user>_<date>_<seq> shape so they survive the migration
        # that drops integer-keyed rows.
        day_slug = today.replace("-", "")
        for position, entry in enumerate(seeded_entries, start=1):
            eid = entry.get("EID")
            if isinstance(eid, int):
                entry["EID"] = f"{username}_{day_slug}_{position:04d}"
        set_prepared_entries(issue_id, seeded_entries, db_path)
    set_pipeline_version(issue_id, 1, db_path)


def seed_demo_user(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the demo users 'titou' and 'demo_user'.

    Each copies the config/pipeline files from data/ and gets today's seeded
    issue. Grant admin rights with ``set_admin('demo_user')``.
    """
    _seed_user_account("titou", "titou", db_path)
    _seed_user_account("demo_user", "demo_user", db_path)
    print("Seeded demo users 'titou' and 'demo_user' (issue today).")


if __name__ == "__main__":
    init_db()
    seed_demo_user()