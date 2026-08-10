"""Tier-1 tests for app._parse_run_at (pure logic, no DB/network).

``_parse_run_at`` converts an issue's stored ``run_at`` into an aware datetime
in the schedule timezone. Naive stored values (legacy rows / SQLite format)
are treated as UTC; empty or unparsable values fall back to now.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import app as appmod


def _patch_paris(monkeypatch):
    monkeypatch.setattr(appmod, "schedule_timezone", lambda: ZoneInfo("Europe/Paris"))


def test_parse_run_at_aware_iso_converted_to_schedule_tz(monkeypatch):
    _patch_paris(monkeypatch)
    dt = appmod._parse_run_at({"run_at": "2026-08-10T04:06:12+00:00"})
    assert dt.tzinfo is not None
    assert dt.tzinfo.key == "Europe/Paris"
    assert (dt.hour, dt.minute) == (6, 6)


def test_parse_run_at_naive_sqlite_treated_as_utc(monkeypatch):
    _patch_paris(monkeypatch)
    dt = appmod._parse_run_at({"run_at": "2026-08-10 04:06:12"})
    assert dt.tzinfo is not None
    assert dt.hour == 6


def test_parse_run_at_empty_falls_back_to_aware_now(monkeypatch):
    _patch_paris(monkeypatch)
    dt = appmod._parse_run_at({"run_at": ""})
    assert dt.tzinfo is not None


def test_parse_run_at_naive_iso_treated_as_utc(monkeypatch):
    _patch_paris(monkeypatch)
    dt = appmod._parse_run_at({"run_at": "2026-08-10T04:06:12"})
    assert dt.tzinfo is not None
    assert dt.hour == 6