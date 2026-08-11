"""Tests for the prepared-entries EID dedup helper (Tier 1: pure logic, no DB).

Importing src.db is safe (it does not open the database at import time).
"""

from __future__ import annotations

from src import db


def test_dedupe_entries_drops_no_eid_and_duplicates():
    entries = [
        {"EID": "a", "title": "1"},
        {"EID": "a", "title": "dup"},
        {"EID": "b", "title": "2"},
        {"EID": None, "title": "no-eid"},
        {"title": "no-eid-2"},
        "not-a-dict",
    ]
    result = db.dedupe_entries(entries)
    assert [e["title"] for e in result] == ["1", "2"]


def test_dedupe_entries_string_vs_int_eid_collapse():
    entries = [
        {"EID": "7", "title": "str"},
        {"EID": 7, "title": "int"},
    ]
    result = db.dedupe_entries(entries)
    assert [e["title"] for e in result] == ["str"]