"""Run the full press-room pipeline for a single user, storing results in SQLite.

Usage:
    python run_pipeline.py --user titou
    python run_pipeline.py --user titou --day 2026-08-06

Pipeline stages per user/day:
  1. Scrape RSS feeds          -> filtered_entries
  2. Rank, rerank, translate   -> parsed_entries
  3. Write editorial + sections-> prepared_entries
  4. Synthesize editorial MP3  -> editorial.mp3

All artifacts are written to the database, keyed by (user, day).
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src import db as database
from src import editorial_to_mp3, feed_reader, parse_feed, prepare_entries
from src.feed_reader import make_eid


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs: dict[str, Any] = {"encoding": "utf-8"} if mode == "w" else {}
    with open(path, mode, **kwargs) as fh:
        fh.write(content)


def run_for_user(username: str, day: str | None = None) -> dict[str, Any]:
    """Run the pipeline for a user and persist artifacts to the database."""
    user = database.get_user(username)
    if user is None:
        raise SystemExit(f"Unknown user: {username}. Create it first (see db.py).")

    user_id = user["id"]
    day = day or date.today().isoformat()
    try:
        editorial_minutes = user["editorial_minutes"]
    except (KeyError, IndexError):
        editorial_minutes = 5

    feeds = database.get_user_file(user_id, "feeds.yml")
    interests = database.get_user_file(user_id, "readers_interests.md")
    if feeds is None or interests is None:
        raise SystemExit(
            f"User '{username}' is missing feeds.yml/readers_interests.md in the database."
        )

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        feeds_path = work / "feeds.yml"
        interests_path = work / "readers_interests.md"
        _write(feeds_path, feeds)
        _write(interests_path, interests)

        filtered_path = work / "filtered_entries.yml"
        parsed_path = work / "parsed_entries.yml"
        prepared_path = work / "prepared_entries.yml"
        mp3_path = work / "editorial.mp3"

        print(f"\n>>> Running pipeline for '{username}' ({day})")
        run_stamp = datetime.now()

        def eid_factory(seq: int) -> str:
            return make_eid(username, run_stamp, seq)

        feed_reader.scrape_feeds(
            feeds_path=feeds_path,
            output_path=filtered_path,
            default_today_only=(database.get_filter_mode(user_id) == "today"),
            eid_factory=eid_factory,
        )
        parse_feed.parse_and_export(
            entries_path=filtered_path,
            output_path=parsed_path,
            interests_path=interests_path,
        )
        prepare_entries.prepare_and_export(
            parsed_entries_path=parsed_path,
            output_path=prepared_path,
            interests_path=interests_path,
            editorial_minutes=editorial_minutes,
        )
        editorial_to_mp3.generate_editorial_mp3(
            parsed_entries_path=prepared_path, output_path=mp3_path
        )

        issue_id = database.get_or_create_issue(user_id, day)
        database.set_artifact(issue_id, "filtered_entries", filtered_path.read_bytes())
        database.set_artifact(issue_id, "parsed_entries", parsed_path.read_bytes())
        database.set_artifact(issue_id, "prepared_entries", prepared_path.read_bytes())
        if mp3_path.exists():
            database.set_artifact(issue_id, "editorial_mp3", mp3_path.read_bytes())

        for name in database.SOURCE_FILES:
            content = database.get_user_file(user_id, name)
            if content:
                database.set_artifact(issue_id, name, content.encode("utf-8"))
        database.set_pipeline_version(issue_id, 1)

    print(f"\nStored all artifacts for '{username}' / {day} in the database.")
    return {"user": username, "day": day, "issue_id": issue_id}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run the press-room pipeline for one user.")
    parser.add_argument("--user", type=str, default="titou", help="Username to run for.")
    parser.add_argument(
        "--day",
        type=str,
        default=None,
        help="ISO date for the issue (default: today).",
    )
    args = parser.parse_args()
    database.init_db()
    run_for_user(username=args.user, day=args.day)


if __name__ == "__main__":
    main()