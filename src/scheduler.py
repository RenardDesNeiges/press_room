"""Background daily scheduler for the press-room pipeline.

The webapp starts a daemon thread that waits until the configured local time
each day (config.yml -> schedule.time) in the configured timezone
(config.yml -> schedule.timezone), then runs the pipeline for every user
currently in the database, re-read at each run (so newly-added users are picked
up without restart).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from src import db as database
from src.config import schedule_timezone
from src.run_pipeline import run_for_user

logger = logging.getLogger(__name__)


def next_run(hour: int, minute: int, tz: ZoneInfo, now: datetime | None = None) -> datetime:
    """Return the next occurrence of HH:MM in ``tz`` (today if still ahead, else tomorrow)."""
    tz_now = now.astimezone(tz) if now is not None else datetime.now(tz)
    candidate = tz_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= tz_now:
        candidate += timedelta(days=1)
    return candidate


def scheduled_usernames() -> list[str]:
    return [row["username"] for row in database.list_users()]


def run_pipeline_for_all(users: list[str] | None = None) -> None:
    """Run the pipeline for every listed user, logging failures without aborting."""
    if users is None:
        users = scheduled_usernames()
    for username in users:
        try:
            logger.info("Scheduled pipeline run for '%s'", username)
            run_for_user(username)
        except SystemExit as exc:
            logger.error("Scheduled run skipped for '%s': %s", username, exc)
        except Exception:
            logger.exception("Scheduled pipeline run failed for '%s'", username)


def start_daily(hour: int, minute: int) -> threading.Thread:
    """Start a daemon thread that runs all DB users each day at HH:MM in the schedule timezone."""
    tz = schedule_timezone()

    def loop() -> None:
        while True:
            target = next_run(hour, minute, tz)
            delay = (target - datetime.now(timezone.utc)).total_seconds()
            logger.info(
                "Next scheduled pipeline run at %s %s (in %.0f s)",
                target.strftime("%Y-%m-%d %H:%M"),
                target.tzname(),
                delay,
            )
            time.sleep(delay)
            run_pipeline_for_all()

    thread = threading.Thread(target=loop, name="pressroom-daily-pipeline", daemon=True)
    thread.start()
    return thread
