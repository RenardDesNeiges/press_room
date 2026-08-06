"""Background daily scheduler for the press-room pipeline.

The webapp starts a daemon thread that waits until the configured local time
each day (config.yml -> schedule.time), then runs the pipeline for each user
listed in schedule.users.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from src.run_pipeline import run_for_user

logger = logging.getLogger(__name__)


def next_run(hour: int, minute: int, now: datetime | None = None) -> datetime:
    """Return the next occurrence of HH:MM (today if still ahead, else tomorrow)."""
    now = now or datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_pipeline_for_all(users: list[str]) -> None:
    """Run the pipeline for every listed user, logging failures without aborting."""
    for username in users:
        try:
            logger.info("Scheduled pipeline run for '%s'", username)
            run_for_user(username)
        except SystemExit as exc:
            logger.error("Scheduled run skipped for '%s': %s", username, exc)
        except Exception:
            logger.exception("Scheduled pipeline run failed for '%s'", username)


def start_daily(users: list[str], hour: int, minute: int) -> threading.Thread:
    """Start a daemon thread that runs the pipeline for ``users`` each day at HH:MM."""
    def loop() -> None:
        while True:
            target = next_run(hour, minute)
            delay = (target - datetime.now()).total_seconds()
            logger.info("Next scheduled pipeline run at %s (in %.0f s)", target, delay)
            time.sleep(delay)
            run_pipeline_for_all(users)

    thread = threading.Thread(target=loop, name="pressroom-daily-pipeline", daemon=True)
    thread.start()
    return thread
