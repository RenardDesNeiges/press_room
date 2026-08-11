"""Tier-1 tests for src/app_log (file + console logging via the root logger).

Pure logic only: no DB, no network. The real repo-root log file is never
touched — ``LOG_FILE_PATH`` is monkeypatched to ``tmp_path`` and the root
logger's handlers are restored afterwards.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import src.app_log


@pytest.fixture
def restore_root_handlers():
    """Record the root logger's handlers and level, restoring them afterwards."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved_handlers:
            root.removeHandler(handler)
            handler.close()
    root.handlers = saved_handlers
    root.setLevel(saved_level)


def _file_handler_count(log_path: Path) -> int:
    root = logging.getLogger()
    name = str(log_path)
    return sum(
        1
        for h in root.handlers
        if getattr(h, "baseFilename", "") and h.baseFilename.endswith(name)
    )


def test_setup_creates_log_file_and_returns_path(tmp_path, monkeypatch, restore_root_handlers):
    log_path = tmp_path / "pressroom.log"
    monkeypatch.setattr(src.app_log, "LOG_FILE_PATH", log_path)

    returned = src.app_log.setup_file_logging()

    assert returned == log_path
    assert log_path.exists()
    logging.getLogger("pressroom.test").warning("boom-123")
    assert "boom-123" in log_path.read_text(encoding="utf-8")


def test_setup_is_idempotent_for_file_handler(
    tmp_path, monkeypatch, restore_root_handlers
):
    log_path = tmp_path / "pressroom.log"
    monkeypatch.setattr(src.app_log, "LOG_FILE_PATH", log_path)

    src.app_log.setup_file_logging()
    src.app_log.setup_file_logging()

    assert _file_handler_count(log_path) == 1