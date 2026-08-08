"""Tests for src/config.py: the config.yml loader and schedule helpers.

These test ``load_config`` directly (deterministic regardless of the local,
gitignored ``config.yml``) and the schedule helpers via monkeypatched values.
"""

from __future__ import annotations

import src.config as config


def test_load_config_missing(tmp_path):
    assert config.load_config(tmp_path / "nope.yml") == {}


def test_load_config_invalid_yaml(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text(": : : : {[", encoding="utf-8")
    assert config.load_config(path) == {}


def test_load_config_not_a_dict(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert config.load_config(path) == {}


def test_load_config_single_value(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text('words\n', encoding="utf-8")
    assert config.load_config(path) == {}


def test_load_config_valid(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text(
        "paths:\n  db: 'db.sqlite'\nschedule:\n  time: '07:30'\n",
        encoding="utf-8",
    )
    data = config.load_config(path)
    assert data["paths"]["db"] == "db.sqlite"
    assert data["schedule"]["time"] == "07:30"


def test_schedule_clock_valid(monkeypatch):
    monkeypatch.setattr(config, "SCHEDULE_TIME", "06:45")
    assert config.schedule_clock() == (6, 45)


def test_schedule_clock_invalid_falls_back_to_six(monkeypatch):
    monkeypatch.setattr(config, "SCHEDULE_TIME", "garbage")
    assert config.schedule_clock() == (6, 0)


def test_schedule_timezone_valid(monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(config, "SCHEDULE_TIMEZONE", "America/New_York")
    assert config.schedule_timezone().key == "America/New_York"


def test_schedule_timezone_invalid_falls_back_to_paris(monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(config, "SCHEDULE_TIMEZONE", "Mars/Base-1")
    assert config.schedule_timezone() == ZoneInfo("Europe/Paris")