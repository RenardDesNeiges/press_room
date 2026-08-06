"""SQLite persistence layer for the press-room webapp.

Schema:
- users            : username + password hash
- user_files       : per-user readers_interests.md and feeds.yml
- issues           : one row per user per day
- issue_artifacts  : per-issue pipeline outputs (filtered/parsed/prepared/editorial.mp3)
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from config import DEFAULT_DB_PATH, DATA_DIR


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
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
    run_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
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
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Lightweight migration for DBs created before the run_at column.
        cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(issues)").fetchall()
        }
        if "run_at" not in cols:
            conn.execute("ALTER TABLE issues ADD COLUMN run_at TEXT")


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


def get_or_create_issue(
    user_id: int, day: str, db_path: Path = DEFAULT_DB_PATH
) -> int:
    """Return the issue id for a user/day, creating the row if needed.

    ``run_at`` records when the pipeline last ran for this issue.
    """
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM issues WHERE user_id = ? AND day = ?", (user_id, day)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE issues SET run_at = datetime('now','localtime') WHERE id = ?",
                (row["id"],),
            )
            return int(row["id"])
        cursor = conn.execute(
            "INSERT INTO issues (user_id, day) VALUES (?, ?)", (user_id, day)
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


def seed_demo_user(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the demo user 'titou' copying the config/pipeline files from data/."""
    data_dir = DATA_DIR

    with connect(db_path) as conn:
        conn.execute("DELETE FROM users WHERE username = 'titou'")
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("titou", generate_password_hash("titou")),
        )
        user_id = int(cursor.lastrowid)

    files: dict[str, Path] = {
        "readers_interests.md": data_dir / "readers_interests.md",
        "feeds.yml": data_dir / "feeds.yml",
    }
    for name, path in files.items():
        set_user_file(user_id, name, path.read_text(encoding="utf-8"), db_path)

    today = date.today().isoformat()
    issue_id = get_or_create_issue(user_id, today, db_path)

    for stage, filename in (
        ("filtered_entries", "filtered_entries.yml"),
        ("parsed_entries", "parsed_entries.yml"),
        ("prepared_entries", "prepared_entries.yml"),
        ("editorial_mp3", "editorial.mp3"),
    ):
        path = data_dir / filename
        if path.exists():
            content = path.read_bytes()
            set_artifact(issue_id, stage, content, db_path)

    print(f"Seeded demo user 'titou' (issue {today}).")


if __name__ == "__main__":
    init_db()
    seed_demo_user()