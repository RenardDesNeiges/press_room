"""Tests for src/translate.py (Tier 1: pure / lightly mocked translation logic)."""

from __future__ import annotations

import pytest

from src import translate as translate_mod
from src.translate import build_readers_interests, normalize_language, translate


# --- normalize_language -----------------------------------------------------

def test_normalize_language_canonical_codes():
    assert normalize_language("fr") == "fr"
    assert normalize_language("en") == "en"
    assert normalize_language("es") == "es"
    assert normalize_language("de") == "de"


def test_normalize_language_aliases():
    assert normalize_language("français") == "fr"
    assert normalize_language("francais") == "fr"
    assert normalize_language("french") == "fr"
    assert normalize_language("espagnol") == "es"
    assert normalize_language("español") == "es"
    assert normalize_language("spanish") == "es"
    assert normalize_language("deutsch") == "de"
    assert normalize_language("allemand") == "de"
    assert normalize_language("german") == "de"


def test_normalize_language_is_case_and_whitespace_tolerant():
    assert normalize_language("ENGLISH") == "en"
    assert normalize_language("  Français  ") == "fr"
    assert normalize_language(" De") == "de"


def test_normalize_language_unknown_raises():
    with pytest.raises(ValueError):
        normalize_language("klingon")


# --- translate --------------------------------------------------------------

def test_translate_returns_input_for_empty_text():
    assert translate("", "en") == ""
    assert translate(None, "en") is None


def test_translate_returns_input_for_whitespace_text():
    assert translate("   \n\t ", "es") == "   \n\t "


def test_translate_forwards_model_and_temperature(monkeypatch):
    calls = []

    def fake_query(prompt, model_name=None, temperature=0.2):
        calls.append((model_name, temperature))
        return "  Translated output.  "

    monkeypatch.setattr(translate_mod, "query_model", fake_query)
    out = translate("Bonjour", "en", model_name="test-model", temperature=0.5)
    assert out == "Translated output."
    assert calls == [("test-model", 0.5)]


# --- build_readers_interests ------------------------------------------------

def test_build_readers_interests_layout(monkeypatch):
    def fake_translate(text, target_language, **kwargs):
        return f"{target_language}:{text}"

    monkeypatch.setattr(translate_mod, "translate", fake_translate)
    source = "Premier paragraphe."
    out = build_readers_interests(source)

    assert out.startswith(f"Français\n\n{source}")
    assert "\n\n-----\n\nEnglish\n\nen:Premier paragraphe." in out
    assert "\n\n-----\n\nEspañol\n\nes:Premier paragraphe." in out
    assert "\n\n-----\n\nDeutsch\n\nde:Premier paragraphe." in out
    assert out.count("\n\n-----\n\n") == 3
    assert out.endswith("de:Premier paragraphe.")
    assert source in out


def test_build_readers_interests_requests_only_target_languages(monkeypatch):
    requested = []

    def fake_translate(text, target_language, **kwargs):
        requested.append(target_language)
        return f"{target_language}:{text}"

    monkeypatch.setattr(translate_mod, "translate", fake_translate)
    build_readers_interests("Un texte source.")

    assert requested == ["en", "es", "de"]


def test_build_readers_interests_trims_after_separator(monkeypatch):
    def fake_translate(text, target_language, **kwargs):
        return f"{target_language}:{text}"

    monkeypatch.setattr(translate_mod, "translate", fake_translate)
    out = build_readers_interests("Première partie.\n\n-----\n\nEnglish\n\nDéjà traduit.")
    assert out.startswith("Français\n\nPremière partie.")
    assert "Déjà traduit." not in out
    assert "en:Première partie." in out


def test_build_readers_interests_empty_input_returns_empty():
    assert build_readers_interests("") == ""
    assert build_readers_interests("   \n  ") == ""
    assert build_readers_interests("-----") == ""