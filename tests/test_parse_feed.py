"""Tests for src/parse_feed.py (Tier 1: pure selection/translation logic)."""

from __future__ import annotations

from src import parse_feed


# --- diversify_by_source ----------------------------------------------------

def test_diversify_caps_per_source():
    ranked = [
        {"EID": 1, "source": "A"},
        {"EID": 2, "source": "A"},
        {"EID": 3, "source": "A"},
        {"EID": 4, "source": "B"},
        {"EID": 5, "source": "B"},
    ]
    out = parse_feed.diversify_by_source(ranked, target_count=10, max_per_source=2)
    assert [e["EID"] for e in out] == [1, 2, 4, 5]


def test_diversify_preserves_order():
    ranked = [
        {"EID": 1, "source": "B"},
        {"EID": 2, "source": "A"},
        {"EID": 3, "source": "A"},
    ]
    out = parse_feed.diversify_by_source(ranked, target_count=10, max_per_source=1)
    assert [e["EID"] for e in out] == [1, 2]


def test_diversify_stops_at_target():
    ranked = [
        {"EID": 1, "source": "A"},
        {"EID": 2, "source": "B"},
        {"EID": 3, "source": "C"},
    ]
    out = parse_feed.diversify_by_source(ranked, target_count=2, max_per_source=10)
    assert [e["EID"] for e in out] == [1, 2]


def test_diversify_default_source_unknown():
    ranked = [{"EID": 1}, {"EID": 2}, {"EID": 3}]
    out = parse_feed.diversify_by_source(ranked, target_count=10, max_per_source=2)
    assert [e["EID"] for e in out] == [1, 2]


# --- translate_entry ---------------------------------------------------------

def test_non_french_entry_translates_all_text_fields(monkeypatch):
    calls = []

    def fake_query(prompt, model_name=None, temperature=0.2):
        calls.append(prompt)
        return "TRADUIT"

    monkeypatch.setattr(parse_feed, "query_model", fake_query)
    entry = {
        "title": "Hello",
        "summary": "A summary.",
        "rerank_reason": "Important story.",
        "lang": "DE",
    }
    out = parse_feed.translate_entry(entry, model_name="test-model")
    assert out["title"] == "TRADUIT"
    assert out["summary"] == "TRADUIT"
    assert out["rerank_reason"] == "TRADUIT"
    assert out["lang"] == "FR"
    assert len(calls) == 3


def test_french_entry_translates_reason_only(monkeypatch):
    calls = []

    def fake_translate(prompt, model_name=None, temperature=0.2):
        calls.append(prompt)
        return "RAISON TRADUITE"

    monkeypatch.setattr(parse_feed, "query_model", fake_translate)
    entry = {
        "title": "Titre français",
        "summary": "Résumé.",
        "rerank_reason": "English reason.",
        "lang": "FR",
    }
    out = parse_feed.translate_entry(entry, model_name="test-model")
    assert out["title"] == "Titre français"
    assert out["summary"] == "Résumé."
    assert out["rerank_reason"] == "RAISON TRADUITE"
    assert out["lang"] == "FR"
    assert len(calls) == 1


def test_translate_entry_ignores_empty_fields(monkeypatch):
    def fake_translate(prompt, model_name=None, temperature=0.2):
        return "X"

    monkeypatch.setattr(parse_feed, "query_model", fake_translate)
    entry = {"title": "", "summary": None, "rerank_reason": "", "lang": "EN", "url": "http://x"}
    out = parse_feed.translate_entry(entry)
    assert out["title"] == ""
    assert out["summary"] is None
    assert out["rerank_reason"] == ""
    assert out["url"] == "http://x"
    assert out["lang"] == "FR"


def test_input_entry_is_not_mutated(monkeypatch):
    monkeypatch.setattr(parse_feed, "query_model", lambda *a, **k: "TRADUIT")
    entry = {"title": "T", "lang": "EN"}
    before = dict(entry)
    parse_feed.translate_entry(entry)
    assert entry == before