"""Run the full press-room pipeline for a single user, storing results in SQLite.

Usage:
    python run_pipeline.py --user titou
    python run_pipeline.py --user titou --day 2026-08-06

Pipeline stages per user/day:
  1. Scrape RSS feeds          -> filtered_entries
  2. Rank, rerank, translate   -> parsed_entries
  3. Write sections + news_summary + editorial from plan -> prepared_entries
  4. Synthesize editorial MP3  -> editorial.mp3

All artifacts are written to the database, keyed by (user, day).
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path
from typing import Any

import yaml

from src import db as database
from src import editorial_to_mp3, feed_reader, parse_feed, prepare_entries
from src import telegram as tg
from src.config import schedule_now
from src.feed_reader import make_eid
from src.gen_static_page import format_date_fr

from datetime import datetime

logger = logging.getLogger(__name__)


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
    day = day or schedule_now().date().isoformat()
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
        news_summary_path = work / "news_summary.yml"
        editorial_path = work / "editorial.yml"
        mp3_path = work / "editorial.mp3"

        print(f"\n>>> Running pipeline for '{username}' ({day})")
        run_stamp = schedule_now()

        def eid_factory(seq: int) -> str:
            return make_eid(username, run_stamp, seq)

        feed_reader.scrape_feeds(
            feeds_path=feeds_path,
            output_path=filtered_path,
            default_today_only=(database.get_filter_mode(user_id) == "today"),
            eid_factory=eid_factory,
        )
        parsed_entries = parse_feed.parse_and_export(
            entries_path=filtered_path,
            output_path=parsed_path,
            interests_path=interests_path,
        )
        if not parsed_entries:
            raise SystemExit(
                f"No articles parsed for '{username}' ({day}) — aborting pipeline run."
            )
        prepare_entries.prepare_sections_and_export(parsed_path, prepared_path)
        prepare_entries.plan_and_export(prepared_path, news_summary_path, interests_path)
        prepare_entries.editorial_from_plan_and_export(
            news_summary_path,
            editorial_path,
            prepared_path,
            interests_path,
            editorial_minutes=editorial_minutes,
        )
        editorial_to_mp3.generate_editorial_mp3(
            parsed_entries_path=editorial_path, output_path=mp3_path
        )

        artifacts = {
            "filtered_entries": filtered_path.read_bytes(),
            "parsed_entries": parsed_path.read_bytes(),
            "prepared_entries": prepared_path.read_bytes(),
            "news_summary": news_summary_path.read_bytes(),
            "editorial": editorial_path.read_bytes(),
        }
        if mp3_path.exists():
            artifacts["editorial_mp3"] = mp3_path.read_bytes()

        prepared_data = yaml.safe_load(prepared_path.read_bytes()) or {}
        seeded_entries = prepared_data.get("entries") or []

        source_files = {}
        for name in database.SOURCE_FILES:
            content = database.get_user_file(user_id, name)
            if content:
                source_files[name] = content

        issue_id = database.persist_issue_run(
            user_id,
            day,
            artifacts=artifacts,
            prepared_entries_data=seeded_entries,
            source_files=source_files,
        )
        _notify_telegram(user_id, issue_id, day)

    print(f"\nStored all artifacts for '{username}' / {day} in the database.")
    return {"user": username, "day": day, "issue_id": issue_id}


def _notify_telegram(user_id, issue_id, day) -> None:

    day_fr = format_date_fr(datetime.strptime(day,"%Y-%m-%d"))

    if not database.telegram_enabled(user_id):
        return
    cfg = database.get_telegram_config(user_id)
    try:
        blob = database.get_artifact(issue_id, "editorial_mp3")
        editorial_blob = database.get_artifact(issue_id, "editorial")
        prepared_entries_blob = database.get_artifact(issue_id, "prepared_entries")
        if editorial_blob:
            try:
                title = (yaml.safe_load(editorial_blob.decode("utf-8", errors="replace")) or {}).get("title") or ""
            except Exception:
                title = ""
            try:
                edito = (yaml.safe_load(editorial_blob.decode("utf-8", errors="replace")) or {}).get("editorial") or ""
            except Exception:
                edito = ""
        if prepared_entries_blob:
            try:
                title = (yaml.safe_load(editorial_blob.decode("utf-8", errors="replace")) or {}).get("title") or ""
            except Exception:
                title = ""
            try:
                entries = (yaml.safe_load(prepared_entries_blob.decode("utf-8", errors="replace")) or {}).get("entries") or ""
            except Exception:
                entries = ""
            try:
                media = [e['media'] for e in entries if e['media'] is not None][0]
            except:
                media = None
        if blob:
            caption = f"_{title}_\n\nL'édition _Pressroom_ du {day_fr} est prête\.\n\n_{edito[:1000].replace('.','\.').replace('-','\-')}_\.\.\."
            tg.send_audio(cfg["token"], cfg["chat_id"], blob, 
                            filename="editorial.mp3",
                            caption=caption,
                            media = media,
                            link={
                                "text": "Lire l'édition complète",
                                "url": "http://press-room.ch",
                                }
                          )
        else:
            tg.send_text(cfg["token"], cfg["chat_id"], caption=caption)
    except Exception:
        logger.exception("Telegram notification failed for issue %s", issue_id)


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
