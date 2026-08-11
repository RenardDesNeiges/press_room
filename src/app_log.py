"""File-backed logging for the press-room.

``setup_file_logging`` configures the root logger to append to
``PROJECT_ROOT/pressroom.log`` and mirror records to the console. It is
idempotent: calling it repeatedly never stacks duplicate handlers, so it is safe
to call from every entry point (webapp, CLI, scheduler thread).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import PROJECT_ROOT

LOG_FILE_PATH: Path = PROJECT_ROOT / "pressroom.log"

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _targets_file(handler: logging.Handler, path: Path) -> bool:
    base = getattr(handler, "baseFilename", None)
    return base is not None and Path(base) == path


def setup_file_logging(level: int = logging.INFO) -> Path:
    """Configure the root logger to write to LOG_FILE_PATH and the console.

    Does nothing twice: if the root logger already has a file handler on
    LOG_FILE_PATH (and a stream handler), it only ensures the level is set.
    Returns LOG_FILE_PATH.
    """
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    if not any(_targets_file(h, LOG_FILE_PATH) for h in root.handlers):
        file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
        root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)
        )
        root.addHandler(stream_handler)

    return LOG_FILE_PATH


if __name__ == "__main__":
    setup_file_logging()
    logging.getLogger(__name__).info("File logging initialized at %s", LOG_FILE_PATH)